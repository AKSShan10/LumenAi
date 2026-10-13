// One place that talks HTTP to the backend: adds the login token and turns errors into messages.
// Every feature has its own small *Api.js file that uses these helpers.
import { auth } from "./authToken.js";

// Calls the backend with the login token; logs out on 401 and turns errors into plain messages
export async function request(path, options = {}) {
  const token = auth.get();
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;  // → the backend reads this header to know who is logged in
  const response = await fetch(path, { ...options, headers });  // → sends the HTTP request to the FastAPI backend

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

// Opens a file that needs the login token in a new browser tab (a plain link cannot send the token).
// The tab is opened at once, inside the click, so the browser does not block it; the file is put into it when it
// has arrived. A file the browser cannot show (a Word file) is downloaded instead and the empty tab is closed.
const SHOWN_IN_TAB = ["application/pdf", "text/plain"];

// Fetches a file with the login token and shows it in a new tab, or downloads it if it cannot be shown
export async function openInNewTab(path, filename) {
  const tab = window.open("", "_blank");
  const token = auth.get();
  const response = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) {
    if (tab) tab.close();
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "The file could not be opened.");
  }
  const file = await response.blob();
  const address = URL.createObjectURL(file);
  if (tab && SHOWN_IN_TAB.some((type) => file.type.startsWith(type))) {
    tab.location.href = address;
    setTimeout(() => URL.revokeObjectURL(address), 60000);   // the tab has loaded it by then
    return;
  }
  if (tab) tab.close();                                        // a browser cannot show it: save it instead
  const link = document.createElement("a");
  link.href = address;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(address);
}

// Request options for a POST that sends `data` as JSON
export const json = (data) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

// Request options for a PUT that sends `data` as JSON
export const put = (data) => ({ ...json(data), method: "PUT" });
export const post = { method: "POST" };
export const del = { method: "DELETE" };
