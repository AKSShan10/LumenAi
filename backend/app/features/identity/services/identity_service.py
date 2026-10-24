"""The identity check of an interview (F7): is the person in the call the candidate of this interview?

    read_photo_face(candidate)              the face vector of the candidate's photo (or why it cannot be used)
    check(session, interview, frame)        compares one camera picture with this candidate's photo AND with every
                                            other candidate's photo in the system; saves the result
    decide(session, interview, decision)    the interviewer confirms, rejects, or clears the result
    result(session, interview)              what the interviewer's room shows

Results (never a silent guess; the interviewer always decides):
    confident      this candidate's photo matches well, and no other record matches as well
    low            a possible match, but not certain, or another record matches as well or better
    no_match       the face does not match the photo
    no_face        no face was found in the camera picture (ask the candidate to face the camera)
    no_photo / photo_unusable / engine_missing    the check cannot run (the reason is shown)
The camera picture is compared in memory and never saved.
"""
import logging

from fastapi import HTTPException
from sqlmodel import Session, select

from app.features.candidates.models import Candidate
from app.features.candidates.services.cv_storage_service import photo_file
from app.features.identity.schemas import IdentityOut
from app.features.identity.services import face_service
from app.features.identity.services.face_service import CONFIDENT, SAME_PERSON, FaceProblem
from app.features.interviews.models import InterviewSession
from app.features.jobs.models import Job
from app.utils.datetime_utils import utc_now

log = logging.getLogger("identity")

PHOTO_PROBLEMS = {"no_face": "No face was found in the photo from the application.",
                  "several_faces": "The photo from the application shows more than one face.",
                  "unreadable": "The photo from the application could not be read.",
                  "download_failed": "The photo could not be downloaded from the Google Form."}


def read_photo_face(candidate: Candidate) -> None:
    """Works out the face vector of the saved photo and sets candidate.face_status (the caller commits)."""
    path = photo_file(candidate)
    if not path:
        candidate.face_vector, candidate.face_status = [], "no_photo"
        return
    try:
        candidate.face_vector, candidate.face_status = face_service.face_vector(path.read_bytes()), "ready"
    except FaceProblem as problem:
        candidate.face_vector, candidate.face_status = [], problem.code


def _stop(identity: dict, code: str, message: str) -> dict:
    """The identity result for a check that could not compare (no photo, no face ...), with its message."""
    return {**identity, "result": code, "similarity": None, "better_match": None, "message": message}


def check(session: Session, interview: InterviewSession, frame: bytes) -> IdentityOut:
    """Compares one camera picture with the photos and saves the result on the interview (never the picture)."""
    if interview.status != "live":                    # only while the call is running
        raise HTTPException(409, "The identity can be checked during the call.")
    candidate = session.get(Candidate, interview.candidate_id)
    identity = {"checked_at": utc_now().isoformat(), "decision": "", "decided_by": "", "decided_at": None}
    if candidate.face_status in ("", "no_photo", "engine_missing") and candidate.photo_path:
        read_photo_face(candidate)                    # the models were missing at import time: try again now
        session.add(candidate)

    # 1. can the check run at all? Each reason is shown to the interviewer, never skipped silently
    if not candidate.photo_path:
        identity = _stop(identity, "no_photo", "No photo was sent with the application. Please check the identity by hand.")
    elif face_service.engine_problem():
        identity = _stop(identity, "engine_missing", face_service.engine_problem())
    elif candidate.face_status != "ready":
        identity = _stop(identity, "photo_unusable", PHOTO_PROBLEMS.get(candidate.face_status, "The photo cannot be used.")
                         + " Please check the identity by hand.")
    else:
        try:
            live = face_service.face_vector(frame, allow_several=True)     # → compared in memory, never saved
        except FaceProblem as problem:
            code = "no_face" if problem.code in ("no_face", "unreadable") else problem.code
            identity = _stop(identity, code, "No face was found in the camera picture. Ask the candidate to look at "
                                             "the camera, then check again.")
        else:
            identity = {**identity, **_compare(session, candidate, live)}      # 2. compare with the records
    interview.identity = identity                     # 3. the result stays with the interview (not the picture)
    session.add(interview)
    session.commit()
    log.info("identity check session=%s result=%s", interview.id, identity["result"])  # no names, no pictures
    return result(session, interview)


def _compare(session: Session, candidate: Candidate, live: list) -> dict:
    """This candidate's photo, and the best other record with a usable photo."""
    score = face_service.similarity(live, candidate.face_vector)          # this candidate's own photo
    best = None                                       # the best match among the OTHER candidates
    others = session.exec(select(Candidate).where(Candidate.id != candidate.id,
                                                  Candidate.face_status == "ready")).all()
    for other in others:
        if candidate.email and other.email.lower() == candidate.email.lower():
            continue                                  # the same person's application to another job
        other_score = face_service.similarity(live, other.face_vector)
        if other_score >= SAME_PERSON and (best is None or other_score > best["similarity"]):
            job = session.get(Job, other.job_id)
            best = {"candidate_id": other.id, "name": other.full_name, "job_title": job.title if job else "",
                    "similarity": other_score}
    # another record matches as well or better: never call it a confident match, name the other record
    if best and best["similarity"] >= score:
        code = "low" if score >= SAME_PERSON else "no_match"
        message = (f"Another record matches as well or better: {best['name']} ({best['job_title']}), similarity "
                   f"{best['similarity']}. This candidate: {score}. Please check the person's ID.")
    elif score >= CONFIDENT:
        code, message = "confident", f"The face in the call matches the photo from the application (similarity {score})."
    elif score >= SAME_PERSON:
        code, message = "low", (f"A possible match, but not certain (similarity {score}). "
                                "Please check the person's ID.")
    else:
        code, message = "no_match", (f"The face in the call does not match the photo from the application "
                                     f"(similarity {score}). Please check the person's ID.")
    return {"result": code, "similarity": score, "better_match": best, "message": message}


def decide(session: Session, interview: InterviewSession, decision: str, email: str) -> IdentityOut:
    """confirmed | rejected | "" (take back). Possible without a face check: the interviewer checked an ID by hand."""
    identity = dict(interview.identity or {})
    identity["decision"] = decision
    identity["decided_by"], identity["decided_at"] = (email, utc_now().isoformat()) if decision else ("", None)
    interview.identity = identity
    session.add(interview)
    session.commit()
    log.info("identity decision session=%s decision=%s", interview.id, decision or "taken back")
    return result(session, interview)


def result(session: Session, interview: InterviewSession) -> IdentityOut:
    """The identity status of the interview, as the interviewer's room shows it."""
    candidate = session.get(Candidate, interview.candidate_id)
    identity = interview.identity or {}
    return IdentityOut(session_id=interview.id, candidate_id=interview.candidate_id,
                       photo_on_record=bool(candidate and photo_file(candidate)),
                       face_status=candidate.face_status if candidate else "",
                       result=identity.get("result", ""), similarity=identity.get("similarity"),
                       better_match=identity.get("better_match"), message=identity.get("message", ""),
                       checked_at=identity.get("checked_at"), decision=identity.get("decision", ""),
                       decided_by=identity.get("decided_by", ""), decided_at=identity.get("decided_at"),
                       same_person_at=SAME_PERSON, confident_at=CONFIDENT)
