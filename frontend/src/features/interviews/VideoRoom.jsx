import "@livekit/components-styles";
import { ChatIcon, ConnectionStateToast, DisconnectButton, LeaveIcon, LiveKitRoom, MediaDeviceMenu, ParticipantTile,
  RoomAudioRenderer, StartMediaButton, TrackToggle, useTracks } from "@livekit/components-react";
import { Track } from "livekit-client";

// The video call itself, the same for the interviewer and the candidate.
// The browser connects straight to the LiveKit server with the ticket our backend signed (one person, one room).
// LiveKit sends the camera, microphone and a shared screen, and reconnects by itself after a short network drop
// (ConnectionStateToast shows "Reconnecting...").
//
// Speaker view, like Zoom:
//   nobody shares:  the other person big, yourself small in the corner
//   a screen share: the shared screen big, both cameras in a strip at the side
//
// chat = {open, unread, onToggle}: the Chat button in the bar below opens and closes our chat panel (CallChat.jsx).
export default function VideoRoom({ serverUrl, ticket, onLeave, waitingFor = "the other person", chat }) {
  return (
    <div className="video-room" data-lk-theme="default">
      <LiveKitRoom serverUrl={serverUrl} token={ticket} connect video audio onDisconnected={onLeave}
                   style={{ height: "100%" }}>
        <Stage waitingFor={waitingFor} />
        <RoomAudioRenderer />
        <ConnectionStateToast />
        <CallControls chat={chat} />
      </LiveKitRoom>
    </div>
  );
}

const canShareScreen = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getDisplayMedia;   // not on most phones

// The bar under the video: microphone, camera, share screen, chat, leave (LiveKit's own buttons + our Chat button).
// On a narrow screen only the icons are shown (CSS hides .bar-text).
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
        <button type="button" className="lk-button chat-button" aria-pressed={chat.open} onClick={chat.onToggle}
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

const keyOf = (track) => `${track.participant.identity}-${track.source}`;

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
  return (                                           // the other person big, yourself small
    <div className="stage">
      <div className="stage-main">
        {other ? <ParticipantTile trackRef={other} /> : <div className="stage-waiting">Waiting for {waitingFor} to join...</div>}
      </div>
      {mine && <div className="stage-self"><ParticipantTile trackRef={mine} /></div>}
    </div>
  );
}
