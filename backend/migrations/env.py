"""Alembic reads this file every time it runs. It answers two questions:

    which database?     the one from the app settings (DATABASE_URL, built from .env)
    which tables?       the models listed in app/core/all_models.py
"""
import os

from alembic import context
from sqlalchemy import create_engine
from sqlmodel import SQLModel

# When Alembic is started from the terminal, the settings in .env are not loaded yet.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except ImportError:
    pass

from app.core import all_models  # noqa: E402,F401  (registers every table)
from app.core.config import DATABASE_URL  # noqa: E402

# The app (and one test) may pass another address; otherwise the one from the settings is used.
url = context.config.get_main_option("sqlalchemy.url") or DATABASE_URL

engine = create_engine(url)
with engine.connect() as connection:
    # render_as_batch: lets SQLite (used in the tests) change a table too
    context.configure(connection=connection, target_metadata=SQLModel.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
