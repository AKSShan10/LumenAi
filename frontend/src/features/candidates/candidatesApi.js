// Candidates of a job: checking and fetching applications from the job's Google Form, manual upload, the saved CVs
import { del, download, openInNewTab, post, request } from "../../shared/api/httpClient.js";

export const candidatesApi = {
  // GET /api/jobs/{id}/candidates: the candidates of one job, newest first
  list: (jobId) => request(`/api/jobs/${jobId}/candidates`),
  check: (jobId) => request(`/api/jobs/${jobId}/applications/check`),          // looks only at the answers after the checkpoint
  recheck: (jobId) => request(`/api/jobs/${jobId}/applications/recheck`, post), // moves the checkpoint back to the start
  fetchNew: (jobId) => request(`/api/jobs/${jobId}/applications/fetch`, post), // downloads the new CVs
  // POST /api/jobs/{id}/candidates/upload: uploads one CV file (form data) with optional name, email, phone
  upload: (jobId, file, person) => {
    const form = new FormData();          // a file is sent as form data, not as JSON
    form.append("file", file);
    form.append("full_name", person.fullName || "");
    form.append("email", person.email || "");
    form.append("phone", person.phone || "");
    return request(`/api/jobs/${jobId}/candidates/upload`, { method: "POST", body: form });
  },
  // GET /api/candidates/{id}/cv: opens the saved CV in a new tab (Word files are downloaded)
  viewCv: (candidate) => openInNewTab(`/api/candidates/${candidate.id}/cv`, candidate.original_file_name || `candidate_${candidate.number}`),
  // GET /api/candidates/{id}/cv: downloads the saved CV file
  downloadCv: (candidate) => download(`/api/candidates/${candidate.id}/cv`, candidate.original_file_name || `candidate_${candidate.number}`),
  // DELETE /api/candidates/{id}: deletes the candidate and their saved CV file
  remove: (id) => request(`/api/candidates/${id}`, del),
};
