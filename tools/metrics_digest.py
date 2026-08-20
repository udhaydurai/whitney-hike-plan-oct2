#!/usr/bin/env python3
"""
Parse Garmin's *derived metric* exports into one digest.

These are a different family of files from summarizedActivities and from the wellness
exports. They arrive as one JSON per metric per ~100-day window, named

    MetricsHeatAltitudeAcclimation_20260420_20260729_127865405.json
                                   ^from    ^to      ^userProfilePK

and the windows overlap at the seams, so the same calendar date appears in two files.
Deduplicate by keeping the LAST record for a date, which is the one the watch settled on.

Units and traps, all of which are real in this data:

* `altitudeAcclimation` is METRES of acclimated altitude, not a percentage. It reads
  1400 after Mammoth, which is 4,593 ft — plausible. Read as a percent it would be
  a nonsense 1400%. `acclimationPercentage` is the separate percent field and is only
  populated on days with an altitude exposure.
* `currentAltitude` is METRES.
* `calendarDate` is an ISO string in some metrics (TrainingReadiness, TrainingHistory,
  HeatAltitudeAcclimation) and epoch MILLISECONDS in others (AcuteTrainingLoad,
  HillScore, EnduranceScore). Handle both or half the series silently vanishes.
* Epoch dates are midnight UTC, so read them as UTC — a local conversion shifts every
  one of them back a day in this container.

Usage:
    python3 tools/metrics_digest.py <folder-of-metric-json> garmin/metrics.json
"""

import datetime as dt
import glob
import json
import os
import pathlib
import re
import sys

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "garmin/metrics")
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "garmin/metrics.json")

M_TO_FT = 3.28084


def cal_date(v):
    """calendarDate is ISO string in some metrics and epoch ms in others."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return dt.datetime.utcfromtimestamp(v / 1000).strftime("%Y-%m-%d")
    return str(v)[:10]


def load(metric):
    """Every window file for one metric, deduplicated by date, latest record wins."""
    by_date = {}
    for f in sorted(glob.glob(str(SRC / f"{metric}_*.json"))):
        try:
            rows = json.load(open(f, encoding="utf-8"))
        except Exception as ex:
            print(f"  ! {os.path.basename(f)}: {ex}")
            continue
        if not isinstance(rows, list):
            continue
        for r in rows:
            d = cal_date(r.get("calendarDate"))
            if d:
                by_date[d] = r
    return by_date


def coverage(by_date):
    if not by_date:
        return {"days": 0, "from": None, "to": None}
    ks = sorted(by_date)
    return {"days": len(ks), "from": ks[0], "to": ks[-1]}


out = {}

# ── altitude acclimation: the one metric that speaks directly to Whitney
acc = load("MetricsHeatAltitudeAcclimation")
series = []
for d in sorted(acc):
    r = acc[d]
    m = r.get("altitudeAcclimation")
    series.append({
        "date": d,
        "acclimFt": round(m * M_TO_FT) if m is not None else None,
        "acclimM": m,
        "currentAltFt": (round(r["currentAltitude"] * M_TO_FT)
                         if r.get("currentAltitude") is not None else None),
        "heatPct": r.get("heatAcclimationPercentage"),
    })
nonzero = [s for s in series if (s["acclimM"] or 0) > 0]
peak = max(nonzero, key=lambda s: s["acclimM"]) if nonzero else None
latest = series[-1] if series else None
# decay rate: metres lost per day across the most recent run of falling values
decay = None
if len(series) >= 8:
    tail = [s for s in series[-21:] if s["acclimM"] is not None]
    drops = [(a["acclimM"] - b["acclimM"])
             for a, b in zip(tail, tail[1:]) if b["acclimM"] < a["acclimM"]]
    if drops:
        decay = round(sum(drops) / len(drops), 1)
out["altitudeAcclimation"] = {
    "source": "Garmin MetricsHeatAltitudeAcclimation. altitudeAcclimation is metres, "
              "converted to feet here. Garmin's own model, not a measurement.",
    "coverage": coverage(acc),
    "latest": latest,
    "peak": peak,
    "meanDailyDecayM": decay,
    "series": series,
}

# ── training status and load
th = load("TrainingHistory")
out["trainingStatus"] = {
    "coverage": coverage(th),
    "latest": ({"date": sorted(th)[-1],
                "status": th[sorted(th)[-1]].get("trainingStatus"),
                "trend": th[sorted(th)[-1]].get("fitnessLevelTrend")} if th else None),
    "series": [{"date": d, "status": th[d].get("trainingStatus")} for d in sorted(th)],
}

atl = load("MetricsAcuteTrainingLoad")
aseries = [{"date": d,
            "acute": atl[d].get("dailyTrainingLoadAcute"),
            "chronic": atl[d].get("dailyTrainingLoadChronic"),
            "acwr": atl[d].get("dailyAcuteChronicWorkloadRatio"),
            "status": atl[d].get("acwrStatus")} for d in sorted(atl)]
out["trainingLoad"] = {
    "source": "Garmin MetricsAcuteTrainingLoad. acwr is acute:chronic workload ratio.",
    "coverage": coverage(atl),
    "latest": aseries[-1] if aseries else None,
    "series": aseries,
}

# ── endurance score
es = load("EnduranceScore")
out["enduranceScore"] = {
    "coverage": coverage(es),
    "latest": ({"date": sorted(es)[-1], "score": es[sorted(es)[-1]].get("overallScore")}
               if es else None),
    "series": [{"date": d, "score": es[d].get("overallScore")} for d in sorted(es)],
}

# ── hill score
hs = load("HillScore")
out["hillScore"] = {
    "coverage": coverage(hs),
    "series": [{"date": d, "classification": hs[d].get("hillScoreClassificationId")}
               for d in sorted(hs)],
}

# ── VO2 max / max MET, by sport
mm = load("MetricsMaxMetData")
vo2 = []
for f in sorted(glob.glob(str(SRC / "MetricsMaxMetData_*.json"))):
    for r in json.load(open(f, encoding="utf-8")):
        vo2.append({"date": cal_date(r.get("calendarDate")), "sport": r.get("sport"),
                    "vo2Max": r.get("vo2MaxValue"), "maxMet": round(r.get("maxMet"), 1)
                    if r.get("maxMet") is not None else None})
vo2 = sorted({(v["date"], v["sport"]): v for v in vo2 if v["date"]}.values(),
             key=lambda v: v["date"])
out["vo2MaxSeries"] = {"coverage": coverage(mm), "series": vo2,
                       "latest": vo2[-1] if vo2 else None}

# ── training readiness: the closest thing to wellness in this family of files.
# It carries sleepScore and an HRV factor, but not raw SpO2 or HRV values.
tr = load("TrainingReadinessDTO")
tseries = [{"date": d,
            "score": tr[d].get("score"),
            "level": tr[d].get("level"),
            "sleepScore": tr[d].get("sleepScore"),
            "hrvFactorPct": tr[d].get("hrvFactorPercent"),
            "recoveryTimeH": (round(tr[d]["recoveryTime"] / 60, 1)
                              if tr[d].get("recoveryTime") is not None else None)}
           for d in sorted(tr)]
out["trainingReadiness"] = {
    "source": "Garmin TrainingReadinessDTO. Carries sleepScore and an HRV factor "
              "percentage, but no raw SpO2 or HRV. Those live in the wellness export.",
    "coverage": coverage(tr),
    "latest": tseries[-1] if tseries else None,
    "series": tseries,
}

out["meta"] = {
    "generatedFrom": str(SRC),
    "files": len(glob.glob(str(SRC / "*.json"))),
    "note": "Derived Garmin metrics. Objective, so they fall under the Garmin "
            "source-of-truth rule. Absent here: SpO2, raw HRV, sleep stages, "
            "heart-rate zone configuration, body-composition profile.",
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=1, default=str))
print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB) from {out['meta']['files']} files")
for k in ("altitudeAcclimation", "trainingLoad", "trainingStatus", "trainingReadiness",
          "enduranceScore", "vo2MaxSeries"):
    c = out[k]["coverage"]
    print(f"  {k:22s} {c['days']:>4} days  {c['from']} -> {c['to']}")
a = out["altitudeAcclimation"]
if a["latest"]:
    print(f"\naltitude acclimation now {a['latest']['acclimFt']:,} ft "
          f"(peak {a['peak']['acclimFt']:,} ft on {a['peak']['date']}), "
          f"decaying about {a['meanDailyDecayM']} m/day")
