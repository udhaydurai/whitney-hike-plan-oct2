# Runbook

This repository is the persistent store for the Mt. Whitney project. Sessions that
work on it are ephemeral — the container is wiped when a session ends — so nothing
lives outside this repo. A fresh session clones, works, pushes, and disappears.

Read this file first. It is the contract.

## The source-of-truth rule

Stated by the athlete, and non-negotiable:

> Garmin has all the data and I shared it. The PDF should be used for fuelling, my
> mood or anything which is not there in the data.

Concretely:

**Garmin owns every objective metric.** Date, distance, ascent, descent, elevation,
elapsed and moving time, stopped percentage, heart rate, calories, training effect,
exercise load, steps, body battery, sweat loss, zone times. Paces are computed from
those, never typed.

**The conversation owns everything Garmin cannot see.** Fuelling, hydration, sodium,
gels taken, how it felt, symptoms, weather as experienced, poles, pack weight, boots,
who came, and the coaching interpretation.

Where the two disagreed, Garmin won every time, and the disagreements are recorded in
`garminOverrides` in the log rather than narrated in the dashboard. `build/nightly.py`
enforces the rule mechanically: it refuses a patch containing any objective field
instead of warning about it.

## Two intake paths, deliberately different

### Nightly — subjective only

The athlete sends the day's fuelling, training and how it felt. Never numbers Garmin
measures.

```bash
echo '{"date":"2026-08-04","dailyLog":{"carbsG":…,"proteinG":…,"sleepFelt":"…"}}' \
  | python3 build/nightly.py -
./publish.sh "nightly: Aug 4"
```

This writes `data/daily/2026-08-04.json` — **one file per date, never the shared log.**
That is deliberate and load-bearing. The nightly scheduled task and an interactive
session can both be running on the same evening; when both appended to
`data/training-log.json`, the second push of the night was rejected, and the only ways
out were a hand-resolved JSON conflict or a force-push that deletes the other side's
work. Neither is available to an unattended job at 9 pm. A new date is a new path, and
git merges different paths without being asked, so the conflict cannot happen rather
than being handled. `build/dashboard.py` merges the directory at build time.

Never move check-ins back into `training-log.json`, and never resolve a push rejection
with `--force`. The other writer is a 9 pm job recording food that cannot be
reconstructed the next morning.

A hike patch may only annotate a hike the weekly rebuild has already created:

```bash
echo '{"date":"2026-08-01","hike":{"fuel":"6 gels …","notes":"…","preWeightLb":…}}' \
  | python3 build/nightly.py -
```

If `nightly.py` refuses, do not work around it. The refusal is the feature.

### Weekly — Garmin authoritative

The athlete sends the watch data weekly. This is the only path that writes objective fields.

```bash
# 1. from a fresh bulk export folder
python3 tools/garmin_digest.py /path/to/Garmin_history --out garmin/digest.json
python3 tools/wellness_digest.py /path/to/health garmin/wellness.json

# 2. Garmin overwrites every objective metric; subjective fields survive
python3 build/rebuild_data.py

# 3. rebuild, verify, publish
./publish.sh "weekly Garmin rebuild"
```

`rebuild_data.py` compares against `data/training-log.backup.json` — the pre-Garmin
snapshot — so the override changelog stays populated across re-runs.

## Units in the Garmin bulk export — every one of these caused a wrong number once

| Field | Stored as | Convert |
|---|---|---|
| `distance` | centimetres, always | × 6.2137e-6 → miles |
| `elevationGain` / `Loss`, `maxElevation` | centimetres | × 0.0328084 → feet |
| `calories`, `bmrCalories` | **kilojoules** | ÷ 4.184 → kcal |
| `hrTimeInZone_0..6` | milliseconds | ÷ 1000 |
| `beginTimestamp` | epoch **milliseconds** | ÷ 1000 |
| `waterEstimated` | millilitres (sweat loss) | as-is |

Do not reintroduce a magnitude heuristic for the centimetre fields. Guessing the unit
from size reported 31,824 ft of ascent on a six-mile neighbourhood walk, and read a
0.5 mi walk as metres. Always centimetres.

## Units in the derived-metric exports (Metrics*, TrainingHistory, HillScore …)

A second family of Garmin files, one JSON per metric per ~100-day window, overlapping at
the seams. `tools/metrics_digest.py` reads them.

| Field | Stored as | Convert |
|---|---|---|
| `altitudeAcclimation` | **metres of acclimated altitude** | × 3.28084 → feet |
| `currentAltitude` | metres | × 3.28084 → feet |
| `acclimationPercentage` | a real percent, populated only on exposure days | as-is |
| `calendarDate` | ISO string in some metrics, **epoch ms in others** | handle both |

`altitudeAcclimation` is not a percentage. It reads 1400 after two nights at Mammoth,
which is 4,593 ft and plausible; as a percent it would be 1400%. Deduplicate the window
overlaps by keeping the last record for a date.

Epoch `calendarDate` values are midnight UTC. Convert them as UTC — a local conversion
moves every one of them back a day in this container.

## A digest may never blank its own output

A weekly run pointed at an export with no wellness files produced a structurally valid
but empty `wellness.json`, and writing it deleted 583 sleep nights, 303 HRV points and
the zone configuration in a single commit. An export that lacks a metric is not evidence
that the metric is gone. `wellness_digest.py` now exits rather than overwrite a populated
digest with an empty one, the same way `nightly.py` refuses an objective field.

## Do not identify a hike by a superlative

`SJ` was "the hike with the highest maxElevFt", which meant San Jacinto until San
Gorgonio (11,510 ft, Aug 15) out-topped it (10,817 ft). `SJ` then silently pointed at a
hike with no fuel record and the build died mid-publish. Identify a specific hike by
route or label. The same reasoning as "never index a hike by position".

A Garmin-only hike has no `route` until the conversation names one, and the altitude
table indexes `h["route"]` directly. `rebuild_data.py` fills it from Garmin's own
activity name so the key always exists.

Chromium's path is not fixed across containers. `verify_site.py` resolves `$CHROME_PATH`,
then any installed Playwright chromium, before falling back to `/opt/pw-browsers`.

`rucking` is its own activity type and shares no substring with hiking or walking.
Leaving it out of `HIKEY` silently dropped eleven sessions.

Sort durations numerically. Lexicographic sort on `"8:58"` vs `"11:04"` put the two
longest efforts in the project — San Jacinto and Grand Canyon Rim to Rim — below a
nine-minute walk, and they went unnoticed for a whole build.

Moving time comes from the speed stream at ≥ 0.1 m/s. A distance-delta threshold
counted GPS jitter as movement and inflated San Jacinto to 8:14 against Garmin's 4:58.
Garmin was right.

## Publishing

The published folder is `docs/`, not `site/`. GitHub Pages deploying from a branch can
only serve the branch root or `/docs` — an arbitrary folder name is not an option — so
`build/site.py` writes there and Pages is configured as **main branch, /docs**. Do not
rename it back.

`./publish.sh "message"` runs build → verify → **commit** → fetch → rebase → push, and
exits without committing if nothing changed. It will not publish a site that fails
verification.

The order matters and was wrong twice. Committing has to come *before* the rebase: git
rebase refuses to run against a dirty tree, so an earlier version that rebased first
reported a conflict on literally every run. And the rebuild has to come *after* the
rebase, because merging in another writer's data makes the generated files stale by
definition.

Generated paths (`docs/**`, `whitney-dashboard.html`) are routed by `.gitattributes` to a
merge driver that keeps our copy and reports success. A conflict in 140 KB of generated
HTML carries no information — both sides are renderings of their own inputs — and the
rebuild afterwards produces the only version that was ever correct. If anything *else*
conflicts, publish.sh stops and says so rather than guessing.

`tools/verify_site.py` checks four things on a 390 px viewport: zero JS errors, no
horizontal overflow, the service worker actually reaches `active`, and a real offline
reload after the local server is killed. The server is killed rather than just setting
the context offline, because Chromium does not always route service-worker fetches
through the page's network emulation — an earlier version of the check logged a live
304 while the page believed it was offline.

## Dashboard design rules

Set by the athlete after rejecting the first version: *"this is not a Q&A document or log
file."*

* Eleven-plus sections ordered status → action → evidence → reference.
* Every number is computed in `build/dashboard.py` from the data. No figure is typed
  into prose. If a figure appears in a sentence, it came from an f-string.
* Each fact has exactly one owning section.
* No first person. No Q&A headings. No narrated self-correction — corrections are
  dated rows in the appendix changelog.

Two bugs that a visual check missed and only a line-by-line audit caught: a variable
collision on `prows` made the training-phases section render Garmin export options,
and a hardcoded `d["hikes"][7]` made every row of the stopped-time table read 0h 00m
while the headline said 54.6%. Recompute per row; never index a hike by position.

## Dates — the container is UTC, the athlete is not

**Never call `date.today()`.** Import `build/clock.py` and use `clock.today()`,
`clock.iso()` or `clock.pretty()`.

The container runs on UTC. The nightly check-in fires at 9 pm Pacific, which is 04:00 UTC
the *next* day, so the very first nightly run filed Tuesday evening's food under
Wednesday. That is not a one-off: every single night falls in the window where the
container date and the local date disagree. A training log whose dates sit a day off the
calendar it is compared against is worse than no log.

`nightly.py` now defaults to the local date and refuses any date in the future, naming
UTC drift as the likely cause. Days-to-summit is computed from `clock.today()` rather
than from `meta.lastUpdated` — using the latter froze the countdown whenever nobody
edited the file.

## Python in this container

Python 3.11. Two things bite repeatedly when generating HTML from f-strings:

* Same-quote nesting is a syntax error. Precompute the inner value into a variable.
* `{{` inside an f-string *expression* builds a set, it does not escape a brace.
  `f"{ {'a':1} }"` is a set containing a dict, and raises `unhashable type: 'dict'`.
  Precompute anything with braces outside the f-string.

Use `fitdecode`, not `fitparse` — the latter will not build a wheel here.

Chromium for Playwright is at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.

## Facts corrected by the athlete — do not reintroduce them

* **Gem Lake was a family outing, not a hike.** Tagged `effortType: family` and
  excluded from pace and heart-rate trends. Any argument built on its zone data is
  invalid.
* **He has slept at 8,600 ft**, in Mammoth Lakes, for two nights. The earlier claim
  that he had never slept above 8,000 ft was wrong.
* **He has hiked on consecutive days** — eight back-to-back pairs exist in the data,
  including 25–26 July. `consecutiveDays` is computed, not asserted, for this reason.
* **Blue Sky is his home ground and he has never had symptoms there**, which rules
  out dehydration as the cause of the stopping-on-inclines pattern.
* **Do not chase many variables at once.** The energy-budget model is his, and it is
  the frame: roughly 1,800 kcal of usable glycogen, burn of 285–480 kcal/hr, so the
  tank alone lasts about 5.2 hours. Blue Sky is a five-hour hike. San Jacinto ran 11.1.

## Symptom attribution

Merge symptoms only from exposures marked `onFoot`. Dizziness at the top of the
Mammoth gondola belongs to the gondola, not to the Devils Postpile hike that happened
the same day.

## What is not medical advice

`openIssues` contains items for a doctor — the Diamox trial, the vision change. The
dashboard records them and says plainly that they are for a doctor. Keep it that way.
