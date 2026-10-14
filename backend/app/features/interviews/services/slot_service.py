"""Suggests interview times for the shortlist: one after another, inside working hours, never over the lunch break
or on the weekend. Plain date maths, no AI. Nothing is saved here: the interviewer sees the times, can change any of
them, and then schedules (interview_service.schedule_many).

    plan_slots(count, first_day, minutes, time_zone, hours)   → [start, start, ...]   (aware datetimes)

Example (45 minutes, 8:00-17:00, lunch 12:30-13:30): 8:00, 8:45, ... 11:45 (ends 12:30), 13:30, ... 15:45 (ends 16:30),
then 8:00 on the next working day, because 16:30-17:15 would pass 17:00.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

WEEKEND = {5, 6}          # Saturday and Sunday (Monday = 0): no interviews
MAX_DAYS = 120            # look at most this many days ahead, so a wrong setting can never loop for ever


@dataclass
class WorkingHours:
    day_start: time = time(8, 0)
    day_end: time = time(17, 0)
    lunch_start: time | None = time(12, 30)          # None (both) = no lunch break
    lunch_end: time | None = time(13, 30)


# Explains in plain words why the hours cannot be used, or "" when they are fine
def hours_problem(hours: WorkingHours, minutes: int) -> str:
    if hours.lunch_start is None:                    # no lunch break: only the working day must be long enough
        if not hours.day_start < hours.day_end:
            return "The end of the day must be after its start."
        if minutes > _minutes_between(hours.day_start, hours.day_end):
            return f"A {minutes}-minute interview does not fit in the working day."
        return ""
    if not hours.day_start < hours.lunch_start < hours.lunch_end < hours.day_end:
        return "The times must be in order: start of the day, lunch start, lunch end, end of the day."
    morning = _minutes_between(hours.day_start, hours.lunch_start)
    afternoon = _minutes_between(hours.lunch_end, hours.day_end)
    if minutes > max(morning, afternoon):
        return f"A {minutes}-minute interview does not fit before or after the lunch break."
    return ""


# Minutes from one clock time to a later one on the same day
def _minutes_between(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


# The given day and clock time in the interviewer's time zone
def _at(day: date, clock: time, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, clock, tzinfo=zone)


# True when the two time ranges overlap (one starts before the other ends)
def _overlaps(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return start < other_end and end > other_start


def plan_slots(count: int, first_day: date, minutes: int, time_zone: str, hours: WorkingHours,
               busy: list[tuple[datetime, datetime]] = (), now: datetime | None = None,
               not_before: datetime | None = None) -> list[datetime]:
    """`count` start times from `first_day` on. `busy` = the interviewer's interviews already planned (start, end):
    a new one never overlaps them. Nothing starts before `now` (so "today" starts at the next free time) or before
    `not_before` (the "Start at" time, or the end of the interviewer's last interview)."""
    zone = ZoneInfo(time_zone)
    now = now or datetime.now(timezone.utc)
    length = timedelta(minutes=minutes)
    starts: list[datetime] = []
    day = first_day
    for _ in range(MAX_DAYS):
        if len(starts) == count:
            break
        if day.weekday() not in WEEKEND:
            starts += _slots_of_day(day, count - len(starts), length, zone, hours, list(busy) + _ranges(starts, length), now,
                                    not_before)
        day += timedelta(days=1)
    return starts


# The free start times of one working day, at most `wanted` of them
def _slots_of_day(day: date, wanted: int, length: timedelta, zone: ZoneInfo, hours: WorkingHours,
                  busy: list[tuple[datetime, datetime]], now: datetime, not_before: datetime | None) -> list[datetime]:
    has_lunch = hours.lunch_start is not None
    lunch_start = _at(day, hours.lunch_start, zone) if has_lunch else None
    lunch_end = _at(day, hours.lunch_end, zone) if has_lunch else None
    day_end = _at(day, hours.day_end, zone)
    found = []
    start = _at(day, hours.day_start, zone)
    while len(found) < wanted and start + length <= day_end:
        end = start + length
        if has_lunch and _overlaps(start, end, lunch_start, lunch_end):   # would run into lunch: start after it
            start = lunch_end
            continue
        clash = next((b for a, b in busy if _overlaps(start, end, a, b)), None)
        if clash:                                                 # the interviewer is busy: start after that one
            start = clash
            continue
        if not_before and start < not_before:                     # before "Start at" / the last interview: start there
            start = not_before
            continue
        if start <= now:                                          # already past (today): try the next slot
            start = end
            continue
        found.append(start)
        start = end                                               # no gap: the next one starts when this one ends
    return found


# The (start, end) ranges of the times found so far
def _ranges(starts: list[datetime], length: timedelta) -> list[tuple[datetime, datetime]]:
    return [(s, s + length) for s in starts]
