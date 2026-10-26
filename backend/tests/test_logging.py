"""The log: one line for every API call, kept in a file, with no private text in it."""
import logging

from app.core.logging_setup import setup_logging


def lines(caplog, name) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == name]


def test_every_api_call_is_logged_with_its_result(client, caplog):
    caplog.set_level(logging.INFO)
    client.get("/api/health")
    client.get("/api/jobs/999999")
    client.post("/api/assistant/actions/999999", json={})
    api = lines(caplog, "api")
    assert any(line.startswith("GET /api/health 200 ") and line.endswith("ms") for line in api)
    assert any(line.startswith("GET /api/jobs/999999 404 ") for line in api)          # failures are logged too
    assert any(line.startswith("POST /api/assistant/actions/999999 422 ") for line in api)


def test_the_log_has_no_private_text(client, anonymous, caplog):
    caplog.set_level(logging.INFO)
    client.get("/api/company-documents/search", params={"q": "secret words typed by the interviewer"})
    anonymous.post("/api/auth/login", json={"email": "interviewer@example.com", "password": "a-wrong-passcode"})
    everything = " ".join(record.getMessage() for record in caplog.records)
    assert "GET /api/company-documents/search 200" in everything
    assert "POST /api/auth/login 401" in everything
    assert "secret" not in everything and "a-wrong-passcode" not in everything and "test-passcode" not in everything
    assert "interviewer@example.com" not in everything                     # the email is not logged either


def test_a_job_post_is_logged(make_job, caplog):
    from sqlmodel import Session
    from app.core.database import engine
    from app.features.jobs.models import Job
    from app.features.jobs.services.job_posting_service import post_job
    job = make_job(approve=True, title="Log Tester", description="A made-up job that is used to test the log file.")
    caplog.set_level(logging.INFO)
    with Session(engine) as session:
        post_job(session, session.get(Job, job["id"]), "Log Tester wanted for a made-up team.",
                 "https://docs.google.com/forms/made-up")
    assert f"blogger post job={job['id']} posted" in lines(caplog, "job_posting")


def test_log_lines_are_saved_in_a_file(tmp_path):
    log_file = tmp_path / "logs" / "lumenai.log"
    setup_logging(str(log_file))
    setup_logging(str(log_file))                                   # a second call adds no second handler
    root = logging.getLogger()
    try:
        logging.getLogger("api").info("GET /api/health 200 3ms")
        text = log_file.read_text(encoding="utf-8")
        assert text.count("GET /api/health 200 3ms") == 1 and " INFO api: " in text
    finally:
        for handler in list(root.handlers):                        # do not keep writing to the test folder
            if getattr(handler, "baseFilename", "") == str(log_file):
                root.removeHandler(handler)
                handler.close()


def test_log_time_is_shown_in_bangladesh_time():
    """A container runs on UTC; the log shows the time of LOG_TIME_ZONE (Bangladesh = UTC+6)."""
    from app.core.logging_setup import use_time_zone
    old = logging.Formatter.__dict__["converter"]                  # as stored (a staticmethod), so it can be put back
    try:
        use_time_zone("Asia/Dhaka")
        record = logging.makeLogRecord({"msg": "x"})
        record.created = 1793000000.0                              # 2026-10-26 07:33:20 UTC
        assert logging.Formatter("%(asctime)s").format(record).startswith("2026-10-26 13:33:20")
        use_time_zone("Mars/Base")                                 # unknown: nothing changes, no crash
        assert logging.Formatter("%(asctime)s").format(record).startswith("2026-10-26 13:33:20")
    finally:
        logging.Formatter.converter = old
