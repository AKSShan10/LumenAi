"""Prompts of the job description workflow (job_description_graph.py)."""

# Step "write_draft": a short free-text prompt becomes a full job profile.
JOB_DRAFT_PROMPT = (
    "You help a recruiter turn a short free-text prompt into a job profile and a job description in English. "
    "The data has: the recruiter's prompt; \"examples\" = past job descriptions of the same company; "
    "\"company_policy\" = policy notes of the same company. "
    "Take every requirement from the prompt only. Use the examples only for structure, tone and wording. "
    "Follow the company policy notes where they apply to a job description. "
    "Write a description of 120 to 200 words: a short summary, the main responsibilities and the requirements. "
    "Do not invent a salary, location or benefits. Use neutral, inclusive language. "
    "If the data has \"change_request\", the recruiter read \"previous_description\" and wants it changed: "
    "write a new version that follows the change request. The change request counts like the prompt: "
    "it may add or remove requirements and may change the length, tone or focus. "
    "Return JSON: {\"title\": \"...\", \"required_skills\": [\"...\"], \"preferred_skills\": [\"...\"], "
    "\"min_years\": 0, \"qualifications\": \"...\", \"description\": \"...\"}"
)

# Step "revise_draft": the code check found problems; the AI fixes exactly those.
JOB_REVISE_PROMPT = (
    "You wrote a job profile for a recruiter, and a check found problems. "
    "The data has the recruiter's prompt, an optional change request, your draft, the list of problems, "
    "and the same examples and company policy. "
    "Fix every problem in the list and change nothing else. Keep the rules: every requirement comes from the prompt or the change request, "
    "the description has 120 to 200 words, no invented salary, location or benefits. "
    "Return JSON in the same form: {\"title\": \"...\", \"required_skills\": [\"...\"], \"preferred_skills\": [\"...\"], "
    "\"min_years\": 0, \"qualifications\": \"...\", \"description\": \"...\"}"
)
