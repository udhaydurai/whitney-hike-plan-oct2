#!/usr/bin/env python3
"""
Parse the Garmin wellness exports into one small digest.

Reads sleepData, healthStatusData, heartRateZones, bioMetrics and fitnessAge files
from a folder and writes wellness.json. Sleep and daily health are what the activity
export does not carry, and SpO2 in particular is the one baseline that speaks directly
to altitude tolerance.
"""

import glob
import json
import os
import pathlib
import statistics as st
import sys

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "garmin/health")
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "garmin/wellness.json")


def load(pat):
    out = []
    for f in sorted(glob.glob(str(SRC / pat))):
        try:
            out.append((os.path.basename(f), json.load(open(f, encoding="utf-8"))))
        except Exception as ex:
            print(f"  ! {f}: {ex}")
    return out


# ─── zone configuration: this is Garmin's own setting, so it settles any dispute
zones = None
for _, d in load("*heartRateZones*"):
    for z in d:
        if z.get("trainingMethod") == "HR_RESERVE" and z.get("sport") == "DEFAULT":
            f = [z["zone1Floor"], z["zone2Floor"], z["zone3Floor"],
                 z["zone4Floor"], z["zone5Floor"]]
            mx = z["maxHeartRateUsed"]
            zones = {
                "method": "HR_RESERVE (%HRR)",
                "restingHR": z["restingHeartRateUsed"],
                "maxHR": mx,
                "lthrUsed": z["lactateThresholdHeartRateUsed"],
                "bands": {f"Z{i+1}": [f[i], (f[i + 1] - 1) if i < 4 else mx]
                          for i in range(5)},
                "source": "Garmin heartRateZones.json — the watch's actual configuration.",
            }

# ─── bio profile
bio = {}
for _, d in load("*userBioMetricProfileData*"):
    if d:
        r = d[0]
        bio.update(heightCm=round(r["height"], 1),
                   weightKg=round(r["weight"] / 1000, 1),
                   weightLb=round(r["weight"] / 1000 * 2.20462, 1),
                   vo2Max=r.get("vo2Max"),
                   lactateThresholdHR=r.get("lactateThresholdHeartRate"))
for _, d in load("*bioMetrics_latest*"):
    if d:
        bio["ftpCycling"] = d[0].get("functionalThresholdPower")

# ─── fitness age
fitage = {}
for _, d in load("*fitnessAgeData*"):
    if d:
        r = d[0]
        fitage = {k: (round(v, 1) if isinstance(v, float) else v)
                  for k, v in r.items()
                  if k in ("asOfDateGmt", "chronologicalAge", "bmi", "rhr",
                           "currentBioAge", "healthyAllBioAge", "biometricVo2Max",
                           "vo2MaxForHealthyActive")}

# ─── daily health status: HRV, resting HR, SpO2, respiration, skin temp
daily = {}
for _, d in load("*healthStatusData*"):
    for row in d:
        day = row.get("calendarDate")
        if not day:
            continue
        rec = daily.setdefault(day, {})
        for m in row.get("metrics", []):
            v = m.get("value")
            if v in (None, 0.0) and m.get("type") != "SKIN_TEMP_C":
                continue
            rec[m["type"]] = v
            if m.get("status") not in (None, "UNKNOWN"):
                rec[m["type"] + "_status"] = m["status"]

# ─── true resting heart rate, from the daily user-summary (UDS) files
#
# healthStatusData carries a metric called "HR", and it is NOT resting heart rate. It
# reads about 5-6 bpm high: for Aug 17-23 2026 it averaged 58.3 while Garmin Connect's
# own 7-day resting figure for the same week was 52. Reporting the wrong one made the
# dashboard describe an athlete measurably less recovered than he actually is, and it
# was only caught because he checked the number against his watch.
#
# UDSFile_*.json carries Garmin's own `restingHeartRate` per calendarDate, which
# reproduces Connect to within a beat (53.3 vs 52 for that week). Prefer it always, and
# keep the healthStatusData value only as a labelled fallback so a missing UDS file
# degrades to something rather than nothing.
#
# The UDS files live in DI-Connect-Aggregator, a sibling of the wellness folder, so look
# there as well as in SRC itself.
import itertools
uds_pats = ["UDSFile*.json", "../DI-Connect-Aggregator/UDSFile*.json",
            "**/UDSFile*.json"]
uds_rows, uds_files = {}, 0
for pat in uds_pats:
    for f in sorted(glob.glob(str(SRC / pat), recursive=True)):
        try:
            rows = json.load(open(f, encoding="utf-8"))
        except Exception as ex:
            print(f"  ! {f}: {ex}")
            continue
        uds_files += 1
        for row in (rows if isinstance(rows, list) else [rows]):
            day = row.get("calendarDate")
            v = row.get("restingHeartRate")
            if day and v:
                uds_rows[day] = v          # later windows win on overlap
    if uds_rows:
        break

for day, v in uds_rows.items():
    rec = daily.setdefault(day, {})
    rec["RESTING_HR"] = v

if uds_rows:
    print(f"resting HR: {len(uds_rows)} days from {uds_files} UDS file(s) "
          f"— Garmin's own restingHeartRate")
else:
    print("  ! no UDSFile found; falling back to healthStatusData HR, which reads high")

# ─── sleep
sleep = {}
for _, d in load("*sleepData*"):
    for row in d:
        day = row.get("calendarDate")
        if not day or len(row) <= 1:
            continue
        deep = row.get("deepSleepSeconds") or 0
        light = row.get("lightSleepSeconds") or 0
        rem = row.get("remSleepSeconds") or 0
        awake = row.get("awakeSleepSeconds") or 0
        total = deep + light + rem
        sc = row.get("sleepScores") or {}
        sleep[day] = {
            "totalHrs": round(total / 3600, 2),
            "deepMin": round(deep / 60),
            "lightMin": round(light / 60),
            "remMin": round(rem / 60),
            "awakeMin": round(awake / 60),
            "score": sc.get("overallScore"),
            "recoveryScore": sc.get("recoveryScore"),
            "deepScore": sc.get("deepScore"),
            "feedback": sc.get("feedback"),
            "avgStress": row.get("avgSleepStress"),
            "respirationAvg": row.get("averageRespiration"),
            "restlessMoments": row.get("restlessMomentCount"),
        }

# ─── summaries
def series(key, src):
    return sorted((d, v[key]) for d, v in src.items() if v.get(key) is not None)


def stats(vals):
    if not vals:
        return None
    return {"n": len(vals), "mean": round(st.mean(vals), 1),
            "median": round(st.median(vals), 1),
            "lo": round(min(vals), 1), "hi": round(max(vals), 1)}


spo2 = series("SPO2", daily)
hrv = series("HRV", daily)
# prefer the UDS resting series; fall back to the high-reading healthStatusData one
rhr = series("RESTING_HR", daily) or series("HR", daily)
rhr_src = "UDSFile restingHeartRate" if series("RESTING_HR", daily) else "healthStatusData HR (reads ~5 bpm high)"
resp = series("RESPIRATION", daily)
sc = series("score", sleep)
dur = series("totalHrs", sleep)
deep = series("deepMin", sleep)
recov = series("recoveryScore", sleep)

res = {
    "zones": zones,
    "bioProfile": bio,
    "fitnessAge": fitage,
    "coverage": {
        "sleepNights": len(sleep),
        "sleepFrom": min(sleep) if sleep else None,
        "sleepTo": max(sleep) if sleep else None,
        "healthDays": len(daily),
        "healthFrom": min(daily) if daily else None,
        "healthTo": max(daily) if daily else None,
    },
    "spo2": stats([v for _, v in spo2]),
    "hrv": stats([v for _, v in hrv]),
    "restingHR": stats([v for _, v in rhr]),
    "restingHRSource": rhr_src,
    "respiration": stats([v for _, v in resp]),
    "sleepScore": stats([v for _, v in sc]),
    "sleepHours": stats([v for _, v in dur]),
    "deepSleepMin": stats([v for _, v in deep]),
    "recoveryScore": stats([v for _, v in recov]),
    "spo2Series": [{"date": d, "v": v} for d, v in spo2],
    "hrvSeries": [{"date": d, "v": v} for d, v in hrv],
    "sleepByDate": sleep,
    "dailyByDate": daily,
}
# ── refuse to blank a populated digest.
# A weekly run pointed at a folder with no wellness files produces a structurally valid
# but completely empty digest, and writing it destroyed 583 sleep nights, 303 HRV points
# and the zone configuration in one commit. An export that does not contain wellness data
# is not evidence that the wellness data is gone. Refuse, the way nightly.py refuses.
_new_empty = not zones and not sleep and not daily
if _new_empty and OUT.exists():
    try:
        _old = json.loads(OUT.read_text())
    except Exception:
        _old = {}
    _had = ((_old.get("coverage") or {}).get("sleepNights") or 0) \
        or ((_old.get("coverage") or {}).get("healthDays") or 0) or _old.get("zones")
    if _had:
        sys.exit(
            f"REFUSED: no wellness files found in {SRC}, but {OUT} already holds "
            f"{(_old.get('coverage') or {}).get('sleepNights')} sleep nights and "
            f"{(_old.get('coverage') or {}).get('healthDays')} health days. "
            "Writing the empty digest would delete them. Send the sleepData / "
            "healthStatusData / heartRateZones files, or leave the existing digest alone."
        )

OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")

print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")
print(f"\nzones (Garmin's own config): maxHR {zones['maxHR']}, resting {zones['restingHR']}")
for z, b in zones["bands"].items():
    print(f"   {z}  {b[0]}–{b[1]} bpm")
print(f"\nbio: {bio}")
print(f"fitness age: {fitage}")
print(f"\ncoverage: {res['coverage']['sleepNights']} sleep nights "
      f"{res['coverage']['sleepFrom']} → {res['coverage']['sleepTo']}; "
      f"{res['coverage']['healthDays']} health days "
      f"{res['coverage']['healthFrom']} → {res['coverage']['healthTo']}")
for k in ("spo2", "hrv", "restingHR", "respiration", "sleepScore", "sleepHours", "deepSleepMin", "recoveryScore"):
    print(f"  {k:14s} {res[k]}")
