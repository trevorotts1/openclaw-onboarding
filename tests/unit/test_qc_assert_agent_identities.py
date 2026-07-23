#!/usr/bin/env python3
"""Unit tests for qc-assert-agent-identities-resolved.sh (U060).

Validates that the gate correctly detects unresolved generator template
patterns and passes when all identity files are resolved.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path


class TestQCAssertAgentIdentities(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.script = Path(__file__).resolve().parents[2] / "scripts" / "qc-assert-agent-identities-resolved.sh"
        if not cls.script.exists():
            raise FileNotFoundError(f"Missing: {cls.script}")

    def _run(self, root: Path, json_mode: bool = False) -> subprocess.CompletedProcess:
        args = [str(self.script)]
        if json_mode:
            args.append("--json")
        args.append(str(root))
        return subprocess.run(args, capture_output=True, text=True)

    def _make_mutant(self, content: str) -> Path:
        d = Path(tempfile.mkdtemp(prefix="u060_"))
        spec_dir = d / "42-personal-assistant-library/specialists/99-mutant"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "SOUL.md").write_text(content)
        aw = d / "54-anthology-writer"
        aw.mkdir(parents=True, exist_ok=True)
        (aw / "SOUL.md").write_text("# AW\n\nResolved.\n")
        (aw / "IDENTITY.md").write_text("# AW ID\n\nResolved.\n")
        return d

    def test_all_resolved_passes(self):
        r = self._run(Path(__file__).resolve().parents[2])
        self.assertEqual(r.returncode, 0, f"Got: {r.stdout}")

    def test_all_resolved_json(self):
        r = self._run(Path(__file__).resolve().parents[2], json_mode=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "[]")

    def test_mutant_fill_in(self):
        r = self._run(self._make_mutant("# X\n\n_Fill this in during your first conversation. Make it yours._\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unresolved-fill-in", r.stdout)

    def test_mutant_agent_name(self):
        r = self._run(self._make_mutant("# X\n\nI'm [Agent Name]. [One-line identity description].\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unresolved-fill-in", r.stdout)

    def test_mutant_human_name(self):
        r = self._run(self._make_mutant("# X\n\nHelp [Human Name] [achieve their primary goal].\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unresolved-fill-in", r.stdout)

    def test_mutant_customize(self):
        r = self._run(self._make_mutant("# X\n\n> Customize this file with your agent's identity, principles, and boundaries.\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unresolved-fill-in", r.stdout)

    def test_mutant_gen_date(self):
        r = self._run(self._make_mutant("# X\n**Last updated:** {{GENERATION_DATE}}\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unresolved-var", r.stdout)

    def test_mutant_industry(self):
        r = self._run(self._make_mutant("# X\n**Industry:** {{COMPANY_INDUSTRY}}\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unresolved-var", r.stdout)

    def test_mutant_persona_ver(self):
        r = self._run(self._make_mutant("# X\n**Persona:** v{{ASSIGNED_PERSONA_VERSION}}\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unresolved-var", r.stdout)

    def test_mutant_genfor_token(self):
        r = self._run(self._make_mutant("# X\n**Generated for:** {{TOKEN}}\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unresolved-generated-for", r.stdout)

    def test_mutant_genfor_co(self):
        r = self._run(self._make_mutant("# X\n**Generated for:** {{COMPANY_NAME}}\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unresolved-generated-for", r.stdout)

    def test_mutant_missing_file(self):
        d = Path(tempfile.mkdtemp(prefix="u060_"))
        aw = d / "54-anthology-writer"
        aw.mkdir(parents=True, exist_ok=True)
        (aw / "IDENTITY.md").write_text("# ID\n")
        r = self._run(d)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("missing-required-file", r.stdout)

    def test_edge_resolved(self):
        content = "# Agent\n**Version:** 1.0\n**Last updated:** 2026-07-23\n**Generated for:** the company\n\nReal content.\n"
        r = self._run(self._make_mutant(content))
        self.assertEqual(r.returncode, 0, f"Got: {r.stdout}")

    def test_edge_runtime_tokens(self):
        content = "# Agent\n**Version:** 1.0\n**Last updated:** 2026-07-23\n**Generated for:** the company\n\n{{TOKEN}} is the owner. {{OWNER_NAME}} calls.\n"
        r = self._run(self._make_mutant(content))
        self.assertEqual(r.returncode, 0, f"Got: {r.stdout}")


if __name__ == "__main__":
    unittest.main()
