// Candidate identification (F7, interviewer only): the face in the call compared with the application photo
import { auth } from "../../shared/api/authToken.js";
import { request } from "../../shared/api/httpClient.js";

export const identityApi = {
  // GET /api/sessions/{id}/identity: the identity status of this interview
  get: (sessionId) => request(`/api/sessions/${sessionId}/identity`),
  // POST /api/sessions/{id}/identity/check: sends ONE camera picture (a JPG blob); the server never saves it
  check: (sessionId, picture) => {
    const form = new FormData();
    form.append("frame", picture, "frame.jpg");
    return request(`/api/sessions/${sessionId}/identity/check`, { method: "POST", body: form });
  },
  // PUT /api/sessions/{id}/identity/decision: confirmed | rejected | "" (take back)
  decide: (sessionId, decision) => request(`/api/sessions/${sessionId}/identity/decision`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) }),
  // GET /api/candidates/{id}/photo: the photo from the application, as an address the <img> can show
  photo: async (candidateId) => {
    const token = auth.get();
    const response = await fetch(`/api/candidates/${candidateId}/photo`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    return response.ok ? URL.createObjectURL(await response.blob()) : "";
  },
};
