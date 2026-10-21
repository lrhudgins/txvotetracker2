# Local statewide refresh every six hours

This patch uses the direct `getFile` endpoint you supplied for SOS election ID 53815. It runs on your Mac so private score lists remain available locally. It downloads into ignored `inbox/`, invokes the existing statewide-first parser and score matcher, and pushes only generated `docs/data` aggregates with your saved Git credentials. No voter data is included in this patch.

The job does not need browser automation, Homebrew, gh, or additional Python packages. It uses macOS curl with HTTPS certificate verification enabled. A shared lock serializes aggregate publication with the optional folder watcher. Downloads use a separate job lock and hidden temporary files, then validate before atomic replacement.

## Install code

Stop your watcher with Ctrl-C, extract into the existing repository, and commit the included code:

```bash
git add scripts/local_update.py scripts/refresh_statewide.py scripts/statewide_schedule.py tests/test_local_update.py tests/test_statewide_refresh.py SIX_HOUR_UPDATE.md
git commit -m "Add six-hour local statewide downloads and aggregate refresh"
git pull --rebase origin main
git push origin main
```

Resolve any Git conflict before pushing. Do not force-push. The statewide parser/default update must already be installed, and `.gitignore` must retain `inbox/` and `.cache/`.

## Test the actual endpoint from your Mac

Run the known report date first without committing or publishing anything:

```bash
.venv/bin/python scripts/refresh_statewide.py --date 2026-10-20 --download-only
```

Success prints `downloaded` or `unchanged`. HTTP/validation failures retain any existing file. If this test fails, stop and provide only the controlled error text, not CSV contents or credentials.

The development environment cannot access this live endpoint, so live server behavior and macOS launchctl installation could not be tested here. Tests use synthetic HTTP/download fixtures and the same CSV schema as your supplied statewide export. No successful live download is claimed.

## Enable the six-hour schedule

After the download test succeeds:

```bash
.venv/bin/python scripts/statewide_schedule.py
```

The installer starts a job immediately and schedules it at 21,600-second intervals (six hours). It writes a per-user LaunchAgent using absolute paths to this repository's `.venv/bin/python` and downloader. You can close Terminal after installation. Your Mac must be logged in, awake, and connected to the internet for a scheduled run to complete; it does not run on GitHub while the Mac is asleep or off. After a restart/login the agent starts again. Moving the repository requires reinstalling the agent from the new location and removing the old one first.

The private job logs are:

```text
.cache/statewide-refresh.log
.cache/statewide-refresh-error.log
```

Inspect recent results:

```bash
tail -n 20 .cache/statewide-refresh.log .cache/statewide-refresh-error.log
```

Keep your Git credentials saved in macOS Keychain as already configured. The background job cannot ask for a password. If a push fails and leaves an unpushed aggregate commit, push that commit manually before the next scheduled run; the publisher preserves its existing guard against pushing unrelated commits.

You may keep the optional inbox watcher running for immediate manual score uploads. The new publisher lock prevents concurrent Git writes. Otherwise, new score uploads are processed at the next successful scheduled refresh.

## Dates and download behavior

- The request's `electionDate` parameter is the **report date**, not November 3. Dates come from the configured America/Chicago timezone.
- Each run refreshes the latest two report dates and backfills missing dated files from October 19 through the current report date, capped at November 3.
- An unavailable date (HTTP 204/404) is retried on a later run. Existing files are retained.
- A CSV must have the SOS fields and valid target-county records before replacing a local report. HTML/JSON error responses are never accepted as CSVs. A ZIP containing one CSV is also supported.
- Identical downloads do not rewrite the existing file. Raw CSVs are saved with owner-only permissions.
- If no requested download succeeds, the job does not publish a new dashboard update. Available older reports remain intact.
- All dated files stay local for existing observation-date deduplication. The usual district-assignment and matched-voter score rules remain in effect.
- The job remains installed until removed. After the election it keeps refreshing the final two report dates for corrections; remove it when tracking is finished.

For a full manual refresh and aggregate push:

```bash
.venv/bin/python scripts/refresh_statewide.py --push
```

For an older report correction, add `--date YYYY-MM-DD` to that command.

## Remove the schedule

```bash
.venv/bin/python scripts/statewide_schedule.py --remove
```

This removes the LaunchAgent without deleting reports or scores. Keep any old GitHub county-download workflow disabled; this patch does not restore it or modify Pages deployment.

The schedule follows Apple's per-user LaunchAgent and StartInterval design: https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html

Validation: 67 Python tests pass, including date selection, request construction, private file permissions, atomic replacement, unchanged downloads, malformed response rejection, HTTP failure preservation, ZIP validation, publication boundaries, six-hour plist configuration, and overlapping-job locking. Python 3.9 syntax checks pass. All test identities are synthetic.
