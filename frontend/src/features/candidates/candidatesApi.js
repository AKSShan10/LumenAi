// Candidates of a job: the response sheet link, checking and fetching applications, manual upload, the saved CVs
import { del, download, post, put, request } from "../../shared/api/httpClient.js";

export const candidatesApi = {
  list: (jobId) => request(`/api/jobs/${jobId}/candidates`),
  saveSheet: (jobId, sheetUrl) => request(`/api/jobs/${jobId}/response-sheet`, put({ sheet_url: sheetUrl })),
  check: (jobId) => request(`/api/jobs/${jobId}/applications/check`),          // counts new answers; downloads nothing
  fetchNew: (jobId) => request(`/api/jobs/${jobId}/applications/fetch`, post), // downloads the new CVs
  upload: (jobId, file, person) => {
    const form = new FormData();          // a file is sent as form data, not as JSON
    form.append("file", file);
    form.append("full_name", person.fullName || "");
    form.append("email", person.email || "");
    form.append("phone", person.phone || "");
    return request(`/api/jobs/${jobId}/candidates/upload`, { method: "POST", body: form });
  },
  downloadCv: (candidate) => download(`/api/candidates/${candidate.id}/cv`, candidate.original_file_name || `candidate_${candidate.id}`),
  remove: (id) => request(`/api/candidates/${id}`, del),
};
