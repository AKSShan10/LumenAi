// CV screening of a job: the AI reads each CV, the backend code checks the job's requirements
import { json, post, put, request } from "../../shared/api/httpClient.js";

export const screeningApi = {
  results: (jobId) => request(`/api/jobs/${jobId}/screening`),
  status: (jobId) => request(`/api/jobs/${jobId}/screening/status`),     // progress of the latest screening run
  screen: (jobId, again = false) => request(`/api/jobs/${jobId}/screening`, json({ again })),   // again: every CV again
  screenOne: (candidateId) => request(`/api/candidates/${candidateId}/screening`, post),
  // the interviewer's decision: "included", "excluded", or null to undo it; the note is optional
  decide: (candidateId, decision, note) => request(`/api/candidates/${candidateId}/decision`, put({ decision, note })),
  weights: (jobId) => request(`/api/jobs/${jobId}/score-weights`),
  saveWeights: (jobId, weights) => request(`/api/jobs/${jobId}/score-weights`, put(weights)),   // recalculates every score
};
