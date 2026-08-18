"""Persistence for extracted resume Markdown.

Each resume gets one `.md` file carrying YAML front matter that records where the text
came from. The front matter makes an extraction auditable, and lets a rerun reuse text
that has already been paid for instead of calling OCR again.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ats_parser.text_extraction import ExtractedText

FRONT_MATTER_FENCE = "---"


def markdown_path(output_dir: Path, source_file: Path) -> Path:
    return output_dir / "markdown" / f"{source_file.stem}.md"


def write_markdown(path: Path, source_file: Path, extracted: ExtractedText) -> None:
    """Write the Markdown document atomically so a crash cannot leave a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = {
        "source_file": source_file.name,
        "extractor": extracted.extractor,
        "model": extracted.model,
        "page_count": extracted.page_count,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    # JSON scalars are valid YAML, so this quotes and escapes every value correctly.
    front_matter = "\n".join(f"{key}: {json.dumps(value)}" for key, value in fields.items())
    document = f"{FRONT_MATTER_FENCE}\n{front_matter}\n{FRONT_MATTER_FENCE}\n\n{extracted.markdown}\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(path)


def read_markdown(path: Path) -> str | None:
    """Return the body of a previously written document, or None if it is unusable."""
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return body_of(text) or None


def body_of(document: str) -> str:
    """Strip YAML front matter, tolerating documents written without it."""
    if not document.startswith(FRONT_MATTER_FENCE):
        return document.strip()
    closing = document.find(f"\n{FRONT_MATTER_FENCE}", len(FRONT_MATTER_FENCE))
    if closing == -1:
        return document.strip()
    return document[closing + len(FRONT_MATTER_FENCE) + 1:].strip()
