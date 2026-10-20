"""Download/process locally, then commit and optionally push only generated aggregates."""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from update import ROOT, run


def git(root, *args, capture=True):
    result = subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=capture)
    if result.returncode:
        raise RuntimeError(f'git {args[0]} failed: {(result.stderr or "").strip()}')
    return (result.stdout or '').strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--push', action='store_true', help='Commit and push generated docs/data using your existing Git credentials.')
    parser.add_argument('--from-file', action='append', default=[], metavar='SOURCE_ID=PATH')
    args = parser.parse_args()
    local = {}
    for spec in args.from_file:
        if '=' not in spec:
            parser.error('--from-file requires SOURCE_ID=PATH')
        sid, path = spec.split('=', 1)
        local[sid] = str(Path(path).expanduser().resolve())
    if args.push:
        git(ROOT, 'rev-parse', '--show-toplevel')
        if git(ROOT, 'status', '--porcelain'):
            raise RuntimeError('Commit your existing changes before running --push. No files were changed.')
        branch = git(ROOT, 'branch', '--show-current')
        if not branch:
            raise RuntimeError('Check out a branch before running --push.')
        git(ROOT, 'fetch', 'origin')
        upstream = f'origin/{branch}'
        git(ROOT, 'rev-parse', '--verify', upstream)
        counts = git(ROOT, 'rev-list', '--left-right', '--count', f'HEAD...{upstream}').split()
        if int(counts[0]):
            raise RuntimeError('Your branch has unpushed commits. Push those separately before using this aggregate-only publisher.')
        git(ROOT, 'merge', '--ff-only', upstream)
        remote = git(ROOT, 'remote', 'get-url', 'origin')
        match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?', remote)
        if match:
            os.environ['GITHUB_REPOSITORY'] = match[1]
            os.environ['GITHUB_REF_NAME'] = branch
    result = run(ROOT, local)
    if args.push:
        # Explicit allowlist: never stage source rosters, config files, or code.
        git(ROOT, 'add', '--', 'docs/data')
        changed = git(ROOT, 'diff', '--cached', '--name-only')
        if changed:
            if any(not p.startswith('docs/data/') for p in changed.splitlines()):
                raise RuntimeError('Unexpected staged file outside docs/data; nothing was committed.')
            git(ROOT, 'commit', '-m', 'Refresh early voting aggregates from local update')
            git(ROOT, 'push', 'origin', f'HEAD:{branch}')
            print('Pushed dashboard aggregates. Source files remain on your computer.')
        else:
            print('No aggregate changes to push.')
    return result


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
