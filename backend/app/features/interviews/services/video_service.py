"""The video call (LiveKit). LiveKit runs the call itself; our backend only gives out "tickets".

    video_problem()                    what is missing in .env, or "" when the video is set up
    make_ticket(room, identity, name)  a signed ticket (JWT) that lets ONE person join ONE room for a few hours

How a call works: the browser gets a ticket from our backend, then connects straight to the LiveKit server with it.
The ticket is signed with LIVEKIT_API_SECRET, so nobody can make one for another room. The identity is
"interviewer" or "candidate", so later the transcript knows who is speaking (and a second tab of the same person
replaces the first one instead of adding a third person).
"""
from datetime import timedelta

from app.core import config

TICKET_HOURS = 4


# Returns which LiveKit setting is empty or wrong in .env, or "" when video is set up
def video_problem() -> str:
    for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        if not getattr(config, name):
            return f"Video is not set up: {name} is empty in .env"
    if not config.LIVEKIT_URL.startswith(("wss://", "ws://")):        # e.g. the old "/" for a local server
        return "Video is not set up: LIVEKIT_URL must be the LiveKit Cloud address (wss://your-project.livekit.cloud)"
    return ""


# Signs a LiveKit JWT for one person in one room (4 hours); used by start_call and candidate_ticket
def make_ticket(room: str, identity: str, name: str) -> str:
    from livekit import api                         # imported here: only needed when someone joins a call
    # → LiveKit permission: join only this room, send and receive audio/video
    grant = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True)
    # → signed with LIVEKIT_API_SECRET, so nobody can forge a ticket
    return (api.AccessToken(config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET)
            .with_identity(identity).with_name(name or identity).with_grants(grant)
            .with_ttl(timedelta(hours=TICKET_HOURS)).to_jwt())


def video_check() -> dict:
    """The Settings button: are the settings there, and can a ticket be made? Connects to nothing."""
    problem = video_problem()
    if problem:
        return {"ok": False, "message": problem + "."}
    try:
        make_ticket("settings-check", "check", "check")
    except Exception as problem:                     # never str(problem): it could contain the secret
        return {"ok": False, "message": f"A call ticket could not be made ({type(problem).__name__}). Check the LiveKit keys."}
    return {"ok": True, "message": f"Video is set up ({config.LIVEKIT_URL}). Try a real call with two browsers."}
