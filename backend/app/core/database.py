"""Database connection. SQLModel creates the tables for us on startup."""
from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, Session, create_engine

from app.core.config import DATABASE_URL

# pool_pre_ping: if PostgreSQL restarted, reconnect instead of failing the next request.
# (The SQLite flag is only used by the quick offline tests.)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)


def init_db() -> None:
    from app.core import all_models  # noqa: F401  (registers every table)
    try:
        SQLModel.metadata.create_all(engine)
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
