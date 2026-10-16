import { useEffect, useRef } from "react";
import { useLocalParticipant } from "@livekit/components-react";
import workletCode from "./pcm-worklet.js?raw";

// Sends this browser's own microphone to the backend for the live transcript, so the speaker is known from the line
// (the interviewer's tab → /api/sessions/{id}/stt, the candidate's tab → /api/join/{token}/stt).
// It uses the microphone LiveKit already opened: no second permission, and a muted microphone sends only silence.
// It shows nothing itself. Inside <LiveKitRoom> (VideoRoom.jsx).
//   path        the WebSocket address
//   login       the interviewer's login token, sent as the first message (empty for the candidate)
//   onStatus    tells the page: "listening", "connecting" or an error in plain words
// The line reconnects by itself after a drop; after an error from the backend it stops.
const AGAIN_MS = 3000;

export default function MicToText({ path, login = "", onStatus = () => {} }) {
  const { microphoneTrack } = useLocalParticipant();
  const track = microphoneTrack?.track?.mediaStreamTrack;
  const report = useRef(onStatus);
  report.current = onStatus;

  useEffect(() => {
    if (!track) return undefined;
    let stopped = false;
    let socket = null;
    let retry = null;
    const audio = new AudioContext();
    let worklet = null;

    // Opens the WebSocket; on a drop (not an error) it opens again after a few seconds
    function connect() {
      if (stopped) return;
      report.current("connecting");
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      // → WebSocket to the backend: our microphone, 0.1 s pieces of sound
      socket = new WebSocket(`${scheme}://${window.location.host}${path}`);
      socket.binaryType = "arraybuffer";
      let failed = false;
      socket.onopen = () => {
        if (login) socket.send(JSON.stringify({ token: login }));   // the login as a message, never in the address
        report.current("listening");
      };
      socket.onmessage = (event) => {
        const answer = JSON.parse(event.data);
        if (answer.error) { failed = true; report.current(answer.error); }
      };
      socket.onclose = () => {
        if (!stopped && !failed) retry = setTimeout(connect, AGAIN_MS);    // a drop: try again
      };
    }

    // The microphone → the worklet (16 kHz pieces) → the WebSocket
    async function start() {
      try {
        // The worklet file is loaded from its text (a blob address), which works the same in "npm run dev" and Docker
        const address = URL.createObjectURL(new Blob([workletCode], { type: "text/javascript" }));
        await audio.audioWorklet.addModule(address);
        URL.revokeObjectURL(address);
        if (stopped) return;
        const source = audio.createMediaStreamSource(new MediaStream([track]));
        worklet = new AudioWorkletNode(audio, "pcm-sender");
        worklet.port.onmessage = (event) => {
          if (socket && socket.readyState === WebSocket.OPEN) socket.send(event.data);
        };
        const silent = audio.createGain();          // the browser runs the worklet only when it leads to the speakers,
        silent.gain.value = 0;                      // so it is connected through a gain of 0: nothing is heard
        source.connect(worklet).connect(silent).connect(audio.destination);
        connect();
        // A tab opened without a click may hold the sound back until the person clicks somewhere on the page
        if (audio.state === "suspended") {
          audio.resume().catch(() => {});
          document.addEventListener("click", () => audio.resume().catch(() => {}), { once: true });
        }
      } catch {
        report.current("This browser cannot send the microphone for the transcript.");
      }
    }
    start();

    return () => {                                  // the call closed or the microphone changed
      stopped = true;
      clearTimeout(retry);
      if (socket) socket.close();
      if (worklet) worklet.port.onmessage = null;
      audio.close().catch(() => {});
    };
  }, [track, path, login]);

  return null;
}
