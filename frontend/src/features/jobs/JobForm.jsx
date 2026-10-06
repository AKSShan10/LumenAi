import { useState } from "react";
import { jobsApi } from "./jobsApi.js";

// Turns "Python, FastAPI , Docker" into ["Python", "FastAPI", "Docker"]
const toList = (text) => text.split(",").map((s) => s.trim()).filter(Boolean);

// Step 1: write a short prompt and let the AI fill the form (it follows the company documents).
//         Not happy with the answer? Say what should change and click "Generate again".
// Step 2: check and change every field. Then save. Nothing is saved until "Save job" is clicked.
export default function JobForm({ job, onSaved, onCancel }) {
  const [prompt, setPrompt] = useState(job?.prompt || "");
  const [title, setTitle] = useState(job?.title || "");
  const [required, setRequired] = useState((job?.required_skills || []).join(", "));
  const [preferred, setPreferred] = useState((job?.preferred_skills || []).join(", "));
  const [minYears, setMinYears] = useState(job?.min_years ?? 0);
  const [qualifications, setQualifications] = useState(job?.qualifications || "");
  const [description, setDescription] = useState(job?.description || "");
  const [used, setUsed] = useState(null);       // what the AI followed: { examples, policies, revisions }
  const [note, setNote] = useState("");         // what the check still wants the interviewer to look at
  const [generated, setGenerated] = useState(false);     // has the AI answered at least once on this form?
  const [changeRequest, setChangeRequest] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function fillFromPrompt() {
    setError(""); setNote(""); setUsed(null);
    if (prompt.trim().length < 10) return setError("Write a few words about the job first.");
    setBusy("prompt");
    try {
      // "Generate again" sends the wish and the description that was not liked
      const draft = generated ? await jobsApi.draftFromPrompt(prompt, changeRequest, description)
                              : await jobsApi.draftFromPrompt(prompt);
      if (!draft.from_ai) return setError(draft.message);
      setTitle(draft.title); setRequired(draft.required_skills.join(", ")); setPreferred(draft.preferred_skills.join(", "));
      setMinYears(draft.min_years); setQualifications(draft.qualifications); setDescription(draft.description);
      setUsed({ examples: draft.examples, policies: draft.policies, revisions: draft.revisions });
      setNote(draft.message);
      setGenerated(true); setChangeRequest("");
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  async function save(event) {
    event.preventDefault();
    setError("");
    if (toList(required).length === 0) return setError("Add at least one required skill.");
    setBusy("save");
    try {
      const body = { title, description, required_skills: toList(required), preferred_skills: toList(preferred),
                     min_years: Number(minYears), qualifications, prompt };
      onSaved(job ? await jobsApi.update(job.id, body) : await jobsApi.create(body));
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  return (
    <form className="card" onSubmit={save}>
      <h2>{job ? `Edit job: ${job.title}` : "Create a job profile"}</h2>
      {job?.status === "approved" && <p className="muted small">Saving changes makes this job a draft again; approve it once more afterwards.</p>}

      <label>Step 1 · Describe the job in a few sentences
        <textarea rows="3" value={prompt} onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Backend developer with Python, FastAPI and Docker, 3 years experience, BSc in CSE" />
      </label>
      {generated && (
        <label>What should change? <small>(optional)</small>
          <input value={changeRequest} onChange={(e) => setChangeRequest(e.target.value)} maxLength="500"
                 placeholder="Shorter, more focus on teamwork, mention remote work" />
        </label>
      )}
      <button type="button" className="secondary" onClick={fillFromPrompt} disabled={busy !== ""}>
        {busy === "prompt" ? "The AI is writing..." : generated ? "Generate again" : "Fill the form with AI"}
      </button>
      {generated && <span className="muted small"> A new answer replaces the fields below. Nothing is saved until you click Save job.</span>}
      {used && (
        <p className="muted small">
          {used.examples.length > 0 ? <>Written in the style of: {used.examples.join(" · ")}. </> : "No similar past job description was found. "}
          {used.policies.length > 0 && <>Company policy followed: {used.policies.join(" · ")}. </>}
          {used.revisions > 0 && <>The check sent the draft back to the AI {used.revisions} time(s).</>}
        </p>
      )}
      {note && <p className="warn">{note}</p>}

      <p className="muted small">Step 2 · Check and change the fields below. The AI only suggests; you decide.</p>
      <label>Job title
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Backend Developer" required />
      </label>
      <label>Required skills <small>(comma separated)</small>
        <input value={required} onChange={(e) => setRequired(e.target.value)} placeholder="Python, REST APIs, SQL" />
      </label>
      <label>Preferred skills <small>(comma separated, optional)</small>
        <input value={preferred} onChange={(e) => setPreferred(e.target.value)} placeholder="Docker, AWS" />
      </label>
      <div className="two-columns">
        <label>Minimum years of experience
          <input type="number" min="0" max="50" value={minYears} onChange={(e) => setMinYears(e.target.value)} />
        </label>
        <label>Qualifications <small>(optional)</small>
          <input value={qualifications} onChange={(e) => setQualifications(e.target.value)} placeholder="BSc in Computer Science or similar" />
        </label>
      </div>
      <label>Job description
        <textarea rows="9" value={description} onChange={(e) => setDescription(e.target.value)}
                  placeholder="Let the AI write it from the prompt above, or write it yourself." />
      </label>

      {error && <p className="error">{error}</p>}
      <div>
        <button disabled={busy !== ""}>{busy === "save" ? "Saving..." : "Save job"}</button>
        {onCancel && <button type="button" className="link" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}
