"""Issue 30 / M2: package judges every dispatched piece at the delivery scope that matches its intake.

A test_only intake stays a rehearsal. A non-test intake is a client delivery: the piece must be
locally_verified (L2) and carry a review record whose reviewer is in the dispatch ledger. A live dispatch
cannot run offline (Skill 49's adapter allow-list refuses the free consumer), so the live scope is driven
through ``package._bind_piece`` over a real dispatched run with ``test_only=False``; ``assemble`` itself is
shown passing the intake's scope down for the test_only case.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from test_assemble_binding import (COUNCIL, FIXTURES, DispatchedRun, recorded_binding,  # noqa: E402,F401
                                   setUpModule, tearDownModule)
from test_lane83_designs import make_piece  # noqa: E402
from test_only_readback import TEST_ONLY_CHECKOUT_READBACK, paid_image_plan, patch_paid_budget  # noqa: E402
from launcher_core import intake, package, route  # noqa: E402

ROLE = "checkout"


class DeliveryScopeTests(DispatchedRun):
    def bind(self, run, piece, test_only):
        normalized = intake.validate(self.doc)
        binding = package._bind_dispatch(run, normalized, route.compile_route(normalized), strict=True)
        package._bind_piece(binding, piece, ROLE, ROLE, False, test_only)

    def reviewed(self, run, **review_over):
        """The piece and its stored dispatch result rewritten as a reviewed page, plus the review files."""
        piece = copy.deepcopy(self.pieces(run)[ROLE])
        stored_path = run / "dispatch" / f"result-{ROLE}.json"
        stored = json.loads(stored_path.read_text(encoding="utf-8"))
        for doc in (piece, stored):
            doc.update(status="locally_verified", proof_class="L2", independent_review=True,
                       reviewer_session="TEST-REVIEWER")
        stored_path.write_text(json.dumps(stored), encoding="utf-8")
        review = {"schema": "signature-launch-review-record/v1", "reviewer_session": "TEST-REVIEWER",
                  "reviewer_model": "m", "verdict": "PASS", "request_id": piece["request_id"],
                  "reviewed_artifacts": [{"path": a["path"], "sha256": a["sha256"]} for a in piece["artifacts"]]}
        review.update(review_over)
        (run / "dispatch" / f"review-{ROLE}.json").write_text(json.dumps(review), encoding="utf-8")
        (run / "dispatch" / "dispatch-session-registry.json").write_text(
            json.dumps({"sessions": [{"session_id": "TEST-REVIEWER", "model": "m"}]}), encoding="utf-8")
        return piece

    def test_a_test_only_intake_is_judged_as_a_rehearsal(self):
        spy = mock.Mock(wraps=package._receipts_module().validate_result)
        with mock.patch.object(package._receipts_module(), "validate_result", spy):
            self.assemble(name="rehearsal")
        self.assertTrue(spy.call_args_list)
        self.assertEqual({c.kwargs["scope"] for c in spy.call_args_list}, {"rehearsal"})

    def test_an_unreviewed_piece_is_refused_as_a_client_delivery(self):
        run = self.copy_run()
        self.bind(run, self.pieces(run)[ROLE], test_only=True)  # the same piece is fine as a rehearsal
        with self.assertRaises(package.PackageError) as ctx:
            self.bind(run, self.pieces(run)[ROLE], test_only=False)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-ECHO")
        self.assertIn("client_delivery needs an independent review record", ctx.exception.detail)

    def test_a_reviewed_piece_passes_as_a_client_delivery(self):
        run = self.copy_run()
        self.bind(run, self.reviewed(run), test_only=False)

    def test_a_review_with_a_failed_verdict_is_refused_as_a_client_delivery(self):
        run = self.copy_run()
        piece = self.reviewed(run, verdict="FAIL")
        with self.assertRaises(package.PackageError) as ctx:
            self.bind(run, piece, test_only=False)
        self.assertIn("no recognised successful verdict", ctx.exception.detail)

    def test_an_unparseable_review_or_ledger_is_a_refusal_not_a_crash(self):
        for name in (f"review-{ROLE}.json", "dispatch-session-registry.json"):
            run = self.copy_run(name=f"junk-{name[:6]}")
            piece = self.reviewed(run)
            (run / "dispatch" / name).write_text("{not json", encoding="utf-8")
            with self.assertRaises(package.PackageError) as ctx:
                self.bind(run, piece, test_only=False)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-ECHO", name)

    def bind_slot(self, run, piece, slot):
        normalized = intake.validate(self.doc)
        binding = package._bind_dispatch(run, normalized, route.compile_route(normalized), strict=True)
        package._bind_piece(binding, piece, ROLE, slot, True, False)

    def test_a_slot_page_reads_its_own_review_record_not_its_parents(self):
        run = self.copy_run()
        piece = self.reviewed(run)
        parent = run / "dispatch" / f"review-{ROLE}.json"
        (run / "dispatch" / "review-slotx.json").write_text(parent.read_text(encoding="utf-8"), encoding="utf-8")
        self.bind_slot(run, piece, "slotx")  # its own record is enough
        with self.assertRaises(package.PackageError) as ctx:  # the parent's record does not stand in for another slot
            self.bind_slot(run, piece, "sloty")
        self.assertIn("without a review record", ctx.exception.detail)


class _StopAfterSlotPage(Exception):
    pass


class AssembleCallSiteScopeTests(unittest.TestCase):
    """Issue 30 / M2: ``package.assemble`` hands the intake's own test_only to BOTH ``_bind_piece`` call sites.

    A non-test intake cannot reach those call sites offline (it first needs a verified live receipt store, a
    matching intake snapshot and a complete checkout binding), so the earlier gates are stubbed and
    ``_bind_piece`` is spied on: route-node pages and slot pages must both be bound at test_only False for a
    non-test intake and True for a test intake. A call site fixed to the literal True judges a client delivery
    at rehearsal scope and lets an unreviewed page through.
    """

    def run_assemble(self, test_only):
        """Assemble with the earlier gates stubbed; return every (slot, extra, test_only) the spy saw."""
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            patch_paid_budget(self)
            raw = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
            raw["image_plan"] = {"brand_file": "/tmp/test-brand.json", "brand_owner": "TEST-ONLY Client",
                                 **paid_image_plan(9)}
            raw["test_only"] = test_only
            normalized = intake.validate(raw)
            graph = route.compile_route(normalized)
            pieces = {n["role"]: make_piece(work, normalized, n, provider="kie") for n in graph["nodes"]}
            parent = "landing"
            node = {"role": parent, "role_instance": "sales", "page_id": route.route_law._page_id(normalized["launch_id"], "sales"),
                    "echoed_page_id": next(n["page_id"] for n in graph["nodes"] if n["role"] == parent)}
            pieces["sales"] = make_piece(work, normalized, node, provider="kie")
            for slot, piece in pieces.items():  # issue 57: a client delivery needs each page run's closed stage_gate state
                closed = json.dumps({"stages": {"final-mockups": {"status": "closed"}}}).encode()
                carried = work / "pieces" / f"{slot}.stage-state.json"
                carried.parent.mkdir(exist_ok=True)
                carried.write_bytes(closed)
                piece["stage_state"] = {"path": f"pieces/{slot}.stage-state.json",
                                        "sha256": hashlib.sha256(closed).hexdigest()}
            run = work / "dispatch-run"
            binding = recorded_binding(run, normalized["approval"]["hash"])
            seen = []

            def spy(_binding, _raw, _role, slot, extra, scope_flag):
                seen.append((slot, extra, scope_flag))
                if extra:
                    raise _StopAfterSlotPage()

            evidence = {"state": "verified", "entries": 1}
            module = mock.Mock(verify_delivery_store=mock.Mock(return_value=(True, "ok")))
            with mock.patch.object(package, "_find_dispatch_root", return_value=(run, True)), \
                    mock.patch.object(package, "_bind_dispatch", return_value=binding), \
                    mock.patch.object(package, "receipt_evidence", return_value=evidence), \
                    mock.patch.object(package, "_load_receipt_module", return_value=module), \
                    mock.patch.object(package.checkout_module, "order_form_mapping", return_value={}), \
                    mock.patch.object(package, "_bind_piece", side_effect=spy):
                with self.assertRaises(_StopAfterSlotPage):
                    package.assemble(work / "pkg", normalized, graph, pieces, source_root=work,
                                     council=COUNCIL, require_designs=True,
                                     checkout_readback=TEST_ONLY_CHECKOUT_READBACK,
                                     to_confirm=binding["to_confirm"], landing_pages=binding["landing_pages"])
            return seen

    def test_both_call_sites_follow_the_intake_scope(self):
        for test_only in (False, True):
            with self.subTest(test_only=test_only):
                seen = self.run_assemble(test_only)
                node_calls = [c for c in seen if not c[1]]
                slot_calls = [c for c in seen if c[1]]
                self.assertTrue(node_calls, "no route-node page was bound")
                self.assertEqual([c[0] for c in slot_calls], ["sales"])
                self.assertEqual({c[2] for c in seen}, {test_only})


if __name__ == "__main__":
    unittest.main()
