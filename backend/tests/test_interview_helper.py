"""The AI helper in the interviewer's call: suggested questions with model answers, and a chat.
The fake AI is used (no key). The AI only suggests; code checks its answer; the candidate never reaches it."""
import json

from app.features.interview_helper.services import helper_service
from tests.test_video_call import interview, livekit  # noqa: F401  (a scheduled interview and LiveKit settings)


def test_suggest_questions_with_model_answers(client, interview):  # noqa: F811
    first = client.post(f"/api/sessions/{interview['id']}/helper/questions", json={"topic": "Docker"})
    assert first.status_code == 200
    body = first.json()
    assert body["kind"] == "questions" and body["text"] == "Docker"
    questions = body["questions"]
    assert 1 <= len(questions) <= helper_service.MAX_QUESTIONS
    assert questions[0]["requirement"] == "Docker"                       # the topic comes first
    assert all(q["question"] and q["requirement"] and q["why"] and q["model_answer"] for q in questions)

    again = client.post(f"/api/sessions/{interview['id']}/helper/questions", json={}).json()
    earlier = {q["question"] for q in questions}
    assert not earlier & {q["question"] for q in again["questions"]}     # nothing suggested twice
    history = client.get(f"/api/sessions/{interview['id']}/helper").json()
    assert [m["id"] for m in history] == [body["id"], again["id"]]


def test_code_checks_the_ais_answer(client, interview, monkeypatch):  # noqa: F811
    messy = [{"question": f"Question {i}?", "requirement": "", "why": "w", "model_answer": "m"} for i in range(12)]
    messy[:0] = ["not a question", {"question": "   "}, {"requirement": "no question at all"}]
    monkeypatch.setattr(helper_service, "llm_json", lambda prompt, facts: {"questions": messy})
    questions = client.post(f"/api/sessions/{interview['id']}/helper/questions", json={}).json()["questions"]
    assert len(questions) == helper_service.MAX_QUESTIONS                # at most 8
    assert questions[0] == {"question": "Question 0?", "requirement": "General", "why": "w", "model_answer": "m",
                            "source": ""}


def test_when_the_ai_fails_nothing_is_saved(client, interview, monkeypatch):  # noqa: F811
    monkeypatch.setattr(helper_service, "llm_json", lambda prompt, facts: None)
    failed = client.post(f"/api/sessions/{interview['id']}/helper/questions", json={})
    assert failed.status_code == 502 and "did not answer" in failed.json()["detail"]
    assert client.get(f"/api/sessions/{interview['id']}/helper").json() == []


def test_chat_with_the_helper(client, interview):  # noqa: F811
    mine, theirs = client.post(f"/api/sessions/{interview['id']}/helper/chat",
                               json={"text": "What should I ask about databases?"}).json()
    assert mine["role"] == "interviewer" and mine["text"] == "What should I ask about databases?"
    assert theirs["role"] == "helper" and "1. Ask about" in theirs["text"]
    assert [m["role"] for m in client.get(f"/api/sessions/{interview['id']}/helper").json()] == ["interviewer", "helper"]


def test_the_ai_gets_the_transcript_and_gaps_but_never_the_email(client, anonymous, interview, livekit,  # noqa: F811
                                                                  monkeypatch):
    client.post(f"/api/sessions/{interview['id']}/start")
    with anonymous.websocket_connect(f"/api/join/{interview['token']}/stt") as theirs:   # one transcript sentence
        theirs.send_text(json.dumps({"say": "I mostly used MySQL, not PostgreSQL."}))
        theirs.receive_json()
    seen = {}

    def remember(prompt, facts):
        seen.update(facts)
        return {"answer": "1. Ask about PostgreSQL."}
    monkeypatch.setattr(helper_service, "llm_json", remember)
    client.post(f"/api/sessions/{interview['id']}/helper/chat", json={"text": "Any follow-up?"})
    assert seen["transcript"] == ["Candidate: I mostly used MySQL, not PostgreSQL."]
    assert seen["job"]["title"] == "Backend Developer" and "PostgreSQL" in seen["job"]["required_skills"]
    assert seen["conversation"][-1] == {"from": "interviewer", "text": "Any follow-up?"}
    assert "karima@example.com" not in json.dumps(seen)                  # never the candidate's email address


def test_only_the_interviewer_and_fair_questions(client, anonymous, interview):  # noqa: F811
    assert anonymous.get(f"/api/sessions/{interview['id']}/helper").status_code == 401
    assert anonymous.post(f"/api/sessions/{interview['id']}/helper/questions", json={}).status_code == 401
    assert client.post(f"/api/sessions/{interview['id']}/helper/chat", json={"text": ""}).status_code == 422
    assert client.get("/api/sessions/999999/helper").status_code == 404
    for prompt in (helper_service.QUESTIONS_PROMPT, helper_service.CHAT_PROMPT):
        assert "religion" in prompt and "Never judge voice" in prompt


def test_deleting_the_candidate_deletes_the_helper_messages(client, interview):  # noqa: F811
    client.post(f"/api/sessions/{interview['id']}/helper/chat", json={"text": "Hello"})
    assert client.delete(f"/api/candidates/{interview['candidate_id']}").status_code == 204
    from sqlmodel import Session, select
    from app.core.database import engine
    from app.features.interview_helper.models import HelperMessage
    with Session(engine) as session:
        assert session.exec(select(HelperMessage).where(HelperMessage.session_id == interview["id"])).all() == []


# ---------- RAG: company notes behind the questions ----------

def test_questions_name_the_company_note_they_use(client, interview, monkeypatch):  # noqa: F811
    from sqlmodel import Session
    from app.core.database import engine
    from app.features.job_library.services.company_document_service import add_document
    with Session(engine) as session:
        note = add_document(session, "Backend coding standard", "Every FastAPI endpoint uses Pydantic models and "
                            "Depends() for the database session. Code review before merge.", kind="policy")
        note_id = note.id
    seen = {}
    real = helper_service.find_documents

    def search(session, query, kind, top_k, min_similarity=0.0):
        seen.update(query=query, kind=kind, min_similarity=min_similarity)
        hits = real(session, query, kind, top_k, min_similarity)
        return [h for h in hits if h["title"] == "Backend coding standard"] or hits[:1]
    monkeypatch.setattr(helper_service, "find_documents", search)
    body = client.post(f"/api/sessions/{interview['id']}/helper/questions", json={"topic": "FastAPI"}).json()
    assert seen["kind"] == "policy" and "FastAPI" in seen["query"]              # the topic is part of the search
    assert seen["min_similarity"] == helper_service.MIN_NOTE_SIMILARITY          # unrelated notes are left out
    assert body["questions"][0]["source"] == "Backend coding standard"
    assert body["sources"] == ["Backend coding standard"]
    with Session(engine) as session:                                            # other tests count the notes
        from app.features.job_library.models import CompanyDocument
        session.delete(session.get(CompanyDocument, note_id))
        session.commit()


def test_no_matching_document_and_made_up_sources(client, interview, monkeypatch):  # noqa: F811
    monkeypatch.setattr(helper_service, "find_documents", lambda *args, **kwargs: [])   # nothing similar enough
    seen = {}

    def answer(prompt, facts):
        seen.update(facts)
        return {"questions": [{"question": "How do you review code?", "requirement": "teamwork", "why": "w",
                               "model_answer": "m", "source": "Company handbook"}]}   # a note it never got
    monkeypatch.setattr(helper_service, "llm_json", answer)
    body = client.post(f"/api/sessions/{interview['id']}/helper/questions", json={}).json()
    assert seen["company_notes"] == []
    assert body["questions"][0]["source"] == "" and body["sources"] == []       # the made-up source is removed
    assert "company_notes\" is empty" in helper_service.QUESTIONS_PROMPT        # the AI is told what to do then


def test_chat_answer_lists_one_item_per_line_with_sources(client, interview, monkeypatch):  # noqa: F811
    monkeypatch.setattr(helper_service, "find_documents",
                        lambda *args, **kwargs: [{"title": "Interview guide", "text": "Ask one thing at a time."}])
    reply = client.post(f"/api/sessions/{interview['id']}/helper/chat", json={"text": "Questions?"}).json()[1]
    assert reply["sources"] == ["Interview guide"]
    assert "\n1. " in reply["text"] and "\n2. " in reply["text"]                  # every item on its own line
