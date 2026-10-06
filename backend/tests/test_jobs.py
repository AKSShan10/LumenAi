"""Job profiles: create, edit, delete, AI draft from a prompt, approve."""
JOB = {"title": "Backend Developer", "required_skills": ["Python", " FastAPI ", "Python"], "preferred_skills": ["Docker"],
       "min_years": 3, "qualifications": "BSc in CSE", "description": ""}
PROMPT = "Backend developer with Python, FastAPI and Docker, 3 years experience, BSc in CSE"


def new_job(client, **changes) -> dict:
    response = client.post("/api/jobs", json={**JOB, **changes})
    assert response.status_code == 201
    return response.json()


def test_create_and_list(client):
    job = new_job(client)
    assert job["required_skills"] == ["Python", "FastAPI"]            # trimmed, no duplicates
    assert job["status"] == "draft" and job["approved_at"] is None
    assert client.get("/api/jobs").json()[0]["id"] == job["id"]       # newest first
    assert client.get(f"/api/jobs/{job['id']}").json()["title"] == "Backend Developer"


def test_a_job_needs_a_title_and_a_required_skill(client):
    assert client.post("/api/jobs", json={**JOB, "title": "A"}).status_code == 422
    assert client.post("/api/jobs", json={**JOB, "required_skills": []}).status_code == 422
    assert client.get("/api/jobs/999999").status_code == 404


def test_ai_draft_from_prompt(client):
    before = len(client.get("/api/jobs").json())
    draft = client.post("/api/jobs/draft-from-prompt", json={"prompt": PROMPT}).json()
    assert len(client.get("/api/jobs").json()) == before                # a draft is not saved as a job
    assert draft["from_ai"] is True and draft["title"] == "Backend Developer"
    assert {"Python", "FastAPI", "Docker"} <= set(draft["required_skills"])
    assert draft["min_years"] == 3 and len(draft["description"].split()) >= 80
    assert client.post("/api/jobs/draft-from-prompt", json={"prompt": "short"}).status_code == 422


def test_generate_again_follows_the_change_request(client, monkeypatch):
    from app.graphs import job_description_graph as workflow
    first = client.post("/api/jobs/draft-from-prompt", json={"prompt": PROMPT}).json()
    again = client.post("/api/jobs/draft-from-prompt", json={
        "prompt": PROMPT, "change_request": "more focus on teamwork", "previous": first["description"]}).json()
    assert again["from_ai"] is True and "more focus on teamwork" in again["description"]     # the fake AI repeats the wish

    seen = {}

    def ai(instructions, data):
        seen.update(data)
        return {"title": "Backend Developer", "required_skills": ["Python"], "description": "word " * 100 + "Salary 50000 BDT."}
    monkeypatch.setattr(workflow, "llm_json", ai)
    paid = client.post("/api/jobs/draft-from-prompt", json={
        "prompt": PROMPT, "change_request": "mention the salary of 50000 BDT", "previous": first["description"]}).json()
    assert seen["change_request"] == "mention the salary of 50000 BDT" and seen["previous_description"] == first["description"]
    assert paid["message"] == ""                                       # pay is allowed: the interviewer asked for it


def test_approve_and_edit(client):
    job = new_job(client, title="Data Analyst")
    assert client.post(f"/api/jobs/{job['id']}/approve").status_code == 400       # no description yet

    text = "We are looking for a Data Analyst who turns data into clear reports for the business teams."
    edited = client.put(f"/api/jobs/{job['id']}", json={**JOB, "title": "Data Analyst", "description": text}).json()
    approved = client.post(f"/api/jobs/{job['id']}/approve").json()
    assert approved["status"] == "approved" and approved["approved_at"]
    documents = client.get("/api/company-documents").json()
    assert [d for d in documents if d["job_id"] == job["id"] and d["source"] == "approved job"]

    client.post(f"/api/jobs/{job['id']}/approve")                                  # approving twice adds it once
    assert len([d for d in client.get("/api/company-documents").json() if d["job_id"] == job["id"]]) == 1

    same = client.put(f"/api/jobs/{job['id']}", json={k: edited[k] for k in JOB} | {"prompt": ""}).json()
    assert same["status"] == "approved"                                            # nothing changed
    changed = client.put(f"/api/jobs/{job['id']}", json={**JOB, "title": "Senior Data Analyst", "description": text}).json()
    assert changed["status"] == "draft" and changed["approved_at"] is None         # must be approved again


def test_approve_without_keeping_the_description(client):
    job = new_job(client, title="QA Engineer", description="A QA Engineer tests the product and reports problems clearly.")
    client.post(f"/api/jobs/{job['id']}/approve", json={"add_to_library": False})
    assert not [d for d in client.get("/api/company-documents").json() if d["job_id"] == job["id"]]


def test_delete(client):
    job = new_job(client, title="Temporary Job")
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_jobs_need_login(anonymous):
    assert anonymous.get("/api/jobs").status_code == 401
    assert anonymous.post("/api/jobs/draft-from-prompt", json={"prompt": PROMPT}).status_code == 401
