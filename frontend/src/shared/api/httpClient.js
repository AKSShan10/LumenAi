// One place that talks HTTP to the backend and turns errors into messages.
// Every feature has its own small *Api.js file that uses these helpers.

export async function request(path, options = {}) {
  const response = await fetch(path, options);

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
