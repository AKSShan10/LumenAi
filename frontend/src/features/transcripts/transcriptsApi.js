// The live transcript: reading the saved sentences (the microphones use WebSockets, see MicToText.jsx)
import { request } from "../../shared/api/httpClient.js";

export const transcriptsApi = {
  // GET /api/sessions/{id}/transcript?after=...: the sentences after that id (interviewer only)
  transcript: (sessionId, after = 0) => request(`/api/sessions/${sessionId}/transcript?after=${after}`),
};
