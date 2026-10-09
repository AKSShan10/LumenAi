"""Human control: the interviewer includes or excludes a candidate. It goes through the LangGraph workflow:
the run pauses in hr_review (interrupt + checkpointer) and the decision continues it (apply_decision).
The system result is always kept next to the person's decision. Made-up CVs only."""
import pytest
from sqlmodel import Session, select

from app.core import config
from app.core.database import engine
from app.features.screening.models import ScreeningResult
from app.features.screening.services import screening_worker
from app.features.system.models import WorkflowRun
from app.graphs.cv_screening_graph import runner

STORY = ("Worked in a product team, wrote automated tests, reviewed code and explained technical choices to "
         "colleagues. Planned releases with the product owner and kept the documentation up to date. ")


def cv(name: str, skills: str, years: int, degree: str) -> bytes:
    return (f"{name}\nMade-up CV used by the tests.\nSkills: {skills}\nExperience: {years} years as a backend developer.\n"
            f"{STORY}\nEducation: {degree}\n").encode()


@pytest.fixture
def job(make_job) -> dict:
    return make_job(approve=True, title="Backend Developer", description="A made-up job for the decision tests.",
                    required_skills=["Python", "FastAPI", "PostgreSQL"], min_years=3, qualifications="BSc in CSE or similar")


def upload(client, job, file_name, data, name) -> int:
    return client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": (file_name, data)},
                       data={"full_name": name}).json()["candidate_id"]


def row_of(client, job, name) -> dict:
    return next(r for r in client.get(f"/api/jobs/{job['id']}/screening").json() if r["full_name"] == name)


def decide(client, candidate_id, decision, note=""):
    return client.put(f"/api/candidates/{candidate_id}/decision", json={"decision": decision, "note": note})


def paused_at(candidate_id) -> tuple:
    with Session(engine) as session:
        thread = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).one().thread_id
    return runner().get_state({"configurable": {"thread_id": thread}}).next


def test_include_an_excluded_candidate_and_undo(client, job):
    alex = upload(client, job, "a.txt", cv("Alex Mercer", "Python, FastAPI, PostgreSQL", 2, "BSc in CSE"), "Alex Mercer")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    row = row_of(client, job, "Alex Mercer")
    assert (row["result"], row["final"], row["decision"]) == ("excluded", "excluded", "")       # 2 years, 3 needed
    assert paused_at(alex) == ("hr_review",)                                                   # the run waits for a person

    answer = decide(client, alex, "included", "Strong projects; 2.5 years is close enough.")
    assert answer.status_code == 200 and "now included" in answer.json()["message"]
    row = row_of(client, job, "Alex Mercer")
    assert (row["result"], row["final"], row["decision"]) == ("excluded", "included", "included")   # both are kept
    assert row["decision_note"] == "Strong projects; 2.5 years is close enough."
    assert row["decided_by"] == "interviewer@example.com" and row["decided_at"]
    assert paused_at(alex) == ("hr_review",)                                                   # waits again: can change

    undo = decide(client, alex, None).json()
    assert "undone" in undo["message"]
    row = row_of(client, job, "Alex Mercer")
    assert (row["final"], row["decision"], row["decision_note"], row["decided_by"]) == ("excluded", "", "", "")
    with Session(engine) as session:
        outcomes = [r.outcome for r in session.exec(select(WorkflowRun).where(WorkflowRun.stage == "hr_decision",
                                                                            WorkflowRun.subject_id == alex)).all()]
    assert outcomes == ["included", "undone"]


def test_the_note_is_optional_and_a_passed_one_can_be_excluded(client, job):
    karima = upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI, PostgreSQL", 4, "BSc in CSE"), "Karima Akter")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    assert decide(client, karima, "excluded").status_code == 200                              # no note
    row = row_of(client, job, "Karima Akter")
    assert (row["result"], row["final"], row["decision_note"]) == ("passed", "excluded", "")


def test_screening_again_lets_the_system_decide_again(client, job):
    alex = upload(client, job, "a.txt", cv("Alex Mercer", "Python, FastAPI, PostgreSQL", 2, "BSc in CSE"), "Alex Mercer")
    karima = upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI, PostgreSQL", 4, "BSc in CSE"), "Karima Akter")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    decide(client, alex, "included", "Kept by HR")
    decide(client, karima, "excluded")

    client.post(f"/api/candidates/{alex}/screening")                                          # one row again
    row = row_of(client, job, "Alex Mercer")
    assert (row["final"], row["decision"], row["decision_note"]) == ("excluded", "", "")        # the system decides
    assert row_of(client, job, "Karima Akter")["final"] == "excluded"                         # the others are untouched

    decide(client, alex, "included")                                                          # a person can change again
    assert row_of(client, job, "Alex Mercer")["final"] == "included" and paused_at(alex) == ("hr_review",)

    client.post(f"/api/jobs/{job['id']}/screening", json={"again": True})                    # every CV again
    assert row_of(client, job, "Alex Mercer")["final"] == "excluded"
    assert row_of(client, job, "Karima Akter")["final"] == "included"
    with Session(engine) as session:
        cleared = [r.outcome for r in session.exec(select(WorkflowRun).where(WorkflowRun.stage == "hr_decision")).all()
                   if r.outcome.startswith("cleared") and r.subject_id in (alex, karima)]
    assert len(cleared) == 3                                                                  # every cleared decision is logged


def test_a_decision_without_a_paused_run_still_goes_through_the_workflow(client, job):
    """For example a CV screened before this step existed, or a lost run: a short run goes straight to hr_review."""
    alex = upload(client, job, "a.txt", cv("Alex Mercer", "Python, FastAPI, PostgreSQL", 2, "BSc in CSE"), "Alex Mercer")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    with Session(engine) as session:
        result = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == alex)).one()
        result.thread_id = ""
        session.add(result)
        session.commit()
    assert decide(client, alex, "included").status_code == 200
    assert row_of(client, job, "Alex Mercer")["final"] == "included" and paused_at(alex) == ("hr_review",)


def test_the_candidate_list_shows_the_screening_state(client, job):
    upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI, PostgreSQL", 4, "BSc in CSE"), "Karima Akter")
    alex = upload(client, job, "a.txt", cv("Alex Mercer", "Python, FastAPI, PostgreSQL", 2, "BSc in CSE"), "Alex Mercer")
    nadia = upload(client, job, "n.txt", "নাদিয়া ইসলাম। পাইথন ডেভেলপার। ".encode() * 30, "Nadia Islam")
    states = lambda: {c["full_name"]: (c["screening_state"], c["decided"])                   # noqa: E731
                      for c in client.get(f"/api/jobs/{job['id']}/candidates").json()}
    assert set(states().values()) == {("waiting", False)}                                      # not screened yet
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    assert states() == {"Karima Akter": ("included", False), "Alex Mercer": ("excluded", False),
                        "Nadia Islam": ("needs_review", False)}
    decide(client, alex, "included")
    decide(client, nadia, "excluded", "Not in English")                                      # a person can decide here too
    assert states()["Alex Mercer"] == ("included", True) and states()["Nadia Islam"] == ("excluded", True)


def test_progress_while_screening(client, job, monkeypatch):
    """The page asks for the progress while the backend screens: running, total and done."""
    from app.graphs import cv_screening_graph
    seen = []
    real = cv_screening_graph.llm_json

    def watch(instructions, data):
        if instructions == cv_screening_graph.EXTRACT_PROFILE_PROMPT:
            seen.append(client.get(f"/api/jobs/{job['id']}/screening/status").json())
        return real(instructions, data)
    monkeypatch.setattr(cv_screening_graph, "llm_json", watch)
    for n in range(1, 4):
        upload(client, job, f"{n}.txt", cv(f"Person{n} Family{n}", "Python, FastAPI, PostgreSQL", 4, "BSc in CSE"),
               f"Person{n} Family{n}")
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    assert [(s["running"], s["done"], s["total"]) for s in seen] == [(True, 0, 3), (True, 1, 3), (True, 2, 3)]
    assert seen[1]["message"] == "Screening 1 of 3 CV(s)..."


def test_rules(client, anonymous, job, make_job):
    karima = upload(client, job, "k.txt", cv("Karima Akter", "Python", 4, "BSc in CSE"), "Karima Akter")
    assert decide(client, karima, "included").status_code == 400                             # not screened yet
    assert decide(client, karima, "maybe").status_code == 422
    assert decide(client, 999999, "included").status_code == 404
    assert anonymous.put(f"/api/candidates/{karima}/decision", json={"decision": "included"}).status_code == 401
    assert anonymous.get(f"/api/jobs/{job['id']}/screening/status").status_code == 401
    assert client.get("/api/jobs/999999/screening/status").status_code == 404


# ---------- the backend screens by itself ----------

def test_new_cvs_are_screened_in_the_background(client, job, monkeypatch):
    monkeypatch.setattr(config, "SCREENING_MODE", "background")
    upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI, PostgreSQL", 4, "BSc in CSE"), "Karima Akter")
    upload(client, job, "r.txt", cv("Rahim Uddin", "Python, FastAPI, MySQL", 4, "BSc in CSE"), "Rahim Uddin")
    screening_worker._jobs.join()                                                             # wait for the worker
    assert row_of(client, job, "Karima Akter")["final"] == "included"
    assert row_of(client, job, "Rahim Uddin")["final"] == "excluded"
    status = client.get(f"/api/jobs/{job['id']}/screening/status").json()
    assert (status["running"], status["done"], status["total"]) == (False, 2, 2)
    assert status["message"] == "Screening finished: 2 CV(s), 1 included, 1 excluded."

    answer = client.post(f"/api/jobs/{job['id']}/screening", json={"again": True}).json()
    assert answer["message"] == "Screening started for 2 CV(s)." and answer["left"] == 2
    screening_worker._jobs.join()
    assert all(not r["waiting"] for r in client.get(f"/api/jobs/{job['id']}/screening").json())
    assert client.get(f"/api/jobs/{job['id']}/screening/status").json()["done"] == 2


def test_the_free_quota_wait(client, job, monkeypatch):
    """"Too many requests": the worker waits and screens the same CV again."""
    from app.graphs import cv_screening_graph
    monkeypatch.setattr(config, "SCREENING_RATE_LIMIT_WAIT", 0)
    real, calls = cv_screening_graph.llm_json, []

    def busy_once(instructions, data):
        calls.append(1)
        if len(calls) == 1:
            return None                                                                       # the quota is busy once
        return real(instructions, data)
    monkeypatch.setattr(cv_screening_graph, "llm_json", busy_once)
    monkeypatch.setattr(cv_screening_graph, "last_error", lambda: "too many requests or the free quota is used up")
    monkeypatch.setattr(cv_screening_graph, "MAX_PROFILE_TRIES", 1)
    upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI, PostgreSQL", 4, "BSc in CSE"), "Karima Akter")
    assert screening_worker.screen_waiting(job["id"])["done"] == 1
    assert row_of(client, job, "Karima Akter")["final"] == "included"
