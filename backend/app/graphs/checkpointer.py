"""Where LangGraph keeps a workflow that is paused and waiting for a person (its "checkpointer").

The CV screening workflow ends with the step hr_review, which pauses (LangGraph's interrupt) until the
interviewer includes or excludes the candidate. The paused workflow must survive a restart of the backend, so it
is saved in PostgreSQL by LangGraph's own PostgresSaver. It makes its own tables (checkpoints, checkpoint_writes,
checkpoint_blobs, checkpoint_migrations) the first time; they are not part of our Alembic migrations.

The tables are made when the app starts (main.py), before any other database work: LangGraph builds some of its
indexes "concurrently", which waits until no other database transaction is open.
Tests that use SQLite keep paused workflows in memory instead (InMemorySaver).

The assistant chat keeps its memory in the same tables, but its agent runs async (the MCP tools are async), and
PostgresSaver only works in normal code. async_checkpointer() opens LangGraph's AsyncPostgresSaver on the same
tables for one chat message.
"""
import threading
from contextlib import asynccontextmanager

from app.core import config

_lock = threading.Lock()
_saver = None


# Creates the shared LangGraph checkpointer once: PostgresSaver (makes its tables) or InMemorySaver in tests
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


@asynccontextmanager
async def async_checkpointer():
    """The checkpointer for async code (the assistant agent), opened for one run. Same tables as checkpointer()."""
    saver = checkpointer()                            # makes sure the tables exist (or the shared memory one in tests)
    if not config.DATABASE_URL.startswith("postgresql"):
        yield saver                                   # InMemorySaver works in async code too
        return
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    address = config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    async with AsyncPostgresSaver.from_conn_string(address) as async_saver:
        yield async_saver
