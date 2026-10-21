"""Synthetic transport fixtures; no network or real voter identities."""
import base64
import gzip
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sos_download_payload as payload
import sos_rosters
import test_statewide_refresh as fixtures
CSV = fixtures.CSV
import refresh_statewide as refresh


class PayloadTests(unittest.TestCase):
    def test_supported_envelopes(self):
        encoded = base64.b64encode(CSV).decode()
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, 'w') as archive:
            archive.writestr('report.csv', CSV)
        variants = [CSV, gzip.compress(CSV), zipped.getvalue(),
                    json.dumps(CSV.decode()).encode(),
                    json.dumps({'unknown': {'nested': CSV.decode()}}).encode(),
                    json.dumps({'unknown': encoded}).encode(),
                    json.dumps({'unknown': 'data:text/csv;base64,' + encoded}).encode(),
                    gzip.compress(json.dumps({'unknown': encoded}).encode()),
                    json.dumps({'unknown': base64.b64encode(gzip.compress(CSV)).decode()}).encode(),
                    json.dumps({'unknown': list(CSV)}).encode(),
                    json.dumps({'unknown': base64.b64encode(zipped.getvalue()).decode()}).encode(),
                    json.dumps({'a': encoded, 'b': encoded}).encode(),
                    b'\xff\xfe' + CSV.decode().encode('utf-16-le')]
        for value in variants:
            with self.subTest(size=len(value)):
                self.assertTrue(payload.csv_header(payload.decode(value)))

    def test_invalid_and_ambiguous_envelopes(self):
        variants = [b'<html>PRIVATE</html>', b'{invalid',
                    json.dumps({'file': 'A' * 140000}).encode(),
                    json.dumps({'url': 'https://example.test/private.csv'}).encode(),
                    json.dumps({'a': CSV.decode(), 'b': CSV.decode().replace('69', '70')}).encode()]
        for value in variants:
            with self.subTest(size=len(value)), self.assertRaises(ValueError) as error:
                payload.decode(value)
            self.assertNotIn('PRIVATE', str(error.exception))

    def test_gzip_size_limit(self):
        with patch.object(payload, 'MAX_BYTES', 100):
            with self.assertRaises(ValueError):
                payload.decode(gzip.compress(b'A' * 101))

    def test_giant_header_is_controlled(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'bad.csv'
            path.write_text('A' * 140000)
            with self.assertRaisesRegex(ValueError, 'header'):
                sos_rosters.load(path, {'full_counties': ['Brazos'], 'split_counties': []}, '2026-10-20')

    def test_json_download_integration_and_failed_decode_preserves_file(self):
        fixture = fixtures.ScheduledRefreshTests()
        fixture.setUp()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for body, valid in [(json.dumps({'unknown': base64.b64encode(CSV).decode()}).encode(), True),
                                (json.dumps({'unknown': 'A' * 140000}).encode(), False)]:
                with patch.object(refresh.shutil, 'which', return_value='/usr/bin/curl'), patch.object(refresh.subprocess, 'run', side_effect=fixture.curl(body)):
                    if valid:
                        self.assertEqual(refresh.download(fixture.day, folder, fixture.settings), 'downloaded')
                    else:
                        with self.assertRaises(ValueError):
                            refresh.download(fixture.day, folder, fixture.settings)
                self.assertEqual((folder / refresh.filename(fixture.day)).read_bytes(), CSV)
                self.assertFalse(list(folder.glob('*.part')))
