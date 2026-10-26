"""Talent pool (innovation feature): keep good past candidates, find who fits a new job, invite them by email.
Code decides who fits; the AI only drafts the email; a person sends it. Made-up data only."""
from datetime import timedelta

import pytest
from sqlmodel import Session

from app.ai.fake_llm import fake_answer
from app.core.database import engine
from app.features.jobs.models import Job
from app.features.talent_pool.models import TalentPoolEntry
from app.features.talent_pool.services import invite_service
from app.graphs import talent_invite_graph
from app.graphs.talent_invite_prompts import TALENT_INVITE_PROMPT
from app.utils.datetime_utils import utc_now
from tests.test_interviews import cv
from tests.test_video_call import interview, livekit  # noqa: F401


def upload(client, job_id: int, name: str, email: str) -> int:
    return client.post(f"/api/jobs/{job_id}/candidates/upload", files={"file": (f"{name}.txt", cv(name, 5))},
                       data={"full_name": name, "email": email}).json()["candidate_id"]


@pytest.fixture
def pool(client, make_job, monkeypatch) -> dict:
    """Karima applied to an old job and was kept in the pool; a new job needs Python, Docker and PostgreSQL."""
    sent = []
    monkeypatch.setattr(invite_service, "send_email", lambda to, subject, body: sent.append((to, subject, body))
                        or {"ok": True, "error": ""})
    old = make_job(approve=True, title="Backend Developer", description="A made-up job.", required_skills=["Python"])
    new = make_job(approve=True, title="Platform Engineer", description="A made-up new job.",
                   required_skills=["Python", "Docker"], preferred_skills=["PostgreSQL"])
    with Session(engine) as session:                    # the "Apply now" form of the new job's post
        job = session.get(Job, new["id"])
        job.google_form_link = "https://forms.gle/made-up"
        session.add(job)
        session.commit()
    candidate = upload(client, old["id"], "Karima Akter", "karima.pool@example.com")
    added = client.put(f"/api/candidates/{candidate}/talent-pool", json={"status": "strong", "note": "Good SQL."})
    assert added.status_code == 200 and added.json()["in_pool"] is True
    return {"old": old, "new": new, "candidate": candidate, "sent": sent}


def entry_of(candidate_id: int) -> TalentPoolEntry:
    from sqlmodel import select
    with Session(engine) as session:
        return session.exec(select(TalentPoolEntry).where(TalentPoolEntry.candidate_id == candidate_id)).one()


def test_the_interviewer_keeps_and_removes_a_candidate(client, anonymous, pool):
    candidate = pool["candidate"]
    shown = client.get(f"/api/candidates/{candidate}/talent-pool").json()
    assert shown["status"] == "strong" and shown["note"] == "Good SQL." and shown["keep_until"]
    client.put(f"/api/candidates/{candidate}/talent-pool", json={"status": "other_role", "note": ""})
    row = next(r for r in client.get("/api/talent-pool").json() if r["candidate_id"] == candidate)
    assert row["status"] == "other_role" and row["state"] == "active" and row["from_job"] == "Backend Developer"

    assert client.put(f"/api/candidates/{candidate}/talent-pool", json={"status": "best"}).status_code == 422
    assert anonymous.get("/api/talent-pool").status_code == 401
    assert client.get("/api/candidates/999999/talent-pool").status_code == 404
    assert client.delete(f"/api/candidates/{candidate}/talent-pool").json()["in_pool"] is False
    assert candidate not in [r["candidate_id"] for r in client.get("/api/talent-pool").json()]


def test_code_finds_who_fits_a_new_job(client, pool):
    rows = client.get(f"/api/jobs/{pool['new']['id']}/talent-matches").json()["rows"]
    karima = next(r for r in rows if r["candidate_id"] == pool["candidate"])
    assert karima["matched"] == ["Python", "PostgreSQL"] and karima["missing"] == ["Docker"]   # shown in her CV
    assert karima["match"] == 60 and karima["from_job"] == "Backend Developer"      # (2 + 1) / (2 + 2 + 1)
    old_job = client.get(f"/api/jobs/{pool['old']['id']}/talent-matches").json()["rows"]
    assert pool["candidate"] not in [r["candidate_id"] for r in old_job]                         # not her own job


def test_the_ai_drafts_and_a_person_sends(client, pool):
    job, karima = pool["new"]["id"], pool["candidate"]
    pool_id = entry_of(karima).id
    drafts = client.post(f"/api/jobs/{job}/talent-invites/draft", json={"pool_ids": [pool_id]}).json()
    assert drafts[0]["email"] == "karima.pool@example.com" and "Platform Engineer" in drafts[0]["subject"]
    assert pool["sent"] == []                                                    # nothing is sent by the draft

    drafts[0]["body"] = "Dear Karima, a new role. Edited by the interviewer."
    drafts[0]["subject"] = "A new role for you"                               # the interviewer removed the job title
    drafts[0]["email"] = "someone.else@example.com"                              # the page cannot change the address
    result = client.post(f"/api/jobs/{job}/talent-invites/send", json={"invites": drafts}).json()
    assert result[0]["ok"] is True
    to, subject, body = pool["sent"][0]
    assert to == "karima.pool@example.com" and body.startswith("Dear Karima, a new role. Edited")
    assert "Platform Engineer" in subject
    assert "https://forms.gle/made-up" in body and f"/unsubscribe/{entry_of(karima).unsubscribe_token}" in body

    row = next(r for r in client.get("/api/talent-pool").json() if r["candidate_id"] == karima)
    assert row["invites"][0]["job_title"] == "Platform Engineer" and row["invites"][0]["applied"] is False
    upload(client, job, "Karima Akter", "karima.pool@example.com")                # she applies again
    row = next(r for r in client.get("/api/talent-pool").json() if r["candidate_id"] == karima)
    assert row["invites"][0]["applied"] is True
    assert karima not in [r["candidate_id"] for r in client.get(f"/api/jobs/{job}/talent-matches").json()["rows"]]


def test_unsubscribed_people_are_never_invited_again(client, anonymous, pool):
    job, karima = pool["new"]["id"], pool["candidate"]
    entry = entry_of(karima)
    page = anonymous.get(f"/api/unsubscribe/{entry.unsubscribe_token}").json()
    assert page == {"first_name": "Karima", "unsubscribed": False}             # opening the link changes nothing
    assert anonymous.post(f"/api/unsubscribe/{entry.unsubscribe_token}").json()["unsubscribed"] is True
    assert anonymous.get("/api/unsubscribe/not-a-real-token-at-all-123").status_code == 404

    assert karima not in [r["candidate_id"] for r in client.get(f"/api/jobs/{job}/talent-matches").json()["rows"]]
    invite = {"pool_id": entry.id, "name": "Karima Akter", "email": "x@example.com", "subject": "Hi", "body": "Hi"}
    result = client.post(f"/api/jobs/{job}/talent-invites/send", json={"invites": [invite]}).json()
    assert result[0]["ok"] is False and "unsubscribed" in result[0]["error"] and pool["sent"] == []
    again = client.put(f"/api/candidates/{karima}/talent-pool", json={"status": "strong"})
    assert again.status_code == 409 and "not to be contacted" in again.json()["detail"]


def test_the_interviewer_can_add_back_someone_who_unsubscribed(client, anonymous, pool):
    job, karima = pool["new"]["id"], pool["candidate"]
    old_token = entry_of(karima).unsubscribe_token
    anonymous.post(f"/api/unsubscribe/{old_token}")
    back = client.put(f"/api/candidates/{karima}/talent-pool", json={"status": "strong", "add_back": True}).json()
    assert back["in_pool"] is True and back["unsubscribed"] is False            # confirmed by the interviewer
    assert entry_of(karima).unsubscribe_token != old_token                       # a new link; the old one is gone
    assert anonymous.get(f"/api/unsubscribe/{old_token}").status_code == 404
    assert karima in [r["candidate_id"] for r in client.get(f"/api/jobs/{job}/talent-matches").json()["rows"]]


def test_expired_entries_are_not_suggested(client, pool):
    with Session(engine) as session:
        entry = session.get(TalentPoolEntry, entry_of(pool["candidate"]).id)
        entry.keep_until = utc_now() - timedelta(days=1)
        session.add(entry)
        session.commit()
    assert pool["candidate"] not in [r["candidate_id"] for r in client.get(f"/api/jobs/{pool['new']['id']}/talent-matches").json()["rows"]]
    row = next(r for r in client.get("/api/talent-pool").json() if r["candidate_id"] == pool["candidate"])
    assert row["state"] == "expired"


def test_deleting_the_candidate_deletes_the_pool_entry(client, pool):
    assert client.delete(f"/api/candidates/{pool['candidate']}").status_code == 204
    assert pool["candidate"] not in [r["candidate_id"] for r in client.get("/api/talent-pool").json()]


def test_the_invitation_prompt_is_fair():
    for rule in ("Never mention scores", "never age, gender", "Do not promise a job"):
        assert rule in TALENT_INVITE_PROMPT


def test_the_comparison_table_shows_the_pool(client, anonymous, interview, livekit):  # noqa: F811
    from tests.test_assessments import assess, ready
    candidate = ready(client, anonymous, interview)
    assess(client, candidate)
    row = lambda: next(r for r in client.get(f"/api/jobs/{interview['job_id']}/comparison").json()  # noqa: E731
                       if r["candidate_id"] == candidate)
    assert row()["pool"] == ""
    client.put(f"/api/candidates/{candidate}/talent-pool", json={"status": "strong"})   # "Add to talent pool"
    assert row()["pool"] == "active"


# ---------- fair matching, filters and the invitation workflow ----------

STORY = ("Built and maintained backend services for an online shop, wrote tests, reviewed code and worked with the "
         "product team on new features.")


def upload_cv(client, job_id: int, name: str, email: str, text: str) -> int:
    return client.post(f"/api/jobs/{job_id}/candidates/upload", files={"file": (f"{email}.txt", text.encode())},
                       data={"full_name": name, "email": email}).json()["candidate_id"]


@pytest.fixture
def data_job(make_job) -> dict:
    """A new job: required Python and PostgreSQL (weight 2 each), preferred Kubernetes (weight 1)."""
    return make_job(approve=True, title="Data Engineer", description="A made-up data job.",
                    required_skills=["Python", "PostgreSQL"], preferred_skills=["Kubernetes"])


def keep(client, make_job, people: list[tuple[str, str, str]], status: str = "strong") -> dict:
    """Each (name, email, CV text) applied to an old job and is kept in the pool. Returns {email: candidate id}."""
    old = make_job(approve=True, title="Old Backend Job", description="A made-up old job.", required_skills=["Java"])
    ids = {}
    for name, email, text in people:
        ids[email] = upload_cv(client, old["id"], name, email, text)
        client.put(f"/api/candidates/{ids[email]}/talent-pool", json={"status": status})
    return ids


def found(client, job_id: int, query: str = "min_match=0") -> dict:
    return {r["candidate_id"]: r for r in client.get(f"/api/jobs/{job_id}/talent-matches?{query}").json()["rows"]}


def test_the_match_ignores_who_the_person_is(client, make_job, data_job):
    """Counterfactual test: CVs that differ only in name, gender, age, nationality or address get the same match."""
    skills = "Skills: Python, PostgreSQL, Kubernetes. 5 years of experience."
    people = [("Karima Akter", "fair1@example.com", f"Karima Akter\nShe is a backend developer.\n{skills}\n{STORY}"),
              ("Liam Gallagher", "fair2@example.com", f"Liam Gallagher\nHe is a backend developer.\n{skills}\n{STORY}"),
              ("Rafi Ahmed", "fair3@example.com", f"Rafi Ahmed\nDate of birth: 1975\nNationality: Bangladeshi\n"
                                                  f"Address: Dhaka\n{skills}\n{STORY}"),
              ("Sarah Jenkins", "fair4@example.com", f"Sarah Jenkins\nDate of birth: 2001\nNationality: Irish\n"
                                                     f"Address: Dublin\n{skills}\n{STORY}")]
    ids = keep(client, make_job, people)
    rows = found(client, data_job["id"])
    results = {(rows[i]["match"], tuple(rows[i]["matched"])) for i in ids.values()}
    assert results == {(100, ("Python", "PostgreSQL", "Kubernetes"))}          # exactly the same for everyone
    order = [r["candidate_id"] for r in client.get(f"/api/jobs/{data_job['id']}/talent-matches?min_match=0").json()["rows"]
             if r["candidate_id"] in ids.values()]
    assert order == [ids[e] for e in sorted(ids, key=lambda e: dict((p[1], p[0]) for p in people)[e].lower())]  # by name


def test_the_same_skill_written_differently_counts_the_same(client, make_job, data_job):
    ids = keep(client, make_job, [
        ("Alias One", "alias1@example.com", f"Alias One\nSkills: Python, PostgreSQL, Kubernetes.\n{STORY}"),
        ("Alias Two", "alias2@example.com", f"Alias Two\nSkills: python3, Postgres, k8s.\n{STORY}"),
        ("Alias Three", "alias3@example.com", f"Alias Three\nSkills: Python, Python, Python, PostgreSQL.\n{STORY}")])
    rows = found(client, data_job["id"])
    assert rows[ids["alias1@example.com"]]["match"] == rows[ids["alias2@example.com"]]["match"] == 100
    assert rows[ids["alias3@example.com"]]["match"] == 80                      # repeating a skill gives nothing extra


def test_required_skills_weigh_more_and_the_filters_work(client, make_job, data_job, monkeypatch):
    monkeypatch.setattr(invite_service, "send_email", lambda to, subject, body: {"ok": True, "error": ""})
    ids = keep(client, make_job, [
        ("Both Required", "req1@example.com", f"Both Required\nSkills: Python, PostgreSQL.\n{STORY}"),
        ("One And Preferred", "req2@example.com", f"One And Preferred\nSkills: Python, Kubernetes.\n{STORY}")])
    both, one = ids["req1@example.com"], ids["req2@example.com"]
    client.put(f"/api/candidates/{one}/talent-pool", json={"status": "other_role"})
    rows = found(client, data_job["id"])
    assert rows[both]["match"] == 80 and rows[one]["match"] == 60             # (2+2)/5 and (2+1)/5

    answer = client.get(f"/api/jobs/{data_job['id']}/talent-matches").json()
    assert answer["min_match"] == 50                                            # POOL_MIN_MATCH from .env
    assert set(found(client, data_job["id"], "min_match=70")) & {both, one} == {both}
    assert set(found(client, data_job["id"], "min_match=0&all_required=true")) & {both, one} == {both}
    assert set(found(client, data_job["id"], "min_match=0&status=other_role")) & {both, one} == {one}
    assert set(found(client, data_job["id"], "min_match=0&min_score=60")) & {both, one} == set()   # no assessment yet
    assert client.get(f"/api/jobs/{data_job['id']}/talent-matches?min_match=101").status_code == 422

    pool_id = next(r["pool_id"] for r in found(client, data_job["id"]).values() if r["candidate_id"] == both)
    drafts = client.post(f"/api/jobs/{data_job['id']}/talent-invites/draft", json={"pool_ids": [pool_id]}).json()
    client.post(f"/api/jobs/{data_job['id']}/talent-invites/send", json={"invites": drafts})
    assert both not in found(client, data_job["id"], "min_match=0&hide_invited=true")


def test_the_workflow_checks_the_ai_text_and_writes_again(client, pool, monkeypatch):
    job, pool_id = pool["new"]["id"], entry_of(pool["candidate"]).id
    calls = []

    def first_bad(prompt, facts):
        calls.append(facts)
        if len(calls) == 1:                         # breaks the rules: a link, a score, a promise, a skill not in the CV
            return {"subject": "Platform Engineer", "body": "Hi Karima, you scored 90% and we guarantee a job. "
                    "Docker experience. See https://example.com " + "word " * 30}
        return {"subject": "A new opening: Platform Engineer", "body": "Dear Karima, thank you for applying for "
                "Backend Developer. We have a new Platform Engineer opening, and your Python and PostgreSQL "
                "experience may fit it well. We would be glad if you applied for this role soon."}
    monkeypatch.setattr(talent_invite_graph, "llm_json", first_bad)
    state = talent_invite_graph.draft_invite(pool_id, job, "shorter")
    assert state["outcome"] == "ai" and state["tries"] == 2 and state["problems"] == []
    assert state["subject"] == "A new opening: Platform Engineer"
    problems = " ".join(calls[1]["problems"])                                  # the AI got the problems to fix
    for what in ("web address", "score or a percentage", "promise", "Docker"):
        assert what in problems
    assert calls[0]["instruction"] == "shorter" and "greeting is not formal" in problems
    assert "email" not in str(calls[0]) and "score" not in calls[0]            # no address, no earlier result


def test_the_standard_text_is_used_when_the_ai_fails_twice(client, pool, monkeypatch):
    job, pool_id = pool["new"]["id"], entry_of(pool["candidate"]).id
    monkeypatch.setattr(talent_invite_graph, "llm_json", lambda prompt, facts: None)
    state = talent_invite_graph.draft_invite(pool_id, job)
    assert state["outcome"] == "standard_text" and state["tries"] == 2
    assert "Karima" in state["body"] and "Platform Engineer" in state["body"]
    runs = client.get("/api/workflow-runs").json()
    assert any(r["stage"] == "talent_invite" and r["outcome"] == "standard_text" for r in runs)


def test_write_again_for_one_person_with_a_wish(client, pool):
    job, pool_id = pool["new"]["id"], entry_of(pool["candidate"]).id
    again = client.post(f"/api/jobs/{job}/talent-invites/draft",
                        json={"pool_ids": [pool_id], "instruction": "Mention remote work."}).json()
    assert len(again) == 1 and again[0]["body"].startswith("Dear Karima")      # always formal
    assert "/unsubscribe/" in again[0]["footer"] and "https://forms.gle/made-up" in again[0]["footer"]
    too_long = {"pool_ids": [pool_id], "instruction": "x" * 301}
    assert client.post(f"/api/jobs/{job}/talent-invites/draft", json=too_long).status_code == 422


def test_write_again_improves_the_previous_draft(client, pool, monkeypatch):
    job, pool_id = pool["new"]["id"], entry_of(pool["candidate"]).id
    first = client.post(f"/api/jobs/{job}/talent-invites/draft", json={"pool_ids": [pool_id]}).json()[0]
    calls = []

    def remember(prompt, facts):
        calls.append(facts)
        return fake_answer(prompt, facts)
    monkeypatch.setattr(talent_invite_graph, "llm_json", remember)
    edited = first["body"] + "\nCall me on +880 1711 000000 or see https://example.com"     # typed on the page
    again = client.post(f"/api/jobs/{job}/talent-invites/draft",
                        json={"pool_ids": [pool_id], "instruction": "Make it shorter",
                              "previous_subject": first["subject"], "previous_body": edited}).json()[0]
    previous = calls[0]["previous_draft"]
    assert previous["subject"] == first["subject"] and "Best regards" not in previous["body"]   # signature removed
    assert "https://" not in previous["body"] and "1711" not in previous["body"]               # links and numbers too
    assert len(again["body"].split()) < len(first["body"].split())                              # shorter
    assert again["body"].startswith("Dear Karima") and again["body"].count("Best regards") == 1
    two = {"pool_ids": [pool_id, pool_id + 1], "previous_body": "Dear Karima, ..."}
    assert client.post(f"/api/jobs/{job}/talent-invites/draft", json=two).status_code == 409


def test_the_subject_always_shows_the_job_title(client, pool, monkeypatch):
    from app.graphs.talent_invite_graph import with_job_title
    assert with_job_title("A new opening", "Platform Engineer") == "A new opening: Platform Engineer"
    assert with_job_title("Platform engineer role", "Platform Engineer") == "Platform engineer role"   # already there
    assert with_job_title("", "Platform Engineer") == "A new opening: Platform Engineer"
    monkeypatch.setattr(talent_invite_graph, "llm_json", lambda prompt, facts: {
        "subject": "We thought of you", "body": "Dear Karima, thank you for applying for Backend Developer. We have "
        "a new Platform Engineer opening, and your Python and PostgreSQL experience may fit it well. We would be glad "
        "if you applied for this role soon."})
    state = talent_invite_graph.draft_invite(entry_of(pool["candidate"]).id, pool["new"]["id"])
    assert state["subject"] == "We thought of you: Platform Engineer" and state["tries"] == 1   # fixed by code
