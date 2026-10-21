"""Consolidated assessment (interviewer only, login needed; the candidate never reaches it).

  POST /api/candidates/{id}/assessment            "Create assessment": answers 202, the work runs in the background
  GET  /api/candidates/{id}/assessment            the report; the page asks every 3 seconds while it is "running"
  PUT  /api/candidates/{id}/assessment/decision   {decision: hire | hold | reject | pending, note}: a person decides
  GET  /api/jobs/{id}/comparison                  the interviewed candidates of a job, best overall score first
  PUT  /api/jobs/{id}/assessment-weight           {cv_weight}: change the CV / interview split; scores recalculated

The routes only check the request; the work is in assessment_service.py and graphs/assessment_graph.py.
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import current_email, require_interviewer
from app.features.assessments.schemas import AssessmentOut, ComparisonRow, DecisionIn, WeightIn
from app.features.assessments.services import assessment_service
from app.features.candidates.routers.candidate_router import get_candidate_or_404
from app.features.jobs.services.job_service import get_job_or_404

router = APIRouter(prefix="/api", tags=["Assessment"], dependencies=[Depends(require_interviewer)])


@router.post("/candidates/{candidate_id}/assessment", response_model=AssessmentOut, status_code=202)
def start_assessment(candidate_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    """Starts the assessment. Needs a CV score and an analysed interview. The answer comes at once ("running")."""
    started = assessment_service.start(session, get_candidate_or_404(session, candidate_id))
    background.add_task(assessment_service.run, candidate_id)   # → runs after the answer is sent
    return started


@router.get("/candidates/{candidate_id}/assessment", response_model=AssessmentOut)
def get_assessment(candidate_id: int, session: Session = Depends(get_session)):
    """The report: scores, summary, strengths, weaknesses, evidence gaps, areas to explore, decision."""
    return assessment_service.result(session, get_candidate_or_404(session, candidate_id))


@router.put("/candidates/{candidate_id}/assessment/decision", response_model=AssessmentOut)
def record_decision(candidate_id: int, body: DecisionIn, session: Session = Depends(get_session),
                    email: str = Depends(current_email)):
    """The interviewer records hire, hold or reject with a note ("pending" takes it back)."""
    return assessment_service.decide(session, get_candidate_or_404(session, candidate_id), body, email)


@router.get("/jobs/{job_id}/comparison", response_model=list[ComparisonRow])
def compare_candidates(job_id: int, session: Session = Depends(get_session)):
    """The comparison table of the Reports page."""
    return assessment_service.comparison(session, get_job_or_404(session, job_id))


@router.put("/jobs/{job_id}/assessment-weight", response_model=list[ComparisonRow])
def change_weight(job_id: int, body: WeightIn, session: Session = Depends(get_session)):
    """The interviewer changes how much the CV counts (0-100 %); the overall scores of the job are recalculated."""
    return assessment_service.set_weight(session, get_job_or_404(session, job_id), body.cv_weight)
