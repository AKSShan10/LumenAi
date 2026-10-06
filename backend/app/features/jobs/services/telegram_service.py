"""Talks to the Telegram Bot API. Only the Telegram MCP server (app/mcp_servers/telegram_server.py) uses this file.

    telegram_send()     posts one message to the channel
    telegram_check()    is the token right, and can the bot post in the channel?

TELEGRAM_PROVIDER=fake posts nothing and answers as if it worked (tests, and demos without a bot).
The bot token is part of the address Telegram is called at, so error texts are written by hand here:
an error from the network library could contain the address, and with it the token.
"""
import httpx

from app.core import config

TIMEOUT_SEC = 20
MAX_MESSAGE_CHARS = 4096          # Telegram's limit for one message


def settings_problem() -> str:
    if not config.TELEGRAM_BOT_TOKEN:
        return "TELEGRAM_BOT_TOKEN is missing in .env"
    if not config.TELEGRAM_CHANNEL_ID:
        return "TELEGRAM_CHANNEL_ID is missing in .env"
    return ""


def _call(method: str, payload: dict) -> dict:
    """One call to the Bot API. Returns Telegram's answer: {"ok": true, "result": ...} or {"ok": false, "description": ...}."""
    url = f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
    try:
        return httpx.post(url, json=payload, timeout=TIMEOUT_SEC).json()
    except httpx.TimeoutException:
        return {"ok": False, "description": "Telegram did not answer in time"}
    except Exception as exc:                      # never str(exc): it may contain the token
        return {"ok": False, "description": f"could not reach Telegram ({type(exc).__name__})"}


def telegram_send(text: str, button_text: str = "", button_url: str = "") -> dict:
    """Posts the message. Returns {"ok", "message_id", "link", "error"}."""
    if len(text) > MAX_MESSAGE_CHARS:
        return {"ok": False, "message_id": 0, "link": "", "error": "the post is longer than 4096 characters"}
    if config.TELEGRAM_PROVIDER == "fake":
        return {"ok": True, "message_id": 1, "link": "", "error": ""}
    problem = settings_problem()
    if problem:
        return {"ok": False, "message_id": 0, "link": "", "error": problem}

    payload = {"chat_id": config.TELEGRAM_CHANNEL_ID, "text": text, "disable_web_page_preview": True}
    if button_text and button_url:                # a button under the message that opens the link
        payload["reply_markup"] = {"inline_keyboard": [[{"text": button_text, "url": button_url}]]}
    answer = _call("sendMessage", payload)
    if not answer.get("ok"):
        return {"ok": False, "message_id": 0, "link": "", "error": answer.get("description") or "Telegram refused the post"}

    message = answer["result"]
    username = (message.get("chat") or {}).get("username")       # only public channels have one
    link = f"https://t.me/{username}/{message['message_id']}" if username else ""
    return {"ok": True, "message_id": message["message_id"], "link": link, "error": ""}


def telegram_check() -> dict:
    """Says in plain words whether posting will work. Posts nothing."""
    if config.TELEGRAM_PROVIDER == "fake":
        return {"ok": True, "message": "Fake Telegram is on (TELEGRAM_PROVIDER=fake): nothing is really posted."}
    problem = settings_problem()
    if problem:
        return {"ok": False, "message": problem}
    bot = _call("getMe", {})
    if not bot.get("ok"):
        return {"ok": False, "message": f"The bot token was not accepted: {bot.get('description', 'unknown error')}"}
    chat = _call("getChat", {"chat_id": config.TELEGRAM_CHANNEL_ID})
    if not chat.get("ok"):
        return {"ok": False, "message": f"The bot cannot see the channel: {chat.get('description', 'unknown error')}. "
                                        "Check TELEGRAM_CHANNEL_ID and add the bot to the channel as an admin."}
    title = chat["result"].get("title") or config.TELEGRAM_CHANNEL_ID
    return {"ok": True, "message": f"Bot @{bot['result'].get('username')} can reach the channel \"{title}\"."}
