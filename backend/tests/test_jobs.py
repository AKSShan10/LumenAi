"""Job profiles: saved, changed and approved by the service (the assistant's tools call it); the API only reads and deletes."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel import Session

from app.core.database import engine
from app.features.jobs.models import Job
from app.features.jobs.schemas import JobCreate
from app.features.jobs.services.job_service import approve_job, update_job

JOB = {"title": "Backend Developer", "required_skills": ["Python", " FastAPI ", "Python"], "preferred_skills": ["Docker"],
       "min_years": 3, "qualifications": "BSc in CSE", "description": ""}
TEXT = "We are looking for a Data Analyst who turns data into clear reports for the business teams."


def test_save_and_list(client, make_job):
    job = make_job(**JOB)
    assert job["required_skills"] == ["Python", "FastAPI"]            # trimmed, no duplicates
    assert job["status"] == "draft" and job["approved_at"] is None
    assert client.get("/api/jobs").json()[0]["id"] == job["id"]       # newest first
    assert client.get(f"/api/jobs/{job['id']}").json()["title"] == "Backend Developer"
    assert client.get("/api/jobs/999999").status_code == 404


def test_a_job_needs_a_title_and_a_required_skill():
    with pytest.raises(ValidationError):
        JobCreate(**{**JOB, "title": "A"})
    with pytest.raises(ValidationError):
        JobCreate(**{**JOB, "required_skills": []})


def test_approve_and_change(client, make_job):
    job = make_job(**{**JOB, "title": "Data Analyst"})
    with Session(engine) as session:
        with pytest.raises(HTTPException):                                         # no description yet
            approve_job(session, session.get(Job, job["id"]), add_to_library=True)

        body = JobCreate(**{**JOB, "title": "Data Analyst", "description": TEXT})
        update_job(session, session.get(Job, job["id"]), body)
        approved = approve_job(session, session.get(Job, job["id"]), add_to_library=True)
        assert approved.status == "approved" and approved.approved_at
        approve_job(session, session.get(Job, job["id"]), add_to_library=True)     # approving twice adds it once
        documents = [d for d in client.get("/api/company-documents").json() if d["job_id"] == job["id"]]
        assert len(documents) == 1 and documents[0]["source"] == "approved job"

        same = update_job(session, session.get(Job, job["id"]), body)
        assert same.status == "approved"                                           # nothing changed
        changed = update_job(session, session.get(Job, job["id"]), JobCreate(**{**JOB, "title": "Senior Data Analyst", "description": TEXT}))
        assert changed.status == "draft" and changed.approved_at is None           # must be approved again


def test_approve_without_keeping_the_description(client, make_job):
    job = make_job(approve=True, title="QA Engineer", description="A QA Engineer tests the product and reports problems clearly.")
    assert job["status"] == "approved"
    assert not [d for d in client.get("/api/company-documents").json() if d["job_id"] == job["id"]]


def test_delete(client, make_job):
    job = make_job(title="Temporary Job")
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_jobs_are_only_read_and_deleted_through_the_api(client, make_job):
    """Writing, changing and approving happen in the chat. The old form endpoints are gone."""
    job = make_job(title="Read Only Tester")
    assert client.post("/api/jobs", json=JOB).status_code == 405
    assert client.put(f"/api/jobs/{job['id']}", json=JOB).status_code == 405
    assert client.post(f"/api/jobs/{job['id']}/approve").status_code == 404
    assert client.post(f"/api/jobs/{job['id']}/post", json={}).status_code == 404
    assert client.post("/api/jobs/draft-from-prompt", json={"prompt": "Backend developer with Python"}).status_code == 405
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "draft"


def test_jobs_need_login(anonymous):
    assert anonymous.get("/api/jobs").status_code == 401
    assert anonymous.delete("/api/jobs/1").status_code == 401
