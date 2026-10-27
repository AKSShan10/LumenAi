# Innovation Feature (F11): Talent Pool and Rediscovery

**Project:** LumenAI, BJIT AI Trainee Project
**Author:** Md. Abdul Kahhar Siddiki Shan (ID 30229)
**Code:** `backend/app/features/talent_pool/`, `backend/app/graphs/talent_invite_graph.py`, `frontend/src/features/talent_pool/`
**Tests:** `backend/tests/test_talent_pool.py` (17 tests)

---

## 1. What it is

The talent pool keeps strong candidates who were not hired, and brings them back when a new job fits them.

1. **Keep.** On a candidate's assessment report, the interviewer adds the person to the talent pool with a status ("Strong candidate, not selected" or "Good fit for another role") and an optional note.
2. **Rediscover.** When a new job is approved, the Talent Pool page lists the pool candidates whose CVs show that job's skills, with a match percentage.
3. **Invite.** The interviewer selects people, the AI drafts a short personal invitation for each one, code checks every draft, and **a person sends it**.

---

## 2. Why I built it

Every hiring round in LumenAI produces more work than one hire. The system reads every CV, interviews the shortlist, grades the answers and writes an evidence-backed report. Usually only one person is hired. Before this feature, everything learned about the other strong candidates was lost when the job closed.

I saw three problems:

- **Good candidates were thrown away.** A candidate can be the second-best person for one job and the best person for the next one. Without a pool, the team has to find that person again from the start, or never finds them.
- **The same work was paid for twice.** Posting the job, collecting CVs, screening and interviewing take time from the hiring team. When a similar job opens, a known, already-assessed candidate is a faster and more reliable starting point than a new round of unknown applicants.
- **Past candidates had no good way back.** A person who did well in an interview but was not selected usually hears nothing more. A respectful, personal invitation to a fitting new job keeps a good relationship with that person.

The other features (F1–F10) help hire for **one** job. The talent pool makes each hiring round useful for the **next** jobs too. That is why I chose it as the innovation feature.

### Alternatives I considered

Before choosing, I compared several ideas for F11: a job description quality checker, a "Why candidate A over B" explanation, duplicate CV detection, reference-check questions and interview self-scheduling. I chose the talent pool because:

- It adds a new capability across hiring rounds, instead of improving one step of a single round.
- It reuses what LumenAI already has: CV text, screening results, assessment reports, LangGraph workflows and the invitation email.
- It can be built safely with the project's rules: code decides the match, the AI only drafts, and a person sends.

---

## 3. Why it is important

| For | Benefit |
|---|---|
| **The hiring team** | Starts a new job with people who are already screened and interviewed, instead of an empty list. |
| **The organisation** | Gets more value from every interview it has already run, and fills similar roles faster. |
| **Candidates** | Strong people who were not selected get a fair second chance, through a polite and personal invitation they can decline or unsubscribe from. |
| **Fairness** | The match uses only job skills and CV text, so rediscovery does not depend on who someone is or who remembers them. |

---

## 4. How it works

### 4.1 Keeping a candidate

- **Added from the assessment report** (Talent pool card): status `strong` or `other_role`, plus an optional note.
- **Limited retention:** each entry is kept for `POOL_KEEP_DAYS` (default 365 days). Expired entries are never suggested.
- **Removal:** the interviewer can remove a person at any time. Deleting a candidate deletes their pool entry and invitations.

### 4.2 Finding who fits a new job (code only, no AI)

- **Score:** the match percentage is calculated by code from the job's skills and the skills found in the CV.
- **Weights:** a required skill counts **twice**, a preferred skill **once**.
- **Same skill, different name:** names for the same skill count the same, for example Postgres = PostgreSQL.
- **Filters:** minimum match (starting value `POOL_MIN_MATCH`, default 50 %), "All required skills", earlier score, status, and "Hide already invited".
- **Left out:**
  - people who are not active (unsubscribed or expired);
  - the job they already applied to;
  - anyone whose email already applied to the new job;
  - CVs that show none of the job's skills.

### 4.3 Writing and sending the invitation (LangGraph)

The talent invite workflow (`talent_invite_graph.py`) runs once per person:

```
start → load_facts → write_draft → check_draft → finish → end
                          ↑      (retry once) │
                          └───────────────────┤
                                              └→ standard_text (if the AI fails twice) → finish
```

- **What the AI sees:** only the first name, the earlier and new job titles, and the CV skills that fit the new job. It never sees scores, earlier results, decisions or contact details.
- **What code checks in each draft:** the name and job title are present, and there are no links, email addresses, scores, decisions, promises of a job, or skills the CV does not show.
- **Write again:** the interviewer can ask for a change in their own words, or use the quick "Shorter" / "Very short" buttons. The new draft is written from the draft on the page.
- **Added by the system, not the AI:** the apply link, the unsubscribe link and the signature.
- **Sending:** a person reviews and clicks Send. Nothing is sent automatically.

---

## 5. Responsible-AI safeguards

- **A person decides:** the AI only drafts. Keeping, matching, filtering and sending are code or human actions.
- **Fair matching:** name, gender, age, address, nationality, school and earlier scores never change the match or the order. Counterfactual tests prove it (`test_the_match_ignores_who_the_person_is`).
- **Fair wording:** the invitation prompt forbids scores, earlier results, decisions and private matters (`test_the_invitation_prompt_is_fair`).
- **Consent and privacy:**
  - **Unsubscribe link:** every email has one, and it works without logging in.
  - **No more emails:** a person who unsubscribes is never suggested or invited again.
  - **Add back:** the interviewer can add an unsubscribed person back only after confirming the person asked for it, and that creates a new unsubscribe link.
- **Limited retention:** entries expire after `POOL_KEEP_DAYS`.

> In a real deployment, the application form should tell candidates that their CV may be kept for future openings.

---

## 6. Where it is in the code

| Part | Location |
|---|---|
| Table and migration | `talent_pool/models/talent_pool_model.py` (`talent_pool`, `talent_invite`), `migrations/versions/20261022_0032_talent_pool.py` |
| Keep, match, unsubscribe | `talent_pool/services/pool_service.py` |
| Drafts and sending | `talent_pool/services/invite_service.py` |
| Routers | `talent_pool/routers/talent_pool_router.py`, `talent_pool/routers/unsubscribe_router.py` |
| Invitation workflow and prompt | `graphs/talent_invite_graph.py`, `graphs/talent_invite_prompts.py` |
| API | `GET/PUT/DELETE /api/candidates/{id}/talent-pool`, `GET /api/talent-pool`, `GET /api/jobs/{id}/talent-matches`, `POST /api/jobs/{id}/talent-invites/draft`, `POST /api/jobs/{id}/talent-invites/send`, `GET` / `POST /api/unsubscribe/{token}` (public; opening the link alone never unsubscribes) |
| Screens | `TalentPoolPage.jsx` (Talent Pool page), `TalentPoolCard.jsx` (card on the assessment report) |
| Diagram | `docs/architecture/langgraph/LumenAI_LangGraph_5_Talent_Invite.*` |
| Settings | `POOL_KEEP_DAYS` (default 365), `POOL_MIN_MATCH` (default 50) |

---

## 7. How to try it

1. Open an **assessment report** and add the candidate to the talent pool with the Talent pool card.
2. Approve a **new job** with skills that the candidate's CV shows.
3. Open **Talent Pool**, choose the new job, and adjust the filters if needed.
4. Tick the candidates and click **Draft invitations**. Edit a draft or use **Write again** / **Shorter**.
5. Click **Send**. Open the unsubscribe link from the email and confirm; the person is then no longer suggested.

---

## 8. Testing

`backend/tests/test_talent_pool.py` has 17 tests. They cover:

- keeping and removing a person;
- matching, including skill-name variants and the higher weight of required skills;
- the filters;
- ignoring personal attributes;
- the prompt's fairness rules;
- the draft check and its single retry;
- the standard text when the AI fails twice;
- Write again;
- unsubscribe and add back;
- expiry;
- deletion.

All tests run offline with a fake AI.

---

## 9. Limitations and future work

- **Skill words only:** matching uses skill names, not meaning (no vector search yet). A CV that describes a skill in other words may match lower.
- **Manual adding:** candidates enter the pool only when an interviewer adds them; there is no automatic suggestion.
- **Manual sending:** invitations go one batch at a time when a person clicks Send; there is no scheduled re-engagement.
- **Future work:** semantic matching with embeddings (pgvector), suggesting pool candidates automatically when a job is approved, and tracking who applied after an invitation.
