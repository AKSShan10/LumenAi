"""F4 candidate scoring: the AI scores three sections, Python checks the quotes and does the weighted maths.
Made-up CVs only."""
import pytest
from sqlmodel import Session

from app.core.database import engine
from app.features.screening.models import ScreeningResult
from app.features.screening.services.score_service import weighted_score
from app.graphs import cv_screening_graph

STORY = ("Worked in a product team, wrote automated tests, reviewed code and explained technical choices to "
         "colleagues. Planned releases with the product owner and kept the documentation up to date. ")


def cv(name: str, skills: str, years: int, degree: str, extra: str = "") -> bytes:
    return (f"{name}\nMade-up CV used by the tests.\nSkills: {skills}\nExperience: {years} years as a backend developer.\n"
            f"{STORY}\nEducation: {degree}\n{extra}").encode()


@pytest.fixture
def job(make_job) -> dict:
    return make_job(approve=True, title="Backend Developer", description="A made-up job for the scoring tests.",
                    required_skills=["Python", "FastAPI", "PostgreSQL", "Docker"], min_years=2,
                    qualifications="BSc in CSE or similar")


def upload(client, job, file_name, data, name):
    return client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": (file_name, data)},
                       data={"full_name": name}).json()["candidate_id"]


def rows(client, job) -> dict:
    return {row["full_name"]: row for row in client.get(f"/api/jobs/{job['id']}/screening").json()}


# ---------- the arithmetic (plain Python) ----------

def test_weighted_score():
    sections = {"skills": {"score": 80}, "experience": {"score": 60}, "qualifications": {"score": 100}}
    assert weighted_score(sections, {"skills": 50, "experience": 30, "qualifications": 20}) == 78.0   # 40 + 18 + 20
    assert weighted_score(sections, {"skills": 0, "experience": 0, "qualifications": 100}) == 100.0
    assert weighted_score({**sections, "skills": {"score": None}}, {"skills": 50, "experience": 30, "qualifications": 20}) is None
    assert weighted_score({}, {"skills": 50, "experience": 30, "qualifications": 20}) is None


# ---------- through the workflow ----------

def test_scores_breakdown_and_proof(client, job):
    upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI, PostgreSQL, Docker", 4, "BSc in CSE"), "Karima Akter")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    row = rows(client, job)["Karima Akter"]
    sections = row["sections"]
    assert sections["skills"]["score"] == 100 and sections["experience"]["score"] == 100      # fake AI: 4/4, 4 >= 2 years
    assert sections["qualifications"]["score"] == 85
    assert all(part["proof"] is True and part["quote"] for part in sections.values())        # quotes are really in the CV
    assert row["weighted_score"] == 97.0                                                      # 50 + 30 + 17 (default 50/30/20)


def test_an_invented_quote_is_removed(client, job):
    upload(client, job, "b.txt", cv("Bad Quote", "Python, FastAPI, PostgreSQL, Docker", 3, "BSc in CSE",
                                    extra="FAKE-BAD-QUOTE"), "Bad Quote")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    sections = rows(client, job)["Bad Quote"]["sections"]
    assert all(part["proof"] is False and part["quote"] == "" for part in sections.values())
    assert sections["skills"]["score"] == 100                                                 # the score stays; the proof is missing


def test_excluded_are_scored_needs_review_are_not(client, job):
    upload(client, job, "r.txt", cv("Rahim Uddin", "Python, FastAPI", 3, "BSc in CSE"), "Rahim Uddin")
    upload(client, job, "n.txt", "নাদিয়া ইসলাম। পাইথন ডেভেলপার। ".encode() * 30, "Nadia Islam")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    rahim, nadia = rows(client, job)["Rahim Uddin"], rows(client, job)["Nadia Islam"]
    assert rahim["result"] == "excluded" and rahim["sections"]["skills"]["score"] == 50 and rahim["weighted_score"]
    assert nadia["result"] == "needs_review" and nadia["sections"] == {} and nadia["weighted_score"] is None


def test_new_weights_recalculate_without_the_ai(client, job, monkeypatch):
    upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI", 1, "Diploma in Arts"), "Karima Akter")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    before = rows(client, job)["Karima Akter"]
    assert client.get(f"/api/jobs/{job['id']}/score-weights").json() == \
        {"skills": 50, "experience": 30, "qualifications": 20, "updated": 0}

    monkeypatch.setattr(cv_screening_graph, "llm_json", lambda *a: pytest.fail("no AI call when weights change"))
    answer = client.put(f"/api/jobs/{job['id']}/score-weights",
                        json={"skills": 100, "experience": 0, "qualifications": 0}).json()
    assert answer["updated"] == 1 and answer["skills"] == 100
    after = rows(client, job)["Karima Akter"]
    assert after["sections"] == before["sections"]                                            # the AI's scores are kept
    assert after["weighted_score"] == before["sections"]["skills"]["score"]                   # only skills count now


def test_weights_must_add_up_to_100(client, job, anonymous):
    for bad in ({"skills": 50, "experience": 30, "qualifications": 30}, {"skills": -10, "experience": 60, "qualifications": 50},
                {"skills": 50, "experience": 50}):
        assert client.put(f"/api/jobs/{job['id']}/score-weights", json=bad).status_code == 422
    assert client.put("/api/jobs/999999/score-weights",
                      json={"skills": 50, "experience": 30, "qualifications": 20}).status_code == 404
    assert anonymous.get(f"/api/jobs/{job['id']}/score-weights").status_code == 401


def test_when_the_ai_cannot_score(client, job, monkeypatch):
    real = cv_screening_graph.llm_json
    monkeypatch.setattr(cv_screening_graph, "llm_json",
                        lambda i, d: None if i == cv_screening_graph.SCORE_SECTIONS_PROMPT else real(i, d))
    candidate_id = upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI, PostgreSQL, Docker", 4, "BSc in CSE"),
                          "Karima Akter")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    row = rows(client, job)["Karima Akter"]
    assert row["result"] == "passed" and row["sections"] == {} and row["weighted_score"] is None   # no made-up score
    with Session(engine) as session:
        from sqlmodel import select
        assert session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).one()
