// The Q&A analysis of an interview (interviewer only): the answers graded after the call
import { request } from "../../shared/api/httpClient.js";

export const qaAnalysisApi = {
  // GET /api/sessions/{id}/analysis: the result ("not_started", "running", "done" or "failed")
  get: (sessionId) => request(`/api/sessions/${sessionId}/analysis`),
  // POST /api/sessions/{id}/analysis: starts the analysis; the answer comes at once with "running"
  start: (sessionId) => request(`/api/sessions/${sessionId}/analysis`, { method: "POST" }),
};
