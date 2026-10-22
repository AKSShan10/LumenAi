// Interviews: schedule a shortlisted candidate, the invitation email (with a calendar invite), the candidate's page
import { json, put, request } from "../../shared/api/httpClient.js";

export const interviewsApi = {
  // GET /api/sessions?job_id=...: the interviews of one job
  list: (jobId) => request(`/api/sessions?job_id=${jobId}`),
  // GET /api/sessions/{id}: one interview (who, when, call times, analysis score)
  get: (sessionId) => request(`/api/sessions/${sessionId}`),
  // when: {scheduled_at (ISO, UTC), duration_minutes, time_zone}; the backend writes the invitation draft
  schedule: (candidateId, when) => request("/api/sessions", json({ candidate_id: candidateId, ...when })),
  // POST /api/sessions/plan: suggested times for the whole shortlist (nothing is saved)
  plan: (settings) => request("/api/sessions/plan", json(settings)),
  // POST /api/sessions/template: the AI writes ONE invitation for the shortlist, to check ({subject, body, message})
  template: (settings) => request("/api/sessions/template", json(settings)),
  // POST /api/sessions/bulk: schedules many candidates at once with the checked invitation; nothing is sent
  scheduleMany: (items, template) => request("/api/sessions/bulk", json({ items, template })),
  // POST /api/sessions/send-all?job_id=...: sends every unsent invitation of the job
  sendAll: (jobId) => request(`/api/sessions/send-all?job_id=${jobId}`, { method: "POST" }),
  // PUT /api/sessions/{id}/time: changes the interview time (the backend writes the email again)
  changeTime: (sessionId, when) => request(`/api/sessions/${sessionId}/time`, put(when)),
  // POST /api/sessions/{id}/invitation: asks the AI to write the invitation email again
  writeAgain: (sessionId) => request(`/api/sessions/${sessionId}/invitation`, { method: "POST" }),
  // PUT /api/sessions/{id}/invitation: sends the checked invitation email to the candidate
  send: (sessionId, to, subject, body) => request(`/api/sessions/${sessionId}/invitation`, put({ to, subject, body })),
  joinInfo: (token) => request(`/api/join/${token}`),      // public: the candidate's page
  // the video call: the answers have {server_url, ticket, room_name, identity} for LiveKit
  start: (sessionId) => request(`/api/sessions/${sessionId}/start`, { method: "POST" }),   // start or join again
  end: (sessionId) => request(`/api/sessions/${sessionId}/end`, { method: "POST" }),       // end for both
  profile: (sessionId) => request(`/api/sessions/${sessionId}/profile`),   // the candidate's profile (interviewer only)
  joinTicket: (token, name) => request(`/api/join/${token}/ticket`, json({ name })),        // public: the candidate
  // the chat in the call: "after" = the newest message id the page already has (0 = all)
  chat: (sessionId, after = 0) => request(`/api/sessions/${sessionId}/chat?after=${after}`),
  // POST /api/sessions/{id}/chat: the interviewer sends a chat message in the call
  sendChat: (sessionId, text) => request(`/api/sessions/${sessionId}/chat`, json({ text })),
  joinChat: (token, after = 0) => request(`/api/join/${token}/chat?after=${after}`),          // public: the candidate
  // POST /api/join/{token}/chat: the candidate sends a chat message in the call (no login)
  joinSendChat: (token, text) => request(`/api/join/${token}/chat`, json({ text })),
};

// How the invitation status is shown: "" = draft, sent, not_sent, no_email, or "failed: <reason>"
const STATUS_WORDS = {
  "": { label: "Draft, not sent", badge: "draft" },
  sent: { label: "Sent", badge: "done" },
  not_sent: { label: "Not sent (no email set up)", badge: "draft" },
  no_email: { label: "Not sent (no address)", badge: "failed" },
};
// Turns an invitation status into a label and badge color; unknown values mean it failed
export const invitationStatus = (status) => STATUS_WORDS[status] || { label: "Failed", badge: "failed" };
