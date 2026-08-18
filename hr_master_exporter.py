
"""
HR Master Resume Exporter
-------------------------
Reads all JSON resumes in INPUT_DIR and creates a single CSV with one row
per candidate. It dynamically expands experience, projects, certifications,
etc., based on the maximum entries found.

Update INPUT_DIR if needed.
"""

import json
import re
from pathlib import Path
import pandas as pd

INPUT_DIR = Path("parsed_resumes_rerun_2026-07-23")
OUTPUT_FILE = "HR_Master_Resume_Database.csv"

SKIP = {"batch_metrics.json","usage.json","failures.json"}

json_files=[f for f in sorted(INPUT_DIR.glob("*.json")) if f.name not in SKIP]

def max_count(field):
    m=0
    for f in json_files:
        d=json.loads(f.read_text(encoding="utf-8"))
        m=max(m,len(d.get(field,[])))
    return m

MAX_EXP=max_count("work_experience")
MAX_PROJ=max_count("projects")
MAX_CERT=max_count("certifications")
MAX_ACH=max_count("achievements")
MAX_LEAD=max_count("leadership")
MAX_AWARD=max_count("awards")
MAX_PUB=max_count("publications")
MAX_PAT=max_count("patents")
MAX_HACK=max_count("hackathons")
MAX_COMP=max_count("competitions")
MAX_VOL=max_count("volunteer_experience")

def edu_bucket(deg):
    d=(deg or "").lower()
    if any(x in d for x in ["secondary (10","sslc","10th"]): return "Secondary"
    if any(x in d for x in ["higher secondary","12th","hsc","puc"]): return "Higher Secondary"
    if "diploma" in d: return "Diploma"
    if any(x in d for x in ["bachelor","b.tech","b.e","bsc","b.com","bba","bca","llb","mbbs"]): return "UG"
    if any(x in d for x in ["master","m.tech","mba","mca","msc","m.com","ma"]): return "PG"
    if "phd" in d or "doctor" in d: return "Doctorate"
    return "Other"

def exp_key(exp):
    end=(exp.get("end_date") or "")
    start=(exp.get("start_date") or "")
    if str(end).lower()=="present":
        return (9999,9999)
    nums=re.findall(r"\d{4}",str(end)+" "+str(start))
    endyr=int(nums[0]) if nums else 0
    startyr=int(nums[-1]) if nums else 0
    return (endyr,startyr)

rows=[]

for idx,f in enumerate(json_files,1):
    d=json.loads(f.read_text(encoding="utf-8"))
    p=d.get("personal_information",{})
    s=d.get("skills",{})

    allskills=[]
    for k in ["programming_languages","frameworks","libraries","databases",
              "cloud_platforms","developer_tools","soft_skills","other_skills"]:
        allskills.extend(s.get(k,[]))
    allskills.extend(d.get("keywords",[]))
    seen=[]
    for x in allskills:
        if x and x not in seen:
            seen.append(x)

    row={
        "Resume ID":idx,
        "Source File":f.stem,
        "Full Name":p.get("full_name"),
        "Email":p.get("email"),
        "Phone":p.get("phone"),
        "Location":p.get("location"),
        "LinkedIn":p.get("linkedin"),
        "GitHub":p.get("github"),
        "Portfolio":p.get("portfolio"),
        "Website":p.get("website"),
        "Professional Summary":d.get("professional_summary"),
        "Programming Languages":", ".join(s.get("programming_languages",[])),
        "Frameworks":", ".join(s.get("frameworks",[])),
        "Libraries":", ".join(s.get("libraries",[])),
        "Databases":", ".join(s.get("databases",[])),
        "Cloud Platforms":", ".join(s.get("cloud_platforms",[])),
        "Developer Tools":", ".join(s.get("developer_tools",[])),
        "Soft Skills":", ".join(s.get("soft_skills",[])),
        "Other Skills":", ".join(s.get("other_skills",[])),
        "Keywords":", ".join(d.get("keywords",[])),
        "ATS Keywords":", ".join(d.get("ats_score_keywords",[])),
        "All Skills":", ".join(seen),
        "Languages":", ".join(d.get("languages",[])),
        "References":", ".join(d.get("references",[])),
        "Extracurricular Activities":", ".join(d.get("extracurricular_activities",[])),
        "Pages":d.get("resume_statistics",{}).get("pages"),
        "Sections":", ".join(d.get("resume_statistics",{}).get("sections_detected",[]))
    }

    for b in ["Secondary","Higher Secondary","Diploma","UG","PG","Doctorate","Other"]:
        row[b]=""

    for e in d.get("education",[]):
        bucket=edu_bucket(e.get("degree"))
        txt="\n".join(filter(None,[
            e.get("degree"),
            e.get("specialization"),
            e.get("institution"),
            f"{e.get('grading_type') or ''} {e.get('grade_value') or ''}".strip(),
            f"{e.get('start_date') or ''} - {e.get('end_date') or ''}".strip(" -")
        ]))
        if row[bucket]:
            row[bucket]+="\n\n"+txt
        else:
            row[bucket]=txt

    exps=sorted(d.get("work_experience",[]),key=exp_key,reverse=True)
    for i in range(MAX_EXP):
        if i<len(exps):
            ex=exps[i]
            row[f"Exp{i+1} Company"]=ex.get("company")
            row[f"Exp{i+1} Role"]=ex.get("role")
            row[f"Exp{i+1} Start"]=ex.get("start_date")
            row[f"Exp{i+1} End"]=ex.get("end_date")
            row[f"Exp{i+1} Duration"]=ex.get("duration")
            row[f"Exp{i+1} Responsibilities"]=" | ".join(ex.get("responsibilities",[]))

    def fill_dynamic(field,maxn,prefix,key="name"):
        arr=d.get(field,[])
        for i in range(maxn):
            row[f"{prefix}{i+1}"]=arr[i].get(key) if i<len(arr) and isinstance(arr[i],dict) else (arr[i] if i<len(arr) else "")
    fill_dynamic("projects",MAX_PROJ,"Project ","title")
    fill_dynamic("certifications",MAX_CERT,"Certification ")
    fill_dynamic("achievements",MAX_ACH,"Achievement ")
    fill_dynamic("leadership",MAX_LEAD,"Leadership ")
    fill_dynamic("awards",MAX_AWARD,"Award ")
    fill_dynamic("publications",MAX_PUB,"Publication ")
    fill_dynamic("patents",MAX_PAT,"Patent ")
    fill_dynamic("hackathons",MAX_HACK,"Hackathon ")
    fill_dynamic("competitions",MAX_COMP,"Competition ")
    fill_dynamic("volunteer_experience",MAX_VOL,"Volunteer ")

    rows.append(row)

pd.DataFrame(rows).to_csv(OUTPUT_FILE,index=False,encoding="utf-8-sig")
print("Created",OUTPUT_FILE)
