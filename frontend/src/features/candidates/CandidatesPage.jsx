import { useEffect, useRef, useState } from "react";
import { jobsApi } from "../jobs/jobsApi.js";
import { candidatesApi } from "./candidatesApi.js";
import ConfirmDialog from "../../shared/utils/ConfirmDialog.jsx";
import DataTable from "../../shared/utils/DataTable.jsx";
import ScreeningCard from "../screening/ScreeningCard.jsx";
import DecisionControl from "../screening/DecisionControl.jsx";
import { screeningApi } from "../screening/screeningApi.js";
import { SectionHead, StepTabs } from "./StepTabs.jsx";
import JobPicker from "../../shared/utils/JobPicker.jsx";
import { currentJob } from "../../shared/utils/currentJob.js";

const SOURCES = { google_form: "Google Form", upload: "Uploaded by hand" };
const CHECK_EVERY_MS = 60000;      // the job's Google Form is looked at again every minute
const TAB_KEY = "lumenai.candidatesTab";   // the last open tab is remembered in this browser

// The tab that was open last time, or Applications (the browser may block storage, so try/catch)
function lastTab() {
  try { return localStorage.getItem(TAB_KEY) || "applications"; } catch { return "applications"; }
}

// The Candidates page: pick an approved job, see how many new applications are in its Google Form (the form of
// the job's "Apply now" link, given when the job was posted), fetch them (the CV files are saved on this
// computer), or upload CVs by hand. Each application is ONE form answer, so a person is always shown with their own CV.
// The page has one tab per hiring step: Applications → Included / Excluded → Shortlist, each in its own color.
// "All jobs" (no job chosen) shows everyone who applied to any job; choosing a job opens the steps and the actions.
// The job chosen here is opened on the other pages too (currentJob.js).
const STATE = { waiting: ["waiting", ""], needs_review: ["needs a look", "draft"], included: ["included", "done"],
  excluded: ["excluded", "failed"] };
export default function CandidatesPage() {
  const [jobs, setJobs] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [news, setNews] = useState(null);           // answer of the last check: how many are new
  const [checkedAt, setCheckedAt] = useState(null); // when the form was last looked at
  const [show, setShow] = useState("all");          // which candidates the list shows: all | google_form | upload
  const [result, setResult] = useState(null);       // answer of the last fetch
  const [candidates, setCandidates] = useState([]);
  const [everyone, setEveryone] = useState([]);     // All jobs: every candidate with the job title
  const [person, setPerson] = useState({ fullName: "", email: "", phone: "" });
  const [files, setFiles] = useState([]);
  const [photo, setPhoto] = useState(null);         // F7: the candidate's photo for the identity check (optional)
  const [uploadNotes, setUploadNotes] = useState([]);
  const [toDelete, setToDelete] = useState(null);   // the candidate the yes / no pop-up asks about
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState(lastTab);           // applications | included | excluded | shortlist
  const [counts, setCounts] = useState({});         // included / excluded / shortlist, told by the ScreeningCard
  const fileInput = useRef(null);
  const photoInput = useRef(null);
  const busyRef = useRef("");                        // the timer reads this to see whether something is running
  busyRef.current = busy;

  useEffect(() => {
    jobsApi.list().then((list) => {
      const approved = list.filter((j) => j.status === "approved");
      setJobs(approved);
      choose(approved.find((j) => j.id === currentJob.get(approved)) || null);   // the job chosen on another page
    }).catch((e) => setError(e.message));
  }, []);

  // Asks the backend how many form answers are new. Only the answers after the checkpoint count; nothing is downloaded.
  async function check(id) {
    setBusy("check");
    try { setNews(await candidatesApi.check(id)); setCheckedAt(new Date()); }
    catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // For the rare case that answers were deleted in the form: looks at every answer again, from the first one.
  async function recheck() {
    setError(""); setResult(null); setBusy("recheck");
    try { setNews(await candidatesApi.recheck(jobId)); setCheckedAt(new Date()); }
    catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // Looks at the form again every minute while this page is open, so the number of new applications
  // stays up to date without a click. It only counts: the CVs are downloaded when you click Fetch.
  const formReady = Boolean(news?.ok);
  useEffect(() => {
    if (!jobId || !formReady) return undefined;
    const timer = setInterval(() => {
      if (document.hidden || busyRef.current !== "") return;      // not while the tab is in the background or busy
      candidatesApi.check(jobId).then((answer) => { setNews(answer); setCheckedAt(new Date()); setResult(null); }).catch(() => {});
    }, CHECK_EVERY_MS);
    return () => clearInterval(timer);                             // stops when you leave the page or change the job
  }, [jobId, formReady]);

  // Picks a job: clears old messages, loads its candidates and checks its Google Form for new answers.
  // null = All jobs: loads everyone (→ GET /api/candidates); the form and the uploads need a job.
  function choose(job) {
    setNews(null); setCheckedAt(null); setResult(null); setUploadNotes([]); setError(""); setShow("all");
    if (!job) {
      setJobId(null);
      candidatesApi.listAll().then(setEveryone).catch((e) => setError(e.message));
      return;
    }
    currentJob.set(job.id);
    setJobId(job.id);
    candidatesApi.list(job.id).then(setCandidates).catch((e) => setError(e.message));
    check(job.id);                                  // so you know about new applications as soon as the page opens
  }

  // On Fetch: downloads the new form applications, then reloads the candidates and the new count
  async function fetchNew() {
    setError(""); setResult(null); setBusy("fetch");
    try {
      setResult(await candidatesApi.fetchNew(jobId));  // → POST /api/jobs/{id}/applications/fetch: downloads the new CVs
      setCandidates(await candidatesApi.list(jobId));
      setNews(await candidatesApi.check(jobId));
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // On Upload: one CV with the person's name, email, phone and (optional) photo becomes one candidate
  async function upload(event) {
    event.preventDefault();
    if (!files[0] || !person.fullName.trim() || !person.email.trim() || !person.phone.trim()) {
      setUploadNotes([{ ok: false, message: "Choose the CV and fill in the full name, email and phone." }]);
      return;
    }
    setError(""); setBusy("upload");
    const notes = [];
    try {
      const answer = await candidatesApi.upload(jobId, files[0], person, photo);   // one person, one CV
      notes.push(answer);
      setCandidates(await candidatesApi.list(jobId));
      if (answer.ok) {
        setFiles([]); setPhoto(null); setPerson({ fullName: "", email: "", phone: "" });
        if (fileInput.current) fileInput.current.value = "";
        if (photoInput.current) photoInput.current.value = "";
      }
    } catch (e) { setError(e.message); } finally { setUploadNotes(notes); setBusy(""); }
  }

  // On Screen again: asks the backend to screen this one CV again, then reloads the candidates
  async function screenAgain(candidate) {
    setError(""); setBusy(`screen-${candidate.id}`);
    setResult({ ok: true, message: `Screening ${candidate.full_name || "this candidate"}...` });
    try { setResult(await screeningApi.screenOne(candidate.id)); setCandidates(await candidatesApi.list(jobId)); }
    catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  // After Yes in the pop-up: deletes the candidate with candidatesApi.remove and reloads the list
  async function remove() {
    const candidate = toDelete;
    setToDelete(null); setError("");
    try {
      await candidatesApi.remove(candidate.id);
      setCandidates(await candidatesApi.list(jobId));
      if (formReady) check(jobId);
    } catch (e) { setError(e.message); }
  }

  // Opens a tab and remembers it for next time
  function pick(key) {
    setTab(key);
    try { localStorage.setItem(TAB_KEY, key); } catch { /* storage blocked: only not remembered */ }
  }

  if (!jobs) return <div className="card">{error ? <p className="error">{error}</p> : <p>Loading...</p>}</div>;
  if (jobs.length === 0) {
    return <div className="card"><p className="muted">No approved job yet. Write and approve a job in the chat on the Jobs page first.</p></div>;
  }
  if (!jobId) {                                     // All jobs: an overview; the steps and actions need a job
    return (
      <div className="card">
        <div className="row-between">
          <h3>All candidates <small className="muted">({everyone.length})</small></h3>
          <JobPicker id="candidates-job" jobs={jobs} value={null}
                     onChange={(id) => choose(jobs.find((j) => j.id === id) || null)} />
        </div>
        <p className="muted small">Everyone who applied to any job, newest first. Choose a job to fetch applications, upload
          CVs, see the screening steps and make the shortlist.</p>
        {error && <p className="error">{error}</p>}
        <DataTable rows={everyone} empty="No candidates yet." columns={[
          { key: "name", title: "Name", render: (c) => <b>{c.full_name || "(name not given)"}</b> },
          { key: "job", title: "Job", className: "small", render: (c) => (
            <button type="button" className="link" title="Open this job"
                    onClick={() => choose(jobs.find((j) => j.id === c.job_id) || null)}>{c.job_title}</button>) },
          { key: "email", title: "Email", className: "small" },
          { key: "state", title: "Screening", className: "small", render: (c) => (
            <span className={`badge ${STATE[c.screening_state]?.[1] || ""}`}>{STATE[c.screening_state]?.[0] || c.screening_state}</span>) },
          { key: "from", title: "From", className: "small", render: (c) => (
            <>{SOURCES[c.source] || c.source}{c.applied_at && <div className="muted">{c.applied_at}</div>}</>) },
        ]} />
      </div>
    );
  }
  const shown = candidates.filter((c) => show === "all" || c.source === show);
  // The # column: 1 for the oldest candidate of this job, then 2, 3 ... with no gaps, also after a delete.
  // The list comes newest first, so the newest one gets the highest number.
  const serial = (candidate) => candidates.length - candidates.indexOf(candidate);
  const needsLook = candidates.filter((c) => c.screening_state === "needs_review").length;
  const waiting = candidates.filter((c) => c.screening_state === "waiting").length;

  const screening = (
    <ScreeningCard jobId={jobId} candidates={candidates} view={tab} onCounts={setCounts} onOpen={pick}
                   onScreened={() => candidatesApi.list(jobId).then(setCandidates).catch((e) => setError(e.message))} />
  );

  return (
    <>
      <div className="card page-top">
        <div className="job-pick">
          <JobPicker id="candidates-job" jobs={jobs} value={jobId}
                     onChange={(id) => choose(jobs.find((j) => j.id === id) || null)} />
        </div>
        <StepTabs active={tab} onPick={pick}
                  counts={{ applications: candidates.length, ...counts }}
                  extra={{ applications: needsLook > 0 ? `${needsLook} need a look` : waiting > 0 ? `${waiting} waiting` : "",
                           included: counts.included > 0 ? "ready to shortlist" : "",
                           shortlist: counts.shortlist > 0 ? "for the interview" : "" }} />
      </div>
      {result && <p className={`page-note ${result.ok ? "ok" : "error"}`}>{result.message}</p>}
      {error && <p className="page-note error">{error}</p>}

      {/* The screening card keeps watching the screening. On Applications it shows only the screening progress, placed
          after the Fetch and Upload cards (CVs come in first, then they are screened); on the other tabs it shows
          that list, right under the tabs. */}
      {tab !== "applications" && screening}

      {tab === "applications" && (<>
        <div className="add-grid">
          <div className="card add-card">
            <h3>Applications from the Google Form</h3>
            <p className="muted small">The answers are read from the job's Google Form: the "Apply now" link given when the job
              was posted in the Assistant chat. No sheet link is needed. The name, email, phone and CV are taken from the same
              answer, so they always belong together. Your Google Drive is only read, never changed.</p>
            {news?.form_link && <p className="small">Form: <a href={news.form_link} target="_blank" rel="noreferrer">{news.form_link}</a></p>}
            <div>
              <button type="button" onClick={fetchNew} disabled={busy !== "" || !news?.ok || news.new === 0}>
                {busy === "fetch" ? "Fetching..." : news?.ok && news.new > 0 ? `Fetch new applications (${news.new})` : "Fetch new applications"}
              </button>
              <button type="button" className="secondary" onClick={() => check(jobId)} disabled={busy !== ""}>
                {busy === "check" ? "Checking..." : "Check again"}
              </button>
            </div>
            {news && !result && <p className={!news.ok ? "error" : news.new > 0 ? "warn" : "muted"}>{news.message}</p>}
            {formReady && (
              <p className="muted small">Every minute, while this page is open, only the answers after the checkpoint are looked at.
                {" "}Checkpoint: {news.checkpoint_row - 1} answer(s) finished.
                {checkedAt && <> Last checked at {checkedAt.toLocaleTimeString()}.</>}
                {" "}<button type="button" className="link" onClick={recheck} disabled={busy !== ""}>
                  {busy === "recheck" ? "Checking every answer..." : "Check every answer again"}</button></p>
            )}
          </div>

          <div className="card add-card">
            <h3>Upload a CV by hand <small className="muted">(for CVs received in another way)</small></h3>
            <form onSubmit={upload}>
              {/* One candidate per upload: the contact details are needed to invite the person */}
              <div className="two-columns">
                <label>CV file <small>(PDF, DOCX, DOC or TXT, up to 5 MB)</small>
                  <input type="file" accept=".pdf,.docx,.doc,.txt" required ref={fileInput}
                         onChange={(e) => setFiles([...e.target.files].slice(0, 1))} />
                </label>
                <label>Photo <small>(JPG or PNG, for the identity check in the interview)</small>
                  <input type="file" accept=".jpg,.jpeg,.png,.webp,image/*" ref={photoInput}
                         onChange={(e) => setPhoto(e.target.files[0] || null)} />
                </label>
                <label>Full name
                  <input value={person.fullName} required onChange={(e) => setPerson({ ...person, fullName: e.target.value })} maxLength="120" />
                </label>
                <label>Email
                  <input type="email" value={person.email} required onChange={(e) => setPerson({ ...person, email: e.target.value })} maxLength="200" />
                </label>
                <label>Phone
                  <input type="tel" value={person.phone} required onChange={(e) => setPerson({ ...person, phone: e.target.value })} maxLength="40" />
                </label>
              </div>
              <button className="secondary" disabled={busy !== ""}>{busy === "upload" ? "Uploading..." : "Upload"}</button>
            </form>
            {uploadNotes.map((note) => <p key={note.message} className={note.ok ? "ok" : "error"}>{note.message}</p>)}
          </div>
        </div>

        {screening}

        <div className="card section tone-slate">
          <SectionHead step="applications" count={candidates.length}
                       text="Everyone who applied for this job. New CVs are screened by themselves; the result goes to Included or Excluded.">
            {/* Form applications and hand uploads are kept apart: in the list, and in two folders on the disk. */}
            <label className="inline">Show{" "}
              <select value={show} onChange={(e) => setShow(e.target.value)}>
                <option value="all">All ({candidates.length})</option>
                <option value="google_form">From the Google Form ({candidates.filter((c) => c.source === "google_form").length})</option>
                <option value="upload">Uploaded by hand ({candidates.filter((c) => c.source === "upload").length})</option>
              </select>
            </label>
          </SectionHead>
          <DataTable rows={shown} empty="No candidates here yet." columns={[
            { key: "number", title: "#", render: (c) => serial(c) },
            { key: "name", title: "Name", render: (c) => (
              <>
                <b>{c.full_name || "(name not given)"}</b>
                {c.warnings.map((warning) => <div key={warning} className="warn small">{warning}</div>)}
                {/* Screened CVs are shown in the Screening card below. Here only: not screened yet, or needs a look. */}
                {c.screening_state === "waiting" && <div><span className="badge">waiting for screening</span></div>}
                {c.screening_state === "needs_review" && (
                  <div className="small">
                    <span className="badge draft">needs a look</span>
                    <div className="warn small">{c.screening_reason}</div>
                    <button className="link" onClick={() => screenAgain(c)} disabled={busy !== ""}>
                      {busy === `screen-${c.id}` ? "Screening..." : "Screen again"}</button>{" "}
                    <DecisionControl candidateId={c.id} final="needs_review" decided={false}
                                     onDone={(answer) => { setResult(answer); candidatesApi.list(jobId).then(setCandidates); }} />
                  </div>
                )}
              </>
            ) },
            { key: "email", title: "Email", className: "small" },
            { key: "phone", title: "Phone", className: "small" },
            { key: "cv", title: "CV file", className: "small", render: (c) => (
              <>
                {c.has_file ? (
                  <>
                    <div>{c.original_file_name || "CV file"}</div>
                    <button className="link" onClick={() => candidatesApi.viewCv(c).catch((e) => setError(e.message))}>View CV</button>{" · "}
                    <button className="link" onClick={() => candidatesApi.downloadCv(c).catch((e) => setError(e.message))}>Download</button>
                  </>
                ) : "(no file)"}
                {c.saved_as && <div className="muted">{c.saved_as}</div>}
                {c.text_source === "ai_read" && <div className="muted">Text read by the AI from the PDF during screening (scanned or picture CV)</div>}
              </>
            ) },
            { key: "from", title: "From", className: "small", render: (c) => (
              <>
                <span className={`badge ${c.source === "upload" ? "draft" : "approved"}`}>{SOURCES[c.source] || c.source}</span>
                {c.applied_at && <div className="muted">{c.applied_at}</div>}
              </>
            ) },
            { key: "delete", title: "", render: (c) => <button className="link" onClick={() => setToDelete(c)}>Delete</button> },
          ]} />
        </div>
      </>)}

      {toDelete && (
        <ConfirmDialog question={`Delete ${toDelete.full_name || "this candidate"}?`}
                       detail="The saved CV file on this computer is deleted too. The file in your Google Drive is not touched."
                       onYes={remove} onNo={() => setToDelete(null)} />
      )}
    </>
  );
}
