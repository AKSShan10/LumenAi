// The Knowledge base: company documents the AI looks up before it writes a job (RAG). Read, search and remove only.
// Documents are added in the chat (typed, or as an attached file).
import { del, request } from "../../shared/api/httpClient.js";

export const companyDocumentsApi = {
  // GET /api/company-documents: all stored company documents
  list: () => request("/api/company-documents"),
  // GET /api/company-documents/{id}: one document with its whole text (the "View" button)
  get: (id) => request(`/api/company-documents/${id}`),
  // DELETE /api/company-documents/{id}: removes one company document
  remove: (id) => request(`/api/company-documents/${id}`, del),
  // GET /api/company-documents/search?q=...: the documents most similar to the text (RAG test)
  search: (q) => request(`/api/company-documents/search?q=${encodeURIComponent(q)}`),
};
