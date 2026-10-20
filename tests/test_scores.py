import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update as u
import precinct_scores as scores
import folder_inputs


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads((ROOT / 'config/settings.json').read_text())

    def write(self, root, name, rows, headers=('Prec', 'STID', 'Score', 'First')):
        folder = Path(root) / 'inbox/scores'; folder.mkdir(parents=True, exist_ok=True)
        with (folder / name).open('w', newline='') as f:
            writer = csv.writer(f); writer.writerow(headers); writer.writerows(rows)

    def publish(self, root):
        errors = scores.publish(Path(root), Path(root) / 'inbox', self.settings, '2026-10-20T12:00:00Z')
        return errors, json.loads((Path(root) / 'docs/data/precinct_scores.json').read_text())

    def test_mean_excludes_blanks_preserves_zero_and_publishes_no_identifiers(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp, 'travis__2026-10-20__scores.csv', [['101','1000000001','-100','PRIVATE NAME'],['101','1000000002','100','PRIVATE NAME'],['101','1000000003','','PRIVATE NAME'],['102','1000000004','0','PRIVATE NAME']])
            errors, data = self.publish(temp)
            self.assertFalse(errors)
            self.assertEqual(data['rows'][0]['mean_score'], 0)
            self.assertEqual(data['rows'][0]['scored_count'], 2)
            self.assertEqual(data['rows'][0]['missing_score_count'], 1)
            self.assertEqual(data['rows'][1]['mean_score'], 0)
            public = json.dumps(data)
            self.assertNotIn('PRIVATE NAME', public)
            self.assertNotIn('1000000001', public)

    def test_filename_can_supply_precinct_and_same_voter_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp, 'travis__2026-10-20__precinct-101__scores.csv', [['','1000000001','50',''],['','1000000001','50','']])
            errors, data = self.publish(temp)
            self.assertFalse(errors)
            self.assertEqual(data['rows'][0]['precinct'], '101')
            self.assertEqual(data['rows'][0]['scored_count'], 1)
            self.assertEqual(data['rows'][0]['mean_score'], 50)

    def test_invalid_score_preserves_previous_mean_as_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            name='travis__2026-10-20__precinct-101__scores.csv'
            self.write(temp, name, [['101','1000000001','20','']]);self.publish(temp)
            for invalid in ('101','NaN','inf','unknown'):
                self.write(temp, name, [['101','1000000001',invalid,'']])
                errors, data = self.publish(temp)
                self.assertTrue(errors)
                self.assertEqual(data['rows'][0]['mean_score'], 20)
                self.assertEqual(data['rows'][0]['status'], 'stale')

    def test_correction_replaces_prior_snapshot_and_missing_data_stays_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp, 'travis__2026-10-20__precinct-101__scores.csv', [['101','1000000001','invalid','']])
            self.write(temp, 'travis__2026-10-20__precinct-101__scores__r2.csv', [['101','1000000002','','']])
            errors, data = self.publish(temp)
            self.assertFalse(errors)
            self.assertIsNone(data['rows'][0]['mean_score'])
            self.assertEqual(data['rows'][0]['status'], 'missing')

    def test_new_countywide_snapshot_removes_old_precinct_and_county_keys_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp, 'travis__2026-10-19__scores.csv', [['101','1000000001','30','']])
            self.write(temp, 'travis__2026-10-20__scores.csv', [['102','1000000002','40','']])
            self.write(temp, 'brazos__2026-10-20__scores.csv', [['102','1000000003','-40','']])
            errors, data = self.publish(temp)
            self.assertFalse(errors)
            self.assertEqual({(r['county'],r['precinct'],r['mean_score']) for r in data['rows']}, {('Travis','102',40),('Brazos','102',-40)})

    def test_score_folder_does_not_enter_turnout_roster_import(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp, 'travis__2026-10-20__scores.csv', [['101','1000000001','30','']])
            self.assertEqual(folder_inputs.scan(Path(temp)/'inbox', self.settings), {})
            self.assertTrue(folder_inputs.stamp(Path(temp)/'inbox'))

    def test_brazos_second_page_does_not_need_repeated_header(self):
        pages = [SimpleNamespace(extract_text=lambda: 'Selected Election Name Vuid Precinct\n2026 GENERAL/SPECIAL TEST 1000000001 33'),
                 SimpleNamespace(extract_text=lambda: '2026 GENERAL/SPECIAL TEST 1000000002 34')]
        pdf = MagicMock(); pdf.__enter__.return_value.pages = pages
        with patch('pdfplumber.open', return_value=pdf):
            rows = u.parse_document(b'%PDF fixture', 'daily.pdf', {'county':'Brazos','adapter':'brazos_index','default_mode':'in_person','columns_json':'{}'}, '2026-10-19')
            self.assertEqual(len(rows), 2)
        pages[1] = SimpleNamespace(extract_text=lambda: '')
        with patch('pdfplumber.open', return_value=pdf):
            with self.assertRaisesRegex(ValueError, 'no readable text'):
                u.parse_document(b'%PDF fixture', 'daily.pdf', {'county':'Brazos','adapter':'brazos_index','default_mode':'in_person','columns_json':'{}'}, '2026-10-19')
