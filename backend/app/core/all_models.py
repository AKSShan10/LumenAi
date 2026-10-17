"""Every database table, imported in one place so SQLModel knows them all (used by database.py and tests).

Each feature adds its tables here.
"""
from app.features.assistant.models.chat_model import AssistantAction, ChatConversation, ChatMessage
from app.features.auth.models.user_model import User
from app.features.candidates.models.candidate_model import Candidate
from app.features.interview_helper.models.helper_message_model import HelperMessage
from app.features.interviews.models.call_message_model import CallMessage
from app.features.interviews.models.interview_model import InterviewSession
from app.features.job_library.models.company_document_model import CompanyDocument
from app.features.jobs.models.job_model import Job
from app.features.jobs.models.job_posting_model import JobPosting
from app.features.qa_analysis.models.qa_analysis_model import QaAnalysis, QaItem
from app.features.screening.models.screening_model import ScreeningResult
from app.features.screening.models.shortlist_model import ShortlistEntry
from app.features.system.models.workflow_run_model import WorkflowRun
from app.features.transcripts.models.transcript_model import TranscriptTurn

__all__ = ["AssistantAction", "CallMessage", "Candidate", "ChatConversation", "ChatMessage", "CompanyDocument",
           "HelperMessage", "InterviewSession", "Job", "JobPosting", "QaAnalysis", "QaItem", "ScreeningResult", "ShortlistEntry", "TranscriptTurn", "User", "WorkflowRun"]
