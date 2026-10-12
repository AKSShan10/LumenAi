"""The run log: every AI workflow run is saved as one row and shown on the Settings page."""
from app.graphs.job_description_graph import write_job_draft


def test_every_run_is_logged(client):
    # the newest rows, not a count: other tests write many rows, more than one page holds
    before = [run["id"] for run in client.get("/api/workflow-runs?limit=200").json()]
    write_job_draft("Backend developer with Python and FastAPI, 3 years experience")
    runs = client.get("/api/workflow-runs?limit=200").json()
    assert [run["id"] for run in runs if run["id"] not in before] == [runs[0]["id"]]     # exactly one new row
    last = runs[0]                                                 # newest first
    assert last["stage"] == "job_description" and last["outcome"] == "done" and last["error"] == ""
    assert last["seconds"] >= 0


def test_limit(client):
    write_job_draft("QA engineer with Selenium and Python, 2 years experience")
    write_job_draft("Data analyst with SQL and Excel, 1 year experience")
    assert len(client.get("/api/workflow-runs?limit=1").json()) == 1
    assert client.get("/api/workflow-runs?limit=0").status_code == 422
