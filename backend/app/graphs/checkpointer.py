"""Where LangGraph keeps a workflow that is paused and waiting for a person (its "checkpointer").

The CV screening workflow ends with the step hr_review, which pauses (LangGraph's interrupt) until the
interviewer includes or excludes the candidate. The paused workflow must survive a restart of the backend, so it
is saved in PostgreSQL by LangGraph's own PostgresSaver. It makes its own tables (checkpoints, checkpoint_writes,
checkpoint_blobs, checkpoint_migrations) the first time; they are not part of our Alembic migrations.

The tables are made when the app starts (main.py), before any other database work: LangGraph builds some of its
indexes "concurrently", which waits until no other database transaction is open.
Tests that use SQLite keep paused workflows in memory instead (InMemorySaver).
"""
import threading

from app.core import config

_lock = threading.Lock()
_saver = None


def checkpointer():
    global _saver
    with _lock:
        if _saver is None:
            if config.DATABASE_URL.startswith("postgresql"):
                from langgraph.checkpoint.postgres import PostgresSaver
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool
                address = config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
                pool = ConnectionPool(address, min_size=1, max_size=5, open=True,
                                      kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
                _saver = PostgresSaver(pool)
                _saver.setup()                        # creates LangGraph's tables if they are missing
            else:
                from langgraph.checkpoint.memory import InMemorySaver
                _saver = InMemorySaver()
        return _saver
