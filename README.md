<h1 align="center">LumenAI</h1>

<p align="center">
  <b>AI recruitment and interview intelligence.</b><br>
  From a short prompt to an evidence-backed hiring decision.
</p>

<p align="center">
  <img alt="Status" src="https://img.shields.io/badge/status-in%20development-orange">
  <img alt="Backend" src="https://img.shields.io/badge/backend-FastAPI-009688">
  <img alt="Workflows" src="https://img.shields.io/badge/workflows-LangGraph-1C3C3C">
  <img alt="Frontend" src="https://img.shields.io/badge/frontend-React-61DAFB">
  <img alt="Database" src="https://img.shields.io/badge/database-PostgreSQL-336791">
  <img alt="Run" src="https://img.shields.io/badge/run-Docker%20Compose-2496ED">
</p>

---

## Table of contents

1. [About the project](#about-the-project)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Technology stack](#technology-stack)
5. [Repository structure](#repository-structure)
6. [Getting started](#getting-started)
7. [Configuration](#configuration)
8. [Usage walkthrough](#usage-walkthrough)
9. [Privacy and security](#privacy-and-security)
10. [Known limitations](#known-limitations)
11. [Branching and commits](#branching-and-commits)
12. [Documentation](#documentation)
13. [Author](#author)

---

## About the project

Recruitment teams receive more applications than they can assess consistently. Screening is done under time pressure, criteria drift between reviewers, and interview outcomes end up as loose notes that are hard to compare or defend.

LumenAI supports the recruiter through the whole hiring flow, from writing the job description to the final decision. At every step the AI shows the evidence behind its suggestion, and a person makes the decision.

**Positioning:** AI recruitment and interview intelligence, from a short prompt to an evidence-backed hiring decision.

**Why the name "LumenAI":** _to be written by the author (two to four sentences)._

> **Repository status:** this `main` branch holds the project skeleton and the architecture documents. The application code is developed on `dev`.

## Features

### Core

| # | Feature | Summary |
|---|---|---|
| F1 | Job preparation, CV screening and ranking | The AI writes the job description from a short prompt, using the company's past job descriptions. Uploaded CVs are read, checked against every requirement and ranked, with a quote as proof. |
| F2 | Candidate scoring | Skills, experience and qualifications are rated, then combined into a weighted score. |
| F3 | Video interview | Scheduling, an AI-written invitation with a private link, and a live video call. During the call an interview helper suggests questions to the interviewer. |
| F4 | Live transcript | Speech from both speakers becomes a timestamped, speaker-attributed transcript. |
| F5 | Interview answer analysis | Each question and answer is found and rated against the company's own notes. |
| F6 | Consolidated assessment | One final report per candidate, a comparison view, the hiring decision and a PDF export. |

### Stretch

_None attempted yet._

### Innovation (F11)

_To be decided._

## Architecture

### High-level system diagram

The 15 steps of the hiring flow, in four phases. The colour shows who does each step.

![High-level system diagram](docs/architecture/LumenAI_High_Level_System_Diagram.png)

### Detailed architecture

The same 15 steps. Each step shows the page, backend service, workflow, outside service and database table that carry it out.

![Detailed architecture diagram](docs/architecture/LumenAI_Detailed_Architecture.png)

### LangGraph design

One parent graph starts one of three subgraphs: pre-interview (CV screening and scoring), interview analysis, and post-interview (final report). The subgraphs use parallel branches, a single OCR retry and a quote-repair loop limited to two rounds.

![LangGraph workflows](docs/architecture/LumenAI_LangGraph_Workflows.png)

## Technology stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite | Fast to build screens; widely known. |
| Backend | FastAPI + SQLModel | Required stack; typed endpoints with automatic API docs. |
| AI workflows | LangGraph | Required stack; makes each AI step, branch and retry explicit. |
| Database | PostgreSQL | Reliable relational store for jobs, candidates and reports. |
| AI model | Google Gemini | Text, vision (scanned CVs) and embeddings from one provider. |
| Video call | LiveKit | Browser video rooms without building media servers. |
| Speech-to-text | Deepgram | Live streaming transcription with a simple API key. |
| Packaging | Docker Compose | One command starts the whole application. |

## Repository structure

```
.
├── backend/
│   ├── app/
│   │   ├── core/          settings, database, security
│   │   ├── ai/            AI client and prompts
│   │   ├── utils/         shared helpers
│   │   ├── graphs/        LangGraph workflows
│   │   └── features/      one folder per feature:
│   │                      models/ schemas/ services/ routers/
│   ├── scripts/
│   └── tests/
├── frontend/
│   ├── public/
│   └── src/
│       ├── shared/        api, hooks, styles, utils
│       └── features/      one folder per feature
├── docs/
│   └── architecture/      diagrams (.png and .drawio)
├── .env.example
├── .gitignore
└── README.md
```

| Feature folder | Purpose |
|---|---|
| `auth` | Login |
| `system` | Health check and workflow run log |
| `jobs` | Job profile, approval and posting record |
| `job_library` | Company job descriptions used to write new ones |
| `screening` | CV upload and screening |
| `candidates` | Candidate details |
| `scoring` | Scores, weights and ranking |
| `interviews` | Scheduling, invitation and video room |
| `interview_helper` | Question suggestions during the call |
| `transcripts` | Live speech-to-text transcript |
| `knowledge_base` | Company notes used to check answers |
| `qa_analysis` | Rating of each interview answer |
| `assessments` | Final report and decision |

## Getting started

### Prerequisites

- Docker and Docker Compose
- Git
- API keys for the outside services listed under [Configuration](#configuration)

### Setup

```bash
git clone <repository-url>
cd <repository-folder>
git checkout dev
cp .env.example .env      # then fill in your keys
```

### Commands

| Action | Command |
|---|---|
| Build and run | `docker compose up --build` |
| Build and run with a public https:// address (candidate on another device) | `docker compose --profile tunnel up --build` |
| Show the tunnel's https:// address | `docker compose logs tunnel` |
| Stop | `docker compose down` |
| Reset (delete all data) | `docker compose down -v` |
| Run the tests | `pytest` |
| New database change (in `backend`) | `alembic revision --autogenerate -m "what changed"` |
| Show the database version (in `backend`) | `alembic current` |

### Docker services

| Service | What it runs |
|---|---|
| `db` | PostgreSQL |
| `api` | the FastAPI backend (database migrations at start, CV screening worker) |
| `web` | the React app on nginx; passes `/api` to the backend and `/rtc` to LiveKit |
| `livekit` | the video call server (used when `LIVEKIT_URL=/`) |
| `email-mcp`, `blogger-mcp`, `recruitment-mcp` | the MCP servers, each as its own service (HTTP, only reachable by the other containers) |
| `tunnel` | optional public `https://` address (Cloudflare quick tunnel), started with `--profile tunnel` |

Gemini, Google Drive / Forms, Blogger and Gmail are online services; the containers call them over the internet.

### A candidate on another device (https tunnel)

The quick tunnel gives the app a public `https://....trycloudflare.com` address. It needs no key or account, but **the address changes every time the tunnel restarts** (a PC restart, a Docker restart or `docker compose down`). After each restart:

1. Start the tunnel (or recreate it to get a fresh address):
   ```
   docker compose --profile tunnel up -d --force-recreate tunnel
   ```
2. Find the address. If several are listed, use the **last** one:
   ```
   docker compose logs tunnel | findstr trycloudflare.com
   ```
3. Put it in `.env`: `APP_URL=https://<the address>.trycloudflare.com`
4. Recreate the api so it reads `.env` again (`restart` is not enough):
   ```
   docker compose up -d api
   ```
5. In the invitation, click **Write again** so the link uses the new address, then send it.

`docker compose ps tunnel` shows when the tunnel last started ("Up 14 minutes"): if it restarted, the old address no longer works. Invitations already sent keep the old link, so send them on the day of the interview or keep the tunnel running. If the log shows `failed to request quick Tunnel`, the network may block it; add `--protocol http2` to the tunnel's command in `docker-compose.yml`.

**Video:** use the `livekit` service when the candidate is on the same Wi-Fi (set `LIVEKIT_NODE_IP` to this computer's Wi-Fi address), or LiveKit Cloud (`LIVEKIT_URL=wss://...`) when the candidate is on another network: a tunnel cannot carry the UDP video.

**A fixed address:** a named Cloudflare tunnel (free account + your own domain on Cloudflare) keeps the same address, so `APP_URL` is set once. Its token goes in `.env` only, never in git.

## Configuration

All keys and passwords are read from environment variables. Copy `.env.example` to `.env` and fill in the values. The `.env` file is never committed.

| Group | Used for |
|---|---|
| AI model | Job descriptions, CV screening, scoring, answer analysis, reports |
| Database | PostgreSQL connection |
| Security | Login tokens |
| Video call | Interview rooms |
| Speech-to-text | Live transcript |
| Email | Interview invitations |

### Live transcript (speech-to-text)

Each browser in the call sends its own microphone to the backend (WebSocket), so the speaker comes from the microphone, not a guess. Finished sentences are saved with the time from the interview start; the sound itself is never stored.

1. Create a key at [console.deepgram.com](https://console.deepgram.com) → API Keys.
2. In `.env`: `STT_PROVIDER=deepgram` and `DEEPGRAM_API_KEY=<the key>`.
3. Recreate the api: `docker compose up -d --force-recreate api`, then click **Test speech-to-text** on the Settings page.

`STT_PROVIDER=fake` writes test sentences instead (no key; for demos only). The interviewer sees the sentences in the **Live Transcript** tab of the call; after the call, **Transcript** on the Interviews page shows them with the chat and a **Download .txt** button.

## Usage walkthrough

1. Write a short prompt about the job. The AI writes the job description.
2. Review and approve the job, then post it on a job board.
3. Upload the CVs that arrive. The system screens, scores and ranks them.
4. Choose candidates and send interview invitations.
5. Hold the video interview. The helper suggests questions and the transcript is written live.
6. Run the answer analysis and create the final report.
7. Compare candidates and record the decision.

_Screenshots will be added with the code._

## Privacy and security

- No secrets in the repository. Keys are supplied through environment variables.
- No candidate data in the repository. Only made-up CVs are used for testing.
- No audio or video is recorded. Only the written transcript is kept.
- Candidates never see scores or reports.
- Scoring uses job-relevant criteria only.
- The AI suggests. People make every hiring decision.

Which outside services receive candidate data, and exactly what is sent to each, will be documented here with the code.

## Known limitations

_To be completed as the features are built. This section will state plainly what does not work and why._

## Branching and commits

| Branch | Purpose |
|---|---|
| `main` | Stable branch. Skeleton and documents now; working releases later. |
| `dev` | Integration branch for the application code. |
| `feature/<name>` | One feature or task at a time. |

Commit messages describe the change, for example `Add OCR retry to CV parsing`, not `update` or `fix`.

## Documentation

All project documents are under [`docs/`](docs/README.md): the architecture diagrams now, and the clarification document, Work Breakdown Structure and innovation rationale as they are completed.

## Author

**Md. Abdul Kahhar Siddiki Shan**<br>
BJIT AI Trainee Programme, final project
