import { useEffect, useState } from "react";
import { jobsApi } from "./jobsApi.js";
import ConfirmDialog from "../../shared/utils/ConfirmDialog.jsx";

const MAX_CHARS = 3500;

// Posting an approved job to the Telegram channel.
// The post is the description you already approved (put together by code, no AI). It is shown read-only.
// "Edit the post" opens the text box, where you can change it or let the AI write a shorter version.
// Nothing is posted before you click "Post to Telegram" and answer Yes.
// After a post, only the result is shown; "Post again" starts over.
export default function JobPostPanel({ job }) {
  const [applyUrl, setApplyUrl] = useState("");
  const [approvedText, setApprovedText] = useState("");   // the post made from the approved job
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);          // is the text box open?
  const [fromAi, setFromAi] = useState(false);            // is the text an AI version?
  const [changeRequest, setChangeRequest] = useState("");
  const [note, setNote] = useState("");                   // what the check still wants the interviewer to look at
  const [postings, setPostings] = useState(null);
  const [again, setAgain] = useState(false);              // "Post again" was clicked
  const [asking, setAsking] = useState(false);            // the yes / no pop-up is open
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    jobsApi.postText(job.id).then((answer) => { setApprovedText(answer.text); setText(answer.text); })
      .catch((e) => setError(e.message));
    jobsApi.postings(job.id).then((list) => {
      setPostings(list);
      if (list[0]) setApplyUrl(list[0].apply_url);          // the link used last time
    }).catch((e) => setError(e.message));
  }, [job.id]);

  if (!postings) return <div className="card"><h3>Post to Telegram</h3>{error ? <p className="error">{error}</p> : <p>Loading...</p>}</div>;

  const lastPosted = postings.find((p) => p.status === "posted");
  const showResultOnly = lastPosted && !again;             // already posted: no text box, no preview
  const linkOk = applyUrl.trim().startsWith("https://");
  const tooLong = text.trim().length > MAX_CHARS;
  const message = `${text.trim()}\n\nApply here: ${applyUrl.trim() || "(paste the form link above)"}`;

  async function writeShorter() {
    setError(""); setNote(""); setBusy("write");
    try {
      // "Generate again" sends the wish and the AI version that was not liked
      const draft = fromAi ? await jobsApi.postDraft(job.id, changeRequest, text) : await jobsApi.postDraft(job.id);
      if (!draft.from_ai) return setError(draft.message);
      setText(draft.text); setNote(draft.message); setFromAi(true); setChangeRequest("");
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  function useApproved() {
    setText(approvedText); setFromAi(false); setNote(""); setChangeRequest(""); setError("");
  }

  async function post() {
    setAsking(false); setError(""); setBusy("post");
    try {
      const posting = await jobsApi.post(job.id, text.trim(), applyUrl.trim());
      setPostings([posting, ...postings]);
      if (posting.status === "failed") return setError("Telegram did not accept the post: " + posting.error);
      setAgain(false); setEditing(false); useApproved();    // back to the result view
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  const earlierPosts = postings.length > 0 && (
    <div className="section">
      <h3>Earlier posts</h3>
      <table>
        <thead><tr><th>When</th><th>Result</th><th>Details</th></tr></thead>
        <tbody>
          {postings.map((p) => (
            <tr key={p.id}>
              <td>{new Date(p.created_at).toLocaleString()}</td>
              <td><span className={`badge ${p.status === "posted" ? "done" : "failed"}`}>{p.status}</span></td>
              <td className="small">
                {p.status === "failed" ? p.error
                  : p.message_link ? <a href={p.message_link} target="_blank" rel="noreferrer">Open the post</a>
                  : "Posted to the channel"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  // ---------- already posted: only the result ----------
  if (showResultOnly) {
    return (
      <div className="card">
        <h3>Post to Telegram</h3>
        <p className="ok">This job was posted to the Telegram channel on {new Date(lastPosted.created_at).toLocaleString()}.</p>
        <button type="button" className="secondary" onClick={() => setAgain(true)}>Post again</button>
        {earlierPosts}
      </div>
    );
  }

  // ---------- not posted yet (or "Post again") ----------
  return (
    <div className="card">
      <h3>Post to Telegram</h3>
      <p className="muted small">The post is the description you approved. Paste the form link, read the post and click Post to Telegram.</p>

      <label>Application form link <small>(the Google Form the candidates fill in)</small>
        <input value={applyUrl} onChange={(e) => setApplyUrl(e.target.value)} placeholder="https://docs.google.com/forms/..." />
      </label>

      {!editing ? (
        <>
          <p className="muted small">This will appear in the channel, with an "Apply now" button under it
            {fromAi ? " (shorter version written by the AI)" : text !== approvedText ? " (edited by you)" : ""}:</p>
          <p className="description">{message}</p>
        </>
      ) : (
        <>
          <label>Post text <small>({text.trim().length} / {MAX_CHARS} characters; the form link is added below it)</small>
            <textarea rows="10" value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          {fromAi && (
            <label>What should change? <small>(optional)</small>
              <input value={changeRequest} onChange={(e) => setChangeRequest(e.target.value)} maxLength="500"
                     placeholder="Even shorter, friendlier, start with the team" />
            </label>
          )}
          <div>
            <button type="button" className="secondary" onClick={writeShorter} disabled={busy !== ""}>
              {busy === "write" ? "The AI is writing..." : fromAi ? "Generate again" : "Make a shorter version with AI"}
            </button>
            {text !== approvedText && <button type="button" className="link" onClick={useApproved}>Use the approved description</button>}
          </div>
          {note && <p className="warn">{note}</p>}
        </>
      )}
      {tooLong && <p className="warn">The post is too long for one message. Edit it, or let the AI write a shorter version.</p>}
      {error && <p className="error">{error}</p>}

      <div>
        {editing ? <button type="button" className="secondary" onClick={() => setEditing(false)} disabled={text.trim().length < 20}>Done editing</button>
                 : <button type="button" className="secondary" onClick={() => setEditing(true)} disabled={busy !== ""}>Edit the post</button>}
        {!editing && (
          <button type="button" onClick={() => setAsking(true)} disabled={!linkOk || tooLong || text.trim().length < 20 || busy !== ""}>
            {busy === "post" ? "Posting..." : "Post to Telegram"}
          </button>
        )}
        {again && <button type="button" className="link" onClick={() => { setAgain(false); setEditing(false); useApproved(); }}>Cancel</button>}
        {!editing && !linkOk && <span className="muted small"> Paste the form link first (it starts with https://).</span>}
      </div>

      {asking && (
        <ConfirmDialog question="Post this job to the Telegram channel?"
                       detail="Everyone in the channel will see it. A post cannot be taken back from here."
                       onYes={post} onNo={() => setAsking(false)} />
      )}
      {earlierPosts}
    </div>
  );
}
