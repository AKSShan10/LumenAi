"""The parent graph: recruitment orchestrator. It starts the right subgraph and saves a log of the run.

    START -> load_context --stage?--> (one subgraph per stage, added with each feature)
                                                |
                                          persist_state -> END

    load_context        Python: the input the chosen subgraph needs
    persist_state       Python + database: one row in workflow_run (stage, outcome, error, time taken)

Why one run per action and not one long run per candidate: people act between the stages (HR uploads
CVs, the interviewer holds the interview, the recruiter decides), sometimes days apart. Each person's
click starts the parent graph with a "stage". The results are saved in the database after every stage,
so an unfinished run is simply started again after a restart.
"""
import logging
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from app.core.database import engine
from app.features.system.models import WorkflowRun

log = logging.getLogger("recruitment_graph")

# The stages that have a subgraph. Each feature adds its stage here and its node in the wiring below.
STAGES: tuple[str, ...] = ()


class RecruitmentState(TypedDict):
    stage: str             # pre_interview | interview_analysis | post_interview
    subject_id: int        # candidate id (pre / post interview) or interview session id
    subgraph_input: dict   # made by load_context
    outcome: str           # how the subgraph ended (screened, excluded, needs_review, done, failed)
    error: str             # only set if the run failed
    started: float


# ---------- routing ----------

def choose_stage(state: RecruitmentState) -> str:
    return state["stage"] if state["stage"] in STAGES else "persist_state"


# ---------- nodes ----------

def load_context(state: RecruitmentState) -> dict:
    """Each feature adds an `if state["stage"] == ...` branch here that builds its subgraph input."""
    if state["stage"] not in STAGES:
        return {"error": f"No workflow is built for stage '{state['stage']}' yet", "outcome": "failed"}
    return {"subgraph_input": {}}


def persist_state(state: RecruitmentState) -> dict:
    outcome, error = state["outcome"] or "failed", state["error"]
    with Session(engine) as session:
        session.add(WorkflowRun(stage=state["stage"], subject_id=state["subject_id"], outcome=outcome,
                                error=error, seconds=round(time.time() - state["started"], 2)))
        session.commit()
    return {"outcome": outcome}


# ---------- wiring ----------

graph = StateGraph(RecruitmentState)
graph.add_node("load_context", load_context)
graph.add_node("persist_state", persist_state)

graph.add_edge(START, "load_context")
graph.add_conditional_edges("load_context", choose_stage, list(STAGES) + ["persist_state"])
for stage in STAGES:
    graph.add_edge(stage, "persist_state")
graph.add_edge("persist_state", END)

recruitment_graph = graph.compile()


def run_workflow(stage: str, subject_id: int) -> str:
    """Run one stage for one CV / interview / candidate. Returns how it ended. Never raises.

    Routers start it in the background, so the screen does not wait for the AI:
        background.add_task(run_workflow, "pre_interview", candidate.id)
    """
    state = {"stage": stage, "subject_id": subject_id, "subgraph_input": {}, "outcome": "", "error": "",
             "started": time.time()}
    try:
        return recruitment_graph.invoke(state)["outcome"]
    except Exception:
        log.exception("%s %s could not run", stage, subject_id)
        return "failed"
