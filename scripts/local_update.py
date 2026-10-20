"""Download/process locally, then commit and optionally push only generated aggregates."""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from update import ROOT, run
from folder_inputs import stamp


def git(root, *args, capture=True):
    result = subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=capture)
    if result.returncode:
        raise RuntimeError(f'git {args[0]} failed: {(result.stderr or "").strip()}')
    return (result.stdout or '').strip()


def publish_once(push=False, local=None, inbox=None):
    local = local or {}
    if push:
        git(ROOT, 'rev-parse', '--show-toplevel')
        if git(ROOT, 'ls-files', '--', 'inbox'):
            raise RuntimeError('Private inbox files are tracked by Git. Untrack inbox before publishing; .gitignore alone cannot protect already tracked files.')
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
    result = run(ROOT, local, inbox) if inbox is not None else run(ROOT, local)
    if push:
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--push', action='store_true', help='Commit and push generated docs/data using your existing Git credentials.')
    parser.add_argument('--from-file', action='append', default=[], metavar='SOURCE_ID=PATH')
    parser.add_argument('--inbox', type=Path, help='Process only named local files from this folder, without county downloads.')
    parser.add_argument('--watch', action='store_true', help='Keep watching the inbox and refresh after files settle.')
    parser.add_argument('--interval', type=float, default=3, help='Watcher polling interval in seconds (minimum 1).')
    args = parser.parse_args()
    if (args.inbox is not None or args.watch) and args.from_file:
        parser.error('Use folder mode or --from-file, not both.')
    local = {}
    for spec in args.from_file:
        if '=' not in spec:
            parser.error('--from-file requires SOURCE_ID=PATH')
        sid, path = spec.split('=', 1)
        local[sid] = str(Path(path).expanduser().resolve())
    # Local runs default to the private folder. --from-file retains the legacy
    # per-source override behavior; other enabled sources may still download.
    inbox = args.inbox if args.inbox is not None else None if args.from_file else Path('inbox')
    if inbox is not None:
        inbox = (ROOT / inbox).resolve()
        inbox.mkdir(parents=True, exist_ok=True)
    if not args.watch:
        return publish_once(args.push, local, inbox)
    interval = max(1, args.interval)
    last_processed, pending = None, None
    print(f'Watching {inbox}. Files are processed after one quiet polling interval. Ctrl-C stops the watcher.', flush=True)
    try:
        while True:
            try:
                current = stamp(inbox)
                if current == pending and current != last_processed:
                    try:
                        result = publish_once(args.push, local, inbox)
                        if result:
                            print('Some files failed; diagnostics were retained. Watching for the next change.', flush=True)
                    except Exception as exc:
                        print(f'Update failed: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
                    last_processed = current
                pending = current
            except OSError:
                pass  # a browser/Finder may be replacing a file during this poll
            time.sleep(interval)
    except KeyboardInterrupt:
        print('\nStopped watching.')
        return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
