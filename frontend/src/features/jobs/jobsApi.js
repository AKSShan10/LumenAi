// Job profiles: create, edit, delete, AI draft from a prompt, approve, post to Telegram
import { del, json, put, request } from "../../shared/api/httpClient.js";

export const jobsApi = {
  list: () => request("/api/jobs"),
  create: (job) => request("/api/jobs", json(job)),
  update: (id, job) => request(`/api/jobs/${id}`, put(job)),
  remove: (id) => request(`/api/jobs/${id}`, del),
  // changeRequest and previous are only sent by "Generate again"
  draftFromPrompt: (prompt, changeRequest = "", previous = "") =>
    request("/api/jobs/draft-from-prompt", json({ prompt, change_request: changeRequest, previous })),
  approve: (id, addToLibrary) => request(`/api/jobs/${id}/approve`, json({ add_to_library: addToLibrary })),
  postText: (id) => request(`/api/jobs/${id}/post-text`),
  postDraft: (id, changeRequest = "", previous = "") =>
    request(`/api/jobs/${id}/post-draft`, json({ change_request: changeRequest, previous })),
  post: (id, text, applyUrl) => request(`/api/jobs/${id}/post`, json({ text, apply_url: applyUrl })),
  postings: (id) => request(`/api/jobs/${id}/postings`),
};
