"""The job posting workflow: one run per "post this job?" question in the Assistant chat.

    START -> check_job --problem----------------------------------> save_result -> END
                |  ok
                v
            ask_person   (PAUSE: LangGraph interrupt, waits for the interviewer's Yes or No)
                |
         Yes ---+--- No ---------------------------------------> save_result -> END
                v
             publish   (Blogger, through the MCP tool publish_blog_post)
                v
            save_result -> END

    check_job     PYTHON      the job is approved, the form link is a link, the post has 20 to 3500 characters
    ask_person    PERSON      the run pauses until the interviewer answers the Yes / No question on the screen.
                              The paused run is kept by the checkpointer (PostgreSQL), so it survives a restart
    publish       PYTHON+MCP  job_posting_service.post_job(): checks again that the job is still approved, posts
                              the text with an "Apply now" link and saves the try in job_posting
    save_result   PYTHON+DB   what happened, on the question: done | failed | cancelled, with one sentence

The AI never posts: in the chat it can only ask (assistant_agent.request_job_post). The backend starts this run
after the AI's turn (start_post), and only the interviewer's answer continues it (answer_post).
The post text is made by code from the approved job (job_posting_service.approved_post); no AI call here.
"""
import logging
from typing import TypedDict

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlmodel import Session

from app.core.database import engine
from app.features.assistant.models import AssistantAction
from app.features.jobs.models import Job
from app.features.jobs.services.job_posting_service import post_job
from app.graphs.checkpointer import checkpointer

log = logging.getLogger("job_post_graph")


class JobPostState(TypedDict, total=False):
    action_id: int        # the Yes / No question (assistant_action)
    problem: str          # why the job cannot be posted ("" = it can)
    yes: bool             # the interviewer's answer
    status: str           # done | failed | cancelled
    result: str           # one sentence for the chat


# ---------- steps ----------

def check_job(state: JobPostState) -> dict:
    with Session(engine) as session:
        action = session.get(AssistantAction, state["action_id"])
        job = session.get(Job, action.job_id)
        link, text = action.apply_url.strip(), action.text.strip()
        if not job:
            problem = "The job no longer exists."
        elif job.status != "approved":
            problem = "Approve the job first. Only an approved job can be posted."
        elif not link.startswith("https://") or " " in link:
            problem = "The application form link is missing or not a link."
        elif not 20 <= len(text) <= 3500:
            problem = "The post text must have 20 to 3500 characters."
        else:
            problem = ""
    return {"problem": problem}


def ask_person(state: JobPostState) -> dict:
    """The pause. The value given to interrupt() is what the screen asks; the answer comes from answer_post()."""
    answer = interrupt({"action_id": state["action_id"], "question": "Post this job on the company blog?"})
    return {"yes": bool(answer.get("yes"))}


def publish(state: JobPostState) -> dict:
    with Session(engine) as session:
        action = session.get(AssistantAction, state["action_id"])
        job = session.get(Job, action.job_id)
        if not job:
            return {"status": "failed", "result": "The job no longer exists."}
        try:
            posting = post_job(session, job, action.text, action.apply_url)      # checks again: still approved?
        except HTTPException as problem:                                     # for example: edited, a draft again
            return {"status": "failed", "result": str(problem.detail)}
        if posting.status == "posted":
            return {"status": "done", "result": f"The job \"{job.title}\" was posted to the Blogger blog."}
        return {"status": "failed", "result": "The post was not accepted: " + posting.error}


def save_result(state: JobPostState) -> dict:
    if state.get("problem"):
        status, result = "failed", state["problem"]
    elif not state.get("yes"):
        status, result = "cancelled", "You said No. Nothing was changed."
    else:
        status, result = state["status"], state["result"]
    with Session(engine) as session:
        action = session.get(AssistantAction, state["action_id"])
        action.status, action.result = status, result
        session.add(action)
        session.commit()
    log.info("job post action=%s %s", state["action_id"], status)
    return {"status": status, "result": result}


def after_check(state: JobPostState) -> str:
    return "save_result" if state["problem"] else "ask_person"


def after_answer(state: JobPostState) -> str:
    return "publish" if state["yes"] else "save_result"


# ---------- wiring ----------

graph = StateGraph(JobPostState)
graph.add_node("check_job", check_job)
graph.add_node("ask_person", ask_person)
graph.add_node("publish", publish)
graph.add_node("save_result", save_result)

graph.add_edge(START, "check_job")
graph.add_conditional_edges("check_job", after_check, ["ask_person", "save_result"])
graph.add_conditional_edges("ask_person", after_answer, ["publish", "save_result"])
graph.add_edge("publish", "save_result")
graph.add_edge("save_result", END)

job_post_graph = graph.compile()                     # for drawing (scripts/print_workflows.py)
_runner = None


def runner():
    """The workflow with the checkpointer, so a run can pause in ask_person and be continued later."""
    global _runner
    if _runner is None:
        _runner = graph.compile(checkpointer=checkpointer())
    return _runner


def thread_of(action: AssistantAction) -> str:
    """One thread per question. The time is part of it, so a new database (tests) never meets an old thread."""
    return f"job-post-{action.id}-{int(action.created_at.timestamp() * 1_000_000)}"


def start_post(action: AssistantAction) -> None:
    """Starts the run for a new "post this job?" question. It stops at ask_person and waits."""
    runner().invoke({"action_id": action.id}, {"configurable": {"thread_id": thread_of(action)}})


def answer_post(action: AssistantAction, yes: bool) -> None:
    """Continues the paused run with the interviewer's answer (a run that was never started is started first)."""
    config = {"configurable": {"thread_id": thread_of(action)}}
    if runner().get_state(config).next != ("ask_person",):
        start_post(action)
        if runner().get_state(config).next != ("ask_person",):
            return                                    # check_job found a problem: it is saved on the question
    runner().invoke(Command(resume={"yes": yes}), config)
