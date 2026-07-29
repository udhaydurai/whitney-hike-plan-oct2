#!/usr/bin/env python3
"""
Import the shared Google Sheet as the authoritative plan, and split open issues
from closed ones.

The sheet is the plan Udhay and his partner actually agreed. It disagrees with what
was in the log in several places, starting with this Saturday, so it wins — the same
precedence the Garmin export gets over the PDF. Conflicts are recorded rather than
resolved silently, because two of them are genuine disagreements between what the
sheet says and what Udhay wrote in his own notes column.

The issues change is structural. Every issue now carries an explicit status. The
dashboard renders only the open ones, and closed ones move to a dated log. Until now a
corrected fact could sit in the open list still asserting the thing that had been
corrected — "never hiked two consecutive days" was in the open list long after the data
showed eight such pairs.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "training-log.json"
d = json.loads(LOG.read_text(encoding="utf-8"))
import sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import clock
TODAY = clock.iso()   # local date; the container is UTC and runs a day ahead at night

# ─────────────────────────────────────────────────────────────────────────────
# 1. issues: every one gets a status, and the four Udhay closed are closed
# ─────────────────────────────────────────────────────────────────────────────
CLOSE = {
    "Pulse oximetry is off": (
        "Pulse Ox enabled during sleep on the Fenix on Jul 28. A baseline will build "
        "on its own from here — no action left."),
    "Watch altimeter and zones need recalibration": (
        "Not needed. Satellite selection is on auto and ±50 ft of barometric drift is "
        "acceptable for this purpose. Zones were read directly from Garmin's own "
        "configuration rather than assumed."),
    "Left shoulder blade pressure during exertion": (
        "One week only, at a load he was not conditioned for and probably with the pack "
        "poorly set up. Did not recur."),
}
DROP = ["Hydration vest not yet purchased"]           # already gone; belt and braces

for i in d["openIssues"]:
    txt = i.get("issue", "")
    i.setdefault("status", "open")
    for key, why in CLOSE.items():
        if txt.startswith(key):
            i["status"] = "closed"
            i["closed"] = TODAY
            i["resolution"] = why

d["openIssues"] = [i for i in d["openIssues"] if i.get("issue") not in DROP]

# ── the consecutive-days issue asserted something the data had already disproved.
#    Restated as the gap that is actually still open.
for i in d["openIssues"]:
    if i.get("issue", "").startswith("Never hiked two consecutive days"):
        i["issue"] = "No big day followed by another big day"
        i["action"] = (
            "Back-to-back days are not the gap — the data has eight consecutive-day "
            "pairs, including Jul 25–26. What is untested is a long day followed by "
            "another long day: Jul 25–26 was 2.8 h then 5.7 h, where Whitney is roughly "
            "6.6 h with a full pack then a 4 am start for 14,505 ft. Week 7 of the plan "
            "(Sep 12, permit at High Creek Camp) is the one scheduled chance to rehearse "
            "it, because camping mid-route forces a second day on tired legs.")

# ── the sleep-altitude ladder is genuinely still open, but the step is now smaller
for i in d["openIssues"]:
    if i.get("issue", "").startswith("Sleep-altitude ladder"):
        i["issue"] = "Sleeping height still steps up 3,400 ft on the night before the summit"
        i["action"] = (
            "Highest slept is 8,600 ft, two nights in Mammoth Lakes. Trail Camp is "
            "12,000 ft, a 3,400 ft step. Two things now close most of it: the Cottonwood "
            "Camp night on Sep 29, and the High Creek Camp permit in Week 7 of the plan "
            "on Sep 12, which sits around 9,000-9,600 ft. Taking the Week 7 overnight "
            "rather than making it a day hike is what turns this from an open risk into "
            "a rehearsed one.")

# ─────────────────────────────────────────────────────────────────────────────
# 2. the nine-week plan, straight from the sheet
# ─────────────────────────────────────────────────────────────────────────────
d["nineWeekPlan"] = {
    "source": ("Shared Google Sheet, read Jul 29 2026. This is the agreed plan and it "
               "supersedes anything earlier in this log."),
    "weeks": [
        {"week": 1, "date": "2026-08-01", "peak": "San Bernardino Peak",
         "route": "Main Trail (Forsee Creek)", "summitFt": 10691, "ascentFt": 4700,
         "distanceMi": 16, "permit": None, "partnerNote": None, "ownNote": None},
        {"week": 2, "date": "2026-08-08", "peak": "San Gorgonio",
         "route": "Vivian Creek", "summitFt": 11503, "ascentFt": 5400,
         "distanceMi": 19, "permit": "day-hike permit obtained",
         "partnerNote": "day hike plan", "ownNote": "not available"},
        {"week": 3, "date": "2026-08-15", "peak": "San Jacinto",
         "route": "Deer Springs loop", "summitFt": 10834, "ascentFt": 5298,
         "distanceMi": 18, "permit": None, "partnerNote": "20 lb of water",
         "ownNote": "plan for Gorgonio"},
        {"week": 4, "date": "2026-08-22", "peak": "San Gorgonio",
         "route": "South Fork", "summitFt": 11503, "ascentFt": 4700,
         "distanceMi": 16, "permit": "day-hike permit",
         "partnerNote": "day hike plan", "ownNote": None},
        {"week": 5, "date": "2026-08-29", "peak": "San Gorgonio",
         "route": "Vivian Creek", "summitFt": 11503, "ascentFt": 5400,
         "distanceMi": 19, "permit": None,
         "partnerNote": "day hike, or camp at the halfway camp", "ownNote": None},
        {"week": 6, "date": "2026-09-05", "peak": "San Jacinto (heavy pack)",
         "route": "Marion Mountain", "summitFt": 10834, "ascentFt": 4600,
         "distanceMi": 12, "permit": None,
         "partnerNote": "skipping this one — hiking Half Dome instead", "ownNote": None},
        {"week": 7, "date": "2026-09-12", "peak": "San Gorgonio (heavy pack)",
         "route": "Vivian Creek", "summitFt": 11503, "ascentFt": 7500,
         "distanceMi": 25, "permit": "overnight permit at High Creek Camp",
         "partnerNote": "double summit — down to High Creek, then up again",
         "ownNote": None},
        {"week": 8, "date": "2026-09-19", "peak": "Local pack carry",
         "route": "Potato Chip Rock", "summitFt": None, "ascentFt": 2100,
         "distanceMi": 5.5, "permit": None, "partnerNote": None, "ownNote": None},
        {"week": 9, "date": "2026-09-26", "peak": "Pure taper / rest",
         "route": None, "summitFt": None, "ascentFt": None, "distanceMi": None,
         "permit": None, "partnerNote": None, "ownNote": None},
    ],
    "conflicts": [
        {"what": "Saturday Aug 1",
         "sheet": "San Bernardino Peak via Forsee Creek — 16 mi, 4,700 ft, summit 10,691 ft",
         "log": "San Jacinto Peak via Devils Slide — permit faxed to the ranger station",
         "matters": ("Different mountain, and the Devils Slide permit follow-up is only "
                     "relevant to the version in the log. Everything already written for "
                     "Saturday — the fuelling schedule, the Diamox trial, the stopped-time "
                     "prediction — still applies, because it is pinned to hours on the "
                     "clock rather than to a route.")},
        {"what": "Saturday Aug 15",
         "sheet": "San Jacinto via Deer Springs loop — 18 mi, 5,298 ft",
         "log": "San Gorgonio via Vivian Creek — the free permit was to be reserved at permits.sgwa.org",
         "matters": ("The sheet's own notes column carries the same disagreement: the "
                     "target says San Jacinto while the note says plan for Gorgonio. "
                     "Unresolved, and it changes which permit to reserve.")},
    ],
    "readsOnThePlan": [
        {"point": "The plan is bigger than what the log had",
         "detail": ("Six of the nine weeks are 16-25 mi. The largest effort recorded so "
                    "far is San Jacinto at 13.24 mi and 4,590 ft, which ran 11:04. Aug 1 "
                    "is 16 mi and 4,700 ft — a step up, not a repeat.")},
        {"point": "Week 7 is the whole plan's keystone",
         "detail": ("25 mi and 7,500 ft with an overnight at High Creek Camp, double "
                    "summit. That single week tests the three things nothing else does: "
                    "sleeping high, carrying a full pack, and a big day on legs that "
                    "already did a big day. If any week has to survive a schedule cut, "
                    "it is this one.")},
        {"point": "There is no recovery week between Weeks 3 and 7",
         "detail": ("Aug 15, 22, 29, Sep 5 and Sep 12 are consecutive weekends of 18, 16, "
                    "19, 12 and 25 mi. Week 9 is the only taper. Worth watching resting "
                    "heart rate and sleep across that block rather than assuming it "
                    "absorbs cleanly.")},
        {"point": "Every week now exceeds the tank",
         "detail": ("At the median burn of 331 kcal/hr, roughly 1,800 kcal of usable "
                    "glycogen runs out at about 5.2 h. A 16-19 mi day is 9-12 h. Every "
                    "one of these weeks is a fuelling test whether it is planned as one "
                    "or not.")},
    ],
}

# planned hikes and trail options are superseded by the sheet
d["plannedHikes"] = [
    {"date": w["date"], "name": f"{w['peak']}" + (f" via {w['route']}" if w["route"] else ""),
     "estDistanceMi": w["distanceMi"], "estAscentFt": w["ascentFt"],
     "summitFt": w["summitFt"], "status": "from the shared plan sheet",
     "purpose": w["partnerNote"] or w["ownNote"] or ""}
    for w in d["nineWeekPlan"]["weeks"]]

# ─────────────────────────────────────────────────────────────────────────────
# 3. gear from the sheet's second table
# ─────────────────────────────────────────────────────────────────────────────
d["gear"] = [g for g in d["gear"]
             if not g["item"].startswith("Spare correct-strength reading glasses")]

SHEET_GEAR = [
    ("Osprey Exos Pro 55 pack", "owned",
     "From the plan sheet. The pack the log never had. Whitney Day 1 is roughly 30 lb in "
     "this, against a 12 lb training maximum so far."),
    ("MSR Access 2 tent", "owned",
     "From the plan sheet. Conflicts with the Big Agnes Copper Spur UL1 already in this "
     "list — needs confirming which one goes up the mountain."),
    ("Sawyer Squeeze filter", "owned",
     "From the plan sheet. Conflicts with the GRAYL UltraPress already in this list."),
    ("Therm-a-Rest NeoAir XLite NXT pad", "owned", "From the plan sheet."),
    ("Magma 30 sleeping bag", "owned",
     "From the plan sheet. A 30 °F bag at 12,000 ft in early October is the right "
     "ballpark but has no margin — Trail Camp can drop into the 20s."),
    ("Stove", "NEEDED", "Blank in the plan sheet."),
    ("Bear canister", "arranged",
     "Blank in the plan sheet, but the Day 1 itinerary collects canisters at the ranger "
     "station, so this is rental rather than a gap."),
]
have = {g["item"] for g in d["gear"]}
for item, status, note in SHEET_GEAR:
    if item not in have:
        d["gear"].append({"item": item, "status": status,
                          "priority": "high" if status == "NEEDED" else "done",
                          "note": note})

# ─────────────────────────────────────────────────────────────────────────────
# 4. the summit itinerary and landmark table, sheet 3
# ─────────────────────────────────────────────────────────────────────────────
d["summitItinerary"] = {
    "source": "Shared Google Sheet, sheet 3. Times are the plan's own estimates.",
    "days": [
        {"day": "Day 1", "date": "2026-09-30",
         "steps": ["Depart San Diego around 8 am, 300 mi and about 6 h to Lone Pine",
                   "Lunch at Rubio's in Adelanto on the way, around 11 am",
                   "Eastern Sierra Interagency Information Center around 2 pm for the "
                   "permit and the bear canisters",
                   "Check in at Whitney Portal campsite #10 from 2 pm",
                   "Dinner in Lone Pine"]},
        {"day": "Day 2", "date": "2026-10-01",
         "steps": ["Breakfast in Lone Pine",
                   "Start hiking 8 am — 6 mi and 3,640 ft to Trail Camp, about 6.6 h",
                   "In camp by 2 pm. Drink heavily and take it easy"]},
        {"day": "Day 3", "date": "2026-10-02",
         "steps": ["On trail by 4 am with a day pack",
                   "Up 5 mi and 2,497 ft, about 3.3 h — summit around 8 am",
                   "Half an hour on top",
                   "Down to Trail Camp by about 11 am",
                   "Break camp, then 6 mi and 3,640 ft of descent to Whitney Portal, "
                   "about 6.6 h"]},
    ],
    "note": ("Day 3 as written is a 4 am start, the summit, and then the full descent to "
             "the Portal — around 13 h on the move after a night at 12,000 ft. That is "
             "the single hardest day in the plan and it is the one the training block "
             "has to build toward."),
    "landmarks": [
        ("Whitney Portal", 8360, 0.0), ("Stream crossing", 8800, 0.5),
        ("N Fork Lone Pine Creek", 8810, 0.8), ("Lone Pine Lake", 9960, 2.8),
        ("Bighorn Park (16 sb)", 10340, 3.5), ("Outpost Camp", 10360, 3.8),
        ("Mirror Lake (14 sb)", 10640, 4.3), ("Whitebark stump (18 sb)", 11000, 4.8),
        ("Trailside Meadow", 11395, 5.3), ("Camping turnout (18 sb)", 11890, 6.0),
        ("Trail Camp", 12039, 6.3), ("Switchback cables", 12820, 7.7),
        ("Trail Crest (96 sb)", 13777, 8.5), ("John Muir Trail junction", 13480, 9.0),
        ("Mt. Muir", 13550, 9.3), ("Keeler Needle", 14000, 10.5),
        ("Summit", 14496, 11.0),
    ],
    "landmarkNote": ("Cumulative distance and elevation from the Portal, with switchback "
                     "counts. The reference column in the sheet is a 7:10 ascent, which "
                     "is a fast time and not the target — the value here is having real "
                     "landmarks to pin the fuelling schedule to instead of clock hours."),
}

LOG.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

op = [i for i in d["openIssues"] if i.get("status") != "closed"]
cl = [i for i in d["openIssues"] if i.get("status") == "closed"]
print(f"issues: {len(op)} open, {len(cl)} closed")
for i in cl:
    print(f"   closed: {i['issue'][:70]}")
print(f"nine-week plan: {len(d['nineWeekPlan']['weeks'])} weeks, "
      f"{len(d['nineWeekPlan']['conflicts'])} conflicts flagged")
print(f"gear: {len(d['gear'])} items")
print(f"itinerary: {len(d['summitItinerary']['days'])} days, "
      f"{len(d['summitItinerary']['landmarks'])} landmarks")
