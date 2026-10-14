"""Prompt of the interview invitation workflow (invitation_graph.py)."""

# Step "write_draft": the AI writes the invitation email.
# The AI never gets the candidate's email address. It writes {join_link} where the link goes; code puts in the real
# link, so the AI can never write a wrong link. The calendar invite is made by code too (calendar_service.py).
INVITATION_PROMPT = (
    "You write an interview invitation email for a recruiter. The data has the candidate's name, the job title, "
    "the interview date and time (already written for the reader, with the time zone), the length in minutes and the "
    "interviewer's name. Write a warm, professional email in plain English: greet the candidate by name, thank them "
    "for applying, invite them to an online video interview for the job, give the date, time and length exactly as "
    "given, and say how to join: write the placeholder {join_link} on its own line where the link goes (never invent "
    "a link). Say that the link is personal, that a calendar invite is attached, and that they need a computer or "
    "phone with a camera, a microphone and a stable internet connection, in a quiet place. Ask them to "
    "reply if the time does not suit them. Close with the interviewer's name and \"Hiring team\". "
    "Do not invent a company name, an address, a salary or anything else that is not in the data. "
    "At most 220 words. Plain text, no Markdown. "
    "If the data has \"fix_these\", your earlier draft had these problems: write it again without them. "
    "Return JSON: {\"subject\": \"...\", \"body\": \"...\"}"
)

# "Schedule all": the AI writes ONE invitation for the whole shortlist. The name, date and time are placeholders
# such as {candidate_name}; code fills them in for each candidate (invitation_service.fill_template).
INVITATION_TEMPLATE_PROMPT = INVITATION_PROMPT + (
    " The candidate's name, the date and the time are placeholders in curly brackets, like {candidate_name}, {date} "
    "and {time}: copy each placeholder exactly as written, because code fills them in for every candidate."
)
