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

from app.graphs.job_description_graph import job_description_graph  # noqa: E402
from app.graphs.job_post_graph import job_post_graph  # noqa: E402
from app.graphs.recruitment_graph import recruitment_graph  # noqa: E402

# Each feature adds its workflow here: (title, file, compiled graph)
WORKFLOWS = [
    ("Job description workflow", "backend/app/graphs/job_description_graph.py", job_description_graph),
    ("Job post workflow", "backend/app/graphs/job_post_graph.py", job_post_graph),
    ("Main recruitment workflow", "backend/app/graphs/recruitment_graph.py", recruitment_graph),
]
OUTPUT = BACKEND.parent / "docs" / "architecture" / "LumenAI_Workflows_From_Code.md"


def main() -> None:
    parts = ["# LumenAI workflows, drawn from the code",
             "",
             "Made by `backend/scripts/print_workflows.py`. Do not edit by hand: run the script again after a change.",
             "A solid arrow is always followed. A dotted arrow is a choice made by the code at that step.",
             ""]
    for title, file, compiled in WORKFLOWS:
        drawing = compiled.get_graph().draw_mermaid()
        steps = [name for name in compiled.get_graph().nodes if not name.startswith("__")]
        print(f"\n=== {title} ({file}) ===\nSteps: {' -> '.join(steps)}\n\n{drawing}")
        parts += [f"## {title}", "", f"Code: `{file}`", "", f"Steps: {', '.join(f'`{s}`' for s in steps)}", "",
                  "```mermaid", drawing.strip(), "```", ""]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
