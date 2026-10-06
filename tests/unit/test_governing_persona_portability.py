#!/usr/bin/env python3
"""Run the real persona writer with stock system Bash and a service-style PATH."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / '23-ai-workforce-blueprint/scripts/generate-governing-personas.sh'
spec = importlib.util.spec_from_file_location('portable_prebuild', REPO / 'scripts/prebuild-standard-workforce.py')
prebuild = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prebuild)


class PersonaPortabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.depts = self.root / 'departments'
        self.depts.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('OPENCLAW_', 'PERSONA_', 'COACHING_')) and k not in ('BASH_ENV', 'ENV')}
        self.env.update(HOME=str(self.root), DEPARTMENTS_DIR=str(self.depts), PATH='/usr/bin:/bin',
                        PERSONA_CATEGORIES=str(self.root / 'no-catalog.json'),
                        COACHING_PERSONAS_DIR=str(self.root / 'no-personas'))

    def test_real_persona_writer_on_system_bash_exact_partial_unknown_and_resume(self):
        for dept in ('Marketing', 'app-development', 'client-marketing-team', 'unknown-department', 'keep-owner-edit'):
            (self.depts / dept).mkdir()
        existing = self.depts / 'keep-owner-edit/governing-personas.md'
        existing.write_text('## Primary Persona\nOwner-chosen persona, preserve this.\n')
        result = subprocess.run(['/bin/bash', str(SCRIPT)], env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Gary Halbert', (self.depts / 'Marketing/governing-personas.md').read_text())
        self.assertIn('Frederick Brooks', (self.depts / 'app-development/governing-personas.md').read_text())
        self.assertIn('Gary Halbert', (self.depts / 'client-marketing-team/governing-personas.md').read_text())
        self.assertIn('Gary Vaynerchuk', (self.depts / 'unknown-department/governing-personas.md').read_text())
        before = {path: path.read_bytes() for path in self.depts.rglob('governing-personas.md')}
        again = subprocess.run(['/bin/bash', str(SCRIPT)], env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertIn('Owner-chosen', existing.read_text())

    def test_prebuild_pins_system_bash_even_with_hostile_path_bash(self):
        fake_bin = self.root / 'bin'
        fake_bin.mkdir()
        fake = fake_bin / 'bash'
        fake.write_text('#!/bin/sh\nexit 97\n')
        fake.chmod(0o755)
        with patch.dict(os.environ, dict(self.env, PATH=str(fake_bin) + ':/usr/bin:/bin'), clear=True):
            executable = prebuild._resolve_persona_bash()
        self.assertEqual(executable, str(Path('/bin/bash').resolve()))

    def test_invalid_explicit_interpreter_is_rejected_without_fallback(self):
        with patch.dict(os.environ, dict(self.env, OPENCLAW_BASH='bash'), clear=True):
            with self.assertRaises(ValueError):
                prebuild._resolve_persona_bash()
        with patch.dict(os.environ, dict(self.env, OPENCLAW_BASH='/usr/bin/true'), clear=True):
            with self.assertRaises(ValueError):
                prebuild._resolve_persona_bash()


if __name__ == '__main__':
    unittest.main()
