import { useEffect, useState } from "react";
import { companyDocumentsApi } from "./companyDocumentsApi.js";
import DataTable from "../../shared/utils/DataTable.jsx";

const KINDS = { job_description: "Past job description", policy: "Company policy" };

// The company's own texts that are stored in the database. Before the AI writes a job, it is given the most
// similar past job descriptions (for style) and the company policy notes (for rules). This is the RAG step.
// This panel only shows, searches and removes. Documents are added in the chat (typed, or as an attached file).
export default function CompanyDocumentsPanel() {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState(null);
  const [error, setError] = useState("");

  const load = () => companyDocumentsApi.list().then(setItems).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function run(action) {
    setError("");
    try { await action(); await load(); } catch (e) { setError(e.message); }
  }
  const search = (event) => {
    event.preventDefault();
    run(async () => setHits(await companyDocumentsApi.search(query)));
  };

  return (
    <div className="card">
      <h3>Company documents <small className="muted">({items.length}; what the AI looks up before it writes)</small></h3>
      <p className="muted small">To add one, attach a PDF, DOCX or TXT file in the chat, or paste the text there and ask the AI to store it.</p>
      {error && <p className="error">{error}</p>}

      <DataTable rows={items} empty="No documents yet." columns={[
        { key: "added", title: "Added", className: "small", render: (d) => new Date(d.created_at).toLocaleDateString() },
        { key: "title", title: "Title" },
        { key: "kind", title: "Kind", className: "small", render: (d) => KINDS[d.kind] || d.kind },
        { key: "source", title: "From", className: "small" },
        { key: "words", title: "Words" },
        { key: "remove", title: "",
          render: (d) => <button className="link" onClick={() => run(() => companyDocumentsApi.remove(d.id))}>Remove</button> },
      ]} />

      <div className="section">
        <h3>Try the search</h3>
        <p className="muted small">Type a job prompt to see which documents the AI would be given, and how similar each is (0 to 1).</p>
        <form onSubmit={search} className="row">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Backend developer with Python and FastAPI" />
          <button className="secondary" disabled={query.trim().length < 3}>Search</button>
        </form>
        {hits && (hits.length === 0 ? <p className="muted">Nothing similar was found.</p> : (
          <ul>
            {hits.map((h) => <li key={h.id}>{h.title} <span className="muted small">· {KINDS[h.kind] || h.kind} · similarity {h.similarity}</span></li>)}
          </ul>
        ))}
      </div>
    </div>
  );
}
