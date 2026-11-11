#!/usr/bin/env python3
"""Issue 81: Skill 50's P4 deploy approval is a verified record, never a bare flag.

LAUNCH-INTAKE.md says "A bare "approved": true flag anywhere is never read as
evidence", yet P4's _chk_deploy_approval accepted `approved:true` + any
`approved_by` string from a file the run itself could write. It now requires
working/deploy/approval.json to name a Command Center approval that the shared
approval_record.verify confirms (kind email_deploy, sha256 of the QC'd
working/copy/emails.json, this run as scope, test_only=False).

The real verifier trusts only a live Command Center fetch, so these tests point
run_email_engine at a stub verifier that accepts exactly one minted record; one
more test drives the REAL shared verifier with no Command Center configured and
shows it still refuses (fail closed). Hermetic: no network, temp dir only.

Run: python3 -m pytest 50-email-engine/tests/test_deploy_approval.py -q
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
ENGINE = SKILL / "run_email_engine.py"

_spec = importlib.util.spec_from_file_location("deploy_approval_run_email_engine", ENGINE)
engine = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = engine
_spec.loader.exec_module(engine)

MINTED = "APPR-MINTED-0001"
STUB = '''\
class ApprovalRefused(Exception):
    pass


class ApprovalUnavailable(Exception):
    pass


def verify(approval_id, kind, plan_hash, scope, *, test_only=False, **kw):
    if test_only is not False:
        raise ApprovalRefused("a file or test-only record is not an approval")
    want = ({minted!r}, "email_deploy", {plan_hash!r}, {scope!r})
    if (approval_id, kind, plan_hash, scope) != want:
        raise ApprovalRefused("not the minted approval for this copy and this run")
    return {{"ok": True}}
'''


class DeployApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run-seam-81"
        (self.run_dir / "working" / "deploy").mkdir(parents=True)
        (self.run_dir / "working" / "copy").mkdir(parents=True)
        self.emails = self.run_dir / "working" / "copy" / "emails.json"
        self.emails.write_text('{"emails": []}', encoding="utf-8")
        self.approval = self.run_dir / "working" / "deploy" / "approval.json"
        self.stub = Path(self.tmp.name) / "approval_record_stub.py"
        self._install_stub()

    def _install_stub(self):
        digest = hashlib.sha256(self.emails.read_bytes()).hexdigest()
        self.stub.write_text(STUB.format(minted=MINTED, plan_hash=digest,
                                         scope=[self.run_dir.name]), encoding="utf-8")
        patcher = mock.patch.object(engine, "_APPROVAL_RECORD", self.stub)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _check(self, record):
        self.approval.write_text(json.dumps(record), encoding="utf-8")
        return engine._chk_deploy_approval(self.run_dir)

    def test_bare_approved_flag_is_refused_with_the_launch_intake_sentence(self):
        ok, message = self._check({"approved": True, "approved_by": "Founder"})
        self.assertFalse(ok)
        self.assertIn("AF-EMAIL-DEPLOY-UNAPPROVED", message)
        self.assertIn('A bare "approved": true flag anywhere is never read as evidence', message)

    def test_a_bare_flag_beside_an_unverified_id_is_still_refused(self):
        ok, message = self._check({"approval_id": "APPR-SOMEONE-ELSE", "approved": True,
                                   "approved_by": "Founder"})
        self.assertFalse(ok)
        self.assertIn("not verified against the platform record", message)

    def test_a_minted_record_bound_to_this_copy_and_run_is_accepted(self):
        ok, message = self._check({"approval_id": MINTED})
        self.assertTrue(ok, message)

    def test_copy_changed_after_approval_is_refused(self):
        self.assertTrue(self._check({"approval_id": MINTED})[0])  # control
        self.emails.write_text('{"emails": [1]}', encoding="utf-8")
        ok, message = self._check({"approval_id": MINTED})
        self.assertFalse(ok)
        self.assertIn("AF-EMAIL-DEPLOY-UNAPPROVED", message)

    def test_approval_for_another_run_is_refused(self):
        other = Path(self.tmp.name) / "another-run"
        (other / "working" / "deploy").mkdir(parents=True)
        (other / "working" / "copy").mkdir(parents=True)
        (other / "working" / "copy" / "emails.json").write_bytes(self.emails.read_bytes())
        (other / "working" / "deploy" / "approval.json").write_text(
            json.dumps({"approval_id": MINTED}), encoding="utf-8")
        ok, _ = engine._chk_deploy_approval(other)
        self.assertFalse(ok)

    def test_missing_copy_or_missing_verifier_fails_closed(self):
        self.approval.write_text(json.dumps({"approval_id": MINTED}), encoding="utf-8")
        self.emails.unlink()
        self.assertFalse(engine._chk_deploy_approval(self.run_dir)[0])
        self.emails.write_text('{"emails": []}', encoding="utf-8")
        self.assertTrue(engine._chk_deploy_approval(self.run_dir)[0])  # control
        with mock.patch.object(engine, "_APPROVAL_RECORD", Path(self.tmp.name) / "missing.py"):
            ok, message = engine._chk_deploy_approval(self.run_dir)
        self.assertFalse(ok)
        self.assertIn("not installed", message)

    def test_missing_file_still_blocks(self):
        self.approval.unlink(missing_ok=True)
        self.assertFalse(engine._chk_deploy_approval(self.run_dir)[0])

    def test_the_real_shared_verifier_refuses_when_no_command_center_is_configured(self):
        real = SKILL.parent / "shared-utils" / "signature_launch_contract" / "approval_record.py"
        self.assertTrue(real.is_file())
        self.approval.write_text(json.dumps({"approval_id": "APPR-0000-REAL-1"}), encoding="utf-8")
        scrubbed = {k: v for k, v in os.environ.items()
                    if k not in ("MISSION_CONTROL_URL", "MC_API_TOKEN")}
        with mock.patch.object(engine, "_APPROVAL_RECORD", real), \
                mock.patch.dict(os.environ, scrubbed, clear=True):
            ok, message = engine._chk_deploy_approval(self.run_dir)
        self.assertFalse(ok)
        self.assertIn("AF-EMAIL-DEPLOY-UNAPPROVED", message)

    def test_no_bare_flag_branch_is_left_in_the_checker(self):
        source = ENGINE.read_text(encoding="utf-8")
        self.assertNotIn('rec.get("approved") is True', source)
        self.assertIn("approval_record", source)

    def test_the_shipped_golden_example_is_not_a_bare_flag(self):
        golden = SKILL / "examples" / "golden-landing-10" / "working" / "deploy" / "approval.json"
        record = json.loads(golden.read_text(encoding="utf-8"))
        self.assertNotIn("approved", record)
        self.assertNotIn("approved_by", record)
        self.assertTrue(str(record.get("approval_id", "")).strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
