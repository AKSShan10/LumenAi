import { Suspense, lazy, useEffect, useState } from "react";
import { interviewsApi } from "./interviewsApi.js";
import CallChat from "./CallChat.jsx";
import AppFooter from "../../shared/utils/AppFooter.jsx";
// LiveKit is big, so the call code is loaded only when someone opens a call
const VideoRoom = lazy(() => import("./VideoRoom.jsx"));

// The candidate's page. It is opened with the private link from the invitation email (/join/<secret>),
// needs no login, and shows nothing from the interviewer's app: only their own interview and the call.
// Before the interviewer starts: wait here (the page looks again every few seconds). While live: name + Join.
// After the end: the call closes and cannot be joined again.
const LOOK_AGAIN_MS = 5000;

// The candidate's page from the invitation link (/join/<secret>): waits, then joins the call
export default function CandidateJoinPage({ joinToken }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [call, setCall] = useState(null);           // {server_url, ticket} while in the call
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(false);          // the candidate left the call themself
  const [chatOpen, setChatOpen] = useState(false);  // the chat panel: closed until the Chat button is clicked
  const [unread, setUnread] = useState(0);

  // Asks GET /api/join/{token} for the interview status; leaves the call when it has ended
  function look() {
    return interviewsApi.joinInfo(joinToken).then((answer) => {
      setInfo(answer);
      setName((typed) => typed || answer.candidate_name || "");
      if (answer.status === "ended") setCall(null);  // the interviewer ended it: leave the call
    });
  }

  useEffect(() => { look().catch((e) => setError(e.message)); }, [joinToken]);   // eslint-disable-line react-hooks/exhaustive-deps

  const status = info?.status;
  useEffect(() => {                                  // waiting for the start, or in the call: look again regularly
    if (!status || status === "ended") return undefined;
    const timer = setInterval(() => { if (!document.hidden) look().catch(() => {}); }, LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [status]);                                      // eslint-disable-line react-hooks/exhaustive-deps

  // On Join: gets a LiveKit ticket with interviewsApi.joinTicket, which opens the video call
  async function join(event) {
    event.preventDefault();
    setBusy(true); setError(""); setLeft(false);
    // → POST /api/join/{token}/ticket: gets the candidate's LiveKit ticket
    try { setCall(await interviewsApi.joinTicket(joinToken, name.trim())); }
    catch (e) { setError(e.message); look().catch(() => {}); }
    finally { setBusy(false); }
  }

  if (call) {                                       // in the call: the whole window; the chat opens at the side
    return (
      <div className="room-page">
        <header className="room-bar">
          <b>Interview · {info?.job_title}</b>
        </header>
        <div className="room-body">
          <Suspense fallback={<p className="room-note">Opening the call...</p>}>
            <VideoRoom serverUrl={call.server_url} ticket={call.ticket} waitingFor="the interviewer"
                       transcribe={{ path: `/api/join/${joinToken}/stt` }}
                       chat={{ open: chatOpen, unread, onToggle: () => setChatOpen(!chatOpen) }}
                       onLeave={() => { setCall(null); setLeft(true); }} />
          </Suspense>
          <CallChat me="candidate" open={chatOpen} onUnread={setUnread}
                    onOpen={() => setChatOpen(true)} onClose={() => setChatOpen(false)}
                    load={(after) => interviewsApi.joinChat(joinToken, after)}
                    send={(text) => interviewsApi.joinSendChat(joinToken, text)} />
        </div>
      </div>
    );
  }

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
            {info.status === "ended" && <p className="muted">This interview has ended. Thank you.</p>}
            {info.status === "scheduled" && (
              <p className="muted">The interviewer has not started yet. Keep this page open: the Join button appears when the
                interview starts. Please use a camera, a microphone and a stable internet connection.</p>
            )}
            {info.status === "live" && (
              <form onSubmit={join}>
                {left && <p className="muted small">You left the call. You can join again.</p>}
                <label htmlFor="join-name">Your name</label>
                <input id="join-name" value={name} maxLength="60" required onChange={(e) => setName(e.target.value)} />
                <button type="submit" disabled={busy || !name.trim()}>{busy ? "Joining..." : "Join the interview"}</button>
                <p className="muted small">Your browser will ask to use your camera and microphone.</p>
              </form>
            )}
          </>
        )}
      </div>
      <AppFooter />
    </div>
  );
}
