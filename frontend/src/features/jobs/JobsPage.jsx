import { useEffect, useState } from "react";
import { jobsApi } from "./jobsApi.js";
import ConfirmDialog from "../../shared/utils/ConfirmDialog.jsx";
import { currentJob } from "../../shared/utils/currentJob.js";
import { navigate } from "../../shared/utils/navigate.js";

const PLACES = { blogger: "Blogger blog" };
const FILTERS = [["all", "All"], ["draft", "Draft"], ["approved", "Approved"]];

// The Jobs tab: the saved jobs on the left, the chosen job on the right.
// This tab only shows (and deletes). Writing, changing, approving and posting are done in the chat:
// the "next step" button opens the chat with the message ready, and the interviewer clicks Send.
// onOpenChat(text): opens the chat tab with that text in the box.  onChanged(): the tab numbers are read again.
export default function JobsPage({ onOpenChat, onChanged }) {
  const [jobs, setJobs] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [postings, setPostings] = useState([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [longText, setLongText] = useState(false);     // the whole description is shown
  const [askDelete, setAskDelete] = useState(false);   // the yes / no pop-up is open
  const [error, setError] = useState("");

  // Loads the list and shows the job chosen on another page, or else the newest job
  async function load() {
    try {
      const list = await jobsApi.list();
      setJobs(list);
      setJobId(currentJob.get(list) || list[0]?.id || null);
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);

  // Shows one job and remembers it for the other pages
  function showJob(id) { currentJob.set(id); setJobId(id); setLongText(false); }

  // The posts of the job that is shown
  useEffect(() => {
    setPostings([]);
    if (jobId) jobsApi.postings(jobId).then(setPostings).catch((e) => setError(e.message));
  }, [jobId]);

  if (!jobs) return <div className="card">{error ? <p className="error">{error}</p> : <p>Loading...</p>}</div>;

  if (jobs.length === 0) {
    return (
      <div className="card empty-state">
        <h3>No jobs yet</h3>
        <p className="muted">Ask the AI to write one, for example: "Write a job for a backend developer with Python".</p>
        <button onClick={() => onOpenChat("Write a job for a backend developer with Python and FastAPI, 3 years experience")}>
          Write a job in the chat
        </button>
      </div>
    );
  }

  const job = jobs.find((j) => j.id === jobId);
  const word = search.trim().toLowerCase();
  // The list on the left: the status filter and the search box (title or a required skill)
  const shown = jobs.filter((j) => (filter === "all" || j.status === filter)
    && (!word || j.title.toLowerCase().includes(word) || j.required_skills.some((s) => s.toLowerCase().includes(word))));
  const howMany = (key) => (key === "all" ? jobs.length : jobs.filter((j) => j.status === key).length);
  const posted = postings.some((p) => p.status === "posted");

  // After Yes in the pop-up: deletes the shown job with jobsApi.remove and reloads the list
  async function remove() {
    setAskDelete(false); setError("");
    try { await jobsApi.remove(job.id); currentJob.set(null); await load(); onChanged(); } catch (e) { setError(e.message); }
  }

  // The one thing to do next for this job, as a sentence and a button
  function nextStep() {
    if (job.status !== "approved") {
      return { text: "Approve the job before it can be posted.", button: "Approve in the chat",
               click: () => onOpenChat(`Approve job #${job.id}`) };
    }
    if (!posted) {
      return { text: "Post the job on the company blog with the application form link.", button: "Post in the chat",
               click: () => onOpenChat(`Post job #${job.id} on the blog. The application form link is: `) };
    }
    return { text: "Collect the applications from the Google Form.", button: "Open Candidates →",
             click: () => navigate("/candidates") };
  }

  return (
    <div className="jobs-split">
      {/* left: the list of jobs */}
      <div className="card job-list">
        <input className="search-box" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search jobs or skills" />
        <div className="filter-chips">
          {FILTERS.map(([key, label]) => (
            <button key={key} type="button" className={filter === key ? "on" : ""} onClick={() => setFilter(key)}>
              {label} {howMany(key)}
            </button>
          ))}
        </div>
        {shown.length === 0 && <p className="muted small">No job matches.</p>}
        {shown.map((j) => (
          <button key={j.id} type="button" className={`job-item ${j.id === jobId ? "selected" : ""}`} onClick={() => showJob(j.id)}>
            <b>{j.title}</b>
            <span><span className={`badge ${j.status}`}>{j.status}</span>
              <span className="muted small"> {j.min_years}+ years · #{j.id}</span></span>
          </button>
        ))}
      </div>

      {/* right: the chosen job */}
      <div className="card job-detail">
        {!job ? <p className="muted">Choose a job on the left.</p> : (
          <>
            <div className="row-between">
              <div>
                <h2 className="job-title">{job.title} <span className={`badge ${job.status}`}>{job.status}</span>
                  {posted && <span className="badge posted">posted</span>}</h2>
                <p className="muted small">Job #{job.id}
                  {job.approved_at && <> · approved {new Date(job.approved_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</>}
                </p>
              </div>
              <button className="danger" onClick={() => setAskDelete(true)}>Delete</button>
            </div>

            {(() => { const next = nextStep(); return (
              <div className="next-step">
                <span><b>Next step:</b> {next.text}</span>
                <button className="secondary" onClick={next.click}>{next.button}</button>
              </div>
            ); })()}

            <div className="job-facts">
              <span className="muted">Required</span>
              <div>{job.required_skills.map((s) => <span key={s} className="skill-chip">{s}</span>)}</div>
              {job.preferred_skills.length > 0 && <>
                <span className="muted">Preferred</span>
                <div>{job.preferred_skills.map((s) => <span key={s} className="skill-chip light">{s}</span>)}</div>
              </>}
              <span className="muted">Experience</span>
              <div>{job.min_years}+ years</div>
              {job.qualifications && <><span className="muted">Qualification</span><div>{job.qualifications}</div></>}
              {job.prompt && <><span className="muted">Asked for</span><div className="small">{job.prompt}</div></>}
            </div>

            <h4 className="part-title">Description</h4>
            {job.description ? (
              <div className={`description ${longText ? "" : "clamped"}`}>
                {job.description}
                {job.description.length > 500 && (
                  <div><button type="button" className="link" onClick={() => setLongText(!longText)}>
                    {longText ? "Show less" : "Show more"}</button></div>
                )}
              </div>
            ) : <p className="muted">No description yet.</p>}

            <h4 className="part-title">Posts</h4>
            {postings.length === 0 && <p className="muted small">Not posted yet.</p>}
            {postings.map((p) => (
              <div key={p.id} className="post-row">
                <span className={`badge ${p.status === "posted" ? "done" : "failed"}`}>{p.status}</span>
                <span>{PLACES[p.channel] || p.channel}</span>
                <span className="muted small">{new Date(p.created_at).toLocaleString()}</span>
                <span className="post-link">
                  {p.status === "failed" ? <span className="error small">{p.error}</span>
                    : p.message_link ? <a href={p.message_link} target="_blank" rel="noreferrer">Open the post ↗</a> : "Posted"}
                </span>
              </div>
            ))}
          </>
        )}
        {error && <p className="error">{error}</p>}
      </div>

      {askDelete && (
        <ConfirmDialog question={`Delete the job "${job.title}"?`} detail="This cannot be undone."
                       onYes={remove} onNo={() => setAskDelete(false)} />
      )}
    </div>
  );
}
