"""Download fixtures contain synthetic voters only; no actual HTTP requests."""
import io
import json
import os
import plistlib
import sys
import tempfile
import unittest
import urllib.parse
import zipfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refresh_statewide as refresh
import statewide_schedule as schedule
import local_update as local

CSV=b'COUNTY,VOTER_NAME,ID_VOTER,VOTING_METHOD,PRECINCT\nBRAZOS,"SYNTHETIC, ONE",1000000001,IN-PERSON,69\n'


class ScheduledRefreshTests(unittest.TestCase):
    def setUp(self):
        self.settings=json.loads((ROOT/'config/settings.json').read_text())
        self.day=date(2026,10,20)

    def curl(self,body=CSV,status='200',code=0):
        def run(command,**kwargs):
            Path(command[command.index('--output')+1]).write_bytes(body)
            self.assertIn('--proto',command);self.assertIn('=https',command)
            return SimpleNamespace(stdout=status,stderr='',returncode=code)
        return run

    def test_url_uses_report_date_and_known_election_id(self):
        fields=urllib.parse.parse_qs(urllib.parse.urlsplit(refresh.report_url(date(2026,10,21))).query)
        self.assertEqual(fields,{'type':['EVR_STATEWIDE'],'electionId':['53815'],'electionDate':['10/21/2026']})

    def test_backfill_missing_days_but_always_refresh_latest_two(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            (folder/refresh.filename(date(2026,10,19))).touch()
            (folder/refresh.filename(date(2026,10,20))).touch()
            self.assertEqual(refresh.planned_dates(self.settings,folder,date(2026,10,21)),[date(2026,10,20),date(2026,10,21)])
            self.assertEqual(refresh.planned_dates(self.settings,folder,date(2026,10,18)),[])

    def test_validated_atomic_download_private_permissions_and_unchanged_file(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            with patch.object(refresh.shutil,'which',return_value='/usr/bin/curl'),patch.object(refresh.subprocess,'run',side_effect=self.curl()):
                self.assertEqual(refresh.download(self.day,folder,self.settings),'downloaded')
                saved=folder/refresh.filename(self.day);before=saved.stat().st_mtime_ns
                self.assertEqual(saved.read_bytes(),CSV);self.assertEqual(saved.stat().st_mode&0o777,0o600)
                self.assertEqual(refresh.download(self.day,folder,self.settings),'unchanged')
                self.assertEqual(saved.stat().st_mtime_ns,before)
                self.assertFalse(list(folder.glob('*.part')))

    def test_http_errors_never_overwrite_existing_report_or_log_body(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);saved=folder/refresh.filename(self.day);saved.write_bytes(CSV)
            for body,status,code in [(b'<html>PRIVATE RESPONSE</html>','200',0),(b'PRIVATE RESPONSE','403',22)]:
                with patch.object(refresh.shutil,'which',return_value='/usr/bin/curl'),patch.object(refresh.subprocess,'run',side_effect=self.curl(body,status,code)):
                    with self.assertRaises((RuntimeError,ValueError)) as error:refresh.download(self.day,folder,self.settings)
                    self.assertNotIn('PRIVATE RESPONSE',str(error.exception))
                    self.assertEqual(saved.read_bytes(),CSV)
            with patch.object(refresh.shutil,'which',return_value='/usr/bin/curl'),patch.object(refresh.subprocess,'run',side_effect=self.curl(b'','404',22)):
                self.assertEqual(refresh.download(self.day,folder,self.settings),'unavailable')
                self.assertEqual(saved.read_bytes(),CSV)

    def test_zip_download_accepts_one_csv_and_validates_it(self):
        with tempfile.TemporaryDirectory() as temp:
            body=io.BytesIO()
            with zipfile.ZipFile(body,'w') as z:z.writestr('statewide.csv',CSV)
            with patch.object(refresh.shutil,'which',return_value='/usr/bin/curl'),patch.object(refresh.subprocess,'run',side_effect=self.curl(body.getvalue())):
                self.assertEqual(refresh.download(self.day,Path(temp),self.settings),'downloaded')
                self.assertEqual((Path(temp)/refresh.filename(self.day)).read_bytes(),CSV)

    def test_failed_refresh_never_calls_publisher_success_uses_only_inbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'config').mkdir();(root/'config/settings.json').write_text(json.dumps(self.settings))
            with patch.object(refresh,'download',side_effect=RuntimeError('HTTP 403')),patch.object(local,'publish_once') as publisher:
                self.assertEqual(refresh.refresh(root,report_date=self.day,push=True),1)
                publisher.assert_not_called()
            with patch.object(refresh,'download',return_value='downloaded'),patch.object(local,'publish_once',return_value=0) as publisher:
                self.assertEqual(refresh.refresh(root,report_date=self.day,push=True),0)
                publisher.assert_called_once_with(push=True,inbox=root/'inbox')

    def test_schedule_is_six_hours_uses_absolute_arguments_and_no_shell(self):
        root=Path('/tmp/repository with spaces')
        config=plistlib.loads(plistlib.dumps(schedule.configuration(root,root/'.venv/bin/python')))
        self.assertEqual(config['StartInterval'],21600);self.assertTrue(config['RunAtLoad'])
        self.assertEqual(config['ProgramArguments'],[str(root/'.venv/bin/python'),str(root/'scripts/refresh_statewide.py'),'--push'])
        self.assertEqual(config['EnvironmentVariables']['GIT_TERMINAL_PROMPT'],'0')
        self.assertNotIn('sh',config['ProgramArguments'])

    def test_overlapping_jobs_are_locked(self):
        with tempfile.TemporaryDirectory() as temp:
            with local.update_lock(Path(temp),'statewide-download'):
                with self.assertRaisesRegex(RuntimeError,'already running'):
                    with local.update_lock(Path(temp),'statewide-download',blocking=False):pass


if __name__=='__main__':unittest.main()
