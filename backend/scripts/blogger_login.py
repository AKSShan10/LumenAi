"""Log in to Google ONCE, so LumenAI may publish on your blog. Gives you the refresh token for .env.

Run it from the backend folder, on your own computer (not inside Docker: it opens your browser):

    python scripts/blogger_login.py

Before that, put BLOGGER_CLIENT_ID and BLOGGER_CLIENT_SECRET in the .env file (from Google Cloud Console).
The script opens Google's login page, waits for you to click Allow, and prints one line to copy into .env.
The refresh token is a secret: it is printed only in your own terminal. Never share or commit it.
"""
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import dotenv_values

PORT = 8765                                           # Google sends the browser back to http://127.0.0.1:8765
REDIRECT = f"http://127.0.0.1:{PORT}"
SCOPE = "https://www.googleapis.com/auth/blogger"     # permission: manage your Blogger posts
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

answer = {}                                           # what Google sent back to the browser


class CatchTheCode(BaseHTTPRequestHandler):
    def do_GET(self):
        answer.update({key: values[0] for key, values in parse_qs(urlparse(self.path).query).items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h3>Done. You can close this tab and go back to the terminal.</h3>")

    def log_message(self, *args):                     # keep the terminal quiet (the address holds the code)
        pass


def main():
    settings = dotenv_values(ENV_FILE)
    client_id, client_secret = settings.get("BLOGGER_CLIENT_ID"), settings.get("BLOGGER_CLIENT_SECRET")
    if not client_id or not client_secret:
        return print(f"Put BLOGGER_CLIENT_ID and BLOGGER_CLIENT_SECRET in {ENV_FILE} first.")

    state = secrets.token_urlsafe(16)                 # a random word, to be sure the answer belongs to this login
    login_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state})   # offline + consent = we get a refresh token
    print("Your browser opens now. Log in with the Google account that owns the blog and click Allow.")
    print("If it does not open, copy this address into the browser:\n" + login_url)
    webbrowser.open(login_url)

    server = HTTPServer(("127.0.0.1", PORT), CatchTheCode)
    while "code" not in answer and "error" not in answer:
        server.handle_request()                       # wait for Google to send the browser back
    if answer.get("error") or answer.get("state") != state:
        return print("The login was not finished:", answer.get("error") or "the answer did not match this login")

    tokens = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
        "code": answer["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"}).json()
    if not tokens.get("refresh_token"):
        return print("Google gave no refresh token:", tokens.get("error_description") or tokens.get("error") or "unknown error")

    print("\nIt worked. Copy this line into your .env file (replace the old one if there is one):\n")
    print("BLOGGER_REFRESH_TOKEN=" + tokens["refresh_token"])
    print("\nThen start the backend again and click \"Test job posting\" on the Settings page.")


if __name__ == "__main__":
    main()
