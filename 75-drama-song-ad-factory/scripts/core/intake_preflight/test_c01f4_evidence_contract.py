"""C01F4-evidence: the published evidence fields are one contract with the
descriptor artifacts. A row naming evidence the descriptors do not emit is
refused by name; a real run (assembler writes edit/timeline.json + edit/ad.mp4)
passes the order gate and the completion evidence on the edit/ paths."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(CORE), str(CORE / "intake_preflight")]
from intake_preflight import factory


class EvidenceMatchesDescriptors(unittest.TestCase):
    def test_stale_assembly_evidence_refused_by_name(self):
        reg = copy.deepcopy(factory.STAGE_REGISTRY)
        reg["assembly"]["required_evidence"] = ["assembly/timeline.json"]
        reg["assembly"]["output_producer"] = "assembly/timeline.json"
        reg["assembly"]["idempotency"] = "assembly/<timeline-digest>"
        problems = factory.validate_registry(registry=reg)
        self.assertTrue(any("assembly" in p and "required_evidence" in p
                            for p in problems), problems)
        self.assertTrue(any("assembly" in p and "output_producer" in p
                            for p in problems), problems)
        self.assertTrue(any("assembly" in p and "idempotency" in p
                            for p in problems), problems)

    def test_stale_evidence_refused_on_contract_path_too(self):
        reg = copy.deepcopy(factory.STAGE_REGISTRY)
        reg["assembly"]["required_evidence"] = ["assembly/timeline.json"]
        contract = factory._stage_contract_problems("assembly",
                                                    reg["assembly"])
        self.assertTrue(any("required_evidence" in p for p in contract),
                        contract)

    def test_repaired_tree_validates_clean(self):
        self.assertEqual(factory.validate_registry(), [])

    def test_real_run_edit_paths_admit_and_complete(self):
        with tempfile.TemporaryDirectory(prefix="c01f4-evidence-") as tmp:
            run = Path(tmp)
            for rel in ("edit/timeline.json", "edit/ad.mp4",
                        "research/receipt.json", "research/claims.json",
                        "research/captures.json",
                        "creative/story.json", "creative/blueprint.json",
                        "script/lyrics.json",
                        "music/picked-song.mp3", "song-choices/pick.json",
                        "continuity/qc-records.json",
                        "continuity/makers.json",
                        "storyboard/shot-list.json",
                        "storyboard/contracts.json",
                        "keyframes/manifest.json",
                        "video/clips.json",
                        "qc/retakes.json",
                        "final-qc/record.json"):
                p = run / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("{}", encoding="utf-8")
            (run / "delivery").mkdir(parents=True, exist_ok=True)
            (run / "delivery" / "receipts.json").write_text(
                '[{"destination": "origin", "status": "delivered"}]',
                encoding="utf-8")
            got = {s: "COMPLETE" for s in factory.CANONICAL_STAGES}
            ok, code, _, missing = factory.production_order_gate(
                run, "delivery", got=got)
            self.assertTrue(ok, (code, missing))
            evidence = factory._collect_completion_evidence(run, got)
            self.assertNotIn("edit/timeline.json",
                             evidence["missing_artifacts"], evidence)
            self.assertNotIn("edit/ad.mp4",
                             evidence["missing_artifacts"], evidence)


if __name__ == "__main__":
    unittest.main()
