#!/usr/bin/env python3
"""W39 CONSUMERS-R2: Q12 and the welcome sheet are bound to the run's record.

Regression for the reviewer-confirmed consumer defects:

  * an explicit run that does not resolve REFUSES -- a missing authority can
    never select the legacy structural fallback and pass;
  * receipt numbers and campaign/purpose fields are never authority: a forged
    ``chosen_length_s=60`` beside a genuine 180-second run whose folder is
    missing both clips is rejected;
  * NaN, Infinity, -1, 0 and boolean length claims neither crash ``evaluate``
    nor pass;
  * a receipt whose identity conflicts with the resolved run is rejected;
  * a structural-only inspection still reports legacy history but never
    grants a production completion;
  * real short (90/120), long and campaign runs pass, and the welcome sheet
    lists exactly the items each one owes.

Every run here is written by the REAL intake card, stage store and method
record. No provider, no ffmpeg process, no render: the deliverable bytes in
the folder are contract fixture bytes used only to exercise the final
checker and the sheet.

Run: python3 delivery_package/test_delivery_package_consumers_r2.py
"""
from __future__ import annotations

import os
import pwd
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from choice_card.intake_card import intake_session as session  # noqa: E402
import delivery_checklist.delivery_checklist as dc              # noqa: E402
import delivery_package.contract as C                           # noqa: E402
import delivery_package.welcome_sheet as ws                     # noqa: E402
from delivery_package import run_inputs as RI                   # noqa: E402

REPLIES = {
    "offer": "New Chapter Coaching", "link": "https://example.com/coaching",
    "audience": "successful founders 45-60",
    "character": "Christine, a lawyer", "photos": "Generate the photos",
    "models": "deepseek-chain builds, opus-chain checks", "spend": "$25",
    "script": "1", "song": "1", "storyboard": "1",
}


def confirm_run(run, *, length="3 minutes + 60s and 90s clips", purpose=None):
    """A REAL confirmed intake (card session, stage store, method record)."""
    run = Path(run)
    flow = purpose is not None
    replies = dict(REPLIES)
    if flow:
        replies["purpose"] = str(purpose)
        replies["episode_length" if purpose == 1 else "length"] = length
    else:
        replies["length"] = length
    turn = session.process([], run_dir=run, purpose_flow=flow,
                           runtime="claude-nine")
    for _ in range(40):
        if turn.get("done"):
            return turn["run_id"]
        qid = turn.get("question_id")
        raw = "yes" if qid == "recap" else replies.get(qid, "1")
        turn = session.process(
            [raw], run_dir=run, purpose_flow=flow, runtime="claude-nine",
            question_id=qid, question_digest=turn.get("question_digest"),
            source="client", source_ref="w39:" + str(qid))
        if turn.get("outcome") == "error":
            raise AssertionError(turn)
    raise AssertionError("intake did not reach its confirmation: %r" % turn)


def write_owed(folder, items):
    """Contract-valid bytes for exactly the items this run owes (no render)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for item in items:
        C.produce_item(item, folder)
    return folder


def receipt(run, folder, *, run_id=None, **claims):
    """The Final edit receipt shape Q12 reads: the folder and the run."""
    ans = {"delivery_folder": str(folder),
           "source": "delivery_package.verify_folder (resolved run)"}
    if run_id is not None:
        ans["run_id"] = run_id
    ans.update(claims)
    return {"run_root": str(run), "PACKAGE_COMPLETE": ans}


def q12(receipt_obj):
    """The actual final checker, reduced to its Q12 answer and evidence."""
    result = dc.evaluate(receipt_obj)
    return result["answers"]["PACKAGE_COMPLETE"], result["evidence"]


def pdf_strings(data):
    """Every text-showing string of the content stream, escapes resolved."""
    text = data.decode("latin-1")
    return [re.sub(r"\\(.)", r"\1", m.group(1))
            for m in re.finditer(r"\(((?:\\.|[^\\()])*)\)\s*Tj", text)]


class OwedFamilies(unittest.TestCase):
    """Real short, long and campaign runs against the real final checker."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="w39-consumers-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_90_and_120_owe_no_clips_and_pass(self):
        for label, seconds in (("90 seconds", 90), ("2 minutes", 120)):
            with self.subTest(length=seconds):
                run = self.tmp / ("short-" + str(seconds))
                confirm_run(run, length=label)
                ctx = RI.delivery_context(run)
                self.assertEqual(ctx["chosen_length_s"], seconds)
                self.assertEqual(ctx["not_applicable"], ("clips",))
                folder = write_owed(run / "delivery", ctx["items"])
                answer, evidence = q12(receipt(run, folder))
                self.assertEqual(answer["answer"], "yes", answer)
                self.assertEqual(evidence["authority"], "resolved-run")
                self.assertEqual(evidence["items_expected"], 11)
                self.assertFalse(list(folder.glob("06 - *.mp4")))

    def test_long_run_owes_the_contracts_two_clips(self):
        run = self.tmp / "long"
        confirm_run(run, length="3 minutes + 60s and 90s clips")
        ctx = RI.delivery_context(run)
        clips = next(i for i in ctx["items"] if i.key == "clips")
        self.assertEqual(clips.files, C.ITEMS_BY_KEY["clips"].files)
        folder = write_owed(run / "delivery", ctx["items"])
        answer, evidence = q12(receipt(run, folder))
        self.assertEqual(answer["answer"], "yes", answer)
        self.assertEqual(evidence["items_expected"], 12)

    def test_campaign_owes_trailers_and_ad_clips(self):
        run = self.tmp / "campaign"
        confirm_run(run, length="3 minutes", purpose=1)
        ctx = RI.delivery_context(run)
        self.assertTrue(ctx["campaign"])
        self.assertEqual(len(ctx["items"]), 13)
        folder = write_owed(run / "delivery", ctx["items"])
        answer, evidence = q12(receipt(run, folder))
        self.assertEqual(answer["answer"], "yes", answer)
        self.assertEqual(evidence["items_expected"], 13)
        for name in C.METHOD_ITEM_FILES[6] + C.AD_CLIPS_ITEM.files:
            self.assertTrue((folder / name).is_file(), name)
        for name in C.ITEMS_BY_KEY["clips"].files:
            self.assertFalse((folder / name).exists(), name)


class ForgedAuthority(unittest.TestCase):
    """Receipt claims are data: they never shrink a real run's obligations."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="w39-forged-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run = self.tmp / "run"
        self.run_id = confirm_run(
            self.run, length="3 minutes + 60s and 90s clips")
        self.short = write_owed(self.tmp / "short-export",
                                C.required_items(60))

    def test_forged_60_claim_beside_real_180_run_missing_clips_rejects(self):
        answer, evidence = q12(receipt(
            self.run, self.short, run_id=self.run_id, chosen_length_s=60))
        self.assertEqual(answer["answer"], "no", (answer, evidence))
        self.assertEqual(evidence["authority"], "resolved-run")
        self.assertIn("run context unverified", answer["measurement"])

    def test_real_180_run_missing_clips_rejects_without_any_claim(self):
        answer, evidence = q12(receipt(
            self.run, self.short, run_id=self.run_id))
        self.assertEqual(answer["answer"], "no", (answer, evidence))
        self.assertIn("clips", evidence["missing_items"])

    def test_identity_conflict_rejects_even_a_complete_folder(self):
        complete = write_owed(self.tmp / "complete",
                              RI.delivery_context(self.run)["items"])
        answer, evidence = q12(receipt(
            self.run, complete, run_id="another-run"))
        self.assertEqual(answer["answer"], "no", (answer, evidence))
        self.assertIn("run context unverified", answer["measurement"])

    def test_malformed_control_refuses(self):
        malformed = self.tmp / "malformed-control"
        (malformed / "control").mkdir(parents=True)
        (malformed / "control" / "intake-session.json").write_text(
            "{broken", encoding="utf-8")
        complete = write_owed(self.tmp / "complete-malformed", C.PACKAGE_ITEMS)
        answer, evidence = q12(receipt(malformed, complete))
        self.assertEqual(answer["answer"], "no", (answer, evidence))
        self.assertIn("run context unverified", answer["measurement"])

    def test_explicit_run_without_control_refuses(self):
        missing = self.tmp / "missing-control"
        missing.mkdir()
        complete = write_owed(self.tmp / "complete-12", C.PACKAGE_ITEMS)
        answer, evidence = q12(receipt(
            missing, complete, run_id="unknown-run"))
        self.assertEqual(answer["answer"], "no", (answer, evidence))
        self.assertIn("run context unverified", answer["measurement"])


class NumericTrustBoundary(unittest.TestCase):
    """Malformed lengths refuse; they never crash and never pass."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="w39-numeric-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.complete = write_owed(self.tmp / "complete", C.PACKAGE_ITEMS)

    def _answer(self, value):
        return q12({"PACKAGE_COMPLETE": {
            "delivery_folder": str(self.complete),
            "chosen_length_s": value,
            "source": "packaging call resolved answer"}})

    def test_nan_infinity_negative_zero_and_bool_never_pass_or_crash(self):
        for value in (float("nan"), float("inf"), float("-inf"), 1e309,
                      -1, 0, True, False):
            with self.subTest(value=repr(value)):
                answer, evidence = self._answer(value)
                self.assertEqual(answer["answer"], "no", (answer, evidence))
                self.assertIn("run context unverified",
                              answer["measurement"])

    def test_unbound_valid_number_is_never_authority(self):
        answer, evidence = self._answer(60)
        self.assertEqual(answer["answer"], "no", (answer, evidence))
        self.assertEqual(evidence["authority"], "structural-only")
        self.assertIn("structural inspection only", answer["measurement"])


class StructuralOnlyHistory(unittest.TestCase):
    """Legacy records stay readable; they never grant a new completion."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="w39-history-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_complete_legacy_folder_is_reported_but_not_completed(self):
        folder = write_owed(self.tmp / "legacy", C.PACKAGE_ITEMS)
        answer, evidence = q12({"PACKAGE_COMPLETE": {
            "delivery_folder": str(folder)}})
        self.assertEqual(answer["answer"], "no", (answer, evidence))
        self.assertEqual(evidence["authority"], "structural-only")
        self.assertEqual(evidence["items_present"], 12)
        self.assertEqual(evidence["missing_items"], [])
        self.assertIn("structural inspection only", answer["measurement"])


class WelcomeSheetObligations(unittest.TestCase):
    """The REAL DEL-12 deliver path renders the run's owed tuple."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="w39-welcome-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _sheet(self, run):
        item = C.ITEMS_BY_KEY["welcome_sheet"]
        written = ws.produce_delivery(run, item)
        self.assertEqual([p.name for p in written], list(item.files))
        return "\n".join(
            pdf_strings((run / "delivery" / item.files[0]).read_bytes()))

    def test_short_long_and_campaign_sheets_list_exactly_their_items(self):
        """Each family's REAL sheet shows exactly the items that family owes."""
        short = self.tmp / "short-sheet"
        confirm_run(short, length="90 seconds")
        text = self._sheet(short)
        for name in C.ITEMS_BY_KEY["clips"].files:
            self.assertNotIn(name, text)
        for name in C.METHOD_ITEM_FILES[6] + C.AD_CLIPS_ITEM.files:
            self.assertNotIn(name, text)
        self.assertIn("12 - Welcome Sheet.pdf", text)
        info = ws.build_welcome_sheet(
            self.tmp / "short-copy.pdf",
            items=RI.delivery_context(short)["items"])
        self.assertEqual(info["items"], 11)

        long_run = self.tmp / "long-sheet"
        confirm_run(long_run, length="3 minutes + 60s and 90s clips")
        long_text = self._sheet(long_run)
        for name in C.ITEMS_BY_KEY["clips"].files:
            self.assertIn(name, long_text)
        self.assertNotIn("06 - Trailer", long_text)

        campaign = self.tmp / "campaign-sheet"
        confirm_run(campaign, length="3 minutes", purpose=1)
        campaign_text = self._sheet(campaign)
        for name in C.METHOD_ITEM_FILES[6] + C.AD_CLIPS_ITEM.files:
            self.assertIn(name, campaign_text)
        for name in C.ITEMS_BY_KEY["clips"].files:
            self.assertNotIn(name, campaign_text)
        self.assertIn(
            "Two short trailers that send people to the full episode.",
            campaign_text)
        self.assertIn(
            "Two short ad clips that sell your offer on social media.",
            campaign_text)

    def test_missing_authority_refuses_before_write(self):
        missing = self.tmp / "welcome-no-authority"
        missing.mkdir()
        item = C.ITEMS_BY_KEY["welcome_sheet"]
        with self.assertRaises(RI.RunInputError):
            ws.produce_delivery(missing, item)
        self.assertFalse((missing / "delivery").exists())


class RunAliasSelection(unittest.TestCase):
    """One normalized run selection across run_root, run_dir and root.

    The receipt or its own PACKAGE_COMPLETE answer may name the run by any of
    the three aliases. A relative delivery_folder resolves against THAT run --
    never against the current directory -- and the authority lookup uses the
    same normalized root. Distinct paths, missing folders and unproven runs
    still refuse.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="w39-alias-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run = self.tmp / "run"
        self.run_id = confirm_run(
            self.run, length="3 minutes + 60s and 90s clips")
        self.folder = write_owed(
            self.run / "delivery", RI.delivery_context(self.run)["items"])
        self.complete = write_owed(self.tmp / "complete", C.PACKAGE_ITEMS)
        self.elsewhere = self.tmp / "elsewhere"
        self.elsewhere.mkdir()

    def _evaluate(self, receipt_obj):
        """The REAL evaluate() from a directory that holds no delivery."""
        previous = os.getcwd()
        os.chdir(self.elsewhere)
        try:
            return dc.evaluate(receipt_obj)
        finally:
            os.chdir(previous)

    def test_alias_matrix_positive_relative_and_absolute_folder(self):
        run = str(self.run)
        cases = {
            "receipt run_root": ({"run_root": run}, {}),
            "receipt run_dir": ({"run_dir": run}, {}),
            "receipt root": ({"root": run}, {}),
            "answer run_root": ({}, {"run_root": run}),
            "answer run_dir": ({}, {"run_dir": run}),
            "answer root": ({}, {"root": run}),
            "absolute folder": ({"run_dir": run},
                                {"delivery_folder": str(self.folder)}),
        }
        for label, (claim, answer_claim) in cases.items():
            with self.subTest(alias=label):
                answer = {"delivery_folder": "delivery",
                          "run_id": self.run_id}
                answer.update(answer_claim)
                receipt_obj = dict(claim)
                receipt_obj["PACKAGE_COMPLETE"] = answer
                result = self._evaluate(receipt_obj)
                q12 = result["answers"]["PACKAGE_COMPLETE"]
                self.assertEqual(q12["answer"], "yes", (label, q12))
                self.assertEqual(result["evidence"]["authority"],
                                 "resolved-run")
                self.assertEqual(
                    Path(result["evidence"]["folder"]).resolve(),
                    self.folder.resolve())

    def test_alias_conflicts_missing_folder_and_bad_authority_refuse(self):
        run = str(self.run)
        other = self.tmp / "other-run"
        confirm_run(other, length="90 seconds")
        malformed = self.tmp / "malformed-control"
        (malformed / "control").mkdir(parents=True)
        (malformed / "control" / "intake-session.json").write_text(
            "{broken", encoding="utf-8")
        no_control = self.tmp / "no-control"
        no_control.mkdir()

        def receipt_for(claim, answer_claim=None):
            answer = {"delivery_folder": "delivery", "run_id": self.run_id}
            answer.update(answer_claim or {})
            obj = dict(claim)
            obj["PACKAGE_COMPLETE"] = answer
            return obj

        cases = [
            ("conflicting receipt aliases",
             receipt_for({"run_root": run, "run_dir": str(other)}),
             "conflicting run roots"),
            ("conflicting receipt and answer aliases",
             receipt_for({"run_dir": run}, {"run_root": str(other)}),
             "conflicting run roots"),
            ("missing folder still refused",
             receipt_for({"run_dir": run}, {"delivery_folder": "absent"}),
             "delivery folder missing"),
            ("explicit run without control",
             receipt_for({"run_dir": str(no_control)},
                         {"delivery_folder": str(self.complete)}),
             "run context unverified"),
            ("malformed control",
             receipt_for({"run_dir": str(malformed)},
                         {"delivery_folder": str(self.complete)}),
             "run context unverified"),
            ("forged length beside a real run",
             receipt_for({"run_dir": run},
                         {"delivery_folder": str(self.folder),
                          "chosen_length_s": 60}),
             "run context unverified"),
            ("nonexistent run alias",
             receipt_for({"run_dir": str(self.tmp / "absent-run")},
                         {"delivery_folder": str(self.complete)}),
             "run context unverified"),
        ]
        for label, receipt_obj, expected in cases:
            with self.subTest(alias=label):
                result = self._evaluate(receipt_obj)
                q12 = result["answers"]["PACKAGE_COMPLETE"]
                self.assertEqual(q12["answer"], "no", (label, q12))
                self.assertIn(expected, q12["measurement"], label)

    def _absent_username(self):
        """A username with no passwd entry, proven by its own failing lookup."""
        for n in range(1, 100):
            name = "w57-no-home-%d" % n
            try:
                pwd.getpwnam(name)
            except KeyError:
                return name            # control: the lookup that must fail did
        self.fail("could not find a username with no passwd entry")

    def test_unusable_run_paths_refuse_without_raising(self):
        """A NUL or an unresolvable home is a REFUSED claim, never a crash.

        Both are real receipt text, on all three aliases, on the receipt and
        on its PACKAGE_COMPLETE answer. Every one of these twelve calls raised
        ValueError / RuntimeError out of the public ``evaluate()`` before the
        normalization boundary existed; the healthy absolute control in
        ``test_alias_conflicts_missing_folder_and_bad_authority_refuse``
        never raised, so the crash was input-specific, not a broken probe.
        """
        absent = self._absent_username()
        for label, value in (("embedded NUL", "delivery" + "\x00" + "bad"),
                             ("missing home", "~" + absent + "/run")):
            for alias in ("run_root", "run_dir", "root"):
                for where in ("receipt", "answer"):
                    with self.subTest(case=label, alias=alias, where=where):
                        answer = {"delivery_folder": "delivery",
                                  "run_id": self.run_id}
                        receipt_obj = {}
                        if where == "receipt":
                            receipt_obj[alias] = value
                        else:
                            answer[alias] = value
                        receipt_obj["PACKAGE_COMPLETE"] = answer
                        result = self._evaluate(receipt_obj)  # must not raise
                        q12 = result["answers"]["PACKAGE_COMPLETE"]
                        self.assertEqual(q12["answer"], "no", (label, q12))
                        self.assertIn("not a usable path",
                                      q12["measurement"], label)

    def test_equal_aliases_spelled_differently_are_one_root(self):
        """run_root and run_dir naming the same run are ONE root, not a conflict."""
        answer = {"delivery_folder": "delivery", "run_id": self.run_id,
                  "run_dir": str(self.run) + "/."}
        result = self._evaluate({"run_root": str(self.run),
                                 "PACKAGE_COMPLETE": answer})
        q12 = result["answers"]["PACKAGE_COMPLETE"]
        self.assertEqual(q12["answer"], "yes", q12)
        self.assertEqual(result["evidence"]["authority"], "resolved-run")


if __name__ == "__main__":
    unittest.main(verbosity=2)
