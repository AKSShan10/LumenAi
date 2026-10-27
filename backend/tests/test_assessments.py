"""The consolidated assessment (F6): the CV screening and the interview analysis become one report per candidate.
The fake AI is used (no key). The AI writes, code checks every quote and works out the overall score; only a person
decides. Made-up data only."""
from app.ai.fake_llm import fake_answer
from app.core import config
from app.graphs import assessment_graph
from app.graphs.assessment_prompts import (
    AREAS_PROMPT, REPAIR_PROMPT, STRENGTHS_PROMPT, SUMMARY_PROMPT, WEAKNESSES_PROMPT)
from tests.test_qa_analysis import analyse, have_the_call
from tests.test_video_call import interview, livekit  # noqa: F401  (a scheduled interview and LiveKit settings)


def assess(client, candidate_id: int) -> dict:
    started = client.post(f"/api/candidates/{candidate_id}/assessment")
    assert started.status_code == 202 and started.json()["status"] == "running"
    return client.get(f"/api/candidates/{candidate_id}/assessment").json()     # the background task has finished


def ready(client, anonymous, interview) -> int:  # noqa: F811
    """An ended interview whose answers are analysed. Returns the candidate id."""
    have_the_call(client, anonymous, interview)
    analyse(client, interview)
    return interview["candidate_id"]


def test_the_report_combines_cv_and_interview(client, anonymous, interview, livekit):  # noqa: F811
    candidate = interview["candidate_id"]
    assert client.get(f"/api/candidates/{candidate}/assessment").json()["status"] == "not_started"
    early = client.post(f"/api/candidates/{candidate}/assessment")
    assert early.status_code == 409 and "Analyse the interview answers first" in early.json()["detail"]

    ready(client, anonymous, interview)
    report = assess(client, candidate)
    assert report["status"] == "done" and report["error"] == ""
    analysis = client.get(f"/api/sessions/{interview['id']}/analysis").json()
    assert report["interview_score"] == analysis["interview_score"] and report["cv_score"] is not None
    weight = config.ASSESSMENT_CV_WEIGHT
    assert report["overall_score"] == round(report["cv_score"] * weight / 100
                                            + report["interview_score"] * (100 - weight) / 100, 1)
    assert report["summary"] and report["decision"] == "pending"
    assert report["strengths"] and report["weaknesses"] and report["recommended_areas"]
    for item in report["strengths"] + report["weaknesses"]:
        assert item["quote"] and item["source"] in ("CV", "Interview")
    assert report["repair_rounds"] == 0                                         # every quote was found at once

    rows = client.get(f"/api/jobs/{report['job_id']}/comparison").json()
    assert rows[0]["candidate_id"] == candidate and rows[0]["overall_score"] == report["overall_score"]


def test_quotes_without_proof_are_repaired_or_removed(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    candidate = ready(client, anonymous, interview)
    calls = {"repair": 0}

    def made_up(prompt, facts):
        answer = fake_answer(prompt, facts)
        if prompt == STRENGTHS_PROMPT:
            answer["strengths"].append({"text": "Led a team of ten.", "quote": "I led a team of ten engineers",
                                        "source": "CV"})                         # never said, not in the CV
        if prompt == REPAIR_PROMPT:
            calls["repair"] += 1
            answer = {"strengths": facts["strengths"], "weaknesses": facts["weaknesses"]}   # the AI does not fix it
        return answer
    monkeypatch.setattr(assessment_graph, "llm_json", made_up)
    report = assess(client, candidate)
    assert report["status"] == "done" and calls["repair"] == 2 and report["repair_rounds"] == 2   # at most 2 rounds
    assert "Led a team of ten." not in [s["text"] for s in report["strengths"]]                  # then removed


def test_code_writes_where_the_quote_was_found(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    candidate = ready(client, anonymous, interview)

    def wrong_source(prompt, facts):
        answer = fake_answer(prompt, facts)
        if prompt == STRENGTHS_PROMPT:
            for item in answer["strengths"]:
                item["source"] = "Interview"                                    # the AI says Interview for all
        return answer
    monkeypatch.setattr(assessment_graph, "llm_json", wrong_source)
    strengths = assess(client, candidate)["strengths"]
    assert {"CV", "Interview"} == {s["source"] for s in strengths}              # code corrected the CV ones


def test_when_the_ai_fails_the_reason_is_shown(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    candidate = ready(client, anonymous, interview)
    monkeypatch.setattr(assessment_graph, "llm_json",
                        lambda prompt, facts: None if prompt == WEAKNESSES_PROMPT else fake_answer(prompt, facts))
    report = assess(client, candidate)
    assert report["status"] == "failed" and "did not answer" in report["error"]

    monkeypatch.setattr(assessment_graph, "llm_json",
                        lambda prompt, facts: None if prompt == SUMMARY_PROMPT else fake_answer(prompt, facts))
    report = assess(client, candidate)
    assert report["status"] == "failed" and "summary" in report["error"]


def test_only_a_person_decides(client, anonymous, interview, livekit):  # noqa: F811
    candidate = interview["candidate_id"]
    early = client.put(f"/api/candidates/{candidate}/assessment/decision", json={"decision": "hire"})
    assert early.status_code == 409                                              # no report yet
    ready(client, anonymous, interview)
    assess(client, candidate)
    decided = client.put(f"/api/candidates/{candidate}/assessment/decision",
                         json={"decision": "hold", "note": "Second interview for PostgreSQL."}).json()
    assert decided["decision"] == "hold" and decided["decision_note"] == "Second interview for PostgreSQL."
    assert decided["decided_by"] == "interviewer@example.com" and decided["decided_at"]
    again = assess(client, candidate)
    assert again["decision"] == "hold"                                           # a new report keeps the decision
    undone = client.put(f"/api/candidates/{candidate}/assessment/decision", json={"decision": "pending"}).json()
    assert undone["decision"] == "pending" and undone["decided_by"] == "" and undone["decided_at"] is None
    assert client.put(f"/api/candidates/{candidate}/assessment/decision", json={"decision": "maybe"}).status_code == 422
    assert anonymous.get(f"/api/candidates/{candidate}/assessment").status_code == 401
    assert anonymous.get(f"/api/jobs/{interview['job_id']}/comparison").status_code == 401
    assert client.get("/api/candidates/999999/assessment").status_code == 404
    assert client.get("/api/jobs/999999/comparison").status_code == 404


def test_the_weight_comes_from_the_settings(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    candidate = ready(client, anonymous, interview)
    monkeypatch.setattr(config, "ASSESSMENT_CV_WEIGHT", 50)
    report = assess(client, candidate)
    assert report["cv_weight"] == 50
    assert report["overall_score"] == round((report["cv_score"] + report["interview_score"]) / 2, 1)


def test_evidence_gaps_are_found_by_code():
    state = {"requirements": ["Python", "Docker", "Redis"], "cv_proof": ["Python"], "covered": ["Docker"]}
    assert assessment_graph._gaps(state) == ["Redis"]                          # not in the CV and not shown


def test_fair_rules_are_in_every_prompt():
    for prompt in (STRENGTHS_PROMPT, WEAKNESSES_PROMPT, AREAS_PROMPT, REPAIR_PROMPT, SUMMARY_PROMPT):
        assert "Never say whether to hire" in prompt and "Never judge voice" in prompt


def test_deleting_the_candidate_deletes_the_assessment(client, anonymous, interview, livekit):  # noqa: F811
    candidate = ready(client, anonymous, interview)
    assess(client, candidate)
    assert client.delete(f"/api/candidates/{candidate}").status_code == 204
    from sqlmodel import Session, select
    from app.core.database import engine
    from app.features.assessments.models import Assessment
    with Session(engine) as session:
        assert session.exec(select(Assessment).where(Assessment.candidate_id == candidate)).all() == []


def test_the_interviewer_changes_the_weight_of_a_job(client, anonymous, interview, livekit):  # noqa: F811
    candidate = ready(client, anonymous, interview)
    report = assess(client, candidate)
    assert report["cv_weight"] == 40                                            # the default: CV 40 %, interview 60 %
    client.put(f"/api/candidates/{candidate}/assessment/decision", json={"decision": "hold", "note": "Check SQL."})

    rows = client.put(f"/api/jobs/{report['job_id']}/assessment-weight", json={"cv_weight": 30})
    assert rows.status_code == 200 and rows.json()[0]["cv_weight"] == 30
    changed = client.get(f"/api/candidates/{candidate}/assessment").json()
    assert changed["cv_weight"] == 30                                           # recalculated by code, no AI call
    assert changed["overall_score"] == round(report["cv_score"] * 0.3 + report["interview_score"] * 0.7, 1)
    assert changed["summary"] == report["summary"] and changed["decision"] == "hold"   # report and decision kept

    again = assess(client, candidate)                                           # a new report uses the job's weight
    assert again["cv_weight"] == 30

    for wrong in (-1, 101):
        assert client.put(f"/api/jobs/{report['job_id']}/assessment-weight", json={"cv_weight": wrong}).status_code == 422
    assert anonymous.put(f"/api/jobs/{report['job_id']}/assessment-weight", json={"cv_weight": 50}).status_code == 401
    assert client.put("/api/jobs/999999/assessment-weight", json={"cv_weight": 50}).status_code == 404


def test_interview_quotes_link_to_the_transcript(client, anonymous, interview, livekit):  # noqa: F811
    candidate = ready(client, anonymous, interview)
    report = assess(client, candidate)
    turns = client.get(f"/api/sessions/{interview['id']}/transcript").json()
    items = report["strengths"] + report["weaknesses"]
    assert any(i["source"] == "Interview" for i in items) and any(i["source"] == "CV" for i in items)
    for item in items:
        if item["source"] == "CV":
            assert item["time"] is None                                          # a CV quote has no time
        else:                                                                    # the sentence that has the quote
            said = next(t for t in turns if t["start_sec"] == item["time"])
            assert said["speaker"] == "candidate" and item["quote"].split()[0] in said["text"]


def test_every_area_to_explore_has_a_checked_basis(client, anonymous, interview, livekit, monkeypatch):  # noqa: F811
    candidate = ready(client, anonymous, interview)

    def areas(prompt, facts):
        if prompt != AREAS_PROMPT:
            return fake_answer(prompt, facts)
        python = facts["job"]["required_skills"][0]
        return {"areas": [
            {"area": "Depth", "why": "Short answer.", "requirement": python.upper(), "quote": "words never said"},
            {"area": "Database design", "why": "Weak answer.", "requirement": "", "quote": "PostgreSQL is a database"},
            {"area": "Leadership", "why": "Not discussed.", "requirement": "Leadership", "quote": ""}]}  # no basis
    monkeypatch.setattr(assessment_graph, "llm_json", areas)
    found = assess(client, candidate)["recommended_areas"]
    assert [a["area"] for a in found] == ["Depth", "Database design"]            # the one with no basis is left out
    assert found[0]["requirement"] and found[0]["quote"] == "" and found[0]["source"] == ""   # job name, quote removed
    assert found[1]["source"] == "Interview" and found[1]["time"] == 25.0        # the transcript line it was said


def test_the_report_shows_the_parts_behind_the_scores(client, anonymous, interview, livekit):  # noqa: F811
    candidate = ready(client, anonymous, interview)
    report = assess(client, candidate)
    analysis = client.get(f"/api/sessions/{interview['id']}/analysis").json()
    graded = [i for i in analysis["items"] if i["job_related"]]
    parts = {p["name"]: p["score"] for p in report["interview_parts"]}
    assert list(parts) == ["Technical competency", "Communication", "Relevance of responses",      # F9 scorecard
                           "Problem-solving approach", "Depth of experience demonstrated", "Alignment with job requirements"]
    assert parts["Technical competency"] == round(sum(i["accuracy"] for i in graded) / len(graded), 1)
    assert all(p["reason"] for p in report["interview_parts"])
    assert {p["name"] for p in report["cv_parts"]} <= {"Skills", "Experience", "Qualifications"} and report["cv_parts"]
    rows = {r["requirement"]: r for r in report["requirements"]}
    for name in analysis["covered"]:
        assert rows[name]["interview"] is True                                   # shown in the interview
    for name in analysis["uncovered"]:
        assert rows[name]["interview"] is False
    assert all(r["cv"] in ("met", "partial", "unmet", "unchecked") for r in rows.values())
