import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update as u
import folder_inputs as folder
import local_update as local


class FolderInputTests(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads((ROOT / 'config/settings.json').read_text())
        self.source = {'id': 'lee', 'county': 'Lee', 'adapter': 'roster', 'default_mode': 'auto', 'columns_json': '{}'}

    def write(self, root, day, kind='daily', ids=('1000000001',), revision='', method='in-person'):
        path = Path(root) / f'lee__2026-11-03__2026-10-{day:02d}__{method}__{kind}{revision}.csv'
        path.write_text('VUID,Precinct\n' + ''.join(uid + ',1\n' for uid in ids))
        return path

    def read(self, root):
        files = folder.scan(root, self.settings)['Lee']
        return folder.read_county(files, self.source, u.parse_document, u.parse_travis_archive)

    def test_cumulative_replaces_earlier_daily_and_new_daily_supplements(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp, 18, ids=('1000000009',))
            self.write(temp, 19, 'cumulative', ('1000000001', '1000000002'))
            self.write(temp, 20, ids=('1000000003',))
            rows, fingerprint, notes = self.read(temp)
            self.assertEqual({r['vuid'] for r in rows}, {'1000000001', '1000000002', '1000000003'})
            self.assertIsNone(next(r['vote_date'] for r in rows if r['vuid'] == '1000000001'))
            self.assertEqual(next(r['vote_date'] for r in rows if r['vuid'] == '1000000003'), '2026-10-20')

    def test_correction_revision_removes_superseded_records(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp, 19, ids=('1000000001', '1000000002'))
            self.write(temp, 19, ids=('1000000003',), revision='__r2')
            rows, _, _ = self.read(temp)
            self.assertEqual([r['vuid'] for r in rows], ['1000000003'])

    def test_repeated_voter_in_daily_reports_counts_once(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp, 19)
            self.write(temp, 20)
            rows, _, notes = self.read(temp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['vote_date'], '2026-10-19')
            self.assertTrue(any('repeated voter' in n for n in notes))

    def test_bad_name_or_wrong_election_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp, 'download.csv'); bad.write_text('VUID\n')
            with self.assertRaisesRegex(ValueError, 'Rename'):
                folder.scan(temp, self.settings)
            bad.unlink()
            bad = Path(temp, 'lee__2026-03-03__2026-10-19__mail__daily.csv'); bad.write_text('VUID\n')
            with self.assertRaisesRegex(ValueError, 'Wrong election'):
                folder.scan(temp, self.settings)

    def test_duplicate_pdf_and_csv_need_distinct_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            first = self.write(temp, 19)
            first.with_suffix('.pdf').write_bytes(b'%PDF test')
            with self.assertRaisesRegex(ValueError, 'same county'):
                folder.scan(temp, self.settings)

    def test_method_conflict_and_report_date_conflict_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write(temp, 19)
            path.write_text('VUID,Precinct,Vote Method\n1000000001,1,mail\n')
            with self.assertRaisesRegex(ValueError, 'method'):
                self.read(temp)
            path.write_text('VUID,Precinct,Date Voted\n1000000001,1,2026-10-20\n')
            with self.assertRaisesRegex(ValueError, 'after its filename'):
                self.read(temp)

    def test_folder_run_does_not_download_and_deletion_rebuilds_totals(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'config').mkdir()
            (root / 'config/settings.json').write_text(json.dumps(self.settings))
            (root / 'config/county_sources.csv').write_text('id,county,url,adapter,enabled,default_mode,columns_json,notes\nbrazos,Brazos,https://example.gov,roster,true,auto,{},test\n')
            inbox = root / 'inbox'; inbox.mkdir()
            path = self.write(inbox, 19)
            with patch.object(u, 'fetch', side_effect=AssertionError('Network must not be called')):
                self.assertEqual(u.run(root, inbox=inbox), 0)
                latest = json.loads((root / 'docs/data/latest.json').read_text())
                self.assertEqual(latest['reported_subtotal'], 1)
                path.unlink()
                self.assertEqual(u.run(root, inbox=inbox), 0)
                latest = json.loads((root / 'docs/data/latest.json').read_text())
                self.assertIsNone(latest['reported_subtotal'])

    def test_watcher_processes_one_stable_change(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(local, 'ROOT', Path(temp)), patch.object(local, 'stamp', return_value=(('test.csv', 1, 1),)), patch.object(local, 'publish_once', return_value=0) as publish, patch.object(local.time, 'sleep', side_effect=[None, KeyboardInterrupt]), patch.object(sys, 'argv', ['local_update.py', '--watch', '--push']):
                self.assertEqual(local.main(), 0)
                publish.assert_called_once_with(True, {}, Path(temp) / 'inbox')
