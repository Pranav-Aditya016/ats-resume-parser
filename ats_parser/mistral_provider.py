"""Mistral implementation of the resume-provider contract.

Document transcription happens in `ats_parser.text_extraction`. This module only turns
already-extracted Markdown into a canonical ATS record.
"""

import json
import os
import re
import time

from mistralai.client import Mistral

from ats_parser.normalization import extract_skills_section, normalize_record
from ats_parser.schema import PARSER_INSTRUCTIONS, RESUME_SCHEMA


class MistralProvider:
    """Turn resume Markdown into ATS JSON with a Mistral chat model."""

    def __init__(self, model: str):
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY is missing. Add it to the .env file.")
        self.client = Mistral(api_key=api_key)
        self.model = model
        self.last_usage = None
        self.last_cost_usd = None
        self.last_response_latency_seconds = None

    def parse(self, source_text: str) -> dict:
        parse_start = time.perf_counter()
        result = self._extract_json(source_text)
        self.last_response_latency_seconds = round(time.perf_counter() - parse_start, 3)
        return result

    def _extract_json(self, source_text: str) -> dict:
        prompt = (
            f"{PARSER_INSTRUCTIONS}\n\n"
            "Return a JSON object with exactly this JSON Schema:\n"
            f"{json.dumps(RESUME_SCHEMA)}\n\n"
            "Resume text extracted from the source document:\n"
            f"{source_text}"
        )
        response = self.client.chat.complete(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        # ChatCompletionResponse carries token counts on `usage`; `usage_info` is the
        # OCR response's field name and always reads back as None here.
        usage_info = getattr(response, "usage", None)
        if usage_info is not None:
            prompt_tokens = getattr(usage_info, "prompt_tokens", None) or 0
            completion_tokens = getattr(usage_info, "completion_tokens", None) or 0
            total_tokens = getattr(usage_info, "total_tokens", None) or (prompt_tokens + completion_tokens)
            self.last_usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
            self.last_cost_usd = round((prompt_tokens / 1_000_000) * 0.10 + (completion_tokens / 1_000_000) * 0.30, 6)
        else:
            self.last_usage = None
            self.last_cost_usd = None
        choices = getattr(response, "choices", None) or []
        text = (getattr(choices[0].message, "content", "") if choices else "").strip()
        if not text:
            raise RuntimeError("Mistral returned an empty response.")
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Mistral returned invalid JSON.") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Mistral returned JSON that is not an object.")
        return self._repair_record(result, source_text)

    def _repair_record(self, record: dict, source_text: str) -> dict:
        repaired = dict(record)
        skills = repaired.setdefault("skills", {})
        if not isinstance(skills, dict):
            skills = {}
            repaired["skills"] = skills

        developer_tools = skills.setdefault("developer_tools", [])
        soft_skills = skills.setdefault("soft_skills", [])
        other_skills = skills.setdefault("other_skills", [])

        if not isinstance(developer_tools, list):
            developer_tools = []
        if not isinstance(soft_skills, list):
            soft_skills = []
        if not isinstance(other_skills, list):
            other_skills = []

        text = source_text.lower()
        skill_terms = self._extract_skill_terms(source_text)
        if skill_terms:
            for key, target in [
                ("developer_tools", developer_tools),
                ("soft_skills", soft_skills),
                ("other_skills", other_skills),
            ]:
                if not target:
                    target.extend(skill_terms[key])

        work_experience = repaired.setdefault("work_experience", [])
        internships = repaired.setdefault("internships", [])
        if isinstance(work_experience, list) and isinstance(internships, list):
            if self._looks_like_work_history(source_text, internships):
                if not work_experience and internships:
                    repaired["work_experience"] = internships
                    repaired["internships"] = []
                elif work_experience and internships and len(work_experience) <= len(internships):
                    repaired["work_experience"] = work_experience + internships
                    repaired["internships"] = []

        if "experience" in text and not work_experience and internships:
            repaired["work_experience"] = internships
            repaired["internships"] = []

        return normalize_record(repaired, source_text)

    def _extract_skill_terms(self, source_text: str) -> dict[str, list[str]]:
        result = {"developer_tools": [], "soft_skills": [], "other_skills": []}
        # OCR text outside the bounded Skills section is never skill data.
        for line in extract_skills_section(source_text):
            if re.search(r"\b(excel|word|powerpoint|tally|zoho|sap|quickbooks|busy|ms office|office)\b", line, re.I):
                result["developer_tools"].extend(self._split_items(line))
            elif re.search(r"\b(communication|teamwork|leadership|adaptability|time management|attention to detail|problem solving|analytical)\b", line, re.I):
                result["soft_skills"].extend(self._split_items(line))
            else:
                result["other_skills"].extend(self._split_items(line))
        seen = set()
        for key in result:
            cleaned = []
            for item in result[key]:
                normalized = re.sub(r"\s+", " ", item).strip()
                if not normalized or normalized.lower() in seen:
                    continue
                cleaned.append(normalized)
                seen.add(normalized.lower())
            result[key] = cleaned
        return result

    def _split_items(self, text: str) -> list[str]:
        separators = ["|", ",", "/", ";", "\n"]
        for separator in separators:
            if separator in text:
                parts = [part.strip() for part in text.split(separator)]
                return [part for part in parts if part]
        return [text]

    def _looks_like_work_history(self, source_text: str, internships: list) -> bool:
        lowered = source_text.lower()
        if not internships:
            return False
        experience_markers = ["experience", "work experience", "employment history", "professional experience"]
        if any(marker in lowered for marker in experience_markers):
            return True
        for item in internships:
            company = str(item.get("company") or "").lower()
            role = str(item.get("role") or "").lower()
            if company or role:
                return True
        return False
