// Company documents the AI looks up before it writes a job (RAG)
import { del, json, request } from "../../shared/api/httpClient.js";

export const companyDocumentsApi = {
  list: () => request("/api/company-documents"),
  add: (kind, title, text) => request("/api/company-documents", json({ kind, title, text })),
  upload: (kind, title, file) => {
    const form = new FormData();          // a file is sent as form data, not as JSON
    form.append("kind", kind);
    form.append("title", title);
    form.append("file", file);
    return request("/api/company-documents/upload", { method: "POST", body: form });
  },
  remove: (id) => request(`/api/company-documents/${id}`, del),
  search: (q) => request(`/api/company-documents/search?q=${encodeURIComponent(q)}`),
};
