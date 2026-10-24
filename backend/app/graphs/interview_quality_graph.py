"""The interview quality workflow (F10): the quality of the interview process itself, not of the candidate.

    START -> load_inputs
          -> [grade_questions | measure_talk_time | check_coverage | compare_consistency]   (parallel)
          -> find_low_signal -> recommend_improvements -> check_recommendations -> save -> END
    any error -> failed -> END

    load_inputs             Python + DB  the job, the finished Q&A analysis of this interview, the transcript, and the
                                         other analysed interviews of the same job (for consistency)
    grade_questions         AI           each interviewer question: relevance to the job (0-100), open or closed,
                                         a reason and a clearer wording when needed
    measure_talk_time       Python       speaking time per speaker from the transcript times; balanced when the
                                         interviewer speaks at most 40 % of the time
    check_coverage          Python       each job requirement: shown | no_signal (asked, nothing shown) | not_asked
    compare_consistency     Python       the same job's interviews side by side; requirements asked in some, not all
    find_low_signal         Python       questions whose answers gave little information; the five scores and the
                                         quality score (their average)
    recommend_improvements  AI           a short summary and 3-5 improvements, each based on one measured fact
    check_recommendations   Python       keeps only improvements whose fact really exists; removes judging words;
                                         if none is left, code writes them from the facts
    save / failed           Python + DB  the result (or the reason) and one workflow_run row

Only the words and the times are used: never voice, tone or appearance. It never changes a candidate's score or a
decision, and the candidate never sees it. About 2 AI calls per interview.
"""
import logging
import re
import time
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, select

from app.ai.llm_client import last_error, llm_json
from app.core.database import engine
from app.features.candidates.models import Candidate
from app.features.interview_quality.models import InterviewQuality
from app.features.interviews.models import InterviewSession
from app.features.jobs.models import Job
from app.features.qa_analysis.models import QaAnalysis, QaItem
from app.features.system.models import WorkflowRun
from app.features.transcripts.models import TranscriptTurn
from app.graphs.interview_quality_prompts import GRADE_QUESTIONS_PROMPT, RECOMMEND_PROMPT

log = logging.getLogger("interview_quality_graph")

PARALLEL_STEPS = ["grade_questions", "measure_talk_time", "check_coverage", "compare_consistency"]
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


class QualityState(TypedDict):
    session_id: int
    job_title: str
    requirements: list          # required + preferred skills of the job
    required: list              # required skills only (they count twice in the coverage score)
    covered: list               # requirements the answers showed (from the Q&A analysis)
    items: list                 # the questions: [{"n", "question", "job_related", "words", "completeness", "requirements", "time"}]
    turns: list                 # the transcript: [{"speaker", "start", "end"}]
    interviews: list            # the analysed interviews of this job (this one included), for consistency
    # each parallel step writes only its own key, so the four can run at the same time
    graded: Optional[dict]      # {n: {"relevance", "open", "reason", "better"}}; None = the AI failed
    talk: dict
    coverage: list
    consistency: dict
    questions: list             # the reviewed questions shown on the page
    scores: list                # [{"key", "name", "score"}]
    quality_score: Optional[float]
    summary: str
    recommendations: list       # [{"basis", "ref", "text", "time"}]
    error: str
    started: float


# ---------- helpers ----------

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


def _average(values: list) -> Optional[float]:
    """The average of the values that are not None, rounded to one decimal (None when there are none)."""
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


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


# 100 when the interviewer speaks at most 40 %, then 2.5 points less per percent (0 at 80 % or more)
def _balance_score(share: Optional[float]) -> Optional[float]:
    """The speaking balance score: 100 up to 40 % interviewer talk, then 2.5 points less per percent."""
    if share is None:
        return None
    return round(max(0.0, 100 - max(0.0, share - MAX_INTERVIEWER_SHARE) * 2.5), 1)


def _code_recommendations(state: QualityState) -> list:
    """Improvements written by code from the measured facts (used when the AI gave none that could be checked)."""
    out = []
    for c in state["coverage"]:
        if c["state"] == "not_asked":
            out.append({"basis": "requirement", "ref": c["requirement"], "time": None,
                        "text": f"Add a question about {c['requirement']}: no question in this interview covered it."})
        elif c["state"] == "no_signal":
            out.append({"basis": "requirement", "ref": c["requirement"], "time": None,
                        "text": f"Ask a follow-up about {c['requirement']}: it was asked, but the answer showed little."})
    for q in state["questions"]:
        if q["signal"] == "low":
            better = f' For example: "{q["better"]}"' if q["better"] else ""
            out.append({"basis": "question", "ref": str(q["n"]), "time": q["time"],
                        "text": f"Question {q['n']} gave little information ({q['signal_reason']}). "
                                f"Ask it as an open question.{better}"})
    talk = state["talk"]
    if talk["interviewer_share"] is not None and not talk["balanced"]:
        out.append({"basis": "talk", "ref": "", "time": None,
                    "text": f"The interviewer spoke {talk['interviewer_share']} % of the time. Ask shorter questions "
                            f"and give the candidate more time to answer (aim for {MAX_INTERVIEWER_SHARE} % or less)."})
    for name in state["consistency"].get("uneven", []):
        out.append({"basis": "consistency", "ref": name, "time": None,
                    "text": f"Ask about {name} in every interview for this job, so the candidates can be compared fairly."})
    return out[:MAX_RECOMMENDATIONS]


# ---------- nodes ----------

# Workflow step "load_inputs": the job, the finished Q&A analysis, the transcript and the job's other interviews
def load_inputs(state: QualityState) -> dict:
    """Workflow step: the job, the finished Q&A analysis, the transcript and the job's other interviews."""
    with Session(engine) as session:
        interview = session.get(InterviewSession, state["session_id"])
        job = session.get(Job, interview.job_id) if interview else None
        analysis = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == state["session_id"])).first()
        if not job or not analysis or analysis.status != "done":
            return {"error": "Analyse the answers first. The interview quality uses the Q&A analysis."}
        items = session.exec(select(QaItem).where(QaItem.session_id == state["session_id"])
                             .order_by(QaItem.position)).all()
        turns = session.exec(select(TranscriptTurn).where(TranscriptTurn.session_id == state["session_id"])
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
                "current": other.id == state["session_id"]})
    if not items:
        return {"error": "The Q&A analysis found no questions in this interview."}
    required = list(job.required_skills or [])
    return {"job_title": job.title, "required": required, "covered": list(analysis.covered or []),
            "requirements": list(dict.fromkeys(required + list(job.preferred_skills or []))),
            "items": [{"n": i.position, "question": i.question, "job_related": i.job_related,
                       "words": len(i.answer.split()), "completeness": i.completeness,
                       "requirements": list(i.requirements or []), "time": i.evidence_time} for i in items],
            "turns": [{"speaker": t.speaker, "start": t.start_sec, "end": t.end_sec} for t in turns],
            "interviews": sorted(interviews, key=lambda i: i["date"])}


# Workflow step "grade_questions": the AI reviews every job-related interviewer question
def grade_questions(state: QualityState) -> dict:
    """Workflow step (AI): reviews every job-related interviewer question."""
    questions = [{"n": i["n"], "question": i["question"]} for i in state["items"] if i["job_related"]]
    if not questions:
        return {"graded": {}}
    answer = llm_json(GRADE_QUESTIONS_PROMPT, {"job_title": state["job_title"],           # → AI call
                                               "requirements": state["requirements"], "questions": questions})
    if not isinstance(answer, dict):
        return {"graded": None}
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


# Workflow step "measure_talk_time": who spoke how long (from the transcript times)
def measure_talk_time(state: QualityState) -> dict:
    """Workflow step: who spoke how long, from the transcript times."""
    return {"talk": _talk(state["turns"])}


# Workflow step "check_coverage": was each job requirement asked, and did the answer show it?
def check_coverage(state: QualityState) -> dict:
    """Workflow step: was each job requirement asked, and did the answer show it?"""
    coverage = []
    for name in state["requirements"]:
        asked = [i["n"] for i in state["items"] if i["job_related"] and name in i["requirements"]]
        coverage.append({"requirement": name, "required": name in state["required"], "questions": asked,
                         "state": "shown" if name in state["covered"] else "no_signal" if asked else "not_asked"})
    return {"coverage": coverage}


# Workflow step "compare_consistency": the job's interviews side by side (needs at least two)
def compare_consistency(state: QualityState) -> dict:
    """Workflow step: the job's analysed interviews side by side (needs at least two)."""
    interviews = state["interviews"]
    if len(interviews) < 2 or not state["requirements"]:
        return {"consistency": {"interviews": interviews, "uneven": [], "score": None}}
    uneven = [name for name in state["requirements"]
              if 0 < sum(name in i["asked"] for i in interviews) < len(interviews)]
    score = round(100 * (len(state["requirements"]) - len(uneven)) / len(state["requirements"]), 1)
    return {"consistency": {"interviews": interviews, "uneven": uneven, "score": score}}


# Workflow step "find_low_signal": questions that gave little information, and the five scores
def find_low_signal(state: QualityState) -> dict:
    """Workflow step: questions that gave little information, the five scores and the quality score."""
    if state["graded"] is None:
        return {"error": f"The AI did not review the questions ({last_error()}). Please try again."}
    questions = []
    for item in state["items"]:
        if not item["job_related"]:
            continue                                   # small talk is not reviewed
        why = []
        if item["completeness"] is not None and item["completeness"] < LOW_COMPLETENESS:
            why.append(f"answer completeness {item['completeness']}")
        if item["words"] < SHORT_ANSWER_WORDS:
            why.append(f"answer of {item['words']} words")
        graded = state["graded"].get(item["n"], {})
        questions.append({"n": item["n"], "question": item["question"], "requirements": item["requirements"],
                          "relevance": graded.get("relevance"), "open": graded.get("open", True),
                          "reason": graded.get("reason", ""), "better": graded.get("better", ""),
                          "signal": "low" if why else "good", "signal_reason": ", ".join(why), "time": item["time"]})

    weight = {c["requirement"]: 2 if c["required"] else 1 for c in state["coverage"]}
    asked = sum(weight[c["requirement"]] for c in state["coverage"] if c["state"] != "not_asked")
    values = {"question_relevance": _average([q["relevance"] for q in questions]),
              "coverage": round(100 * asked / sum(weight.values()), 1) if weight else None,
              "signal": round(100 * sum(q["signal"] == "good" for q in questions) / len(questions), 1) if questions else None,
              "balance": _balance_score(state["talk"]["interviewer_share"]),
              "consistency": state["consistency"]["score"]}
    scores = [{"key": key, "name": name, "score": values[key]} for key, name in SCORE_NAMES]
    return {"questions": questions, "scores": scores, "quality_score": _average(list(values.values()))}


# Workflow step "recommend_improvements": the AI writes the summary and the improvements from the measured facts
def recommend_improvements(state: QualityState) -> dict:
    """Workflow step (AI): the summary and the improvements, from the measured facts only."""
    facts = {"job_title": state["job_title"],
             "not_asked": [c["requirement"] for c in state["coverage"] if c["state"] == "not_asked"],
             "no_signal": [c["requirement"] for c in state["coverage"] if c["state"] == "no_signal"],
             "low_signal": [{"n": q["n"], "question": q["question"], "why": q["signal_reason"]}
                            for q in state["questions"] if q["signal"] == "low"],
             "low_relevance": [{"n": q["n"], "question": q["question"], "relevance": q["relevance"]}
                               for q in state["questions"] if (q["relevance"] or 0) < LOW_RELEVANCE],
             "talk": {"interviewer_share": state["talk"]["interviewer_share"], "balanced": state["talk"]["balanced"]},
             "uneven": state["consistency"]["uneven"]}
    answer = llm_json(RECOMMEND_PROMPT, facts)                                  # → AI call
    if not isinstance(answer, dict):
        log.info("interview quality session=%s: no AI recommendations (%s), code writes them", state["session_id"],
                 last_error())
        return {"summary": "", "recommendations": []}                         # code writes them in the next step
    items = [{"basis": str(r.get("basis") or "").strip().lower(), "ref": str(r.get("ref") or "").strip(),
              "text": str(r.get("text") or "").strip()[:400], "time": None}
             for r in answer.get("recommendations") or [] if isinstance(r, dict)]
    return {"summary": str(answer.get("summary") or "").strip()[:800], "recommendations": items}


# Workflow step "check_recommendations": every improvement must rest on a measured fact; no judging words
def check_recommendations(state: QualityState) -> dict:
    """Workflow step: keeps only improvements based on a measured fact; no judging words."""
    gaps = {c["requirement"] for c in state["coverage"] if c["state"] != "shown"}
    weak = {str(q["n"]): q for q in state["questions"]
            if q["signal"] == "low" or (q["relevance"] or 0) < LOW_RELEVANCE}
    kept = []
    for rec in state["recommendations"]:
        basis, ref = rec["basis"], rec["ref"]
        proven = ((basis == "requirement" and ref in gaps) or (basis == "question" and ref in weak)
                  or (basis == "talk" and not state["talk"]["balanced"] and state["talk"]["interviewer_share"] is not None)
                  or (basis == "consistency" and ref in state["consistency"]["uneven"]))
        if not proven or not rec["text"] or JUDGING.search(rec["text"]):
            continue                                   # no fact behind it, or it judges a person: removed
        kept.append({**rec, "ref": ref if basis != "talk" else "",
                     "time": weak[ref]["time"] if basis == "question" else None})
    kept = kept[:MAX_RECOMMENDATIONS] or _code_recommendations(state)
    summary = state["summary"] if state["summary"] and not JUDGING.search(state["summary"]) else (
        f"Interview quality {state['quality_score']}: the average of question relevance, competency coverage, "
        f"answer signal, speaking balance and consistency.")
    return {"recommendations": kept, "summary": summary}


# Workflow step "save": the result replaces the old one
def save(state: QualityState) -> dict:
    """Workflow step: saves the result (it replaces the old one) and one workflow_run row."""
    with Session(engine) as session:
        row = session.exec(select(InterviewQuality).where(InterviewQuality.session_id == state["session_id"])).one()
        row.status, row.error, row.quality_score = "done", "", state["quality_score"]
        row.scores, row.talk, row.coverage = state["scores"], state["talk"], state["coverage"]
        row.questions, row.consistency = state["questions"], state["consistency"]
        row.summary, row.recommendations = state["summary"], state["recommendations"]
        session.add(row)
        session.add(WorkflowRun(stage="interview_quality", subject_id=state["session_id"], outcome="done",
                                seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("interview quality session=%s done score=%s", state["session_id"], state["quality_score"])
    return {}


# Workflow step "failed": marked failed with the reason, so the page can show it
def failed(state: QualityState) -> dict:
    """Workflow step: marks the check failed with the reason, so the page can show it."""
    with Session(engine) as session:
        row = session.exec(select(InterviewQuality).where(InterviewQuality.session_id == state["session_id"])).first()
        if row:
            row.status, row.error = "failed", state["error"]
            session.add(row)
        session.add(WorkflowRun(stage="interview_quality", subject_id=state["session_id"], outcome="failed",
                                error=state["error"], seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("interview quality session=%s failed: %s", state["session_id"], state["error"])
    return {}


# After loading: the four parallel steps, or "failed"
def after_load(state: QualityState):
    """After loading: the four parallel steps, or "failed"."""
    return "failed" if state["error"] else PARALLEL_STEPS


def go_on(state: QualityState) -> str:
    """After a step: go on, or to "failed" when the step set an error."""
    return "failed" if state["error"] else "go"


graph = StateGraph(QualityState)
graph.add_node("load_inputs", load_inputs)
graph.add_node("grade_questions", grade_questions)
graph.add_node("measure_talk_time", measure_talk_time)
graph.add_node("check_coverage", check_coverage)
graph.add_node("compare_consistency", compare_consistency)
graph.add_node("find_low_signal", find_low_signal)
graph.add_node("recommend_improvements", recommend_improvements)
graph.add_node("check_recommendations", check_recommendations)
graph.add_node("save", save)
graph.add_node("failed", failed)

graph.add_edge(START, "load_inputs")
graph.add_conditional_edges("load_inputs", after_load, PARALLEL_STEPS + ["failed"])
graph.add_edge(PARALLEL_STEPS, "find_low_signal")           # waits until all four have finished
graph.add_conditional_edges("find_low_signal", go_on, {"go": "recommend_improvements", "failed": "failed"})
graph.add_edge("recommend_improvements", "check_recommendations")
graph.add_edge("check_recommendations", "save")
graph.add_edge("save", END)
graph.add_edge("failed", END)

interview_quality_graph = graph.compile()


def assess_interview(session_id: int) -> QualityState:
    """Runs the workflow for one interview. The interview_quality row must exist (status running). Never raises."""
    state: QualityState = {"session_id": session_id, "job_title": "", "requirements": [], "required": [], "covered": [],
                           "items": [], "turns": [], "interviews": [], "graded": {}, "talk": {}, "coverage": [],
                           "consistency": {}, "questions": [], "scores": [], "quality_score": None, "summary": "",
                           "recommendations": [], "error": "", "started": time.time()}
    try:
        return interview_quality_graph.invoke(state)
    except Exception:
        log.exception("interview quality workflow could not run")
        stopped = {**state, "error": "The interview quality check stopped unexpectedly. Please try again."}
        failed(stopped)
        return stopped
