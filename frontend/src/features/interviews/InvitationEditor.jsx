import { useState } from "react";
import { interviewsApi, invitationStatus } from "./interviewsApi.js";

// The interview of one shortlisted candidate: schedule it, then check and send the invitation.
// Draft first: the AI writes the email, code puts in the private join link and the calendar invite, and nothing
// is sent until the interviewer clicks "Send email".
const LENGTHS = [30, 45, 60, 90];
const ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";     // the interviewer's time zone

// "2026-10-20T10:00" (the browser's datetime-local box) for a Date
function forInput(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function tomorrowAtTen() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(10, 0, 0, 0);
  return forInput(date);
}

export default function InvitationEditor({ candidate, session, onChange }) {
  const [when, setWhen] = useState(session ? forInput(new Date(session.scheduled_at)) : tomorrowAtTen());
  const [minutes, setMinutes] = useState(session ? session.duration_minutes : 45);
  const [changing, setChanging] = useState(false);    // the "Change time" form is open
  const [to, setTo] = useState(session ? session.invite_email : candidate.email || "");
  const [subject, setSubject] = useState(session ? session.invitation_subject : "");
  const [body, setBody] = useState(session ? session.invitation_body : "");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState(session?.message ? { ok: !session.invitation_status.startsWith("failed"), message: session.message } : null);
  const [error, setError] = useState("");

  function show(saved) {                              // the backend's answer: the interview as it is now
    setTo(saved.invite_email); setSubject(saved.invitation_subject); setBody(saved.invitation_body);
    setWhen(forInput(new Date(saved.scheduled_at))); setMinutes(saved.duration_minutes); setChanging(false);
    setNote(saved.message ? { ok: !saved.invitation_status.startsWith("failed"), message: saved.message } : null);
    onChange(saved);
  }

  async function run(name, call) {
    setBusy(name); setError(""); setNote(null);
    try { show(await call()); } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  const timeBody = () => ({ scheduled_at: new Date(when).toISOString(), duration_minutes: Number(minutes), time_zone: ZONE });

  function timeForm(label, onSubmit) {
    return (
      <form className="weights" onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
        <label htmlFor={`when-${candidate.candidate_id}`} className="inline">Date and time
          <input id={`when-${candidate.candidate_id}`} type="datetime-local" value={when} required
                 onChange={(e) => setWhen(e.target.value)} />
        </label>
        <label htmlFor={`length-${candidate.candidate_id}`} className="inline">Length
          <select id={`length-${candidate.candidate_id}`} value={minutes} onChange={(e) => setMinutes(e.target.value)}>
            {LENGTHS.map((m) => <option key={m} value={m}>{m} minutes</option>)}
          </select>
        </label>
        <span className="muted small">{ZONE}</span>
        <button type="submit" disabled={busy !== ""}>{busy === "time" ? "Writing the email..." : label}</button>
      </form>
    );
  }

  if (!session) {
    return (
      <div className="invitation">
        <b>Schedule an interview with {candidate.full_name || "this candidate"}</b>
        <p className="muted small">The AI writes the invitation; you check it before anything is sent. The email gets a
          personal join link and a calendar invite.</p>
        {timeForm("Schedule and write the invitation", () => run("time", () => interviewsApi.schedule(candidate.candidate_id, timeBody())))}
        {error && <p className="error small">{error}</p>}
      </div>
    );
  }

  const status = invitationStatus(session.invitation_status);
  return (
    <div className="invitation">
      <div className="row-between">
        <b>Interview on {new Date(session.scheduled_at).toLocaleString()} ({session.duration_minutes} minutes)</b>
        <span className={`badge ${status.badge}`}>{status.label}</span>
      </div>
      <p className="small">Join link (personal to this candidate):{" "}
        <a href={session.join_link} target="_blank" rel="noreferrer">{session.join_link}</a>{" "}
        <button type="button" className="link" onClick={() => navigator.clipboard?.writeText(session.join_link).catch(() => {})}>Copy</button>
      </p>
      {session.invitation_status.startsWith("failed") && <p className="error small">{session.invitation_status}</p>}
      {changing ? timeForm("Save the new time", () => run("time", () => interviewsApi.changeTime(session.id, timeBody())))
        : <div><button type="button" className="link" onClick={() => setChanging(true)}>Change time</button></div>}

      <form className="invitation-form" onSubmit={(e) => { e.preventDefault(); run("send", () => interviewsApi.send(session.id, to, subject, body)); }}>
        <label htmlFor={`to-${session.id}`}>To</label>
        <input id={`to-${session.id}`} type="email" value={to} onChange={(e) => setTo(e.target.value)} placeholder="candidate@example.com" />
        <label htmlFor={`subject-${session.id}`}>Subject</label>
        <input id={`subject-${session.id}`} value={subject} maxLength="200" required onChange={(e) => setSubject(e.target.value)} />
        <label htmlFor={`body-${session.id}`}>Email</label>
        <textarea id={`body-${session.id}`} rows="14" value={body} maxLength="8000" required onChange={(e) => setBody(e.target.value)} />
        <p className="muted small">A calendar invite (invite.ics) is attached when it is sent. If the join link is removed
          from the text, it is put back before sending.</p>
        <div className="row">
          <button type="submit" disabled={busy !== ""}>
            {busy === "send" ? "Sending..." : session.invitation_status === "sent" ? "Send again" : "Send email"}</button>
          <button type="button" className="secondary" disabled={busy !== ""}
                  onClick={() => run("again", () => interviewsApi.writeAgain(session.id))}>
            {busy === "again" ? "Writing..." : "Write again with AI"}</button>
        </div>
      </form>
      {note && <p className={note.ok ? "ok small" : "error small"}>{note.message}</p>}
      {error && <p className="error small">{error}</p>}
    </div>
  );
}
