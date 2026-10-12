"""Interview scheduling and the invitation: only shortlisted candidates, a private join link, draft first (the AI
writes, code puts the link in, a person sends), a calendar invite with the email. Made-up CVs only."""
import email
from datetime import datetime, timedelta, timezone

import pytest

from app.core import config
from app.graphs import invitation_graph
from app.features.interviews.services.calendar_service import calendar_invite

STORY = ("Worked in a product team, wrote automated tests, reviewed code and explained technical choices to "
         "colleagues. Planned releases with the product owner and kept the documentation up to date. ")


def cv(name: str, years: int) -> bytes:
    return (f"{name}\nMade-up CV used by the tests.\nSkills: Python, FastAPI, PostgreSQL\n"
            f"Experience: {years} years as a backend developer.\n{STORY}\nEducation: BSc in CSE\n").encode()


def later(days=3, hour=9) -> str:
    start = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return start.isoformat().replace("+00:00", "Z")


@pytest.fixture
def job(make_job) -> dict:
    return make_job(approve=True, title="Backend Developer", description="A made-up job for the interview tests.",
                    required_skills=["Python", "FastAPI", "PostgreSQL"], min_years=3, qualifications="BSc in CSE or similar")


@pytest.fixture
def people(client, job) -> dict:
    """Karima: included and shortlisted. Rahim: included, not shortlisted."""
    ids = {}
    for name in ("Karima Akter", "Rahim Uddin"):
        ids[name] = client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": (f"{name}.txt", cv(name, 5))},
                                data={"full_name": name, "email": f"{name.split()[0].lower()}@example.com"}).json()["candidate_id"]
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    assert client.post(f"/api/jobs/{job['id']}/shortlist",
                       json={"candidate_ids": [ids["Karima Akter"]], "rule": "by_hand"}).status_code == 200
    return ids


def schedule(client, candidate_id, when=None, minutes=45, zone="Asia/Dhaka"):
    return client.post("/api/sessions", json={"candidate_id": candidate_id, "scheduled_at": when or later(),
                                              "duration_minutes": minutes, "time_zone": zone})


def test_schedule_writes_a_draft_with_the_private_link(client, job, people):
    answer = schedule(client, people["Karima Akter"], later(days=3, hour=9))
    assert answer.status_code == 201
    session = answer.json()
    token = session["join_link"].rsplit("/join/", 1)[1]
    assert session["join_link"] == f"{config.APP_URL}/join/{token}" and len(token) >= 40
    assert session["invitation_status"] == ""                        # a draft: nothing is sent by itself
    assert session["invite_email"] == "karima@example.com"
    assert session["invitation_subject"] == "Interview invitation: Backend Developer"
    body = session["invitation_body"]
    assert session["join_link"] in body and "{join_link}" not in body  # code put the real link in
    assert "Dear Karima Akter" in body and "3:00 PM (Asia/Dhaka, GMT+06)" in body   # 09:00 UTC = 15:00 in Dhaka
    assert "Test Interviewer" in body                                 # signed with the interviewer's name

    listed = client.get(f"/api/sessions?job_id={job['id']}").json()
    assert [s["id"] for s in listed] == [session["id"]]
    assert client.get(f"/api/sessions/{session['id']}").json()["join_link"] == session["join_link"]


def test_the_ai_never_gets_the_email_address(client, job, people, monkeypatch):
    seen = []
    real = invitation_graph.llm_json
    monkeypatch.setattr(invitation_graph, "llm_json", lambda instructions, data: seen.append(data) or real(instructions, data))
    schedule(client, people["Karima Akter"])
    assert seen and "karima@example.com" not in str(seen) and "@" not in str(seen)


def test_only_shortlisted_candidates_in_the_future(client, job, people):
    not_shortlisted = schedule(client, people["Rahim Uddin"])
    assert not_shortlisted.status_code == 400 and "shortlisted" in not_shortlisted.json()["detail"]
    past = schedule(client, people["Karima Akter"], later(days=-1))
    assert past.status_code == 400 and "future" in past.json()["detail"]
    assert schedule(client, people["Karima Akter"], later(days=400)).status_code == 400
    assert schedule(client, people["Karima Akter"], zone="Mars/Olympus").status_code == 422
    assert schedule(client, people["Karima Akter"], "2026-12-01T09:00:00").status_code == 422   # no time zone
    assert schedule(client, people["Karima Akter"], minutes=5).status_code == 422
    assert schedule(client, 999999).status_code == 404

    assert schedule(client, people["Karima Akter"]).status_code == 201
    twice = schedule(client, people["Karima Akter"])
    assert twice.status_code == 409                                   # one open interview per candidate


def test_when_the_ai_cannot_write_a_standard_text_is_used(client, job, people, monkeypatch):
    monkeypatch.setattr(invitation_graph, "llm_json", lambda instructions, data: None)
    session = schedule(client, people["Karima Akter"]).json()
    assert "standard text" in session["message"]
    assert session["join_link"] in session["invitation_body"] and "Dear Karima Akter" in session["invitation_body"]


def test_send_without_smtp_is_saved_as_not_sent(client, job, people, monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "")
    session = schedule(client, people["Karima Akter"]).json()
    sent = client.put(f"/api/sessions/{session['id']}/invitation",
                      json={"to": "karima@example.com", "subject": "Interview", "body": "Hello Karima, see you soon."}).json()
    assert sent["invitation_status"] == "not_sent" and "not set up" in sent["message"]
    assert sent["join_link"] in sent["invitation_body"]                # the link was removed, so code put it back

    no_address = client.put(f"/api/sessions/{session['id']}/invitation",
                            json={"to": " ", "subject": "Interview", "body": "Hello"}).json()
    assert no_address["invitation_status"] == "no_email"


def test_send_with_the_calendar_invite(client, job, people, fake_smtp, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_TRANSPORT", "smtp")              # this process sends (MCP: test_mcp_email.py)
    session = schedule(client, people["Karima Akter"], later(days=5, hour=9)).json()
    edited = session["invitation_body"] + "\n\nP.S. Edited by the interviewer."
    sent = client.put(f"/api/sessions/{session['id']}/invitation",
                      json={"to": "karima@example.com", "subject": session["invitation_subject"], "body": edited}).json()
    assert sent["invitation_status"] == "sent" and sent["sent_at"] and "calendar invite" in sent["message"]

    message = email.message_from_string(fake_smtp.messages[-1])
    assert message["To"] == "karima@example.com" and message["Subject"] == "Interview invitation: Backend Developer"
    parts = {part.get_content_type(): part for part in message.walk()}
    text = parts["text/plain"].get_payload(decode=True).decode()
    assert "Edited by the interviewer" in text and session["join_link"] in text
    calendar = parts["text/calendar"].get_payload(decode=True).decode().replace("\r\n ", "")
    start = datetime.fromisoformat(session["scheduled_at"].replace("Z", "+00:00"))
    assert "METHOD:REQUEST" in calendar and f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}" in calendar
    assert f"DTEND:{(start + timedelta(minutes=45)).strftime('%Y%m%dT%H%M%SZ')}" in calendar
    assert session["join_link"] in calendar and "mailto:karima@example.com" in calendar and "SEQUENCE:0" in calendar
    assert any(part.get_filename() == "invite.ics" for part in message.walk())


def test_a_new_time_updates_the_same_calendar_event(client, job, people, fake_smtp, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_TRANSPORT", "smtp")
    session = schedule(client, people["Karima Akter"]).json()
    first = client.put(f"/api/sessions/{session['id']}/invitation",
                       json={"to": "karima@example.com", "subject": "Interview", "body": session["invitation_body"]}).json()
    moved = client.put(f"/api/sessions/{session['id']}/time",
                       json={"scheduled_at": later(days=6, hour=4), "duration_minutes": 60, "time_zone": "Asia/Dhaka"}).json()
    assert moved["invitation_status"] == "" and moved["duration_minutes"] == 60     # a new draft: send it again
    assert "10:00 AM (Asia/Dhaka, GMT+06)" in moved["invitation_body"]
    client.put(f"/api/sessions/{session['id']}/invitation",
               json={"to": "karima@example.com", "subject": "New time", "body": moved["invitation_body"]})
    calendars = [m.replace("\r\n ", "") for m in fake_smtp.messages[-2:]]
    uid = lambda text: next(line for line in text.splitlines() if line.startswith("UID:"))   # noqa: E731
    assert first["invitation_status"] == "sent"
    assert uid(calendars[0]) == uid(calendars[1]) and "SEQUENCE:1" in calendars[1]


def test_write_again_with_ai(client, job, people):
    session = schedule(client, people["Karima Akter"]).json()
    again = client.post(f"/api/sessions/{session['id']}/invitation").json()
    assert again["invitation_status"] == "" and session["join_link"] in again["invitation_body"]
    assert "The AI wrote the invitation" in again["message"]


def test_the_candidate_page_shows_only_their_interview(client, anonymous, job, people):
    session = schedule(client, people["Karima Akter"]).json()
    token = session["join_link"].rsplit("/", 1)[1]
    page = anonymous.get(f"/api/join/{token}")                        # no login: the private link is enough
    assert page.status_code == 200
    assert page.json() == {"job_title": "Backend Developer", "candidate_name": "Karima Akter",
                           "scheduled_at": page.json()["scheduled_at"], "duration_minutes": 45, "status": "scheduled"}
    assert anonymous.get("/api/join/not-a-real-token-at-all-123").status_code == 404
    assert anonymous.get("/api/join/short").status_code == 404


def test_a_deleted_candidate_loses_the_interview(client, job, people):
    session = schedule(client, people["Karima Akter"]).json()
    client.delete(f"/api/candidates/{people['Karima Akter']}")
    assert client.get(f"/api/sessions/{session['id']}").status_code == 404


def test_login_is_needed(anonymous):
    assert anonymous.post("/api/sessions", json={}).status_code == 401
    assert anonymous.get("/api/sessions?job_id=1").status_code == 401
    assert anonymous.put("/api/sessions/1/invitation", json={}).status_code == 401
    assert anonymous.get("/api/email-check").status_code == 401


def test_calendar_text_rules():
    start = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    text = calendar_invite(uid="u-1@lumenai", start=start, minutes=30, title="Interview: QA, Senior; Team",
                           description="Line one\nLine two " + "x" * 120, link="https://example.com/join/abc",
                           organizer="hr@example.com", attendee="a@example.com", attendee_name="Asha Rahman", sequence=2)
    lines = text.split("\r\n")
    assert all(len(line.encode()) <= 75 for line in lines)            # long lines are folded
    unfolded = text.replace("\r\n ", "")
    assert "SUMMARY:Interview: QA\\, Senior\\; Team" in unfolded       # commas and semicolons are escaped
    assert "DTSTART:20261020T090000Z" in unfolded and "DTEND:20261020T093000Z" in unfolded and "SEQUENCE:2" in unfolded
    assert "DESCRIPTION:Line one\\nLine two" in unfolded


# ---------- the LangGraph workflow (graphs/invitation_graph.py) ----------

def paused_at(session_id) -> tuple:
    from sqlmodel import Session
    from app.core.database import engine
    from app.features.interviews.models import InterviewSession
    with Session(engine) as db:
        interview = db.get(InterviewSession, session_id)
    return invitation_graph.runner().get_state({"configurable": {"thread_id": invitation_graph.thread_of(interview)}}).next


def test_the_workflow_waits_for_the_person_and_waits_again_after_sending(client, job, people, monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "")
    session = schedule(client, people["Karima Akter"]).json()
    assert paused_at(session["id"]) == ("ask_person",)                # drafted and checked: waits for a click
    client.put(f"/api/sessions/{session['id']}/invitation",
               json={"to": "karima@example.com", "subject": "Interview", "body": session["invitation_body"]})
    assert paused_at(session["id"]) == ("ask_person",)                # waits again: can be sent again or rewritten


def test_the_check_sends_a_bad_draft_back_once(client, job, people, monkeypatch):
    seen = []

    def invents_a_link(instructions, data):
        seen.append(data)
        return {"subject": "Interview", "body": f"Dear Karima, on {data['date']} join at https://made-up.example/call"}
    monkeypatch.setattr(invitation_graph, "llm_json", invents_a_link)
    session = schedule(client, people["Karima Akter"]).json()
    assert len(seen) == 2 and "fix_these" in seen[1]                   # written again, told what to fix
    assert any("web address" in problem for problem in seen[1]["fix_these"])
    assert "made-up.example" not in session["invitation_body"]          # still bad: the standard text is used
    assert "standard text" in session["message"] and session["join_link"] in session["invitation_body"]


def test_a_good_draft_passes_the_check_the_first_time(client, job, people, monkeypatch):
    calls = []
    real = invitation_graph.llm_json
    monkeypatch.setattr(invitation_graph, "llm_json", lambda instructions, data: calls.append(1) or real(instructions, data))
    session = schedule(client, people["Karima Akter"]).json()
    assert len(calls) == 1 and "The AI wrote the invitation" in session["message"]
