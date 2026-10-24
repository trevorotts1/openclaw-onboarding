#!/usr/bin/env python3
"""Self-check for the Purple Billboard shared contract layer.

Proves both directions: every canonical fixture is accepted, every deliberately
broken fixture is rejected, and the rejects are rejected for the stated reason
rather than by a blanket failure. Three controls defend against the classic
false pass:

  * a known-good control validates one document of every kind, so a broken
    schema file cannot present as "everything correctly failed";
  * a vacuity control asserts the engine rejects a schema it must reject;
  * when jsonschema is importable, every fixture is cross-validated against
    Draft 2020-12 so the stdlib subset engine cannot drift silently. When it is
    not importable the check reports a named skip instead of silently passing.

Run: python3 tools/tests/test_pb_contracts.py
     bash scripts/qc-pb-contracts.sh    (same thing, from the skill root)
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import pb_contracts as contracts  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pb-contracts"

PUBLIC_KEY = "tenant-alpha::cycle-2026-11/P-1/SCHEDULED_POST"

KIND_DIRS = {
    "collection": "collection",
    "outbound": "outbound",
    "approval": "approval",
    "readiness": "readiness",
    "action": "action",
}


def run(*argv):
    """Run one CLI command in-process; return (exit code, parsed JSON)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = contracts.main([str(arg) for arg in argv])
    return code, json.loads(buffer.getvalue())


def fixture(*parts):
    return str(FIXTURES.joinpath(*parts))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.ledger_dir = Path(tempfile.mkdtemp(prefix="pb-contracts-"))
        self.ledger = str(self.ledger_dir / "ledger.json")

    def tearDown(self):
        shutil.rmtree(self.ledger_dir, ignore_errors=True)


class ControlTests(unittest.TestCase):
    def test_all_schema_files_present_and_non_empty(self):
        for kind, name in contracts.SCHEMA_FILES.items():
            path = contracts.SCHEMA_DIR / name
            self.assertTrue(path.is_file(), "missing schema for %s: %s" % (kind, path))
            self.assertGreater(path.stat().st_size, 200, "suspiciously small schema: %s" % path)

    def test_known_good_control_accepts_one_of_every_kind(self):
        # If a schema file is broken, this fails. Without it a blanket-failing
        # validator would look like a perfect set of negative results.
        cases = [
            ("collection", fixture("collection", "valid.json")),
            ("outbound", fixture("outbound", "public-placement.json")),
            ("outbound", fixture("outbound", "person-gift.json")),
            ("approval", fixture("approval", "manifest.json")),
            ("readiness", fixture("readiness", "valid.json")),
            ("action", fixture("action", "completed-valid.json")),
        ]
        for kind, path in cases:
            code, payload = run("validate", "--kind", kind, "--file", path)
            self.assertEqual(0, code, "%s should validate: %s" % (path, payload.get("errors")))
            self.assertTrue(payload["ok"])

    def test_vacuity_control_engine_rejects_missing_required(self):
        self.assertTrue(contracts.validate_schema({"type": "object", "required": ["a"]}, {}))
        self.assertEqual([], contracts.validate_schema({"type": "string"}, "x"))


class ValidateTests(unittest.TestCase):
    CASES = [
        ("collection valid", "collection", ("collection", "valid.json"), True),
        ("manifest stale revision is still a valid document", "approval",
         ("approval", "manifest-stale.json"), True),
        ("public placement with a contact id", "outbound",
         ("outbound", "public-placement-with-contact.json"), False),
        ("person envelope with a contact id", "outbound",
         ("outbound", "person-gift.json"), True),
        ("person envelope with no contact id", "outbound",
         ("outbound", "person-missing-contact.json"), False),
        ("reveal with a verified parent", "outbound", ("outbound", "public-reveal.json"), True),
        ("reveal without a verified parent", "outbound",
         ("outbound", "public-reveal-unverified-parent.json"), False),
        ("readiness with per-stage evidence", "readiness", ("readiness", "valid.json"), True),
        ("readiness invalidated key still READY", "readiness",
         ("readiness", "invalidated-key-still-ready.json"), False),
        ("readiness stage evidence out of order", "readiness",
         ("readiness", "chain-out-of-order.json"), False),
        ("action completed with a finalizer receipt", "action",
         ("action", "completed-valid.json"), True),
        ("action stop ACK presented as completion", "action",
         ("action", "stop-ack-is-not-completion.json"), False),
    ]

    def test_validate_table(self):
        for label, kind, parts, expected in self.CASES:
            with self.subTest(label):
                code, payload = run("validate", "--kind", kind, "--file", fixture(*parts))
                self.assertEqual(expected, payload["ok"], "%s: %s" % (label, payload.get("errors")))
                self.assertEqual(0 if expected else 1, code)
                if not expected:
                    self.assertTrue(payload["errors"], "%s failed without a reason" % label)


class TransitionTests(unittest.TestCase):
    CASES = [
        ("collection accepts a new item while open", "collection",
         ("collection", "valid.json"), ("collection", "after-add-item.json"), True),
        ("declined capture cannot accept a new item", "collection",
         ("collection", "declined-before.json"), ("collection", "declined-add-item-after.json"), False),
        ("partial capture records cannot be dropped", "collection",
         ("collection", "valid.json"), ("collection", "drop-item-after.json"), False),
        ("collection identity cannot change", "collection",
         ("collection", "valid.json"), ("collection", "identity-change-after.json"), False),
        ("action advances dispatched to acknowledged", "action",
         ("action", "before-dispatch.json"), ("action", "after-ack.json"), True),
        ("action cannot move backwards", "action",
         ("action", "after-ack.json"), ("action", "after-backward.json"), False),
    ]

    def test_transition_table(self):
        for label, kind, before, after, expected in self.CASES:
            with self.subTest(label):
                code, payload = run(
                    "transition", "--kind", kind, "--before", fixture(*before), "--after", fixture(*after)
                )
                self.assertEqual(expected, payload["ok"], "%s: %s" % (label, payload.get("errors")))
                self.assertEqual(0 if expected else 1, code)


class DispatchTests(Fixture):
    def prime(self, now="2026-10-24T10:01:00Z"):
        code, payload = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", fixture("gates", "public-allow.json"),
            "--manifest", fixture("approval", "manifest.json"),
            "--ledger", self.ledger,
            "--now", now,
        )
        self.assertEqual(0, code, payload)
        self.assertEqual("DISPATCHED", payload["decision"])
        return payload

    def receipt(self, status, now):
        code, payload = run(
            "receipt", "--ledger", self.ledger, "--key", PUBLIC_KEY,
            "--status", status, "--evidence-id", "ev-%s" % status, "--now", now,
        )
        self.assertEqual(0, code, payload)

    def test_duplicate_dispatch_with_same_idempotency_key_collapses(self):
        first = self.prime()
        code, second = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", fixture("gates", "public-allow.json"),
            "--manifest", fixture("approval", "manifest.json"),
            "--ledger", self.ledger,
            "--now", "2026-10-24T10:02:00Z",
        )
        self.assertEqual(0, code, second)
        self.assertEqual("COLLAPSED", second["decision"])
        self.assertEqual("DUPLICATE_LOGICAL_INTENT", second["reason"])
        self.assertEqual(first["action_id"], second["action_id"])
        self.assertEqual(1, second["attempts"], "a duplicate must not add an attempt")

    def test_retry_with_stale_gate_fails(self):
        self.prime()
        self.receipt("failed_not_sent", "2026-10-24T10:02:00Z")
        code, payload = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", fixture("gates", "public-allow-stale.json"),
            "--manifest", fixture("approval", "manifest.json"),
            "--ledger", self.ledger,
            "--now", "2026-10-24T10:03:00Z",
        )
        self.assertEqual(1, code, payload)
        self.assertEqual("STALE_GATE", payload["decision"])
        self.assertEqual("RETRY_GATE_NOT_FRESH", payload["reason"])
        self.assertEqual(1, payload["attempts"])

    def test_retry_with_fresh_gate_dispatches(self):
        self.prime()
        self.receipt("failed_not_sent", "2026-10-24T10:02:00Z")
        code, payload = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", fixture("gates", "public-allow-fresh.json"),
            "--manifest", fixture("approval", "manifest.json"),
            "--ledger", self.ledger,
            "--now", "2026-10-24T10:06:00Z",
        )
        self.assertEqual(0, code, payload)
        self.assertEqual("DISPATCHED", payload["decision"])
        self.assertEqual(2, payload["attempt"], "a retry is the same action, second attempt")
        self.assertEqual("act-public-1#2", payload["attempt_id"])

    def test_unknown_effect_is_not_replayed(self):
        self.prime()
        self.receipt("unknown", "2026-10-24T10:02:00Z")
        code, payload = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", fixture("gates", "public-allow-fresh.json"),
            "--manifest", fixture("approval", "manifest.json"),
            "--ledger", self.ledger,
            "--now", "2026-10-24T10:06:00Z",
        )
        self.assertEqual(1, code, payload)
        self.assertEqual("RECONCILE_UNKNOWN", payload["decision"])
        self.assertEqual(1, payload["attempts"], "an unknown effect must not be replayed")

    def test_expired_gate_is_refused(self):
        code, payload = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", fixture("gates", "public-allow.json"),
            "--manifest", fixture("approval", "manifest.json"),
            "--ledger", self.ledger,
            "--now", "2026-10-24T12:00:00Z",
        )
        self.assertEqual(1, code, payload)
        self.assertEqual("STALE_GATE", payload["decision"])
        self.assertIn("GATE_EXPIRED", payload["reason"])

    def test_stale_approval_revision_fails(self):
        code, payload = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", fixture("gates", "public-allow.json"),
            "--manifest", fixture("approval", "manifest-stale.json"),
            "--ledger", self.ledger,
            "--now", "2026-10-24T10:01:00Z",
        )
        self.assertEqual(1, code, payload)
        self.assertEqual("STALE_APPROVAL", payload["decision"])
        self.assertTrue(any("stale" in err for err in payload["errors"]), payload["errors"])

    def test_changed_binding_quarantines(self):
        code, payload = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", fixture("gates", "public-allow-fresh.json"),
            "--manifest", fixture("approval", "manifest.json"),
            "--ledger", self.ledger,
            "--now", "2026-10-24T10:06:00Z",
        )
        self.assertEqual(0, code, payload)
        # A gate taken under another binding revision must not move queued work.
        other = copy.deepcopy(json.loads(Path(fixture("gates", "public-allow-fresh.json")).read_text()))
        other["binding_revision"] = "binding-8"
        path = self.ledger_dir / "gate-other-binding.json"
        path.write_text(json.dumps(other), encoding="utf-8")
        self.receipt("failed_not_sent", "2026-10-24T10:07:00Z")
        code, payload = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", str(path),
            "--manifest", fixture("approval", "manifest.json"),
            "--ledger", self.ledger,
            "--now", "2026-10-24T10:08:00Z",
        )
        self.assertEqual(1, code, payload)
        self.assertEqual("QUARANTINED", payload["decision"])
        self.assertEqual("BINDING_CHANGED", payload["reason"])


def _iter_document_cases():
    """Yield (label, schema, document) for the jsonschema conformance pass."""
    for kind, directory in KIND_DIRS.items():
        schema = contracts.load_schema(kind)
        for path in sorted((FIXTURES / directory).glob("*.json")):
            yield "%s/%s" % (directory, path.name), schema, json.loads(path.read_text(encoding="utf-8"))
    public_gate_schema = contracts.branch_gate_schema("public_placement")
    person_gate_schema = contracts.branch_gate_schema("person_directed")
    for path in sorted((FIXTURES / "gates").glob("*.json")):
        schema = person_gate_schema if path.name.startswith("person") else public_gate_schema
        yield "gates/%s" % path.name, schema, json.loads(path.read_text(encoding="utf-8"))


class ConformanceTests(unittest.TestCase):
    def test_engine_agrees_with_jsonschema_when_available(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest(
                "jsonschema is not importable on this interpreter; the stdlib engine "
                "ran the fixture table (named skip, not a silent pass)"
            )
        checked = 0
        for label, schema, document in _iter_document_cases():
            ours = contracts.validate_schema(schema, document)
            theirs = list(Draft202012Validator(schema).iter_errors(document))
            self.assertEqual(
                bool(ours),
                bool(theirs),
                "engine disagreement on %s: stdlib=%s jsonschema=%s"
                % (label, ours[:3], [e.message for e in theirs][:3]),
            )
            checked += 1
        self.assertGreater(checked, 25, "conformance pass covered only %d documents" % checked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
