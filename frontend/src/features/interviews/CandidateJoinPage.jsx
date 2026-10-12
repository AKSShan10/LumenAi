import { useEffect, useState } from "react";
import { interviewsApi } from "./interviewsApi.js";
import AppFooter from "../../shared/utils/AppFooter.jsx";

// The candidate's page. It is opened with the private link from the invitation email (/join/<secret>),
// needs no login, and shows nothing from the interviewer's app: only their own interview.
// The consent notice must stay visible (requirements: consent is shown before the call).
// The video call itself is added here by the interview feature (F6).
export default function CandidateJoinPage({ joinToken }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    interviewsApi.joinInfo(joinToken).then(setInfo).catch((e) => setError(e.message));
  }, [joinToken]);

  return (
    <div className="login-page">
      <div className="card login">
        <h1>Interview</h1>
        {error && <p className="error">{error}</p>}
        {!info && !error && <p className="muted">Loading...</p>}
        {info && (
          <>
            <p>Hello {info.candidate_name || "there"}, this is your interview for <b>{info.job_title}</b>.</p>
            <p><b>{new Date(info.scheduled_at).toLocaleString([], { dateStyle: "full", timeStyle: "short" })}</b>
              {" "}(your time), about {info.duration_minutes} minutes.</p>
            <p className="consent">
              <b>Please note:</b> this interview is transcribed and analysed by AI to help the interviewer.
              A person makes every decision.
            </p>
            {info.status === "ended"
              ? <p className="muted">This interview has ended. Thank you.</p>
              : <p className="muted">The video call opens on this page at the interview time. Please come back then, with a
                  camera, a microphone and a stable internet connection.</p>}
          </>
        )}
      </div>
      <AppFooter />
    </div>
  );
}
