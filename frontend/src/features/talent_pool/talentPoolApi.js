// Talent pool (innovation feature): keep past candidates, find who fits a new job, invite them; the public unsubscribe
import { del, json, put, request } from "../../shared/api/httpClient.js";

export const talentPoolApi = {
  // GET /api/candidates/{id}/talent-pool: is this candidate in the pool?
  entry: (candidateId) => request(`/api/candidates/${candidateId}/talent-pool`),
  // PUT /api/candidates/{id}/talent-pool: keep the candidate (or change status and note)
  // addBack = true: add again someone who unsubscribed (only when they asked to be contacted again)
  add: (candidateId, status, note, addBack = false) => request(`/api/candidates/${candidateId}/talent-pool`,
    put({ status, note, add_back: addBack })),
  // DELETE /api/candidates/{id}/talent-pool: take the candidate out
  remove: (candidateId) => request(`/api/candidates/${candidateId}/talent-pool`, del),
  // GET /api/talent-pool: everyone in the pool
  list: () => request("/api/talent-pool"),
  // GET /api/jobs/{id}/talent-matches?min_match=..: past candidates who may fit the job (code), with the filters.
  // Answers {min_match, rows}. Empty filters are left out (min_match empty = the default from .env).
  matches: (jobId, filters = {}) => {
    const query = new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== "" && v !== false && v !== null));
    return request(`/api/jobs/${jobId}/talent-matches?${query}`);
  },
  // POST /api/jobs/{id}/talent-invites/draft: the workflow drafts one checked email per person (nothing is sent);
  // also "Write again" for one person, with a wish (the emails are always formal)
  draft: (jobId, poolIds, instruction = "") => request(`/api/jobs/${jobId}/talent-invites/draft`,
    json({ pool_ids: poolIds, instruction })),
  // POST /api/jobs/{id}/talent-invites/send: sends the emails as the interviewer checked them
  send: (jobId, invites) => request(`/api/jobs/${jobId}/talent-invites/send`, json({ invites })),
  // GET / POST /api/unsubscribe/{token}: the public "no more emails" page (no login)
  unsubscribeInfo: (token) => request(`/api/unsubscribe/${token}`),
  unsubscribe: (token) => request(`/api/unsubscribe/${token}`, { method: "POST" }),
};

export const POOL_STATUS = { strong: "Strong candidate, not selected", other_role: "Good fit for another role" };
