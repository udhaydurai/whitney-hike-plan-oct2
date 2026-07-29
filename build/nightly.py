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

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "training-log.json"

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

    date = patch.get("date")
    if not date:
        fail("patch has no date")
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        fail(f"date {date!r} is not YYYY-MM-DD")

    d = json.loads(LOG.read_text(encoding="utf-8"))
    changed = []

    # ── hike subjective merge
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
        target = next((h for h in d["hikes"] if h["date"] == date), None)
        if target is None:
            fail(f"no hike on {date}. The hike record is created by the weekly Garmin "
                 f"rebuild; a nightly patch can only annotate one that exists.")
        for k, v in hp.items():
            before = target.get(k)
            if before != v:
                target[k] = v
                changed.append(f"hikes[{date}].{k}: {before!r} -> {v!r}")

    # ── daily record for non-hike days: this is the whole point of the nightly cadence
    if "dailyLog" in patch:
        d.setdefault("dailyLog", [])
        entry = dict(patch["dailyLog"])
        bad = sorted(set(entry) & OBJECTIVE)
        if bad:
            fail("dailyLog may not carry Garmin-owned fields: " + ", ".join(bad))
        entry["date"] = date
        existing = next((e for e in d["dailyLog"] if e.get("date") == date), None)
        if existing:
            existing.update(entry)
            changed.append(f"dailyLog[{date}] updated ({len(entry)-1} field(s))")
        else:
            d["dailyLog"].append(entry)
            d["dailyLog"].sort(key=lambda e: e["date"])
            changed.append(f"dailyLog[{date}] added ({len(entry)-1} field(s))")

    # ── issues
    for text in patch.get("openIssues") or []:
        d["openIssues"].append({"raised": date, "issue": text, "status": "open"})
        changed.append(f"openIssues += {text[:60]!r}")

    for needle in patch.get("resolveIssues") or []:
        hit = [i for i in d["openIssues"]
               if needle.lower() in json.dumps(i).lower() and i.get("status") != "resolved"]
        if not hit:
            print(f"note: no open issue matched {needle!r}", file=sys.stderr)
        for i in hit:
            i["status"] = "resolved"
            i["resolved"] = date
            changed.append(f"issue resolved: {needle[:50]!r}")

    if not changed:
        print("no change")
        return

    d["meta"]["lastNightlyCheckIn"] = date
    LOG.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"applied {len(changed)} change(s) for {date}:")
    for c in changed:
        print(f"   {c}")


if __name__ == "__main__":
    main()
