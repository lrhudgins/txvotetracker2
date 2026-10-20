import copy
import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update as u


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads((ROOT / 'config/settings.json').read_text())
        self.source = {'id': 'test', 'county': 'Travis', 'adapter': 'roster', 'default_mode': 'in_person', 'columns_json': '{}'}
        self.row = {'vuid': '1000000001', 'precinct': '101', 'district': 10, 'mode': 'in_person', 'vote_date': '2026-10-19'}

    def agg(self, rows, source=None, crosswalk=None):
        return u.aggregate(rows, source or self.source, self.settings, crosswalk or {}, '2026-10-20')

    def test_overlapping_daily_and_cumulative_rosters_deduplicate(self):
        result = self.agg([dict(self.row), dict(self.row), dict(self.row, vuid='1000000002')])
        self.assertEqual(result['total'], 2)

    def test_split_county_unknown_is_withheld_and_outside_is_excluded(self):
        result = self.agg([dict(self.row, district=None), dict(self.row, vuid='1000000002', district=37)])
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['unknown_district'], 1)
        self.assertEqual(result['outside_district'], 1)

    def test_full_county_and_verified_crosswalk_can_assign_residents(self):
        self.assertEqual(self.agg([dict(self.row, district=None)], dict(self.source, county='Brazos'))['total'], 1)
        self.assertEqual(self.agg([dict(self.row, district=None)], crosswalk={('Travis', '101'): 10})['total'], 1)

    def test_ambiguous_split_precinct_crosswalk_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, 'crosswalk.csv')
            path.write_text('county,precinct,congressional_district,verified_for_election,source_url\nTravis,101,10,2026-11-03,https://example.gov\nTravis,101,37,2026-11-03,https://example.gov\n')
            with self.assertRaises(ValueError):
                u.load_crosswalk(path, '2026-11-03')

    def test_election_day_and_old_election_records_excluded(self):
        result = self.agg([dict(self.row), dict(self.row, vuid='1000000002', mode='election_day', vote_date='2026-11-03'), dict(self.row, vuid='1000000003', vote_date='2026-03-03')])
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['excluded_period'], 2)

    def test_conflicting_duplicate_does_not_double_count(self):
        with self.assertRaises(ValueError):
            self.agg([dict(self.row), dict(self.row, precinct='102')])

    def test_generic_district_column_is_not_congressional(self):
        parsed = u.standardize([{'VUID': '1000000001', 'District': '10', 'Precinct': '001'}], ['VUID', 'District', 'Precinct'], self.source, 'early.csv')
        self.assertIsNone(parsed[0]['district'])
        self.assertEqual(parsed[0]['precinct'], '1')

    def test_csv_zip_auto_schema_and_mode(self):
        text = b'VUID,Precinct,Congressional District,Date Voted\n1000000001,001,10,10/19/2026\n'
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('EV_20261019.csv', text)
            z.writestr('EV_cumulative.csv', text)
        rows = u.parse_document(archive.getvalue(), 'rosters.zip', dict(self.source, default_mode='auto'))
        self.assertEqual(self.agg(rows)['total'], 1)

    def test_invalid_roster_row_fails_instead_of_silent_undercount(self):
        with self.assertRaises(ValueError):
            u.standardize([{'VUID': 'bad'}], ['VUID'], self.source, 'early.csv')

    def test_brazos_discovers_only_current_election_rosters(self):
        html = b'<h3>2026 General/Special Election</h3><ul><li><a href="a.pdf">10/19/2026 Roster (in person)</a></li><li><a href="b.pdf">10/16/2026 Roster (mail)</a></li></ul><h3>2026 Primary Runoff Election</h3><a href="old.pdf">5/26/2026 Roster (mail)</a>'
        files = u.brazos_files(html, 'https://example.gov/roster/')
        self.assertEqual(len(files), 2)
        self.assertEqual(files[0], ('https://example.gov/roster/a.pdf', 'in_person', '2026-10-19'))

    def test_rerun_replaces_snapshot_and_failure_preserves_last_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'config').mkdir()
            (root / 'config/settings.json').write_text(json.dumps(self.settings))
            (root / 'config/precinct_crosswalk.csv').write_text('county,precinct,congressional_district,verified_for_election,source_url\n')
            (root / 'config/county_sources.csv').write_text('id,county,url,adapter,enabled,default_mode,columns_json,notes\ntest,Travis,https://example.gov/roster.zip,roster,true,in_person,{},test\n')
            with patch.object(u, 'get_records', return_value=([self.row], 'same', [])):
                self.assertEqual(u.run(root), 0)
                self.assertEqual(u.run(root), 0)
            result = json.loads((root / 'docs/data/latest.json').read_text())
            self.assertEqual(result['reported_subtotal'], 1)
            with patch.object(u, 'get_records', side_effect=ValueError('source blocked')):
                self.assertEqual(u.run(root), 1)
            result = json.loads((root / 'docs/data/latest.json').read_text())
            self.assertEqual(result['reported_subtotal'], 1)
            self.assertEqual(next(c for c in result['counties'] if c['county'] == 'Travis')['status'], 'stale')
            public = ''.join(p.read_text() for p in (root / 'docs').rglob('*') if p.is_file())
            self.assertNotIn(self.row['vuid'], public)
            self.assertEqual(len(list((root / 'docs/data/history').glob('*.json'))), 1)

    def test_primary_reference_crosswalk_marks_assignments_provisional(self):
        cw = u.Crosswalk()
        cw['Travis', '101'] = 10
        cw.reference_keys.add(('Travis', '101'))
        result = self.agg([dict(self.row, district=None)], crosswalk=cw)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['provisional_assigned'], 1)

    def test_travis_corrected_workbook_replaces_original_and_skips_limited(self):
        from openpyxl import Workbook
        def excel(ids, day=19, kind='Early Vote'):
            book = Workbook(); sheet = book.active
            sheet.append(['Travis County ' + kind + ' Roster'])
            sheet.append([f'2026-10-{day:02d}'])
            sheet.append(['November 3, 2026 Joint General and Special Election'])
            sheet.append(['VUID', 'Last Name', 'First Name', 'PCT'])
            for uid in ids:
                sheet.append([uid, 'Synthetic', 'Test', '101'])
            data = io.BytesIO(); book.save(data); return data.getvalue()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('10.19.2026 Early Vote.xlsx', excel(['1000000001']))
            z.writestr('10.19.2026 Early Vote_UPDATED.xlsx', excel(['1000000001', '1000000002']))
            z.writestr('10.19.2026 Limited Ballot Roster.xlsx', b'not a regular roster')
            z.writestr('10.12.2026 Ballot by Mail.xlsx', excel(['1000000003'], 12, 'Ballot by Mail'))
            z.writestr('10.13.2026 Ballot by Mail.xlsx', excel(['1000000003'], 13, 'Ballot by Mail'))
        rows, notes = u.parse_travis_archive(archive.getvalue(), self.source)
        self.assertEqual(len(rows), 3)
        self.assertEqual(next(r['vote_date'] for r in rows if r['mode'] == 'mail'), '2026-10-12')
        self.assertTrue(any('corrected' in n for n in notes))
        self.assertTrue(any('limited-ballot' in n for n in notes))


if __name__ == '__main__':
    unittest.main()
