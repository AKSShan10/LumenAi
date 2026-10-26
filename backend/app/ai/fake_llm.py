"""An offline stand-in for the AI model, used when LLM_PROVIDER=fake.

Use it for tests and for trying the app without an API key. Use a real model for the actual demo.
Each feature adds its own fake answer here, chosen by the prompt it sends.
The answers come from simple word rules. This is NOT real AI.
"""
import hashlib
import math
import re

from app.utils.skill_names import find_skill

from app.features.interview_helper.services.helper_service import CHAT_PROMPT, QUESTIONS_PROMPT
from app.graphs.cv_screening_prompts import ATS_KEYWORDS_PROMPT, EXTRACT_PROFILE_PROMPT, SCORE_SECTIONS_PROMPT
from app.graphs.invitation_prompts import (
    INVITATION_CHANGE_PROMPT, INVITATION_PROMPT, INVITATION_TEMPLATE_CHANGE_PROMPT, INVITATION_TEMPLATE_PROMPT)
from app.graphs.job_description_prompts import JOB_DRAFT_PROMPT, JOB_REVISE_PROMPT
from app.graphs.qa_analysis_prompts import GRADE_PROMPTS, REQUIREMENTS_PROMPT, SEGMENT_PROMPT
from app.graphs.talent_invite_prompts import TALENT_INVITE_PROMPT
from app.features.claims.services.claim_prompts import COMPARE_PROMPT, EXTRACT_PROMPT
from app.features.interview_quality.services.interview_quality_prompts import GRADE_QUESTIONS_PROMPT, RECOMMEND_PROMPT
from app.graphs.assessment_prompts import (
    AREAS_PROMPT, REPAIR_PROMPT, STRENGTHS_PROMPT, SUMMARY_PROMPT, WEAKNESSES_PROMPT)


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
    if instructions in (INVITATION_PROMPT, INVITATION_TEMPLATE_PROMPT, INVITATION_CHANGE_PROMPT,
                        INVITATION_TEMPLATE_CHANGE_PROMPT):
        return _fake_invitation(data)
    if instructions == QUESTIONS_PROMPT:
        return _fake_questions(data)
    if instructions == CHAT_PROMPT:
        return _fake_helper_chat(data)
    if instructions == SEGMENT_PROMPT:
        return _fake_qa_pairs(data)
    if instructions == REQUIREMENTS_PROMPT:
        return _fake_qa_requirements(data)
    if instructions in GRADE_PROMPTS.values():
        return _fake_grades(data)
    if instructions == STRENGTHS_PROMPT:
        return {"strengths": _fake_evidence(data, strong=True)}
    if instructions == WEAKNESSES_PROMPT:
        return {"weaknesses": _fake_evidence(data, strong=False)}
    if instructions == AREAS_PROMPT:
        return {"areas": [{"area": gap, "why": "No proof in the CV or the interview yet. (Fake AI text.)",
                           "requirement": gap, "quote": ""} for gap in data.get("evidence_gaps", [])] or
                [{"area": f"Follow up: {a['question']}", "why": "The answer was short. (Fake AI text.)", "requirement": "",
                  "quote": " ".join(a["answer"].split()[:4])} for a in data["answers"][:1]]}
    if instructions == REPAIR_PROMPT:
        return _fake_repair(data)
    if instructions == EXTRACT_PROMPT:
        return _fake_claims(data)
    if instructions == COMPARE_PROMPT:
        return _fake_compare(data)
    if instructions == GRADE_QUESTIONS_PROMPT:
        return _fake_question_review(data)
    if instructions == RECOMMEND_PROMPT:
        return _fake_recommendations(data)
    if instructions == TALENT_INVITE_PROMPT:
        skills = ", ".join(data["fitting_skills"]) or "your skills"
        if data.get("previous_draft") and "short" in data["instruction"].lower():     # "Write again": a shorter text
            return {"subject": data["previous_draft"]["subject"] or f"A new opening: {data['new_job']}",
                    "body": f"Dear {data['first_name']},\n\nThank you for your earlier application. We have a new "
                            f"opening for {data['new_job']}, and your experience with {skills} may fit it. We would be "
                            f"glad if you applied. (Fake AI text.)"}
        return {"subject": f"A new opening: {data['new_job']}",
                "body": f"Dear {data['first_name']},\n\nThank you again for your earlier application for "
                        f"{data['earlier_job']}. We now have a new opening for {data['new_job']}, and your experience "
                        f"with {skills} may fit this role well. We would be glad if you applied for it. "
                        f"(Fake AI text for offline tests.)"}
    if instructions == SUMMARY_PROMPT:
        return {"summary": f"Overall score {data['overall_score']} (CV {data['cv_score']}, interview "
                           f"{data['interview_score']}). {len(data['strengths'])} strengths and "
                           f"{len(data['weaknesses'])} weaknesses were found. (Fake AI text for offline tests.)"}
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
    if data.get("previous_draft") and "short" in data.get("change_request", "").lower():   # "Write again: shorter"
        return {"subject": data["previous_draft"]["subject"] or f"Interview invitation: {data['job_title']}",
                "body": f"Dear {data['candidate_name']},\n\nPlease join our online interview for {data['job_title']} on "
                        f"{data['date']} at {data['time']}:\n{{join_link}}\n\nKind regards,\n{data['interviewer_name']}"}
    body = (f"Dear {data['candidate_name']},\n\nThank you for applying for the {data['job_title']} position. "
            f"We would like to invite you to an online video interview on {data['date']} at {data['time']} "
            f"(about {data['length_minutes']} minutes).\n\nJoin with your personal link:\n{{join_link}}\n\n"
            "A calendar invite is attached. Please reply if the time does not suit you.\n\n"
            f"Kind regards,\n{data['interviewer_name']}\nHiring team\n(Fake AI text for offline tests.)")
    return {"subject": f"Interview invitation: {data['job_title']}", "body": body}


def _fake_questions(data: dict) -> dict:
    """One question per requirement: first the topic, then what the CV did not show, then the required skills.
    Already suggested questions are skipped."""
    wanted = ([data["topic"]] if data.get("topic") else []) + data.get("not_shown_in_cv", []) + \
        data["job"].get("required_skills", []) + ["teamwork", "problem solving"]
    questions, seen = [], set(data.get("already_suggested", []))
    note = (data.get("company_notes") or [{}])[0]               # the first company note found (RAG), if any
    asks = ["Can you describe a project where you used {}?", "What was the hardest problem you solved with {}?",
            "How would you explain {} to a new team member?"]
    for ask in asks:
        for requirement in wanted:
            question = ask.format(requirement)
            if question in seen:
                continue
            seen.add(question)
            questions.append({"question": question, "requirement": requirement,
                              "why": f"The job asks for {requirement}. (Fake AI text for offline tests.)",
                              "model_answer": f"A strong answer names a real project, what the candidate did with "
                                              f"{requirement} and what the result was.",
                              "source": note.get("title", "") if not questions else ""})   # the first uses the note
    return {"questions": questions[:8]}


def _fake_helper_chat(data: dict) -> dict:
    """Repeats the interviewer's last message and lists two required skills to ask about."""
    last = data["conversation"][-1]["text"] if data.get("conversation") else ""
    skills = (data["job"].get("required_skills") or ["the main skills"])[:2]
    lines = "\n".join(f"{i}. Ask about {skill}." for i, skill in enumerate(skills, 1))
    notes = [n["title"] for n in data.get("company_notes", [])][:1]
    return {"answer": f"You asked: {last}\n{lines}\n(Fake AI text for offline tests.)", "sources": notes}


# ---------- Q&A analysis (qa_analysis_graph.py) ----------

SMALL_TALK = ("hear me", "how are you", "ready to start", "any questions for us")


def _fake_qa_pairs(data: dict) -> dict:
    """An interviewer line with "?" is a question; the candidate lines after it are the answer.
    "... and how ...?" is split into two parts. Greetings are small talk."""
    pairs, current = [], None
    for line in data["lines"]:
        if line["speaker"] == "Interviewer":
            current = None
            if line["text"].strip().endswith("?"):
                current = {"question": line["text"].strip(), "question_lines": [line["n"]], "answer_lines": [],
                           "job_related": not any(words in line["text"].lower() for words in SMALL_TALK)}
                pairs.append(current)
        elif current is not None:
            current["answer_lines"].append(line["n"])
    result = []
    for pair in pairs:
        first, joint, second = pair["question"].partition(" and how ")
        if joint:                                      # one question that asks two things
            result.append({**pair, "question": first + "?", "split": True})
            result.append({**pair, "question": "How " + second, "split": True})
        else:
            result.append({**pair, "split": False})
    return {"pairs": result}


def _fake_qa_requirements(data: dict) -> dict:
    """A requirement is linked when its name appears in the question or the answer."""
    return {"pairs": [{"n": p["n"], "requirements": [r for r in data["requirements"]
                                                     if r.lower() in (p["question"] + " " + p["answer"]).lower()]}
                      for p in data["pairs"]]}


def _fake_grades(data: dict) -> dict:
    """Longer answers get better grades. The quote is the first four words of the answer."""
    notes = [n["title"] for n in data.get("company_notes", [])][:1]
    grades = []
    for pair in data["pairs"]:
        words = pair["answer"].split()
        grade = 75 if len(words) >= 12 else 50 if len(words) >= 6 else 25
        grades.append({"n": pair["n"], "grade": grade, "quote": " ".join(words[:4]),
                       "reason": f"The answer has {len(words)} words. (Fake AI text for offline tests.)",
                       "sources": notes,
                       "follow_up": "" if grade >= 75 else "Can you give a concrete example from your work?"})
    return {"grades": grades}


# ---------- Assessment (assessment_graph.py) ----------

def _fake_evidence(data: dict, strong: bool) -> list:
    """Strengths: requirements the CV met (quote: the CV words from that skill on) and answers scoring 50+.
    Weaknesses: answers scoring below 50. Every quote is copied from the CV text or an answer."""
    items, words = [], data["cv_text"].split()
    if strong:
        for match in data["requirement_matches"]:
            spot = next((n for n, w in enumerate(words) if match["requirement"].lower() in w.lower()), None)
            if match["status"] == "met" and spot is not None:
                items.append({"text": f"The CV shows {match['requirement']}.", "quote": " ".join(words[spot:spot + 3]),
                              "source": "CV"})
    for answer in data["answers"]:
        good = (answer["score"] or 0) >= 50
        if good == strong:
            items.append({"text": f"{'Good' if strong else 'Weak'} answer about: {answer['question']}",
                          "quote": " ".join(answer["answer"].split()[:4]), "source": "Interview"})
    return items[:5]


def _fake_repair(data: dict) -> dict:
    """Leaves out the items whose quote was not found."""
    wrong = {p["quote"] for p in data["problems"]}
    return {"strengths": [i for i in data["strengths"] if i["quote"] not in wrong],
            "weaknesses": [i for i in data["weaknesses"] if i["quote"] not in wrong]}


# ---------- CV claim verification (claim_service.py) ----------

def _fake_claims(data: dict) -> dict:
    """The skills line and the experience line of a made-up CV become claims; the quotes are copied from the CV."""
    claims = []
    for line in data["cv_text"].splitlines():
        if line.lower().startswith("skills:"):
            skills = [s.strip() for s in line.split(":", 1)[1].split(",") if s.strip()][:3]
            for n, skill in enumerate(skills, 1):          # the quote: "Skills: Python", "Skills: Python, FastAPI" ...
                claims.append({"claim": f"Works with {skill}.", "cv_quote": "Skills: " + ", ".join(skills[:n])})
        if line.lower().startswith("experience:"):
            claims.append({"claim": "Has the stated years of experience.", "cv_quote": line.strip()[:60]})
    return {"claims": claims}


def _fake_compare(data: dict) -> dict:
    """A claim whose main word is in a candidate line is supported (quote: that line's first words); else not discussed."""
    out = []
    for claim in data["claims"]:
        word = claim["claim"].replace("Works with ", "").rstrip(".").lower()
        line = next((l for l in data["lines"] if word and word in l["text"].lower()), None)
        if line:
            out.append({"n": claim["n"], "status": "supported", "line": line["n"],
                        "interview_quote": " ".join(line["text"].split()[:4]), "note": "Mentioned in the interview.",
                        "follow_up": ""})
        else:
            out.append({"n": claim["n"], "status": "not_discussed", "line": 0, "interview_quote": "",
                        "note": "Not mentioned.", "follow_up": f"Could you tell me about: {claim['claim']}"})
    return {"claims": out}


# ---------- interview quality (interview_quality_service.py) ----------

def _fake_question_review(data: dict) -> dict:
    """A question that names a job requirement is relevant (80), else 40; open when it starts with how/what/tell..."""
    out = []
    for q in data["questions"]:
        text = q["question"].lower()
        relevant = any(r.lower() in text for r in data["requirements"])
        open_question = text.startswith(("how", "what", "why", "tell", "describe", "explain", "walk"))
        out.append({"n": q["n"], "relevance": 80 if relevant else 40, "open": open_question,
                    "reason": "Names a job requirement. (Fake AI text.)" if relevant else "Not about a requirement. (Fake AI text.)",
                    "better": "" if open_question else f"Could you describe {q['question'].rstrip('?').lower()}?"})
    return {"questions": out}


def _fake_recommendations(data: dict) -> dict:
    """One improvement per kind of fact, in a fixed order; the summary names the job."""
    recs = [{"basis": "requirement", "ref": r, "text": f"Ask about {r} next time. (Fake AI text.)"}
            for r in data["not_asked"][:2]]
    recs += [{"basis": "question", "ref": str(q["n"]), "text": f"Ask question {q['n']} in a more open way. (Fake AI text.)"}
             for q in data["low_signal"][:2]]
    if not data["talk"]["balanced"]:
        recs.append({"basis": "talk", "ref": "", "text": "Let the candidate speak more. (Fake AI text.)"})
    return {"summary": f"The interview for {data['job_title']} was reviewed. (Fake AI text for offline tests.)",
            "recommendations": recs}

