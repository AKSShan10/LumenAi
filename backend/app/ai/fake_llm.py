"""An offline stand-in for the AI model, used when LLM_PROVIDER=fake.

Use it for tests and for trying the app without an API key. Use a real model for the actual demo.
Each feature adds its own fake answer here, chosen by the prompt it sends.
The answers come from simple word rules. This is NOT real AI.
"""
import hashlib
import math
import re

from app.utils.skill_names import find_skill

from app.graphs.cv_screening_prompts import ATS_KEYWORDS_PROMPT, EXTRACT_PROFILE_PROMPT, SCORE_SECTIONS_PROMPT
from app.graphs.invitation_prompts import INVITATION_PROMPT, INVITATION_TEMPLATE_PROMPT
from app.graphs.job_description_prompts import JOB_DRAFT_PROMPT, JOB_REVISE_PROMPT


# Returns a word-rule answer instead of Gemini, chosen by which prompt was sent (used by llm_json)
def fake_answer(instructions: str, data) -> dict:
    if instructions == JOB_DRAFT_PROMPT:
        return _fake_job(data)
    if instructions == JOB_REVISE_PROMPT:
        return _fake_job(data)          # the same rules again, from the same prompt
    if instructions == EXTRACT_PROFILE_PROMPT:
        return _fake_cv_fields(data)
    if instructions == SCORE_SECTIONS_PROMPT:
        return _fake_section_scores(data)
    if instructions == ATS_KEYWORDS_PROMPT:
        return _fake_ats_keywords(data)
    if instructions in (INVITATION_PROMPT, INVITATION_TEMPLATE_PROMPT):
        return _fake_invitation(data)
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


KNOWN_SKILLS = ("Python", "FastAPI", "Django", "Flask", "PostgreSQL", "MySQL", "MongoDB", "Docker", "Kubernetes",
                "JavaScript", "TypeScript", "React", "Node.js", "Java", "Spring", "Go", "AWS", "Git", "Redis", "Linux")


def _fake_cv_fields(data: dict) -> dict:
    """CV fields by word rules: known skill names, the largest "N years", lines with a degree, "Job: ... at ..." lines.
    The qualification is judged like the real AI does in the same call."""
    text = data["cv"]
    if "FAKE-BAD-ANSWER" in text:                    # lets a test check what happens when the AI answers badly
        return {"skills": "not a list"}
    skills = [s for s in KNOWN_SKILLS if re.search(rf"(?<![\w.]){re.escape(s)}(?![\w])", text, re.IGNORECASE)]
    years = [float(y) for y in re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*years", text, re.IGNORECASE)]
    degrees = [line.strip()[:100] for line in text.splitlines()
               if re.search(r"\b(BSc|B\.Sc|MSc|M\.Sc|Bachelor|Master|PhD|Diploma)\b", line)]
    letters = [c for c in text if c.isalpha()]
    english = not letters or sum(c.isascii() for c in letters) / len(letters) > 0.7
    education = [{"degree": d, "institute": ""} for d in degrees]
    jobs = [{"title": m.group(1).strip(), "company": m.group(2).strip(), "years": 0}        # "Job: <title> at <company>"
            for m in re.finditer(r"^Job:\s*(.+?)\s+at\s+(.+)$", text, re.MULTILINE)]
    total = max(years, default=0)
    qualification = None
    if data["required_qualification"]:
        q = _fake_qualification({"required": data["required_qualification"], "education": education})
        qualification = {"status": "met" if q["met"] else "unmet", "reason": q["reason"],
                         "evidence": degrees[0] if q["met"] and degrees else ""}
    return {"skills": skills, "total_years": total, "education": education,
            "experience": jobs, "language": "en" if english else "bn",
            "requirement_checks": [_fake_requirement_check(r, text) for r in data.get("requirements", [])],
            "years_check": _fake_years_check(total, data.get("min_years") or 0, text),
            "qualification_check": qualification}


def _fake_years_check(years: float, minimum: float, cv: str) -> dict | None:
    """A stand-in for the AI judging the years: enough = met, a little less (3/4 or more) = partial."""
    if not minimum:
        return None
    status = "met" if years >= minimum else "partial" if years >= 0.75 * minimum else "unmet"
    line = _first_line(cv, r"\d+(?:\.\d+)?\s*\+?\s*years") if years else ""
    return {"status": status, "reason": f"Fake check: about {years:g} of {minimum:g} years.", "evidence": line}


# Words that are "close but not the same" for the fake AI's Partially met (a stand-in for judging by meaning).
FAKE_CLOSE = {"postgresql": ["mysql", "sql server"], "fastapi": ["flask", "django"], "playwright": ["selenium"]}


def _fake_requirement_check(requirement: str, cv: str) -> dict:
    """A stand-in for the AI judging by meaning (lines that only wish for a skill do not count, like the real AI):
    met: the skill, or a word of 4+ letters of it, is in a CV line (e.g. "test plans" for "Test planning");
    partial: a close tool is named (MySQL for PostgreSQL); else unmet. The evidence is a real CV line,
    except "FAKE-WRONG-QUOTE" in the CV, which makes the fake AI quote words that are not in the CV."""
    lines = [l for l in cv.splitlines() if not re.search(r"interested in|want to learn|not used|no experience", l, re.I)]
    usable = "\n".join(lines)
    how = find_skill(requirement, [], usable)          # also another name of it ("Postgres" for PostgreSQL)
    if how:
        line = _first_line(usable, re.escape(how.split('"')[1])) if '"' in how else ""
        evidence = "a made-up quote" if "FAKE-WRONG-QUOTE" in cv else line
        return {"requirement": requirement, "status": "met", "reason": f"Fake check: {how}.", "evidence": evidence}
    words = re.findall(r"[a-z]{4,}", requirement.lower())
    for word in words:
        line = _first_line(usable, rf"\b{re.escape(word[:5])}")
        if line:
            evidence = "a made-up quote" if "FAKE-WRONG-QUOTE" in cv else line
            return {"requirement": requirement, "status": "met", "reason": f"Fake check: the CV shows {requirement}.",
                    "evidence": evidence}
    for close in FAKE_CLOSE.get(requirement.lower(), []):
        line = _first_line(usable, rf"\b{re.escape(close)}\b")
        if line:
            return {"requirement": requirement, "status": "partial",
                    "reason": f"Fake check: {close} is close to {requirement}.", "evidence": line}
    return {"requirement": requirement, "status": "unmet", "reason": f"Fake check: no {requirement} in the CV.",
            "evidence": ""}


def _fake_ats_keywords(data: dict) -> dict:
    """The job's skills plus the known tool names found in the description."""
    words = list(data.get("required_skills") or []) + list(data.get("preferred_skills") or [])
    words += [s for s in KNOWN_SKILLS if re.search(rf"(?<![\w.]){re.escape(s)}(?![\w])", data.get("description") or "")]
    return {"keywords": list(dict.fromkeys(words))}


def _fake_qualification(data: dict) -> dict:
    """Met when a degree in the CV shares a subject word with the required qualification."""
    required = {w for w in re.findall(r"[a-z]{4,}", data["required"].lower())} - {"similar", "equivalent", "degree", "with"}
    for item in data["education"]:
        degree = str(item.get("degree", ""))
        words = set(re.findall(r"[a-z]{4,}", degree.lower())) | ({"computer", "science"} if "CSE" in degree else set())
        if required & words or "cse" in data["required"].lower() and "computer" in words:
            return {"met": True, "reason": f"Fake check: \"{degree}\" fits."}
    return {"met": False, "reason": "Fake check: no degree in the CV fits the requirement."}


def _first_line(text: str, pattern: str) -> str:
    """The first CV line that matches, cut to 20 words: the fake AI's "quote"."""
    line = next((line.strip() for line in text.splitlines() if re.search(pattern, line, re.IGNORECASE)), "")
    return " ".join(line.split()[:20])


def _fake_section_scores(data: dict) -> dict:
    """Scores by word rules: share of required skills named, years against the minimum, a degree line or not."""
    job, cv = data["job"], data["cv"]
    found = [s for s in job["required_skills"] if re.search(rf"(?<![\w.]){re.escape(s)}(?![\w])", cv, re.IGNORECASE)]
    skills = round(100 * len(found) / len(job["required_skills"])) if job["required_skills"] else 50
    years = max([float(y) for y in re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*years", cv, re.IGNORECASE)], default=0)
    experience = min(100, round(70 * years / job["min_years"])) if job["min_years"] else min(100, round(20 * years))
    degree = _first_line(cv, r"\b(BSc|B\.Sc|MSc|Bachelor|Master|PhD)\b")
    quote = lambda text: "Words that are not in the CV" if "FAKE-BAD-QUOTE" in cv else text   # noqa: E731
    return {"skills": {"score": skills, "reason": f"Fake check: {len(found)} of the required skills are named.",
                       "quote": quote(_first_line(cv, r"skills"))},
            "experience": {"score": experience, "reason": f"Fake check: about {years:g} years.",
                           "quote": quote(_first_line(cv, r"years"))},
            "qualifications": {"score": 85 if degree else 20, "reason": "Fake check: degree line found." if degree
                               else "Fake check: no degree found.", "quote": quote(degree)}}


FAKE_PDF_TEXT = (
    "Tanvir Hasan\n"
    "Made-up CV read by the fake AI from a PDF without a text layer (a scanned page).\n"
    "Skills: Python, FastAPI, PostgreSQL, Docker\n"
    "Experience: 3 years as a backend developer. Built REST APIs, stored data in PostgreSQL, wrote automated tests "
    "and deployed services with Docker. Worked in a team of six developers, reviewed code, planned releases and "
    "wrote clear documentation for other teams.\n"
    "Education: BSc in Computer Science and Engineering\n"
    "Languages: English")


def fake_pdf_text(pdf: bytes) -> str | None:
    """Stands in for the AI reading a PDF: the same made-up text for every real PDF file."""
    return FAKE_PDF_TEXT if pdf.startswith(b"%PDF") else None


def fake_embedding(text: str, size: int = 64) -> list[float]:
    """Words hashed into a small vector, so similar texts get similar vectors (tests only)."""
    vector = [0.0] * size
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % size] += 1.0
    length = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / length for v in vector]


def _fake_invitation(data: dict) -> dict:
    """A short invitation from the data, with the {join_link} placeholder (code puts the real link in)."""
    body = (f"Dear {data['candidate_name']},\n\nThank you for applying for the {data['job_title']} position. "
            f"We would like to invite you to an online video interview on {data['date']} at {data['time']} "
            f"(about {data['length_minutes']} minutes).\n\nJoin with your personal link:\n{{join_link}}\n\n"
            "A calendar invite is attached. Please reply if the time does not suit you.\n\n"
            f"Kind regards,\n{data['interviewer_name']}\nHiring team\n(Fake AI text for offline tests.)")
    return {"subject": f"Interview invitation: {data['job_title']}", "body": body}
