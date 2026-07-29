#!/usr/bin/env python3
"""
Whitney Training Dashboard generator.

Reads data/training-log.json and writes whitney-dashboard.html — a fully
self-contained page (no CDN, no JS deps) so it renders anywhere.

To add a hike: append a record to "hikes" in the JSON, re-run this script.
"""

import json
import html
import re
import datetime
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "training-log.json"
OUT = ROOT / "whitney-dashboard.html"

# ---------------------------------------------------------------- palette
C = {
    "ink":      "#101720",
    "ink2":     "#3d4a5c",
    "ink3":     "#6b7a8f",
    "line":     "#dfe5ec",
    "bg":       "#f6f8fa",
    "card":     "#ffffff",
    "primary":  "#1f7a68",   # teal - aerobic / good
    "primary2": "#8fd4c4",
    "accent":   "#2b6cb0",   # blue - hydration
    "accent2":  "#a8c8e8",
    "warn":     "#b46a12",   # amber - watch
    "warn2":    "#f0cf9a",
    "bad":      "#a8352c",   # red - problem
    "bad2":     "#efb8b2",
    "gold":     "#8a6d1f",   # summit
    "violet":   "#5b4b8a",
}

SEV = {
    "high":   (C["bad"],   C["bad2"],   "High"),
    "medium": (C["warn"],  C["warn2"],  "Medium"),
    "watch":  (C["violet"], "#cfc6e6",  "Watch"),
    "info":   (C["ink3"],  C["line"],   "Info"),
}

FLAG = {
    "summit":          (C["gold"], "Summit"),
    "milestone":       (C["primary"], "Milestone"),
    "breakthrough":    (C["primary"], "Breakthrough"),
    "fueling-problem": (C["bad"], "Fueling gap"),
    "fatigue":         (C["warn"], "Fatigue"),
    "symptom":         (C["violet"], "Symptom"),
}


def e(s):
    return html.escape(str(s if s is not None else ""))


def tosec(t):
    p = [int(x) for x in str(t).split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def mmss(sec):
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def short_date(iso):
    d = datetime.date.fromisoformat(iso)
    return d.strftime("%b %-d")


# ---------------------------------------------------------------- svg charts
def line_chart(series, *, w=680, h=222, ylabel="", pad_l=52, pad_b=34,
               pad_t=28, pad_r=14, invert=False, fmt=lambda v: f"{v:g}",
               band=None, ymin=None):
    """series: list of dicts {label, color, points:[(x_label, value)], dash}"""
    all_v = [v for s in series for _, v in s["points"] if v is not None]
    if not all_v:
        return ""
    vmin, vmax = min(all_v), max(all_v)
    if band:
        vmin, vmax = min(vmin, band[0]), max(vmax, band[1])
    span = (vmax - vmin) or 1
    vmin -= span * 0.14
    vmax += span * 0.14
    if ymin is not None:
        vmin = max(vmin, ymin)   # never pad below a physical floor, e.g. 0 mg
    span = vmax - vmin

    labels = [x for x, _ in series[0]["points"]]
    n = len(labels)
    iw = w - pad_l - pad_r
    ih = h - pad_t - pad_b

    def X(i):
        return pad_l + (iw * i / (n - 1) if n > 1 else iw / 2)

    def Y(v):
        f = (v - vmin) / span
        if invert:
            f = 1 - f
        return pad_t + ih - f * ih

    p = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']

    # optional target band
    if band:
        y1, y2 = Y(band[1]), Y(band[0])
        p.append(f'<rect x="{pad_l}" y="{min(y1,y2):.1f}" width="{iw}" '
                 f'height="{abs(y2-y1):.1f}" fill="{C["primary2"]}" opacity=".22"/>')

    # gridlines + y labels
    for k in range(4):
        v = vmin + span * (k / 3)
        y = Y(v)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" '
                 f'stroke="{C["line"]}" stroke-width="1"/>')
        p.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" '
                 f'class="tick">{e(fmt(v))}</text>')

    # x labels
    for i, lab in enumerate(labels):
        if n > 9 and i % 2 == 1:
            continue
        p.append(f'<text x="{X(i):.1f}" y="{h-pad_b+20}" text-anchor="middle" '
                 f'class="tick">{e(lab)}</text>')

    for s in series:
        pts = [(i, v) for i, (_, v) in enumerate(s["points"]) if v is not None]
        if not pts:
            continue
        d = " ".join(f"{'M' if j == 0 else 'L'}{X(i):.1f},{Y(v):.1f}"
                     for j, (i, v) in enumerate(pts))
        dash = f' stroke-dasharray="{s["dash"]}"' if s.get("dash") else ""
        p.append(f'<path d="{d}" fill="none" stroke="{s["color"]}" '
                 f'stroke-width="2.4" stroke-linejoin="round"{dash}/>')
        for i, v in pts:
            p.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="4.2" '
                     f'fill="{C["card"]}" stroke="{s["color"]}" stroke-width="2.2"/>')
            p.append(f'<title>{e(s["label"])} — {e(labels[i])}: {e(fmt(v))}</title>')

    if ylabel:
        p.append(f'<text x="6" y="13" class="axlab">{e(ylabel)}</text>')
    p.append("</svg>")
    return "".join(p)


def grouped_bars(rows, *, w=680, h=230, series_meta, fmt=lambda v: f"{v:g}",
                 pad_l=46, pad_b=40, pad_t=14, pad_r=14):
    """rows: [(label, [v1, v2, ...])]  series_meta: [(name, color)]"""
    all_v = [v for _, vs in rows for v in vs if v is not None]
    if not all_v:
        return ""
    vmax = max(all_v) * 1.16
    iw = w - pad_l - pad_r
    ih = h - pad_t - pad_b
    n = len(rows)
    k = len(series_meta)
    slot = iw / n
    bw = min(26, (slot * 0.68) / k)

    p = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for g in range(4):
        v = vmax * g / 3
        y = pad_t + ih - (v / vmax) * ih
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" '
                 f'stroke="{C["line"]}" stroke-width="1"/>')
        p.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" '
                 f'class="tick">{e(fmt(v))}</text>')

    for i, (lab, vs) in enumerate(rows):
        cx = pad_l + slot * (i + 0.5)
        start = cx - (bw * k) / 2
        for j, v in enumerate(vs):
            x = start + bw * j
            if v is None:
                # explicit "not logged" placeholder — absence of data, not a zero
                p.append(f'<rect x="{x:.1f}" y="{pad_t+ih-12:.1f}" width="{bw-2:.1f}" '
                         f'height="12" fill="none" stroke="{C["line"]}" '
                         f'stroke-width="1.2" stroke-dasharray="3 2" rx="2">'
                         f'<title>{e(series_meta[j][0])} — {e(lab)}: not logged</title></rect>')
                p.append(f'<text x="{x+(bw-2)/2:.1f}" y="{pad_t+ih-16:.1f}" '
                         f'text-anchor="middle" class="tick" '
                         f'style="font-size:9px">n/a</text>')
                continue
            bh = (v / vmax) * ih
            p.append(f'<rect x="{x:.1f}" y="{pad_t+ih-bh:.1f}" width="{bw-2:.1f}" '
                     f'height="{bh:.1f}" fill="{series_meta[j][1]}" rx="2">'
                     f'<title>{e(series_meta[j][0])} — {e(lab)}: {e(fmt(v))}</title></rect>')
        p.append(f'<text x="{cx:.1f}" y="{h-pad_b+18}" text-anchor="middle" '
                 f'class="tick">{e(lab)}</text>')
    p.append("</svg>")

    leg = "".join(
        f'<span class="lg"><i style="background:{col}"></i>{e(nm)}</span>'
        for nm, col in series_meta)
    return f'<div class="legend">{leg}</div>' + "".join(p)


def scatter_stopped(points, *, w=700, h=290, tank_h=5.5):
    """Duration vs stopped-time scatter, with the tank-duration line marked."""
    if not points:
        return ""
    pad_l, pad_r, pad_t, pad_b = 50, 16, 24, 46
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    xmax = max(p[0] for p in points) * 1.06
    ymax = max(60, max(p[1] for p in points) * 1.12)

    def X(v):
        return pad_l + v / xmax * iw

    def Y(v):
        return pad_t + ih - v / ymax * ih

    p = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for k in range(4):
        v = ymax * k / 3
        y = Y(v)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" '
                 f'stroke="{C["line"]}"/>'
                 f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="tick">'
                 f'{v:.0f}%</text>')
    for t in range(0, int(xmax) + 1, 2):
        p.append(f'<text x="{X(t):.1f}" y="{h-pad_b+20}" text-anchor="middle" class="tick">'
                 f'{t}h</text>')
    # tank line
    p.append(f'<rect x="{pad_l}" y="{pad_t}" width="{X(tank_h)-pad_l:.1f}" height="{ih}" '
             f'fill="{C["primary2"]}" opacity=".22"/>')
    p.append(f'<line x1="{X(tank_h):.1f}" y1="{pad_t}" x2="{X(tank_h):.1f}" y2="{pad_t+ih}" '
             f'stroke="{C["bad"]}" stroke-width="2" stroke-dasharray="5 3"/>')
    p.append(f'<text x="{X(tank_h)+6:.1f}" y="{pad_t+12}" class="axlab" fill="{C["bad"]}">'
             f'tank empties · {tank_h} h</text>')
    for hrs, pct, label in points:
        big = hrs >= 9
        col = C["bad"] if pct >= 40 else (C["warn"] if pct >= 20 else C["primary"])
        p.append(f'<circle cx="{X(hrs):.1f}" cy="{Y(pct):.1f}" r="{6 if big else 4.5}" '
                 f'fill="{col}" fill-opacity=".72" stroke="{C["card"]}" stroke-width="1.4">'
                 f'<title>{html.escape(label)} — {hrs:.1f} h, {pct}% stopped</title></circle>')
    p.append(f'<text x="6" y="13" class="axlab">stopped time</text>')
    p.append(f'<text x="{w-pad_r}" y="{h-6}" text-anchor="end" class="tick">hike duration</text>')
    p.append("</svg>")
    return "".join(p)


def profile_with_fuel(prof, hours, *, w=700, h=300):
    """Elevation profile with the hour-by-hour fuel schedule overlaid."""
    rd = prof["readings"]
    pad_l, pad_r, pad_t, pad_b = 52, 46, 22, 62
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    tmax = prof["totalHours"]
    emin = min(r["ft"] for r in rd) - 300
    emax = max(r["ft"] for r in rd) + 300

    def X(t):
        return pad_l + t / tmax * iw

    def Y(ft):
        return pad_t + ih - (ft - emin) / (emax - emin) * ih

    p = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    # elevation gridlines
    for k in range(5):
        ft = emin + (emax - emin) * k / 4
        y = Y(ft)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" '
                 f'stroke="{C["line"]}"/>'
                 f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="tick">'
                 f'{ft/1000:.1f}k</text>')
    # filled elevation area
    pts = " ".join(f"{X(r['h']):.1f},{Y(r['ft']):.1f}" for r in rd)
    p.append(f'<polygon points="{pad_l},{pad_t+ih} {pts} {w-pad_r},{pad_t+ih}" '
             f'fill="{C["primary2"]}" opacity=".38"/>')
    p.append(f'<polyline points="{pts}" fill="none" stroke="{C["primary"]}" stroke-width="2.4"/>')

    # summit marker
    st = prof["summitAtHours"]
    sf = max(r["ft"] for r in rd)
    p.append(f'<line x1="{X(st):.1f}" y1="{pad_t}" x2="{X(st):.1f}" y2="{pad_t+ih}" '
             f'stroke="{C["gold"]}" stroke-width="1.6" stroke-dasharray="4 3"/>')
    p.append(f'<text x="{X(st):.1f}" y="{pad_t-7}" text-anchor="middle" class="axlab" '
             f'fill="{C["gold"]}">summit {sf:,} ft · h{st:g}</text>')

    # "tank empty" marker
    et = prof["emptyAtHours"]
    p.append(f'<rect x="{X(et):.1f}" y="{pad_t}" width="{X(tmax)-X(et):.1f}" height="{ih}" '
             f'fill="{C["bad"]}" opacity=".13"/>')
    p.append(f'<line x1="{X(et):.1f}" y1="{pad_t}" x2="{X(et):.1f}" y2="{pad_t+ih}" '
             f'stroke="{C["bad"]}" stroke-width="2"/>')
    p.append(f'<text x="{X(et)+5:.1f}" y="{pad_t+13}" class="axlab" fill="{C["bad"]}">'
             f'tank empty · h{et:g}</text>')

    # fuel markers along the bottom
    for r in hours:
        hh = r["hour"]
        if hh > tmax:
            continue
        x = X(hh)
        gel = r["gel"]
        col = C["bad"] if gel else C["accent"]
        y = pad_t + ih
        p.append(f'<line x1="{x:.1f}" y1="{y}" x2="{x:.1f}" y2="{y+9}" '
                 f'stroke="{col}" stroke-width="2"/>')
        p.append(f'<circle cx="{x:.1f}" cy="{y+14:.1f}" r="5" fill="{col}">'
                 f'<title>Hour {hh}: {html.escape(", ".join(r["items"]))} — '
                 f'{r["cal"]} cal, {r["carbG"]} g carb</title></circle>')
        p.append(f'<text x="{x:.1f}" y="{y+17.5:.1f}" text-anchor="middle" '
                 f'style="font-size:7.5px;fill:#fff;font-weight:700">'
                 f'{"G" if gel else hh}</text>')
    # x axis hour labels
    for t in range(0, int(tmax) + 1, 2):
        p.append(f'<text x="{X(t):.1f}" y="{h-pad_b+50}" text-anchor="middle" class="tick">'
                 f'{t}h</text>')
    p.append(f'<text x="6" y="13" class="axlab">elevation (ft)</text>')
    p.append("</svg>")
    leg = (f'<span class="lg"><i style="background:{C["bad"]}"></i>gel</span>'
           f'<span class="lg"><i style="background:{C["accent"]}"></i>solid food</span>'
           f'<span class="lg"><i style="background:{C["gold"]}"></i>summit</span>'
           f'<span class="lg"><i style="background:{C["bad"]};opacity:.3"></i>'
           f'where you ran empty last time</span>')
    return f'<div class="legend">{leg}</div>' + "".join(p)


def stacked_zones(hikes, *, w=680, h=214):
    zc = [("Z1", "#c9d4e0"), ("Z2", C["accent2"]), ("Z3", C["primary2"]),
          ("Z4", C["warn2"]), ("Z5", C["bad2"])]
    rows = [h_ for h_ in hikes if h_.get("zonesPct")]
    if not rows:
        return ""
    pad_l, pad_b, pad_t, pad_r = 40, 56, 14, 14
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    slot = iw / len(rows)
    bw = min(58, slot * 0.6)
    p = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for g in range(5):
        v = 100 * g / 4
        y = pad_t + ih - (v / 100) * ih
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" '
                 f'stroke="{C["line"]}"/>'
                 f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="tick">{v:.0f}%</text>')
    for i, hk in enumerate(rows):
        cx = pad_l + slot * (i + 0.5)
        acc = 0.0
        for zn, col in zc:
            v = hk["zonesPct"].get(zn, 0)
            if not v:
                continue
            bh = (v / 100) * ih
            y = pad_t + ih - acc - bh
            p.append(f'<rect x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                     f'height="{bh:.1f}" fill="{col}">'
                     f'<title>{zn} — {short_date(hk["date"])}: {v}%</title></rect>')
            acc += bh
        p.append(f'<text x="{cx:.1f}" y="{h-pad_b+18}" text-anchor="middle" '
                 f'class="tick">{e(short_date(hk["date"]))}</text>')
        meth = hk.get("zoneMethod", "%max HR")
        col = C["primary"] if "HRR" in meth else C["warn"]
        p.append(f'<text x="{cx:.1f}" y="{h-pad_b+33}" text-anchor="middle" '
                 f'class="tick" style="font-size:9.5px;fill:{col}">{e(meth)}</text>')
    p.append("</svg>")
    leg = "".join(f'<span class="lg"><i style="background:{c}"></i>{z}</span>' for z, c in zc)
    return f'<div class="legend">{leg}</div>' + "".join(p)


# ---------------------------------------------------------------- build
def build():
    d = json.loads(DATA.read_text())
    m, phys = d["meta"], d["physiology"]
    hikes, rucks = d["hikes"], d["ruckSessions"]
    ng = d["nutritionGuidance"]
    kg = phys["bodyweightKg"]
    lb = phys["bodyweightLb"]

    def rng(spec):
        """'7-10 g' -> (7.0, 10.0)"""
        nums = re.findall(r"[\d.]+", spec)
        return (float(nums[0]), float(nums[-1]))

    # sleeping-altitude ladder figures — referenced by both the ladder and the gaps narrative
    sl = d.get("sleepLadder", {})
    slept = sl.get("achievedFt", 8000)
    cott = sl.get("cottonwoodFt", 10000)
    tcamp = sl.get("trailCampFt", m["whitneyProfile"]["trailCampElevationFt"])
    step = tcamp - cott

    today = datetime.date.fromisoformat(m["lastUpdated"])
    summit = datetime.date.fromisoformat(m["summitDate"])
    days_out = (summit - today).days

    # biggest ASCENT and highest ELEVATION are different hikes — don't conflate them
    peak = max(hikes, key=lambda h: h["ascentFt"])
    highest = max(hikes, key=lambda h: h["maxElevFt"])
    total_ascent = sum(h["ascentFt"] for h in hikes)
    total_mi = sum(h["distanceMi"] for h in hikes) + sum(r["distanceMi"] for r in rucks)
    vo2 = phys["vo2max"][-1]["value"]
    span = f'{short_date(m["logCoversFrom"])} – {short_date(m["logCoversTo"])}'
    # highest point overall may have been reached without walking (gondola)
    non_foot = [a for a in d.get("altitudeExposure", []) if not a.get("onFoot")]
    top_any = max([a["elevationFt"] for a in non_foot] + [highest["maxElevFt"]])
    top_note = (f'on foot · {top_any:,} ft by gondola'
                if top_any > highest["maxElevFt"] else "on foot")

    # ---- stat tiles, scoped to the Whitney block rather than whatever the PDF happened to cover
    wb = d.get("whitneyBlock")
    if wb:
        blk_from = datetime.date.fromisoformat(wb["from"]).strftime("%b %-d")
        blk_to = datetime.date.fromisoformat(wb["to"]).strftime("%b %-d")
        tiles = [
            ("Days to summit", days_out, summit.strftime("%b %-d, %Y"), C["gold"]),
            ("Highest point on foot", f'{wb["highestOnFootFt"]:,} ft', top_note, C["primary"]),
            ("Biggest single ascent", f'{wb["biggestAscentFt"]:,} ft',
             f'Whitney Day 1 is {m["whitneyProfile"]["day1AscentFt"]:,} ft', C["primary"]),
            ("VO2 max", vo2,
             f'from {phys["vo2max"][0]["value"]} · Oct target {phys["vo2maxTargets"]["october"]}', C["accent"]),
            ("Distance this block", f'{wb["distanceMi"]} mi',
             f'{wb["hikes"]} hikes · {wb["rucks"]} rucks · {wb["walks"]} walks', C["ink2"]),
            ("Ascent this block", f'{wb["ascentFt"]:,} ft', f'{blk_from} – {blk_to}', C["ink2"]),
            ("Hours on foot", f'{wb["hours"]} h', f'{wb["kcal"]:,} kcal burned', C["ink2"]),
            ("Longest day ever", "16:00", 'Grand Canyon Rim to Rim, May 2025', C["violet"]),
        ]
    else:
        tiles = [
            ("Days to summit", days_out, summit.strftime("%b %-d, %Y"), C["gold"]),
            ("Highest point on foot", f'{highest["maxElevFt"]:,} ft', top_note, C["primary"]),
            ("Biggest single ascent", f'{peak["ascentFt"]:,} ft', f'Whitney Day 1 is {m["whitneyProfile"]["day1AscentFt"]:,} ft', C["primary"]),
            ("VO2 max", vo2, f'from {phys["vo2max"][0]["value"]} · Oct target {phys["vo2maxTargets"]["october"]}', C["accent"]),
            ("Total logged distance", f"{total_mi:.0f} mi", f"{len(hikes)} hikes · {len(rucks)} rucks", C["ink2"]),
            ("Cumulative hike ascent", f"{total_ascent:,} ft", span, C["ink2"]),
        ]
    tile_html = "".join(
        f'<div class="tile"><div class="tl">{e(l)}</div>'
        f'<div class="tv" style="color:{col}">{e(v)}</div>'
        f'<div class="ts">{e(s)}</div></div>'
        for l, v, s, col in tiles)

    # ---- charts
    ch_ascent = grouped_bars(
        [(short_date(h["date"]), [h["ascentFt"]]) for h in hikes],
        series_meta=[("Ascent (ft)", C["primary"])],
        fmt=lambda v: f"{v/1000:.1f}k", h=225)

    # pace and HR only mean something on hikes where YOU set the pace — family
    # outings are governed by staying together, so they are excluded from trends
    trn = [h for h in hikes if h.get("effortType", "training") == "training"]
    fam = [h for h in hikes if h.get("effortType") == "family"]
    ch_hr = line_chart(
        [{"label": "Avg HR", "color": C["bad"],
          "points": [(short_date(h["date"]), h["avgHR"]) for h in trn]},
         {"label": "Max HR", "color": C["warn"], "dash": "5 4",
          "points": [(short_date(h["date"]), h["maxHR"]) for h in trn]}],
        ylabel="bpm", fmt=lambda v: f"{v:.0f}")

    ch_pace = line_chart(
        [{"label": "Moving pace", "color": C["accent"],
          "points": [(short_date(h["date"]),
                      tosec(h["movingPace"]) / 60 if h.get("movingPace") else None)
                     for h in trn]}],
        ylabel="min/mi (lower = faster)", invert=True,
        fmt=lambda v: mmss(v * 60))
    excl = ", ".join(f'{short_date(h["date"])} ({h["route"].split(",")[0]})' for h in fam)

    ch_ruck = line_chart(
        [{"label": "Pace", "color": C["accent"],
          "points": [(short_date(r["date"]), tosec(r["movingPace"]) / 60
                      if r.get("movingPace") else None) for r in rucks]},
         ],
        ylabel="min/mi (lower = faster)", invert=True, fmt=lambda v: mmss(v * 60), h=200)

    ch_ruck_hr = line_chart(
        [{"label": "Avg HR", "color": C["bad"],
          "points": [(short_date(r["date"]), r.get("avgHR")) for r in rucks]}],
        ylabel="bpm", fmt=lambda v: f"{v:.0f}", h=200)

    fuel_rows = [(short_date(h["date"]),
                  [round(h["sweatLossMl"] / 1000, 2),
                   h.get("fuel", {}).get("waterL")])
                 for h in hikes if h.get("sweatLossMl")]
    ch_fluid = grouped_bars(
        fuel_rows,
        series_meta=[("Sweat loss (L)", C["bad"]), ("Fluid taken in (L)", C["accent"])],
        fmt=lambda v: f"{v:.1f}L", h=235)

    cal_rows = [(short_date(h["date"]),
                 [h.get("totalCal"), h.get("fuel", {}).get("caloriesIn")])
                for h in hikes if h.get("totalCal")]
    ch_cal = grouped_bars(
        cal_rows,
        series_meta=[("Calories burned", C["warn"]), ("Calories eaten", C["primary"])],
        fmt=lambda v: f"{v/1000:.1f}k", h=235)

    ch_zones = stacked_zones(hikes)

    # ---- sweat rate per hour: Garmin's estimate normalised by elapsed hiking time
    sweat = [(h, h["sweatLossMl"] / (tosec(h["totalTime"]) / 3600))
             for h in hikes if h.get("sweatLossMl")]
    ch_sweat = line_chart(
        [{"label": "Sweat rate", "color": C["bad"],
          "points": [(short_date(h["date"]), round(r)) for h, r in sweat]}],
        ylabel="ml per hour", fmt=lambda v: f"{v:.0f}", h=210,
        band=(600, 800))
    sw_vals = [r for _, r in sweat]
    sw_lo, sw_hi = min(sw_vals), max(sw_vals)
    sw_avg = sum(sw_vals) / len(sw_vals)
    sw_n = len(sweat)

    # ---- actual on-trail intake rate vs burn rate, where both are known
    fuel_rate = []
    for h in hikes:
        if not h.get("totalCal"):
            continue
        hrs = tosec(h["totalTime"]) / 3600
        cin = h.get("fuel", {}).get("caloriesIn")
        fuel_rate.append((h, h["totalCal"] / hrs,
                          None if cin is None else cin / hrs))
    known = [(h, b, i) for h, b, i in fuel_rate if i is not None]
    burn_lo = min(b for _, b, _ in fuel_rate)
    burn_hi = max(b for _, b, _ in fuel_rate)
    in_lo = min(i for _, _, i in known)
    in_hi = max(i for _, _, i in known)

    # ---- what a long-hike-day carb target looks like as an actual day of eating
    sd = ng["sampleLongHikeDay"]
    day_rows = ""
    day_total = 0
    for meal in sd["meals"]:
        sub = sum(i["qty"] * i["carbsG"] for i in meal["items"])
        day_total += sub
        items = ", ".join(
            f'{i["qty"]} {i["unit"]+" " if i["unit"] else ""}{i["food"]}'
            for i in meal["items"])
        day_rows += (
            f'<tr><td><b>{e(meal["when"])}</b><div class="sub">{e(items)}</div>'
            f'<div class="sub" style="color:{C["bad"]}">{e(meal["avoid"])}</div></td>'
            f'<td class="num nw"><b>{sub:.0f} g</b></td></tr>')
    lhd_lo, lhd_hi = rng(ng["carbsPerKgPerDay"]["longHikeDay"])
    lhd_lo, lhd_hi = lhd_lo * kg, lhd_hi * kg
    in_band = lhd_lo <= day_total <= lhd_hi

    # ---- nutrition in absolute grams
    carb_rows = ""
    for k, v in ng["carbsPerKgPerDay"].items():
        lo, hi = rng(v)
        pretty = re.sub(r"(?<!^)(?=[A-Z])", " ", k).lower()
        carb_rows += (f'<tr><td>{e(pretty)}</td>'
                      f'<td class="num nw">{e(v)}/kg</td>'
                      f'<td class="num nw"><b>{lo*kg:.0f}–{hi*kg:.0f} g</b></td></tr>')
    plo, phi = rng(ng["proteinPerKgPerDay"]["range"])
    prot_abs = f"{plo*kg:.0f}–{phi*kg:.0f} g"

    # ---- pack weight as a share of bodyweight
    pack_rows = ""
    for w, label in [(12, "every session logged so far"),
                     (18, "Aug 1 — Devils Slide"),
                     (25, "Aug 15 — San Gorgonio"),
                     (28, "Aug 22 — load-focused local"),
                     (30, "Whitney Day 1, estimated")]:
        pct = w / lb * 100
        col = (C["primary"] if pct <= 12 else
               C["warn"] if pct <= 18 else C["bad"])
        note = ("comfortable day-pack range" if pct <= 12 else
                "typical backpacking range" if pct <= 20 else
                "upper limit — trains best gradually")
        pack_rows += (f'<tr><td><b>{w} lb</b><div class="sub">{e(label)}</div></td>'
                      f'<td class="num nw" style="color:{col};font-weight:650">{pct:.0f}%</td>'
                      f'<td class="sub">{e(note)}</td></tr>')

    # ---- hike table
    def flagchip(f):
        if not f:
            return ""
        col, lab = FLAG.get(f, (C["ink3"], f))
        return f'<span class="chip" style="color:{col};border-color:{col}">{e(lab)}</span>'

    hrows = ""
    for h in reversed(hikes):
        fl = flagchip(h.get("flag"))
        effnote = ""
        if h.get("effortType") == "family":
            fl += (f'<span class="chip" style="color:{C["ink3"]};border-color:{C["line"]}">'
                   f'family outing</span>')
            effnote = f'<br><b>{e(h.get("effortNote", ""))}</b>'
        sw = h.get("sweatLossMl")
        wl = h.get("fuel", {}).get("waterL")
        defc = ""
        if sw and wl:
            dl = sw / 1000 - wl
            col = C["bad"] if dl > 2 else (C["warn"] if dl > 0.8 else C["primary"])
            defc = f'<span style="color:{col};font-weight:650">−{dl:.1f}L</span>'
        hrows += (
            "<tr>"
            f'<td class="nw"><b>{e(short_date(h["date"]))}</b>'
            f'{"<sup>~</sup>" if h.get("dateApprox") else ""}</td>'
            f'<td>{e(h["label"])} {fl}<div class="sub">{e(h["route"])}</div></td>'
            f'<td class="num">{h["distanceMi"]:.2f}</td>'
            f'<td class="num">{(h.get("ascentFt") or 0):,}</td>'
            f'<td class="num">{(h.get("maxElevFt") or 0):,}</td>'
            f'<td class="num nw">{e(h.get("movingPace") or "–")}</td>'
            f'<td class="num">{h.get("avgHR") or "–"}<span class="sub2">/{h.get("maxHR") or "–"}</span></td>'
            f'<td class="num">{e(h.get("aerobicEffect","–"))}</td>'
            f'<td class="num">{e(h.get("exerciseLoad","–"))}</td>'
            f'<td class="num">{"✓" if h.get("poles") else "—"}</td>'
            f'<td class="num">{defc or "—"}</td>'
            "</tr>"
            f'<tr class="notrow"><td></td><td colspan="10" class="note">{e(h["coachNote"])}'
            f'{effnote}</td></tr>'
        )

    rrows = ""
    for r in rucks:
        rrows += (
            "<tr>"
            f'<td class="nw"><b>{e(short_date(r["date"]))}</b></td>'
            f'<td class="num">{r["packLb"]}</td>'
            f'<td class="num">{r["distanceMi"]:.2f}</td>'
            f'<td class="num nw">{e(r.get("movingPace") or "–")}</td>'
            f'<td class="num">{r.get("avgHR") or "–"}<span class="sub2">/{r.get("maxHR") or "–"}</span></td>'
            f'<td>{flagchip(r.get("flag"))}<div class="sub">{e(r.get("coachNote") or "")}</div></td>'
            "</tr>")

    # ---- issues
    order = {"high": 0, "medium": 1, "watch": 2, "info": 3}
    issues = sorted(d["openIssues"], key=lambda i: order.get(i["severity"], 9))
    irows = ""
    for i in issues:
        col, bgc, lab = SEV.get(i["severity"], SEV["info"])
        since = f' · since {e(short_date(i["since"]))}' if i.get("since") else ""
        irows += (
            f'<div class="issue" style="border-left-color:{col}">'
            f'<div class="ihead"><span class="sev" style="background:{bgc};color:{col}">{e(lab)}</span>'
            f'<b>{e(i["issue"])}</b></div>'
            f'<div class="sub">{e(i["action"])}{since}</div></div>')

    # ---- gear
    grows = ""
    for g in d["gear"]:
        need = g["status"] == "NEEDED"
        box = "☐" if need else "☑"
        col = C["bad"] if need else C["primary"]
        badge = (f'<span class="chip" style="color:{C["bad"]};border-color:{C["bad"]}">needed</span>'
                 if need else "")
        note = f'<div class="sub">{e(g["note"])}</div>' if g.get("note") else ""
        grows += (f'<li><span style="color:{col};font-weight:700">{box}</span> '
                  f'<b>{e(g["item"])}</b>{badge}{note}</li>')

    # ---- phases
    prows = ""
    st_col = {"complete": C["primary"], "current": C["accent"], "upcoming": C["ink3"]}
    for p in d["trainingPhases"]:
        col = st_col.get(p["status"], C["ink3"])
        mark = "●" if p["status"] == "current" else ("✓" if p["status"] == "complete" else "○")
        pnote = f' — {e(p["note"])}' if p.get("note") else ""
        prows += (f'<div class="phase" style="border-color:{col}">'
                  f'<div class="pnum" style="color:{col}">{mark} Phase {p["phase"]}</div>'
                  f'<b>{e(p["name"])}</b><div class="sub">{e(p["window"])}{pnote}</div></div>')

    # ---- routine
    wrows = "".join(
        f'<tr><td class="nw"><b>{e(r["day"])}</b></td><td>{e(r["session"])}'
        f'<div class="sub">{e(r.get("note",""))}</div></td></tr>'
        for r in d["weekdayRoutine"]["template"])

    # ---- nutrition
    trail = ng["onTrail"]

    # ---- trails
    trows = ""
    for t in d["trailOptions"]:
        closed = "CLOSED" in str(t["status"]).upper()
        col = C["bad"] if closed else C["primary"]
        tnote = f'<div class="sub">{e(t["note"])}</div>' if t.get("note") else ""
        asc = f'{t["ascentFt"]:,}' if t.get("ascentFt") else "–"
        mx = f'{t["maxElevFt"]:,}' if t.get("maxElevFt") else "–"
        trows += (f'<tr><td><b>{e(t["name"])}</b>{tnote}</td>'
                  f'<td class="num nw">{e(t.get("distanceMi","–"))}</td>'
                  f'<td class="num nw">{asc}</td>'
                  f'<td class="num nw">{mx}</td>'
                  f'<td class="nw" style="color:{col};font-weight:600">{e(t["status"])}</td></tr>')

    # ---- altitude exposure (hikes + non-hike events, by elevation)
    exposures = d.get("altitudeExposure", [])
    # a hike and an exposure event on the same date are the same thing — merge, don't duplicate
    hike_dates = {h["date"] for h in hikes}
    # merge symptoms onto a hike row only from on-foot exposures — a same-day gondola
    # ride is a separate event and its symptoms must not leak onto the hike
    sym_by_date = {a["date"]: a.get("symptoms") for a in exposures if a.get("onFoot")}
    alt_events = [{"date": h["date"], "place": h["route"], "elevationFt": h["maxElevFt"],
                   "onFoot": True, "symptoms": sym_by_date.get(h["date"]),
                   "note": h["label"], "isHike": True}
                  for h in hikes if h["maxElevFt"] >= 7000]
    alt_events += [dict(a, isHike=False) for a in exposures
                   if a["date"] not in hike_dates or not a.get("onFoot")]
    alt_events.sort(key=lambda a: a["elevationFt"], reverse=True)
    max_alt = m["whitneyProfile"]["summitElevationFt"]
    arows = ""
    for a in alt_events:
        pct = a["elevationFt"] / max_alt * 100
        sym = a.get("symptoms")
        recl = a.get("reclassified")
        col = C["primary"] if (recl or not sym) else C["warn"]
        foot = "on foot" if a.get("onFoot") else "not on foot"
        symblock = ""
        if sym:
            style = ("" if not recl else
                     f' style="color:{C["ink2"]};background:{C["bg"]};'
                     f'border-left-color:{C["primary2"]}"')
            symblock = f'<div class="symp"{style}>{e(sym)}</div>'
        if a.get("reclassifyNote"):
            symblock += f'<div class="tgt">{e(a["reclassifyNote"])}</div>'
        arows += (
            f'<div class="altrow">'
            f'<div class="altbar"><span style="width:{pct:.1f}%;background:{col}"></span></div>'
            f'<div class="altmeta"><b>{a["elevationFt"]:,} ft</b>'
            f'<span class="sub2"> · {e(short_date(a["date"]))} · {foot}</span>'
            f'{" <span class=chip style=color:" + C["primary"] + ";border-color:" + C["primary2"] + ">reclassified</span>" if recl else ""}'
            f'<div class="sub">{e(a["place"])}</div>'
            f'{symblock}</div></div>')

    # reference lines
    ref = "".join(
        f'<div class="altrow"><div class="altbar ref">'
        f'<span style="width:{v/max_alt*100:.1f}%"></span></div>'
        f'<div class="altmeta"><b>{v:,} ft</b><span class="sub2"> · {e(lab)}</span></div></div>'
        for v, lab in [(m["whitneyProfile"]["trailCampElevationFt"], "Whitney Trail Camp — where you SLEEP on Oct 1"),
                       (max_alt, "Whitney summit")])

    # ---- nights slept at altitude — a separate ladder, because sleeping altitude
    # is what actually drives acclimatisation, not the high point you touched
    srows = ""
    for s in d.get("sleepAtAltitude", []):
        pct = s["elevationFt"] / tcamp * 100
        srows += (
            f'<div class="altrow">'
            f'<div class="altbar"><span style="width:{min(pct,100):.1f}%;'
            f'background:{C["primary"]}"></span></div>'
            f'<div class="altmeta"><b>{s["elevationFt"]:,} ft</b>'
            f'<span class="sub2"> · {s["nights"]} night'
            f'{"s" if s["nights"] != 1 else ""} · {e(s["dates"])}</span>'
            f'<div class="sub">{e(s["place"])}</div>'
            f'<div class="tgt">{e(s["note"])}</div></div></div>')
    for v, lab in [(cott, f"Cottonwood Camp, Sep 29 — planned"),
                   (tcamp, "Whitney Trail Camp, Oct 1 — the night that matters")]:
        srows += (
            f'<div class="altrow"><div class="altbar ref">'
            f'<span style="width:{v/tcamp*100:.1f}%"></span></div>'
            f'<div class="altmeta"><b>{v:,} ft</b>'
            f'<span class="sub2"> · {e(lab)}</span></div></div>')

    # ---- forward plan
    KIND = {
        "hike": (C["primary"], "Hike"), "rest": (C["ink3"], "Rest"),
        "week": (C["accent"], "Weekday"), "admin": (C["bad"], "Admin"),
        "addition": (C["violet"], "Added"), "travel": (C["ink2"], "Travel"),
        "acclimatization": (C["accent"], "Acclimatize"), "summit": (C["gold"], "Summit"),
    }
    frows = ""
    for s in d.get("forwardPlan", []):
        col, klab = KIND.get(s["kind"], (C["ink3"], s["kind"]))
        hot = s.get("priority") == "high"
        pack = ""
        if s.get("packLb"):
            pv = s["packLb"]
            txt = "full pack weight" if str(pv) == "full" else f"pack {pv} lb"
            pack = f'<span class="chip" style="color:{C["ink2"]};border-color:{C["line"]}">{e(txt)}</span>'
        tgt = (f'<div class="tgt">{e(s["targets"])}</div>') if s.get("targets") else ""
        frows += (
            f'<div class="step{" hot" if hot else ""}" style="border-left-color:{col}">'
            f'<div class="swin"><span class="kind" style="color:{col}">{e(klab)}</span>'
            f'{e(s["window"])}</div>'
            f'<div class="stitle">{e(s["title"])}{pack}</div>'
            f'<div class="sub">{e(s["detail"])}</div>{tgt}</div>')

    dq = "".join(f"<li>{e(x)}</li>" for x in d["dataQualityNotes"])
    supp = ""
    for s in d["supplements"]:
        snote = f'<div class="sub">{e(s["note"])}</div>' if s.get("note") else ""
        supp += (f'<li><b>{e(s["name"])}</b> <span class="chip">{e(s["status"])}</span>'
                 f'{snote}</li>')

    hyd = d["hydrationAnalysis"]
    fp = d["fuelingProtocol"]

    # ---- weekly nutrition plan
    TYPE_COL = {"easy": C["ink3"], "easy-moderate": C["accent"], "moderate": C["accent"],
                "load": C["warn"], "hike": C["primary"]}
    nw_html = ""
    weeks = d.get("nutritionWeeks", [])
    if weeks:
        w = weeks[-1]
        drows = ""
        for day in w["days"]:
            tc = TYPE_COL.get(day["type"], C["ink3"])
            past = day.get("past")
            drows += (
                f'<tr{" class=hotrow" if day.get("flag") else ""}'
                f'{" style=opacity:.55" if past else ""}>'
                f'<td class="nw"><b>{e(day["day"])}</b>'
                f'<div class="sub2" style="color:{tc};font-weight:650;text-transform:uppercase;'
                f'letter-spacing:.4px;font-size:10px">{e(day["type"])}</div></td>'
                f'<td>{e(day["session"])}<div class="sub">{e(day["note"])}</div></td>'
                f'<td class="num nw"><b>{e(day["carbsG"])}</b></td>'
                f'<td class="num nw">{e(day["proteinG"])}</td></tr>')
        lf = w["loadDayFoodPlan"]
        lrows2 = "".join(
            f'<tr><td><b>{e(x["when"])}</b><div class="sub">{e(x["items"])}</div></td>'
            f'<td class="num nw">{x["carbsG"]} g</td></tr>' for x in lf["meals"])
        lf_total = sum(x["carbsG"] for x in lf["meals"])
        mt = w["measureThis"]
        nw_html = f"""
<section>
  <h2>This week's nutrition<span class="n">{e(w['label'])}</span></h2>
  <p class="lede">{e(w['context'])} Hike day assumed to be <b>{e(w['hikeDay'])}</b> —
  {e(w['hikeDayNote'])}</p>
  <div class="scroll"><table>
  <thead><tr><th>Day</th><th>Session</th><th>Carbs</th><th>Protein</th></tr></thead>
  <tbody>{drows}</tbody></table></div>
  <p class="sub">All figures in grams per day at {lb} lb / {kg:.0f} kg. Carbs follow
  3–5 g/kg easy, 5–7 moderate, 7–10 on load and hike days; protein stays in the
  1.6–2.0 g/kg band throughout.</p>

  <h3>Friday's load day, as food</h3>
  <p class="lede">{e(lf['note'])}</p>
  <div class="scroll"><table style="min-width:0">
  <tbody>{lrows2}
  <tr><td><b>Total</b></td><td class="num nw"
   style="color:{C['primary']};font-weight:700">{lf_total} g</td></tr></tbody></table></div>

  <div class="callout"><b>{e(mt['title'])}</b> — the single most valuable thing you can do
  this weekend. {e(mt['why'])}
  <div class="tgt">{e(mt['how'])}</div></div>
</section>"""

    # ---- answers to the two physiology questions
    pa = d.get("physiologyAnswers")
    pa_html = ""
    if pa:
        rm, wq, iq = pa["restingMetabolicRate"], pa["weightQuestion"], pa["inclineQuestion"]
        WCOL = {"the answer": C["bad"], "primary": C["bad"],
                "primary at altitude": C["bad"], "primary everywhere": C["bad"],
                "primary on long efforts": C["bad"], "secondary": C["warn"],
                "amplifier": C["warn"], "contributing": C["warn"],
                "contributing on long efforts": C["warn"], "structural": C["violet"]}
        crows = ""
        for c in iq["causes"]:
            col = WCOL.get(c["weight"], C["ink3"])
            crows += (
                f'<tr><td><b>{e(c["cause"])}</b>'
                f'<div class="sub">{e(c["detail"])}</div></td>'
                f'<td class="nw" style="color:{col};font-weight:650;font-size:11px;'
                f'text-transform:uppercase;letter-spacing:.4px">{e(c["weight"])}</td></tr>')
        fixes = "".join(f"<li>{e(x)}</li>" for x in iq["techniqueFixes"])

        # ---- the tank: hike duration vs time-to-empty
        eb = d.get("energyBudget", {})
        eb_html = ""
        if eb:
            tank = eb["usableGlycogenCal"]
            # bar chart: for each hike with intake data, duration vs when the tank empties
            rows_eb = ""
            for s in eb["scenarios"]:
                emp = s["emptyAtHours"]
                sj_h = eb["sanJacinto"]["hours"]
                survives = emp >= sj_h
                col = C["primary"] if survives else C["bad"]
                w = min(100, emp / 24 * 100)
                rows_eb += (
                    f'<tr><td class="nw"><b>{s["intakeRate"]} cal/hr</b>'
                    f'<div class="sub">{e(s["label"])}</div></td>'
                    f'<td style="width:150px"><div class="altbar" style="flex:none;width:140px">'
                    f'<span style="width:{w:.0f}%;background:{col}"></span></div></td>'
                    f'<td class="num nw" style="color:{col};font-weight:700">{emp:.1f} h</td>'
                    f'<td class="sub">{e(s["outcome"])}</td></tr>')
            sj = eb["sanJacinto"]
            sa = eb["saturday"]
            eb_html = f"""
  <div class="callout"><b>Your tank.</b> {e(eb['concept'])}</div>
  <div class="tiles" style="margin:14px 0">
    <div class="tile"><div class="tl">Usable glycogen</div>
      <div class="tv" style="color:{C['accent']};font-size:24px">~{tank:,} cal</div>
      <div class="ts">the tank — training doesn't enlarge it much</div></div>
    <div class="tile"><div class="tl">Your burn rate</div>
      <div class="tv" style="color:{C['warn']};font-size:24px">{e(eb['burnRateCalPerHour'])}</div>
      <div class="ts">cal/hr, steady across all 10 hikes</div></div>
    <div class="tile"><div class="tl">Tank alone lasts</div>
      <div class="tv" style="color:{C['bad']};font-size:24px">{eb['tankAloneHours']} h</div>
      <div class="ts">eating nothing at all</div></div>
  </div>
  <div class="callout good"><b>And here is why Blue Sky feels different.</b> {e(eb['keyInsight'])}</div>
  <div class="callout"><b>San Jacinto, in one line.</b> {e(sj['verdict'])}</div>

  <h3>San Jacinto replayed at different intake rates</h3>
  <div class="scroll"><table>
  <thead><tr><th>Eating</th><th>Time to empty</th><th></th><th>Outcome on an 11.1 h day</th></tr></thead>
  <tbody>{rows_eb}</tbody></table></div>

  <div class="callout" style="background:#fff6f5;border-color:{C['bad2']}">
  <b>The number that decides Saturday.</b> {e(sa['note'])}</div>

  <h3>So the whole answer is two lines</h3>
  <ul class="clean">{fixes}</ul>
  <p class="sub">{e(eb['glycogenNote'])}</p>"""
        alt_rows = ""
        for ft, label in [(10934, "Gem Lakes, Jul 26"),
                          (tcamp, "Whitney Trail Camp"),
                          (max_alt, "Whitney summit")]:
            mt_ = ft * 0.3048
            lo = max(0, (mt_ - 1500) / 1000 * 8)
            hi = max(0, (mt_ - 1500) / 1000 * 11)
            alt_rows += (
                f'<tr><td><b>{ft:,} ft</b><div class="sub">{e(label)}</div></td>'
                f'<td class="num nw">−{lo:.0f} to −{hi:.0f}%</td>'
                f'<td class="num nw" style="color:{C["bad"]};font-weight:700">'
                f'{vo2*(1-hi/100):.0f}–{vo2*(1-lo/100):.0f}</td></tr>')
        pa_html = f"""
<section>
  <h2>Two questions answered<span class="n">weight, and the wall on every incline</span></h2>

  <h3>Why the weight has not moved</h3>
  <p class="lede"><b>{e(wq['shortAnswer'])}</b></p>
  <div class="callout"><b>Your resting metabolism, measured ten times.</b>
  Back-calculating Garmin's resting-calorie figure to a 24-hour basis gives
  <b>{rm['estimateCalPerDay']:,} cal/day</b> across {rm['n']} hikes, with a spread of only
  {e(rm['spread'])}. That stability is unusual and it makes the rest of this arithmetic
  trustworthy.</div>
  <p class="lede">{e(wq['arithmetic'])}</p>
  <div class="callout good"><b>And this is good news, not a problem.</b> {e(wq['whyItMatters'])}</div>
  <p class="sub">{e(wq['caveat'])}</p>

  <h3>Why every incline feels like a wall</h3>
  <p class="lede"><b>{e(iq['shortAnswer'])}</b></p>
  <div class="callout"><b>Correction to my first answer.</b> {e(iq['retraction'])}</div>
  <p class="lede">{e(iq['evidence'])}</p>
  <div class="scroll"><table>
  <thead><tr><th>What is actually going on</th><th>Weight</th></tr></thead>
  <tbody>{crows}</tbody></table></div>

  {eb_html}

  <h3>What thin air costs you<span class="n"> — a footnote now, not the theory</span></h3>
  <div class="scroll"><table style="min-width:0">
  <thead><tr><th>Elevation</th><th>Aerobic capacity</th><th>Effective VO2 max</th></tr></thead>
  <tbody>{alt_rows}</tbody></table></div>
  <p class="sub">Against {vo2} at sea level. This is why the same grade that is comfortable at
  Blue Sky stops you at 10,900 ft — and why the Cottonwood acclimatisation night earns its place
  in the schedule.</p>

  <p class="sub">{e(iq['diagnosticQuestion'])}</p>
</section>"""

    # ---- 20 months of history: Rim to Rim + the stopped-time breakpoint
    hist, r2r, sta = d.get("history"), d.get("rimToRim"), d.get("stoppedTimeAnalysis")
    hist_html = ""
    if hist and r2r and sta:
        try:
            dig = json.loads((ROOT / "garmin" / "digest.json").read_text())
            pts = [(x["durSec"] / 3600, x["stoppedPct"],
                    f'{x["start"][:10]} · {x["name"] or ""}')
                   for x in dig
                   if x.get("durSec") and x.get("stoppedPct") is not None]
        except Exception:
            pts = []
        brows = "".join(
            f'<tr><td class="nw"><b>{e(b["band"])}</b></td>'
            f'<td class="num nw">{b["n"]}</td>'
            f'<td style="width:150px"><div class="altbar" style="flex:none;width:140px">'
            f'<span style="width:{b["meanStopped"]:.0f}%;background:'
            f'{C["bad"] if b["meanStopped"]>=40 else C["warn"] if b["meanStopped"]>=20 else C["primary"]}">'
            f'</span></div></td>'
            f'<td class="num nw"><b>{b["meanStopped"]}%</b></td>'
            f'<td class="sub nw">range {b["lo"]}–{b["hi"]}%</td></tr>'
            for b in sta["bands"])
        adds = "".join(f"<li>{e(x)}</li>" for x in r2r["whatWhitneyAddsThatThisDidnt"])
        bugs = "".join(f"<li>{e(x)}</li>" for x in hist["unitBugsFound"])
        BR = hist["burnRate"]
        hist_html = f"""
<section>
  <h2>Twenty months of history<span class="n">{hist['activities']} activities, {e(hist['dateRange'][0])} to {e(hist['dateRange'][1])}</span></h2>
  <p class="lede">{e(hist['note'])}</p>

  <h3>The hike that was missing from this log</h3>
  <div class="callout good"><b>Grand Canyon Rim to Rim, 25 May 2025.</b> {e(r2r['whyItChangesThings'])}</div>
  <div class="tiles" style="margin:14px 0">
    <div class="tile"><div class="tl">Distance</div>
      <div class="tv" style="color:{C['gold']};font-size:24px">{r2r['distanceMi']} mi</div>
      <div class="ts">Whitney is ~22 over two days</div></div>
    <div class="tile"><div class="tl">Ascent</div>
      <div class="tv" style="color:{C['gold']};font-size:24px">{r2r['ascentFt']:,} ft</div>
      <div class="ts">Whitney total is 6,200</div></div>
    <div class="tile"><div class="tl">On your feet</div>
      <div class="tv" style="color:{C['gold']};font-size:24px">{e(r2r['totalTime'])}</div>
      <div class="ts">started {e(r2r['startedAt'])} · {r2r['stoppedPct']}% stopped</div></div>
    <div class="tile"><div class="tl">Energy</div>
      <div class="tv" style="color:{C['gold']};font-size:24px">{r2r['kcal']:,}</div>
      <div class="ts">kcal · {r2r['steps']:,} steps · HR {r2r['avgHR']}</div></div>
  </div>
  <p class="lede">{e(r2r['vsWhitney'])}</p>
  <h3>What Whitney adds that this didn't test</h3>
  <ul class="clean">{adds}</ul>
  <div class="callout good"><b>The honest read.</b> {e(r2r['reassurance'])}</div>

  <h3>{e(sta['headline'])}</h3>
  {scatter_stopped(pts)}
  <p class="sub">Every hiking and walking activity with a moving-time figure. The green band is the
  window your tank covers unaided; the dashed line is where it runs out.</p>
  <div class="scroll"><table>
  <thead><tr><th>Duration</th><th>n</th><th>Mean stopped time</th><th></th><th></th></tr></thead>
  <tbody>{brows}</tbody></table></div>
  <p class="lede">{e(sta['interpretation'])}</p>
  <div class="callout" style="background:#fff6f5;border-color:{C['bad2']}">
  <b>The coincidence that isn't one.</b> {e(sta['theCoincidenceThatIsNot'])}</div>
  <div class="callout"><b>And it makes a falsifiable prediction.</b> {e(sta['whatItPredicts'])}</div>

  <h3>Burn rate, now confirmed across {BR['n']} long days</h3>
  <p class="lede">Mean <b>{BR['meanKcalHr']} kcal/hr</b>, range {BR['rangeKcalHr'][0]}–{BR['rangeKcalHr'][1]}.
  {e(BR['note'])}</p>

  <h3>Four unit bugs I found and fixed</h3>
  <ul class="clean">{bugs}</ul>
</section>"""

    # ---- what the real FIT file revealed
    ff = d.get("fitFindings")
    ff_html = ""
    if ff:
        def itemlist(items, col):
            return "".join(
                f'<div class="step" style="border-left-color:{col}">'
                f'<div class="stitle">{e(i["item"])}</div>'
                f'<div class="sub">{e(i["detail"])}</div></div>'
                for i in items)
        H = ff["headline"]
        bands = d["hikes"][7].get("fitDerived", {}).get("speedBandsMin", {})
        order = ["stopped", "under 1 mph", "1-2 mph", "2-3 mph", "over 3 mph"]
        tot = sum(bands.values()) or 1
        brows = ""
        for k in order:
            v = bands.get(k, 0)
            pct = v / tot * 100
            col = C["bad"] if k == "stopped" else C["primary"]
            brows += (f'<tr><td class="nw"><b>{e(k)}</b></td>'
                      f'<td style="width:170px"><div class="altbar" style="flex:none;width:160px">'
                      f'<span style="width:{pct:.0f}%;background:{col}"></span></div></td>'
                      f'<td class="num nw">{v//60}h {v%60:02d}m</td>'
                      f'<td class="num nw" style="color:{col};font-weight:700">{pct:.1f}%</td></tr>')
        ff_html = f"""
<section>
  <h2>What the FIT file revealed<span class="n">{ff['records']:,} records vs ~20 from a screenshot</span></h2>
  <p class="lede">{e(ff['file'])}. Three things it confirmed, three it corrected, and one nobody
  was looking for.</p>

  <div class="callout" style="background:#fff6f5;border-color:{C['bad2']}">
  <b>{e(H['title'])}</b><br>{e(H['detail'])}</div>
  <div class="scroll"><table style="min-width:0"><tbody>{brows}</tbody></table></div>
  <p class="lede">{e(H['interpretation'])}</p>
  <div class="callout good"><b>Why this is the lever that matters.</b> {e(H['whyItMatters'])}</div>
  <div class="callout"><b>Saturday's test.</b> {e(H['saturdayTest'])}</div>

  <h3>Confirmed</h3>
  {itemlist(ff['confirmed'], C['primary'])}
  <h3>Corrected — three things I had wrong</h3>
  {itemlist(ff['contradicted'], C['bad'])}
</section>"""

    # ---- watch configuration
    wcf = d.get("watchConfig")
    wcf_html = ""
    if wcf:
        why = "".join(f"<li>{e(x)}</li>" for x in wcf["why"])
        ins = "".join(
            f'<tr><td><b>{e(i["change"])}</b><div class="sub">{e(i["gain"])}</div></td>'
            f'<td class="sub nw" style="color:{C["primary"]};font-weight:650">{e(i["effort"])}</td></tr>'
            for i in wcf["insteadDoThis"])
        wcf_html = f"""
<section>
  <h2>Should you pause the watch on breaks?<span class="n">no — and here's the reasoning</span></h2>
  <div class="callout good"><b>{e(wcf['answer'])}</b></div>
  <ul class="clean">{why}</ul>
  <p class="sub">{e(wcf['verification'])}</p>
  <h3>Three changes that would help, none of them on-trail work</h3>
  <div class="scroll"><table><thead><tr><th>Change</th><th>Effort</th></tr></thead>
  <tbody>{ins}</tbody></table></div>
  <div class="callout"><b>When the full dump lands.</b> {e(wcf['dumpAdvice'])}</div>
</section>"""

    # ---- getting real data out of Garmin
    fx = d.get("fitExport")
    fx_html = ""
    if fx:
        prows = ""
        for i, pa in enumerate(fx["paths"], 1):
            steps = "".join(f"<li>{e(s)}</li>" for s in pa["steps"])
            rec = ('<span class="chip" style="color:' + C["primary"] +
                   ';border-color:' + C["primary2"] + '">recommended</span>'
                   if pa.get("recommended") else "")
            prows += (
                f'<div class="step" style="border-left-color:{C["accent"]}">'
                f'<div class="swin"><span class="kind" style="color:{C["accent"]}">'
                f'Option {i}</span>effort: {e(pa["effort"])}</div>'
                f'<div class="stitle">{e(pa["name"])}{rec}</div>'
                f'<ol class="steps">{steps}</ol>'
                f'<div class="tgt">{e(pa["gotcha"])}</div></div>')
        fx_html = f"""
<section>
  <h2>Getting real data out of Garmin<span class="n">FIT files, not screenshots</span></h2>
  <div class="callout" style="background:#fff6f5;border-color:{C['bad2']}">
  <b>Correction.</b> {e(fx['correction'])}</div>
  <p class="lede">{e(fx['whyBother'])}</p>
  {prows}
</section>"""

    # ---- what actually matters, ranked
    wam = d.get("whatActuallyMatters")
    wam_html = ""
    if wam:
        rows = ""
        for it in wam["items"]:
            r = it["rank"]
            col = C["bad"] if r <= 2 else (C["warn"] if r <= 4 else C["ink3"])
            bar = int(round((8 - r) / 7 * 100))
            rows += (
                f'<tr><td class="num nw" style="color:{col};font-weight:700;font-size:17px">{r}</td>'
                f'<td><b>{e(it["item"])}</b><div class="sub">{e(it["why"])}</div></td>'
                f'<td style="width:110px"><div class="altbar" style="flex:none;width:100px">'
                f'<span style="width:{bar}%;background:{col}"></span></div></td>'
                f'<td class="sub nw">{e(it["status"])}</td></tr>')
        wam_html = f"""
<section>
  <h2>What actually matters<span class="n">ranked by effect on Oct 2</span></h2>
  <p class="lede">{e(wam['note'])} The useful test for anything new: does it beat number one?
  Almost nothing does.</p>
  <div class="scroll"><table>
  <thead><tr><th>#</th><th>Lever</th><th>Relative weight</th><th>Status</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
</section>"""

    # ---- respiratory muscle trainer
    rt = d.get("respiratoryTrainer")
    rt_html = ""
    if rt:
        cau = "".join(f"<li>{e(x)}</li>" for x in rt["cautions"])
        rt_html = f"""
<section>
  <h2>Respiratory trainer<span class="n">started {e(short_date(rt['started']))}</span></h2>
  <p class="lede"><b>{e(rt['verdict'])}</b></p>
  <div class="grid2">
    <div><h3>What it does, and doesn't</h3>
      <p class="lede">{e(rt['whatItDoes'])}</p>
      <h3>At altitude</h3>
      <p class="lede">{e(rt['altitudeRelevance'])}</p>
    </div>
    <div><h3>How to use it</h3>
      <p class="lede">{e(rt['protocol'])}</p>
      <h3>Timing</h3>
      <p class="lede">{e(rt['timing'])}</p>
    </div>
  </div>
  <div class="callout good"><b>The best thing about it, and it is not the lung training.</b>
  {e(rt['bestSideEffect'])}</div>
  <h3>Cautions</h3>
  <ul class="clean">{cau}</ul>
  <div class="callout"><b>Expectations.</b> {e(rt['expectations'])}</div>
</section>"""

    # ---- Saturday fuel plan, hour by hour
    ge, gm, sp = d.get("gelEvidence"), d.get("gelMath"), d.get("saturdayFuelPlan")
    fuel_html = ""
    if ge and gm and sp:
        T, TG = sp["totals"], sp["targets"]
        cov = "".join(
            f'<tr><td class="nw"><b>{c["gels"]} gels</b></td>'
            f'<td class="num nw">{c["cal"]} cal</td>'
            f'<td style="width:130px"><div class="altbar" style="flex:none;width:120px">'
            f'<span style="width:{c["pctOfTarget"]}%;background:{C["bad"]}"></span></div></td>'
            f'<td class="num nw" style="color:{C["bad"]};font-weight:700">{c["pctOfTarget"]}%</td>'
            f'<td class="sub">of a 12-hour target</td></tr>'
            for c in gm["coverage"])
        gcau = "".join(f"<li>{e(x)}</li>" for x in gm["cautions"])
        hrows_f = ""
        for r in sp["hours"]:
            gel = r["gel"]
            hrows_f += (
                f'<tr{" class=hotrow" if gel else ""}>'
                f'<td class="nw"><b>Hour {r["hour"]}</b></td>'
                f'<td>{e(", ".join(r["items"]))}</td>'
                f'<td class="num nw">{r["cal"]}</td>'
                f'<td class="num nw">{r["carbG"]} g</td>'
                f'<td class="num nw">{r["sodiumMg"]}</td></tr>')
        P = ge["product"]
        # ---- caffeine placement
        cp = d.get("caffeinePlan")
        caf_html = ""
        if cp:
            why = "".join(f"<li>{e(x)}</li>" for x in cp["why"])
            curve = line_chart(
                [{"label": "Caffeine on board", "color": C["violet"],
                  "points": [(f'h{c["hour"]}', c["mg"]) for c in cp["onBoardCurve"]]}],
                ylabel="mg on board", fmt=lambda v: f"{v:.0f}", h=190, ymin=0)
            caf_html = f"""
  <h3>Caffeinated vs caffeine-free — where to put them</h3>
  <div class="callout good"><b>{e(cp['confirmed'])}</b></div>
  <p class="lede">{e(cp['strategy'])}</p>
  <ul class="clean">{why}</ul>
  {curve}
  <p class="sub">Modelled on a five-hour half-life. Zero until hour seven by design, peaking through
  the worst of the descent.</p>
  <div class="callout" style="background:#fff6f5;border-color:{C['bad2']}">
  <b>Different rule for Whitney.</b> {e(cp['whitneyRule'])}</div>
  <p class="sub"><b>Packing:</b> {e(cp['packingTip'])}</p>"""

        pr = d.get("sanJacintoProfile")
        prof_html = ""
        if pr:
            prof_html = f"""
  <h3>Your San Jacinto profile, with the new schedule laid over it</h3>
  {profile_with_fuel(pr, sp["hours"])}
  <p class="sub">{e(pr['source'])} <b>{e(pr['insight'])}</b></p>
  <div class="callout"><b>The pace trace says something too.</b> {e(pr['paceObservation'])}</div>
  <div class="callout good"><b>Transferring it to Saturday.</b> {e(pr['transferToDevilsSlide'])}</div>"""
        fuel_html = f"""
<section>
  <h2>Saturday's fuel plan<span class="n">hour by hour, on the clock</span></h2>
  <div class="callout good"><b>Your gel observation is the best evidence in this whole log.</b>
  {e(ge['whyItMatters'])}</div>
  <p class="sub">{e(ge['caffeineCaveat'])} Per gel: {P['calPerGel']} cal,
  {P['carbGPerGel']} g carb, {P['sodiumMgPerGel']} mg sodium,
  caffeine {e(P['caffeineMgPerGel'])}.</p>

  <h3>Six gels — worth doing, but check the arithmetic</h3>
  <p class="lede">{e(gm['verdict'])}</p>
  <div class="scroll"><table style="min-width:0"><tbody>{cov}</tbody></table></div>
  <h3>Four things about running six gels</h3>
  <ul class="clean">{gcau}</ul>

  {caf_html}

  <h3>The plan — anchored to the clock, not the map</h3>
  <div class="callout"><b>{e(sp['principle'])}</b></div>
  <div class="tiles" style="margin:14px 0">
    <div class="tile"><div class="tl">Total</div>
      <div class="tv" style="color:{C['primary']};font-size:24px">{T['cal']:,}</div>
      <div class="ts">calories carried</div></div>
    <div class="tile"><div class="tl">Rate</div>
      <div class="tv" style="color:{C['primary']};font-size:24px">{T['calPerHour']}</div>
      <div class="ts">cal/hr · floor {TG['calPerHourFloor']}, target {TG['calPerHourTarget']}</div></div>
    <div class="tile"><div class="tl">Carbs</div>
      <div class="tv" style="color:{C['accent']};font-size:24px">{T['carbGPerHour']} g</div>
      <div class="ts">per hour · target {e(TG['carbGPerHour'])}</div></div>
    <div class="tile"><div class="tl">Sodium in food</div>
      <div class="tv" style="color:{C['warn']};font-size:24px">{T['sodiumMg']:,}</div>
      <div class="ts">mg · tabs and mix on top</div></div>
  </div>
  {prof_html}

  <div class="scroll"><table>
  <thead><tr><th>Clock</th><th>Eat</th><th>Cal</th><th>Carb</th><th>Na (mg)</th></tr></thead>
  <tbody>{hrows_f}</tbody></table></div>
  <p class="sub">Highlighted rows carry a gel — spaced so no two land close together, with solid
  food in between. {e(sp['headroom'])}</p>
  <div class="callout"><b>On using the map.</b> {e(sp['landmarkCheck'])}</div>
  <p class="sub">{e(sp['sodiumNote'])}</p>
</section>"""

    # ---- beet juice protocol for this week
    bp = d.get("beetProtocol")
    bj = next((b for b in d["beetProducts"] if b.get("label")), None)
    bp_html = ""
    if bp and bj:
        L = bj["label"]
        nut = "".join(
            f'<tr><td>{e(k)}</td><td class="num nw"><b>{e(v)}</b></td></tr>'
            for k, v in [
                ("Calories", L["calories"]), ("Carbohydrate", f'{L["carbsG"]} g'),
                ("of which sugars", f'{L["sugarsG"]} g (0 g added)'),
                ("Fiber", f'{L["fiberG"]} g'), ("Protein", f'{L["proteinG"]} g'),
                ("Sodium", f'{L["sodiumMg"]} mg'),
                ("Potassium", f'{L["potassiumMg"]:,} mg ({L["potassiumDV"]})'),
                ("Iron", f'{L["ironMg"]} mg ({L["ironDV"]})'),
            ])
        bp_html = f"""
<section>
  <h2>Beet juice — this weekend's protocol<span class="n">{e(bp['plan'])}</span></h2>
  <p class="lede">This is the same Trader Joe's bottle flagged back on Jul 20 as
  "good at home, not for Trail Camp". {e(bj['note'])}</p>
  <div class="grid2">
    <div><h3>Per 450 ml bottle</h3>
      <div class="scroll"><table style="min-width:0"><tbody>{nut}</tbody></table></div>
      <p class="sub"><b>Contains:</b> {e(bj['perBottle'])}</p>
    </div>
    <div><h3>How to take it</h3>
      <ul class="clean">
        <li><b>Timing.</b> {e(bp['timing'])}</li>
        <li><b>With food.</b> {e(bp['takeWithFood'])}</li>
        <li><b>Friday is the test.</b> {e(bp['fridayIsTheTest'])}</li>
        <li><b>Counts as food.</b> {e(bp['countsTowardCarbs'])}</li>
      </ul>
    </div>
  </div>
  <div class="callout"><b>The decision rule.</b> {e(bp['decisionRule'])}</div>
  <div class="callout good"><b>Friday's result.</b> {e(bp['fridayResult'])}</div>
  <div class="callout"><b>One distinction worth keeping straight.</b> {e(bp['coffeeCaveat'])}</div>
  <div class="callout good"><b>One place Diamox and beet juice help each other.</b>
  {e(bp['diamoxSynergy'])}</div>
  <div class="callout"><b>Expectations.</b> {e(bp['expectations'])}</div>
  <p class="sub"><b>Harmless surprise worth knowing:</b> {e(bp['harmlessSurprise'])}</p>
</section>"""

    # ---- water carry vs demand, leg by leg
    wc = d.get("waterCarry")
    wc_html = ""
    if wc:
        cap = wc["totalCapacityL"]
        sip_lo, sip_hi = rng(hyd["sipTarget"]["mlPerHour"])
        lrows = ""
        for L in wc["legs"]:
            hrs = L["estHours"]
            need_lo, need_hi = sip_lo * hrs / 1000, sip_hi * hrs / 1000
            swt = sw_avg * hrs / 1000
            short = need_lo - cap
            crit = L.get("critical")
            refill = L["refillAvailable"]
            no_refill = refill.upper().startswith("NO")
            col = C["bad"] if (crit or no_refill) else (
                C["warn"] if refill.startswith("unknown") or refill.startswith("early") else C["primary"])
            lrows += (
                f'<tr{" class=hotrow" if crit else ""}>'
                f'<td><b>{e(L["leg"])}</b><div class="sub">{e(L["note"])}</div></td>'
                f'<td class="num nw">{hrs:g} h</td>'
                f'<td class="num nw">{swt:.1f} L</td>'
                f'<td class="num nw"><b>{need_lo:.1f}–{need_hi:.1f} L</b></td>'
                f'<td class="num nw" style="color:{col};font-weight:650">{e(refill)}</td>'
                f'</tr>')
        draw = "".join(f"<li>{e(x)}</li>" for x in wc["bladderDrawbacks"])
        frz = "".join(f"<li>{e(x)}</li>" for x in wc["freezeMitigations"])
        vess = "".join(
            f'<li><b>{e(v["item"])}</b> — {v["capacityL"]:g} L capacity, '
            f'usually filled to {v["usuallyFilledL"]:g} L'
            f'<div class="sub">{e(v["note"])}</div></li>'
            for v in wc["currentVessels"])
        crit_leg = next((L for L in wc["legs"] if L.get("critical")), None)
        crit_need = sip_lo * crit_leg["estHours"] / 1000 if crit_leg else 0
        wc_html = f"""
<section>
  <h2>Water capacity vs demand<span class="n">the arithmetic doesn't work yet</span></h2>
  <h3>What you carry today</h3>
  <ul class="clean">{vess}</ul>
  <div class="callout"><b>At {cap:g} L total capacity and a {sip_lo:.0f}–{sip_hi:.0f} ml/hr target,
  you are carrying about {cap*1000/sip_hi:.1f}–{cap*1000/sip_lo:.1f} hours of water.</b>
  Every hike in your plan is three to four times that long. This is not a "carry more" problem —
  {sip_lo/1000*12:.1f} L for a twelve-hour day would be {sip_lo/1000*12*2.2:.0f} lb of water alone.
  It is a refill problem, which is why the GRAYL and knowing your sources are load-bearing.</div>
  <div class="scroll"><table>
  <thead><tr><th>Leg</th><th>Est. time</th><th>Sweat loss<br>at {sw_avg:.0f} ml/hr</th>
  <th>Drink target</th><th>Refill?</th></tr></thead>
  <tbody>{lrows}</tbody></table></div>
  <div class="callout"><b>The one leg that decides this.</b>
  {e(crit_leg["leg"]) if crit_leg else ""} has no water at all, and needs roughly
  {crit_need:.1f} L at the low end of target. Your {cap:g} L reservoir covers just over half of
  that. Trail Camp pond is the last water before the switchbacks — so summit morning is the
  single stretch where capacity, not filtering, is the binding constraint.</div>
  <h3>Three things a bladder makes harder</h3>
  <ul class="clean">{draw}</ul>
  <div class="callout good"><b>Recommendation.</b> {e(wc["recommendation"])}</div>
  <h3>Freezing — the October problem</h3>
  <p class="lede">A frozen hose on summit morning means no drinking for hours on the highest,
  driest part of the trip. Cheap to prevent, miserable to discover.</p>
  <ul class="clean">{frz}</ul>
</section>"""

    # ---- Diamox trial protocol
    dx = d.get("diamoxTrial")
    dx_html = ""
    if dx:
        logs = "".join(f"<li>{e(x)}</li>" for x in dx["logThese"])
        qs = "".join(f"<li>{e(x)}</li>" for x in dx["questionsForDoctor"])
        dx_html = f"""
<section>
  <h2>Diamox trial<span class="n">{e(dx['status'])}</span></h2>
  <p class="lede">{e(dx['why'])}</p>
  <div class="callout"><b>When:</b> {e(dx['whenToTrial'])}</div>
  <h3>What to write down</h3>
  <ul class="clean">{logs}</ul>
  <div class="callout"><b>The test most people skip.</b> {e(dx['criticalTest'])}</div>
  <h3>Questions for the prescriber</h3>
  <ul class="clean">{qs}</ul>
  <p class="sub">Dose and timing come from your own prescription label and your doctor —
  nothing here changes that. This section is only about what to observe and what to ask.</p>
</section>"""

    zo = phys["zonesPercentHRR_CORRECT"]
    zrows = "".join(
        f'<tr><td><b>{z}</b></td><td class="num nw">{v[0]}–{v[1]} bpm</td>'
        f'<td class="num nw">{phys["zonesPercentMaxHR_OLD"][z][0]}–{phys["zonesPercentMaxHR_OLD"][z][1]} bpm</td></tr>'
        for z, v in zo.items())

    css = f"""
:root{{color-scheme:light}}
*{{box-sizing:border-box}}
body{{margin:0;background:{C['bg']};color:{C['ink']};
 font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 -webkit-text-size-adjust:100%}}
.wrap{{max-width:1080px;margin:0 auto;padding:20px 16px 72px}}
header.hero{{background:linear-gradient(135deg,#122436,#1f4d5e 58%,{C['primary']});
 color:#fff;border-radius:16px;padding:28px 24px;margin-bottom:20px}}
header.hero h1{{margin:0 0 4px;font-size:26px;letter-spacing:-.3px}}
header.hero p{{margin:0;opacity:.85;font-size:14px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:12px;margin:18px 0 8px}}
.tile{{background:{C['card']};border:1px solid {C['line']};border-radius:12px;padding:14px}}
.tl{{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:{C['ink3']};font-weight:650}}
.tv{{font-size:27px;font-weight:700;letter-spacing:-.6px;margin:3px 0 2px}}
.ts{{font-size:12px;color:{C['ink3']}}}
section{{background:{C['card']};border:1px solid {C['line']};border-radius:14px;
 padding:20px 22px;margin:16px 0}}
h2{{font-size:17px;margin:0 0 4px;letter-spacing:-.2px}}
h2 .n{{color:{C['ink3']};font-weight:500;font-size:13px;margin-left:8px}}
h3{{font-size:13px;text-transform:uppercase;letter-spacing:.7px;color:{C['ink3']};
 margin:22px 0 8px;font-weight:650}}
.lede{{color:{C['ink2']};font-size:14px;margin:0 0 14px;max-width:74ch}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}
@media(max-width:760px){{.grid2{{grid-template-columns:1fr}}}}
.chart{{width:100%;height:auto;display:block;overflow:visible}}
.tick{{font-size:11.5px;fill:{C['ink3']}}}
.axlab{{font-size:11px;fill:{C['ink3']};font-weight:650}}
.legend{{display:flex;flex-wrap:wrap;gap:14px;margin:2px 0 8px}}
.lg{{font-size:11.5px;color:{C['ink2']};display:flex;align-items:center;gap:5px}}
.lg i{{width:11px;height:11px;border-radius:3px;display:inline-block}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -6px;padding:0 6px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;min-width:640px}}
th{{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.6px;
 color:{C['ink3']};font-weight:650;padding:0 9px 7px;border-bottom:1.5px solid {C['line']};white-space:nowrap}}
td{{padding:9px;border-bottom:1px solid {C['line']};vertical-align:top}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
td.nw{{white-space:nowrap}}
tr.notrow td{{border-bottom:1px solid {C['line']};padding-top:0}}
tr.hotrow td{{background:#fff6f5}}
.note{{font-size:12.5px;color:{C['ink2']};background:{C['bg']};border-radius:7px;
 padding:8px 11px;border-left:2.5px solid {C['primary2']}}}
.sub{{font-size:12px;color:{C['ink3']};margin-top:2px}}
.sub2{{font-size:11.5px;color:{C['ink3']}}}
.chip{{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.5px;
 border:1px solid {C['line']};color:{C['ink3']};border-radius:20px;padding:1px 8px;
 margin-left:6px;font-weight:650;vertical-align:1px}}
.issue{{border-left:3.5px solid;background:{C['bg']};border-radius:0 8px 8px 0;
 padding:11px 14px;margin-bottom:9px}}
.ihead{{display:flex;align-items:center;gap:9px;flex-wrap:wrap;font-size:14px}}
.sev{{font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:700;
 border-radius:5px;padding:2px 7px}}
ul.clean{{list-style:none;padding:0;margin:0}}
ul.clean li{{padding:9px 0;border-bottom:1px solid {C['line']};font-size:14px}}
ul.clean li:last-child{{border:0}}
.phases{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:11px}}
.phase{{border:1px solid;border-left-width:3.5px;border-radius:0 9px 9px 0;padding:11px 13px;
 background:{C['bg']};font-size:14px}}
.pnum{{font-size:11px;text-transform:uppercase;letter-spacing:.6px;font-weight:700;margin-bottom:2px}}
.callout{{background:#fff8ec;border:1px solid {C['warn2']};border-radius:10px;
 padding:14px 16px;font-size:13.5px;color:{C['ink2']};margin:12px 0}}
.callout b{{color:{C['ink']}}}
.callout.good{{background:#eefaf6;border-color:{C['primary2']}}}
.pending{{border:1.5px dashed {C['line']};border-radius:10px;padding:18px;
 text-align:center;color:{C['ink3']};font-size:13.5px;background:{C['bg']}}}
.altrow{{display:flex;align-items:flex-start;gap:14px;padding:8px 0;
 border-bottom:1px solid {C['line']}}}
.altbar{{flex:0 0 148px;height:10px;background:{C['bg']};border:1px solid {C['line']};
 border-radius:6px;overflow:hidden;margin-top:5px}}
.altbar span{{display:block;height:100%;border-radius:6px}}
.altbar.ref span{{background:repeating-linear-gradient(90deg,{C['gold']} 0 5px,transparent 5px 9px)}}
.altmeta{{flex:1;font-size:13.5px;min-width:0}}
.symp{{font-size:12.5px;color:{C['warn']};background:#fff8ec;border-radius:6px;
 padding:5px 9px;margin-top:4px;border-left:2.5px solid {C['warn2']}}}
.step{{border-left:3.5px solid;background:{C['bg']};border-radius:0 9px 9px 0;
 padding:11px 14px;margin-bottom:9px}}
.step.hot{{background:#fffdf7;box-shadow:inset 0 0 0 1px {C['warn2']}}}
.swin{{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:{C['ink3']};
 font-weight:650;margin-bottom:2px}}
.kind{{font-weight:700;margin-right:8px}}
.stitle{{font-size:14.5px;font-weight:650;margin-bottom:3px}}
.tgt{{font-size:12.5px;color:{C['ink2']};background:{C['card']};border-radius:7px;
 padding:8px 11px;margin-top:6px;border-left:2.5px solid {C['primary2']}}}
ol.steps{{margin:6px 0 0;padding-left:20px;font-size:13px;color:{C['ink2']}}}
ol.steps li{{padding:2px 0}}
footer{{color:{C['ink3']};font-size:12px;text-align:center;padding:26px 10px 0;line-height:1.7}}
"""

    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Whitney Training Log — {e(m['athlete'])}</title>
<style>{css}</style>
</head><body><div class="wrap">

<header class="hero">
  <h1>Mt. Whitney Training Log</h1>
  <p>{e(m['athlete'])} · summit target {summit.strftime('%B %-d, %Y')} ·
     <b>{days_out} days out</b> · Whitney block from April 2026 · data through
     {e(short_date(m['logCoversTo']))}</p>
</header>

<div class="callout" style="margin:0 0 4px">Headline figures below cover the
<b>Whitney block only — April 2026 onward</b>, since that is when the Oct 2 permit was secured
and the preparation began. The twenty-month Garmin history sits further down, kept for the two
things it alone provides: the Rim to Rim capability benchmark and the stopped-time analysis,
which needs all 99 activities to mean anything.</div>

<div class="tiles">{tile_html}</div>

<section>
  <h2>Where you stand</h2>
  <p class="lede">Ten weeks of data, and the shape of it is unusually clear: the engine got
  measurably better while the fueling did not. Every hike since June 13 shows a fluid and calorie
  deficit, and the one time it really mattered — the San Jacinto descent — that deficit is what
  broke you, not the climb. The Mammoth weekend then added a third thing to watch: mild symptoms
  at 10,000–11,000 ft, now on their third appearance.</p>
  <div class="callout good"><b>The result the plan was built around:</b>
  you summited San Jacinto at 10,817 ft with no headache and no nausea, where a prior attempt
  turned back at 13,000 ft. Aerobic effect maxed at 5.0 and exercise load hit 557. Eight days
  later you spent a whole day above 10,000 ft in Little Lakes Valley with the best pacing
  discipline in the log. The engine is there.</div>
  <div class="callout"><b>The problem that is still open:</b>
  on San Jacinto you replaced roughly 1,900 mg of sodium against 7,000–9,000 mg lost, drank 4L
  against 9.5L of sweat loss, and ate about half the calories you burned. The clumsiness at
  10,500 ft is most likely that, not altitude. Whitney Day 2 is longer, and you sleep at
  12,000 ft before it — so Day 1 has to end with reserves left.</div>
</section>

<section>
  <h2>Climb load per hike<span class="n">the build is real</span></h2>
  {ch_ascent}
  <p class="sub">Whitney Day 1 is {m['whitneyProfile']['day1AscentFt']:,} ft of ascent.
  You matched it on June 6 and exceeded it on July 18.</p>

  <div class="callout"><b>Training hikes only.</b> The pace and heart-rate charts below exclude
  {e(excl)} — those were family outings where the pace, the stops and therefore the zones were set
  by staying together rather than by training intent. Mixing them into a trend would flatter the
  numbers and hide the real signal. Their elevation exposure and sweat rate still count and appear
  everywhere else.</div>
  <div class="grid2">
    <div><h3>Heart rate across training hikes</h3>{ch_hr}
      <p class="sub">Max HR trended down through June as pacing and the rest step improved.
      July 18 is higher on both counts — expected for 4,590 ft and 11 hours.</p></div>
    <div><h3>Moving pace</h3>{ch_pace}
      <p class="sub">Best moving pace came on June 27 (23:13) and held on July 11 (23:12)
      — with poles, boots and a 12 lb pack.<br>
      <b>Read Jun 20 with caution:</b> only a Strava moving time survived for that hike, and
      Strava counts stopped time differently than Garmin, so the point sits artificially slow.
      The real story of Jun 20 is the heart rate — 136 down to 126 on the identical route.</p></div>
  </div>

  <h3>Time in heart-rate zones</h3>
  {ch_zones}
  <p class="sub">The method label under each bar matters — the first three hikes were recorded on
  %max-HR zones, the Mammoth pair on the corrected %HRR zones, so they are not directly comparable.
  San Jacinto's alarming "58% in Zone 4" was an artifact of the wrong model; under %HRR its
  146 bpm average is low Zone 3. <b>The recalibration worked:</b> your Jul 25 and Jul 26
  screenshots show boundaries of 122–132 / 133–144 / 145–155 / 156–167 / &gt;167, which is exactly
  the %HRR set. And the pacing on those two days was the best in the log — 43% Zone 1 and 38%
  Zone 2 in Little Lakes Valley, with 47 seconds above threshold across five and three-quarter hours.</p>
</section>

<section>
  <h2>The fueling gap<span class="n">the one thing left to fix</span></h2>
  <div class="grid2">
    <div><h3>Sweat loss vs fluid taken in</h3>{ch_fluid}
      <p class="sub">Bars marked <b>n/a</b> mean intake was never written down for that hike —
      not that nothing was taken in. Four of five long hikes have a measured gap.</p></div>
    <div><h3>Calories burned vs eaten</h3>{ch_cal}
      <p class="sub">Calories eaten are reconstructed from the food lists you described
      (~400 on Jun 13, ~1,900 on Jul 18), so treat them as estimates. Burn figures are Garmin's.</p></div>
  </div>
  <div class="callout"><b>{e(hyd['sodiumFinding'])}</b></div>
  <p class="lede">{e(hyd['volumeFinding'])} {e(hyd['correction'])}</p>
  <h3>Target protocol</h3>
  <ul class="clean">
    <li><b>Sip</b> {e(hyd['sipTarget']['mlPer15min'])} ml every 15 minutes
        ({e(hyd['sipTarget']['mlPerHour'])} ml/hr) — not big gulps at rest stops.</li>
    <li><b>Electrolytes</b> {e(hyd['electrolyteTarget'])}, targeting
        {e(trail['sodiumPerHour'])} sodium per hour.</li>
    <li><b>Calories</b> {e(fp['targetCalPerHour'])} per hour. {e(fp['strategy'])}</li>
    <li><b>Keep the gels.</b> {e(fp['keepGelsReason'])}</li>
    <li><b>Swap out:</b> {e(', '.join(fp['swapOut']))}. <b>Swap in:</b> {e(', '.join(fp['swapIn']))}.</li>
    <li><b>{e(fp['timerReminder'])}</b> so fueling is on a clock, not on feel.</li>
  </ul>
  <p class="sub">{e(hyd['flagToDoctor'])} Worth raising alongside the reflux history —
  this dashboard is a training log, not medical guidance.</p>
</section>

<section>
  <h2>Hike log<span class="n">{len(hikes)} hikes · newest first</span></h2>
  <div class="scroll"><table>
  <thead><tr><th>Date</th><th>Hike</th><th>Mi</th><th>Ascent</th><th>Max elev</th>
  <th>Mov pace</th><th>HR avg/max</th><th>Aero</th><th>Load</th><th>Poles</th><th>Fluid gap</th></tr></thead>
  <tbody>{hrows}</tbody></table></div>
</section>

<section>
  <h2>Rucking progression<span class="n">12 lb pack throughout</span></h2>
  <div class="grid2">
    <div><h3>Pace</h3>{ch_ruck}</div>
    <div><h3>Average heart rate</h3>{ch_ruck_hr}</div>
  </div>
  <div class="callout good"><b>The adaptation signal:</b> on May 22 you went faster than May 21
  at an average heart rate of 106 versus 115 — more speed for less cardiac cost. That is the
  clearest single piece of evidence in the log that the base training worked.</div>
  <div class="scroll"><table>
  <thead><tr><th>Date</th><th>Pack lb</th><th>Mi</th><th>Mov pace</th><th>HR avg/max</th><th>Note</th></tr></thead>
  <tbody>{rrows}</tbody></table></div>
</section>

<section>
  <h2>Heart-rate zones, recalibrated</h2>
  <p class="lede">Zones were rebuilt on %HRR (resting {phys['restingHR']},
  estimated max {phys['estimatedMaxHR']}) after the July 19 review. The old %max-HR zones made
  ordinary aerobic hiking look like threshold work.</p>
  <div class="scroll"><table style="min-width:420px">
  <thead><tr><th>Zone</th><th>%HRR (use this)</th><th>%max HR (old)</th></tr></thead>
  <tbody>{zrows}</tbody></table></div>
  <p class="sub"><b>LTHR shown as {phys['lthrShown']}:</b> {e(phys['lthrNote'])}
  {e(phys['maxHRnote'])}</p>
</section>

<section>
  <h2>Nutrition<span class="n">targets ready, weekly log empty</span></h2>
  <p class="lede">{e(ng['note'])}</p>
  <div class="grid2">
    <div><h3>Daily carbohydrate at {lb} lb ({kg:.0f} kg)</h3>
      <div class="scroll"><table style="min-width:0">
      <thead><tr><th>Day type</th><th>Per kg</th><th>Your target</th></tr></thead>
      <tbody>{carb_rows}</tbody></table></div>
      <h3>Daily protein</h3>
      <p class="lede"><b>{prot_abs} per day</b> ({e(ng['proteinPerKgPerDay']['range'])} per kg).
      {e(ng['proteinPerKgPerDay']['note'])}</p>
    </div>
    <div><h3>On the trail, per hour</h3>
      <ul class="clean">
        <li><b>Carbs</b> {e(trail['carbsPerHour'])}</li>
        <li><b>Calories</b> {e(trail['calPerHour'])}</li>
        <li><b>Sodium</b> {e(trail['sodiumPerHour'])}</li>
      </ul>
      <h3>After the hike</h3>
      <p class="lede">{e(ng['postHike']['window']).capitalize()}: {e(ng['postHike']['target'])}.
      Safe foods: {e(ng['postHike']['safeFoods'])}.</p>
    </div>
  </div>
  <h3>What {lhd_lo:.0f}–{lhd_hi:.0f} g of carbohydrate actually looks like</h3>
  <p class="lede">{e(sd['note'])} This is one workable long-hike day, not a prescription —
  swap like for like freely.</p>
  <div class="scroll"><table style="min-width:0">
  <tbody>{day_rows}
  <tr><td><b>Day total</b></td><td class="num nw"
   style="color:{C['primary'] if in_band else C['warn']};font-weight:700">{day_total:.0f} g</td></tr>
  </tbody></table></div>
  <p class="sub">{"Lands inside the target band." if in_band else "Sits outside the target band — adjust portions."}
  The point is less the exact total than the realisation that this is roughly three times what
  you have been eating on hike days.</p>
  <div class="callout"><b>Where these two tables seem to disagree, and why they don't.</b>
  {e(trail['calPerHour'])} calories an hour across an eleven-hour day comes to more carbohydrate
  than the daily table allows. That is expected rather than a mistake: the daily figures describe
  a normal hard training day, and a San&nbsp;Jacinto-scale effort legitimately runs past them.
  Use the daily table for weekdays and the day before a hike; use the per-hour numbers as the
  operational target once you are actually walking.</div>
  <div class="callout"><b>What you have actually been doing.</b> On hikes where both numbers
  exist, you burned {burn_lo:.0f}–{burn_hi:.0f} calories an hour and took in
  {in_lo:.0f}–{in_hi:.0f} an hour, against a {e(trail['calPerHour'])} target. On July 25 that
  intake figure was zero across two and three-quarter hours. This gap, repeated, is what makes
  the descents so much worse than the climbs.</div>
  <div class="callout good"><b>One thing to be clear about:</b> across ten weeks the documented
  problem is consistently eating and drinking too little, never too much. Between now and
  October the goal is fuelling adequately, not weighing less — a calorie deficit during a peak
  training block would take away exactly what you need on summit day.</div>
  <p class="sub">Week-by-week targets are in the next section. Actuals get filled in as you
  report them, and each week's targets adjust off the previous week's hike.</p>
</section>

{pa_html}

{hist_html}

{ff_html}

{wcf_html}

{fx_html}

{wam_html}

{fuel_html}

{nw_html}

{bp_html}

{rt_html}

<section>
  <h2>Your sweat rate<span class="n">the most consistent number in the log</span></h2>
  {ch_sweat}
  <p class="sub">Green band is the {e(hyd['sipTarget']['mlPerHour'])} ml/hr drinking target.
  Garmin's sweat-loss figure is a model estimate, not a measurement — but its consistency is
  what makes it useful.</p>
  <div class="callout"><b>Across the {sw_n} hikes with data, your estimated sweat rate lands
  between {sw_lo:.0f} and {sw_hi:.0f} ml per hour, averaging {sw_avg:.0f}.</b>
  That is a genuinely high and genuinely stable number, and it converts the vague advice into
  arithmetic. Whitney Day 2 is realistically 10–12 hours, so you are looking at
  {sw_avg*10/1000:.1f}–{sw_avg*12/1000:.1f} litres of sweat loss on that day alone. You cannot
  carry that — which makes the GRAYL filter and knowing the refill points a load-bearing part
  of the plan, not a nice-to-have.</div>
  <p class="lede">At roughly {sw_avg:.0f} ml/hr and drinking {e(hyd['sipTarget']['mlPerHour'])} ml/hr,
  you will still finish a long day slightly down — which is normal and fine. The failure mode in
  your log is not being slightly down, it is being 3 to 5 litres down.</p>
</section>

<section>
  <h2>Pack weight as a share of bodyweight</h2>
  <p class="lede">At {lb} lb, the jump from your training load to Whitney Day 1 is the single
  biggest untested change in the plan. Seeing it as a percentage makes clear why it needs
  building up rather than discovering on the day.</p>
  <div class="scroll"><table style="min-width:0">
  <thead><tr><th>Pack</th><th>% of bodyweight</th><th></th></tr></thead>
  <tbody>{pack_rows}</tbody></table></div>
  <div class="callout">Coming down from Trail Camp you will be moving roughly
  {lb + 30} lb of combined bodyweight and pack through 6,200 ft of descent. Descending loads
  the knees at several times bodyweight per step, and poles offload 20–25% of that — which is
  the real reason the June 20 poles result matters far more on Whitney than it did on a
  2,400 ft local hike.</div>
</section>

<section>
  <h2>Weekday routine<span class="n">template — actuals not yet logged</span></h2>
  <div class="scroll"><table style="min-width:0">
  <thead><tr><th>Day</th><th>Session</th></tr></thead><tbody>{wrows}</tbody></table></div>
  <div class="callout">Running raises VO2 max faster than anything else available, but it is
  high-impact and you have back and hip-flexor history. Lower-risk equivalents that do the same
  job: incline treadmill at 10–15%, uphill hiking intervals, bike intervals. Stop at any knee or
  IT-band complaint.</div>
</section>

<section>
  <h2>Training phases</h2>
  <div class="phases">{prows}</div>
</section>

<section>
  <h2>Open issues<span class="n">{len(issues)} tracked</span></h2>
  {irows}
</section>

<section>
  <h2>Trail options</h2>
  <div class="scroll"><table>
  <thead><tr><th>Trail</th><th>Mi</th><th>Ascent</th><th>Max elev</th><th>Status</th></tr></thead>
  <tbody>{trows}</tbody></table></div>
</section>

{wc_html}

{dx_html}

<section>
  <h2>Gear &amp; supplements</h2>
  <div class="grid2">
    <div><h3>Gear</h3><ul class="clean">{grows}</ul>
      <p class="sub">{e(d.get("gearNote", ""))}</p></div>
    <div><h3>Supplements</h3><ul class="clean">{supp}</ul></div>
  </div>
</section>

<section>
  <h2>Altitude ladder<span class="n">everywhere you have been, tallest first</span></h2>
  <p class="lede">Bars in amber are exposures where something felt off. The two dashed
  reference bars are Whitney — and the important one is not the summit, it is Trail Camp,
  because that is where you <b>sleep</b> the night before summit day. It sits
  {tcamp - highest["maxElevFt"]:,} ft above anything you have ever stood on, and
  {tcamp - slept:,} ft above the highest you have ever slept.</p>
  {ref}
  {arows}
  <h3>Nights slept at altitude — the ladder that actually matters</h3>
  <p class="lede">Acclimatisation is driven far more by where you <b>sleep</b> than by the highest
  point you touch and come down from. Scaled here against Trail Camp rather than the summit.</p>
  {srows}
  <div class="callout"><b>Two altitude episodes, not three — revised down.</b>
  The clumsiness on the San Jacinto summit boulders (Jul 18) and the dizziness at the top of the
  Mammoth gondola (Jul 25) are the altitude-relevant ones, and both had you either underfuelled
  or hauled up 11,053 ft mechanically with no acclimatisation. The Little Lakes Valley discomfort
  (Jul 26) was mild, acclimatised and resolved into your best-paced hike on record. And the
  Whitney Portal headache leaves this column altogether — it is eyestrain from under-corrected
  reading glasses, not altitude, and 8,360 ft is low for altitude illness anyway. Still worth
  mentioning to your doctor alongside the Diamox plan, but the pattern is thinner than it looked.</div>
</section>

<section>
  <h2>The plan to October 2<span class="n">phases 4–6</span></h2>
  <p class="lede">Your three stated hikes are in here as given — Devils Slide this weekend,
  nothing on the 8th, San Gorgonio on the 15th. That is a good spine and I have not moved it.
  What I have added around it: progressive pack loading, one back-to-back weekend in September,
  and a staged Diamox trial that starts somewhere less demanding than a sixteen-mile hike.
  The extra night near 10,000 ft is now optional rather than urgent, since Mammoth already
  gave you two nights at {slept:,} ft.</p>
  {frows}
</section>

<section>
  <h2>The gaps worth closing<span class="n">what the data can't tell you yet</span></h2>
  <div class="callout"><b>1. Pack weight.</b> Every single one of the 15 logged sessions used a
  12 lb pack or none at all. Whitney Day 1 carries a tent, bag, pad, food, layers and water to
  12,000 ft — realistically around 30 lb. That is not a small adjustment: it changes heart rate,
  it changes pace, and it changes what the 6,200 ft descent does to your knees. Going from 12 lb
  to 30 lb on the day itself would be the largest untested variable of the trip.</div>
  <div class="callout good"><b>2. Sleeping at altitude — I had this wrong, and the correction
  is in your favour.</b> I previously wrote that you had never slept above 8,000 ft. You slept
  two nights at {slept:,} ft in Mammoth Lakes. That changes the picture in two ways. Your ladder
  to summit night is now {slept:,} ft achieved, then ~{cott:,} ft at Cottonwood on Sep 29, then
  {tcamp:,} ft at Trail Camp — a progression rather than a cold {tcamp - 8000:,} ft jump. And it
  reframes the Mammoth weekend: the Jul 26 hike at 10,934 ft was done <b>acclimatised</b>, which
  is very likely why it produced the best pacing in the log, while the unacclimatised gondola
  ride the day before produced dizziness. That is encouraging, because Whitney gives you the
  Cottonwood night for exactly this reason. A {step:,} ft step from Cottonwood to Trail Camp
  remains the real one to respect.</div>
  <div class="callout"><b>3. Consecutive days.</b> Ten hikes, never two in a row. Whitney Day 2
  starts on legs that already climbed 3,700 ft under load and on a night of thin, broken sleep —
  your own San Jacinto sleep score was 39 after a hard day at sea level. A big Saturday followed
  by a moderate Sunday in September tells you more about summit day than any single long hike can.</div>
</section>

<section>
  <h2>Data quality<span class="n">what to trust</span></h2>
  <ul class="clean">{dq}</ul>
</section>

<footer>
  Built from the May 20 – July 20, 2026 training log · generated {today.strftime('%B %-d, %Y')}<br>
  A training record, not medical advice. The symptom flags in this log — shoulder-blade pressure,
  coordination loss at altitude, a very salty sweat rate, recurring gut distress —
  are worth a conversation with your doctor before October 2.
</footer>

</div></body></html>"""

    OUT.write_text(doc)
    print(f"wrote {OUT}  ({len(doc):,} bytes)")
    print(f"  {len(hikes)} hikes, {len(rucks)} rucks, {len(issues)} open issues, {days_out} days to summit")


if __name__ == "__main__":
    build()
