import { useEffect, useState } from "react";
import { openInNewTab } from "../../shared/api/httpClient.js";
import Icon from "../../shared/utils/Icon.jsx";
import { initials } from "./initials.js";
import IdentityCard from "../identity/IdentityCard.jsx";
import { identityApi } from "../identity/identityApi.js";

// The candidate's card at the right of the interviewer's call (never on the candidate's page).
//   Candidate Info: who the candidate is (from the application) and the key highlights of the CV
//   Evaluation:     the screening scores with their reasons, and the requirements worth asking about
// The identity box on top (F7, IdentityCard.jsx): the face check against the application photo.
// profile = the answer of GET /api/sessions/{id}/profile.
const SECTIONS = [["skills", "Skills"], ["experience", "Experience"], ["qualifications", "Qualifications"]];
const STATUS = { met: "Met", partial: "Partially met", unmet: "Unmet" };
const SOURCES = { google_form: "Google Form", upload: "Uploaded by hand" };

// The candidate card at the right of the interviewer's call, with Candidate Info and Evaluation tabs
export default function ProfilePanel({ profile, error, sessionId }) {
  const [tab, setTab] = useState("info");         // info | evaluation

  return (
    <aside className="room-card profile-panel">
      {profile && <IdentityCard sessionId={sessionId} />}
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
  const [photo, setPhoto] = useState("");          // F7: the photo from the application, if there is one
  const [bigPhoto, setBigPhoto] = useState(false); // the photo shown large after a click
  // → GET /api/candidates/{id}/photo: shown instead of the initials
  useEffect(() => {
    if (!c.has_photo) return undefined;
    let address = "";
    identityApi.photo(c.id).then((url) => { address = url; setPhoto(url); });
    return () => { if (address) URL.revokeObjectURL(address); };
  }, [c.id, c.has_photo]);
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
        {photo ? (
          <button type="button" className="photo-button" onClick={() => setBigPhoto(true)} title="Show the photo larger">
            <img src={photo} alt={c.full_name} className="avatar-photo" />
          </button>
        ) : <span className="avatar large">{initials(c.full_name)}</span>}
        <div>
          <b>{c.full_name || "(name not given)"}</b>
          <div className="muted">{latest?.title || `Applied for ${profile.job_title}`}</div>
        </div>
      </div>
      <div className="profile-lines">
        {c.email && <p><Icon name="mail" size={18} /> <a href={`mailto:${c.email}`}>{c.email}</a></p>}
        {c.phone && <p><Icon name="phone" size={18} /> <a href={`tel:${c.phone.replace(/[^\d+]/g, "")}`}>{c.phone}</a></p>}
        <p><Icon name="document" size={18} /> {latest ? `Applied for ${profile.job_title} · ` : ""}{SOURCES[c.source] || c.source}</p>
      </div>

      {bigPhoto && (                                 // the photo large, on top of the page; a click closes it
        <div className="photo-viewer" role="dialog" aria-label="Candidate photo" onClick={() => setBigPhoto(false)}>
          <img src={photo} alt={c.full_name} />
          <span className="small">{c.full_name} · click anywhere to close</span>
        </div>
      )}

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
