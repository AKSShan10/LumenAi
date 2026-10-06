"""The job description workflow: retrieve documents -> write -> check -> (revise) -> log."""
from app.graphs import job_description_graph as workflow
from app.graphs.job_description_graph import clean_draft, find_problems, write_job_draft
from app.graphs.job_description_prompts import JOB_DRAFT_PROMPT, JOB_REVISE_PROMPT

PROMPT = "Backend developer with Python, FastAPI and Docker, 3 years experience, BSc in CSE"
GOOD_TEXT = " ".join(["word"] * 120)


def good_draft(**changes) -> dict:
    return {"title": "Backend Developer", "required_skills": ["Python"], "preferred_skills": [], "min_years": 3,
            "qualifications": "BSc in CSE", "description": GOOD_TEXT, **changes}


def test_steps_of_the_workflow():
    steps = [name for name in workflow.job_description_graph.get_graph().nodes if not name.startswith("__")]
    assert steps == ["retrieve_documents", "write_draft", "check_draft", "revise_draft", "log_run"]


def test_the_check_finds_plain_problems():
    assert find_problems(good_draft(), PROMPT) == []
    assert "the job title is missing" in find_problems(good_draft(title=""), PROMPT)
    assert "no required skills were found" in find_problems(good_draft(required_skills=[]), PROMPT)
    assert any("too short" in p for p in find_problems(good_draft(description="Too short."), PROMPT))
    assert any("too long" in p for p in find_problems(good_draft(description=" ".join(["word"] * 300)), PROMPT))
    paid = good_draft(description=GOOD_TEXT + " Salary: 90,000 BDT.")
    assert any("pay" in p for p in find_problems(paid, PROMPT))
    assert find_problems(paid, PROMPT + ", salary 90,000 BDT") == []          # the prompt gave it, so it is allowed


def test_the_answer_is_cut_to_the_job_form():
    draft = clean_draft({"title": " Backend Developer ", "required_skills": ["Python", "", "Python", 7],
                         "preferred_skills": "Docker", "min_years": "many", "description": None})
    assert draft == {"title": "Backend Developer", "required_skills": ["Python", "7"], "preferred_skills": [],
                     "min_years": 0, "qualifications": "", "description": ""}


def test_a_good_draft_is_not_revised(client):
    result = write_job_draft(PROMPT)
    assert result["error"] == "" and result["problems"] == [] and result["revisions"] == 0
    assert result["draft"]["title"] == "Backend Developer"
    last_run = client.get("/api/workflow-runs?limit=1").json()[0]
    assert last_run["stage"] == "job_description" and last_run["outcome"] == "done"


def test_a_bad_draft_goes_back_to_the_ai_once(client, monkeypatch):
    asked = []

    def ai(instructions, data):
        asked.append(instructions)
        if instructions == JOB_DRAFT_PROMPT:
            return good_draft(description="Too short.")                       # the first draft fails the check
        assert data["problems"] and "too short" in data["problems"][0]        # the AI is told what to fix
        return good_draft()
    monkeypatch.setattr(workflow, "llm_json", ai)

    result = write_job_draft(PROMPT)
    assert asked == [JOB_DRAFT_PROMPT, JOB_REVISE_PROMPT]
    assert result["revisions"] == 1 and result["problems"] == []


def test_problems_that_stay_are_shown_to_the_interviewer(client, monkeypatch):
    monkeypatch.setattr(workflow, "llm_json", lambda instructions, data: good_draft(required_skills=[]))
    draft = client.post("/api/jobs/draft-from-prompt", json={"prompt": PROMPT}).json()
    assert draft["from_ai"] is True and draft["revisions"] == 1               # revised once, then it stops
    assert draft["message"] == "Please check: no required skills were found"


def test_ai_failure_is_reported_and_logged(client, monkeypatch):
    monkeypatch.setattr(workflow, "llm_json", lambda instructions, data: None)
    monkeypatch.setattr(workflow, "last_error", lambda: "the AI service rejected the API key")
    draft = client.post("/api/jobs/draft-from-prompt", json={"prompt": PROMPT}).json()
    assert draft["from_ai"] is False and "rejected the API key" in draft["message"]
    last_run = client.get("/api/workflow-runs?limit=1").json()[0]
    assert last_run["outcome"] == "failed" and "API key" in last_run["error"]


def test_the_ai_is_given_the_company_documents(client, monkeypatch):
    past = client.post("/api/company-documents", json={"kind": "job_description", "title": "Backend Developer 2025",
                       "text": "Backend Developer. You will build REST APIs with Python, FastAPI and Docker for our platform team."}).json()
    policy = client.post("/api/company-documents", json={"kind": "policy", "title": "Hiring policy",
                         "text": "Every job description ends with the equal opportunity statement of the company."}).json()
    seen = {}

    def ai(instructions, data):
        seen.update(data)
        return good_draft()
    monkeypatch.setattr(workflow, "llm_json", ai)

    draft = client.post("/api/jobs/draft-from-prompt", json={"prompt": PROMPT}).json()
    assert "Backend Developer 2025" in [e["title"] for e in seen["examples"]]
    assert [p["title"] for p in seen["company_policy"]] == ["Hiring policy"]
    assert "Backend Developer 2025" in draft["examples"] and draft["policies"] == ["Hiring policy"]
    for document in (past, policy):
        client.delete(f"/api/company-documents/{document['id']}")
