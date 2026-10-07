// One place that talks HTTP to the backend: adds the login token and turns errors into messages.
// Every feature has its own small *Api.js file that uses these helpers.
import { auth } from "./authToken.js";

export async function request(path, options = {}) {
  const token = auth.get();
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { ...options, headers });

  if (response.status === 401 && token) {   // login expired -> back to the login page
    auth.clear();
    window.location.reload();
  }

  if (response.status === 204) return null;              // e.g. after a delete
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    // FastAPI puts the message in "detail" (a string, or a list for validation errors)
    const detail = Array.isArray(body.detail) ? "Please check the form fields." : body.detail;
    throw new Error(detail || "Something went wrong. Please try again.");
  }
  return body;
}

// Downloads a file that needs the login token (a plain link cannot send the token) and saves it under `filename`.
export async function download(path, filename) {
  const token = auth.get();
  const response = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "The file could not be downloaded.");
  }
  const address = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = address;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(address);
}

export const json = (data) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const put = (data) => ({ ...json(data), method: "PUT" });
export const post = { method: "POST" };
export const del = { method: "DELETE" };
