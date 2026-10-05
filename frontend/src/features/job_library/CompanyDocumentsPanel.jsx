import { useEffect, useRef, useState } from "react";
import { companyDocumentsApi } from "./companyDocumentsApi.js";

const KINDS = { job_description: "Past job description", policy: "Company policy" };

// The company's own texts. Before the AI writes a job, it will be given the most similar past job
// descriptions (for style) and the company policy notes (for rules). This is the RAG step.
export default function CompanyDocumentsPanel() {
  const [items, setItems] = useState([]);
  const [kind, setKind] = useState("job_description");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const fileInput = useRef(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState(null);
  const [error, setError] = useState("");

  const load = () => companyDocumentsApi.list().then(setItems).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function run(action) {
    setError("");
    try { await action(); await load(); } catch (e) { setError(e.message); }
  }
  const add = (event) => {
    event.preventDefault();
    run(async () => {
      // A chosen file wins; otherwise the pasted text is saved.
      if (file) await companyDocumentsApi.upload(kind, title, file);
      else await companyDocumentsApi.add(kind, title, text);
      setTitle(""); setText(""); setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    });
  };
  const search = (event) => {
    event.preventDefault();
    run(async () => setHits(await companyDocumentsApi.search(query)));
  };

  return (
    <div className="card">
      <h3>Company documents <small className="muted">(what the AI looks up before it writes)</small></h3>
      <p className="muted small">Upload or paste past job descriptions and company policy notes. A new job description follows the most
        similar past ones and the policy notes.</p>

      <form onSubmit={add}>
        <div className="two-columns">
          <label>Kind
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(KINDS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={file ? "Empty = the file name" : "Backend Developer 2025"} />
          </label>
        </div>
        <label>File <small>(PDF, DOCX or TXT, 5 MB at most)</small>
          <input type="file" accept=".pdf,.docx,.txt" ref={fileInput} onChange={(e) => setFile(e.target.files[0] || null)} />
        </label>
        {!file && (
          <label>Or paste the text
            <textarea rows="4" value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the text here" />
          </label>
        )}
        <button className="secondary" disabled={!file && (title.trim().length < 2 || text.trim().length < 1)}>Add document</button>
      </form>
      {error && <p className="error">{error}</p>}

      {items.length === 0 ? <p className="muted">No documents yet.</p> : (
        <table>
          <thead><tr><th>Title</th><th>Kind</th><th>From</th><th>Words</th><th></th></tr></thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id}>
                <td>{d.title}</td>
                <td className="small">{KINDS[d.kind] || d.kind}</td>
                <td className="small">{d.source}</td>
                <td>{d.words}</td>
                <td><button className="link" onClick={() => run(() => companyDocumentsApi.remove(d.id))}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

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
