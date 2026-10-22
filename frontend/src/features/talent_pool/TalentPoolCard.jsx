import { useEffect, useState } from "react";
import { POOL_STATUS, talentPoolApi } from "./talentPoolApi.js";

// The "Talent pool" card on the assessment report, under the decision: keep this candidate for future jobs.
// Someone who unsubscribed is added back only after the interviewer confirms they asked for it. Not printed.
const day = (value) => new Date(value).toLocaleDateString([], { dateStyle: "medium" });

export default function TalentPoolCard({ candidateId }) {
  const [entry, setEntry] = useState(null);
  const [status, setStatus] = useState("strong");
  const [note, setNote] = useState("");
  const [message, setMessage] = useState(null);
  const [asked, setAsked] = useState(false);         // "The person asked to be contacted again" (for Add back)

  useEffect(() => {
    // → GET /api/candidates/{id}/talent-pool
    talentPoolApi.entry(candidateId).then((found) => {
      setEntry(found);
      if (found.in_pool) { setStatus(found.status); setNote(found.note); }
    }).catch((e) => setMessage({ ok: false, text: e.message }));
  }, [candidateId]);

  // → PUT (add or save) or DELETE /api/candidates/{id}/talent-pool
  async function save(remove = false, addBack = false) {
    setMessage(null);
    try {
      setEntry(remove ? await talentPoolApi.remove(candidateId) : await talentPoolApi.add(candidateId, status, note, addBack));
      setMessage({ ok: true, text: remove ? "Removed from the talent pool." : addBack ? "Added back to the talent pool."
        : "Saved in the talent pool." });
    } catch (e) { setMessage({ ok: false, text: e.message }); }
  }

  if (!entry) return null;
  return (
    <div className="card no-print">
      <h3>Talent pool</h3>
      <p className="muted small">Keep this candidate for future jobs. When a new job fits, they appear on the Talent Pool
        page and can be invited by email.</p>
      {entry.unsubscribed ? (
        <>
          <p className="small">This person unsubscribed: they asked not to be contacted about future openings.</p>
          <label className="small"><input type="checkbox" checked={asked} onChange={(e) => setAsked(e.target.checked)} />
            {" "}The person asked to be contacted again</label>
          <button type="button" onClick={() => save(false, true)} disabled={!asked}>Add back</button>
        </>
      ) : (
        <>
          <div className="pool-form">
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {Object.entries(POOL_STATUS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
            <input maxLength="500" placeholder="Note (optional), e.g. strong in SQL" value={note}
                   onChange={(e) => setNote(e.target.value)} />
            <button type="button" onClick={() => save()}>{entry.in_pool ? "Save" : "Add to talent pool"}</button>
            {entry.in_pool && <button type="button" className="secondary" onClick={() => save(true)}>Remove</button>}
          </div>
          {entry.in_pool && <p className="small muted">In the pool since {day(entry.added_at)} · until {day(entry.keep_until)}</p>}
        </>
      )}
      {message && <p className={message.ok ? "ok small" : "error small"}>{message.text}</p>}
    </div>
  );
}
