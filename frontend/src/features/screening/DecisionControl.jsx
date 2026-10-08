import { useState } from "react";
import { screeningApi } from "./screeningApi.js";

// Human control: the interviewer includes or excludes a candidate, with an optional note, or undoes the decision.
// The backend continues the candidate's paused screening workflow (the hr_review step) with this answer.
// The system result is kept, so the page can always show both.
export default function DecisionControl({ candidateId, final, decided, onDone }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send(decision) {
    setBusy(true); setError("");
    try {
      const answer = await screeningApi.decide(candidateId, decision, note.trim());
      setOpen(false); setNote("");
      onDone(answer);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  if (!open) {
    return <button className="link" onClick={() => setOpen(true)}>Change</button>;
  }
  return (
    <div className="decision">
      <input value={note} onChange={(e) => setNote(e.target.value)} maxLength="500" placeholder="Note (optional)" />
      <div>
        {final !== "included" && <button type="button" onClick={() => send("included")} disabled={busy}>Include</button>}
        {final !== "excluded" && <button type="button" className="danger" onClick={() => send("excluded")} disabled={busy}>Exclude</button>}
        {decided && <button type="button" className="secondary" onClick={() => send(null)} disabled={busy}
                            title="Back to the system result">Undo my decision</button>}
        <button type="button" className="link" onClick={() => setOpen(false)} disabled={busy}>Cancel</button>
      </div>
      {error && <p className="error small">{error}</p>}
    </div>
  );
}
