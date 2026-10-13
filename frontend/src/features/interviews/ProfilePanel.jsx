import { useState } from "react";
import { openInNewTab } from "../../shared/api/httpClient.js";
import Icon from "../../shared/utils/Icon.jsx";
import { initials } from "./initials.js";

// The candidate's card at the right of the interviewer's call (never on the candidate's page).
//   Candidate Info: who the candidate is (from the application) and the key highlights of the CV
//   Evaluation:     the screening scores with their reasons, and the requirements worth asking about
// No photo and no identity check: the avatar shows the initials.
// profile = the answer of GET /api/sessions/{id}/profile.
const SECTIONS = [["skills", "Skills"], ["experience", "Experience"], ["qualifications", "Qualifications"]];
const STATUS = { met: "Met", partial: "Partially met", unmet: "Unmet" };
const SOURCES = { google_form: "Google Form", upload: "Uploaded by hand" };

// The candidate card at the right of the interviewer's call, with Candidate Info and Evaluation tabs
export default function ProfilePanel({ profile, error }) {
  const [tab, setTab] = useState("info");         // info | evaluation

  return (
    <aside className="room-card profile-panel">
      <div className="profile-tabs">
        <button type="button" className={tab === "info" ? "active" : ""} onClick={() => setTab("info")}>Candidate Info</button>
        <button type="button" className={tab === "evaluation" ? "active" : ""} onClick={() => setTab("evaluation")}>Evaluation</button>
      </div>
      <div className="profile-body">
        {error && <p className="error small">{error}</p>}
        {!profile && !error && <p className="muted small">Loading...</p>}
        {profile && (tab === "info" ? <Info profile={profile} /> : <Evaluation profile={profile} />)}
      </div>
    </aside>
  );
}

// Candidate Info tab: contact details, key CV highlights and an Open CV button
function Info({ profile }) {
  const c = profile.candidate;
  const s = profile.screening;
  const [latest, previous] = profile.jobs;
  const degree = profile.degrees[0];
  const [problem, setProblem] = useState("");
  // Shows a job as "title at company", or only the title when there is no company
  const role = (job) => (job.company ? `${job.title} at ${job.company}` : job.title);
  const highlights = [
    ["calendar", s && `${s.total_years} years of experience`],
    ["code", s?.skills.slice(0, 6).join(", ")],
    ["cap", degree && [degree.degree, degree.institute].filter(Boolean).join(", ")],
    ["briefcase", previous ? `Previous role: ${role(previous)}` : latest && `Role: ${role(latest)}`],
  ].filter(([, text]) => text);

  return (
    <>
      <div className="profile-person">
        <span className="avatar large">{initials(c.full_name)}</span>
        <div>
          <b>{c.full_name || "(name not given)"}</b>
          <div className="muted">{latest?.title || `Applied for ${profile.job_title}`}</div>
        </div>
      </div>
      <div className="profile-lines">
        {c.email && <p><Icon name="mail" size={18} /> {c.email}</p>}
        {c.phone && <p><Icon name="phone" size={18} /> {c.phone}</p>}
        <p><Icon name="document" size={18} /> {latest ? `Applied for ${profile.job_title} · ` : ""}{SOURCES[c.source] || c.source}</p>
      </div>

      <h4>Key Highlights from CV</h4>
      {highlights.length === 0 && <p className="muted small">The CV has not been screened yet.</p>}
      <div className="profile-lines">
        {highlights.map(([icon, text]) => <p key={icon}><Icon name={icon} size={18} /> {text}</p>)}
      </div>

      {c.has_file && (
        <button type="button" className="secondary"
                onClick={() => { setProblem(""); openInNewTab(`/api/candidates/${c.id}/cv`, c.original_file_name).catch((e) => setProblem(e.message)); }}>
          Open CV</button>
      )}
      {problem && <p className="error small">{problem}</p>}
    </>
  );
}

// Evaluation tab: the screening scores with reasons and the requirements worth asking about
function Evaluation({ profile }) {
  const s = profile.screening;
  if (!s) return <p className="muted small">The CV has not been screened, so there is no result.</p>;
  const toAsk = s.matches.filter((m) => m.status === "unmet" || m.status === "partial");
  return (
    <>
      <p className="profile-score"><b>{s.weighted_score ?? "-"}</b> <span className="muted">final score of 100</span></p>
      {SECTIONS.map(([key, label]) => {
        const part = s.sections[key] || {};
        return (
          <div key={key} className="profile-section">
            <div><b>{label}</b> {part.score ?? "-"} <span className="muted small">(weight {profile.weights[key]}%)</span></div>
            {part.reason && <div className="small">{part.reason}</div>}
          </div>
        );
      })}
      <h4>Worth asking about</h4>
      {toAsk.length === 0 ? <p className="muted small">The CV showed every requirement.</p> : (
        <ul className="profile-ask">
          {toAsk.map((m) => (
            <li key={m.requirement}>
              <b>{m.requirement}</b>{m.kind === "must" && " (must-have)"}: {STATUS[m.status]}
              {m.how && <div className="muted small">{m.how}</div>}
            </li>
          ))}
        </ul>
      )}
      {s.decision && <p className="muted small">A person decided: {s.decision}{s.decision_note && ` (${s.decision_note})`}</p>}
    </>
  );
}
