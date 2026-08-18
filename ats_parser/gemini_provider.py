"""Google Gemini implementation of the provider contract.

Document transcription happens in `ats_parser.text_extraction`. This module only turns
already-extracted Markdown into a canonical ATS record.
"""

import json
import os
import time

from google import genai
from google.genai import types

from ats_parser.normalization import normalize_record
from ats_parser.schema import PARSER_INSTRUCTIONS, RESUME_SCHEMA


class GeminiProvider:
    """Turn resume Markdown into ATS JSON with Gemini structured output."""

    def __init__(self, model: str):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to the .env file.")
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.last_usage = None
        self.last_cost_usd = None
        self.last_response_latency_seconds = None

    def parse(self, source_text: str) -> dict:
        parse_start = time.perf_counter()
        result = self._generate(source_text)
        self.last_response_latency_seconds = round(time.perf_counter() - parse_start, 3)
        return result

    def _generate(self, source_text: str) -> dict:
        response = self.client.models.generate_content(
            model=self.model,
            contents=[source_text, PARSER_INSTRUCTIONS],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RESUME_SCHEMA,
                temperature=0,
            ),
        )
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_token_count", None) or 0
            completion_tokens = getattr(usage, "candidates_token_count", None) or 0
            total_tokens = getattr(usage, "total_token_count", None) or (prompt_tokens + completion_tokens)
            self.last_usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
            self.last_cost_usd = round((prompt_tokens / 1_000_000) * 0.15 + (completion_tokens / 1_000_000) * 0.60, 6)
        else:
            self.last_usage = None
            self.last_cost_usd = None
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini returned invalid JSON.") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Gemini returned JSON that is not an object.")
        # Now that the source Markdown is available, the skills-section fallback
        # applies to Gemini too, not just Mistral.
        return normalize_record(result, source_text)
