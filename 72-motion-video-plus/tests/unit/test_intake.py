"""Mode-first intake tests for Skill 72 (MG-008).

Proves mechanically that:
(a) each shipped example job validates with the shipped contract validator
    and carries the package shape its mode requires;
(b) the intake flow in INSTRUCTIONS.md resolves the mode before any
    job-setup step (the stage order is the contract), asks the exact
    Section 4.2 question, creates the job package at stage 3, resolves the
    authoring model at stage 7, and keeps the legacy path after the
    canonical stages;
(c) no document in the skill presents the legacy renderer as a default,
    and the canonical documents describe it only as an explicitly chosen
    compatibility path reached through migration;
(d) every mode identifier named in SKILL.md is a member of the canonical
    schema's manifest mode enum, and together they cover the enum exactly.

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import motion_contracts  # noqa: E402

EXAMPLES = SKILL_ROOT / "assets" / "examples"
SCHEMA_PATH = SKILL_ROOT / "references" / "contracts-v2.schema.json"
ALL_MODES = motion_contracts.MODES
VSL_MODES = motion_contracts.VSL_MODES
MODE_QUESTION = (
    "Is this for a PowerPoint slide, a desktop VSL, a mobile VSL, "
    "or a standalone video?"
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_modes() -> set:
    schema = _load(SCHEMA_PATH)
    return set(schema["$defs"]["manifest"]["properties"]["mode"]["enum"])


class ExampleJobTests(unittest.TestCase):
    def test_each_mode_has_a_validated_example_job(self):
        for mode in ALL_MODES:
            with self.subTest(mode=mode):
                job = EXAMPLES / mode
                self.assertTrue(job.is_dir(), f"missing example job for mode {mode}")
                findings = motion_contracts.validate_job(job)
                self.assertEqual([], findings, f"example {mode} must produce zero findings")
                manifest = _load(job / "manifest.json")
                self.assertEqual(mode, manifest["mode"], "example folder must match its manifest mode")
                handoff = job / "parent-handoff.json"
                if mode in VSL_MODES:
                    self.assertTrue(handoff.is_file(), f"{mode} example must carry the parent handoff")
                else:
                    self.assertFalse(handoff.exists(), f"{mode} example must not carry a parent handoff")


class IntakeOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (SKILL_ROOT / "INSTRUCTIONS.md").read_text(encoding="utf-8")

    def _stages(self):
        stages = {}
        for match in re.finditer(r"^### (\d+)\. (.+)$", self.text, re.M):
            stages[int(match.group(1))] = (match.start(), match.group(2))
        return stages

    def test_stage_order_is_canonical_and_mode_first(self):
        stages = self._stages()
        self.assertEqual(list(range(1, 16)), sorted(stages), "canonical stages 1 to 15, contiguous")
        positions = [stages[n][0] for n in range(1, 16)]
        self.assertEqual(sorted(positions), positions, "stages appear in numeric order in the document")
        self.assertIn("intake", stages[1][1].lower(), "stage 1 is the mode-first intake")
        self.assertIn("job package", stages[3][1].lower(), "stage 3 creates the V2 job package")
        self.assertIn("model", stages[7][1].lower(), "stage 7 resolves the authoring model")

    def test_intake_asks_the_mode_question_verbatim(self):
        # Wording is the contract; line wrapping in the markdown is not.
        normalized = re.sub(r"\s+", " ", self.text)
        self.assertIn(MODE_QUESTION, normalized)

    def test_legacy_path_comes_after_the_canonical_stages(self):
        legacy_at = self.text.find("## Legacy compatibility path")
        self.assertGreater(legacy_at, -1, "the legacy section exists")
        self.assertGreater(
            legacy_at,
            self._stages()[15][0],
            "the legacy path is documented after, and therefore subordinate to, the canonical stages",
        )


class LegacyDefaultTests(unittest.TestCase):
    # A line may mention legacy and default together only inside a negation
    # construction: a negation word shortly before the word "default".
    NEGATED_DEFAULT = re.compile(
        r"\b(never|not|no|without|refuses?|fails?)\b[^.]{0,60}\bdefault", re.IGNORECASE
    )

    def _skill_documents(self):
        return [
            path
            for path in sorted(SKILL_ROOT.rglob("*.md"))
            if "tests" not in path.parts and "node_modules" not in path.parts
        ]

    def test_no_document_presents_legacy_as_default(self):
        violations = []
        mentions = 0
        for path in self._skill_documents():
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                lowered = line.lower()
                if "legacy" in lowered and "default" in lowered:
                    mentions += 1
                    if not self.NEGATED_DEFAULT.search(line):
                        violations.append(f"{path.relative_to(SKILL_ROOT)}:{lineno}: {line.strip()}")
        self.assertGreater(mentions, 0, "the check must not be vacuous: legacy/default lines exist")
        self.assertEqual([], violations, "legacy may be paired with default only in a negation")

    def test_canonical_docs_frame_legacy_as_explicit_migration_choice(self):
        for name in ("SKILL.md", "INSTRUCTIONS.md"):
            with self.subTest(document=name):
                text = (SKILL_ROOT / name).read_text(encoding="utf-8")
                framed = False
                for match in re.finditer(r"legacy", text, re.IGNORECASE):
                    window = text[max(0, match.start() - 300): match.start() + 300].lower()
                    if "explicit" in window and "migrat" in window:
                        framed = True
                        break
                self.assertTrue(
                    framed,
                    f"{name} must describe the legacy path as an explicit choice reached through migration",
                )


class ModeEnumTests(unittest.TestCase):
    def test_skill_md_mode_table_matches_schema_enum(self):
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        named = set()
        for line in text.splitlines():
            match = re.match(r"^\|\s*`([^`]+)`", line)
            if match:
                named.add(match.group(1))
        self.assertTrue(named, "SKILL.md must name modes in its mode table")
        self.assertEqual(
            _schema_modes(),
            named,
            "every mode SKILL.md names must be a canonical schema mode, with none missing or extra",
        )


if __name__ == "__main__":
    unittest.main()
