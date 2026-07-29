#!/usr/bin/env python3
"""
One definition of "today", in the athlete's timezone.

The container runs on UTC. The nightly check-in fires at 9 pm Pacific, which is 04:00
UTC the *following* day, so anything reaching for `date.today()` filed Tuesday evening's
food under Wednesday — every night, silently, and the record would have drifted a day
out from the training calendar it is compared against.

Everything that needs a current date imports from here. Nothing calls date.today()
directly. A hike log is worthless if the dates are a day off from the calendar.
"""

import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")


def now():
    """Current local time where the training actually happens."""
    return dt.datetime.now(TZ)


def today():
    """Local calendar date. This is the only correct answer to 'what day is it'."""
    return now().date()


def iso():
    return today().isoformat()


def pretty(d=None):
    """'Jul 28, 2026' without a zero-padded day, portably."""
    d = d or today()
    return d.strftime("%b %d, %Y").replace(" 0", " ")


if __name__ == "__main__":
    print(f"UTC     {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC")
    print(f"local   {now():%Y-%m-%d %H:%M %Z}")
    print(f"today   {iso()}")
    if now().date() != dt.datetime.now(dt.timezone.utc).date():
        print("NOTE: the container date and the local date differ right now — this is "
              "exactly the window the nightly check-in runs in.")
