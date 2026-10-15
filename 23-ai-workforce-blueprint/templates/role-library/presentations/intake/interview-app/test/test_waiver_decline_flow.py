#!/usr/bin/env python3
"""FIX-PLAN Item 12 -- the U026 waiver path, proven end to end on the
HOSTED flow.

The defect this pins: the hosted interview path could never produce the
verbatim declined reason the builders' gates require. The minted payload
never asked the two declined-reason questions, and intake_writer's
flat-answers routing filed the answers (when they somehow arrived) into
deck_brief, a section neither builder gate reads. A client who legitimately
answered "no" was indistinguishable from an unasked run, and the gate
failed closed (AF-UPSELL-WAIVER-MISSING) on a real decline.

The flow proven here, exactly as production runs it:
  payload builder mints the session questions (both reasons asked,
  conditional on a "no", storeOn the canonical nested path)
  -> the client's flat answers reach intake_writer.assemble_intake()
  -> the record carries both reasons VERBATIM under
     pre_presentation_capture.* (never in deck_brief)
  -> write_intake_file() persists the record
  -> sales_checkout_builder.resolve_sales_checkout_gate() and
     vsl_builder.resolve_vsl_gate() both resolve WAIVED with the client's
     own words as the quote.

Negatives pinned with the same weight: a hosted "no" with no reason (or a
blank one) still fails closed with AF-UPSELL-WAIVER-MISSING, exactly as the
chat path's flat shape does; absent toggles still DEFER (silence is never
consent); "yes" still builds. Legacy records whose reasons were misfiled
in deck_brief or flat at top level migrate to the canonical path, and a
contradictory second reason refuses migration rather than being chosen
over the client's recorded words.

Run: python3 test/test_waiver_decline_flow.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
PRESENTATIONS = APP.parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "bridge"))
sys.path.insert(0, str(APP / "payload"))
sys.path.insert(0, str(PRESENTATIONS / "scripts"))

import build_questions_payload as bqp  # noqa: E402
import intake_writer as iw  # noqa: E402
import sales_checkout_builder as scb  # noqa: E402
import vsl_builder as vb  # noqa: E402

# The client's own words, with the casing and punctuation a real client
# types. The waiver is only real if these survive the whole path
# byte-for-byte.
SALES_REASON = "We ALREADY have a checkout page (built in 2024) -- do NOT build another one."
VSL_REASON = "No video exists yet, and we are NOT filming one this quarter."


def _hosted_answers(**overrides) -> dict:
    """A complete set of flat answers as the hosted flow delivers them:
    both upsells declined, each with its verbatim reason."""
    answers = {
        "presentation_type": "from_scratch",
        "offer_name": "The Momentum Method",
        "named_methodology": "The Three-Move Pipeline",
        "transformation_promise": "stuck -> closing",
        "time_to_result": "8 weeks",
        "audience": "women entrepreneurs, 35-55",
        "cta_action": "book a call",
        "tone": "Inspirational",
        "final_price": "$497",
        "speech_speed_preference": "default",
        "want_sales_checkout": "no",
        "sales_checkout_declined_reason": SALES_REASON,
        "want_vsl_page": "no",
        "vsl_page_declined_reason": VSL_REASON,
        "want_email_sequences": "no",
        "client_notes": "",
    }
    answers.update(overrides)
    return answers


# ===========================================================================
# The minted payload actually asks both questions now
# ===========================================================================

class TestHostedPayloadAsksTheWaiverQuestions(unittest.TestCase):
    def test_both_reasons_minted_conditionally_with_canonical_storeon(self):
        root = bqp._project_root(HERE)
        specs, _, store_target = bqp.load_specs(root)
        if not specs.get("questions"):
            self.skipTest("canonical question JSONs not found")
        payload = bqp.build_curated_payload("RUNW12", specs, bqp.DEFAULT_CURATED,
                                            store_target)
        by_id = {q["id"]: q for q in payload["questions"]}
        for rid, toggle, field in (
                ("sales_checkout_declined_reason", "want_sales_checkout",
                 "SALES_CHECKOUT_DECLINED_REASON"),
                ("vsl_page_declined_reason", "want_vsl_page",
                 "VSL_PAGE_DECLINED_REASON")):
            self.assertIn(rid, by_id)
            q = by_id[rid]
            self.assertEqual(q["conditional_on"], {"id": toggle, "equals": "no"})
            self.assertEqual(q["storeOn"], f"pre_presentation_capture.{field}")
            self.assertTrue(q["required"])
            self.assertTrue(q["prompt"])


# ===========================================================================
# The full hosted decline flow: answers -> record -> written file -> gates
# ===========================================================================

class TestHostedDeclineFlowEndToEnd(unittest.TestCase):
    def test_reasons_land_nested_verbatim_and_both_gates_waive(self):
        intake = iw.assemble_intake({"answers": _hosted_answers()}, run_id="W12")
        iw.migrate_intake(intake)
        pre = intake["pre_presentation_capture"]
        # The reasons are at their canonical home, byte-for-byte the
        # client's own words, and NOT in deck_brief (where the pre-fix
        # routing stranded them, invisible to both gates).
        self.assertEqual(pre["SALES_CHECKOUT_DECLINED_REASON"], SALES_REASON)
        self.assertEqual(pre["VSL_PAGE_DECLINED_REASON"], VSL_REASON)
        self.assertNotIn("SALES_CHECKOUT_DECLINED_REASON", intake["deck_brief"])
        self.assertNotIn("VSL_PAGE_DECLINED_REASON", intake["deck_brief"])
        self.assertEqual(iw.validate_intake_completeness(intake), [])

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "W12"
            ipath = iw.write_intake_file(run_dir, intake)
            lpath = iw.write_ledger(run_dir, intake)
            written = json.loads(ipath.read_text(encoding="utf-8"))
            ledger = json.loads(lpath.read_text(encoding="utf-8"))

        # The ledger carries the reasons too (the engine resolver's third
        # read location), under their question ids.
        self.assertEqual(
            ledger["entries"]["sales_checkout_declined_reason"]["value"],
            SALES_REASON)
        self.assertEqual(
            ledger["entries"]["vsl_page_declined_reason"]["value"], VSL_REASON)

        # Both page gates resolve WAIVED off the written record, quoting
        # the client's verbatim words. Not fail-closed, not deferred: an
        # elected "no" now legitimately closes.
        g_sales = scb.resolve_sales_checkout_gate(written)
        self.assertEqual(g_sales["decision"], "waived")
        self.assertEqual(g_sales["quote"], SALES_REASON)
        g_vsl = vb.resolve_vsl_gate(written)
        self.assertEqual(g_vsl["decision"], "waived")
        self.assertEqual(g_vsl["quote"], VSL_REASON)

    def test_yes_answers_still_build(self):
        answers = _hosted_answers(want_sales_checkout="yes", want_vsl_page="yes")
        del answers["sales_checkout_declined_reason"]
        del answers["vsl_page_declined_reason"]
        intake = iw.assemble_intake({"answers": answers}, run_id="W12Y")
        self.assertEqual(
            scb.resolve_sales_checkout_gate(intake)["decision"], "build")
        self.assertEqual(vb.resolve_vsl_gate(intake)["decision"], "build")


# ===========================================================================
# Negatives: the fail-closed and defer semantics are unchanged
# ===========================================================================

class TestDeclineWithoutReasonStillFailsClosed(unittest.TestCase):
    def test_hosted_no_with_no_reason_fails_closed(self):
        answers = _hosted_answers()
        del answers["sales_checkout_declined_reason"]
        del answers["vsl_page_declined_reason"]
        intake = iw.assemble_intake({"answers": answers}, run_id="W12N")
        g_sales = scb.resolve_sales_checkout_gate(intake)
        self.assertEqual(g_sales["decision"], "fail_closed")
        self.assertIn(scb.AF_WAIVER_MISSING, g_sales["detail"])
        g_vsl = vb.resolve_vsl_gate(intake)
        self.assertEqual(g_vsl["decision"], "fail_closed")
        self.assertIn(vb.AF_WAIVER_MISSING, g_vsl["detail"])

    def test_hosted_no_with_blank_reason_fails_closed(self):
        # A blank answer stays blank end to end: it is written as given
        # (never filled in by anyone) and the gates fail closed on it.
        answers = _hosted_answers(sales_checkout_declined_reason="   ",
                                   vsl_page_declined_reason="")
        intake = iw.assemble_intake({"answers": answers}, run_id="W12B")
        self.assertEqual(
            scb.resolve_sales_checkout_gate(intake)["decision"], "fail_closed")
        self.assertEqual(
            vb.resolve_vsl_gate(intake)["decision"], "fail_closed")

    def test_chat_path_flat_shape_fails_closed_identically(self):
        # The sanctioned chat path's flat shape, same "no", same missing
        # reason: the same fail-closed outcome and the same AF code. The
        # hosted repair did not move or soften the gate.
        g_sales = scb.resolve_sales_checkout_gate({"WANT_SALES_CHECKOUT": "no"})
        self.assertEqual(g_sales["decision"], "fail_closed")
        self.assertIn(scb.AF_WAIVER_MISSING, g_sales["detail"])
        g_vsl = vb.resolve_vsl_gate({"WANT_VSL_PAGE": "no"})
        self.assertEqual(g_vsl["decision"], "fail_closed")
        self.assertIn(vb.AF_WAIVER_MISSING, g_vsl["detail"])

    def test_absent_toggles_still_defer(self):
        # Silence is never consent: nothing asked, nothing inferred.
        self.assertEqual(
            scb.resolve_sales_checkout_gate({"pre_presentation_capture": {}})["decision"],
            "defer")
        self.assertEqual(
            vb.resolve_vsl_gate({"pre_presentation_capture": {}})["decision"],
            "defer")
        self.assertEqual(scb.resolve_sales_checkout_gate({})["decision"], "defer")
        self.assertEqual(vb.resolve_vsl_gate({})["decision"], "defer")


# ===========================================================================
# Legacy records: misfiled reasons migrate home; contradictions refuse
# ===========================================================================

class TestLegacyReasonMigration(unittest.TestCase):
    def test_deck_brief_reasons_migrate_to_canonical_and_waive(self):
        # Where the pre-fix writer's flat-answers fallback stranded them.
        record = {
            "deck_brief": {
                "SALES_CHECKOUT_DECLINED_REASON": SALES_REASON,
                "VSL_PAGE_DECLINED_REASON": VSL_REASON,
            },
            "pre_presentation_capture": {
                "WANT_SALES_CHECKOUT": "no",
                "WANT_VSL_PAGE": "no",
            },
        }
        iw.migrate_intake(record)
        pre = record["pre_presentation_capture"]
        self.assertEqual(pre["SALES_CHECKOUT_DECLINED_REASON"], SALES_REASON)
        self.assertEqual(pre["VSL_PAGE_DECLINED_REASON"], VSL_REASON)
        self.assertNotIn("SALES_CHECKOUT_DECLINED_REASON", record["deck_brief"])
        self.assertNotIn("VSL_PAGE_DECLINED_REASON", record["deck_brief"])
        self.assertEqual(
            scb.resolve_sales_checkout_gate(record)["decision"], "waived")
        self.assertEqual(vb.resolve_vsl_gate(record)["decision"], "waived")

    def test_flat_reasons_migrate_to_canonical(self):
        # The chat/driver shape, if such a record is re-ingested through
        # the writer: flat top-level reasons adopt the canonical home.
        record = {
            "SALES_CHECKOUT_DECLINED_REASON": SALES_REASON,
            "VSL_PAGE_DECLINED_REASON": VSL_REASON,
            "pre_presentation_capture": {
                "WANT_SALES_CHECKOUT": "no",
                "WANT_VSL_PAGE": "no",
            },
        }
        iw.migrate_intake(record)
        pre = record["pre_presentation_capture"]
        self.assertEqual(pre["SALES_CHECKOUT_DECLINED_REASON"], SALES_REASON)
        self.assertEqual(pre["VSL_PAGE_DECLINED_REASON"], VSL_REASON)
        self.assertNotIn("SALES_CHECKOUT_DECLINED_REASON", record)
        self.assertNotIn("VSL_PAGE_DECLINED_REASON", record)

    def test_contradictory_reasons_refuse_migration(self):
        # Two different verbatim reasons for one decline: migration must
        # refuse rather than pick one of the client's recorded statements.
        record = {
            "deck_brief": {
                "SALES_CHECKOUT_DECLINED_REASON": "a different reason entirely",
            },
            "pre_presentation_capture": {
                "WANT_SALES_CHECKOUT": "no",
                "SALES_CHECKOUT_DECLINED_REASON": SALES_REASON,
            },
        }
        with self.assertRaises(iw.ContractMigrationError):
            iw.migrate_intake(record)


if __name__ == "__main__":
    unittest.main(verbosity=2)
