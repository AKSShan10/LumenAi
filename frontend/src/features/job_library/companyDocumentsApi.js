// Company documents the AI looks up before it writes a job (RAG): read, search and remove only.
// Documents are added in the chat (typed, or as an attached file).
import { del, request } from "../../shared/api/httpClient.js";

export const companyDocumentsApi = {
  // GET /api/company-documents: all stored company documents
  list: () => request("/api/company-documents"),
  // DELETE /api/company-documents/{id}: removes one company document
  remove: (id) => request(`/api/company-documents/${id}`, del),
  // GET /api/company-documents/search?q=...: the documents most similar to the text (RAG test)
  search: (q) => request(`/api/company-documents/search?q=${encodeURIComponent(q)}`),
};
