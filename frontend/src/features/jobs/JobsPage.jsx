import { useEffect, useState } from "react";
import { jobsApi } from "./jobsApi.js";
import JobForm from "./JobForm.jsx";
import JobPostPanel from "./JobPostPanel.jsx";
import CompanyDocumentsPanel from "../job_library/CompanyDocumentsPanel.jsx";
import ConfirmDialog from "../../shared/utils/ConfirmDialog.jsx";

// The Job Requirements page: pick a job, see it, edit it, approve it, or create a new one.
export default function JobsPage() {
  const [jobs, setJobs] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [mode, setMode] = useState("view");          // view | edit | new
  const [addToLibrary, setAddToLibrary] = useState(true);
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

  if (!jobs) return <div className="card">{error ? <p className="error">{error}</p> : <p>Loading...</p>}</div>;
  const job = jobs.find((j) => j.id === jobId);

  const saved = async (savedJob) => { await load(savedJob.id); setMode("view"); };

  async function run(action, selectId) {
    setError("");
    try { await action(); await load(selectId); } catch (e) { setError(e.message); }
  }
  function remove() {
    setAskDelete(false);
    run(() => jobsApi.remove(job.id), null);
  }

  if (mode === "new" || !job) {
    return <><JobForm onSaved={saved} onCancel={job ? () => setMode("view") : null} /><CompanyDocumentsPanel /></>;
  }
  if (mode === "edit") return <JobForm key={job.id} job={job} onSaved={saved} onCancel={() => setMode("view")} />;

  return (
    <>
      <div className="card">
        <div className="row-between">
          <label className="inline">Job{" "}
            <select value={job.id} onChange={(e) => setJobId(Number(e.target.value))}>
              {jobs.map((j) => <option key={j.id} value={j.id}>{j.title} ({j.status})</option>)}
            </select>
          </label>
          <div>
            <button className="secondary" onClick={() => setMode("edit")}>Edit</button>
            <button className="danger" onClick={() => setAskDelete(true)}>Delete</button>
            <button onClick={() => setMode("new")}>+ New job</button>
          </div>
        </div>

        <h2>{job.title} <span className={`badge ${job.status}`}>{job.status}</span></h2>
        <p><b>Required:</b> {job.required_skills.join(", ")}</p>
        {job.preferred_skills.length > 0 && <p><b>Preferred:</b> {job.preferred_skills.join(", ")}</p>}
        <p><b>Minimum experience:</b> {job.min_years} years{job.qualifications && <> · <b>Qualifications:</b> {job.qualifications}</>}</p>
        {job.description ? <p className="description">{job.description}</p>
                         : <p className="muted">No description yet. Click Edit, then "Fill the form with AI".</p>}

        {job.status !== "approved" && (
          <div className="section">
            <h3>Step 3 · Approve</h3>
            <p className="muted small">Only an approved job can be posted. Read the description before you approve it.</p>
            <label className="inline">
              <input type="checkbox" checked={addToLibrary} onChange={(e) => setAddToLibrary(e.target.checked)} />
              {" "}keep this description as an example for future jobs
            </label>
            <div><button onClick={() => run(() => jobsApi.approve(job.id, addToLibrary), job.id)} disabled={!job.description}>Approve job</button></div>
          </div>
        )}
        {error && <p className="error">{error}</p>}
        {askDelete && (
          <ConfirmDialog question={`Delete the job "${job.title}"?`} detail="This cannot be undone."
                         onYes={remove} onNo={() => setAskDelete(false)} />
        )}
      </div>
      {job.status === "approved" && <JobPostPanel key={job.id} job={job} />}
      <CompanyDocumentsPanel key={`${job.id}-${job.status}`} />
    </>
  );
}
