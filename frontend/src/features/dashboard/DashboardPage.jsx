import { useEffect, useState } from "react";
import DataTable from "../../shared/utils/DataTable.jsx";
import { dashboardApi } from "./dashboardApi.js";
import { currentJob } from "../../shared/utils/currentJob.js";

// The Dashboard: where every job, CV, interview and report stands. All numbers are counted by the backend from the
// saved data (dashboard_service.py, no AI). "All jobs" or one job; the jobs table and the AI health are always for all.
//   tiles · hiring funnel · needs your attention · scores · AI workflow health · jobs
// onOpen(page): opens another page of the app (from an attention item or a job row)

// The colour of a score: green 75 and above, amber 50 and above, red below 50 (the same as everywhere in the app)
const tone = (value) => (value === null || value === undefined ? "" : value >= 75 ? "good" : value >= 50 ? "fair" : "weak");
const BAND = { "0-49": ["weak", "Below 50"], "50-74": ["fair", "50 to 74"], "75-100": ["good", "75 and above"] };
const STAGE = { cv_screening: "CV screening", shortlist: "Shortlist", hr_decision: "Screening decision",
  invitation: "Interview invitation", interview_analysis: "Q&A analysis", post_interview: "Assessment",
  talent_invite: "Pool invitation", job_description: "Job description", assistant: "Assistant chat" };
const stageName = (stage) => STAGE[stage] || stage.replace(/_/g, " ");

// One number in the top row
function Tile({ label, value, detail, accent = "blue" }) {
  return (
    <div className={`dash-tile accent-${accent}`}>
      <span className="muted small">{label}</span>
      <b>{value}</b>
      {detail && <span className="muted small">{detail}</span>}
    </div>
  );
}

// A horizontal bar: the label, the bar (width = share of the largest value), the number. Hover shows the details.
function Bar({ label, value, max, text, className = "" }) {
  const width = max ? Math.max((100 * value) / max, value ? 2 : 0) : 0;
  return (
    <div className="dash-bar" title={`${label}: ${text}`}>
      <span className="dash-bar-label">{label}</span>
      <span className="dash-bar-track"><span className={`dash-bar-fill ${className}`} style={{ width: `${width}%` }} /></span>
      <span className="dash-bar-value">{text}</span>
    </div>
  );
}

export default function DashboardPage({ jobs = [], onOpen = () => {} }) {
  const [jobId, setJobId] = useState(() => { try { return sessionStorage.getItem("lumenai_job") || ""; } catch { return ""; } });
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  // → GET /api/dashboard (again when another job is chosen)
  useEffect(() => {
    setError("");
    dashboardApi.get(jobId).then(setData).catch((e) => {
      if (jobId) { currentJob.clear(); setJobId(""); return; }   // the remembered job was deleted: All jobs
      setError(e.message);
    });
  }, [jobId]);

  if (error) return <div className="card"><p className="error">{error}</p></div>;
  if (!data) return <div className="card"><p className="muted">Loading...</p></div>;

  const { tiles, funnel, scores, attention, workflows } = data;
  const applied = funnel[0].count;
  const bandMax = Math.max(...scores.bands.map((b) => b.count));
  const chosen = data.jobs.find((j) => j.job_id === Number(jobId));

  return (
    <div className="dash">
      <div className="row-between dash-head">
        <p className="muted small">{chosen ? `Showing: ${chosen.title}` : "Showing: all jobs"}</p>
        <label htmlFor="dash-job" className="inline">Job
          <select id="dash-job" value={jobId} onChange={(e) => { setJobId(e.target.value); currentJob.set(Number(e.target.value) || null); }}>
            <option value="">All jobs</option>
            {data.jobs.map((j) => <option key={j.job_id} value={j.job_id}>{j.title}</option>)}
          </select>
        </label>
      </div>

      <div className="dash-tiles">
        <Tile label="Open jobs" value={tiles.open_jobs} detail={`${tiles.draft_jobs} draft`} />
        <Tile label="Applications" accent="sky" value={tiles.applications} detail={`${tiles.new_applications} in the last 7 days`} />
        <Tile label="Shortlisted" accent="violet" value={tiles.shortlisted} />
        <Tile label="Interviews" accent="teal" value={tiles.interviews_upcoming} detail={`upcoming · ${tiles.interviews_ended} ended`} />
        <Tile label="Assessed" accent="green" value={tiles.assessed} detail={`${tiles.pending_decisions} waiting for a decision`} />
        <Tile label="Talent pool" accent="amber" value={tiles.pool_active} detail={`active · ${tiles.invites_sent} invited`} />
      </div>

      <div className="dash-grid">
        <div className="card">
          <h3>Hiring funnel</h3>
          <p className="muted small">How many candidates reached each step, and the share of all applications.</p>
          {applied === 0 ? <p className="muted small">No applications yet.</p>
            : funnel.map((s) => <Bar key={s.step} label={s.step} value={s.count} max={applied}
                                     text={`${s.count} · ${s.percent} %`} />)}
        </div>

        <div className="card">
          <h3>Needs your attention</h3>
          {attention.length === 0 ? <p className="ok small">Nothing is waiting. Everything is up to date.</p> : (
            <ul className="dash-attention">
              {attention.map((a) => (
                <li key={a.key}>
                  <b>{a.count}</b> {a.text}
                  <button type="button" className="link" onClick={() => onOpen(a.page)}>Open</button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="dash-grid">
        <div className="card">
          <h3>Scores</h3>
          <p className="muted small">Averages of the finished assessments{chosen ? "" : " of all jobs"}.</p>
          <div className="dash-mini">
            {[["CV", scores.cv], ["Interview", scores.interview], ["Overall", scores.overall]].map(([name, value]) => (
              <div key={name}><span className="muted small">{name}</span><b className={`mark ${tone(value)}`}>{value ?? "–"}</b></div>
            ))}
          </div>
          <p className="small dash-sub">Overall scores</p>
          {scores.bands.map((b) => <Bar key={b.band} label={BAND[b.band][1]} value={b.count} max={bandMax}
                                        text={String(b.count)} className={BAND[b.band][0]} />)}
          <p className="small dash-sub">Decisions</p>
          <div>
            <span className="badge done">Hire {scores.decisions.hire}</span>
            <span className="badge draft">Hold {scores.decisions.hold}</span>
            <span className="badge failed">Reject {scores.decisions.reject}</span>
            <span className="badge">Pending {scores.decisions.pending}</span>
          </div>
        </div>

        <div className="card">
          <h3>AI workflow health</h3>
          <p className="muted small">AI runs of the last {workflows.days} days. Model in use: <b>{workflows.model}</b></p>
          {workflows.stages.length === 0 ? <p className="muted small">No AI runs in the last {workflows.days} days.</p> : (
            <table>
              <thead><tr><th>Workflow</th><th>Runs</th><th>Failed</th><th>Failure rate</th></tr></thead>
              <tbody>
                {workflows.stages.map((s) => (
                  <tr key={s.stage}>
                    <td>{stageName(s.stage)}</td><td>{s.runs}</td><td>{s.failed}</td>
                    <td><span className={`badge ${s.failure_rate >= 20 ? "failed" : s.failed ? "draft" : "done"}`}>
                      {s.failure_rate} %</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="small muted">Many failures? Check the workflow log on Settings, or choose another AI model there.</p>
        </div>
      </div>

      <div className="card">
        <h3>Jobs</h3>
        <div className="table-scroll">
        <DataTable rows={data.jobs} rowKey={(row) => row.job_id} empty="No jobs yet." columns={[
          { key: "title", title: "Job", render: (row) => (
            <><b>{row.title}</b> <span className={`badge ${row.status === "approved" ? "approved" : "draft"}`}>
              {row.status === "approved" ? "Approved" : "Draft"}</span></>) },
          { key: "applied", title: "Applied", render: (row) => row.applied },
          { key: "shortlisted", title: "Shortlisted", render: (row) => row.shortlisted },
          { key: "interviewed", title: "Interviewed", render: (row) => row.interviewed },
          { key: "assessed", title: "Assessed", render: (row) => row.assessed },
          { key: "avg", title: "Avg overall", render: (row) => <span className={`mark ${tone(row.avg_overall)}`}>{row.avg_overall ?? "–"}</span> },
          { key: "decisions", title: "Hire / Hold / Reject", className: "small", render: (row) => `${row.hire} / ${row.hold} / ${row.reject}` },
          { key: "pending", title: "Pending", render: (row) => (row.pending ? <span className="badge draft">{row.pending}</span> : "–") },
          { key: "open", title: "", className: "small actions", render: () => (
            <>
              <button type="button" className="link" onClick={() => onOpen("candidates")}>Candidates</button>
              <button type="button" className="link" onClick={() => onOpen("reports")}>Reports</button>
            </>) },
        ]} />
        </div>
      </div>
    </div>
  );
}
