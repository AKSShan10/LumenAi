"""The talent pool invitation workflow: one run per person, from the facts to a checked draft.

    START -> load_facts -> write_draft -> check_draft --ok--> finish -> END
                                ^              |
                                '-- problems --'  (once; after that: standard_text -> finish)

    load_facts     PYTHON+DB  first name, earlier job, new job, the skills that fit (from the code match), wish
    write_draft    AI         Gemini writes the subject and the text (it never sees scores, decisions or the address)
    check_draft    PYTHON     the subject always has the job title (code adds it if missing); a formal greeting ("Dear ...");
                              names the person and the new job; no links, emails or phone numbers; no scores, %,
                              earlier decisions or promises; only skills that fit are named; 30-200 words
    standard_text  PYTHON     a plain text the interviewer can edit, when the AI fails twice
    finish         PYTHON+DB  one workflow_run row (Settings → workflow log)

The AI writes; code checks; a person edits and clicks Send (invite_service.send). Nothing is sent here.
Started by invite_service.drafts() for every chosen person, and again on "Write again".
"""
import logging
import re
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, select

from app.ai.llm_client import llm_json
from app.core.database import engine
from app.features.candidates.models import Candidate
from app.features.jobs.models import Job
from app.features.screening.models import ScreeningResult
from app.features.system.models import WorkflowRun
from app.features.talent_pool.models import TalentPoolEntry
from app.features.talent_pool.services.pool_service import skill_match
from app.graphs.talent_invite_prompts import TALENT_INVITE_PROMPT
from app.utils.skill_names import find_skill

log = logging.getLogger("talent_invite_graph")

MAX_TRIES = 2                       # the AI writes at most twice; then the standard text
MIN_WORDS, MAX_WORDS = 30, 200
NOT_ALLOWED = {                     # words that must not be in the email, and why
    r"https?://|www\.": "a web address (the system adds the links)",
    r"[\w.+-]+@[\w-]+\.[\w.]+": "an email address",
    r"\+?\d[\d\s-]{7,}\d": "a phone number",
    r"\bscores?\b|\d+\s*%|\bpercent": "a score or a percentage",
    r"\brejected\b|\bnot selected\b|\bunsuccessful\b|\bdecision\b": "the earlier result or decision",
    r"\bguarantee|\bjob offer\b|\bwill be hired\b|\bwe will hire\b|\boffer you\b": "a promise of a job or an offer",
}


class InviteState(TypedDict):
    pool_id: int
    job_id: int
    instruction: str                # the interviewer's wish on "Write again" ("" = none)
    facts: dict                     # what the AI gets
    other_skills: list              # the job's skills the CV does NOT show: the email must not name them
    subject: str
    body: str
    problems: list                  # what check_draft found in the last draft
    tries: int
    outcome: str                    # ai | standard_text
    started: float


# Workflow step "load_facts": only what the email needs; never scores, decisions, email address or phone
def load_facts(state: InviteState) -> dict:
    with Session(engine) as session:
        entry = session.get(TalentPoolEntry, state["pool_id"])
        candidate = session.get(Candidate, entry.candidate_id)
        job, earlier = session.get(Job, state["job_id"]), session.get(Job, candidate.job_id)
        screening = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate.id)).first()
        cv_skills = list((screening.parsed or {}).get("skills") or []) if screening else []
        fit = skill_match(job, candidate.cv_text or "", cv_skills)       # the same code match as the list
    facts = {"first_name": (candidate.full_name.split() or ["there"])[0], "earlier_job": earlier.title if earlier else "",
             "new_job": job.title, "new_job_description": (job.description or "")[:1500],
             "fitting_skills": fit["matched"], "instruction": state["instruction"]}
    return {"facts": facts, "other_skills": fit["missing"]}


# Workflow step "write_draft": the AI writes the subject and the text (again with the problems, if any)
def write_draft(state: InviteState) -> dict:
    facts = {**state["facts"], "problems": state["problems"]} if state["problems"] else state["facts"]
    answer = llm_json(TALENT_INVITE_PROMPT, facts)                     # → AI call
    subject = str(answer.get("subject") or "").strip()[:200] if isinstance(answer, dict) else ""
    body = str(answer.get("body") or "").strip()[:4000] if isinstance(answer, dict) else ""
    return {"subject": subject, "body": body, "tries": state["tries"] + 1}


def with_job_title(subject: str, job_title: str) -> str:
    """The subject always shows the job title: "A new opening" → "A new opening: Platform Engineer"."""
    subject = subject.strip()
    if job_title.lower() in subject.lower():
        return subject[:200]
    return (f"{subject}: {job_title}" if subject else f"A new opening: {job_title}")[:200]


def draft_problems(subject: str, body: str, facts: dict, other_skills: list) -> list[str]:
    """The check step: plain rules every draft must pass before a person sees it. [] = fine."""
    if not subject or not body:
        return ["the subject or the text is empty (the AI did not answer)"]
    problems, text = [], f"{subject}\n{body}"
    if facts["first_name"].lower() not in body.lower():
        problems.append(f"the text does not greet {facts['first_name']} by name")
    if not re.match(r"\s*dear\b", body, flags=re.IGNORECASE):            # always formal
        problems.append("the greeting is not formal (start with \"Dear <first name>,\")")
    if facts["new_job"].lower() not in body.lower():
        problems.append(f"the text does not name the new job \"{facts['new_job']}\"")
    for pattern, what in NOT_ALLOWED.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            problems.append(f"the text has {what}")
    for skill in other_skills:                                         # a skill the CV does not show
        if find_skill(skill, [], body):
            problems.append(f"the text names {skill}, which is not shown in the CV")
    words = len(body.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"the text has {words} words (it should have {MIN_WORDS}-{MAX_WORDS})")
    return problems


# Workflow step "check_draft"
def check_draft(state: InviteState) -> dict:
    subject = with_job_title(state["subject"], state["facts"]["new_job"]) if state["subject"] else ""
    return {"subject": subject, "problems": draft_problems(subject, state["body"], state["facts"], state["other_skills"])}


# Workflow step "standard_text": a plain email when the AI could not write one that passes the check
def standard_text(state: InviteState) -> dict:
    facts = state["facts"]
    skills = f" Your experience with {', '.join(facts['fitting_skills'])} may fit it well." if facts["fitting_skills"] else ""
    body = (f"Dear {facts['first_name']},\n\nThank you again for your earlier application for {facts['earlier_job']}. "
            f"We have a new opening for {facts['new_job']}.{skills} We would be glad if you applied.")
    return {"subject": f"A new opening: {facts['new_job']}", "body": body, "outcome": "standard_text"}


# Workflow step "finish": one row in the workflow log
def finish(state: InviteState) -> dict:
    outcome = state["outcome"] or "ai"
    with Session(engine) as session:
        entry = session.get(TalentPoolEntry, state["pool_id"])
        session.add(WorkflowRun(stage="talent_invite", subject_id=entry.candidate_id, outcome=outcome,
                                error="; ".join(state["problems"]) if outcome == "standard_text" else "",
                                seconds=round(time.time() - state["started"], 2)))
        session.commit()
    log.info("talent invite draft pool=%s job=%s outcome=%s tries=%s", state["pool_id"], state["job_id"], outcome,
             state["tries"])
    return {"outcome": outcome}


# After check_draft: fine → finish; problems → write again (once) → after that the standard text
def after_check(state: InviteState) -> str:
    if not state["problems"]:
        return "finish"
    return "write_draft" if state["tries"] < MAX_TRIES else "standard_text"


graph = StateGraph(InviteState)
graph.add_node("load_facts", load_facts)
graph.add_node("write_draft", write_draft)
graph.add_node("check_draft", check_draft)
graph.add_node("standard_text", standard_text)
graph.add_node("finish", finish)

graph.add_edge(START, "load_facts")
graph.add_edge("load_facts", "write_draft")
graph.add_edge("write_draft", "check_draft")
graph.add_conditional_edges("check_draft", after_check, ["finish", "write_draft", "standard_text"])
graph.add_edge("standard_text", "finish")
graph.add_edge("finish", END)

talent_invite_graph = graph.compile()


def draft_invite(pool_id: int, job_id: int, instruction: str = "") -> InviteState:
    """Runs the workflow for one person and returns the state with the checked subject and body."""
    return talent_invite_graph.invoke({"pool_id": pool_id, "job_id": job_id, "instruction": instruction,
                                       "facts": {}, "other_skills": [], "subject": "", "body": "", "problems": [],
                                       "tries": 0, "outcome": "", "started": time.time()})
