import "@livekit/components-styles";
import { ChatIcon, ConnectionStateToast, DisconnectButton, LeaveIcon, LiveKitRoom, MediaDeviceMenu, ParticipantTile,
  RoomAudioRenderer, StartMediaButton, TrackToggle, useLocalParticipant, useTracks } from "@livekit/components-react";
import { Track } from "livekit-client";
import MicToText from "./MicToText.jsx";

// The video call itself, the same for the interviewer and the candidate.
// The browser connects straight to the LiveKit server with the ticket our backend signed (one person, one room).
// LiveKit sends the camera, microphone and a shared screen, and reconnects by itself after a short network drop
// (ConnectionStateToast shows "Reconnecting...").
//
// Speaker view for both: the other person big, yourself small in the corner; a shared screen goes big and the
// cameras move to a strip at the side. Only the buttons differ:
//   layout="speaker" (the candidate): a bar with a Chat button (chat = {open, unread, onToggle} opens CallChat.jsx)
//   layout="pair"    (the interviewer's room): round buttons on top of the video, at the bottom
// transcribe = {path, login, onStatus}: also sends this browser's microphone for the live transcript (MicToText.jsx)
export default function VideoRoom({ serverUrl, ticket, onLeave, waitingFor = "the other person", chat, layout = "speaker",
                                    transcribe }) {
  const pair = layout === "pair";
  return (
    <div className={`video-room ${pair ? "pair" : ""}`} data-lk-theme="default">
      <LiveKitRoom serverUrl={livekitAddress(serverUrl)} token={ticket} connect video audio onDisconnected={onLeave}
                   style={{ height: "100%" }}>
        <Stage waitingFor={waitingFor} />
        <RoomAudioRenderer />
        <ConnectionStateToast />
        {transcribe && <MicToText {...transcribe} />}
        {pair ? <RoundControls /> : <CallControls chat={chat} />}
      </LiveKitRoom>
    </div>
  );
}

// "/" = the LiveKit server in Docker, at the same address as this page (nginx passes /rtc to it), so it also works
// through an https:// tunnel. Any other value is a full address, e.g. wss://your-project.livekit.cloud
function livekitAddress(url) {
  if (!url.startsWith("/")) return url;
  return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
}

const canShareScreen = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getDisplayMedia;   // not on most phones

// The candidate's bar under the video: microphone, camera, share screen, chat, leave
// (LiveKit's own buttons + our Chat button). On a narrow screen only the icons are shown (CSS hides .bar-text).
function CallControls({ chat }) {
  return (
    <div className="lk-control-bar">
      <div className="lk-button-group">
        <TrackToggle source={Track.Source.Microphone}><span className="bar-text">Microphone</span></TrackToggle>
        <div className="lk-button-group-menu"><MediaDeviceMenu kind="audioinput" /></div>
      </div>
      <div className="lk-button-group">
        <TrackToggle source={Track.Source.Camera}><span className="bar-text">Camera</span></TrackToggle>
        <div className="lk-button-group-menu"><MediaDeviceMenu kind="videoinput" /></div>
      </div>
      {canShareScreen && (
        <TrackToggle source={Track.Source.ScreenShare} captureOptions={{ audio: true, selfBrowserSurface: "include" }}>
          <span className="bar-text">Share screen</span>
        </TrackToggle>
      )}
      {chat && (
        <button type="button" className="lk-button side-button chat-button" aria-pressed={chat.open} onClick={chat.onToggle}
                title={chat.open ? "Close the chat" : "Open the chat"}>
          <ChatIcon /><span className="bar-text">Chat</span>
          {chat.unread > 0 && !chat.open && <span className="chat-badge" aria-label={`${chat.unread} new`}>{chat.unread}</span>}
        </button>
      )}
      <DisconnectButton><LeaveIcon /><span className="bar-text">Leave</span></DisconnectButton>
      <StartMediaButton />
    </div>
  );
}

// The interviewer's buttons: round, on top of the video at the bottom (like Google Meet), so the video gets the
// whole height. The words (Mute / Unmute ...) show when the mouse is on a button.
// "Leave" only leaves the call; "End interview for both" is at the top of the page.
function RoundControls() {
  const { isMicrophoneEnabled, isCameraEnabled, isScreenShareEnabled } = useLocalParticipant();
  const mic = isMicrophoneEnabled ? "Mute" : "Unmute";
  const camera = isCameraEnabled ? "Stop Video" : "Start Video";
  const share = isScreenShareEnabled ? "Stop Share" : "Share";
  return (
    <div className="round-controls">
      <div className="round-control can-be-off">
        <TrackToggle source={Track.Source.Microphone} title={mic} aria-label={mic} />
      </div>
      <div className="round-control can-be-off">
        <TrackToggle source={Track.Source.Camera} title={camera} aria-label={camera} />
      </div>
      {canShareScreen && (
        <div className="round-control">
          <TrackToggle source={Track.Source.ScreenShare} captureOptions={{ audio: true, selfBrowserSurface: "include" }}
                       title={share} aria-label={share} />
        </div>
      )}
      <div className="round-control leave">
        <DisconnectButton title="Leave" aria-label="Leave"><LeaveIcon /></DisconnectButton>
      </div>
      <StartMediaButton />
    </div>
  );
}

// A unique React key for a video tile: the person's identity plus the source (camera or screen)
const keyOf = (track) => `${track.participant.identity}-${track.source}`;

// Shows the LiveKit videos: the other person big and you small, or a shared screen big
function Stage({ waitingFor }) {
  const tracks = useTracks(
    [{ source: Track.Source.Camera, withPlaceholder: true }, { source: Track.Source.ScreenShare, withPlaceholder: false }],
    { onlySubscribed: false },
  );
  const screen = tracks.find((t) => t.source === Track.Source.ScreenShare);
  const cameras = tracks.filter((t) => t.source === Track.Source.Camera);
  const mine = cameras.find((t) => t.participant.isLocal);
  const other = cameras.find((t) => !t.participant.isLocal);

  if (screen) {                                      // a shared screen: big, the cameras at the side
    return (
      <div className="stage stage-share">
        <div className="stage-main"><ParticipantTile trackRef={screen} /></div>
        <div className="stage-strip">
          {cameras.map((t) => <ParticipantTile key={keyOf(t)} trackRef={t} />)}
        </div>
      </div>
    );
  }
  const waiting = <div className="stage-waiting">Waiting for {waitingFor} to join...</div>;
  return (                                           // the other person big, yourself small
    <div className="stage">
      <div className="stage-main">
        {other ? <ParticipantTile trackRef={other} /> : waiting}
      </div>
      {mine && <div className="stage-self"><ParticipantTile trackRef={mine} /></div>}
    </div>
  );
}
