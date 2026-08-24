---
name: whitney-weekly-garmin-rebuild
description: Weekly Mt. Whitney rebuild for Udhay. Summit is October 2, 2026. This is the only path allowed to write objective metrics.
---

Weekly Mt. Whitney rebuild for Udhay. Summit is October 2, 2026. This is the only path allowed to write objective metrics.

The real credential is NOT stored here. It lives in the scheduled task definition and is
injected as $GITHUB_TOKEN. Never commit a PAT to this repo — GitHub push protection blocks
it, and correctly so.

SETUP — do this first, without narrating it:

1. `git clone https://x-access-token:${GITHUB_TOKEN}@github.com/udhaydurai/whitney-hike-plan-oct2.git "$HOME/whitney"`
   Use `$HOME`. Do not use `/home/claude` — it is not writable and cannot be created, and a
   literal reading of the old version of this file failed on this line before doing anything else.
2. `cd "$HOME/whitney" && export GITHUB_TOKEN=${GITHUB_TOKEN}`
3. Read RUNBOOK.md in full. Every unit trap and sort bug listed there has already produced a wrong number in this project once. Do not rediscover them.

You do not need to install anything. `publish.sh` sources `tools/bootstrap_env.sh` itself,
which sets up Playwright and Chromium without root. It takes about 27 seconds on a fresh
container and about a second on a warm one.

THEN ask him for this week's watch data in one short message. Any of these works: the extracted Garmin bulk export folder, or just summarizedActivities.json plus the wellness files, or the Garmin Connect screenshots if that is all he has. He said he would send watch data weekly, so expect it.

The bulk export is a large zip with about 39 top-level folders, nearly all of it account and
service metadata. `garmin_digest.py` takes the extracted root and finds the fitness subtree on
its own. The wellness files are in `DI_CONNECT/DI-Connect-Wellness`.

WHEN HE SENDS IT:

1. `python3 tools/garmin_digest.py <extracted export root> --out garmin/digest.json`
2. `python3 tools/wellness_digest.py <export root>/DI_CONNECT/DI-Connect-Wellness garmin/wellness.json`
3. `python3 build/rebuild_data.py` — Garmin overwrites every objective metric. The nightly check-ins in data/daily/ are separate files and are merged at build time, so they survive untouched; do not fold them into training-log.json.
4. `./publish.sh "weekly Garmin rebuild <date>"`
5. Confirm it actually landed, from the remote and not from your working copy:
   `git ls-remote <remote> main` and compare against `git rev-parse HEAD`. A clone into a
   temp dir and a read of `data/training-log.json` is the stronger check and is cheap.

THEN report, specifically and briefly:

- new activities added, with distance, ascent, elapsed time and stopped percentage
- any field where Garmin overrode a previously recorded value, from the garminOverrides changelog
- whether the standing falsifiable prediction held: after the Saturday long hike, did stopped time drop below 40%? The two reference points are San Jacinto on Jul 18 at 55% and San Gorgonio on Aug 15 at 46%, so the trend is downward but has not yet cleared the threshold. This is the test of whether the fuelling change is working.
- whether anything in the nine-week plan needs to move. Check `nineWeekPlan.conflicts` and read it rather than assuming — as of Aug 23 2026 it is empty, and the earlier claim in this file that two conflicts were open was stale.

A week with no long hike is not automatically a problem. Weekday rucking to hold the phase is
part of the plan, and Aug 22 was one such week by intent. Ask before recording a missed
session as a gap.

IF THE PUSH IS REJECTED: publish.sh fetches, rebases and retries on its own. NEVER run `git push --force` — the other writer is an unattended 9 pm job recording food that cannot be reconstructed the next morning. If it stops on a real conflict, report it and stop.

IF PUBLISH FAILS ANYWHERE: check `git status` and `git log` before concluding the data did not
check in. `publish.sh` verifies before it commits, so a verification failure leaves everything
uncommitted in the working tree — that looks like a git failure and is not one. Report the
actual failing step and its error. Do not work around a failing step silently, and do not
force push.

Do not fabricate a figure. If the export did not arrive, say so plainly and stop — do not fill the gap from the conversation, because that is exactly the mistake the source-of-truth rule exists to prevent.

The live site is https://udhaydurai.github.io/whitney-hike-plan-oct2/
