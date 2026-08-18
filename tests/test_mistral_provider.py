import unittest

from ats_parser.mistral_provider import MistralProvider
from ats_parser.normalization import normalize_record


class MistralProviderRepairTests(unittest.TestCase):
    def test_repair_record_moves_work_history_out_of_internships(self):
        provider = MistralProvider.__new__(MistralProvider)
        record = {
            "work_experience": [],
            "internships": [
                {
                    "company": "INDIAN STEEL TRADERS",
                    "role": "Junior Accounts Assistant",
                    "responsibilities": ["Bookkeeping", "TDS"],
                }
            ],
            "skills": {"developer_tools": [], "soft_skills": [], "other_skills": []},
        }
        source_text = """
        EXPERIENCE
        INDIAN STEEL TRADERS
        Junior Accounts Assistant
        10-Nov-2020 to 31-Aug-22
        Bookkeeping, TDS, TCS, ledgers
        """

        repaired = provider._repair_record(record, source_text)

        self.assertEqual(len(repaired["work_experience"]), 1)
        self.assertEqual(repaired["work_experience"][0]["company"], "INDIAN STEEL TRADERS")
        self.assertEqual(repaired["internships"], [])

    def test_repair_record_extracts_skills_from_source_text(self):
        provider = MistralProvider.__new__(MistralProvider)
        record = {
            "skills": {"developer_tools": [], "soft_skills": [], "other_skills": []},
        }
        source_text = """
        SKILLS
        Excel | Tally Prime | Zoho Books
        GST | TDS | TCS
        """

        repaired = provider._repair_record(record, source_text)

        self.assertIn("Excel", repaired["skills"]["developer_tools"])
        self.assertIn("Tally Prime", repaired["skills"]["developer_tools"])
        self.assertIn("Zoho Books", repaired["skills"]["developer_tools"])
        self.assertIn("GST", repaired["skills"]["other_skills"])
        self.assertIn("TDS", repaired["skills"]["other_skills"])

    def test_skills_fallback_stops_at_next_section(self):
        provider = MistralProvider.__new__(MistralProvider)
        repaired = provider._repair_record(
            {"skills": {"developer_tools": [], "soft_skills": [], "other_skills": []}},
            """SKILLS
            Python | Java | SQL
            EXPERIENCE
            Example Corp | Engineer
            Built a customer platform
            EDUCATION
            B.E. Civil Engineering
            """,
        )
        skills = repaired["skills"]["other_skills"]
        self.assertEqual(skills, ["Python", "Java", "SQL"])
        self.assertNotIn("Example Corp", " ".join(skills))


class NormalizationTests(unittest.TestCase):
    def test_education_phone_dates_and_grades_are_normalized(self):
        record = normalize_record({
            "personal_information": {"email": "USER@EXAMPLE.COM", "phone": "(91) 98765-43210"},
            "education": [{
                "degree": "B.E. Civil Engineering", "cgpa_or_percentage": "CGPA: 9.68 / 10",
                "start_date": "Dec-2019", "end_date": "12/2023",
            }, {"degree": "HSC", "cgpa_or_percentage": "82%"}],
        })
        degree, school = record["education"]
        self.assertEqual(record["personal_information"]["phone"], "+91 98765 43210")
        self.assertEqual(record["personal_information"]["email"], "user@example.com")
        self.assertEqual(degree["degree"], "Bachelor of Engineering")
        self.assertEqual(degree["specialization"], "Civil Engineering")
        self.assertEqual(degree["grading_type"], "CGPA")
        self.assertEqual(degree["grade_value"], "9.68")
        self.assertEqual(degree["grade_scale"], "10")
        self.assertEqual(degree["start_date"], "2019-12")
        self.assertEqual(degree["end_date"], "2023-12")
        self.assertEqual(school["degree"], "Higher Secondary (12th)")
        self.assertEqual(school["grading_type"], "Percentage")

    def test_unlabeled_numeric_grade_is_not_assumed_to_be_percentage(self):
        record = normalize_record({"education": [{"degree": "B.Tech", "cgpa_or_percentage": "9.68"}]})
        education = record["education"][0]
        self.assertIsNone(education["grading_type"])
        self.assertEqual(education["grade_value"], "9.68")

    def test_degree_abbreviations_are_canonicalized(self):
        record = normalize_record({"education": [
            {"degree": "M.B.A Marketing"},
            {"degree": "B.Arch"},
            {"degree": "M. Arch Sustainable Design"},
        ]})
        self.assertEqual(record["education"][0]["degree"], "Master of Business Administration")
        self.assertEqual(record["education"][0]["specialization"], "Marketing")
        self.assertEqual(record["education"][1]["degree"], "Bachelor of Architecture")
        self.assertEqual(record["education"][2]["degree"], "Master of Architecture")
        self.assertEqual(record["education"][2]["specialization"], "Sustainable Design")

    def test_education_and_resume_prose_are_removed_from_skills(self):
        record = normalize_record({"skills": {"other_skills": [
            "M.B.A Marketing",
            "Responsible for managing a team and delivering projects for the organization",
            "Tally Prime",
        ]}})
        self.assertEqual(record["skills"]["other_skills"], ["Tally Prime"])


if __name__ == "__main__":
    unittest.main()
