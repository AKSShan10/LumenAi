import { useEffect, useState } from "react";
import { screeningApi } from "../screening/screeningApi.js";
import DataTable from "../../shared/utils/DataTable.jsx";
import InvitationEditor from "./InvitationEditor.jsx";
import ScheduleAllForm from "./ScheduleAllForm.jsx";

// "Schedule interviews" on the Interviews page: the shortlisted candidates of one job who have no interview yet.
// The same editors as on the Shortlist of the Candidates page (InvitationEditor for one person, ScheduleAllForm for
// everyone), so step 3 of the process (shortlist → schedule → invitation) can be finished here.
// sessions = the job's interviews from the Interviews page; onScheduled() reloads them.
export default function ScheduleCard({ jobId, sessions, onScheduled }) {
  const [shortlist, setShortlist] = useState([]);
  const [open, setOpen] = useState(null);            // the candidate whose invitation editor is open
  const [all, setAll] = useState(false);             // the "Schedule all" form is open
  const [note, setNote] = useState(null);
  const [error, setError] = useState("");

  // → GET /api/jobs/{id}/shortlist when the job changes
  useEffect(() => {
    setShortlist([]); setOpen(null); setAll(false); setNote(null); setError("");
    screeningApi.shortlist(jobId).then(setShortlist).catch((e) => setError(e.message));
  }, [jobId]);

  const scheduled = new Set(sessions.map((s) => s.candidate_id));
  // the open row stays until it is closed, so its invitation can be checked and sent right after scheduling
  const waiting = shortlist.filter((row) => !scheduled.has(row.candidate_id) || row.candidate_id === open);
  const unscheduled = shortlist.filter((row) => !scheduled.has(row.candidate_id)).length;
  if (!error && !note && shortlist.length > 0 && waiting.length === 0) return null;    // everyone has an interview

  // After "Schedule all": the message, plus who could not be scheduled and why
  function scheduledAll(answer) {
    setAll(false);
    const problems = answer.problems.map((p) => `${p.full_name || "Candidate " + p.candidate_id}: ${p.reason}`).join(" ");
    setNote({ ok: answer.problems.length === 0, message: answer.message + (problems ? ` ${problems}` : "") });
    onScheduled();
  }

  return (
    <div className="card">
      <div className="row-between">
        <h3>Schedule interviews <small className="muted">(shortlisted, not scheduled yet)</small></h3>
        {unscheduled > 1 && (
          <button type="button" className="secondary" onClick={() => setAll(!all)}>Schedule all ({unscheduled})</button>
        )}
      </div>
      {error && <p className="error small">{error}</p>}
      {note && <p className={note.ok ? "ok small" : "error small"}>{note.message}</p>}
      {!error && shortlist.length === 0 && (
        <p className="muted small">Nobody is on the shortlist of this job yet. Shortlist candidates on the Candidates page
          (Step 3 Shortlist), then schedule them here.</p>
      )}
      {all && <ScheduleAllForm jobId={jobId} onDone={scheduledAll} onClose={() => setAll(false)} />}
      {waiting.length > 0 && (
        <DataTable rows={waiting} rowKey={(row) => row.candidate_id}
                   expanded={(row) => (open === row.candidate_id
                     ? <InvitationEditor key={row.candidate_id} candidate={row} session={null} onChange={onScheduled} />
                     : null)}
                   columns={[
          { key: "name", title: "Candidate", render: (row) => (
            <><b>{row.full_name || `(name not given, candidate ${row.number})`}</b>
              {row.email && <div className="muted small">{row.email}</div>}</>) },
          { key: "score", title: "Final score", render: (row) => <b>{row.weighted_score ?? "-"}</b> },
          { key: "action", title: "", render: (row) => (
            <button type="button" className="secondary" onClick={() => setOpen(open === row.candidate_id ? null : row.candidate_id)}>
              {open === row.candidate_id ? "Close" : "Schedule interview"}</button>) },
        ]} />
      )}
    </div>
  );
}
