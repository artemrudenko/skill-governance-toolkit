"""Exercise runtime script updates through the project installer and CLI."""
import shutil
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuntimeInstallTests(unittest.TestCase):
    def test_update_and_uninstall_preserve_edits_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, project = base / 'source', base / 'project'
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns('.git', 'assets', '__pycache__', '*.zip'))
            project.mkdir()
            command = ['bash', str(source / 'scripts/install.sh'), '--codex', '--project',
                       f'--target-project={project}', '--skill', 'skill-find']

            def install(*extra):
                result = subprocess.run(command + list(extra), cwd=project, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            install()
            scripts = project / 'scripts'
            edited = scripts / 'post_mr_comment.py'
            edited.write_text('local modification\n')
            updated_source = source / 'scripts/checkpoint.py'
            updated_source.write_text(updated_source.read_text() + '\n# new toolkit version\n')
            outside = base / 'outside.py'
            outside.write_text('private data\n')
            link = scripts / 'configure_org.sh'
            link.unlink()
            link.symlink_to(outside)
            install('--upgrade')

            self.assertEqual(edited.read_text(), 'local modification\n')
            self.assertEqual((scripts / 'checkpoint.py').read_text(), updated_source.read_text())
            self.assertTrue(link.is_symlink())
            self.assertEqual(outside.read_text(), 'private data\n')
            self.assertTrue((scripts / 'post_mr_comment.skill-governance-toolkit.py').is_file())
            self.assertTrue((scripts / 'configure_org.skill-governance-toolkit.sh').is_file())
            install('--upgrade')
            self.assertFalse((scripts / 'post_mr_comment.skill-governance-toolkit.1.py').exists())

            result = subprocess.run([sys.executable, str(scripts / 'sgt.py'), 'uninstall',
                                     '--scope', 'project', '--target-project', str(project), '--yes'],
                                    cwd=project, capture_output=True, text=True, encoding='cp1252',
                                    env=dict(os.environ, PYTHONIOENCODING='cp1252'))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(edited.read_text(), 'local modification\n')
            self.assertTrue(link.is_symlink())
            self.assertEqual(outside.read_text(), 'private data\n')
            self.assertFalse((scripts / 'checkpoint.py').exists())
            self.assertFalse((scripts / 'post_mr_comment.skill-governance-toolkit.py').exists())

    def test_legacy_scripts_and_linked_directory_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project, external = base / 'project', base / 'external'
            project.mkdir()
            external.mkdir()
            legacy = external / 'checkpoint.py'
            legacy.write_text('legacy user file\n')
            (project / 'scripts').symlink_to(external, target_is_directory=True)
            command = ['bash', str(ROOT / 'scripts/install.sh'), '--codex', '--project',
                       f'--target-project={project}', '--skill', 'skill-find']
            result = subprocess.run(command, cwd=project, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((project / 'scripts').is_symlink())
            self.assertEqual(legacy.read_text(), 'legacy user file\n')
            self.assertEqual(list(external.iterdir()), [legacy])

    def test_untracked_legacy_script_and_marker_link_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / 'project'
            scripts = project / 'scripts'
            scripts.mkdir(parents=True)
            legacy = scripts / 'checkpoint.py'
            legacy.write_text('legacy edits\n')
            command = ['bash', str(ROOT / 'scripts/install.sh'), '--codex', '--project',
                       f'--target-project={project}', '--skill', 'skill-find']
            result = subprocess.run(command, cwd=project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(legacy.read_text(), 'legacy edits\n')
            self.assertTrue((scripts / 'checkpoint.skill-governance-toolkit.py').is_file())
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/sgt.py'), 'uninstall',
                                     '--scope', 'project', '--target-project', str(project), '--yes'],
                                    cwd=project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(legacy.read_text(), 'legacy edits\n')

            marker = scripts / '.sgt-runtime-hashes.json'
            marker.unlink(missing_ok=True)
            external = base / 'marker'
            external.write_text('private')
            marker.symlink_to(external)
            result = subprocess.run(command, cwd=project, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(marker.is_symlink())
            self.assertEqual(external.read_text(), 'private')
            marker.unlink()
            marker.write_text('local record')
            result = subprocess.run(command, cwd=project, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(), 'local record')

    def test_global_upgrade_and_uninstall_preserve_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = dict(os.environ, HOME=str(home))
            command = ['bash', str(ROOT / 'scripts/install.sh'), '--codex', '--global', '--skill', 'skill-find']
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            scripts = home / '.codex/scripts'
            edited = scripts / 'post_mr_comment.py'
            edited.write_text('global edits\n')
            result = subprocess.run(command + ['--upgrade'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(edited.read_text(), 'global edits\n')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/sgt.py'), 'uninstall',
                                     '--scope', 'global', '--host', 'codex', '--yes'],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(edited.read_text(), 'global edits\n')
            self.assertFalse((scripts / 'checkpoint.py').exists())


if __name__ == '__main__':
    unittest.main()
