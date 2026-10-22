"""The assistant agent: the AI reads the conversation, chooses a tool, reads the result and goes on until
it can answer. This is the "ReAct agent" pattern (reason, act, repeat).

    interviewer's message -> agent (AI) --needs a tool?--> tool -> agent (AI) -> ... -> answer

Where the tools come from:
    mcp_servers()    the MCP servers (app/mcp_servers/client.py); MultiServerMCPClient starts them, collects their tools
    HIDDEN_TOOLS     MCP tools the AI must not get (it could post without a person's Yes)
    LOCAL_TOOLS      two tools written here: they only ASK for an approval or a post

The one fixed rule: the AI cannot approve a job or post it to the blog. It can only ask. The interviewer
answers Yes or No on the screen, and then the backend code does it (assistant_service.confirm_action; a post goes
through the posting workflow, graphs/job_post_graph.py, which pauses until that answer).

Memory: every chat has its own LangGraph thread (thread_id), kept by the checkpointer in PostgreSQL. The agent
remembers the whole chat by itself, also the tools it used and their answers; each message only gives it the
new chat lines. So that a long chat does not use too many tokens, the model is shown only the last
MAX_AI_MESSAGES messages of the thread (keep_recent); the full chat stays in the thread and in chat_message.
"""
import asyncio
import logging

from langchain_core.messages import trim_messages
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from sqlmodel import Session

from app.core import config
from app.core.database import engine
from app.features.assistant.models import AssistantAction
from app.features.jobs.models import Job
from app.graphs.assistant_prompts import ASSISTANT_PROMPT
from app.graphs.checkpointer import async_checkpointer
from app.mcp_servers.client import mcp_servers      # where the MCP servers are (one list for the whole app)

log = logging.getLogger("assistant")

TIMEOUT_SEC = 180
MAX_STEPS = 16                   # how many AI and tool steps one message may take
MAX_AI_MESSAGES = 30             # how many of the newest thread messages the model sees (tool answers included)


# The Blogger server can post. The assistant only gets its check tool; posting goes through
# request_job_post, which only asks.
HIDDEN_TOOLS = {"publish_blog_post"}


# ---------- the two tools that only ask ----------

# Checks the job, then saves an AssistantAction so the screen shows a Yes / No question (it does not act)
def _ask(kind: str, job_id: int, text: str = "", apply_url: str = "") -> str:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return f"Job {job_id} was not found. Use list_jobs to see the saved jobs."
        if kind == "approve_job":
            if job.status == "approved":
                return f"Job {job_id} is already approved."
            if not (job.description or "").strip():
                return "The job has no description yet, so it cannot be approved."
        else:
            if job.status != "approved":
                return "The job is not approved yet. Ask for the approval first (request_job_approval)."
            if not apply_url.strip().startswith("https://") or " " in apply_url.strip():
                return "The application form link is missing or not a link. Ask the interviewer for it (https://...)."
            if not 20 <= len(text.strip()) <= 3500:
                return "The post text must have 20 to 3500 characters."
        action = AssistantAction(kind=kind, job_id=job.id, job_title=job.title, text=text.strip(), apply_url=apply_url.strip())
        session.add(action)
        session.commit()
    return ("The interviewer now sees a Yes / No question on the screen. Nothing has happened yet. "
            "Tell them you are waiting for their answer and stop.")


@tool
def request_job_approval(job_id: int) -> str:
    """Ask the interviewer to approve a saved job. This does NOT approve it: they answer Yes or No on the screen."""
    return _ask("approve_job", job_id)


@tool
def request_job_post(job_id: int, text: str, apply_url: str) -> str:
    """Ask the interviewer to post an approved job on the company blog. This does NOT post it: they
    answer Yes or No on the screen. text is the post (from prepare_job_post); apply_url is the application form link."""
    return _ask("post_job", job_id, text, apply_url)


LOCAL_TOOLS = [request_job_approval, request_job_post]


# ---------- the AI model ----------

# Returns the chat model for the agent: Gemini (ChatGoogleGenerativeAI), or the fake model in tests
def chat_model():
    if config.LLM_PROVIDER == "fake":
        from app.ai.fake_chat_model import FakeToolChatModel
        return FakeToolChatModel()
    from langchain_google_genai import ChatGoogleGenerativeAI
    # → the Gemini chat model that chooses the tools in the assistant
    from app.ai.model_choice import current_model
    return ChatGoogleGenerativeAI(model=current_model(), google_api_key=config.LLM_API_KEY)


# ---------- running it ----------

def _text(content) -> str:
    """The AI's answer as plain text (some models answer with a list of parts)."""
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
    return str(content or "").strip()


def keep_recent(state: dict) -> dict:
    """Runs before every model call: the model sees only the newest messages of the thread, starting with one of
    the interviewer's messages (so a tool answer is never cut off from the tool call it belongs to).
    The thread itself keeps everything."""
    recent = trim_messages(state["messages"], strategy="last", token_counter=len, max_tokens=MAX_AI_MESSAGES,
                           start_on="human", allow_partial=False)
    return {"llm_input_messages": recent or state["messages"][-1:]}


# Starts the MCP servers, builds the ReAct agent with the checkpointer and runs one chat turn in its thread
async def _run(messages: list[dict], thread_id: str) -> dict:
    client = MultiServerMCPClient(mcp_servers())  # → MCP: starts the recruitment and blogger MCP servers (mcp_servers)
    # → MCP: collects the servers' tools for the agent, minus publish_blog_post
    mcp_tools = [t for t in await client.get_tools() if t.name not in HIDDEN_TOOLS]
    settings = {"configurable": {"thread_id": thread_id}, "recursion_limit": MAX_STEPS}
    async with async_checkpointer() as saver:
        # create_react_agent is the helper from the course. Newer LangGraph versions print a note that it moved;
        # it still works the same way. With the checkpointer it continues the chat's thread.
        agent = create_react_agent(chat_model(), mcp_tools + LOCAL_TOOLS, prompt=ASSISTANT_PROMPT,
                                   pre_model_hook=keep_recent, checkpointer=saver)  # ----------------  Need to reviw this part in weekend
        before = len((await agent.aget_state(settings)).values.get("messages", []))   # what the thread had already
        # → runs the LangGraph agent: Gemini and tools loop until an answer
        result = await asyncio.wait_for(agent.ainvoke({"messages": messages}, settings), TIMEOUT_SEC)
    new = result["messages"][before + len(messages):]              # what the agent added in this turn
    used = [call["name"] for message in new for call in (getattr(message, "tool_calls", None) or [])]
    return {"answer": _text(new[-1].content) if new else "", "tools": used, "error": ""}


# Turns an agent error into a short safe message for the screen (rate limit, bad key, too many steps)
def _plain_reason(problem: Exception) -> str:
    text, name = str(problem), type(problem).__name__
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return "the AI service limit is reached (too many requests). Wait a little and try again"
    if "API key" in text or "API_KEY" in text or "401" in text or "403" in text:
        return "the AI service rejected the API key (check LLM_API_KEY in .env)"
    if name == "GraphRecursionError":
        return "the assistant needed too many steps. Ask for one thing at a time"
    return f"{name} while the assistant was working (see the backend log)"


def run_assistant(messages: list[dict], thread_id: str) -> dict:
    """Runs the agent in the chat's thread. messages = the NEW chat lines only, [{"role": "user" | "assistant",
    "content": "..."}]; the thread already has the earlier ones. Returns {"answer", "tools", "error"}. Never raises."""
    if config.LLM_PROVIDER != "fake" and not config.LLM_API_KEY:
        return {"answer": "", "tools": [], "error": "LLM_API_KEY is not set in .env"}
    try:
        return asyncio.run(_run(messages, thread_id))
    except asyncio.TimeoutError:
        return {"answer": "", "tools": [], "error": "the assistant took too long to answer. Try again"}
    except Exception as problem:                      # never str(problem) to the screen: it can hold a key
        log.exception("assistant run failed")
        return {"answer": "", "tools": [], "error": _plain_reason(problem)}
