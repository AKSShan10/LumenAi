"""The video call (LiveKit): the interviewer starts it, the candidate joins with the private link only while it is
live, the interviewer ends it for both. Our backend only gives out signed tickets. Made-up data only."""
import jwt
import pytest

from app.core import config
from tests.test_interviews import cv, later

SECRET = "made-up-livekit-secret-that-is-long-enough-123"


@pytest.fixture
def livekit(monkeypatch):
    monkeypatch.setattr(config, "LIVEKIT_URL", "wss://made-up.livekit.cloud")
    monkeypatch.setattr(config, "LIVEKIT_API_KEY", "made-up-key")
    monkeypatch.setattr(config, "LIVEKIT_API_SECRET", SECRET)


@pytest.fixture
def interview(client, make_job, monkeypatch) -> dict:
    """A scheduled interview of a shortlisted candidate (no email is sent)."""
    monkeypatch.setattr(config, "SMTP_HOST", "")
    job = make_job(approve=True, title="Backend Developer", description="A made-up job for the call tests.",
                   required_skills=["Python", "FastAPI", "PostgreSQL"], min_years=3)
    candidate = client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": ("k.txt", cv("Karima Akter", 5))},
                            data={"full_name": "Karima Akter", "email": "karima@example.com"}).json()["candidate_id"]
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    client.post(f"/api/jobs/{job['id']}/shortlist", json={"candidate_ids": [candidate], "rule": "by_hand"})
    session = client.post("/api/sessions", json={"candidate_id": candidate, "scheduled_at": later(),
                                                 "duration_minutes": 45, "time_zone": "UTC"}).json()
    session["token"] = session["join_link"].rsplit("/", 1)[1]
    return session


def claims(ticket: str) -> dict:
    return jwt.decode(ticket, SECRET, algorithms=["HS256"])          # only our secret can check the signature


def test_the_interviewer_starts_and_the_candidate_joins(client, anonymous, interview, livekit):
    early = anonymous.post(f"/api/join/{interview['token']}/ticket", json={"name": "Karima"})
    assert early.status_code == 409 and "not started" in early.json()["detail"]          # not before the start

    started = client.post(f"/api/sessions/{interview['id']}/start")
    assert started.status_code == 200
    body = started.json()
    assert body["server_url"] == "wss://made-up.livekit.cloud" and body["identity"] == "interviewer"
    assert body["session"]["status"] == "live" and body["session"]["started_at"]
    mine = claims(body["ticket"])
    assert mine["sub"] == "interviewer" and mine["name"] == "Test Interviewer" and mine["iss"] == "made-up-key"
    assert mine["video"]["roomJoin"] is True and mine["video"]["room"] == body["room_name"]
    assert anonymous.get(f"/api/join/{interview['token']}").json()["status"] == "live"

    joined = anonymous.post(f"/api/join/{interview['token']}/ticket", json={"name": "Karima Akter"})
    assert joined.status_code == 200
    theirs = claims(joined.json()["ticket"])
    assert theirs["sub"] == "candidate" and theirs["name"] == "Karima Akter"
    assert theirs["video"]["room"] == body["room_name"]                                   # the same room, only this one
    assert client.get(f"/api/sessions/{interview['id']}").json()["candidate_joined_at"]


def test_join_again_keeps_the_start_time(client, interview, livekit):
    first = client.post(f"/api/sessions/{interview['id']}/start").json()["session"]["started_at"]
    again = client.post(f"/api/sessions/{interview['id']}/start").json()
    assert again["session"]["started_at"] == first and again["ticket"]


def test_end_closes_the_call_for_both(client, anonymous, interview, livekit):
    client.post(f"/api/sessions/{interview['id']}/start")
    ended = client.post(f"/api/sessions/{interview['id']}/end").json()
    assert ended["status"] == "ended" and ended["ended_at"]
    late = anonymous.post(f"/api/join/{interview['token']}/ticket", json={"name": "Karima"})
    assert late.status_code == 409 and "ended" in late.json()["detail"]                    # not after the end
    assert anonymous.get(f"/api/join/{interview['token']}").json()["status"] == "ended"
    assert client.post(f"/api/sessions/{interview['id']}/start").status_code == 400        # cannot start again
    moved = client.put(f"/api/sessions/{interview['id']}/time",
                       json={"scheduled_at": later(days=5), "duration_minutes": 45, "time_zone": "UTC"})
    assert moved.status_code == 400


def test_without_livekit_settings_nothing_starts(client, interview, monkeypatch):
    monkeypatch.setattr(config, "LIVEKIT_URL", "")
    answer = client.post(f"/api/sessions/{interview['id']}/start")
    assert answer.status_code == 503 and "LIVEKIT_URL" in answer.json()["detail"]
    assert client.get(f"/api/sessions/{interview['id']}").json()["status"] == "scheduled"
    assert client.get("/api/video-check").json()["ok"] is False


def test_the_candidate_needs_a_name_and_a_real_link(client, anonymous, interview, livekit):
    client.post(f"/api/sessions/{interview['id']}/start")
    assert anonymous.post(f"/api/join/{interview['token']}/ticket", json={"name": ""}).status_code == 422
    assert anonymous.post("/api/join/not-a-real-token-at-all-123/ticket", json={"name": "X"}).status_code == 404


def test_login_rules(anonymous, client, interview, livekit):
    assert anonymous.post(f"/api/sessions/{interview['id']}/start").status_code == 401
    assert anonymous.post(f"/api/sessions/{interview['id']}/end").status_code == 401
    assert anonymous.get("/api/video-check").status_code == 401
    assert client.get("/api/video-check").json()["ok"] is True


def test_only_a_livekit_cloud_address_is_accepted(client, interview, livekit, monkeypatch):
    """The call runs on LiveKit Cloud only; the old local value "/" is refused with a plain message."""
    monkeypatch.setattr(config, "LIVEKIT_URL", "/")
    check = client.get("/api/video-check").json()
    assert check["ok"] is False and "LiveKit Cloud address" in check["message"]
    assert client.post(f"/api/sessions/{interview['id']}/start").status_code == 503
