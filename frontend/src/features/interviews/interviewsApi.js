// Interviews: schedule a shortlisted candidate, the invitation email (with a calendar invite), the candidate's page
import { json, put, request } from "../../shared/api/httpClient.js";

export const interviewsApi = {
  list: (jobId) => request(`/api/sessions?job_id=${jobId}`),
  // when: {scheduled_at (ISO, UTC), duration_minutes, time_zone}; the backend writes the invitation draft
  schedule: (candidateId, when) => request("/api/sessions", json({ candidate_id: candidateId, ...when })),
  changeTime: (sessionId, when) => request(`/api/sessions/${sessionId}/time`, put(when)),
  writeAgain: (sessionId) => request(`/api/sessions/${sessionId}/invitation`, { method: "POST" }),
  send: (sessionId, to, subject, body) => request(`/api/sessions/${sessionId}/invitation`, put({ to, subject, body })),
  joinInfo: (token) => request(`/api/join/${token}`),      // public: the candidate's page
};

// How the invitation status is shown: "" = draft, sent, not_sent, no_email, or "failed: <reason>"
const STATUS_WORDS = {
  "": { label: "Draft, not sent", badge: "draft" },
  sent: { label: "Sent", badge: "done" },
  not_sent: { label: "Not sent (no email set up)", badge: "draft" },
  no_email: { label: "Not sent (no address)", badge: "failed" },
};
export const invitationStatus = (status) => STATUS_WORDS[status] || { label: "Failed", badge: "failed" };
