"""Inviting the whole shortlist at once: suggested times inside working hours (lunch, end of day, weekend, today),
schedule many with one AI draft each, and Send all only after the click. Made-up CVs only."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core import config
from app.features.interviews.services.slot_service import WorkingHours, hours_problem, plan_slots

DHAKA = ZoneInfo("Asia/Dhaka")
MONDAY = date(2030, 10, 21)                 # a Monday, far in the future
EARLY = datetime(2030, 1, 1, tzinfo=timezone.utc)
HOURS = WorkingHours()                      # 8:00-17:00, lunch 12:30-13:30
_today = datetime.now(DHAKA).date()
NEXT_MONDAY = _today + timedelta(days=7 + (7 - _today.weekday()) % 7)    # a Monday 1-2 weeks ahead (routes: within a year)


def clock(moment: datetime) -> str:
    """'Mon 08:45' in Dhaka, to read the tests easily."""
    return moment.astimezone(DHAKA).strftime("%a %H:%M")


# ---------- the time planner (plain maths) ----------

def test_slots_skip_lunch_and_move_to_the_next_day():
    starts = plan_slots(11, MONDAY, 45, "Asia/Dhaka", HOURS, now=EARLY)
    assert [clock(s) for s in starts] == [
        "Mon 08:00", "Mon 08:45", "Mon 09:30", "Mon 10:15", "Mon 11:00", "Mon 11:45",   # 11:45-12:30 ends at lunch
        "Mon 13:30", "Mon 14:15", "Mon 15:00", "Mon 15:45",                              # 16:30-17:15 would pass 17:00
        "Tue 08:00"]


def test_an_interview_never_runs_into_lunch():
    starts = plan_slots(5, MONDAY, 60, "Asia/Dhaka", HOURS, now=EARLY)
    assert [clock(s) for s in starts] == ["Mon 08:00", "Mon 09:00", "Mon 10:00", "Mon 11:00", "Mon 13:30"]  # 12:00-13:00 skipped


def test_the_weekend_is_skipped():
    friday = MONDAY + timedelta(days=4)
    starts = plan_slots(2, friday, 180, "Asia/Dhaka", HOURS, now=EARLY)   # one fits in the morning, one after lunch
    starts += plan_slots(1, friday + timedelta(days=1), 180, "Asia/Dhaka", HOURS, now=EARLY)     # asked from Saturday
    assert [clock(s) for s in starts] == ["Fri 08:00", "Fri 13:30", "Mon 08:00"]


def test_today_starts_after_now_and_busy_times_are_kept_free():
    now = datetime.combine(MONDAY, time(10, 5), tzinfo=DHAKA)
    busy = [(datetime.combine(MONDAY, time(11, 0), tzinfo=DHAKA), datetime.combine(MONDAY, time(12, 0), tzinfo=DHAKA))]
    starts = plan_slots(3, MONDAY, 45, "Asia/Dhaka", HOURS, busy=busy, now=now)
    assert [clock(s) for s in starts] == ["Mon 10:15", "Mon 13:30", "Mon 14:15"]   # 11:00-12:00 busy; 12:00-12:45 hits lunch


def test_start_at_or_after_the_last_interview():
    not_before = datetime.combine(MONDAY, time(14, 30), tzinfo=DHAKA)          # "Start at" 2:30 PM, or the last end
    starts = plan_slots(3, MONDAY, 60, "Asia/Dhaka", HOURS, now=EARLY, not_before=not_before)
    assert [clock(s) for s in starts] == ["Mon 14:30", "Mon 15:30", "Tue 08:00"]   # 16:30-17:30 would pass 17:00
    lunch = datetime.combine(MONDAY, time(12, 0), tzinfo=DHAKA)                 # a start inside lunch moves after it
    assert clock(plan_slots(1, MONDAY, 45, "Asia/Dhaka", HOURS, now=EARLY, not_before=lunch)[0]) == "Mon 13:30"


def test_hours_that_cannot_work_are_explained():
    assert hours_problem(HOURS, 45) == ""
    assert "does not fit" in hours_problem(HOURS, 300)          # 8:00-12:30 is only 270 minutes
    assert "in order" in hours_problem(WorkingHours(time(9), time(17), time(8), time(13)), 45)


# ---------- the routes ----------

def cv(name: str) -> bytes:
    return (f"{name}\nMade-up CV used by the tests.\nSkills: Python, FastAPI, PostgreSQL\n"
            "Experience: 5 years as a backend developer.\nWorked in a product team, wrote automated tests and reviewed "
            "code. Planned releases with the product owner and kept the documentation up to date.\n"
            "Education: BSc in CSE\n").encode()


@pytest.fixture
def shortlist(client, make_job) -> dict:
    """Three made-up candidates on the shortlist of a job."""
    job = make_job(approve=True, title="Backend Developer", description="A made-up job for the schedule-all tests.",
                   required_skills=["Python", "FastAPI", "PostgreSQL"], min_years=3, qualifications="BSc in CSE or similar")
    ids = {}
    for name in ("Karima Akter", "Rahim Uddin", "Nadia Islam"):
        ids[name] = client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": (f"{name}.txt", cv(name))},
                                data={"full_name": name, "email": f"{name.split()[0].lower()}@example.com"}).json()["candidate_id"]
    client.post(f"/api/jobs/{job['id']}/screening", json={})
    assert client.post(f"/api/jobs/{job['id']}/shortlist", json={"candidate_ids": list(ids.values()), "rule": "by_hand"}).status_code == 200
    return {"job": job, "ids": ids}


def last_interview_end() -> datetime:
    """The end of the test interviewer's latest open interview (earlier tests may have booked some too)."""
    from sqlmodel import Session, select
    from app.core.database import engine
    from app.features.interviews.models import InterviewSession
    with Session(engine) as session:
        rows = session.exec(select(InterviewSession).where(InterviewSession.status != "ended")).all()
        ends = [r.scheduled_at.replace(tzinfo=r.scheduled_at.tzinfo or timezone.utc) + timedelta(minutes=r.duration_minutes)
                for r in rows]
    return max(ends)


def plan(client, job_id, **extra):
    return client.post("/api/sessions/plan", json={"job_id": job_id, "first_day": NEXT_MONDAY.isoformat(),
                                                   "duration_minutes": 45, "time_zone": "Asia/Dhaka", **extra})


def test_suggest_times_for_the_whole_shortlist(client, shortlist):
    rows = plan(client, shortlist["job"]["id"]).json()
    assert len(rows) == 3 and all(row["session_id"] is None for row in rows)
    times = [clock(datetime.fromisoformat(row["scheduled_at"].replace("Z", "+00:00"))) for row in rows]
    assert times == ["Mon 08:00", "Mon 08:45", "Mon 09:30"]
    assert client.get(f"/api/sessions?job_id={shortlist['job']['id']}").json() == []      # nothing was saved

    later = plan(client, shortlist["job"]["id"], day_start="09:00", lunch_start="09:30", lunch_end="10:00").json()
    assert [clock(datetime.fromisoformat(r["scheduled_at"].replace("Z", "+00:00"))) for r in later] == \
        ["Mon 10:00", "Mon 10:45", "Mon 11:30"]                       # 9:00-9:45 would run into this "lunch"
    assert plan(client, shortlist["job"]["id"], duration_minutes=180, lunch_start="09:00",
                lunch_end="16:00").status_code == 400                 # cannot fit: a plain message, not a loop


def test_schedule_all_writes_one_draft_each_and_sends_nothing(client, shortlist, fake_smtp):
    rows = plan(client, shortlist["job"]["id"]).json()
    items = [{"candidate_id": r["candidate_id"], "scheduled_at": r["scheduled_at"], "duration_minutes": 45,
              "time_zone": "Asia/Dhaka"} for r in rows]
    items[2]["scheduled_at"] = "2020-01-01T08:00:00Z"                 # one bad time: the others still go ahead
    answer = client.post("/api/sessions/bulk", json={"items": items}).json()
    assert len(answer["sessions"]) == 2 and answer["problems"][0]["reason"] == "The interview time must be in the future."
    assert all(s["invitation_status"] == "" and s["join_link"] in s["invitation_body"] for s in answer["sessions"])
    assert len({s["join_link"] for s in answer["sessions"]}) == 2     # each candidate has their own private link
    assert fake_smtp.messages == []                                   # drafts only: nothing is sent by itself

    again = plan(client, shortlist["job"]["id"]).json()               # the scheduled two keep their times
    assert [r["session_id"] is not None for r in again] == [True, True, False]
    assert clock(datetime.fromisoformat(again[2]["scheduled_at"].replace("Z", "+00:00"))) == "Mon 09:30"


def test_new_suggestions_come_after_the_last_interview_unless_start_at_is_given(client, shortlist):
    first = plan(client, shortlist["job"]["id"]).json()[0]
    client.post("/api/sessions/bulk", json={"items": [{"candidate_id": first["candidate_id"], "scheduled_at": first["scheduled_at"],
                                                       "duration_minutes": 45, "time_zone": "Asia/Dhaka"}]})
    later = plan(client, shortlist["job"]["id"], duration_minutes=60).json()
    starts = [datetime.fromisoformat(r["scheduled_at"].replace("Z", "+00:00")) for r in later[1:]]
    assert starts[0] == last_interview_end()                          # straight after the last interview, no gap
    assert starts[1] - starts[0] == timedelta(minutes=60)
    chosen = plan(client, shortlist["job"]["id"], start_at="15:00").json()      # a free afternoon time
    assert [clock(datetime.fromisoformat(r["scheduled_at"].replace("Z", "+00:00"))) for r in chosen[1:]] == \
        ["Mon 15:00", "Mon 15:45"]


def test_send_all_sends_only_the_unsent_drafts(client, shortlist, fake_smtp, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_TRANSPORT", "smtp")
    rows = plan(client, shortlist["job"]["id"]).json()
    items = [{"candidate_id": r["candidate_id"], "scheduled_at": r["scheduled_at"], "duration_minutes": 45,
              "time_zone": "Asia/Dhaka"} for r in rows]
    scheduled = client.post("/api/sessions/bulk", json={"items": items}).json()["sessions"]
    first = scheduled[0]
    client.put(f"/api/sessions/{first['id']}/invitation",                # one was already sent by hand
               json={"to": first["invite_email"], "subject": first["invitation_subject"], "body": first["invitation_body"]})
    assert len(fake_smtp.messages) == 1

    answer = client.post(f"/api/sessions/send-all?job_id={shortlist['job']['id']}").json()
    assert len(answer["sessions"]) == 2 and answer["problems"] == [] and answer["message"].startswith("2 invitation(s) sent")
    assert len(fake_smtp.messages) == 3                               # the first one was not sent twice
    listed = client.get(f"/api/sessions?job_id={shortlist['job']['id']}").json()
    assert {s["invitation_status"] for s in listed} == {"sent"}
    assert client.post(f"/api/sessions/send-all?job_id={shortlist['job']['id']}").json()["message"] == \
        "There is no unsent invitation."


def test_send_all_reports_what_could_not_be_sent(client, shortlist, monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "")
    rows = plan(client, shortlist["job"]["id"]).json()[:1]
    client.post("/api/sessions/bulk", json={"items": [{"candidate_id": rows[0]["candidate_id"],
                                                       "scheduled_at": rows[0]["scheduled_at"], "duration_minutes": 45,
                                                       "time_zone": "Asia/Dhaka"}]})
    answer = client.post(f"/api/sessions/send-all?job_id={shortlist['job']['id']}").json()
    assert answer["problems"][0]["reason"] == "Email is not set up (SMTP in .env)." and "1 not sent" in answer["message"]


def test_login_is_needed_for_the_new_routes(anonymous):
    assert anonymous.post("/api/sessions/plan", json={}).status_code == 401
    assert anonymous.post("/api/sessions/bulk", json={}).status_code == 401
    assert anonymous.post("/api/sessions/send-all?job_id=1").status_code == 401


# ---------- no lunch break, and one checked invitation for everyone ----------

def test_no_lunch_break_option():
    no_lunch = WorkingHours(lunch_start=None, lunch_end=None)
    starts = plan_slots(7, MONDAY, 60, "Asia/Dhaka", no_lunch, now=EARLY)
    assert [clock(s) for s in starts] == ["Mon 08:00", "Mon 09:00", "Mon 10:00", "Mon 11:00", "Mon 12:00", "Mon 13:00",
                                          "Mon 14:00"]                          # 12:00-13:00 is now allowed
    assert hours_problem(no_lunch, 180) == "" and "working day" in hours_problem(no_lunch, 600)


def test_skip_lunch_through_the_route(client, shortlist):
    free_monday = (NEXT_MONDAY + timedelta(days=7)).isoformat()      # earlier tests booked the first Monday
    rows = plan(client, shortlist["job"]["id"], duration_minutes=60, start_at="11:00", skip_lunch=True,
                first_day=free_monday).json()
    assert [clock(datetime.fromisoformat(r["scheduled_at"].replace("Z", "+00:00"))) for r in rows] == \
        ["Mon 11:00", "Mon 12:00", "Mon 13:00"]                        # straight through lunch time


def test_one_invitation_is_written_with_placeholders(client, shortlist):
    answer = client.post("/api/sessions/template", json={"job_id": shortlist["job"]["id"], "duration_minutes": 45}).json()
    assert "{candidate_name}" in answer["body"] and "{date}" in answer["body"] and "{join_link}" in answer["body"]
    assert "Karima" not in answer["body"]                             # one text for everyone: no real name yet
    assert answer["message"].startswith("The AI wrote the invitation")


def test_schedule_all_with_the_checked_invitation_makes_no_ai_call(client, shortlist, fake_smtp, monkeypatch):
    from app.graphs import invitation_graph
    template = {"subject": "Your interview", "body": "Dear {candidate_name},\n\nSee you on {date} at {time} for "
                "{length_minutes} minutes.\n\n{join_link}\n\n{interviewer_name}"}
    rows = plan(client, shortlist["job"]["id"]).json()
    items = [{"candidate_id": r["candidate_id"], "scheduled_at": r["scheduled_at"], "duration_minutes": 45,
              "time_zone": "Asia/Dhaka"} for r in rows]
    monkeypatch.setattr(invitation_graph, "llm_json", lambda *a, **k: pytest.fail("the AI must not be called"))
    answer = client.post("/api/sessions/bulk", json={"items": items, "template": template}).json()
    assert len(answer["sessions"]) == 3 and answer["problems"] == []
    for s in answer["sessions"]:
        body = s["invitation_body"]
        assert body.startswith(f"Dear {s['candidate_name']},") and s["join_link"] in body and "{" not in body
        assert s["invitation_subject"].startswith("Your interview - ") and s["invitation_status"] == ""
    assert fake_smtp.messages == []                                   # saved as drafts: Send all sends them later

    monkeypatch.undo()                                                # "Write again" for one: the AI writes for them
    again = client.post(f"/api/sessions/{answer['sessions'][0]['id']}/invitation").json()
    assert "Fake AI text" in again["invitation_body"]


def test_a_broken_invitation_is_refused_before_anyone_is_scheduled(client, shortlist):
    rows = plan(client, shortlist["job"]["id"]).json()
    items = [{"candidate_id": r["candidate_id"], "scheduled_at": r["scheduled_at"], "duration_minutes": 45,
              "time_zone": "Asia/Dhaka"} for r in rows]
    broken = {"subject": "Interview", "body": "Dear {candidate_name}, see you soon."}           # no {date}, no link
    answer = client.post("/api/sessions/bulk", json={"items": items, "template": broken})
    assert answer.status_code == 400 and "{join_link}" in answer.json()["detail"] and "{date}" in answer.json()["detail"]
    assert client.get(f"/api/sessions?job_id={shortlist['job']['id']}").json() == []
