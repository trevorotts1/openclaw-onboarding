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
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
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
    def test_71_schema_is_a_byte_copy_of_49(self):
        self.assertEqual(SCHEMA_71.read_bytes(), SCHEMA_49.read_bytes())

    def test_both_accept_1_0_1_1_1_2_and_keep_delivery_bindings(self):
        for path in (SCHEMA_49, SCHEMA_71):
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(doc["properties"]["schema_version"]["enum"], ["1.0", "1.1", "1.2"], path)
            self.assertIn("delivery_bindings", doc["properties"], path)

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
                "subject_type": "launch_plan_build", "subject_hash": dl.vlp.plan_document_hash(record),
                "owner_identity_ref": "client-test-1", "source_message_ref": "msg-test-1",
                "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scope": ["launch_plan_build"], "revoked": False,
                "verification_class": "recorded_consent_not_cryptographically_sealed"}
            out = td / "dispatch"
            dl.dispatch(copy.deepcopy(record), approval, client_identity_ref="client-test-1",
                        worker_identity_ref="worker-test-9", copy_profile=normalized["copy_profile"],
                        allowed_write_target="local_only", out_dir=out)
            launch_path = td / "launch.json"
            launch_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            fake71 = td / "skill71"
            made = subprocess.run([PY, str(S49 / "scripts" / "make_fake_skill71.py"), str(fake71)],
                                  capture_output=True, text=True)
            self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
            (td / "bridge.json").write_text(json.dumps({
                "skill71": {"root": str(fake71), "python": PY},
                "landing": {"run_dir": str(td / "run"), "page_version": "standard", "page_kind": "sales",
                            "brand_owner": "TEST-ONLY Client", "image_cap": 12,
                            "launch_record": str(launch_path), "brand_file": str(brand)}}), encoding="utf-8")
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
