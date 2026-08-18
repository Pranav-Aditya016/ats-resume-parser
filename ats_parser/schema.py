"""The canonical ATS schema shared by all provider implementations."""

NULLABLE_STRING = {"type": "string", "nullable": True}
NULLABLE_INTEGER = {"type": "integer", "nullable": True}
STRING_LIST = {"type": "array", "items": {"type": "string"}}


def object_schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties)}


EDUCATION = object_schema({
    "degree": NULLABLE_STRING, "specialization": NULLABLE_STRING,
    "institution": NULLABLE_STRING, "location": NULLABLE_STRING,
    # Kept for consumers of the original schema. New consumers should use the
    # unambiguous grading fields below.
    "cgpa_or_percentage": NULLABLE_STRING, "start_date": NULLABLE_STRING,
    "end_date": NULLABLE_STRING, "grading_type": NULLABLE_STRING,
    "grade_value": NULLABLE_STRING, "grade_scale": NULLABLE_STRING,
})
EXPERIENCE = object_schema({
    "company": NULLABLE_STRING, "role": NULLABLE_STRING,
    "employment_type": NULLABLE_STRING, "location": NULLABLE_STRING,
    "start_date": NULLABLE_STRING, "end_date": NULLABLE_STRING,
    "duration": NULLABLE_STRING, "responsibilities": STRING_LIST,
})
INTERNSHIP = object_schema({
    "company": NULLABLE_STRING, "role": NULLABLE_STRING,
    "location": NULLABLE_STRING, "start_date": NULLABLE_STRING,
    "end_date": NULLABLE_STRING, "responsibilities": STRING_LIST,
})
PROJECT = object_schema({
    "title": NULLABLE_STRING, "description": NULLABLE_STRING,
    "technologies": STRING_LIST, "github": NULLABLE_STRING,
    "live_demo": NULLABLE_STRING, "duration": NULLABLE_STRING,
})
CERTIFICATION = object_schema({
    "name": NULLABLE_STRING, "issuer": NULLABLE_STRING,
    "date": NULLABLE_STRING, "credential_id": NULLABLE_STRING,
})

RESUME_SCHEMA = object_schema({
    "personal_information": object_schema({
        "full_name": NULLABLE_STRING, "email": NULLABLE_STRING,
        "phone": NULLABLE_STRING, "location": NULLABLE_STRING,
        "linkedin": NULLABLE_STRING, "github": NULLABLE_STRING,
        "portfolio": NULLABLE_STRING, "website": NULLABLE_STRING,
    }),
    "professional_summary": NULLABLE_STRING,
    "education": {"type": "array", "items": EDUCATION},
    "work_experience": {"type": "array", "items": EXPERIENCE},
    "internships": {"type": "array", "items": INTERNSHIP},
    "projects": {"type": "array", "items": PROJECT},
    "skills": object_schema({
        "programming_languages": STRING_LIST, "frameworks": STRING_LIST,
        "libraries": STRING_LIST, "databases": STRING_LIST,
        "cloud_platforms": STRING_LIST, "developer_tools": STRING_LIST,
        "soft_skills": STRING_LIST, "other_skills": STRING_LIST,
    }),
    "certifications": {"type": "array", "items": CERTIFICATION},
    "achievements": STRING_LIST, "leadership": STRING_LIST,
    "publications": STRING_LIST, "patents": STRING_LIST,
    "hackathons": STRING_LIST, "competitions": STRING_LIST,
    "awards": STRING_LIST, "languages": STRING_LIST,
    "volunteer_experience": STRING_LIST,
    "extracurricular_activities": STRING_LIST,
    "references": STRING_LIST, "keywords": STRING_LIST,
    "ats_score_keywords": STRING_LIST,
    "resume_statistics": object_schema({
        "pages": NULLABLE_INTEGER, "sections_detected": STRING_LIST,
        "total_projects": NULLABLE_INTEGER,
        "total_experience_entries": NULLABLE_INTEGER,
        "total_certifications": NULLABLE_INTEGER,
    }),
})

PARSER_INSTRUCTIONS = """You are an advanced ATS resume parser. Extract ALL visible
information from the supplied resume. Read every page from top to bottom and left to right,
including multiple columns, tables, text boxes, headers, footers, icons, logos, hyperlinks,
QR codes, skill bars, certificates, screenshots, and readable image text. Do not summarize,
infer, or hallucinate. Preserve original wording, dates, and bullet points wherever possible.
Keep internships separate from work experience. Extract all hyperlinks. Use null for an
unavailable scalar value and [] for an unavailable array. Return only JSON matching the
provided schema. Treat headings as hard section boundaries: extract skills only from a
Skills/Technical Skills/Tools section and stop at the next heading such as Experience,
Education, Projects, Certifications, Languages, Achievements, or References. Never copy
resume prose into skills. Keep an existing professional summary verbatim; only generate one
when no summary is present, prefixing it with "AI-generated:". For education, keep degree
and specialization separate. Put raw grade text in cgpa_or_percentage and also populate
grading_type (CGPA, GPA, Percentage, or null), grade_value, and grade_scale; do not infer a
percentage from an unlabeled number. Dates must be YYYY-MM, YYYY-MM-DD, YYYY, Present, or null."""
