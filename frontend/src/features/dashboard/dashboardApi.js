// The Dashboard numbers (interviewer only)
import { request } from "../../shared/api/httpClient.js";

export const dashboardApi = {
  // GET /api/dashboard?job_id=3: tiles, funnel, scores, what waits, the jobs and the AI health (no job = all jobs)
  get: (jobId) => request(`/api/dashboard${jobId ? `?job_id=${jobId}` : ""}`),
};
