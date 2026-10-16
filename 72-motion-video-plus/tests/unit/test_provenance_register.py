"""Tests for the MG-047 provenance register and its coverage check.

Run from the repo root:
    python3 -m unittest discover -s 72-motion-video-plus/tests/unit

The positive case proves every dependency in the two shipped npm locks
has a register record. The negative case removes one record from a
temporary copy of the register and proves the checker fails and names
the missing dependency, so the register cannot silently rot.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
REGISTER = SKILL_ROOT / "references" / "provenance-register.json"
CHECKER = SKILL_ROOT / "scripts" / "check_provenance.py"

sys.path.insert(0, str(CHECKER.parent))
import check_provenance  # noqa: E402


def _load_register() -> dict:
    return json.loads(REGISTER.read_text(encoding="utf-8"))


class TestProvenanceCoverage(unittest.TestCase):
    def test_every_locked_dependency_has_a_record(self) -> None:
        missing = check_provenance.missing_records(_load_register(),
                                                   check_provenance.LOCK_PATHS)
        self.assertEqual(missing, [],
                         f"lock dependencies without records: {missing}")

    def test_checker_cli_passes_on_the_shipped_register(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(CHECKER)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

    def test_checker_fails_and_names_the_gap_when_a_record_is_removed(self) -> None:
        register = _load_register()
        victim = next(r for r in register["records"]
                      if r["kind"] == "npm_dependency" and r["name"] == "remotion")
        broken = copy.deepcopy(register)
        broken["records"] = [r for r in broken["records"] if r is not victim
                             and r.get("id") != victim["id"]]
        with tempfile.TemporaryDirectory() as tmp:
            broken_path = Path(tmp) / "register.json"
            broken_path.write_text(json.dumps(broken), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CHECKER), "--register", str(broken_path)],
                capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("remotion@4.0.535", proc.stdout)

    def test_register_records_carry_the_required_fields(self) -> None:
        register = _load_register()
        for rec in register["records"]:
            self.assertIn(rec.get("status"), ("recorded", "unresolved"),
                          f"bad status on {rec.get('id')}")
            self.assertIn("license_source", rec, f"no source on {rec.get('id')}")
            self.assertIn("basis", rec["license_source"],
                          f"no source basis on {rec.get('id')}")
            if rec["status"] == "recorded" and rec["kind"] in (
                    "npm_dependency", "python_dependency", "font"):
                self.assertTrue(rec.get("license_name"),
                                f"recorded without a license name: {rec.get('id')}")

    def test_unresolved_records_are_named_not_hidden(self) -> None:
        register = _load_register()
        unresolved = [r["id"] for r in register["records"]
                      if r["status"] == "unresolved"]
        # The register must state its gaps openly; the known gap set at
        # MG-047 delivery is the Remotion compositor/media packages plus
        # the tool and service records listed in the human document.
        self.assertIn("npm:@remotion/media@4.0.535", unresolved)
        self.assertTrue(register.get("open_rights_questions"),
                        "open rights questions must be listed in the register")
        for rec in register["records"]:
            for orq in rec.get("open_questions", []):
                self.assertIn(orq, {q["id"] for q in register["open_rights_questions"]},
                              f"{rec['id']} references unknown question {orq}")


if __name__ == "__main__":
    unittest.main()
