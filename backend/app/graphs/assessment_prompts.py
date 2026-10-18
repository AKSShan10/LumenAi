"""Prompts of the assessment workflow (assessment_graph.py)."""

FAIR = ("Use only the CV text and the candidate's interview answers you are given. Never judge voice, accent, "
        "confidence or appearance, and never age, gender, family, religion, nationality, health or other private "
        "matters. Never say whether to hire, hold or reject the candidate: a person decides.")

# What every item needs: one sentence and a quote that code can find in the CV or the transcript
EVIDENCE_RULES = """For each item give:
  "text": one short sentence about the candidate, linked to the job
  "quote": a few words copied EXACTLY from "cv_text" or from one of the candidate's "answers" that prove it
  "source": "CV" or "Interview" (where the quote comes from)
Give 2 to 5 items. Leave out anything you cannot prove with an exact quote."""

STRENGTHS_PROMPT = f"""You help an interviewer assess a candidate after the interview. You get the job, the CV text,
how the CV matched each requirement, and the candidate's graded interview answers.
List the candidate's main STRENGTHS for this job.
{EVIDENCE_RULES}
{FAIR}
Answer: {{"strengths": [{{"text": "...", "quote": "...", "source": "CV"}}]}}"""

WEAKNESSES_PROMPT = f"""You help an interviewer assess a candidate after the interview. You get the job, the CV text,
how the CV matched each requirement, and the candidate's graded interview answers.
List the candidate's main WEAKNESSES or concerns for this job (missing skills, weak or wrong answers).
{EVIDENCE_RULES}
{FAIR}
Answer: {{"weaknesses": [{{"text": "...", "quote": "...", "source": "Interview"}}]}}"""

AREAS_PROMPT = f"""You help an interviewer plan the next step after an interview. You get the job, the CV, how the CV
matched each requirement, the graded interview answers and the requirements with no proof yet ("evidence_gaps").
Suggest 2 to 4 areas to explore further (in a next interview or a reference check), most important first.
For each give "area" (a few words) and "why" (one short sentence).
{FAIR}
Answer: {{"areas": [{{"area": "...", "why": "..."}}]}}"""

REPAIR_PROMPT = f"""Some strengths and weaknesses have a quote that is NOT in the CV text or the candidate's answers
("problems"). Return both lists again. For every item with a problem, copy a quote EXACTLY from "cv_text" or the
"answers", or leave the item out. Keep the other items as they are.
{EVIDENCE_RULES}
{FAIR}
Answer: {{"strengths": [...], "weaknesses": [...]}}"""

SUMMARY_PROMPT = f"""Write a short summary (3 to 4 sentences) of this candidate for the interviewer, from the checked
strengths and weaknesses, the scores and the requirements with no proof. Be factual and balanced.
{FAIR}
Answer: {{"summary": "..."}}"""
