# Whitney Training Project

A living training log for the October 2, 2026 Mt. Whitney summit attempt. Built from the
May 20 – July 20, 2026 coaching log (7 ruck sessions, 8 hikes, San Jacinto summit).

## How it works

```
data/training-log.json     <- the single source of truth. Everything lives here.
build/build_dashboard.py   <- reads the JSON, writes the HTML. No dependencies.
whitney-dashboard.html     <- the deliverable. Self-contained, opens anywhere.
```

To update: append to the JSON, then run `python3 build/build_dashboard.py`.
Nothing else needs to change — tiles, charts, tables and issue counts all recompute.

## Adding a hike

Append to the `hikes` array. Only `id`, `date`, `route`, `label`, `distanceMi`,
`ascentFt`, `movingTime`, `movingPace` and `avgHR` are required; everything else
enriches the charts as it becomes available.

```json
{
  "id": "H9", "date": "2026-07-25", "route": "…", "label": "…",
  "distanceMi": 0, "ascentFt": 0, "descentFt": 0, "minElevFt": 0, "maxElevFt": 0,
  "totalTime": "0:00:00", "movingTime": "0:00:00",
  "avgPace": "00:00", "movingPace": "00:00", "bestPace": "00:00",
  "avgHR": 0, "maxHR": 0,
  "steps": 0, "cadence": 0,
  "aerobicEffect": 0, "anaerobicEffect": 0, "exerciseLoad": 0, "primaryBenefit": "…",
  "totalCal": 0, "sweatLossMl": 0,
  "zonesPct": { "Z1": 0, "Z2": 0, "Z3": 0, "Z4": 0, "Z5": 0 },
  "bodyBattery": 0, "recoveryHours": 0,
  "poles": true, "packLb": 12,
  "fuel": { "waterL": 0, "saltTabs": 0, "sodiumMg": 0, "caloriesIn": 0, "items": "…" },
  "notes": "how it felt, weather, who came, what you ate",
  "coachNote": "the interpretation",
  "flag": "milestone | breakthrough | fueling-problem | fatigue | symptom | summit"
}
```

Leave a field `null` rather than `0` when it wasn't recorded — the charts draw an
explicit `n/a` marker for missing data so an unlogged day never reads as a zero.

## Adding a nutrition week

`nutritionWeeks` holds one object per week; the dashboard renders the **last** entry as
"this week". Append a new one each week rather than editing the old — the history is the point.

```json
{ "weekOf": "2026-08-03", "label": "…", "hikeDay": "Sat Aug 15",
  "hikeDayNote": "…", "context": "…",
  "days": [
    { "day": "Mon Aug 3", "type": "easy|easy-moderate|moderate|load|hike",
      "session": "…", "carbsG": "219–365", "proteinG": "130–146",
      "note": "…", "flag": true, "past": false }
  ],
  "loadDayFoodPlan": { "note": "…",
    "meals": [ { "when": "Breakfast", "items": "…", "carbsG": 147 } ] },
  "measureThis": { "title": "…", "why": "…", "how": "…" },
  "actuals": null }
```

`type` drives the colour coding. `flag: true` highlights the row. `past: true` dims it.
`loadDayFoodPlan` totals are summed from the items, so they stay honest automatically.

Fill `actuals` once the week is reported — what was actually eaten, pre/post hike weight,
fluid and sodium taken — then the next week's targets adjust off it.

Bodyweight and height live in `physiology` (161 lb / 5'7"). The builder turns the per-kg
ranges in `nutritionGuidance` into absolute grams, and expresses pack weight as a share of
bodyweight — change the weight and every derived number follows.

`nutritionGuidance.sampleLongHikeDay` drives the "what that looks like as food" table; its
day total is computed from the items, so editing portions updates the total and the
in-band/out-of-band verdict automatically.

## Adding weekday routine actuals

`weekdayRoutine.weeks` is empty. The `template` array holds the plan; each week records
what actually happened:

```json
{ "weekOf": "2026-07-27", "done": { "Tue": "strength", "Wed": "45min Z2 ruck" },
  "missed": ["Fri interval"], "notes": "…" }
```

## Adding altitude exposure that isn't a hike

`altitudeExposure` records elevation you reached without a recorded activity — a
drive-up, a gondola, a camp night. These feed the altitude ladder alongside the hikes.

```json
{ "date": "2026-07-25", "place": "…", "elevationFt": 0, "onFoot": false,
  "symptoms": "… or null", "note": "…" }
```

Same-date entries merge onto a hike row **only** when `onFoot` is true — otherwise a
gondola ride's symptoms would wrongly attach themselves to that day's hike.

## Updating the plan

`forwardPlan` drives the schedule section. `kind` is one of `hike`, `rest`, `week`,
`admin`, `addition`, `travel`, `acclimatization`, `summit`. Set `priority: "high"`
to highlight a step. `packLb` accepts a number or the string `"full"`.

## The one-line summary of the data so far

The engine improved and the fueling didn't. Same route, June 13 vs June 20:
average heart rate 136 → 126 with poles. Meanwhile every long hike ran a fluid
deficit, and San Jacinto ran roughly 5.5L of fluid, 2,000 calories, and 5,000+ mg
of sodium short. That, not fitness, is what made the descent brutal.

The July 25–26 Mammoth weekend added the best pacing in the log (43% Zone 1,
38% Zone 2 at 10,900 ft) and confirmed the %HRR zone recalibration took. It also
added a third episode of mild symptoms at 10–11k ft.

## The three untested variables before October 2

1. **Pack weight** — every logged session used 12 lb or none. Whitney Day 1 is ~30 lb.
2. **Sleeping at altitude** — never above 8,000 ft. Whitney has you sleeping at 12,000 ft.
3. **Consecutive days** — ten hikes, never two in a row. Whitney Day 2 isn't a fresh day.

## Caveats worth keeping in view

- Max HR of 178 is estimated, not tested. Every zone percentage inherits that uncertainty.
- Calories-eaten figures are reconstructed from described food, not logged.
- This is a training record, not medical advice. Several flags in it — shoulder-blade
  pressure under exertion, coordination loss at 10,500 ft, a very salty sweat rate,
  recurring gut distress after long efforts — are worth raising with a doctor before October 2.
