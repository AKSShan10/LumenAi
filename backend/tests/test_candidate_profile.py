"""The candidate's profile in the interviewer's call tab. Made-up data only."""
from tests.test_video_call import interview  # noqa: F401  (the same scheduled interview)


def test_the_interviewer_sees_the_profile_and_screening(client, interview):  # noqa: F811
    answer = client.get(f"/api/sessions/{interview['id']}/profile")
    assert answer.status_code == 200
    profile = answer.json()
    assert profile["candidate"]["full_name"] == "Karima Akter" and profile["candidate"]["email"] == "karima@example.com"
    assert profile["job_title"] == "Backend Developer"
    assert set(profile["weights"]) == {"skills", "experience", "qualifications"}
    screening = profile["screening"]
    assert screening["final"] == "included"
    assert "Python" in screening["skills"] and screening["total_years"] == 5
    assert {m["requirement"] for m in screening["matches"]} >= {"Python", "FastAPI", "PostgreSQL"}
    assert profile["degrees"] and profile["degrees"][0]["degree"].startswith("Education: BSc")   # for "Key highlights"
    assert profile["jobs"] == []                                     # the made-up CV names no "Job: ... at ..." line


def test_jobs_from_the_cv(client, make_job, monkeypatch):
    from app.core import config
    from tests.test_video_call import later
    monkeypatch.setattr(config, "SMTP_HOST", "")
    job = make_job(approve=True, title="Backend Developer", description="A made-up job.", required_skills=["Python"])
    text = ("Rafi Islam\nMade-up CV.\nSkills: Python\nExperience: 4 years as a developer.\n"
            "Job: Senior Software Engineer at Made Up Ltd\nJob: Software Engineer at Example Tech\n"
            "Education: BSc in CSE\n" + "Wrote and tested web services with a small team every day. " * 6).encode()
    cid = client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": ("r.txt", text)},
                      data={"full_name": "Rafi Islam", "email": "rafi@example.com"}).json()["candidate_id"]
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    client.post(f"/api/jobs/{job['id']}/shortlist", json={"candidate_ids": [cid], "rule": "by_hand"})
    session = client.post("/api/sessions", json={"candidate_id": cid, "scheduled_at": later(), "duration_minutes": 45,
                                                 "time_zone": "UTC"}).json()
    jobs = client.get(f"/api/sessions/{session['id']}/profile").json()["jobs"]
    assert jobs == [{"title": "Senior Software Engineer", "company": "Made Up Ltd", "years": 0},
                    {"title": "Software Engineer", "company": "Example Tech", "years": 0}]


def test_only_the_interviewer_and_only_real_interviews(client, anonymous, interview):  # noqa: F811
    assert anonymous.get(f"/api/sessions/{interview['id']}/profile").status_code == 401   # not the candidate
    assert client.get("/api/sessions/99999/profile").status_code == 404
    token = interview["token"]                                                          # the join link gives nothing
    assert anonymous.get(f"/api/join/{token}/profile").status_code in (404, 405)
    info = anonymous.get(f"/api/join/{token}").json()
    assert not {"screening", "weights", "email", "matches"} & set(info)
