// The assistant chat: send a message (with an optional file), answer a Yes / No question, start over
import { del, json, request } from "../../shared/api/httpClient.js";

export const assistantApi = {
  chat: () => request("/api/assistant/chat"),
  send: (text, file) => {
    const form = new FormData();          // a file is sent as form data, not as JSON
    form.append("text", text);
    if (file) form.append("file", file);
    return request("/api/assistant/chat", { method: "POST", body: form });
  },
  answer: (actionId, yes) => request(`/api/assistant/actions/${actionId}`, json({ yes })),
  clear: () => request("/api/assistant/chat", del),
};
