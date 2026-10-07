"""An offline stand-in for the AI model, used when LLM_PROVIDER=fake.

Use it for tests and for trying the app without an API key. Use a real model for the actual demo.
Each feature adds its own fake answer here, chosen by the prompt it sends.
The answers come from simple word rules. This is NOT real AI.
"""
import hashlib
import math
import re

from app.graphs.job_description_prompts import JOB_DRAFT_PROMPT, JOB_REVISE_PROMPT


def fake_answer(instructions: str, data) -> dict:
    if instructions == JOB_DRAFT_PROMPT:
        return _fake_job(data)
    if instructions == JOB_REVISE_PROMPT:
        return _fake_job(data)          # the same rules again, from the same prompt
    return {"ok": True}


def _fake_job(data: dict) -> dict:
    """A job profile from the prompt: the title is the text before "with", skills are the capitalised words."""
    prompt = data["prompt"]
    title = re.split(r"\bwith\b|,|\.", prompt, maxsplit=1)[0].strip().title()[:120]
    skills = list(dict.fromkeys(re.findall(r"\b[A-Z][A-Za-z+#.]*[A-Za-z+#]\b", prompt.split(" ", 1)[-1])))
    years = re.search(r"(\d+)\s*\+?\s*years?", prompt)
    degree = re.search(r"\b(BSc|MSc|Bachelor|Master)[^,.]*", prompt)
    followed = [d["title"] for d in data.get("examples", []) + data.get("company_policy", [])]
    description = (
        f"We are looking for a {title} to join our team. In this role you will design, build and maintain "
        f"software together with other engineers, review code, write tests and keep the documentation up to date. "
        f"You will take part in planning, estimate your own work and explain technical choices in clear words. "
        f"Required skills: {', '.join(skills[:6]) or 'see the job profile'}. "
        f"We expect {years.group(1) if years else 'some'} years of relevant experience and the habit of asking "
        f"questions early. You care about readable code, reliable releases and helpful feedback to colleagues. "
        f"We welcome applications from people of every background. "
        + (f"Written to follow: {'; '.join(followed)}. " if followed else "")
        + (f"Changed as asked: {data['change_request']}. " if data.get("change_request") else "")
        + "(Fake AI text for offline tests.)"
    )
    return {"title": title, "required_skills": skills[:6], "preferred_skills": skills[6:10],
            "min_years": int(years.group(1)) if years else 0,
            "qualifications": degree.group(0).strip() if degree else "", "description": description}


def fake_embedding(text: str, size: int = 64) -> list[float]:
    """Words hashed into a small vector, so similar texts get similar vectors (tests only)."""
    vector = [0.0] * size
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % size] += 1.0
    length = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / length for v in vector]
