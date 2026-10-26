import { useEffect, useState } from "react";
import { companyDocumentsApi } from "./companyDocumentsApi.js";
import ConfirmDialog from "../../shared/utils/ConfirmDialog.jsx";

const KINDS = { job_description: "Past job description", policy: "Company policy" };
const FILTERS = [["all", "All"], ["job_description", "Past job descriptions"], ["policy", "Policies"]];
const SOURCES = { added: "added in the chat", "approved job": "from an approved job" };

// A search result as a word instead of a number. Only a guide for the eye: the exact similarity is in the tooltip.
function matchLabel(similarity) {
  if (similarity >= 0.7) return ["High match", "high"];
  if (similarity >= 0.5) return ["Medium match", "medium"];
  return ["Low match", "low"];
}

// The Knowledge base tab: the company's own texts stored in the database. Before the AI writes a job, it is given
// the most similar past job descriptions (for style) and the company policy notes (for rules). This is the RAG step.
// This tab only shows, searches and removes. Documents are added in the chat (typed, or as an attached file).
// onOpenChat(text): opens the chat tab.  onChanged(): the tab numbers are read again.
export default function CompanyDocumentsPanel({ onOpenChat, onChanged }) {
  const [items, setItems] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState(null);
  const [reading, setReading] = useState(null);        // the document open in the "View" pop-up (with its text)
  const [askRemove, setAskRemove] = useState(null);    // the document waiting for Yes / No before it is removed
  const [error, setError] = useState("");

  // Loads the documents from GET /api/company-documents
  const load = () => companyDocumentsApi.list().then(setItems).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  // Runs one action (search, view or remove) and shows any error
  async function run(action) {
    setError("");
    try { await action(); } catch (e) { setError(e.message); }
  }
  // On Search: the documents the AI would be given for this text (companyDocumentsApi.search)
  const search = (event) => {
    event.preventDefault();
    run(async () => setHits(await companyDocumentsApi.search(query)));
  };
  // After Yes in the pop-up: removes the document, then reloads the list and the tab numbers
  const remove = () => run(async () => {
    const document = askRemove;
    setAskRemove(null);
    await companyDocumentsApi.remove(document.id);
    setHits(null);
    await load();
    onChanged();
  });

  if (!items) return <div className="card">{error ? <p className="error">{error}</p> : <p>Loading...</p>}</div>;
  const shown = items.filter((d) => filter === "all" || d.kind === filter);
  const howMany = (key) => (key === "all" ? items.length : items.filter((d) => d.kind === key).length);

  return (
    <div className="knowledge-split">
      {/* left: the documents */}
      <div className="card">
        <div className="row-between panel-head">
          <div>
            <h3>What the AI reads before it writes</h3>
            <p className="muted small">To add a document, attach a PDF, DOCX or TXT file in the chat, or paste the text there.</p>
          </div>
          <button className="secondary" onClick={() => onOpenChat("")}>+ Add in the chat</button>
        </div>
        <div className="filter-chips">
          {FILTERS.map(([key, label]) => (
            <button key={key} type="button" className={filter === key ? "on" : ""} onClick={() => setFilter(key)}>
              {label} {howMany(key)}
            </button>
          ))}
        </div>
        {error && <p className="error">{error}</p>}

        {items.length === 0 && (
          <div className="empty-state">
            <h3>The knowledge base is empty</h3>
            <p className="muted">Without documents the AI writes jobs from your prompt only.</p>
          </div>
        )}
        {shown.map((d) => (
          <div key={d.id} className="doc-card">
            <div className="row-between">
              <b>{d.title}</b>
              <span className={`badge kind-${d.kind}`}>{KINDS[d.kind] || d.kind}</span>
            </div>
            {d.preview && <p className="doc-preview">“{d.preview}”</p>}
            <div className="row-between small muted">
              <span>Added {new Date(d.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}
                {" · "}{SOURCES[d.source] || d.source} · {d.words} words</span>
              <span>
                <button type="button" className="link" onClick={() => run(async () => setReading(await companyDocumentsApi.get(d.id)))}>View</button>
                <button type="button" className="link remove-link" onClick={() => setAskRemove(d)}>Remove</button>
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* right: try the search */}
      <div className="card">
        <h3>What will the AI read?</h3>
        <p className="muted small">Type a job prompt to see which documents the AI would be given.</p>
        <form onSubmit={search} className="row">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Backend developer with Python" />
          <button className="secondary" disabled={query.trim().length < 3}>Search</button>
        </form>
        {hits && hits.length === 0 && <p className="muted">Nothing similar was found.</p>}
        {hits && hits.map((h) => {
          const [label, level] = matchLabel(h.similarity);
          return (
            <div key={`${h.kind}-${h.id}`} className="match-row" title={`similarity ${h.similarity}`}>
              <b>{h.title}</b> <span className="muted small">· {KINDS[h.kind] || h.kind}</span>
              <div className="match-bar"><i style={{ width: `${Math.max(4, Math.min(100, h.similarity * 100))}%` }} /></div>
              <span className={`match-label ${level}`}>{label}</span>
            </div>
          );
        })}
      </div>

      {reading && (
        <div className="modal-backdrop" onClick={() => setReading(null)}>
          <div className="modal wide" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="row-between">
              <h3>{reading.title}</h3>
              <span className={`badge kind-${reading.kind}`}>{KINDS[reading.kind] || reading.kind}</span>
            </div>
            <div className="description modal-text">{reading.text}</div>
            <div className="modal-buttons"><button type="button" onClick={() => setReading(null)}>Close</button></div>
          </div>
        </div>
      )}
      {askRemove && (
        <ConfirmDialog question={`Remove "${askRemove.title}" from the knowledge base?`}
                       detail="The AI will no longer read it. This cannot be undone."
                       onYes={remove} onNo={() => setAskRemove(null)} />
      )}
    </div>
  );
}
