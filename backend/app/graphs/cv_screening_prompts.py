"""Prompts of the CV screening workflow (cv_screening_graph.py)."""

# Step "ocr_once": the AI reads a PDF whose text the code could not get (a scanned CV, a CV made of pictures).
OCR_PROMPT = (
    "This PDF is a CV (resume). Write down ALL the text you see on every page, in reading order, as plain text. "
    "Include text inside pictures, tables, columns, headers and footers. Do not summarise, do not add anything, "
    "do not describe photos or logos. If a page has no text, skip it.")

# Step "extract_profile": ONE call per CV. The CV text becomes fields, and the same call judges each requirement by
# meaning (met / partial / unmet, with words copied from the CV) and the qualification ("BSc in CSE or similar").
# One call instead of several keeps the free Gemini quota for more CVs. Python checks every quote afterwards.
EXTRACT_PROFILE_PROMPT = (
    "You read a CV (resume) for a recruiter. The data has \"cv\": the text of the CV (email addresses and phone "
    "numbers were removed), \"requirements\": the skills the job asks for, and \"required_qualification\": the "
    "qualification the job asks for (may be empty). "
    "Return only facts that are written in the CV. Do not guess and do not add anything. "
    "Ignore age, gender, marital status, photo, religion, nationality and other personal details: they are not "
    "used. "
    "\"skills\": every technical skill, tool, language and framework named anywhere in the CV (also inside the "
    "job descriptions), each as a short name, for example \"Python\", \"PostgreSQL\", \"Docker\". "
    "\"total_years\": the total years of professional work experience as a number (add up the jobs; count "
    "overlapping jobs once; internships count half; 0 if there is none). "
    "\"education\": each degree as {\"degree\": \"...\", \"institute\": \"...\"}. "
    "\"experience\": each job as {\"title\": \"...\", \"company\": \"...\", \"years\": 0}. "
    "\"language\": the language the CV is written in, as a two-letter code, for example \"en\". "
    "\"requirement_checks\": for EACH item of requirements, judge by meaning, not only by the exact words: "
    "\"met\" = the CV clearly shows it (also with other words, e.g. \"designed test plans\" for \"Test planning\"); "
    "\"partial\" = the CV shows something close or related but not the same (e.g. MySQL for PostgreSQL, or one "
    "part of \"A and B\"); \"unmet\" = nothing in the CV. For met and partial give \"evidence\": a few words "
    "copied EXACTLY from the CV (at most 20 words, no changes); for unmet use \"\". "
    "\"qualification_status\": \"met\", \"partial\" (a related field, or a lower degree) or \"unmet\" for the "
    "required qualification. Accept a degree with a different name as met only if it is clearly the same field, or "
    "if the requirement says \"or similar\" / \"or equivalent\". Use null if required_qualification is empty. "
    "\"qualification_reason\": one short sentence that names the degree from the CV (empty if not needed). "
    "Return JSON: {\"skills\": [], \"total_years\": 0, \"education\": [], \"experience\": [], \"language\": \"en\", "
    "\"requirement_checks\": [{\"requirement\": \"\", \"status\": \"met\", \"evidence\": \"\"}], "
    "\"qualification_status\": null, \"qualification_reason\": \"\"}"
)

# Step "score_sections" (F4): ONE call gives the three section scores. Python then checks every quote
# (check_quotes) and does the weighted maths (combine_score); the AI never sees the weights.
SCORE_SECTIONS_PROMPT = (
    "You score a CV (resume) against a job for a recruiter. The data has \"job\": the title, the required and "
    "preferred skills, the minimum years and the qualification, and \"cv\": the CV text (email and phone removed). "
    "Give three scores from 0 to 100: "
    "\"skills\": how well the technical skills in the CV cover the required skills (and the preferred ones); "
    "\"experience\": how well the work experience fits the job, its length compared with the minimum years and how "
    "relevant it is; "
    "\"qualifications\": how well the education and certificates fit the required qualification. "
    "Rough guide: 90-100 clearly exceeds, 70-89 meets, 40-69 partly meets, 0-39 does not meet. "
    "Judge only what is written in the CV. Never consider age, gender, photo, religion, nationality or other "
    "personal details. "
    "For each score give \"reason\": one short sentence, and \"quote\": a few words copied EXACTLY from the CV that "
    "support the score (at most 20 words, no changes); use \"\" if the CV has nothing to quote. "
    "Return JSON: {\"skills\": {\"score\": 0, \"reason\": \"\", \"quote\": \"\"}, "
    "\"experience\": {\"score\": 0, \"reason\": \"\", \"quote\": \"\"}, "
    "\"qualifications\": {\"score\": 0, \"reason\": \"\", \"quote\": \"\"}}"
)

# Before screening a job (once per job, saved on the job): the keywords an ATS (applicant tracking system) would look
# for in a CV. Python then counts how many of them each CV contains: that is the ATS match score.
ATS_KEYWORDS_PROMPT = (
    "You prepare an ATS (applicant tracking system) keyword list for a job. The data has the job's title, "
    "description, required and preferred skills and qualification. Return the 10 to 25 most important keywords a "
    "recruiter would look for in a CV for this job: technical skills, tools, methods and short domain terms, each as "
    "it is usually written in a CV (for example \"Pytest\", \"REST API\", \"SQL\", \"test automation\"). "
    "Do not include soft skills, the company name, dates, places or personal details. "
    "Return JSON: {\"keywords\": [\"...\"]}"
)
