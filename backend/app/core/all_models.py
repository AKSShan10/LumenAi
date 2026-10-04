"""Every database table, imported in one place so SQLModel knows them all (used by database.py and tests).

Each feature adds its tables here.
"""
from app.features.system.models.workflow_run_model import WorkflowRun

__all__ = ["WorkflowRun"]
