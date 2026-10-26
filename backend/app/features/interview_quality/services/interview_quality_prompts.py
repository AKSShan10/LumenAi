"""Prompts of the interview quality assessment (interview_quality_service.py, F10)."""
from app.graphs.qa_analysis_prompts import SPEECH_TO_TEXT

FAIR = ("You assess the interview process and the interviewer's questions, never a person's worth. Use only the facts "
        "and question texts you are given. Be constructive and respectful: the aim is a better next interview. Never "
        "judge voice, accent, tone, confidence, speed or appearance of anyone, nor age, gender, family, religion, "
        "nationality or health. Never rate the candidate and never say whether to hire or reject.")

GRADE_QUESTIONS_PROMPT = f"""You review the questions an interviewer asked in a job interview. You get the job title,
the job requirements and the questions ("n").
For every question give:
  "relevance": a whole number from 0 to 100: how well the question tests something this job needs
               (90-100 directly tests a requirement, 50-89 related, 0-49 not useful for this job)
  "open": true if it invites an explanation (how, why, describe, tell me about), false for yes/no or one-word questions
  "reason": one short sentence
  "better": a clearer, more open way to ask the same thing, or "" when the question is already good
{SPEECH_TO_TEXT}
{FAIR}
Answer: {{"questions": [{{"n": 1, "relevance": 80, "open": true, "reason": "...", "better": ""}}]}}"""

RECOMMEND_PROMPT = f"""You help an interviewer improve the next interview. You get facts that code has measured:
  "not_asked"       job requirements no question covered
  "no_signal"       requirements that were asked, but the answers showed nothing about them
  "low_signal"      questions whose answers gave little information (with the reason)
  "low_relevance"   questions that did not test much the job needs
  "talk"            the interviewer's share of the speaking time (percent) and whether it is balanced
  "uneven"          requirements asked in some interviews for this job but not in others
Write "summary": two or three sentences about the overall quality of the interview process.
Write "recommendations": 3 to 5 concrete improvements. Each must be based on ONE fact above:
  "basis": "requirement" (ref = a name from not_asked or no_signal), "question" (ref = a question number from
           low_signal or low_relevance), "talk" (ref = ""), or "consistency" (ref = a name from uneven)
  "text": one or two sentences: what to do differently next time
Do not invent facts that are not in the list.
{FAIR}
Answer: {{"summary": "...", "recommendations": [{{"basis": "requirement", "ref": "Docker", "text": "..."}}]}}"""
