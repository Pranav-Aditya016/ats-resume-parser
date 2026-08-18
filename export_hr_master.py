"""Build the recruiter workbook from a directory of parsed resume JSON files.

    python export_hr_master.py --input-dir parsed_resumes --output HR_Candidate_Master.xlsx
"""

import argparse
import sys
from pathlib import Path

from ats_parser.hr_master import build_workbook, load_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Export parsed resumes to the HR workbook.")
    parser.add_argument("--input-dir", type=Path, default=Path("parsed_resumes"))
    parser.add_argument("--output", type=Path, default=Path("HR_Candidate_Master.xlsx"))
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        sys.exit(f"Parsed resume folder not found: {args.input_dir}")
    records = load_records(args.input_dir)
    if not records:
        sys.exit(f"No parsed resume JSON files found in {args.input_dir}")

    build_workbook(records).save(args.output)
    print(f"Wrote {args.output} with {len(records)} candidate(s).")


if __name__ == "__main__":
    main()
