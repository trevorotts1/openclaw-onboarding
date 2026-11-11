"""The dependency manifest pins what 83 relies on (issues 20, 22, 34, 89).

* 34: the six SOPs SKILL.md declares are six `sop` rows, each resolved with a read receipt.
* 89: SKILL.md names those six SOP paths and no others, so the prose list cannot drift from the manifest.
* 22: a version floor is only a minimum, so the files 83 imports from 71/78/79/80/81/82 also carry a
  sha256; a changed file is `missing` in the preflight until it is re-stamped on purpose.
* 20: registration.json says how many entries the preflight reports present, and that number is the
  manifest's.

Stdlib only: python3 -m unittest.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import dependencies  # noqa: E402

REPO = SKILL_ROOT.parent
SOP_PATH = re.compile(r"23-ai-workforce-blueprint/[A-Za-z0-9_./-]*SOP-[A-Za-z0-9_.-]*\.md")
SIX_SOPS = {
    "23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-GIP-02-IMAGE-QC.md",
    "23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-GIP-03-GHL-MEDIA-DELIVERY.md",
    "23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-DIU-602.md",
    "23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-DIU-607.md",
    "23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-DIU-610.md",
    "23-ai-workforce-blueprint/master-orchestrator-dept/SOP-07-Full-Funnel-Build-Orchestration.md",
}
# Every file 83 really loads from each page-skill tree (routes/substrate.py loaders, routes/adapters.py
# ADAPTERS and contract paths). The pin must equal this list: a pin that drops one is a file 83 loads unguarded.
LOADED_FILES = {
    "71-blackceo-signature-page": {"scripts/launch_context.py", "scripts/page_result.py"},
    "78-signature-product-selection": {"scripts/build_selection_plan.py", "scripts/emit_page_result.py",
                                       "scripts/run_image_stages.py"},
    "79-signature-order-form": {"references/checkout.schema.json", "scripts/validate_checkout.py"},
    "80-signature-upsell": {"components/adapters/produce.py", "components/adapters/routing_state.py"},
    "81-signature-downsell": {"validators/validate_downsell.py", "validators/validate_request.py"},
    "82-signature-thank-you": {"scripts/run_manifest.py", "scripts/thank_you_resolver.py"},
}
INTERFACE_TREES = {"71-blackceo-signature-page", "78-signature-product-selection", "79-signature-order-form",
                   "80-signature-upsell", "81-signature-downsell", "82-signature-thank-you"}


def _entries(kind: str):
    return [e for e in dependencies.load_manifest()["entries"] if e.get("kind") == kind]


class SopRowTests(unittest.TestCase):
    def test_six_sop_rows_each_with_a_receipt_that_proves_reading(self):
        rows = _entries("sop")
        self.assertEqual({e["ref"] for e in rows}, SIX_SOPS)
        self.assertEqual(len(rows), 6)
        for row in rows:
            self.assertEqual(row.get("modes"), ["assemble"], row["id"])
            result = dependencies._present(row, dependencies._repo_root())
            self.assertEqual(result["status"], "present", f'{row["id"]}: {result["evidence"]}')

    def test_assemble_mode_blocks_on_each_of_the_six_when_its_receipt_is_taken_away(self):
        for row in _entries("sop"):
            with tempfile.TemporaryDirectory() as tmp:
                gone = Path(tmp) / "no-receipts"
                gone.mkdir()
                with mock.patch.object(dependencies, "resolve_skill_dir", return_value=gone):
                    result = dependencies._present(row, dependencies._repo_root())
            self.assertEqual(result["status"], "missing", row["id"])
            self.assertTrue(dependencies.blocking(row, "assemble", result["status"]), row["id"])
            self.assertFalse(dependencies.blocking(row, "plan", result["status"]), row["id"])

    def test_skill_md_names_exactly_the_manifest_sops(self):
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(set(SOP_PATH.findall(text)), {e["ref"] for e in _entries("sop")})
        # one list, not two: each SOP is spelled out once in the "Read order" list
        read_order = text.split("## Read order", 1)[1].split("## Entry", 1)[0]
        for ref in SIX_SOPS:
            self.assertEqual(read_order.count(ref), 1, ref)
        head = text.split("## Your role with the client", 1)[0]
        self.assertEqual(SOP_PATH.findall(head), [], "the top of SKILL.md points at the list, it is not a second one")


class RegistrationTests(unittest.TestCase):
    def test_registration_pointer_digest_counts_and_enablement_evidence_are_the_manifests(self):
        manifest = dependencies.load_manifest()
        self.assertEqual(dependencies.metadata_spine(manifest)["findings"], [])
        record = json.loads((SKILL_ROOT / "registration.json").read_text(encoding="utf-8"))
        said = re.search(r"reports (\d+) present, 0 missing", record["enablement"]["enabled_evidence"])
        self.assertIsNotNone(said, "enabled_evidence no longer states the preflight count")
        self.assertEqual(int(said.group(1)), len(manifest["entries"]))
        report = dependencies.check(mode="assemble")
        self.assertEqual((len(report["present"]), report["missing"]), (len(manifest["entries"]), []))


class VersionAndInterfaceTests(unittest.TestCase):
    def test_every_floor_is_in_the_siblings_current_series(self):
        for entry in _entries("skill_tree"):
            tree = dependencies._resolve(entry["ref"], REPO, "skill_tree")[0]
            current = dependencies._version((tree / "skill-version.txt").read_text(encoding="utf-8"))
            floor = dependencies._version(entry["min_version"])
            self.assertEqual(floor[:2], current[:2], f'{entry["id"]}: floor {floor} is in an older series than {current}')
            self.assertLessEqual(floor, current, entry["id"])

    def test_the_six_page_skills_are_pinned_to_files_83_really_loads(self):
        pinned = {e["ref"]: e["interface_sha256"] for e in _entries("skill_tree") if e.get("interface_sha256")}
        self.assertEqual(set(pinned), INTERFACE_TREES)
        loaders = "\n".join((SKILL_ROOT / rel).read_text(encoding="utf-8")
                            for rel in ("routes/substrate.py", "routes/adapters.py"))
        for tree, files in pinned.items():
            self.assertEqual(set(files), LOADED_FILES[tree], f"{tree}: pinned files are not exactly what 83 loads")
            for rel in files:
                self.assertIn(f"{tree}/{rel}", loaders, f"{tree}/{rel} is pinned but 83 never loads it")
                self.assertEqual(dependencies._sha256_file(REPO / tree / rel), files[rel], f"{tree}/{rel} drifted")

    def _tree(self, tmp: Path):
        tree = tmp / "tree"
        (tree / "scripts").mkdir(parents=True)
        (tree / "skill-version.txt").write_text("1.0.0\n", encoding="utf-8")
        (tree / "scripts" / "api.py").write_text("def build(plan, run_dir):\n    return plan\n", encoding="utf-8")
        entry = {"id": "tree-fixture", "kind": "skill_tree", "ref": "99-fixture", "min_version": "1.0.0",
                 "required": True,
                 "interface_sha256": {"scripts/api.py": dependencies._sha256_file(tree / "scripts" / "api.py")}}
        return tree, entry

    def _present(self, tree: Path, entry: dict) -> dict:
        with mock.patch.object(dependencies, "_resolve", return_value=(tree, None)):
            return dependencies._present(entry, tree.parent)

    def test_a_renamed_field_inside_a_pinned_file_fails_the_preflight_even_above_the_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, entry = self._tree(Path(tmp))
            self.assertEqual(self._present(tree, entry)["status"], "present")
            (tree / "scripts" / "api.py").write_text("def build(plan, out_dir):\n    return plan\n", encoding="utf-8")
            (tree / "skill-version.txt").write_text("9.9.9\n", encoding="utf-8")  # newer than the floor: still refused
            drifted = self._present(tree, entry)
            self.assertEqual(drifted["status"], "missing", drifted["evidence"])
            self.assertIn("interface drift in scripts/api.py (changed)", drifted["evidence"])
            (tree / "scripts" / "api.py").unlink()
            self.assertIn("(absent)", self._present(tree, entry)["evidence"])

    def test_cli_dependencies_prints_each_pinned_interface_with_expected_and_observed_sha256(self):
        # Issue 22 acceptance: `cli dependencies` reports the interface hashes, not only enforces them.
        import contextlib
        import io
        from launcher_core import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["dependencies", "--mode", "assemble"])
        shown = out.getvalue()
        count = 0
        for entry in _entries("skill_tree"):
            for rel, want in (entry.get("interface_sha256") or {}).items():
                line = next((ln for ln in shown.splitlines() if f"interface {rel} " in ln and want in ln), None)
                self.assertIsNotNone(line, f"{entry['ref']}/{rel}: expected hash not shown")
                self.assertIn(f"expected sha256={want}", line)
                self.assertIn(f"observed sha256={dependencies._sha256_file(REPO / entry['ref'] / rel)}", line)
                count += 1
        self.assertGreaterEqual(count, 6)

    def test_a_tree_with_no_interface_pin_behaves_as_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, entry = self._tree(Path(tmp))
            del entry["interface_sha256"]
            (tree / "scripts" / "api.py").write_text("changed\n", encoding="utf-8")
            self.assertEqual(self._present(tree, entry)["status"], "present")

    def test_stamp_interfaces_rewrites_only_the_moved_hash_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, entry = self._tree(Path(tmp))
            manifest = Path(tmp) / "dependencies.json"
            manifest.write_text(json.dumps({"entries": [entry]}, indent=2), encoding="utf-8")
            before = manifest.read_text(encoding="utf-8")
            with mock.patch.object(dependencies, "MANIFEST", manifest), \
                    mock.patch.object(dependencies, "_resolve", return_value=(tree, None)):
                self.assertEqual(dependencies.stamp_interfaces(Path(tmp)), [])  # nothing moved: nothing written
                (tree / "scripts" / "api.py").write_text("def build(plan, out_dir):\n    return plan\n", encoding="utf-8")
                self.assertEqual(dependencies.stamp_interfaces(Path(tmp)), ["99-fixture/scripts/api.py"])
                after = manifest.read_text(encoding="utf-8")
                self.assertEqual(self._present(tree, json.loads(after)["entries"][0])["status"], "present")
            self.assertNotEqual(before, after)
            self.assertEqual(before.replace(entry["interface_sha256"]["scripts/api.py"],
                                            dependencies._sha256_file(tree / "scripts" / "api.py")), after)


if __name__ == "__main__":
    unittest.main()
