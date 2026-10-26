"""CV screening: the AI reads each CV, plain code checks the requirements and decides. Made-up CVs only."""
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.core.database import engine
from app.features.screening.models import ScreeningResult
from app.features.system.models import WorkflowRun
from app.graphs import cv_screening_graph
from app.utils.skill_names import find_skill, skill_key

SAMPLES = Path(__file__).parent / "sample_cvs"
STORY = ("Worked in a product team, wrote automated tests, reviewed code and explained technical choices to "
         "colleagues. Planned releases with the product owner and kept the documentation up to date. ")


def cv(name: str, skills: str, years: int, degree: str, extra: str = "") -> bytes:
    return (f"{name}\nMade-up CV used by the tests.\nEmail: {name.split()[0].lower()}@example.com  Phone: 01700000009\n"
            f"Skills: {skills}\nExperience: {years} years as a backend developer.\n{STORY}\n"
            f"Education: {degree}\n{extra}").encode()


@pytest.fixture
def job(make_job) -> dict:
    return make_job(approve=True, title="Backend Developer", description="A made-up job for the screening tests.",
                    required_skills=["Python", "FastAPI", "PostgreSQL"], preferred_skills=["Docker"],
                    min_years=2, qualifications="BSc in CSE or similar")


def upload(client, job, file_name, data, name):
    answer = client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": (file_name, data)},
                         data={"full_name": name}).json()
    assert answer["ok"] is True
    return answer["candidate_id"]


def screen(client, job, **body):
    return client.post(f"/api/jobs/{job['id']}/screening", json=body).json()


def results(client, job) -> dict:
    return {row["full_name"]: row for row in client.get(f"/api/jobs/{job['id']}/screening").json()}


# ---------- skill names (plain Python) ----------

def test_skill_names():
    assert skill_key("Postgres") == skill_key("PostgreSQL") == "postgresql"
    assert find_skill("PostgreSQL", ["Postgres"], "") == "listed in the CV's skills"
    assert find_skill("JavaScript", [], "Built shops with JS and React") == ""          # "js" is too short to search
    assert find_skill("Node.js", [], "APIs in NodeJS and Express").startswith("the CV mentions")
    assert find_skill("Java", [], "Five years of JavaScript") == ""                      # not part of another word
    assert find_skill("Go", ["Python"], "we go to the office") == ""


# ---------- the decision ----------

def test_passed_excluded_and_needs_review(client, job):
    upload(client, job, "karima.txt", cv("Karima Akter", "Python, FastAPI, Postgres, Docker", 4,
                                         "BSc in Computer Science and Engineering"), "Karima Akter")
    upload(client, job, "rahim.txt", cv("Rahim Uddin", "Python, FastAPI, MongoDB", 3, "BSc in CSE"), "Rahim Uddin")
    upload(client, job, "tanvir.txt", cv("Tanvir Hasan", "Python, FastAPI, PostgreSQL", 1,
                                         "BSc in Computer Science"), "Tanvir Hasan")
    upload(client, job, "nadia.txt", "নাদিয়া ইসলাম। পাইথন ডেভেলপার, চার বছরের অভিজ্ঞতা। ".encode() * 20, "Nadia Islam")

    answer = screen(client, job)
    assert answer["ok"] is True and answer["screened"] == 4 and "4 CV(s), 1 included, 2 excluded, 1 need(s) a look" in answer["message"]
    rows = results(client, job)

    karima = rows["Karima Akter"]
    assert karima["result"] == "passed" and (karima["must_met"], karima["must_total"]) == (5, 5)
    assert (karima["nice_met"], karima["nice_total"]) == (1, 1) and karima["total_years"] == 4
    postgres = next(m for m in karima["matches"] if m["requirement"] == "PostgreSQL")
    assert postgres["met"] is True and "postgres" in postgres["how"]                    # another name, still met

    assert rows["Rahim Uddin"]["result"] == "excluded" and rows["Rahim Uddin"]["reason"] == "Missing must-have: PostgreSQL."
    assert rows["Tanvir Hasan"]["result"] == "excluded" and "2+ years of experience" in rows["Tanvir Hasan"]["reason"]
    assert rows["Nadia Islam"]["result"] == "needs_review" and "not written in English" in rows["Nadia Islam"]["reason"]
    assert rows["Nadia Islam"]["matches"] == []                                          # stopped before the AI

    assert screen(client, job)["message"] == "Every CV of this job is screened already."


def test_a_wrong_qualification_excludes(client, job):
    upload(client, job, "a.txt", cv("Arif Hossain", "Python, FastAPI, PostgreSQL", 5, "Diploma in Fine Arts"), "Arif Hossain")
    screen(client, job)
    row = results(client, job)["Arif Hossain"]
    assert row["result"] == "excluded" and "BSc in CSE or similar" in row["reason"]


def test_a_cv_with_a_reading_problem_is_never_excluded(client, job):
    """A short or unreadable CV goes to a person, without asking the AI."""
    from docx import Document
    import io
    document, data = Document(), io.BytesIO()
    document.add_paragraph("Sumon Das, made-up CV, all details are in a picture")
    document.save(data)
    upload(client, job, "sumon.docx", data.getvalue(), "Sumon Das")
    screen(client, job)
    row = results(client, job)["Sumon Das"]
    assert row["result"] == "needs_review" and "may be incomplete" in row["reason"] and row["matches"] == []


def test_a_scanned_pdf_is_read_by_the_ai_once(client, job, monkeypatch):
    """parse_cv finds no text -> validate_extraction -> ocr_once (AI vision) -> validate_extraction -> extract_profile."""
    calls = []
    real = cv_screening_graph.llm_read_pdf
    monkeypatch.setattr(cv_screening_graph, "llm_read_pdf", lambda i, pdf: calls.append(1) or real(i, pdf))
    upload(client, job, "scan.pdf", SAMPLES.joinpath("scanned_blank.pdf").read_bytes(), "Tanvir Hasan")
    screen(client, job)
    row = results(client, job)["Tanvir Hasan"]
    assert row["result"] == "passed" and len(calls) == 1
    candidate = client.get(f"/api/jobs/{job['id']}/candidates").json()[0]
    assert candidate["text_source"] == "ai_read" and candidate["warnings"] == []          # shown from the screening
    with Session(engine) as session:
        from app.features.candidates.models import Candidate
        stored = session.get(Candidate, candidate["id"])
        assert stored.text_source == "" and stored.cv_text == ""                         # the candidate table is unchanged
        screening = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == stored.id)).one()
        assert screening.text_source == "ai_read" and "Tanvir Hasan" in screening.cv_text


def test_when_the_ai_cannot_read_the_scan_a_person_looks(client, job, monkeypatch):
    calls = []
    monkeypatch.setattr(cv_screening_graph, "llm_read_pdf", lambda i, pdf: calls.append(1) or None)
    upload(client, job, "scan.pdf", SAMPLES.joinpath("scanned_blank.pdf").read_bytes(), "Tanvir Hasan")
    screen(client, job)
    row = results(client, job)["Tanvir Hasan"]
    assert row["result"] == "needs_review" and "AI could not read the file either" in row["reason"]
    assert len(calls) == 1                                                               # only once, no endless loop


def test_a_candidate_without_a_file_needs_a_person(client, job):
    candidate_id = upload(client, job, "k.txt", cv("Karima Akter", "Python", 4, "BSc in CSE"), "Karima Akter")
    with Session(engine) as session:
        from app.features.candidates.models import Candidate
        from app.features.candidates.services.cv_storage_service import cv_file
        cv_file(session.get(Candidate, candidate_id)).unlink()                           # the file is gone from the disk
    screen(client, job)
    assert results(client, job)["Karima Akter"]["reason"].endswith("No CV file is saved for this candidate.")


def test_a_bad_ai_answer_is_tried_once_more(client, job, monkeypatch):
    asked = []
    real = cv_screening_graph.llm_json

    def counting(instructions, data):
        asked.append(instructions)
        return real(instructions, data)
    monkeypatch.setattr(cv_screening_graph, "llm_json", counting)
    upload(client, job, "bad.txt", cv("Bad Answer", "Python", 3, "BSc in CSE", extra="FAKE-BAD-ANSWER"), "Bad Answer")
    screen(client, job)
    row = results(client, job)["Bad Answer"]
    assert row["result"] == "needs_review" and "could not read the CV into a profile" in row["reason"]
    assert asked.count(cv_screening_graph.EXTRACT_PROFILE_PROMPT) == 2                          # asked twice, then a person


def test_the_ai_never_sees_email_or_phone(client, job, monkeypatch):
    sent = []
    real = cv_screening_graph.llm_json
    monkeypatch.setattr(cv_screening_graph, "llm_json", lambda i, d: sent.append(str(d)) or real(i, d))
    upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI, PostgreSQL", 4, "BSc in CSE"), "Karima Akter")
    screen(client, job)
    assert sent and all("@example.com" not in text and "01700000009" not in text for text in sent)
    assert "[email]" in sent[0] and "[phone]" in sent[0] and "4 years" in sent[0]


# ---------- clicks, limits and other jobs ----------

def test_all_cvs_at_once_and_screen_all_again(client, job, make_job):
    other = make_job(approve=True, title="Other Job", description="Another made-up job.", required_skills=["Java"])
    upload(client, other, "o.txt", cv("Other Person", "Java", 3, "BSc in CSE"), "Other Person")
    for n in range(1, 8):                                                                # more than the old limit of 5
        upload(client, job, f"{n}.txt", cv(f"Person{n} Family{n}", "Python, FastAPI, PostgreSQL", 3, "BSc in CSE"),
               f"Person{n} Family{n}")
    first = screen(client, job)
    assert first["screened"] == 7 and first["left"] == 0
    assert all(row["result"] is None for row in results(client, other).values())         # the other job is untouched

    again = screen(client, job, again=True)                                              # every CV of this job again
    assert again["screened"] == 7


def test_one_candidate_again_and_cleaning_up(client, job):
    candidate_id = upload(client, job, "k.txt", cv("Karima Akter", "Python, FastAPI, PostgreSQL", 4, "BSc in CSE"),
                          "Karima Akter")
    screen(client, job)
    answer = client.post(f"/api/candidates/{candidate_id}/screening").json()
    assert answer["ok"] is True and "included" in answer["message"]
    with Session(engine) as session:
        assert len(session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).all()) == 1
        runs = session.exec(select(WorkflowRun).where(WorkflowRun.stage == "cv_screening",
                                                      WorkflowRun.subject_id == candidate_id)).all()
        assert [run.outcome for run in runs] == ["passed", "passed"]                    # every run is logged

    client.delete(f"/api/candidates/{candidate_id}")                                     # the result goes with the candidate
    with Session(engine) as session:
        assert session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).first() is None


def test_rules(client, anonymous, make_job):
    draft = make_job(title="Draft Screening Tester")
    assert client.post(f"/api/jobs/{draft['id']}/screening", json={}).status_code == 400
    assert client.post("/api/jobs/999999/screening", json={}).status_code == 404
    assert client.post("/api/candidates/999999/screening").status_code == 404
    for call in (anonymous.post("/api/jobs/1/screening", json={}), anonymous.get("/api/jobs/1/screening"),
                 anonymous.post("/api/candidates/1/screening")):
        assert call.status_code == 401


# ---------- the free Gemini quota: one AI call per CV, and the tokens are logged ----------

def test_two_ai_calls_per_cv(client, job, monkeypatch, caplog):
    """The profile and the qualification come from the same call (job has a qualification); the scores are the second."""
    asked = []
    real = cv_screening_graph.llm_json
    monkeypatch.setattr(cv_screening_graph, "llm_json", lambda i, d: asked.append(i) or real(i, d))
    for n in range(1, 4):
        upload(client, job, f"{n}.txt", cv(f"Person{n} Family{n}", "Python, FastAPI, PostgreSQL", 3, "BSc in CSE"),
               f"Person{n} Family{n}")
    with caplog.at_level("INFO", logger="cv_screening_graph"):
        screen(client, job)
    assert len(asked) == 6                                                                # 3 CVs, 2 calls each
    assert asked.count(cv_screening_graph.EXTRACT_PROFILE_PROMPT) == 3 == asked.count(cv_screening_graph.SCORE_SECTIONS_PROMPT)
    assert all(row["result"] == "passed" for row in results(client, job).values())
    assert caplog.text.count("ai_calls=2") == 3


def test_token_counts_for_the_log():
    from types import SimpleNamespace
    from app.ai.llm_client import _tokens
    usage = SimpleNamespace(prompt_tokens=1430, completion_tokens=310,
                            completion_tokens_details=SimpleNamespace(reasoning_tokens=120))
    assert _tokens(usage) == "tokens in=1430 out=310 thinking=120"
    assert _tokens(SimpleNamespace(prompt_tokens=10, completion_tokens=5, completion_tokens_details=None)) == \
        "tokens in=10 out=5 thinking=0"
    # Gemini: no reasoning_tokens, but total_tokens includes the thinking
    assert _tokens(SimpleNamespace(prompt_tokens=1430, completion_tokens=310, total_tokens=2240,
                                   completion_tokens_details=None)) == "tokens in=1430 out=310 thinking=500"
    assert _tokens(SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15,
                                   completion_tokens_details=None)) == "tokens in=10 out=5 thinking=0"
    assert _tokens(None) == "tokens in=? out=?"


# ---------- Met / Partially met / Unmet (semantic matching) ----------

def test_met_partially_met_and_unmet(client, job):
    """MySQL is close to PostgreSQL (partially met, with the CV's words as evidence); 1.5 of 2 years is partly met;
    a partially met must-have is not missing, so the candidate is included and the reason names it."""
    upload(client, job, "s.txt", cv("Sadia Rahman", "Python, FastAPI, MySQL", 1.5, "BSc in CSE"), "Sadia Rahman")
    screen(client, job)
    row = results(client, job)["Sadia Rahman"]
    by_name = {m["requirement"]: m for m in row["matches"]}
    assert by_name["Python"]["status"] == "met" and "python" in by_name["Python"]["how"].lower()   # the AI's reason
    assert by_name["Python"]["evidence"] and by_name["Python"]["verified"] is True
    assert by_name["PostgreSQL"]["status"] == "partial" and "MySQL" in by_name["PostgreSQL"]["evidence"]
    assert by_name["2+ years of experience"]["status"] == "partial"
    assert by_name["Docker"]["status"] == "unmet"                                         # nice to have: no harm
    assert row["result"] == "passed" and "Partially met: PostgreSQL; 2+ years of experience" in row["reason"]


def test_meaning_counts_and_invented_evidence_does_not(client, make_job, monkeypatch):
    qa = make_job(approve=True, title="QA Engineer", description="A made-up QA job with test automation in Python.",
                  required_skills=["Test planning", "Python or JavaScript"], min_years=0)
    upload(client, qa, "q.txt", cv("Nusrat Jahan", "Python", 3, "BSc in CSE",
                                   extra="Designed test plans for web and mobile releases."), "Nusrat Jahan")
    client.post(f"/api/jobs/{qa['id']}/screening", json={})
    row = {r["full_name"]: r for r in client.get(f"/api/jobs/{qa['id']}/screening").json()}["Nusrat Jahan"]
    by_name = {m["requirement"]: m for m in row["matches"]}
    assert by_name["Python or JavaScript"]["status"] == "met"                            # either one is enough
    assert by_name["Test planning"]["status"] == "met" and by_name["Test planning"]["evidence"]   # words from the CV
    assert by_name["Test planning"]["how"] and by_name["Test planning"]["verified"] is True   # the AI's reason
    assert row["result"] == "passed"

    real = cv_screening_graph.llm_json                                                    # the AI claims words not in the CV

    def invented(instructions, data):
        answer = real(instructions, data)
        if instructions == cv_screening_graph.EXTRACT_PROFILE_PROMPT:
            for check in answer["requirement_checks"]:
                check.update(status="met", evidence="Words that are not in the CV")
        return answer
    monkeypatch.setattr(cv_screening_graph, "llm_json", invented)
    upload(client, qa, "x.txt", cv("Imran Ali", "Ruby", 3, "BSc in CSE"), "Imran Ali")
    client.post(f"/api/jobs/{qa['id']}/screening", json={})
    row = {r["full_name"]: r for r in client.get(f"/api/jobs/{qa['id']}/screening").json()}["Imran Ali"]
    planning = {m["requirement"]: m for m in row["matches"]}["Test planning"]
    assert planning["status"] == "met" and planning["verified"] is False   # the AI is trusted; the quote is marked
    assert row["result"] == "passed"


def test_the_ai_decides_met_not_the_code(client, make_job, monkeypatch):
    """The semantic matching is the AI's: even a skill named in the CV is Unmet if the AI says so
    (for example "Interested in learning Kubernetes"). A must-have the AI did not judge goes to a person."""
    devops = make_job(approve=True, title="DevOps Engineer", description="A made-up DevOps job.",
                      required_skills=["Kubernetes", "Docker"], min_years=0)
    real = cv_screening_graph.llm_json

    def judged(instructions, data):
        answer = real(instructions, data)
        if instructions == cv_screening_graph.EXTRACT_PROFILE_PROMPT:
            answer["requirement_checks"] = [{"requirement": "Kubernetes", "status": "unmet",
                                             "reason": "The CV only says the person wants to learn it.", "evidence": ""}]
        return answer
    monkeypatch.setattr(cv_screening_graph, "llm_json", judged)
    upload(client, devops, "k.txt", cv("Nadia Karim", "Docker", 3, "BSc in CSE",
                                       extra="Interested in learning Kubernetes."), "Nadia Karim")
    client.post(f"/api/jobs/{devops['id']}/screening", json={})
    row = {r["full_name"]: r for r in client.get(f"/api/jobs/{devops['id']}/screening").json()}["Nadia Karim"]
    by_name = {m["requirement"]: m for m in row["matches"]}
    assert by_name["Kubernetes"]["status"] == "unmet" and "wants to learn" in by_name["Kubernetes"]["how"]
    assert by_name["Docker"]["status"] == "unchecked"                  # the AI left Docker out
    assert row["result"] == "excluded" and row["reason"] == "Missing must-have: Kubernetes."


# ---------- ATS match score ----------

def test_ats_match_score(client, make_job, monkeypatch):
    qa = make_job(approve=True, title="Backend Developer", description="We build APIs with Python, FastAPI, Docker and Redis.",
                  required_skills=["Python", "FastAPI"], preferred_skills=["Docker"], min_years=0)
    asked = []
    real = cv_screening_graph.llm_json
    from app.features.screening.services import screening_service
    monkeypatch.setattr(screening_service, "llm_json", lambda i, d: asked.append(i) or real(i, d))
    for n, skills in ((1, "Python, FastAPI, Docker, Redis"), (2, "Python, FastAPI")):
        upload(client, qa, f"{n}.txt", cv(f"Person{n} Family{n}", skills, 3, "BSc in CSE"), f"Person{n} Family{n}")
    client.post(f"/api/jobs/{qa['id']}/screening", json={})
    rows = {r["full_name"]: r for r in client.get(f"/api/jobs/{qa['id']}/screening").json()}
    assert rows["Person1 Family1"]["ats_score"] == 100 and rows["Person1 Family1"]["ats"]["total"] == 4
    assert rows["Person2 Family2"]["ats_score"] == 50 and rows["Person2 Family2"]["ats"]["missing"] == ["Docker", "Redis"]
    assert asked.count(screening_service.ATS_KEYWORDS_PROMPT) == 1                       # once per job, then saved
    client.post(f"/api/jobs/{qa['id']}/screening", json={"again": True})
    assert asked.count(screening_service.ATS_KEYWORDS_PROMPT) == 1                       # the same list: reproducible
