"""LumenAI API - the FastAPI application. Open http://localhost:8010/docs (API_PORT in .env) to try every endpoint.

Folder guide (app/):
    core/       settings, database connection, list of all tables
    ai/         talking to the AI model
    graphs/     LangGraph AI workflows
    features/   one folder per feature, each with models, schemas, routers and services
    utils/      small shared helpers
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core import config
from app.core.database import init_db

# Logs contain ids and events only, never names or CV text
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()                                    # create tables if they do not exist yet
    yield


app = FastAPI(title=config.APP_NAME, version="1.0.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """Never send stack traces or file paths to the browser."""
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})


@app.get("/api/health", tags=["System"])
def health():
    return {"status": "ok", "app_name": config.APP_NAME}


# Each feature registers its router here, for example:
#     app.include_router(job_router.router)
