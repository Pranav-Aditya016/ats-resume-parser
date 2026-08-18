"""Batch CLI for the provider-neutral ATS resume parser.

Each resume moves through two stages: transcription to Markdown
(`ats_parser.text_extraction`), then structure extraction (`ats_parser.providers`).
The intermediate Markdown is persisted, so it can be audited, reused across reruns,
and indexed by downstream tooling.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from ats_parser.exporters import export_records
from ats_parser.markdown_store import markdown_path, read_markdown, write_markdown
from ats_parser.providers import create_provider
from ats_parser.text_extraction import SUPPORTED_EXTENSIONS, create_extractor


def configure_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(output_dir / "parser.log", encoding="utf-8"),
        ],
    )


def input_files(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Resume folder not found: {input_dir}")
    return sorted(
        (path for path in input_dir.iterdir()
         if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda path: path.name.lower(),
    )


def atomic_json_write(path: Path, record: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def existing_record(path: Path) -> dict | None:
    """Return a previously completed record, ignoring partial or invalid files."""
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def source_markdown(file_path: Path, document_path: Path, extractor, reuse: bool) -> tuple[str, bool]:
    """Return the resume's Markdown and whether it came from an earlier run."""
    if reuse:
        cached = read_markdown(document_path)
        if cached is not None:
            return cached, True
    extracted = extractor.extract(file_path)
    write_markdown(document_path, file_path, extracted)
    return extracted.markdown, False


def run(
    input_dir: Path,
    output_dir: Path,
    provider_name: str,
    model: str,
    retries: int = 2,
    retry_delay_seconds: float = 3.0,
    resume: bool = False,
) -> int:
    configure_logging(output_dir)
    logger = logging.getLogger("resume_parser")
    files = input_files(input_dir)
    if not files:
        raise FileNotFoundError(f"No supported resumes found in {input_dir}")
    extractor = create_extractor(provider_name, model)
    provider = create_provider(provider_name, model)
    records, failures = [], []
    per_resume_metrics = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    start_time = time.perf_counter()
    for index, file_path in enumerate(files, start=1):
        logger.info("[%s/%s] Parsing %s", index, len(files), file_path.name)
        record_path = output_dir / f"{file_path.stem}.json"
        document_path = markdown_path(output_dir, file_path)
        if resume:
            record = existing_record(record_path)
            if record is not None:
                logger.info("[%s/%s] Skipping completed resume: %s", index, len(files), file_path.name)
                records.append((file_path.name, record))
                continue
        try:
            attempt_call = _retrying(logger, file_path.name, retries, retry_delay_seconds)
            # The two stages retry independently, so a failed extraction never
            # re-runs OCR that has already succeeded and been written to disk.
            text, reused = attempt_call(
                lambda: source_markdown(file_path, document_path, extractor, resume)
            )
            record = attempt_call(lambda: provider.parse(text))
            if reused:
                logger.info("[%s/%s] Reused extracted Markdown: %s", index, len(files), document_path.name)
            atomic_json_write(record_path, record)
            usage = _combined_usage(extractor if not reused else None, provider)
            cost = _combined_cost(extractor if not reused else None, provider)
            latency = getattr(provider, "last_response_latency_seconds", None)
            if usage:
                total_prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
                total_completion_tokens += int(usage.get("completion_tokens", 0) or 0)
                total_tokens += int(usage.get("total_tokens", 0) or 0)
            per_resume_metrics.append({
                "file": file_path.name,
                "processing_time_seconds": latency,
                "usage": usage,
                "estimated_cost_usd": cost,
                "markdown_file": str(document_path.relative_to(output_dir)),
                "markdown_reused": reused,
            })
            if usage or cost is not None:
                atomic_json_write(
                    output_dir / f"{file_path.stem}.usage.json",
                    {
                        "file": file_path.name,
                        "provider": provider_name,
                        "model": model,
                        "usage": usage,
                        "estimated_cost_usd": cost,
                    },
                )
            records.append((file_path.name, record))
        except Exception as exc:
            logger.exception("Failed to parse %s", file_path.name)
            failures.append({"file": file_path.name, "error": str(exc)})
    total_execution_time = round(time.perf_counter() - start_time, 3)
    batch_metrics = {
        "total_execution_time_seconds": total_execution_time,
        "average_processing_time_seconds": round(total_execution_time / max(1, len(files)), 3),
        "successful_parses": len(records),
        "failed_parses": len(failures),
        "retry_count": 0,
        "response_latency_seconds": round(sum(metric.get("processing_time_seconds") or 0 for metric in per_resume_metrics) / max(1, len(per_resume_metrics)), 3),
        "token_usage": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
        },
        "per_resume_metrics": per_resume_metrics,
    }
    atomic_json_write(output_dir / "batch_metrics.json", batch_metrics)
    if records:
        export_records(records, output_dir)
    if failures:
        atomic_json_write(output_dir / "failures.json", {"failures": failures})
        logger.error("Completed with %s failure(s).", len(failures))
        return 1
    logger.info("Completed %s resume(s).", len(records))
    return 0


def _retrying(logger, label: str, retries: int, retry_delay_seconds: float):
    """Return a runner that retries one stage with exponential backoff."""
    def run_stage(action):
        for attempt in range(retries + 1):
            try:
                return action()
            except Exception:
                if attempt == retries:
                    raise
                delay = retry_delay_seconds * (2 ** attempt)
                logger.warning(
                    "%s failed (attempt %s/%s); retrying in %.1f seconds.",
                    label, attempt + 1, retries + 1, delay,
                )
                time.sleep(delay)
    return run_stage


def _combined_usage(*stages) -> dict | None:
    """Sum token usage across the extraction and structuring stages."""
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    seen = False
    for stage in stages:
        usage = getattr(stage, "last_usage", None)
        if not usage:
            continue
        seen = True
        for key in totals:
            totals[key] += int(usage.get(key, 0) or 0)
    return totals if seen else None


def _combined_cost(*stages) -> float | None:
    costs = [getattr(stage, "last_cost_usd", None) for stage in stages]
    present = [cost for cost in costs if cost is not None]
    return round(sum(present), 6) if present else None


def main() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="Batch-parse resumes into ATS JSON, CSV, and Excel.")
    parser.add_argument("--input-dir", type=Path, default=Path("resumes"))
    parser.add_argument("--output-dir", type=Path, default=Path("parsed_resumes"))
    parser.add_argument("--provider", default="gemini", choices=["gemini", "mistral"])
    parser.add_argument(
        "--model",
        default=None,
        help="Override the provider default (GEMINI_MODEL or MISTRAL_MODEL).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retries per failed resume request (default: 2).",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=3.0,
        help="Initial retry delay; it doubles after each retry (default: 3).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse valid JSON records and extracted Markdown already in the output directory.",
    )
    args = parser.parse_args()
    if args.model is None:
        args.model = (
            os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
            if args.provider == "gemini"
            else os.getenv("MISTRAL_MODEL", "mistral-small-latest")
        )
    try:
        if args.retries < 0 or args.retry_delay_seconds < 0:
            parser.error("--retries and --retry-delay-seconds must be non-negative.")
        raise SystemExit(run(
            args.input_dir, args.output_dir, args.provider, args.model,
            retries=args.retries,
            retry_delay_seconds=args.retry_delay_seconds,
            resume=args.resume,
        ))
    except Exception as exc:
        logging.getLogger("resume_parser").error("%s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
