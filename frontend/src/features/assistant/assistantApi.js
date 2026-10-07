// The assistant chat: send a message (with an optional file), answer a Yes / No question,
// start a new chat, read an earlier chat, continue an earlier chat
import { json, post, request } from "../../shared/api/httpClient.js";

export const assistantApi = {
  chat: () => request("/api/assistant/chat"),                              // the current chat
  earlier: (chatId) => request(`/api/assistant/chat?chat_id=${chatId}`),     // read an earlier chat
  continueChat: (chatId) => request(`/api/assistant/chat/${chatId}/continue`, post),   // make it the current chat again
  send: (text, file) => {
    const form = new FormData();          // a file is sent as form data, not as JSON
    form.append("text", text);
    if (file) form.append("file", file);
    return request("/api/assistant/chat", { method: "POST", body: form });
  },
  answer: (actionId, yes) => request(`/api/assistant/actions/${actionId}`, json({ yes })),
  newChat: () => request("/api/assistant/chat/new", post),                 // the earlier chats are kept
};
