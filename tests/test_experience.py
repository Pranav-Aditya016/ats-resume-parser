"""Tests for date normalization and derived employment facts."""

import unittest
from datetime import date

from ats_parser.experience import (
    backfill_durations,
    format_duration,
    parse_duration_months,
    summarize_experience,
)
from ats_parser.normalization import normalize_date, normalize_record

TODAY = date(2026, 7, 31)


class NormalizeDateTests(unittest.TestCase):
    def test_the_formats_the_prompt_asks_for_are_preserved(self):
        # The parser instructions require YYYY-MM and YYYY-MM-DD. Rejecting them
        # discarded nearly every start date the model returned.
        self.assertEqual(normalize_date("2021-06"), "2021-06")
        self.assertEqual(normalize_date("2021-6"), "2021-06")
        self.assertEqual(normalize_date("2021-06-15"), "2021-06-15")

    def test_month_name_forms_are_canonicalized(self):
        for text in ("Jun 2021", "June 2021", "June, 2021", "Jun-2021"):
            self.assertEqual(normalize_date(text), "2021-06", text)

    def test_day_month_name_year_forms_from_real_resumes(self):
        self.assertEqual(normalize_date("10-Nov-2020"), "2020-11-10")
        self.assertEqual(normalize_date("31-Aug-22"), "2022-08-31")

    def test_numeric_and_year_only_forms(self):
        self.assertEqual(normalize_date("06/2021"), "2021-06")
        self.assertEqual(normalize_date("15/06/2021"), "2021-06-15")
        self.assertEqual(normalize_date("2021"), "2021")

    def test_ongoing_markers_become_present(self):
        for text in ("Present", "current", "Till Date", "ongoing", "now"):
            self.assertEqual(normalize_date(text), "Present", text)

    def test_invalid_input_is_rejected(self):
        for text in ("", "   ", "not a date", "2021-13", "32/06/2021", None, 42):
            self.assertIsNone(normalize_date(text), repr(text))


class DurationTests(unittest.TestCase):
    def test_durations_are_parsed_into_months(self):
        self.assertEqual(parse_duration_months("5 Years 1 Month"), 61)
        self.assertEqual(parse_duration_months("3 Years 3 Months"), 39)
        self.assertEqual(parse_duration_months("2 Years"), 24)
        self.assertEqual(parse_duration_months("18 months"), 18)
        self.assertEqual(parse_duration_months("1.5 yrs"), 18)

    def test_unparseable_durations_are_none(self):
        for text in ("", "a while", None, "Present"):
            self.assertIsNone(parse_duration_months(text), repr(text))

    def test_months_render_back_to_readable_text(self):
        self.assertEqual(format_duration(61), "5 Years 1 Month")
        self.assertEqual(format_duration(24), "2 Years")
        self.assertEqual(format_duration(7), "7 Months")
        self.assertEqual(format_duration(0), "0 Months")

    def test_duration_is_backfilled_from_dates_when_missing(self):
        entries = [{"start_date": "2021-06", "end_date": "Present", "duration": None}]
        backfill_durations(entries, today=TODAY)
        self.assertEqual(entries[0]["duration"], "5 Years 1 Month")

    def test_an_existing_duration_is_never_overwritten(self):
        entries = [{"start_date": "2021-06", "end_date": "Present", "duration": "stated"}]
        backfill_durations(entries, today=TODAY)
        self.assertEqual(entries[0]["duration"], "stated")


class TotalExperienceTests(unittest.TestCase):
    def test_total_is_summed_across_dated_roles(self):
        summary = summarize_experience([
            {"company": "ABC", "role": "Senior Planning Engineer",
             "start_date": "2021-06", "end_date": "Present"},
            {"company": "XYZ", "role": "Planning Engineer",
             "start_date": "2018-03", "end_date": "2021-05"},
        ], today=TODAY)

        self.assertEqual(summary["total_experience_months"], 61 + 38)
        self.assertEqual(summary["total_experience_years"], 8.2)  # 99 months = 8.25
        self.assertEqual(summary["computation_basis"], "dates")

    def test_overlapping_employment_is_not_counted_twice(self):
        overlapping = summarize_experience([
            {"start_date": "2020-01", "end_date": "2022-01"},
            {"start_date": "2021-01", "end_date": "2023-01"},
        ], today=TODAY)
        # Jan 2020 to Jan 2023 is 36 months, not the 48 a naive sum would give.
        self.assertEqual(overlapping["total_experience_months"], 36)

    def test_a_role_fully_inside_another_adds_nothing(self):
        summary = summarize_experience([
            {"start_date": "2018-01", "end_date": "2024-01"},
            {"start_date": "2020-01", "end_date": "2021-01"},
        ], today=TODAY)
        self.assertEqual(summary["total_experience_months"], 72)

    def test_undated_roles_fall_back_to_their_stated_duration(self):
        summary = summarize_experience([
            {"start_date": None, "end_date": None, "duration": "2 Years"},
        ], today=TODAY)
        self.assertEqual(summary["total_experience_months"], 24)
        self.assertEqual(summary["computation_basis"], "durations")

    def test_mixed_evidence_is_reported_as_mixed(self):
        summary = summarize_experience([
            {"start_date": "2021-06", "end_date": "Present"},
            {"start_date": None, "end_date": None, "duration": "2 Years"},
        ], today=TODAY)
        self.assertEqual(summary["computation_basis"], "mixed")
        self.assertEqual(summary["total_experience_months"], 61 + 24)

    def test_an_open_ended_role_without_an_end_uses_its_duration(self):
        summary = summarize_experience([
            {"start_date": "2020-01", "end_date": None, "duration": "3 Years"},
        ], today=TODAY)
        self.assertEqual(summary["total_experience_months"], 36)

    def test_empty_history_yields_nulls_rather_than_zero(self):
        summary = summarize_experience([], today=TODAY)
        self.assertIsNone(summary["total_experience_years"])
        self.assertIsNone(summary["current_company"])
        self.assertIsNone(summary["computation_basis"])

    def test_reversed_dates_are_ignored_rather_than_counted_negative(self):
        summary = summarize_experience([
            {"start_date": "2022-01", "end_date": "2020-01"},
        ], today=TODAY)
        self.assertIsNone(summary["total_experience_months"])


class CurrentRoleTests(unittest.TestCase):
    def test_the_present_role_is_the_current_one(self):
        summary = summarize_experience([
            {"company": "XYZ", "role": "Planning Engineer",
             "start_date": "2018-03", "end_date": "2021-05"},
            {"company": "ABC", "role": "Senior Planning Engineer",
             "start_date": "2021-06", "end_date": "Present"},
        ], today=TODAY)
        self.assertEqual(summary["current_company"], "ABC")
        self.assertEqual(summary["current_designation"], "Senior Planning Engineer")

    def test_without_a_present_role_the_latest_end_date_wins(self):
        summary = summarize_experience([
            {"company": "Older", "role": "Junior", "start_date": "2015-01", "end_date": "2017-01"},
            {"company": "Newer", "role": "Senior", "start_date": "2017-02", "end_date": "2020-06"},
        ], today=TODAY)
        self.assertEqual(summary["current_company"], "Newer")

    def test_the_most_recently_started_present_role_wins(self):
        summary = summarize_experience([
            {"company": "Old Concurrent", "role": "Advisor",
             "start_date": "2015-01", "end_date": "Present"},
            {"company": "Main", "role": "Senior Planning Engineer",
             "start_date": "2021-06", "end_date": "Present"},
        ], today=TODAY)
        self.assertEqual(summary["current_company"], "Main")


class RecordIntegrationTests(unittest.TestCase):
    def test_a_full_record_gains_a_usable_experience_summary(self):
        record = normalize_record({
            "work_experience": [
                {"company": "ABC Developers", "role": "Senior Planning Engineer",
                 "start_date": "2021-06", "end_date": "Present", "responsibilities": []},
                {"company": "XYZ Infra", "role": "Planning Engineer",
                 "start_date": "March 2018", "end_date": "May 2021", "responsibilities": []},
            ],
        })

        experience = record["experience_summary"]
        self.assertEqual(record["work_experience"][0]["start_date"], "2021-06")
        self.assertEqual(record["work_experience"][1]["start_date"], "2018-03")
        self.assertEqual(experience["current_company"], "ABC Developers")
        self.assertEqual(experience["current_designation"], "Senior Planning Engineer")
        self.assertIsNotNone(experience["total_experience_years"])

    def test_the_summary_is_present_even_with_no_employment_history(self):
        self.assertIn("experience_summary", normalize_record({}))


if __name__ == "__main__":
    unittest.main()
