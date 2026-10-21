"""Download SOS reports locally, validate before replacement, then publish aggregates."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import local_update
import sos_rosters
from update import ROOT

ENDPOINT='https://goelect.txelections.civixapps.com/api-ivis-system/api/v1/getFile'
MAX_BYTES=150*1024*1024


def report_url(report_date):
    return ENDPOINT+'?'+urllib.parse.urlencode({'type':'EVR_STATEWIDE','electionId':'53815',
                                               'electionDate':report_date.strftime('%m/%d/%Y')})


def filename(report_date):
    return f'STATEWIDE.2026 NOVEMBER GENERAL ELECTION.EarlyVoting.{report_date:%m_%d_%Y}.csv'


def planned_dates(settings, inbox, today):
    start=date.fromisoformat(settings['early_start'])
    end=min(today,date.fromisoformat(settings['election_date']))
    result=[];day=start
    while day<=end:
        # Retry missing dates; refresh the latest two dates for corrections.
        if day>=end-timedelta(days=1) or not (inbox/filename(day)).exists():result.append(day)
        day+=timedelta(days=1)
    return result


def checksum(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    return digest.digest()


def download(report_date, inbox, settings):
    curl=shutil.which('curl')
    if not curl:raise RuntimeError('curl is required; macOS includes /usr/bin/curl.')
    inbox.mkdir(mode=0o700,parents=True,exist_ok=True)
    destination=inbox/filename(report_date)
    if destination.is_symlink():raise ValueError('Refusing a symlinked statewide destination.')
    descriptor,temp_name=tempfile.mkstemp(prefix='.statewide-',suffix='.part',dir=str(inbox))
    os.close(descriptor);temporary=Path(temp_name)
    try:
        try:
            response=subprocess.run([curl,'--fail','--location','--silent','--show-error',
                '--proto','=https','--proto-redir','=https','--connect-timeout','20',
                '--max-time','300','--max-filesize',str(MAX_BYTES),'--output',str(temporary),
                '--write-out','%{http_code}',report_url(report_date)],capture_output=True,text=True,timeout=330)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Statewide download timed out; existing report retained.') from None
        status=response.stdout.strip()
        if status in {'204','404'}:return 'unavailable'
        if response.returncode or status!='200':
            raise RuntimeError(f'Statewide download failed (HTTP {status if status.isdigit() else "unknown"}, curl exit {response.returncode}); existing report retained.')
        if not temporary.stat().st_size or temporary.stat().st_size>MAX_BYTES:
            raise ValueError('Downloaded report is empty or too large; existing report retained.')
        if zipfile.is_zipfile(temporary):
            with zipfile.ZipFile(temporary) as archive:
                entries=[i for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith('.csv') and not i.filename.startswith('__MACOSX/')]
                if len(entries)!=1 or entries[0].file_size>MAX_BYTES:
                    raise ValueError('Download ZIP must contain exactly one supported statewide CSV.')
                body=archive.read(entries[0])
            temporary.write_bytes(body)
        try:
            counties,_=sos_rosters.load(temporary,settings,report_date.isoformat())
            if not counties or any(c['error'] for c in counties.values()) or not any(c['records'] for c in counties.values()):
                raise ValueError('No valid complete target-county records.')
        except (ValueError,UnicodeError,zipfile.BadZipFile):
            raise ValueError('Downloaded content did not validate as an SOS voter CSV; existing report retained. No response contents were logged.') from None
        if destination.exists() and checksum(destination)==checksum(temporary):return 'unchanged'
        os.chmod(temporary,0o600)
        os.replace(temporary,destination)
        return 'downloaded'
    finally:
        temporary.unlink(missing_ok=True)


def refresh(root=ROOT,push=False,report_date=None,download_only=False):
    root=Path(root)
    settings=json.loads((root/'config/settings.json').read_text())
    if settings['election_date']!='2026-11-03':
        raise ValueError('This downloader is configured for the 2026 November election, SOS election ID 53815.')
    today=datetime.now(ZoneInfo(settings['timezone'])).date()
    if report_date and not date.fromisoformat(settings['early_start'])<=report_date<=min(today,date.fromisoformat(settings['election_date'])):
        raise ValueError('Requested report date is outside the current early-voting/election reporting window.')
    inbox=root/'inbox'
    dates=[report_date] if report_date else planned_dates(settings,inbox,today)
    successes=0;failures=0
    with local_update.update_lock(root,'statewide-download',blocking=False):
        for day in dates:
            try:
                result=download(day,inbox,settings)
                print(f'SOS {day}: {result}',flush=True)
                successes+=result in {'downloaded','unchanged'}
            except (OSError,RuntimeError,ValueError,zipfile.BadZipFile) as exc:
                # Never print server response bodies or raw CSV rows.
                failures+=1
                detail = str(exc) if isinstance(exc,(RuntimeError,ValueError)) else 'Report file I/O or archive validation failed.'
                print(f'SOS {day}: {detail}',file=sys.stderr,flush=True)
        if not dates:
            print('No reports are due before the configured early-voting start date.');return 0
        if not successes:
            print('No requested report was downloaded successfully; no dashboard changes were published.',file=sys.stderr)
            return 1
        if download_only:return 1 if failures else 0
        # The shared publisher lock serializes this with an optional watcher.
        result=local_update.publish_once(push=push,inbox=inbox)
        return result or (1 if failures else 0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--push',action='store_true',help='Publish only aggregates using saved Git credentials.')
    parser.add_argument('--date',type=date.fromisoformat,help='Fetch just this report date (YYYY-MM-DD).')
    parser.add_argument('--download-only',action='store_true',help='Validate and save reports without running the publisher.')
    args=parser.parse_args()
    return refresh(push=args.push,report_date=args.date,download_only=args.download_only)


if __name__=='__main__':
    try:sys.exit(main())
    except (RuntimeError,ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);sys.exit(2)
