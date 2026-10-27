// CV claim verification (F8, interviewer only): the CV claims compared with what the candidate said
import { request } from "../../shared/api/httpClient.js";

export const claimsApi = {
  // GET /api/candidates/{id}/claims: not_started | running | done | failed, with the claims
  get: (candidateId) => request(`/api/candidates/${candidateId}/claims`),
  // POST /api/candidates/{id}/claims: starts the check; the answer comes at once with "running"
  start: (candidateId) => request(`/api/candidates/${candidateId}/claims`, { method: "POST" }),
};
