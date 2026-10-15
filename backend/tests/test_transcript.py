"""The live transcript: each browser sends its own microphone, so the speaker comes from the line, not a guess.
Fake speech-to-text (STT_PROVIDER=fake): test sentences, no key, no sound stored. Made-up data only."""
import asyncio
import json

import httpx
import pytest

from app.core import config
from app.features.interviews.services import stt_service
from tests.test_video_call import interview, livekit  # noqa: F401  (a scheduled interview and LiveKit settings)

SECOND_OF_SOUND = b"\x00\x00" * 16000          # one second of silence: 16 kHz, 16-bit mono


def say(ws, text: str) -> dict:
    ws.send_text(json.dumps({"say": text}))        # fake only: a test sentence instead of sound
    return ws.receive_json()


def test_both_microphones_give_sentences_with_speaker_and_time(client, anonymous, interview, livekit):  # noqa: F811
    client.post(f"/api/sessions/{interview['id']}/start")
    with client.websocket_connect(f"/api/sessions/{interview['id']}/stt") as mine:
        mine.send_json({"token": client.token})                          # the login comes as the first message
        first = say(mine, "Tell me about your last project.")
        assert first["speaker"] == "interviewer" and first["text"] == "Tell me about your last project."
        assert first["start_sec"] >= 0 and first["end_sec"] > first["start_sec"]
        with anonymous.websocket_connect(f"/api/join/{interview['token']}/stt") as theirs:
            answer = say(theirs, "I built a booking service with FastAPI.")
            assert answer["speaker"] == "candidate"

    said = client.get(f"/api/sessions/{interview['id']}/transcript").json()
    assert [(t["speaker"], t["text"]) for t in said] == [
        ("interviewer", "Tell me about your last project."), ("candidate", "I built a booking service with FastAPI.")]
    newer = client.get(f"/api/sessions/{interview['id']}/transcript?after={said[0]['id']}").json()
    assert [t["speaker"] for t in newer] == ["candidate"]                # only the new ones


def test_sound_becomes_test_sentences(client, interview, livekit):  # noqa: F811
    client.post(f"/api/sessions/{interview['id']}/start")
    with client.websocket_connect(f"/api/sessions/{interview['id']}/stt") as mine:
        mine.send_json({"token": client.token})
        for _ in range(stt_service.FAKE_EVERY_SEC):
            mine.send_bytes(SECOND_OF_SOUND)
        sentence = mine.receive_json()
    assert sentence["speaker"] == "interviewer" and sentence["text"] == stt_service.FAKE_LINES["interviewer"][0]
    assert sentence["end_sec"] >= stt_service.FAKE_EVERY_SEC


def test_the_echo_guard_drops_the_other_persons_voice(client, anonymous, interview, livekit):  # noqa: F811
    client.post(f"/api/sessions/{interview['id']}/start")
    with client.websocket_connect(f"/api/sessions/{interview['id']}/stt") as mine, \
            anonymous.websocket_connect(f"/api/join/{interview['token']}/stt") as theirs:
        mine.send_json({"token": client.token})
        say(mine, "How did you design the database for that project?")
        echo = say(theirs, "how did you design the database for that project")   # the candidate's mic heard it
        assert echo == {"speaker": "candidate", "dropped": True}
        short = say(theirs, "Yes, I see.")                                   # short answers are never an echo
        assert short["text"] == "Yes, I see."
    said = client.get(f"/api/sessions/{interview['id']}/transcript").json()
    assert [t["speaker"] for t in said] == ["interviewer", "candidate"]


def test_only_while_live_and_only_with_the_right_key(client, anonymous, interview, livekit):  # noqa: F811
    with anonymous.websocket_connect(f"/api/join/{interview['token']}/stt") as early:
        assert "live" in early.receive_json()["error"]                       # not before the start
    with anonymous.websocket_connect("/api/join/not-a-real-token-at-all-123/stt") as wrong:
        assert "not valid" in wrong.receive_json()["error"]
    client.post(f"/api/sessions/{interview['id']}/start")
    with anonymous.websocket_connect(f"/api/sessions/{interview['id']}/stt") as stranger:
        stranger.send_json({"token": "made-up"})
        assert "log in" in stranger.receive_json()["error"]                  # the interviewer's line needs the login
    client.post(f"/api/sessions/{interview['id']}/end")
    with anonymous.websocket_connect(f"/api/join/{interview['token']}/stt") as late:
        assert "live" in late.receive_json()["error"]                        # not after the end


def test_not_set_up_is_said_in_plain_words(client, interview, livekit, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "STT_PROVIDER", "deepgram")
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "")
    client.post(f"/api/sessions/{interview['id']}/start")
    with client.websocket_connect(f"/api/sessions/{interview['id']}/stt") as mine:
        mine.send_json({"token": client.token})
        assert "DEEPGRAM_API_KEY is empty" in mine.receive_json()["error"]


def test_download_has_only_the_transcript(client, anonymous, interview, livekit):  # noqa: F811
    client.post(f"/api/sessions/{interview['id']}/start")
    client.post(f"/api/sessions/{interview['id']}/chat", json={"text": "Task: https://example.com/task"})
    with anonymous.websocket_connect(f"/api/join/{interview['token']}/stt") as theirs:
        say(theirs, "I would add an index for the slow search.")
    file = client.get(f"/api/sessions/{interview['id']}/transcript.txt")
    assert file.status_code == 200 and "attachment" in file.headers["content-disposition"]
    text = file.text
    assert "Candidate: Karima Akter" in text
    assert "] Candidate: I would add an index for the slow search." in text      # [hh:mm:ss] Speaker: text
    assert "Chat" not in text and "example.com/task" not in text                  # the chat stays in its own table
    assert client.get(f"/api/sessions/{interview['id']}/chat").json()[0]["text"] == "Task: https://example.com/task"
    assert anonymous.get(f"/api/sessions/{interview['id']}/transcript.txt").status_code == 401
    assert anonymous.get(f"/api/sessions/{interview['id']}/transcript").status_code == 401


# ---------- Deepgram (no network: a made-up Deepgram line) ----------

class MadeUpDeepgram:
    """Answers like Deepgram live: pieces of a sentence, then speech_final."""
    def __init__(self, answers):
        self.answers, self.sent = answers, []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass

    def __aiter__(self):
        return self._messages()

    async def _messages(self):
        for answer in self.answers:
            await asyncio.sleep(0)
            yield json.dumps(answer)


def piece(text, start, duration, speech_final=False):
    return {"type": "Results", "is_final": True, "speech_final": speech_final, "start": start, "duration": duration,
            "channel": {"alternatives": [{"transcript": text}]}}


def test_deepgram_pieces_become_one_sentence(monkeypatch):
    import websockets
    line = MadeUpDeepgram([piece("I built", 1.0, 0.6), piece("a booking service.", 1.6, 1.2, speech_final=True),
                           piece("", 3.0, 0.5), piece("Then I tested it", 4.0, 1.0), {"type": "UtteranceEnd"}])

    async def connect(address, **settings):
        assert "encoding=linear16" in address and "sample_rate=16000" in address
        assert settings["additional_headers"]["Authorization"] == "Token made-up-key"
        return line
    monkeypatch.setattr(websockets, "connect", connect)
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "made-up-key")
    sentences = []

    async def on_sentence(text, start, end):
        sentences.append((text, start, end))

    async def run():
        audio = asyncio.Queue()
        await audio.put(SECOND_OF_SOUND)
        await audio.put(None)
        await stt_service._deepgram(audio, on_sentence)
    asyncio.run(run())
    assert sentences == [("I built a booking service.", 1.0, 2.8), ("Then I tested it", 4.0, 5.0)]


def test_deepgram_wrong_key_is_said_in_plain_words(monkeypatch):
    import websockets

    class Refused:
        status_code = 401
    async def connect(address, **settings):
        raise websockets.InvalidStatus(Refused())
    monkeypatch.setattr(websockets, "connect", connect)
    with pytest.raises(stt_service.SttError, match="did not accept the key"):
        asyncio.run(stt_service._deepgram(asyncio.Queue(), None))


@pytest.mark.parametrize("provider, key, status, expected", [
    ("fake", "", 200, (True, "Fake speech-to-text")),
    ("deepgram", "", 200, (False, "DEEPGRAM_API_KEY is empty")),
    ("deepgram", "made-up-key", 401, (False, "did not accept the key")),
    ("deepgram", "made-up-key", 200, (True, "Speech-to-text is set up")),
])
def test_the_settings_check(client, monkeypatch, provider, key, status, expected):
    monkeypatch.setattr(config, "STT_PROVIDER", provider)
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", key)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(status))
    answer = client.get("/api/stt-check").json()
    assert answer["ok"] is expected[0] and expected[1] in answer["message"]
