"""Sends the invitation email over SMTP (for example Gmail). Plain code: no AI, no MCP server.

Who calls it:
    send_email()             the invitation workflow, step "send_email", after the interviewer clicks Send
                             (graphs/invitation_graph.py)
    check_email_settings()   the "Test email" button on the Settings page (GET /api/email-check)

How one email is sent (send_email, top to bottom):
    1. check the settings and the address     4. log in with SMTP_USER / SMTP_PASSWORD
    2. build the email: text + calendar invite 5. hand the email to the mail server
    3. open an encrypted connection           6. answer {"ok": True} or {"ok": False, "error": "<plain reason>"}

The settings come from .env through config.py: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM.
Error texts are written by hand here, so a password can never end up in one.
"""
import smtplib
import socket
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.core import config

TIMEOUT_SEC = 20                       # give up when the mail server does not answer within 20 seconds


def send_email(to: str, subject: str, body: str, calendar: str = "") -> dict:
    """Sends one email with the calendar invite.

    to, subject, body   the candidate's address and the invitation as the interviewer checked it
    calendar            the .ics text from calendar_service.calendar_invite() ("" = no invite)
    Returns {"ok": True, "error": ""} or {"ok": False, "error": "<plain reason>"}.
    """
    # 1. Check before connecting: settings and the address
    if not config.SMTP_HOST:
        return {"ok": False, "error": "SMTP_HOST is empty in .env"}
    if not config.SMTP_FROM:
        return {"ok": False, "error": "SMTP_FROM (or SMTP_USER) is empty in .env"}
    if "@" not in to or len(to) > 200:
        return {"ok": False, "error": "the email address of the candidate does not look right"}

    # 2. Build the email
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = config.SMTP_FROM, to, subject
    message["Date"] = formatdate(localtime=False)                # the sending time, in the format mail apps expect
    message["Message-ID"] = make_msgid(domain="lumenai")         # a unique id, so mail apps never mix two emails up
    message.set_content(body)                                    # the text the candidate reads
    if calendar:
        # the invite twice: as a calendar part (Gmail / Outlook show "Add to calendar" with Yes / No) ...
        message.add_alternative(calendar, subtype="calendar", params={"method": "REQUEST"})
        # ... and as the file invite.ics, which any calendar app can open
        message.add_attachment(calendar.encode("utf-8"), maintype="text", subtype="calendar", filename="invite.ics",
                               params={"method": "REQUEST"})

    # 3-5. Connect, log in, send
    try:
        with _open_connection() as server:                       # "with" closes the connection at the end
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)   # Gmail: an app password, not the normal one
            server.send_message(message)                         # → hands the finished email to the mail server
    except Exception as problem:                                 # never str(problem): it may repeat the login
        return {"ok": False, "error": _plain_reason(problem)}
    return {"ok": True, "error": ""}


def check_email_settings() -> dict:
    """The "Test email" button: are the settings complete, and does the mail server accept the login?
    Sends nothing. Returns {"ok": True/False, "message": "<plain words>"}."""
    if not config.SMTP_HOST:
        return {"ok": False, "message": "SMTP_HOST is empty in .env, so invitations are saved but not sent."}
    if not config.SMTP_FROM:
        return {"ok": False, "message": "SMTP_FROM (or SMTP_USER) is empty in .env: the sender address is missing."}
    if config.SMTP_USER and not config.SMTP_PASSWORD:
        return {"ok": False, "message": "SMTP_PASSWORD is empty in .env (for Gmail: an app password)."}
    try:
        with _open_connection() as server:
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)   # only logs in, sends nothing
    except Exception as problem:
        return {"ok": False, "message": _plain_reason(problem)}
    return {"ok": True, "message": f"The email server {config.SMTP_HOST} accepted the login. Nothing was sent."}


def _open_connection() -> smtplib.SMTP:
    """Opens an encrypted connection to the mail server (used by both functions above)."""
    if config.SMTP_PORT == 465:
        # port 465: encrypted (SSL) from the first byte
        return smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=TIMEOUT_SEC)
    server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=TIMEOUT_SEC)   # port 587: starts unencrypted
    if config.SMTP_STARTTLS:
        server.starttls()                                        # switch to encrypted before the password is sent
    return server


def _plain_reason(problem: Exception) -> str:
    """Turns an SMTP error into plain words, without the password or the server's own text."""
    if isinstance(problem, smtplib.SMTPAuthenticationError):
        return "the email server did not accept the login (check SMTP_USER and SMTP_PASSWORD; Gmail needs an app password)"
    if isinstance(problem, smtplib.SMTPRecipientsRefused):
        return "the email server refused the address of the candidate"
    if isinstance(problem, (socket.timeout, TimeoutError)):
        return "the email server did not answer in time"
    if isinstance(problem, OSError) and not isinstance(problem, smtplib.SMTPException):   # wrong host or port
        return f"cannot reach the email server {config.SMTP_HOST}:{config.SMTP_PORT}"
    return f"the email server refused the email ({type(problem).__name__})"
