#!/usr/bin/env python3
"""FIX 11 on the HOSTED path — the app's client can actually reach Ultra.

FIX 11 wired the run mode (ultra|standard|economy) through the question bank,
deck-intake-driver.py and presentation-intake-poll.sh. The hosted interview app
is a THIRD intake path and had no run-mode handling of ANY kind. Measured on
pristine main, with python3 whole-file scans (control: the literal "intake",
non-empty in every file):

  * bridge/intake_writer.py    (525 lines) -- run_mode 0, RUN_MODE 0, ultra 0
  * test/test_intake_writer.py (213 lines) -- the same five zeros
  * pages/questions.json       (15 questions) -- the app never asks
  * pages/index.html, payload/build_questions_payload.py, bridge/
    intake_bridge.py, worker/src/*.js -- the same zeros

So a client on the hosted path could not express a run mode at all, and the
ledger this writer produced carried no RUN_MODE key for the poller's first
candidate. Every hosted run executed STANDARD while every surface reported
success. Silent, and it affected real paying clients.

WHAT THE PRISTINE WRITER DID DO, measured, so this file does not overclaim: an
INJECTED run_mode answer (one no client could produce, because nothing asked)
fell through write_ledger's generic answer loop into entries["run_mode"] RAW --
unnormalised, unvalidated, and also copied into deck_brief.RUN_MODE. "quick",
"in-depth" and "turbo" all landed there unrefused. The canonical RUN_MODE key
was never written in any case.

THE CONTRACT IS THE DRIVER'S. deck-intake-driver.py's _record_run_mode is the
reference implementation; these tests pin this writer to the same ledger key,
the same record shape, the same normalisation, and the same
absence-writes-nothing rule, so presentation-intake-poll.sh reads this path
with NO poller change.

THE TWO AXES ARE NOT INTERCHANGEABLE. Run mode (ultra|standard|economy) is how
the deck is BUILT. Interview depth (quick|in-depth, FIX 30 standard_mode / FIX
36 --intake-depth) is how much of the interview is asked. Nothing here touches
presentation-canonical-entry.sh or tests/test_fix36_intake_depth.py, which own
the other direction of that guard.

NEVER ULTRA BY DEFAULT. Every "undeclared" case below ends at standard.

Run: python3 test/test_intake_writer_run_mode.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "bridge"))
sys.path.insert(0, str(APP / "payload"))

import build_questions_payload as bqp  # noqa: E402
import intake_writer as iw  # noqa: E402

#: The bank -- the source of truth this module mirrors. Absent in a standalone
#: app checkout, in which case the drift tests skip (and say so).
BANK = APP.parent / "deck-intake-questions.json"


def _bank_run_mode_subfield():
    if not BANK.is_file():
        return None
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    rp = [q for q in bank["questions"] if q["id"] == "resource_plan"]
    if not rp:
        return None
    return (rp[0].get("subfields") or {}).get("run_mode")


#: A complete, grounded hosted submission. presentation_type is mandatory --
#: without it the writer fails closed on the deck-type axis before it ever
#: reaches the run mode, which would make every assertion below vacuous.
BASE_ANSWERS = {
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
    "want_sales_checkout": "yes",
    "want_vsl_page": "no",
    "client_notes": "",
}


def _submit(run_mode=None, *, frontend_shaped=False):
    """Drive the REAL writer end to end and return (run_dir, entries, intake).

    frontend_shaped replays intake_bridge.cmd_ingest()'s route -- the payload
    the browser assembled, handed straight to write_intake_file()/
    write_ledger() without going through assemble_intake() at all. Both routes
    are tested because both are real: cmd_ingest is the one production uses.
    """
    answers = dict(BASE_ANSWERS)
    if run_mode is not None:
        answers["run_mode"] = run_mode
    run_dir = pathlib.Path(tempfile.mkdtemp(prefix="hosted-run-mode-"))
    if frontend_shaped:
        pre = {"REPRESENTATION_MIX": "the stated audience",
               "AUDIENCE_COMPOSITION_NOTE": answers["audience"],
               "GROUNDED_CONTENT": answers["offer_name"],
               "VISUAL_MIX": "mix", "DARK_OK": False,
               "HOOK_SEED": answers["transformation_promise"]}
        if run_mode is not None:
            pre["RUN_MODE"] = run_mode
        intake = {"interview_confirmed": True, "presentation_type": "from_scratch",
                  "source": "presentation-interview-app",
                  "pre_presentation_capture": pre,
                  "deck_brief": {"OFFER_NAME": answers["offer_name"],
                                 "AUDIENCE": answers["audience"]},
                  "intake": {}, "answers": answers}
    else:
        intake = iw.assemble_intake({"answers": answers}, run_id="RM-TEST")
    iw.write_intake_file(run_dir, intake)
    ledger = iw.write_ledger(run_dir, intake)
    entries = json.loads(ledger.read_text(encoding="utf-8"))["entries"]
    written = json.loads(
        (run_dir / "working" / "copy" / "intake.json").read_text(encoding="utf-8"))
    return run_dir, entries, written


class TestVocabularyMirrorsTheBank(unittest.TestCase):
    """The mirror may not drift. This module is stdlib-only and cannot import
    the bank at runtime, exactly like MANDATORY_PRE_CAPTURE and
    LEGACY_FIELD_MAPPING above it -- so the drift guard is executable instead."""

    def test_ledger_key_and_subfield_id_match_the_driver(self):
        self.assertEqual(iw._RUN_MODE_SUBFIELD, ("run_mode", "RUN_MODE"))

    def test_vocabulary_matches_the_bank(self):
        ann = _bank_run_mode_subfield()
        if ann is None:
            self.skipTest(f"canonical bank not reachable at {BANK}")
        self.assertEqual([str(v).lower() for v in ann["enum"]],
                         list(iw.RUN_MODES))
        self.assertEqual(ann["storeOn"], iw._RUN_MODE_SUBFIELD[1])
        self.assertEqual(ann["default"], "")   # undeclared is undeclared

    def test_refusal_vocabulary_and_message_match_the_bank(self):
        ann = _bank_run_mode_subfield()
        if ann is None:
            self.skipTest(f"canonical bank not reachable at {BANK}")
        self.assertEqual([str(v).lower() for v in ann["refuse_values"]],
                         list(iw.RUN_MODE_REFUSED_VALUES))
        self.assertEqual(ann["refuse_message"], iw.RUN_MODE_REFUSE_MESSAGE)

    def test_the_default_is_standard_and_is_never_ultra(self):
        self.assertEqual(iw.DEFAULT_RUN_MODE, "standard")
        self.assertNotEqual(iw.DEFAULT_RUN_MODE, "ultra")


class TestTheAppActuallyAsks(unittest.TestCase):
    """The reachability half of the defect: the writer could persist a mode all
    day and it would change nothing while no question ever collected one."""

    def test_the_shipped_question_set_asks_for_a_run_mode(self):
        qj = json.loads((APP / "pages" / "questions.json").read_text(encoding="utf-8"))
        rows = [q for q in qj["questions"] if q["id"] == "run_mode"]
        self.assertEqual(len(rows), 1, [q["id"] for q in qj["questions"]])
        q = rows[0]
        self.assertEqual(q["allowed_values"], list(iw.RUN_MODES))
        self.assertEqual(q["default"], "")          # skip declares nothing
        self.assertFalse(q["required"])             # ... and skipping is allowed
        self.assertNotIn("deck_brief", q["storeOn"])  # execution axis

    def test_the_question_stays_inside_the_documented_cap(self):
        """questions.json's own contract: "Cap 20; this set is 16." The cap is
        enforced twice -- build_questions_payload's selftest/test_payload
        (len(ids) <= 20) and index.html's MAX_QUESTIONS -- and 16 clears both."""
        qj = json.loads((APP / "pages" / "questions.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(qj["questions"]), 20)
        self.assertIn("Cap 20; this set is 16.", qj["description"])
        html = (APP / "pages" / "index.html").read_text(encoding="utf-8")
        self.assertIn("var MAX_QUESTIONS = 20;", html)
        self.assertIn('{ id: "run_mode", order: 11.5, kind: "enum",', html)

    def test_the_curated_payload_carries_it_projected_from_the_bank(self):
        self.assertIn("run_mode", bqp.DEFAULT_CURATED)
        specs, _, store_target = bqp.load_specs(bqp._project_root(APP / "payload"))
        payload = bqp.build_curated_payload("R", specs, bqp.DEFAULT_CURATED,
                                            store_target)
        rows = [q for q in payload["questions"] if q["id"] == "run_mode"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["allowed_values"], list(iw.RUN_MODES))
        self.assertIn("quick", [str(v).lower()
                                for v in rows[0].get("refuse_values", [])])


class TestDeclaredModeLandsInTheLedger(unittest.TestCase):
    def test_ultra_lands_under_the_key_the_poller_reads(self):
        _, entries, _ = _submit("ultra")
        self.assertEqual(entries["RUN_MODE"]["value"], "ultra")
        self.assertEqual(entries["run_mode"]["value"], "ultra")

    def test_the_record_shape_is_the_drivers(self):
        """deck-intake-driver._record_run_mode's record, field for field. Only
        `source` differs -- it names the writer that produced it."""
        _, entries, _ = _submit("ultra")
        rec = entries["RUN_MODE"]
        self.assertEqual(sorted(rec), ["answer", "answered_at", "normalized",
                                       "source", "validated", "value"])
        self.assertTrue(rec["validated"])
        self.assertEqual(rec["normalized"], "ultra")
        self.assertEqual(rec["answer"], "ultra")
        self.assertEqual(rec["source"], "presentation-interview-app")

    def test_case_insensitive_in_lowercase_out(self):
        for raw, want in [("ULTRA", "ultra"), ("UlTrA", "ultra"),
                          ("Economy", "economy"), (" standard ", "standard"),
                          ("ultra;", "ultra")]:
            with self.subTest(raw=raw):
                _, entries, _ = _submit(raw)
                self.assertEqual(entries["RUN_MODE"]["value"], want)
                self.assertEqual(entries["run_mode"]["value"], want)

    def test_every_mode_in_the_vocabulary_round_trips(self):
        for mode in iw.RUN_MODES:
            with self.subTest(mode=mode):
                _, entries, _ = _submit(mode)
                self.assertEqual(entries["RUN_MODE"]["value"], mode)

    def test_the_frontend_shaped_bridge_route_lands_it_too(self):
        """intake_bridge.cmd_ingest() never calls assemble_intake(): it hands
        the browser's payload straight to the two writers. The gate has to hold
        on THAT route, because that is the one production uses."""
        _, entries, written = _submit("ultra", frontend_shaped=True)
        self.assertEqual(entries["RUN_MODE"]["value"], "ultra")
        self.assertEqual(written["pre_presentation_capture"]["RUN_MODE"], "ultra")

    def test_a_declared_mode_never_contaminates_the_deck_brief(self):
        """A run mode is an EXECUTION axis, not deck content -- the bank
        subfield says so in as many words. deck_brief is the deck brief."""
        for shaped in (False, True):
            with self.subTest(frontend_shaped=shaped):
                _, _, written = _submit("ultra", frontend_shaped=shaped)
                self.assertNotIn("RUN_MODE", written.get("deck_brief") or {})
                self.assertNotIn("run_mode", written.get("deck_brief") or {})
                self.assertEqual(
                    (written.get("pre_presentation_capture") or {}).get("RUN_MODE"),
                    "ultra")


class TestUndeclaredIsStandardNeverUltra(unittest.TestCase):
    def test_no_declaration_writes_no_key_at_all(self):
        """Absence is absence -- the driver's rule, inherited verbatim. The
        launcher's own default then answers, and it is standard."""
        _, entries, written = _submit(None)
        self.assertNotIn("RUN_MODE", entries, sorted(entries))
        self.assertNotIn("run_mode", entries, sorted(entries))
        self.assertNotIn("RUN_MODE", written.get("pre_presentation_capture") or {})
        self.assertEqual(iw.DEFAULT_RUN_MODE, "standard")

    def test_a_skipped_answer_leaves_no_empty_entry_behind(self):
        """The app's Skip button submits the question's default (""). A ledger
        saying run_mode="" is not the same record as one that never mentions
        it, and the generic answer loop would otherwise leave exactly that."""
        for blank in ("", "   ", None):
            with self.subTest(blank=blank):
                _, entries, _ = _submit("" if blank is None else blank)
                self.assertNotIn("RUN_MODE", entries, sorted(entries))
                self.assertNotIn("run_mode", entries, sorted(entries))

    def test_nothing_declared_is_never_silently_promoted_to_ultra(self):
        for shaped in (False, True):
            with self.subTest(frontend_shaped=shaped):
                _, entries, written = _submit(None, frontend_shaped=shaped)
                blob = json.dumps({"entries": entries, "intake": written})
                self.assertNotIn("ultra", blob.lower())


class TestRefusals(unittest.TestCase):
    """Refused, never coerced -- and nothing half-lands. Both writers raise
    BEFORE writing, so a refused submission leaves no intake.json carrying the
    bad word and no ledger marked "complete" on top of it."""

    def _refusal(self, word, *, shaped=False):
        with self.assertRaises(iw.RunModeVocabularyError) as ctx:
            _submit(word, frontend_shaped=shaped)
        return str(ctx.exception)

    def test_interview_depth_vocabulary_is_refused_naming_both_axes(self):
        for word in ("quick", "QUICK", "in-depth", "In-Depth", "in_depth",
                     "indepth"):
            with self.subTest(word=word):
                msg = self._refusal(word)
                self.assertIn("ultra|standard|economy", msg)
                self.assertIn("quick|in-depth", msg)
                self.assertIn("never interchangeable", msg)

    def test_the_depth_refusal_holds_on_the_bridge_route_too(self):
        msg = self._refusal("in-depth", shaped=True)
        self.assertIn("ultra|standard|economy", msg)
        self.assertIn("quick|in-depth", msg)

    def test_garbage_is_refused_never_coerced(self):
        for word in ("turbo", "banana", "fast", "max", "ludicrous"):
            with self.subTest(word=word):
                msg = self._refusal(word)
                self.assertIn(word.lower(), msg)
                self.assertIn("run_mode", msg)
                self.assertIn("ultra|standard|economy", msg)
                self.assertNotIn("never interchangeable", msg)

    def test_a_refused_submission_writes_nothing_at_all(self):
        answers = dict(BASE_ANSWERS, run_mode="quick")
        run_dir = pathlib.Path(tempfile.mkdtemp(prefix="hosted-refused-"))
        intake = iw.assemble_intake({"answers": answers}, run_id="RM-REFUSE")
        with self.assertRaises(iw.RunModeVocabularyError):
            iw.write_intake_file(run_dir, intake)
        self.assertFalse((run_dir / "working" / "copy" / "intake.json").exists())
        with self.assertRaises(iw.RunModeVocabularyError):
            iw.write_ledger(run_dir, intake)
        self.assertFalse(
            (run_dir / "working" / "interview" / "intake_ledger.json").exists())

    def test_the_cli_exits_4_on_a_refused_run_mode(self):
        """A distinct code from the deck-type refusal's 3, so a caller can tell
        the client WHICH answer to fix."""
        payload = pathlib.Path(tempfile.mkdtemp(prefix="rm-cli-")) / "in.json"
        payload.write_text(json.dumps(
            {"answers": dict(BASE_ANSWERS, run_mode="in-depth")}),
            encoding="utf-8")
        run_dir = pathlib.Path(tempfile.mkdtemp(prefix="rm-cli-run-"))
        rc = iw.main(["--intake", str(payload), "--run-dir", str(run_dir)])
        self.assertEqual(rc, 4)
        self.assertFalse((run_dir / "working").exists())

    def test_a_valid_run_mode_still_exits_zero(self):
        """The control for the test above: the same CLI, the same payload
        shape, a legal mode -- 0, and the ledger carries it."""
        payload = pathlib.Path(tempfile.mkdtemp(prefix="rm-cli-ok-")) / "in.json"
        payload.write_text(json.dumps(
            {"answers": dict(BASE_ANSWERS, run_mode="ultra")}), encoding="utf-8")
        run_dir = pathlib.Path(tempfile.mkdtemp(prefix="rm-cli-ok-run-"))
        self.assertEqual(iw.main(["--intake", str(payload),
                                  "--run-dir", str(run_dir)]), 0)
        entries = json.loads(
            (run_dir / "working" / "interview" / "intake_ledger.json")
            .read_text(encoding="utf-8"))["entries"]
        self.assertEqual(entries["RUN_MODE"]["value"], "ultra")


class TestNothingElseMoved(unittest.TestCase):
    """The existing hosted contract is unchanged by this fix."""

    def test_the_deck_type_gate_still_fails_closed_first(self):
        run_dir = pathlib.Path(tempfile.mkdtemp(prefix="rm-notype-"))
        answers = {k: v for k, v in BASE_ANSWERS.items()
                   if k != "presentation_type"}
        answers["run_mode"] = "ultra"
        with self.assertRaises(iw.UngroundedDeckTypeError):
            iw.assemble_intake({"answers": answers}, run_id="X")
        self.assertFalse((run_dir / "working").exists())

    def test_the_other_answers_still_land_where_they_always_did(self):
        _, entries, written = _submit("ultra")
        self.assertEqual(written["deck_brief"]["OFFER_NAME"],
                         "The Momentum Method")
        self.assertEqual(written["intake"]["speech_speed_preference"], "default")
        self.assertEqual(
            written["pre_presentation_capture"]["WANT_SALES_CHECKOUT"], "yes")
        self.assertEqual(written["named_methodology"],
                         "The Three-Move Pipeline")
        self.assertEqual(written["deck_type"], "webinar")
        for k in iw.MANDATORY_PRE_CAPTURE:
            self.assertIn(k, written["pre_presentation_capture"])
        self.assertEqual(entries["offer_name"]["value"],
                         "The Momentum Method")


if __name__ == "__main__":
    unittest.main(verbosity=2)
