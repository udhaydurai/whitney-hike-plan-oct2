#!/usr/bin/env python3
"""
Parse a Garmin .FIT file into a training-log.json hike record.

Why this instead of screenshots: a screenshot gives ~20 summary numbers. A FIT file
gives a per-second stream — heart rate, altitude, cadence, temperature, distance,
position — typically 15,000 to 40,000 records for a long hike. That is the difference
between tracing an elevation profile by eye and having the actual curve.

Where to get the file:
  Garmin Connect (web) -> open the activity -> gear icon top right -> "Export Original".
  That downloads a .fit. On mobile, Connect can share the file too.
  For the whole history at once: Account Settings -> Data Management -> Export Your Data.

Usage:
  python3 parse_fit.py ACTIVITY.fit                 # summary to stdout
  python3 parse_fit.py ACTIVITY.fit --json out.json # hike record for the log
  python3 parse_fit.py ACTIVITY.fit --profile 40    # 40-point elevation profile

Requires: pip install fitdecode --break-system-packages
"""

import argparse
import json
import statistics as st
import sys

try:
    import fitdecode
except ImportError:
    sys.exit("Missing dependency. Run: pip install fitdecode --break-system-packages")

M_TO_FT = 3.28084
KM_TO_MI = 0.621371


def _get(frame, *names):
    """First present, non-None field value among names."""
    for n in names:
        if frame.has_field(n):
            v = frame.get_value(n)
            if v is not None:
                return v
    return None


def read_fit(path):
    records, session, laps = [], {}, []
    with fitdecode.FitReader(path) as fr:
        for frame in fr:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            if frame.name == "record":
                records.append({
                    "t": _get(frame, "timestamp"),
                    "hr": _get(frame, "heart_rate"),
                    "alt_m": _get(frame, "enhanced_altitude", "altitude"),
                    "dist_m": _get(frame, "distance"),
                    "speed": _get(frame, "enhanced_speed", "speed"),
                    "cad": _get(frame, "cadence"),
                    "temp_c": _get(frame, "temperature"),
                    "lat": _get(frame, "position_lat"),
                    "lon": _get(frame, "position_long"),
                })
            elif frame.name == "session":
                session = {
                    "start": _get(frame, "start_time"),
                    "total_timer_s": _get(frame, "total_timer_time"),
                    "total_elapsed_s": _get(frame, "total_elapsed_time"),
                    "dist_m": _get(frame, "total_distance"),
                    "ascent_m": _get(frame, "total_ascent"),
                    "descent_m": _get(frame, "total_descent"),
                    "kcal": _get(frame, "total_calories"),
                    "hr_avg": _get(frame, "avg_heart_rate"),
                    "hr_max": _get(frame, "max_heart_rate"),
                    "sport": _get(frame, "sport"),
                    "steps": _get(frame, "total_strides", "total_cycles"),
                }
            elif frame.name == "lap":
                laps.append({
                    "dist_m": _get(frame, "total_distance"),
                    "timer_s": _get(frame, "total_timer_time"),
                    "hr_avg": _get(frame, "avg_heart_rate"),
                    "ascent_m": _get(frame, "total_ascent"),
                })
    return records, session, laps


def hhmmss(sec):
    sec = int(round(sec or 0))
    return f"{sec//3600}:{(sec%3600)//60:02d}:{sec%60:02d}"


def mmss_per_mi(sec, miles):
    if not miles:
        return None
    p = sec / miles
    return f"{int(p//60)}:{int(p%60):02d}"


def moving_seconds(records, min_mps=0.1):
    """
    Seconds actually in motion, using the recorded speed stream.

    An earlier version of this used a distance-delta threshold of 0.4 m per sample,
    which counted GPS jitter and near-stationary shuffling as movement and inflated
    San Jacinto's moving time to 8:14 against Garmin's 4:58. Speed at >= 0.1 m/s
    reproduces Garmin's figure to within a minute, so Garmin was right and the
    distance-delta approach was wrong.
    """
    mv = 0
    prev = None
    for r in records:
        if r["t"] is None:
            continue
        if prev is not None:
            dt = (r["t"] - prev["t"]).total_seconds()
            if 0 < dt <= 30 and (r.get("speed") or 0) >= min_mps:
                mv += dt
        prev = r
    return mv


def speed_profile(records):
    """Time split across speed bands — reveals how much of a hike is standing still."""
    bands = [(0, 0.1, "stopped"), (0.1, 0.45, "under 1 mph"),
             (0.45, 0.9, "1-2 mph"), (0.9, 1.35, "2-3 mph"), (1.35, 99, "over 3 mph")]
    acc = {b[2]: 0 for b in bands}
    total = 0
    prev = None
    for r in records:
        if r["t"] is None:
            continue
        if prev is not None:
            dt = (r["t"] - prev["t"]).total_seconds()
            if 0 < dt <= 30:
                total += dt
                sp = r.get("speed") or 0
                for lo, hi, lab in bands:
                    if lo <= sp < hi:
                        acc[lab] += dt
                        break
        prev = r
    return acc, total


def zones(records, bounds):
    """Time in each %HRR zone. bounds: {'Z1':[lo,hi], ...}"""
    out = {k: 0 for k in bounds}
    out["belowZ1"] = 0
    prev = None
    for r in records:
        if r["t"] is None:
            continue
        if prev is not None and r["hr"] is not None:
            dt = (r["t"] - prev["t"]).total_seconds()
            if 0 < dt <= 30:
                placed = False
                for z, (lo, hi) in bounds.items():
                    if lo <= r["hr"] <= hi:
                        out[z] += dt
                        placed = True
                        break
                if not placed and r["hr"] < min(v[0] for v in bounds.values()):
                    out["belowZ1"] += dt
        prev = r
    return out


def downsample_profile(records, n=40):
    pts = [(r["t"], r["alt_m"]) for r in records if r["alt_m"] is not None and r["t"] is not None]
    if not pts:
        return []
    t0 = pts[0][0]
    total = (pts[-1][0] - t0).total_seconds() or 1
    out = []
    for i in range(n + 1):
        target = total * i / n
        best = min(pts, key=lambda p: abs((p[0] - t0).total_seconds() - target))
        out.append({"h": round(target / 3600, 3), "ft": round(best[1] * M_TO_FT)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fit")
    ap.add_argument("--json", metavar="OUT", help="write a hike record")
    ap.add_argument("--profile", type=int, default=0, metavar="N",
                    help="emit an N-point elevation profile")
    ap.add_argument("--id", default="H?", help="hike id, e.g. H11")
    a = ap.parse_args()

    records, s, laps = read_fit(a.fit)
    if not records:
        sys.exit("No record messages found — is this a FIT activity file?")

    alts = [r["alt_m"] for r in records if r["alt_m"] is not None]
    hrs_ = [r["hr"] for r in records if r["hr"] is not None]
    temps = [r["temp_c"] for r in records if r["temp_c"] is not None]

    elapsed = s.get("total_elapsed_s") or (
        records[-1]["t"] - records[0]["t"]).total_seconds()
    miles = (s.get("dist_m") or (records[-1]["dist_m"] or 0)) / 1000 * KM_TO_MI
    mv = moving_seconds(records)

    ZB = {"Z1": (122, 132), "Z2": (133, 143), "Z3": (144, 155),
          "Z4": (156, 167), "Z5": (168, 300)}
    z = zones(records, ZB)
    ztot = sum(v for k, v in z.items() if k != "belowZ1") or 1

    print(f"file            {a.fit}")
    print(f"sport           {s.get('sport')}")
    print(f"records         {len(records):,}  (a screenshot gives ~20 numbers)")
    print(f"start           {s.get('start')}")
    print(f"distance        {miles:.2f} mi")
    print(f"elapsed         {hhmmss(elapsed)}")
    print(f"moving          {hhmmss(mv)}   ({mv/elapsed*100:.0f}% of elapsed)")
    print(f"avg pace        {mmss_per_mi(elapsed, miles)} /mi total, "
          f"{mmss_per_mi(mv, miles)} /mi moving")
    if s.get("ascent_m"):
        print(f"ascent/descent  {s['ascent_m']*M_TO_FT:,.0f} / "
              f"{(s.get('descent_m') or 0)*M_TO_FT:,.0f} ft")
    if alts:
        print(f"elevation       {min(alts)*M_TO_FT:,.0f} – {max(alts)*M_TO_FT:,.0f} ft")
    if hrs_:
        print(f"heart rate      avg {st.mean(hrs_):.0f}, max {max(hrs_)}, "
              f"median {st.median(hrs_):.0f}")
    if temps:
        print(f"temperature     {min(temps):.0f} – {max(temps):.0f} C  "
              f"(screenshots never show this)")
    if s.get("kcal"):
        print(f"calories        {s['kcal']:,}")
    print(f"laps            {len(laps)}")
    sp, sptot = speed_profile(records)
    if sptot:
        print("\ntime by speed band:")
        for lab in ["stopped", "under 1 mph", "1-2 mph", "2-3 mph", "over 3 mph"]:
            print(f"  {lab:12s} {hhmmss(sp[lab])}  {sp[lab]/sptot*100:5.1f}%")
    print("\ntime in %HRR zones (recalibrated set):")
    for k in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
        print(f"  {k}  {hhmmss(z[k])}  {z[k]/ztot*100:5.1f}%")
    print(f"  below Z1  {hhmmss(z['belowZ1'])}")

    if a.profile:
        prof = downsample_profile(records, a.profile)
        print(f"\n{a.profile}-point elevation profile:")
        print(json.dumps(prof))

    if a.json:
        rec = {
            "id": a.id,
            "date": str(s.get("start"))[:10] if s.get("start") else None,
            "effortType": "training",
            "distanceMi": round(miles, 2),
            "ascentFt": round((s.get("ascent_m") or 0) * M_TO_FT),
            "descentFt": round((s.get("descent_m") or 0) * M_TO_FT),
            "minElevFt": round(min(alts) * M_TO_FT) if alts else None,
            "maxElevFt": round(max(alts) * M_TO_FT) if alts else None,
            "totalTime": hhmmss(elapsed),
            "movingTime": hhmmss(mv),
            "avgPace": mmss_per_mi(elapsed, miles),
            "movingPace": mmss_per_mi(mv, miles),
            "avgHR": round(st.mean(hrs_)) if hrs_ else None,
            "maxHR": max(hrs_) if hrs_ else None,
            "totalCal": s.get("kcal"),
            "tempRangeC": [min(temps), max(temps)] if temps else None,
            "zoneMethod": "%HRR",
            "zonesPct": {k: round(z[k] / ztot * 100) for k in ["Z1", "Z2", "Z3", "Z4", "Z5"]},
            "zonesTime": {k: hhmmss(z[k]) for k in ["Z1", "Z2", "Z3", "Z4", "Z5"]},
            "elevationProfile": downsample_profile(records, 40),
            "speedBands": {k: round(v/60) for k, v in speed_profile(records)[0].items()},
            "stoppedFraction": round(speed_profile(records)[0]["stopped"]/max(1,speed_profile(records)[1]), 3),
            "recordCount": len(records),
            "source": "Parsed from FIT — per-second data, not a screenshot.",
        }
        with open(a.json, "w") as f:
            json.dump(rec, f, indent=2, default=str)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
