"""Consolidated assessment (F6): start it, read it, record the decision, compare the candidates of a job.

    start(session, candidate)         "Create assessment": checks the CV score and the interview analysis exist
    run(candidate_id)                 runs the workflow (graphs/assessment_graph.py); called as a background task
    result(session, candidate)        the report for the page (it asks every 3 s while "running")
    decide(session, candidate, ...)   the interviewer records hire, hold or reject (never the AI)
    comparison(session, job)          every interviewed candidate of the job, best overall score first
    resume_running()                  after a restart: assessments that were still running start again
"""
import logging

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core import config
from app.core.database import engine
from app.features.assessments.models import Assessment
from app.features.assessments.schemas import AssessmentOut, ComparisonRow, DecisionIn
from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession
from app.features.jobs.models import Job
from app.features.qa_analysis.models import QaAnalysis
from app.features.screening.models import ScreeningResult
from app.graphs.assessment_graph import assess_candidate
from app.utils.datetime_utils import utc_now

log = logging.getLogger("assessment")


# The newest finished interview analysis of a candidate, or None
def _done_analysis(session: Session, candidate_id: int) -> QaAnalysis | None:
    interview_ids = session.exec(select(InterviewSession.id).where(InterviewSession.candidate_id == candidate_id)).all()
    return session.exec(select(QaAnalysis).where(QaAnalysis.session_id.in_(interview_ids or [0]),
                                                 QaAnalysis.status == "done")
                        .order_by(QaAnalysis.session_id.desc())).first()


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
        return AssessmentOut(**names, status="not_started", cv_weight=config.ASSESSMENT_CV_WEIGHT)
    return AssessmentOut(**names, **row.model_dump(exclude={"id", "candidate_id", "job_id"}))


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
    rows = []
    for candidate_id in dict.fromkeys(i.candidate_id for i in interviews):          # each candidate once
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            continue
        screening = session.exec(select(ScreeningResult).where(ScreeningResult.candidate_id == candidate_id)).first()
        analysis = _done_analysis(session, candidate_id)
        report = session.exec(select(Assessment).where(Assessment.candidate_id == candidate_id)).first()
        rows.append(ComparisonRow(
            candidate_id=candidate_id, candidate_name=candidate.full_name,
            interview_ended=any(i.candidate_id == candidate_id and i.status == "ended" for i in interviews),
            analysis_done=analysis is not None, status=report.status if report else "not_started",
            cv_score=report.cv_score if report and report.cv_score is not None
            else (screening.weighted_score if screening else None),
            interview_score=report.interview_score if report and report.interview_score is not None
            else (analysis.interview_score if analysis else None),
            overall_score=report.overall_score if report else None,
            cv_weight=report.cv_weight if report and report.status == "done" else config.ASSESSMENT_CV_WEIGHT,
            decision=report.decision if report else "pending"))
    rows.sort(key=lambda r: (r.overall_score is None, -(r.overall_score or 0), r.candidate_name))
    return rows


def resume_running() -> None:
    """Assessments that were running when the backend stopped start again (main.py calls this at start)."""
    with Session(engine) as session:
        waiting = session.exec(select(Assessment.candidate_id).where(Assessment.status == "running")).all()
    for candidate_id in waiting:
        log.info("assessment candidate=%s resumed after a restart", candidate_id)
        run(candidate_id)
