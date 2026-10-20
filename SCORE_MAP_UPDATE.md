# Score map and Brazos parser update

Unzip this patch into the **root of your existing local repository**, replacing matching files. It adds a prepared precinct map and preserves your county source list, crosswalk and turnout history. No voter-level CSVs or rosters are included in the patch.

## 1. Commit and push this code/map update once

Stop the existing watcher with **Ctrl-C** first. From your repository folder:

```bash
git add index.html .nojekyll docs/.nojekyll docs/index.html docs/map-colors.js docs/precinct-map.js docs/data/district.geojson docs/data/precincts.geojson scripts/update.py scripts/folder_inputs.py scripts/local_update.py scripts/precinct_scores.py scripts/prepare_map.py SCORE_MAP_UPDATE.md tests/test_scores.py
git commit -m "Fix Brazos roster and add precinct score map"
git push
```

The raw inbox is already ignored by Git. The local publisher commits only generated `docs/data/` files, so this initial code/map commit is necessary.

## 2. Put scores in their own folder

```bash
mkdir -p inbox/scores
```

Use one of these naming formats:

| Filename | Contents |
| --- | --- |
| `travis__2026-10-20__scores.csv` | A countywide snapshot containing multiple precincts; each row needs `Prec` or `Precinct`. |
| `travis__2026-10-20__precinct-101__scores.csv` | One precinct's snapshot; the filename supplies precinct 101 if `Prec` is missing/blank. |
| `travis__2026-10-20__precinct-101__scores__r2.csv` | A corrected replacement of the same snapshot. |

**Use the actual county in the filename.** `travis` is an example; no county is inferred from a name, address or precinct number alone. County slugs follow `INBOX_GUIDE.md`, including `san-jacinto`.

The date is the score snapshot's as-of date. Score files do not use the turnout roster's election/method/coverage naming structure. Keep turnout files in the rest of `inbox/` with their existing names; the importer treats `inbox/scores/` separately.

The CSV must contain a numeric **`Score`** field. It accepts your existing layout, including **`Prec`** and **`STID`**. Other names, contact fields and demographic columns are ignored. `STID`/`VUID` or `VanId`, when populated, deduplicate identical voter rows within a file. Without an identifier, each nonblank row counts once.

## 3. Start the same folder watcher

```bash
.venv/bin/python scripts/local_update.py --inbox inbox --watch --push
```

Leave Terminal running. Adding, replacing or deleting score CSVs triggers an update just like turnout roster changes. Only aggregate scores and counts are uploaded; source voter records remain local. The Mac must be awake and online to push.

The newest countywide snapshot replaces previous countywide coverage. A newer precinct-specific file can replace that precinct. Same-date corrections use `__r2`, `__r3`, etc.; ambiguous overlapping versions are rejected. Removing an input removes its current score coverage. Invalid scores preserve the last successful county result with a visible stale/error diagnostic.

## Reading the map

- The default layer is **Average uploaded score**. Use **Color by → Early-vote count** for the original turnout layer.
- The score layer uses a fixed **−100 to +100** scale: negative values blue, zero white, positive values orange. No political-party meaning is assigned to either endpoint.
- Each precinct's mean is the arithmetic average of its populated numeric scores. Blank scores are excluded; a genuine zero is included. Values outside the range, infinity, NaN and nonnumeric entries fail validation.
- Gray means no populated score. The uploaded example has no populated `Score` values, so it cannot produce a real score color until scores are filled in. Do not fill blanks with zero to make the map show a color.
- Score averages describe rows in your uploaded score CSVs. They are **not automatically restricted to early voters** and are not candidate vote totals. Popups show score averages and turnout counts as separate measures.
- Click a precinct to see the mean, number of scored/missing rows, as-of date, stale status and reported early-vote count.
- The prepared map has **301 full precinct outlines** assigned to CD-10 in the Council's **2026 primary** workbook. It uses the `CNTY` county FIPS field and `PREC` identifiers. These reference polygons may differ from November boundaries; they are not clipped district pieces. Precincts outside that reference CD-10 selection are not drawn even if their scores appear in a countywide file.

Published score outputs are `docs/data/precinct_scores.json` and `.csv`. They contain county, precinct, average, counts, date and status only. Source voter IDs, individual scores, names and contact information are never exported.

The prepared geometries are included, so there is no extra boundary download required. For deliberate regeneration, use the original official ZIP:

```bash
.venv/bin/python scripts/prepare_map.py --precincts-zip /path/to/precincts26p.zip --force
```

## Brazos correction

The actual October 19 PDF has 92 pages but displays the roster header only on page 1. The parser now verifies that first header and checks voter identifiers on every page without demanding repeated headers. It still rejects unreadable pages and unreconciled rows. The supplied PDF parses to **4,561 distinct voter records**.

Brazos source page: https://elections.brazoscountytx.gov/roster/

Continue using the existing roster filename, for example `inbox/brazos__2026-11-03__2026-10-19__in-person__daily.pdf`. The original folder-mode workflow makes no county website requests.

## Dashboard versus README

Keep **GitHub Settings → Pages → Source → GitHub Actions**, and keep the existing **Publish tracker dashboard** workflow enabled. It publishes the contents of `docs/` at:

https://lrhudgins.github.io/txvotetracker2/

This patch also adds a root `index.html` redirect to `docs/` and `.nojekyll` files. If Pages instead publishes the repository root, the root URL redirects to the dashboard rather than rendering the README. Publishing settings remain on GitHub; this ZIP cannot change them. The code was tested locally, but a live deployment was not performed from this workspace.

Keep **`LOCAL_UPDATES_ONLY=true`** for the manual-folder workflow so the hosted downloader does not compete with your local watcher.
