import { useEffect, useState } from "react";
import { jobsApi } from "./jobsApi.js";
import CompanyDocumentsPanel from "../job_library/CompanyDocumentsPanel.jsx";
import ConfirmDialog from "../../shared/utils/ConfirmDialog.jsx";
import DataTable from "../../shared/utils/DataTable.jsx";

const PLACES = { blogger: "Blogger blog" };

// What is saved in the database: the jobs, their posts and the company documents.
// This view only shows (and deletes). Writing, changing, approving and posting are done in the chat.
export default function JobsPage() {
  const [jobs, setJobs] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [postings, setPostings] = useState([]);
  const [error, setError] = useState("");
  const [askDelete, setAskDelete] = useState(false);   // the yes / no pop-up is open

  // Loads the list again and shows the job with `selectId` (or the newest one).
  async function load(selectId) {
    try {
      const list = await jobsApi.list();
      setJobs(list);
      setJobId(list.some((j) => j.id === selectId) ? selectId : list[0]?.id ?? null);
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(null); }, []);

  // The posts of the job that is shown
  useEffect(() => {
    setPostings([]);
    if (jobId) jobsApi.postings(jobId).then(setPostings).catch((e) => setError(e.message));
  }, [jobId]);

  if (!jobs) return <div className="card">{error ? <p className="error">{error}</p> : <p>Loading...</p>}</div>;
  const job = jobs.find((j) => j.id === jobId);

  // After Yes in the pop-up: deletes the shown job with jobsApi.remove and reloads the list
  async function remove() {
    setAskDelete(false); setError("");
    try { await jobsApi.remove(job.id); await load(null); } catch (e) { setError(e.message); }
  }

  return (
    <>
      <div className="card">
        <h3>Saved jobs <small className="muted">({jobs.length})</small></h3>
        {!job ? (
          <p className="muted">No jobs yet. Ask the AI in the chat, for example: "Write a job for a backend developer with Python".</p>
        ) : (
          <>
            <div className="row-between">
              <label className="inline">Job{" "}
                <select value={job.id} onChange={(e) => setJobId(Number(e.target.value))}>
                  {jobs.map((j) => <option key={j.id} value={j.id}>#{j.id} {j.title} ({j.status})</option>)}
                </select>
              </label>
              <button className="danger" onClick={() => setAskDelete(true)}>Delete</button>
            </div>

            <h2>{job.title} <span className={`badge ${job.status}`}>{job.status}</span></h2>
            <p className="muted small">Job #{job.id}. To change, approve or post it, ask in the chat and use this number.</p>
            <p><b>Required:</b> {job.required_skills.join(", ")}</p>
            {job.preferred_skills.length > 0 && <p><b>Preferred:</b> {job.preferred_skills.join(", ")}</p>}
            <p><b>Minimum experience:</b> {job.min_years} years{job.qualifications && <> · <b>Qualifications:</b> {job.qualifications}</>}</p>
            {job.prompt && <p className="muted small"><b>Asked for:</b> {job.prompt}</p>}
            {job.description ? <p className="description">{job.description}</p>
                             : <p className="muted">No description yet.</p>}

            <div className="section">
              <h3>Posts of this job</h3>
              <DataTable rows={postings} empty="Not posted yet." columns={[
                { key: "when", title: "When", render: (p) => new Date(p.created_at).toLocaleString() },
                { key: "where", title: "Where", render: (p) => PLACES[p.channel] || p.channel },
                { key: "result", title: "Result",
                  // Result column: a green or red badge with the post's status
                  render: (p) => <span className={`badge ${p.status === "posted" ? "done" : "failed"}`}>{p.status}</span> },
                { key: "details", title: "Details", className: "small",
                  // Details column: the error if posting failed, otherwise a link to the post
                  render: (p) => (p.status === "failed" ? p.error
                    : p.message_link ? <a href={p.message_link} target="_blank" rel="noreferrer">Open the post</a> : "Posted") },
              ]} />
            </div>
          </>
        )}
        {error && <p className="error">{error}</p>}
        {askDelete && (
          <ConfirmDialog question={`Delete the job "${job.title}"?`} detail="This cannot be undone."
                         onYes={remove} onNo={() => setAskDelete(false)} />
        )}
      </div>
      <CompanyDocumentsPanel />
    </>
  );
}
