// Saved jobs and their posts: read and delete only. Jobs are written, approved and posted in the chat.
import { del, request } from "../../shared/api/httpClient.js";

export const jobsApi = {
  // GET /api/jobs: all saved jobs
  list: () => request("/api/jobs"),
  // DELETE /api/jobs/{id}: deletes one job
  remove: (id) => request(`/api/jobs/${id}`, del),
  // GET /api/jobs/{id}/postings: where and when this job was posted
  postings: (id) => request(`/api/jobs/${id}/postings`),
};
