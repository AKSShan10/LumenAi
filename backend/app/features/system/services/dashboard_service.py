"""The Dashboard: where every job, CV, interview and report stands. Only counting with code, no AI.

    dashboard(session, job_id)   everything the Dashboard page shows; job_id = one job, None = all jobs
      tiles        the numbers in the top row
      funnel       how many candidates reached each step (applied → screened → shortlisted → interviewed →
                   assessed → hired), each also as % of the applications
      scores       the average CV, interview and overall score, and how many overall scores are 0-49 / 50-74 / 75-100
      attention    what waits for the interviewer (interviews soon, answers to analyse, decisions, CVs to review ...)
      jobs         one row per job (always all jobs)
      workflows    AI runs of the last 7 days per stage, how many failed, and the AI model in use
"""
from collections import defaultdict
from datetime import timedelta

from sqlmodel import Session, select

from app.ai.model_choice import current_model
from app.features.assessments.models import Assessment
from app.features.candidates.models import Candidate
from app.features.interviews.models import InterviewSession
from app.features.jobs.models import Job
from app.features.qa_analysis.models import QaAnalysis
from app.features.screening.models import ScreeningResult, ShortlistEntry
from app.features.system.models import WorkflowRun
from app.features.talent_pool.models import TalentInvite, TalentPoolEntry
from app.features.talent_pool.services.pool_service import state as pool_state
from app.utils.datetime_utils import as_utc, utc_now

DAYS = 7                                    # "new this week" and the AI health window
SOON_HOURS = 24                             # "interviews in the next 24 hours"
BANDS = [("0-49", 0, 50), ("50-74", 50, 75), ("75-100", 75, 101)]   # the same colours as the rest of the app


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def _avg(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def dashboard(session: Session, job_id: int | None = None) -> dict:
    now = utc_now()
    week_ago = now - timedelta(days=DAYS)

    # ---------- read everything once (the tables are small); one job if job_id is given ----------
    def of_job(model):
        query = select(model)
        return session.exec(query.where(model.job_id == job_id) if job_id else query).all()

    jobs = session.exec(select(Job)).all()
    candidates = of_job(Candidate)
    screenings = of_job(ScreeningResult)
    shortlist = of_job(ShortlistEntry)
    interviews = of_job(InterviewSession)
    reports = of_job(Assessment)
    analyses = {a.session_id: a for a in session.exec(select(QaAnalysis)).all()}
    candidate_ids = {c.id for c in candidates}
    pool = [p for p in session.exec(select(TalentPoolEntry)).all() if not job_id or p.candidate_id in candidate_ids]
    invites = session.exec(select(TalentInvite)).all()

    done = [r for r in reports if r.status == "done"]
    ended = [i for i in interviews if i.status == "ended"]
    screened = [s for s in screenings if not s.stale and s.result in ("passed", "excluded")]
    to_review = [s for s in screenings if s.result == "needs_review" and not s.decision]

    # ---------- tiles ----------
    shown_jobs = [j for j in jobs if not job_id or j.id == job_id]
    tiles = {
        "open_jobs": sum(j.status == "approved" for j in shown_jobs),
        "draft_jobs": sum(j.status != "approved" for j in shown_jobs),
        "applications": len(candidates),
        "new_applications": sum(as_utc(c.created_at) >= week_ago for c in candidates),
        "shortlisted": len(shortlist),
        "interviews_upcoming": sum(i.status == "scheduled" and as_utc(i.scheduled_at) >= now for i in interviews),
        "interviews_ended": len(ended),
        "assessed": len(done),
        "pending_decisions": sum(r.decision == "pending" for r in done),
        "pool_active": sum(pool_state(p) == "active" for p in pool),
        "invites_sent": sum(i.pool_id in {p.id for p in pool} for i in invites),
    }

    # ---------- funnel: distinct candidates at each step ----------
    applied = len(candidates)
    steps = [("Applied", applied),
             ("Screened", len({s.candidate_id for s in screened})),
             ("Shortlisted", len({s.candidate_id for s in shortlist})),
             ("Interviewed", len({i.candidate_id for i in ended})),
             ("Assessed", len({r.candidate_id for r in done})),
             ("Hired", sum(r.decision == "hire" for r in done))]
    funnel = [{"step": name, "count": count, "percent": _pct(count, applied)} for name, count in steps]

    # ---------- scores ----------
    overall = [r.overall_score for r in done if r.overall_score is not None]
    scores = {"cv": _avg([r.cv_score for r in done]), "interview": _avg([r.interview_score for r in done]),
              "overall": _avg(overall),
              "bands": [{"band": name, "count": sum(low <= s < high for s in overall)} for name, low, high in BANDS],
              "decisions": {d: sum(r.decision == d for r in done) for d in ("hire", "hold", "reject", "pending")}}

    # ---------- what waits for the interviewer ----------
    soon = [i for i in interviews if i.status == "scheduled" and now <= as_utc(i.scheduled_at) <= now + timedelta(hours=SOON_HOURS)]
    not_analysed = [i for i in ended if not analyses.get(i.id) or analyses[i.id].status != "done"]
    analysed_ids = {i.candidate_id for i in ended if analyses.get(i.id) and analyses[i.id].status == "done"}
    not_assessed = analysed_ids - {r.candidate_id for r in reports if r.status in ("done", "running")}
    not_sent = [i for i in interviews if i.status == "scheduled" and i.invitation_status != "sent"]
    attention = [item for item in [
        {"key": "soon", "count": len(soon), "page": "interviews", "text": "interviews in the next 24 hours"},
        {"key": "invitation", "count": len(not_sent), "page": "interviews", "text": "invitations not sent yet"},
        {"key": "analyse", "count": len(not_analysed), "page": "interviews", "text": "ended interviews to analyse"},
        {"key": "assess", "count": len(not_assessed), "page": "reports", "text": "analysed candidates without an assessment"},
        {"key": "decide", "count": tiles["pending_decisions"], "page": "reports", "text": "assessments waiting for your decision"},
        {"key": "review", "count": len(to_review), "page": "candidates", "text": "CVs that need your review"},
    ] if item["count"]]

    # ---------- one row per job (always all jobs) ----------
    by_job = defaultdict(lambda: defaultdict(int))
    for c in session.exec(select(Candidate)).all():
        by_job[c.job_id]["applied"] += 1
    for s in session.exec(select(ShortlistEntry)).all():
        by_job[s.job_id]["shortlisted"] += 1
    interviewed = defaultdict(set)
    for i in session.exec(select(InterviewSession).where(InterviewSession.status == "ended")).all():
        interviewed[i.job_id].add(i.candidate_id)
    job_reports = defaultdict(list)
    for r in session.exec(select(Assessment).where(Assessment.status == "done")).all():
        job_reports[r.job_id].append(r)
    job_rows = []
    for job in sorted(jobs, key=lambda j: (j.status != "approved", j.title.lower())):
        rs = job_reports[job.id]
        job_rows.append({"job_id": job.id, "title": job.title, "status": job.status,
                         "applied": by_job[job.id]["applied"], "shortlisted": by_job[job.id]["shortlisted"],
                         "interviewed": len(interviewed[job.id]), "assessed": len(rs),
                         "avg_overall": _avg([r.overall_score for r in rs]),
                         "hire": sum(r.decision == "hire" for r in rs), "hold": sum(r.decision == "hold" for r in rs),
                         "reject": sum(r.decision == "reject" for r in rs),
                         "pending": sum(r.decision == "pending" for r in rs)})

    # ---------- AI workflow health: the last 7 days ----------
    runs = defaultdict(lambda: {"runs": 0, "failed": 0})
    for run in session.exec(select(WorkflowRun)).all():
        if as_utc(run.started_at) >= week_ago:
            runs[run.stage]["runs"] += 1
            runs[run.stage]["failed"] += run.outcome.startswith("failed")
    workflows = {"model": current_model(), "days": DAYS,
                 "stages": sorted(({"stage": stage, **n, "failure_rate": _pct(n["failed"], n["runs"])}
                                   for stage, n in runs.items()), key=lambda s: -s["runs"])}

    return {"job_id": job_id, "tiles": tiles, "funnel": funnel, "scores": scores, "attention": attention,
            "jobs": job_rows, "workflows": workflows}
