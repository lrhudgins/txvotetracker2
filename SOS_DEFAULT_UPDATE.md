# Prefer statewide rosters by default

For each county with SOS statewide records in the inbox, the tracker now uses only that county's statewide observations. County-specific daily files, PDFs, spreadsheets, and Travis archives are not combined with those records. This prevents disagreements between county and SOS records from rejecting the import.

County-specific rosters remain the fallback for counties without statewide records. Score files in `inbox/scores/` remain active and join to whichever turnout source is selected. The source-selection choice appears in county diagnostics.

Keep all dated statewide exports you want included in observation-based coverage. This change does not recover earlier voters absent from every statewide file you have supplied. It may change totals previously supplemented by county files. Conflicts within the statewide records themselves still require review; the patch does not arbitrarily choose a conflicting precinct or method.

The patch contains code and synthetic tests only. It does not change your inputs, scores, configuration, boundaries, GitHub workflows, or history.

Stop the watcher with Ctrl-C. Extract into your existing repository, replacing the included files. This patch assumes the statewide SOS update is already installed.

```bash
git add scripts/folder_inputs.py tests/test_sos_rosters.py SOS_DEFAULT_UPDATE.md
git commit -m "Prefer statewide SOS rosters over overlapping county data"
git pull --rebase origin main
git push origin main
```

Resolve any Git conflicts before pushing; do not force-push. Restart:

```bash
.venv/bin/python scripts/local_update.py --inbox inbox --watch --push
```

No voter files need to be deleted or renamed. The watcher rebuilds the aggregates on restart.

Validation: 59 Python tests pass, including a conflicting county precinct being ignored and a legacy Travis ZIP never being parsed when statewide Travis records are available. County-file fallback tests continue to pass.
