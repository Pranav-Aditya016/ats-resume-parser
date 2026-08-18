"""Deterministic cleanup and validation applied after every LLM extraction."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from ats_parser.experience import backfill_durations, summarize_experience
from ats_parser.schema import RESUME_SCHEMA

SKILL_KEYS = ("programming_languages", "frameworks", "libraries", "databases", "cloud_platforms", "developer_tools", "soft_skills", "other_skills")
LIST_FIELDS = ("education", "work_experience", "internships", "projects", "certifications", "achievements", "leadership", "publications", "patents", "hackathons", "competitions", "awards", "languages", "volunteer_experience", "extracurricular_activities", "references", "keywords", "ats_score_keywords")
MONTHS = {name: index for index, name in enumerate("january february march april may june july august september october november december".split(), 1)}
MONTH_ALIASES = {**MONTHS, **{name[:3]: value for name, value in MONTHS.items()}}
DEGREE_PATTERNS = (
    (r"\b(?:b\.?\s*e\.?|bachelor\s+of\s+engineering)\b", "Bachelor of Engineering"),
    (r"\b(?:b\.?\s*tech\.?|bachelor\s+of\s+technology)\b", "Bachelor of Technology"),
    (r"\b(?:m\.?\s*tech\.?|master\s+of\s+technology)\b", "Master of Technology"),
    (r"\b(?:b\.?\s*com\.?|bachelor\s+of\s+commerce)\b", "Bachelor of Commerce"),
    (r"\b(?:m\.?\s*com\.?|master\s+of\s+commerce)\b", "Master of Commerce"),
    (r"\b(?:b\.?\s*sc\.?|bachelor\s+of\s+science)\b", "Bachelor of Science"),
    (r"\b(?:m\.?\s*sc\.?|master\s+of\s+science)\b", "Master of Science"),
    (r"\b(?:b\.?\s*arch\.?|bachelor\s+of\s+architecture)\b", "Bachelor of Architecture"),
    (r"\b(?:m\.?\s*arch\.?|master\s+of\s+architecture)\b", "Master of Architecture"),
    (r"\b(?:b\.?\s*b\.?\s*a\.?|bachelor\s+of\s+business\s+administration)\b", "Bachelor of Business Administration"),
    (r"\b(?:m\.?\s*b\.?\s*a\.?|master\s+of\s+business\s+administration)\b", "Master of Business Administration"),
)
SECTION_HEADERS = re.compile(r"^\s*(?:#{1,6}\s*)?(?:(?:work |professional )?experience|education|projects?|certifications?|languages?|achievements?|awards?|publications?|references?|interests?|objective|summary|profile|volunteer(?:ing)?|extracurricular|declaration)\s*:?[\s]*$", re.I)
SKILLS_HEADER = re.compile(r"^\s*(?:#{1,6}\s*)?(?:technical |core |key )?(?:skills?|tools?|software|competencies)\s*:?[\s]*$", re.I)


def normalize_record(record: dict[str, Any], source_text: str | None = None) -> dict[str, Any]:
    """Return a schema-complete, validated record without changing pipeline inputs."""
    result = _fill_schema(record if isinstance(record, dict) else {}, RESUME_SCHEMA)
    _normalise_strings(result)
    personal = result["personal_information"]
    personal["email"] = _valid_email(personal["email"])
    personal["phone"] = normalize_phone(personal["phone"])
    for field in ("education", "work_experience", "internships", "certifications"):
        for item in result[field]:
            for date_field in ("start_date", "end_date", "date"):
                if date_field in item:
                    item[date_field] = normalize_date(item[date_field])
    for education in result["education"]:
        _normalize_education(education)
    _normalise_skills(result["skills"], source_text)
    for field in LIST_FIELDS:
        result[field] = _unique(result[field])
    # Derived after normalization, and deliberately not part of RESUME_SCHEMA: the
    # model is never asked to do date arithmetic it cannot do reliably.
    backfill_durations(result["work_experience"])
    result["experience_summary"] = summarize_experience(result["work_experience"])
    return result


def _fill_schema(value: Any, schema: dict) -> Any:
    kind = schema.get("type")
    if kind == "object":
        source = value if isinstance(value, dict) else {}
        return {key: _fill_schema(source.get(key), child) for key, child in schema["properties"].items()}
    if kind == "array":
        return [_fill_schema(item, schema["items"]) for item in value] if isinstance(value, list) else []
    if value is None:
        return None
    return value if isinstance(value, str if kind == "string" else int) else None


def _normalise_strings(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str) and key != "professional_summary":
                value[key] = re.sub(r"\s+", " ", item).strip() or None
            else:
                _normalise_strings(item)
    elif isinstance(value, list):
        for item in value:
            _normalise_strings(item)


def _normalize_education(item: dict) -> None:
    raw_degree = item.get("degree") or ""
    lowered = raw_degree.lower()
    if re.search(r"\b(sslc|secondary|10(?:th)?|high school)\b", lowered):
        item["degree"], item["specialization"] = "Secondary (10th)", None
    elif re.search(r"\b(hsc|higher secondary|senior secondary|12(?:th)?|intermediate|puc|plus two)\b", lowered):
        item["degree"], item["specialization"] = "Higher Secondary (12th)", None
    else:
        for pattern, canonical in DEGREE_PATTERNS:
            if match := re.search(pattern, raw_degree, re.I):
                item["degree"] = canonical
                remainder = re.sub(pattern, "", raw_degree, flags=re.I).strip(" -–—():,.")
                if not item.get("specialization") and remainder:
                    item["specialization"] = remainder
                break
    _normalize_grade(item)


def _normalize_grade(item: dict) -> None:
    raw = item.get("cgpa_or_percentage")
    if not raw:
        return
    text = str(raw).strip()
    value = re.search(r"\d+(?:\.\d+)?", text)
    if not value:
        return
    item["grade_value"] = value.group(0)
    scale = re.search(r"(?:out\s+of|/)\s*(\d+(?:\.\d+)?)", text, re.I)
    if re.search(r"\b(?:cgpa|cumulative\s+grade)\b", text, re.I):
        item["grading_type"], item["grade_scale"] = "CGPA", scale.group(1) if scale else None
    elif re.search(r"\bgpa\b", text, re.I):
        item["grading_type"], item["grade_scale"] = "GPA", scale.group(1) if scale else None
    elif "%" in text or re.search(r"\bpercentage\b|\bpercent\b", text, re.I):
        item["grading_type"], item["grade_scale"] = "Percentage", "100"


def normalize_phone(value: Any) -> str | None:
    if not isinstance(value, str): return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10 and digits[0] in "6789": return f"+91 {digits[:5]} {digits[5:]}"
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789": return f"+91 {digits[2:7]} {digits[7:]}"
    return None


def normalize_date(value: Any) -> str | None:
    """Return YYYY, YYYY-MM, YYYY-MM-DD, "Present", or None.

    The parser prompt asks the model for YYYY-MM and YYYY-MM-DD, so those must be
    accepted here. Rejecting them discarded almost every start date the model
    correctly returned.
    """
    if not isinstance(value, str) or not value.strip(): return None
    text = value.strip()
    if re.fullmatch(r"(?:present|current|till date|till present|to date|ongoing|now)", text, re.I): return "Present"
    if re.fullmatch(r"\d{4}", text): return text
    # Already-canonical forms, which the prompt explicitly requests.
    if match := re.fullmatch(r"(\d{4})-(\d{1,2})", text):
        year, month = int(match.group(1)), int(match.group(2))
        return f"{year}-{month:02d}" if 1 <= month <= 12 else None
    if match := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):
        year, month, day = map(int, match.groups())
        try: return date(year, month, day).isoformat()
        except ValueError: return None
    if match := re.fullmatch(r"([A-Za-z]+)[\s,.-]+(\d{2,4})", text):
        if match.group(1).lower() in MONTH_ALIASES:
            return f"{_full_year(int(match.group(2)))}-{MONTH_ALIASES[match.group(1).lower()]:02d}"
    # "10-Nov-2020" and "31-Aug-22" both appear in real resumes.
    if match := re.fullmatch(r"(\d{1,2})[\s,.-]+([A-Za-z]+)[\s,.-]+(\d{2,4})", text):
        if match.group(2).lower() in MONTH_ALIASES:
            try: return date(_full_year(int(match.group(3))), MONTH_ALIASES[match.group(2).lower()], int(match.group(1))).isoformat()
            except ValueError: return None
    if match := re.fullmatch(r"(\d{1,2})[/-](\d{4})", text):
        if 1 <= int(match.group(1)) <= 12: return f"{match.group(2)}-{int(match.group(1)):02d}"
    if match := re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", text):
        day, month, year = map(int, match.groups())
        try: return date(_full_year(year), month, day).isoformat()
        except ValueError: return None
    return None


def _full_year(year: int) -> int:
    """Expand a two-digit year, treating the near future as the past century."""
    if year >= 100: return year
    return 2000 + year if year <= date.today().year % 100 + 5 else 1900 + year


def _valid_email(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) else None


def _normalise_skills(skills: dict, source_text: str | None) -> None:
    extracted = extract_skills_section(source_text) if source_text else []
    for key in SKILL_KEYS:
        cleaned = []
        for value in skills.get(key, []) if isinstance(skills.get(key), list) else []:
            if isinstance(value, str):
                value = re.sub(r"\s+", " ", value).strip(" -•\t")
                if _is_valid_skill(value):
                    cleaned.append(value)
        skills[key] = _unique(cleaned)
    if extracted and not any(skills.values()): skills["other_skills"] = extracted


def _is_valid_skill(value: str) -> bool:
    """Reject narrative, education, and section text from skill fields."""
    if not value or len(value) > 120 or SECTION_HEADERS.match(value):
        return False
    if len(value.split()) > 14:
        return False
    if any(re.search(pattern, value, re.I) for pattern, _ in DEGREE_PATTERNS):
        return False
    narrative_markers = (
        "objective", "experience", "responsibilities", "education", "worked as",
        "responsible for", "seeking a", "to obtain", "career",
    )
    return not any(marker in value.casefold() for marker in narrative_markers)


def extract_skills_section(source_text: str | None) -> list[str]:
    if not source_text: return []
    capturing, values = False, []
    for line in (line.strip(" -•\t") for line in source_text.splitlines()):
        if not line: continue
        if not capturing:
            capturing = bool(SKILLS_HEADER.match(line)); continue
        if SECTION_HEADERS.match(line): break
        values.extend(part.strip() for part in re.split(r"[|,;•]", line) if part.strip())
    return _unique(value for value in values if len(value) <= 120)


def _unique(values: Any) -> list:
    result, seen = [], set()
    for value in values if not isinstance(values, str) else [values]:
        marker = str(value).casefold()
        if value is not None and marker not in seen: result.append(value); seen.add(marker)
    return result
