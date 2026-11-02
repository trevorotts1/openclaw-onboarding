#!/usr/bin/env python3
"""Drift test: Skill 50's s49_launch_shape copy vs Skill 49's validator.

Skill 50 keeps its own launch-shape copy (CON-02 decision: no file removed).
This test loads 49's scripts/validate_launch_plan.py by file path and runs
BOTH implementations over identical records, so a change to 49's plan hash or
approval rule fails here instead of silently diverging. It also proves Skill 50
accepts launch schema 1.0, 1.1 and 1.2.

Both sides verify the approval through shared-utils approval_record.verify
(ENF-01); the fixture launch is test_only, so 49 is called with test_only=True
exactly as 50 derives it from the launch. Every malformed case must be refused
by both.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / "tools"))

import launch_intake_adapter as adapter  # noqa: E402
import s49_launch_shape as shape  # noqa: E402

_V49 = ENGINE.parent / "49-signature-funnel" / "scripts" / "validate_launch_plan.py"
_spec = importlib.util.spec_from_file_location("s49_validate_launch_plan", _V49)
v49 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = v49  # dataclass-safe registration before exec
_spec.loader.exec_module(v49)

CLIENT = "client:jordan-marsh"
WORKER = "worker:builder"


def _record(version: str) -> dict:
    launch = copy.deepcopy(adapter.build_fixtures()["launch"])
    launch["schema_version"] = version
    if version in ("1.1", "1.2"):
        launch["prompt_policy_id"] = "policy-fixture"
    if version == "1.2":
        launch["delivery_bindings"] = {
            "momentum-method-core": {"kind": "url", "delivery_url": None}}
    return launch


def _approval(launch: dict, **over) -> dict:
    a = copy.deepcopy(adapter.build_fixtures()["approval"])
    a["plan_hash"] = shape.plan_document_hash(launch)
    a.update(over)
    return a


def _verdict(fn, *args, **kw) -> bool:
    try:
        fn(*args, **kw)
        return True
    except (shape.ShapeError, v49.ApprovalError):
        return False


class DriftTests(unittest.TestCase):
    def test_accepted_versions_cover_49(self):
        self.assertEqual(shape.ACCEPTED_LAUNCH_SCHEMA_VERSIONS,
                         ("1.0", "1.1", "1.2"))
        for ver in shape.ACCEPTED_LAUNCH_SCHEMA_VERSIONS:
            self.assertEqual(v49.validate_launch(_record(ver)), [], ver)

    def test_plan_hash_identical(self):
        for ver in ("1.0", "1.1", "1.2"):
            rec = _record(ver)
            self.assertEqual(shape.plan_document_hash(rec),
                             v49.plan_document_hash(rec), ver)
            flipped = dict(rec, status="building", plan_approval_ref="other")
            self.assertEqual(shape.plan_document_hash(flipped),
                             v49.plan_document_hash(rec), ver)
        a, b = _record("1.2"), _record("1.2")
        b["delivery_bindings"] = {"x": {"kind": "url", "delivery_url": None}}
        self.assertNotEqual(shape.plan_document_hash(a),
                            shape.plan_document_hash(b))
        self.assertEqual(v49.plan_document_hash(a) == v49.plan_document_hash(b),
                         False)

    def test_approval_verdicts_agree(self):
        rec = _record("1.2")
        cases = {
            "valid": {},
            "wrong_type": {"kind": "paid_asset_budget"},
            "narrow_scope": {"scope": ["paid_asset_budget"]},
            "empty_scope": {"scope": []},
            "revoked": {"revoked": True},
            "bad_class": {"verification_class": "bare_flag"},
            "stale_hash": {"plan_hash": "0" * 64},
            "other_owner": {"client_identity": "client:someone-else"},
            "worker_owner": {"client_identity": WORKER},
            "no_message_ref": {"source_message_ref": " "},
            "bad_schema": {"schema_version": "2.0"},
            "expired": {"expires_at": "2000-01-01T00:00:00+00:00"},
            "bad_time": {"expires_at": "not-a-time"},
        }
        for name, over in cases.items():
            ap = _approval(rec, **over)
            client = ap["client_identity"] if name == "worker_owner" \
                else CLIENT
            mine = _verdict(shape.check_plan_build_approval, rec, ap,
                            client_identity_ref=client,
                            worker_identity_ref=WORKER)
            theirs = _verdict(v49.assert_plan_build_approved, rec, ap,
                              client_identity_ref=client,
                              worker_identity_ref=WORKER,
                              test_only=rec.get("test_only") is True)
            self.assertEqual(mine, theirs, name)
            self.assertEqual(mine, name == "valid", name)
        mine = _verdict(shape.check_plan_build_approval, rec, "nope",
                        client_identity_ref=CLIENT)
        self.assertFalse(mine)

    def test_plan_changed_after_approval_refused_by_both(self):
        rec = _record("1.2")
        ap = _approval(rec)
        rec["bump_enabled"] = True
        for fn, kw in ((shape.check_plan_build_approval, {}),
                       (v49.assert_plan_build_approved,
                        {"test_only": rec.get("test_only") is True})):
            self.assertFalse(_verdict(fn, rec, ap, client_identity_ref=CLIENT,
                                      worker_identity_ref=WORKER, **kw))


class AdapterSchemaTests(unittest.TestCase):
    def _adapt(self, version: str):
        fx = adapter.build_fixtures()
        launch = _record(version)
        fx["session"]["plan_hash"] = shape.plan_document_hash(launch)
        fx["approval"]["plan_hash"] = shape.plan_document_hash(launch)
        return adapter.adapt(fx["session"], launch, fx["approval"],
                             fx["brand_facts"], fx["landing_facts"],
                             worker_identity_ref=fx["worker_identity_ref"])

    def test_adapter_accepts_every_launch_schema(self):
        for ver in ("1.0", "1.1", "1.2"):
            brief = self._adapt(ver)
            self.assertEqual(brief["intake_mode"], "signature_launch", ver)

    def test_adapter_still_refuses_unknown_schema(self):
        with self.assertRaises(adapter.Refusal) as cm:
            self._adapt("9.9")
        self.assertIn("schema_version", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
