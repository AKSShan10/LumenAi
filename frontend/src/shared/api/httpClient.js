// One place that talks HTTP to the backend: adds the login token and turns errors into messages.
// Every feature has its own small *Api.js file that uses these helpers.
import { auth } from "./authToken.js";

export async function request(path, options = {}) {
  const token = auth.get();
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { ...options, headers });

  if (response.status === 204) return null;              // e.g. after a delete
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    // FastAPI puts the message in "detail" (a string, or a list for validation errors)
    const detail = Array.isArray(body.detail) ? "Please check the form fields." : body.detail;
    throw new Error(detail || "Something went wrong. Please try again.");
  }
  return body;
}

export const json = (data) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const put = (data) => ({ ...json(data), method: "PUT" });
export const post = { method: "POST" };
export const del = { method: "DELETE" };
