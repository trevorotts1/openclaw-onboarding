#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q18 style card (fix spec M4, issue 39): AF-FUN-PROMPT-STYLE-CARD.

A client who answers Q18 with a registered Skill 45 style card is told every image will be locked
to it. Until now nothing checked block 8. The prompt gate now resolves the card the intake (brief)
names and requires its LONG tier VERBATIM in every prompt's block 8, ahead of the negative
directives. The card text is read from the design library, so a paraphrase, a truncation, an
unregistered id or a missing library each fail by name.

Run: python3 -m pytest 49-signature-funnel/scripts/test_prove_sf_prompt_floor.py -q
 or: python3 49-signature-funnel/scripts/test_prove_sf_prompt_floor.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import prove_sf_intake as intake  # noqa: E402
import prove_sf_prompt_floor as pf  # noqa: E402
import run_signature_funnel as runner  # noqa: E402

CODE = "AF-FUN-PROMPT-STYLE-CARD"
_BLOCK_8 = re.compile(r"BRAND STYLE AND NEGATIVE BLOCK[:.]")


def carry_card(prompt: str) -> str:
    """Put the fixture card's LONG tier into block 8, ahead of the negative directives."""
    return _BLOCK_8.sub(lambda m: f"{m.group(0)} {pf.FIXTURE_CARD_TIER} ", prompt, count=1)


def carded_ledger(size: int = 3) -> dict:
    ledger = pf._floor_passing_full_prompts(size)
    for rec in ledger["prompts"]:
        rec["prompt"] = carry_card(rec["prompt"])
    return ledger


def codes(violations) -> set:
    return {c for c, _ in violations}


class StyleCardGate(unittest.TestCase):
    def setUp(self):
        ctx = pf.fixture_library()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)

    def test_card_in_every_prompt_passes(self):
        violations, notes = pf.verify(carded_ledger(), pf.FIXTURE_CARD_ID)
        self.assertEqual(violations, [], violations)
        self.assertTrue(any(pf.FIXTURE_CARD_ID in n for n in notes))

    def test_no_card_requested_changes_nothing(self):
        violations, _ = pf.verify(pf._floor_passing_full_prompts(3), None)
        self.assertEqual(violations, [], violations)

    def test_block_8_without_the_card_fails(self):
        # Q18 answered, prompts built from the default Signature look: this used to certify
        violations, _ = pf.verify(pf._floor_passing_full_prompts(3), pf.FIXTURE_CARD_ID)
        self.assertEqual(codes(violations), {CODE}, violations)
        self.assertEqual(len(violations), len(pf._floor_passing_full_prompts(3)["prompts"]))

    def test_one_prompt_missing_the_card_fails_only_that_prompt(self):
        ledger = carded_ledger()
        ledger["prompts"][4]["prompt"] = pf._valid_photo_prompt()
        violations, _ = pf.verify(ledger, pf.FIXTURE_CARD_ID)
        self.assertEqual(len(violations), 1, violations)
        self.assertEqual(codes(violations), {CODE})

    def test_paraphrased_or_truncated_card_fails(self):
        for edit in (lambda t: t.replace("metallic gold", "golden"), lambda t: t[:-12]):
            ledger = pf._floor_passing_full_prompts(3)
            for rec in ledger["prompts"]:
                rec["prompt"] = _BLOCK_8.sub(lambda m: f"{m.group(0)} {edit(pf.FIXTURE_CARD_TIER)} ",
                                             rec["prompt"], count=1)
            violations, _ = pf.verify(ledger, pf.FIXTURE_CARD_ID)
            self.assertEqual(codes(violations), {CODE}, violations)

    def test_card_with_no_negative_after_it_fails(self):
        ledger = carded_ledger()
        rec = ledger["prompts"][0]
        rec["prompt"] = rec["prompt"][: rec["prompt"].rfind(pf.FIXTURE_CARD_TIER) + len(pf.FIXTURE_CARD_TIER)]
        got, _ = pf.evaluate_prompt(rec, pf.DI.resolve_style_card(pf.FIXTURE_CARD_ID))
        self.assertIn(CODE, codes(got))
        self.assertTrue(any("follows" in m for c, m in got if c == CODE), got)

    def test_card_quoted_twice_the_last_copy_must_be_followed_by_a_negative(self):
        # the gate reads the LAST copy of the tier: an earlier, properly placed copy cannot vouch for a
        # later copy that nothing negative follows (first-occurrence matching would let this pass)
        ledger = carded_ledger()
        rec = ledger["prompts"][0]
        rec["prompt"] = rec["prompt"] + " " + pf.FIXTURE_CARD_TIER
        got, _ = pf.evaluate_prompt(rec, pf.DI.resolve_style_card(pf.FIXTURE_CARD_ID))
        self.assertIn(CODE, codes(got))
        self.assertTrue(any("follows" in m for c, m in got if c == CODE), got)

    def test_unregistered_card_and_absent_library_fail_by_name(self):
        violations, _ = pf.verify(pf._floor_passing_full_prompts(3), "FN-NOPE-404")
        self.assertEqual(codes(violations), {CODE})
        self.assertIn("AF-DI-ABSENT", violations[0][1])
        empty = tempfile.mkdtemp(prefix="sf_nolib_")
        os.environ["DIU_LIBRARY_DIR"] = empty  # restored by fixture_library's exit
        violations, _ = pf.verify(carded_ledger(), pf.FIXTURE_CARD_ID)
        self.assertEqual(codes(violations), {CODE})
        self.assertIn("AF-DI-ABSENT", violations[0][1])

    def test_ledger_naming_another_card_than_the_intake_fails(self):
        ledger = carded_ledger()
        ledger["style_card_id"] = "FN-OTHER-002"
        violations, _ = pf.verify(ledger, pf.FIXTURE_CARD_ID)
        self.assertIn(CODE, codes(violations))
        self.assertTrue(any("intake" in m for _, m in violations), violations)

    def test_brief_reader(self):
        with tempfile.TemporaryDirectory() as td:
            for brief, want in (({"answers": {"q18_style_card_id": " FN-1 "}}, "FN-1"),
                                ({"answers": {"q18_style_card_id": ""}}, None),
                                ({"answers": {}}, None),
                                ({"style_card_id": "FN-2"}, "FN-2")):
                path = Path(td) / "brief.json"
                path.write_text(json.dumps(brief), encoding="utf-8")
                self.assertEqual(pf._brief_style_card_id(str(path)), want, brief)
            self.assertIsNone(pf._brief_style_card_id(None))
            (Path(td) / "bad.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                pf._brief_style_card_id(str(Path(td) / "bad.json"))


class StyleCardGateDetails(unittest.TestCase):
    """Round-5 sweep survivors: boundary, wording the operator reads, id normalisation, fixture hygiene."""

    def setUp(self):
        ctx = pf.fixture_library()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        self.card = pf.DI.resolve_style_card(pf.FIXTURE_CARD_ID)

    def test_card_at_the_very_start_of_the_prompt_is_found(self):
        got = pf._check_style_card(pf.FIXTURE_CARD_TIER + " Do not misspell any word.", self.card, "p")
        self.assertEqual(got, [])

    def test_missing_card_message_names_the_card_and_says_it_is_not_embedded(self):
        got = pf._check_style_card("nothing here. Do not misspell.", self.card, "p")
        self.assertEqual(codes(got), {CODE})
        msg = got[0][1]
        self.assertIn("is not embedded verbatim", msg)
        self.assertIn(self.card["sha256"][:12] + ",", msg)
        self.assertNotIn(self.card["sha256"][:13], msg)

    def test_hash_mismatch_message_shows_both_twelve_character_hashes(self):
        # the slice is found but hashes differently: force that branch with a stub card
        stub = dict(self.card, sha256="0" * 64)
        got = pf._check_style_card(pf.FIXTURE_CARD_TIER + " Do not misspell.", stub, "p")
        real = hashlib.sha256(pf.FIXTURE_CARD_TIER.encode("utf-8")).hexdigest()
        self.assertTrue(got[0][1].endswith(f"hashes to {real[:12]}, not the card's {'0' * 12}"), got)

    def test_absent_reader_message_says_it_is_not_installed(self):
        saved = pf.DI
        self.addCleanup(setattr, pf, "DI", saved)
        pf.DI = None
        card, violations = pf._resolve_requested_card({}, pf.FIXTURE_CARD_ID)
        self.assertIsNone(card)
        self.assertEqual(codes(violations), {CODE})
        self.assertIn("is not installed", violations[0][1])

    def test_a_brief_that_is_not_an_object_says_so(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "brief.json"
            path.write_text("[1]", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                pf._brief_style_card_id(str(path))
            self.assertIn("is not a JSON object", str(caught.exception))

    def test_the_note_says_the_card_is_required_and_names_its_hash(self):
        _, notes = pf.verify(carded_ledger(), pf.FIXTURE_CARD_ID)
        want = f"style card {pf.FIXTURE_CARD_ID} (LONG tier sha256 {self.card['sha256']}) is required in block 8"
        self.assertTrue(any(n.startswith(want) for n in notes), notes)

    def test_ids_are_compared_trimmed_and_case_insensitively(self):
        for ledger_id, intake_id in ((" FN-X ", "FN-X"), ("FN-X", " FN-X "), ("fn-x", "FN-X"), ("FN-X", "fn-x")):
            _, violations = pf._resolve_requested_card({"style_card_id": ledger_id}, intake_id)
            self.assertFalse(any("intake" in m for _, m in violations), (ledger_id, intake_id, violations))
        _, violations = pf._resolve_requested_card({"style_card_id": "FN-Y"}, "FN-X")
        self.assertTrue(any("intake" in m for _, m in violations), violations)

    def test_fixture_tier_carries_its_own_negative_so_the_follows_check_is_meaningful(self):
        self.assertIn(pf.NEGATIVE_IMPERATIVE, pf.FIXTURE_CARD_TIER.lower())

    def test_carded_photo_prompt_passes_the_card_check(self):
        rec = {"prompt": pf._carded_photo_prompt()}
        got, _ = pf.evaluate_prompt(rec, self.card)
        self.assertNotIn(CODE, codes(got), got)

    def test_fixture_library_restores_a_previously_set_library_dir(self):
        before = os.environ.get("DIU_LIBRARY_DIR")
        self.addCleanup(lambda: os.environ.__setitem__("DIU_LIBRARY_DIR", before) if before is not None
                        else os.environ.pop("DIU_LIBRARY_DIR", None))
        os.environ["DIU_LIBRARY_DIR"] = "/nonexistent-previous-library"
        with pf.fixture_library():
            self.assertNotEqual(os.environ["DIU_LIBRARY_DIR"], "/nonexistent-previous-library")
        self.assertEqual(os.environ["DIU_LIBRARY_DIR"], "/nonexistent-previous-library")


class SelfTestAndCommandLine(unittest.TestCase):
    """The prover's own --self-test battery and its --brief reading, run through main()."""

    def run_main(self, argv):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pf.main(argv)
        return rc, buf.getvalue()

    def test_self_test_passes_and_reports_the_style_card_cases(self):
        rc, out = self.run_main(["--self-test"])
        self.assertEqual(rc, 0, out)
        self.assertIn("SELF-TEST ok: style card embedded verbatim in block 8 PASSES (Q18).", out)
        for name in ("style_card_missing_from_block_8", "style_card_paraphrased", "style_card_unregistered"):
            self.assertIn(f"SELF-TEST ok: '{name}' -> nonzero, carries {CODE}.", out)
        n = len(pf._violation_cases())
        self.assertIn(f"SELF-TEST FIXTURES: 1 valid-pass, {n}/{n} violation-catch", out)
        self.assertIn("SELF-TEST RESULT: PASS (exit 0)", out)

    def test_self_test_fails_when_the_carded_ledger_does_not_pass(self):
        saved = pf._carded_photo_prompt
        self.addCleanup(setattr, pf, "_carded_photo_prompt", saved)
        pf._carded_photo_prompt = pf._valid_photo_prompt  # the card is gone from block 8
        rc, out = self.run_main(["--self-test"])
        self.assertEqual(rc, 1, out)
        self.assertIn("SELF-TEST FAIL: a prompt ledger carrying the style card verbatim produced", out)
        self.assertIn("SELF-TEST RESULT: FAIL (exit 1)", out)

    def test_the_paraphrased_case_really_carries_a_paraphrased_card(self):
        # the battery must catch a paraphrase, not merely a missing card: the case itself has to be one
        build = {name: fn for name, _, fn in pf._violation_cases()}["style_card_paraphrased"]
        with pf.fixture_library():
            ledger = build()
        self.assertEqual(ledger["style_card_id"], pf.FIXTURE_CARD_ID)
        for rec in ledger["prompts"]:
            self.assertIn("gold-ish accents", rec["prompt"])
            self.assertNotIn("rich metallic gold accents", rec["prompt"])

    def test_an_unreadable_brief_is_a_usage_error_not_a_pass(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.json"
            ledger.write_text(json.dumps(pf._floor_passing_full_prompts(3)), encoding="utf-8")
            rc, out = self.run_main(["--ledger", str(ledger), "--brief", str(Path(td) / "missing.json")])
        self.assertEqual(rc, pf.EXIT_FAILCLOSED, out)
        self.assertIn("USAGE/IO ERROR: cannot read --brief", out)

    def test_help_text_documents_the_brief_card_answer(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            pf.main(["--help"])
        flat = " ".join(buf.getvalue().split())
        self.assertIn("funnel_size in coverage mode; in the prompt gate, its answers.q18_style_card_id", flat)


class P2GateReadsTheBrief(unittest.TestCase):
    """The orchestrator's P2 gate hands the locked brief to the prover (the intake decides)."""

    def run_p2(self, ledger: dict, q18):
        td = tempfile.TemporaryDirectory(prefix="sf_p2_")
        self.addCleanup(td.cleanup)
        rd = Path(td.name)
        brief = intake._valid_runtime(3)
        if q18:
            brief["answers"]["q18_style_card_id"] = q18
        (rd / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
        (rd / "prompt_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        with pf.fixture_library():
            return runner._gate_p2_prompts(rd)

    def test_q18_answered_and_card_absent_from_prompts_blocks_p2(self):
        ok, detail = self.run_p2(pf._floor_passing_full_prompts(3), pf.FIXTURE_CARD_ID)
        self.assertFalse(ok)
        self.assertIn(CODE, detail)

    def test_q18_answered_and_card_in_every_prompt_passes_p2(self):
        ok, detail = self.run_p2(carded_ledger(), pf.FIXTURE_CARD_ID)
        self.assertTrue(ok, detail)

    def test_q18_not_answered_p2_is_unchanged(self):
        ok, detail = self.run_p2(pf._floor_passing_full_prompts(3), None)
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
