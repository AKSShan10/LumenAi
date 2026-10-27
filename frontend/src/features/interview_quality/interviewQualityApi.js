// Interview quality (F10, interviewer only): the quality of the interview process itself, not of the candidate
import { request } from "../../shared/api/httpClient.js";

export const interviewQualityApi = {
  // GET /api/sessions/{id}/quality: not_started | running | done | failed, with the result
  get: (sessionId) => request(`/api/sessions/${sessionId}/quality`),
  // POST /api/sessions/{id}/quality: starts the check; the answer comes at once with "running"
  start: (sessionId) => request(`/api/sessions/${sessionId}/quality`, { method: "POST" }),
};
