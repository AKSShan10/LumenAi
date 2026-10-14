import { useState } from "react";
import { interviewsApi } from "./interviewsApi.js";
import { forInput, ZONE } from "./InvitationEditor.jsx";

// "Schedule all": the whole shortlist at once, in three steps.
//   1. Times: settings (first day, start, length, working hours, lunch or no lunch) → "Suggest times" fills a time for
//      everyone inside working hours (POST /api/sessions/plan; nothing is saved). Any time can be changed.
//   2. The invitation: "Write the invitation" → the AI writes ONE email with {candidate_name}, {date} ... placeholders
//      (POST /api/sessions/template). You check and edit it.
//   3. "Save and schedule": every candidate gets an interview with that email filled in for them, saved as a draft
//      (POST /api/sessions/bulk, no AI call per candidate). Nothing is sent: "Send all invitations" does that after a
//      yes / no question, and each candidate's own "Invitation" button still opens their draft to change or send alone.
const LENGTHS = [30, 45, 60, 90];
const SETTINGS_KEY = "lumenai.scheduleAll";       // the settings are remembered in this browser
const DEFAULTS = { minutes: 45, dayStart: "08:00", dayEnd: "17:00", lunchStart: "12:30", lunchEnd: "13:30", skipLunch: false };
// The placeholders code fills in for each candidate, with what they become
const PLACEHOLDERS = [["{candidate_name}", "the name"], ["{date}", "the date"], ["{time}", "the time"],
                      ["{length_minutes}", "the length"], ["{interviewer_name}", "your name"], ["{join_link}", "the private link"]];

// The saved settings, or the defaults (the browser may block storage, so try/catch)
function savedSettings() {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") }; } catch { return DEFAULTS; }
}

// The next working day (Monday to Friday) as "2026-10-19", for the date box
function nextWorkingDay() {
  const day = new Date();
  do { day.setDate(day.getDate() + 1); } while (day.getDay() === 0 || day.getDay() === 6);   // 0 = Sunday, 6 = Saturday
  return forInput(day).slice(0, 10);
}

// The time of a row as the page shows it, e.g. "Mon 19 Oct, 8:00 AM"
const shown = (iso) => new Date(iso).toLocaleString([], { weekday: "short", day: "numeric", month: "short",
                                                          hour: "numeric", minute: "2-digit" });

// How the email looks for one candidate (a preview; the backend fills in the real values and the real link)
function preview(text, row, minutes) {
  const when = new Date(row.when);
  return text.replaceAll("{candidate_name}", row.full_name)
    .replaceAll("{date}", when.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }))
    .replaceAll("{time}", `${when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} (${ZONE})`)
    .replaceAll("{length_minutes}", String(minutes))
    .replaceAll("{interviewer_name}", "(your name)")
    .replaceAll("{join_link}", "(the candidate's private link)");
}

export default function ScheduleAllForm({ jobId, onDone, onClose }) {
  const [settings, setSettings] = useState(savedSettings);
  const [firstDay, setFirstDay] = useState(nextWorkingDay);
  const [startAt, setStartAt] = useState("");       // "" = start after your last interview
  const [rows, setRows] = useState(null);           // [{candidate_id, full_name, weighted_score, when, session_id}]
  const [invitation, setInvitation] = useState(null);   // the ONE email being checked: {subject, body, message}
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // Changes one setting and remembers it for next time
  function change(key, value) {
    const next = { ...settings, [key]: value };
    setSettings(next);
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(next)); } catch { /* storage blocked: only not remembered */ }
  }

  // Step 1, "Suggest times": asks the backend for a time for every shortlisted candidate
  async function suggest(event) {
    event.preventDefault();
    setBusy("plan"); setError("");
    try {
      const plan = await interviewsApi.plan({
        job_id: jobId, first_day: firstDay, duration_minutes: Number(settings.minutes), time_zone: ZONE,
        day_start: settings.dayStart, day_end: settings.dayEnd, lunch_start: settings.lunchStart, lunch_end: settings.lunchEnd,
        skip_lunch: settings.skipLunch, start_at: startAt || null,
      });
      setRows(plan.map((row) => ({ ...row, when: row.scheduled_at ? forInput(new Date(row.scheduled_at)) : "" })));
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // The candidates that will be scheduled now: no interview yet, and a time is filled in
  const toSchedule = (rows || []).filter((row) => !row.session_id && row.when);

  // Step 2, "Write the invitation": the AI writes ONE email for everyone, to check and edit here
  async function writeInvitation() {
    setBusy("write"); setError("");
    try { setInvitation(await interviewsApi.template({ job_id: jobId, duration_minutes: Number(settings.minutes) })); }
    catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // Step 3, "Save and schedule": every candidate gets an interview with the checked email filled in; nothing is sent
  async function scheduleAll() {
    setBusy("schedule"); setError("");
    try {
      const answer = await interviewsApi.scheduleMany(toSchedule.map((row) => ({
        candidate_id: row.candidate_id, scheduled_at: new Date(row.when).toISOString(),
        duration_minutes: Number(settings.minutes), time_zone: ZONE,
      })), { subject: invitation.subject, body: invitation.body });
      onDone(answer);
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // Changes the time of one row in the table
  const setWhen = (id, when) => setRows((list) => list.map((row) => (row.candidate_id === id ? { ...row, when } : row)));

  return (
    <div className="schedule-all">
      <div className="row-between">
        <b>Schedule all shortlisted candidates</b>
        <button type="button" className="link" onClick={onClose}>Close</button>
      </div>
      <p className="muted small">① Suggest the times, ② check one invitation for everyone, ③ save and schedule. Times stay
        inside working hours and skip Saturday and Sunday (and the lunch break, unless you untick it). They start after
        your last scheduled interview, or at "Start at" on the first day. Times are in {ZONE}.</p>

      <form className="schedule-settings" onSubmit={suggest}>
        <label className="inline">First day
          <input type="date" value={firstDay} required onChange={(e) => setFirstDay(e.target.value)} />
        </label>
        <label className="inline" title="Empty: the first interview starts after your last scheduled interview">Start at
          <input type="time" value={startAt} onChange={(e) => setStartAt(e.target.value)} />
          {startAt
            ? <button type="button" className="link small" onClick={() => setStartAt("")}>clear</button>
            : <span className="muted small">after your last interview</span>}
        </label>
        <label className="inline">Length
          <select value={settings.minutes} onChange={(e) => change("minutes", e.target.value)}>
            {LENGTHS.map((m) => <option key={m} value={m}>{m} minutes</option>)}
          </select>
        </label>
        <label className="inline">Working hours
          <input type="time" value={settings.dayStart} required onChange={(e) => change("dayStart", e.target.value)} />
          to <input type="time" value={settings.dayEnd} required onChange={(e) => change("dayEnd", e.target.value)} />
        </label>
        <label className="inline">Lunch
          <input type="time" value={settings.lunchStart} required disabled={settings.skipLunch}
                 onChange={(e) => change("lunchStart", e.target.value)} />
          to <input type="time" value={settings.lunchEnd} required disabled={settings.skipLunch}
                    onChange={(e) => change("lunchEnd", e.target.value)} />
        </label>
        <label className="inline check">
          <input type="checkbox" checked={settings.skipLunch} onChange={(e) => change("skipLunch", e.target.checked)} />
          No lunch break
        </label>
        <button type="submit" className="secondary" disabled={busy !== ""}>
          {busy === "plan" ? "Suggesting..." : rows ? "Suggest again" : "① Suggest times"}</button>
      </form>
      {error && <p className="error">{error}</p>}

      {rows && (
        <table>
          <thead><tr><th>#</th><th>Name</th><th>Final score</th><th>Interview time</th></tr></thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.candidate_id}>
                <td>{index + 1}</td>
                <td><b>{row.full_name}</b></td>
                <td>{row.weighted_score ?? "-"}</td>
                <td>{row.session_id
                  ? <span className="muted">{shown(row.scheduled_at)} <span className="badge">already scheduled</span></span>
                  : <input type="datetime-local" value={row.when} aria-label={`Interview time for ${row.full_name}`}
                           onChange={(e) => setWhen(row.candidate_id, e.target.value)} />}
                  {!row.session_id && !row.when && <div className="warn small">No free time found: type one.</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {rows && toSchedule.length > 0 && !invitation && (
        <div className="schedule-actions">
          <button type="button" onClick={writeInvitation} disabled={busy !== ""}>
            {busy === "write" ? "Writing the invitation..." : "② Write the invitation"}</button>
          <span className="muted small">The AI writes one email for everyone; you check it before anything is saved.</span>
        </div>
      )}

      {invitation && (
        <div className="template-box">
          <div className="row-between">
            <b>② Check the invitation</b>
            <button type="button" className="link" onClick={writeInvitation} disabled={busy !== ""}>
              {busy === "write" ? "Writing..." : "Write again with AI"}</button>
          </div>
          {invitation.message && <p className="muted small">{invitation.message}</p>}
          <p className="small">These are filled in for each candidate:{" "}
            {PLACEHOLDERS.map(([code, meaning]) => <span key={code} className="placeholder" title={meaning}>{code}</span>)}
          </p>
          <label>Subject <small className="muted">(the date and time are added for each candidate)</small>
            <input value={invitation.subject} maxLength="200"
                   onChange={(e) => setInvitation({ ...invitation, subject: e.target.value })} />
          </label>
          <label>Email
            <textarea rows="12" value={invitation.body} onChange={(e) => setInvitation({ ...invitation, body: e.target.value })} />
          </label>
          {toSchedule[0] && (
            <details className="template-preview">
              <summary>Preview for {toSchedule[0].full_name}</summary>
              <pre>{preview(invitation.body, toSchedule[0], settings.minutes)}</pre>
            </details>
          )}
          <div className="schedule-actions">
            <button type="button" onClick={scheduleAll} disabled={busy !== "" || toSchedule.length === 0}>
              {busy === "schedule" ? "Saving..." : `③ Save and schedule (${toSchedule.length})`}</button>
            <span className="muted small">Each candidate gets this email with their own name, time and private link, saved
              as a draft. Nothing is sent until you click Send all invitations (or Send on one candidate).</span>
          </div>
        </div>
      )}
    </div>
  );
}
