"""Install or remove a macOS per-user six-hour statewide refresh job."""
import argparse
import hashlib
import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path
from update import ROOT


def label(root):
    return 'org.tx10.statewide.'+hashlib.sha256(str(root).encode()).hexdigest()[:10]


def configuration(root,python):
    root=Path(root).resolve()
    return {'Label':label(root),
            'ProgramArguments':[str(python),str(root/'scripts/refresh_statewide.py'),'--push'],
            'WorkingDirectory':str(root),'StartInterval':21600,'RunAtLoad':True,
            'EnvironmentVariables':{'PATH':'/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin','GIT_TERMINAL_PROMPT':'0','PYTHONUNBUFFERED':'1'},
            'StandardOutPath':str(root/'.cache/statewide-refresh.log'),
            'StandardErrorPath':str(root/'.cache/statewide-refresh-error.log')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remove',action='store_true',help='Remove the scheduled job without deleting input files.')
    args=parser.parse_args()
    if platform.system()!='Darwin':raise RuntimeError('Install this scheduler on your Mac, not on a GitHub-hosted runner.')
    root=ROOT.resolve();job=label(root)
    folder=Path.home()/'Library/LaunchAgents';plist=folder/(job+'.plist')
    domain='gui/'+str(os.getuid())
    if args.remove:
        subprocess.run(['launchctl','bootout',domain,str(plist)],capture_output=True,text=True)
        plist.unlink(missing_ok=True)
        print('Removed the six-hour statewide refresh job. Voter files were retained.');return 0
    python=root/'.venv/bin/python'
    if not python.exists():raise RuntimeError('Create the repository .venv first.')
    if subprocess.run(['git','-C',str(root),'status','--porcelain'],capture_output=True,text=True,check=True).stdout.strip():
        raise RuntimeError('Commit and push the code before installing the schedule.')
    folder.mkdir(parents=True,exist_ok=True);cache=root/'.cache';cache.mkdir(mode=0o700,exist_ok=True)
    for name in ['statewide-refresh.log','statewide-refresh-error.log']:
        fd=os.open(str(cache/name),os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600);os.close(fd)
    subprocess.run(['launchctl','bootout',domain,str(plist)],capture_output=True,text=True)
    with plist.open('wb') as f:plistlib.dump(configuration(root,python),f)
    os.chmod(plist,0o600)
    installed=subprocess.run(['launchctl','bootstrap',domain,str(plist)],capture_output=True,text=True)
    if installed.returncode:
        raise RuntimeError('launchctl could not load the schedule. Try running this installer from Terminal while logged into your Mac.')
    print('Installed: run immediately and every six hours while logged in and awake.')
    print('Logs: .cache/statewide-refresh.log and .cache/statewide-refresh-error.log')
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (RuntimeError,OSError,subprocess.CalledProcessError) as exc:
        print(str(exc),file=sys.stderr);sys.exit(2)
