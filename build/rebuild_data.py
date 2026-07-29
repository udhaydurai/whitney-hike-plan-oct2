#!/usr/bin/env python3
"""
Rebuild the training log with a single clear source-of-truth rule.

    GARMIN owns every objective metric.  date, distance, ascent, elevation,
    elapsed and moving time, stopped %, heart rate, calories, training effect,
    exercise load, steps, body battery.  Derived paces are computed from those.

    THE CONVERSATION owns everything Garmin cannot see.  fuelling, hydration,
    sodium, how it felt, symptoms, weather as experienced, poles, pack weight,
    boots, who came, and the coaching interpretation.

Nothing objective is carried over from the PDF any more. Where the two disagreed,
Garmin won, and the disagreement is recorded in the changelog rather than narrated
in the dashboard.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OLD = json.loads((ROOT / "data" / "training-log.json").read_text(encoding="utf-8"))
# the changelog compares against the pre-Garmin snapshot, so re-running stays idempotent
# without emptying the record of what changed
_bk = ROOT / "data" / "training-log.backup.json"
PRE = json.loads(_bk.read_text(encoding="utf-8")) if _bk.exists() else OLD
DIG = json.loads((ROOT / "garmin" / "digest.json").read_text(encoding="utf-8"))

BY_DATE = {a["start"][:10]: a for a in DIG}


def sec(t):
    if not t:
        return None
    p = [int(x) for x in str(t).split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def hhmmss(s):
    if s is None:
        return None
    s = int(s)
    return f"{s//3600}:{(s%3600)//60:02d}:{s%60:02d}"


def pace(seconds, miles):
    if not seconds or not miles:
        return None
    p = seconds / miles
    return f"{int(p//60)}:{int(p%60):02d}"


def r1(v):
    return None if v is None else round(float(v), 1)


# ---- the subjective layer, keyed by corrected date. Objective fields deliberately absent.
SUBJ = {}
for h in OLD["hikes"]:
    SUBJ[h["date"]] = {k: v for k, v in h.items() if k in (
        "id", "route", "label", "effortType", "effortNote", "poles", "packLb",
        "boots", "partners", "fuel", "notes", "coachNote", "flag", "sleep",
        "weather", "primaryBenefit")}
RSUBJ = {}
for r in OLD["ruckSessions"]:
    RSUBJ[r["date"]] = {k: v for k, v in r.items() if k in (
        "id", "packLb", "notes", "coachNote", "flag", "recoveryHours")}

changelog = []


def build_activity(a, subj, kind):
    """One record, Garmin-first."""
    mi = a["distanceMi"]
    tot, mov = a["durSec"], sec(a["movingTime"])
    rec = {
        "id": subj.get("id"),
        "date": a["start"][:10],
        "kind": kind,
        "source": "garmin",
        # --- objective, Garmin only
        "distanceMi": mi,
        "ascentFt": a["ascentFt"],
        "descentFt": a["descentFt"],
        "minElevFt": a["minElevFt"],
        "maxElevFt": a["maxElevFt"],
        "totalTime": hhmmss(tot),
        "movingTime": a["movingTime"],
        "stoppedPct": a["stoppedPct"],
        "avgPace": pace(tot, mi),
        "movingPace": pace(mov, mi),
        "avgSpeedMph": round(mi / (tot / 3600), 2) if tot else None,
        "movingSpeedMph": round(mi / (mov / 3600), 2) if mov else None,
        "avgHR": int(a["avgHR"]) if a.get("avgHR") else None,
        "maxHR": int(a["maxHR"]) if a.get("maxHR") else None,
        "totalCal": a.get("calories"),
        "aerobicEffect": r1(a.get("aerobicEffect")),
        "anaerobicEffect": r1(a.get("anaerobicEffect")),
        "exerciseLoad": round(a["exerciseLoad"]) if a.get("exerciseLoad") else None,
        "steps": int(a["steps"]) if a.get("steps") else None,
        "bodyBattery": int(a["bodyBatteryDelta"]) if a.get("bodyBatteryDelta") is not None else None,
        "restingCal": a.get("restingCal"),
        "sweatLossMl": a.get("sweatLossMl"),
        "hrZoneSec": a.get("hrZoneSec"),
    }
    # --- subjective, conversation only
    for k in ("route", "label", "effortType", "poles", "packLb", "boots",
              "partners", "fuel", "notes", "coachNote", "flag", "sleep",
              "weather", "recoveryHours"):
        if k in subj and subj[k] is not None:
            rec[k] = subj[k]
    rec.setdefault("effortType", "training")
    return rec


# ---- hikes
hikes = []
for date in sorted(d for d in BY_DATE if BY_DATE[d]["type"] == "hiking" and d >= "2026-04-01"):
    a = BY_DATE[date]
    s = SUBJ.get(date, {})
    if not s.get("id"):
        s = dict(s, id=f"H?{date[5:]}")
    rec = build_activity(a, s, "hike")
    # record where Garmin overrode the PDF
    old = next((h for h in PRE["hikes"] if h["date"] == date), None)
    if old:
        for f, label in [("movingTime", "moving time"), ("avgHR", "average HR"),
                         ("totalCal", "calories"), ("maxHR", "max HR"),
                         ("aerobicEffect", "aerobic effect")]:
            ov, nv = old.get(f), rec.get(f)
            if ov is not None and nv is not None and str(ov) != str(nv):
                changelog.append({"date": date, "field": label,
                                  "was": ov, "now": nv, "why": "Garmin export is authoritative"})
    hikes.append(rec)

# ---- rucks
rucks = []
for date in sorted(d for d in BY_DATE if "ruck" in (BY_DATE[d]["type"] or "")):
    a = BY_DATE[date]
    s = RSUBJ.get(date, {"id": f"R?{date[5:]}"})
    s.setdefault("packLb", 12)
    rucks.append(build_activity(a, s, "ruck"))

# renumber cleanly in date order
for i, h in enumerate(hikes, 1):
    h["id"] = f"H{i}"
for i, r in enumerate(rucks, 1):
    r["id"] = f"R{i}"

# ---- consecutive-day check, done from data rather than assumed
import datetime as dt
alldays = sorted({h["date"] for h in hikes} | {r["date"] for r in rucks})
consec = []
for i in range(1, len(alldays)):
    d0 = dt.date.fromisoformat(alldays[i - 1])
    d1 = dt.date.fromisoformat(alldays[i])
    if (d1 - d0).days == 1:
        consec.append((alldays[i - 1], alldays[i]))

out = dict(OLD)
out["hikes"] = hikes
out["ruckSessions"] = rucks
out["meta"] = dict(OLD["meta"],
                   logCoversFrom=alldays[0], logCoversTo=alldays[-1],
                   sourceRule=("Garmin export is authoritative for every objective metric. "
                               "The conversation supplies fuelling, symptoms, gear, conditions "
                               "and interpretation only."))
out["consecutiveDays"] = {
    "pairs": [{"first": a, "second": b} for a, b in consec],
    "note": ("Computed from the data, not assumed. Any pair of back-to-back days appears here.")}
out["garminOverrides"] = changelog

# drop keys that were conversation scaffolding rather than dashboard content
for k in ("physiologyAnswers", "fitFindings", "fitExport", "watchConfig",
          "gelEvidence", "history"):
    out.pop(k, None)

(ROOT / "data" / "training-log.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"hikes {len(hikes)}  rucks {len(rucks)}")
print(f"window {alldays[0]} -> {alldays[-1]}")
print(f"garmin overrode the PDF in {len(changelog)} fields")
for c in changelog:
    print(f"   {c['date']}  {c['field']}: {c['was']} -> {c['now']}")
print(f"\nconsecutive-day pairs found: {len(consec)}")
for a, b in consec:
    ka = "hike" if any(h["date"] == a for h in hikes) else "ruck"
    kb = "hike" if any(h["date"] == b for h in hikes) else "ruck"
    print(f"   {a} ({ka}) -> {b} ({kb})")
print("\nfloat check:", [h["aerobicEffect"] for h in hikes])
