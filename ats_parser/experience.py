"""Derived employment facts: total experience, current role, per-entry duration.

Recruiters shortlist on "how long has this person worked" and "where are they now",
but a resume only ever states those indirectly. This module computes them from the
normalized employment history rather than asking the model, because date arithmetic
is exactly what language models are worst at and deterministic code is best at.

Conventions, chosen once and applied consistently:

* Overlapping employment is merged, so two concurrent roles do not count twice.
* Internships are excluded. They are a separate schema field and recruiters asking
  for "total experience" mean full-time history.
* A year-only date resolves to January, so 2018-2021 reads as three years.
* "Present" resolves to the date the batch runs.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

DURATION_UNITS = re.compile(
    r"(\d+(?:\.\d+)?)\s*(years?|yrs?|yr|months?|mons?|mos?|mo)\b", re.I
)
YEAR_UNIT = re.compile(r"^(?:years?|yrs?|yr)$", re.I)


def summarize_experience(entries: list[dict], today: date | None = None) -> dict:
    """Return the derived employment summary for one candidate."""
    today = today or date.today()
    intervals, undated_months = _intervals(entries, today)
    merged_months = sum(end - start for start, end in _merge(intervals))
    total_months = merged_months + undated_months
    basis = _basis(bool(intervals), bool(undated_months))
    current = _current_entry(entries)
    return {
        "total_experience_months": total_months or None,
        "total_experience_years": round(total_months / 12, 1) if total_months else None,
        "current_company": (current or {}).get("company"),
        "current_designation": (current or {}).get("role"),
        "computation_basis": basis,
    }


def backfill_durations(entries: list[dict], today: date | None = None) -> None:
    """Fill a missing duration in place when the entry's dates can supply one."""
    today = today or date.today()
    for entry in entries:
        if entry.get("duration"):
            continue
        span = _entry_span(entry, today)
        if span is not None:
            entry["duration"] = format_duration(span[1] - span[0])


def format_duration(months: int) -> str:
    years, remainder = divmod(max(months, 0), 12)
    parts = []
    if years:
        parts.append(f"{years} Year{'s' if years != 1 else ''}")
    if remainder or not years:
        parts.append(f"{remainder} Month{'s' if remainder != 1 else ''}")
    return " ".join(parts)


def parse_duration_months(value: Any) -> int | None:
    """Read '5 Years 1 Month', '2 yrs', or '18 months' as a month count."""
    if not isinstance(value, str) or not value.strip():
        return None
    total = 0.0
    matched = False
    for amount, unit in DURATION_UNITS.findall(value):
        matched = True
        total += float(amount) * (12 if YEAR_UNIT.match(unit) else 1)
    return int(round(total)) if matched and total > 0 else None


def _intervals(entries: list[dict], today: date | None) -> tuple[list[tuple[int, int]], int]:
    """Split entries into dated intervals and a month total for undated ones."""
    intervals: list[tuple[int, int]] = []
    undated_months = 0
    for entry in entries:
        span = _entry_span(entry, today)
        if span is not None:
            intervals.append(span)
            continue
        # No usable dates, so the stated duration is all there is. It cannot be
        # placed on the timeline, so it cannot be overlap-checked.
        stated = parse_duration_months(entry.get("duration"))
        if stated:
            undated_months += stated
    return intervals, undated_months


def _entry_span(entry: dict, today: date | None) -> tuple[int, int] | None:
    start = _month_index(entry.get("start_date"), today)
    if start is None:
        return None
    end = _month_index(entry.get("end_date"), today)
    if end is None:
        stated = parse_duration_months(entry.get("duration"))
        end = start + stated if stated else None
    if end is None or end < start:
        return None
    return start, end


def _month_index(value: Any, today: date | None) -> int | None:
    """Map a normalized date to a month ordinal, so spans are simple subtraction."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.lower() == "present":
        reference = today or date.today()
        return reference.year * 12 + reference.month
    if match := re.fullmatch(r"(\d{4})", text):
        return int(match.group(1)) * 12 + 1
    if match := re.fullmatch(r"(\d{4})-(\d{2})(?:-\d{2})?", text):
        return int(match.group(1)) * 12 + int(match.group(2))
    return None


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _basis(has_dated: bool, has_undated: bool) -> str | None:
    if has_dated and has_undated:
        return "mixed"
    if has_dated:
        return "dates"
    return "durations" if has_undated else None


def _current_entry(entries: list[dict]) -> dict | None:
    """The role held now, else the most recent one that can be ordered."""
    ongoing = [e for e in entries if str(e.get("end_date") or "").lower() == "present"]
    if ongoing:
        return max(ongoing, key=lambda e: _month_index(e.get("start_date"), None) or 0)
    dated = [(idx, e) for e in entries if (idx := _month_index(e.get("end_date"), None)) is not None]
    return max(dated, key=lambda pair: pair[0])[1] if dated else None
