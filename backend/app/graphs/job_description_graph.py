"""The job description workflow: a short prompt becomes a job profile, written from company documents (RAG).

    START -> retrieve_documents -> write_draft -> check_draft --ok--------------------> log_run -> END
                                                      |  ^
                                             problems |  |
                                                      v  |
                                                  revise_draft        (at most MAX_REVISIONS times)

    retrieve_documents   Python + database: the most similar past job descriptions and the company policy notes
    write_draft          AI: writes the title, skills, years, qualifications and the description
    check_draft          Python: is anything missing or against the rules? (the AI suggests, code checks)
    revise_draft         AI: fixes exactly the problems the check found
    log_run              Python + database: one row in workflow_run (outcome, error, time taken)

Nothing is saved as a job here. The result fills the job form, and the interviewer checks, edits and saves it.
"""
import logging
import re
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from app.ai.llm_client import last_error, llm_json
from app.core.database import engine
from app.features.job_library.services.company_document_service import (
    MIN_EXAMPLE_SIMILARITY, TOP_EXAMPLES, TOP_POLICIES, find_documents)
from app.features.system.models import WorkflowRun
from app.graphs.job_description_prompts import JOB_DRAFT_PROMPT, JOB_REVISE_PROMPT

log = logging.getLogger("job_description_graph")

MAX_REVISIONS = 1                # how often the check may send the draft back to the AI
MIN_WORDS, MAX_WORDS = 80, 260   # a little wider than the 120-200 words the AI is asked for


class JobDraftState(TypedDict):
    prompt: str            # what the interviewer typed
    change_request: str    # "generate again": what the interviewer wants changed (may be empty)
    previous: str          # "generate again": the description the interviewer did not like
    examples: list         # past job descriptions found by the search: [{title, text, similarity}]
    policies: list         # company policy notes found by the search
    draft: dict            # the job profile: title, required_skills, preferred_skills, min_years, qualifications, description
    problems: list         # what check_draft found (empty = fine)
    revisions: int         # how often revise_draft has run
    error: str             # set if the AI could not answer at all
    started: float


# ---------- helpers ----------

def _skills(value) -> list[str]:
    items = value if isinstance(value, list) else []
    cleaned = [str(s).strip()[:60] for s in items if str(s).strip()]
    return list(dict.fromkeys(cleaned))[:30]          # no duplicates, same order


def clean_draft(answer: dict) -> dict:
    """The AI's answer, cut to the shape and size of the job form."""
    try:
        years = max(0, min(50, int(answer.get("min_years") or 0)))
    except (TypeError, ValueError):
        years = 0
    return {"title": str(answer.get("title") or "").strip()[:120],
            "required_skills": _skills(answer.get("required_skills")),
            "preferred_skills": _skills(answer.get("preferred_skills")),
            "min_years": years,
            "qualifications": str(answer.get("qualifications") or "").strip()[:300],
            "description": str(answer.get("description") or "").strip()[:5000]}


def _mentions_pay(text: str) -> bool:
    return bool(re.search(r"\b(salary|bdt|usd|tk|taka)\b|[$৳]", text, re.IGNORECASE))


def find_problems(draft: dict, prompt: str) -> list[str]:
    """Plain rules the draft must pass. Each problem is one short sentence the AI (or the interviewer) can fix."""
    problems = []
    if len(draft["title"]) < 2:
        problems.append("the job title is missing")
    if not draft["required_skills"]:
        problems.append("no required skills were found")
    words = len(draft["description"].split())
    if words < MIN_WORDS:
        problems.append(f"the description is too short ({words} words)")
    if words > MAX_WORDS:
        problems.append(f"the description is too long ({words} words)")
    if _mentions_pay(draft["description"]) and not _mentions_pay(prompt):
        problems.append("the description mentions pay, but the prompt does not")
    return problems


def _for_ai(documents: list) -> list[dict]:
    return [{"title": d["title"], "text": d["text"]} for d in documents]


# ---------- nodes ----------

def retrieve_documents(state: JobDraftState) -> dict:
    with Session(engine) as session:
        examples = find_documents(session, state["prompt"], "job_description", TOP_EXAMPLES, MIN_EXAMPLE_SIMILARITY)
        policies = find_documents(session, state["prompt"], "policy", TOP_POLICIES)
    return {"examples": examples, "policies": policies}


def write_draft(state: JobDraftState) -> dict:
    data = {"prompt": state["prompt"], "examples": _for_ai(state["examples"]),
            "company_policy": _for_ai(state["policies"])}
    if state["change_request"]:                      # "generate again" with a wish from the interviewer
        data["change_request"] = state["change_request"]
        data["previous_description"] = state["previous"]
    answer = llm_json(JOB_DRAFT_PROMPT, data)
    if not answer:
        return {"error": last_error()}
    return {"draft": clean_draft(answer)}


def check_draft(state: JobDraftState) -> dict:
    if state["error"]:
        return {}
    # pay may come from the prompt or from the change request
    return {"problems": find_problems(state["draft"], state["prompt"] + " " + state["change_request"])}


def revise_draft(state: JobDraftState) -> dict:
    answer = llm_json(JOB_REVISE_PROMPT, {"prompt": state["prompt"], "change_request": state["change_request"],
                                          "draft": state["draft"], "problems": state["problems"],
                                          "examples": _for_ai(state["examples"]),
                                          "company_policy": _for_ai(state["policies"])})
    # If the AI gives no answer now, the first draft is kept; the problems are shown to the interviewer.
    draft = clean_draft(answer) if answer else state["draft"]
    return {"draft": draft, "revisions": state["revisions"] + 1}


def log_run(state: JobDraftState) -> dict:
    with Session(engine) as session:
        session.add(WorkflowRun(stage="job_description", subject_id=0, outcome="failed" if state["error"] else "done",
                                error=state["error"], seconds=round(time.time() - state["started"], 2)))
        session.commit()
    return {}


# ---------- routing ----------

def after_check(state: JobDraftState) -> str:
    if state["error"] or not state["problems"] or state["revisions"] >= MAX_REVISIONS:
        return "log_run"
    return "revise_draft"


# ---------- wiring ----------

graph = StateGraph(JobDraftState)
graph.add_node("retrieve_documents", retrieve_documents)
graph.add_node("write_draft", write_draft)
graph.add_node("check_draft", check_draft)
graph.add_node("revise_draft", revise_draft)
graph.add_node("log_run", log_run)

graph.add_edge(START, "retrieve_documents")
graph.add_edge("retrieve_documents", "write_draft")
graph.add_edge("write_draft", "check_draft")
graph.add_conditional_edges("check_draft", after_check, ["revise_draft", "log_run"])
graph.add_edge("revise_draft", "check_draft")         # the loop: a revised draft is checked again
graph.add_edge("log_run", END)

job_description_graph = graph.compile()


def write_job_draft(prompt: str, change_request: str = "", previous: str = "") -> JobDraftState:
    """Runs the workflow for one prompt and returns its final state. Never raises.
    "Generate again" passes what should change and the description the interviewer did not like."""
    state: JobDraftState = {"prompt": prompt, "change_request": change_request.strip(), "previous": previous.strip(),
                            "examples": [], "policies": [], "draft": clean_draft({}),
                            "problems": [], "revisions": 0, "error": "", "started": time.time()}
    try:
        return job_description_graph.invoke(state)
    except Exception:
        log.exception("job description workflow could not run")
        return {**state, "error": "the workflow stopped unexpectedly, see the backend log"}
