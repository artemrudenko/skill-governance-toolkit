"""Reject symlinked ownership markers using synthetic fixtures."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import managed_skills
from managed_docs import MARKER, install_docs, load_hashes
from sgt import _plan_install_dir


class OwnershipLinkTests(unittest.TestCase):
    def test_docs_markers_preserve_local_and_external_files(self):
        for marker in (MARKER, '.sgt-owned'):
            for dangling in (False, True):
                with self.subTest(marker=marker, dangling=dangling), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    source, docs = root / 'source', root / 'project' / 'docs'
                    source.mkdir()
                    docs.mkdir(parents=True)
                    (source / 'guide.md').write_text('incoming')
                    (docs / 'guide.md').write_text('local')
                    hashes = {'guide.md': hashlib.sha256(b'local').hexdigest()}
                    (docs / MARKER).write_text(json.dumps(hashes))
                    (docs / '.sgt-owned').write_text('guide.md\n')
                    outside = root / 'outside'
                    content = json.dumps(hashes) if marker == MARKER else 'guide.md\n'
                    if not dangling:
                        outside.write_text(content)
                    (docs / marker).unlink()
                    (docs / marker).symlink_to(outside)
                    install_docs(source, docs)
                    self.assertTrue((docs / marker).is_symlink())
                    self.assertEqual((docs / 'guide.md').read_text(), 'local')
                    self.assertEqual(outside.exists(), not dangling)
                    if not dangling:
                        self.assertEqual(outside.read_text(), content)
                    _, files, _ = _plan_install_dir(root / 'project', set(), [], None)
                    self.assertNotIn(docs / 'guide.md', files)

    def test_index_marker_rejects_forged_ownership_and_external_writes(self):
        for existing_index in (False, True):
            with self.subTest(existing_index=existing_index), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, dest = root / 'source', root / 'project' / 'skills'
                (source / 'skills').mkdir(parents=True)
                (source / 'skills' / 'INDEX.jsonl').write_text('')
                dest.mkdir(parents=True)
                index = dest / 'INDEX.jsonl'
                if existing_index:
                    index.write_text('local')
                external = root / 'external'
                external.write_text(hashlib.sha256(b'local').hexdigest() + '\n')
                marker = dest / managed_skills.INDEX_MARKER
                marker.symlink_to(external)
                self.assertFalse(managed_skills.owned_index_unchanged(dest))
                with patch.object(managed_skills, 'ROOT', source):
                    managed_skills.install(dest, [], write_index=True)
                self.assertTrue(marker.is_symlink())
                self.assertEqual(index.exists(), existing_index)
                if existing_index:
                    self.assertEqual(index.read_text(), 'local')
                self.assertEqual(external.read_text(), hashlib.sha256(b'local').hexdigest() + '\n')
                _, files, _ = _plan_install_dir(root / 'project', set(), [], None)
                self.assertNotIn(index, files)

    def test_dangling_index_marker_does_not_create_external_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / 'skills'
            dest.mkdir()
            external = root / 'absent'
            (dest / managed_skills.INDEX_MARKER).symlink_to(external)
            managed_skills.install(dest, [], write_index=True)
            self.assertFalse(external.exists())
            self.assertFalse((dest / 'INDEX.jsonl').exists())

    def test_removal_rejects_marker_paths_outside_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / 'docs'
            docs.mkdir()
            external = root / 'external'
            external.write_text('local')
            (docs / '.sgt-owned').write_text('../external\n' + str(external) + '\n')
            (docs / MARKER).write_text(json.dumps({
                '../external': hashlib.sha256(b'local').hexdigest(),
                str(external): hashlib.sha256(b'local').hexdigest(),
            }))
            _, files, _ = _plan_install_dir(root, set(), [], None)
            self.assertEqual(files, [])
            self.assertEqual(external.read_text(), 'local')

    def test_regular_index_updates_and_preserves_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'skills').mkdir()
            (root / 'skills' / 'INDEX.jsonl').write_text('')
            dest = root / 'project' / 'skills'
            with patch.object(managed_skills, 'ROOT', root):
                managed_skills.install(dest, [], write_index=True)
                self.assertTrue(managed_skills.owned_index_unchanged(dest))
                managed_skills.install(dest, [], write_index=True)
                (dest / 'INDEX.jsonl').write_text('edits')
                managed_skills.install(dest, [], write_index=True)
            self.assertEqual((dest / 'INDEX.jsonl').read_text(), 'edits')

    def test_symlinked_directories_do_not_authorize_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside, project = root / 'outside', root / 'project'
            outside.mkdir()
            project.mkdir()
            (outside / 'guide.md').write_text('local')
            (outside / MARKER).write_text(json.dumps({'guide.md': hashlib.sha256(b'local').hexdigest()}))
            (outside / '.sgt-owned').write_text('guide.md\n')
            (project / 'docs').symlink_to(outside, target_is_directory=True)
            self.assertEqual(load_hashes(project / 'docs'), {})
            self.assertEqual(_plan_install_dir(project, set(), [], None), ([], [], []))

    def test_uninstall_plan_preserves_links_and_changed_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'agents').mkdir()
            (root / 'scripts').mkdir()
            outside = root / 'outside'
            outside.write_text('personal')
            (root / 'agents' / 'agent.md').symlink_to(outside)
            (root / 'agents' / '.sgt-owned').write_text('agent.md\n')
            (root / 'scripts' / 'sgt.py').write_text('local changes')
            (root / 'scripts' / 'linked.py').symlink_to(outside)
            _, files, _ = _plan_install_dir(root, set(), ['sgt.py', 'linked.py'], None)
            self.assertEqual(files, [])
            self.assertTrue((root / 'agents' / 'agent.md').is_symlink())
            self.assertTrue((root / 'scripts' / 'linked.py').is_symlink())

    def test_uninstall_preserves_linked_user_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / 'project'
            project.mkdir()
            outside = root / 'instructions.md'
            original = '<!-- skill-governance-toolkit: BEGIN -->\nkeep\n<!-- skill-governance-toolkit: END -->\n'
            outside.write_text(original)
            link = project / 'AGENTS.md'
            link.symlink_to(outside)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('sgt.py')),
                                     'uninstall', '--scope', 'project', '--target-project', str(project), '--yes'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(link.is_symlink())
            self.assertEqual(outside.read_text(), original)


if __name__ == '__main__':
    unittest.main()
