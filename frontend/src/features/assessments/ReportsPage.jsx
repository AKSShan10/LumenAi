import { useEffect, useState } from "react";
import { navigate } from "../../shared/utils/navigate.js";
import { jobsApi } from "../jobs/jobsApi.js";
import DataTable from "../../shared/utils/DataTable.jsx";
import JobPicker from "../../shared/utils/JobPicker.jsx";
import { currentJob } from "../../shared/utils/currentJob.js";
import { assessmentsApi } from "./assessmentsApi.js";
import { talentPoolApi } from "../talent_pool/talentPoolApi.js";

// The Reports page: the interviewed candidates of a job side by side, best overall score first.
// "Create assessment" starts the report in the background; "View report" opens it inside the app
// (AssessmentReportPage.jsx, /assessment-report/<candidate id>) with the decision and Export PDF.
// The CV / interview weight (40 / 60 by default) can be changed per job; the overall scores are then recalculated
// by the backend (only maths, no AI), and the table is ranked again.
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
  const [draft, setDraft] = useState(null);         // the CV weight being typed (null = show the saved one)
  const [note, setNote] = useState("");

  useEffect(() => {
    jobsApi.list().then((list) => {
      const approved = list.filter((j) => j.status === "approved");
      setJobs(approved);
      setJobId(currentJob.get(approved));          // the job chosen on another page, or All jobs
    }).catch((e) => setError(e.message));
  }, []);

  // → GET /api/jobs/{id}/comparison (one job) or GET /api/comparison (All jobs, grouped by job)
  function load(id = jobId) {
    if (!jobs) return Promise.resolve();
    return (id ? assessmentsApi.comparison(id) : assessmentsApi.comparisonAll())
      .then(setRows).catch((e) => setError(e.message));
  }
  useEffect(() => {
    setDraft(null); setNote("");                     // another job: show its own saved weight
    load(jobId);
    const timer = setInterval(() => { if (!document.hidden) load(jobId); }, LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [jobId, jobs]);                                 // eslint-disable-line react-hooks/exhaustive-deps

  // A click on a job name in the All jobs list: show only that job (and remember it for the other pages)
  function showJob(id) { currentJob.set(id); setJobId(id); }

  // Opens the report of a candidate in the app. "Create assessment" opens it with ?start=1: the report page starts
  // the assessment and shows the progress.
  function openReport(row, start = false) {
    navigate(`/assessment-report/${row.candidate_id}${start ? "?start=1" : ""}`);
  }

  // "Add to talent pool": → PUT /api/candidates/{id}/talent-pool (status "strong"; the note can be added on the report)
  async function addToPool(row) {
    setError("");
    try { await talentPoolApi.add(row.candidate_id, "strong", ""); await load(); } catch (e) { setError(e.message); }
  }
  const POOL_WORDS = { active: "In talent pool", unsubscribed: "Unsubscribed", expired: "Pool time ended" };

  // On "Save weights": → PUT /api/jobs/{id}/assessment-weight; the answer is the recalculated table
  async function saveWeight(cvWeight) {
    setError(""); setNote("");
    try {
      setRows(await assessmentsApi.setWeight(jobId, cvWeight));
      setDraft(null);
      setNote(`Saved: CV ${cvWeight} %, interview ${100 - cvWeight} %. The overall scores were recalculated.`);
    } catch (e) { setError(e.message); }
  }

  if (!jobs) return <div className="card"><p className="muted">Loading...</p></div>;
  if (jobs.length === 0) return <div className="card"><p className="muted">No approved job yet.</p></div>;
  const weight = rows[0]?.cv_weight ?? 40;
  const typed = draft ?? String(weight);
  const valid = /^\d{1,3}$/.test(typed) && Number(typed) <= 100;     // a whole number from 0 to 100

  return (
    <div className="card">
      <div className="row-between">
        <h3>Candidate comparison</h3>
        <JobPicker id="reports-job" jobs={jobs} value={jobId} onChange={setJobId} />
      </div>
      {!jobId && <p className="muted small">All jobs, grouped by job. Inside each job the best overall score comes first;
        scores of different jobs are not ranked against each other. Choose a job to change its CV / interview weights.</p>}
      {jobId && <>
      <div className="weight-bar">
        <label htmlFor="cv-weight" className="inline">CV weight
          <input id="cv-weight" type="number" min="0" max="100" step="5" value={typed}
                 onChange={(e) => setDraft(e.target.value)} disabled={rows.length === 0} /> %
        </label>
        <span>Interview weight <b>{valid ? 100 - Number(typed) : "–"} %</b></span>
        <button type="button" onClick={() => saveWeight(Number(typed))}
                disabled={!valid || Number(typed) === weight || rows.length === 0}>Save weights</button>
        {weight !== 40 && <button type="button" className="link" onClick={() => saveWeight(40)}>Back to 40 / 60</button>}
      </div>
      <p className="muted small">Overall score = CV score × {weight} % + interview score × {100 - weight} %. Changing the
        weights recalculates the overall scores of this job (no new AI work). The AI writes the report; you record the
        decision.</p>
      {!valid && <p className="error small">The CV weight must be a whole number from 0 to 100.</p>}
      </>}
      {note && <p className="ok small">{note}</p>}
      {error && <p className="error">{error}</p>}

      <DataTable rows={rows} rowKey={(row) => row.candidate_id}
                 empty={jobId ? "No interviewed candidates for this job yet." : "No interviewed candidates yet."} columns={[
        // the rank inside the candidate's own job
        { key: "rank", title: "#", render: (row) => (row.overall_score !== null
          ? rows.filter((r) => r.job_id === row.job_id).indexOf(row) + 1 : "–") },
        ...(jobId ? [] : [{ key: "job", title: "Job", className: "small", render: (row) => (
          <button type="button" className="link" onClick={() => showJob(row.job_id)} title="Show only this job">
            {row.job_title}</button>) }]),
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
              {row.status === "done" && (row.pool
                ? <span className={`badge ${row.pool === "active" ? "done" : ""}`}>{POOL_WORDS[row.pool]}</span>
                : <button className="link" onClick={() => addToPool(row)}>Add to talent pool</button>)}
            </>
          );
        } },
      ]} />
    </div>
  );
}
