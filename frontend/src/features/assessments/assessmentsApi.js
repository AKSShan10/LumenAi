// The consolidated assessment (interviewer only): the final report, the decision and the comparison of candidates
import { put, request } from "../../shared/api/httpClient.js";

export const assessmentsApi = {
  // GET /api/jobs/{id}/comparison: the interviewed candidates of a job, best overall score first
  comparison: (jobId) => request(`/api/jobs/${jobId}/comparison`),
  // GET /api/candidates/{id}/assessment: the report ("not_started", "running", "done" or "failed")
  get: (candidateId) => request(`/api/candidates/${candidateId}/assessment`),
  // POST /api/candidates/{id}/assessment: starts the assessment; the answer comes at once with "running"
  start: (candidateId) => request(`/api/candidates/${candidateId}/assessment`, { method: "POST" }),
  // PUT /api/candidates/{id}/assessment/decision: the interviewer's decision (hire, hold, reject, or pending to undo)
  decide: (candidateId, decision, note) => request(`/api/candidates/${candidateId}/assessment/decision`, put({ decision, note })),
};
