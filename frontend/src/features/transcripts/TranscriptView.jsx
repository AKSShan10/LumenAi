import { useEffect, useState } from "react";
import { download } from "../../shared/api/httpClient.js";
import { transcriptsApi } from "./transcriptsApi.js";
import { TurnList, addTurns } from "./LiveTranscript.jsx";

// The transcript of one interview on the Interviews page, with a .txt download. Only what was said: the chat
// stays in the call's Chat tab and its own table.
// While the call is still live, it refreshes every 5 seconds.
const LOOK_AGAIN_MS = 5000;

export default function TranscriptView({ row, onClose }) {
  const [turns, setTurns] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    // → GET /api/sessions/{id}/transcript: everything said in the call
    const look = () => transcriptsApi.transcript(row.id)
      .then((said) => setTurns((old) => addTurns(old, said)))
      .catch((e) => setError(e.message));
    look();
    if (row.status !== "live") return undefined;
    const timer = setInterval(look, LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [row.id, row.status]);

  // → GET /api/sessions/{id}/transcript.txt: the transcript as a text file
  function save() {
    download(`/api/sessions/${row.id}/transcript.txt`, `interview-${row.id}-transcript.txt`).catch((e) => setError(e.message));
  }

  return (
    <div className="card transcript-view">
      <div className="row-between">
        <h3>Transcript · {row.candidate_name || "candidate"}</h3>
        <div>
          <button type="button" onClick={save}>Download .txt</button>{" "}
          <button type="button" className="secondary" onClick={onClose}>Close</button>
        </div>
      </div>
      <p className="muted small">Times are from the start of the interview. The speaker comes from each person's own
        microphone.{row.status === "live" ? " The call is live: new sentences appear by themselves." : ""}</p>
      {error && <p className="error">{error}</p>}
      {turns.length ? <TurnList turns={turns} names={{ candidate: row.candidate_name }} />
        : <p className="muted">Nothing was transcribed in this interview.</p>}
    </div>
  );
}
