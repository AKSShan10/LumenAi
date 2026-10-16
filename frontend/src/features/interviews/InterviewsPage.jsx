import { useEffect, useState } from "react";
import { jobsApi } from "../jobs/jobsApi.js";
import { interviewsApi, invitationStatus } from "./interviewsApi.js";
import DataTable from "../../shared/utils/DataTable.jsx";
import TranscriptView from "../transcripts/TranscriptView.jsx";

// The interviews of a job: start the video call, join it again, or end it. Interviews are scheduled from the
// Shortlist on the Candidates page. The call opens in its own tab (InterviewRoomPage.jsx, /interview-room/<id>).
// The candidate joins with the private link from the invitation, and only while the call is live.
const CALL = {
  scheduled: { label: "Not started", badge: "" },
  live: { label: "Live", badge: "done" },
  ended: { label: "Ended", badge: "draft" },
};
const LOOK_AGAIN_MS = 10000;      // the list refreshes itself, so "Live" and the join times appear
// Turns a date text from the backend into a short local date and time (empty if no date)
const when = (text) => (text ? new Date(text).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");

// The Interviews page: the interviews of a job, with Start, End and Copy link buttons; opened from App
export default function InterviewsPage() {
  const [jobs, setJobs] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState(null);
  const [error, setError] = useState("");
  const [shownId, setShownId] = useState(null);     // the interview whose transcript is open

  useEffect(() => {
    jobsApi.list().then((list) => {
      const approved = list.filter((j) => j.status === "approved");
      setJobs(approved);
      if (approved[0]) setJobId(approved[0].id);
    }).catch((e) => setError(e.message));
  }, []);

  // Loads the interviews of the job from GET /api/sessions?job_id=...
  function load(id = jobId) {
    if (!id) return Promise.resolve();
    // → GET /api/sessions?job_id=...: the interviews of this job
    return interviewsApi.list(id).then(setSessions).catch((e) => setError(e.message));
  }
  useEffect(() => {
    load(jobId);
    const timer = setInterval(() => { if (!document.hidden) load(jobId); }, LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [jobId]);                                       // eslint-disable-line react-hooks/exhaustive-deps

  // The call opens in a new tab. window.open (inside the click) gives that tab a copy of this tab's login.
  function openCall(row) {
    setError(""); setNote(null);
    // → opens the call page in a new tab; the new tab starts the LiveKit call
    const tab = window.open(`/interview-room/${row.id}`, "_blank");
    if (!tab) { setError("The browser blocked the new tab. Allow pop-ups for this site and click again."); return; }
    setNote({ ok: true, message: `The interview with ${row.candidate_name || "the candidate"} opened in a new tab.` });
    setTimeout(() => load(), 3000);                  // the new tab starts the call: show "Live" soon
  }

  // On End interview: calls interviewsApi.end for this row, shows the answer and reloads the list
  async function end(row) {
    setBusy(`end-${row.id}`); setError("");
    try {
      setNote({ ok: true, message: (await interviewsApi.end(row.id)).message });
      await load();
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // On Copy candidate link: copies the join link; if copying fails, shows the link instead
  function copyLink(row) {
    navigator.clipboard?.writeText(row.join_link)
      .then(() => setNote({ ok: true, message: `The link of ${row.candidate_name || "the candidate"} was copied.` }))
      .catch(() => setNote({ ok: true, message: row.join_link }));
  }

  const shown = sessions.find((s) => s.id === shownId);

  if (!jobs) return <div className="card"><p className="muted">Loading...</p></div>;
  if (jobs.length === 0) return <div className="card"><p className="muted">No approved job yet.</p></div>;

  return (
    <>
      <div className="card">
        <div className="row-between">
          <h3>Interviews</h3>
          <label htmlFor="interviews-job" className="inline">Job
            <select id="interviews-job" value={jobId || ""} onChange={(e) => setJobId(Number(e.target.value))}>
              {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
            </select>
          </label>
        </div>
        <p className="muted small">Schedule interviews from the Shortlist on the Candidates page. Start the call here at the
          interview time; the candidate can join only while it is live.</p>
        {note && <p className={note.ok ? "ok small" : "error small"}>{note.message}</p>}
        {error && <p className="error">{error}</p>}

        <DataTable rows={sessions} empty="No interviews for this job yet." columns={[
          { key: "who", title: "Candidate", render: (row) => <b>{row.candidate_name || "(name not given)"}</b> },
          { key: "time", title: "Time", render: (row) => <>{when(row.scheduled_at)}<div className="muted small">{row.duration_minutes} minutes</div></> },
          { key: "invite", title: "Invitation", className: "small", render: (row) => {
            const status = invitationStatus(row.invitation_status);
            return <span className={`badge ${status.badge}`}>{status.label}</span>;
          } },
          { key: "call", title: "Call", className: "small", render: (row) => (
            <>
              <span className={`badge ${CALL[row.status]?.badge || ""}`}>{CALL[row.status]?.label || row.status}</span>
              {row.started_at && <div className="muted">started {when(row.started_at)}</div>}
              {row.candidate_joined_at && <div className="muted">candidate joined {when(row.candidate_joined_at)}</div>}
              {row.ended_at && <div className="muted">ended {when(row.ended_at)}</div>}
            </>
          ) },
          { key: "actions", title: "", className: "small actions", render: (row) => (
            <>
              {row.status !== "ended" && (
                <button className="link" onClick={() => openCall(row)}>
                  {row.status === "live" ? "Join again (new tab)" : "Start interview (new tab)"}</button>
              )}
              {row.status === "live" && (
                <button className="link" onClick={() => end(row)} disabled={busy !== ""}>End interview</button>
              )}
              {row.status !== "ended" && <button className="link" onClick={() => copyLink(row)}>Copy candidate link</button>}
              {row.started_at && <button className="link" onClick={() => setShownId(row.id)}>Transcript</button>}
            </>
          ) },
        ]} />
      </div>
      {shown && <TranscriptView key={shown.id} row={shown} onClose={() => setShownId(null)} />}
    </>
  );
}
