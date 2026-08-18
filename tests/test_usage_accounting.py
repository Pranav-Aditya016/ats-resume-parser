"""Regression tests for token and page accounting.

The chat response carries token counts on `usage`; `usage_info` is the OCR response's
field name. Reading the wrong one silently reported every run as costing nothing, so
these tests pin the field names rather than the arithmetic alone.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from ats_parser.mistral_provider import MistralProvider
from ats_parser.text_extraction import MistralOCRExtractor


def chat_response(usage=None, content='{"personal_information": {}}'):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=message)])


class ChatUsageTests(unittest.TestCase):
    def _provider(self):
        provider = MistralProvider.__new__(MistralProvider)
        provider.model = "mistral-small-latest"
        provider.last_usage = provider.last_cost_usd = None
        return provider

    def test_token_counts_are_read_from_the_usage_field(self):
        provider = self._provider()
        usage = SimpleNamespace(prompt_tokens=2414, completion_tokens=1262, total_tokens=3676)
        provider.client = SimpleNamespace(
            chat=SimpleNamespace(complete=lambda **kwargs: chat_response(usage))
        )

        provider._extract_json("# Resume")

        self.assertEqual(provider.last_usage["prompt_tokens"], 2414)
        self.assertEqual(provider.last_usage["completion_tokens"], 1262)
        self.assertEqual(provider.last_usage["total_tokens"], 3676)
        # 2414/1M * $0.10 + 1262/1M * $0.30
        self.assertAlmostEqual(provider.last_cost_usd, 0.00062, places=6)

    def test_a_response_carrying_only_usage_info_is_not_mistaken_for_usage(self):
        provider = self._provider()
        stale = SimpleNamespace(prompt_tokens=999, completion_tokens=999, total_tokens=999)
        response = chat_response(usage=None)
        response.usage_info = stale
        provider.client = SimpleNamespace(
            chat=SimpleNamespace(complete=lambda **kwargs: response)
        )

        provider._extract_json("# Resume")

        self.assertIsNone(provider.last_usage)
        self.assertIsNone(provider.last_cost_usd)


class OCRUsageTests(unittest.TestCase):
    def _extractor(self):
        extractor = MistralOCRExtractor.__new__(MistralOCRExtractor)
        extractor.model = "mistral-ocr-latest"
        extractor.last_usage = extractor.last_cost_usd = None
        return extractor

    def test_ocr_is_billed_per_page_and_reports_no_tokens(self):
        extractor = self._extractor()
        pages = [SimpleNamespace(markdown="# Page one"), SimpleNamespace(markdown="Page two")]
        response = SimpleNamespace(pages=pages, usage_info=SimpleNamespace(pages_processed=2))
        extractor.client = SimpleNamespace(ocr=SimpleNamespace(process=lambda **kwargs: response))

        with mock.patch("pathlib.Path.read_bytes", return_value=b"%PDF"):
            from pathlib import Path
            extracted = extractor.extract(Path("resume.pdf"))

        self.assertEqual(extracted.page_count, 2)
        self.assertAlmostEqual(extractor.last_cost_usd, 0.002)
        self.assertIsNone(extractor.last_usage)  # Pages are not tokens.

    def test_page_count_falls_back_to_the_returned_pages(self):
        extractor = self._extractor()
        response = SimpleNamespace(pages=[SimpleNamespace(markdown="Only page")], usage_info=None)
        extractor.client = SimpleNamespace(ocr=SimpleNamespace(process=lambda **kwargs: response))

        with mock.patch("pathlib.Path.read_bytes", return_value=b"%PDF"):
            from pathlib import Path
            extracted = extractor.extract(Path("resume.pdf"))

        self.assertEqual(extracted.page_count, 1)
        self.assertIsNone(extractor.last_cost_usd)

    def test_empty_ocr_result_is_an_error(self):
        extractor = self._extractor()
        response = SimpleNamespace(pages=[], usage_info=SimpleNamespace(pages_processed=0))
        extractor.client = SimpleNamespace(ocr=SimpleNamespace(process=lambda **kwargs: response))

        with mock.patch("pathlib.Path.read_bytes", return_value=b"%PDF"):
            from pathlib import Path
            with self.assertRaises(RuntimeError):
                extractor.extract(Path("resume.pdf"))


if __name__ == "__main__":
    unittest.main()
