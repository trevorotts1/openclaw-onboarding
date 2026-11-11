"""Issue 31 (WP-17b): `normalizer.py --emit-binding` is the only producer of
runtime-binding.json, and it refuses to write the record unless the real
normalizer + processor + store prove "grant once" and "paid edges only" first.
"""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))
import normalizer  # noqa: E402

SIGLAUNCH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIGLAUNCH / "processor"))
sys.path.insert(0, str(SIGLAUNCH / "store"))
import processor as real_processor  # noqa: E402
import store as real_store  # noqa: E402

KEYS = {"normalizer", "schema_version", "grant_policy", "paid_edges_only",
        "verified_at", "evidence_ref"}


def _tmp():
    d = tempfile.TemporaryDirectory()
    return d, Path(d.name)


class EmitBindingTests(unittest.TestCase):
    def test_record_has_exactly_the_contract_keys_and_values(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        path = normalizer.emit_binding(out, now=datetime(2026, 11, 10, 18, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(path, out / "runtime-binding.json")
        rec = json.loads(path.read_text())
        self.assertEqual(set(rec), KEYS)
        self.assertEqual(rec["normalizer"], "44/tools/siglaunch/normalizer")
        self.assertEqual(rec["schema_version"], "1.2")
        self.assertEqual(rec["grant_policy"], "once")
        self.assertIs(rec["paid_edges_only"], True)
        self.assertEqual(rec["verified_at"], "2026-11-10T18:00:00Z")
        self.assertRegex(rec["evidence_ref"], r"^siglaunch-normalizer-probe:sha256:[0-9a-f]{64}$")

    def test_a_directory_gets_the_default_file_name_and_a_file_path_is_used_as_given(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        target = out / "custom-name.json"
        self.assertEqual(normalizer.emit_binding(target), target)
        self.assertEqual(set(json.loads(target.read_text())), KEYS)
        self.assertEqual(normalizer.emit_binding(out).name, "runtime-binding.json")

    def test_the_cli_flag_writes_the_record_and_exits_zero(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(normalizer.main(["--emit-binding", str(out)]), 0)
        self.assertEqual(printed.getvalue().strip(), str(out / "runtime-binding.json"))
        self.assertEqual(set(json.loads((out / "runtime-binding.json").read_text())), KEYS)

    def test_without_the_flag_the_module_is_still_not_a_production_entry(self):
        self.assertIs(normalizer.PRODUCTION_ENTRY_ENABLED, False)
        self.assertEqual(normalizer.main([]), normalizer.EXIT_NOT_PRODUCTION)
        self.assertEqual(normalizer.main(["--bogus"]), normalizer.EXIT_NOT_PRODUCTION)
        # a missing path is a usage error, never a silent success and never a production run
        self.assertNotIn(normalizer.main(["--emit-binding"]), (0, normalizer.EXIT_NOT_PRODUCTION))
        self.assertIs(normalizer.PRODUCTION_ENTRY_ENABLED, False)

    def test_the_probe_transcript_is_deterministic_and_covers_every_claim(self):
        a, b = normalizer.probe_binding(), normalizer.probe_binding()
        self.assertTrue(a["ok"], a)
        self.assertEqual(a["digest"], b["digest"])
        names = [p["probe"] for p in a["probes"]]
        self.assertEqual(names, ["paid-event-grants", "redelivery-is-duplicate", "replay-grants-nothing-more",
                                 "pending-never-grants", "failed-never-grants",
                                 "requires_customer_action-never-grants", "unknown-never-grants",
                                 "refund-revokes-never-grants"])


class RefusalTests(unittest.TestCase):
    """Break-it pass: each claim, broken in the real code path, refuses the record."""

    def _refused(self, **inject):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        with self.assertRaises(normalizer.BindingRefused) as ctx:
            normalizer.emit_binding(out, **inject)
        self.assertEqual(list(out.iterdir()), [], "a refused emit must write nothing")
        return str(ctx.exception)

    def test_a_processor_that_grants_unpaid_events_is_refused(self):
        class Greedy(real_processor.DurableProcessor):
            def process(self, event, contact_ref=None):
                return super().process(dict(event, payment_status="succeeded"), contact_ref)
        msg = self._refused(processor_module=SimpleNamespace(DurableProcessor=Greedy))
        self.assertIn("pending-never-grants", msg)

    def test_a_processor_that_grants_again_on_replay_is_refused(self):
        class Twice(real_processor.DurableProcessor):
            def process(self, event, contact_ref=None):
                out = super().process(event, contact_ref)
                out["actions_created"] = out.get("actions_created", 0) + 1
                return out
        msg = self._refused(processor_module=SimpleNamespace(DurableProcessor=Twice))
        self.assertIn("replay-grants-nothing-more", msg)

    def test_a_store_that_does_not_dedupe_redelivery_is_refused(self):
        class Forgetful(real_store.Store):
            def record_event_if_unseen(self, tenant_id, provider, event_id, event):
                super().record_event_if_unseen(tenant_id, provider, event_id, event)
                return True
        msg = self._refused(store_module=SimpleNamespace(Store=Forgetful))
        self.assertIn("redelivery-is-duplicate", msg)

    def test_a_refund_that_leaves_the_right_active_is_refused(self):
        class NoRevoke(real_store.Store):
            def revoke_entitlement(self, tenant_id, line_ref, entitlement):
                return None
        msg = self._refused(store_module=SimpleNamespace(Store=NoRevoke))
        self.assertIn("refund-revokes-never-grants", msg)

    def test_a_missing_v12_schema_is_refused_with_no_fallback_to_an_older_version(self):
        original = normalizer._SCHEMA_V12
        normalizer._SCHEMA_V12 = None
        try:
            self.assertIn("v1.2 schema is missing", self._refused())
        finally:
            normalizer._SCHEMA_V12 = original

    def test_a_target_directory_that_does_not_exist_is_refused_not_a_traceback(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        with self.assertRaises(normalizer.BindingRefused):
            normalizer.emit_binding(out / "no-such-dir" / "runtime-binding.json")
        self.assertEqual(normalizer.main(["--emit-binding", str(out / "no-such-dir" / "x.json")]),
                         normalizer.EXIT_BINDING_REFUSED)

    def test_the_cli_exits_nonzero_and_writes_nothing_when_a_probe_fails(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        original = normalizer.probe_binding
        normalizer.probe_binding = lambda **kw: {"ok": False, "probes": [{"probe": "x", "ok": False}], "digest": "0" * 64}
        try:
            self.assertEqual(normalizer.main(["--emit-binding", str(out)]), normalizer.EXIT_BINDING_REFUSED)
        finally:
            normalizer.probe_binding = original
        self.assertEqual(list(out.iterdir()), [])


class VerifyBindingTests(unittest.TestCase):
    """--verify-binding: a record verifies only if this normalizer's probes reproduce it."""

    def _emitted(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        normalizer.emit_binding(out)
        return out, out / "runtime-binding.json"

    def _rewritten(self, **changes):
        out, path = self._emitted()
        rec = json.loads(path.read_text())
        rec.update(changes)
        path.write_text(json.dumps(rec))
        return path

    def test_a_record_the_emitter_wrote_verifies_by_directory_or_by_file(self):
        out, path = self._emitted()
        self.assertEqual(normalizer.verify_binding(out), path)
        self.assertEqual(normalizer.verify_binding(path), path)
        before = path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(normalizer.main(["--verify-binding", str(out)]), 0)
        self.assertEqual(path.read_bytes(), before, "verify is read-only")

    def test_every_value_a_forger_could_flip_is_refused_by_name(self):
        flips = {
            "evidence_ref": "siglaunch-normalizer-probe:sha256:" + "0" * 64,
            "paid_edges_only": 1,   # equal to True in Python, not the same claim
            "grant_policy": "every_time",
            "schema_version": "1.0",
            "normalizer": "44/tools/other",
            "verified_at": "yesterday",
        }
        for key, value in flips.items():
            with self.subTest(key):
                with self.assertRaises(normalizer.BindingRefused) as ctx:
                    normalizer.verify_binding(self._rewritten(**{key: value}))
                self.assertIn(key, str(ctx.exception))

    def test_a_hand_written_record_with_an_invented_digest_is_refused(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        (out / "runtime-binding.json").write_text(json.dumps({
            "normalizer": "44/tools/siglaunch/normalizer", "schema_version": "1.2", "grant_policy": "once",
            "paid_edges_only": True, "verified_at": "2026-11-10T18:00:00Z",
            "evidence_ref": "siglaunch-normalizer-probe:sha256:" + "ab" * 32}))
        with self.assertRaises(normalizer.BindingRefused) as ctx:
            normalizer.verify_binding(out)
        self.assertIn("evidence_ref", str(ctx.exception))

    def test_an_extra_or_missing_key_an_unreadable_file_and_a_non_object_are_refused(self):
        out, path = self._emitted()
        rec = json.loads(path.read_text())
        for label, body in [("extra", dict(rec, note="hi")), ("missing", {k: v for k, v in rec.items() if k != "verified_at"}),
                            ("not an object", [rec]), ("not json", None)]:
            with self.subTest(label):
                path.write_text("{oops" if body is None else json.dumps(body))
                with self.assertRaises(normalizer.BindingRefused):
                    normalizer.verify_binding(path)
        path.unlink()
        with self.assertRaises(normalizer.BindingRefused):
            normalizer.verify_binding(path)

    def test_a_record_does_not_verify_against_a_normalizer_that_now_behaves_differently(self):
        out, path = self._emitted()

        class Greedy(real_processor.DurableProcessor):
            def process(self, event, contact_ref=None):
                return super().process(dict(event, payment_status="succeeded"), contact_ref)
        with self.assertRaises(normalizer.BindingRefused):
            normalizer.verify_binding(path, processor_module=SimpleNamespace(DurableProcessor=Greedy))

    def test_the_cli_exits_seven_for_a_forged_record_and_two_for_a_bad_call(self):
        path = self._rewritten(evidence_ref="siglaunch-normalizer-probe:sha256:" + "0" * 64)
        self.assertEqual(normalizer.main(["--verify-binding", str(path)]), normalizer.EXIT_BINDING_REFUSED)
        self.assertEqual(normalizer.main(["--verify-binding"]), 2)
        self.assertEqual(normalizer.main(["--verify-binding", "a", "b"]), 2)
        self.assertIs(normalizer.PRODUCTION_ENTRY_ENABLED, False)


def _failed(**inject):
    """Names of the probes that fail when the real normalizer runs against the injected modules."""
    result = normalizer.probe_binding(**inject)
    return result, {p["probe"] for p in result["probes"] if not p["ok"]}


def _processor(**changes):
    """A processor whose process() output is edited: changes maps a key to f(out, event) -> value."""
    class Edited(real_processor.DurableProcessor):
        def process(self, event, contact_ref=None):
            out = super().process(event, contact_ref)
            for key, fn in changes.items():
                out[key] = fn(out, event)
            return out
    return SimpleNamespace(DurableProcessor=Edited)


class EveryProbeClauseTests(unittest.TestCase):
    """Break-it pass at clause level: each condition inside each probe is the only thing that
    fails the probe it belongs to, so removing any one clause from the normalizer is caught."""

    def test_the_unbroken_normalizer_passes_every_probe(self):
        result, failed = _failed()
        self.assertTrue(result["ok"], result)
        self.assertEqual(failed, set())

    def test_a_probe_that_crashes_is_a_failed_probe_not_a_pass(self):
        class Crashing(real_processor.DurableProcessor):
            def process(self, event, contact_ref=None):
                raise RuntimeError("boom")
        result, failed = _failed(processor_module=SimpleNamespace(DurableProcessor=Crashing))
        self.assertFalse(result["ok"])
        self.assertIn("paid-event-grants", failed)
        paid = result["probes"][0]
        self.assertIs(paid["ok"], False)
        self.assertEqual(paid["observed"], {"error": "RuntimeError"})
        self._refused_by_emit(SimpleNamespace(DurableProcessor=Crashing))

    def _refused_by_emit(self, processor_module):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        with self.assertRaises(normalizer.BindingRefused):
            normalizer.emit_binding(out, processor_module=processor_module)
        self.assertEqual(list(out.iterdir()), [])

    def test_paid_event_needs_accepted_processed_and_an_active_right(self):
        class SeenBefore(real_store.Store):
            def record_event_if_unseen(self, tenant_id, provider, event_id, event):
                super().record_event_if_unseen(tenant_id, provider, event_id, event)
                return False  # every ingest reads as a duplicate
        class NoRight(real_store.Store):
            def entitlement_state(self, tenant_id, line_ref, entitlement):
                return "revoked" if line_ref == "line-paid" else super().entitlement_state(tenant_id, line_ref, entitlement)
        for label, kwargs in [
            ("accepted", {"store_module": SimpleNamespace(Store=SeenBefore)}),
            ("processed", {"processor_module": _processor(result=lambda out, ev: "ignored"
                                                          if out["result"] == "processed" else out["result"])}),
            ("active", {"store_module": SimpleNamespace(Store=NoRight)}),
        ]:
            with self.subTest(label):
                _, failed = _failed(**kwargs)
                self.assertIn("paid-event-grants", failed)

    def test_replay_needs_no_actions_no_reconciled_rights_and_the_one_active_right(self):
        class NoActive(real_store.Store):
            def active_entitlements(self, tenant_id):
                return []
        class TwoActive(real_store.Store):
            def active_entitlements(self, tenant_id):
                return super().active_entitlements(tenant_id) + ["extra-ent"]
        for label, kwargs in [
            ("actions", {"processor_module": _processor(actions_created=lambda out, ev: 1)}),
            ("reconciled", {"processor_module": _processor(rights_reconciled=lambda out, ev: 1)}),
            ("no active entitlement", {"store_module": SimpleNamespace(Store=NoActive)}),
            ("extra active entitlement", {"store_module": SimpleNamespace(Store=TwoActive)}),
        ]:
            with self.subTest(label):
                _, failed = _failed(**kwargs)
                self.assertIn("replay-grants-nothing-more", failed)

    def test_a_non_paid_status_needs_the_no_grant_result_and_no_book_entry(self):
        class Books(real_store.Store):
            def entitlement_state(self, tenant_id, line_ref, entitlement):
                return "active" if line_ref in ("line-pending", "line-unknown") else super().entitlement_state(tenant_id, line_ref, entitlement)
        _, failed = _failed(processor_module=_processor(
            result=lambda out, ev: "ignored" if out["result"].startswith("no_grant:") else out["result"]))
        self.assertEqual(failed, {"pending-never-grants", "failed-never-grants",
                                  "requires_customer_action-never-grants", "unknown-never-grants"})
        _, failed = _failed(store_module=SimpleNamespace(Store=Books))
        self.assertEqual(failed, {"pending-never-grants", "unknown-never-grants"})

    def test_a_refund_needs_the_refund_result_and_a_revoked_right(self):
        _, failed = _failed(processor_module=_processor(
            result=lambda out, ev: "applied" if out["result"] == "refund_applied" else out["result"]))
        self.assertIn("refund-revokes-never-grants", failed)


class EvidenceDigestTests(unittest.TestCase):
    """evidence_ref is a digest of what the probes observed, not a constant and not a hash of names."""

    def test_the_digest_is_the_hash_of_the_whole_transcript_including_what_was_observed(self):
        result = normalizer.probe_binding()
        transcript = json.dumps(result["probes"], sort_keys=True, separators=(",", ":"))
        self.assertEqual(result["digest"], hashlib.sha256(transcript.encode()).hexdigest())
        self.assertTrue(all(p["observed"] for p in result["probes"]))

    def test_the_digest_changes_when_any_observed_value_changes_even_if_every_probe_still_passes(self):
        base = normalizer.probe_binding()
        class Redelivering(real_store.Store):
            def record_event_if_unseen(self, tenant_id, provider, event_id, event):
                seen = super().record_event_if_unseen(tenant_id, provider, event_id, event)
                return seen and event_id == "ev-paid"  # non-paid events read as duplicates
        changed = normalizer.probe_binding(store_module=SimpleNamespace(Store=Redelivering))
        self.assertTrue(changed["ok"], changed)
        self.assertNotEqual(base["probes"], changed["probes"])
        self.assertNotEqual(base["digest"], changed["digest"])

    def test_every_probe_observation_feeds_the_digest(self):
        base = normalizer.probe_binding()
        for index, probe in enumerate(base["probes"]):
            with self.subTest(probe["probe"]):
                probes = json.loads(json.dumps(base["probes"]))
                probes[index]["observed"]["marker"] = "changed"
                transcript = json.dumps(probes, sort_keys=True, separators=(",", ":"))
                self.assertNotEqual(base["digest"], hashlib.sha256(transcript.encode()).hexdigest())
                self.assertEqual(base["digest"], normalizer.probe_binding()["digest"])

    def test_the_record_carries_the_digest_the_probes_produced(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        rec = json.loads(normalizer.emit_binding(out).read_text())
        self.assertEqual(rec["evidence_ref"], "siglaunch-normalizer-probe:sha256:" + normalizer.probe_binding()["digest"])

    def test_verified_at_is_written_in_utc_whatever_zone_the_clock_carried(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        east = timezone(timedelta(hours=-5))
        path = normalizer.emit_binding(out, now=datetime(2026, 11, 10, 18, 0, 0, tzinfo=east))
        self.assertEqual(json.loads(path.read_text())["verified_at"], "2026-11-10T23:00:00Z")


class ExitCodeTests(unittest.TestCase):
    """The docs say a refused binding exits 7; the number is the contract, so it is asserted literally."""

    def test_the_documented_exit_code_is_the_literal_seven(self):
        self.assertEqual(normalizer.EXIT_BINDING_REFUSED, 7)
        self.assertIn("exits 7", (Path(normalizer.__file__).parent / "RUNTIME-BINDING.md").read_text())

    def test_a_refused_binding_exits_seven_from_main_and_from_the_command_line(self):
        d, out = _tmp()
        self.addCleanup(d.cleanup)
        missing = str(out / "no-such-dir" / "runtime-binding.json")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(normalizer.main(["--emit-binding", missing]), 7)
        for flag in ("--emit-binding", "--verify-binding"):
            with self.subTest(flag):
                done = subprocess.run([sys.executable, "-I", normalizer.__file__, flag, missing],
                                      capture_output=True, text=True, env={"PATH": os.environ.get("PATH", "")})
                self.assertEqual(done.returncode, 7, done.stderr)


if __name__ == "__main__":
    unittest.main()
