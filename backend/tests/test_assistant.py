"""The assistant chatbot: the AI chooses the tools, a person confirms approvals and job posts.

LLM_PROVIDER=fake gives a stand-in model that chooses tools with word rules. Everything else is real:
the agent loop, the MCP servers (started as child processes) and the tools.
"""
import io
import json

import pytest

from app.features.assistant.services import assistant_service
from app.graphs import assistant_agent
from app.graphs.checkpointer import checkpointer

FORM = "https://docs.google.com/forms/d/e/made-up-form/viewform"
PAST_JOB = ("Backend Developer. You will build REST APIs with Python and FastAPI, write tests and work with "
            "PostgreSQL. We value clear code reviews and steady releases.")


@pytest.fixture(autouse=True)
def new_chat(client):
    client.post("/api/assistant/chat/new")
    yield


def thread_messages(thread_id: str) -> list:
    """What LangGraph's checkpointer keeps for a chat's thread."""
    saved = checkpointer().get_tuple({"configurable": {"thread_id": thread_id}})
    return [m.content for m in saved.checkpoint["channel_values"]["messages"]] if saved else []


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
    assert "publish_blog_post" in every_tool                                   # the Blogger server can post ...
    assert assistant_agent.HIDDEN_TOOLS == {"publish_blog_post"}               # ... but the assistant does not get that tool
    assert {"write_job_draft", "save_job", "search_company_documents", "save_attached_file_as_document",
            "prepare_job_post", "check_blogger_settings"} <= every_tool
    assert not [name for name in every_tool if "approve" in name]              # no MCP tool approves a job
    assert [t.name for t in assistant_agent.LOCAL_TOOLS] == ["request_job_approval", "request_job_post"]


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


def test_search(client, add_doc):
    document = add_doc("job_description", "Assistant search test", PAST_JOB)
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
    chat = say(client, f"Post job {job['id']} on the blog, the form is {FORM}")
    assert last(chat)["tools"] == ["prepare_job_post", "request_job_post"]
    assert client.get(f"/api/jobs/{job['id']}/postings").json() == []
    question = chat["actions"][0]
    assert question["kind"] == "post_job" and question["apply_url"] == FORM
    assert question["text"].startswith(job["title"]) and "http" not in question["text"]     # the link is added by code

    # 5. Yes: the backend posts it (fake Blogger) and saves the result
    chat = client.post(f"/api/assistant/actions/{question['id']}", json={"yes": True}).json()
    assert "was posted to the Blogger blog" in last(chat)["content"]
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
    chat = say(client, f"Post job {job['id']} on the blog, the form is {FORM}")
    assert chat["actions"] == [] and "Approve the job first" in last(chat)["content"]
    assert client.get(f"/api/jobs/{job['id']}/postings").json() == []


def test_a_post_needs_the_form_link(client, make_job):
    job = make_job(approve=True, title="Link Tester", description="A made-up job used to test the assistant.")
    chat = say(client, f"Post job {job['id']} on the blog")
    assert chat["actions"] == [] and client.get(f"/api/jobs/{job['id']}/postings").json() == []


def test_an_edited_job_is_not_posted_by_an_old_yes(client, make_job):
    """The job was approved when the assistant asked, but changed before the interviewer answered."""
    from sqlmodel import Session
    from app.core.database import engine
    from app.features.jobs.models import Job
    from app.features.jobs.schemas import JobCreate
    from app.features.jobs.services.job_service import update_job
    job = make_job(approve=True, title="Edit Tester", description="A made-up job used to test the assistant.")
    chat = say(client, f"Post job {job['id']} on the blog, the form is {FORM}")
    with Session(engine) as session:
        update_job(session, session.get(Job, job["id"]), JobCreate(title="Edit Tester", required_skills=["Python"],
                                                                   description="The text was changed after the approval."))
    chat = client.post(f"/api/assistant/actions/{chat['actions'][0]['id']}", json={"yes": True}).json()
    assert "Approve the job first" in last(chat)["content"]
    assert client.get(f"/api/jobs/{job['id']}/postings").json() == []


# ---------- the chat itself ----------

def test_the_conversation_is_kept(client):
    say(client, "hello")
    chat = client.get("/api/assistant/chat").json()
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant"] and "I can store" in last(chat)["content"]


def test_new_chat_keeps_the_earlier_chat(client):
    first = say(client, "List the jobs")
    assert first["is_current"] is True and len(first["messages"]) == 2

    fresh = client.post("/api/assistant/chat/new").json()
    assert fresh["messages"] == [] and fresh["is_current"] is True and fresh["chat_id"] != first["chat_id"]
    assert client.post("/api/assistant/chat/new").json()["chat_id"] == fresh["chat_id"]     # an empty chat is used again

    # the earlier chat is still in the database, with its title, and can be read
    listed = {c["id"]: c for c in fresh["chats"]}
    assert listed[first["chat_id"]]["title"] == "List the jobs" and listed[first["chat_id"]]["messages"] == 2
    earlier = client.get("/api/assistant/chat", params={"chat_id": first["chat_id"]}).json()
    assert earlier["is_current"] is False and [m["content"] for m in earlier["messages"]][0] == "List the jobs"
    assert client.get("/api/assistant/chat", params={"chat_id": 999999}).status_code == 404

    # a new message goes to the new chat, and the AI is only given the lines of that chat
    again = say(client, "hello")
    assert again["chat_id"] == fresh["chat_id"] and len(again["messages"]) == 2


def test_an_earlier_chat_can_be_continued(client, monkeypatch):
    first = say(client, "List the jobs")
    client.post("/api/assistant/chat/new")
    second = say(client, "hello")
    assert second["chat_id"] != first["chat_id"]

    # "Continue this chat": the first chat is the current one again; the second one is kept
    chat = client.post(f"/api/assistant/chat/{first['chat_id']}/continue").json()
    assert chat["chat_id"] == first["chat_id"] and chat["is_current"] is True and len(chat["messages"]) == 2
    assert [c["id"] for c in chat["chats"]][:2] == [first["chat_id"], second["chat_id"]]      # the current one first
    assert client.get("/api/assistant/chat").json()["chat_id"] == first["chat_id"]

    # a new line goes into it, and the AI is given the earlier lines of that chat only
    seen = {}

    def model(messages, thread_id):
        seen["messages"], seen["thread"] = messages, thread_id
        return {"answer": "ok", "tools": [], "error": ""}
    monkeypatch.setattr(assistant_service, "run_assistant", model)
    chat = say(client, "and now?")
    assert chat["chat_id"] == first["chat_id"] and len(chat["messages"]) == 4
    assert [m["content"] for m in seen["messages"]] == ["and now?"]            # the rest is in the chat's thread
    assert seen["thread"].startswith(f"chat-{first['chat_id']}-")
    assert "List the jobs" in str(thread_messages(seen["thread"])) and "hello" not in str(thread_messages(seen["thread"]))

    assert client.post("/api/assistant/chat/999999/continue").status_code == 404


def test_continuing_leaves_no_empty_chat_and_cancels_a_waiting_question(client, make_job):
    first = say(client, "hello")
    job = make_job(title="Continue Tester", description="A made-up job used to test the assistant.")
    client.post("/api/assistant/chat/new")
    asked = say(client, f"Approve job {job['id']}")
    assert len(asked["actions"]) == 1
    chat = client.post(f"/api/assistant/chat/{first['chat_id']}/continue").json()
    assert chat["actions"] == []                                               # it belonged to the chat that was left
    empty = client.post("/api/assistant/chat/new").json()                      # an empty current chat ...
    chat = client.post(f"/api/assistant/chat/{first['chat_id']}/continue").json()
    assert empty["chat_id"] not in [c["id"] for c in chat["chats"]]            # ... is not kept in the list


def test_the_ai_only_gets_the_current_chat(client, monkeypatch):
    say(client, "a line from the earlier chat")
    client.post("/api/assistant/chat/new")
    seen = {}

    def model(messages, thread_id):
        seen["messages"] = messages
        return {"answer": "ok", "tools": [], "error": ""}
    monkeypatch.setattr(assistant_service, "run_assistant", model)
    say(client, "a line from the new chat")
    assert [m["content"] for m in seen["messages"]] == ["a line from the new chat"]


def test_a_waiting_question_is_cancelled_by_a_new_chat(client, make_job):
    job = make_job(title="Cancel Tester", description="A made-up job used to test the assistant.")
    chat = say(client, f"Approve job {job['id']}")
    question = chat["actions"][0]
    assert client.post("/api/assistant/chat/new").json()["actions"] == []
    assert client.post(f"/api/assistant/actions/{question['id']}", json={"yes": True}).status_code == 400
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "draft"


def test_the_ai_gets_a_note_about_the_file_not_the_whole_file(client, monkeypatch):
    seen = {}

    def model(messages, thread_id):
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
                        lambda messages, thread_id: {"answer": "", "tools": [], "error": "the AI service limit is reached"})
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
    assert anonymous.post("/api/assistant/chat/new").status_code == 401
    assert anonymous.post("/api/assistant/chat/1/continue").status_code == 401


def test_the_chat_has_langgraph_memory(client, monkeypatch):
    """Every chat has its own thread in LangGraph's checkpointer: the agent is given only the new lines, and the
    thread keeps the earlier ones, also the tools it used and the result of a Yes."""
    sent = []
    real = assistant_service.run_assistant

    def spy(messages, thread_id):
        sent.append(([m["content"] for m in messages], thread_id))
        return real(messages, thread_id)
    monkeypatch.setattr(assistant_service, "run_assistant", spy)

    say(client, "List the jobs")
    say(client, "hello")
    (first, thread), (second, same_thread) = sent
    assert first == ["List the jobs"] and second == ["hello"] and thread == same_thread
    remembered = thread_messages(thread)
    assert remembered[0] == "List the jobs" and "hello" in remembered
    assert len(remembered) > 4                        # also the tool call and the tool's answer for "List the jobs"

    client.post("/api/assistant/chat/new")
    say(client, "hi")
    assert sent[-1][1] != thread                      # a new chat has a new thread


def test_the_model_sees_only_the_newest_messages():
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    long_chat = []
    for n in range(40):
        long_chat += [HumanMessage(f"question {n}"),
                      AIMessage("", tool_calls=[{"name": "list_jobs", "args": {}, "id": f"c{n}", "type": "tool_call"}]),
                      ToolMessage("{}", tool_call_id=f"c{n}", name="list_jobs"), AIMessage(f"answer {n}")]
    shown = assistant_agent.keep_recent({"messages": long_chat})["llm_input_messages"]
    assert len(shown) <= assistant_agent.MAX_AI_MESSAGES and shown[0].type == "human"
    assert shown[-1].content == "answer 39"


def test_a_failed_run_starts_a_fresh_thread(client, monkeypatch):
    threads = []

    def failing(messages, thread_id):
        threads.append(thread_id)
        return {"answer": "", "tools": [], "error": "the AI service limit is reached"}
    monkeypatch.setattr(assistant_service, "run_assistant", failing)
    say(client, "hello")
    say(client, "hello again")
    assert threads[0] != threads[1]                   # an unfinished thread is not continued
