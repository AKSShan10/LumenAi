// The identity box at the top of the candidate card in the interviewer's room (F7).
// "Check identity" takes ONE picture from the candidate's camera in this browser and sends it to the backend, which
// compares the face with the photo the candidate sent with the application and with the other
// candidates' photos. The picture is never saved. The result never decides anything: the interviewer confirms or
// rejects. The candidate's page never shows any of this.
import { useEffect, useState } from "react";
import { identityApi } from "./identityApi.js";

const RESULTS = {
  confident: ["Confident match", "done"],
  low: ["Low confidence", "draft"],
  no_match: ["No match", "failed"],
  no_face: ["No face found", "draft"],
  no_photo: ["No photo on record", ""],
  photo_unusable: ["Photo cannot be used", "draft"],
  engine_missing: ["Face check not installed", "failed"],
};
const DECISIONS = { confirmed: ["Identity confirmed", "done"], rejected: ["Not the candidate", "failed"] };

// One picture from the candidate's camera (the other person's video in the call), as a JPG
async function cameraPicture() {
  const video = document.querySelector('.lk-participant-tile[data-lk-local-participant="false"][data-lk-source="camera"] video')
    || document.querySelector(".stage-main video");
  if (!video || !video.videoWidth) throw new Error("The candidate's camera is not on. Ask the candidate to turn it on.");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
}

export default function IdentityCard({ sessionId }) {
  const [identity, setIdentity] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // → GET /api/sessions/{id}/identity (the photo itself is shown in Candidate Info)
  useEffect(() => {
    identityApi.get(sessionId).then(setIdentity).catch((e) => setError(e.message));
  }, [sessionId]);

  // "Check identity": one camera picture → POST /api/sessions/{id}/identity/check
  async function check() {
    setBusy(true); setError("");
    try { setIdentity(await identityApi.check(sessionId, await cameraPicture())); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  // Confirm / Doesn't match / Take back → PUT /api/sessions/{id}/identity/decision
  async function decide(decision) {
    setError("");
    try { setIdentity(await identityApi.decide(sessionId, decision)); } catch (e) { setError(e.message); }
  }

  if (!identity) return error ? <p className="error small">{error}</p> : null;
  const [label, tone] = DECISIONS[identity.decision] || RESULTS[identity.result] || ["Not checked yet", ""];
  return (
    <div className="identity-card">
      <div className="identity-head">
        <div>
          <div className="small muted">Identity</div>
          <span className={`badge ${tone}`}>{label}</span>
          {identity.similarity !== null && identity.similarity !== undefined && !identity.decision && (
            <span className="small muted"> similarity {identity.similarity}</span>)}
        </div>
      </div>
      {identity.message && !identity.decision && <p className="small">{identity.message}</p>}
      {identity.decision && <p className="small muted">By {identity.decided_by}{identity.decided_at &&
        ` at ${new Date(identity.decided_at).toLocaleTimeString([], { timeStyle: "short" })}`}</p>}
      {error && <p className="error small">{error}</p>}
      <div className="identity-actions">
        {!identity.decision && (
          <>
            <button type="button" className="secondary" onClick={check} disabled={busy}>
              {busy ? "Checking..." : identity.result ? "Check again" : "Check identity"}</button>
            <button type="button" className="secondary" onClick={() => decide("confirmed")}>Confirm</button>
            <button type="button" className="secondary" onClick={() => decide("rejected")}>Doesn't match</button>
          </>
        )}
        {identity.decision && <button type="button" className="link" onClick={() => decide("")}>Take back</button>}
      </div>
      <p className="small muted">The camera picture is compared once and not saved. You make the decision.</p>
    </div>
  );
}
