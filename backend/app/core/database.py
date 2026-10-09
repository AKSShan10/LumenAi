"""Database connection. Alembic creates and changes the tables for us on startup.

How a table change reaches the database:
    1. change the model (and add a new table to core/all_models.py)
    2. in backend/:  alembic revision --autogenerate -m "what changed"   -> a new file in migrations/versions/
    3. read that file, then start the app: init_db() applies every migration that is still missing
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, Session, create_engine

from app.core.config import DATABASE_URL

BACKEND_DIR = Path(__file__).resolve().parents[2]      # the folder with alembic.ini and migrations/

# pool_pre_ping: if PostgreSQL restarted, reconnect instead of failing the next request.
# (The SQLite flag is only used by the quick offline tests.)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))   # % has a special meaning in .ini files
    return config


def run_migrations() -> None:
    """Brings the database to the newest version."""
    config = alembic_config(engine.url.render_as_string(hide_password=False))
    tables = inspect(engine).get_table_names()
    if tables and "alembic_version" not in tables:
        # A database from before Alembic: its tables were made by create_all, so the first migration
        # would fail with "table already exists". Add what is missing and mark it as up to date.
        SQLModel.metadata.create_all(engine)
        command.stamp(config, "head")
    command.upgrade(config, "head")


def init_db() -> None:
    from app.core import all_models  # noqa: F401  (registers every table)
    try:
        run_migrations()
    except OperationalError as exc:
        where = engine.url.render_as_string(hide_password=True)
        raise RuntimeError(
            f"Cannot connect to PostgreSQL ({where}). Is it running? "
            "Start it with:  docker compose up -d db"
        ) from exc


def get_session():
    """FastAPI dependency: one database session per request."""
    with Session(engine) as session:
        yield session
