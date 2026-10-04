"""Tests for the parent graph and its run log (state saving)."""
from app.graphs.recruitment_graph import run_workflow


def test_every_run_is_logged(client):
    before = len(client.get("/api/workflow-runs?limit=200").json())
    assert run_workflow("pre_interview", 7) == "failed"            # no subgraph is built for this stage yet
    runs = client.get("/api/workflow-runs?limit=200").json()
    assert len(runs) == before + 1
    last = runs[0]                                                 # newest first
    assert last["stage"] == "pre_interview" and last["subject_id"] == 7
    assert last["outcome"] == "failed" and "No workflow is built" in last["error"]
    assert last["seconds"] >= 0


def test_limit(client):
    run_workflow("post_interview", 1)
    run_workflow("post_interview", 2)
    assert len(client.get("/api/workflow-runs?limit=1").json()) == 1
    assert client.get("/api/workflow-runs?limit=0").status_code == 422
