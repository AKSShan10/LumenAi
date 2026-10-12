import { Suspense, lazy, useEffect, useState } from "react";
import { auth } from "../../shared/api/authToken.js";
import { interviewsApi } from "./interviewsApi.js";
import CallChat from "./CallChat.jsx";

// LiveKit is big, so the call code is loaded only when the call opens
const VideoRoom = lazy(() => import("./VideoRoom.jsx"));

// The interviewer's call, in its own browser tab (/interview-room/<id>), opened from the Interviews page.
// It starts the call (or joins it again), shows the call and the chat (text and links), and has
// "End interview for both".
// The tab gets a copy of the login from the tab that opened it.
export default function InterviewRoomPage({ sessionId }) {
  const [call, setCall] = useState(null);           // {server_url, ticket, session}
  const [state, setState] = useState("opening");    // opening | in_call | left | ended | error
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);  // the chat panel: closed until the Chat button is clicked
  const [unread, setUnread] = useState(0);

  async function open() {
    setState("opening"); setError("");
    try {
      const answer = await interviewsApi.start(sessionId);
      setCall(answer); setState("in_call");
      document.title = `Interview: ${answer.session.candidate_name || "candidate"}`;
    } catch (e) { setError(e.message); setState("error"); }
  }

  useEffect(() => { if (auth.get()) open(); }, [sessionId]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function endForBoth() {
    setBusy(true);
    try { await interviewsApi.end(sessionId); setState("ended"); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  if (!auth.get()) {
    return <div className="room-message"><p>Please open the interview from the Interviews page of LumenAI (you need to be logged in).</p></div>;
  }

  const who = call?.session;
  return (
    <div className="room-page">
      <header className="room-bar">
        <div>
          <b>{who ? `Interview with ${who.candidate_name || "the candidate"}` : "Interview"}</b>
          {who && <span className="room-sub"> · {who.job_title}</span>}
        </div>
        {state === "in_call" && (
          <button type="button" className="danger" onClick={endForBoth} disabled={busy}>
            {busy ? "Ending..." : "End interview for both"}</button>
        )}
      </header>

      {error && <p className="error room-note">{error}</p>}
      {state === "opening" && <p className="room-note">Opening the call...</p>}
      {state === "in_call" && (
        <div className="room-body">
          <Suspense fallback={<p className="room-note">Opening the call...</p>}>
            <VideoRoom serverUrl={call.server_url} ticket={call.ticket} waitingFor="the candidate"
                       chat={{ open: chatOpen, unread, onToggle: () => setChatOpen(!chatOpen) }}
                       onLeave={() => setState((s) => (s === "ended" ? s : "left"))} />
          </Suspense>
          <CallChat me="interviewer" open={chatOpen} onUnread={setUnread}
                    onOpen={() => setChatOpen(true)} onClose={() => setChatOpen(false)}
                    load={(after) => interviewsApi.chat(sessionId, after)}
                    send={(text) => interviewsApi.sendChat(sessionId, text)} />
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
