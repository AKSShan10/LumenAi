"""The shortlist: included candidates the interviewer chose for the interview invitation (table shortlist_entry).
Only included candidates can be on it, and a candidate who is excluded later is taken off it. Made-up CVs only."""
import pytest
from sqlmodel import Session, select

from app.core.database import engine
from app.features.screening.models import ScreeningResult
from app.features.system.models import WorkflowRun

STORY = ("Worked in a product team, wrote automated tests, reviewed code and explained technical choices to "
         "colleagues. Planned releases with the product owner and kept the documentation up to date. ")


def cv(name: str, skills: str, years: int, degree: str) -> bytes:
    return (f"{name}\nMade-up CV used by the tests.\nSkills: {skills}\nExperience: {years} years as a backend developer.\n"
            f"{STORY}\nEducation: {degree}\n").encode()


@pytest.fixture
def job(make_job) -> dict:
    return make_job(approve=True, title="Backend Developer", description="A made-up job for the shortlist tests.",
                    required_skills=["Python", "FastAPI", "PostgreSQL"], min_years=3, qualifications="BSc in CSE or similar")


@pytest.fixture
def people(client, job) -> dict:
    """Two included candidates (Karima, Rahim) and one excluded (Alex: 2 years, 3 needed), screened."""
    ids = {}
    for name, years in (("Karima Akter", 5), ("Rahim Uddin", 4), ("Alex Mercer", 2)):
        data = cv(name, "Python, FastAPI, PostgreSQL", years, "BSc in CSE")
        ids[name] = client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": (f"{name}.txt", data)},
                                data={"full_name": name}).json()["candidate_id"]
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    finals = {r["full_name"]: r["final"] for r in client.get(f"/api/jobs/{job['id']}/screening").json()}
    assert finals == {"Karima Akter": "included", "Rahim Uddin": "included", "Alex Mercer": "excluded"}
    return ids


def add(client, job, ids, rule="top", value=2):
    return client.post(f"/api/jobs/{job['id']}/shortlist", json={"candidate_ids": ids, "rule": rule, "value": value})


def shortlist(client, job) -> list:
    return client.get(f"/api/jobs/{job['id']}/shortlist").json()


def log(candidate_id) -> list:
    with Session(engine) as session:
        return [r.outcome for r in session.exec(select(WorkflowRun).where(WorkflowRun.stage == "shortlist",
                                                                        WorkflowRun.subject_id == candidate_id)).all()]


def test_included_candidates_are_saved_with_the_rule(client, job, people):
    karima, rahim = people["Karima Akter"], people["Rahim Uddin"]
    answer = add(client, job, [karima, rahim])
    assert answer.status_code == 200
    assert answer.json()["added"] == 2 and "Top 2" in answer.json()["message"]

    rows = shortlist(client, job)
    assert {r["candidate_id"] for r in rows} == {karima, rahim}
    assert all(r["rule"] == "Top 2" and r["added_by"] == "interviewer@example.com" and r["added_at"] for r in rows)
    assert all(r["added_by_name"] == "Test Interviewer" for r in rows)       # the page shows the name
    assert log(karima) == ["added (Top 2)"]

    again = add(client, job, [karima, rahim]).json()                  # nobody is added twice
    assert (again["added"], again["already"]) == (0, 2)
    assert len(shortlist(client, job)) == 2

    rule = add(client, job, [karima], "min_score", 70).json()
    assert rule["added"] == 0                                         # still on it, with the first rule
    assert shortlist(client, job)[0]["rule"] == "Top 2"


def test_the_rule_names(client, job, people):
    add(client, job, [people["Karima Akter"]], "min_score", 72.5)
    add(client, job, [people["Rahim Uddin"]], "by_hand", None)
    rules = {r["full_name"]: r["rule"] for r in shortlist(client, job)}
    assert rules == {"Karima Akter": "Final score at least 72.5", "Rahim Uddin": "Added by hand"}


def test_only_included_candidates_of_this_job(client, job, people, make_job):
    answer = add(client, job, [people["Karima Akter"], people["Alex Mercer"]])
    assert answer.status_code == 400 and "Alex Mercer is not included" in answer.json()["detail"]
    assert shortlist(client, job) == []                               # nothing is added when one id is wrong

    other = make_job(approve=True, title="Data Analyst", description="Another made-up job.")
    wrong_job = add(client, other, [people["Karima Akter"]])
    assert wrong_job.status_code == 400 and "not a candidate of this job" in wrong_job.json()["detail"]
    assert add(client, job, [999999]).status_code == 400


def test_the_rule_value_is_checked(client, job, people):
    karima = people["Karima Akter"]
    for rule, value in (("top", 0), ("top", 2.5), ("top", None), ("min_score", 101), ("min_score", None), ("min_score", -1)):
        assert add(client, job, [karima], rule, value).status_code == 422, (rule, value)
    assert add(client, job, [], "top", 5).status_code == 422          # nobody chosen
    assert shortlist(client, job) == []


def test_remove_by_hand(client, job, people):
    rahim = people["Rahim Uddin"]
    add(client, job, [rahim], "by_hand", None)
    assert client.delete(f"/api/candidates/{rahim}/shortlist").status_code == 204
    assert shortlist(client, job) == []
    assert client.delete(f"/api/candidates/{rahim}/shortlist").status_code == 404
    assert log(rahim) == ["added (Added by hand)", "removed by a person"]


def test_excluded_later_is_taken_off(client, job, people):
    karima, alex = people["Karima Akter"], people["Alex Mercer"]
    add(client, job, [karima])
    client.put(f"/api/candidates/{karima}/decision", json={"decision": "excluded", "note": ""})
    assert shortlist(client, job) == []
    assert log(karima)[-1] == "removed (now excluded)"

    # an excluded candidate whom a person includes can be put on the shortlist; undoing that takes them off again
    client.put(f"/api/candidates/{alex}/decision", json={"decision": "included", "note": "close enough"})
    assert add(client, job, [alex], "by_hand", None).json()["added"] == 1
    client.put(f"/api/candidates/{alex}/decision", json={"decision": None, "note": ""})
    assert shortlist(client, job) == []


def test_screened_again_stays_while_still_included(client, job, people):
    rahim = people["Rahim Uddin"]
    add(client, job, [rahim])
    client.post(f"/api/candidates/{rahim}/screening")                  # screened again, still included
    assert [r["candidate_id"] for r in shortlist(client, job)] == [rahim]


def test_a_deleted_candidate_is_taken_off(client, job, people):
    karima = people["Karima Akter"]
    add(client, job, [karima])
    assert client.delete(f"/api/candidates/{karima}").status_code == 204
    assert shortlist(client, job) == []


def test_highest_final_score_first(client, job, people):
    karima, rahim = people["Karima Akter"], people["Rahim Uddin"]
    with Session(engine) as session:                                  # fixed scores, so the order is known
        for candidate_id, score in ((karima, 70.0), (rahim, 90.0)):
            row = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).one()
            row.weighted_score = score
            session.add(row)
        session.commit()
    add(client, job, [karima, rahim])
    assert [(r["full_name"], r["weighted_score"]) for r in shortlist(client, job)] == [("Rahim Uddin", 90.0),
                                                                                       ("Karima Akter", 70.0)]


def test_login_is_needed(anonymous, job):
    assert anonymous.get(f"/api/jobs/{job['id']}/shortlist").status_code == 401
    assert anonymous.post(f"/api/jobs/{job['id']}/shortlist", json={"candidate_ids": [1], "rule": "by_hand"}).status_code == 401
    assert anonymous.delete("/api/candidates/1/shortlist").status_code == 401
