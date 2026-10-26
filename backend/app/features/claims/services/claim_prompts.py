"""Prompts of the CV claim verification (claim_service.py)."""
from app.graphs.qa_analysis_prompts import SPEECH_TO_TEXT

FAIR = ("Use only the CV text and the candidate's interview lines you are given. Be neutral and respectful: these are "
        "prompts for the interviewer's follow-up questions, never accusations. Never say or suggest that the candidate "
        "lied, exaggerated, faked or was dishonest, and never say whether to hire or reject. Never judge voice, accent, "
        "confidence or appearance, age, gender, family, religion, nationality or health.")

EXTRACT_PROMPT = f"""You read a candidate's CV for a job. List up to 8 concrete, checkable CLAIMS the CV makes that matter
for the job: years of experience with a skill, a role or responsibility, a project, a result with a number, a
qualification. Skip vague phrases ("team player", "hard-working").
For each give "claim" (one short neutral sentence) and "cv_quote" (a few words copied EXACTLY from "cv_text").
{FAIR}
Answer: {{"claims": [{{"claim": "...", "cv_quote": "..."}}]}}"""

COMPARE_PROMPT = f"""You compare CV claims with what the candidate said in the interview. The candidate's interview
lines are numbered ("lines"). For every claim ("n") give:
  "status": "supported"      the interview clearly backs the claim up
            "contradicted"   the candidate said something that does not fit the claim (e.g. a different number of years)
            "unverified"     the topic came up, but the answer did not back the claim up
            "not_discussed"  the interview never touched this claim
  "line": the number of the interview line your quote is from (0 for not_discussed)
  "interview_quote": a few words copied EXACTLY from that line ("" for not_discussed)
  "note": one short neutral sentence about what was found
  "follow_up": one polite open question the interviewer could ask to clarify ("" when supported)
Only say "contradicted" when the candidate's own words clearly do not fit the claim.
{SPEECH_TO_TEXT}
{FAIR}
Answer: {{"claims": [{{"n": 1, "status": "...", "line": 3, "interview_quote": "...", "note": "...", "follow_up": "..."}}]}}"""
