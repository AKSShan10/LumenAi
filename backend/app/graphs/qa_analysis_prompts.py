"""Prompts of the Q&A analysis workflow (qa_analysis_graph.py)."""

# The transcript is made by speech-to-text, so a word can be misheard ("student group" for "status code").
SPEECH_TO_TEXT = ("The transcript comes from speech-to-text, so some words may be misheard (for example \"student "
                  "group\" instead of \"status code\"). Read every question and answer by its most likely meaning "
                  "in this job interview.")

FAIR = ("Judge only the words of the answer. Never judge voice, accent, fluency, pauses, speed, confidence or "
        "appearance, and never age, gender, family, religion, nationality, health or other private matters. "
        "Never lower a grade because of a word the speech-to-text clearly misheard. "
        "Your grades help a person; you never decide whether to hire the candidate.")

SEGMENT_PROMPT = """You read the transcript of a job interview: numbered lines ("n"), each said by the Interviewer or
the Candidate. Find every question the interviewer asked and the candidate's answer to it.
{stt}
For each pair give:
  "question": the question in the interviewer's words (shortened if it is long), with clearly misheard words corrected
  "question_lines": the line numbers of the question
  "answer_lines": the line numbers of the candidate's answer (Candidate lines only)
  "job_related": false for small talk (greetings, "can you hear me", thanks, the next steps), true otherwise
  "split": true when this pair is one part of a question that asked several things
If one question asks several things (for example "What is Docker and how did you use it?"), make one pair per part,
each with its own question text and the same answer lines, and set "split": true.
Leave out questions the candidate did not answer. Keep the order of the interview.
Answer: {{"pairs": [{{"question": "...", "question_lines": [1], "answer_lines": [2, 3], "job_related": true,
            "split": false}}]}}""".format(stt=SPEECH_TO_TEXT)

REQUIREMENTS_PROMPT = """You get question and answer pairs ("n") from a job interview and the job's requirements.
For every pair, list the requirements the question and answer are about. Use only names from "requirements", written
exactly as given. A pair may test none, one or several requirements.
{stt}
Answer: {{"pairs": [{{"n": 1, "requirements": ["..."]}}]}}""".format(stt=SPEECH_TO_TEXT)

# What each of the four graders looks at (one AI call per criterion, all four run at the same time)
CRITERIA = {
    "relevance": "Relevance: does the answer address what was asked?",
    "accuracy": ("Accuracy: is what the candidate says correct? When a company note (\"company_notes\") covers the "
                 "topic, compare the answer with that note and name it in \"sources\". Otherwise use general "
                 "knowledge and give \"sources\": []."),
    "completeness": ("Completeness: does the answer cover every part of the question, with enough detail (for "
                     "example what was done, how, why and the result)? Also give \"follow_up\": one short follow-up "
                     "question the interviewer could ask to fill what is missing (\"\" when nothing is missing)."),
    "articulation": ("Articulation: are the answer's words clear and well organised in the transcript: on topic, in "
                     "a logical order, easy to follow? This is about the written words only, never about how the "
                     "candidate sounds."),
}

GRADE_PROMPT = """You grade a candidate's answers from a job interview on ONE criterion.
{criterion}
{stt}
Grades: 100 excellent, 75 good, 50 partly, 25 weak, 0 not at all.
For every pair ("n") give "grade" (exactly 0, 25, 50, 75 or 100), "reason" (one short sentence), and "quote": a few
words copied exactly from the answer that show why.
{fair}
Answer: {{"grades": [{{"n": 1, "grade": 75, "reason": "...", "quote": "...", "sources": [], "follow_up": ""}}]}}"""

GRADE_PROMPTS = {name: GRADE_PROMPT.format(criterion=text, stt=SPEECH_TO_TEXT, fair=FAIR)
                 for name, text in CRITERIA.items()}
