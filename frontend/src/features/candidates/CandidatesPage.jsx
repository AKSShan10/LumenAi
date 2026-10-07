import { useEffect, useRef, useState } from "react";
import { jobsApi } from "../jobs/jobsApi.js";
import { candidatesApi } from "./candidatesApi.js";
import ConfirmDialog from "../../shared/utils/ConfirmDialog.jsx";

const SOURCES = { google_form: "Google Form", upload: "Uploaded by hand" };
const CHECK_EVERY_MS = 60000;      // the response sheet is looked at again every minute

// The Candidates page: pick an approved job, see how many new applications are in its response sheet,
// fetch them (the CV files are saved on this computer), or upload CVs by hand.
// Each form application comes from ONE row of the sheet, so a person is always shown with their own CV.
export default function CandidatesPage() {
  const [jobs, setJobs] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [sheetUrl, setSheetUrl] = useState("");
  const [savedUrl, setSavedUrl] = useState("");     // the link that is saved for this job
  const [news, setNews] = useState(null);           // answer of the last check: how many are new
  const [checkedAt, setCheckedAt] = useState(null); // when the sheet was last looked at
  const [show, setShow] = useState("all");          // which candidates the list shows: all | google_form | upload
  const [result, setResult] = useState(null);       // answer of the last fetch
  const [candidates, setCandidates] = useState([]);
  const [person, setPerson] = useState({ fullName: "", email: "", phone: "" });
  const [files, setFiles] = useState([]);
  const [uploadNotes, setUploadNotes] = useState([]);
  const [toDelete, setToDelete] = useState(null);   // the candidate the yes / no pop-up asks about
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const fileInput = useRef(null);
  const busyRef = useRef("");                        // the timer reads this to see whether something is running
  busyRef.current = busy;

  useEffect(() => {
    jobsApi.list().then((list) => {
      const approved = list.filter((j) => j.status === "approved");
      setJobs(approved);
      if (approved[0]) choose(approved[0]);
    }).catch((e) => setError(e.message));
  }, []);

  // Asks the backend how many form answers are new. Nothing is downloaded.
  async function check(id) {
    setBusy("check");
    try { setNews(await candidatesApi.check(id)); setCheckedAt(new Date()); }
    catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // Looks at the sheet again every minute while this page is open, so the number of new applications
  // stays up to date without a click. It only counts: the CVs are downloaded when you click Fetch.
  useEffect(() => {
    if (!jobId || !savedUrl) return undefined;
    const timer = setInterval(() => {
      if (document.hidden || busyRef.current !== "") return;      // not while the tab is in the background or busy
      candidatesApi.check(jobId).then((answer) => { setNews(answer); setCheckedAt(new Date()); setResult(null); }).catch(() => {});
    }, CHECK_EVERY_MS);
    return () => clearInterval(timer);                             // stops when you leave the page or change the job
  }, [jobId, savedUrl]);

  function choose(job) {
    setJobId(job.id); setSheetUrl(job.response_sheet_url || ""); setSavedUrl(job.response_sheet_url || "");
    setNews(null); setCheckedAt(null); setResult(null); setUploadNotes([]); setError(""); setShow("all");
    candidatesApi.list(job.id).then(setCandidates).catch((e) => setError(e.message));
    if (job.response_sheet_url) check(job.id);      // so you know about new applications as soon as the page opens
  }

  async function saveSheet() {
    setError(""); setResult(null); setBusy("save");
    try {
      const job = await candidatesApi.saveSheet(jobId, sheetUrl.trim());
      setSavedUrl(job.response_sheet_url);
      setJobs(jobs.map((j) => (j.id === job.id ? job : j)));
      await check(jobId);
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  async function fetchNew() {
    setError(""); setResult(null); setBusy("fetch");
    try {
      setResult(await candidatesApi.fetchNew(jobId));
      setCandidates(await candidatesApi.list(jobId));
      setNews(await candidatesApi.check(jobId));
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // One request per file, so many files never make one request too large.
  async function upload(event) {
    event.preventDefault();
    setError(""); setBusy("upload");
    const notes = [];
    try {
      for (const file of files) {
        const answer = await candidatesApi.upload(jobId, file, files.length === 1 ? person : {});
        notes.push(answer);
      }
      setCandidates(await candidatesApi.list(jobId));
      setFiles([]); setPerson({ fullName: "", email: "", phone: "" });
      if (fileInput.current) fileInput.current.value = "";
    } catch (e) { setError(e.message); } finally { setUploadNotes(notes); setBusy(""); }
  }

  async function remove() {
    const candidate = toDelete;
    setToDelete(null); setError("");
    try {
      await candidatesApi.remove(candidate.id);
      setCandidates(await candidatesApi.list(jobId));
      if (savedUrl) check(jobId);
    } catch (e) { setError(e.message); }
  }

  if (!jobs) return <div className="card">{error ? <p className="error">{error}</p> : <p>Loading...</p>}</div>;
  if (jobs.length === 0) {
    return <div className="card"><p className="muted">No approved job yet. Write and approve a job in the chat on the Job Requirements page first.</p></div>;
  }
  const linkOk = sheetUrl.trim().startsWith("https://");
  const linkChanged = sheetUrl.trim() !== savedUrl;
  const shown = candidates.filter((c) => show === "all" || c.source === show);

  return (
    <>
      <div className="card">
        <label className="inline">Job{" "}
          <select value={jobId} onChange={(e) => choose(jobs.find((j) => j.id === Number(e.target.value)))}>
            {jobs.map((j) => <option key={j.id} value={j.id}>#{j.id} {j.title}</option>)}
          </select>
        </label>

        <h3>Applications from the Google Form</h3>
        <p className="muted small">Paste the link of the form's response sheet (in Google Forms: Responses, then "View in Sheets").
          The name, email, phone and CV are taken from the same row, so they always belong together.
          Your Google Drive is only read, never changed.</p>
        <label>Response sheet link
          <input value={sheetUrl} onChange={(e) => setSheetUrl(e.target.value)} placeholder="https://docs.google.com/spreadsheets/d/..." />
        </label>
        <div>
          {linkChanged && <button type="button" onClick={saveSheet} disabled={!linkOk || busy !== ""}>{busy === "save" ? "Saving..." : "Save the link"}</button>}
          {!linkChanged && savedUrl && (
            <>
              <button type="button" onClick={fetchNew} disabled={busy !== "" || !news?.ok || news.new === 0}>
                {busy === "fetch" ? "Fetching..." : news?.ok && news.new > 0 ? `Fetch new applications (${news.new})` : "Fetch new applications"}
              </button>
              <button type="button" className="secondary" onClick={() => check(jobId)} disabled={busy !== ""}>
                {busy === "check" ? "Checking..." : "Check again"}
              </button>
            </>
          )}
        </div>
        {news && !result && <p className={!news.ok ? "error" : news.new > 0 ? "warn" : "muted"}>{news.message}</p>}
        {savedUrl && !linkChanged && (
          <p className="muted small">The sheet is checked again every minute while this page is open.
            {checkedAt && <> Last checked at {checkedAt.toLocaleTimeString()}.</>}</p>
        )}
        {result && <p className={result.ok ? "ok" : "error"}>{result.message}</p>}
        {error && <p className="error">{error}</p>}
      </div>

      <div className="card">
        <h3>Upload CVs by hand <small className="muted">(for CVs received in another way)</small></h3>
        <form onSubmit={upload}>
          <label>CV files <small>(PDF, DOCX or TXT, 5 MB each; you can choose several)</small>
            <input type="file" accept=".pdf,.docx,.txt" multiple ref={fileInput} onChange={(e) => setFiles([...e.target.files])} />
          </label>
          {files.length === 1 && (
            <div className="two-columns">
              <label>Full name <small>(optional)</small>
                <input value={person.fullName} onChange={(e) => setPerson({ ...person, fullName: e.target.value })} maxLength="120" />
              </label>
              <label>Email <small>(optional)</small>
                <input value={person.email} onChange={(e) => setPerson({ ...person, email: e.target.value })} maxLength="200" />
              </label>
              <label>Phone <small>(optional)</small>
                <input value={person.phone} onChange={(e) => setPerson({ ...person, phone: e.target.value })} maxLength="40" />
              </label>
            </div>
          )}
          {files.length > 1 && <p className="muted small">{files.length} files chosen. Each file becomes one candidate without a name; choose one file at a time to type the name.</p>}
          <button className="secondary" disabled={files.length === 0 || busy !== ""}>{busy === "upload" ? "Uploading..." : "Upload"}</button>
        </form>
        {uploadNotes.map((note) => <p key={note.message} className={note.ok ? "ok" : "error"}>{note.message}</p>)}
      </div>

      <div className="card">
        <div className="row-between">
          <h3>Candidates <small className="muted">({candidates.length})</small></h3>
          {/* Form applications and hand uploads are kept apart: in the list, and in two folders on the disk. */}
          <label className="inline">Show{" "}
            <select value={show} onChange={(e) => setShow(e.target.value)}>
              <option value="all">All ({candidates.length})</option>
              <option value="google_form">From the Google Form ({candidates.filter((c) => c.source === "google_form").length})</option>
              <option value="upload">Uploaded by hand ({candidates.filter((c) => c.source === "upload").length})</option>
            </select>
          </label>
        </div>
        {shown.length === 0 ? <p className="muted">No candidates here yet.</p> : (
          <table>
            <thead><tr><th>#</th><th>Name</th><th>Email</th><th>Phone</th><th>CV file</th><th>From</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {shown.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>
                    <b>{c.full_name || "(name not given)"}</b>
                    {c.warnings.map((warning) => <div key={warning} className="warn small">{warning}</div>)}
                  </td>
                  <td className="small">{c.email}</td>
                  <td className="small">{c.phone}</td>
                  <td className="small">
                    {c.has_file ? <button className="link" onClick={() => candidatesApi.downloadCv(c).catch((e) => setError(e.message))}>{c.original_file_name || "Download"}</button>
                                : "(no file)"}
                    {c.saved_as && <div className="muted">{c.saved_as}</div>}
                  </td>
                  <td className="small"><span className={`badge ${c.source === "upload" ? "draft" : "approved"}`}>{SOURCES[c.source] || c.source}</span>
                    {c.applied_at && <div className="muted">{c.applied_at}</div>}</td>
                  <td><span className={`badge ${c.status === "new" ? "done" : "failed"}`}>{c.status === "new" ? "saved" : "needs review"}</span></td>
                  <td><button className="link" onClick={() => setToDelete(c)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {toDelete && (
        <ConfirmDialog question={`Delete ${toDelete.full_name || "this candidate"}?`}
                       detail="The saved CV file on this computer is deleted too. The file in your Google Drive is not touched."
                       onYes={remove} onNo={() => setToDelete(null)} />
      )}
    </>
  );
}
