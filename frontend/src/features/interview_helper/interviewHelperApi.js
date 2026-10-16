// The AI helper in the interviewer's call: suggested questions with model answers, and a chat (interviewer only)
import { json, request } from "../../shared/api/httpClient.js";

export const interviewHelperApi = {
  // GET /api/sessions/{id}/helper: everything asked and answered for this interview, oldest first
  history: (sessionId) => request(`/api/sessions/${sessionId}/helper`),
  // POST /api/sessions/{id}/helper/questions: up to 8 questions with model answers ("" topic = the AI chooses)
  questions: (sessionId, topic) => request(`/api/sessions/${sessionId}/helper/questions`, json({ topic })),
  // POST /api/sessions/{id}/helper/chat: ask the helper; returns [your message, its answer]
  chat: (sessionId, text) => request(`/api/sessions/${sessionId}/helper/chat`, json({ text })),
};
