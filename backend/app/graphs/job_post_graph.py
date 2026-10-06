"""The job post workflow: an approved job becomes a SHORT post for the Telegram channel. It is optional:
by default the post is the approved description itself, put together by code (job_posting_service.approved_post).

    START -> write_post -> check_post --ok--------------------> log_run -> END
                               |  ^
                      problems |  |
                               v  |
                           revise_post        (at most MAX_REVISIONS times)

    write_post     AI: writes the post from the approved job
    check_post     Python: is anything missing or against the rules? (the AI suggests, code checks)
    revise_post    AI: fixes exactly the problems the check found
    log_run        Python + database: one row in workflow_run (outcome, error, time taken)

Nothing is posted here. The result fills a text box; the interviewer reads it, may change it, and clicks
"Post to Telegram". Posting is done by the backend code (job_posting_service.py), not by the AI.
"""
import logging
import re
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from app.ai.llm_client import last_error, llm_json
from app.core.database import engine
from app.features.system.models import WorkflowRun
from app.graphs.job_post_prompts import JOB_POST_PROMPT, JOB_POST_REVISE_PROMPT

log = logging.getLogger("job_post_graph")

MAX_REVISIONS = 1                # how often the check may send the post back to the AI
MIN_WORDS, MAX_WORDS = 40, 190   # a little wider than the 60-150 words the AI is asked for


class JobPostState(TypedDict):
    job: dict              # the approved job: id, title, skills, min_years, qualifications, description
    change_request: str    # "generate again": what the interviewer wants changed (may be empty)
    previous: str          # "generate again": the post the interviewer did not like
    text: str              # the post
    problems: list         # what check_post found (empty = fine)
    revisions: int         # how often revise_post has run
    error: str             # set if the AI could not answer at all
    started: float


# ---------- helpers ----------

def clean_post(answer: dict) -> str:
    return str(answer.get("text") or "").strip()[:3500]


def _mentions_pay(text: str) -> bool:
    return bool(re.search(r"\b(salary|bdt|usd|tk|taka)\b|[$৳]", text, re.IGNORECASE))


def find_post_problems(text: str, job: dict) -> list[str]:
    """Plain rules the post must pass. Each problem is one short sentence the AI (or the interviewer) can fix."""
    problems = []
    words = len(text.split())
    if words < MIN_WORDS:
        problems.append(f"the post is too short ({words} words)")
    if words > MAX_WORDS:
        problems.append(f"the post is too long ({words} words)")
    if job["title"].lower() not in text.lower():
        problems.append("the job title is not in the post")
    if re.search(r"https?://|www\.", text, re.IGNORECASE):
        problems.append("the post contains a link (the application link is added afterwards)")
    if _mentions_pay(text) and not _mentions_pay(job["description"]):
        problems.append("the post mentions pay, but the job description does not")
    return problems


def _job_for_ai(job: dict) -> dict:
    return {key: job[key] for key in ("title", "required_skills", "preferred_skills", "min_years",
                                      "qualifications", "description")}


# ---------- nodes ----------

def write_post(state: JobPostState) -> dict:
    data = {"job": _job_for_ai(state["job"])}
    if state["change_request"]:                      # "generate again" with a wish from the interviewer
        data["change_request"] = state["change_request"]
        data["previous_post"] = state["previous"]
    answer = llm_json(JOB_POST_PROMPT, data)
    if not answer:
        return {"error": last_error()}
    return {"text": clean_post(answer)}


def check_post(state: JobPostState) -> dict:
    if state["error"]:
        return {}
    return {"problems": find_post_problems(state["text"], state["job"])}


def revise_post(state: JobPostState) -> dict:
    answer = llm_json(JOB_POST_REVISE_PROMPT, {"job": _job_for_ai(state["job"]), "post": state["text"],
                                               "change_request": state["change_request"],
                                               "problems": state["problems"]})
    # If the AI gives no answer now, the first post is kept; the problems are shown to the interviewer.
    text = clean_post(answer) if answer else state["text"]
    return {"text": text, "revisions": state["revisions"] + 1}


def log_run(state: JobPostState) -> dict:
    with Session(engine) as session:
        session.add(WorkflowRun(stage="job_post", subject_id=state["job"]["id"],
                                outcome="failed" if state["error"] else "done",
                                error=state["error"], seconds=round(time.time() - state["started"], 2)))
        session.commit()
    return {}


# ---------- routing ----------

def after_check(state: JobPostState) -> str:
    if state["error"] or not state["problems"] or state["revisions"] >= MAX_REVISIONS:
        return "log_run"
    return "revise_post"


# ---------- wiring ----------

graph = StateGraph(JobPostState)
graph.add_node("write_post", write_post)
graph.add_node("check_post", check_post)
graph.add_node("revise_post", revise_post)
graph.add_node("log_run", log_run)

graph.add_edge(START, "write_post")
graph.add_edge("write_post", "check_post")
graph.add_conditional_edges("check_post", after_check, ["revise_post", "log_run"])
graph.add_edge("revise_post", "check_post")           # the loop: a revised post is checked again
graph.add_edge("log_run", END)

job_post_graph = graph.compile()


def write_job_post(job: dict, change_request: str = "", previous: str = "") -> JobPostState:
    """Runs the workflow for one job and returns its final state. Never raises."""
    state: JobPostState = {"job": job, "change_request": change_request.strip(), "previous": previous.strip(), "text": "", "problems": [], "revisions": 0, "error": "", "started": time.time()}
    try:
        return job_post_graph.invoke(state)
    except Exception:
        log.exception("job post workflow could not run")
        return {**state, "error": "the workflow stopped unexpectedly, see the backend log"}
