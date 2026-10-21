# SOS download decoding fix

The supported CSV header is COUNTY,VOTER_NAME,ID_VOTER,VOTING_METHOD,PRECINCT. The previous downloader tried to read an API JSON response directly as CSV. This patch handles nested JSON with CSV text or base64, ZIP, and gzip, then validates the actual CSV before replacing any saved report. It does not log response bodies, follow URLs in JSON, or upload voter files.

Stop any running folder watcher with Ctrl-C. If you installed the six-hour job, pause it:

```sh
.venv/bin/python scripts/statewide_schedule.py --remove
```

Extract this ZIP into your repository folder, replacing the included files. Keep the new `scripts/sos_download_payload.py` alongside `refresh_statewide.py`.

Commit the fix before using the publisher:

```sh
git add scripts/refresh_statewide.py scripts/sos_download_payload.py scripts/sos_rosters.py tests/test_sos_download_payload.py SOS_DOWNLOAD_FIX.md
git commit -m "Decode SOS JSON and compressed report downloads"
git pull --rebase
git push
.venv/bin/python scripts/refresh_statewide.py --date 2026-10-20 --download-only
```

After `downloaded` or `unchanged`, update aggregates and restore the six-hour job:

```sh
.venv/bin/python scripts/refresh_statewide.py --push
.venv/bin/python scripts/statewide_schedule.py
```

Requires the previously supplied six-hour updater and SOS parser. No new Python packages are needed. Unsupported responses produce a controlled error and retain the prior file. Automatic downloads still require the Mac to be awake, online, and logged in.

Validation uses synthetic response fixtures. The live endpoint is blocked in the development environment, so its exact response envelope has not been verified. If the server returns only a download URL rather than embedded file content, this patch deliberately rejects it rather than guessing.
