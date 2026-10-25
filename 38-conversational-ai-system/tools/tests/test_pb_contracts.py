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

# Derived from the real identity function, never hand-written: a key format change
# must move this pin with it instead of silently addressing a missing entry.
PUBLIC_KEY = contracts.idempotency_key(
    json.loads((FIXTURES / "outbound" / "public-placement.json").read_text(encoding="utf-8")))

KIND_DIRS = {
    "collection": "collection",
    "outbound": "outbound",
    "approval": "approval",
    "readiness": "readiness",
    "action": "action",
    "lifecycle": "lifecycle",
    "compatibility": "compatibility",
    "reconciliation": "reconciliation",
}


def run(*argv):
    """Run one CLI command in-process; return (exit code, parsed JSON)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = contracts.main([str(arg) for arg in argv])
    return code, json.loads(buffer.getvalue())


def dispatch(ledger, action, gate, manifest=None, now="2026-10-24T10:01:00Z"):
    argv = ["dispatch", "--action", action, "--gate", gate, "--ledger", ledger, "--now", now]
    if manifest:
        argv += ["--manifest", manifest]
    return run(*argv)


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
            ("lifecycle", fixture("lifecycle", "loop-closed.json")),
            ("compatibility", fixture("compatibility", "valid.json")),
            ("reconciliation", fixture("reconciliation", "merge-by-verified-identifier.json")),
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

    def _write(self, name, document):
        path = self.ledger_dir / name
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        return str(path)

    def test_a_new_approved_cycle_is_a_new_placement_not_a_duplicate(self):
        """T-24: the same placement re-approved in the NEXT cycle must still post.

        The retry and the new cycle share tenant and logical_intent_key; only the
        campaign cycle (and the manifest it is approved under) differ. Collapsing
        the second would silently drop a legitimately approved placement.
        """
        self.prime()
        action = json.loads((FIXTURES / "outbound" / "public-placement.json").read_text(encoding="utf-8"))
        next_action = copy.deepcopy(action)
        next_action.update({
            "action_id": "act-public-2",
            "campaign_cycle_id": "cycle-2026-12",
            "approval_manifest_id": "manifest-2026-12",
            "approval_revision": "rev-1",
            "scheduled_at": "2026-12-01T15:00:00Z",
            "not_before": "2026-12-01T15:00:00Z",
        })
        manifest = json.loads((FIXTURES / "approval" / "manifest.json").read_text(encoding="utf-8"))
        next_manifest = copy.deepcopy(manifest)
        next_manifest.update({
            "manifest_id": "manifest-2026-12",
            "campaign_cycle_id": "cycle-2026-12",
            "revision": "rev-1",
        })
        for placement in next_manifest["placements"]:
            placement["scheduled_at"] = "2026-12-01T15:00:00Z"
        gate = json.loads((FIXTURES / "gates" / "public-allow.json").read_text(encoding="utf-8"))
        next_gate = copy.deepcopy(gate)
        next_gate.update({"approval_revision": "rev-1", "checked_at": "2026-10-24T10:00:30Z"})

        self.assertNotEqual(
            contracts.idempotency_key(action), contracts.idempotency_key(next_action),
            "a new cycle must not share the placement identity of the previous one")

        code, payload = run(
            "dispatch",
            "--action", self._write("action-cycle12.json", next_action),
            "--gate", self._write("gate-cycle12.json", next_gate),
            "--manifest", self._write("manifest-cycle12.json", next_manifest),
            "--ledger", self.ledger,
            "--now", "2026-10-24T10:01:00Z",
        )
        self.assertEqual(0, code, payload)
        self.assertEqual("DISPATCHED", payload["decision"],
                         "a newly approved cycle is legitimate, never a duplicate")
        self.assertEqual("act-public-2", payload["action_id"])

        ledger = json.loads(Path(self.ledger).read_text(encoding="utf-8"))
        self.assertEqual(2, len(ledger["actions"]), "both placements are recorded")
        self.assertEqual(
            {"act-public-1", "act-public-2"},
            {entry["action_id"] for entry in ledger["actions"].values()})

    def test_a_version_one_ledger_still_dedupes_a_retry(self):
        """The one migration: an entry written before placement identity.

        A version 1 entry never recorded its placement, so its key cannot be
        recomputed. It must still be found on a retry — losing it would send a
        queued post twice.
        """
        first = self.prime()
        ledger = json.loads(Path(self.ledger).read_text(encoding="utf-8"))
        legacy_key = "tenant-alpha::cycle-2026-11/P-1/SCHEDULED_POST"
        self.assertIn(legacy_key.split("::", 1)[1], first["idempotency_key"])
        legacy_entry = list(ledger["actions"].values())[0]
        Path(self.ledger).write_text(
            json.dumps({"version": 1, "actions": {legacy_key: legacy_entry}}, indent=2),
            encoding="utf-8")

        code, payload = run(
            "dispatch",
            "--action", fixture("outbound", "public-placement.json"),
            "--gate", fixture("gates", "public-allow.json"),
            "--manifest", fixture("approval", "manifest.json"),
            "--ledger", self.ledger,
            "--now", "2026-10-24T10:01:30Z",
        )
        self.assertEqual(0, code, payload)
        self.assertEqual("COLLAPSED", payload["decision"],
                         "a pre-identity entry must still collapse a retry")
        self.assertEqual(1, payload["attempts"])
        self.assertEqual(legacy_key, payload["idempotency_key"],
                         "the retry reports the entry it actually collapsed into")

        code, payload = run(
            "receipt", "--ledger", self.ledger, "--key", legacy_key,
            "--status", "failed_not_sent", "--evidence-id", "ev-legacy",
            "--now", "2026-10-24T10:02:00Z",
        )
        self.assertEqual(0, code, payload)
        migrated = json.loads(Path(self.ledger).read_text(encoding="utf-8"))
        self.assertEqual(2, migrated["version"])
        self.assertEqual({}, migrated["actions"])
        self.assertIn(legacy_key, migrated["legacy_actions"])

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


class LifecycleTests(unittest.TestCase):
    """DATA-CONTRACTS section 9: the loop ladder, one controller, one event revision."""

    def test_closed_verified_alias_is_rejected(self):
        code, payload = run("validate", "--kind", "lifecycle",
                            "--file", fixture("lifecycle", "loop-closed-verified.json"))
        self.assertEqual(1, code)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("CLOSED_VERIFIED" in err for err in payload["errors"]), payload["errors"])

    def test_claiming_closed_early_is_rejected(self):
        code, payload = run("validate", "--kind", "lifecycle",
                            "--file", fixture("lifecycle", "loop-closed-early.json"))
        self.assertEqual(1, code)
        self.assertTrue(any("closed_event_revision" in err for err in payload["errors"]), payload["errors"])

    def test_lifecycle_transition_table(self):
        cases = [
            ("adopting may start running", "loop-adopting.json", "loop-running.json", True),
            ("closing closes on the finalizer", "loop-closing.json", "loop-closed.json", True),
            ("running cannot skip closing", "loop-running.json", "loop-closed.json", False),
            ("a crashed controller is never recreated", "loop-closing.json", "loop-closed-recreated.json", False),
        ]
        for label, before, after, expected in cases:
            with self.subTest(label):
                code, payload = run(
                    "transition", "--kind", "lifecycle",
                    "--before", fixture("lifecycle", before), "--after", fixture("lifecycle", after),
                )
                self.assertEqual(expected, payload["ok"], "%s: %s" % (label, payload.get("errors")))
                self.assertEqual(0 if expected else 1, code)
                if not expected:
                    self.assertTrue(payload["errors"], "%s failed without a reason" % label)

    # The edge table IS the rule, and every behavioural case above reads it, so a
    # widened table would rewrite its own expectations and still pass. Pin it in
    # full: any widening, narrowing or deletion must fail here instead.
    EXPECTED_EDGES = {
        "NOT_INSTALLED": frozenset({"ADOPTING"}),
        "ADOPTING": frozenset({"RUNNING", "CANCELED"}),
        "RUNNING": frozenset({"PAUSED_RESUMABLE", "CLOSING", "CANCELED"}),
        "PAUSED_RESUMABLE": frozenset({"RUNNING", "CLOSING", "CANCELED"}),
        "CLOSING": frozenset({"CLOSED", "CANCELED"}),
        "CLOSED": frozenset(),
        "CANCELED": frozenset(),
    }

    def test_the_lifecycle_edge_table_is_pinned(self):
        actual = {
            state: frozenset(next_states) for state, next_states in contracts.LIFECYCLE_EDGES.items()
        }
        self.assertEqual(self.EXPECTED_EDGES, actual)

    def test_a_closed_loop_cannot_reopen(self):
        # CLOSED is terminal. The fixture set had no transition out of a terminal
        # state, so widening that row was invisible to the suite.
        base = json.loads(Path(fixture("lifecycle", "loop-closed.json")).read_text(encoding="utf-8"))
        targets = ["NOT_INSTALLED", "ADOPTING", "RUNNING", "PAUSED_RESUMABLE", "CLOSING"]
        with tempfile.TemporaryDirectory(prefix="pb-contracts-") as tmp:
            for index, state in enumerate(targets):
                with self.subTest(state):
                    after = copy.deepcopy(base)
                    after["state"] = state
                    after["applied_event_revision"] = base["applied_event_revision"] + 1
                    after["closed_event_revision"] = None
                    after["stop_action_id"] = base["stop_action_id"] if state == "CLOSING" else None
                    after["finalizer_evidence_id"] = None
                    path = Path(tmp) / ("reopen-%d.json" % index)
                    path.write_text(json.dumps(after), encoding="utf-8")
                    code, payload = run(
                        "transition", "--kind", "lifecycle",
                        "--before", fixture("lifecycle", "loop-closed.json"), "--after", str(path),
                    )
                    self.assertEqual(1, code, payload)
                    self.assertFalse(payload["ok"], "CLOSED reopened to %s" % state)
                    self.assertTrue(
                        any("unsupported transition 'CLOSED' -> %r" % state in e for e in payload["errors"]),
                        payload["errors"],
                    )


class CompatibilityTests(unittest.TestCase):
    """DATA-CONTRACTS section 10: rollback compares the revision the upgrade wrote."""

    def test_valid_record_is_accepted(self):
        code, payload = run("validate", "--kind", "compatibility",
                            "--file", fixture("compatibility", "valid.json"))
        self.assertEqual(0, code, payload)
        self.assertTrue(payload["ok"])

    def test_rollback_to_a_newer_client_revision_is_rejected(self):
        code, payload = run("validate", "--kind", "compatibility",
                            "--file", fixture("compatibility", "rollback-to-newer.json"))
        self.assertEqual(1, code)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("forward repair" in err for err in payload["errors"]), payload["errors"])

    def test_writer_generation_is_required(self):
        code, payload = run("validate", "--kind", "compatibility",
                            "--file", fixture("compatibility", "no-writer-generation.json"))
        self.assertEqual(1, code)
        self.assertTrue(any("writer_generation" in err for err in payload["errors"]), payload["errors"])


class ReconciliationTests(unittest.TestCase):
    """DATA-CONTRACTS section 1: verified identifiers, never by name, never across tenants."""

    def test_verified_identifier_merge_is_accepted(self):
        code, payload = run("validate", "--kind", "reconciliation",
                            "--file", fixture("reconciliation", "merge-by-verified-identifier.json"))
        self.assertEqual(0, code, payload)
        self.assertTrue(payload["ok"])

    def test_merge_rules(self):
        cases = [
            ("merge-by-display-name.json", "never merge by display name"),
            ("merge-across-tenants.json", "never merge across tenants"),
            ("identifier-from-other-tenant.json", "not this tenant's"),
        ]
        for name, needle in cases:
            with self.subTest(name):
                code, payload = run("validate", "--kind", "reconciliation",
                                    "--file", fixture("reconciliation", name))
                self.assertEqual(1, code)
                self.assertFalse(payload["ok"])
                self.assertTrue(any(needle in err for err in payload["errors"]), payload["errors"])


class PlacementDivergenceTests(Fixture):
    """DATA-CONTRACTS section 3: the approved manifest is the authority."""

    MUTATIONS = [
        ("channel", "manifest-mut-channel.json"),
        ("scheduled_at", "manifest-mut-scheduled-at.json"),
        ("timezone", "manifest-mut-timezone.json"),
        ("cta_text", "manifest-mut-cta-text.json"),
        ("keyword", "manifest-mut-keyword.json"),
        ("promised_item_version", "manifest-mut-promised-item-version.json"),
        ("bonus_asset_versions", "manifest-mut-bonus-asset-versions.json"),
        ("conversation_policy_version", "manifest-mut-conversation-policy-version.json"),
        ("allowed_spare_ids", "manifest-mut-allowed-spare-ids.json"),
    ]

    def test_each_mutated_field_blocks_dispatch_and_names_itself(self):
        for index, (field, name) in enumerate(self.MUTATIONS):
            with self.subTest(field):
                mutated = fixture("approval", name)
                # The probe document is a well-formed manifest: the block below is
                # the divergence check, not a blanket schema failure.
                code, payload = run("validate", "--kind", "approval", "--file", mutated)
                self.assertEqual(0, code, payload)
                self.assertTrue(payload["ok"], "%s is not a valid manifest: %s" % (name, payload["errors"]))

                # Known-good control: the pristine pair still dispatches.
                code, control = dispatch(str(self.ledger_dir / ("ctl-%d.json" % index)),
                                         fixture("outbound", "public-placement.json"),
                                         fixture("gates", "public-allow.json"),
                                         fixture("approval", "manifest.json"))
                self.assertEqual(0, code, control)
                self.assertEqual("DISPATCHED", control["decision"], control)

                code, payload = dispatch(str(self.ledger_dir / ("mut-%d.json" % index)),
                                         fixture("outbound", "public-placement.json"),
                                         fixture("gates", "public-allow.json"), mutated)
                self.assertEqual(1, code, payload)
                self.assertEqual("STALE_APPROVAL", payload["decision"])
                self.assertIn(field, payload["reason"])
                self.assertTrue(
                    any(err.startswith("$.%s:" % field) for err in payload["errors"]), payload["errors"]
                )


class CrossTenantContactTests(Fixture):
    """DATA-CONTRACTS section 1: one contact is reconciled inside one tenant."""

    def test_same_contact_under_two_tenants_cannot_both_dispatch(self):
        code, first = dispatch(str(self.ledger_dir / "one.json"), fixture("outbound", "person-gift.json"),
                               fixture("gates", "person-allow.json"))
        self.assertEqual(0, code, first)
        self.assertEqual("DISPATCHED", first["decision"], first)

        code, second = dispatch(str(self.ledger_dir / "one.json"),
                                fixture("outbound", "person-gift-other-tenant.json"),
                                fixture("gates", "person-allow.json"))
        self.assertEqual(1, code, second)
        self.assertEqual("QUARANTINED", second["decision"])
        self.assertIn("CONTACT-77", second["reason"])

    def test_control_a_different_contact_still_dispatches(self):
        other = copy.deepcopy(json.loads(Path(fixture("outbound", "person-gift-other-tenant.json")).read_text()))
        other["canonical_contact_id"] = "contact-88"
        path = self.ledger_dir / "other-contact.json"
        path.write_text(json.dumps(other), encoding="utf-8")
        dispatch(str(self.ledger_dir / "two.json"), fixture("outbound", "person-gift.json"),
                 fixture("gates", "person-allow.json"))
        code, payload = dispatch(str(self.ledger_dir / "two.json"), str(path),
                                 fixture("gates", "person-allow.json"))
        self.assertEqual(0, code, payload)
        self.assertEqual("DISPATCHED", payload["decision"], payload)


class CollectionContractTests(unittest.TestCase):
    """DATA-CONTRACTS sections 1 and 8: cardinality, budgets and real timestamps."""

    CASES = [
        ("duplicate reminder slots", "collection", "duplicate-reminder-slots.json", "reminder_slots"),
        ("a non-timestamp", "collection", "non-timestamp.json", "requested_at"),
        ("the origin reference is missing", "collection", "origin-reference-missing.json", "channel_references"),
        ("the capture budget is exceeded", "collection", "capture-budget-exceeded.json", "capture_budget"),
        ("duplicate pending request ids", "collection", "duplicate-pending-ids.json", "pending_request_ids"),
        ("an approved manifest with zero placements", "approval", "manifest-zero-placements.json", "placements"),
    ]

    def test_rejections_name_the_field(self):
        for label, kind, name, field in self.CASES:
            with self.subTest(label):
                code, payload = run("validate", "--kind", kind, "--file", fixture(kind, name))
                self.assertEqual(1, code, payload)
                self.assertFalse(payload["ok"])
                self.assertTrue(any(field in err for err in payload["errors"]), payload["errors"])

    def test_controls_still_validate(self):
        for kind, parts in [("collection", ("collection", "valid.json")), ("approval", ("approval", "manifest.json"))]:
            code, payload = run("validate", "--kind", kind, "--file", fixture(*parts))
            self.assertEqual(0, code, "%s should validate: %s" % (parts, payload.get("errors")))


class GateRecordTests(Fixture):
    """DATA-CONTRACTS section 3: what the gate record must carry and prove."""

    def test_public_control_dispatches(self):
        code, payload = dispatch(str(self.ledger_dir / "pub.json"), fixture("outbound", "public-placement.json"),
                                 fixture("gates", "public-allow.json"), fixture("approval", "manifest.json"))
        self.assertEqual(0, code, payload)
        self.assertEqual("DISPATCHED", payload["decision"], payload)

    def test_public_without_platform_permission_is_refused(self):
        code, payload = dispatch(str(self.ledger_dir / "pub2.json"), fixture("outbound", "public-placement.json"),
                                 fixture("gates", "public-allow-no-publish-permission.json"),
                                 fixture("approval", "manifest.json"))
        self.assertEqual(1, code, payload)
        self.assertEqual("NO_PLATFORM_PUBLISHING_PERMISSION", payload["reason"])

    def test_person_control_dispatches(self):
        code, payload = dispatch(str(self.ledger_dir / "per.json"), fixture("outbound", "person-gift.json"),
                                 fixture("gates", "person-allow.json"))
        self.assertEqual(0, code, payload)
        self.assertEqual("DISPATCHED", payload["decision"], payload)

    def test_a_comment_opener_is_not_an_inbound_dm_window(self):
        code, payload = dispatch(str(self.ledger_dir / "per2.json"), fixture("outbound", "person-comment-opener.json"),
                                 fixture("gates", "person-allow.json"))
        self.assertEqual(1, code, payload)
        self.assertEqual("COMMENT_OPENER_IS_NOT_AN_INBOUND_DM_WINDOW", payload["reason"])

    def test_a_dm_without_an_inbound_window_is_refused(self):
        code, payload = dispatch(str(self.ledger_dir / "per3.json"), fixture("outbound", "person-gift.json"),
                                 fixture("gates", "person-allow-no-window.json"))
        self.assertEqual(1, code, payload)
        self.assertEqual("NO_INBOUND_DM_WINDOW", payload["reason"])

    def test_outbound_does_not_refresh_eligibility(self):
        code, payload = dispatch(str(self.ledger_dir / "per4.json"), fixture("outbound", "person-gift.json"),
                                 fixture("gates", "person-allow-outbound-eligibility.json"))
        self.assertEqual(1, code, payload)
        self.assertEqual("ELIGIBILITY_NOT_REFRESHED_BY_OUTBOUND", payload["reason"])

    def test_no_trusted_contact_mapping_is_a_named_refusal(self):
        # DATA-CONTRACTS 3 lists "trusted contact mapping" as a person-branch check,
        # and closes the gate's return at five decisions carried with supporting
        # evidence. An absent mapping is a refused check, so it must name itself; it
        # is never a malformed document and never an allow.
        code, payload = dispatch(str(self.ledger_dir / "per5.json"), fixture("outbound", "person-gift.json"),
                                 fixture("gates", "person-allow-no-mapping.json"))
        self.assertEqual(1, code, payload)
        self.assertEqual("SUPPRESSED", payload["decision"], payload)
        self.assertEqual("NO_TRUSTED_CONTACT_MAPPING", payload["reason"])
        self.assertEqual([], payload["errors"])

    def _gate_with_mapping(self, value, name):
        gate = copy.deepcopy(json.loads(Path(fixture("gates", "person-allow.json")).read_text(encoding="utf-8")))
        gate["trusted_contact_mapping_evidence_id"] = value
        path = self.ledger_dir / name
        path.write_text(json.dumps(gate), encoding="utf-8")
        return str(path)

    def test_a_blank_trusted_contact_mapping_is_absent(self):
        # The gate schema admits any string here, so whitespace is a document the
        # gate must refuse by name — not malformed, never an allow. A falsy-only
        # presence test dispatched on "   ".
        for index, value in enumerate(["   ", " \t\n", ""]):
            with self.subTest(repr(value)):
                gate = self._gate_with_mapping(value, "blank-mapping-%d.json" % index)
                code, payload = dispatch(str(self.ledger_dir / ("blank-%d.json" % index)),
                                         fixture("outbound", "person-gift.json"), gate)
                self.assertEqual(1, code, payload)
                self.assertEqual("SUPPRESSED", payload["decision"], payload)
                self.assertEqual("NO_TRUSTED_CONTACT_MAPPING", payload["reason"])
                self.assertEqual([], payload["errors"])

    def test_a_real_trusted_contact_mapping_still_dispatches(self):
        # Known-good control on the same instrument: the refusal above is the
        # blank case, not a check that refuses everything.
        for index, value in enumerate(["ev-tcm-1", "  ev-tcm-1  "]):
            with self.subTest(repr(value)):
                gate = self._gate_with_mapping(value, "real-mapping-%d.json" % index)
                code, payload = dispatch(str(self.ledger_dir / ("real-%d.json" % index)),
                                         fixture("outbound", "person-gift.json"), gate)
                self.assertEqual(0, code, payload)
                self.assertEqual("DISPATCHED", payload["decision"], payload)
                self.assertEqual("GATE_ALLOWED", payload["reason"])

    def test_a_non_string_trusted_contact_mapping_is_still_invalid_gate(self):
        # Presence must not swallow a wrong type: only the schema layer may call
        # a document malformed, and it must name the field.
        for index, value in enumerate([123, {}, [], True]):
            with self.subTest(repr(value)):
                gate = self._gate_with_mapping(value, "typed-mapping-%d.json" % index)
                code, payload = dispatch(str(self.ledger_dir / ("typed-%d.json" % index)),
                                         fixture("outbound", "person-gift.json"), gate)
                self.assertEqual(1, code, payload)
                self.assertEqual("INVALID_GATE", payload["decision"], payload)
                self.assertTrue(any("trusted_contact_mapping_evidence_id" in e for e in payload["errors"]),
                                payload["errors"])


    # Characters under test, as code points so nothing invisible lives in this
    # source: U+200B zero width space and U+FEFF byte order mark (category Cf),
    # U+00A0 no-break space and U+3000 ideographic space (category Zs).
    ZWSP = chr(0x200B)
    BOM = chr(0xFEFF)
    NBSP = chr(0x00A0)
    IDEO = chr(0x3000)

    def test_an_invisible_only_trusted_contact_mapping_is_absent(self):
        # The residual the whitespace fix left: str.strip() removes category Zs
        # but not category Cf, so a gate whose mapping id was one zero width
        # space or one byte order mark still dispatched. A value that carries no
        # information is absent no matter how it is spelled.
        blanks = [self.ZWSP, self.BOM, self.ZWSP + self.BOM, self.ZWSP + " " + self.BOM + self.IDEO + "\t "]
        for index, value in enumerate(blanks):
            with self.subTest(repr(value)):
                gate = self._gate_with_mapping(value, "invisible-mapping-%d.json" % index)
                code, payload = dispatch(str(self.ledger_dir / ("invisible-%d.json" % index)),
                                         fixture("outbound", "person-gift.json"), gate)
                self.assertEqual(1, code, payload)
                self.assertEqual("SUPPRESSED", payload["decision"], payload)
                self.assertEqual("NO_TRUSTED_CONTACT_MAPPING", payload["reason"])
                self.assertEqual([], payload["errors"])

    def test_non_breaking_and_ideographic_spaces_are_still_absent(self):
        # Control on the instrument that fixes the case above must not move the
        # case the whitespace fix already closed: category Zs keeps refusing.
        for index, value in enumerate([self.NBSP, self.IDEO, self.NBSP + self.IDEO]):
            with self.subTest(repr(value)):
                gate = self._gate_with_mapping(value, "space-mapping-%d.json" % index)
                code, payload = dispatch(str(self.ledger_dir / ("space-%d.json" % index)),
                                         fixture("outbound", "person-gift.json"), gate)
                self.assertEqual(1, code, payload)
                self.assertEqual("SUPPRESSED", payload["decision"], payload)
                self.assertEqual("NO_TRUSTED_CONTACT_MAPPING", payload["reason"])
                self.assertEqual([], payload["errors"])

    def test_a_real_id_decorated_with_format_marks_still_dispatches(self):
        # Decision recorded: a format mark around a real id is decoration, not a
        # different id. The id is a reference to the mapping evidence, its
        # meaning is the identifier it spells, and an invisible mark carries no
        # information of its own -- so it is trimmed like whitespace padding and
        # the id dispatches. Known-good control beside the refusals above.
        values = ["id" + self.ZWSP, self.BOM + "ev-tcm-1", self.ZWSP + "ev-tcm-1" + self.BOM, " ev-tcm-1 " + self.ZWSP]
        for index, value in enumerate(values):
            with self.subTest(repr(value)):
                gate = self._gate_with_mapping(value, "decorated-mapping-%d.json" % index)
                code, payload = dispatch(str(self.ledger_dir / ("decorated-%d.json" % index)),
                                         fixture("outbound", "person-gift.json"), gate)
                self.assertEqual(0, code, payload)
                self.assertEqual("DISPATCHED", payload["decision"], payload)
                self.assertEqual("GATE_ALLOWED", payload["reason"])

    def test_the_normaliser_trims_format_marks_but_never_rewrites_the_id(self):
        # Unit-level statement of the decision the dispatch cases above read
        # back: blank is absent, decoration is trimmed, the id body is literal.
        self.assertIsNone(contracts.normalise_evidence_id(self.ZWSP))
        self.assertIsNone(contracts.normalise_evidence_id(self.BOM))
        self.assertIsNone(contracts.normalise_evidence_id(self.ZWSP + " " + self.IDEO))
        self.assertEqual("ev-tcm-1", contracts.normalise_evidence_id(self.ZWSP + "ev-tcm-1" + self.BOM))
        self.assertEqual("ev-tcm-1", contracts.normalise_evidence_id("  ev-tcm-1  "))
        self.assertEqual("ev" + self.ZWSP + "-tcm-1", contracts.normalise_evidence_id("ev" + self.ZWSP + "-tcm-1"))


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
