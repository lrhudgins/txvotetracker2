# Automatic early-voter score matching

This patch replaces averages of all uploaded score rows with averages for matched 2026 CD-10 early voters. It contains code and synthetic tests only. It does not include your voter files, generated voter-level matches, configuration, or turnout history.

## Install once

Stop the watcher with Ctrl-C. Extract this ZIP into your existing repository, replacing the corresponding files. It assumes the previous precinct-map update is installed.

From the repository folder, commit only the code changes:

```bash
git add scripts/update.py scripts/folder_inputs.py scripts/local_update.py scripts/precinct_scores.py scripts/voter_matching.py docs/index.html docs/precinct-map.js tests/test_scores.py tests/test_local_update.py tests/test_voter_matching.py AUTOMATIC_MATCHING_UPDATE.md
git commit -m "Match uploaded scores to early voters locally"
git pull --rebase origin main
git push origin main
```

If Git reports a conflict, resolve it before restarting. Do not force-push.

Keep the daily county downloader disabled as previously configured. This patch does not restore or modify GitHub workflows. Keep the Pages deployment workflow to publish aggregate changes.

## Private input folders

Use the existing repository's ignored `inbox/` folder. It must contain the complete current inputs you want counted, rather than only the most recently added daily file.

| File | Naming convention |
| --- | --- |
| Travis complete roster ZIP | `inbox/travis__2026-11-03__2026-10-20__mixed__archive.zip` |
| Brazos daily in-person roster | `inbox/brazos__2026-11-03__2026-10-19__in-person__daily.pdf` |
| Countywide scored voter list | `inbox/scores/travis__2026-10-20__scores.csv` |
| Precinct scored voter list | `inbox/scores/travis__2026-10-20__precinct-101__scores.csv` |

Use the actual county in every filename; the examples do not establish which county your sample belongs to. Use lowercase hyphenated county names, including `san-jacinto`. Rename `precinct_101_voters-2.csv` using the score convention and its actual county. Do not place voter files in `docs/`.

The score parser accepts your populated export's `Prec`, `STID`, `VanId`, `First`, `Last`, and `Score` headers. Other demographic, address, contact, and political-history fields are ignored. In this export, `Name` is a street field; it is never treated as a voter name. Explicit `Full Name` / `Voter Name` headers are also supported. Supply existing numeric scores between -100 and 100; the code computes averages, not individual political scores.

`STID`/`VUID` must be ten-digit Texas voter IDs. `VanId` is never equated with a state voter ID. A file without state IDs can match by first/last name. Precinct can come from `Prec` or the filename. County always comes from the filename.

## Run continuously

```bash
.venv/bin/python scripts/local_update.py --inbox inbox --watch --push
```

The watcher scans both roster and score subfolders. Adding or replacing either type recalculates turnout and matched scores after files settle, then pushes aggregates. Keep the process running; Ctrl-C stops it. No extra packages are required beyond the existing requirements.

For a single local refresh without pushing:

```bash
.venv/bin/python scripts/local_update.py --inbox inbox
```

Local runs now default to `inbox` even if `--inbox` is omitted. Avoid the legacy `--from-file` mode: other enabled county sources can still download in that mode. The direct `scripts/update.py` interface retains its existing download behavior unless `--inbox inbox` is specified.

## Matching and scores

1. Read and deduplicate the selected rosters. Apply the existing election-period, early-voting-method, and CD-10 membership rules. Only these eligible early voters reach the join.
2. Match an exact state voter ID within the county first. A matching state ID can follow a voter whose score-list precinct differs; the result uses the roster precinct.
3. Otherwise require a unique normalized name within the same county and precinct. Case, accents, and punctuation are normalized. Structured first/last fields retain their respective roles. Full name fields allow either display order; comma-separated names are read as last, first. Middle names, suffixes, initials, and nicknames are not guessed or dropped.
4. Exclude ambiguous matches and contradictory state IDs. Do not assign one score record to two people. Repeated identical state-ID rows count once; conflicting duplicate scores fail validation.
5. Average only populated scores of matched early voters. Zero is a score; blank is missing. Unmatched voters never become zero. No scored matches means a gray precinct.

Match coverage appears in each map popup and the aggregate CSV: eligible early voters, matched voters, matches by ID/name, unmatched voters, ambiguous voters, conflicting identifiers, and matched voters missing scores. A low-coverage average may describe only a small subset of the precinct's early voters.

Latest countywide score snapshots replace older snapshots. Newer precinct files can replace the corresponding precinct. Use `__r2` before `.csv` to supersede a same-date file. Keep daily vote rosters together unless a later cumulative/archive file replaces them. Deleting score files removes their score coverage; deleting rosters removes their current matching population.

A failed roster or score import preserves the last successful *matched-early-voter* average as stale. Old averages of all score-list voters are deliberately discarded during this upgrade. A score list with no corresponding local roster waits for a roster instead of averaging everyone.

## Privacy

Raw names, identifiers, and row-level matches exist only in process memory and your local input files. No row-level match export or identity cache is written. Public output has an explicit aggregate schema. Match diagnostics contain counts and controlled error messages, not names, IDs, or file contents.

The publisher stages only `docs/data`, and refuses to run if anything under `inbox` is already tracked by Git. Your existing `.gitignore` must contain `inbox/`. If you previously committed raw data, ignoring or untracking it does not remove old public Git history; this patch does not rewrite repository history.

For ordinary installation commits, use the explicit file list above. Never force-add `inbox` or put raw inputs in public output folders. This patch does not alter the privacy or retention of files you have already uploaded to ChatGPT.

## Validation

The automated tests cover new roster and score uploads rebuilding the join without network access, duplicate-name ambiguity, ID contradictions, name normalization, election/district filtering, zero versus missing, snapshot replacement, stale-data preservation, and aggregate-only Git publication. Tests use synthetic identities only.
