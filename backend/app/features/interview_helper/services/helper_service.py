"""The interview helper (co-pilot): suggested questions with model answers, and a chat. Interviewer only.

One AI call each, no LangGraph: the AI gets the facts, answers once, and plain code checks the answer.

RAG: before each call, the company documents (kind "policy") most similar to the question or topic are found
(company_document_service.find_documents) and given to the AI as "company_notes". The AI must name the note it used
("source"); code keeps only names of notes it really got, so a made-up source is removed. When no document is similar
enough, the list is empty, the AI is told not to claim anything about the company, and the page says so.

    context(session, interview)                   what the AI may know: the job, the CV profile, the must-haves
                                                  the CV did not show, the last transcript sentences, company notes
    suggest_questions(session, interview, topic)  up to 8 questions, each with the requirement it tests, why, and a
                                                  model answer; saved as one helper_message (kind "questions")
    chat(session, interview, text)                the interviewer asks, the helper answers; both are saved
    history(session, interview)                   everything asked and answered for this interview, oldest first

Rules: the AI only suggests. It never scores the candidate, never decides, never sees the candidate's email address,
and is told never to ask about age, family, religion, health or other private matters.
"""
import logging

from fastapi import HTTPException
from sqlmodel import Session, select

from app.ai.llm_client import last_error, llm_json
from app.features.candidates.models import Candidate
from app.features.interview_helper.models import HelperMessage
from app.features.interview_helper.schemas import HelperMessageOut
from app.features.interviews.models import InterviewSession
from app.features.job_library.services.company_document_service import (
    MIN_EXAMPLE_SIMILARITY, TOP_POLICIES, find_documents)
from app.features.jobs.models import Job
from app.features.screening.models import ScreeningResult
from app.features.transcripts.models import TranscriptTurn

log = logging.getLogger("interview_helper")

MAX_QUESTIONS = 8          # the most questions shown in one list
LAST_SENTENCES = 40        # how many of the newest transcript sentences the AI sees
LAST_CHAT = 6              # how many of the newest chat messages the AI sees
LAST_LISTS = 3             # earlier question lists the AI sees, so it does not suggest the same questions again
MIN_NOTE_SIMILARITY = MIN_EXAMPLE_SIMILARITY   # a company note less similar than this is not given to the AI
FAIR = ("Never suggest questions about age, gender, marital status, family, pregnancy, religion, nationality, race, "
        "health, disability or other private matters. Never judge voice, appearance or confidence.")

QUESTIONS_PROMPT = f"""You help an interviewer during a live job interview.
You get the job, what the candidate's CV shows, the job requirements the CV did not show ("not_shown_in_cv"),
the newest part of the interview transcript, company notes ("company_notes": [{{"title", "text"}}]), an optional topic,
and questions already suggested.
Suggest up to {MAX_QUESTIONS} new interview questions for this candidate. Prefer requirements the CV did not show
and good follow-ups to what was just said. If a topic is given, keep to it. Do not repeat "already_suggested".
For each question give:
  "question": the question to ask, one or two sentences
  "requirement": the job requirement it tests, in a few words (for example "PostgreSQL" or "teamwork")
  "why": one short sentence why it is worth asking this candidate
  "model_answer": what a strong answer would contain, two to four sentences. It is a reference, not a score.
                  When a company note covers the topic, base the model answer on that note.
  "source": the exact "title" of the company note you used, or "" when you used none.
Use only the company notes you are given; never invent company rules, tools or facts. If "company_notes" is empty,
base everything on the job, the CV and the transcript, and do not mention the company's own practice.
{FAIR}
Answer: {{"questions": [{{"question": "...", "requirement": "...", "why": "...", "model_answer": "...", "source": "..."}}]}}"""

CHAT_PROMPT = f"""You help an interviewer during a live job interview. Answer the interviewer's last message in
"conversation", briefly and practically, using the job, the candidate's CV profile, the transcript and company notes.
Start with one short sentence. When you list things (for example questions), put every item on its own line:
"1. ...\n2. ...\n3. ...". You may suggest questions or explain a topic.
Use only the company notes you are given; never invent company rules, tools or facts. If "company_notes" is empty and
the interviewer asks about the company's own rules, say that no company document covers it.
You never decide whether to hire the candidate and never give the candidate a score: a person decides.
{FAIR}
Answer: {{"answer": "...", "sources": ["<title of each company note you used>"]}}"""


def context(session: Session, interview: InterviewSession, query: str = "") -> dict:
    """The facts the AI gets for this interview. Never the candidate's email address.
    query: the topic or the interviewer's question, used to find the most related company notes (RAG)."""
    job = session.get(Job, interview.job_id)
    candidate = session.get(Candidate, interview.candidate_id)
    result = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == interview.candidate_id)).first()
    parsed = (result.parsed or {}) if result else {}
    # the must-haves and nice-to-haves the screening did not find in the CV: good things to ask about
    not_shown = [m.get("requirement", "") for m in ((result.matches or []) if result else [])
                 if m.get("status") != "met"]                   # unmet, partial or not checked
    # the newest transcript sentences, oldest first, as "Interviewer: ..." / "Candidate: ..."
    newest = session.exec(select(TranscriptTurn).where(TranscriptTurn.session_id == interview.id)
                          .order_by(TranscriptTurn.start_sec.desc()).limit(LAST_SENTENCES)).all()
    transcript = [f"{t.speaker.capitalize()}: {t.text}" for t in reversed(newest)]
    # company policy notes most related to this job (RAG: the search compares meanings, see company_document_service)
    # RAG: the company notes most similar to the question (or the job), only if similar enough
    search = f"{query} {job.title} {' '.join(job.required_skills or [])}".strip()
    notes = find_documents(session, search, "policy", TOP_POLICIES, MIN_NOTE_SIMILARITY)
    log.info("helper rag session=%s notes=%s", interview.id, [n["title"] for n in notes] or "none")
    return {
        "job": {"title": job.title, "description": (job.description or "")[:2000],
                "required_skills": job.required_skills or [], "preferred_skills": job.preferred_skills or [],
                "min_years": job.min_years, "qualifications": job.qualifications},
        "candidate": {"name": candidate.full_name if candidate else "", "skills": parsed.get("skills", []),
                      "total_years": parsed.get("total_years", 0),
                      "experience": [e.get("title", "") for e in parsed.get("experience", []) if isinstance(e, dict)],
                      "education": [e.get("degree", "") for e in parsed.get("education", []) if isinstance(e, dict)]},
        "not_shown_in_cv": [r for r in not_shown if r],
        "transcript": transcript,
        "company_notes": [{"title": n["title"], "text": n["text"]} for n in notes],
    }


def suggest_questions(session: Session, interview: InterviewSession, topic: str = "") -> HelperMessageOut:
    """Asks the AI for up to 8 questions, checks them in code, saves the list and returns it."""
    earlier = session.exec(select(HelperMessage).where(HelperMessage.session_id == interview.id,
                                                       HelperMessage.kind == "questions")
                           .order_by(HelperMessage.id.desc()).limit(LAST_LISTS)).all()
    facts = context(session, interview, topic)
    facts["topic"] = topic.strip()
    titles = {n["title"] for n in facts["company_notes"]}      # the only sources that may be named
    facts["already_suggested"] = [q["question"] for row in earlier for q in row.questions]

    answer = llm_json(QUESTIONS_PROMPT, facts)                  # → the AI call (Gemini, or the fake AI in tests)
    if not isinstance(answer, dict):
        raise HTTPException(502, f"The AI did not answer ({last_error()}). Please try again.")

    # Code checks the AI's answer: only complete questions, text trimmed, at most 8
    questions = []
    for item in answer.get("questions") or []:
        if not isinstance(item, dict) or not str(item.get("question") or "").strip():
            continue                                            # skip anything that is not a real question
        source = str(item.get("source") or "").strip()
        if source not in titles:
            source = ""                                         # a note the AI was not given is made up: removed
        questions.append({"question": str(item["question"]).strip()[:500],
                          "requirement": str(item.get("requirement") or "General").strip()[:100],
                          "why": str(item.get("why") or "").strip()[:300],
                          "model_answer": str(item.get("model_answer") or "").strip()[:1200],
                          "source": source})
    questions = questions[:MAX_QUESTIONS]
    if not questions:
        raise HTTPException(502, "The AI gave no usable questions. Please try again.")

    row = HelperMessage(session_id=interview.id, role="helper", kind="questions", text=topic.strip()[:200],
                        questions=questions, sources=sorted({q["source"] for q in questions if q["source"]}))
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(row)


def chat(session: Session, interview: InterviewSession, text: str) -> list[HelperMessageOut]:
    """Saves the interviewer's message, asks the AI, saves its answer. Returns both messages."""
    mine = HelperMessage(session_id=interview.id, role="interviewer", kind="chat", text=text.strip()[:1000])
    session.add(mine)
    session.commit()
    session.refresh(mine)

    recent = session.exec(select(HelperMessage).where(HelperMessage.session_id == interview.id,
                                                      HelperMessage.kind == "chat")
                          .order_by(HelperMessage.id.desc()).limit(LAST_CHAT)).all()
    facts = context(session, interview, text)
    titles = {n["title"] for n in facts["company_notes"]}
    facts["conversation"] = [{"from": m.role, "text": m.text} for m in reversed(recent)]   # oldest first

    answer = llm_json(CHAT_PROMPT, facts)                       # → the AI call
    reply = str(answer.get("answer") or "").strip() if isinstance(answer, dict) else ""
    used = answer.get("sources") if isinstance(answer, dict) and isinstance(answer.get("sources"), list) else []
    used = sorted({str(t) for t in used if str(t) in titles})   # only notes the AI really got
    if not reply:
        reply = f"Sorry, the AI did not answer ({last_error() or 'empty answer'}). Please ask again."
    theirs = HelperMessage(session_id=interview.id, role="helper", kind="chat", text=reply[:4000], sources=used)
    session.add(theirs)
    session.commit()
    session.refresh(theirs)
    return [_out(mine), _out(theirs)]


def history(session: Session, interview: InterviewSession) -> list[HelperMessageOut]:
    """Every question list and chat message of this interview, oldest first (the tab loads it when it opens)."""
    rows = session.exec(select(HelperMessage).where(HelperMessage.session_id == interview.id)
                        .order_by(HelperMessage.id)).all()
    return [_out(r) for r in rows]


def _out(row: HelperMessage) -> HelperMessageOut:
    """A saved row as the answer for the page."""
    return HelperMessageOut(id=row.id, role=row.role, kind=row.kind, text=row.text, questions=row.questions or [],
                            sources=row.sources or [], created_at=row.created_at)
