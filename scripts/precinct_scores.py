"""Match supplied scores to eligible early voters locally; publish aggregates only."""
import csv
import io
import json
import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from voter_matching import match_precincts

POPULATION = 'Matched CD-10 early voters in the 2026 rosters; scores are supplied, not inferred.'
POPULATION_VERSION = 'matched-early-voters-v1'

NAME = re.compile(r'(?P<county>[a-z]+(?:-[a-z]+)*)__'
                  r'(?P<asof>\d{4}-\d{2}-\d{2})__'
                  r'(?:(?:precinct-(?P<precinct>[A-Za-z0-9.-]+)|part-(?P<part>[a-z0-9]+(?:-[a-z0-9]+)*))__)?(?:(?P<scale>dnc)-)?scores'
                  r'(?:__r(?P<revision>[1-9]\d*))?\.(?:csv|tsv|txt)$')


def pct(value):
    text = re.sub(r'\.0$', '', str(value or '').strip().upper())
    return str(int(text)) if text.isdigit() else text


def norm(value):
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


def open_score_text(path):
    """VAN Standard Text is commonly UTF-16 TSV despite its .txt suffix."""
    body = path.read_bytes()
    if len(body) > 150 * 1024 * 1024:
        raise ValueError('A score input exceeds the 150 MiB limit.')
    if body.startswith((b'\xff\xfe', b'\xfe\xff')):
        encoding = 'utf-16'
    elif b'\x00' in body[:256]:
        encoding = 'utf-16-be' if body[:256:2].count(b'\x00') > body[1:256:2].count(b'\x00') else 'utf-16-le'
    else:
        encoding = 'utf-8-sig'
    try:
        text = body.decode(encoding)
    except UnicodeError:
        if encoding != 'utf-8-sig':
            raise ValueError('Score text encoding is invalid; export UTF-8 or UTF-16.') from None
        try:
            text = body.decode('cp1252')
        except UnicodeError:
            raise ValueError('Score text encoding is invalid; export UTF-8 or UTF-16.') from None
    return io.StringIO(text, newline='')


def read_file(path, info):
    groups, seen = defaultdict(list), {}
    empty_rows, unassigned_rows, duplicates, incomplete_rows, unidentifiable_rows = 0, 0, 0, 0, 0
    dnc = info.get('scale') == 'dnc'
    with open_score_text(path) as f:
        first_line = f.readline(); f.seek(0)
        # Choose using the header, so commas inside street addresses cannot
        # change the interpretation of an otherwise tab-delimited export.
        delimiter = '\t' if '\t' in first_line else '|' if '|' in first_line else ';' if ';' in first_line and ',' not in first_line else ','
        reader = csv.DictReader(f, delimiter=delimiter)
        headers = {norm(h): h for h in (reader.fieldnames or [])}
        if len(headers) != len(reader.fieldnames or []):
            raise ValueError('Score input has duplicate column names.')
        dnc_fields = [headers[n] for n in ('26demsupport', 'dncdemsupport', 'dncdemocraticsupport', 'dncscore') if n in headers]
        if dnc:
            if len(dnc_fields) > 1:
                raise ValueError('Multiple DNC support fields found; keep one authoritative support column.')
            score_col = dnc_fields[0] if dnc_fields else headers.get('score')
            if not score_col:
                raise ValueError('DNC input needs 26:_Dem_Support, DNC Score, or Score. Turnout/GOTV/education fields are not support scores.')
        else:
            score_col = headers.get('score')
            if not score_col:
                raise ValueError('Score input needs a Score column. For VAN Democratic support on 0–100, use dnc-scores in the filename.')
        prec_col = next((headers[n] for n in ('prec', 'precinct', 'pct', 'precinctname') if n in headers), None)
        id_cols = [headers[n] for n in ('stid', 'vuid', 'voterid', 'vanid', 'voterfilevanid') if n in headers]
        name_cols = {key: next((headers[n] for n in aliases if n in headers), None)
                     for key, aliases in {
                         'first_name': ('first', 'firstname', 'givenname'),
                         'last_name': ('last', 'lastname', 'surname'),
                         'middle_name': ('middle', 'middlename'),
                         'suffix': ('suffix', 'namesuffix'),
                         # In this export, Name is the street name, not a voter.
                         'full_name': ('fullname', 'votername')}.items()}
        if not (any(norm(c) not in {'vanid', 'voterfilevanid'} for c in id_cols)
                or (name_cols['first_name'] and name_cols['last_name']) or name_cols['full_name']):
            raise ValueError('Score input needs STID/VUID or FirstName and LastName columns; VAN ID alone cannot match county rosters.')
        for row in reader:
            if None in row:
                raise ValueError('Score input has extra fields; check its delimiter and quoting.')
            if any(v is None for v in row.values()):
                incomplete_rows += 1
                continue  # visibly report truncated rows; never fabricate values
            if not any(str(v or '').strip() for v in row.values()):
                empty_rows += 1
                continue
            precinct = pct(row.get(prec_col, '')) or info.get('precinct')
            if info.get('precinct') and precinct != info['precinct']:
                raise ValueError('A Prec value disagrees with the precinct in its filename.')
            raw = str(row.get(score_col, '') or '').strip()
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
                lower = 0 if dnc else -100
                if not math.isfinite(value) or not lower <= value <= 100:
                    raise ValueError('DNC support must be finite and between 0 and 100.' if dnc else 'Score values must be finite numbers between -100 and 100.')
                if dnc:
                    value = 2 * value - 100
            identifier = next(((('van' if norm(col) in {'vanid', 'voterfilevanid'} else 'state'), str(row.get(col, '') or '').strip())
                               for col in id_cols if str(row.get(col, '') or '').strip()), None)
            vuid = identifier[1] if identifier and identifier[0] == 'state' else ''
            vuid = re.sub(r'\.0$', '', vuid)
            if vuid and not re.fullmatch(r'\d{10}', vuid):
                raise ValueError('STID/VUID must be a ten-digit Texas state voter ID; VanId is a separate identifier.')
            person = {'precinct': precinct, 'score': value, 'vuid': vuid,
                      'vanid': next((str(row.get(col, '') or '').strip() for col in id_cols
                                     if norm(col) in {'vanid', 'voterfilevanid'} and str(row.get(col, '') or '').strip()), ''),
                      **{k: str(row.get(col, '') or '').strip() for k, col in name_cols.items()}}
            if value is not None and not (vuid or (person['first_name'] and person['last_name']) or person['full_name']):
                unidentifiable_rows += 1
                continue  # a VAN ID cannot substitute for a state voter ID
            if identifier:
                if identifier in seen:
                    if seen[identifier] != (precinct, value):
                        raise ValueError('A duplicate voter identifier has conflicting precincts or scores.')
                    duplicates += 1
                    continue
                seen[identifier] = precinct, value
            groups[precinct].append(person)
    if info.get('precinct') and not groups:
        groups[info['precinct']] = []
    return groups, {'blank_rows_ignored': empty_rows, 'unassigned_blank_scores': unassigned_rows,
                    'duplicate_rows_ignored': duplicates,
                    'incomplete_rows_ignored': incomplete_rows,
                    'unidentifiable_rows_ignored': unidentifiable_rows,
                    'input_scale': 'DNC 0–100' if dnc else 'Native -100–100',
                    'score_conversion': '2 * score - 100' if dnc else 'none'}


def collect(folder, settings):
    folder = Path(folder)
    allowed = {c.lower().replace(' ', '-'): c for c in settings['full_counties'] + settings['split_counties']}
    by_county = defaultdict(list)
    if folder.exists():
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.suffix.lower() not in {'.csv', '.tsv', '.txt'}:
                continue
            if any(p.startswith('.') for p in path.relative_to(folder).parts):
                continue
            if path.is_symlink():
                raise ValueError('Symlinked score inputs are not supported.')
            match = NAME.fullmatch(path.name)
            if not match or match['county'] not in allowed:
                raise ValueError('Rename score inputs: county__YYYY-MM-DD__[precinct-101__ or part-01__][dnc-]scores[__r2].csv (TXT/TSV also supported).')
            info = match.groupdict()
            date.fromisoformat(info['asof'])
            info.update(county=allowed[info['county']], revision=int(info['revision'] or 1), path=path)
            if info['precinct']:
                info['precinct'] = pct(info['precinct'])
            by_county[info['county']].append(info)
    return by_county


def publish(root, inbox, settings, updated_at, voted_by_county=None, failed_counties=None):
    output = Path(root) / 'docs/data/precinct_scores.json'
    previous = json.loads(output.read_text()) if output.exists() else {'rows': []}
    # Old all-uploaded-voter means must never masquerade as early-voter means.
    prior_rows = previous.get('rows', []) if previous.get('population_version') == POPULATION_VERSION else []
    voted_by_county = voted_by_county or {}
    failed_counties = failed_counties or set()
    errors, results, reports = [], [], []
    try:
        by_county = collect(Path(inbox) / 'scores', settings)
    except (ValueError, OSError) as exc:
        by_county = None
        errors.append(str(exc))
    if by_county is None:
        results = [dict(row, status='stale') for row in prior_rows]
    else:
        for county, files in by_county.items():
            try:
                if county in failed_counties:
                    raise ValueError('Roster import failed; matched scores cannot be refreshed.')
                broad = [i for i in files if not i['precinct']]
                batch_date = max(i['asof'] for i in broad) if broad else None
                batch = [i for i in broad if i['asof'] == batch_date]
                if any(i.get('part') for i in batch) and any(not i.get('part') for i in batch):
                    raise ValueError('Do not mix complete countywide files and part files for the same snapshot date. Remove the superseded input.')
                parts = {}
                for info in batch:
                    key = info.get('part') or '__complete__'
                    old = parts.get(key)
                    if old and old['revision'] == info['revision']:
                        raise ValueError('Duplicate county part/date/revision or countywide snapshot. Use a distinct part label or __r2 for a correction.')
                    if not old or info['revision'] > old['revision']:
                        parts[key] = info
                baselines = list(parts.values())
                baseline = max(baselines, key=lambda i: (i['asof'], i['revision'])) if baselines else None
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
                for info in baselines + list(specific.values()):
                    version = info['asof'], info['revision']
                    if baseline and info['precinct'] and version < (baseline['asof'], baseline['revision']):
                        continue
                    groups, report = read_file(info['path'], info)
                    for precinct, values in groups.items():
                        old = selected.get(precinct)
                        if old and info.get('part') and old[2].get('part'):
                            # Parts are chunks of one county snapshot. Sharing
                            # a precinct is expected; combine its voter records.
                            selected[precinct] = max(old[0], version), old[1] + values, info
                            continue
                        if old and old[0] == version:
                            raise ValueError('Overlapping score files have the same date/revision; remove one or use __r2.')
                        if old and old[0] > version:
                            continue
                        selected[precinct] = version, values, info
                    reports.append(dict(county=county, **report))
                score_rows, seen_ids = [], {}
                for version, values, info in selected.values():
                    for person in values:
                        identities = [(kind, person[field]) for kind, field in (('state', 'vuid'), ('van', 'vanid')) if person.get(field)]
                        existing = [seen_ids[key] for key in identities if key in seen_ids]
                        if existing:
                            old = existing[0]
                            if any(record is not old for record in existing) or (old['score'], old['precinct']) != (person['score'], person['precinct']) or any(old.get(field) and person.get(field) and old[field] != person[field] for field in ('vuid', 'vanid')):
                                raise ValueError('A voter ID appears in selected score files with conflicting precincts, scores, or identifiers.')
                            for key in identities:
                                seen_ids[key] = old
                            for field in ('vuid', 'vanid'):
                                if not old.get(field):
                                    old[field] = person.get(field, '')
                            continue
                        score_rows.append(person)
                        for key in identities:
                            seen_ids[key] = person
                if county not in voted_by_county:
                    reports.append({'county': county, 'status': 'waiting_for_roster', 'score_records': len(score_rows)})
                    continue
                matched = match_precincts(voted_by_county[county], score_rows)
                for precinct, group in sorted(matched.items()):
                    values = group.pop('values')
                    numeric = [v for v in values if v is not None]
                    asof = selected[precinct][2]['asof'] if precinct in selected else max(i['asof'] for i in files)
                    results.append({'county': county, 'precinct': precinct,
                                    'mean_score': round(math.fsum(numeric) / len(numeric), 6) if numeric else None,
                                    'scored_count': len(numeric), 'missing_score_count': len(values) - len(numeric),
                                    **group, 'as_of': asof, 'status': 'ok' if numeric else 'missing'})
            except (ValueError, OSError, csv.Error) as exc:
                errors.append(f'{county}: {exc}')
                results.extend(dict(row, status='stale') for row in prior_rows if row['county'] == county)
    payload = {'updated_at': updated_at, 'scale': [-100, 100], 'status': 'error' if errors else 'ok',
               'population': POPULATION, 'population_version': POPULATION_VERSION,
               'rows': results, 'diagnostics': reports, 'errors': errors}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
    csv_path = output.with_suffix('.csv')
    with csv_path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['county', 'precinct', 'mean_score', 'scored_count', 'missing_score_count',
                                             'early_voter_count', 'matched_count', 'id_match_count', 'name_match_count',
                                             'unmatched_count', 'ambiguous_count', 'identifier_conflict_count', 'as_of', 'status'])
        writer.writeheader()
        writer.writerows(results)
    return errors
