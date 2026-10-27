"""Interview quality assessment (F10): the quality of the interview process itself, not of the candidate.

Read this file from top to bottom:
    start(session, interview)    "Check interview quality": needs the finished Q&A analysis; marks it running
    result(session, interview)   the result for the analysis page (it asks every 3 s while "running")
    resume_running()             after a restart: checks that were still running start again
    run(session_id)              the check: the 8 steps in order, then save (or failed)
    then the 8 steps, in the same order as run() calls them:
    Step 1  load_inputs             Python + DB  the job, the finished Q&A analysis of this interview, the transcript,
                                                 and the other analysed interviews of the same job (for consistency)
    Step 2  grade_questions         AI           each interviewer question: relevance (0-100), open or closed, a
                                                 reason and a clearer wording when needed
    Step 3  measure_talk_time       Python       speaking time per speaker; balanced when the interviewer speaks at
                                                 most 40 % of the time
    Step 4  check_coverage          Python       each job requirement: shown | no_signal (asked, nothing shown) | not_asked
    Step 5  compare_consistency     Python       the same job's interviews side by side; requirements asked in some, not all
    Step 6  find_low_signal         Python       questions whose answers gave little information; the five scores and
                                                 the quality score (their average)
    Step 7  recommend_improvements  AI           a short summary and 3-5 improvements, each based on one measured fact
    Step 8  check_recommendations   Python       keeps only improvements whose fact really exists; removes judging
                                                 words; if none is left, code writes them from the facts

Search for "Step 3 of 8" to jump to a step; its small helpers are right below it. A step that cannot go on
raises CheckFailed, and run() saves the reason.

Plain Python, not LangGraph: only one step is AI and the others are quick Python, so the steps simply run one after
another. About 2 AI calls per interview.
The interviewer only. It judges the process, never a person, and never changes a candidate's score or a decision.
"""
import logging
import re
import time
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.ai.llm_client import last_error, llm_json
from app.core.database import engine
from app.features.candidates.models import Candidate
from app.features.interview_quality.models import InterviewQuality
from app.features.interview_quality.schemas import InterviewQualityOut
from app.features.interview_quality.services.interview_quality_prompts import GRADE_QUESTIONS_PROMPT, RECOMMEND_PROMPT
from app.features.interviews.models import InterviewSession
from app.features.jobs.models import Job
from app.features.qa_analysis.models import QaAnalysis, QaItem
from app.features.system.models import WorkflowRun
from app.features.transcripts.models import TranscriptTurn
from app.utils.datetime_utils import utc_now

log = logging.getLogger("interview_quality")

MAX_INTERVIEWER_SHARE = 40       # percent of the speaking time; above this the interview is not balanced
LOW_COMPLETENESS = 50            # an answer below this completeness grade gave little information
SHORT_ANSWER_WORDS = 15          # an answer shorter than this gave little information
LOW_RELEVANCE = 50               # a question below this relevance did not test much the job needs
MAX_RECOMMENDATIONS = 5
# Words that would judge a person instead of the process; a recommendation with one is removed
JUDGING = re.compile(r"\b(voice|accent|appearance|looks|confiden\w*|nervous\w*|gender|religio\w*|nationalit\w*|"
                     r"stupid|lazy|rude|incompetent)\b", re.IGNORECASE)
SCORE_NAMES = [("question_relevance", "Question relevance"), ("coverage", "Competency coverage"),
               ("signal", "Answer signal"), ("balance", "Speaking balance"), ("consistency", "Consistency")]


class CheckFailed(Exception):
    """A step could not go on; the message is shown on the page."""


# ---------- called by the router ----------

def _row(session: Session, session_id: int) -> InterviewQuality | None:
    """The interview_quality row of one interview, or None."""
    return session.exec(select(InterviewQuality).where(InterviewQuality.session_id == session_id)).first()


def start(session: Session, interview: InterviewSession) -> InterviewQualityOut:
    """"Check interview quality": needs the finished Q&A analysis; marks the check running."""
    analysis = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == interview.id)).first()
    if not analysis or analysis.status != "done":
        raise HTTPException(409, "Analyse the answers first. The interview quality uses the Q&A analysis.")
    row = _row(session, interview.id)
    if row and row.status == "running":
        raise HTTPException(409, "The interview quality check is already running. Please wait a moment.")
    row = row or InterviewQuality(session_id=interview.id)
    row.status, row.error, row.updated_at = "running", "", utc_now()          # the old result stays until the new one
    session.add(row)
    session.commit()
    return result(session, interview)


def result(session: Session, interview: InterviewSession) -> InterviewQualityOut:
    """The result for the analysis page (status not_started when nobody started it)."""
    row = _row(session, interview.id)
    if not row:
        return InterviewQualityOut(session_id=interview.id, status="not_started")
    return InterviewQualityOut(**row.model_dump(exclude={"id"}))


def resume_running() -> None:
    """Checks that were running when the backend stopped start again (main.py calls this at start)."""
    with Session(engine) as session:
        waiting = session.exec(select(InterviewQuality.session_id).where(InterviewQuality.status == "running")).all()
    for session_id in waiting:
        log.info("interview quality session=%s resumed after a restart", session_id)
        run(session_id)


# ---------- the check: 8 steps in order, then save or failed ----------

def run(session_id: int) -> None:
    """Runs the check for one interview and saves the result. The interview_quality row must exist. Never raises."""
    started = time.time()
    try:
        data = load_inputs(session_id)                 # Step 1; every later step reads data and adds its part
        data.update(grade_questions(data))             # Step 2  → AI call
        data.update(measure_talk_time(data))           # Step 3
        data.update(check_coverage(data))              # Step 4
        data.update(compare_consistency(data))         # Step 5
        data.update(find_low_signal(data))             # Step 6
        data.update(recommend_improvements(data))      # Step 7  → AI call
        data.update(check_recommendations(data))       # Step 8
        save(data, started)
    except CheckFailed as problem:
        failed(session_id, str(problem), started)
    except Exception:
        log.exception("interview quality check could not run")
        failed(session_id, "The interview quality check stopped unexpectedly. Please try again.", started)


# "save": the result replaces the old one
def save(data: dict, started: float) -> None:
    """Saves the result (it replaces the old one) and one workflow_run row."""
    with Session(engine) as session:
        row = session.exec(select(InterviewQuality).where(InterviewQuality.session_id == data["session_id"])).one()
        row.status, row.error, row.quality_score = "done", "", data["quality_score"]
        row.scores, row.talk, row.coverage = data["scores"], data["talk"], data["coverage"]
        row.questions, row.consistency = data["questions"], data["consistency"]
        row.summary, row.recommendations = data["summary"], data["recommendations"]
        session.add(row)
        session.add(WorkflowRun(stage="interview_quality", subject_id=data["session_id"], outcome="done",
                                seconds=round(time.time() - started, 2)))
        session.commit()
    log.info("interview quality session=%s done score=%s", data["session_id"], data["quality_score"])


# "failed": marked failed with the reason, so the page can show it
def failed(session_id: int, error: str, started: float) -> None:
    """Marks the check failed with the reason, so the page can show it."""
    with Session(engine) as session:
        row = session.exec(select(InterviewQuality).where(InterviewQuality.session_id == session_id)).first()
        if row:
            row.status, row.error = "failed", error
            session.add(row)
        session.add(WorkflowRun(stage="interview_quality", subject_id=session_id, outcome="failed",
                                error=error, seconds=round(time.time() - started, 2)))
        session.commit()
    log.info("interview quality session=%s failed: %s", session_id, error)


# ############################## the 8 steps ##############################


# ==================== Step 1 of 8: load_inputs ====================
# Python + DB: what the check needs, read once from the database
def load_inputs(session_id: int) -> dict:
    """The job, the finished Q&A analysis, the transcript and the job's other interviews."""
    with Session(engine) as session:
        interview = session.get(InterviewSession, session_id)
        job = session.get(Job, interview.job_id) if interview else None
        analysis = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == session_id)).first()
        if not job or not analysis or analysis.status != "done":
            raise CheckFailed("Analyse the answers first. The interview quality uses the Q&A analysis.")
        items = session.exec(select(QaItem).where(QaItem.session_id == session_id)
                             .order_by(QaItem.position)).all()
        turns = session.exec(select(TranscriptTurn).where(TranscriptTurn.session_id == session_id)
                             .order_by(TranscriptTurn.start_sec, TranscriptTurn.id)).all()

        # the other interviews of the same job that have a finished Q&A analysis (for consistency)
        interviews = []
        for other in session.exec(select(InterviewSession).where(InterviewSession.job_id == job.id,
                                                                 InterviewSession.status == "ended")).all():
            done = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == other.id,
                                                         QaAnalysis.status == "done")).first()
            if not done:
                continue
            asked = session.exec(select(QaItem).where(QaItem.session_id == other.id,
                                                      QaItem.job_related.is_(True))).all()
            spoken = session.exec(select(TranscriptTurn).where(TranscriptTurn.session_id == other.id)
                                  .order_by(TranscriptTurn.start_sec, TranscriptTurn.id)).all()
            candidate = session.get(Candidate, other.candidate_id)
            talk = _talk([{"speaker": t.speaker, "start": t.start_sec, "end": t.end_sec} for t in spoken])
            interviews.append({
                "session_id": other.id, "candidate": candidate.full_name if candidate else f"Candidate {other.candidate_id}",
                "date": other.ended_at.isoformat() if other.ended_at else "", "questions": len(asked),
                "minutes": round(max((t.end_sec for t in spoken), default=0) / 60, 1),
                "interviewer_share": talk["interviewer_share"],
                "asked": sorted({r for item in asked for r in (item.requirements or [])}),
                "current": other.id == session_id})
    if not items:
        raise CheckFailed("The Q&A analysis found no questions in this interview.")
    required = list(job.required_skills or [])
    return {"session_id": session_id, "job_title": job.title, "required": required, "covered": list(analysis.covered or []),
            "requirements": list(dict.fromkeys(required + list(job.preferred_skills or []))),
            "items": [{"n": i.position, "question": i.question, "job_related": i.job_related,
                       "words": len(i.answer.split()), "completeness": i.completeness,
                       "requirements": list(i.requirements or []), "time": i.evidence_time} for i in items],
            "turns": [{"speaker": t.speaker, "start": t.start_sec, "end": t.end_sec} for t in turns],
            "interviews": sorted(interviews, key=lambda i: i["date"])}


# ==================== Step 2 of 8: grade_questions ====================
# AI: reviews every job-related interviewer question
def grade_questions(data: dict) -> dict:
    """AI: reviews every job-related interviewer question."""
    questions = [{"n": i["n"], "question": i["question"]} for i in data["items"] if i["job_related"]]
    if not questions:
        return {"graded": {}}
    answer = llm_json(GRADE_QUESTIONS_PROMPT, {"job_title": data["job_title"],           # → AI call
                                               "requirements": data["requirements"], "questions": questions})
    if not isinstance(answer, dict):
        raise CheckFailed(f"The AI did not review the questions ({last_error()}). Please try again.")
    graded = {}
    for item in answer.get("questions") or []:
        if not isinstance(item, dict):
            continue
        n, relevance = _number(item.get("n")), _grade(item.get("relevance"))
        if n is None or relevance is None:
            continue
        graded[n] = {"relevance": relevance, "open": item.get("open") is not False,
                     "reason": str(item.get("reason") or "").strip()[:300],
                     "better": str(item.get("better") or "").strip()[:300]}
    return {"graded": graded}


def _number(value) -> Optional[int]:
    """A whole number from the AI's answer, or None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _grade(value) -> Optional[int]:
    """A grade from the AI as a whole number from 0 to 100, or None when it is not a number."""
    try:
        return int(round(max(0.0, min(100.0, float(value)))))
    except (TypeError, ValueError):
        return None


# ==================== Step 3 of 8: measure_talk_time ====================
# Python: who spoke how long (_talk is also used by load_inputs for the other interviews)
def measure_talk_time(data: dict) -> dict:
    """Who spoke how long, from the transcript times."""
    return {"talk": _talk(data["turns"])}


def _talk(turns: list) -> dict:
    """Seconds per speaker, the interviewer's share and the longest time the interviewer spoke without a break."""
    seconds = {"interviewer": 0.0, "candidate": 0.0}
    longest, stretch_start, last_speaker = 0.0, 0.0, ""
    for turn in turns:
        seconds[turn["speaker"]] = seconds.get(turn["speaker"], 0.0) + max(0.0, turn["end"] - turn["start"])
        if turn["speaker"] != last_speaker:
            stretch_start = turn["start"]                  # a new speaker: a new stretch starts
        if turn["speaker"] == "interviewer":
            longest = max(longest, turn["end"] - stretch_start)
        last_speaker = turn["speaker"]
    total = seconds["interviewer"] + seconds["candidate"]
    share = round(100 * seconds["interviewer"] / total, 1) if total else None
    return {"interviewer_sec": round(seconds["interviewer"], 1), "candidate_sec": round(seconds["candidate"], 1),
            "interviewer_share": share, "longest_interviewer_sec": round(longest, 1),
            "balanced": share is not None and share <= MAX_INTERVIEWER_SHARE}


# ==================== Step 4 of 8: check_coverage ====================
# Python: was each job requirement asked, and did the answer show it?
def check_coverage(data: dict) -> dict:
    """Was each job requirement asked, and did the answer show it?"""
    coverage = []
    for name in data["requirements"]:
        asked = [i["n"] for i in data["items"] if i["job_related"] and name in i["requirements"]]
        coverage.append({"requirement": name, "required": name in data["required"], "questions": asked,
                         "state": "shown" if name in data["covered"] else "no_signal" if asked else "not_asked"})
    return {"coverage": coverage}


# ==================== Step 5 of 8: compare_consistency ====================
# Python: the job's analysed interviews side by side (needs at least two)
def compare_consistency(data: dict) -> dict:
    """The job's analysed interviews side by side (needs at least two)."""
    interviews = data["interviews"]
    if len(interviews) < 2 or not data["requirements"]:
        return {"consistency": {"interviews": interviews, "uneven": [], "score": None}}
    uneven = [name for name in data["requirements"]
              if 0 < sum(name in i["asked"] for i in interviews) < len(interviews)]
    score = round(100 * (len(data["requirements"]) - len(uneven)) / len(data["requirements"]), 1)
    return {"consistency": {"interviews": interviews, "uneven": uneven, "score": score}}


# ==================== Step 6 of 8: find_low_signal ====================
# Python: questions that gave little information, the five scores and the quality score
def find_low_signal(data: dict) -> dict:
    """Questions that gave little information, the five scores and the quality score."""
    questions = []
    for item in data["items"]:
        if not item["job_related"]:
            continue                                   # small talk is not reviewed
        why = []
        if item["completeness"] is not None and item["completeness"] < LOW_COMPLETENESS:
            why.append(f"answer completeness {item['completeness']}")
        if item["words"] < SHORT_ANSWER_WORDS:
            why.append(f"answer of {item['words']} words")
        graded = data["graded"].get(item["n"], {})
        questions.append({"n": item["n"], "question": item["question"], "requirements": item["requirements"],
                          "relevance": graded.get("relevance"), "open": graded.get("open", True),
                          "reason": graded.get("reason", ""), "better": graded.get("better", ""),
                          "signal": "low" if why else "good", "signal_reason": ", ".join(why), "time": item["time"]})

    weight = {c["requirement"]: 2 if c["required"] else 1 for c in data["coverage"]}
    asked = sum(weight[c["requirement"]] for c in data["coverage"] if c["state"] != "not_asked")
    values = {"question_relevance": _average([q["relevance"] for q in questions]),
              "coverage": round(100 * asked / sum(weight.values()), 1) if weight else None,
              "signal": round(100 * sum(q["signal"] == "good" for q in questions) / len(questions), 1) if questions else None,
              "balance": _balance_score(data["talk"]["interviewer_share"]),
              "consistency": data["consistency"]["score"]}
    scores = [{"key": key, "name": name, "score": values[key]} for key, name in SCORE_NAMES]
    return {"questions": questions, "scores": scores, "quality_score": _average(list(values.values()))}


def _average(values: list) -> Optional[float]:
    """The average of the values that are not None, rounded to one decimal (None when there are none)."""
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


# 100 when the interviewer speaks at most 40 %, then 2.5 points less per percent (0 at 80 % or more)
def _balance_score(share: Optional[float]) -> Optional[float]:
    """The speaking balance score: 100 up to 40 % interviewer talk, then 2.5 points less per percent."""
    if share is None:
        return None
    return round(max(0.0, 100 - max(0.0, share - MAX_INTERVIEWER_SHARE) * 2.5), 1)


# ==================== Step 7 of 8: recommend_improvements ====================
# AI: the summary and the improvements, from the measured facts only
def recommend_improvements(data: dict) -> dict:
    """AI: the summary and the improvements, from the measured facts only."""
    facts = {"job_title": data["job_title"],
             "not_asked": [c["requirement"] for c in data["coverage"] if c["state"] == "not_asked"],
             "no_signal": [c["requirement"] for c in data["coverage"] if c["state"] == "no_signal"],
             "low_signal": [{"n": q["n"], "question": q["question"], "why": q["signal_reason"]}
                            for q in data["questions"] if q["signal"] == "low"],
             "low_relevance": [{"n": q["n"], "question": q["question"], "relevance": q["relevance"]}
                               for q in data["questions"] if (q["relevance"] or 0) < LOW_RELEVANCE],
             "talk": {"interviewer_share": data["talk"]["interviewer_share"], "balanced": data["talk"]["balanced"]},
             "uneven": data["consistency"]["uneven"]}
    answer = llm_json(RECOMMEND_PROMPT, facts)                                  # → AI call
    if not isinstance(answer, dict):
        log.info("interview quality session=%s: no AI recommendations (%s), code writes them", data["session_id"],
                 last_error())
        return {"summary": "", "recommendations": []}                         # code writes them in the next step
    items = [{"basis": str(r.get("basis") or "").strip().lower(), "ref": str(r.get("ref") or "").strip(),
              "text": str(r.get("text") or "").strip()[:400], "time": None}
             for r in answer.get("recommendations") or [] if isinstance(r, dict)]
    return {"summary": str(answer.get("summary") or "").strip()[:800], "recommendations": items}


# ==================== Step 8 of 8: check_recommendations ====================
# Python: keeps only improvements based on a measured fact; no judging words
def check_recommendations(data: dict) -> dict:
    """Keeps only improvements based on a measured fact; no judging words."""
    gaps = {c["requirement"] for c in data["coverage"] if c["state"] != "shown"}
    weak = {str(q["n"]): q for q in data["questions"]
            if q["signal"] == "low" or (q["relevance"] or 0) < LOW_RELEVANCE}
    kept = []
    for rec in data["recommendations"]:
        basis, ref = rec["basis"], rec["ref"]
        proven = ((basis == "requirement" and ref in gaps) or (basis == "question" and ref in weak)
                  or (basis == "talk" and not data["talk"]["balanced"] and data["talk"]["interviewer_share"] is not None)
                  or (basis == "consistency" and ref in data["consistency"]["uneven"]))
        if not proven or not rec["text"] or JUDGING.search(rec["text"]):
            continue                                   # no fact behind it, or it judges a person: removed
        kept.append({**rec, "ref": ref if basis != "talk" else "",
                     "time": weak[ref]["time"] if basis == "question" else None})
    kept = kept[:MAX_RECOMMENDATIONS] or _code_recommendations(data)
    summary = data["summary"] if data["summary"] and not JUDGING.search(data["summary"]) else (
        f"Interview quality {data['quality_score']}: the average of question relevance, competency coverage, "
        f"answer signal, speaking balance and consistency.")
    return {"recommendations": kept, "summary": summary}


def _code_recommendations(data: dict) -> list:
    """Improvements written by code from the measured facts (used when the AI gave none that could be checked)."""
    out = []
    for c in data["coverage"]:
        if c["state"] == "not_asked":
            out.append({"basis": "requirement", "ref": c["requirement"], "time": None,
                        "text": f"Add a question about {c['requirement']}: no question in this interview covered it."})
        elif c["state"] == "no_signal":
            out.append({"basis": "requirement", "ref": c["requirement"], "time": None,
                        "text": f"Ask a follow-up about {c['requirement']}: it was asked, but the answer showed little."})
    for q in data["questions"]:
        if q["signal"] == "low":
            better = f' For example: "{q["better"]}"' if q["better"] else ""
            out.append({"basis": "question", "ref": str(q["n"]), "time": q["time"],
                        "text": f"Question {q['n']} gave little information ({q['signal_reason']}). "
                                f"Ask it as an open question.{better}"})
    talk = data["talk"]
    if talk["interviewer_share"] is not None and not talk["balanced"]:
        out.append({"basis": "talk", "ref": "", "time": None,
                    "text": f"The interviewer spoke {talk['interviewer_share']} % of the time. Ask shorter questions "
                            f"and give the candidate more time to answer (aim for {MAX_INTERVIEWER_SHARE} % or less)."})
    for name in data["consistency"].get("uneven", []):
        out.append({"basis": "consistency", "ref": name, "time": None,
                    "text": f"Ask about {name} in every interview for this job, so the candidates can be compared fairly."})
    return out[:MAX_RECOMMENDATIONS]
