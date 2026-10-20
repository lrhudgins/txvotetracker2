# Texas CD-10 early vote tracker · 2026 general election

Daily GitHub Actions updater and GitHub Pages dashboard, using the supplied PLANC2333 district shapefile. The updater writes aggregate counts, source diagnostics and a date-indexed observation history. No candidate preferences are inferred.

## Start on GitHub

1. Unzip this package and put its **contents** at the root of a GitHub repository with default branch `main`. Include `.github/workflows/update.yml` (it is a hidden directory on some computers).
2. Open **Actions → Refresh early vote tracker → Run workflow**. The first run installs Python dependencies, prepares the district map and tries the source downloads.
3. Open **Settings → Pages**. Choose **GitHub Actions** as the publishing source. The included **Publish tracker dashboard** workflow publishes `docs/` after local pushes and after the updater workflow finishes. Your dashboard URL will be `https://YOUR-USERNAME.github.io/YOUR-REPOSITORY/`.
4. On the dashboard, **Edit county sources** opens the permanent source-list editor in your repository. Its address is `https://github.com/YOUR-USERNAME/YOUR-REPOSITORY/edit/main/config/county_sources.csv`.

The job runs once daily at **18:17 UTC (1:17 PM CDT / 12:17 PM CST)**. GitHub schedules can be delayed; this is not an exact-time service. Editing `config/` also triggers an update. Clicking **Refresh view** rereads published data; it does not launch a GitHub Action.

## Update on your computer and upload automatically

Your computer can perform the source requests and processing, then push **only generated dashboard aggregates**. GitHub hosts the page. Local requests may work where GitHub requests get 403; this depends on the county site and your network, so local browser-download fallback is also supported.

1. Use a local Git clone of your repository. Copy this update's scripts, tests, dashboard, workflows and crosswalk into that clone. **Preserve your own `config/county_sources.csv` and existing `docs/data/` history.** Commit and push the code/config update normally once before running the aggregate-only uploader.
2. Install the Python requirements using the local setup below. Configure normal Git authentication once (`gh auth login`, Git Credential Manager or SSH), and make sure a normal `git push` works. No token belongs in this project's files.
3. In GitHub **Settings → Secrets and variables → Actions → Variables**, create the repository variable **`LOCAL_UPDATES_ONLY` = `true`**. This skips the hosted downloader and prevents competing scheduled updates. Keep the **Publish tracker dashboard** workflow enabled and set **Settings → Pages → Source → GitHub Actions**.
4. From the repository directory, run:

```bash
python scripts/local_update.py --push
```

This requires a clean working tree and no unpushed existing commits. It fetches and fast-forwards the remote branch, downloads/processes the configured sources, stages only `docs/data/`, commits the changed aggregates, and pushes to the same branch on `origin`. It refuses to overwrite user edits, resolve branch divergence automatically, or upload existing unpushed code. If push fails after committing, resolve it with a normal `git push` before the next local run.

If a site still blocks automated downloading, save the file in an ignored folder and use it instead of requesting that source:

```bash
mkdir -p inbox
# Save the Travis ZIP from your browser as inbox/G26-Voter-Rosters.zip.
python scripts/local_update.py --push --from-file travis=inbox/G26-Voter-Rosters.zip
```

`--from-file` can be repeated for other configured source IDs. For Brazos, supply a ZIP containing the dated official in-person/mail PDFs: the filenames must identify their dates and methods, such as the actual `in-person-10-19-2026-accessible.pdf`. A single daily PDF is only that day's coverage, not a cumulative archive. Without `--push`, `local_update.py` refreshes files locally for inspection. `update.py` also accepts the same `--from-file` flag. Raw input stays in `inbox/`, which Git ignores.

A source failure still allows successful county aggregates and diagnostics to be pushed, but the command returns exit code 1 so the problem stays visible. Public output never includes voter names or VUIDs.

For a daily local run on macOS/Linux, add a cron entry using the **absolute path to your virtualenv Python and script**:

```cron
30 13 * * * /ABSOLUTE/PATH/TO/REPO/.venv/bin/python /ABSOLUTE/PATH/TO/REPO/scripts/local_update.py --push >> /ABSOLUTE/PATH/TO/REPO/.cache/local-update.log 2>&1
```

Create `.cache/` first. The schedule uses your computer's timezone. The computer must be awake, online and able to authenticate Git without an interactive prompt. On Windows, use Task Scheduler with the virtualenv Python, `scripts/local_update.py --push` as arguments, and the repository as the working directory. Set up and test a manual run before scheduling.

## Imported precinct workbook

The supplied `precincts26p_districts.xls` has **FENAME**, **PREC** and **PlanC2333** fields. The converted `config/precinct_crosswalk.csv` contains 562 assignments in the 13 target counties. Travis has 308 mapped precincts, 78 assigned to CD-10. Every precinct identifier appearing in the supplied regular Travis roster matches this workbook.

Those mappings are labeled **2026-primary-reference**. The dashboard includes matched totals with an explicit **provisional geography** label. It does not claim that matching precinct numbers prove November boundary continuity. To regenerate the CSV from a newer Council workbook:

```bash
python scripts/import_crosswalk.py /path/to/precincts26p_districts.xls
```

If county documentation verifies a mapping for November, set that row's `verified_for_election` to `2026-11-03` and retain its supporting source URL. Do not mark a reference mapping verified merely to remove the label. Countywide CD-10 assignments in whole counties do not depend on this reference mapping.

## What is already connected

| Source | Behavior |
| --- | --- |
| Travis · `https://votetravis.gov/wp-content/uploads/G26-Voter-Rosters.zip` | Downloads dated Excel reports in the supplied archive daily. Uses the workbook report date, selects UPDATED corrections, deduplicates voters and explicitly flags the separate limited-ballot roster. Tested with the actual uploaded ZIP. |
| Brazos · `https://elections.brazoscountytx.gov/roster/` | Discovers all dated PDF links in the **2026 General/Special Election** section, both in-person and received-mail rosters. The dedicated parser checks each page's VUID count against parsed voter rows. |
| Grimes, Burleson and Theo Elections | Included as reference links. A usable current downloadable feed was not verified in the brief search, so these do not contribute counts. |

**Validation update (October 20):** the actual uploaded Travis ZIP and Council precinct workbook were parsed and reconciled. The regular rosters contain 45,848 distinct voters across all Travis districts; the primary crosswalk assigns 11,346 to CD-10 (10,026 in person and 1,320 mail). These are provisional geographic assignments, not independently verified November precinct assignments. The original and corrected October 5 files are not added together. One voter appearing on two different mail report dates is counted once using the first report date. The limited-ballot workbook has no VUIDs and is explicitly excluded. Live direct downloads remain unverified in this workspace, and Brazos returned 403 from the user’s GitHub runner.

## Add another county link

Edit **`config/county_sources.csv`**. There is one active row per county. A row looks like:

```csv
id,county,url,adapter,enabled,default_mode,columns_json,notes
lee,Lee,https://OFFICIAL-COUNTY-SITE/current-early-voters.csv,roster,true,in_person,{},Official early voter roster
```

The example is a placeholder; replace its URL with a real official download. Use the county spelling from `config/settings.json`.

- `adapter`: `roster` for direct CSV, TSV, TXT-delimited, Excel, PDF or ZIP downloads. `brazos_index` is specific to the current Brazos roster page. Arbitrary HTML landing pages are reference links until a download parser is added.
- `enabled`: `true` to ingest; `false` to retain only a reference link.
- `default_mode`: `in_person`, `mail`, or `auto`. `auto` uses a recognized voting-method column or an unambiguous filename. Only use received/voted mail rosters; application lists and ballots-issued lists are not turnout.
- `columns_json`: `{}` for automatic recognition. To map different headers, use CSV-escaped JSON such as `"{""vuid"":""Certificate Number"",""precinct"":""PCT"",""district"":""US Congress"",""date"":""Date Voted""}"`.
- Multiple roster URLs for the same county: put them in **one row's URL field separated by `|`**. They are combined and deduplicated together. Do not add separate active rows for overlapping sources in one county.

Prefer a cumulative archive or complete list of daily files. The updater recomputes a county's snapshot from everything available at its URLs; it does **not** add yesterday's cumulative count to today's. If a source only exposes today's file, append previous daily URLs with `|`, or supply a cumulative archive. File lists must cover the intended voting period.

If the diagnostic says a column is missing, change `columns_json` to the actual headers. If a PDF is scanned, lacks readable tables, or uses a new layout, provide a machine-readable roster or add a dedicated parser; it will not be guessed from names or page lengths. Text PDF parsing depends on `pdfplumber`, not OCR.

## District assignment and map limitations

The included district ZIP contains district polygons, **not voting precincts**. The 2026 plan's CD-10 comprises all of Brazos, Burleson, Grimes, Houston, Lee, Leon, Madison, Polk, San Jacinto and Trinity; only portions of Bastrop, Travis and Walker. The county coverage is documented by the official Council report linked in `config/settings.json`.

Each roster row is assigned using its **explicit congressional district**, or its whole county when that county lies entirely in CD-10. A generic column called `District` is deliberately not treated as congressional: it might be a school, commissioner or other district.

For split counties without an explicit congressional district, add an official **November 3, 2026** residence-precinct crosswalk to `config/precinct_crosswalk.csv`:

```csv
county,precinct,congressional_district,verified_for_election,source_url
```

Verified rows need the election date and their official source URL. Imported primary reference rows leave the verification date blank and carry an explicit assignment-basis field. Preserve precinct suffixes. Do not assign an entire precinct if it is itself split between congressional districts: use voter-level congressional assignments instead. Conflicting assignments fail validation. **Unassigned residents are withheld** and displayed separately; a county's total is never distributed proportionally into CD-10.

The optional reference precinct layer comes from the Council's **2026 primary** shapefile. Its polygons are clipped to the supplied CD-10 outline. The map is a visual aid; assignments from the separate primary workbook are labeled provisional. Counts match labels by county and precinct ID; that does not establish that boundaries remained unchanged. The map can be unavailable while count ingestion continues.

## Outputs and interpretation

- `docs/data/latest.json`: reported CD-10 subtotal, each county's coverage, dates and diagnostics.
- `docs/data/history/YYYY-MM-DD.json`: last observation saved for that Chicago calendar date. Rerunning the same day replaces that day's observation. Later corrections do not rewrite older days.
- `docs/data/history.json`: compact observation time series.
- `docs/data/precinct_counts.csv` and `.json`: aggregated CD-10 records by county, residence precinct, method and vote date when available.
- `docs/data/source_state.json`: last successful aggregate for each active county, plus latest check status. No voter IDs, names or addresses.

Unknown means unknown, not zero. When no records of one voting method are present, that method stays unknown because roster absence does not establish a verified zero. A source failure preserves previous successful counts with a **stale** label and fails the GitHub job so it is visible in Actions. The workflow still commits diagnostics. The separate publishing workflow deploys the latest dashboard even after a source error; this avoids relying on a workflow-token commit to trigger a branch-based Pages build. Missing counties are listed even when no source is configured. The overall number is explicitly a **reported subtotal**, not a complete district total. It can combine reports of different ages.

Rosters with vote dates are restricted to October 19–30 for in-person early voting and September 1–November 3 for received mail. Undated records can contribute cumulative participation but not a cast-date time series; undated in-person data is withheld outside the early-voting period plus one reporting day to avoid ingesting Election Day voters. Inputs are presumed to be voted/received rosters for this general election, not registration rolls. For future elections, update the election window, geography and source links deliberately.

VUIDs are used transiently for deduplication. The updater does not save or commit raw rosters or voter IDs; browser-downloaded local files may be retained privately in the ignored `inbox/` folder. Matching duplicate voter records count once; conflicting precincts or methods cause a visible source failure. Travis repeat report dates are resolved to the earliest daily report with a visible note. Source download errors, missing headers and unrecognized rows do not quietly become zeros.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/prepare_map.py
python scripts/update.py
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000`. Source download access depends on the running machine's network. The updater uses verified HTTPS; it does not bypass access restrictions. Core deduplication, scope, error preservation, ZIP/schema and privacy tests use synthetic fixtures and do not require live requests.

## Source references

- District plan: https://data.capitol.texas.gov/dataset/planc2333
- Reference precinct map and field documentation: https://data.capitol.texas.gov/dataset/precincts
- Travis archive: https://votetravis.gov/wp-content/uploads/G26-Voter-Rosters.zip
- Brazos current rosters: https://elections.brazoscountytx.gov/roster/
- Grimes election information: https://grimescountytexas.gov/index.asp?SEC=%7B9C5A9278-6517-495F-A6A0-6E7B8EAED779%7D
- Burleson election information: https://www.burlesoncountytx.gov/page/gov.elections.earlyvoting
- Theo Elections (reference only): https://theoelections.com/early-vote

Checked October 20, 2026. These are turnout rosters, not candidate vote results.
