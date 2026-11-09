import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from checkpoint import snapshot


class CheckpointTests(unittest.TestCase):
    def test_archive_is_complete_and_hashes_match(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = snapshot(directory)
            with tarfile.open(archive) as bundle:
                manifest = json.load(bundle.extractfile('MANIFEST.json'))
                self.assertIn('06-ghl-install-pages/tools/playwright_recipes/host.py', manifest['sha256'])
                self.assertTrue(any(name.endswith('PLAYWRIGHT-PROGRESS.md') for name in manifest['sha256']))
                for name, expected in manifest['sha256'].items():
                    self.assertEqual(hashlib.sha256(bundle.extractfile(name).read()).hexdigest(), expected)
                    self.assertFalse(Path(name).is_absolute())
                    self.assertNotIn('..', Path(name).parts)
                self.assertEqual(set(bundle.getnames()), set(manifest['sha256']) | {'MANIFEST.json'})

    def test_only_allowlisted_sources_and_private_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = snapshot(directory)
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            with tarfile.open(archive) as bundle:
                for name in bundle.getnames():
                    self.assertNotIn('__pycache__', name)
                    self.assertNotIn('auth-runtime', name)
                    self.assertNotIn('state.json', name)
                    self.assertNotIn('handoff.json', name)

    def test_repeated_checkpoints_preserve_previous_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            first = snapshot(directory)
            original = first.read_bytes()
            second = snapshot(directory)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
