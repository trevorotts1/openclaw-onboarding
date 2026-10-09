#!/usr/bin/env python3
"""FU-U11 D1: printed pages, the plan hash, the card block and the excerpt seam.

Proves, behaviourally, the four cases the unit brief names:

  (a) a WHITE-PAGE fixture FAILs BOOK_BLANK_PAGES and a PRINTED-PAGE fixture
      PASSes the same check on the same code path;
  (b) a book video job with no approved plan hash is REFUSED (the plan-hash
      requirement U10 left dormant is ACTIVATED here, after U11's producer);
  (c) a changed prompt changes the hash and is refused until re-approved;
  (d) the client excerpt is NEVER sent to a video model: the assembled H3
      prompt carries no excerpt text, because the overlay is posted as DATA.

(d) asserts the SEAM now that U9 has landed on main: captions_burn.py is
importable, entry ``overlay_excerpt`` and hook
``final_assembler.captions_burn.overlay_excerpt`` exist, and the call site
returns the PENDING row when the artifact is absent and the burn hand-off
row when it is present. The excerpt still never reaches a video prompt --
it is posted as DATA, and the burn receipt claims no frame it did not draw.

This is the RECONCILED suite (FU-U11 halves): the 999 form is the base, with
the onboarding half's unique checks ported in -- the second fixture family,
the single-blank chapter-break rule, the carried-hash-no-approval refusal,
approval-field exclusion and key-order stability, the template-assembled H3
boundary, pages_block, and the excerpt_lines package surface.

Run: HOME=$(mktemp -d) python3 scripts/core/book_shot/test_book_pages_d1.py
stdlib + cv2/numpy (PREREQS python-mediapipe); no network, no spend.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import book_shot as BS                                    # noqa: E402 (package)
import book_shot.book_shot as BSM                         # noqa: E402 (module)
from book_shot.fixtures import build_fixtures as FIX       # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _run_all():
    """Run every D1 case once, into the module's FAILS list."""
    import shutil
    TMP = tempfile.mkdtemp(prefix="book-pages-d1-")
    try:
        _cases(TMP)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


def test_book_pages_d1():
    """pytest entry point: run the D1 cases (check() records, never raises)."""
    _run_all()


def test_no_failed_checks():
    """pytest guard: check() records failures, it does not raise them.

    Without this a bare ``pytest`` run would report green on a red suite.
    The direct runner gets the same signal through main()'s exit code.
    """
    assert not FAILS, "failed checks: %s" % FAILS


def main():
    _run_all()
    print("")
    if FAILS:
        print("FAILED %d: %s" % (len(FAILS), "; ".join(FAILS)))
        return 1
    print("all checks pass")
    return 0


def _cases(TMP):
    import cv2
    import numpy as np
    FX = FIX.build(TMP)

    # ---------------------------------------------------------------- (a) --
    # A white-page fixture against a printed-page fixture, same checker.
    printed = FIX.pages_frame(cv2, np, "printed")
    white = FIX.pages_frame(cv2, np, "white")
    ok = BS.check_pages(printed)
    bad = BS.check_pages(white)
    check("(a) a printed-page frame PASSes check_pages",
          ok["verdict"] == "PASS", ok)
    check("(a) a white-page frame FAILs with BOOK_BLANK_PAGES",
          bad["verdict"] == "FAIL" and bad["reason_code"] == "BOOK_BLANK_PAGES",
          bad)
    check("(a) the blank-page verdict names the measured blank fraction",
          (bad.get("checks") or {}).get("pages", {}).get("empty_cells", 0)
          > (ok.get("checks") or {}).get("pages", {}).get("empty_cells", 0),
          bad)

    # A clip whose OPEN FRAMES are mostly white fails on the sampled window,
    # not only on a single handed-in image.
    open_frames = [FX["paths"]["cover_frame"]] if "cover_frame" in FX["paths"] \
        else [printed]
    open_frames = open_frames + [white, white, white]
    # (the white frames sit AFTER the closed cover, i.e. in the open window)
    seq = BS.check_pages_sequence(open_frames)
    check("(a) more than one blank page among the open frames FAILs",
          seq["verdict"] == "FAIL" and seq["reason_code"] == "BOOK_BLANK_PAGES",
          seq)
    seq_ok = BS.check_pages_sequence([printed, printed, printed])
    check("(a) all-printed open frames PASS the sequence check",
          seq_ok["verdict"] == "PASS", seq_ok)
    # ONE blank open frame may be a chapter break (onboarding half's rule).
    one_blank = BS.check_pages_sequence([printed, white, printed])
    check("(a) a single blank open frame does not fail the sequence",
          one_blank["verdict"] == "PASS", one_blank)
    # The onboarding half's independent fixture family must sort the same
    # way: the grid check is proven on a generator it was not calibrated on.
    ob_printed = FIX.open_book_frames(cv2, np, printed=True)
    ob_white = FIX.open_book_frames(cv2, np, printed=False)
    check("(a) the onboarding printed-page fixture PASSes the same check",
          all(BS.check_pages(f)["verdict"] == "PASS" for f in ob_printed),
          [BS.check_pages(f)["verdict"] for f in ob_printed])
    check("(a) the onboarding white-page fixture FAILs BOOK_BLANK_PAGES",
          all(BS.check_pages(f)["reason_code"] == "BOOK_BLANK_PAGES"
              for f in ob_white),
          [BS.check_pages(f)["reason_code"] for f in ob_white])

    # ---------------------------------------------------------------- (b) --
    # A book video job with no approved plan hash is refused.
    KD = _kie()
    spec = BS.plan_spec({"book_title": FX["title"], "pages": "texture"})
    sha = BS.plan_sha256(spec)
    frame_with_cover = FX["paths"]["front_frame"]
    base = {"shot_kind": "book", "request_kind": "video",
            "book_start_frame": frame_with_cover,
            "book_cover_path": FX["paths"]["cover"]}
    no_hash = KD.book_shot_refusal("kling-3.0/video", dict(base))
    check("(b) a book job with NO book_plan_sha256 is REFUSED",
          no_hash is not None
          and no_hash["reason_code"] == "BOOK_PLAN_NOT_APPROVED", no_hash)
    matching = KD.book_shot_refusal(
        "kling-3.0/video",
        dict(base, book_plan_sha256=sha, approved_book_plan_sha256=sha))
    check("(b) a matching approved plan hash passes",
          matching is None, matching)
    # (onboarding half) a carried hash with no approval is refused too.
    unapproved = KD.book_shot_refusal(
        "kling-3.0/video",
        dict(base, book_plan_sha256=sha,
             book_start_frame=frame_with_cover,
             book_cover_path=FX["paths"]["cover"]))
    check("(b) a carried hash with no approval is REFUSED",
          unapproved is not None
          and unapproved["reason_code"] == "BOOK_PLAN_NOT_APPROVED",
          unapproved)

    # ---------------------------------------------------------------- (c) --
    # A changed prompt changes the hash and is refused until re-approved.
    changed = BS.plan_spec({"book_title": FX["title"], "pages": "texture",
                            "subject": "A different subject line"})
    sha2 = BS.plan_sha256(changed)
    check("(c) a changed prompt changes the plan hash", sha != sha2,
          (sha, sha2))
    stale = KD.book_shot_refusal(
        "kling-3.0/video",
        dict(base, book_plan_sha256=sha2, approved_book_plan_sha256=sha))
    check("(c) the changed prompt is REFUSED until re-approved",
          stale is not None
          and stale["reason_code"] == "BOOK_PLAN_NOT_APPROVED", stale)
    reapproved = KD.book_shot_refusal(
        "kling-3.0/video",
        dict(base, book_plan_sha256=sha2, approved_book_plan_sha256=sha2))
    check("(c) re-approving the new hash lets it through",
          reapproved is None, reapproved)
    # (onboarding half) the approval fields never feed the hash, and key
    # order never moves it: approving a plan cannot chase its own hash.
    approved_carrier = dict(spec, approved_book_plan_sha256=sha,
                            approved_at="2026-10-09")
    check("(c) approval fields are excluded from the plan hash",
          BS.plan_sha256(approved_carrier) == sha,
          BS.plan_sha256(approved_carrier)[:12])
    check("(c) the hash is stable across key order",
          BS.plan_sha256({"a": 1, "b": 2}) == BS.plan_sha256({"b": 2, "a": 1}))

    # ---------------------------------------------------------------- (d) --
    # The excerpt is DATA, never prompt text.
    EXCERPT = ["The kitchen was never empty on a Sunday.",
               "She kept the recipe cards in a tin.",
               "Every table remembers who sat there."]
    out = BS.excerpt_overlay(EXCERPT, provenance="provided")
    check("(d) the overlay carries the excerpt as DATA",
          out["overlay"]["lines"] == EXCERPT, out)
    check("(d) the overlay is marked data-only, never prompt",
          out.get("to_video_model") is False, out)
    spec_d = BS.plan_spec({"book_title": FX["title"], "pages": "texture",
                           "excerpt": EXCERPT})
    try:
        blocks = BS.prompt_blocks(spec_d, "flip")
        prompt = BS.build_prompt(spec_d, "flip", blocks)
    except Exception as exc:                              # noqa: BLE001
        prompt = ""
        check("(d) the book prompt still assembles with an excerpt present",
              False, exc)
    # Every DISTINCTIVE word of the excerpt must be absent. Common words
    # ("the", "she") live in every prompt already, so they are not evidence;
    # a distinctive word appearing would be real leakage.
    STOP = {"the", "a", "an", "she", "he", "it", "was", "were", "on", "in",
            "and", "or", "to", "of", "for", "her", "his", "every", "never",
            "who", "there", "that", "they", "their", "kept"}
    words = {w.strip(".,").lower() for ln in EXCERPT for w in ln.split()}
    distinctive = words - STOP
    pwords = set(re.findall(r"[a-z']+", prompt.lower()))
    leaked = sorted(w for w in distinctive if w and w in pwords)
    check("(d) the assembled prompt NEVER carries excerpt words",
          not leaked, leaked)
    check("(d) no whole excerpt line appears in the prompt",
          not [ln for ln in EXCERPT if ln.lower() in prompt.lower()], prompt)
    check("(d) the prompt names no overlay text at all",
          "overlay" not in prompt.lower(), prompt)

    # The U9 boundary: one named hook, and it does not burn anything itself.
    hook = BS.EXCERPT_OVERLAY_HOOK
    check("(d) exactly one overlay hook is named, for U9",
          hook == "final_assembler.captions_burn.overlay_excerpt", hook)
    # An over-cap excerpt fails closed (never truncated, never rewritten).
    try:
        BS.normalize_excerpt(EXCERPT + ["a fourth line"])
        check("(d) an over-cap excerpt raises (fail closed)", False)
    except BS.BookShotError as exc:
        check("(d) an over-cap excerpt raises (fail closed)",
              exc.code == BS.BOOK_EXCERPT_INVALID, exc)
    # The onboarding half proved the same boundary one layer up, through the
    # U15b template assembler: the assembled H3 prompt carries the
    # PRINTED_PAGES fragment and never an excerpt word.
    import prompt_templates as PT
    spec_pt = (PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
               / "product-book-S09.json")
    chars_pt = (PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
                / "sample-characters.json")
    if spec_pt.is_file() and chars_pt.is_file():
        prompt_pt, sections = PT.assemble_h3(
            json.loads(spec_pt.read_text("utf-8")),
            json.loads(chars_pt.read_text("utf-8")))
        check("(d) the template-assembled H3 prompt carries PRINTED_PAGES",
              "printed" in prompt_pt.lower() and "pages" in sections,
              sorted(sections))
        # The word test would be a false claim here: the fixture subject is
        # literally "...on a light oak kitchen table" and the PRINTED_PAGES
        # fragment itself says "no blank pages and no large empty white
        # areas", so "kitchen", "table" and "empty" are authored template
        # words that collide with the excerpt BY CHANCE. The evidence the
        # boundary rests on is structural: the template knows no excerpt key,
        # and no whole excerpt line ever appears.
        check("(d) the H3 spec carries no excerpt key at all",
              "excerpt" not in json.loads(spec_pt.read_text("utf-8")),
              sorted(json.loads(spec_pt.read_text("utf-8"))))
        check("(d) no whole excerpt line appears in the template prompt",
              not [ln for ln in EXCERPT
                   if ln.lower() in prompt_pt.lower()], "")
        # pages_block (onboarding half) quotes that same fragment verbatim.
        check("(d) pages_block consumes the template, never authors text",
              (BS.pages_block({"pages": "texture"}) or "") in prompt_pt,
              BS.pages_block({"pages": "texture"}))
    else:
        check("(d) the product-book H3 fixture exists", False, str(spec_pt))
    check("(d) pages_block is silent unless pages==texture",
          BS.pages_block({"pages": "plain"}) is None
          and BS.pages_block({}) is None, BS.pages_block({}))

    # ------------------------------------------------- intake excerpt ------
    from intake_book import book as IB
    brief = {"book_title": "T", "author": "A", "buy_link": "https://x.example/b",
             "audience": "a", "pain_or_transformation": "p"}
    with_ex = dict(brief, excerpt_lines=EXCERPT)
    r1 = IB.evaluate(with_ex)
    check("intake: a supplied excerpt is carried with provenance 'provided'",
          r1["summary"].get("excerpt_lines") == EXCERPT
          and r1["summary"].get("excerpt_provenance") == "provided", r1)
    r2 = IB.evaluate(dict(brief))
    check("intake: no excerpt -> no excerpt key at all",
          "excerpt_lines" not in (r2.get("summary") or {}), r2.get("summary"))
    r3 = IB.evaluate(dict(brief, excerpt_lines=["one", "two", "three", "four"]))
    check("intake: more than 3 excerpt lines is REFUSED",
          r3["outcome"] == "rejected"
          and r3["reason_code"] == "book_excerpt_invalid", r3)
    r4 = IB.evaluate(dict(brief, excerpt_lines=["The kitchn was empty"]))
    check("intake: a misspelled excerpt is REFUSED",
          r4["outcome"] == "rejected"
          and r4["reason_code"] == "book_excerpt_invalid", r4)
    check("intake: a refused excerpt never reaches the questions",
          r4["questions"] == [], r4["questions"])
    try:
        BS.normalize_excerpt(["The kitchn was empty"])
        check("book_shot: a misspelled excerpt raises", False)
    except BS.BookShotError as exc:
        check("book_shot: a misspelled excerpt raises",
              exc.code == BS.BOOK_EXCERPT_INVALID, exc)
    # The onboarding half's read-only package surface (intake_book.__init__
    # imports it) reports errors instead of raising.
    ex_view = IB.excerpt_lines(dict(brief, excerpt_lines=EXCERPT))
    check("compat: excerpt_lines returns (lines, provided, no errors)",
          ex_view == (EXCERPT, "provided", []), ex_view)
    ex_missing = IB.excerpt_lines(dict(brief))
    check("compat: excerpt_lines with no excerpt is ([], missing, [])",
          ex_missing == ([], "missing", []), ex_missing)
    ex_bad = IB.excerpt_lines(dict(brief, excerpt_lines=["one", "two",
                                                         "three", "four"]))
    check("compat: excerpt_lines over the cap reports the error",
          ex_bad[0] == [] and ex_bad[1] == "missing" and ex_bad[2],
          ex_bad)

    # ------------------------------------------- card approval block -------
    plan = BS.plan_spec({"book_title": FX["title"], "author": FX["author"],
                         "pages": "texture", "excerpt": EXCERPT[:2]})
    block = BS.plan_card_block(plan, ["No buy link supplied."])
    text = "\n".join(block)
    check("card: the block shows the plan hash",
          BS.plan_sha256(plan) in text, text)
    check("card: the block shows the title and the author",
          FX["title"] in text and FX["author"] in text, text)
    check("card: the block shows the excerpt as client-supplied",
          "client-supplied" in text, text)
    check("card: the block carries the notice it was given",
          "No buy link supplied." in text, text)
    check("card: the block offers NO new choice (no numbered options)",
          not re.search(r"^\s*\d+\.\s", text, re.M), text)
    check("card: the block says the excerpt never reaches a video model",
          "never sent to the video model" in text, text)
    check("card: a non-book plan adds no block",
          BS.plan_card_block(None) == [], BS.plan_card_block(None))

    import importlib
    CR = importlib.import_module("catalog_calculator.card_render")
    card = {"length": "60 seconds", "book_plan": plan}
    rendered, _ = CR.render(card, None)
    check("card: the calculator card carries the book block",
          "Book shots" in rendered and BS.plan_sha256(plan) in rendered,
          rendered[-400:])
    plain, _ = CR.render({"length": "60 seconds"}, None)
    check("card: a non-book card is unchanged (no book block)",
          "Book shots" not in plain, plain[-200:])

    IC = importlib.import_module("choice_card.intake_card.intake_card")
    icheck = IC.render_card(None, book_plan=plan)
    check("card: the intake card carries the book block",
          "Book shots" in icheck and BS.plan_sha256(plan) in icheck, "")
    plain_ic = IC.render_card(None)
    check("card: a non-book intake card is unchanged",
          "Book shots" not in plain_ic, "")
    msgs = IC.render_messages(None, book_plan=plan)
    check("card: the intake messages carry the block and stay under the limit",
          any("Book shots" in m for m in msgs)
          and all(len(m) <= IC.TELEGRAM_LIMIT for m in msgs),
          [len(m) for m in msgs])
    # The block is an approval, not a question: the question count and the
    # answer instruction are IDENTICAL with and without it.
    with_b = "\n\n".join(IC.render_messages(None, book_plan=plan))
    without_b = "\n\n".join(IC.render_messages(None))
    import re as _re
    q_with = len(_re.findall(r"Question \d+ of \d+", with_b))
    q_without = len(_re.findall(r"Question \d+ of \d+", without_b))
    check("card: the block never adds a question",
          q_with == q_without and q_with == len(IC.QUESTIONS),
          (q_with, q_without, len(IC.QUESTIONS)))
    check("card: the closing answer line is unchanged",
          IC.CLOSING_LINE in with_b and IC.CLOSING_LINE in without_b,
          "")

    # -------------------------------------- the U9 hook call site ----------
    # Item 6 boundary: exactly ONE burn site in this codebase and it is U9's.
    # U9 landed with train 2.7.33, so this asserts the SEAM -- the module is
    # importable, the entry point and hook string exist, the call site
    # reports the hand-off -- never the artifact's absence.
    import glob
    import importlib
    core = os.path.dirname(HERE)
    burns = sorted(os.path.relpath(p, core) for p in
                   glob.glob(os.path.join(core, "**", "*.py"), recursive=True)
                   if "captions_burn" in os.path.basename(p))
    check("U9: the captions_burn artifact lives at final_assembler/captions_burn.py",
          [p for p in burns if os.path.basename(p) == "captions_burn.py"]
          == [os.path.join("final_assembler", "captions_burn.py")], burns)
    CB = importlib.import_module("final_assembler.captions_burn")
    check("U9: captions_burn is importable from the skill root",
          getattr(CB, "TOOL_NAME", None) == "captions_burn", CB)
    check("U9: entry point overlay_excerpt exists",
          callable(getattr(CB, "overlay_excerpt", None)), burns)
    check("U9: hook string is final_assembler.captions_burn.overlay_excerpt",
          CB.EXCERPT_OVERLAY_HOOK
          == "final_assembler.captions_burn.overlay_excerpt"
          and CB.ENTRY == "overlay_excerpt",
          getattr(CB, "EXCERPT_OVERLAY_HOOK", None))
    # ...and no SECOND burn module was smuggled in under another name. A burn
    # module SPEAKS of burning: it defines an overlay_excerpt/burn entry point.
    # captions_burn.py is the one allowed owner of that entry point; every
    # other module that grew one is a violation.
    # (master_provenance.py merely BANS caption writers, so it is not one.)
    burners = []
    for p in glob.glob(os.path.join(core, "**", "*.py"), recursive=True):
        if os.path.basename(p).startswith("test_"):
            continue
        if os.path.basename(p) == "captions_burn.py":
            continue
        try:
            src = open(p, encoding="utf-8").read()
        except OSError:
            continue
        if re.search(r"^def (overlay_excerpt|burn_captions|burn_excerpt)\b",
                     src, re.M):
            burners.append(os.path.relpath(p, core))
    check("U9: no module outside captions_burn.py defines a burn entry point",
          burners == [], burners)
    AS = importlib.import_module("final_assembler.assembler")
    # The PENDING half of the seam's contract, with the artifact on disk: the
    # same function, same branch, only the artifact probe says absent. The
    # tree itself is never mutated.
    _real_isfile = os.path.isfile

    def _absent(path, _real=_real_isfile):
        if os.path.basename(path) == "captions_burn.py":
            return False
        return _real(path)

    os.path.isfile = _absent
    try:
        row_pending = AS.excerpt_overlay_stage(
            {"excerpt_overlay": {"lines": EXCERPT, "provenance": "provided"}})
    finally:
        os.path.isfile = _real_isfile
    check("U9: with the artifact absent the call site reports PENDING",
          row_pending["pending"] is True
          and row_pending["reason_code"] == "BOOK_OVERLAY_UNAVAILABLE"
          and row_pending["rows"][0]["hook"]
          == "captions_burn.overlay_excerpt"
          and row_pending["rows"][0]["burned"] is False
          and row_pending["rows"][0]["artifact_present"] is False,
          row_pending)
    # The burn half, with the real artifact on disk.
    row_burn = AS.excerpt_overlay_stage(
        {"excerpt_overlay": {"lines": EXCERPT, "provenance": "provided"}})
    check("U9: with captions_burn.py present the call site hands off the burn",
          row_burn["pending"] is False
          and row_burn["reason_code"] is None
          and row_burn["rows"][0]["hook"] == "captions_burn.overlay_excerpt"
          and row_burn["rows"][0]["burned"] is True
          and row_burn["rows"][0]["lines"] == len(EXCERPT),
          row_burn)
    receipt = CB.overlay_excerpt(EXCERPT, provenance="provided")
    check("U9: overlay_excerpt plans the burn and never claims it burned",
          receipt.get("ok") is True
          and receipt.get("planned") is True
          and receipt.get("burned") is False
          and receipt.get("hook")
          == "final_assembler.captions_burn.overlay_excerpt"
          and receipt.get("lines") == EXCERPT, receipt)
    check("U9: no excerpt -> no overlay row at all",
          AS.excerpt_overlay_stage({}) == {"rows": [], "pending": False,
                                           "reason_code": None},
          AS.excerpt_overlay_stage({}))
    # The overlay is DATA: it rides the plan under its own key and is never
    # read when the video prompt is assembled.
    plan_d = BS.plan_spec({"book_title": FX["title"], "pages": "texture",
                           "excerpt": EXCERPT})
    prompt_d = BS.build_prompt(plan_d, "flip")
    check("U9: the video prompt never reads the overlay key",
          "excerpt_overlay" not in prompt_d and "overlay" not in prompt_d.lower(),
          prompt_d)


def _kie():
    import importlib
    return importlib.import_module("kie_dispatch.kie_dispatch")


if __name__ == "__main__":
    raise SystemExit(main())
