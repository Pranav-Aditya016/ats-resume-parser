import json
from pathlib import Path
import pandas as pd

INPUT_DIR = Path("parsed_resumes_rerun_2026-07-23")
OUTPUT_FILE = "all_resumes.xlsx"

skip = {"batch_metrics.json", "usage.json", "failures.json"}

# ---------- PASS 1 : Find maximum counts ----------

json_files = [f for f in INPUT_DIR.glob("*.json") if f.name not in skip]

max_exp = 0
max_edu = 0

for file in json_files:
    with open(file, encoding="utf-8") as f:
        data = json.load(f)

    max_exp = max(max_exp, len(data.get("work_experience", [])))
    max_edu = max(max_edu, len(data.get("education", [])))

print(f"Maximum Experiences : {max_exp}")
print(f"Maximum Education   : {max_edu}")

# ---------- PASS 2 : Build rows ----------

rows = []

resume_id = 1

for file in sorted(json_files):

    with open(file, encoding="utf-8") as f:
        data = json.load(f)

    personal = data.get("personal_information", {})
    skills = data.get("skills", {})

    row = {
        "Resume ID": resume_id,
        "Source File": file.stem,

        "Name": personal.get("full_name"),
        "Email": personal.get("email"),
        "Phone": personal.get("phone"),
        "Location": personal.get("location"),

        "LinkedIn": personal.get("linkedin"),
        "GitHub": personal.get("github"),
        "Portfolio": personal.get("portfolio"),
        "Website": personal.get("website"),

        "Professional Summary": data.get("professional_summary"),

        "Languages": ", ".join(data.get("languages", [])),

        "Programming Languages": ", ".join(skills.get("programming_languages", [])),
        "Frameworks": ", ".join(skills.get("frameworks", [])),
        "Libraries": ", ".join(skills.get("libraries", [])),
        "Databases": ", ".join(skills.get("databases", [])),
        "Cloud Platforms": ", ".join(skills.get("cloud_platforms", [])),
        "Developer Tools": ", ".join(skills.get("developer_tools", [])),
        "Soft Skills": ", ".join(skills.get("soft_skills", [])),
        "Other Skills": ", ".join(skills.get("other_skills", [])),

        "Certifications": ", ".join(
            c.get("name", "")
            for c in data.get("certifications", [])
        ),

        "Projects": ", ".join(
            p.get("title", "")
            for p in data.get("projects", [])
        ),
    }

    # -------- EDUCATION --------

    education = data.get("education", [])

    for i in range(max_edu):

        if i < len(education):

            edu = education[i]

            row[f"Edu{i+1} Degree"] = edu.get("degree")
            row[f"Edu{i+1} Specialization"] = edu.get("specialization")
            row[f"Edu{i+1} Institution"] = edu.get("institution")
            row[f"Edu{i+1} Grade"] = edu.get("grade_value")
            row[f"Edu{i+1} Grade Type"] = edu.get("grading_type")
            row[f"Edu{i+1} Start"] = edu.get("start_date")
            row[f"Edu{i+1} End"] = edu.get("end_date")

        else:

            row[f"Edu{i+1} Degree"] = ""
            row[f"Edu{i+1} Specialization"] = ""
            row[f"Edu{i+1} Institution"] = ""
            row[f"Edu{i+1} Grade"] = ""
            row[f"Edu{i+1} Grade Type"] = ""
            row[f"Edu{i+1} Start"] = ""
            row[f"Edu{i+1} End"] = ""

    # -------- EXPERIENCE --------

    experience = data.get("work_experience", [])

    for i in range(max_exp):

        if i < len(experience):

            exp = experience[i]

            row[f"Exp{i+1} Company"] = exp.get("company")
            row[f"Exp{i+1} Role"] = exp.get("role")
            row[f"Exp{i+1} Employment Type"] = exp.get("employment_type")
            row[f"Exp{i+1} Start"] = exp.get("start_date")
            row[f"Exp{i+1} End"] = exp.get("end_date")
            row[f"Exp{i+1} Duration"] = exp.get("duration")
            row[f"Exp{i+1} Location"] = exp.get("location")

            row[f"Exp{i+1} Responsibilities"] = " | ".join(
                exp.get("responsibilities", [])
            )

        else:

            row[f"Exp{i+1} Company"] = ""
            row[f"Exp{i+1} Role"] = ""
            row[f"Exp{i+1} Employment Type"] = ""
            row[f"Exp{i+1} Start"] = ""
            row[f"Exp{i+1} End"] = ""
            row[f"Exp{i+1} Duration"] = ""
            row[f"Exp{i+1} Location"] = ""
            row[f"Exp{i+1} Responsibilities"] = ""

    rows.append(row)
    resume_id += 1

# ---------- SAVE ----------

df = pd.DataFrame(rows)

df.to_excel(OUTPUT_FILE, index=False)

print(f"\nDone!")
print(f"Created {OUTPUT_FILE}")
print(f"Rows    : {len(df)}")
print(f"Columns : {len(df.columns)}")