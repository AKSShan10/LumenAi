"""Talks to the Blogger API (Google's blog site). Only the Blogger MCP server (app/mcp_servers/blogger_server.py) uses this file.

    blogger_publish()   publishes one blog post
    blogger_check()     is the Google login right, and can we reach the blog?

How the login works: Blogger belongs to a person's Google account, so it needs OAuth.
You log in ONCE with scripts/blogger_login.py and get a "refresh token" (kept in .env).
Before each call this file swaps the refresh token for a short-lived "access token".

BLOGGER_PROVIDER=fake publishes nothing and answers as if it worked (tests, and demos without a blog).
Error texts are written by hand here, so a token can never end up in an error message.
"""
import html

import httpx

from app.core import config

TIMEOUT_SEC = 20


# Says which Blogger setting is missing in .env, or "" when all are set
def settings_problem() -> str:
    for name in ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN"):
        if not getattr(config, name):
            return f"{name} is missing in .env"
    return ""


def _access_token() -> tuple[str, str]:
    """Swaps the refresh token for an access token. Returns (token, problem)."""
    try:
        # → Google OAuth: swaps the refresh token for an access token
        answer = httpx.post(config.GOOGLE_TOKEN_URL, timeout=TIMEOUT_SEC, data={
            "client_id": config.BLOGGER_CLIENT_ID, "client_secret": config.BLOGGER_CLIENT_SECRET,
            "refresh_token": config.BLOGGER_REFRESH_TOKEN, "grant_type": "refresh_token"}).json()
    except Exception as exc:                      # never str(exc): it may contain a secret
        return "", f"could not reach Google ({type(exc).__name__})"
    if not answer.get("access_token"):
        return "", ("Google did not accept the login (" + str(answer.get("error") or "unknown error")
                    + "). Run scripts/blogger_login.py again and update BLOGGER_REFRESH_TOKEN")
    return answer["access_token"], ""


def _call(method: str, path: str, token: str, body: dict | None = None) -> dict:
    """One call to the Blogger API. Returns Blogger's answer, or {"error": {"message": ...}}."""
    url = f"{config.BLOGGER_API_URL}/blogs/{config.BLOGGER_BLOG_ID}{path}"
    try:
        return httpx.request(method, url, json=body, timeout=TIMEOUT_SEC,
                             headers={"Authorization": f"Bearer {token}"}).json()
    except httpx.TimeoutException:
        return {"error": {"message": "Blogger did not answer in time"}}
    except Exception as exc:
        return {"error": {"message": f"could not reach Blogger ({type(exc).__name__})"}}


def post_html(text: str, button_text: str = "", button_url: str = "") -> str:
    """A blog post is HTML. The text is escaped, so nothing in it can act as HTML; line breaks are kept."""
    content = html.escape(text.strip()).replace("\n", "<br>\n")
    if button_text and button_url:
        content += f'\n<p><a href="{html.escape(button_url, quote=True)}"><b>{html.escape(button_text)}</b></a></p>'
    return content


def blogger_publish(title: str, text: str, button_text: str = "", button_url: str = "") -> dict:
    """Publishes the post. Returns {"ok", "link", "error"}."""
    if not title.strip() or not text.strip():
        return {"ok": False, "link": "", "error": "the post needs a title and a text"}
    if config.BLOGGER_PROVIDER == "fake":
        return {"ok": True, "link": "", "error": ""}
    problem = settings_problem()
    if problem:
        return {"ok": False, "link": "", "error": problem}
    token, problem = _access_token()
    if problem:
        return {"ok": False, "link": "", "error": problem}

    # → Blogger API: creates the blog post (called by the MCP tool)
    answer = _call("POST", "/posts/", token, {"kind": "blogger#post", "title": title.strip(),
                                              "content": post_html(text, button_text, button_url)})
    if not answer.get("id"):
        return {"ok": False, "link": "", "error": (answer.get("error") or {}).get("message") or "Blogger refused the post"}
    return {"ok": True, "link": answer.get("url") or "", "error": ""}


def blogger_check() -> dict:
    """Says in plain words whether publishing will work. Publishes nothing."""
    if config.BLOGGER_PROVIDER == "fake":
        return {"ok": True, "message": "Fake Blogger is on (BLOGGER_PROVIDER=fake): nothing is really published."}
    problem = settings_problem()
    if problem:
        return {"ok": False, "message": problem}
    token, problem = _access_token()
    if problem:
        return {"ok": False, "message": problem}
    blog = _call("GET", "", token)
    if not blog.get("id"):
        return {"ok": False, "message": "The blog was not found: " + ((blog.get("error") or {}).get("message") or "unknown error")
                                        + ". Check BLOGGER_BLOG_ID."}
    return {"ok": True, "message": f"The Google login works and the blog \"{blog.get('name')}\" can be reached."}
