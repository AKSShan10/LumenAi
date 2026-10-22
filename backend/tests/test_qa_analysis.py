"""The Q&A analysis (F5): after the interview, the transcript becomes graded questions and answers.
The fake AI is used (no key). The AI suggests the grades, code checks them. Made-up data only."""
from app.ai.fake_llm import fake_answer
from app.graphs import qa_analysis_graph
from app.graphs.qa_analysis_prompts import FAIR, GRADE_PROMPTS, SEGMENT_PROMPT
from tests.test_video_call import interview, livekit  # noqa: F401  (a scheduled interview and LiveKit settings)

CALL = [("interviewer", "Hello Karima, can you hear me?"),
        ("candidate", "Yes, I can hear you well."),
        ("interviewer", "Tell me about your experience with Python?"),
        ("candidate", "I have used Python for five years to build web services with FastAPI and Celery."),
        ("interviewer", "What is PostgreSQL and how did you use it in your last project?"),
        ("candidate", "PostgreSQL is a database."),
        ("interviewer", "Thank you. Do you have any questions for us?"),
        ("candidate", "No, thank you.")]


def have_the_call(client, anonymous, interview, lines=CALL):  # noqa: F811
    """Starts and ends the call, and saves the transcript lines 5 seconds apart (the live microphones are tested in
    test_transcript.py; here fixed times keep the order the same on every run)."""
    from sqlmodel import Session
    from app.core.database import engine
    from app.features.transcripts.models import TranscriptTurn
    client.post(f"/api/sessions/{interview['id']}/start")
    with Session(engine) as session:
        for n, (speaker, text) in enumerate(lines):
            session.add(TranscriptTurn(session_id=interview["id"], speaker=speaker, start_sec=n * 5.0,
                                       end_sec=n * 5.0 + 4, text=text))
        session.commit()
    client.post(f"/api/sessions/{interview['id']}/end")


def analyse(client, interview) -> dict:  # noqa: F811
    started = client.post(f"/api/sessions/{interview['id']}/analysis")
    assert started.status_code == 202 and started.json()["status"] == "running"
    return client.get(f"/api/sessions/{interview['id']}/analysis").json()    # the background task has finished


def test_the_answers_are_graded(client, anonymous, interview, livekit):  # noqa: F811
    have_the_call(client, anonymous, interview)
    result = analyse(client, interview)
    assert result["status"] == "done" and result["error"] == ""
    items = result["items"]
    assert [i["job_related"] for i in items] == [False, True, True, True, False]         # greetings: small talk
    assert items[0]["score"] is None and items[0]["relevance"] is None                   # kept, not graded
    assert [i["split_from_multi_part"] for i in items] == [False, False, True, True, False]
    assert items[2]["question"] == "What is PostgreSQL?" and items[3]["question"].startswith("How did you use it")

    python = items[1]
    assert python["answer"] == CALL[3][1]                                                # the candidate's own words
    assert python["requirements"] == ["Python", "FastAPI"]
    assert [python[c] for c in ("relevance", "accuracy", "completeness", "articulation")] == [75, 75, 75, 75]
    assert python["score"] == 75 and set(python["reasons"]) == {"relevance", "accuracy", "completeness", "articulation"}
    assert python["evidence_quote"] == "I have used Python" and python["evidence_time"] == 15.0

    assert items[2]["score"] == 25 and items[2]["requirements"] == ["PostgreSQL"]
    assert python["follow_up"] == "" and items[2]["follow_up"]                     # a follow-up for a weak answer
    assert items[0]["follow_up"] == ""                                                # small talk gets none
    assert result["interview_score"] == round((75 + 25 + 25) / 3, 1)                     # job-related answers only
    assert result["covered"] == ["Python", "FastAPI"] and result["uncovered"] == ["PostgreSQL"]

    row = client.get(f"/api/sessions/{interview['id']}").json()                  # the Interviews list shows it
    assert row["analysis_status"] == "done" and row["interview_score"] == result["interview_score"]

    again = analyse(client, interview)                                                   # a new run replaces the old
    assert len(again["items"]) == len(items)


def test_code_checks_the_ais_answer(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    have_the_call(client, anonymous, interview)

    def made_up(prompt, facts):
        answer = fake_answer(prompt, facts)
        if prompt == SEGMENT_PROMPT:
            answer["pairs"].append({"question": "Who said this?", "answer_lines": [1, 3], "job_related": True})
        if prompt in GRADE_PROMPTS.values():
            for grade in answer["grades"]:
                grade.update(grade=60, quote="words the candidate never said")
        return answer
    monkeypatch.setattr(qa_analysis_graph, "llm_json", made_up)
    items = analyse(client, interview)["items"]
    assert "Who said this?" not in [i["question"] for i in items]       # interviewer lines are never an answer
    assert items[1]["relevance"] == 60                                  # any whole grade from 0 to 100 is kept
    assert items[1]["evidence_quote"] == "" and items[1]["evidence_time"] is None    # a made-up quote is removed


def test_when_the_ai_fails_the_reason_is_shown(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    have_the_call(client, anonymous, interview)
    monkeypatch.setattr(qa_analysis_graph, "llm_json", lambda prompt, facts: None)
    result = analyse(client, interview)
    assert result["status"] == "failed" and "did not answer" in result["error"] and result["items"] == []

    def no_accuracy(prompt, facts):                                     # one of the four graders fails
        return None if prompt == GRADE_PROMPTS["accuracy"] else fake_answer(prompt, facts)
    monkeypatch.setattr(qa_analysis_graph, "llm_json", no_accuracy)
    result = analyse(client, interview)
    assert result["status"] == "failed" and "did not grade" in result["error"]


def test_nothing_said_by_the_candidate(client, anonymous, interview, livekit):  # noqa: F811
    have_the_call(client, anonymous, interview, lines=[("interviewer", "Are you there?")])
    result = analyse(client, interview)
    assert result["status"] == "failed" and "Nothing the candidate said" in result["error"]


def test_accuracy_uses_company_documents(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    from sqlmodel import Session
    from app.core.database import engine
    from app.features.job_library.models import CompanyDocument
    from app.features.job_library.services.company_document_service import add_document
    with Session(engine) as session:
        note_id = add_document(session, "Python guide", "Our Python services use FastAPI and PostgreSQL.",
                               kind="policy").id
    have_the_call(client, anonymous, interview)

    def with_made_up_source(prompt, facts):
        answer = fake_answer(prompt, facts)
        if prompt == GRADE_PROMPTS["accuracy"]:
            assert [n["title"] for n in facts["company_notes"]] == ["Python guide"]     # the RAG search found it
            answer["grades"][0]["sources"].append("Company handbook")                  # a document it never got
        return answer
    monkeypatch.setattr(qa_analysis_graph, "llm_json", with_made_up_source)
    try:
        items = analyse(client, interview)["items"]
        assert items[1]["references"] == ["Python guide"]               # the made-up one is removed
        assert items[0]["references"] == []                             # small talk is not graded
    finally:
        with Session(engine) as session:                                # other tests count the documents
            session.delete(session.get(CompanyDocument, note_id))
            session.commit()


def test_only_the_interviewer_and_only_after_the_call(client, anonymous, interview):  # noqa: F811
    assert client.get(f"/api/sessions/{interview['id']}/analysis").json()["status"] == "not_started"
    early = client.post(f"/api/sessions/{interview['id']}/analysis")
    assert early.status_code == 409 and "End the interview first" in early.json()["detail"]
    assert anonymous.get(f"/api/sessions/{interview['id']}/analysis").status_code == 401
    assert anonymous.post(f"/api/sessions/{interview['id']}/analysis").status_code == 401
    assert client.get("/api/sessions/999999/analysis").status_code == 404


def test_fair_grading_rules_are_in_the_prompts():
    for prompt in GRADE_PROMPTS.values():
        assert FAIR in prompt and "Never judge voice" in prompt
    assert "never about how the candidate sounds" in GRADE_PROMPTS["articulation"]
    assert "speech-to-text" in SEGMENT_PROMPT and "clearly misheard" in FAIR    # misheard words are not punished


def test_deleting_the_candidate_deletes_the_analysis(client, anonymous, interview, livekit):  # noqa: F811
    have_the_call(client, anonymous, interview)
    analyse(client, interview)
    assert client.delete(f"/api/candidates/{interview['candidate_id']}").status_code == 204
    from sqlmodel import Session, select
    from app.core.database import engine
    from app.features.qa_analysis.models import QaAnalysis, QaItem
    with Session(engine) as session:
        assert session.exec(select(QaItem).where(QaItem.session_id == interview["id"])).all() == []
        assert session.exec(select(QaAnalysis).where(QaAnalysis.session_id == interview["id"])).all() == []


def test_answers_analysed_before_the_follow_up_column_still_load(client, anonymous, interview, livekit):  # noqa: F811
    """Rows made before migration 0030 have follow_up = NULL; the page must still load them."""
    from sqlmodel import Session, select
    from app.core.database import engine
    from app.features.qa_analysis.models import QaItem
    have_the_call(client, anonymous, interview)
    analyse(client, interview)
    with Session(engine) as session:
        for item in session.exec(select(QaItem).where(QaItem.session_id == interview["id"])).all():
            item.follow_up = None                                    # as in an old row
            session.add(item)
        session.commit()
    answer = client.get(f"/api/sessions/{interview['id']}/analysis")
    assert answer.status_code == 200 and all(i["follow_up"] == "" for i in answer.json()["items"])


def test_grades_are_whole_numbers_from_0_to_100():
    grade = qa_analysis_graph._grade
    assert [grade(60), grade("72.6"), grade(120), grade(-5)] == [60, 73, 100, 0]   # kept, rounded or capped
    assert grade("good") is None and grade(None) is None                           # not a number: skipped
