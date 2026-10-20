# Drop voter files here, then update automatically

The folder is **`inbox/` inside your local Git repository**. It is deliberately ignored by Git: the raw files stay on your Mac, while only aggregates are published. Subfolders are allowed; each file still needs the complete filename below.

Brazos source page: **https://elections.brazoscountytx.gov/roster/**

Use this exact filename structure, in lowercase:

```text
county__election-date__report-date__method__coverage.ext
```

Use **double underscores** between fields. The election date is always **2026-11-03** for this tracker. Report date means the day covered by a daily report, or the through-date of a complete cumulative snapshot. Do not use the day you happened to download the file unless that is also its report date.

| Example filename | File to put there |
| --- | --- |
| `travis__2026-11-03__2026-10-19__mixed__archive.zip` | The complete Travis ZIP you supplied, current through October 19. Keep its internal files unchanged. |
| `brazos__2026-11-03__2026-10-19__in-person__daily.pdf` | Brazos's October 19 in-person roster PDF. |
| `brazos__2026-11-03__2026-10-16__mail__daily.pdf` | Brazos's October 16 received-mail roster PDF. |
| `lee__2026-11-03__2026-10-20__in-person__cumulative.csv` | A complete Lee in-person roster through October 20, if you have one. This is a naming example, not a supplied Lee data source. |
| `brazos__2026-11-03__2026-10-19__in-person__daily__r2.pdf` | A corrected replacement of the October 19 in-person report. Highest revision wins. |

## Allowed field values

- **County:** `bastrop`, `brazos`, `burleson`, `grimes`, `houston`, `lee`, `leon`, `madison`, `polk`, `san-jacinto`, `travis`, `trinity`, `walker`.
- **Method:** `in-person`, `mail`, or `mixed`. `mail` must be voted/received mail, not applications or ballots issued. `mixed` is only for ZIP archives containing multiple voting methods.
- **Coverage:** `daily` for that one report day; `cumulative` for a complete roster through the report date; `archive` for a complete ZIP snapshot containing dated reports. All ZIP files use `archive`.
- **Extension:** `.pdf`, `.csv`, `.tsv`, `.txt`, `.xls`, `.xlsx`, `.zip`. Renaming an extension does not convert the file format. PDFs must be supported, readable text rosters, not scans. A new county PDF layout may need a dedicated parser.
- **Optional correction:** append `__r2`, `__r3`, etc. immediately before the extension. An unnumbered file is revision 1. You can also replace the original file with corrected contents under the same name.

The filename supplies county, election, reporting date, method and coverage. **The file still needs actual voter records and a VUID column.** Precincts or congressional districts are also needed for district assignment in split counties. Filenames cannot supply a voter's residence precinct or reconstruct unreadable PDF data. Standard CSV/Excel headers include `VUID`, `Precinct` (or `PCT`), optionally `Congressional District`, and optionally `Date Voted`.

## Combining files

- All daily reports are combined and voters are deduplicated by VUID.
- For each county and method, only the newest cumulative/archive snapshot is used. Daily files after its through-date supplement it; earlier daily files are superseded.
- Highest revision replaces the earlier file for the same day/coverage. Ambiguous files with identical metadata fail visibly rather than being added together.
- Missing days stay missing. A filename does not prove that you supplied the complete reporting period.
- Conflicting voter precincts, districts or explicit vote dates cause a source error. Repeated daily report dates count a voter once using the earliest report date, with a diagnostic note.
- Adding, replacing or deleting a file rebuilds the current totals from what remains in the folder. A failed parse preserves the last successful county aggregate and marks it stale. An entirely empty folder clears the current subtotal to unknown; saved earlier-day history is retained.
- In folder mode, **no county website is queried**, including Brazos. Only your Git fetch/push accesses the network.

## Start the automatic folder watcher

Copy the updated `scripts/` files into your existing repository and commit/push that code update once. Preserve your county links and accumulated dashboard history. Your existing `.gitignore` already excludes `inbox/`.

This download is a patch: unzip its contents into the **root of your existing clone**, replacing the matching files. It does not contain or replace your county-source configuration, crosswalk or historical aggregates. Commit the patched files once:

```bash
git add scripts/update.py scripts/local_update.py scripts/folder_inputs.py docs/index.html INBOX_GUIDE.md watch_voter_files.command tests/test_folder_inputs.py
git commit -m "Add local voter-folder imports"
git push
```

From your local repository folder:

```bash
mkdir -p inbox
.venv/bin/python scripts/local_update.py --inbox inbox --watch --push
```

Keep that Terminal window running. Add or replace the named files in Finder; after they stop changing for a polling interval (3 seconds by default), the watcher rebuilds the aggregates and pushes them to GitHub. **Ctrl-C stops the watcher.** The Mac must stay awake and online for automatic Git uploads. A failed Git push needs to be resolved with normal Git before the next successful automatic push; restart the watcher to retry unchanged input files.

For one update without keeping a watcher running:

```bash
.venv/bin/python scripts/local_update.py --inbox inbox --push
```

For a local preview without uploading:

```bash
.venv/bin/python scripts/local_update.py --inbox inbox
.venv/bin/python -m http.server 8000 --directory docs
```

Open `http://localhost:8000`. A watcher and a daily scheduled updater should not run concurrently against the same clone.

Keep GitHub repository variable **`LOCAL_UPDATES_ONLY=true`** so the hosted downloader does not compete with the local folder workflow. Keep **Pages → Source → GitHub Actions** and the publishing workflow enabled. The source files in `inbox/` are ignored and will not trigger GitHub workflows directly; the watcher publishes the resulting aggregate changes.
