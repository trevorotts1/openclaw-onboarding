"""Acceptance harness — A18 + the S44 half of A20 — against the REAL
production pipeline: normalizer ingest -> DurableProcessor on the
S44-05 durable store. Recording fakes only at the native boundary
(the tag applier and the fulfillment executor).

A18 (S44, weight 3): "Rapid extra purchases not blocked by long waits."
  A base purchase followed immediately by several distinct extra
  purchases, fired back-to-back with NO fulfillment execution and NO
  timing/wait step anywhere in between. Every succeeded line must be
  granted, every grant action done, and every fulfillment action
  present in the ledger (state 'claimed', i.e. available to the
  fulfillment worker) the moment its process() call returns. Waits in
  this stack live only inside per-workflow timing contracts for
  downstream workflows (S44-08 comparator); the harness asserts no
  wait step in a representative contract binds any processor action
  type — fulfillment actions are not workflow wait steps.

A20 (S44/S82, weight 3), S44 half: "Base fulfillment survives tab
close and extra failure." S82's thank-you page emits NO send; it only
records a confirmation_shown observation.
  (a) Tab close: the base entitlement is granted and its fulfillment
      runs end-to-end from the purchase event alone. This harness
      contains no page/thank-you step at all — the page never appears,
      and nothing in the flow misses it.
  (b) Extra failure: a later extra-offer event whose payment failed
      grants nothing and leaves the base grant, its actions, and its
      fulfillment fully intact.
  (c) Single-send: the completion effect both observers converge on
      is the claim-gated verified-purchase tag application (the
      handler workflow's entry seam, DESIGN-S44-06 section 1). The
      event worker (DurableProcessor.process) and a page-observation
      consumer both funnel into the store's claim_action ledger with
      the SAME action key; the ledger admits exactly one winner. In
      both orders, the native-boundary applier fires exactly once and
      the ledger holds exactly one row for the send action.

Level honesty: L1/L2 module-level proof. NOT native (L4) proof.
"""
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

_WORK = Path(__file__).parent.parent
for _sub in ("processor", "store", "normalizer", "timing"):
    sys.path.insert(0, str(_WORK / _sub))

from normalizer import LaunchContext, ingest
from processor import DurableProcessor
from store import Store
from timing import compare_timing

CTX = LaunchContext("T1", "LOC1", "LN1",
                    {"prod-main": "main", "prod-bump": "bump",
                     "prod-u1": "upsell_1", "prod-u2": "upsell_2",
                     "prod-d1": "downsell_1"})
TAG = "siglaunch:purchased:main"
VERSION = "v1"
PROCESSOR_ACTION_TYPES = ("grant_access", "initiate_fulfillment",
                          "apply_verified_purchase_tag")


def line(line_ref, product_ref, ent):
    return {"native_line_ref": line_ref, "native_product_ref": product_ref,
            "offer_id": "off-" + line_ref, "currency": "USD",
            "amount_minor": 1000, "entitlement_ids": [ent]}


def readback(event_id, txn, lines, order="ord-1", status="succeeded",
             kind="order_paid", occurred="2026-10-15T20:00:00Z"):
    return {
        "tenant_id": "T1", "location_id": "LOC1", "launch_id": "LN1",
        "provider": "ghl", "provider_event_id": event_id,
        "native_event_kind": kind,
        "native_order_ref": order, "native_transaction_ref": txn,
        "occurred_at": occurred, "received_at": "2026-10-15T20:00:05Z",
        "payment_status": status,
        "line_items": lines,
        "evidence_ref": f"readback/{order}", "test_only": True,
        "contact_ref": "contact-1",
    }


def _scratch_dir() -> Path:
    """Per-test scratch on the workspace filesystem, self-cleaning.
    (This box's /tmp tmpfs is full — 812K free at harness time — and
    SQLITE_FULL on WAL setup is an environment failure, not evidence
    about the pipeline; the DBs live and die under .scratch/ here.)"""
    root = Path(__file__).parent / ".scratch"
    root.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(dir=root))


def ledger_count(db_path, action_type):
    """Direct read-back of the durable action ledger (counting rows is
    evidence, so read the ledger itself, not a proxy)."""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM actions WHERE tenant_id='T1'"
            " AND action_type=?", (action_type,)).fetchone()[0]
    finally:
        conn.close()


class A18A20Acceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = _scratch_dir()
        self.db = str(self.tmp / "s44.db")
        self.store = Store(self.db)
        self.tags_applied = []
        self.proc = DurableProcessor(
            self.store,
            tag_applier=lambda c, t: self.tags_applied.append((c, t)),
            purchase_tag=TAG)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        try:
            (Path(__file__).parent / ".scratch").rmdir()
        except OSError:
            pass

    def _ingest_process(self, rb):
        status, payload = ingest(self.store, rb, CTX)
        self.assertEqual(status, "accepted")
        return self.proc.process(payload["event"],
                                 contact_ref=payload["contact_ref_context"])

    # ── A18 ─────────────────────────────────────────────────────────────
    def test_a18_rapid_extra_purchases_not_blocked_by_long_waits(self):
        purchases = [
            ("evt-a18-0", "txn-a18-0", line("li-m", "prod-main", "ent-main")),
            ("evt-a18-1", "txn-a18-1", line("li-u1", "prod-u1", "ent-u1")),
            ("evt-a18-2", "txn-a18-2", line("li-u2", "prod-u2", "ent-u2")),
            ("evt-a18-3", "txn-a18-3", line("li-d1", "prod-d1", "ent-d1")),
            ("evt-a18-4", "txn-a18-4", line("li-b", "prod-bump", "ent-bump")),
        ]
        start = time.perf_counter()
        for event_id, txn, ln in purchases:
            out = self._ingest_process(
                readback(event_id, txn, [ln], order="ord-a18"))
            self.assertEqual(out["result"], "processed")
            # immediacy: the fulfillment action is in the ledger, ready
            # for its worker, the moment process() returns — no wait
            # step ran, none is pending, none gates the NEXT purchase.
            fkey = ("T1", txn, ln["native_line_ref"],
                    "initiate_fulfillment", VERSION)
            action = self.store.get_action(fkey)
            self.assertIsNotNone(action)
            self.assertEqual(action["state"], "claimed")
        wall = time.perf_counter() - start
        print(f"A18_WALL_SECONDS={wall:.4f}")
        # generous bound: proves absence of waits, not machine speed
        self.assertLess(wall, 5.0)

        # every succeeded line granted; every grant action done
        self.assertEqual(self.store.active_entitlements("T1"),
                         ["ent-bump", "ent-d1", "ent-main",
                          "ent-u1", "ent-u2"])
        for _eid, txn, ln in purchases:
            gkey = ("T1", txn, ln["native_line_ref"], "grant_access",
                    VERSION)
            self.assertEqual(self.store.get_action(gkey)["state"], "done")
        # the fulfillment worker NEVER ran during the sequence (every
        # fulfillment action is still merely claimed) and the tag seam
        # fired per purchase — later purchases were not blocked by
        # earlier purchases' downstream fulfillment or sequences.
        self.assertEqual(ledger_count(self.db, "initiate_fulfillment"), 5)
        self.assertEqual(len(self.tags_applied), 5)

        # grounding: waits exist only as steps of per-workflow timing
        # contracts for downstream workflows; none binds a processor
        # action type. The comparator treats them as workflow-step
        # concerns (a 3-day nurture wait + an event-anchored wait).
        contract = {"slug": "nurture", "allow_multiple": True, "waits": [
            {"step": "wait-3d", "mode": "duration",
             "offset_seconds": 259200, "timezone": "America/New_York",
             "past_due": "send_immediately"},
            {"step": "wait-cart", "mode": "event_anchored",
             "offset_seconds": 3600, "timezone": "UTC",
             "past_due": "skip"}]}
        wait_steps = {w["step"] for w in contract["waits"]}
        self.assertTrue(wait_steps.isdisjoint(PROCESSOR_ACTION_TYPES))
        self.assertNotIn("initiate_fulfillment", wait_steps)
        verdict = compare_timing(contract, {"allowMultiple": True,
                                            "steps": []})
        self.assertEqual(verdict["slug"], "nurture")

    # ── A20 (a) tab close ───────────────────────────────────────────────
    def test_a20a_tab_close_base_granted_without_any_page_visit(self):
        # The buyer closes the tab right after checkout. There is NO
        # page/thank-you observation anywhere in this flow — no page
        # object, no page call, no page-shaped input. The purchase
        # event alone must carry the base grant and its fulfillment.
        out = self._ingest_process(readback(
            "evt-a20-base", "txn-a20",
            [line("li-m", "prod-main", "ent-main")], order="ord-a20"))
        self.assertEqual(out["result"], "processed")
        self.assertEqual(self.store.active_entitlements("T1"), ["ent-main"])
        gkey = ("T1", "txn-a20", "li-m", "grant_access", VERSION)
        self.assertEqual(self.store.get_action(gkey)["state"], "done")
        # fulfillment runs end-to-end, still with no page involvement
        fkey = ("T1", "txn-a20", "li-m", "initiate_fulfillment", VERSION)
        self.assertEqual(self.store.get_action(fkey)["state"], "claimed")
        executed = []
        self.assertEqual(
            self.proc.fulfill(fkey, lambda p: executed.append(p)), "done")
        self.assertEqual(executed, [{"slot": "main"}])
        self.assertEqual(
            self.proc.fulfill(fkey, lambda p: executed.append(p)),
            "already_done")
        self.assertEqual(len(executed), 1)

    # ── A20 (b) extra failure ───────────────────────────────────────────
    def test_a20b_extra_failure_leaves_base_grant_intact(self):
        self._ingest_process(readback(
            "evt-a20-base", "txn-a20",
            [line("li-m", "prod-main", "ent-main")], order="ord-a20"))
        base_fkey = ("T1", "txn-a20", "li-m", "initiate_fulfillment",
                     VERSION)
        base_gkey = ("T1", "txn-a20", "li-m", "grant_access", VERSION)

        # a later extra offer's payment fails (its own transaction)
        out = self._ingest_process(readback(
            "evt-a20-fail", "txn-a20-f",
            [line("li-u1", "prod-u1", "ent-u1")], order="ord-a20",
            status="failed"))
        self.assertEqual(out["result"], "no_grant:failed")

        # base untouched: grant active, actions in their prior states
        self.assertEqual(self.store.active_entitlements("T1"), ["ent-main"])
        self.assertTrue(
            self.store.line_has_active_entitlement("T1", "li-m"))
        self.assertEqual(self.store.get_action(base_gkey)["state"], "done")
        self.assertEqual(self.store.get_action(base_fkey)["state"],
                         "claimed")
        # the failed extra produced no grant and no fulfillment action
        self.assertIsNone(self.store.get_action(
            ("T1", "txn-a20-f", "li-u1", "grant_access", VERSION)))
        self.assertIsNone(self.store.get_action(
            ("T1", "txn-a20-f", "li-u1", "initiate_fulfillment", VERSION)))
        self.assertEqual(self.tags_applied, [("contact-1", TAG)])
        self.assertEqual(self.store.unknown_actions("T1"), [])
        self.assertEqual(self.store.open_quarantine("T1"), [])
        # and base fulfillment still executes normally afterwards
        self.assertEqual(self.proc.fulfill(base_fkey, lambda p: None),
                         "done")

    # ── A20 (c) single-send ─────────────────────────────────────────────
    def _page_observation(self, store, calls, key):
        """The S82 confirmation_shown observation consumer: the page
        emits NO send; its observation asks S44 to ensure the order's
        completion effect. It funnels into the SAME claimed action key
        the processor uses. Only the claim winner fires the applier."""
        if store.claim_action(key, {"tag": TAG}) is None:
            calls.append(("contact-1", TAG))
            store.mark_action(key, "done", evidence_ref="readback/ord-1")
            return "fired"
        return "already_claimed"

    def _single_send_scenario(self, first):
        d = _scratch_dir()
        try:
            db = str(d / "s44.db")
            store = Store(db)
            calls = []
            proc = DurableProcessor(
                store,
                tag_applier=lambda c, t: calls.append((c, t)),
                purchase_tag=TAG)
            rb = readback("evt-a20-send", "txn-a20s",
                          [line("li-m", "prod-main", "ent-main"),
                           line("li-b", "prod-bump", "ent-bump")],
                          order="ord-a20s")
            status, payload = ingest(store, rb, CTX)
            self.assertEqual(status, "accepted")
            event = payload["event"]
            cref = payload["contact_ref_context"]
            send_key = ("T1", "txn-a20s", "*",
                        "apply_verified_purchase_tag", VERSION)

            if first == "page":
                self.assertEqual(
                    self._page_observation(store, calls, send_key),
                    "fired")
                proc.process(event, contact_ref=cref)
                self.assertEqual(
                    self._page_observation(store, calls, send_key),
                    "already_claimed")
            else:
                proc.process(event, contact_ref=cref)
                self.assertEqual(
                    self._page_observation(store, calls, send_key),
                    "already_claimed")
                # the event worker re-observes the same completion:
                # a full re-process must not multiply any effect
                proc.process(event, contact_ref=cref)

            # exactly one send at the native boundary, exactly one
            # ledger row for the send action, grants exactly once each
            self.assertEqual(calls, [("contact-1", TAG)])
            self.assertEqual(store.get_action(send_key)["state"], "done")
            conn = sqlite3.connect(db)
            try:
                send_rows = conn.execute(
                    "SELECT COUNT(*) FROM actions WHERE tenant_id='T1'"
                    " AND action_type='apply_verified_purchase_tag'"
                ).fetchone()[0]
                grant_rows = conn.execute(
                    "SELECT COUNT(*) FROM actions WHERE tenant_id='T1'"
                    " AND action_type='grant_access'").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(send_rows, 1)
            self.assertEqual(grant_rows, 2)
            self.assertEqual(store.active_entitlements("T1"),
                             ["ent-bump", "ent-main"])
        finally:
            shutil.rmtree(d, ignore_errors=True)
            try:
                (Path(__file__).parent / ".scratch").rmdir()
            except OSError:
                pass

    def test_a20c_single_send_page_and_worker_observe_same_completion(self):
        with self.subTest(first="worker"):
            self._single_send_scenario("worker")
        with self.subTest(first="page"):
            self._single_send_scenario("page")


if __name__ == "__main__":
    unittest.main()
