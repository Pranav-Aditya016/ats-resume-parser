"""CSV and Excel exports for parsed ATS records."""

import csv
import json
from pathlib import Path

from openpyxl import Workbook


def export_records(records: list[tuple[str, dict]], output_dir: Path) -> None:
    _write_summary_csv(records, output_dir / "resume_summary.csv")
    _write_workbook(records, output_dir / "resume_results.xlsx")


def _summary_rows(records: list[tuple[str, dict]]) -> list[dict]:
    rows = []
    for source_file, record in records:
        personal = record.get("personal_information", {})
        skills = record.get("skills", {})
        experience = record.get("experience_summary") or {}
        rows.append({
            "source_file": source_file,
            "full_name": personal.get("full_name"),
            "email": personal.get("email"),
            "phone": personal.get("phone"),
            "location": personal.get("location"),
            # The fields a recruiter shortlists on, ahead of the narrative ones.
            "total_experience_years": experience.get("total_experience_years"),
            "current_designation": experience.get("current_designation"),
            "current_company": experience.get("current_company"),
            "professional_summary": record.get("professional_summary"),
            "languages": _join_values(record.get("languages", []), language=True),
            "skills": _join_values(
                skill for group in skills.values() for skill in (group or [])
            ),
            "keywords": _join_values(record.get("keywords", [])),
        })
    return rows


def _write_summary_csv(records: list[tuple[str, dict]], path: Path) -> None:
    rows = _summary_rows(records)
    headers = list(rows[0]) if rows else ["source_file"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _write_workbook(records: list[tuple[str, dict]], path: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    _add_sheet(workbook, "candidates", _summary_rows(records))
    for field, title in [
        ("education", "education"), ("work_experience", "work_experience"),
        ("internships", "internships"), ("projects", "projects"),
        ("certifications", "certifications"),
    ]:
        _add_sheet(workbook, title, _nested_rows(records, field))
    _add_sheet(workbook, "skills", _skill_rows(records))
    workbook.save(path)


def _nested_rows(records: list[tuple[str, dict]], field: str) -> list[dict]:
    rows = []
    for source_file, record in records:
        for item in record.get(field, []) or []:
            rows.append({"source_file": source_file, **{
                key: _cell(value) for key, value in item.items()
            }})
    return rows


def _skill_rows(records: list[tuple[str, dict]]) -> list[dict]:
    return [
        {"source_file": source_file, **{
            category: _join_values(values or [])
            for category, values in record.get("skills", {}).items()
        }}
        for source_file, record in records
    ]


def _add_sheet(workbook: Workbook, title: str, rows: list[dict]) -> None:
    worksheet = workbook.create_sheet(title)
    headers = list(rows[0]) if rows else ["source_file"]
    worksheet.append(headers)
    for row in rows:
        worksheet.append([_cell(row.get(header)) for header in headers])
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column in worksheet.columns:
        letter = column[0].column_letter
        worksheet.column_dimensions[letter].width = min(
            60, max(12, max(len(str(cell.value or "")) for cell in column) + 2)
        )


def _cell(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _join_values(values, language: bool = False) -> str:
    """Create a readable export value from strings or normalized objects."""
    rendered = []
    for value in values or []:
        if isinstance(value, dict):
            value = value.get("language") if language else json.dumps(value, ensure_ascii=False)
        if value is not None:
            rendered.append(str(value))
    return "; ".join(rendered)
