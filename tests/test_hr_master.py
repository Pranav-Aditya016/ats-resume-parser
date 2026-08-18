"""Tests for the recruiter workbook."""

import unittest

from ats_parser.hr_master import (
    MASTER_COLUMNS,
    MAX_POSITIONS,
    NOT_IN_RESUME,
    build_workbook,
    highest_education,
    master_row,
    ordered_positions,
)


def role(company, start=None, end=None, designation="Engineer", duration=None):
    return {"company": company, "role": designation, "start_date": start,
            "end_date": end, "duration": duration, "responsibilities": []}


class PositionOrderingTests(unittest.TestCase):
    def test_most_recent_role_comes_first(self):
        ordered = ordered_positions([
            role("Oldest", "2012-01", "2015-01"),
            role("Newest", "2021-06", "Present"),
            role("Middle", "2015-02", "2021-05"),
        ])
        self.assertEqual([e["company"] for e in ordered], ["Newest", "Middle", "Oldest"])

    def test_an_ongoing_role_outranks_any_dated_one(self):
        ordered = ordered_positions([
            role("Ended recently", "2024-01", "2025-12"),
            role("Ongoing", "2019-01", "Present"),
        ])
        self.assertEqual(ordered[0]["company"], "Ongoing")

    def test_undated_roles_are_kept_rather_than_dropped(self):
        ordered = ordered_positions([role("Undated"), role("Dated", "2020-01", "2021-01")])
        self.assertEqual(len(ordered), 2)
        self.assertEqual(ordered[0]["company"], "Dated")


class MasterRowTests(unittest.TestCase):
    def test_only_the_three_most_recent_roles_reach_the_master_sheet(self):
        record = {"work_experience": [
            role(f"Company {n}", f"20{n:02d}-01", f"20{n + 1:02d}-01") for n in range(10, 21)
        ]}
        row = master_row(1, "candidate", record)

        self.assertEqual(row["Total Positions Listed"], 11)
        self.assertEqual(row["Job 1 Company"], "Company 20")
        self.assertEqual(row["Job 2 Company"], "Company 19")
        self.assertEqual(row["Job 3 Company"], "Company 18")
        self.assertNotIn("Job 4 Company", row)

    def test_a_candidate_with_one_role_leaves_later_slots_empty(self):
        row = master_row(1, "candidate", {"work_experience": [role("Only", "2020-01", "Present")]})
        self.assertEqual(row["Job 1 Company"], "Only")
        self.assertIsNone(row["Job 2 Company"])
        self.assertIsNone(row["Job 3 Company"])
        self.assertEqual(row["Total Positions Listed"], 1)

    def test_missing_commercial_details_say_so_rather_than_being_blank(self):
        row = master_row(1, "candidate", {})
        for column in ("Current CTC", "Expected CTC", "Notice Period", "Preferred Location"):
            self.assertEqual(row[column], NOT_IN_RESUME, column)

    def test_recruiter_columns_exist_and_stay_empty_for_manual_entry(self):
        row = master_row(1, "candidate", {})
        for column in ("Applied Position", "Resume Source", "Screening Status", "Recruiter Remarks"):
            self.assertIsNone(row[column], column)

    def test_derived_experience_reaches_the_row(self):
        record = {"work_experience": [
            role("ABC", "2021-06", "Present", "Senior Planning Engineer"),
        ]}
        row = master_row(1, "candidate", record)
        self.assertEqual(row["Current Company"], "ABC")
        self.assertEqual(row["Current Designation"], "Senior Planning Engineer")
        self.assertIsNotNone(row["Total Experience (Years)"])

    def test_every_row_has_exactly_the_declared_columns(self):
        self.assertEqual(list(master_row(1, "x", {})), MASTER_COLUMNS)
        self.assertEqual(len([c for c in MASTER_COLUMNS if c.endswith("Company") and c.startswith("Job")]),
                         MAX_POSITIONS)


class EducationTests(unittest.TestCase):
    def test_the_most_advanced_qualification_wins(self):
        education = highest_education([
            {"degree": "Secondary (10th)"},
            {"degree": "Bachelor of Engineering", "specialization": "Civil Engineering",
             "institution": "Anna University", "end_date": "2017"},
            {"degree": "Higher Secondary (12th)"},
        ])
        self.assertEqual(education["qualification"], "Under Graduate")
        self.assertEqual(education["specialization"], "Civil Engineering")
        self.assertEqual(education["year"], "2017")

    def test_a_masters_outranks_a_bachelors(self):
        education = highest_education([
            {"degree": "Bachelor of Engineering"},
            {"degree": "Master of Business Administration"},
        ])
        self.assertEqual(education["qualification"], "Post Graduate")

    def test_no_education_yields_nulls(self):
        self.assertIsNone(highest_education([])["qualification"])


class WorkbookTests(unittest.TestCase):
    def test_workbook_has_a_master_and_a_raw_sheet(self):
        records = [("candidate-a", {"personal_information": {"full_name": "A"},
                                    "work_experience": [role("ABC", "2020-01", "Present")]}),
                   ("candidate-b", {"personal_information": {"full_name": "B"}})]
        workbook = build_workbook(records)

        self.assertEqual(workbook.sheetnames, ["HR Candidate Master", "Raw Data"])
        master = workbook["HR Candidate Master"]
        self.assertEqual([c.value for c in master[1]], MASTER_COLUMNS)
        self.assertEqual(master.max_row, 3)  # header plus two candidates

    def test_raw_sheet_keeps_history_beyond_the_three_shown(self):
        record = {"work_experience": [role(f"C{n}", f"20{n:02d}-01", f"20{n + 1:02d}-01") for n in range(10, 16)]}
        workbook = build_workbook([("candidate", record)])
        raw_headers = [c.value for c in workbook["Raw Data"][1]]
        self.assertIn("Experience 6: company", raw_headers)


if __name__ == "__main__":
    unittest.main()
