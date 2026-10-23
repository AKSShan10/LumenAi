"""The Q&A analysis workflow (F5): after the interview, the transcript becomes graded questions and answers.

    START -> load_transcript -> segment_qa_pairs -> classify_requirements
          -> [evaluate_relevance | evaluate_accuracy (+RAG) | evaluate_completeness | evaluate_articulation
              | evaluate_problem_solving | evaluate_depth]                                              (parallel)
          -> merge_evaluation -> detect_requirement_gaps -> build_scorecard -> save -> END
    any error -> failed -> END

    load_transcript          Python + database: the job and every transcript sentence, numbered
    segment_qa_pairs         AI: finds each question and its answer, marks small talk, splits multi-part questions
    classify_requirements    AI: links each pair to the job requirements it is about
    evaluate_*               AI, six calls at the same time: one grade per answer (0 to 100) with a reason
                             and a quote. Accuracy also gets the 3 most similar company documents (RAG);
                             completeness also suggests a follow-up question for what the answer missed.
    merge_evaluation         Python: checks each quote is really in the answer and adds its time; the answer score
                             is the average of its grades
    detect_requirement_gaps  Python: which job requirements the answers showed (covered) and which not (uncovered)
    build_scorecard          Python: the interview scorecard (F9): six dimensions with a score, a reason and the best
                             checked quote; alignment with the job requirements is counted by code; the interview score
                             is the average of the six dimensions
    save / failed            Python + database: the result (or the reason it failed) and one workflow_run row

The AI suggests, code checks. Only the transcript text is used: never voice, appearance or confidence.
The answer text is always the candidate's own words from the transcript (code copies it), never the AI's.
About 8 AI calls per interview, however long it was.
"""
import logging
import re
import time
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, delete, select

from app.ai.llm_client import last_error, llm_json
from app.core.database import engine
from app.features.interviews.models import InterviewSession
from app.features.job_library.services.company_document_service import (
    MIN_EXAMPLE_SIMILARITY, TOP_POLICIES, find_documents)
from app.features.jobs.models import Job
from app.features.qa_analysis.models import QaAnalysis, QaItem
from app.features.system.models import WorkflowRun
from app.features.transcripts.models import TranscriptTurn
from app.graphs.qa_analysis_prompts import CRITERIA, GRADE_PROMPTS, REQUIREMENTS_PROMPT, SEGMENT_PROMPT

log = logging.getLogger("qa_analysis_graph")

MAX_PAIRS = 40                   # the most questions and answers one analysis keeps
SHOWN_SCORE = 50                 # an answer with at least this score shows its requirements (covered)
EVALUATE_STEPS = ["evaluate_relevance", "evaluate_accuracy", "evaluate_completeness", "evaluate_articulation",
                  "evaluate_problem_solving", "evaluate_depth"]
# The interview scorecard (F9): (key, name shown, the grader it comes from; None = counted by code)
DIMENSIONS = [("technical", "Technical competency", "accuracy"),
              ("communication", "Communication", "articulation"),
              ("relevance", "Relevance of responses", "relevance"),
              ("problem_solving", "Problem-solving approach", "problem_solving"),
              ("depth", "Depth of experience demonstrated", "depth"),
              ("alignment", "Alignment with job requirements", None)]


class QaState(TypedDict):
    session_id: int
    job_title: str
    requirements: list       # the job's required and preferred skills
    required: list           # only the required ones (they count twice in the alignment score)
    lines: list              # the transcript: [{"n", "speaker", "start", "text"}]
    pairs: list              # [{"question", "answer", "answer_lines", "job_related", "split", "requirements"}]
    # The four graders' answers by pair number: {n: {"grade", "reason", "quote", "sources"}}; None = the AI failed.
    # Each grader writes only its own key, so the four can run at the same time.
    relevance: Optional[dict]
    accuracy: Optional[dict]
    completeness: Optional[dict]
    articulation: Optional[dict]
    problem_solving: Optional[dict]
    depth: Optional[dict]
    evidence: dict           # per grader: [{"n", "grade", "reason", "quote", "time"}] (quotes checked), for the scorecard
    scorecard: list          # the six F9 dimensions: [{"key", "name", "score", "reason", "quote", "time"}]
    notes: list              # titles of the company documents the accuracy grader got (RAG)
    items: list              # the finished rows for qa_item
    interview_score: Optional[float]
    covered: list
    uncovered: list
    error: str               # set when a step failed: the workflow goes to "failed"
    started: float


# ---------- helpers ----------

# Turns a value from the AI into a whole number, or None (the AI may send "3", 3.0 or rubbish)
def _number(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# A grade from the AI as a whole number from 0 to 100: 60 stays 60, 120 becomes 100 (None if it is not a number)
def _grade(value) -> Optional[int]:
    try:
        grade = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None
    return int(round(grade))


# Lower case, letters and digits only, so "Docker, mostly!" matches "docker mostly"
def _plain(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip() + " "


# When the quote was said (seconds from the start), or None if the quote is not in the candidate's answer
def _quote_time(quote: str, pair: dict, lines: list) -> Optional[float]:
    wanted = _plain(quote)
    if len(wanted.split()) < 2:                       # one word proves nothing
        return None
    answer_lines = [line for line in lines if line["n"] in pair["answer_lines"]]
    for line in answer_lines:
        if wanted in _plain(line["text"]):
            return line["start"]
    if wanted in _plain(pair["answer"]):              # the quote runs over two sentences
        return answer_lines[0]["start"]
    return None


# The job-related pairs as the graders see them: number, question and answer
def _for_graders(pairs: list) -> list[dict]:
    return [{"n": n, "question": p["question"], "answer": p["answer"]}
            for n, p in enumerate(pairs, 1) if p["job_related"]]


# One grader: asks the AI to grade every job-related answer on one criterion, then cleans its answer
def _evaluate(state: QaState, criterion: str, notes: list | None = None) -> Optional[dict]:
    pairs = _for_graders(state["pairs"])
    if not pairs:
        return {}                                      # only small talk: nothing to grade
    facts = {"job_title": state["job_title"], "pairs": pairs}
    if notes is not None:
        facts["company_notes"] = notes
    answer = llm_json(GRADE_PROMPTS[criterion], facts)  # → one AI call for all answers
    if not isinstance(answer, dict):
        return None
    grades = {}
    for item in answer.get("grades") or []:
        if not isinstance(item, dict):
            continue
        n, grade = _number(item.get("n")), _grade(item.get("grade"))
        if n is None or grade is None:
            continue                                   # skip anything without a pair number and a grade
        sources = item.get("sources") if isinstance(item.get("sources"), list) else []
        grades[n] = {"grade": grade, "reason": str(item.get("reason") or "").strip()[:300],
                     "quote": str(item.get("quote") or "").strip()[:300], "sources": [str(s) for s in sources],
                     "follow_up": str(item.get("follow_up") or "").strip()[:300]}   # only completeness gives it
    return grades


# ---------- nodes ----------

# Workflow step "load_transcript": the job and every transcript sentence of this interview, oldest first
def load_transcript(state: QaState) -> dict:
    with Session(engine) as session:
        interview = session.get(InterviewSession, state["session_id"])
        job = session.get(Job, interview.job_id) if interview else None
        turns = session.exec(select(TranscriptTurn).where(TranscriptTurn.session_id == state["session_id"])
                             .order_by(TranscriptTurn.start_sec, TranscriptTurn.id)).all()
    if not job:
        return {"error": "The interview or its job was not found."}
    if not any(t.speaker == "candidate" for t in turns):
        return {"error": "Nothing the candidate said was transcribed, so there is nothing to analyse."}
    lines = [{"n": n, "speaker": t.speaker, "start": t.start_sec, "text": t.text} for n, t in enumerate(turns, 1)]
    requirements = list(dict.fromkeys((job.required_skills or []) + (job.preferred_skills or [])))
    return {"job_title": job.title, "requirements": requirements, "required": list(job.required_skills or []),
            "lines": lines}


# Workflow step "segment_qa_pairs": the AI finds the questions and answers; code copies the answer words
def segment_qa_pairs(state: QaState) -> dict:
    shown = [{"n": line["n"], "speaker": line["speaker"].capitalize(), "text": line["text"]} for line in state["lines"]]
    answer = llm_json(SEGMENT_PROMPT, {"lines": shown})              # → AI call
    if not isinstance(answer, dict):
        return {"error": f"The AI did not answer ({last_error()}). Please try again."}

    by_number = {line["n"]: line for line in state["lines"]}
    pairs = []
    for item in answer.get("pairs") or []:
        if not isinstance(item, dict):
            continue
        # only real line numbers said by the candidate count as the answer
        numbers = sorted({n for n in map(_number, item.get("answer_lines") or [])
                          if n in by_number and by_number[n]["speaker"] == "candidate"})
        question = str(item.get("question") or "").strip()
        if not question or not numbers:
            continue                                   # no question text or no answer: left out
        pairs.append({"question": question[:500],
                      "answer": " ".join(by_number[n]["text"] for n in numbers)[:4000],   # the candidate's own words
                      "answer_lines": numbers,
                      "job_related": item.get("job_related") is not False,    # small talk only when the AI says so
                      "split": item.get("split") is True,
                      "requirements": []})
    if not pairs:
        return {"error": "No question and answer was found in the transcript."}
    return {"pairs": pairs[:MAX_PAIRS]}


# Workflow step "classify_requirements": the AI links each job-related pair to the job requirements it is about
def classify_requirements(state: QaState) -> dict:
    pairs = _for_graders(state["pairs"])
    if not pairs or not state["requirements"]:
        return {}                                      # nothing to link
    answer = llm_json(REQUIREMENTS_PROMPT, {"requirements": state["requirements"], "pairs": pairs})   # → AI call
    if not isinstance(answer, dict):
        return {"error": f"The AI did not answer ({last_error()}). Please try again."}

    known = {r.lower(): r for r in state["requirements"]}      # only the job's own requirement names are kept
    linked = {}
    for item in answer.get("pairs") or []:
        if isinstance(item, dict) and isinstance(item.get("requirements"), list):
            names = [known[str(r).strip().lower()] for r in item["requirements"] if str(r).strip().lower() in known]
            linked[_number(item.get("n"))] = list(dict.fromkeys(names))
    return {"pairs": [{**p, "requirements": linked.get(n, [])} for n, p in enumerate(state["pairs"], 1)]}


# Workflow steps "evaluate_*": the four graders, run at the same time
def evaluate_relevance(state: QaState) -> dict:
    return {"relevance": _evaluate(state, "relevance")}


def evaluate_accuracy(state: QaState) -> dict:
    # RAG: the company documents most similar to the job and the questions, only if similar enough
    search = state["job_title"] + " " + " ".join(p["question"] for p in state["pairs"] if p["job_related"])
    with Session(engine) as session:
        found = find_documents(session, search, "policy", TOP_POLICIES, MIN_EXAMPLE_SIMILARITY)
    notes = [{"title": d["title"], "text": d["text"]} for d in found]
    return {"accuracy": _evaluate(state, "accuracy", notes), "notes": [n["title"] for n in notes]}


def evaluate_completeness(state: QaState) -> dict:
    return {"completeness": _evaluate(state, "completeness")}


def evaluate_articulation(state: QaState) -> dict:
    return {"articulation": _evaluate(state, "articulation")}


def evaluate_problem_solving(state: QaState) -> dict:
    return {"problem_solving": _evaluate(state, "problem_solving")}


def evaluate_depth(state: QaState) -> dict:
    return {"depth": _evaluate(state, "depth")}


# Workflow step "merge_evaluation": puts the grades together; checks quotes; works out the answer scores
def merge_evaluation(state: QaState) -> dict:
    if any(state[criterion] is None for criterion in CRITERIA):
        return {"error": f"The AI did not grade the answers ({last_error()}). Please try again."}
    items, evidence = [], {criterion: [] for criterion in CRITERIA}
    for n, pair in enumerate(state["pairs"], 1):
        item = {"position": n, "question": pair["question"], "answer": pair["answer"],
                "job_related": pair["job_related"], "split_from_multi_part": pair["split"],
                "requirements": pair["requirements"], "reasons": {}, "references": [],
                "evidence_quote": "", "evidence_time": None, "score": None}
        grades = []
        for criterion in CRITERIA:
            graded = state[criterion].get(n) if pair["job_related"] else None
            item[criterion] = graded["grade"] if graded else None
            if not graded:
                continue
            grades.append(graded["grade"])
            item["reasons"][criterion] = graded["reason"]
            said_at = _quote_time(graded["quote"], pair, state["lines"])
            evidence[criterion].append({"n": n, "grade": graded["grade"], "reason": graded["reason"],
                                        "quote": graded["quote"] if said_at is not None else "", "time": said_at})
            if not item["evidence_quote"] and said_at is not None:     # the first quote that is really in the answer
                item["evidence_quote"], item["evidence_time"] = graded["quote"], said_at
        if grades:
            item["score"] = round(sum(grades) / len(grades), 1)        # the answer score: average of its grades
        # a follow-up question that fills what the answer missed (from the completeness grader)
        item["follow_up"] = (state["completeness"].get(n) or {}).get("follow_up", "") if pair["job_related"] else ""
        used = (state["accuracy"].get(n) or {}).get("sources", [])
        item["references"] = [title for title in state["notes"] if title in used]   # only documents it really got
        items.append(item)
    return {"items": items, "evidence": evidence}


# Workflow step "detect_requirement_gaps": a requirement is covered when an answer about it scored 50 or more
def detect_requirement_gaps(state: QaState) -> dict:
    shown = {r for item in state["items"] if (item["score"] or 0) >= SHOWN_SCORE for r in item["requirements"]}
    return {"covered": [r for r in state["requirements"] if r in shown],
            "uncovered": [r for r in state["requirements"] if r not in shown]}


# Workflow step "build_scorecard" (code only): the six F9 dimensions and the interview score
def build_scorecard(state: QaState) -> dict:
    card = []
    for key, name, criterion in DIMENSIONS:
        if criterion:                                   # the average of that grade over the job-related answers
            graded = state["evidence"].get(criterion) or []
            if not graded:
                card.append({"key": key, "name": name, "score": None, "reason": "No job-related answer to grade.",
                             "quote": "", "time": None})
                continue
            best = max(graded, key=lambda g: (bool(g["quote"]), g["grade"]))     # strongest answer with a quote
            card.append({"key": key, "name": name, "score": round(sum(g["grade"] for g in graded) / len(graded), 1),
                         "reason": best["reason"], "quote": best["quote"], "time": best["time"]})
            continue
        # alignment with the job requirements: the share shown in the answers; required skills count twice
        weight = {r: (2 if r in state["required"] else 1) for r in state["requirements"]}
        total = sum(weight.values())
        shown = sum(weight[r] for r in state["covered"])
        linked = [i for i in state["items"] if i["evidence_quote"] and set(i["requirements"]) & set(state["covered"])]
        best = max(linked, key=lambda i: i["score"] or 0) if linked else None
        card.append({"key": key, "name": name, "score": round(100 * shown / total, 1) if total else None,
                     "reason": f"{len(state['covered'])} of {len(state['requirements'])} job requirements were shown "
                               "in the answers (required skills count twice)." if total else "The job has no requirements.",
                     "quote": best["evidence_quote"] if best else "", "time": best["evidence_time"] if best else None})
    scores = [d["score"] for d in card if d["score"] is not None]
    return {"scorecard": card, "interview_score": round(sum(scores) / len(scores), 1) if scores else None}


# Workflow step "save": the new questions and answers replace the old ones; the analysis is marked done
def save(state: QaState) -> dict:
    with Session(engine) as session:
        session.exec(delete(QaItem).where(QaItem.session_id == state["session_id"]))
        for item in state["items"]:
            session.add(QaItem(session_id=state["session_id"], **item))
        row = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == state["session_id"])).one()
        row.status, row.error, row.interview_score = "done", "", state["interview_score"]
        row.covered, row.uncovered, row.scorecard = state["covered"], state["uncovered"], state["scorecard"]
        session.add(row)
        session.add(WorkflowRun(stage="interview_analysis", subject_id=state["session_id"], outcome="done",
                                seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("qa analysis session=%s done pairs=%s score=%s", state["session_id"], len(state["items"]),
             state["interview_score"])
    return {}


# Workflow step "failed": the analysis is marked failed with the reason, so the page can show it
def failed(state: QaState) -> dict:
    with Session(engine) as session:
        row = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == state["session_id"])).first()
        if row:
            row.status, row.error = "failed", state["error"]
            session.add(row)
        session.add(WorkflowRun(stage="interview_analysis", subject_id=state["session_id"], outcome="failed",
                                error=state["error"], seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("qa analysis session=%s failed: %s", state["session_id"], state["error"])
    return {}


# ---------- routing ----------

# After a step: go on, or to "failed" when the step set an error
def go_on(state: QaState) -> str:
    return "failed" if state["error"] else "go"


# After classify_requirements: the six graders at the same time, or "failed"
def after_classify(state: QaState):
    return "failed" if state["error"] else EVALUATE_STEPS


# ---------- wiring ----------

graph = StateGraph(QaState)
graph.add_node("load_transcript", load_transcript)
graph.add_node("segment_qa_pairs", segment_qa_pairs)
graph.add_node("classify_requirements", classify_requirements)
graph.add_node("evaluate_relevance", evaluate_relevance)
graph.add_node("evaluate_accuracy", evaluate_accuracy)
graph.add_node("evaluate_completeness", evaluate_completeness)
graph.add_node("evaluate_articulation", evaluate_articulation)
graph.add_node("evaluate_problem_solving", evaluate_problem_solving)
graph.add_node("evaluate_depth", evaluate_depth)
graph.add_node("merge_evaluation", merge_evaluation)
graph.add_node("detect_requirement_gaps", detect_requirement_gaps)
graph.add_node("build_scorecard", build_scorecard)
graph.add_node("save", save)
graph.add_node("failed", failed)

graph.add_edge(START, "load_transcript")
graph.add_conditional_edges("load_transcript", go_on, {"go": "segment_qa_pairs", "failed": "failed"})
graph.add_conditional_edges("segment_qa_pairs", go_on, {"go": "classify_requirements", "failed": "failed"})
graph.add_conditional_edges("classify_requirements", after_classify, EVALUATE_STEPS + ["failed"])
graph.add_edge(EVALUATE_STEPS, "merge_evaluation")      # waits until all six graders have finished
graph.add_conditional_edges("merge_evaluation", go_on, {"go": "detect_requirement_gaps", "failed": "failed"})
graph.add_edge("detect_requirement_gaps", "build_scorecard")
graph.add_edge("build_scorecard", "save")
graph.add_edge("save", END)
graph.add_edge("failed", END)

qa_analysis_graph = graph.compile()


def analyse_interview(session_id: int) -> QaState:
    """Runs the workflow for one interview. The qa_analysis row must exist (status running). Never raises."""
    state: QaState = {"session_id": session_id, "job_title": "", "requirements": [], "required": [], "lines": [],
                      "pairs": [], "relevance": {}, "accuracy": {}, "completeness": {}, "articulation": {},
                      "problem_solving": {}, "depth": {}, "evidence": {}, "scorecard": [], "notes": [],
                      "items": [], "interview_score": None, "covered": [], "uncovered": [], "error": "",
                      "started": time.time()}
    try:
        return qa_analysis_graph.invoke(state)
    except Exception:
        log.exception("qa analysis workflow could not run")
        stopped = {**state, "error": "The analysis stopped unexpectedly. Please try again."}
        failed(stopped)
        return stopped
