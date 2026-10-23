"""The Dashboard: counted by code from the saved data (no AI). Made-up data only."""
from tests.test_assessments import assess, ready
from tests.test_video_call import interview, livekit  # noqa: F401  (a scheduled interview and LiveKit settings)


def numbers(client, job_id: int) -> dict:
    answer = client.get(f"/api/dashboard?job_id={job_id}")
    assert answer.status_code == 200
    return answer.json()


def test_the_funnel_and_the_tiles_follow_the_candidate(client, anonymous, interview, livekit):  # noqa: F811
    job = interview["job_id"]
    before = numbers(client, job)                                  # screened, shortlisted, interview scheduled
    assert [(s["step"], s["count"]) for s in before["funnel"]] == [
        ("Applied", 1), ("Screened", 1), ("Shortlisted", 1), ("Interviewed", 0), ("Assessed", 0), ("Hired", 0)]
    assert before["tiles"]["interviews_upcoming"] == 1 and before["tiles"]["open_jobs"] == 1
    assert any(a["key"] == "invitation" for a in before["attention"])          # the invitation was not sent

    candidate = ready(client, anonymous, interview)                # the call ended and the answers were analysed
    waiting = numbers(client, job)
    assert next(a for a in waiting["attention"] if a["key"] == "assess")["count"] == 1

    report = assess(client, candidate)
    after = numbers(client, job)
    assert next(a for a in after["attention"] if a["key"] == "decide")["page"] == "reports"
    assert after["tiles"]["assessed"] == 1 and after["tiles"]["pending_decisions"] == 1
    assert after["scores"]["overall"] == report["overall_score"] and after["scores"]["cv"] == report["cv_score"]
    assert sum(b["count"] for b in after["scores"]["bands"]) == 1

    client.put(f"/api/candidates/{candidate}/assessment/decision", json={"decision": "hire"})
    hired = numbers(client, job)
    assert hired["funnel"][-1] == {"step": "Hired", "count": 1, "percent": 100}
    assert all(a["key"] != "decide" for a in hired["attention"])
    row = next(r for r in hired["jobs"] if r["job_id"] == job)
    assert (row["applied"], row["interviewed"], row["assessed"], row["hire"]) == (1, 1, 1, 1)
    assert row["avg_overall"] == report["overall_score"]


def test_ai_health_and_access(client, anonymous, interview, livekit):  # noqa: F811
    ready(client, anonymous, interview)
    health = client.get("/api/dashboard").json()["workflows"]       # all jobs
    stages = {s["stage"]: s for s in health["stages"]}
    assert stages["interview_analysis"]["runs"] >= 1 and health["model"] and health["days"] == 7
    assert all(0 <= s["failure_rate"] <= 100 for s in health["stages"])
    assert anonymous.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard?job_id=999999").status_code == 404
