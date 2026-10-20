"""Strict filename-driven local roster imports. No network requests."""
import hashlib
import re
from datetime import date
from pathlib import Path

EXTENSIONS = {'.csv', '.tsv', '.txt', '.xls', '.xlsx', '.pdf', '.zip'}
PATTERN = re.compile(r'(?P<county>[a-z]+(?:-[a-z]+)*)__'
                     r'(?P<election>\d{4}-\d{2}-\d{2})__'
                     r'(?P<asof>\d{4}-\d{2}-\d{2})__'
                     r'(?P<method>in-person|mail|mixed)__'
                     r'(?P<coverage>daily|cumulative|archive)'
                     r'(?:__r(?P<revision>[1-9]\d*))?\.(?P<extension>csv|tsv|txt|xls|xlsx|pdf|zip)$')


def scan(folder, settings):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    counties = {c.lower().replace(' ', '-'): c for c in settings['full_counties'] + settings['split_counties']}
    result, keys = {}, set()
    for path in sorted(folder.rglob('*')):
        if path.relative_to(folder).parts[0] == 'scores':
            continue
        if not path.is_file() or any(p.startswith('.') for p in path.relative_to(folder).parts):
            continue
        if path.suffix.lower() not in EXTENSIONS:
            continue  # readmes and browser temporary downloads are not rosters
        if path.is_symlink():
            raise ValueError('Symlinked voter files are not supported.')
        match = PATTERN.fullmatch(path.name)
        if not match:
            raise ValueError(f'Rename {path.name}: COUNTY__ELECTION-DATE__REPORT-DATE__METHOD__COVERAGE[__r2].ext')
        item = match.groupdict()
        if item['county'] not in counties:
            raise ValueError(f'Unknown target county in {path.name}. Use lowercase hyphenated county names.')
        if item['election'] != settings['election_date']:
            raise ValueError(f'Wrong election date in {path.name}.')
        date.fromisoformat(item['asof'])
        date.fromisoformat(item['election'])
        if item['method'] == 'mixed' and (item['coverage'] != 'archive' or item['extension'] != 'zip'):
            raise ValueError('mixed is supported only for complete ZIP archives; use separate methods for daily files.')
        if item['coverage'] == 'archive' and item['extension'] != 'zip':
            raise ValueError('archive requires a ZIP file.')
        if item['extension'] == 'zip' and item['coverage'] != 'archive':
            raise ValueError('ZIP files must use archive coverage.')
        item['county'] = counties[item['county']]
        item['revision'] = int(item['revision'] or 1)
        key = tuple(item[k] for k in ('county', 'asof', 'method', 'coverage', 'revision'))
        if key in keys:
            raise ValueError('Two files have the same county/date/method/coverage/revision. Remove one or give its correction __r2.')
        keys.add(key)
        item['path'] = str(path)
        result.setdefault(item['county'], []).append(item)
    return result


def read_county(files, source, parse_document, parse_travis_archive):
    """Latest snapshots replace older ones; only later daily files supplement them."""
    selected_by_method, notes = {}, []
    for method in ('in-person', 'mail'):
        candidates = [f for f in files if f['method'] in {method, 'mixed'}]
        snapshots = [f for f in candidates if f['coverage'] != 'daily']
        baseline = max(snapshots, key=lambda f: (f['asof'], f['revision'])) if snapshots else None
        if baseline:
            tied = [f for f in snapshots if (f['asof'], f['revision']) == (baseline['asof'], baseline['revision'])]
            if len(tied) > 1:
                raise ValueError(f'Ambiguous {method} snapshot: give the authoritative replacement a higher revision.')
        dailies = {}
        for item in candidates:
            if item['coverage'] != 'daily' or (baseline and item['asof'] <= baseline['asof']):
                continue
            old = dailies.get(item['asof'])
            if not old or item['revision'] > old['revision']:
                dailies[item['asof']] = item
        selected_by_method[method] = ([baseline] if baseline else []) + [dailies[k] for k in sorted(dailies)]
    selected = {f['path']: f for group in selected_by_method.values() for f in group}
    cache, hashes = {}, []
    for path, item in sorted(selected.items()):
        body = Path(path).read_bytes()
        if len(body) > 150 * 1024 * 1024:
            raise ValueError('A local roster exceeds the 150 MiB limit.')
        hashes.append(Path(path).name + ':' + hashlib.sha256(body).hexdigest())
        if source['county'] == 'Travis' and item['method'] == 'mixed':
            rows, messages = parse_travis_archive(body, source)
            notes.extend(messages)
        else:
            child = dict(source, default_mode='auto' if item['method'] == 'mixed' else 'in_person' if item['method'] == 'in-person' else item['method'])
            fallback = item['asof'] if item['coverage'] == 'daily' else None
            # Pass a date-free context so a cumulative snapshot date is never
            # mistaken for an individual vote date by a county PDF adapter.
            context = 'in-person-roster' if item['method'] == 'in-person' else 'mail-roster'
            rows = parse_document(body, context + Path(path).suffix.lower(), child, fallback)
        if any(r['vote_date'] and r['vote_date'] > item['asof'] for r in rows):
            raise ValueError(f'Roster contains a date after its filename report date: {Path(path).name}')
        if item['coverage'] == 'daily' and any(r['vote_date'] != item['asof'] for r in rows):
            raise ValueError(f'Daily roster contains dates different from its filename: {Path(path).name}')
        if item['method'] != 'mixed':
            expected = 'in_person' if item['method'] == 'in-person' else 'mail'
            if any(r['mode'] != expected for r in rows):
                raise ValueError('Voting method in a roster disagrees with its filename.')
        cache[path] = rows
    records = []
    for method, group in selected_by_method.items():
        normalized_method = 'in_person' if method == 'in-person' else 'mail'
        for item in group:
            records.extend(dict(r) for r in cache[item['path']] if r['mode'] == normalized_method)
    unique, repeated_reports = {}, set()
    for row in records:
        old = unique.get(row['vuid'])
        if old:
            if any(old[k] and row[k] and old[k] != row[k] for k in ('precinct', 'district', 'mode')):
                raise ValueError('Overlapping local rosters disagree on a voter precinct, district or method.')
            if old['vote_date'] and row['vote_date'] and old['vote_date'] != row['vote_date']:
                if old.get('date_basis') == 'vote_date' and row.get('date_basis') == 'vote_date':
                    raise ValueError('Overlapping rosters have conflicting explicit vote dates.')
                if row.get('date_basis') == 'vote_date':
                    old['vote_date'], old['date_basis'] = row['vote_date'], 'vote_date'
                elif old.get('date_basis') != 'vote_date':
                    old['vote_date'] = min(old['vote_date'], row['vote_date'])
                repeated_reports.add(row['vuid'])
            for key in ('precinct', 'district', 'vote_date'):
                if not old[key]:
                    old[key] = row[key]
            for key in ('first_name', 'last_name', 'full_name'):
                if not old.get(key):
                    old[key] = row.get(key, '')
        else:
            unique[row['vuid']] = row
    if not unique:
        raise ValueError('No voter records parsed from the selected local files; zero is not inferred.')
    if repeated_reports:
        notes.append(f'{len(repeated_reports)} repeated voter(s) counted once at their earliest daily report date.')
    notes.append(f'Folder import: {len(selected)} selected file(s); latest cumulative/archive snapshots replace older snapshots and earlier daily files.')
    return list(unique.values()), hashlib.sha256('|'.join(hashes).encode()).hexdigest(), notes


def stamp(folder):
    """A cheap polling signature; content hashes are computed on ingestion."""
    folder = Path(folder)
    return tuple(sorted((str(p.relative_to(folder)), p.stat().st_size, p.stat().st_mtime_ns)
                        for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS
                        and not any(part.startswith('.') for part in p.relative_to(folder).parts)))
