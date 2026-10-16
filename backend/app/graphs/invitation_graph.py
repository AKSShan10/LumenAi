"""The interview invitation workflow: one run per interview, from the first draft to the sent email.

    START -> write_draft -> check_draft --ok--> save_draft -> ask_person (PAUSE: waits for the interviewer)
                 ^              |                                     |  Send            |  Write again / new time
                 '-- problems --'  (once; then the standard text)     v                  '--> write_draft
                                                                  send_email -> save_result -> ask_person (waits again)

    write_draft   AI          Gemini writes the subject and the text (never sees the email address; writes {join_link}).
                              "Schedule all" gives a template the interviewer already checked: it is filled in, no AI call
    check_draft   PYTHON      the placeholder is there, no web or email address of its own, the date as given, not too long
    save_draft    PYTHON+DB   the real link goes in; the draft is saved on the interview (status "" = draft)
    ask_person    PERSON      the run pauses (LangGraph interrupt) until the interviewer clicks Send or Write again.
                              The paused run is kept by the checkpointer (PostgreSQL), so it survives a restart
    send_email    PYTHON      the edited text + the calendar invite, sent over SMTP (smtp_service.send_email)
    save_result   PYTHON+DB   sent | not_sent | no_email | failed: <reason>; then it waits in ask_person again,
                              so the invitation can be sent again or rewritten after a new time

The AI writes; code checks and puts in the link and the calendar; a person sends. Nothing is sent by itself.
Started by interview_service.schedule(); continued by interview_service (send, write again, new time).
"""
import logging
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import START, StateGraph
from langgraph.types import Command, interrupt
from sqlmodel import Session

from app.ai.llm_client import last_error, llm_json
from app.core import config
from app.core.database import engine
from app.features.interviews.models import InterviewSession
from app.features.interviews.services import smtp_service
from app.features.interviews.services.invitation_service import (
    as_utc, calendar_for, draft_problems, email_facts, fill_template, join_link, standard_text,
    subject_with_time, with_link)
from app.features.system.models import WorkflowRun
from app.graphs.checkpointer import checkpointer
from app.graphs.invitation_prompts import INVITATION_PROMPT

log = logging.getLogger("invitation_graph")

MAX_WRITES = 2                   # the AI writes a draft at most twice per round; then the standard text is used


class InvitationState(TypedDict, total=False):
    session_id: int        # the interview (interview_session)
    interviewer: str       # the interviewer's name, for the signature
    subject: str
    body: str              # with {join_link} until save_draft puts the real link in
    problems: list         # what check_draft found ("" list = fine)
    writes: int            # how often the AI wrote in this round
    answer: dict           # what the interviewer did in ask_person: {action: send | write_again, to, subject, body}
    message: str           # one sentence for the page
    template: dict         # "Schedule all": {subject, body} with {candidate_name}, {date} ... (used once, then cleared)


# ---------- steps ----------

def write_draft(state: InvitationState) -> dict:
    """Workflow step "write_draft": Gemini (llm_json) writes the invitation subject and text from the facts"""
    with Session(engine) as session:
        facts = email_facts(session, session.get(InterviewSession, state["session_id"]), state["interviewer"])
    template = state.get("template")
    if template:                                     # "Schedule all": the checked template, filled in by code
        return {"subject": fill_template(template["subject"], facts), "body": fill_template(template["body"], facts),
                "writes": 1, "template": {}}         # cleared: "Write again" later asks the AI for this candidate
    if state.get("problems"):
        facts["fix_these"] = state["problems"]                          # the second try: say what to fix
    answer = llm_json(INVITATION_PROMPT, facts)
    writes = state.get("writes", 0) + 1
    if not isinstance(answer, dict):
        return {"subject": "", "body": "", "writes": writes, "problems": [f"the AI did not answer ({last_error()})"]}
    return {"subject": str(answer.get("subject") or "").strip()[:200], "body": str(answer.get("body") or "").strip()[:7000],
            "writes": writes}


def check_draft(state: InvitationState) -> dict:
    """Workflow step "check_draft": checks the AI's email with draft_problems (link placeholder, date, length)"""
    with Session(engine) as session:
        facts = email_facts(session, session.get(InterviewSession, state["session_id"]), state["interviewer"])
    if not state["subject"] and not state["body"] and state.get("problems"):
        return {}                                                        # the AI did not answer: keep its reason
    return {"problems": draft_problems(state["subject"], state["body"], facts)}


def save_draft(state: InvitationState) -> dict:
    """Workflow step "save_draft": puts the real join link in and saves the draft (or the standard text if it failed)"""
    with Session(engine) as session:
        interview = session.get(InterviewSession, state["session_id"])
        subject, body, message = state["subject"], state["body"], ""
        if state.get("problems"):                                        # still not good after the last try
            subject, body = standard_text(email_facts(session, interview, state["interviewer"]))
            message = ("The AI's email did not pass the check (" + "; ".join(state["problems"]) +
                       "), so a standard text was used. Check it before sending.")
        interview.invitation_subject = subject_with_time(subject, interview)   # date + time: a new Gmail thread
        interview.invitation_body = with_link(body, join_link(interview))
        interview.invitation_status = ""                                 # a new draft: not sent yet
        session.add(interview)
        session.commit()
    return {"message": message or "The AI wrote the invitation. Check it, then click Send email.", "writes": 0,
            "problems": []}


def ask_person(state: InvitationState) -> dict:
    """The pause. The page shows the draft; the interviewer's click continues the run (answer())."""
    # → PAUSE: waits for Send / Write again; answer() resumes it
    answer = interrupt({"session_id": state["session_id"], "question": "Send this invitation?"})
    answer = answer if isinstance(answer, dict) else {}
    return {"answer": answer, "interviewer": answer.get("interviewer") or state["interviewer"]}


def send_email(state: InvitationState) -> dict:
    """Workflow step "send_email": saves the edited email and sends it with the calendar invite (smtp_service.send_email)"""
    answer = state["answer"]
    with Session(engine) as session:
        interview = session.get(InterviewSession, state["session_id"])
        to = str(answer.get("to") or "").strip()
        interview.invite_email, interview.invitation_subject = to, str(answer.get("subject") or "").strip()
        interview.invitation_body = with_link(str(answer.get("body") or "").strip(), join_link(interview))  # link put back
        if not to:
            interview.invitation_status = "no_email"
            message = "No email address, so nothing was sent. Add the address and send again."
        elif not config.SMTP_HOST or not config.SMTP_FROM:                # email sending is not set up in .env
            interview.invitation_status = "not_sent"
            message = ("Saved, but not sent: email sending is not set up (SMTP_HOST in .env). "
                       "Copy the text and the link, or set up SMTP and send again.")
        else:
            # → sends the email over SMTP (Gmail etc.) with the calendar invite; a button click, so no AI and no MCP
            result = smtp_service.send_email(to, interview.invitation_subject, interview.invitation_body,
                                             calendar_for(session, interview, to))
            if result.get("ok"):
                interview.invitation_status, interview.sent_at = "sent", datetime.now(timezone.utc)
                message = f"Invitation sent to {to}, with the calendar invite."
            else:
                reason = result.get("error") or "unknown problem"
                interview.invitation_status, message = f"failed: {reason}"[:300], f"Not sent: {reason}."
        session.add(interview)
        session.commit()
    return {"message": message}


def save_result(state: InvitationState) -> dict:
    """Workflow step "save_result": writes one workflow_run row with the send outcome (sent, failed ...)"""
    with Session(engine) as session:
        interview = session.get(InterviewSession, state["session_id"])
        outcome = interview.invitation_status.split(":")[0]
        session.add(WorkflowRun(stage="invitation", subject_id=interview.candidate_id, outcome=outcome,
                                error=interview.invitation_status[len(outcome) + 2:], seconds=0.0))
        session.commit()
    log.info("invitation session=%s %s", state["session_id"], outcome)
    return {}


# ---------- routing (Python decides which step comes next) ----------

def after_check(state: InvitationState) -> str:
    """Routing after check_draft: back to write_draft if problems and tries remain, otherwise save_draft"""
    if state.get("problems") and state.get("writes", 0) < MAX_WRITES:
        return "write_draft"
    return "save_draft"


def after_answer(state: InvitationState) -> str:
    """Routing after ask_person: send_email if the interviewer clicked Send, otherwise write_draft again"""
    return "send_email" if state["answer"].get("action") == "send" else "write_draft"


# ---------- wiring ----------

graph = StateGraph(InvitationState)
graph.add_node("write_draft", write_draft)
graph.add_node("check_draft", check_draft)
graph.add_node("save_draft", save_draft)
graph.add_node("ask_person", ask_person)
graph.add_node("send_email", send_email)
graph.add_node("save_result", save_result)

graph.add_edge(START, "write_draft")
graph.add_edge("write_draft", "check_draft")
graph.add_conditional_edges("check_draft", after_check, ["write_draft", "save_draft"])
graph.add_edge("save_draft", "ask_person")
graph.add_conditional_edges("ask_person", after_answer, ["send_email", "write_draft"])
graph.add_edge("send_email", "save_result")
graph.add_edge("save_result", "ask_person")              # the loop: it can be sent again or rewritten later

invitation_graph = graph.compile()                       # for drawing (scripts/print_workflows.py)
_runner = None


def runner():
    """The workflow with the checkpointer, so a run can pause in ask_person and be continued later."""
    global _runner
    if _runner is None:
        _runner = graph.compile(checkpointer=checkpointer())
    return _runner


def thread_of(interview: InterviewSession) -> str:
    """One thread per interview. The time is part of it, so a new database (tests) never meets an old thread."""
    return f"invitation-{interview.id}-{int(as_utc(interview.created_at).timestamp() * 1_000_000)}"


def _config(interview: InterviewSession) -> dict:
    """Returns the LangGraph config with this interview's thread_id (thread_of)"""
    return {"configurable": {"thread_id": thread_of(interview)}}


def start_invitation(interview: InterviewSession, interviewer: str, template: dict | None = None) -> str:
    """Starts the run for a new interview: it writes and checks the draft, then pauses in ask_person.
    template = {subject, body} from "Schedule all" (filled in instead of an AI draft). Returns the message for the page."""
    result = runner().invoke({"session_id": interview.id, "interviewer": interviewer, "writes": 0, "problems": [],
                              "template": template or {}}, _config(interview))
    return result.get("message", "")


def answer(interview: InterviewSession, reply: dict, interviewer: str) -> str:
    """Continues the paused run with the interviewer's click: {"action": "send", "to", "subject", "body"} or
    {"action": "write_again"}. A run that is not waiting (for example an interview from before this workflow) is
    started first. Returns the message for the page."""
    if runner().get_state(_config(interview)).next != ("ask_person",):
        start_invitation(interview, interviewer)
        if reply.get("action") != "send":
            return runner().get_state(_config(interview)).values.get("message", "")   # starting wrote a new draft
    # → RESUME: continues the paused ask_person step with the click
    result = runner().invoke(Command(resume={**reply, "interviewer": interviewer}), _config(interview))
    return result.get("message", "")
