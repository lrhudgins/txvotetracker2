"""Aggregate supplied Score values; never infer scores or export voter-level data."""
import csv
import json
import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

NAME = re.compile(r'(?P<county>[a-z]+(?:-[a-z]+)*)__'
                  r'(?P<asof>\d{4}-\d{2}-\d{2})__'
                  r'(?:precinct-(?P<precinct>[A-Za-z0-9.-]+)__)?scores'
                  r'(?:__r(?P<revision>[1-9]\d*))?\.csv$')


def pct(value):
    text = re.sub(r'\.0$', '', str(value or '').strip().upper())
    return str(int(text)) if text.isdigit() else text


def norm(value):
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


def read_file(path, info):
    groups, seen = defaultdict(list), {}
    empty_rows, unassigned_rows, duplicates = 0, 0, 0
    with path.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = {norm(h): h for h in (reader.fieldnames or [])}
        if 'score' not in headers:
            raise ValueError('Score CSV needs a Score column.')
        prec_col = next((headers[n] for n in ('prec', 'precinct', 'pct') if n in headers), None)
        id_cols = [headers[n] for n in ('stid', 'vuid', 'voterid', 'vanid') if n in headers]
        for row in reader:
            if not any(str(v or '').strip() for v in row.values()):
                empty_rows += 1
                continue
            precinct = pct(row.get(prec_col, '')) or info.get('precinct')
            if info.get('precinct') and precinct != info['precinct']:
                raise ValueError('A Prec value disagrees with the precinct in its filename.')
            raw = str(row.get(headers['score'], '') or '').strip()
            if not precinct:
                if raw:
                    raise ValueError('A populated Score needs Prec/Precinct or a precinct in the filename.')
                unassigned_rows += 1
                continue
            value = None
            if raw:
                try:
                    value = float(raw)
                except ValueError:
                    raise ValueError('A Score value is not numeric.') from None
                if not math.isfinite(value) or not -100 <= value <= 100:
                    raise ValueError('Score values must be finite numbers between -100 and 100.')
            identifier = next(((('van' if norm(col) == 'vanid' else 'state'), str(row.get(col, '') or '').strip())
                               for col in id_cols if str(row.get(col, '') or '').strip()), None)
            if identifier:
                if identifier in seen:
                    if seen[identifier] != (precinct, value):
                        raise ValueError('A duplicate voter identifier has conflicting precincts or scores.')
                    duplicates += 1
                    continue
                seen[identifier] = precinct, value
            groups[precinct].append(value)
    if info.get('precinct') and not groups:
        groups[info['precinct']] = []
    return groups, {'blank_rows_ignored': empty_rows, 'unassigned_blank_scores': unassigned_rows,
                    'duplicate_rows_ignored': duplicates}


def collect(folder, settings):
    folder = Path(folder)
    allowed = {c.lower().replace(' ', '-'): c for c in settings['full_counties'] + settings['split_counties']}
    by_county = defaultdict(list)
    if folder.exists():
        for path in sorted(folder.rglob('*.csv')):
            if any(p.startswith('.') for p in path.relative_to(folder).parts):
                continue
            if path.is_symlink():
                raise ValueError('Symlinked score inputs are not supported.')
            match = NAME.fullmatch(path.name)
            if not match or match['county'] not in allowed:
                raise ValueError('Rename score files: county__YYYY-MM-DD__[precinct-101__]scores[__r2].csv')
            info = match.groupdict()
            date.fromisoformat(info['asof'])
            info.update(county=allowed[info['county']], revision=int(info['revision'] or 1), path=path)
            if info['precinct']:
                info['precinct'] = pct(info['precinct'])
            by_county[info['county']].append(info)
    return by_county


def publish(root, inbox, settings, updated_at):
    output = Path(root) / 'docs/data/precinct_scores.json'
    previous = json.loads(output.read_text()) if output.exists() else {'rows': []}
    errors, results, reports = [], [], []
    try:
        by_county = collect(Path(inbox) / 'scores', settings)
    except (ValueError, OSError) as exc:
        by_county = None
        errors.append(str(exc))
    if by_county is None:
        results = [dict(row, status='stale') for row in previous.get('rows', [])]
    else:
        for county, files in by_county.items():
            try:
                broad = [i for i in files if not i['precinct']]
                baseline = max(broad, key=lambda i: (i['asof'], i['revision'])) if broad else None
                if baseline and sum((i['asof'], i['revision']) == (baseline['asof'], baseline['revision']) for i in broad) > 1:
                    raise ValueError('Multiple countywide score snapshots have the same date/revision.')
                specific = {}
                for info in files:
                    if not info['precinct']:
                        continue
                    old = specific.get(info['precinct'])
                    version = info['asof'], info['revision']
                    if old and version == (old['asof'], old['revision']):
                        raise ValueError('Multiple precinct score files have the same date/revision.')
                    if not old or version > (old['asof'], old['revision']):
                        specific[info['precinct']] = info
                selected = {}
                for info in ([baseline] if baseline else []) + list(specific.values()):
                    version = info['asof'], info['revision']
                    if baseline and info['precinct'] and version < (baseline['asof'], baseline['revision']):
                        continue
                    groups, report = read_file(info['path'], info)
                    for precinct, values in groups.items():
                        old = selected.get(precinct)
                        if old and old[0] == version:
                            raise ValueError('Overlapping score files have the same date/revision; remove one or use __r2.')
                        if old and old[0] > version:
                            continue
                        selected[precinct] = version, values, info
                    reports.append(dict(county=county, file=info['path'].name, **report))
                for precinct, (version, values, info) in sorted(selected.items()):
                    numeric = [v for v in values if v is not None]
                    results.append({'county': county, 'precinct': precinct,
                                    'mean_score': round(math.fsum(numeric) / len(numeric), 6) if numeric else None,
                                    'scored_count': len(numeric), 'missing_score_count': len(values) - len(numeric),
                                    'as_of': info['asof'], 'status': 'ok' if numeric else 'missing'})
            except (ValueError, OSError, csv.Error) as exc:
                errors.append(f'{county}: {exc}')
                results.extend(dict(row, status='stale') for row in previous.get('rows', []) if row['county'] == county)
    payload = {'updated_at': updated_at, 'scale': [-100, 100], 'status': 'error' if errors else 'ok',
               'population': 'Rows supplied in score CSVs; not restricted to voters in the early-vote rosters.',
               'rows': results, 'diagnostics': reports, 'errors': errors}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
    csv_path = output.with_suffix('.csv')
    with csv_path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['county', 'precinct', 'mean_score', 'scored_count', 'missing_score_count', 'as_of', 'status'])
        writer.writeheader()
        writer.writerows(results)
    return errors
