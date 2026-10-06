"""The assistant chatbot: the AI chooses the tools, a person confirms approvals and Telegram posts.

LLM_PROVIDER=fake gives a stand-in model that chooses tools with word rules. Everything else is real:
the agent loop, the MCP servers (started as child processes) and the tools.
"""
import io
import json

import pytest

from app.features.assistant.services import assistant_service
from app.graphs import assistant_agent

FORM = "https://docs.google.com/forms/d/e/made-up-form/viewform"
PAST_JOB = ("Backend Developer. You will build REST APIs with Python and FastAPI, write tests and work with "
            "PostgreSQL. We value clear code reviews and steady releases.")


@pytest.fixture(autouse=True)
def new_chat(client):
    client.delete("/api/assistant/chat")
    yield


def say(client, text, file=None) -> dict:
    files = {"file": file} if file else None
    response = client.post("/api/assistant/chat", data={"text": text}, files=files)
    assert response.status_code == 200, response.text
    return response.json()


def last(chat) -> dict:
    return chat["messages"][-1]


# ---------- which tools the assistant gets ----------

def test_the_assistant_cannot_reach_the_posting_tool():
    import asyncio
    from langchain_mcp_adapters.client import MultiServerMCPClient
    every_tool = {t.name for t in asyncio.run(MultiServerMCPClient(assistant_agent.mcp_servers()).get_tools())}
    assert "send_channel_post" in every_tool                                   # the Telegram server has it ...
    assert "send_channel_post" in assistant_agent.HIDDEN_TOOLS                 # ... but the assistant does not get it
    assert {"write_job_draft", "save_job", "search_company_documents", "save_attached_file_as_document",
            "prepare_telegram_post", "check_telegram_settings"} <= every_tool
    assert not [name for name in every_tool if "approve" in name]              # no MCP tool approves a job
    assert [t.name for t in assistant_agent.LOCAL_TOOLS] == ["request_job_approval", "request_telegram_post"]


# ---------- company documents ----------

def test_an_attached_file_is_stored_exactly(client):
    chat = say(client, "Add this as a past job description", file=("backend-2025.txt", PAST_JOB.encode()))
    assert chat["messages"][0]["attachment_name"] == "backend-2025.txt"
    assert last(chat)["tools"] == ["save_attached_file_as_document"] and "backend-2025" in last(chat)["content"]
    documents = client.get("/api/company-documents").json()
    stored = [d for d in documents if d["title"] == "backend-2025"]
    assert stored and stored[0]["kind"] == "job_description" and stored[0]["words"] == len(PAST_JOB.split())

    chat = say(client, "This is our hiring policy", file=("policy.txt", b"Every job advert ends with our equal opportunity statement."))
    assert [d for d in client.get("/api/company-documents").json() if d["title"] == "policy"][0]["kind"] == "policy"
    for document in client.get("/api/company-documents").json():
        if document["title"] in ("backend-2025", "policy"):
            client.delete(f"/api/company-documents/{document['id']}")


def test_search(client):
    document = client.post("/api/company-documents", json={"kind": "job_description", "title": "Assistant search test",
                                                           "text": PAST_JOB}).json()
    chat = say(client, "Search the documents for Python FastAPI REST APIs")
    assert last(chat)["tools"] == ["search_company_documents"] and "Assistant search test" in last(chat)["content"]
    client.delete(f"/api/company-documents/{document['id']}")


def test_a_bad_file_is_refused(client):
    assert client.post("/api/assistant/chat", data={"text": "store"}, files={"file": ("photo.png", b"x")}).status_code == 400
    assert client.post("/api/assistant/chat", data={"text": ""}).status_code == 400


# ---------- the whole path: write, approve, post ----------

def test_write_approve_and_post_with_a_yes_each_time(client):
    # 1. the assistant writes the job with the workflow and saves it as a draft
    chat = say(client, "Write a job for a Backend developer with Python, FastAPI and Docker, 3 years experience")
    assert last(chat)["tools"] == ["write_job_draft", "save_job"]
    job = client.get("/api/jobs").json()[0]
    assert job["status"] == "draft" and "Python" in job["required_skills"] and len(job["description"].split()) >= 80
    assert str(job["id"]) in last(chat)["content"]

    # 2. asking to approve only creates a question; the job stays a draft
    chat = say(client, f"Approve job {job['id']}")
    assert last(chat)["tools"] == ["request_job_approval"]
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "draft"
    question = chat["actions"][0]
    assert (question["kind"], question["job_id"], question["status"]) == ("approve_job", job["id"], "pending")

    # 3. the interviewer says Yes: now the backend approves it
    chat = client.post(f"/api/assistant/actions/{question['id']}", json={"yes": True}).json()
    assert chat["actions"] == [] and "is approved" in last(chat)["content"]
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "approved"

    # 4. asking to post only creates a question; nothing is posted
    chat = say(client, f"Post job {job['id']} to Telegram, the form is {FORM}")
    assert last(chat)["tools"] == ["prepare_telegram_post", "request_telegram_post"]
    assert client.get(f"/api/jobs/{job['id']}/postings").json() == []
    question = chat["actions"][0]
    assert question["kind"] == "post_telegram" and question["apply_url"] == FORM
    assert question["text"].startswith(job["title"]) and "http" not in question["text"]     # the link is added by code

    # 5. Yes: the backend posts it (fake Telegram) and saves the result
    chat = client.post(f"/api/assistant/actions/{question['id']}", json={"yes": True}).json()
    assert "was posted to the Telegram channel" in last(chat)["content"]
    postings = client.get(f"/api/jobs/{job['id']}/postings").json()
    assert len(postings) == 1 and postings[0]["status"] == "posted" and postings[0]["apply_url"] == FORM

    # a question can be answered only once
    assert client.post(f"/api/assistant/actions/{question['id']}", json={"yes": True}).status_code == 400
    assert len(client.get(f"/api/jobs/{job['id']}/postings").json()) == 1


def test_no_means_nothing_happens(client):
    say(client, "Create a job for a QA engineer with Selenium and Python")
    job = client.get("/api/jobs").json()[0]
    chat = say(client, f"Approve job {job['id']}")
    chat = client.post(f"/api/assistant/actions/{chat['actions'][0]['id']}", json={"yes": False}).json()
    assert "Nothing was changed" in last(chat)["content"] and chat["actions"] == []
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "draft"
    assert client.post("/api/assistant/actions/999999", json={"yes": True}).status_code == 404


def test_a_draft_job_cannot_be_posted(client):
    say(client, "Create a job for a Data analyst with SQL and Excel")
    job = client.get("/api/jobs").json()[0]
    chat = say(client, f"Post job {job['id']} to Telegram, the form is {FORM}")
    assert chat["actions"] == [] and "Approve the job first" in last(chat)["content"]
    assert client.get(f"/api/jobs/{job['id']}/postings").json() == []


def test_a_post_needs_the_form_link(client):
    job = client.post("/api/jobs", json={"title": "Link Tester", "required_skills": ["Python"],
                                         "description": "A made-up job used to test the assistant."}).json()
    client.post(f"/api/jobs/{job['id']}/approve", json={"add_to_library": False})
    chat = say(client, f"Post job {job['id']} to Telegram")
    assert chat["actions"] == [] and client.get(f"/api/jobs/{job['id']}/postings").json() == []


def test_an_edited_job_is_not_posted_by_an_old_yes(client):
    """The job was approved when the assistant asked, but edited before the interviewer answered."""
    job = client.post("/api/jobs", json={"title": "Edit Tester", "required_skills": ["Python"],
                                         "description": "A made-up job used to test the assistant."}).json()
    client.post(f"/api/jobs/{job['id']}/approve", json={"add_to_library": False})
    chat = say(client, f"Post job {job['id']} to Telegram, the form is {FORM}")
    client.put(f"/api/jobs/{job['id']}", json={"title": "Edit Tester", "required_skills": ["Python"],
                                               "description": "The text was changed after the approval."})
    chat = client.post(f"/api/assistant/actions/{chat['actions'][0]['id']}", json={"yes": True}).json()
    assert "Approve the job first" in last(chat)["content"]
    assert client.get(f"/api/jobs/{job['id']}/postings").json() == []


# ---------- the chat itself ----------

def test_the_conversation_is_kept_and_can_be_cleared(client):
    say(client, "hello")
    chat = client.get("/api/assistant/chat").json()
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant"] and "I can store" in last(chat)["content"]
    assert client.delete("/api/assistant/chat").json() == {"messages": [], "actions": []}


def test_the_ai_gets_a_note_about_the_file_not_the_whole_file(client, monkeypatch):
    seen = {}

    def model(messages):
        seen["messages"] = messages
        return {"answer": "ok", "tools": [], "error": ""}
    monkeypatch.setattr(assistant_service, "run_assistant", model)
    long_text = "Company policy. " + "word " * 3000
    say(client, "store this", file=("long.txt", long_text.encode()))
    content = seen["messages"][-1]["content"]
    assert "[Attached file: long.txt, message_id=" in content and "3002 words" in content
    assert len(content) < 1000                                                 # only the beginning is sent to the AI


def test_a_failure_is_shown_in_plain_words(client, monkeypatch):
    monkeypatch.setattr(assistant_service, "run_assistant",
                        lambda messages: {"answer": "", "tools": [], "error": "the AI service limit is reached"})
    chat = say(client, "hello")
    assert last(chat)["content"] == "The assistant could not answer: the AI service limit is reached."
    runs = client.get("/api/workflow-runs").json()
    assert runs[0]["stage"] == "assistant" and runs[0]["outcome"] == "failed"

    assert "limit is reached" in assistant_agent._plain_reason(Exception("429 RESOURCE_EXHAUSTED secret-key-123"))
    assert "secret-key-123" not in assistant_agent._plain_reason(Exception("boom secret-key-123"))


def test_the_assistant_needs_login(anonymous):
    assert anonymous.get("/api/assistant/chat").status_code == 401
    assert anonymous.post("/api/assistant/chat", data={"text": "hello"}).status_code == 401
    assert anonymous.post("/api/assistant/actions/1", json={"yes": True}).status_code == 401
    assert anonymous.delete("/api/assistant/chat").status_code == 401
