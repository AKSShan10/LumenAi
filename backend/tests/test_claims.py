"""CV claim verification (F8): CV claims compared with what the candidate said. Flags are prompts for follow-up
questions, never accusations or decisions. The fake AI is used (no key). Made-up data only."""
from app.ai.fake_llm import fake_answer
from app.features.claims.services import claim_service
from app.features.claims.services.claim_prompts import COMPARE_PROMPT, EXTRACT_PROMPT
from tests.test_qa_analysis import have_the_call
from tests.test_video_call import interview, livekit  # noqa: F401  (a scheduled interview and LiveKit settings)


def check(client, candidate_id: int) -> dict:
    started = client.post(f"/api/candidates/{candidate_id}/claims")
    assert started.status_code == 202 and started.json()["status"] == "running"
    return client.get(f"/api/candidates/{candidate_id}/claims").json()        # the background task has finished


def test_claims_are_compared_with_the_interview(client, anonymous, interview, livekit):  # noqa: F811
    candidate = interview["candidate_id"]
    assert client.get(f"/api/candidates/{candidate}/claims").json()["status"] == "not_started"
    early = client.post(f"/api/candidates/{candidate}/claims")
    assert early.status_code == 409 and "End the interview first" in early.json()["detail"]

    have_the_call(client, anonymous, interview)
    result = check(client, candidate)
    assert result["status"] == "done" and result["session_id"] == interview["id"]
    by_claim = {c["claim"]: c for c in result["claims"]}
    python = by_claim["Works with Python."]
    assert python["status"] == "supported" and python["time"] == 15.0 and python["follow_up"] == ""
    assert python["cv_quote"] == "Skills: Python" and python["interview_quote"] == "I have used Python"
    years = by_claim["Has the stated years of experience."]
    assert years["status"] == "not_discussed" and years["interview_quote"] == "" and years["time"] is None
    assert years["follow_up"]                                                    # a question for the interviewer
    assert [c["status"] for c in result["claims"]][-1] == "supported"            # what needs a follow-up comes first
    runs = client.get("/api/workflow-runs").json()
    assert any(r["stage"] == "claim_check" and r["outcome"] == "done" for r in runs)


def test_a_contradiction_needs_the_candidates_own_words(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    candidate = interview["candidate_id"]
    have_the_call(client, anonymous, interview)

    def compare(prompt, facts):
        if prompt != COMPARE_PROMPT:
            return fake_answer(prompt, facts)
        return {"claims": [
            {"n": 1, "status": "contradicted", "line": 2, "interview_quote": "I have used Python for five years",
             "note": "The candidate lied about the years.", "follow_up": "Why did you fake this?"},
            {"n": 2, "status": "contradicted", "line": 2, "interview_quote": "words the candidate never said",
             "note": "Different.", "follow_up": "Can you explain?"},
            {"n": 3, "status": "unverified", "line": 3, "interview_quote": "PostgreSQL is a database",
             "note": "Only a short answer.", "follow_up": "How did you use PostgreSQL?"}]}
    monkeypatch.setattr(claim_service, "llm_json", compare)
    claims = check(client, candidate)["claims"]
    first, second, third = (next(c for c in claims if c["claim"] == name) for name in
                            ("Works with Python.", "Works with FastAPI.", "Works with PostgreSQL."))
    assert first["status"] == "contradicted" and first["time"] == 15.0          # proven by the candidate's words
    assert "lied" not in first["note"] and "fake" not in first["follow_up"]      # accusing words replaced
    assert first["note"] == claim_service.NEUTRAL_NOTE["contradicted"]
    assert second["status"] == "not_discussed" and second["interview_quote"] == ""   # no proof: no contradiction
    assert third["status"] == "unverified" and third["time"] == 25.0
    assert claims[0]["status"] == "contradicted"


def test_made_up_cv_quotes_are_dropped_and_failures_are_explained(client, anonymous, interview, livekit,  # noqa: F811
                                                                  monkeypatch):
    candidate = interview["candidate_id"]
    have_the_call(client, anonymous, interview)

    def extract(prompt, facts):
        if prompt == EXTRACT_PROMPT:
            return {"claims": [{"claim": "Led a team of ten.", "cv_quote": "led a team of ten engineers"},
                               {"claim": "Works with Python.", "cv_quote": "Skills: Python"}]}
        return fake_answer(prompt, facts)
    monkeypatch.setattr(claim_service, "llm_json", extract)
    assert [c["claim"] for c in check(client, candidate)["claims"]] == ["Works with Python."]

    monkeypatch.setattr(claim_service, "llm_json", lambda prompt, facts: None)
    failed = check(client, candidate)
    assert failed["status"] == "failed" and "did not answer" in failed["error"]


def test_access_privacy_and_fair_wording(client, anonymous, interview, livekit):  # noqa: F811
    candidate = interview["candidate_id"]
    assert anonymous.get(f"/api/candidates/{candidate}/claims").status_code == 401
    assert client.get("/api/candidates/999999/claims").status_code == 404
    for prompt in (EXTRACT_PROMPT, COMPARE_PROMPT):
        assert "never accusations" in prompt and "never say whether to hire" in prompt
    have_the_call(client, anonymous, interview)
    check(client, candidate)
    assert client.delete(f"/api/candidates/{candidate}").status_code == 204
    from sqlmodel import Session, select
    from app.core.database import engine
    from app.features.claims.models import ClaimCheck
    with Session(engine) as session:
        assert session.exec(select(ClaimCheck).where(ClaimCheck.candidate_id == candidate)).all() == []
