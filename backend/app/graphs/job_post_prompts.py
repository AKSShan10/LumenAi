"""Prompts of the job post workflow (job_post_graph.py)."""

# Step "write_post": an approved job becomes a short post for the Telegram channel.
JOB_POST_PROMPT = (
    "You help a recruiter announce an approved job in a Telegram channel. "
    "The data has the job: title, required_skills, preferred_skills, min_years, qualifications and description. "
    "Write a short post in plain English text, 60 to 150 words: the job title on the first line, two or three "
    "sentences about the role, then the main requirements as short lines that start with a dash. "
    "Use only facts from the job. Do not invent a salary, location, deadline or benefits. "
    "Do not use Markdown or HTML. Do not write any link or 'apply' line: the application link is added afterwards. "
    "Use neutral, inclusive language. "
    "If the data has \"change_request\", the recruiter read \"previous_post\" and wants it changed: write a new "
    "version that follows the change request for length, tone and focus, still using only facts from the job. "
    "Return JSON: {\"text\": \"...\"}"
)

# Step "revise_post": the code check found problems; the AI fixes exactly those.
JOB_POST_REVISE_PROMPT = (
    "You wrote a Telegram post for a job, and a check found problems. "
    "The data has the job, an optional change request, your post and the list of problems. Fix every problem and change nothing else. "
    "Keep the rules: 60 to 150 words, the job title on the first line, only facts from the job, no links, "
    "no Markdown or HTML. "
    "Return JSON in the same form: {\"text\": \"...\"}"
)
