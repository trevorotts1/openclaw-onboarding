import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from selection_core import build_selection  # noqa: E402
from selection_session import SessionStore  # noqa: E402
from selection_session_store import DurableSessionStore, StorageError  # noqa: E402
from selection_runtime import Runtime  # noqa: E402
from build_selection_plan import SELF_TEST_LAUNCH  # noqa: E402
import copy as _copy


def make_selection():
    return build_selection(
        SELF_TEST_LAUNCH, offer_id="MAIN-B", price_choice_id="MAIN-B-USD",
        selected_at="2026-10-15T20:00:00Z", source_page_id="TEST-SELECTION",
        session_ref="opaque",
    )


class DurableStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name) / "sessions"

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip_matches_memory_semantics(self):
        store = DurableSessionStore(self.base, ttl_seconds=600)
        ref = store.create(make_selection(), now=1000)
        out = store.resume(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
                           launch=SELF_TEST_LAUNCH, now=1100)
        self.assertEqual(out["state"], "resumed")
        self.assertEqual(out["selection"]["offer_id"], "MAIN-B")

    def test_record_survives_new_instance(self):
        ref = DurableSessionStore(self.base).create(make_selection(), now=1000)
        reopened = DurableSessionStore(self.base)
        out = reopened.resume(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
                              launch=SELF_TEST_LAUNCH, now=1001)
        self.assertEqual(out["state"], "resumed")

    def test_tenant_isolation_on_disk(self):
        ref = DurableSessionStore(self.base).create(make_selection(), now=1000)
        store = DurableSessionStore(self.base)
        out = store.resume(ref, tenant_id="OTHER-TENANT", launch_id="TEST-LAUNCH",
                           launch=SELF_TEST_LAUNCH, now=1001)
        self.assertEqual(out["state"], "expired")
        self.assertNotIn("selection", out)
        # one database file per tenant, and no file for the probing tenant
        self.assertTrue((self.base / "TEST-TENANT" / "selection-sessions.sqlite3").exists())
        self.assertFalse((self.base / "OTHER-TENANT").exists())

    def test_expiry_persists(self):
        store = DurableSessionStore(self.base, ttl_seconds=600)
        ref = store.create(make_selection(), now=1000)
        out = DurableSessionStore(self.base, ttl_seconds=600).resume(
            ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
            launch=SELF_TEST_LAUNCH, now=1700)
        self.assertEqual(out["state"], "expired")
        self.assertIn("nothing was chosen for you", out["message"])

    def test_confirm_idempotent_across_instances(self):
        ref = DurableSessionStore(self.base).create(make_selection(), now=1000)
        first = DurableSessionStore(self.base).confirm(
            ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
            launch=SELF_TEST_LAUNCH, now=1001)
        second = DurableSessionStore(self.base).confirm(
            ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
            launch=SELF_TEST_LAUNCH, now=1002)
        self.assertEqual(first["state"], "confirmed")
        self.assertEqual(first["draft_ref"], second["draft_ref"])
        self.assertTrue(second["duplicate"])

    def test_drift_still_requires_reconfirm(self):
        store = DurableSessionStore(self.base)
        ref = store.create(make_selection(), now=1000)
        changed = _copy.deepcopy(SELF_TEST_LAUNCH)
        changed["offers"][1]["prices"][0]["amount_minor"] = 21700
        out = store.resume(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
                           launch=changed, now=1001)
        self.assertEqual(out["state"], "reconfirm_required")
        self.assertEqual(out["previous_amount_minor"], 19700)

    def test_corrupt_tenant_database_fails_closed_to_expired(self):
        store = DurableSessionStore(self.base)
        ref = store.create(make_selection(), now=1000)
        db = self.base / "TEST-TENANT" / "selection-sessions.sqlite3"
        db.write_bytes(b"this is not a sqlite database")
        out = DurableSessionStore(self.base).resume(
            ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
            launch=SELF_TEST_LAUNCH, now=1001)
        self.assertEqual(out["state"], "expired")
        self.assertNotIn("selection", out)

    def test_create_write_failure_is_loud_not_silent(self):
        blocker = Path(self._tmp.name) / "blocker"
        blocker.write_text("a file, not a directory")
        store = DurableSessionStore(blocker / "sessions")
        with self.assertRaises(StorageError):
            store.create(make_selection(), now=1000)

    def test_memory_and_durable_agree_on_states(self):
        mem = SessionStore(ttl_seconds=600)
        dur = DurableSessionStore(self.base, ttl_seconds=600)
        mref = mem.create(make_selection(), now=1000)
        dref = dur.create(make_selection(), now=1000)
        for store, ref in ((mem, mref), (dur, dref)):
            out = store.resume(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
                               launch=SELF_TEST_LAUNCH, now=1100)
            self.assertEqual(out["state"], "resumed")


class RuntimeAdapterTests(unittest.TestCase):
    def test_plan_and_preview_actions(self):
        rt = Runtime()
        out = rt.handle({"action": "plan", "launch": SELF_TEST_LAUNCH})
        self.assertTrue(out["ok"])
        prev = rt.handle({"action": "preview", "plan": out["result"], "state": "default"})
        self.assertTrue(prev["ok"])
        self.assertIn("<fieldset", prev["result"]["html"])

    def test_single_offer_declines_through_adapter(self):
        single = dict(SELF_TEST_LAUNCH, journey_mode="single_simple",
                      offers=SELF_TEST_LAUNCH["offers"][:1])
        out = Runtime().handle({"action": "plan", "launch": single})
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["outcome"], "declined_single_offer")

    def test_violation_maps_to_structured_error(self):
        bad = json.loads(json.dumps(SELF_TEST_LAUNCH))
        bad["offers"][0]["prices"][0]["approval_status"] = "recommended_unapproved"
        out = Runtime().handle({
            "action": "select", "launch": bad, "offer_id": "MAIN-A",
            "price_choice_id": "MAIN-A-USD", "selected_at": "2026-10-15T20:00:00Z",
            "source_page_id": "P", "session_ref": "opaque",
        })
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "S78-UNAPPROVED-PRICE")

    def test_unknown_action_fails_closed(self):
        out = Runtime().handle({"action": "charge_the_card", "launch": SELF_TEST_LAUNCH})
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "S78-RUNTIME-UNKNOWN-ACTION")

    def test_missing_field_is_bad_request_not_traceback(self):
        out = Runtime().handle({"action": "select", "launch": SELF_TEST_LAUNCH})
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "S78-RUNTIME-BAD-REQUEST")

    def test_session_round_trip_with_durable_store(self):
        with tempfile.TemporaryDirectory() as td:
            rt = Runtime(store={"kind": "durable", "base_dir": str(Path(td) / "s")})
            sel = rt.handle({
                "action": "select", "launch": SELF_TEST_LAUNCH, "offer_id": "MAIN-B",
                "price_choice_id": "MAIN-B-USD", "selected_at": "2026-10-15T20:00:00Z",
                "source_page_id": "P", "session_ref": "opaque",
            })
            self.assertTrue(sel["ok"], sel)
            created = rt.handle({"action": "session_create", "selection": sel["result"], "now": 1000})
            ref = created["result"]["session_ref"]
            confirmed = rt.handle({
                "action": "session_confirm", "session_ref": ref, "tenant_id": "TEST-TENANT",
                "launch_id": "TEST-LAUNCH", "launch": SELF_TEST_LAUNCH, "now": 1001,
            })
            self.assertTrue(confirmed["ok"], confirmed)
            self.assertEqual(confirmed["result"]["state"], "confirmed")
            again = rt.handle({
                "action": "session_confirm", "session_ref": ref, "tenant_id": "TEST-TENANT",
                "launch_id": "TEST-LAUNCH", "launch": SELF_TEST_LAUNCH, "now": 1002,
            })
            self.assertEqual(again["result"]["draft_ref"], confirmed["result"]["draft_ref"])
            self.assertTrue(again["result"]["duplicate"])

    def test_cli_storage_failure_exits_3_with_storage_code(self):
        # Review S78-10 defect 1: the contract pins storage failure to the
        # fail-closed exit 3; the envelope code alone is not enough.
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            blocker = Path(td) / "blocker"
            blocker.write_text("a file, not a directory")
            req = Path(td) / "req.json"
            req.write_text(json.dumps(
                {"action": "session_create", "selection": make_selection(), "now": 1000}))
            run = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "selection_runtime.py"),
                 str(req), "--durable-base", str(blocker / "sessions")],
                capture_output=True, text=True)
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            envelope = json.loads(run.stdout)
            self.assertFalse(envelope["ok"])
            self.assertEqual(envelope["error"]["code"], "S78-SESSION-STORAGE")

    def test_request_cannot_redirect_storage(self):
        rt = Runtime()
        out = rt.handle({
            "action": "session_create", "selection": make_selection(), "now": 1000,
            "store": {"kind": "durable", "base_dir": "/tmp/attacker-chosen"},
        })
        self.assertTrue(out["ok"])  # handled by the construction-time memory store
        self.assertFalse(Path("/tmp/attacker-chosen").exists())


if __name__ == "__main__":
    unittest.main()
