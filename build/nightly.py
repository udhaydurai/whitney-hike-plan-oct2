#!/usr/bin/env python3
"""
Apply one night's check-in to the training log — subjective fields only.

The rule this file exists to enforce, in the user's words:

    "why do you have to use the pdf for data? Garmin has all the data and i shared it.
     pdf should be used for fueling, my mood or anything which is not there in the data"

So the nightly path is deliberately incapable of writing an objective metric. If a
patch contains distance, ascent, heart rate, calories, moving time or anything else
Garmin measures, this refuses the whole patch rather than quietly taking the rest.
That is stricter than warning, and it is the right way round: a wrong distance typed
from memory on a Tuesday would survive into the dashboard and be indistinguishable
from a measured one. The weekly Garmin rebuild is the only writer of those fields.

Writes data/daily/<date>.json — one file per day, never the shared log. That is what
stops the nightly scheduled task and an interactive session from colliding: a new date
is a new path, and git merges different paths without help. build/dashboard.py merges
the directory at build time.

Usage:
    python3 build/nightly.py patch.json
    echo '{"date":"2026-07-29","dailyLog":{...}}' | python3 build/nightly.py -

Patch shape — every key optional:

    {
      "date": "2026-07-29",
      "hike":     { subjective hike fields, merged into the hike on that date },
      "dailyLog": { free-form weekday record: meals, carbs, protein, how it felt },
      "openIssues":   [ "text to append" ],
      "resolveIssues":[ "substring of an existing issue to mark resolved" ]
    }
"""

import json
import pathlib
import sys
import datetime as dt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import clock

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "training-log.json"
DAILY = ROOT / "data" / "daily"

# ── Garmin's territory. Present in a nightly patch, this is an error, not a warning.
OBJECTIVE = {
    "distanceMi", "ascentFt", "descentFt", "minElevFt", "maxElevFt",
    "totalTime", "movingTime", "stoppedPct", "avgPace", "movingPace",
    "avgSpeedMph", "movingSpeedMph", "avgHR", "maxHR", "totalCal",
    "aerobicEffect", "anaerobicEffect", "exerciseLoad", "steps",
    "bodyBattery", "restingCal", "sweatLossMl", "hrZoneSec", "vo2Max",
    "calories", "durSec", "source", "kind",
}

# ── what the conversation is allowed to supply. Anything outside both sets is a typo
#    worth catching rather than silently storing under a misspelled key.
SUBJECTIVE = {
    "route", "label", "effortType", "effortNote", "poles", "packLb", "boots",
    "partners", "fuel", "notes", "coachNote", "flag", "sleep", "weather",
    "primaryBenefit", "recoveryHours", "symptoms", "preWeightLb", "postWeightLb",
    "gelsTaken", "sodiumMg", "waterL", "caffeineMg",
}


def fail(msg):
    print(f"REFUSED: {msg}", file=sys.stderr)
    sys.exit(2)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    raw = sys.stdin.read() if src == "-" else pathlib.Path(src).read_text(encoding="utf-8")
    try:
        patch = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"patch is not valid JSON — {e}")

    # ── the date, in the athlete's timezone
    #
    # The container runs UTC and the nightly job fires at 9 pm Pacific, which is already
    # tomorrow in UTC. The first night's check-in was filed a day ahead because of exactly
    # that. Default to the local date, and refuse anything ahead of it — a check-in
    # describing food already eaten can be for today or earlier, never for the future.
    local = clock.today()
    date = patch.get("date") or local.isoformat()
    try:
        d0 = dt.date.fromisoformat(date)
    except ValueError:
        fail(f"date {date!r} is not YYYY-MM-DD")

    if d0 > local:
        fail(f"{date} is in the future — local date is {local.isoformat()} "
             f"({clock.now():%H:%M %Z}).\n"
             f"         If this came from date.today() in the container, that is UTC and "
             f"runs ahead after 5 pm Pacific. Use build/clock.py.")
    if (local - d0).days > 3:
        fail(f"{date} is {(local - d0).days} days ago (local date {local.isoformat()}). "
             f"Pass it explicitly again if that is really intended.")

    log = json.loads(LOG.read_text(encoding="utf-8"))

    # ── validate against the same rules as before, but write to data/daily/<date>.json
    #    rather than into the shared log. See the merge comment in build/dashboard.py:
    #    one file per date is what makes the nightly job and an interactive session stop
    #    being two writers on one file.
    hp = patch.get("hike") or {}
    if hp:
        bad = sorted(set(hp) & OBJECTIVE)
        if bad:
            fail("nightly check-in may not write Garmin-owned fields: "
                 + ", ".join(bad)
                 + ".\n         Those come from the weekly export via build/rebuild_data.py.")
        unknown = sorted(set(hp) - SUBJECTIVE)
        if unknown:
            fail("unrecognised field(s): " + ", ".join(unknown)
                 + ".\n         Add to SUBJECTIVE in build/nightly.py if genuinely new.")
        if not any(h["date"] == date for h in log["hikes"]):
            fail(f"no hike on {date}. The hike record is created by the weekly Garmin "
                 f"rebuild; a nightly patch can only annotate one that exists.")

    dl = patch.get("dailyLog")
    if dl:
        bad = sorted(set(dl) & OBJECTIVE)
        if bad:
            fail("dailyLog may not carry Garmin-owned fields: " + ", ".join(bad))

    if not any(patch.get(k) for k in ("hike", "dailyLog", "openIssues", "resolveIssues")):
        fail("patch has nothing in it — expected hike, dailyLog, openIssues or resolveIssues")

    DAILY.mkdir(parents=True, exist_ok=True)
    out = DAILY / f"{date}.json"

    # a second check-in on the same evening merges into that day's file rather than
    # replacing it, so an afternoon note is not lost by a bedtime one
    rec = {}
    if out.exists():
        rec = json.loads(out.read_text(encoding="utf-8"))
    for k in ("hike", "dailyLog"):
        if patch.get(k):
            rec[k] = {**(rec.get(k) or {}), **patch[k]}
    for k in ("openIssues", "resolveIssues"):
        if patch.get(k):
            rec[k] = list(dict.fromkeys((rec.get(k) or []) + patch[k]))
    rec["date"] = date

    out.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    fields = sum(len(v) for k, v in rec.items() if isinstance(v, (dict, list)))
    print(f"wrote {out.relative_to(ROOT)} — {fields} field(s) for {date}")
    for k, v in rec.items():
        if k != "date":
            print(f"   {k}: {v if not isinstance(v, dict) else ', '.join(v)}")


if __name__ == "__main__":
    main()
