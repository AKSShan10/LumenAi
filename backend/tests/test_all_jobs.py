"""The "All jobs" views: candidates, interviews and the comparison of every job at once. Made-up data only."""
from tests.test_assessments import assess, ready
from tests.test_interviews import cv
from tests.test_video_call import interview, livekit  # noqa: F401  (a scheduled interview and LiveKit settings)


def test_all_jobs_lists(client, anonymous, interview, livekit, make_job):  # noqa: F811
    other = make_job(approve=True, title="Data Analyst", description="A made-up job.", required_skills=["SQL"])
    added = client.post(f"/api/jobs/{other['id']}/candidates/upload", files={"file": ("a.txt", cv("Alex Rivera", 2))},
                        data={"full_name": "Alex Rivera", "email": "alex@example.com"}).json()["candidate_id"]

    everyone = client.get("/api/candidates").json()
    mine = {c["id"]: c for c in everyone}
    assert mine[added]["job_title"] == "Data Analyst" and mine[interview["candidate_id"]]["job_title"]
    assert [c["id"] for c in everyone] == sorted(mine, reverse=True)              # newest first
    assert anonymous.get("/api/candidates").status_code == 401

    sessions = client.get("/api/sessions").json()                                 # without job_id: all jobs
    assert interview["id"] in [s["id"] for s in sessions] and all(s["job_title"] for s in sessions)
    assert [s["id"] for s in client.get(f"/api/sessions?job_id={other['id']}").json()] == []

    assess(client, ready(client, anonymous, interview))
    rows = client.get("/api/comparison").json()
    row = next(r for r in rows if r["candidate_id"] == interview["candidate_id"])
    assert row["job_id"] == interview["job_id"] and row["job_title"] and row["overall_score"] is not None
    titles = [r["job_title"].lower() for r in rows]
    assert titles == sorted(titles)                                                 # grouped by job
