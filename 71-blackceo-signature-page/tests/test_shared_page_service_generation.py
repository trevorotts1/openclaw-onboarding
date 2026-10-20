#!/usr/bin/env python3
"""Regression: a generation run that produces zero images is FAILED.

scripts/shared_page_service.py used to treat --pipeline-command as
optional and return 0 after the admission seam, so a local fixture run
that generated nothing read exactly like a generated run (diagnosis
2026-10-19, "Concrete implementation gap": exit 0, seven intake/routing/
brand files, zero images). Pins:
  (a) a requested generation run whose pipeline exits 0 but writes no
      images exits non-zero and prints FAILED, naming the zero-image
      condition;
  (b) the legitimate --validation-only mode still succeeds but labels
      itself "MODE=validation-only: no artifacts generated", so it can
      never read as a generation run.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "scripts" / "shared_page_service.py"
PY = sys.executable

IDENT = {"tenant_id": "tenant-acme", "location_id": "loc-123",
         "launch_id": "launch-2026-bf", "revision": 3}

def dump(doc):
    return (json.dumps(doc, indent=2) + "\n").encode("utf-8")

def graph_doc():
    return {
        "schema_version": "1.0", **IDENT,
        "nodes": [
            {"page_id": "page-landing-1", "role": "landing"},
            {"page_id": "page-select-1", "role": "product_selection"},
            {"page_id": "page-thanks-1", "role": "thank_you"},
        ],
        "edges": [
            {"from": "page-landing-1", "event": "interest_submitted",
             "to": "page-select-1", "guard": "verified_native_contact_submit"},
            {"from": "page-select-1", "event": "selection_validated",
             "to": "page-thanks-1", "guard": "selection_complete"},
        ],
        "pending_failed_payment_behavior":
            "retain_current_purchase_state_until_resolved_or_explicit_decline",
        "test_only": True,
    }

def request_doc(graph_hash):
    return {
        "schema_version": "1.0", **IDENT,
        "request_id": "req-001", "page_id": "page-landing-1",
        "page_role": "landing", "assigned_skill": 71,
        "approval_ref": "approval://plan-9", "input_hash": "in-hash-1",
        "brand_ref": "brand:acme", "brand_hash": "brand-hash-1",
        "route_graph_ref": "route-graph.json", "route_graph_hash": graph_hash,
        "offer_refs": ["offer-main"], "copy_profile": "standard",
        "allowed_write_target": "local_only", "test_only": True,
    }

def launch_doc(graph_hash):
    offer = {
        "offer_id": "offer-main", "slot": "main", "display_name": "Main Offer",
        "deliverables": ["the thing"], "exclusions": [], "entitlement_ids": [],
        "requires": [], "excludes": [], "native_product_id": None,
        "prices": [{"price_choice_id": "pc-1", "currency": "USD",
                    "amount_minor": 4900, "billing_type": "one_time",
                    "native_price_id": None, "schedule": [],
                    "approval_status": "approved"}],
        "source_kind": "owner", "source_ref": "owner-brief", "test_only": True,
    }
    return {
        "schema_version": "1.0", **IDENT,
        "journey_mode": "multiple_options", "status": "approved",
        "brand_ref": "brand:acme", "brand_hash": "brand-hash-1",
        "route_graph_ref": "route-graph.json", "route_graph_hash": graph_hash,
        "plan_approval_ref": "approval://plan-9", "offers": [offer],
        "extras": {"upsell_1": False, "downsell_1": False, "upsell_2": False},
        "bump_enabled": False, "image_provider": "agnes",
        "source_refs": ["owner-brief"], "test_only": True,
    }

class ZeroImageGenerationIsFailure(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s71-zero-image-"))
        self.addCleanup(lambda: shutil.rmtree(self.td, ignore_errors=True))
        self.graph_bytes = dump(graph_doc())
        self.ghash = hashlib.sha256(self.graph_bytes).hexdigest()
        self.brand_path = self.write("brand.json",
                                     json.dumps({"brand_owner": "Acme"}))
        self.brand_hash = hashlib.sha256(self.brand_path.read_bytes()).hexdigest()
        self.write("graph.json", self.graph_bytes)
        self.write("request.json", dump(request_doc(self.ghash)))
        self.write("launch.json", dump(launch_doc(self.ghash)))
        self.run_dir = self.td / "run"

    def write(self, name, raw):
        p = self.td / name
        p.write_bytes(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
        return p

    def service_cmd(self, *extra):
        return [PY, str(SERVICE),
                "--request", str(self.td / "request.json"),
                "--run-dir", str(self.run_dir),
                "--page-version", "standard",
                "--brand-owner", "Acme Owner",
                "--image-cap", "40",
                "--brand-file", str(self.brand_path),
                "--launch-record", str(self.td / "launch.json"),
                "--route-graph", str(self.td / "graph.json"),
                *extra]

    def run_service(self, *extra):
        return subprocess.run(self.service_cmd(*extra),
                              capture_output=True, text=True)

    def images_on_disk(self):
        if not self.run_dir.exists():
            return []
        return [p for p in self.run_dir.rglob("*.png") if p.is_file()]

    def seal_fixtures(self):
        """Bind the request and launch to the real brand and graph bytes so
        the admission seam accepts and the assertion lands on generation."""
        request = request_doc(self.ghash)
        request["brand_hash"] = self.brand_hash
        self.write("request.json", dump(request))
        launch = launch_doc(self.ghash)
        launch["brand_hash"] = self.brand_hash
        self.write("launch.json", dump(launch))

    def test_generation_run_with_zero_images_fails(self):
        self.seal_fixtures()
        # A pipeline that exits 0 and writes nothing: the exact shape that
        # used to read as success.
        proc = self.run_service("--pipeline-command", "true")
        assert proc.returncode != 0, (
            f"zero-image generation run exited 0\nSTDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}")
        self.assertIn("FAILED", proc.stdout)
        self.assertIn("zero images", proc.stdout)
        self.assertEqual(self.images_on_disk(), [])
        # The legitimate validation-only mode stays, and labels itself.
        proc = self.run_service("--validation-only")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("MODE=validation-only: no artifacts generated",
                      proc.stdout)
        self.assertEqual(self.images_on_disk(), [])

if __name__ == "__main__":
    unittest.main()
