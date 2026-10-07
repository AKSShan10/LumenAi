// Saved jobs and their posts: read and delete only. Jobs are written, approved and posted in the chat.
import { del, request } from "../../shared/api/httpClient.js";

export const jobsApi = {
  list: () => request("/api/jobs"),
  remove: (id) => request(`/api/jobs/${id}`, del),
  postings: (id) => request(`/api/jobs/${id}/postings`),
};
