#!/usr/bin/env python3
"""
Scan an extracted Garmin bulk export and produce ONE small file worth sending.

Why: the full export is mostly account and service metadata — aviation, marine,
Navionics, inReach, e-commerce records. None of that is training data, and none of
it needs to leave your machine. The fitness data lives in a single subtree.

Run it on the extracted folder:
    python garmin_digest.py "C:\\Users\\Sudha\\Downloads\\Garmin_history"

It writes garmin_digest.json next to itself: every hike and walk it can find, with
distance, elevation, duration, heart rate, calories and training effect. That single
file is enough to rebuild the whole training log.

Add --copy-fit DIR to also gather the .fit files for long activities, so you can zip
a handful rather than hundreds.

NOTE: written against Garmin's documented export layout but not tested on your file.
If it reports nothing found, it prints what it DID see — send me that and I'll fix it.
"""

import argparse
import json
import os
import pathlib
import shutil
import sys
import datetime as _dt

CM_TO_MI = 6.2137e-6      # Garmin stores distance in centimetres
CM_TO_FT = 0.0328084
MS_TO_S = 1 / 1000
KJ_TO_KCAL = 1 / 4.184   # this export stores energy in kilojoules

# "rucking" is its own Garmin activity type and shares no substring with the others —
# leaving it out silently dropped 11 sessions on the first pass.
HIKEY = ("hiking", "hike", "walking", "walk", "mountaineering", "trail_running", "rucking")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pick(d, *names):
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return None


def guess_distance_mi(v):
    """
    summarizedActivities stores distance in CENTIMETRES, always.

    An earlier version guessed the unit from magnitude, which broke on short
    activities: a 0.5 mi walk is 80,000 cm, below the 100,000 threshold, so it got
    read as metres. Verified against San Jacinto — 2,131,327 cm = 13.24 mi, matching
    both the FIT file and the app.
    """
    v = num(v)
    return None if v is None else round(v * CM_TO_MI, 2)


def guess_elev_ft(v):
    """
    Also centimetres. The magnitude heuristic here was worse: it reported 31,824 ft
    of ascent on a 6-mile neighbourhood walk, because 9,700 cm fell under the
    threshold and was treated as 9,700 metres. Verified against San Jacinto —
    139,900 cm = 4,590 ft and 329,720 cm = 10,817 ft max.
    """
    v = num(v)
    return None if v is None else round(v * CM_TO_FT)


def guess_seconds(v):
    v = num(v)
    if v is None:
        return None
    return round(v * MS_TO_S) if v > 100_000 else round(v)


def when(v):
    """Garmin's beginTimestamp is epoch milliseconds; startTimeLocal is a string."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    n = num(v)
    if n is None:
        return str(v)
    if n > 1e11:          # milliseconds
        n /= 1000
    try:
        return _dt.datetime.utcfromtimestamp(n).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return str(v)


def secs(t):
    """'11:04:30' -> 39870. For numeric sorting, since string sort puts 11h before 8h."""
    if not t:
        return -1
    p = [int(x) for x in str(t).split(":")]
    return p[0]*3600 + p[1]*60 + p[2] if len(p) == 3 else p[0]*60 + p[1]


def hhmmss(s):
    if s is None:
        return None
    s = int(s)
    return f"{s//3600}:{(s%3600)//60:02d}:{s%60:02d}"


def find_activity_json(root):
    hits = []
    for p in root.rglob("*.json"):
        n = p.name.lower()
        if "summarizedactivities" in n or "activities" in n:
            hits.append(p)
    return hits


def flatten(obj):
    """Garmin nests the list under a wrapper key that has changed over the years."""
    if isinstance(obj, list):
        for item in obj:
            yield from flatten(item)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and "activit" in k.lower():
                for item in v:
                    if isinstance(item, dict):
                        yield item
                return
        if "activityId" in obj or "activityType" in obj:
            yield obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--out", default="garmin_digest.json")
    ap.add_argument("--copy-fit", metavar="DIR",
                    help="copy .fit files for activities over --min-hours into DIR")
    ap.add_argument("--min-hours", type=float, default=3.0)
    ap.add_argument("--all-types", action="store_true",
                    help="keep every activity type, not just hikes and walks")
    a = ap.parse_args()

    root = pathlib.Path(a.folder).expanduser()
    if not root.exists():
        sys.exit(f"Folder not found: {root}")

    # --- orientation: what is actually in here
    tops = sorted([p.name for p in root.iterdir() if p.is_dir()])
    fits = list(root.rglob("*.fit"))
    jsons = list(root.rglob("*.json"))
    print(f"scanning {root}")
    print(f"  top-level folders : {len(tops)}")
    print(f"  .fit files        : {len(fits)}")
    print(f"  .json files       : {len(jsons)}")
    di = [t for t in tops if t.upper().startswith("DI_CONNECT")]
    print(f"  DI_CONNECT present: {'YES ' + di[0] if di else 'NO  <-- the fitness data lives here'}")

    cand = find_activity_json(root)
    print(f"  activity JSON     : {len(cand)}")
    for c in cand[:6]:
        print(f"      {c.relative_to(root)}  ({c.stat().st_size/1024:.0f} KB)")

    acts = []
    for c in cand:
        try:
            data = json.loads(c.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            print(f"  ! could not parse {c.name}: {e}")
            continue
        for r in flatten(data):
            acts.append(r)

    if not acts:
        print("\nNo activity records recognised. Here is what I saw, so we can fix the parser:")
        for t in tops:
            print("   ", t)
        if jsons:
            s = jsons[0]
            print(f"\nfirst 600 chars of {s.relative_to(root)}:")
            print(s.read_text(encoding='utf-8', errors='replace')[:600])
        return

    out = []
    seen = set()
    for r in acts:
        aid = pick(r, "activityId", "activityid")
        if aid in seen:
            continue
        seen.add(aid)
        atype = str(pick(r, "activityType", "activityTypeDTO", "sportType") or "").lower()
        if isinstance(pick(r, "activityType"), dict):
            atype = str(pick(r, "activityType").get("typeKey", "")).lower()
        if not a.all_types and not any(k in atype for k in HIKEY):
            continue
        dur = guess_seconds(pick(r, "duration", "elapsedDuration", "sumElapsedDuration"))
        mov = guess_seconds(pick(r, "movingDuration", "sumMovingDuration"))
        rec = {
            "activityId": aid,
            "name": pick(r, "activityName", "name"),
            "type": atype or None,
            "start": when(pick(r, "startTimeLocal", "startTimeGMT", "beginTimestamp")),
            "durSec": dur,
            "distanceMi": guess_distance_mi(pick(r, "distance", "sumDistance")),
            "ascentFt": guess_elev_ft(pick(r, "elevationGain", "sumElevationGain", "totalAscent")),
            "descentFt": guess_elev_ft(pick(r, "elevationLoss", "sumElevationLoss", "totalDescent")),
            "maxElevFt": guess_elev_ft(pick(r, "maxElevation")),
            "minElevFt": guess_elev_ft(pick(r, "minElevation")),
            "totalTime": hhmmss(dur),
            "movingTime": hhmmss(mov),
            "stoppedPct": (round((dur - mov) / dur * 100) if dur and mov and dur > 0 else None),
            "avgHR": num(pick(r, "avgHr", "averageHR")),
            "maxHR": num(pick(r, "maxHr", "maxHR")),
            # verified against San Jacinto: 16,509 in this file vs 3,940 kcal in the FIT
            "calories": (round(num(pick(r, "calories", "sumCalories")) * KJ_TO_KCAL)
                         if pick(r, "calories", "sumCalories") is not None else None),
            "aerobicEffect": num(pick(r, "aerobicTrainingEffect")),
            "anaerobicEffect": num(pick(r, "anaerobicTrainingEffect")),
            "exerciseLoad": num(pick(r, "activityTrainingLoad", "trainingLoad")),
            "steps": num(pick(r, "steps")),
            "vo2Max": num(pick(r, "vO2MaxValue", "vo2MaxValue")),
            # bmrCalories is also kJ; waterEstimated is Garmin's sweat-loss model, in ml
            "restingCal": (round(num(r["bmrCalories"]) * KJ_TO_KCAL)
                           if r.get("bmrCalories") is not None else None),
            "sweatLossMl": (round(num(r["waterEstimated"]))
                            if r.get("waterEstimated") is not None else None),
            "bodyBatteryDelta": num(pick(r, "differenceBodyBattery")),
            "lapCount": num(pick(r, "lapCount")),
            "location": pick(r, "locationName"),
            "hrZoneSec": {f"z{i}": round(num(r[f"hrTimeInZone_{i}"]) / 1000)
                          for i in range(7) if r.get(f"hrTimeInZone_{i}") is not None},
        }
        out.append(rec)

    out.sort(key=lambda x: str(x.get("start") or ""))
    print(f"\nmatched {len(out)} activities"
          f"{'' if a.all_types else ' of hiking/walking type'} out of {len(seen)} total")
    if out:
        print(f"  date range: {out[0]['start']}  ->  {out[-1]['start']}")
        longs = [x for x in out if secs(x["totalTime"]) >= a.min_hours*3600]
        print(f"  {len(longs)} of them run {a.min_hours}+ hours")
        print("\n  longest ten:")
        for x in sorted(out, key=lambda v: secs(v["totalTime"]), reverse=True)[:10]:
            print(f"    {str(x['start'])[:10]}  {x['totalTime']:>9}  "
                  f"{x['distanceMi'] or '?':>6} mi  {x['ascentFt'] or '?':>6} ft  "
                  f"stopped {x['stoppedPct'] if x['stoppedPct'] is not None else '?'}%  {x['name']}")

    pathlib.Path(a.out).write_text(json.dumps(out, indent=1, default=str))
    kb = pathlib.Path(a.out).stat().st_size / 1024
    print(f"\nwrote {a.out}  ({kb:.0f} KB)  <-- send me this one file")

    if a.copy_fit:
        dest = pathlib.Path(a.copy_fit)
        dest.mkdir(parents=True, exist_ok=True)
        want = {str(x["activityId"]) for x in out
                if secs(x["totalTime"]) >= a.min_hours*3600}
        n = 0
        for f in fits:
            if any(w in f.name for w in want):
                shutil.copy2(f, dest / f.name)
                n += 1
        tot = sum(p.stat().st_size for p in dest.glob("*.fit")) / 1e6
        print(f"copied {n} .fit files to {dest}  ({tot:.1f} MB) — zip that folder")


if __name__ == "__main__":
    main()
