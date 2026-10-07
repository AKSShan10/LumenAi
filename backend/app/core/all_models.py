"""Every database table, imported in one place so SQLModel knows them all (used by database.py and tests).

Each feature adds its tables here.
"""
from app.features.assistant.models.chat_model import AssistantAction, ChatConversation, ChatMessage
from app.features.job_library.models.company_document_model import CompanyDocument
from app.features.jobs.models.job_model import Job
from app.features.jobs.models.job_posting_model import JobPosting
from app.features.system.models.workflow_run_model import WorkflowRun

__all__ = ["AssistantAction", "ChatMessage", "CompanyDocument", "Job", "JobPosting", "WorkflowRun"]
