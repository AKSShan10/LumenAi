"""An offline stand-in for the chat model of the assistant, used when LLM_PROVIDER=fake.

It chooses tools with simple word rules, so the tests and a demo without a key can run the real agent,
the real MCP servers and the real tools. This is NOT real AI.

How it works: from the interviewer's last message it makes a short plan (a list of tools). Each time the
agent asks it, it gives the next tool of the plan; when the plan is done it writes a short answer.
"""
import json
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


# Picks the list of tools to run from simple words in the interviewer's message (fake AI only)
def _plan(text: str) -> list[str]:
    low = text.lower()
    has_job_number = bool(re.search(r"job\s*#?\d+", low))
    find_job = [] if has_job_number else ["list_jobs"]
    if "[attached file:" in low:
        return ["save_attached_file_as_document"]
    if "blog" in low and ("check" in low or "test" in low):
        return ["check_blogger_settings"]
    if "post" in low or "blog" in low:
        return find_job + ["prepare_job_post", "request_job_post"]
    if "approve" in low:
        return find_job + ["request_job_approval"]
    if "search" in low or "find" in low:
        return ["search_company_documents"]
    if "job" in low and re.search(r"\b(write|create|draft|generate|make)\b", low):
        return ["write_job_draft", "save_job"]
    if "list" in low or "show" in low:
        return ["list_company_documents"] if "document" in low else ["list_jobs"]
    return []


# Turns a tool's answer (MCP text parts or a plain string) into a dict, so the fake model can read it
def _json(message: ToolMessage) -> dict:
    content = message.content
    if isinstance(content, list):                     # MCP tools answer with a list of text parts
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {"text": str(content)}


class FakeToolChatModel(BaseChatModel):
    # Returns the name LangChain uses for this fake chat model
    @property
    def _llm_type(self) -> str:
        return "fake-tool-chat-model"

    # Ignores the tool list and returns itself: the word rules already know the tool names
    def bind_tools(self, tools, **kwargs):
        return self                                   # the rules below know the tool names already

    # Called by LangChain for each model turn: wraps the fake decision (_decide) in a ChatResult
    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    # Asks for the next unused tool of the plan, or writes the final answer once every tool has answered
    def _decide(self, messages) -> AIMessage:
        last_human = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        text = str(messages[last_human].content)
        results = {m.name: _json(m) for m in messages[last_human + 1:] if isinstance(m, ToolMessage)}
        plan = _plan(text)

        for step in plan:
            if step in results:
                if "error" in results[step]:          # a tool said no: stop and tell the interviewer
                    return AIMessage(content="That did not work: " + str(results[step]["error"]))
                continue
            return AIMessage(content="", tool_calls=[{"name": step, "args": self._arguments(step, text, results),
                                                      "id": f"fake-{step}", "type": "tool_call"}])
        return AIMessage(content=self._answer(plan, results))

    # Builds the arguments for one tool call from the message text and the earlier tool results
    def _arguments(self, step: str, text: str, results: dict) -> dict:
        number = re.search(r"job\s*#?(\d+)", text.lower())
        jobs = results.get("list_jobs", {}).get("jobs") or [{}]
        job_id = int(number.group(1)) if number else int(jobs[0].get("id") or 0)
        if step == "save_attached_file_as_document":
            message_id = int(re.search(r"message_id=(\d+)", text).group(1))
            return {"message_id": message_id, "kind": "policy" if "policy" in text.lower() else "job_description"}
        if step == "search_company_documents":
            return {"query": text}
        if step == "write_job_draft":
            # "Write a job for a backend developer with Python" -> "backend developer with Python"
            prompt = re.sub(r"^\s*(please\s+)?(write|create|draft|generate|make)\s+(me\s+)?(a\s+)?(new\s+)?job"
                            r"(\s+description)?(\s+for)?(\s+an?)?\s+", "", text, flags=re.IGNORECASE)
            return {"prompt": prompt or text}
        if step == "save_job":
            draft = results["write_job_draft"]["draft"]
            return {**draft, "prompt": text[:2000]}
        if step in ("prepare_job_post", "request_job_approval"):
            return {"job_id": job_id}
        if step == "request_job_post":
            link = re.search(r"https://\S+", text)
            return {"job_id": job_id, "text": results["prepare_job_post"].get("text", ""),
                    "apply_url": link.group(0) if link else ""}
        return {}

    # Writes the fake model's final chat answer from the result of the last tool in the plan
    def _answer(self, plan: list[str], results: dict) -> str:
        if not plan:
            return ("I can store company documents, write a job description, ask you to approve a job and "
                    "prepare its post. For example: \"Write a job for a backend developer with Python\". "
                    "(Fake AI: simple word rules, for tests and demos without a key.)")
        last = results.get(plan[-1], {})
        if plan[-1] == "save_job":
            job = last.get("job", {})
            followed = results["write_job_draft"].get("followed_examples") or []
            return (f"I wrote and saved the job \"{job.get('title')}\" as job {job.get('id')} (draft). "
                    + (f"I followed: {', '.join(followed)}. " if followed else "No similar company document was found. ")
                    + "Tell me what to change, or ask me to approve it.")
        if plan[-1] == "save_attached_file_as_document":
            return f"I stored \"{last.get('title')}\" as a company document ({last.get('kind')}, {last.get('words')} words)."
        if plan[-1] in ("request_job_approval", "request_job_post"):
            asked = "Yes / No question" in str(last.get("text"))
            return ("I prepared it. Please answer Yes or No on the screen; nothing happens before that."
                    if asked else str(last.get("text")))
        if plan[-1] == "search_company_documents":
            found = last.get("documents") or []
            return ("The closest company documents: " + "; ".join(f"{d['title']} ({d['similarity']})" for d in found)
                    if found else "No similar company document was found.")
        if plan[-1] == "list_jobs":
            return "Saved jobs: " + ("; ".join(f"{j['id']}: {j['title']} ({j['status']})" for j in last.get("jobs", [])) or "none")
        if plan[-1] == "list_company_documents":
            return "Company documents: " + ("; ".join(d["title"] for d in last.get("documents", [])) or "none")
        return str(last.get("message") or last)
