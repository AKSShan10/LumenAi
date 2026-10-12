"""Sends an email over SMTP, with the calendar invite. Used by the email MCP server (and directly when
EMAIL_TRANSPORT=smtp).

    send_email(to, subject, body, calendar)   {"ok": True} or {"ok": False, "error": "<plain reason>"}
    check_email_settings()                    {"ok", "message"}: are the settings complete? Sends nothing

The email has the text, the calendar invite as a calendar part (Gmail and Outlook show "Add to calendar" with
Yes / No), and the same invite as the file invite.ics.
Error texts are written by hand here, so a password can never end up in one.
"""
import smtplib
import socket
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.core import config

TIMEOUT_SEC = 20


def check_email_settings() -> dict:
    if not config.SMTP_HOST:
        return {"ok": False, "message": "SMTP_HOST is empty in .env, so invitations are saved but not sent."}
    if not config.SMTP_FROM:
        return {"ok": False, "message": "SMTP_FROM (or SMTP_USER) is empty in .env: the sender address is missing."}
    if config.SMTP_USER and not config.SMTP_PASSWORD:
        return {"ok": False, "message": "SMTP_PASSWORD is empty in .env (for Gmail: an app password)."}
    try:
        with _connect() as server:
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
    except Exception as problem:                      # never str(problem): it may repeat the login
        return {"ok": False, "message": _reason(problem)}
    return {"ok": True, "message": f"The email server {config.SMTP_HOST} accepted the login. Nothing was sent."}


def _connect() -> smtplib.SMTP:
    if config.SMTP_PORT == 465:
        return smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=TIMEOUT_SEC)
    server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=TIMEOUT_SEC)
    if config.SMTP_STARTTLS:
        server.starttls()
    return server


def _reason(problem: Exception) -> str:
    if isinstance(problem, smtplib.SMTPAuthenticationError):
        return "the email server did not accept the login (check SMTP_USER and SMTP_PASSWORD; Gmail needs an app password)"
    if isinstance(problem, smtplib.SMTPRecipientsRefused):
        return "the email server refused the address of the candidate"
    if isinstance(problem, (socket.timeout, TimeoutError)):
        return "the email server did not answer in time"
    if isinstance(problem, (ConnectionRefusedError, socket.gaierror, OSError)) and not isinstance(problem, smtplib.SMTPException):
        return f"cannot reach the email server {config.SMTP_HOST}:{config.SMTP_PORT}"
    return f"the email server refused the email ({type(problem).__name__})"


def build_message(to: str, subject: str, body: str, calendar: str = "") -> EmailMessage:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = config.SMTP_FROM, to, subject
    message["Date"], message["Message-ID"] = formatdate(localtime=False), make_msgid(domain="lumenai")
    message.set_content(body)
    if calendar:
        # as an alternative part: mail apps show the event with Yes / No; as a file: any app can open it
        message.add_alternative(calendar, subtype="calendar", params={"method": "REQUEST"})
        message.add_attachment(calendar.encode("utf-8"), maintype="text", subtype="calendar", filename="invite.ics",
                               params={"method": "REQUEST"})
    return message


def send_email(to: str, subject: str, body: str, calendar: str = "") -> dict:
    problem = check_settings_quickly()
    if problem:
        return {"ok": False, "error": problem}
    if "@" not in to or len(to) > 200:
        return {"ok": False, "error": "the email address of the candidate does not look right"}
    try:
        with _connect() as server:
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(build_message(to, subject, body, calendar))
    except Exception as problem:
        return {"ok": False, "error": _reason(problem)}
    return {"ok": True, "error": ""}


def check_settings_quickly() -> str:
    """The settings problem without connecting, or ""."""
    if not config.SMTP_HOST:
        return "SMTP_HOST is empty in .env"
    if not config.SMTP_FROM:
        return "SMTP_FROM (or SMTP_USER) is empty in .env"
    return ""
