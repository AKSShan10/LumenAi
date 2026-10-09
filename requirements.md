# LumenAI — build requirements

This file describes LumenAI completely enough that an AI coding agent (or a developer) can build it from an empty folder. It describes the system as it is built today.

**How to use this file as an agent:** read sections 1–5 first, create the folders in section 6 exactly, then build in the order of section 16. After each step, run the tests of that step before going on. Do not add features that are not written here.

---

## 1. Product

**LumenAI** is a web application that helps a recruiter through one hiring process:

1. Write a job from a short prompt, approve it, post it.
2. Collect CVs (upload or Google Drive), screen and rank them.
3. Schedule a video interview and send the invitation.
4. Run the interview with a live transcript, an AI helper and a chat.
5. Analyse the questions and answers after the interview.
6. Produce one assessment report per candidate and record the hiring decision.

**The rule behind every feature: the AI suggests, code checks, people decide.**

- The AI gives verdicts, ratings and text.
- Python code checks that every quote really exists in the CV or the transcript, and does all the maths.
- A person approves the job, sends the email, keeps or excludes a candidate, and records hire / hold / reject. The AI never makes a hiring decision.

## 2. Users and access

| User | How they get in | What they can do |
| --- | --- | --- |
| Interviewer (also HR / recruiter) | One shared passcode (`INTERVIEWER_PASSCODE`) → JWT token | Everything |
| Candidate | A secret link from the invitation (`/join/<join_token>`); no account | Join their own call, see the consent notice, use the call chat. Nothing else. |

- `POST /api/auth/login {passcode}` → `{token}`. Token: JWT, HS256, signed with `SECRET_KEY`, payload `{role: "interviewer", exp}`.
- Every `/api/...` router requires the interviewer token, except `/api/auth/login`, `/api/health` and `/api/join/...`.
- The frontend keeps the token in memory + `sessionStorage` and sends it as `Authorization: Bearer <token>`. A 401 answer logs the user out.
- The candidate page must never show the AI helper, scores, notes or live analysis.

## 3. Technology (use these, pinned)

**Backend** — Python 3.11+

```text
fastapi==0.141.1          uvicorn[standard]==0.46.0   python-multipart==0.0.26
sqlmodel==0.0.47          SQLAlchemy==2.0.54          psycopg[binary]==3.3.6
pydantic==2.13.3          langgraph==1.2.12           openai==3.19.2
pymupdf==1.28.2           python-docx==1.2.0          httpx==0.28.1
pytest==9.1.1             livekit-api==1.2.1          PyJWT==2.15.0
websockets==16.1.1        google-cloud-speech==2.40.0 mcp==1.27.0
```

**Frontend** — React 19.3.0, react-dom 19.3.0, Vite 8.3.1, `@vitejs/plugin-react` 6.1.1, `livekit-client` 2.22.3, `@livekit/components-react` 2.9.24, `@livekit/components-styles` 1.2.0. Plain JavaScript (JSX), plain CSS in one file. No router library (a small `page` state in `App.jsx` chooses the page), no state library, no UI kit.

**Services**

| Need | Service | Offline replacement |
| --- | --- | --- |
| Database | PostgreSQL 16 (SQLite in tests) | – |
| AI text, OCR, embeddings | Google Gemini through its OpenAI-compatible API (`openai` package) | `LLM_PROVIDER=fake` |
| Video call | LiveKit Cloud | – |
| Speech-to-text | Deepgram live (default) or Google Cloud Speech-to-Text | `STT_PROVIDER=fake` |
| Email | SMTP (e.g. Gmail app password), reached through an MCP server | empty `SMTP_HOST` = draft only |
| CV folder | Google Drive (read-only service account), reached through an MCP server | `DRIVE_PROVIDER=fake` (a local folder) |
| Run everything | Docker Compose: `db`, `api`, `web` (nginx) | – |

## 4. Code style (important)

- Simple, beginner-friendly code. Short functions, clear names, short comments that say *why*.
- No clever abstractions, no base classes, no dependency-injection frameworks, no async where sync works.
- A **router** only checks the request and calls a service. The work is in the **service** or the **graph**. Tables are in **models**. Request and response bodies are in **schemas**.
- Every setting comes from `.env` through `core/config.py`. No secret is written in code.
- Every new file must sit in a folder that exists in section 6.

## 5. Configuration (`.env.example`)

```text
APP_NAME=LumenAI

LLM_PROVIDER=gemini            # gemini | fake
LLM_API_KEY=replace-me
LLM_MODEL=gemini-3.5-flash
# LLM_TEMPERATURE=             (leave unset)
# EMBEDDING_MODEL=gemini-embedding-001

POSTGRES_USER=recruit
POSTGRES_PASSWORD=change-me
POSTGRES_DB=recruit
POSTGRES_PORT=5432

MAX_FILE_MB=5
MAX_FILES_PER_UPLOAD=25
OCR_MAX_PAGES=3

DRIVE_PROVIDER=google          # google | fake
# GOOGLE_DRIVE_CREDENTIALS=../secrets/google-drive.json

INTERVIEWER_PASSCODE=change-me
SECRET_KEY=replace-with-a-long-random-string

LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...

SMTP_HOST=                     # empty = invitation is shown, not sent
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
EMAIL_TRANSPORT=mcp            # mcp | smtp
# SMTP_STARTTLS=false

STT_PROVIDER=deepgram          # deepgram | google | fake
DEEPGRAM_API_KEY=replace-me
# DEEPGRAM_MODEL=nova-3
# GOOGLE_APPLICATION_CREDENTIALS=../secrets/google-stt.json

ASSESSMENT_CV_WEIGHT=40        # overall = CV score x 40 % + interview score x 60 %

API_PORT=8010
WEB_PORT=8090
DEV_WEB_PORT=5173
APP_URL=http://localhost:8090  # address used in the candidate's join link
```

Other settings with defaults in `config.py`: `DATABASE_URL` (built from the `POSTGRES_*` values when not given), `TOKEN_HOURS`, `MIN_TEXT_CHARS` (below this a PDF counts as scanned).

**Never commit:** `.env`, `secrets/google-stt.json`, `secrets/google-drive.json`, real CVs, database files. `.gitignore` must cover them. Use made-up CVs only.

## 6. Project tree (create exactly this)

```text
lumenai/
├── .env.example  .gitignore  README.md  FEATURES.md
├── docker-compose.yml  pytest.ini
├── secrets/README.md                      # how to get the two Google key files
├── demo_data/                             # made-up job descriptions, notes, CVs, an interview script
├── docs/                                  # architecture diagrams
├── backend/
│   ├── Dockerfile  requirements.txt
│   ├── scripts/create_demo_interview.py   # a ready interview for a quick video test
│   ├── tests/                             # see section 15
│   └── app/
│       ├── main.py                        # FastAPI app, all routers, resume unfinished AI work at start
│       ├── core/      config.py  database.py  security.py  all_models.py
│       ├── ai/        llm_client.py  fake_llm.py  prompts.py
│       ├── utils/     datetime_utils.py  score_utils.py  search_utils.py  text_utils.py
│       ├── graphs/    cv_screening_graph.py   cv_screening_prompts.py  scoring_prompts.py
│       │              qa_analysis_graph.py    qa_analysis_prompts.py
│       │              assessment_graph.py     assessment_prompts.py
│       ├── mcp_servers/  client.py  email_server.py  drive_server.py
│       └── features/<feature>/{models,schemas,services,routers}/
│             auth  jobs  job_library  screening  candidates  scoring
│             interviews  interview_helper  transcripts
│             knowledge_base  qa_analysis  assessments  system
└── frontend/
    ├── Dockerfile  nginx.conf  index.html  package.json  vite.config.js
    ├── public/audio/pcm-audio-worklet.js  # microphone → 16 kHz PCM
    └── src/
        ├── main.jsx  App.jsx
        ├── shared/  api/{httpClient.js, authToken.js}  hooks/usePolling.js
        │            styles/global.css  utils/{Icon.jsx, AppFooter.jsx, formatTime.js}
        └── features/<feature>/            # *Page.jsx screens, *.jsx parts, *Api.js backend calls
              auth  jobs  job_library  screening  candidates  scoring
              interviews  interview_helper  transcripts
              knowledge_base  qa_analysis  assessments  system
```

File names inside a backend feature follow one pattern: `models/<name>_model.py`, `schemas/<feature>_schemas.py`, `services/<name>_service.py`, `routers/<name>_router.py`.

## 7. Data model

All tables are SQLModel classes. `core/all_models.py` imports every one so `create_all` builds them. `core/database.py` also has a small `NEW_COLUMNS` list that adds a missing column to an existing table at start (no migration tool).

| Table | Fields |
| --- | --- |
| `Job` | id, title, description, required_skills (list), preferred_skills (list), min_years, qualifications, score_weights (dict or null), prompt, status `draft\|approved`, drive_folder, approved_at, created_at |
| `JobPosting` | id, job_id, platform `linkedin\|bdjobs\|other`, url, method `manual`, posted_at |
| `JobDescriptionExample` | id, title, text, source `added\|approved job`, job_id, embedding (list or null), created_at |
| `Candidate` | id, job_id, file_name, email, cv_text, source `linkedin\|bdjobs\|email\|other\|google_drive`, kept_by_hr, excluded_by_hr, hr_note, allow_any_language, drive_file_id, text_source `text\|ocr`, profile (dict), status `uploaded\|queued\|screened\|excluded\|needs_review`, error, score, rank, cv_file (bytes) |
| `Match` | id, candidate_id, requirement, is_required, verdict `met\|partial\|unmet`, quote, reason |
| `DimensionScore` | id, candidate_id, dimension `technical_skills\|experience\|qualifications`, rating (0/25/50/75/100), justification, quote |
| `InterviewSession` | id, candidate_id, job_id, scheduled_at, join_token (unique), room_name (unique), status `scheduled\|live\|ended`, started_at, ended_at, candidate_joined_at, invite_email, invitation_subject, invitation_body, invitation_status `sent\|not_sent\|no_email\|failed: <reason>`, interviewer_notes, created_at |
| `ChatMessage` | id, session_id, sender `interviewer\|candidate`, text, sent_at |
| `TranscriptTurn` | id, session_id, speaker `interviewer\|candidate`, start_sec, end_sec, text |
| `HelperMessage` | id, session_id, role `interviewer\|helper`, kind `chat\|questions\|document`, text, questions (list of `{question, requirement, why, model_answer, asked_before}`), created_at |
| `LiveAnalysis` | id, session_id (unique), answers, ratings (dict 0–100), insights (list), updated_at |
| `KnowledgeDocument` | id, job_id, name, chunks, created_at |
| `KnowledgeChunk` | id, document_id, job_id, text, embedding (list or null) |
| `QaAnalysis` | id, session_id (unique), status `running\|done\|failed`, error, interview_score, covered (list), uncovered (list), created_at |
| `QaItem` | id, session_id, position, question, answer, job_related, split_from_multi_part, relevance, accuracy, completeness, articulation, score, feedback, evidence_quote, evidence_time, reasons (dict), requirements (list), references (list) |
| `Assessment` | id, candidate_id (unique), job_id, status `running\|done\|failed`, error, match_score, ai_score, interview_score, overall_score, summary, strengths, gaps, evidence_gaps, recommended_areas, repair_rounds, decision `pending\|hire\|hold\|reject`, decision_note, updated_at |
| `WorkflowRun` | id, stage `pre_interview\|interview_analysis\|post_interview`, subject_id, outcome, error, started_at, seconds |

Deleting a job or a candidate deletes everything that belongs to it (matches, scores, interviews, transcript, chat, analysis, assessment). The candidate's person name is never shown as the identifier; the UI shows the **file name**.

## 8. AI layer (`app/ai/`)

- `llm_client.py`: one OpenAI-compatible client pointed at Gemini. Functions: ask for a JSON answer (parse it, retry once on bad JSON), OCR (page images → text), embeddings, and a connection check that turns provider errors into plain words (wrong key, wrong model, quota).
- `fake_llm.py`: used when `LLM_PROVIDER=fake`. Returns simple rule-based answers (word matching) for every prompt so the whole app and all tests run without a key. It must be clearly described as *not real AI*.
- `prompts.py`: prompts for single AI calls (job draft, job description, OCR, weights, invitation email, helper questions, helper chat, live analysis). Graph prompts live next to their graph.
- Every prompt asks for JSON only, uses the rating scale **0 / 25 / 50 / 75 / 100**, and asks for an exact quote as evidence.
- Embeddings are stored as a JSON list. Search = cosine similarity in Python (`utils/search_utils.py`); if there is no embedding, fall back to word overlap. No vector database.

## 9. Functional requirements

### F1 — Jobs, CV screening, ranking

**Jobs**

1. The recruiter types a short prompt. `POST /api/jobs/draft-from-prompt` returns title, required skills, preferred skills, minimum years, qualifications and a description. The AI is given the **2 closest** past job descriptions from the company library (RAG) so it writes in the company's style; the answer names the examples used.
2. The recruiter edits and saves (status `draft`). `POST /api/jobs/{id}/approve` → `approved`, and the description is added to the library. Editing an approved job makes it a draft again.
3. Posting is semi-manual: the recruiter copies the job text, posts it on LinkedIn / BDJobs by hand, and saves platform + link (`JobPosting`). (Posting through an API is out of scope.)
4. Company job-description library: add by text or by file, list, delete, search.

**Collecting CVs**

5. Upload PDF or DOCX (`POST /api/jobs/{id}/cvs`, multipart, with an optional `source`). Limits: `MAX_FILE_MB` per file, `MAX_FILES_PER_UPLOAD` per request. Other file types are refused with a clear message per file.
6. On demand from Google Drive: `POST /api/jobs/{id}/cvs/drive {folder?}`. The backend saves the folder on the job, lists the folder through the Drive MCP server, skips files that are not PDF/DOCX or are too large, downloads the rest in one MCP run, and saves each with `source="google_drive"`. `drive_file_id` is remembered so a file is never collected twice. A Google Doc is exported as PDF.

**Screening** — `POST /api/jobs/{id}/screen` (answers 202, work runs in the background, the page polls). One graph run per CV (section 10):

7. Read the text (PDF with PyMuPDF, DOCX including tables). If the text is shorter than `MIN_TEXT_CHARS`, read up to `OCR_MAX_PAGES` pages with OCR once.
8. Refuse a CV that is not in English (less than 70 % Latin letters) → `needs_review` with the reason. HR can press **Screen anyway**.
9. Remove emails and phone numbers from the text before any AI call. Keep the email separately; it is used only to send the invitation.
10. The AI extracts a profile and judges every job requirement `met | partial | unmet` with a quote and a reason. **Code keeps a verdict only if the quote is really in the CV text**; otherwise the verdict becomes `unmet`.
11. **Match %** (Python): `met = 1, partial = 0.5, unmet = 0`; required skills count double; result 0–100.
12. A CV with any required skill `unmet` is **excluded** (not ranked, cannot be invited) with the missing requirements as the reason.
13. Screened candidates are ranked per job by score. The uploaded file is deleted once the CV is screened; a `needs_review` CV keeps its file so it can be tried again.
14. Unfinished screening continues after a backend restart.

**HR decisions (people decide)**

15. Excluded by the AI → **Keep in the ranking** (`PUT /api/candidates/{id}/keep {keep, note}`): becomes `screened`, badge "kept by HR", can be invited, missing must-haves stay visible. **Exclude again** undoes it.
16. Screened → **Exclude from the ranking** (`PUT /api/candidates/{id}/exclude {exclude, note}`): becomes `excluded`, badge "excluded by HR", scores stay visible, cannot be invited. **Put back in the ranking** undoes it.
17. Both decisions survive re-screening. Save rule in the graph:
    ```python
    excluded = (bool(missing) and not candidate.kept_by_hr) or candidate.excluded_by_hr
    candidate.status = "excluded" if excluded else "screened"
    ```
18. `needs_review` page: shows the reason, the first 1500 characters of the text that was read (contacts removed), **Screen again**, **Screen anyway** (`POST /api/candidates/{id}/rescreen {any_language}`), and **Delete candidate**.

### F2 — AI candidate scoring

1. In the same graph, three AI calls run in parallel and rate `technical_skills`, `experience`, `qualifications` (0/25/50/75/100) with a justification and a quote. Code snaps ratings to the nearest level and drops quotes that are not in the CV.
2. **AI score** (Python) = `round(Σ rating × weight / 100)`. Default weights: technical skills 50, experience 30, qualifications 20. Weights must sum to 100.
3. `POST /api/jobs/suggest-weights` lets the AI propose weights with a reason; `PUT /api/jobs/{id}/weights` saves them. Changing weights re-scores everyone with no new AI call.
4. The candidate page shows the breakdown table (dimension, weight, rating, justification, quote).

### F3 — Video interview, invitation, helper, chat

**Scheduling and invitation**

1. Only a `screened` candidate can be scheduled, and only for a future date and time. `POST /api/sessions` creates the session with a random `join_token` and `room_name`.
2. **Draft first.** Scheduling only writes the invitation draft. The AI writes subject and body **without seeing the email address**; code inserts the join link `APP_URL/join/<join_token>`.
3. The recruiter can edit address, subject and body, press **Write again with AI** (`POST /api/sessions/{id}/invitation`) or **Send email** (`PUT /api/sessions/{id}/invitation`). If the link was removed from the text, code puts it back before sending.
4. Sending goes through the email MCP server when `EMAIL_TRANSPORT=mcp` (default). Result: `sent`, `not_sent` (no SMTP configured), `no_email`, or `failed: <plain reason>`.

**Call**

5. `POST /api/sessions/{id}/start` sets `live` and returns a LiveKit ticket for the interviewer. The candidate opens the link: `GET /api/join/{token}` (job title, time, status) and `POST /api/join/{token}/ticket {name}`. The candidate cannot enter before the interviewer starts or after the call has ended.
6. **Consent is visible.** The candidate join page states, before joining, that the conversation is transcribed and analysed by AI and that a person makes the decision. Do not hide or remove this notice.
7. `POST /api/sessions/{id}/end` ends the call for both.

**Interview room layout (interviewer)** — two videos; under them three tabs **Live Transcript / AI Helper / Chat**; right column **Candidate Info / Evaluation / Notes**, **Live analysis**, **AI insights**.

8. **AI Helper** (interviewer only), `/api/sessions/{id}/helper`:
   - `POST /questions {topic}` → up to 8 suggested questions, each with the requirement it tests, why, and a model answer. Context given to the AI: the job, the CV profile and its gaps, the top 3 company notes (RAG), the last 40 transcript turns, the last 3 lists already suggested (so it does not repeat), and **past questions** (see below).
   - `POST /chat {text}` → free chat with the helper (sees the last 6 chat messages). Answers with "1. … 2. …" are shown as a numbered list with a copy link per item.
   - `POST /documents` → add a PDF/DOCX (e.g. an updated CV) to the helper's context.
   - `PUT /notes` → interviewer's own notes.
   - `POST /live` → live analysis: four ratings (relevance, technical knowledge, and two more text-based criteria) plus 2–4 short insights, made **only from the transcript text**, refreshed about 10 seconds after the candidate stops talking or on **Update now**. Voice, confidence and appearance are never judged.
9. **Question history (RAG):** the helper searches the questions from earlier, already analysed interviews for the same job or a **similar** job (at least 50 % of title words match, or at least 50 % of required skills shared). Newest 200 are compared, the best 8 are given to the AI with `times_asked`. A suggested question that overlaps a past one by 70 % of its words is tagged **asked before**.
10. **Call chat:** `GET/POST /api/sessions/{id}/chat` for the interviewer; the candidate uses the same chat through their join token. Both sides poll. Unread count on the tab. Messages are listed with the transcript afterwards.

### F4 — Live transcript

1. Each browser sends **its own microphone** (16 kHz PCM from an audio worklet) over WebSocket `/api/sessions/{id}/stt`, so the speaker is known from the channel, not guessed.
2. The backend forwards audio to the speech-to-text service and saves finished sentences as `TranscriptTurn` with start/end seconds from the interview start. **Raw audio is never stored.**
3. Deepgram: join partial pieces into one sentence. Google: restart the stream every 4 minutes. Fake: test sentences.
4. **Echo guard:** if one microphone hears both voices, a sentence of 5 words or more that overlaps 80 % with a sentence from the other speaker within 6 seconds is dropped; the socket answers `{"speaker", "dropped": true}`.
5. The client reconnects on a dropped socket. After the call: `GET /api/sessions/{id}/transcript` and `/transcript.txt` (download).

### F5 — Q&A analysis with a knowledge base (RAG)

1. Knowledge base per job: add notes by text or file; split into chunks of about 120 words; embed; `search` returns the top 3 chunks.
2. `POST /api/sessions/{id}/analysis` (202, background, page polls) runs the analysis graph: find question/answer pairs, mark small talk (kept, not scored), split multi-part questions, link each pair to job requirements.
3. Four parallel AI calls grade every job-related answer on **relevance, accuracy, completeness, articulation** (0/25/50/75/100) with one reason each. Accuracy is compared with the top 3 knowledge-base chunks, and the documents used are stored as references.
4. Code checks that each evidence quote is in the transcript and attaches the time it was said. Answer score = average of the four; **interview score** = average of job-related answer scores.
5. Code lists which job requirements were shown (`covered`) and which were not (`uncovered`).

### F6 — Assessment, report, decision, comparison

1. `POST /api/candidates/{id}/assessment` (202, background) runs the assessment graph over Match %, AI score and interview score.
2. In parallel: AI strengths, AI weaknesses, AI recommended areas to explore, and (Python) **evidence gaps** — requirements with no proof in the CV or the interview.
3. **Traceability check:** every strength and weakness needs a quote that really exists in the CV or the transcript. Failed items go back to the AI for repair, at most 2 rounds; after that, unproven strengths are removed.
4. The AI writes the summary last. **Overall score** (Python) = `CV score × ASSESSMENT_CV_WEIGHT % + interview score × (100 − weight) %` (default 40 / 60).
5. The interviewer records `hire | hold | reject` with a note (`PUT .../assessment/decision`).
6. Report page with **Export PDF** (browser print; print CSS shows only the report). `GET /api/jobs/{id}/comparison` → table of candidates, best overall score first.

### System

- `GET /api/health` → `{status, app_name, llm}` (no login).
- `GET /api/dashboard` → counts for the dashboard cards.
- `GET /api/llm-check`, `/stt-check`, `/email-check`, `/drive-check` → each returns ok / not ok with a plain-word reason; nothing is sent. The Drive check shows the service-account email that folders must be shared with.
- `GET /api/workflow-runs` → recent graph runs (stage, outcome, seconds, error).

## 10. LangGraph workflows

LangGraph is used for the three multi-step jobs only. Single AI calls (job draft, email, helper, live analysis) are plain function calls. LangGraph's built-in checkpointing is **not** used; state is saved in the database tables and unfinished work is restarted from them.

```text
cv_screening_graph (pre-interview, one run per CV)
  START → parse_cv → validate_extraction ─(too little text, first try)→ ocr_retry → validate_extraction
                         │ (still bad / not English) → needs_review → END
                         ↓
          extract_profile ─(no skills found)→ needs_review → END
                         ↓
          match_requirements → [score_skills | score_experience | score_qualifications]  (parallel)
                         → combine_score → justifications → save → rank → END

qa_analysis_graph (interview analysis, one run per interview)
  START → load_transcript → segment_qa_pairs → classify_requirements
        → [evaluate_relevance | evaluate_accuracy (+RAG) | evaluate_completeness | evaluate_articulation]  (parallel)
        → merge_evaluation → detect_requirement_gaps → save → END          (any error → failed → END)

assessment_graph (post-interview, one run per candidate)
  START → load_all_results → [analyze_strengths | analyze_weaknesses | evidence_gaps | recommended_areas]  (parallel)
        → merge_assessment → validate_traceability ⇄ repair_assessment (max 2 rounds)
        → generate_report → save → END                                     (any error → failed → END)
```

## 11. MCP servers (`app/mcp_servers/`)

- Each server is a small **FastMCP** Python module. The backend starts it as a **child process over stdio** when it needs it, calls the tool, and the process ends. Nothing is deployed and no desktop app is configured.
- **The backend code decides which tool to call.** No AI model chooses tools.
- `client.py`: `call_tool(module, tool, args)` and `call_tools(module, [(tool, args), ...], timeout)`; raises `McpError` with a plain message.
- `email_server.py` (name `lumenai-email`): tools `send_email(to, subject, body)`, `check_email_settings()`. The SMTP code itself is in `features/interviews/services/smtp_service.py`.
- `drive_server.py` (name `lumenai-drive`): tools `list_cv_files(folder)`, `download_cv_file(file_id, folder)`, `check_drive_settings()`. The Drive code is in `features/screening/services/drive_service.py` (read-only scope, service-account key at `secrets/google-drive.json`, folder id taken from a link or an id, paging).
- Tools answer JSON; a problem is returned as `{"error": "<plain reason>"}`.

## 12. API summary

All paths need the interviewer token unless marked *public*.

```text
POST   /api/auth/login                              public
GET    /api/health                                  public

POST GET /api/jobs            GET PUT DELETE /api/jobs/{id}
POST   /api/jobs/draft-from-prompt     POST /api/jobs/generate-description
POST   /api/jobs/{id}/approve
GET POST /api/jobs/{id}/postings       DELETE /api/jobs/{id}/postings/{posting_id}
GET    /api/job-library   POST /api/job-library/text   POST /api/job-library/files
DELETE /api/job-library/{id}           GET /api/job-library/search?q=

POST   /api/jobs/{id}/cvs              POST /api/jobs/{id}/cvs/drive
POST   /api/jobs/{id}/screen           GET  /api/jobs/{id}/candidates
POST   /api/jobs/suggest-weights       PUT  /api/jobs/{id}/weights
GET DELETE /api/candidates/{id}
PUT    /api/candidates/{id}/keep       PUT  /api/candidates/{id}/exclude
POST   /api/candidates/{id}/rescreen

POST GET /api/sessions                 GET /api/sessions/{id}
POST PUT /api/sessions/{id}/invitation
POST   /api/sessions/{id}/start        POST /api/sessions/{id}/end
GET    /api/sessions/{id}/transcript   GET  /api/sessions/{id}/transcript.txt
GET POST /api/sessions/{id}/chat
WS     /api/sessions/{id}/stt
GET    /api/join/{token}               public
POST   /api/join/{token}/ticket        public

GET    /api/sessions/{id}/helper
POST   /api/sessions/{id}/helper/questions | /chat | /documents | /live
PUT    /api/sessions/{id}/helper/notes

GET    /api/jobs/{id}/knowledge        POST .../knowledge/files   POST .../knowledge/text
DELETE /api/jobs/{id}/knowledge/{doc}  GET  .../knowledge/search?q=
POST GET /api/sessions/{id}/analysis

POST GET /api/candidates/{id}/assessment
PUT    /api/candidates/{id}/assessment/decision
GET    /api/jobs/{id}/comparison

GET    /api/dashboard  /api/llm-check  /api/stt-check  /api/email-check  /api/drive-check  /api/workflow-runs
```

Long work (`screen`, `rescreen`, `analysis`, `assessment`) answers **202** and runs as a FastAPI background task; the page polls with `usePolling`. Errors are returned as `{"detail": "<sentence a recruiter understands>"}`.

## 13. Frontend

**Shell** (`App.jsx`): a dark navy sidebar on the left with the product name **LumenAI** and the links **Dashboard, Candidates, Interviews, Job Requirements, Reports, Settings**, with **Log out at the bottom of the sidebar**. A header bar on top of every page and a footer (`AppFooter.jsx`: "© <year> LumenAI · … · The AI suggests. People decide.") on every page and on the login page.

```css
.shell   { display: flex; height: 100vh; overflow: hidden; }
.sidebar { width: 228px; flex: none; display: flex; flex-direction: column; height: 100%; overflow-y: auto; }
.content { flex: 1; min-width: 0; display: flex; flex-direction: column; height: 100%; overflow-y: auto; }
```

Only `.content` scrolls, so the sidebar and Log out stay in place. Print rules reset these heights.

| Page | What it shows |
| --- | --- |
| Login | Passcode form, "Wrong passcode" message |
| Dashboard | Count cards and recent activity |
| Job Requirements | Prompt → **Fill the form with AI**, job form, approve, posting panel, company job descriptions, knowledge base, score weights |
| Candidates | Job picker, **Upload CVs** (with source), **Collect CVs from Google Drive**, **Screen CVs**, ranking with badges (source, OCR, kept by HR, excluded by HR), Excluded and Needs review sections |
| Candidate detail | Requirements with quotes, score breakdown, HR decision cards, needs-review card, schedule interview + invitation editor, delete |
| Interviews | Sessions list: view email, copy link, start, transcript + chat + notes, **Analyse answers** |
| Interview room | Layout from F3 |
| Candidate join (`/join/<token>`, no sidebar) | Consent notice, name box, video, chat. Dark page: inputs must have readable text colour. |
| Q&A analysis | Interview score, each question/answer with four grades, reasons, quote with time, references |
| Reports | Comparison table → assessment report (score cards, summary, strengths, weaknesses, evidence gaps, recommended areas, decision, Export PDF) |
| Settings | **Test AI / speech-to-text / email / Google Drive** buttons and the workflow-runs list |

Style: plain and professional, navy + white, simple cards and tables, small inline SVG icons from `Icon.jsx`. No candidate photo, no "confidence" or "speaking clarity" scores, no recording indicator.

## 14. Non-functional requirements

- **Privacy:** contacts are removed from CV text before AI calls; the AI never receives the email address; CV files are deleted after screening; raw audio is never stored; deleting a candidate deletes all their data. (Names inside CV text and transcripts are *not* removed — state this honestly in the README.)
- **Fairness:** score only job-related evidence. Do not rate voice, accent, appearance, age, gender or confidence.
- **Explainability:** every score on screen shows its reason and quote; every calculated number can be redone by hand from the formula.
- **Human control:** approve, send, keep/exclude and hire/hold/reject are always a person's click.
- **Reliability:** an AI failure marks the item `needs_review` or `failed` with a readable reason; it never crashes the page. Unfinished screening, analysis and assessment resume at start.
- **Security:** secrets only in `.env` and `secrets/`; join tokens are long random strings; Drive access is read-only; upload size and type limits are enforced on the server.
- **Runs with one command:** `docker compose up --build` → web on `WEB_PORT`, API docs on `API_PORT/docs`. PostgreSQL data in a named volume. `secrets/` is mounted read-only into the `api` container.
- **Runs offline:** with `LLM_PROVIDER=fake`, `STT_PROVIDER=fake`, `DRIVE_PROVIDER=fake` and empty SMTP, every page can be clicked through (except real video).

## 15. Tests

`pytest` in `backend/tests/`, using the fake AI, fake speech-to-text and SQLite by default (`TEST_DATABASE_URL` switches to PostgreSQL). No network, no keys.

| File | Covers |
| --- | --- |
| `conftest.py`, `helpers.py`, `interview_fixtures.py` | test database, client with token, shared data |
| `test_jobs.py` | create, edit, delete, AI description |
| `test_requirement_change.py` | prompt → draft, library RAG, approve, posting, CV source |
| `test_cv_screening.py` | exclusion, OCR, English check, resume, DOCX tables |
| `test_candidate_scoring.py` | ratings, weights, re-score |
| `test_hr_overrides.py` | keep, exclude, put back, survive re-screening, needs review |
| `test_drive_collection.py` | Drive collection with the fake provider, no duplicates, skipped files |
| `test_mcp_email.py` | email through the MCP server, failure reasons |
| `test_interviews_and_transcript.py` | draft-first invitation, join link, tickets, echo guard, chat |
| `test_interview_helper.py` | questions, chat, notes, live analysis, question history |
| `test_knowledge_base.py`, `test_qa_analysis.py` | chunks, search, grading, quote check |
| `test_assessments.py` | traceability, repair loop, overall score, decision, comparison |
| `test_graphs.py` | graph shapes and stage routing |
| `test_ai_connection.py`, `test_deepgram.py` | readable check messages |

Target: all tests pass (currently 110) and `npm run build` succeeds.

## 16. Build order

Build and test one step before starting the next.

0. **Setup and login** — tree, `config`, `database`, `security`, `main`, AI client + fake AI, login, health, checks, frontend shell (sidebar, header, footer), Docker Compose.
1. **F1 jobs** — jobs, library (RAG), approve, postings.
2. **F1 screening** — upload, text extraction, OCR, language and privacy checks, screening graph, ranking, candidate page, HR keep / exclude, needs review.
3. **F2 scoring** — parallel scorers, weights, breakdown.
4. **F3 interviews** — sessions, draft-first invitation, SMTP, LiveKit tickets, join page with consent, interviews page.
5. **F4 transcript** — audio worklet, WebSocket, speech-to-text providers, echo guard, download.
6. **F5 analysis** — knowledge base, analysis graph, analysis page.
7. **F6 assessment** — assessment graph, report, decision, comparison, print CSS.
8. **Interview helper and chat** — helper questions/chat/documents/notes, live analysis, question history, call chat, room layout.
9. **MCP** — client, email server, Drive server, Drive collection, Settings checks.
10. **Dashboard, workflow runs, README, FEATURES, demo data.**

## 17. Out of scope

- Posting jobs automatically to LinkedIn or BDJobs.
- Scheduled / automatic CV collection (collection is on demand only).
- Candidate accounts, several interviewer accounts, or role management beyond interviewer and candidate.
- Recording or storing audio or video.
- Any automatic hiring decision.
- Judging voice, confidence, appearance, or identity.

## 18. Done means

- `docker compose up --build` starts the three services and the login page opens.
- With the fake providers, the full path works in the browser: prompt → job → approve → upload CVs → screen → rank → schedule → draft → send → interview → transcript → analysis → assessment → decision → comparison.
- All backend tests pass and the frontend builds.
- No secret, key file, database file or real CV is in the repository.
