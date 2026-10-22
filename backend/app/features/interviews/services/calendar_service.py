"""The calendar invite (.ics file) that goes with the invitation email. Made by code, no AI.

Who calls it: invitation_service.calendar_for(), when the interviewer clicks Send.
Gmail, Outlook and Apple Mail show it as an event with "Add to calendar" / Yes / No.
The event keeps the same id (UID) for one interview and gets a higher SEQUENCE when the time changes, so the
candidate's calendar moves the event instead of adding a second one.
"""
from datetime import datetime, timedelta, timezone


def calendar_invite(uid: str, start: datetime, minutes: int, title: str, description: str, link: str,
                    organizer: str, attendee: str, attendee_name: str, sequence: int) -> str:
    """Returns the text of the .ics file (iCalendar format, RFC 5545) for one interview.

    uid        the same for one interview every time it is sent, e.g. "interview-7-a1b2c3@lumenai"
    start      the interview time (with time zone); minutes = its length
    sequence   0 for the first invite, +1 for each new time (the calendar then updates the event)
    organizer  the sender's address (SMTP_FROM); attendee = the candidate's address
    """
    def clean(text: str) -> str:
        # , ; \ and line breaks have a meaning in .ics, so they get a backslash in front
        return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
                .replace("\r\n", "\\n").replace("\n", "\\n"))

    def utc(moment: datetime) -> str:
        return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")   # e.g. 20261020T090000Z (Z = UTC)

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//LumenAI//Interview invitation//EN", "CALSCALE:GREGORIAN",
             "METHOD:REQUEST",                                   # REQUEST = an invitation the person can accept
             "BEGIN:VEVENT",
             f"UID:{uid}", f"SEQUENCE:{sequence}", f"DTSTAMP:{utc(datetime.now(timezone.utc))}",
             f"DTSTART:{utc(start)}", f"DTEND:{utc(start + timedelta(minutes=minutes))}",
             f"SUMMARY:{clean(title)}", f"DESCRIPTION:{clean(description)}",
             f"LOCATION:{clean(link)}", f"URL:{link}", "STATUS:CONFIRMED", "TRANSP:OPAQUE"]   # OPAQUE = shows as busy
    if organizer:
        lines.append(f"ORGANIZER;CN={clean('Hiring team')}:mailto:{organizer}")
    if attendee:
        name = clean(attendee_name or attendee).replace(":", " ")
        lines.append(f"ATTENDEE;CN={name};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{attendee}")
    lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Interview in 15 minutes", "TRIGGER:-PT15M",  # reminder
              "END:VALARM", "END:VEVENT", "END:VCALENDAR"]

    # An .ics line may have at most 75 bytes: a longer line continues on the next line, which starts with a space
    folded = []
    for line in lines:
        data, parts = line.encode("utf-8"), []
        while len(data) > 75:
            cut = 75 if not parts else 74
            while cut > 0 and (data[cut] & 0xC0) == 0x80:       # never cut a letter that takes several bytes in half
                cut -= 1
            parts.append(data[:cut].decode("utf-8"))
            data = data[cut:]
        parts.append(data.decode("utf-8"))
        folded.append("\r\n ".join(parts))
    return "\r\n".join(folded) + "\r\n"                         # .ics files use \r\n line ends
