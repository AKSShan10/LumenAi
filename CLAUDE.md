# LumenAI — context for Claude

Read this first. Then read `requirements.md` (full specification) and `FEATURES.md` (which files belong to which feature) before changing code.

## What this project is

LumenAI is an AI recruitment platform: job from a prompt → CV screening and ranking → video interview with live transcript, AI helper and chat → Q&A analysis → assessment report → hiring decision.

It is the final project of a BJIT AI trainee (Md. Abdul Kahhar Siddiki Shan). Delivery date: 27 October 2026. The product name is **LumenAI** (not HireTrace; `APP_NAME=LumenAI`).

**Rule behind every feature:** the AI suggests, code checks, people decide. The AI gives verdicts, ratings (0/25/50/75/100) and text. Python checks that every quote really is in the CV or transcript and does all the maths. A person approves, sends, keeps/excludes and decides hire / hold / reject.

## Stack

- Backend: Python, FastAPI, SQLModel, PostgreSQL 16 (SQLite in tests), LangGraph, Gemini through the OpenAI-compatible API, MCP (`mcp` package, FastMCP servers started by the backend over stdio).
- Frontend: React 19 + Vite, plain JavaScript and one CSS file (`shared/styles/global.css`). No router library, no state library, no UI kit.
- Services: LiveKit (video), Deepgram or Google (speech-to-text), SMTP email, Google Drive (read-only).
- Docker Compose: `db`, `api`, `web`.

## How I want you to work

1. **Simple, beginner-friendly code.** Short functions, clear names, short comments that say why. No clever abstractions, no base classes, no async where sync works.
2. **Follow the project tree.** Every new file must go in a folder that already exists. Backend features use `features/<feature>/{models,schemas,services,routers}/`. Do not create new top-level folders or loose files.
3. **Routers only check the request.** The work is in the service or the graph.
4. **Small changes.** Change only what the task needs. Do not rename, reformat or reorganise other files.
5. **Explain before large changes.** For anything touching more than a few files, tell me the plan and the files first.
6. **Tests.** Add or update a test in `backend/tests/` for backend changes. Run the tests and the frontend build before saying it is done, and tell me honestly what you did not check.
7. **Plain words.** I am learning. Explain in simple English, step by step.
8. **Do not add features** that are not in `requirements.md` unless I ask.

## Never do

- Never commit or print `.env`, `secrets/google-stt.json`, `secrets/google-drive.json`, database files or real CVs. Use made-up CVs only.
- Never hide or remove the consent notice on the candidate join page (the requirements say consent must be visible).
- Never show the AI helper, scores, notes or live analysis to the candidate.
- Never rate voice, confidence, appearance or identity. No candidate photo, no "confidence" or "speaking clarity" scores.
- Never let the AI make a hiring decision or choose MCP tools; the backend code calls the tools.
- Never write the WBS, the SRS or the workflow diagram for me. Those must be my own work; you may review, format and comment.

## Commands

```bash
# database only
docker compose up -d db

# backend (from backend/)
python -m venv .venv
.venv\Scripts\activate                 # Mac / Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010 --env-file ../.env

# frontend (from frontend/)
npm install
npm run dev                            # http://localhost:5173
npm run build

# tests (from backend/, offline, no keys needed)
python -m pytest -q

# everything in Docker
docker compose up --build              # web http://localhost:8090, API docs http://localhost:8010/docs
```

Offline mode for trying things without keys: `LLM_PROVIDER=fake`, `STT_PROVIDER=fake`, `DRIVE_PROVIDER=fake`, empty `SMTP_HOST`.

A new table or column needs a migration (Alembic): add a new table to `backend/app/core/all_models.py`, then in `backend/` run `alembic revision --autogenerate -m "what changed"`, read the new file in `backend/migrations/versions/` and commit it. The backend applies missing migrations when it starts.

## Git and Redmine

- `main` = skeleton and diagrams. `dev` = code.
- `feature/<redmine-id>-<name>` is created from `dev`; `task/<redmine-id>-<name>` is created from its feature branch. One commit per task. No squash. Task → feature → dev.
- Commit message (BJIT guideline):

  ```text
  type(scope): summary in imperative mood, 50 characters or less

  - what changed
  - why

  Refs #<redmine-id>        (or: Closes #<redmine-id>)
  ```

  Types: feat, fix, docs, style, refactor, test, chore.
- I commit and push myself with GitHub Desktop. Give me the commit message; do not commit or push unless I ask.

## Current state

- Built and tested offline: setup and login, F1 jobs and screening, F2 scoring, F3 interviews and invitation, F4 live transcript, F5 Q&A analysis, F6 assessment, interview helper, call chat, question history, email and Google Drive through MCP, HR keep / exclude, dashboard, settings checks. 110 backend tests pass on SQLite.
- I have run real LiveKit, real Gemini and real Google Drive myself.
- Not yet checked with real services: Gmail through MCP, Deepgram, chat between two browsers, the Docker build.

## Open items

- Job posting through MCP: waiting, do not build yet.
- F11: not chosen yet.
- Duplicate-CV check: not built.
- README privacy wording: names inside CV text and transcripts are not removed; the README must say so honestly.
- Google Drive and MCP come from my mentor, not from the written requirements; to be confirmed with the trainer.
- Diagrams in `docs/`: the component-view diagram is outdated (14 steps; the flow now has 15).
