"""The calendar invite (.ics file) that goes with the invitation email. Made by code, no AI.

    calendar_invite(...)   the text of the .ics file (iCalendar, RFC 5545)

Gmail, Outlook and Apple Mail show it as an event with "Add to calendar" / Yes / No. The event has the same id
(UID) every time it is sent for one interview, and a higher SEQUENCE when the time changed, so the candidate's
calendar moves the event instead of adding a second one.
"""
from datetime import datetime, timedelta, timezone


def _escape(text: str) -> str:
    """Commas, semicolons, backslashes and line breaks have a meaning in .ics text, so they are escaped."""
    return (text.replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """An .ics line may have at most 75 bytes; a longer one continues on the next line after a space."""
    data, parts = line.encode("utf-8"), []
    while len(data) > 75:
        cut = 75 if not parts else 74
        while cut > 0 and (data[cut] & 0xC0) == 0x80:       # never cut a letter that takes several bytes in half
            cut -= 1
        parts.append(data[:cut].decode("utf-8"))
        data = data[cut:]
    parts.append(data.decode("utf-8"))
    return "\r\n ".join(parts)


# Writes a time as UTC in the .ics format, e.g. 20261020T090000Z
def _utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# Builds the .ics text of the interview event (same UID, higher SEQUENCE on a new time)
def calendar_invite(uid: str, start: datetime, minutes: int, title: str, description: str, link: str,
                    organizer: str, attendee: str, attendee_name: str, sequence: int) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//LumenAI//Interview invitation//EN", "CALSCALE:GREGORIAN",
             "METHOD:REQUEST", "BEGIN:VEVENT",
             f"UID:{uid}", f"SEQUENCE:{sequence}", f"DTSTAMP:{_utc(datetime.now(timezone.utc))}",
             f"DTSTART:{_utc(start)}", f"DTEND:{_utc(start + timedelta(minutes=minutes))}",
             f"SUMMARY:{_escape(title)}", f"DESCRIPTION:{_escape(description)}",
             f"LOCATION:{_escape(link)}", f"URL:{link}", "STATUS:CONFIRMED", "TRANSP:OPAQUE"]
    if organizer:
        lines.append(f"ORGANIZER;CN={_escape('Hiring team')}:mailto:{organizer}")
    if attendee:
        name = _escape(attendee_name or attendee).replace(":", " ")
        lines.append(f"ATTENDEE;CN={name};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{attendee}")
    lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Interview in 15 minutes", "TRIGGER:-PT15M", "END:VALARM",
              "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
