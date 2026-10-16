"""Sending the invitation email over SMTP (features/interviews/services/smtp_service.py). The Send button calls it
directly: no AI and no MCP server. A pretend SMTP server on this computer receives the email, so nothing is really sent."""
import email
import json

from app.core import config
from app.features.interviews.services import smtp_service


def test_send_email_with_a_calendar(fake_smtp):
    calendar = "BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\nUID:t-1@lumenai\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    answer = smtp_service.send_email("asha@example.com", "Interview", "Hello Asha", calendar)
    assert answer == {"ok": True, "error": ""}
    message = email.message_from_string(fake_smtp.messages[-1])
    assert message["To"] == "asha@example.com" and message["From"] == "hr@example.com"
    assert "text/calendar" in {part.get_content_type() for part in message.walk()}


def test_problems_come_back_in_plain_words(fake_smtp, monkeypatch):
    bad = smtp_service.send_email("not-an-address", "x", "y")
    assert bad["ok"] is False and "does not look right" in bad["error"]

    monkeypatch.setattr(config, "SMTP_PORT", 1)                        # nothing listens there
    closed = smtp_service.send_email("asha@example.com", "x", "y")
    assert closed["ok"] is False and "cannot reach the email server" in closed["error"]
    assert "made-up-password" not in json.dumps(closed)               # never the password


def test_check_email_settings(fake_smtp, monkeypatch):
    ok = smtp_service.check_email_settings()
    assert ok["ok"] is True and "Nothing was sent" in ok["message"] and fake_smtp.messages == []
    monkeypatch.setattr(config, "SMTP_HOST", "")
    empty = smtp_service.check_email_settings()
    assert empty["ok"] is False and "SMTP_HOST is empty" in empty["message"]


def test_the_settings_button(client, fake_smtp):
    assert client.get("/api/email-check").json()["ok"] is True


def test_the_invitation_is_sent_with_the_link(client, make_job, fake_smtp):
    """The whole way: schedule a shortlisted candidate, click Send, and the email + calendar arrive."""
    from tests.test_interviews import cv, later
    job = make_job(approve=True, title="QA Engineer", description="A made-up job.", required_skills=["Python"])
    candidate = client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": ("n.txt", cv("Nadia Islam", 4))},
                            data={"full_name": "Nadia Islam", "email": "nadia@example.com"}).json()["candidate_id"]
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    client.post(f"/api/jobs/{job['id']}/shortlist", json={"candidate_ids": [candidate], "rule": "by_hand"})
    session = client.post("/api/sessions", json={"candidate_id": candidate, "scheduled_at": later(),
                                                 "duration_minutes": 30, "time_zone": "UTC"}).json()
    sent = client.put(f"/api/sessions/{session['id']}/invitation", json={
        "to": "nadia@example.com", "subject": session["invitation_subject"], "body": session["invitation_body"]}).json()
    assert sent["invitation_status"] == "sent"
    message = email.message_from_string(fake_smtp.messages[-1])
    assert message["To"] == "nadia@example.com"
    assert session["join_link"] in fake_smtp.messages[-1].replace("=\n", "").replace("\r\n ", "")
