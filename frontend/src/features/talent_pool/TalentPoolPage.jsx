import { useEffect, useState } from "react";
import { jobsApi } from "../jobs/jobsApi.js";
import DataTable from "../../shared/utils/DataTable.jsx";
import ConfirmDialog from "../../shared/utils/ConfirmDialog.jsx";
import { POOL_STATUS, talentPoolApi } from "./talentPoolApi.js";

// The Talent Pool page (innovation feature).
//   1. Past candidates for a job: choose an approved job; code lists the pool candidates whose CV shows its skills
//      (match %, required skills count twice). The filters can be changed. Tick some → "Draft invitations" (the
//      workflow writes and checks each email) → edit, or "Write again" with a wish → "Send" (a person decides).
//   2. Talent pool: everyone kept from the assessment reports, their state and the invitations sent.
// The apply link and the unsubscribe link are added below every email by the backend.
const day = (value) => new Date(value).toLocaleDateString([], { dateStyle: "medium" });
const STATE = { active: ["Active", "done"], unsubscribed: ["Unsubscribed", "failed"], expired: ["Expired", ""] };

export default function TalentPoolPage() {
  const [jobs, setJobs] = useState([]);
  const [jobId, setJobId] = useState("");
  const [matches, setMatches] = useState([]);
  const [filters, setFilters] = useState({ min_match: "", all_required: false, min_score: "", status: "", hide_invited: false });
  const [wishes, setWishes] = useState({});          // pool id -> the wish typed for "Write again"
  const [rewriting, setRewriting] = useState(null);  // the pool id being written again
  const [chosen, setChosen] = useState([]);          // pool ids ticked in the matches table
  const [drafts, setDrafts] = useState(null);        // the emails being checked before sending
  const [results, setResults] = useState(null);
  const [pool, setPool] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ask, setAsk] = useState(null);              // the pop-up: {action: "remove" | "addBack", row}

  const loadPool = () => talentPoolApi.list().then(setPool).catch((e) => setError(e.message));
  useEffect(() => {
    jobsApi.list().then((list) => {
      const approved = list.filter((j) => j.status === "approved");
      setJobs(approved);
      if (approved[0]) setJobId(approved[0].id);
    }).catch((e) => setError(e.message));
    loadPool();
  }, []);

  // → GET /api/jobs/{id}/talent-matches with the filters; the first answer fills in the default minimum match
  function loadMatches(id = jobId, chosenFilters = filters) {
    if (!id) return;
    talentPoolApi.matches(id, chosenFilters).then((answer) => {
      setMatches(answer.rows);
      setFilters((old) => (old.min_match === "" ? { ...old, min_match: String(answer.min_match) } : old));
    }).catch((e) => setError(e.message));
  }
  useEffect(() => { setChosen([]); setDrafts(null); setResults(null); loadMatches(jobId); }, [jobId]);   // eslint-disable-line react-hooks/exhaustive-deps

  // A filter changed: keep it and load the list again
  function setFilter(key, value) {
    const next = { ...filters, [key]: value };
    setFilters(next);
    if (key === "min_match" && value !== "" && !(Number(value) >= 0 && Number(value) <= 100)) return;
    if (key === "min_score" && value !== "" && !(Number(value) >= 0 && Number(value) <= 100)) return;
    loadMatches(jobId, next);
  }

  const tick = (poolId) => setChosen((old) => (old.includes(poolId) ? old.filter((id) => id !== poolId) : [...old, poolId]));

  // "Draft invitations": → POST /api/jobs/{id}/talent-invites/draft (nothing is sent yet)
  async function draft() {
    setBusy(true); setError(""); setResults(null);
    try { setDrafts(await talentPoolApi.draft(jobId, chosen)); } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  // "Write again" for one person: → POST .../talent-invites/draft with that person and the wish
  async function writeAgain(poolId) {
    setRewriting(poolId); setError("");
    try {
      const [fresh] = await talentPoolApi.draft(jobId, [poolId], wishes[poolId] || "");
      setDrafts((old) => old.map((d) => (d.pool_id === poolId ? fresh : d)));
    } catch (e) { setError(e.message); }
    finally { setRewriting(null); }
  }

  // "Send": → POST /api/jobs/{id}/talent-invites/send with the texts as edited here
  async function send() {
    setBusy(true); setError("");
    try {
      setResults(await talentPoolApi.send(jobId, drafts));
      setDrafts(null); setChosen([]);
      loadMatches(); loadPool();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  // "Add back" for someone who unsubscribed (after Yes in the pop-up): → PUT /api/candidates/{id}/talent-pool
  async function addBack(row) {
    setAsk(null); setError("");
    try { await talentPoolApi.add(row.candidate_id, row.status, row.note, true); loadPool(); loadMatches(); }
    catch (e) { setError(e.message); }
  }

  // "Remove" (after Yes in the pop-up): takes the person out of the pool, their invitations too
  // → DELETE /api/candidates/{id}/talent-pool. Their application, report and decision stay.
  async function remove(row) {
    setAsk(null); setError("");
    try { await talentPoolApi.remove(row.candidate_id); loadPool(); loadMatches(); setDrafts(null); setChosen([]); }
    catch (e) { setError(e.message); }
  }

  const edit = (n, field, value) => setDrafts((old) => old.map((d, i) => (i === n ? { ...d, [field]: value } : d)));

  return (
    <>
      <div className="card">
        <div className="row-between">
          <h3>Past candidates for a job</h3>
          <label htmlFor="pool-job" className="inline">Job
            <select id="pool-job" value={jobId} onChange={(e) => setJobId(Number(e.target.value))}>
              {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
            </select>
          </label>
        </div>
        <p className="muted small">The match uses only the job's skills and the CV text (also other names of a skill,
          e.g. Postgres = PostgreSQL). Required skills count twice, preferred skills once. Name, gender, age, address and
          earlier results are never used. The AI only drafts the email; nothing is sent until you click Send.</p>
        <div className="pool-filters">
          <label className="inline">Minimum match
            <input type="number" min="0" max="100" step="5" value={filters.min_match}
                   onChange={(e) => setFilter("min_match", e.target.value)} /> %</label>
          <label className="inline"><input type="checkbox" checked={filters.all_required}
                   onChange={(e) => setFilter("all_required", e.target.checked)} /> All required skills</label>
          <label className="inline">Earlier score at least
            <input type="number" min="0" max="100" placeholder="off" value={filters.min_score}
                   onChange={(e) => setFilter("min_score", e.target.value)} /></label>
          <label className="inline">Status
            <select value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
              <option value="">Both</option>
              {Object.entries(POOL_STATUS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select></label>
          <label className="inline"><input type="checkbox" checked={filters.hide_invited}
                   onChange={(e) => setFilter("hide_invited", e.target.checked)} /> Hide already invited</label>
        </div>
        {error && <p className="error">{error}</p>}

        <DataTable rows={matches} rowKey={(row) => row.pool_id}
                   empty="No one meets these filters. Lower the minimum match or clear a filter. People are not suggested for a job they already applied to." columns={[
          { key: "pick", title: "", render: (row) => (
            <input type="checkbox" checked={chosen.includes(row.pool_id)} onChange={() => tick(row.pool_id)}
                   aria-label={`Choose ${row.name}`} />) },
          { key: "who", title: "Candidate", render: (row) => <><b>{row.name}</b><div className="small muted">{POOL_STATUS[row.status]}</div></> },
          { key: "from", title: "Applied for", className: "small", render: (row) => row.from_job },
          { key: "match", title: "Match", render: (row) => <b>{row.match} %</b> },
          { key: "skills", title: "Requirements in the CV", className: "small", render: (row) => (
            <>
              {row.matched.map((s) => <span key={s} className="badge done">{s}</span>)}
              {row.missing.map((s) => <span key={s} className="badge">{s}</span>)}
            </>) },
          { key: "earlier", title: "Earlier result", className: "small", render: (row) => (row.overall_score !== null
            ? `${row.overall_score} · ${row.decision}` : "–") },
          { key: "invited", title: "Invited", className: "small", render: (row) => (row.invited_at ? day(row.invited_at) : "–") },
        ]} />
        <button type="button" onClick={draft} disabled={!chosen.length || busy}>
          {busy && !drafts ? "Drafting..." : `Draft invitations (${chosen.length})`}</button>

        {drafts && (
          <div className="pool-drafts">
            <h3>Check the emails</h3>
            <p className="muted small">Each email was checked by code: it is formal, names the person and the job, has no links,
              scores, earlier results or promises, and names only skills shown in the CV. Edit it, or write it again
              with a wish.</p>
            {drafts.map((d, n) => (
              <div key={d.pool_id} className="pool-draft">
                <b>{d.name}</b> <span className="muted small">{d.email}</span>
                <input value={d.subject} maxLength="200" onChange={(e) => edit(n, "subject", e.target.value)} />
                <textarea rows="7" value={d.body} maxLength="4000" onChange={(e) => edit(n, "body", e.target.value)} />
                <pre className="pool-footer">{d.footer.trim()}</pre>
                <div className="pool-filters">
                  <input maxLength="300" placeholder="Wish for Write again (optional), e.g. shorter, mention remote work"
                         value={wishes[d.pool_id] || ""} onChange={(e) => setWishes({ ...wishes, [d.pool_id]: e.target.value })} />
                  <button type="button" className="secondary" onClick={() => writeAgain(d.pool_id)}
                          disabled={busy || rewriting !== null}>{rewriting === d.pool_id ? "Writing..." : "Write again"}</button>
                </div>
              </div>
            ))}
            <button type="button" onClick={send} disabled={busy}>{busy ? "Sending..." : "Send"}</button>
            <button type="button" className="secondary" onClick={() => setDrafts(null)} disabled={busy}>Cancel</button>
          </div>
        )}
        {results && results.map((r) => (
          <p key={r.pool_id} className={r.ok ? "ok small" : "error small"}>
            {r.name}: {r.ok ? "sent." : `not sent (${r.error}).`}</p>
        ))}
      </div>

      <div className="card">
        <h3>Talent pool</h3>
        <p className="muted small">Candidates kept from their assessment report (Talent pool card). Each stays for a
          limited time, and anyone can unsubscribe with the link in an invitation.</p>
        <DataTable rows={pool} rowKey={(row) => row.candidate_id} empty="No one yet. Open an assessment report and use the Talent pool card." columns={[
          { key: "who", title: "Candidate", render: (row) => <><b>{row.name}</b><div className="small muted">{row.email}</div></> },
          { key: "from", title: "Applied for", className: "small", render: (row) => row.from_job },
          { key: "status", title: "Status", className: "small", render: (row) => (
            <>{POOL_STATUS[row.status]}{row.note && <div className="muted">{row.note}</div>}</>) },
          { key: "state", title: "State", className: "small", render: (row) => (
            <span className={`badge ${STATE[row.state][1]}`}>{STATE[row.state][0]}</span>) },
          { key: "until", title: "Kept until", className: "small", render: (row) => day(row.keep_until) },
          { key: "invites", title: "Invitations", className: "small", render: (row) => (row.invites.length
            ? row.invites.map((i, n) => <div key={n}>{i.job_title} · {day(i.sent_at)}{i.applied && <span className="badge done">Applied</span>}</div>)
            : "–") },
          { key: "actions", title: "Actions", className: "small actions", render: (row) => (
            <>
              {row.state === "unsubscribed" && (
                <button type="button" className="link" onClick={() => setAsk({ action: "addBack", row })}>Add back</button>)}
              <button type="button" className="link" onClick={() => setAsk({ action: "remove", row })}>Remove</button>
            </>) },
        ]} />
        {ask?.action === "remove" && (
          <ConfirmDialog question={`Remove ${ask.row.name} from the talent pool?`}
                         detail="Their invitations are removed too. Their application, report and decision stay."
                         onYes={() => remove(ask.row)} onNo={() => setAsk(null)} />)}
        {ask?.action === "addBack" && (
          <ConfirmDialog question={`Add ${ask.row.name} back to the talent pool?`}
                         detail="Only do this if they asked to be contacted again. They get a new unsubscribe link."
                         onYes={() => addBack(ask.row)} onNo={() => setAsk(null)} />)}
      </div>
    </>
  );
}
