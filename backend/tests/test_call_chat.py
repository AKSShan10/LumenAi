"""The chat inside the video call: text and links between the interviewer and the candidate. Made-up data only."""
from tests.test_video_call import interview, livekit  # noqa: F401  (the same scheduled interview and LiveKit settings)


def test_both_sides_chat_while_live(client, anonymous, interview, livekit):  # noqa: F811
    token = interview["token"]
    early = anonymous.post(f"/api/join/{token}/chat", json={"text": "Hello?"})
    assert early.status_code == 409                                              # the candidate waits for the start
    assert client.post(f"/api/sessions/{interview['id']}/chat", json={"text": "Welcome! Starting soon."}).status_code == 200

    client.post(f"/api/sessions/{interview['id']}/start")
    sent = anonymous.post(f"/api/join/{token}/chat", json={"text": "  My work: https://github.com/made-up/demo  "}).json()
    assert sent["sender"] == "candidate" and sent["text"] == "My work: https://github.com/made-up/demo"
    client.post(f"/api/sessions/{interview['id']}/chat", json={"text": "Task: https://example.com/task"})

    everything = client.get(f"/api/sessions/{interview['id']}/chat").json()
    assert [(m["sender"], m["text"][:8]) for m in everything] == [
        ("interviewer", "Welcome!"), ("candidate", "My work:"), ("interviewer", "Task: ht")]
    assert everything[0]["sender_name"] == "Test Interviewer"                     # names for the chat; the role stays
    assert everything[1]["sender_name"] == "Karima Akter"
    newer = anonymous.get(f"/api/join/{token}/chat?after={everything[1]['id']}").json()
    assert [m["text"] for m in newer] == ["Task: https://example.com/task"]          # only the new ones


def test_the_chat_closes_at_the_end(client, anonymous, interview, livekit):  # noqa: F811
    client.post(f"/api/sessions/{interview['id']}/start")
    client.post(f"/api/sessions/{interview['id']}/end")
    assert anonymous.post(f"/api/join/{interview['token']}/chat", json={"text": "late"}).status_code == 400
    assert client.post(f"/api/sessions/{interview['id']}/chat", json={"text": "late"}).status_code == 400


def test_empty_long_and_wrong(client, anonymous, interview, livekit):  # noqa: F811
    client.post(f"/api/sessions/{interview['id']}/start")
    assert anonymous.post(f"/api/join/{interview['token']}/chat", json={"text": ""}).status_code == 422
    assert anonymous.post(f"/api/join/{interview['token']}/chat", json={"text": "   "}).status_code == 422
    assert anonymous.post(f"/api/join/{interview['token']}/chat", json={"text": "x" * 1001}).status_code == 422
    assert anonymous.get("/api/join/not-a-real-token-at-all-123/chat").status_code == 404
    assert anonymous.get(f"/api/sessions/{interview['id']}/chat").status_code == 401   # the interviewer side needs login
