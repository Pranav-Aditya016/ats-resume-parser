import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import resume_parser
from ats_parser.text_extraction import ExtractedText


class StubOCR:
    def __init__(self):
        self.calls = []
        self.last_usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        self.last_cost_usd = 0.002

    def extract(self, file_path):
        self.calls.append(file_path.name)
        return ExtractedText(f"# {file_path.stem}\n\nPlanning Engineer", "stub-ocr", "stub-1", 1)


class StubProvider:
    def __init__(self):
        self.seen_text = []
        self.last_usage = {"prompt_tokens": 300, "completion_tokens": 60, "total_tokens": 360}
        self.last_cost_usd = 0.004
        self.last_response_latency_seconds = 0.5

    def parse(self, source_text):
        self.seen_text.append(source_text)
        return {"personal_information": {"full_name": "Test Candidate"}, "skills": {}}


class PipelineMarkdownTests(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.input_dir = root / "resumes"
        self.output_dir = root / "parsed"
        self.input_dir.mkdir()
        (self.input_dir / "candidate.pdf").write_bytes(b"%PDF-1.4")
        self.ocr = StubOCR()
        self.provider = StubProvider()

    def _run(self, resume=False):
        with mock.patch.object(resume_parser, "create_extractor", return_value=_Routed(self.ocr)), \
             mock.patch.object(resume_parser, "create_provider", return_value=self.provider):
            return resume_parser.run(
                self.input_dir, self.output_dir, "stub", "stub-model",
                retries=0, resume=resume,
            )

    def test_markdown_is_written_and_drives_extraction(self):
        exit_code = self._run()

        document = self.output_dir / "markdown" / "candidate.md"
        self.assertEqual(exit_code, 0)
        self.assertTrue(document.is_file())
        text = document.read_text(encoding="utf-8")
        self.assertIn('extractor: "stub-ocr"', text)
        self.assertIn("Planning Engineer", text)
        # The provider must receive the extracted Markdown, not the raw document.
        self.assertEqual(self.provider.seen_text, ["# candidate\n\nPlanning Engineer"])

    def test_rerun_with_resume_reuses_markdown_instead_of_calling_ocr_again(self):
        self._run()
        (self.output_dir / "candidate.json").unlink()  # Force re-extraction of structure only.

        self._run(resume=True)

        self.assertEqual(self.ocr.calls, ["candidate.pdf"])  # OCR ran once, not twice.
        self.assertEqual(len(self.provider.seen_text), 2)

    def test_metrics_record_the_markdown_file_and_combine_stage_usage(self):
        self._run()

        metrics = json.loads((self.output_dir / "batch_metrics.json").read_text(encoding="utf-8"))
        entry = metrics["per_resume_metrics"][0]
        self.assertEqual(entry["markdown_file"], str(Path("markdown") / "candidate.md"))
        self.assertFalse(entry["markdown_reused"])
        # 100 + 300 prompt tokens across the extraction and structuring stages.
        self.assertEqual(entry["usage"]["prompt_tokens"], 400)
        self.assertEqual(entry["usage"]["total_tokens"], 480)
        self.assertAlmostEqual(entry["estimated_cost_usd"], 0.006)

    def test_reused_markdown_is_not_billed_again(self):
        self._run()
        (self.output_dir / "candidate.json").unlink()

        self._run(resume=True)

        metrics = json.loads((self.output_dir / "batch_metrics.json").read_text(encoding="utf-8"))
        entry = metrics["per_resume_metrics"][0]
        self.assertTrue(entry["markdown_reused"])
        self.assertEqual(entry["usage"]["prompt_tokens"], 300)  # Structuring stage only.
        self.assertAlmostEqual(entry["estimated_cost_usd"], 0.004)


class _Routed:
    """Minimal DocumentExtractor stand-in that forwards everything to the stub OCR."""

    def __init__(self, ocr):
        self._ocr = ocr

    def extract(self, file_path):
        return self._ocr.extract(file_path)

    @property
    def last_usage(self):
        return self._ocr.last_usage

    @property
    def last_cost_usd(self):
        return self._ocr.last_cost_usd


if __name__ == "__main__":
    unittest.main()
