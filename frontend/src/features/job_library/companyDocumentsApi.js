// Company documents the AI looks up before it writes a job (RAG): read, search and remove only.
// Documents are added in the chat (typed, or as an attached file).
import { del, request } from "../../shared/api/httpClient.js";

export const companyDocumentsApi = {
  list: () => request("/api/company-documents"),
  remove: (id) => request(`/api/company-documents/${id}`, del),
  search: (q) => request(`/api/company-documents/search?q=${encodeURIComponent(q)}`),
};
