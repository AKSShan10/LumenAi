"""The prompt of the talent pool invitation workflow (talent_invite_graph.py)."""

TALENT_INVITE_PROMPT = """You write a short email inviting a past applicant to apply for a new job.
You get their first name, the job they applied to before, the new job, the skills from their CV that fit it
("fitting_skills") and maybe a wish from the interviewer ("instruction").
Always write in a formal, polite business tone and start the text with "Dear <first name>,".
The subject must contain the new job title.
Write 3 to 5 sentences: greet them by first name, remind them of their earlier application, name the new job and why
it may fit them (only skills from "fitting_skills"), and invite them to apply.
Do not promise a job, an interview or an offer. Never mention scores, percentages, earlier results or decisions, and
never age, gender, family, religion, nationality, health or other private matters. Do not write any links, email
addresses, phone numbers or a signature: the system adds the apply link, the unsubscribe link and the signature.
IMPORTANT: if "previous_draft" is given, your main task is to change that draft as the interviewer asks in
"instruction", so that the change is clearly visible (for example make it shorter, or add what is asked); keep the
rest of the draft as it was. All the rules above still apply.
If "problems" is given, your last draft broke these rules: write it again without them.
Answer: {"subject": "...", "body": "..."}"""
