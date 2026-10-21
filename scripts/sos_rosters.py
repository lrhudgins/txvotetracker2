"""Stream official SOS statewide exports into transient county record lists."""
import csv
import hashlib
import re
from datetime import date

ORIGINAL = re.compile(r'STATEWIDE\.(?P<year>\d{4}) NOVEMBER GENERAL ELECTION\.EarlyVoting\.'
                      r'(?P<month>\d{1,2})_(?P<day>\d{1,2})_(?P<reportyear>\d{4})\.csv', re.I)
NAMED = re.compile(r'statewide__(?P<election>\d{4}-\d{2}-\d{2})__'
                   r'(?P<asof>\d{4}-\d{2}-\d{2})__mixed__(?P<coverage>daily|cumulative)'
                   r'(?:__r(?P<revision>[1-9]\d*))?\.csv')


def identify(name, settings):
    item = NAMED.fullmatch(name)
    if item:
        info = item.groupdict()
        if info['election'] != settings['election_date']:
            raise ValueError('Statewide roster filename specifies the wrong election.')
        date.fromisoformat(info['asof'])
        return dict(info, revision=int(info['revision'] or 1), method='mixed', extension='csv')
    item = ORIGINAL.fullmatch(name)
    if not item:
        return None
    election = date.fromisoformat(settings['election_date'])
    if int(item['year']) != election.year or election.month != 11 or item['reportyear'] != item['year']:
        raise ValueError('SOS statewide roster filename does not match the configured November election.')
    report = date(int(item['reportyear']), int(item['month']), int(item['day'])).isoformat()
    return dict(election=election.isoformat(), asof=report, coverage='daily',
                revision=1, method='mixed', extension='csv')


def load(path, settings, asof):
    """Read once per scan, discard non-target counties, never write raw splits.

    Dates are observations, not independently verified individual vote dates.
    Per-county errors are returned so one bad county cannot block the others.
    """
    from update import standardize, norm
    allowed = {norm(c): c for c in settings['full_counties'] + settings['split_counties']}
    if path.stat().st_size > 150 * 1024 * 1024:
        raise ValueError('Statewide roster exceeds the 150 MiB input limit.')
    with path.open('rb') as f:
        prefix = f.read(4)
    encoding = 'utf-16' if prefix.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    raw, errors = {}, {}
    with path.open(encoding=encoding, newline='') as f:
        reader = csv.DictReader(f)
        try:
            headers = {norm(h): h for h in reader.fieldnames or []}
        except csv.Error:
            raise ValueError('SOS CSV header could not be read; download the original CSV export.') from None
        required = ('county', 'votername', 'idvoter', 'votingmethod', 'precinct')
        if len(headers) != len(reader.fieldnames or []) or not all(k in headers for k in required):
            raise ValueError('SOS export needs unique COUNTY, VOTER_NAME, ID_VOTER, VOTING_METHOD, and PRECINCT columns.')
        try:
            for row in reader:
                county = allowed.get(norm(row.get(headers['county'], '')))
                if not county:
                    continue
                if None in row or any(v is None for v in row.values()):
                    errors[county] = 'A target-county SOS row has missing or extra fields; county withheld.'
                    continue
                raw.setdefault(county, []).append(row)
        except csv.Error:
            raise ValueError('SOS CSV structure could not be read; check the original export.') from None
    result = {}
    for county in sorted(set(raw) | set(errors)):
        try:
            if county in errors:
                raise ValueError(errors[county])
            source = dict(county=county, default_mode='auto', columns_json='{}')
            records = standardize(raw[county], reader.fieldnames, source, 'SOS statewide roster', asof)
            result[county] = {'records': records, 'error': None}
        except ValueError as exc:
            result[county] = {'records': [], 'error': str(exc)}
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return result, digest.hexdigest()
