import { useEffect, useState } from "react";
import { jobsApi } from "../jobs/jobsApi.js";
import DataTable from "../../shared/utils/DataTable.jsx";
import { assessmentsApi } from "./assessmentsApi.js";

// The Reports page: the interviewed candidates of a job side by side, best overall score first.
// "Create assessment" starts the report in the background; "View report" opens it in a new tab
// (AssessmentReportPage.jsx, /assessment-report/<candidate id>) with the decision and Export PDF.
const LOOK_AGAIN_MS = 10000;          // the table refreshes itself, so new scores appear
const DECISION = {
  pending: { label: "Pending", badge: "" },
  hire: { label: "Hire", badge: "done" },
  hold: { label: "Hold", badge: "draft" },
  reject: { label: "Reject", badge: "failed" },
};
// The colour of a score: green 75 and above, amber 50 and above, red below 50
const tone = (value) => (value === null || value === undefined ? "" : value >= 75 ? "good" : value >= 50 ? "fair" : "weak");
const Score = ({ value }) => <span className={`mark ${tone(value)}`}>{value ?? "–"}</span>;

export default function ReportsPage() {
  const [jobs, setJobs] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    jobsApi.list().then((list) => {
      const approved = list.filter((j) => j.status === "approved");
      setJobs(approved);
      if (approved[0]) setJobId(approved[0].id);
    }).catch((e) => setError(e.message));
  }, []);

  // → GET /api/jobs/{id}/comparison: the comparison table
  function load(id = jobId) {
    if (!id) return Promise.resolve();
    return assessmentsApi.comparison(id).then(setRows).catch((e) => setError(e.message));
  }
  useEffect(() => {
    load(jobId);
    const timer = setInterval(() => { if (!document.hidden) load(jobId); }, LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [jobId]);                                       // eslint-disable-line react-hooks/exhaustive-deps

  // Opens the report of a candidate in a new tab; window.open (inside the click) copies this tab's login.
  // "Create assessment" opens it with ?start=1: the report tab starts the assessment and shows the progress.
  function openReport(row, start = false) {
    setError("");
    const page = window.open(`/assessment-report/${row.candidate_id}${start ? "?start=1" : ""}`, "_blank");
    if (!page) setError("The browser blocked the new tab. Allow pop-ups for this site and click again.");
    else if (start) setTimeout(() => load(), 3000);   // show "Assessing..." here soon
  }

  if (!jobs) return <div className="card"><p className="muted">Loading...</p></div>;
  if (jobs.length === 0) return <div className="card"><p className="muted">No approved job yet.</p></div>;
  const weight = rows[0]?.cv_weight ?? 40;

  return (
    <div className="card">
      <div className="row-between">
        <h3>Candidate comparison</h3>
        <label htmlFor="reports-job" className="inline">Job
          <select id="reports-job" value={jobId || ""} onChange={(e) => setJobId(Number(e.target.value))}>
            {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
          </select>
        </label>
      </div>
      <p className="muted small">Overall score = CV score × {weight} % + interview score × {100 - weight} %. The AI writes
        the report; you record the decision.</p>
      {error && <p className="error">{error}</p>}

      <DataTable rows={rows} empty="No interviewed candidates for this job yet." columns={[
        { key: "rank", title: "#", render: (row) => (row.overall_score !== null ? rows.indexOf(row) + 1 : "–") },
        { key: "who", title: "Candidate", render: (row) => <b>{row.candidate_name || "(name not given)"}</b> },
        { key: "cv", title: "CV score", render: (row) => <Score value={row.cv_score} /> },
        { key: "interview", title: "Interview score", render: (row) => <Score value={row.interview_score} /> },
        { key: "overall", title: "Overall", render: (row) => <b><Score value={row.overall_score} /></b> },
        { key: "decision", title: "Decision", className: "small", render: (row) => (
          <span className={`badge ${DECISION[row.decision]?.badge || ""}`}>{DECISION[row.decision]?.label || row.decision}</span>
        ) },
        { key: "actions", title: "", className: "small actions", render: (row) => {
          if (!row.interview_ended) return <span className="muted">Interview not finished</span>;
          if (!row.analysis_done) return <span className="muted">Analyse the answers first (Interviews page)</span>;
          if (row.status === "not_started") {
            return <button className="link" onClick={() => openReport(row, true)}>Create assessment</button>;
          }
          return (
            <>
              {row.status === "running" && <span className="muted">Assessing... </span>}
              {row.status === "failed" && <span className="badge failed">Failed</span>}{" "}
              <button className="link" onClick={() => openReport(row)}>View report</button>
            </>
          );
        } },
      ]} />
    </div>
  );
}
