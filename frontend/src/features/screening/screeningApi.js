// CV screening of a job: the AI reads each CV, the backend code checks the job's requirements
import { del, json, openInNewTab, post, put, request } from "../../shared/api/httpClient.js";

export const screeningApi = {
  // GET /api/candidates/{id}/cv: opens the candidate's CV in a new tab
  viewCv: (candidateId, name) => openInNewTab(`/api/candidates/${candidateId}/cv`, `${name || "candidate"} CV`),
  // GET /api/jobs/{id}/screening: the screening results of every candidate of the job
  results: (jobId) => request(`/api/jobs/${jobId}/screening`),
  status: (jobId) => request(`/api/jobs/${jobId}/screening/status`),     // progress of the latest screening run
  screen: (jobId, again = false) => request(`/api/jobs/${jobId}/screening`, json({ again })),   // again: every CV again
  // POST /api/candidates/{id}/screening: screens one CV again
  screenOne: (candidateId) => request(`/api/candidates/${candidateId}/screening`, post),
  // the interviewer's decision: "included", "excluded", or null to undo it; the note is optional
  decide: (candidateId, decision, note) => request(`/api/candidates/${candidateId}/decision`, put({ decision, note })),
  // GET /api/jobs/{id}/score-weights: the job's skills / experience / qualifications weights
  weights: (jobId) => request(`/api/jobs/${jobId}/score-weights`),
  saveWeights: (jobId, weights) => request(`/api/jobs/${jobId}/score-weights`, put(weights)),   // recalculates every score
  // the shortlist: included candidates chosen for the interview invitation (saved in the database)
  shortlist: (jobId) => request(`/api/jobs/${jobId}/shortlist`),
  // rule: "top" (value = K), "min_score" (value = the minimum final score) or "by_hand" (no value)
  addToShortlist: (jobId, candidateIds, rule, value = null) =>
    request(`/api/jobs/${jobId}/shortlist`, json({ candidate_ids: candidateIds, rule, value })),
  // DELETE /api/candidates/{id}/shortlist: takes the candidate off the shortlist
  removeFromShortlist: (candidateId) => request(`/api/candidates/${candidateId}/shortlist`, del),
};
