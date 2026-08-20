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

import datetime as dt
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
    # A hike Garmin recorded but the conversation has not yet named still needs a place
    # string: the dashboard's altitude-exposure table indexes h["route"] directly. Fall
    # back to Garmin's own activity name, then its location — both are Garmin fields, so
    # this invents nothing. Do not leave it absent; a KeyError here blocked a whole publish.
    rec.setdefault("route", a.get("name") or a.get("location") or "Unnamed Garmin activity")
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


def _spo2_block(spo2, spo2_days, _keep):
    """
    Pulse ox state, read from the data rather than asserted.

    The log said "3 readings in 304 days — effectively off" and told him to enable it.
    He did, on 2026-07-29, and it has recorded nightly since. A dashboard still telling
    him to turn on a setting he already turned on is worse than silent, so both the state
    and the recommendation are computed. The device instructions are kept only for the
    case where the readings actually stop.
    """
    import datetime as _dt
    if not spo2:
        return {"readings": 0, "days": spo2_days, "values": [],
                "on": False,
                "problem": f"Pulse oximetry has produced no readings in {spo2_days} days "
                           f"of health data.",
                "action": _keep(["spo2Gap", "action"], "")}
    dates = [x["date"] for x in spo2]
    vals = [x["v"] for x in spo2]
    # the current run: consecutive daily readings ending at the most recent one
    run_end = _dt.date.fromisoformat(dates[-1])
    run = 1
    for a, b in zip(reversed(dates[:-1]), reversed(dates[1:])):
        if (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days == 1:
            run += 1
        else:
            break
    run_from = (run_end - _dt.timedelta(days=run - 1)).isoformat()
    recent = [x["v"] for x in spo2 if x["date"] >= run_from]
    on = run >= 7
    lo, hi = min(recent), max(recent)
    mean = round(sum(recent) / len(recent), 1)
    if on:
        problem = (f"Pulse oximetry has been recording nightly since {run_from} — "
                   f"{run} consecutive nights, against {len(spo2)} readings in "
                   f"{spo2_days} days of health data overall.")
        action = (f"The sea-level baseline is now {mean}% (range {lo:.0f}–{hi:.0f}%) over "
                  f"{run} nights, which is enough for the readings at Cottonwood and Trail "
                  f"Camp to be read as a drop from something rather than as first-ever "
                  f"numbers. Leave it on through Oct 2.")
    else:
        problem = (f"Pulse oximetry has produced {len(spo2)} readings in {spo2_days} days "
                   f"of health data, the most recent on {dates[-1]}.")
        action = _keep(["spo2Gap", "action"], "")
    return {"readings": len(spo2), "days": spo2_days, "values": vals, "on": on,
            "runNights": run, "runFrom": run_from, "recentMean": mean,
            "recentRange": [lo, hi], "problem": problem, "action": action}


# ── wellness: recomputed from the Garmin digest, not carried over.
# These are objective metrics — nights, hours, HRV, SpO2 — and under the source-of-truth
# rule they may not sit frozen in the log. They were, and the block still read "583 nights
# to 2026-07-28" three weeks after the export moved on. The prose that interprets them is
# conversation-owned and is preserved; any figure inside that prose is rebuilt from the
# numbers so the sentence cannot drift from the data it describes.
_wp = ROOT / "garmin" / "wellness.json"
if _wp.exists():
    W = json.loads(_wp.read_text(encoding="utf-8"))
    old_w = OLD.get("wellness", {})
    sleep_by, daily_by = W["sleepByDate"], W["dailyByDate"]
    nights = sorted(sleep_by)

    def _hrs(d):
        r = sleep_by.get(d)
        return r["totalHrs"] if r else None

    def _night(d):
        r = sleep_by.get(d)
        return {"hrs": r["totalHrs"], "score": r["score"]} if r else None

    allh = [sleep_by[d]["totalHrs"] for d in nights]
    last60 = nights[-60:]
    l60h = [sleep_by[d]["totalHrs"] for d in last60]
    l60s = [sleep_by[d]["score"] for d in last60 if sleep_by[d].get("score") is not None]
    deep = [sleep_by[d]["deepMin"] for d in nights if sleep_by[d].get("deepMin") is not None]

    # the longest efforts, ranked by duration in SECONDS — a lexicographic sort on
    # "8:58" vs "11:04" is what once buried San Jacinto below a nine-minute walk
    longest = sorted([a for a in DIG if a.get("durSec")],
                     key=lambda a: -a["durSec"])[:7]
    brows = []
    for a in longest:
        d0 = a["start"][:10]
        day = dt.date.fromisoformat(d0)
        brows.append({
            "date": d0,
            "name": a.get("name"),
            "duration": a.get("totalTime"),
            "before": _night((day - dt.timedelta(days=1)).isoformat()),
            "nightOf": _night(d0),
            "after": _night((day + dt.timedelta(days=1)).isoformat()),
        })
    _med = round(sorted(allh)[len(allh) // 2], 2)
    non = [r["nightOf"]["hrs"] for r in brows if r["nightOf"]]
    nbe = [r["before"]["hrs"] for r in brows if r["before"]]
    mean_on = round(sum(non) / len(non), 1) if non else None
    mean_be = round(sum(nbe) / len(nbe), 1) if nbe else None

    hrv = [x["v"] for x in W["hrvSeries"]]
    rhr_vals = [v["HR"] for v in daily_by.values() if v.get("HR") is not None]
    h9 = [x for x in W["hrvSeries"] if x["date"] >= (dt.date.fromisoformat(nights[-1])
                                                     - dt.timedelta(days=63)).isoformat()]
    half = len(h9) // 2 or 1
    hrv_then = round(sum(x["v"] for x in h9[:half]) / half) if h9 else None
    hrv_now = round(sum(x["v"] for x in h9[half:]) / max(1, len(h9) - half)) if h9 else None

    spo2 = W["spo2Series"]
    spo2_days = W["coverage"]["healthDays"]

    def _keep(path, default):
        cur = old_w
        for k in path:
            cur = (cur or {}).get(k) if isinstance(cur, dict) else None
        return cur if cur else default

    out["wellness"] = {
        "source": (f"Garmin sleep and health-status exports: {len(nights)} nights "
                   f"{nights[0]} to {nights[-1]}, {spo2_days} days of daily metrics."),
        "sleep": {
            "meanHrs": round(sum(allh) / len(allh), 2),
            "medianHrs": round(sorted(allh)[len(allh) // 2], 2),
            "under6Pct": round(sum(1 for v in allh if v < 6) / len(allh) * 100),
            "last60MeanHrs": round(sum(l60h) / len(l60h), 2),
            "last60MeanScore": round(sum(l60s) / len(l60s)) if l60s else None,
            "meanDeepMin": round(sum(deep) / len(deep)) if deep else None,
        },
        "bigDaySleep": {
            "rows": brows,
            "meanNightOfHrs": mean_on,
            "meanNightBeforeHrs": mean_be,
            # "collapses on every long effort" was prose, and Aug 15 broke it: 5.5 h and
            # a score of 75 after thirteen hours out. State the count that is true.
            "finding": (f"Across the {len(brows)} longest days the night-of average is "
                        f"{mean_on} hours against {mean_be} the night before, and "
                        f"{sum(1 for r in brows if r['nightOf'] and r['nightOf']['hrs'] < _med)} "
                        f"of {len(non)} fell below the {_med} h median."),
            "whitneyImplication": _keep(["bigDaySleep", "whitneyImplication"], ""),
        },
        "recovery": {
            "hrvMean": round(sum(hrv) / len(hrv), 1),
            "hrvRange": [min(hrv), max(hrv)],
            "restingHRMean": round(sum(rhr_vals) / len(rhr_vals), 1),
            "restingHRRange": [min(rhr_vals), max(rhr_vals)],
            "trend": (f"Over the last nine weeks HRV has moved from about {hrv_then} to "
                      f"{hrv_now} ms, against a full-record mean of "
                      f"{round(sum(hrv)/len(hrv),1)} ms."),
        },
        "spo2Gap": _spo2_block(spo2, spo2_days, _keep),
    }

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
