#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: CHAPTER GATE  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# The sacred per-contributor chapter floors (PRD §3.5). ONE chapter per
# contributor, measured on the STRIPPED text so a whitespace-padded short
# chapter cannot pass, the contributor-locked title/subtitle carried byte-exact,
# and every non-"N/A" personal story provably PLACED in the artifact.
#
#   AF-AW-CHAP-LEN    — measured stripped word count outside 2,000-3,500
#                       (chapter mode only; self-report ignored, padding inert).
#   AF-AW-VERIFY-BLOCK — the mandatory COMPLETION VERIFICATION block is absent
#                       (chapter mode only).
#   AF-AW-PLACEHOLDER — an unresolved {{..}} / [[..]] / <ALLCAPS> placeholder
#                       survived into the finalized artifact.
#   AF-AW-TITLE-LOCK  — the locked title and/or subtitle (from --title) is not
#                       carried byte-exact (whitespace/case normalized) in the
#                       artifact. A changed subtitle in the body trips this.
#   AF-AW-STORIES     — a non-"N/A" personal-story anchor (from --intake) is not
#                       placed in the artifact.
#
# MODES:  --mode chapter (default) enforces all five. --mode outline enforces
#         placeholder + title-lock + stories (no length band, no verify block),
#         so the same prover proves placement in the OUTLINE and the CHAPTER.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_aw_chapter.py <artifact.md> [--mode chapter|outline]
#        [--title title.json] [--intake intake.json] [--json] | --self-test
# =============================================================================
"""Fail-closed chapter/outline gate for the Anthology Writer (Skill 54)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _aw_common as c  # noqa: E402

AF_CHAP_LEN = "AF-AW-CHAP-LEN"
AF_VERIFY_BLOCK = "AF-AW-VERIFY-BLOCK"
AF_PLACEHOLDER = "AF-AW-PLACEHOLDER"
AF_TITLE_LOCK = "AF-AW-TITLE-LOCK"
AF_STORIES = "AF-AW-STORIES"
AF_OVERRIDE_UNLOGGED = "AF-AW-OVERRIDE-UNLOGGED"
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"


def evaluate(text: str, mode: str = "chapter", title: dict = None, intake: dict = None,
             override: dict = None, brief: dict = None) -> c.Result:
    r = c.Result("prove_aw_chapter")

    if mode == "chapter":
        # DEFAULT band unless a client-exact override wins through the LOGGED,
        # brief-tied channel (fleet law: exact ask wins; an unlogged override
        # fails closed rather than silently swap the SACRED floor).
        cmin, cmax = c.CHAPTER_WORD_MIN, c.CHAPTER_WORD_MAX
        status, reason, applied = c.resolve_band_override(
            override, brief, ("chapter_word_min", "chapter_word_max"))
        if status == "unlogged":
            r.fail(AF_OVERRIDE_UNLOGGED, reason)
        elif status == "applied":
            cmin = applied.get("chapter_word_min", cmin)
            cmax = applied.get("chapter_word_max", cmax)
            r.note("%s — chapter band overridden to %d-%d" % (reason, cmin, cmax))
        words = c.word_count(text)
        if words < cmin or words > cmax:
            r.fail(AF_CHAP_LEN, "measured stripped word count %d outside %d-%d "
                   "(self-reported counts are ignored; padding is inert)"
                   % (words, cmin, cmax))
        else:
            r.note("measured stripped word count %d within %d-%d" % (words, cmin, cmax))
        if c.VERIFY_BLOCK_MARKER not in text:
            r.fail(AF_VERIFY_BLOCK, "mandatory %r block absent" % c.VERIFY_BLOCK_MARKER)
        else:
            r.note("%r block present" % c.VERIFY_BLOCK_MARKER)

    ph = c.unresolved_placeholders(text)
    if ph:
        r.fail(AF_PLACEHOLDER, "unresolved placeholder(s) in the finalized artifact: %s"
               % ", ".join(ph[:6]))
    else:
        r.note("no unresolved placeholders")

    if title is not None:
        for key in ("title", "subtitle"):
            locked = str(title.get(key, "")).strip()
            if not locked:
                r.fail(AF_TITLE_LOCK, "locked %s is missing from title.json" % key)
            elif not c.contains_phrase(text, locked):
                r.fail(AF_TITLE_LOCK, "locked %s %r not carried byte-exact in the %s"
                       % (key, locked, mode))
            else:
                r.note("locked %s carried into the %s" % (key, mode))
    else:
        r.note("title-lock check skipped (no --title supplied)")

    if intake is not None:
        anchors = c.story_phrases(intake)
        if not anchors:
            r.note("no non-N/A personal stories to place")
        for a in anchors:
            if not c.contains_phrase(text, a):
                r.fail(AF_STORIES, "personal-story anchor %r is not placed in the %s"
                       % (a, mode))
        if anchors and r.passed:
            r.note("all %d personal-story anchor(s) placed in the %s" % (len(anchors), mode))
    else:
        r.note("story-placement check skipped (no --intake supplied)")
    return r


def prove(path, mode, title_path, intake_path, override_path=None,
          brief_path=None, as_json=False) -> int:
    title = c.read_json(title_path) if title_path else None
    intake = c.read_json(intake_path) if intake_path else None
    override = c.read_json(override_path) if override_path else None
    # The locked brief the override must cite; defaults to the intake (intake IS
    # the locked brief) when --brief is not passed explicitly.
    brief = c.read_json(brief_path) if brief_path else intake
    return evaluate(c.read_text(path), mode=mode, title=title, intake=intake,
                    override=override, brief=brief).emit(as_json)


def self_test() -> int:
    checks = []
    gtitle = c.read_json(_FIX / "golden" / "title.json")
    gintake = c.read_json(_FIX / "golden" / "intake.json")

    golden = c.read_text(_FIX / "golden" / "chapter.md")
    checks.append(("golden chapter PASS (band + block + lock + stories)",
                   evaluate(golden, "chapter", gtitle, gintake).passed))

    goutline = c.read_text(_FIX / "golden" / "outline.md")
    checks.append(("golden outline PASS (placement in outline too)",
                   evaluate(goutline, "outline", gtitle, gintake).passed))

    short = evaluate(c.read_text(_FIX / "attack" / "chapter_short.md"), "chapter", gtitle, gintake)
    checks.append(("short chapter AUTOFAILs AF-AW-CHAP-LEN",
                   any(code == AF_CHAP_LEN for code, _ in short.violations)))

    pad = evaluate(c.read_text(_FIX / "attack" / "chapter_whitespace_pad.md"), "chapter", gtitle, gintake)
    checks.append(("whitespace-padded chapter STILL AUTOFAILs AF-AW-CHAP-LEN",
                   any(code == AF_CHAP_LEN for code, _ in pad.violations)))

    nover = evaluate(c.read_text(_FIX / "attack" / "chapter_verify_missing.md"), "chapter", gtitle, gintake)
    checks.append(("chapter without completion block AUTOFAILs AF-AW-VERIFY-BLOCK",
                   any(code == AF_VERIFY_BLOCK for code, _ in nover.violations)))

    sub = evaluate(c.read_text(_FIX / "attack" / "chapter_subtitle_changed.md"), "chapter", gtitle, gintake)
    checks.append(("changed-subtitle chapter AUTOFAILs AF-AW-TITLE-LOCK",
                   any(code == AF_TITLE_LOCK for code, _ in sub.violations)))

    drop = evaluate(c.read_text(_FIX / "attack" / "chapter_story_dropped.md"), "chapter", gtitle, gintake)
    checks.append(("dropped-story chapter AUTOFAILs AF-AW-STORIES",
                   any(code == AF_STORIES for code, _ in drop.violations)))

    plc = evaluate(c.read_text(_FIX / "attack" / "chapter_placeholder.md"), "chapter", gtitle, gintake)
    checks.append(("placeholder-leak chapter AUTOFAILs AF-AW-PLACEHOLDER",
                   any(code == AF_PLACEHOLDER for code, _ in plc.violations)))

    # client-exact override: a LOGGED, brief-tied override wins over the default
    # band; an UNLOGGED override (no source/approver/reason/brief_ref, or an
    # untied brief_ref) fails CLOSED rather than silently swap the SACRED floor.
    ref = sorted(c.brief_identity(gintake))[0]
    logged = {"chapter_word_min": 2000, "chapter_word_max": 3600,
              "source": "client-exact-request", "approved_by": "operator",
              "reason": "the contributor asked for up to 3,600 words", "brief_ref": ref}
    checks.append(("logged brief-tied override is honored (default band still passes)",
                   evaluate(golden, "chapter", gtitle, gintake, override=logged, brief=gintake).passed))
    unlogged = {"chapter_word_min": 100, "chapter_word_max": 200}
    un = evaluate(golden, "chapter", gtitle, gintake, override=unlogged, brief=gintake)
    checks.append(("unlogged override AUTOFAILs AF-AW-OVERRIDE-UNLOGGED (fail-closed)",
                   any(code == AF_OVERRIDE_UNLOGGED for code, _ in un.violations)))
    untied = dict(logged, brief_ref="some-other-book")
    ut = evaluate(golden, "chapter", gtitle, gintake, override=untied, brief=gintake)
    checks.append(("override not tied to the locked brief AUTOFAILs AF-AW-OVERRIDE-UNLOGGED",
                   any(code == AF_OVERRIDE_UNLOGGED for code, _ in ut.violations)))
    return c.selftest_report("prove_aw_chapter", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Anthology Writer chapter/outline gate (Skill 54).")
    ap.add_argument("path", nargs="?", help="chapter.md / outline.md to prove")
    ap.add_argument("--mode", choices=["chapter", "outline"], default="chapter")
    ap.add_argument("--title", help="title.json carrying the locked title/subtitle")
    ap.add_argument("--intake", help="intake.json carrying personal_stories")
    ap.add_argument("--band-override", dest="band_override",
                    help="a LOGGED overrides.json declaring a client-exact chapter word "
                         "band (chapter_word_min/chapter_word_max) tied to the locked brief")
    ap.add_argument("--brief", help="the locked brief (intake.json) the override must cite; "
                                    "defaults to --intake")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, args.mode, args.title, args.intake,
                 override_path=args.band_override, brief_path=args.brief, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
