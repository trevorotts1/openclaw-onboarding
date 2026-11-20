"""Every Skill 78 stop explains itself in plain words (owner order, 2026-11-20).

Offline, no spend. Proves: every stop the client or a buyer can see has a table entry with all four
parts (what happened, why the rule exists, the fix, 2 to 4 choices, one the agent or, for a buyer,
the page doing the work); no rendered message carries a reason code, file path, traceback or raw
exception text; an unknown stop still gets four parts in fixed plain words; placeholders fill with the
real names and numbers; and the stops really reach the client with their explanation (runtime envelope,
session states, a Violation raised by the catalog check, the picture step's printed stop line).

STOP INVENTORY (every place this skill stops, refuses, holds or waits; the table entry for each):
  plan / invocation (selection_core.check_invocation, validate_catalog, build_selection_plan):
    S78-SINGLE-OFFER-DECLINE, S78-JOURNEY-MODE-DECLINE, S78-NO-MAIN-OFFERS,
    S78-OFFER-NO-DELIVERABLES, S78-NO-COMPARISON-ROWS
  prices (selection_core._check_price, validate_catalog, validate_assets):
    S78-UNKNOWN-PRICE, S78-UNAPPROVED-PRICE, S78-INVALID-AMOUNT, S78-DUPLICATE-OFFER-ID,
    S78-INSTALLMENT-TOTAL-MISMATCH, S78-RECURRING-INTERVAL-MISSING, S78-TRIAL-TERMS-MISSING,
    S78-TEST-ONLY-IN-PRODUCTION, S78-MISSING-NATIVE-MAPPING, S78-ASSET-PROVENANCE
  page words (scan_claims, build_recommendation, validate_selection_content):
    S78-UNPROVEN-CLAIM, S78-RECOMMENDATION-UNAPPROVED, S78-COPY-PRICE-MISMATCH,
    S78-HIDDEN-EXCLUSION, S78-AMBIGUOUS-COPY, S78-COMPARE-EMPTY, S78-MANUSCRIPT-SHAPE,
    S78-CTA-PAYMENT-LANGUAGE, S78-PAYMENT-COLLECTION
  the buyer's choice at checkout (build_selection, validate_binding, reject_query_authority):
    S78-SELECTION-UNKNOWN-OFFER, S78-SELECTION-PRICE-DRIFT, S78-SELECTION-TENANT-MISMATCH,
    S78-SELECTION-STALE-REVISION, S78-QUERY-PRICE-AUTHORITY
  checkout links (emit_binding_plan, validate_selection_binding.validate_plan):
    S78-BINDING-INCOMPLETE, S78-BINDING-SHARED-TARGET, S78-BINDING-DUPLICATE-TARGET,
    S78-BINDING-TARGET-DRIFT, S78-BINDING-NOT-ALLOWLISTED
  request handler and saved choices (selection_runtime, selection_session_store, selection_session):
    S78-RUNTIME-BAD-REQUEST, S78-RUNTIME-UNKNOWN-ACTION, S78-SESSION-STORAGE,
    S78-SESSION-EXPIRED (state expired), S78-SESSION-RECONFIRM (state reconfirm_required)
  wireframes and mockups (run_image_stages refusals and Skill 71's board wait, matched by their words):
    S78-IMAGES-INPUTS-NONE, S78-IMAGES-INPUTS-MISSING, S78-IMAGES-PLAN-NOT-BUILT,
    S78-IMAGES-PAID-NOT-ALLOWED, S78-IMAGES-BOARD-APPROVAL-WAIT, S78-IMAGES-BOARD-SPEC-MISSING,
    S78-IMAGES-STEP-FAILED
Not stops: emit_page_result's ValueErrors are operator wiring checks (missing request echo, bad status);
the chain reports them through the image-step entries above, never to the client as raw text.
"""
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402
from explain_stop import FALLBACK, explain_stop, from_output, load_table  # noqa: E402
from selection_core import Violation, validate_catalog  # noqa: E402
from selection_runtime import Runtime  # noqa: E402
from selection_session import SessionStore  # noqa: E402

INVENTORY = set(re.findall(r"S78-[A-Z0-9-]+[A-Z0-9]", __doc__))
TABLE = load_table()
ENTRIES = TABLE["entries"]
LEAKS = [re.compile(r"\bS\d{2}-[A-Z]"), re.compile(r"\bAF-[A-Z]"), re.compile(r"Traceback|File \""),
         re.compile(r"\w+\.(py|json|sh|md)\b"), re.compile(r"(^|\s)/\w+/")]
# A choice where the agent does the work starts "I " (the agent speaking to the client); to a buyer it is the
# page doing the work, "We " (the business speaking). Every entry has one.
AGENT_CHOICE = re.compile(r"^I ")
DONE_FOR_BUYER = re.compile(r"^We ")

def leaks(text):
    return [p.pattern for p in LEAKS if p.search(text)]

def codes_in_scripts():
    found = set()
    for path in (SKILL / "scripts").glob("*.py"):
        found |= set(re.findall(r"[\"'](S78-[A-Z0-9-]+[A-Z0-9])[\"']", path.read_text(encoding="utf-8")))
    return found

class TableTests(unittest.TestCase):
    def test_every_entry_has_four_parts_and_two_to_four_choices(self):
        for code, e in ENTRIES.items():
            for part in ("what_happened", "why", "fix"):
                self.assertTrue(str(e.get(part, "")).strip(), f"{code} has no {part}")
            self.assertTrue(2 <= len(e["choices"]) <= 4, f"{code} has {len(e['choices'])} choices")
            done_for_you = DONE_FOR_BUYER if e.get("audience") == "buyer" else AGENT_CHOICE
            self.assertTrue(any(done_for_you.match(c) for c in e["choices"]), f"{code} has no do-it-for-you choice")

    def test_every_stop_in_the_inventory_has_an_entry(self):
        self.assertGreaterEqual(len(INVENTORY), 46)
        self.assertEqual(sorted(INVENTORY - set(ENTRIES)), [], "a stop with no plain explanation")
        self.assertEqual(sorted(set(ENTRIES) - INVENTORY), [], "a table entry missing from the inventory above")

    def test_every_stop_code_in_the_scripts_is_in_the_inventory(self):
        # the maintainer rule: a new client-facing stop ships with its explanation entry, or this fails
        self.assertEqual(sorted(codes_in_scripts() - INVENTORY), [])

    def test_every_rendered_message_is_free_of_codes_paths_and_tracebacks(self):
        for code in ENTRIES:
            msg = explain_stop(code)["message"]
            self.assertEqual(leaks(msg), [], f"{code}: {msg}")
            self.assertNotIn("{", msg, f"{code} left a placeholder: {msg}")
            self.assertTrue(msg.rstrip().endswith("Reply with the number you want."), code)

    def test_spent_nothing_is_said_only_when_the_entry_allows_it(self):
        for code, e in ENTRIES.items():
            said = "spent no money" in explain_stop(code)["message"] or "not been charged" in explain_stop(code)["message"]
            self.assertEqual(said, bool(e.get("spends_nothing")), code)
        self.assertNotIn("spent no money", explain_stop("S78-IMAGES-STEP-FAILED")["message"])

class FillTests(unittest.TestCase):
    def test_placeholders_fill_with_real_numbers(self):
        out = explain_stop("S78-INSTALLMENT-TOTAL-MISMATCH",
                           {"offer": "Growth", "count": 3, "schedule_total": "$290.00", "total": "$297.00"})
        self.assertEqual(out["what_happened"],
                         "Growth is split into 3 payments that add up to $290.00, but its price says $297.00.")

    def test_a_real_violation_carries_its_numbers_to_the_client(self):
        launch = json.loads(json.dumps(SELF_TEST_LAUNCH))
        price = launch["offers"][1]["prices"][0]
        price.update(billing_type="installment", amount_minor=19700,
                     schedule=[{"amount_minor": 9000, "due": "today"}, {"amount_minor": 9000, "due": "in 30 days"}])
        with self.assertRaises(Violation) as caught:
            validate_catalog(launch)
        exp = caught.exception.client_explanation
        self.assertIn("TEST ONLY B is split into 2 payments that add up to $180.00", exp["what_happened"])
        self.assertIn("$197.00", exp["what_happened"])
        self.assertEqual(leaks(exp["message"]), [])

    def test_a_fact_carrying_a_code_or_path_is_cleaned(self):
        out = explain_stop("S78-UNKNOWN-PRICE", {"offer": "S78-X /tmp/a/b.py"})
        self.assertEqual(leaks(out["message"]), [])

class FallbackTests(unittest.TestCase):
    def test_unknown_code_gets_four_fixed_plain_parts_and_never_its_raw_text(self):
        out = explain_stop("S99-NEVER-SEEN", envelope={"detail": "KeyError: 'secret'", "next_action": "rm -rf x"})
        self.assertEqual((out["what_happened"], out["why"], out["fix"]),
                         (FALLBACK["what_happened"], FALLBACK["why"], FALLBACK["fix"]))
        self.assertNotIn("secret", out["message"])
        self.assertNotIn("KeyError", out["message"])
        self.assertNotIn("rm -rf", out["message"])
        self.assertTrue(2 <= len(out["choices"]) <= 4 and any(AGENT_CHOICE.match(c) for c in out["choices"]))
        self.assertFalse(out["spent_nothing"])

    def test_a_crash_inside_the_runtime_never_reaches_the_client_as_exception_text(self):
        import selection_runtime
        with mock.patch.object(selection_runtime, "build_plan", side_effect=KeyError("secret")):
            out = Runtime().handle({"action": "plan", "launch": SELF_TEST_LAUNCH})
        self.assertFalse(out["ok"])
        self.assertIn("secret", out["error"]["message"])  # the exception text stays here, for the logs
        shown = out["error"]["client_explanation"]["message"]
        self.assertEqual(leaks(shown), [], shown)
        self.assertNotIn("secret", shown)
        self.assertNotIn("KeyError", shown)

    def test_unknown_with_nothing_is_never_empty_and_never_a_raw_code(self):
        for env in (None, {}, {"error": {"code": "S78-BRAND-NEW", "message": "S78-BRAND-NEW"}},
                    "Traceback (most recent call last):\n  File \"/x/y.py\", line 3\nKeyError: 'z'"):
            out = explain_stop(envelope=env)
            self.assertTrue(out["what_happened"] and out["why"] and out["fix"] and out["choices"], env)
            self.assertEqual(leaks(out["message"]), [], out["message"])

    def test_a_piped_stop_line_keeps_its_real_numbers(self):
        line = json.dumps({"ok": False, "error": {"code": "S78-INSTALLMENT-TOTAL-MISMATCH", "message": "log",
                           "facts": {"offer": "Elite", "count": 2, "schedule_total": "$400.00", "total": "$497.00"}}})
        out = explain_stop(envelope=from_output("RUN x y\n" + line + "\nREFUSED: [S78-INSTALLMENT-TOTAL-MISMATCH] log\n"))
        self.assertEqual(out["what_happened"],
                         "Elite is split into 2 payments that add up to $400.00, but its price says $497.00.")
        self.assertEqual(from_output("plain text, no envelope"), "plain text, no envelope")

    def test_image_step_refusal_text_is_matched_to_its_entry(self):
        out = explain_stop(envelope="REFUSED: provider 'kie' is a paid route and needs --allow-paid on this command line")
        self.assertIn("nobody said yes to spending money", out["what_happened"])

class WiringTests(unittest.TestCase):
    def test_runtime_error_envelope_carries_client_explanation_beside_code_and_message(self):
        bad = json.loads(json.dumps(SELF_TEST_LAUNCH))
        bad["offers"][0]["prices"][0].update(approval_status="unknown", amount_minor=None)
        out = Runtime().handle({"action": "plan", "launch": bad})
        self.assertEqual(out["error"]["code"], "S78-UNKNOWN-PRICE")
        self.assertTrue(out["error"]["message"])
        self.assertIn("TEST ONLY A has no price yet.", out["error"]["client_explanation"]["message"])

    def test_bad_request_and_storage_envelopes_explain_too(self):
        out = Runtime().handle({"action": "plan"})
        self.assertEqual(leaks(out["error"]["client_explanation"]["message"]), [])
        self.assertIn("could not read", out["error"]["client_explanation"]["what_happened"])

    def test_a_declined_plan_is_ok_and_still_explained(self):
        single = dict(SELF_TEST_LAUNCH, journey_mode="single_simple", offers=SELF_TEST_LAUNCH["offers"][:1])
        out = Runtime().handle({"action": "plan", "launch": single})
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["outcome"], "declined_single_offer")
        self.assertIn("only one main package", out["client_explanation"]["what_happened"])
        mode = Runtime().handle({"action": "invocation", "launch": dict(SELF_TEST_LAUNCH, journey_mode="folded_levels")})
        self.assertIn('a "folded levels"', mode["client_explanation"]["what_happened"])

    def test_session_expired_and_reconfirm_carry_the_buyer_explanation(self):
        store = SessionStore(ttl_seconds=10)
        rt = Runtime()
        sel = rt.handle({"action": "select", "launch": SELF_TEST_LAUNCH, "offer_id": "MAIN-B",
                         "price_choice_id": "MAIN-B-USD", "selected_at": "2026-11-20T12:00:00Z",
                         "source_page_id": "P", "session_ref": "opaque"})["result"]
        ref = store.create(sel, now=0)
        gone = store.resume(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH", launch=SELF_TEST_LAUNCH, now=99)
        self.assertEqual(gone["state"], "expired")
        self.assertIn("nothing was picked for you", gone["client_explanation"]["message"])
        self.assertIn("1. We take you back to the packages now", gone["client_explanation"]["message"])
        changed = json.loads(json.dumps(SELF_TEST_LAUNCH))
        changed["offers"][1]["prices"][0]["amount_minor"] = 24700
        ref = store.create(sel, now=0)
        out = store.confirm(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH", launch=changed, now=1)
        self.assertEqual(out["state"], "reconfirm_required")
        self.assertEqual(out["reason_code"], "S78-SELECTION-PRICE-DRIFT")  # kept for logs
        self.assertIn("It was $197.00, now it is $247.00.", out["client_explanation"]["what_happened"])
        self.assertIn("You have not been charged.", out["client_explanation"]["message"])

    def test_the_picture_step_stop_reaches_the_client_with_its_real_numbers(self):
        """run_image_stages.py refuses the copy gate; its printed output, piped through
        explain_stop.py --from-output, still says how many payments and what they add up to."""
        import subprocess
        import tempfile
        golden = SKILL / "fixtures" / "golden-three-option"
        launch = json.loads((golden / "launch.json").read_text())
        price = next(o for o in launch["offers"] if o["offer_id"] == "MAIN-ELITE")["prices"][0]
        price["schedule"][1]["amount_minor"] = 24750  # 24850 + 24750 = $496.00, the price says $497.00
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "launch.json").write_text(json.dumps(launch))
            (tmp / "request.json").write_text(json.dumps({"test_only": True}))
            (tmp / "inputs.json").write_text(json.dumps(
                {"route_graph": "g", "brand_file": "b", "brand_owner": "o", "image_cap": "1"}))
            run = subprocess.run([sys.executable, str(SKILL / "scripts" / "run_image_stages.py"),
                                  "--plan", str(golden / "plan.json"), "--request", str(tmp / "request.json"),
                                  "--run-dir", str(tmp / "run"), "--launch-record", str(tmp / "launch.json"),
                                  "--inputs", str(tmp / "inputs.json")], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
            self.assertIn("REFUSED: [S78-INSTALLMENT-TOTAL-MISMATCH]", run.stdout + run.stderr)  # log line kept
            self.assertFalse((tmp / "run").exists())  # nothing drawn
        told = subprocess.run([sys.executable, str(SKILL / "scripts" / "explain_stop.py"), "--from-output", "-"],
                              input=run.stdout + run.stderr, capture_output=True, text=True)
        self.assertEqual(told.returncode, 0, told.stderr)
        self.assertIn("TEST ONLY Elite is split into 2 payments that add up to $496.00, but its price says $497.00.",
                      told.stdout)
        self.assertEqual(leaks(told.stdout), [], told.stdout)

    def test_plan_built_normally_has_no_explanation_noise(self):
        out = Runtime().handle({"action": "plan", "launch": SELF_TEST_LAUNCH})
        self.assertTrue(out["ok"])
        self.assertNotIn("client_explanation", out)
        self.assertEqual(build_plan(SELF_TEST_LAUNCH)["outcome"], "plan")

if __name__ == "__main__":
    unittest.main()
