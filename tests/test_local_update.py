import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import local_update as local


class LocalPublisherTests(unittest.TestCase):
    def prepare(self, temp):
        base = Path(temp); root = base / 'work'; remote = base / 'remote.git'
        def call(*args):
            subprocess.run(['git', *args], check=True, capture_output=True, text=True)
        call('init', '--bare', str(remote))
        call('init', '-b', 'main', str(root))
        call('-C', str(root), 'config', 'user.name', 'Local test')
        call('-C', str(root), 'config', 'user.email', 'local-test@example.invalid')
        (root / '.gitignore').write_text('inbox/\n.cache/\n')
        (root / 'README.md').write_text('Synthetic repository\n')
        call('-C', str(root), 'add', '.')
        call('-C', str(root), 'commit', '-m', 'Initial test')
        call('-C', str(root), 'remote', 'add', 'origin', str(remote))
        call('-C', str(root), 'push', '-u', 'origin', 'main')
        return root, remote

    def test_local_update_pushes_aggregates_only_even_if_another_source_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root, remote = self.prepare(temp)
            (root / 'inbox').mkdir()
            (root / 'inbox/raw.csv').write_text('private synthetic source\n')
            def update(root_arg, overrides, inbox):
                self.assertEqual(inbox, root_arg/'inbox')
                p = root_arg / 'docs/data'; p.mkdir(parents=True)
                (p / 'latest.json').write_text(json.dumps({'reported_subtotal': 12}))
                return 1  # diagnostics from one failed source still get published
            with patch.object(local, 'ROOT', root), patch.object(local, 'run', side_effect=update), patch.object(sys, 'argv', ['local_update.py', '--push']):
                self.assertEqual(local.main(), 1)
            published = subprocess.check_output(['git', '--git-dir', str(remote), 'ls-tree', '-r', '--name-only', 'main'], text=True)
            self.assertIn('docs/data/latest.json', published)
            self.assertNotIn('raw.csv', published)

    def test_existing_changes_block_before_downloading(self):
        with tempfile.TemporaryDirectory() as temp:
            root, remote = self.prepare(temp)
            (root / 'README.md').write_text('Uncommitted user edit\n')
            with patch.object(local, 'ROOT', root), patch.object(local, 'run') as updater, patch.object(sys, 'argv', ['local_update.py', '--push']):
                with self.assertRaisesRegex(RuntimeError, 'existing changes'):
                    local.main()
                updater.assert_not_called()
