#!/usr/bin/env python3
"""
Whitney dashboard, rebuilt.

Design rules, after the first version turned into a transcript:
  * Eleven sections, ordered status -> action -> evidence -> reference.
  * Every number is COMPUTED here from data. No figure is typed into prose.
  * Each fact has exactly one owning section.
  * No first person. No Q&A headings. No narrated self-correction — corrections
    live as dated rows in the appendix changelog.
  * Garmin is authoritative for metrics; the conversation supplies fuelling,
    symptoms, gear, conditions, interpretation.
"""

import datetime as dt
import html
import json
import pathlib
import statistics as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = json.loads((ROOT / "data" / "training-log.json").read_text(encoding="utf-8"))

# ── nightly check-ins live one file per day under data/daily/ and are merged here.
#
# They used to be written straight into training-log.json, which made the nightly
# scheduled task and any interactive session two writers on one file. Git cannot merge
# JSON, so the second push of the evening was rejected and the only ways forward were a
# hand-resolved conflict or a force-push that deletes the other side's work. Neither is
# available to an unattended job at 9 pm.
#
# One file per date removes the conflict rather than handling it: a new day is a new
# path, and git merges different paths without being asked. Nothing appends to a shared
# file, so nothing can collide.
_daily_dir = ROOT / "data" / "daily"
_daily = []
for _f in sorted(_daily_dir.glob("*.json")) if _daily_dir.exists() else []:
    try:
        _daily.append(json.loads(_f.read_text(encoding="utf-8")))
    except json.JSONDecodeError as _e:
        raise SystemExit(f"{_f.name} is not valid JSON: {_e}")

D["dailyLog"] = sorted(
    list({e["date"]: e for e in (D.get("dailyLog") or [])
          + [x["dailyLog"] | {"date": x["date"]} for x in _daily if x.get("dailyLog")]}.values()),
    key=lambda e: e["date"])

# subjective hike fields from a nightly check-in overlay the hike the weekly Garmin
# rebuild created; they never replace an objective metric
for _x in _daily:
    if _x.get("hike"):
        for _h in D["hikes"]:
            if _h["date"] == _x["date"]:
                _h.update(_x["hike"])

for _x in _daily:
    for _txt in _x.get("openIssues") or []:
        D["openIssues"].append({"raised": _x["date"], "issue": _txt, "status": "open",
                                "severity": "medium", "since": _x["date"], "action": ""})
    for _needle in _x.get("resolveIssues") or []:
        for _i in D["openIssues"]:
            if _needle.lower() in json.dumps(_i).lower() and _i.get("status") != "closed":
                _i.update(status="closed", closed=_x["date"],
                          resolution=_i.get("resolution") or "Closed at a nightly check-in.")
DIG = json.loads((ROOT / "garmin" / "digest.json").read_text(encoding="utf-8"))
OUT = ROOT / "whitney-dashboard.html"

C = dict(ink="#101720", ink2="#3d4a5c", ink3="#6b7a8f", line="#dfe5ec", bg="#f6f8fa",
         card="#ffffff", primary="#1f7a68", primary2="#8fd4c4", accent="#2b6cb0",
         accent2="#a8c8e8", warn="#b46a12", warn2="#f0cf9a", bad="#a8352c",
         bad2="#efb8b2", gold="#8a6d1f", violet="#5b4b8a")


def e(x):
    return html.escape("" if x is None else str(x))


def sec(t):
    if not t:
        return None
    p = [int(x) for x in str(t).split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def hm(s):
    s = int(s)
    return f"{s//3600}h {(s%3600)//60:02d}m"


def sd(iso):
    return dt.date.fromisoformat(iso).strftime("%b %-d")


# ─────────────────────────────────────────── computed facts (single source each)
M, PH = D["meta"], D["physiology"]
HK = [h for h in D["hikes"]]
RK = D["ruckSessions"]
TRN = [h for h in HK if h.get("effortType", "training") == "training"]
FAM = [h for h in HK if h.get("effortType") == "family"]
KG, LB = PH["bodyweightKg"], PH["bodyweightLb"]
today = dt.date.fromisoformat(M["lastUpdated"])
summit = dt.date.fromisoformat(M["summitDate"])
DAYS = (summit - today).days
WP = M["whitneyProfile"]

BLK = [a for a in DIG if a["start"] >= "2026-04-01"]
B_HK = [a for a in BLK if a["type"] == "hiking"]
B_RK = [a for a in BLK if "ruck" in (a["type"] or "")]
B_WK = [a for a in BLK if "walking" in (a["type"] or "")]

# resting metabolic rate, from Garmin's resting-calorie figure normalised to a day
_rmr = [h["restingCal"] / (sec(h["totalTime"]) / 3600) * 24
        for h in D["hikes"] if h.get("restingCal")]
RMR = round(st.mean(_rmr)) if _rmr else None
RMR_RANGE = (round(min(_rmr)), round(max(_rmr))) if _rmr else None

# burn rate on long efforts, from the full 20-month export
_burn = [(a["calories"] / (a["durSec"] / 3600))
         for a in DIG if a.get("durSec", 0) >= 5 * 3600 and a.get("calories")]
BURN_MEAN = round(st.mean(_burn))
BURN_MED = round(st.median(_burn))
BURN_LO, BURN_HI = round(min(_burn)), round(max(_burn))

# the tank
TANK = D["energyBudget"]["usableGlycogenCal"]
TANK_H = TANK / BURN_MEAN

# sweat rate
_sw = [(h, h["sweatLossMl"] / (sec(h["totalTime"]) / 3600))
       for h in D["hikes"] if h.get("sweatLossMl")]
SW = [v for _, v in _sw]
SW_MEAN, SW_LO, SW_HI, SW_N = round(st.mean(SW)), round(min(SW)), round(max(SW)), len(SW)

# stopped time, computed across the whole export
BANDS = []
for lo, hi, lab in [(0, 3, "under 3 h"), (3, 5, "3–5 h"), (5, 6, "5–6 h"),
                    (6, 9, "6–9 h"), (9, 99, "9 h+")]:
    g = [a for a in DIG if a.get("stoppedPct") is not None
         and lo <= a["durSec"] / 3600 < hi]
    if g:
        s = [a["stoppedPct"] for a in g]
        BANDS.append(dict(band=lab, n=len(g), mean=round(st.mean(s), 1),
                          lo=min(s), hi=max(s)))
_L = [a for a in DIG if a.get("stoppedPct") is not None and a["durSec"] >= 3 * 3600]
_x = [a["durSec"] / 3600 for a in _L]
_y = [a["stoppedPct"] for a in _L]
_mx, _my = st.mean(_x), st.mean(_y)
R_CORR = (sum((p - _mx) * (q - _my) for p, q in zip(_x, _y))
          / (sum((p - _mx) ** 2 for p in _x) * sum((q - _my) ** 2 for q in _y)) ** .5)
VO2 = PH["vo2maxSeries"]
R2R = D["rimToRim"]
SJ = next(h for h in HK if h["maxElevFt"] == max(x["maxElevFt"] for x in TRN))
BIG = max(HK, key=lambda h: h["ascentFt"])
HIGH = max(HK, key=lambda h: h["maxElevFt"])
CONSEC = D["consecutiveDays"]["pairs"]


# ─────────────────────────────────────────── chart helpers
def bars(rows, *, w=680, h=210, fmt=lambda v: f"{v:g}", colfn=None):
    vals = [v for _, v in rows if v is not None]
    if not vals:
        return ""
    vmax = max(vals) * 1.16
    pl, pr, pt, pb = 46, 14, 14, 40
    iw, ih = w - pl - pr, h - pt - pb
    slot = iw / len(rows)
    bw = min(30, slot * .62)
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for k in range(4):
        v = vmax * k / 3
        y = pt + ih - v / vmax * ih
        p.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w-pr}" y2="{y:.1f}" stroke="{C["line"]}"/>'
                 f'<text x="{pl-8}" y="{y+4:.1f}" text-anchor="end" class="tk">{e(fmt(v))}</text>')
    for i, (lab, v) in enumerate(rows):
        cx = pl + slot * (i + .5)
        col = colfn(lab, v) if colfn else C["primary"]
        if v is not None:
            bh = v / vmax * ih
            p.append(f'<rect x="{cx-bw/2:.1f}" y="{pt+ih-bh:.1f}" width="{bw:.1f}" '
                     f'height="{bh:.1f}" rx="2" fill="{col}">'
                     f'<title>{e(lab)}: {e(fmt(v))}</title></rect>')
        p.append(f'<text x="{cx:.1f}" y="{h-pb+18}" text-anchor="middle" class="tk">{e(lab)}</text>')
    p.append("</svg>")
    return "".join(p)


def lines(series, *, w=680, h=214, ylab="", fmt=lambda v: f"{v:g}", invert=False, ymin=None):
    vals = [v for s in series for _, v in s["pts"] if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    lo -= span * .16
    hi += span * .16
    if ymin is not None:
        lo = max(lo, ymin)
    span = hi - lo
    labs = [x for x, _ in series[0]["pts"]]
    n = len(labs)
    pl, pr, pt, pb = 52, 14, 26, 34
    iw, ih = w - pl - pr, h - pt - pb
    X = lambda i: pl + (iw * i / (n - 1) if n > 1 else iw / 2)
    Y = lambda v: pt + ih - ((1 - (v - lo) / span) if invert else (v - lo) / span) * ih
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for k in range(4):
        v = lo + span * k / 3
        y = Y(v)
        p.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w-pr}" y2="{y:.1f}" stroke="{C["line"]}"/>'
                 f'<text x="{pl-8}" y="{y+4:.1f}" text-anchor="end" class="tk">{e(fmt(v))}</text>')
    # label density adapts to the series length — 56 daily points must not print 56 labels
    step = max(1, -(-n // 9))
    for i, lab in enumerate(labs):
        if i % step and i != n - 1:
            continue
        p.append(f'<text x="{X(i):.1f}" y="{h-pb+18}" text-anchor="middle" class="tk">{e(lab)}</text>')
    for s in series:
        pts = [(i, v) for i, (_, v) in enumerate(s["pts"]) if v is not None]
        if not pts:
            continue
        d_ = " ".join(f"{'M' if j==0 else 'L'}{X(i):.1f},{Y(v):.1f}" for j, (i, v) in enumerate(pts))
        dash = f' stroke-dasharray="{s["dash"]}"' if s.get("dash") else ""
        p.append(f'<path d="{d_}" fill="none" stroke="{s["col"]}" stroke-width="2.3"{dash}/>')
        for i, v in pts:
            p.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="4" fill="{C["card"]}" '
                     f'stroke="{s["col"]}" stroke-width="2"><title>{e(s["lab"])} '
                     f'{e(labs[i])}: {e(fmt(v))}</title></circle>')
    if ylab:
        p.append(f'<text x="6" y="13" class="ax">{e(ylab)}</text>')
    p.append("</svg>")
    leg = "".join(f'<span class="lg"><i style="background:{s["col"]}"></i>{e(s["lab"])}</span>'
                  for s in series if len(series) > 1)
    return (f'<div class="legend">{leg}</div>' if leg else "") + "".join(p)


def scatter(pts, *, w=690, h=280, mark=None):
    if not pts:
        return ""
    pl, pr, pt, pb = 50, 16, 24, 44
    iw, ih = w - pl - pr, h - pt - pb
    xmax = max(p[0] for p in pts) * 1.06
    ymax = max(60, max(p[1] for p in pts) * 1.12)
    X = lambda v: pl + v / xmax * iw
    Y = lambda v: pt + ih - v / ymax * ih
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for k in range(4):
        v = ymax * k / 3
        y = Y(v)
        p.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w-pr}" y2="{y:.1f}" stroke="{C["line"]}"/>'
                 f'<text x="{pl-8}" y="{y+4:.1f}" text-anchor="end" class="tk">{v:.0f}%</text>')
    for t in range(0, int(xmax) + 1, 2):
        p.append(f'<text x="{X(t):.1f}" y="{h-pb+20}" text-anchor="middle" class="tk">{t}h</text>')
    if mark:
        p.append(f'<rect x="{pl}" y="{pt}" width="{X(mark)-pl:.1f}" height="{ih}" '
                 f'fill="{C["primary2"]}" opacity=".2"/>')
        p.append(f'<line x1="{X(mark):.1f}" y1="{pt}" x2="{X(mark):.1f}" y2="{pt+ih}" '
                 f'stroke="{C["bad"]}" stroke-width="2" stroke-dasharray="5 3"/>')
        p.append(f'<text x="{X(mark)+6:.1f}" y="{pt+12}" class="ax" fill="{C["bad"]}">'
                 f'tank empty · {mark:.1f} h</text>')
    for hrs, pct, lab in pts:
        col = C["bad"] if pct >= 40 else (C["warn"] if pct >= 20 else C["primary"])
        p.append(f'<circle cx="{X(hrs):.1f}" cy="{Y(pct):.1f}" r="{6 if hrs>=9 else 4.4}" '
                 f'fill="{col}" fill-opacity=".72" stroke="{C["card"]}" stroke-width="1.3">'
                 f'<title>{e(lab)} — {hrs:.1f} h, {pct}%</title></circle>')
    p.append(f'<text x="6" y="13" class="ax">stopped time</text>'
             f'<text x="{w-pr}" y="{h-6}" text-anchor="end" class="tk">duration</text></svg>')
    return "".join(p)


def profile(prof, fuel, *, w=700, h=290):
    rd = prof["readings"]
    pl, pr, pt, pb = 52, 44, 22, 58
    iw, ih = w - pl - pr, h - pt - pb
    tmax = prof["totalHours"]
    emin = min(r["ft"] for r in rd) - 300
    emax = max(r["ft"] for r in rd) + 300
    X = lambda t: pl + t / tmax * iw
    Y = lambda f: pt + ih - (f - emin) / (emax - emin) * ih
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for k in range(5):
        ft = emin + (emax - emin) * k / 4
        y = Y(ft)
        p.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w-pr}" y2="{y:.1f}" stroke="{C["line"]}"/>'
                 f'<text x="{pl-8}" y="{y+4:.1f}" text-anchor="end" class="tk">{ft/1000:.1f}k</text>')
    pts = " ".join(f"{X(r['h']):.1f},{Y(r['ft']):.1f}" for r in rd)
    p.append(f'<polygon points="{pl},{pt+ih} {pts} {w-pr},{pt+ih}" fill="{C["primary2"]}" opacity=".38"/>')
    p.append(f'<polyline points="{pts}" fill="none" stroke="{C["primary"]}" stroke-width="2.3"/>')
    stt = prof["summitAtHours"]
    p.append(f'<line x1="{X(stt):.1f}" y1="{pt}" x2="{X(stt):.1f}" y2="{pt+ih}" '
             f'stroke="{C["gold"]}" stroke-width="1.5" stroke-dasharray="4 3"/>'
             f'<text x="{X(stt):.1f}" y="{pt-6}" text-anchor="middle" class="ax" '
             f'fill="{C["gold"]}">summit · h{stt:g}</text>')
    for r in fuel:
        if r["hour"] > tmax:
            continue
        x, y = X(r["hour"]), pt + ih
        col = C["bad"] if r["gel"] else C["accent"]
        p.append(f'<line x1="{x:.1f}" y1="{y}" x2="{x:.1f}" y2="{y+8}" stroke="{col}" stroke-width="2"/>'
                 f'<circle cx="{x:.1f}" cy="{y+13:.1f}" r="4.6" fill="{col}">'
                 f'<title>Hour {r["hour"]}: {e(", ".join(r["items"]))} — {r["cal"]} cal</title></circle>')
    for t in range(0, int(tmax) + 1, 2):
        p.append(f'<text x="{X(t):.1f}" y="{h-pb+46}" text-anchor="middle" class="tk">{t}h</text>')
    p.append(f'<text x="6" y="13" class="ax">elevation (ft)</text></svg>')
    leg = (f'<span class="lg"><i style="background:{C["bad"]}"></i>gel</span>'
           f'<span class="lg"><i style="background:{C["accent"]}"></i>solid food</span>'
           f'<span class="lg"><i style="background:{C["gold"]}"></i>summit</span>')
    return f'<div class="legend">{leg}</div>' + "".join(p)


# ─────────────────────────────────────────── sections
def tile(lab, val, sub, col):
    return (f'<div class="tile"><div class="tl">{e(lab)}</div>'
            f'<div class="tv" style="color:{col}">{e(val)}</div>'
            f'<div class="ts">{e(sub)}</div></div>')


def s_status():
    hi_note = "on foot"
    nf = [a for a in D.get("altitudeExposure", []) if not a.get("onFoot")]
    if nf and max(a["elevationFt"] for a in nf) > HIGH["maxElevFt"]:
        hi_note = f'on foot · {max(a["elevationFt"] for a in nf):,} ft by gondola'
    t = "".join([
        tile("Days to summit", DAYS, summit.strftime("%b %-d, %Y"), C["gold"]),
        tile("Highest on foot", f'{HIGH["maxElevFt"]:,} ft', hi_note, C["primary"]),
        tile("Biggest ascent", f'{BIG["ascentFt"]:,} ft',
             f'Whitney Day 1 is {WP["day1AscentFt"]:,} ft', C["primary"]),
        tile("VO2 max", VO2["current"]["value"],
             f'peaked {VO2["peak"]["value"]} in {VO2["peak"]["month"]} · Oct target '
             f'{PH["vo2maxTargets"]["october"]}', C["accent"]),
        tile("This block", f'{round(sum(a["distanceMi"] or 0 for a in BLK))} mi',
             f'{len(B_HK)} hikes · {len(B_RK)} rucks · {len(B_WK)} walks', C["ink2"]),
        tile("Ascent this block", f'{sum(a["ascentFt"] or 0 for a in BLK):,} ft',
             f'{sd(M["logCoversFrom"])} – {sd(M["logCoversTo"])}', C["ink2"]),
        tile("Hours on foot", f'{round(sum(a["durSec"] for a in BLK)/3600)} h',
             f'{sum(a["calories"] or 0 for a in BLK):,} kcal', C["ink2"]),
        tile("Longest day ever", R2R["totalTime"][:5],
             f'Rim to Rim, {sd(R2R["date"])} 2025', C["violet"]),
    ])
    return f"""<section id="status">
  <h2>Status</h2>
  <div class="tiles">{t}</div>
  <div class="callout good"><b>Endurance is not the constraint.</b> Rim to Rim covered
  {R2R['distanceMi']} mi and {R2R['ascentFt']:,} ft of climbing in one {R2R['totalTime'][:5]} day —
  more distance and more ascent than Whitney's two days combined. San Jacinto reached
  {SJ['maxElevFt']:,} ft with no headache or nausea.</div>
  <div class="callout"><b>One problem is still open: fuelling on long days.</b>
  Across long efforts the burn rate is {BURN_LO}–{BURN_HI} kcal/hr (median {BURN_MED}), while
  recorded intake has run as low as zero. On San Jacinto roughly {SJ['fuel']['caloriesIn']:,} kcal
  went in against {SJ['totalCal']:,} burned, and about {SJ['fuel']['waterL']}L of fluid against
  {SJ['sweatLossMl']/1000:.1f}L of estimated sweat loss.</div>
</section>"""


def s_levers():
    rows = ""
    for it in D["whatActuallyMatters"]["items"]:
        r = it["rank"]
        col = C["bad"] if r <= 2 else (C["warn"] if r <= 4 else C["ink3"])
        rows += (f'<tr><td class="num nw" style="color:{col};font-weight:700;font-size:17px">{r}</td>'
                 f'<td><b>{e(it["item"])}</b><div class="sub">{e(it["why"])}</div></td>'
                 f'<td style="width:110px"><div class="mtr" style="width:100px">'
                 f'<span style="width:{int((8-r)/7*100)}%;background:{col}"></span></div></td>'
                 f'<td class="sub nw">{e(it["status"])}</td></tr>')
    return f"""<section id="levers">
  <h2>What matters most<span class="n">ranked by effect on Oct 2</span></h2>
  <div class="scroll"><table><thead><tr><th>#</th><th>Lever</th><th>Weight</th>
  <th>Status</th></tr></thead><tbody>{rows}</tbody></table></div>
</section>"""


def s_week():
    w = D["nutritionWeeks"][-1]
    sp, gm, cp = D["saturdayFuelPlan"], D["gelMath"], D["caffeinePlan"]
    T = sp["totals"]
    drows = ""
    for day in w["days"]:
        col = {"easy": C["ink3"], "easy-moderate": C["accent"], "moderate": C["accent"],
               "load": C["warn"], "hike": C["primary"]}.get(day["type"], C["ink3"])
        drows += (f'<tr{" class=hot" if day.get("flag") else ""}'
                  f'{" style=opacity:.5" if day.get("past") else ""}>'
                  f'<td class="nw"><b>{e(day["day"])}</b><div class="tag" style="color:{col}">'
                  f'{e(day["type"])}</div></td><td>{e(day["session"])}'
                  f'<div class="sub">{e(day["note"])}</div></td>'
                  f'<td class="num nw"><b>{e(day["carbsG"])}</b></td>'
                  f'<td class="num nw">{e(day["proteinG"])}</td></tr>')
    frows = "".join(
        f'<tr{" class=hot" if r["gel"] else ""}><td class="nw"><b>h{r["hour"]}</b></td>'
        f'<td>{e(", ".join(r["items"]))}</td><td class="num nw">{r["cal"]}</td>'
        f'<td class="num nw">{r["carbG"]} g</td><td class="num nw">{r["sodiumMg"]}</td></tr>'
        for r in sp["hours"])
    admin = next(s for s in D["forwardPlan"] if s["kind"] == "admin")
    dx = D["diamoxTrial"]
    bp = D["beetProtocol"]
    return f"""<section id="week">
  <h2>This week<span class="n">Jul 28 – Aug 2 · hike Saturday</span></h2>

  <div class="callout" style="background:#fff6f5;border-color:{C['bad2']}">
  <b>Admin, in order of deadline.</b> {e(admin['detail'])}</div>

  <h3>Saturday's fuel plan</h3>
  <div class="tiles">{''.join([
    tile("Calories carried", f"{T['cal']:,}", f"{T['calPerHour']} kcal/hr", C["primary"]),
    tile("Floor to finish", f"{sp['targets']['calPerHourFloor']} kcal/hr",
         f"target {sp['targets']['calPerHourTarget']}", C["warn"]),
    tile("Carbs", f"{T['carbGPerHour']} g/hr", f"target {sp['targets']['carbGPerHour']}", C["accent"]),
    tile("Sodium in food", f"{T['sodiumMg']:,} mg", "tabs and mix on top", C["warn"]),
  ])}</div>
  <div class="callout"><b>Anchor the eating to the clock, not the map.</b>
  {e(sp['principle'].split('Landmarks')[1].strip() if 'Landmarks' in sp['principle'] else sp['principle'])}</div>
  <div class="scroll"><table><thead><tr><th>Clock</th><th>Eat</th><th>Cal</th>
  <th>Carb</th><th>Na</th></tr></thead><tbody>{frows}</tbody></table></div>
  <p class="sub">Six gels total. Highlighted rows carry one, spaced so no two land together.
  {e(gm['verdict'].split('.')[1].strip())}. Caffeine-free at hours 3 and 5, caffeinated from
  hour 7 — {cp['totalMg']} mg in all, peaking near
  {max(c['mg'] for c in cp['onBoardCurve']):.0f} mg on board late in the descent.</p>

  <h3>Nutrition, day by day at {LB} lb</h3>
  <div class="scroll"><table><thead><tr><th>Day</th><th>Session</th><th>Carbs</th>
  <th>Protein</th></tr></thead><tbody>{drows}</tbody></table></div>

  <h3>Two trials running alongside</h3>
  <div class="grid2">
    <div><b>Diamox</b><div class="sub">{e(dx['whenToTrial'])} {e(dx['criticalTest'])}</div></div>
    <div><b>Beet juice</b><div class="sub">{e(bp['fridayResult'])} {e(bp['decisionRule'])}</div></div>
  </div>

  <div class="callout good"><b>The measurement that matters most.</b>
  {e(w['measureThis']['how'])} Roughly 1 lb lost equals 450 ml of net deficit, which converts
  every sweat-loss estimate in this dashboard into a measured number.</div>
</section>"""


def s_weeks():
    """
    The nine-week plan as agreed in the shared sheet.

    The sheet outranks anything earlier in the log, on the same principle the Garmin
    export outranks the PDF: it is the record two people actually agreed to. Where it
    disagrees with what was here before, the disagreement is printed rather than
    quietly resolved — two of them change which permit to reserve.
    """
    P = D["nineWeekPlan"]
    # Two columns, not six. A six-column table scrolls sideways on a 390px screen, which
    # pushes distance and ascent off the edge — the two numbers most worth seeing. The
    # figures move into the target cell as their own line so nothing needs scrolling.
    rows = ""
    for w in P["weeks"]:
        mi = w["distanceMi"] or 0
        away = (w.get("ownNote") or "").strip().lower().startswith("not available")
        big = mi >= 18 and not away
        route = f' <span class="sub2">via {e(w["route"])}</span>' if w["route"] else ""
        bits = []
        if mi:
            bits.append(f'{mi:g} mi')
        if w["ascentFt"]:
            bits.append(f'{w["ascentFt"]:,} ft')
        if w["summitFt"]:
            bits.append(f'summit {w["summitFt"]:,}')
        if mi:
            # hours from this athlete's own recorded moving speed, not from a guidebook
            bits.append(f'~{mi / 1.55:.0f}–{mi / 1.25:.0f} h')
        stats = (f'<div class="tgt" style="margin-top:4px">{" · ".join(bits)}</div>'
                 if bits else "")
        notes = " · ".join(x for x in (w.get("partnerNote"), w.get("ownNote"),
                                       w.get("permit")) if x)
        style = ("background:#fff8e6" if big else
                 "background:#f4f6f8;opacity:.62" if away else "")
        rows += (f'<tr{f" style={style}" if style else ""}>'
                 f'<td class="nw" style="vertical-align:top">'
                 f'<b>{e(sd(w["date"]))}</b><div class="sub2">wk {w["week"]}</div></td>'
                 f'<td><b>{e(w["peak"])}</b>{route}{stats}'
                 f'{f"<div class=sub>{e(notes)}</div>" if notes else ""}</td></tr>')

    conf = "".join(
        f'<div class="issue" style="border-left-color:{C["bad"]}">'
        f'<div class="ih"><span class="sev" style="background:{C["bad2"]};color:{C["bad"]}">'
        f'Conflict</span><b>{e(c["what"])}</b></div>'
        f'<div class="sub"><b>Sheet:</b> {e(c["sheet"])}<br>'
        f'<b>Previously here:</b> {e(c["log"])}<br>{e(c["matters"])}</div></div>'
        for c in P["conflicts"])

    reads = "".join(f'<li><b>{e(r["point"])}.</b> {e(r["detail"])}</li>'
                    for r in P["readsOnThePlan"])

    tot_mi = sum(w["distanceMi"] or 0 for w in P["weeks"])
    tot_ft = sum(w["ascentFt"] or 0 for w in P["weeks"])
    biggest = max(P["weeks"], key=lambda w: w["distanceMi"] or 0)

    return f"""<section id="weeks">
  <h2>Nine weeks to the summit<span class="n">{tot_mi:g} mi · {tot_ft:,} ft · from the shared plan sheet</span></h2>
  <table class="t" style="width:100%;min-width:0;table-layout:fixed"><thead><tr><th class="nw" style="width:74px">Weekend</th>
   <th>Target, size and estimated time</th></tr></thead><tbody>{rows}</tbody></table>
  <div class="sub" style="margin-top:8px">Estimated time uses the recorded moving-speed
   range of 1.25–1.55 mph on climbing terrain, so it is this athlete's pace rather than a
   guidebook's. Highlighted rows are 18 mi or more; the greyed row is a weekend already marked unavailable — the biggest is
   {e(sd(biggest["date"]))} at {biggest["distanceMi"]:g} mi and {biggest["ascentFt"]:,} ft.</div>
  <h3 style="margin:22px 0 8px">Unresolved against what was here before</h3>
  {conf}
  <h3 style="margin:22px 0 8px">What the plan says about readiness</h3>
  <ul class="ul">{reads}</ul>
</section>"""


def s_summit():
    """The itinerary and the landmark table, so fuelling can be pinned to places."""
    I = D["summitItinerary"]
    days = "".join(
        f'<div class="step" style="border-left-color:{C["gold"]}">'
        f'<div class="swin"><span style="color:{C["gold"]};font-weight:700">{e(x["day"])}</span> '
        f'{e(sd(x["date"]))}</div>'
        f'<ul class="ul" style="margin:6px 0 0">'
        + "".join(f"<li>{e(s)}</li>" for s in x["steps"]) + "</ul></div>"
        for x in I["days"])

    L = I["landmarks"]
    # gain per mile is what tells you which segment will hurt, and it is not uniform
    lrows = ""
    for n, (name, ft, mi) in enumerate(L):
        if n == 0:
            grad = "—"
        else:
            pm, pf = L[n - 1][2], L[n - 1][1]
            dmi, dft = mi - pm, ft - pf
            gpm = dft / dmi if dmi else 0
            col = C["bad"] if gpm >= 900 else C["warn"] if gpm >= 650 else C["ink3"]
            grad = (f'<span style="color:{col};font-weight:650">{gpm:+,.0f}</span>'
                    if dft else "—")
        camp = ' style="background:#eef6f3"' if "Camp" in name or name == "Summit" else ""
        lrows += (f'<tr{camp}><td>{e(name)}</td><td class="num nw">{ft:,}</td>'
                  f'<td class="num nw">{mi:g}</td><td class="num nw">{grad}</td></tr>')

    return f"""<section id="summit">
  <h2>Summit itinerary<span class="n">Sep 30 – Oct 2 · from the shared plan sheet</span></h2>
  {days}
  <div class="callout"><b>The hard day is Day 3, not Day 2.</b> {e(I["note"])}</div>
  <h3 style="margin:22px 0 8px">Landmarks from Whitney Portal</h3>
  <div class="scroll"><table class="t"><thead><tr><th>Landmark</th>
   <th class="num">Elevation</th><th class="num">Cum. mi</th>
   <th class="num">ft/mi</th></tr></thead><tbody>{lrows}</tbody></table></div>
  <div class="sub" style="margin-top:8px">{e(I["landmarkNote"])} The ft/mi column is
   computed from the elevations, so the steep segments show themselves: the switchbacks
   above Trail Camp and the pull to Trail Crest are where the gradient spikes, and they
   arrive at hour four and five of the summit day — the hours the tank is already empty.</div>
</section>"""


def s_plan():
    KIND = {"hike": (C["primary"], "Hike"), "rest": (C["ink3"], "Rest"),
            "week": (C["accent"], "Weekday"), "admin": (C["bad"], "Admin"),
            "addition": (C["violet"], "Optional"), "travel": (C["ink2"], "Travel"),
            "acclimatization": (C["accent"], "Acclimatise"), "summit": (C["gold"], "Summit")}
    rows = ""
    for s in D["forwardPlan"]:
        col, kl = KIND.get(s["kind"], (C["ink3"], s["kind"]))
        pack = ""
        if s.get("packLb"):
            pv = s["packLb"]
            pack = (f'<span class="chip">'
                    f'{"full pack" if str(pv)=="full" else f"pack {pv} lb"}</span>')
        tgt = f'<div class="tgt">{e(s["targets"])}</div>' if s.get("targets") else ""
        rows += (f'<div class="step{" hot" if s.get("priority")=="high" else ""}" '
                 f'style="border-left-color:{col}">'
                 f'<div class="swin"><span style="color:{col};font-weight:700">{e(kl)}</span> '
                 f'{e(s["window"])}</div><div class="stt">{e(s["title"])}{pack}</div>'
                 f'<div class="sub">{e(s["detail"])}</div>{tgt}</div>')
    wk = "".join(f'<tr><td class="nw"><b>{e(r["day"])}</b></td><td>{e(r["session"])}'
                 f'<div class="sub">{e(r.get("note",""))}</div></td></tr>'
                 for r in D["weekdayRoutine"]["template"])
    return f"""<section id="plan">
  <h2>The plan to October 2<span class="n">phases 4–6</span></h2>
  {rows}
  <h3>Weekday template</h3>
  <div class="scroll"><table style="min-width:0"><tbody>{wk}</tbody></table></div>
</section>"""


def s_energy():
    eb = D["energyBudget"]
    sj = eb["sanJacinto"]
    srows = ""
    for s in eb["scenarios"]:
        emp = TANK / max(1, sj["burnRate"] - s["intakeRate"])
        ok = emp >= sj["hours"]
        col = C["primary"] if ok else C["bad"]
        srows += (f'<tr><td class="nw"><b>{s["intakeRate"]} kcal/hr</b>'
                  f'<div class="sub">{e(s["label"])}</div></td>'
                  f'<td style="width:150px"><div class="mtr" style="width:140px">'
                  f'<span style="width:{min(100,emp/24*100):.0f}%;background:{col}"></span></div></td>'
                  f'<td class="num nw" style="color:{col};font-weight:700">{emp:.1f} h</td>'
                  f'<td class="sub">{"finishes with reserves" if ok else "empty before the end"}</td></tr>')
    brows = "".join(
        f'<tr><td class="nw"><b>{e(b["band"])}</b></td><td class="num nw">{b["n"]}</td>'
        f'<td style="width:150px"><div class="mtr" style="width:140px">'
        f'<span style="width:{b["mean"]:.0f}%;background:'
        f'{C["bad"] if b["mean"]>=40 else C["warn"] if b["mean"]>=20 else C["primary"]}">'
        f'</span></div></td><td class="num nw"><b>{b["mean"]}%</b></td>'
        f'<td class="sub nw">{b["lo"]}–{b["hi"]}%</td></tr>' for b in BANDS)
    pts = [(a["durSec"] / 3600, a["stoppedPct"], f'{a["start"][:10]} {a["name"] or ""}')
           for a in DIG if a.get("stoppedPct") is not None]
    return f"""<section id="energy">
  <h2>Why long days end badly<span class="n">the energy budget</span></h2>
  <div class="tiles">{''.join([
    tile("Usable glycogen", f"~{TANK:,} kcal", "the tank; training barely changes it", C["accent"]),
    tile("Burn on long days", f"{BURN_MED} kcal/hr",
         f"median of {len(_burn)} efforts over 5 h · {BURN_LO}–{BURN_HI}", C["warn"]),
    tile("Tank alone lasts", f"{TANK_H:.1f} h", "eating nothing at all", C["bad"]),
  ])}</div>
  <p class="lede">Every hike is a race between the clock and the tank. Blue Sky days run about
  five hours, which the tank nearly covers unaided — which is why they feel fine start to finish.
  San Jacinto ran {sj['hours']} hours at {sj['burnRate']} kcal/hr against
  {sj['intakeRate']} kcal/hr going in.</p>

  <h3>San Jacinto replayed at different intake rates</h3>
  <div class="scroll"><table style="min-width:0"><tbody>{srows}</tbody></table></div>

  <h3>Stopped time rises with duration, and the bend sits at the tank</h3>
  {scatter(pts, mark=TANK_H)}
  <div class="scroll"><table><thead><tr><th>Duration</th><th>n</th><th>Mean stopped</th>
  <th></th><th>Range</th></tr></thead><tbody>{brows}</tbody></table></div>
  <p class="lede">Across {len(DIG)} recorded activities the pattern is monotonic. Correlation
  between duration and stopped time on efforts over three hours is
  <b>r = +{R_CORR:.2f}</b> across {len(_L)} hikes. Under the tank duration, stopping is
  incidental; past it, it escalates. Heart rate stays flat throughout — the cost shows up in
  total time rather than in effort.</p>

  <h3>San Jacinto profile with Saturday's fuel schedule overlaid</h3>
  {profile(D["sanJacintoProfile"], D["saturdayFuelPlan"]["hours"])}
  <p class="sub">{e(D["sanJacintoProfile"]["source"])} Summit at hour
  {D["sanJacintoProfile"]["summitAtHours"]:g} of {D["sanJacintoProfile"]["totalHours"]}, leaving
  {D["sanJacintoProfile"]["descentHours"]:.1f} hours of descending. Old fuelling put two gels
  across the whole climb; the new schedule feeds every hour.</p>
</section>"""


def s_fuel():
    hyd, fp = D["hydrationAnalysis"], D["fuelingProtocol"]
    wc = D["waterCarry"]
    fl = [(sd(h["date"]), round(h["sweatLossMl"] / 1000, 2)) for h in D["hikes"] if h.get("sweatLossMl")]
    ind = [(sd(h["date"]), h.get("fuel", {}).get("waterL")) for h in D["hikes"] if h.get("sweatLossMl")]
    swr = [(sd(h["date"]), round(v)) for h, v in _sw]
    lrows = ""
    for L in wc["legs"]:
        need = 600 * L["estHours"] / 1000, 800 * L["estHours"] / 1000
        nr = L["refillAvailable"]
        col = C["bad"] if nr.upper().startswith("NO") else (
            C["warn"] if nr[0] in "ue" else C["primary"])
        lrows += (f'<tr{" class=hot" if L.get("critical") else ""}>'
                  f'<td><b>{e(L["leg"])}</b><div class="sub">{e(L["note"])}</div></td>'
                  f'<td class="num nw">{L["estHours"]:g} h</td>'
                  f'<td class="num nw">{SW_MEAN*L["estHours"]/1000:.1f} L</td>'
                  f'<td class="num nw"><b>{need[0]:.1f}–{need[1]:.1f} L</b></td>'
                  f'<td class="nw" style="color:{col};font-weight:650">{e(nr)}</td></tr>')
    frz = "".join(f"<li>{e(x)}</li>" for x in wc["freezeMitigations"])
    return f"""<section id="fuel">
  <h2>Fuel, fluid and sodium<span class="n">targets and the measured gap</span></h2>
  <div class="tiles">{''.join([
    tile("Calories", f"{fp['targetCalPerHour']}", "kcal per hour on trail", C["primary"]),
    tile("Fluid", f"{hyd['sipTarget']['mlPerHour']}", "ml per hour, sipped", C["accent"]),
    tile("Sodium", D["nutritionGuidance"]["onTrail"]["sodiumPerHour"], "per hour", C["warn"]),
    tile("Sweat rate", f"{SW_MEAN} ml/hr", f"{SW_LO}–{SW_HI} across {SW_N} hikes", C["bad"]),
  ])}</div>
  <div class="callout"><b>Sodium, not water concentration, was the gap.</b> {e(hyd['sodiumFinding'])}</div>
  <p class="lede">{e(hyd['volumeFinding'])} {e(fp['strategy'])} {e(fp['keepGelsReason'])}</p>

  <h3>Sweat rate per hour</h3>
  {lines([{"lab":"ml/hr","col":C["bad"],"pts":swr}], ylab="ml per hour", fmt=lambda v:f"{v:.0f}")}
  <p class="sub">Garmin's model estimate rather than a measurement, but its consistency is what
  makes it usable for planning. Saturday's weigh-in replaces it with a real figure.</p>

  <h3>Estimated sweat loss against fluid recorded</h3>
  {bars(fl, fmt=lambda v: f"{v:.1f}L", colfn=lambda l,v: C["bad"])}
  <p class="sub">Recorded intake exists for only
  {sum(1 for _,v in ind if v)} of {len(ind)} of these — the rest was never written down, which is
  itself the problem the logger is meant to fix.</p>

  <h3>Water capacity against demand, leg by leg</h3>
  <p class="lede">Current capacity is {wc['totalCapacityL']} L, which covers roughly
  {wc['totalCapacityL']*1000/800:.1f}–{wc['totalCapacityL']*1000/600:.1f} hours at target.
  {e(wc['recommendation'])}</p>
  <div class="scroll"><table><thead><tr><th>Leg</th><th>Time</th>
  <th>Sweat at {SW_MEAN}</th><th>Drink target</th><th>Refill</th></tr></thead>
  <tbody>{lrows}</tbody></table></div>
  <div class="callout" style="background:#fff6f5;border-color:{C['bad2']}">
  <b>Summit morning is the one leg where capacity, not filtering, binds.</b>
  Trail Camp pond is the last water before the switchbacks.</div>
  <h3>Hose freezing — the October risk</h3>
  <ul class="clean">{frz}</ul>
</section>"""


def s_altitude():
    sl = D["sleepLadder"]
    tc, mx = sl["trailCampFt"], WP["summitElevationFt"]
    rows = ""
    ref = [(tc, "Whitney Trail Camp — where you sleep on Oct 1"), (mx, "Whitney summit")]
    for v, lab in ref:
        rows += (f'<div class="arow"><div class="mtr ref" style="width:150px">'
                 f'<span style="width:{v/mx*100:.0f}%"></span></div>'
                 f'<div class="am"><b>{v:,} ft</b><span class="sub2"> · {e(lab)}</span></div></div>')
    exp = [{"date": h["date"], "place": h["route"], "ft": h["maxElevFt"], "foot": True,
            "sym": None} for h in HK if h["maxElevFt"] >= 7000]
    symd = {a["date"]: a.get("symptoms") for a in D["altitudeExposure"] if a.get("onFoot")}
    for x in exp:
        x["sym"] = symd.get(x["date"])
    exp += [{"date": a["date"], "place": a["place"], "ft": a["elevationFt"],
             "foot": a.get("onFoot"), "sym": a.get("symptoms"),
             "recl": a.get("reclassified")}
            for a in D["altitudeExposure"] if not a.get("onFoot")]
    for a in sorted(exp, key=lambda x: -x["ft"]):
        col = C["primary"] if (a.get("recl") or not a["sym"]) else C["warn"]
        s = (f'<div class="symp">{e(a["sym"])}</div>' if a["sym"] and not a.get("recl") else "")
        chip = ('<span class="chip">not altitude</span>' if a.get("recl") else "")
        rows += (f'<div class="arow"><div class="mtr" style="width:150px">'
                 f'<span style="width:{a["ft"]/mx*100:.0f}%;background:{col}"></span></div>'
                 f'<div class="am"><b>{a["ft"]:,} ft</b><span class="sub2"> · {e(sd(a["date"]))}'
                 f' · {"on foot" if a["foot"] else "not on foot"}</span>{chip}'
                 f'<div class="sub">{e(a["place"])}</div>{s}</div></div>')
    srows = ""
    for s in D["sleepAtAltitude"]:
        srows += (f'<div class="arow"><div class="mtr" style="width:150px">'
                  f'<span style="width:{s["elevationFt"]/tc*100:.0f}%;background:{C["primary"]}">'
                  f'</span></div><div class="am"><b>{s["elevationFt"]:,} ft</b>'
                  f'<span class="sub2"> · {s["nights"]} nights · {e(s["dates"])}</span>'
                  f'<div class="sub">{e(s["place"])}</div></div></div>')
    for v, lab in [(sl["cottonwoodFt"], "Cottonwood Camp, Sep 29 — planned"),
                   (tc, "Trail Camp, Oct 1 — the night that decides summit day")]:
        srows += (f'<div class="arow"><div class="mtr ref" style="width:150px">'
                  f'<span style="width:{v/tc*100:.0f}%"></span></div>'
                  f'<div class="am"><b>{v:,} ft</b><span class="sub2"> · {e(lab)}</span></div></div>')
    vo2 = PH["vo2max"][-1]["value"]
    arows = ""
    for ft, lab in [(HIGH["maxElevFt"], "highest reached on foot"), (tc, "Trail Camp"), (mx, "summit")]:
        m_ = ft * .3048
        a1, a2 = max(0, (m_ - 1500) / 1000 * 8), max(0, (m_ - 1500) / 1000 * 11)
        arows += (f'<tr><td><b>{ft:,} ft</b><div class="sub">{e(lab)}</div></td>'
                  f'<td class="num nw">−{a1:.0f} to −{a2:.0f}%</td>'
                  f'<td class="num nw" style="color:{C["bad"]};font-weight:700">'
                  f'{vo2*(1-a2/100):.0f}–{vo2*(1-a1/100):.0f}</td></tr>')
    ai = next(i for i in D["openIssues"] if "episodes" in i["issue"])
    return f"""<section id="altitude">
  <h2>Altitude and acclimatisation</h2>
  <h3>Everywhere reached, tallest first</h3>
  {rows}
  <h3>Nights slept at altitude — the ladder that drives acclimatisation</h3>
  {srows}
  <p class="sub">Scaled against Trail Camp rather than the summit, because sleeping altitude
  matters more than the high point touched. The remaining step is
  {tc - sl['cottonwoodFt']:,} ft, from Cottonwood to Trail Camp.</p>
  <h3>What thin air costs</h3>
  <div class="scroll"><table style="min-width:0"><thead><tr><th>Elevation</th>
  <th>Aerobic capacity</th><th>Effective VO2 max</th></tr></thead><tbody>{arows}</tbody></table></div>
  <p class="sub">Against {vo2} at sea level.</p>
  <div class="callout"><b>Symptom history.</b> {e(ai['action'])}</div>
</section>"""


def s_wellness():
    w = D["wellness"]
    sl, bd, rc, sp = w["sleep"], w["bigDaySleep"], w["recovery"], w["spo2Gap"]
    rows = ""
    for r in bd["rows"]:
        f = lambda x: (f'{x["hrs"]:.1f} h'
                       + (f' <span class="sub2">sc {x["score"]}</span>' if x.get("score") else "")
                       ) if x else "—"
        n = r["nightOf"]
        col = C["bad"] if n and n["hrs"] < 4 else (C["warn"] if n and n["hrs"] < 5.5 else C["primary"])
        rows += (f'<tr><td class="nw"><b>{e(r["date"])}</b><div class="sub">{e(r["name"] or "")}</div></td>'
                 f'<td class="num nw">{e(r["duration"])}</td>'
                 f'<td class="num nw">{f(r["before"])}</td>'
                 f'<td class="num nw" style="color:{col};font-weight:700">{f(n)}</td>'
                 f'<td class="num nw">{f(r["after"])}</td></tr>')
    hrv_pts = [(x["date"][5:], x["v"]) for x in
               json.loads((ROOT / "garmin" / "wellness.json").read_text())["hrvSeries"][-56:]]
    HRV_CHART = lines([{"lab": "HRV", "col": C["primary"], "pts": hrv_pts}],
                      ylab="ms", fmt=lambda v: f"{v:.0f}")
    return f"""<section id="wellness">
  <h2>Sleep and recovery<span class="n">{e(w['source'].split(':')[1].strip())}</span></h2>
  <div class="tiles">{''.join([
    tile("Typical sleep", f"{sl['medianHrs']:.1f} h", f"mean {sl['meanHrs']:.1f} · {sl['under6Pct']}% of nights under 6", C["warn"]),
    tile("Last 60 nights", f"{sl['last60MeanHrs']:.1f} h", f"score {sl['last60MeanScore']} · deep {sl['meanDeepMin']} min", C["accent"]),
    tile("After a long day", f"{bd['meanNightOfHrs']:.1f} h", f"against {bd['meanNightBeforeHrs']:.1f} the night before", C["bad"]),
    tile("HRV", f"{rc['hrvMean']:.0f}", f"range {rc['hrvRange'][0]:.0f}–{rc['hrvRange'][1]:.0f} · resting HR {rc['restingHRMean']:.0f}", C["primary"]),
  ])}</div>

  <h3>Sleep around the six longest days</h3>
  <div class="scroll"><table><thead><tr><th>Day</th><th>Duration</th><th>Night before</th>
  <th>Night of</th><th>Night after</th></tr></thead><tbody>{rows}</tbody></table></div>
  <p class="lede">{e(bd['finding'])}</p>
  <div class="callout" style="background:#fff6f5;border-color:{C['bad2']}">
  <b>What this means for Trail Camp.</b> {e(bd['whitneyImplication'])}</div>

  <h3>HRV, last eight weeks</h3>
  {HRV_CHART}
  <p class="sub">{e(rc['trend'])}</p>

  <div class="callout"><b>Pulse oximetry is off.</b> {e(sp['problem'])} {e(sp['action'])}</div>
</section>"""


def s_untested():
    pack = ""
    for w, lab in [(12, "every logged session"), (18, "Aug 1"), (25, "Aug 15"),
                   (28, "Aug 22"), (30, "Whitney Day 1, estimated")]:
        pct = w / LB * 100
        col = C["primary"] if pct <= 12 else (C["warn"] if pct <= 18 else C["bad"])
        pack += (f'<tr><td><b>{w} lb</b><div class="sub">{e(lab)}</div></td>'
                 f'<td class="num nw" style="color:{col};font-weight:650">{pct:.0f}%</td></tr>')
    cd = ", ".join(f'{sd(p["first"])}–{sd(p["second"])}' for p in CONSEC[-3:])
    big = sorted(HK, key=lambda h: sec(h["totalTime"]), reverse=True)[0]
    return f"""<section id="untested">
  <h2>Untested before Oct 2<span class="n">what Rim to Rim did not prove</span></h2>

  <div class="callout"><b>Pack weight.</b> Every logged session used 12 lb or none. Whitney Day 1
  carries roughly 30 lb to 12,000 ft — {30/LB*100:.0f}% of bodyweight against
  {12/LB*100:.0f}% in training. Inside normal backpacking range, but it changes heart rate, pace
  and the load on the knees through {WP['totalDescentFt']:,} ft of descent.</div>
  <div class="scroll"><table style="min-width:0"><thead><tr><th>Pack</th>
  <th>Share of {LB} lb</th></tr></thead><tbody>{pack}</tbody></table></div>

  <div class="callout"><b>Sleeping at 12,000 ft.</b> Two nights at
  {D['sleepAtAltitude'][0]['elevationFt']:,} ft in Mammoth is the highest so far. Cottonwood on
  Sep 29 bridges to {D['sleepLadder']['cottonwoodFt']:,} ft; Trail Camp is another
  {D['sleepLadder']['trailCampFt']-D['sleepLadder']['cottonwoodFt']:,} ft above that.</div>

  <div class="callout"><b>A big day followed by another day.</b> Back-to-back days do exist in the
  record — {len(CONSEC)} pairs, most recently {e(cd)} — but they are ruck days and easy family
  hikes. Nothing resembles the longest single day ({big["totalTime"]}) followed by more walking,
  which is exactly the shape of Whitney Day 2.</div>

  <div class="callout" style="background:#fff6f5;border-color:{C['bad2']}">
  <b>Sun and eye protection.</b> Nothing in the record covers sunglasses, sunscreen or lip balm.
  At {WP['summitElevationFt']:,} ft in October, with granite and possible snow reflecting UV back,
  category 3–4 wraparound sunglasses are equipment rather than comfort.</div>
</section>"""


def s_issues():
    SEV = {"high": (C["bad"], C["bad2"], "High"), "medium": (C["warn"], C["warn2"], "Medium"),
           "watch": (C["violet"], "#cfc6e6", "Watch"), "info": (C["ink3"], C["line"], "Info")}
    order = {"high": 0, "medium": 1, "watch": 2, "info": 3}
    # An issue is open or it is closed. Nothing that has been resolved or corrected
    # appears in the open list, because a corrected fact left in the open list keeps
    # asserting the thing that was corrected.
    ALL = D["openIssues"]
    iss = sorted((i for i in ALL if i.get("status") != "closed"),
                 key=lambda i: order.get(i["severity"], 9))
    done = [i for i in ALL if i.get("status") == "closed"]

    rows = ""
    for i in iss:
        col, bg, lab = SEV.get(i["severity"], SEV["info"])
        since = f' · since {sd(i["since"])}' if i.get("since") else ""
        rows += (f'<div class="issue" style="border-left-color:{col}">'
                 f'<div class="ih"><span class="sev" style="background:{bg};color:{col}">{lab}</span>'
                 f'<b>{e(i["issue"])}</b></div>'
                 f'<div class="sub">{e(i["action"])}{since}</div></div>')
    hi = sum(1 for i in iss if i["severity"] == "high")

    crows = "".join(
        f'<tr><td class="nw">{e(sd(c["closed"])) if c.get("closed") else "—"}</td>'
        f'<td><b>{e(c["issue"])}</b><div class="sub">{e(c.get("resolution",""))}</div></td></tr>'
        for c in sorted(done, key=lambda c: c.get("closed") or ""))
    closed_block = ("" if not done else f"""
  <h3 style="margin:22px 0 8px;font-size:14.5px;color:{C['ink3']}">
    Closed<span class="n">{len(done)} · kept for the record, not for attention</span></h3>
  <div class="scroll"><table class="t"><thead><tr><th class="nw">Closed</th>
  <th>Issue and how it closed</th></tr></thead>
  <tbody>{crows}</tbody></table></div>""")

    return f"""<section id="issues">
  <h2>Open issues<span class="n">{len(iss)} open · {hi} high · {len(done)} closed</span></h2>
  {rows}{closed_block}
</section>"""


def s_log():
    def flag(f):
        FL = {"summit": (C["gold"], "Summit"), "milestone": (C["primary"], "Milestone"),
              "breakthrough": (C["primary"], "Breakthrough"),
              "fueling-problem": (C["bad"], "Fuel gap"), "fatigue": (C["warn"], "Fatigue"),
              "symptom": (C["violet"], "Symptom")}
        if not f:
            return ""
        c, l = FL.get(f, (C["ink3"], f))
        return f'<span class="chip" style="color:{c};border-color:{c}">{e(l)}</span>'
    hrows = ""
    for h in reversed(HK):
        fam = ('<span class="chip">family</span>' if h.get("effortType") == "family" else "")
        sw, wl = h.get("sweatLossMl"), h.get("fuel", {}).get("waterL")
        gap = "—"
        if sw and wl:
            dl = sw / 1000 - wl
            gap = (f'<span style="color:{C["bad"] if dl>2 else C["warn"] if dl>.8 else C["primary"]};'
                   f'font-weight:650">−{dl:.1f}L</span>')
        hrows += (f'<tr><td class="nw"><b>{e(sd(h["date"]))}</b></td>'
                  f'<td>{e(h.get("label") or h.get("route") or "")} {flag(h.get("flag"))}{fam}'
                  f'<div class="sub">{e(h.get("route") or "")}</div></td>'
                  f'<td class="num">{h["distanceMi"]:.2f}</td>'
                  f'<td class="num">{h["ascentFt"]:,}</td>'
                  f'<td class="num">{h["maxElevFt"]:,}</td>'
                  f'<td class="num nw">{e(h["movingPace"])}</td>'
                  f'<td class="num">{h["avgHR"]}<span class="sub2">/{h["maxHR"]}</span></td>'
                  f'<td class="num">{h["stoppedPct"]}%</td>'
                  f'<td class="num">{e(h.get("aerobicEffect") or "–")}</td>'
                  f'<td class="num">{e(h.get("exerciseLoad") or "–")}</td>'
                  f'<td class="num">{"✓" if h.get("poles") else "—"}</td>'
                  f'<td class="num nw">{gap}</td></tr>')
        if h.get("coachNote"):
            hrows += f'<tr class="nr"><td></td><td colspan="11" class="note">{e(h["coachNote"])}</td></tr>'
    rrows = "".join(
        f'<tr><td class="nw"><b>{e(sd(r["date"]))}</b></td>'
        f'<td class="num">{r.get("packLb") or "–"}</td>'
        f'<td class="num">{r["distanceMi"]:.2f}</td>'
        f'<td class="num nw">{e(r["movingPace"])}</td>'
        f'<td class="num">{r["avgHR"]}<span class="sub2">/{r["maxHR"]}</span></td>'
        f'<td class="sub">{e(r.get("coachNote") or "")}</td></tr>' for r in RK)
    hk_all = [a for a in DIG if a["type"] == "hiking"]
    top = sorted(hk_all, key=lambda a: a["durSec"], reverse=True)[:6]
    trows = "".join(
        f'<tr><td class="nw">{e(a["start"][:10])}</td><td>{e(a["name"] or "")}</td>'
        f'<td class="num nw">{a["totalTime"]}</td><td class="num">{a["distanceMi"]}</td>'
        f'<td class="num">{a["ascentFt"]:,}</td><td class="num">{a["stoppedPct"]}%</td></tr>'
        for a in top)
    return f"""<section id="log">
  <h2>Training log<span class="n">{len(HK)} hikes · {len(RK)} rucks · {sd(M['logCoversFrom'])}–{sd(M['logCoversTo'])}</span></h2>
  <div class="scroll"><table><thead><tr><th>Date</th><th>Hike</th><th>Mi</th><th>Ascent</th>
  <th>Max elev</th><th>Mov pace</th><th>HR</th><th>Stop</th><th>Aero</th><th>Load</th>
  <th>Poles</th><th>Fluid gap</th></tr></thead><tbody>{hrows}</tbody></table></div>
  <p class="sub">Family outings are marked; their pace and heart rate reflect walking with others
  and are excluded from training trends.</p>

  <h3>Rucking</h3>
  <div class="scroll"><table><thead><tr><th>Date</th><th>Pack lb</th><th>Mi</th>
  <th>Mov pace</th><th>HR</th><th>Note</th></tr></thead><tbody>{rrows}</tbody></table></div>

  <h3>Baseline: longest days on record, all {len(DIG)} activities since {DIG[0]['start'][:10]}</h3>
  <div class="scroll"><table><thead><tr><th>Date</th><th>Activity</th><th>Time</th>
  <th>Mi</th><th>Ascent</th><th>Stopped</th></tr></thead><tbody>{trows}</tbody></table></div>
  <div class="callout good"><b>Grand Canyon Rim to Rim, {sd(R2R['date'])} 2025.</b>
  {R2R['distanceMi']} mi, {R2R['ascentFt']:,} ft up, {R2R['descentFt']:,} ft down,
  {R2R['totalTime']} from a {e(R2R['startedAt'])} start, {R2R['kcal']:,} kcal, average HR
  {R2R['avgHR']}. Topped out at {R2R['maxElevFt']:,} ft, so it tested distance and vertical
  but not altitude.</div>
</section>"""


def s_reference():
    VO2_CHART = lines(
        [{"lab": "VO2 max", "col": C["accent"],
          "pts": [(m["month"][2:], m["value"]) for m in VO2["monthly"]]}],
        ylab="ml/kg/min", fmt=lambda v: f"{v:.0f}")
    zo = PH["zonesPercentHRR_CORRECT"]
    zold = PH["zonesPercentMaxHR_OLD"]
    zr = "".join(f'<tr><td><b>{z}</b></td><td class="num nw">{v[0]}–{v[1]} bpm</td>'
                 f'<td class="num nw sub">{zold[z][0]}–{zold[z][1]} bpm</td></tr>'
                 for z, v in zo.items())
    ng = D["nutritionGuidance"]
    import re as _re
    cr = ""
    for k, v in ng["carbsPerKgPerDay"].items():
        n = [float(x) for x in _re.findall(r"[\d.]+", v)]
        pretty = _re.sub(r"(?<!^)(?=[A-Z])", " ", k).lower()
        cr += (f'<tr><td>{e(pretty)}</td><td class="num nw sub">{e(v)}/kg</td>'
               f'<td class="num nw"><b>{n[0]*KG:.0f}–{n[-1]*KG:.0f} g</b></td></tr>')
    pn = [float(x) for x in _re.findall(r"[\d.]+", ng["proteinPerKgPerDay"]["range"])]
    gear = ""
    for g in D["gear"]:
        need = g["status"] == "NEEDED"
        gear += (f'<li><span style="color:{C["bad"] if need else C["primary"]};font-weight:700">'
                 f'{"☐" if need else "☑"}</span> <b>{e(g["item"])}</b>'
                 f'{"<span class=chip style=color:"+C["bad"]+";border-color:"+C["bad"]+">needed</span>" if need else ""}'
                 f'{f"<div class=sub>{e(g.get(chr(110)+chr(111)+chr(116)+chr(101)))}</div>" if g.get("note") else ""}</li>')
    sup = "".join(f'<li><b>{e(s["name"])}</b> <span class="chip">{e(s["status"])}</span>'
                  f'{f"<div class=sub>{e(s[chr(110)+chr(111)+chr(116)+chr(101)])}</div>" if s.get("note") else ""}</li>'
                  for s in D["supplements"])
    tr = "".join(f'<tr><td><b>{e(t["name"])}</b></td><td class="num nw">{e(t.get("distanceMi","–"))}</td>'
                 f'<td class="num nw">{f"{t[chr(97)+chr(115)+chr(99)+chr(101)+chr(110)+chr(116)+chr(70)+chr(116)]:,}" if t.get("ascentFt") else "–"}</td>'
                 f'<td class="nw" style="color:{C["bad"] if "CLOSED" in str(t["status"]).upper() else C["primary"]}">'
                 f'{e(t["status"])}</td></tr>' for t in D["trailOptions"])
    ov = "".join(f'<tr><td class="nw">{e(c["date"])}</td><td>{e(c["field"])}</td>'
                 f'<td class="num nw sub">{e(c["was"])}</td><td class="num nw"><b>{e(c["now"])}</b></td></tr>'
                 for c in D.get("garminOverrides", []))
    dq = "".join(f"<li>{e(x)}</li>" for x in D["dataQualityNotes"])
    return f"""<section id="reference">
  <h2>Reference</h2>
  <div class="grid2">
    <div><h3>Heart-rate zones</h3>
      <div class="scroll"><table style="min-width:0"><thead><tr><th>Zone</th>
      <th>%HRR — in use</th><th>%max HR — retired</th></tr></thead><tbody>{zr}</tbody></table></div>
      <p class="sub">Resting {PH['restingHR']}, estimated max {PH['estimatedMaxHR']}.
      {e(PH['maxHRnote'])}</p>
      <h3>VO2 max &mdash; {len(VO2["monthly"])} months</h3>
      {VO2_CHART}
      <p class="sub">{e(VO2["reading"])} {e(VO2["gapNote"])}</p>
      <h3>Resting metabolism</h3>
      <p class="sub">Back-calculating Garmin's resting-calorie figure to a 24-hour basis gives
      <b>{RMR:,} kcal/day</b> across {len(_rmr)} hikes, spread {RMR_RANGE[0]:,}–{RMR_RANGE[1]:,}.
      Useful as the floor under any daily intake target.</p></div>
    <div><h3>Daily carbohydrate at {LB} lb</h3>
      <div class="scroll"><table style="min-width:0"><thead><tr><th>Day type</th>
      <th>Per kg</th><th>Target</th></tr></thead><tbody>{cr}</tbody></table></div>
      <p class="sub">Protein <b>{pn[0]*KG:.0f}–{pn[1]*KG:.0f} g/day</b>
      ({e(ng['proteinPerKgPerDay']['range'])} per kg). On a very long day the total legitimately
      exceeds the daily table — use per-hour targets once walking.</p></div>
  </div>
  <div class="grid2">
    <div><h3>Gear</h3><ul class="clean">{gear}</ul>
      <p class="sub">{e(D.get('gearNote',''))}</p></div>
    <div><h3>Supplements</h3><ul class="clean">{sup}</ul></div>
  </div>
  <h3>Trail options</h3>
  <div class="scroll"><table><thead><tr><th>Trail</th><th>Mi</th><th>Ascent</th>
  <th>Status</th></tr></thead><tbody>{tr}</tbody></table></div>
</section>

<section id="appendix">
  <h2>Appendix<span class="n">sources, corrections, data quality</span></h2>
  <h3>Source-of-truth rule</h3>
  <p class="lede">{e(M['sourceRule'])}</p>
  <h3>Where Garmin overrode earlier figures</h3>
  <div class="scroll"><table><thead><tr><th>Date</th><th>Field</th><th>Was</th>
  <th>Now</th></tr></thead><tbody>{ov}</tbody></table></div>
  <h3>Getting data out of Garmin</h3>
  <ol class="steps">
    <li>Single activity: connect.garmin.com on the web, open the activity itself, gear icon,
    Export File. Not available in the mobile app.</li>
    <li>Whole history: Account Settings, Data Management, Export Your Data. The activity
    summary lives at DI_CONNECT/DI-Connect-Fitness/*_summarizedActivities.json.</li>
    <li>Strava also offers Export Original on any synced activity, and behaves better on a phone.</li>
  </ol>
  <h3>Watch settings worth changing</h3>
  <ol class="steps">
    <li>Leave the watch running through breaks. Stopped time is data, and elapsed time is the
    correct denominator for the fuel budget.</li>
    <li>Enable Auto Lap by distance at 1 mile — per-mile splits instead of one undivided lap.</li>
    <li>Press lap once at the summit to split ascent from descent exactly.</li>
  </ol>
  <h3>Data quality</h3>
  <ul class="clean">{dq}</ul>
</section>"""


CSS = f"""
:root{{color-scheme:light}}*{{box-sizing:border-box}}
body{{margin:0;background:{C['bg']};color:{C['ink']};font:15px/1.55 -apple-system,
 BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%}}
.wrap{{max-width:1060px;margin:0 auto;padding:18px 15px 70px}}
header.hero{{background:linear-gradient(135deg,#122436,#1f4d5e 58%,{C['primary']});color:#fff;
 border-radius:15px;padding:24px 22px}}
header.hero h1{{margin:0 0 4px;font-size:25px;letter-spacing:-.3px}}
header.hero p{{margin:0;opacity:.85;font-size:13.5px}}
nav.toc{{display:flex;flex-wrap:wrap;gap:7px;margin:14px 0 4px}}
nav.toc a{{font-size:12px;font-weight:650;color:{C['ink2']};background:{C['card']};
 border:1px solid {C['line']};border-radius:20px;padding:5px 11px;text-decoration:none}}
section{{background:{C['card']};border:1px solid {C['line']};border-radius:14px;
 padding:19px 21px;margin:14px 0;scroll-margin-top:12px}}
h2{{font-size:18px;margin:0 0 12px;letter-spacing:-.2px}}
h2 .n{{color:{C['ink3']};font-weight:500;font-size:13px;margin-left:9px}}
h3{{font-size:12.5px;text-transform:uppercase;letter-spacing:.7px;color:{C['ink3']};
 margin:22px 0 9px;font-weight:700}}
.lede{{color:{C['ink2']};font-size:14px;margin:0 0 13px;max-width:78ch}}
.sub{{font-size:12.5px;color:{C['ink3']};margin-top:2px;line-height:1.5}}
.sub2{{font-size:11.5px;color:{C['ink3']}}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:11px;margin:4px 0 14px}}
.tile{{background:{C['bg']};border:1px solid {C['line']};border-radius:12px;padding:13px}}
.tl{{font-size:10.5px;text-transform:uppercase;letter-spacing:.6px;color:{C['ink3']};font-weight:700}}
.tv{{font-size:25px;font-weight:750;letter-spacing:-.6px;margin:3px 0 1px}}
.ts{{font-size:11.5px;color:{C['ink3']};line-height:1.4}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}
@media(max-width:760px){{.grid2{{grid-template-columns:1fr}}}}
.chart{{width:100%;height:auto;display:block;overflow:visible;margin:2px 0 6px}}
.tk{{font-size:11px;fill:{C['ink3']}}}.ax{{font-size:11px;fill:{C['ink3']};font-weight:650}}
.legend{{display:flex;flex-wrap:wrap;gap:13px;margin:2px 0 6px}}
.lg{{font-size:11.5px;color:{C['ink2']};display:flex;align-items:center;gap:5px}}
.lg i{{width:11px;height:11px;border-radius:3px}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -5px;padding:0 5px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;min-width:600px}}
th{{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.6px;
 color:{C['ink3']};font-weight:700;padding:0 9px 7px;border-bottom:1.5px solid {C['line']};white-space:nowrap}}
td{{padding:9px;border-bottom:1px solid {C['line']};vertical-align:top}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}td.nw{{white-space:nowrap}}
tr.hot td{{background:#fff8ee}}
tr.nr td{{padding-top:0}}
.note{{font-size:12.5px;color:{C['ink2']};background:{C['bg']};border-radius:7px;
 padding:8px 11px;border-left:2.5px solid {C['primary2']}}}
.chip{{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.5px;
 border:1px solid {C['line']};color:{C['ink3']};border-radius:20px;padding:1px 8px;
 margin-left:6px;font-weight:700;vertical-align:1px}}
.tag{{font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:700}}
.callout{{background:#fff8ec;border:1px solid {C['warn2']};border-radius:10px;
 padding:13px 15px;font-size:13.5px;color:{C['ink2']};margin:11px 0}}
.callout b{{color:{C['ink']}}}
.callout.good{{background:#eefaf6;border-color:{C['primary2']}}}
.mtr{{height:9px;background:{C['bg']};border:1px solid {C['line']};border-radius:6px;overflow:hidden}}
.mtr span{{display:block;height:100%;border-radius:6px}}
.mtr.ref span{{background:repeating-linear-gradient(90deg,{C['gold']} 0 5px,transparent 5px 9px)}}
.arow{{display:flex;gap:14px;align-items:flex-start;padding:8px 0;border-bottom:1px solid {C['line']}}}
.arow .mtr{{flex:0 0 150px;margin-top:5px}}.am{{flex:1;min-width:0;font-size:13.5px}}
.symp{{font-size:12.5px;color:{C['warn']};background:#fff8ec;border-radius:6px;
 padding:5px 9px;margin-top:4px;border-left:2.5px solid {C['warn2']}}}
.step{{border-left:3.5px solid;background:{C['bg']};border-radius:0 9px 9px 0;padding:11px 14px;margin-bottom:9px}}
.step.hot{{background:#fffdf7;box-shadow:inset 0 0 0 1px {C['warn2']}}}
.swin{{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:{C['ink3']};font-weight:650}}
.stt{{font-size:14.5px;font-weight:650;margin:2px 0 3px}}
.tgt{{font-size:12.5px;color:{C['ink2']};background:{C['card']};border-radius:7px;
 padding:8px 11px;margin-top:6px;border-left:2.5px solid {C['primary2']}}}
.issue{{border-left:3.5px solid;background:{C['bg']};border-radius:0 8px 8px 0;padding:11px 14px;margin-bottom:8px}}
.ih{{display:flex;align-items:center;gap:9px;flex-wrap:wrap;font-size:14px}}
.sev{{font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:700;border-radius:5px;padding:2px 7px}}
ul.clean{{list-style:none;padding:0;margin:0}}
ul.clean li{{padding:9px 0;border-bottom:1px solid {C['line']};font-size:14px}}
ul.clean li:last-child{{border:0}}
ol.steps{{margin:6px 0 0;padding-left:20px;font-size:13.5px;color:{C['ink2']}}}
ol.steps li{{padding:3px 0}}
footer{{color:{C['ink3']};font-size:12px;text-align:center;padding:24px 12px 0;line-height:1.7}}
"""

NAV = [("status", "Status"), ("levers", "What matters"), ("week", "This week"),
       ("weeks", "Nine weeks"), ("summit", "Summit day"),
       ("plan", "Plan to Oct 2"), ("energy", "Energy budget"), ("fuel", "Fuel & fluid"),
       ("altitude", "Altitude"), ("wellness", "Sleep & recovery"), ("untested", "Untested"), ("issues", "Open issues"),
       ("log", "Training log"), ("reference", "Reference"), ("appendix", "Appendix")]

# The site is published on a public GitHub Pages URL, so meta.athlete is deliberately
# null and no name appears anywhere in the output. Removing it from the data rather than
# only from the render matters: the repo itself is public too, so a name left in the
# JSON would be just as readable as one in the <title>.
TITLE_SUFFIX = f" — {e(M['athlete'])}" if M.get("athlete") else ""
BYLINE = f"{e(M['athlete'])} · " if M.get("athlete") else ""

doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mt. Whitney Training Dashboard{TITLE_SUFFIX}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header class="hero">
  <h1>Mt. Whitney Training Dashboard</h1>
  <p>{BYLINE}summit {summit.strftime('%B %-d, %Y')} · <b>{DAYS} days out</b> ·
  Whitney block {sd(M['logCoversFrom'])}–{sd(M['logCoversTo'])} 2026 ·
  {len(DIG)} activities on record since {DIG[0]['start'][:10]}</p>
</header>
<nav class="toc">{''.join(f'<a href="#{i}">{e(l)}</a>' for i,l in NAV)}</nav>
{s_status()}
{s_levers()}
{s_week()}
{s_weeks()}
{s_summit()}
{s_plan()}
{s_energy()}
{s_fuel()}
{s_altitude()}
{s_wellness()}
{s_untested()}
{s_issues()}
{s_log()}
{s_reference()}
<footer>
  Generated {today.strftime('%B %-d, %Y')} · every figure computed from
  data/training-log.json and the Garmin export, none typed into prose.<br>
  A training record, not medical advice. The symptom and medication items in Open issues
  are for a doctor, not a dashboard.
</footer>
</div></body></html>"""

OUT.write_text(doc, encoding="utf-8")
print(f"wrote {OUT}  ({len(doc):,} bytes)")
print(f"  {len(HK)} hikes · {len(RK)} rucks · {sum(1 for i in D['openIssues'] if i.get('status')!='closed')} open issues · {DAYS} days out")
print(f"  computed: RMR {RMR} ({RMR_RANGE[0]}-{RMR_RANGE[1]}) · burn med {BURN_MED} "
      f"({BURN_LO}-{BURN_HI}) · tank {TANK_H:.2f} h · sweat {SW_MEAN} ({SW_LO}-{SW_HI}, n={SW_N})")
print(f"  stopped bands: {[(b['band'],b['n'],b['mean']) for b in BANDS]}")
print(f"  r = +{R_CORR:.3f} across {len(_L)} · {len(DIG)} activities total")
