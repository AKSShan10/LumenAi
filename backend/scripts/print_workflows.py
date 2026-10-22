"""Draws every LangGraph workflow from the code itself and saves the drawings.

Run it from the backend folder:

    python scripts/print_workflows.py

It prints each workflow and writes docs/architecture/LumenAI_Workflows_From_Code.md.
The drawings are Mermaid text: GitHub and VS Code show them as diagrams, or paste one into https://mermaid.live
Because they are made from the compiled graphs, they always match the code. No database is needed.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))                      # so "import app..." works when run as a script

from langgraph.prebuilt import create_react_agent  # noqa: E402

from app.ai.fake_chat_model import FakeToolChatModel  # noqa: E402
from app.graphs.assistant_agent import LOCAL_TOOLS, keep_recent  # noqa: E402
from app.graphs.cv_screening_graph import cv_screening_graph  # noqa: E402
from app.graphs.job_description_graph import job_description_graph  # noqa: E402
from app.graphs.invitation_graph import invitation_graph  # noqa: E402
from app.graphs.job_post_graph import job_post_graph  # noqa: E402
from app.graphs.qa_analysis_graph import qa_analysis_graph  # noqa: E402
from app.graphs.assessment_graph import assessment_graph  # noqa: E402

# The chatbot agent is built for every message (assistant_agent._run). Its shape is always the same:
# keep_recent -> agent <-> tools. Here it is built with the stand-in model and the two local tools, only to draw it.
# (In the app it also has the checkpointer: each chat is one thread, so the agent remembers the chat.)
assistant_agent_graph = create_react_agent(FakeToolChatModel(), LOCAL_TOOLS, pre_model_hook=keep_recent)

# Each feature adds its workflow here: (title, file, compiled graph)
WORKFLOWS = [
    ("Job description workflow", "backend/app/graphs/job_description_graph.py", job_description_graph),
    ("Job posting workflow (pauses for the interviewer's Yes or No)", "backend/app/graphs/job_post_graph.py",
     job_post_graph),
    ("CV screening workflow (pre-interview subgraph, one run per CV)", "backend/app/graphs/cv_screening_graph.py",
     cv_screening_graph),
    ("Interview invitation workflow (pauses until the interviewer sends)", "backend/app/graphs/invitation_graph.py",
     invitation_graph),
    ("Q&A analysis workflow (after the interview, one run per interview)", "backend/app/graphs/qa_analysis_graph.py",
     qa_analysis_graph),
    ("Assessment workflow (post-interview, one run per candidate)", "backend/app/graphs/assessment_graph.py",
     assessment_graph),
    ("Assistant agent (the chatbot)", "backend/app/graphs/assistant_agent.py", assistant_agent_graph),
]
OUTPUT = BACKEND.parent / "docs" / "architecture" / "LumenAI_Workflows_From_Code.md"


# LangGraph colours the boxes light but sets no text colour, so a dark editor theme (VS Code) shows light text
# on light boxes. Dark text, a visible border and readable arrow labels work on dark and light backgrounds.
READABLE = {
    "classDef default fill:#f2f0ff,line-height:1.2":
        "classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2",
    "classDef last fill:#bfb6fc": "classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434",
    "classDef first fill-opacity:0": "classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434",
    "([<p>__start__</p>])": "([start])",           # the HTML label ignores the text colour; plain text follows it
    "([<p>__end__</p>])": "([end])",
}


# Returns the Mermaid drawing with colours that stay readable on a dark background
def readable(drawing: str) -> str:
    for old, new in READABLE.items():
        drawing = drawing.replace(old, new)
    return drawing


def main() -> None:
    parts = ["# LumenAI workflows, drawn from the code",
             "",
             "Made by `backend/scripts/print_workflows.py`. Do not edit by hand: run the script again after a change.",
             "A solid arrow is always followed. A dotted arrow is a choice made by the code at that step.",
             ""]
    for title, file, compiled in WORKFLOWS:
        drawing = readable(compiled.get_graph().draw_mermaid())
        steps = [name for name in compiled.get_graph().nodes if not name.startswith("__")]
        print(f"\n=== {title} ({file}) ===\nSteps: {' -> '.join(steps)}\n\n{drawing}")
        parts += [f"## {title}", "", f"Code: `{file}`", "", f"Steps: {', '.join(f'`{s}`' for s in steps)}", "",
                  "```mermaid", drawing.strip(), "```", ""]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
