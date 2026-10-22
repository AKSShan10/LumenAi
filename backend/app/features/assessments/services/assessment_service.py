"""Consolidated assessment (F6): start it, read it, record the decision, compare the candidates of a job.

    start(session, candidate)         "Create assessment": checks the CV score and the interview analysis exist
    run(candidate_id)                 runs the workflow (graphs/assessment_graph.py); called as a background task
    result(session, candidate)        the report for the page (it asks every 3 s while "running"), with the parts
                                      behind the scores (breakdown)
    decide(session, candidate, ...)   the interviewer records hire, hold or reject (never the AI)
    comparison(session, job)          every interviewed candidate of the job, best overall score first
    set_weight(session, job, weight)  the interviewer changes the CV / interview split; overall scores recalculated
    resume_running()                  after a restart: assessments that were still running start again
"""
import logging

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.database import engine
from app.features.assessments.models import Assessment
from app.features.assessments.schemas import AssessmentOut, ComparisonRow, DecisionIn, PartScore, RequirementRow
from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession
from app.features.jobs.models import Job
from app.features.qa_analysis.models import QaAnalysis, QaItem
from app.features.screening.models import ScreeningResult
from app.features.talent_pool.models import TalentPoolEntry
from app.features.talent_pool.services.pool_service import state as pool_state
from app.graphs.assessment_graph import assess_candidate, job_cv_weight, overall_score
from app.utils.datetime_utils import utc_now

log = logging.getLogger("assessment")

CV_PARTS = [("skills", "Skills"), ("experience", "Experience"), ("qualifications", "Qualifications")]
INTERVIEW_PARTS = [("relevance", "Relevance"), ("accuracy", "Accuracy"), ("completeness", "Completeness"),
                   ("articulation", "Articulation")]


# The newest finished interview analysis of a candidate, or None
def _done_analysis(session: Session, candidate_id: int) -> QaAnalysis | None:
    interview_ids = session.exec(select(InterviewSession.id).where(InterviewSession.candidate_id == candidate_id)).all()
    return session.exec(select(QaAnalysis).where(QaAnalysis.session_id.in_(interview_ids or [0]),
                                                 QaAnalysis.status == "done")
                        .order_by(QaAnalysis.session_id.desc())).first()


def breakdown(session: Session, job: Job | None, candidate_id: int, session_id: int | None) -> dict:
    """The parts behind the totals, read from the saved results (code only, no AI):
    the CV section scores, the average of each interview criterion, and every requirement with its CV and interview
    result. So the report shows where each total comes from."""
    screening = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).first()
    sections = (screening.sections or {}) if screening else {}
    cv_parts = [PartScore(name=label, score=(sections.get(key) or {}).get("score"))
                for key, label in CV_PARTS if isinstance(sections.get(key), dict)]

    analysis = session.exec(select(QaAnalysis).where(QaAnalysis.session_id == (session_id or 0))).first()
    items = session.exec(select(QaItem).where(QaItem.session_id == (session_id or 0),
                                              QaItem.job_related.is_(True))).all()
    interview_parts = []
    for key, label in INTERVIEW_PARTS:
        grades = [getattr(i, key) for i in items if getattr(i, key) is not None]
        interview_parts.append(PartScore(name=label, score=round(sum(grades) / len(grades), 1) if grades else None))

    skills = list(dict.fromkeys(((job.required_skills or []) + (job.preferred_skills or [])) if job else []))
    covered = set(analysis.covered or []) if analysis else set()
    matches = {m.get("requirement"): m for m in (screening.matches or []) if isinstance(m, dict)} if screening else {}
    rows = [RequirementRow(requirement=name, kind=str(matches.get(name, {}).get("kind") or ""),
                           cv=str(matches.get(name, {}).get("status") or "unchecked"),
                           cv_how=str(matches.get(name, {}).get("how") or ""),
                           interview=name in covered) for name in skills]
    rows += [RequirementRow(requirement=str(name), kind=str(m.get("kind") or ""), cv=str(m.get("status") or "unchecked"),
                            cv_how=str(m.get("how") or "")) for name, m in matches.items() if name not in skills]
    return {"cv_parts": cv_parts, "interview_parts": interview_parts if items else [], "requirements": rows}


def start(session: Session, candidate: Candidate) -> AssessmentOut:
    """Marks the assessment running (a new one, or again); the router then runs it in the background."""
    screening = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate.id)).first()
    if not screening or screening.weighted_score is None:
        raise HTTPException(409, "The CV has no score yet. Screen the CV first.")
    if not _done_analysis(session, candidate.id):
        raise HTTPException(409, "Analyse the interview answers first (Interviews page → Analyse answers).")
    row = session.exec(select(Assessment).where(Assessment.candidate_id == candidate.id)).first()
    if row and row.status == "running":
        raise HTTPException(409, "The assessment is already running. Please wait a moment.")
    row = row or Assessment(candidate_id=candidate.id, job_id=candidate.job_id)
    row.status, row.error, row.updated_at = "running", "", utc_now()      # the old report stays until the new one
    session.add(row)
    session.commit()
    return result(session, candidate)


def run(candidate_id: int) -> None:
    """The work itself (about 4-6 AI calls). Runs after the answer was sent, so the page does not wait."""
    assess_candidate(candidate_id)                    # → the LangGraph workflow; it saves the result itself


def result(session: Session, candidate: Candidate) -> AssessmentOut:
    """The report of this candidate; status "not_started" if nobody created it yet."""
    job = session.get(Job, candidate.job_id)
    names = {"candidate_id": candidate.id, "candidate_name": candidate.full_name, "job_id": candidate.job_id,
             "job_title": job.title if job else ""}
    row = session.exec(select(Assessment).where(Assessment.candidate_id == candidate.id)).first()
    if not row:
        return AssessmentOut(**names, status="not_started", cv_weight=job_cv_weight(job))
    parts = breakdown(session, job, candidate.id, row.session_id) if row.session_id else {}
    return AssessmentOut(**names, **row.model_dump(exclude={"id", "candidate_id", "job_id"}), **parts)


def decide(session: Session, candidate: Candidate, body: DecisionIn, email: str) -> AssessmentOut:
    """The interviewer's decision with an optional note. Only on a finished report; "pending" takes it back."""
    row = session.exec(select(Assessment).where(Assessment.candidate_id == candidate.id)).first()
    if not row or row.status != "done":
        raise HTTPException(409, "Create the assessment first, then record the decision.")
    row.decision, row.decision_note = body.decision, body.note.strip()
    row.decided_by, row.decided_at = (email, utc_now()) if body.decision != "pending" else ("", None)
    session.add(row)
    session.commit()
    log.info("assessment candidate=%s decision=%s", candidate.id, body.decision)
    return result(session, candidate)


def comparison(session: Session, job: Job) -> list[ComparisonRow]:
    """Every candidate of the job who had an interview, best overall score first (not assessed ones last)."""
    interviews = session.exec(select(InterviewSession).where(InterviewSession.job_id == job.id)).all()
    weight = job_cv_weight(job)                       # the job's CV / interview split (40 / 60 by default)
    rows = []
    for candidate_id in dict.fromkeys(i.candidate_id for i in interviews):          # each candidate once
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            continue
        screening = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).first()
        analysis = _done_analysis(session, candidate_id)
        report = session.exec(select(Assessment).where(Assessment.candidate_id == candidate_id)).first()
        kept = session.exec(select(TalentPoolEntry).where(TalentPoolEntry.candidate_id == candidate_id)).first()
        rows.append(ComparisonRow(
            candidate_id=candidate_id, candidate_name=candidate.full_name,
            interview_ended=any(i.candidate_id == candidate_id and i.status == "ended" for i in interviews),
            analysis_done=analysis is not None, status=report.status if report else "not_started",
            cv_score=report.cv_score if report and report.cv_score is not None
            else (screening.weighted_score if screening else None),
            interview_score=report.interview_score if report and report.interview_score is not None
            else (analysis.interview_score if analysis else None),
            overall_score=report.overall_score if report else None,
            cv_weight=weight,
            pool=pool_state(kept) if kept else "",
            decision=report.decision if report else "pending"))
    rows.sort(key=lambda r: (r.overall_score is None, -(r.overall_score or 0), r.candidate_name))
    return rows


def set_weight(session: Session, job: Job, cv_weight: int) -> list[ComparisonRow]:
    """Saves the job's CV weight (the interview gets the rest) and recalculates the overall score of every finished
    assessment of the job. Only maths, no AI: the reports, quotes and decisions stay as they are."""
    job.assessment_cv_weight = cv_weight
    session.add(job)
    reports = session.exec(select(Assessment).where(Assessment.job_id == job.id, Assessment.status == "done")).all()
    for report in reports:
        report.cv_weight = cv_weight
        report.overall_score = overall_score(report.cv_score, report.interview_score, cv_weight)
        session.add(report)
    session.commit()
    log.info("assessment weight job=%s cv=%s%% interview=%s%% reports=%s", job.id, cv_weight, 100 - cv_weight,
             len(reports))
    return comparison(session, job)


def resume_running() -> None:
    """Assessments that were running when the backend stopped start again (main.py calls this at start)."""
    with Session(engine) as session:
        waiting = session.exec(select(Assessment.candidate_id).where(Assessment.status == "running")).all()
    for candidate_id in waiting:
        log.info("assessment candidate=%s resumed after a restart", candidate_id)
        run(candidate_id)
