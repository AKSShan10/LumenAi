import { Suspense, lazy, useEffect, useState } from "react";
import { auth } from "../../shared/api/authToken.js";
import { interviewsApi } from "./interviewsApi.js";
import CallChat from "./CallChat.jsx";
import LiveTranscript from "./LiveTranscript.jsx";
import ProfilePanel from "./ProfilePanel.jsx";

// LiveKit is big, so the call code is loaded only when the call opens
const VideoRoom = lazy(() => import("./VideoRoom.jsx"));

// The interviewer's call, in its own browser tab (/interview-room/<id>), opened from the Interviews page.
// It starts the call (or joins it again) and shows, like the HireAI design:
//   top:   who the interview is with, the time since the start, "End interview for both"
//   left:   two tabs: Live Transcript (both microphones, speaker and time) and Chat (text and links)
//   center: the candidate big and yourself small, in the shape of a camera picture (16:9), buttons on top of it
//   right:  the candidate's card (Candidate Info / Evaluation) - only the interviewer sees it
// The tab gets a copy of the login from the tab that opened it.
export default function InterviewRoomPage({ sessionId }) {
  const [call, setCall] = useState(null);           // {server_url, ticket, session}
  const [state, setState] = useState("opening");    // opening | in_call | left | ended | error
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState(null);     // the candidate's profile (only the interviewer gets it)
  const [profileError, setProfileError] = useState("");
  const [tab, setTab] = useState("transcript");    // transcript | chat
  const [sttStatus, setSttStatus] = useState("");   // listening | connecting | an error in plain words
  const [unread, setUnread] = useState(0);         // new chat messages while the Transcript tab is open

  // Starts or rejoins the call (interviewsApi.start), then loads the candidate's profile card
  async function open() {
    setState("opening"); setError("");
    try {
      // → POST /api/sessions/{id}/start: gets the LiveKit server URL and ticket
      const answer = await interviewsApi.start(sessionId);
      setCall(answer); setState("in_call");
      // → GET /api/sessions/{id}/profile: loads the candidate card
      interviewsApi.profile(sessionId).then(setProfile).catch((e) => setProfileError(e.message));
      document.title = `Interview: ${answer.session.candidate_name || "candidate"}`;
    } catch (e) { setError(e.message); setState("error"); }
  }

  useEffect(() => { if (auth.get()) open(); }, [sessionId]);   // eslint-disable-line react-hooks/exhaustive-deps

  // On End interview for both: calls interviewsApi.end, which closes the call for everyone
  async function endForBoth() {
    setBusy(true);
    // → POST /api/sessions/{id}/end: closes the call for both people
    try { await interviewsApi.end(sessionId); setState("ended"); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  if (!auth.get()) {
    return <div className="room-message"><p>Please open the interview from the Interviews page of LumenAI (you need to be logged in).</p></div>;
  }

  const who = call?.session;
  return (
    <div className="room-page light">
      <header className="room-bar">
        <div>
          <b>{who ? `Interview with ${who.candidate_name || "the candidate"}` : "Interview"}</b>
          {who && <div className="room-sub">{who.job_title}</div>}
        </div>
        {state === "in_call" && (
          <div className="room-actions">
            <Elapsed since={who?.started_at} />
            <button type="button" className="end-button" onClick={endForBoth} disabled={busy}>
              {busy ? "Ending..." : "End interview for both"}</button>
          </div>
        )}
      </header>

      {error && <p className="error room-note">{error}</p>}
      {state === "opening" && <p className="room-note">Opening the call...</p>}
      {state === "in_call" && (
        <div className="room-grid">
          <div className="room-card room-talk">
            <div className="profile-tabs">
              <button type="button" className={tab === "transcript" ? "active" : ""} onClick={() => setTab("transcript")}>
                Live Transcript</button>
              <button type="button" className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
                Chat{unread > 0 && tab !== "chat" && <span className="tab-count">{unread}</span>}</button>
            </div>
            <LiveTranscript sessionId={sessionId} status={sttStatus} hidden={tab !== "transcript"}
                            names={{ candidate: who?.candidate_name }} />
            <CallChat me="interviewer" open={tab === "chat"} embedded onUnread={setUnread} onOpen={() => setTab("chat")}
                      load={(after) => interviewsApi.chat(sessionId, after)}
                      send={(text) => interviewsApi.sendChat(sessionId, text)} />
          </div>
          <div className="room-center">
            <div className="room-card room-stage">
              <Suspense fallback={<p className="room-note">Opening the call...</p>}>
                <VideoRoom serverUrl={call.server_url} ticket={call.ticket} waitingFor="the candidate" layout="pair"
                           transcribe={{ path: `/api/sessions/${sessionId}/stt`, login: auth.get(), onStatus: setSttStatus }}
                           onLeave={() => setState((s) => (s === "ended" ? s : "left"))} />
              </Suspense>
            </div>
          </div>
          <ProfilePanel profile={profile} error={profileError} />
        </div>
      )}
      {state === "left" && (
        <div className="room-message">
          <p>You left the call. It stays open for the candidate until you end it.</p>
          <p><button type="button" onClick={open}>Join again</button>{" "}
            <button type="button" className="danger" onClick={endForBoth} disabled={busy}>End interview for both</button></p>
        </div>
      )}
      {state === "ended" && (
        <div className="room-message"><p>The interview has ended. You can close this tab.</p></div>
      )}
    </div>
  );
}

// The time since the interviewer started the call, e.g. 00:24:18 (nothing is recorded)
function Elapsed({ since }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (!since) return null;
  const seconds = Math.max(0, Math.floor((now - new Date(since).getTime()) / 1000));
  // Writes a number with two digits, e.g. 7 -> "07", for the timer
  const two = (n) => String(n).padStart(2, "0");
  return (
    <span className="room-timer" title="Time since the interview started. Nothing is recorded.">
      <span className="room-timer-dot" />{two(Math.floor(seconds / 3600))}:{two(Math.floor(seconds / 60) % 60)}:{two(seconds % 60)}
    </span>
  );
}
