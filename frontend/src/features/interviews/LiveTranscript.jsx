import { useEffect, useRef, useState } from "react";
import { interviewsApi } from "./interviewsApi.js";

// The interviewer's "Live Transcript" tab in the call. Each browser sends its own microphone (MicToText.jsx), the
// backend saves every finished sentence, and this tab asks for the new ones every 2 seconds (like the chat).
// The speaker comes from the microphone the sentence came from; the time is from the start of the interview.
const LOOK_AGAIN_MS = 2000;

// 65.4 → "01:05", 3725 → "1:02:05"
export function clock(seconds) {
  const s = Math.floor(seconds);
  const two = (n) => String(n).padStart(2, "0");
  const hours = Math.floor(s / 3600);
  return `${hours ? `${hours}:` : ""}${two(Math.floor(s / 60) % 60)}:${two(s % 60)}`;
}

// The sentences as a list: time, who, text (also used by TranscriptView.jsx after the call)
export function TurnList({ turns, names = {} }) {
  return (
    <ol className="transcript-list">
      {turns.map((t) => (
        <li key={t.id} className={`transcript-turn ${t.speaker}`}>
          <span className="transcript-time">{clock(t.start_sec)}</span>
          <b>{names[t.speaker] || (t.speaker === "interviewer" ? "Interviewer" : "Candidate")}</b>
          <span>{t.text}</span>
        </li>
      ))}
    </ol>
  );
}

// Adds new sentences once each and keeps them in the order they were said
export function addTurns(old, more) {
  const known = new Set(old.map((t) => t.id));
  return [...old, ...more.filter((t) => !known.has(t.id))].sort((a, b) => a.start_sec - b.start_sec || a.id - b.id);
}

// The live tab: status of your microphone line, then the sentences, newest at the bottom
export default function LiveTranscript({ sessionId, status, names, hidden }) {
  const [turns, setTurns] = useState([]);
  const newest = useRef(0);
  const list = useRef(null);

  useEffect(() => {
    // → GET /api/sessions/{id}/transcript?after=...: only the sentences we do not have yet
    const look = () => interviewsApi.transcript(sessionId, newest.current).then((more) => {
      if (!more.length) return;
      newest.current = Math.max(newest.current, ...more.map((t) => t.id));
      setTurns((old) => addTurns(old, more));
    }).catch(() => {});
    look();
    const timer = setInterval(look, LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [sessionId]);

  useEffect(() => {                                  // keep the newest sentence in view
    if (list.current && !hidden) list.current.scrollTop = list.current.scrollHeight;
  }, [turns, hidden]);

  const words = { listening: "Transcribing both microphones.", connecting: "Connecting the transcript..." };
  return (
    <div className="live-transcript" hidden={hidden}>
      <p className={`small ${words[status] ? "muted" : "error"}`}>{words[status] || status || "Waiting for the microphone..."}</p>
      <div className="transcript-scroll" ref={list}>
        {turns.length ? <TurnList turns={turns} names={names} />
          : <p className="muted small">The sentences appear here when someone speaks.</p>}
      </div>
    </div>
  );
}
