"""Alembic migrations: the files in migrations/versions/ must build the same tables as the models."""
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

from app.core import all_models  # noqa: F401  (registers every table)
from app.core import database


def test_migrations_build_every_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    command.upgrade(database.alembic_config(url), "head")           # an empty database, migrations only

    fresh = create_engine(url)
    tables = set(inspect(fresh).get_table_names())
    assert set(SQLModel.metadata.tables) <= tables and "alembic_version" in tables

    # No difference left between the models and the database. If this fails, a model was changed
    # without a migration: run  alembic revision --autogenerate -m "..."  in backend/.
    with fresh.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), SQLModel.metadata)
    assert differences == []


def test_database_from_before_alembic_is_kept(tmp_path, monkeypatch):
    """Tables made by the old create_all are not created again; the database is marked as up to date."""
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    SQLModel.metadata.create_all(old)
    monkeypatch.setattr(database, "engine", old)

    database.run_migrations()
    database.run_migrations()                                        # a second start changes nothing

    assert "alembic_version" in inspect(old).get_table_names()
