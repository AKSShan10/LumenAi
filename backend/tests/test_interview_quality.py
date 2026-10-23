"""Interview quality assessment (F10): the quality of the interview process itself, not of the candidate.
The fake AI is used (no key). Code measures the facts; every recommendation must rest on one. Made-up data only."""
from app.ai.fake_llm import fake_answer
from app.graphs import interview_quality_graph as quality_graph
from app.graphs.interview_quality_prompts import FAIR, GRADE_QUESTIONS_PROMPT, RECOMMEND_PROMPT
from tests.test_qa_analysis import analyse, have_the_call
from tests.test_video_call import interview, livekit  # noqa: F401  (a scheduled interview and LiveKit settings)


def check(client, interview) -> dict:  # noqa: F811
    started = client.post(f"/api/sessions/{interview['id']}/quality")
    assert started.status_code == 202 and started.json()["status"] == "running"
    return client.get(f"/api/sessions/{interview['id']}/quality").json()     # the background task has finished


def test_the_interview_process_is_assessed(client, anonymous, interview, livekit):  # noqa: F811
    session = interview["id"]
    assert client.get(f"/api/sessions/{session}/quality").json()["status"] == "not_started"
    have_the_call(client, anonymous, interview)
    early = client.post(f"/api/sessions/{session}/quality")
    assert early.status_code == 409 and "Analyse the answers first" in early.json()["detail"]

    analyse(client, interview)
    result = check(client, interview)
    assert result["status"] == "done" and result["error"] == ""

    # speaking time from the transcript times: 4 interviewer and 4 candidate lines of 4 seconds each
    talk = result["talk"]
    assert talk["interviewer_sec"] == 16 and talk["candidate_sec"] == 16
    assert talk["interviewer_share"] == 50 and talk["balanced"] is False and talk["longest_interviewer_sec"] == 4

    # coverage: Python and FastAPI were shown; PostgreSQL was asked, but the answer showed nothing
    states = {c["requirement"]: c["state"] for c in result["coverage"]}
    assert states == {"Python": "shown", "FastAPI": "shown", "PostgreSQL": "no_signal"}

    # the questions: small talk is not reviewed; the short PostgreSQL answers gave little signal
    questions = result["questions"]
    assert [q["n"] for q in questions] == [2, 3, 4]
    assert [q["signal"] for q in questions] == ["good", "low", "low"]
    assert "answer of 4 words" in questions[1]["signal_reason"]
    assert questions[0]["relevance"] == 80 and questions[2]["relevance"] == 40

    scores = {s["key"]: s["score"] for s in result["scores"]}
    assert scores["coverage"] == 100 and scores["signal"] == round(100 / 3, 1)
    assert scores["balance"] == 75                                     # 50 % → 100 - (50 - 40) × 2.5
    assert scores["consistency"] is None                               # only one interview for this job
    measured = [v for v in scores.values() if v is not None]
    assert result["quality_score"] == round(sum(measured) / len(measured), 1)

    recs = result["recommendations"]
    assert [r["basis"] for r in recs] == ["question", "question", "talk"]
    assert recs[0]["ref"] == "3" and recs[0]["time"] == questions[1]["time"]
    assert result["summary"]
    runs = client.get("/api/workflow-runs").json()
    assert any(r["stage"] == "interview_quality" and r["outcome"] == "done" for r in runs)


def test_every_recommendation_needs_a_measured_fact(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    have_the_call(client, anonymous, interview)
    analyse(client, interview)

    def invented(instructions, data):
        if instructions != RECOMMEND_PROMPT:
            return fake_answer(instructions, data)
        return {"summary": "A fair interview.", "recommendations": [
            {"basis": "requirement", "ref": "Kubernetes", "text": "Ask about Kubernetes."},  # not a job requirement
            {"basis": "question", "ref": "2", "text": "Improve question 2."},                # question 2 was fine
            {"basis": "talk", "ref": "", "text": "Your voice sounded nervous."},              # judges a person
            {"basis": "question", "ref": "3", "text": "Ask how PostgreSQL was used."}]}       # a real fact
    monkeypatch.setattr(quality_graph, "llm_json", invented)
    result = check(client, interview)
    assert [(r["basis"], r["ref"]) for r in result["recommendations"]] == [("question", "3")]

    monkeypatch.setattr(quality_graph, "llm_json", lambda i, d: fake_answer(i, d) if i != RECOMMEND_PROMPT else None)
    fallback = check(client, interview)                                # the AI failed: code writes them from the facts
    assert fallback["status"] == "done"
    assert {r["basis"] for r in fallback["recommendations"]} == {"requirement", "question", "talk"}
    assert "Interview quality" in fallback["summary"]


def test_when_the_question_review_fails_the_reason_is_shown(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    have_the_call(client, anonymous, interview)
    analyse(client, interview)
    monkeypatch.setattr(quality_graph, "llm_json", lambda i, d: None if i == GRADE_QUESTIONS_PROMPT else fake_answer(i, d))
    result = check(client, interview)
    assert result["status"] == "failed" and "did not review the questions" in result["error"]


def test_talk_time_and_consistency_are_counted_by_code():
    turns = [{"speaker": "interviewer", "start": 0, "end": 10}, {"speaker": "interviewer", "start": 10, "end": 30},
             {"speaker": "candidate", "start": 30, "end": 40}]
    talk = quality_graph._talk(turns)
    assert talk["interviewer_share"] == 75 and talk["longest_interviewer_sec"] == 30   # two lines without a break
    assert quality_graph._balance_score(30) == 100 and quality_graph._balance_score(80) == 0

    state = {"requirements": ["Python", "Docker", "SQL"],
             "interviews": [{"asked": ["Python", "Docker"]}, {"asked": ["Python"]}, {"asked": ["Python", "Docker"]}]}
    consistency = quality_graph.compare_consistency(state)["consistency"]
    assert consistency["uneven"] == ["Docker"]                          # SQL was asked in none: treated the same
    assert consistency["score"] == round(100 * 2 / 3, 1)
    assert quality_graph.compare_consistency({**state, "interviews": state["interviews"][:1]})["consistency"]["score"] is None


def test_access_privacy_and_fair_rules(client, anonymous, interview, livekit):  # noqa: F811
    session = interview["id"]
    assert anonymous.get(f"/api/sessions/{session}/quality").status_code == 401
    assert client.get("/api/sessions/999999/quality").status_code == 404
    for prompt in (GRADE_QUESTIONS_PROMPT, RECOMMEND_PROMPT):
        assert FAIR in prompt and "never say whether to hire" in prompt
    have_the_call(client, anonymous, interview)
    analyse(client, interview)
    check(client, interview)
    assert client.delete(f"/api/candidates/{interview['candidate_id']}").status_code == 204
    from sqlmodel import Session, select
    from app.core.database import engine
    from app.features.interview_quality.models import InterviewQuality
    with Session(engine) as db:
        assert db.exec(select(InterviewQuality).where(InterviewQuality.session_id == session)).all() == []
