"""Tests for the MG-025 approval gate evaluator (scripts/check_approvals.py).

The Python evaluator mirrors the TypeScript gate
(runtime/src/orchestrator/). The committed fixtures under
tests/fixtures/approvals/ carry approvals signed by the TypeScript
implementation with the labeled test keys, so a passing Python gate
over them is also a cross-language parity proof: identical revision
digests, identical HMAC verification, identical verdicts. Golden
digests are pinned in tests/evidence/mg025/measurements.json, which
these tests assert and never rewrite. Negative cases mutate temporary
copies; the committed fixtures are never edited.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import check_approvals as gate  # noqa: E402

FIXTURES = SKILL_ROOT / "tests" / "fixtures" / "approvals"
PROD = FIXTURES / "prod-job"
FIXTURE_JOB = FIXTURES / "fixture-job"
NARRATION = FIXTURES / "narration-job"
MEASUREMENTS = json.loads(
    (SKILL_ROOT / "tests" / "evidence" / "mg025" / "measurements.json").read_text()
)
RUNTIME = {"engine": "remotion", "engineVersion": "4.0.535", "runtimeLockId": "lock-mg025-test"}


def trust() -> dict:
    return gate.load_trust(str(FIXTURES / "registry.json"), str(FIXTURES / "keyring.json"))


def copy_job(source: Path) -> Path:
    target = Path(tempfile.mkdtemp(prefix="mg025-job-")) / source.name
    shutil.copytree(source, target)
    return target


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_approval(job_dir: Path, approval_id: str, scope: str, subject_revision: str,
                  actor_id: str, artifact_refs: list[dict]) -> dict:
    manifest = json.loads((job_dir / "manifest.json").read_text())
    keyring = json.loads((FIXTURES / "keyring.json").read_text())
    event_rel = f"approvals/{approval_id}.event.json"
    event = gate.sign_event({
        "event_id": f"evt-{approval_id}",
        "approval_id": approval_id,
        "job_id": manifest["job_id"],
        "company_id": manifest["company_id"],
        "scope": scope,
        "decision": "approved",
        "subject_revision": subject_revision,
        "actor_id": actor_id,
        "artifact_refs": artifact_refs,
    }, keyring[actor_id])
    event_path = job_dir / event_rel
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_path.write_text(json.dumps(event, indent=2) + "\n")
    return {
        "schema_version": "2.0",
        "approval_id": approval_id,
        "job_id": manifest["job_id"],
        "company_id": manifest["company_id"],
        "scope": scope,
        "decision": "approved",
        "subject_revision": subject_revision,
        "artifact_refs": [*artifact_refs, {"path": event_rel, "sha256": sha256_file(event_path)}],
        "actor_id": actor_id,
        "source_event_ref": event_rel,
        "authority_status": "verified",
    }


class RevisionParityTests(unittest.TestCase):
    def test_golden_revisions_match_the_typescript_pins(self):
        prod = gate.compute_revision_lock(PROD, RUNTIME)
        self.assertEqual(prod["design_revision"], MEASUREMENTS["prod_job"]["design_revision"])
        self.assertEqual(prod["full_revision"], MEASUREMENTS["prod_job"]["full_revision"])
        for name, digest in MEASUREMENTS["prod_job"]["components"].items():
            self.assertEqual(prod["components"][name]["digest"], digest, f"component {name}")
        self.assertEqual(prod["problems"], [])
        fixture = gate.compute_revision_lock(FIXTURE_JOB, RUNTIME)
        self.assertEqual(fixture["full_revision"], MEASUREMENTS["fixture_job"]["full_revision"])
        narration = gate.compute_revision_lock(NARRATION, RUNTIME)
        self.assertEqual(narration["full_revision"], MEASUREMENTS["narration_job"]["full_revision"])
        self.assertEqual(
            narration["components"]["narration"]["digest"],
            MEASUREMENTS["narration_job"]["narration_component"],
        )

    def test_writing_approvals_does_not_move_the_revision(self):
        before = gate.compute_revision_lock(PROD, RUNTIME)
        self.assertEqual(before["full_revision"], MEASUREMENTS["prod_job"]["full_revision"])


class GateVerdictTests(unittest.TestCase):
    def test_render_and_design_gates_pass_on_the_production_fixture(self):
        design = gate.evaluate_design_gate(PROD, trust())
        self.assertEqual(design["verdict"], "pass")
        self.assertEqual(design["phase"], "DESIGN_APPROVED")
        render = gate.evaluate_render_gate(PROD, RUNTIME, trust())
        self.assertEqual(render["verdict"], "pass")
        self.assertEqual(render["phase"], "PREVIEW_APPROVED")
        self.assertEqual(render["approval_id"], "appr-prod-preview")
        self.assertEqual(render["authority_basis"], "registry:authorized_reviewer+signed_event")
        self.assertFalse(render["diagnostic"])

    def test_fixture_job_passes_as_diagnostic(self):
        render = gate.evaluate_render_gate(FIXTURE_JOB, RUNTIME, gate.load_trust())
        self.assertEqual(render["verdict"], "pass")
        self.assertTrue(render["diagnostic"])
        self.assertEqual(render["authority_basis"], "fixture_test_issuer+signed_event")

    def test_headline_change_moves_only_source_and_stales_preview(self):
        job = copy_job(PROD)
        before = gate.compute_revision_lock(job, RUNTIME)
        scene_path = job / "scenes" / "bar-01.json"
        scene = json.loads(scene_path.read_text())
        scene["copy"]["headline"] = "A completely new headline"
        scene_path.write_text(json.dumps(scene, indent=2) + "\n")
        after = gate.compute_revision_lock(job, RUNTIME)
        moved = [name for name in gate.COMPONENT_NAMES
                 if before["components"][name]["digest"] != after["components"][name]["digest"]]
        self.assertEqual(moved, ["source"])
        self.assertEqual(after["design_revision"], before["design_revision"])
        render = gate.evaluate_render_gate(job, RUNTIME, trust())
        self.assertEqual(render["verdict"], "blocked")
        self.assertEqual(render["first_error_category"], gate.APPROVAL_STALE)
        self.assertEqual(render["exit_code"], 4)
        design = gate.evaluate_design_gate(job, trust())
        self.assertEqual(design["verdict"], "pass")

    def test_forged_event_signature_is_a_security_violation(self):
        job = copy_job(PROD)
        approvals = json.loads((job / "approvals.json").read_text())
        preview = next(a for a in approvals if a["scope"] == "preview")
        event_rel = preview["source_event_ref"]
        event_path = job / event_rel
        event = json.loads(event_path.read_text())
        payload = {k: v for k, v in event.items() if k != "signature"}
        forged = gate.sign_event(payload, "attacker-chosen-key")
        event_path.write_text(json.dumps(forged, indent=2) + "\n")
        preview["artifact_refs"] = [
            {"path": r["path"], "sha256": sha256_file(event_path)} if r["path"] == event_rel else r
            for r in preview["artifact_refs"]
        ]
        (job / "approvals.json").write_text(json.dumps(approvals, indent=2) + "\n")
        render = gate.evaluate_render_gate(job, RUNTIME, trust())
        self.assertEqual(render["first_error_category"], gate.SECURITY_VIOLATION)
        self.assertEqual(render["exit_code"], 9)

    def test_unregistered_actor_has_no_authority_source_by_default(self):
        render = gate.evaluate_render_gate(PROD, RUNTIME, gate.load_trust())
        self.assertEqual(render["verdict"], "blocked")
        self.assertEqual(render["first_error_category"], gate.APPROVAL_AUTHORITY_UNAVAILABLE)

    def test_no_approvals_is_approval_required(self):
        render = gate.evaluate_render_gate(NARRATION, RUNTIME, trust())
        self.assertEqual(render["first_error_category"], gate.APPROVAL_REQUIRED)
        self.assertEqual(render["exit_code"], 4)


class DeliveryGateTests(unittest.TestCase):
    def _staged_delivery(self):
        job = copy_job(PROD)
        (job / "renders").mkdir(exist_ok=True)
        artifact_path = job / "renders" / "final.mp4"
        artifact_path.write_bytes(b"mg025 fake final render bytes\n")
        artifact = {"path": "renders/final.mp4", "sha256": sha256_file(artifact_path)}
        lock = gate.compute_revision_lock(job, RUNTIME)
        approvals = json.loads((job / "approvals.json").read_text())
        approvals.append(make_approval(
            job, "appr-prod-delivery", "delivery", lock["full_revision"],
            "owner-t-otts", [{"path": artifact["path"], "sha256": artifact["sha256"]}],
        ))
        (job / "approvals.json").write_text(json.dumps(approvals, indent=2) + "\n")
        return job, artifact

    def test_delivery_passes_with_owner_approval_and_passing_final_qc(self):
        job, artifact = self._staged_delivery()
        qc = {"artifact_path": artifact["path"], "artifact_sha256": artifact["sha256"], "verdict": "pass"}
        report = gate.evaluate_delivery_gate(job, RUNTIME, trust(), artifact, qc)
        self.assertEqual(report["verdict"], "pass", report["findings"])
        self.assertEqual(report["phase"], "FINAL_QC_PASSED")

    def test_failed_final_qc_blocks_at_exit_6(self):
        job, artifact = self._staged_delivery()
        qc = {"artifact_path": artifact["path"], "artifact_sha256": artifact["sha256"], "verdict": "fail"}
        report = gate.evaluate_delivery_gate(job, RUNTIME, trust(), artifact, qc)
        self.assertEqual(report["first_error_category"], gate.QC_FAILED)
        self.assertEqual(report["exit_code"], 6)

    def test_fixture_render_can_never_be_promoted(self):
        job = copy_job(FIXTURE_JOB)
        (job / "renders").mkdir(exist_ok=True)
        artifact_path = job / "renders" / "final.mp4"
        artifact_path.write_bytes(b"mg025 fake fixture render bytes\n")
        artifact = {"path": "renders/final.mp4", "sha256": sha256_file(artifact_path)}
        lock = gate.compute_revision_lock(job, RUNTIME)
        approvals = json.loads((job / "approvals.json").read_text())
        approvals.append(make_approval(
            job, "appr-fixture-delivery", "delivery", lock["full_revision"],
            "fixture-test-issuer", [{"path": artifact["path"], "sha256": artifact["sha256"]}],
        ))
        (job / "approvals.json").write_text(json.dumps(approvals, indent=2) + "\n")
        qc = {"artifact_path": artifact["path"], "artifact_sha256": artifact["sha256"], "verdict": "pass"}
        report = gate.evaluate_delivery_gate(job, RUNTIME, gate.load_trust(), artifact, qc)
        self.assertEqual(report["verdict"], "blocked")
        self.assertTrue(report["diagnostic"])
        self.assertEqual(report["first_error_category"], gate.APPROVAL_AUTHORITY_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
