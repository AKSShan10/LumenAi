import { useEffect, useRef, useState } from "react";
import { screeningApi } from "./screeningApi.js";
import DecisionControl from "./DecisionControl.jsx";
import DataTable from "../../shared/utils/DataTable.jsx";
import { filterIncluded } from "./includedFilter.js";
import InvitationEditor from "../interviews/InvitationEditor.jsx";
import { interviewsApi, invitationStatus } from "../interviews/interviewsApi.js";

// Met / Partially met / Unmet of one requirement (old results only have met: true / false)
const STATUS = {
  met: { label: "Met", badge: "done" },
  partial: { label: "Partially met", badge: "draft" },
  unmet: { label: "Unmet", badge: "failed" },
  unchecked: { label: "not checked", badge: "" },
};
// The Met / Partial / Unmet status of a requirement; old results only have met true or false
const statusOf = (m) => m.status || (m.met === true ? "met" : m.met === false ? "unmet" : "unchecked");

const SECTIONS = [["skills", "Skills"], ["experience", "Experience"], ["qualifications", "Qualifications"]];
const LOOK_AGAIN_MS = 3000;       // while the backend screens, the progress is fetched every 3 seconds
const SHOW_ALL = { mode: "all", value: "" };
// Dates from the database may come without a time zone; they are UTC.
const asUtc = (text) => new Date(/Z|[+-]\d\d:\d\d$/.test(text) ? text : text + "Z");

// The screening of the chosen job, under the candidate list on the Candidates page.
// The backend screens every new CV by itself (LangGraph workflow, app/graphs/cv_screening_graph.py), so there is no
// "Screen" button. While it works, a progress bar shows "Screening 3 of 7 CVs"; at the end a message says what came out.
// CVs that wait, or that need a look, are shown in the candidate list.
// Two groups: Included and Excluded, each sorted by the final (weighted) score. The interviewer can move a candidate
// from one group to the other (Change); the system result stays visible next to the person's decision.
// The Shortlist: included candidates the interviewer chose (with the Top K / minimum score filter, or one by one).
// It is saved in the database; the interview invitation starts from it.
export default function ScreeningCard({ jobId, candidates, onScreened }) {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(null);           // the candidate whose details are shown
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [weights, setWeights] = useState(null);     // the job's weights as saved
  const [draft, setDraft] = useState(null);         // the weights being typed
  const screenedCount = useRef(0);
  const [progress, setProgress] = useState(null);  // the latest screening run: {running, total, done, message}
  const wasRunning = useRef(false);
  const [filter, setFilter] = useState(SHOW_ALL);    // the filter used on the Included list
  const [topK, setTopK] = useState("");             // what is typed in the Top K box
  const [minScore, setMinScore] = useState("");     // what is typed in the minimum score box
  const [shortlist, setShortlist] = useState([]);   // the saved shortlist of the job
  const [sessions, setSessions] = useState([]);     // the interviews of the job (one per shortlisted candidate)
  const [inviting, setInviting] = useState(null);   // the shortlisted candidate whose interview editor is open

  // Loads the screening results, the shortlist and the interviews of the job together
  function load() {
    return Promise.all([screeningApi.results(jobId), screeningApi.shortlist(jobId), interviewsApi.list(jobId)])
      .then(([list, chosen, interviews]) => {
      setRows(list);
      setShortlist(chosen);
      setSessions(interviews);
      const screened = list.filter((r) => r.result !== null && !r.waiting).length;
      if (screened !== screenedCount.current) {      // new results: the candidate list shows new states too
        if (screenedCount.current !== 0 || screened !== 0) onScreened();
        screenedCount.current = screened;
      }
    });
  }

  useEffect(() => {
    if (!jobId) return;
    load().catch((e) => setError(e.message));
  }, [jobId, candidates]);                           // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!jobId) return;
    screenedCount.current = 0;
    screeningApi.weights(jobId).then((w) => { setWeights(w); setDraft(w); }).catch((e) => setError(e.message));
  }, [jobId]);

  // The progress of the backend's screening: "started", "3 of 7", then "finished: 4 included, 3 excluded".
  function checkProgress() {
    return screeningApi.status(jobId).then((run) => {
      if (run.running && !wasRunning.current) setNote({ ok: true, message: `Screening started for ${run.total} CV(s).` });
      if (!run.running && wasRunning.current && run.message) {
        setNote({ ok: true, message: run.message });  // finished
        load().catch(() => {});
      }
      wasRunning.current = run.running;
      setProgress(run);
    });
  }

  useEffect(() => {
    wasRunning.current = false; setProgress(null); setNote(null);
    setFilter(SHOW_ALL); setTopK(""); setMinScore("");      // another job: show its whole Included list
    setRows([]); setShortlist([]); setSessions([]); setInviting(null);
  }, [jobId]);

  useEffect(() => {                                  // new CVs (fetch, upload) start a run by itself: notice it
    if (!jobId) return;
    checkProgress().catch(() => {});
  }, [jobId, candidates]);                           // eslint-disable-line react-hooks/exhaustive-deps

  const running = !!progress?.running;
  useEffect(() => {                                  // while it runs: progress and the new rows every few seconds
    if (!jobId || !running) return undefined;
    const timer = setInterval(() => {
      if (document.hidden) return;
      checkProgress().catch(() => {});
      load().catch(() => {});
    }, LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [jobId, running]);                              // eslint-disable-line react-hooks/exhaustive-deps

  // New weights: the backend recalculates every final score with plain maths. The AI is not asked again.
  async function saveWeights(event) {
    event.preventDefault();
    setError(""); setNote(null); setBusy("weights");
    try {
      const saved = await screeningApi.saveWeights(jobId, { skills: draft.skills, experience: draft.experience, qualifications: draft.qualifications });
      setWeights(saved); setDraft(saved);
      setNote({ ok: true, message: `Weights saved. ${saved.updated} final score(s) recalculated.` });
      await load();
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // Every CV of the job again: the system decides again (decisions made by a person are cleared).
  async function screenAllAgain() {
    setError(""); setNote(null); setBusy("again");
    try {
      const answer = await screeningApi.screen(jobId, true);
      setNote(answer);
      wasRunning.current = true;                     // the "started" message is shown already
      await checkProgress();
      await load();
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // On Screen again: screens one CV again with screeningApi.screenOne, then reloads
  async function screenOne(row) {
    setError(""); setBusy(`one-${row.candidate_id}`);
    setNote({ ok: true, message: `Screening ${row.full_name || "this candidate"}...` });
    try { setNote(await screeningApi.screenOne(row.candidate_id)); await load(); onScreened(); }
    catch (e) { setError(e.message); setNote(null); } finally { setBusy(""); }
  }

  // The shortlist. Only included candidates can be put on it (the backend checks this too).
  async function addToShortlist(ids, rule, value) {
    setError(""); setNote(null); setBusy("shortlist");
    try { setNote(await screeningApi.addToShortlist(jobId, ids, rule, value)); await load(); }
    catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // On Remove: takes the candidate off the shortlist with screeningApi.removeFromShortlist
  async function removeFromShortlist(row) {
    setError(""); setNote(null); setBusy("shortlist");
    try {
      await screeningApi.removeFromShortlist(row.candidate_id);
      setNote({ ok: true, message: `${row.full_name || "The candidate"} was taken off the shortlist.` });
      await load();
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // After a person's decision: shows the answer and reloads the results and the candidate list
  function decided(answer) {
    setNote(answer);
    load().then(onScreened).catch((e) => setError(e.message));
  }

  if (!jobId) return null;
  // Sorts rows by final score, highest first; rows without a score go last
  const byScore = (a, b) => (b.weighted_score ?? -1) - (a.weighted_score ?? -1);
  // The rows of one group (included or excluded), sorted by final score
  const group = (name) => rows.filter((r) => r.final === name).sort(byScore);
  const included = group("included");
  const excluded = group("excluded");
  const picked = filterIncluded(included, filter);
  const onShortlist = new Set(shortlist.map((row) => row.candidate_id));
  // the candidates the filter shows that are not on the shortlist yet (the "Add these" button)
  const toAdd = filter.mode === "all" || picked.problem ? [] : picked.shown.filter((row) => !onShortlist.has(row.candidate_id));

  // The Top K / minimum score filter bar shown above the Included list
  function filterBar() {
    return (
      <div className="filter-bar">
        <b>Show from Included</b>
        <form onSubmit={(e) => { e.preventDefault(); setFilter({ mode: "top", value: topK }); }}>
          <label htmlFor="filter-top-k" className="inline">Top K
            <input id="filter-top-k" type="number" min="1" step="1" placeholder="5" value={topK}
                   onChange={(e) => setTopK(e.target.value)} />
          </label>
          <button type="submit" className="secondary">Show top</button>
        </form>
        <form onSubmit={(e) => { e.preventDefault(); setFilter({ mode: "min_score", value: minScore }); }}>
          <label htmlFor="filter-min-score" className="inline">Final score at least
            <input id="filter-min-score" type="number" min="0" max="100" step="any" placeholder="70" value={minScore}
                   onChange={(e) => setMinScore(e.target.value)} />
          </label>
          <button type="submit" className="secondary">Show</button>
        </form>
        <button type="button" className="link" onClick={() => setFilter(SHOW_ALL)} disabled={filter.mode === "all"}>
          Show all</button>
      </div>
    );
  }

  // Builds one results table (Included or Excluded) with scores and the row buttons
  function table(list, title, empty, info = null) {
    return (
      <>
        <h4>{title} <small className="muted">({title === "Included" ? included.length : list.length})</small></h4>
        {info}
        <DataTable rows={list} rowKey={(row) => row.candidate_id} empty={empty}
                   expanded={(row) => (open === row.candidate_id ? details(row) : null)} columns={[
          { key: "rank", title: "#", render: (row, index) => index + 1 },
          { key: "name", title: "Name", render: (row) => (
            <>
              <b>{row.full_name || "(name not given)"}</b>
              {row.decision && <div className="small"><span className="badge draft">changed by {row.decided_by || "an interviewer"}</span></div>}
              {onShortlist.has(row.candidate_id) && <div className="small"><span className="badge done">shortlisted</span></div>}
              {row.waiting && <div className="muted small">waiting to be screened again</div>}
            </>
          ) },
          ...SECTIONS.map(([key, label]) => ({
            key, title: <>{label}{weights && <small className="muted"> {weights[key]}%</small>}</>,
            // Section score of this row (skills, experience or qualifications), or "-"
            render: (row) => row.sections[key]?.score ?? "-",
          })),
          { key: "final", title: "Final score", render: (row) => <b>{row.weighted_score ?? "-"}</b> },
          { key: "ats", title: <span title="Share of the job's ATS keywords found in the CV">ATS match</span>,
            // ATS match column: the share of job keywords found in the CV, or "-"
            render: (row) => (row.ats_score != null ? `${row.ats_score}%` : "-") },
          { key: "why", title: "Why", className: "small", render: (row) => (row.decision ? (
            <>
              <div>{row.decision === "included" ? "Included" : "Excluded"} by a person{row.decision_note && `: "${row.decision_note}"`}</div>
              <div className="muted">System: {row.result === "passed" ? "included" : row.result === "excluded" ? "excluded" : "needs a look"}. {row.reason}</div>
            </>
          ) : row.reason) },
          { key: "actions", title: "", className: "small actions", render: (row) => (
            <>
              <button className="link" onClick={() => screeningApi.viewCv(row.candidate_id, row.full_name).catch((e) => setError(e.message))}>
                View CV</button>
              <button className="link" onClick={() => setOpen(open === row.candidate_id ? null : row.candidate_id)}>
                {open === row.candidate_id ? "Hide" : "Details"}</button>
              <DecisionControl candidateId={row.candidate_id} final={row.final} decided={!!row.decision} onDone={decided} />
              {row.final === "included" && !row.waiting && !onShortlist.has(row.candidate_id) && (
                <button className="link" onClick={() => addToShortlist([row.candidate_id], "by_hand")} disabled={busy !== ""}>
                  Shortlist</button>
              )}
              <button className="link" onClick={() => screenOne(row)} disabled={busy !== ""}>
                {busy === `one-${row.candidate_id}` ? "Screening..." : "Screen again"}</button>
            </>
          ) },
        ]} />
      </>
    );
  }

  // the open interview of a candidate (an ended one does not count), or undefined
  const sessionOf = (candidateId) => sessions.find((s) => s.candidate_id === candidateId && s.status !== "ended");

  function savedSession(saved) {                     // the editor scheduled, rewrote or sent: keep the list in step
    setSessions((list) => [...list.filter((s) => s.id !== saved.id), saved]);
  }

  // Builds the Shortlist table, with the interview status and the Schedule interview button
  function shortlistTable() {
    return (
      <>
        <h4>Shortlist <small className="muted">({shortlist.length})</small></h4>
        <p className="muted small">Included candidates chosen for the interview, highest final score first. The interview
          invitation starts from this list. A candidate who is excluded later is taken off it.</p>
        <DataTable rows={shortlist} rowKey={(row) => row.candidate_id}
                   expanded={(row) => (inviting === row.candidate_id
                     ? <InvitationEditor key={sessionOf(row.candidate_id)?.id || "new"} candidate={row}
                                         session={sessionOf(row.candidate_id)} onChange={savedSession} />
                     : null)}
                   empty="Nobody is on the shortlist yet. Filter the Included list (Top K or a minimum score) and add them, or use Shortlist on a row."
                   columns={[
          { key: "rank", title: "#", render: (row, index) => index + 1 },
          { key: "name", title: "Name", render: (row) => (
            <><b>{row.full_name || `(name not given, candidate ${row.number})`}</b>
              {row.email && <div className="muted small">{row.email}</div>}</>
          ) },
          { key: "final", title: "Final score", render: (row) => <b>{row.weighted_score ?? "-"}</b> },
          { key: "rule", title: "Chosen by", className: "small", render: (row) => row.rule },
          { key: "who", title: "Added by", className: "small",
            // Added by column: the name of the interviewer who added the candidate
            render: (row) => <span title={row.added_by}>{row.added_by_name || row.added_by || "-"}</span> },
          { key: "when", title: "Added", className: "small", render: (row) => asUtc(row.added_at).toLocaleString() },
          { key: "interview", title: "Interview", className: "small", render: (row) => {
            const interview = sessionOf(row.candidate_id);
            if (!interview) return <span className="muted">not scheduled</span>;
            const status = invitationStatus(interview.invitation_status);
            return (<>{new Date(interview.scheduled_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
              <div><span className={`badge ${status.badge}`}>{status.label}</span></div></>);
          } },
          { key: "actions", title: "", className: "small actions", render: (row) => (
            <>
              <button className="link" onClick={() => screeningApi.viewCv(row.candidate_id, row.full_name).catch((e) => setError(e.message))}>
                View CV</button>
              <button className="link" onClick={() => setInviting(inviting === row.candidate_id ? null : row.candidate_id)}>
                {inviting === row.candidate_id ? "Close" : sessionOf(row.candidate_id) ? "Invitation" : "Schedule interview"}</button>
              <button className="link" onClick={() => removeFromShortlist(row)} disabled={busy !== ""}>Remove</button>
            </>
          ) },
        ]} />
      </>
    );
  }

  // The details under a row: section scores, each requirement with its evidence, and the ATS match
  function details(row) {
    return (
      <>
        {Object.keys(row.sections).length > 0 && weights && (
          <table>
            <thead><tr><th>Section</th><th>Score</th><th>Weight</th><th>Points</th><th>Why</th><th>Proof from the CV</th></tr></thead>
            <tbody>
              {SECTIONS.map(([key, label]) => {
                const part = row.sections[key] || {};
                return (
                  <tr key={key}>
                    <td>{label}</td>
                    <td>{part.score ?? "-"}</td>
                    <td>{weights[key]}%</td>
                    <td>{part.score != null ? (part.score * weights[key] / 100).toFixed(1) : "-"}</td>
                    <td>{part.reason}</td>
                    <td>{part.proof ? <i>"{part.quote}"</i> : <span className="muted">no proof found in the CV</span>}</td>
                  </tr>
                );
              })}
              <tr><td><b>Final score</b></td><td colSpan="5"><b>{row.weighted_score ?? "-"}</b> of 100</td></tr>
            </tbody>
          </table>
        )}
        {row.matches.length > 0 && (
          <table>
            <thead><tr><th>Requirement</th><th>Kind</th><th>Result</th><th>AI explanation</th><th>Evidence from the CV</th></tr></thead>
            <tbody>
              {row.matches.map((m) => (
                <tr key={m.requirement}>
                  <td>{m.requirement}</td>
                  <td>{m.kind === "must" ? "must-have" : "nice to have"}</td>
                  <td><span className={`badge ${STATUS[statusOf(m)].badge}`}>{STATUS[statusOf(m)].label}</span></td>
                  <td>{m.how}</td>
                  <td>
                    {m.evidence ? <i>"{m.evidence}"</i> : ""}
                    {m.verified === false && <span className="small muted"> (not found in the CV text)</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {row.ats?.total > 0 && (
          <p><b>ATS match {row.ats.score}%</b>: {row.ats.matched.length} of {row.ats.total} job keywords found in the CV.
            {row.ats.missing.length > 0 && <span className="muted"> Missing: {row.ats.missing.join(", ")}.</span>}</p>
        )}
        <p className="muted">Skills the AI read from the CV: {row.skills.join(", ") || "none"}
          {row.education.length > 0 && <> · Education: {row.education.join("; ")}</>}
          {row.matches.length > 0 && <> · About {row.total_years} years of experience</>}</p>
      </>
    );
  }

  return (
    <div className="card">
      <div className="row-between">
        <h3>Screening</h3>
        <button type="button" className="secondary" onClick={screenAllAgain} disabled={busy !== "" || rows.length === 0 || running}
                title="Screen every CV of this job again, for example after the requirements changed. The system decides again; decisions made by a person are cleared.">
          {busy === "again" ? "Starting..." : "Screen all again"}
        </button>
      </div>
      <p className="muted small">New CVs are screened by the backend by itself. The AI reads each CV (email and phone are removed
        first); the code checks every requirement and decides. You can move anyone between Included and Excluded; screening again lets the system decide again. Nobody is deleted.</p>

      {draft && (
        <form className="weights" onSubmit={saveWeights}>
          <b>Weights</b>
          {SECTIONS.map(([key, label]) => (
            <label key={key} className="inline">{label}{" "}
              <input type="number" min="0" max="100" value={draft[key]} style={{ width: 70 }}
                     onChange={(e) => setDraft({ ...draft, [key]: Number(e.target.value) })} /> %
            </label>
          ))}
          {(() => {
            const sum = draft.skills + draft.experience + draft.qualifications;
            const changed = SECTIONS.some(([key]) => draft[key] !== weights[key]);
            return (<>
              <span className={sum === 100 ? "muted small" : "error small"}>total {sum}{sum !== 100 && " (must be 100)"}</span>
              <button type="submit" className="secondary" disabled={!changed || sum !== 100 || busy !== ""}>
                {busy === "weights" ? "Saving..." : "Save weights"}</button>
            </>);
          })()}
        </form>
      )}
      {running && (
        <div className="progress-line">
          <progress value={progress.done} max={Math.max(progress.total, 1)} />
          <span className="small">Screening {progress.done} of {progress.total} CV(s)...</span>
        </div>
      )}
      {note && <p className={note.ok ? "ok" : "error"}>{note.message}</p>}
      {error && <p className="error">{error}</p>}

      {table(picked.shown, "Included",
             filter.mode === "all" ? "Nobody is included yet." : "No included candidate matches this filter.",
             included.length > 0 && (
               <>
                 {filterBar()}
                 {picked.problem && <p className="error small">{picked.problem}</p>}
                 {picked.message && (
                   <p className="muted small">{picked.message}{" "}
                     {toAdd.length > 0 ? (
                       <button type="button" className="secondary" disabled={busy !== ""}
                               onClick={() => addToShortlist(toAdd.map((row) => row.candidate_id), filter.mode, Number(filter.value))}>
                         {busy === "shortlist" ? "Adding..." : `Add ${toAdd.length === 1 ? "this 1" : `these ${toAdd.length}`} to the shortlist`}
                       </button>
                     ) : picked.shown.length > 0 && <span>Everyone shown is on the shortlist.</span>}
                   </p>
                 )}
               </>
             ))}
      {shortlistTable()}
      {table(excluded, "Excluded", "Nobody is excluded.")}
    </div>
  );
}
