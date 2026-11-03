"""CON-01: one launch schema authority (Skill 49), byte-copied into Skill 71, proven with the REAL consumers.

Skill 83 stamps launch record schema 1.2. Before this fix Skill 71's launch-context import accepted only
1.0/1.1, so a real landing build was refused while the fake-consumer suites stayed green. Nothing here
fakes the consumer: the record is built by 83's own bridge and fed to 71's real launch_context.validate and
to 49's real landing_bridge -> 71 write_intake (only the 14-stage production gate is stubbed, as in 49's
own landing bridge tests).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

import substrate  # noqa: E402
from launcher_core import image_plan, intake, launch_bridge, route  # noqa: E402

S49 = REPO / "49-signature-funnel"
S71 = REPO / "71-blackceo-signature-page"
SCHEMA_49 = S49 / "schema" / "launch.schema.json"
SCHEMA_71 = S71 / "references" / "launch.schema.json"
SCHEMA_SHARED = REPO / "shared-utils" / "signature_launch" / "domain" / "launch.schema.json"
PY = sys.executable


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def elevation_record(brand_file: str) -> dict:
    doc = json.loads((SKILL_ROOT / "fixtures" / "elevation" / "intake.json").read_text(encoding="utf-8"))
    doc["image_plan"] = {"brand_file": brand_file, "brand_owner": "TEST-ONLY Client"}
    normalized = intake.validate(doc)
    inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=normalized["test_only"])
    return launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs), normalized


class LaunchSchemaParity(unittest.TestCase):
    def test_71_and_shared_schemas_are_byte_copies_of_49(self):
        for copy_path in (SCHEMA_71, SCHEMA_SHARED):
            self.assertEqual(copy_path.read_bytes(), SCHEMA_49.read_bytes(), copy_path)

    def test_both_accept_1_0_1_1_1_2_and_keep_delivery_bindings(self):
        for path in (SCHEMA_49, SCHEMA_71, SCHEMA_SHARED):
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(doc["properties"]["schema_version"]["enum"], ["1.0", "1.1", "1.2"], path)
            self.assertIn("delivery_bindings", doc["properties"], path)
            self.assertIn("included_in", doc["properties"]["offers"]["items"]["properties"]["relationships"]["properties"], path)

    def test_real_83_record_passes_71_launch_context(self):
        lc = _load(S71 / "scripts" / "launch_context.py", "con01_launch_context")
        schema = json.loads(SCHEMA_71.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            record, _ = elevation_record(str(Path(td) / "brand.json"))
        self.assertEqual(record["schema_version"], "1.2")
        self.assertEqual(lc.validate(record, schema, label="launch"), [])
        for version in ("1.0", "1.1"):
            self.assertEqual(lc.validate({**record, "schema_version": version}, schema, label="launch"), [])
        self.assertNotEqual(lc.validate({**record, "schema_version": "2.0"}, schema, label="launch"), [])

    def test_optional_selection_fields_pass_71_launch_context_and_unknown_keys_still_refused(self):
        lc = _load(S71 / "scripts" / "launch_context.py", "con01_launch_context_sel")
        schema = json.loads(SCHEMA_71.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            record, _ = elevation_record(str(Path(td) / "brand.json"))
        record = copy.deepcopy(record)
        for offer in record["offers"]:
            if offer["slot"] == "main":
                offer.update(
                    intended_buyer="TEST-ONLY buyer", primary_outcome="TEST-ONLY outcome",
                    limited_deliverables=[{"item": "TEST-ONLY limited", "note": "TEST-ONLY note"}],
                    conditional_deliverables=["TEST-ONLY cond"])
        record["selection_faq"] = [{"question": "TEST-ONLY q?", "answer": "TEST-ONLY a"}]
        record["trust_items"] = ["TEST-ONLY trust"]
        self.assertEqual(lc.validate(record, schema, label="launch"), [])
        bad = copy.deepcopy(record)
        bad["offers"][0]["not_a_field"] = "x"
        self.assertNotEqual(lc.validate(bad, schema, label="launch"), [])
        bad = copy.deepcopy(record)
        bad["selection_faq"] = [{"question": "TEST-ONLY q?"}]
        self.assertNotEqual(lc.validate(bad, schema, label="launch"), [])

    def test_real_landing_bridge_into_71_write_intake_exits_0_on_a_1_2_record(self):
        dl = substrate.dispatch()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            brand = td / "brand-src.json"
            brand.write_bytes(b'{"brand_id": "test-only-brand", "test_only": true}\n')
            record, normalized = elevation_record(str(brand))
            record["brand_ref"] = "brand.json"
            record["brand_hash"] = hashlib.sha256(brand.read_bytes()).hexdigest()
            record["route_graph_ref"] = "route-graph.json"
            self.assertEqual(record["schema_version"], "1.2")
            approval = {
                "schema_version": "1.0", "approval_id": record["plan_approval_ref"],
                "kind": "launch_plan_build", "plan_hash": dl.vlp.plan_document_hash(record),
                "client_identity": "client-test-1", "source_message_ref": "msg-test-1",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "scope": ["launch_plan_build"], "revoked": False,
                "verification_class": "recorded_consent_not_cryptographically_sealed"}
            out = td / "dispatch"
            dl.dispatch(copy.deepcopy(record), approval, client_identity_ref="client-test-1",
                        worker_identity_ref="worker-test-9", copy_profile=normalized["copy_profile"],
                        allowed_write_target="local_only", out_dir=out)
            launch_path = td / "launch.json"
            launch_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            fake71 = td / "skill71"
            # a token-driven page needs the shared design components installed beside the Skill 71 tree
            shutil.copytree(REPO / "shared-utils" / "signature_launch" / "design",
                            td / "shared-utils" / "signature_launch" / "design",
                            ignore=shutil.ignore_patterns("tests", "__pycache__"))
            made = subprocess.run([PY, str(S49 / "scripts" / "make_fake_skill71.py"), str(fake71)],
                                  capture_output=True, text=True)
            self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
            # the landing lane must draw its pages: the shared image inputs file of the approved image plan
            image_inputs = {"design_style": "B", "design_style_source": "client_choice",
                            "creative_direction": "TEST-ONLY creative direction: calm, bold, editorial",
                            "brand_file": str(brand), "brand_owner": "TEST-ONLY Client", "image_cap": 12,
                            "image_provider": "stub", "test_only": True}
            inputs_path = td / "image_inputs.json"
            inputs_path.write_text(json.dumps(image_inputs), encoding="utf-8")
            (td / "bridge.json").write_text(json.dumps({
                "skill71": {"root": str(fake71), "python": PY},
                "landing": {"run_dir": str(td / "run"), "page_version": "standard", "page_kind": "sales",
                            "brand_owner": "TEST-ONLY Client", "image_cap": 12,
                            "launch_record": str(launch_path), "brand_file": str(brand),
                            "draft": True,  # the stubbed 14-stage gate never closes: a fixture run is a declared draft
                            "image_inputs": str(inputs_path),
                            "image_plan": {"image_inputs": str(inputs_path), "image_cap": 12,
                                           "brand_owner": "TEST-ONLY Client", "design_style": "B",
                                           "image_provider": "stub"}}}), encoding="utf-8")
            proc = subprocess.run(
                [PY, str(S49 / "scripts" / "landing_bridge.py"), "--request", str(out / "request-landing.json"),
                 "--result", str(td / "result.json"), "--work-dir", str(out),
                 "--bridge-config", str(td / "bridge.json"), "--landing-pages", "sales"],
                capture_output=True, text=True, timeout=600)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            written = json.loads((td / "run" / "intake.json").read_text(encoding="utf-8"))
            self.assertEqual(written["launch_profile"], "signature_launch_landing")


if __name__ == "__main__":
    unittest.main()
