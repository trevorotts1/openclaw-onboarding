"""FIX-03: the Skill 83 manifest and the authoritative dependency manifest agree.

Document 3 (Additional November 8th Fixes) FIX-03: two names for the same
substrate were in circulation — `skill.json` named
`shared-utils/signature_launch` while `launcher_core/dependencies.json` named
`shared-utils/signature_launch_contract`. `dependencies.json` is authoritative,
so metadata conforms to it and never defines a second list.

This module is the consistency proof FIX-03 step 4 asks for. It fails when:
  * skill.json grows a second dependency list that disagrees with the manifest,
  * the pointer's target, digest or counts go stale against the manifest,
  * the manifest declares the retired bare name again, or
  * the Skill 49 root manifest (FIX-02) names a dependency that does not exist.

The one thing it does NOT assert is another skill's pointer: registration.json
is a generated record owned outside this lane, and its own staleness is recorded
as a change request rather than silently patched here.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import dependencies  # noqa: E402

OLD_NAME = "shared-utils/signature_launch"
CONTRACT = "shared-utils/signature_launch_contract"
MANIFEST_REF = "launcher_core/dependencies.json"


def _skill_json() -> dict:
    return json.loads((SKILL_ROOT / "skill.json").read_text(encoding="utf-8"))


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


class DependencyNameConsistency(unittest.TestCase):
    def test_skill_json_points_at_the_authoritative_manifest(self):
        spine = _skill_json()["depends_on"]
        self.assertIsInstance(spine, dict)
        self.assertEqual(spine.get("authoritative_manifest"), MANIFEST_REF)

    def test_skill_json_pointer_stamp_matches_the_manifest(self):
        manifest = dependencies.load_manifest()
        spine = _skill_json()["depends_on"]
        self.assertEqual(spine.get("requirements_digest"),
                         dependencies.requirements_digest(manifest))
        self.assertEqual(spine.get("manifest_entry_count"), len(manifest["entries"]))
        self.assertEqual(spine.get("required_entry_count"),
                         sum(1 for e in manifest["entries"] if e.get("required")))

    def test_metadata_spine_finds_nothing_wrong_with_skill_json(self):
        report = dependencies.metadata_spine(dependencies.load_manifest())
        mine = [f for f in report["findings"] if f.startswith("skill.json:")]
        self.assertEqual(mine, [], mine)

    def test_manifest_names_the_contract_and_never_the_retired_bare_name(self):
        refs = [entry["ref"] for entry in dependencies.load_manifest()["entries"]]
        self.assertIn(CONTRACT, refs)
        self.assertNotIn(OLD_NAME, refs)

    def test_skill_json_declares_no_second_dependency_list(self):
        # A pointer may name its target. Anything else that looks like a
        # dependency ref would be a second list, which is the drift FIX-03 bans.
        allowed = set(dependencies._declared_refs(dependencies.load_manifest())) | {MANIFEST_REF}
        # A prose note is not a name: refs carry no whitespace.
        named = {s for s in _strings(_skill_json()["depends_on"])
                 if "/" in s and s != MANIFEST_REF and not any(c.isspace() for c in s)}
        self.assertEqual(named - allowed, set(),
                         f"skill.json names dependencies the manifest does not declare: "
                         f"{sorted(named - allowed)}")
        self.assertNotIn(OLD_NAME, {s for s in named if s == OLD_NAME})


class Skill49RootManifest(unittest.TestCase):
    """FIX-02: the published Skill 49 tree carries its own root manifest."""

    def setUp(self):
        self.path = dependencies._repo_root() / "49-signature-funnel" / "skill.json"

    def test_the_manifest_exists_and_follows_the_family_schema(self):
        self.assertTrue(self.path.is_file(), f"missing root manifest: {self.path}")
        record = json.loads(self.path.read_text(encoding="utf-8"))
        family = _skill_json()
        self.assertEqual(record["schema"], family["schema"])
        self.assertTrue(record["name"].startswith("signature-funnel"), record["name"])
        self.assertEqual(record["entry"], "SKILL.md")

    def test_identity_agrees_with_the_skill_tree_itself(self):
        record = json.loads(self.path.read_text(encoding="utf-8"))
        skill49 = self.path.parent
        self.assertEqual(record["version"],
                         (skill49 / "skill-version.txt").read_text(encoding="utf-8").strip())
        skill_md = (skill49 / "SKILL.md").read_text(encoding="utf-8").split("\n")
        self.assertIn(f"version: {record['version']}", skill_md)
        self.assertIn(f"name: {record['name']}", skill_md)

    def test_every_entrypoint_exists(self):
        record = json.loads(self.path.read_text(encoding="utf-8"))
        skill49 = self.path.parent
        for key, rel in record["entrypoints"].items():
            self.assertTrue((skill49 / rel).is_file(), f"{key}: {rel}")

    def test_every_named_dependency_resolves_in_this_repository(self):
        record = json.loads(self.path.read_text(encoding="utf-8"))
        root = dependencies._repo_root()
        named = list(record["depends_on"]["required"])
        named += list(record["depends_on"].get("pin_composition_requires", []))
        self.assertTrue(named, "the manifest names no dependency at all")
        for name in named:
            self.assertTrue((root / name).exists(), f"named dependency absent: {name}")


if __name__ == "__main__":
    unittest.main()
