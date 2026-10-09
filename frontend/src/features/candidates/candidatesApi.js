// Candidates of a job: checking and fetching applications from the job's Google Form, manual upload, the saved CVs
import { del, download, openInNewTab, post, request } from "../../shared/api/httpClient.js";

export const candidatesApi = {
  list: (jobId) => request(`/api/jobs/${jobId}/candidates`),
  check: (jobId) => request(`/api/jobs/${jobId}/applications/check`),          // looks only at the answers after the checkpoint
  recheck: (jobId) => request(`/api/jobs/${jobId}/applications/recheck`, post), // moves the checkpoint back to the start
  fetchNew: (jobId) => request(`/api/jobs/${jobId}/applications/fetch`, post), // downloads the new CVs
  upload: (jobId, file, person) => {
    const form = new FormData();          // a file is sent as form data, not as JSON
    form.append("file", file);
    form.append("full_name", person.fullName || "");
    form.append("email", person.email || "");
    form.append("phone", person.phone || "");
    return request(`/api/jobs/${jobId}/candidates/upload`, { method: "POST", body: form });
  },
  viewCv: (candidate) => openInNewTab(`/api/candidates/${candidate.id}/cv`, candidate.original_file_name || `candidate_${candidate.number}`),
  downloadCv: (candidate) => download(`/api/candidates/${candidate.id}/cv`, candidate.original_file_name || `candidate_${candidate.number}`),
  remove: (id) => request(`/api/candidates/${id}`, del),
};
