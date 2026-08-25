#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: PERSONAL-STORY PLACEMENT GATE (fail-closed)
# -----------------------------------------------------------------------------
# The outline prompt's "we must use it for sure" mandate as code: for each non-N/A
# personal story, its NORMALIZED key phrase must be present in BOTH the approved
# outline AND the manuscript. Missing from either = AF-BK-STORIES (story quoted).
#
# Stories come from run/stories.json: [{id, chapter, key_phrase, text}, ...].
# Normalization (lowercase / strip punctuation / collapse whitespace) tolerates
# markdown + curly quotes so a faithfully-placed story still matches.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_stories.py --stories <stories.json> --outline <APPROVED-OUTLINE.md>
#            --manuscript <manuscript.md> [--json] | --self-test
# =============================================================================
"""Fail-closed personal-story placement gate (Skill 53)."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_STORIES = "AF-BK-STORIES"

# conventional intake location relative to the stories.json parent (a run dir)
_INTAKE_CANDIDATES = ("intake.json", "../intake.json")


def evaluate(stories, outline_text: str, manuscript_text: str) -> c.Result:
    r = c.Result("prove_bw_stories")
    if not isinstance(stories, list):
        r.fail(AF_STORIES, "stories payload is not a JSON list")
        return r
    n_outline = c.normalize_phrase(outline_text)
    n_manu = c.normalize_phrase(manuscript_text)
    checked = 0
    for st in stories:
        if not isinstance(st, dict):
            continue
        key = st.get("key_phrase") or st.get("text") or ""
        sid = st.get("id", "?")
        if c.is_na(key) or not c.is_present(key):
            r.note("story %s is N/A — no placement required" % sid)
            continue
        checked += 1
        nkey = c.normalize_phrase(key)
        in_outline = nkey in n_outline
        in_manu = nkey in n_manu
        if not in_outline:
            r.fail(AF_STORIES, "story %s key phrase not in the approved OUTLINE: %r" % (sid, key))
        if not in_manu:
            r.fail(AF_STORIES, "story %s key phrase not in the MANUSCRIPT: %r" % (sid, key))
        if in_outline and in_manu:
            r.note("story %s placed in outline + manuscript" % sid)
    if checked == 0:
        r.fail(AF_STORIES, "no non-N/A story placed: %d story entry(s) in the intake declare a "
               "non-N/A key_phrase but ZERO were checked (fail-closed — an empty stories list "
               "cannot prove placement)" % (len(stories),))
    return r


def _load_intake(stories_path, intake_flag=None):
    """Best-effort intake load for the zero-checked-stories cross-check. Returns
    (intake_obj_or_None)."""
    candidates = []
    if intake_flag:
        candidates.append(Path(intake_flag))
    else:
        sp = Path(stories_path)
        base = sp.parent if sp.parent.name != "" else Path(".")
        for cand in _INTAKE_CANDIDATES:
            p = (base / cand).resolve()
            candidates.append(p)
    for p in candidates:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def _intake_declares_story(intake) -> bool:
    """True when any book_stories entry carries a non-N/A key_phrase."""
    if not isinstance(intake, dict):
        return False
    entries = intake.get("book_stories")
    if isinstance(entries, dict):
        entries = list(entries.values())
    if not isinstance(entries, list):
        return False
    for e in entries:
        key = ""
        if isinstance(e, dict):
            key = e.get("key_phrase") or e.get("text") or ""
        elif isinstance(e, str):
            key = e
        if c.is_present(key) and not c.is_na(key):
            return True
    return False


def prove(stories_path, outline_path, manuscript_path, as_json=False,
          intake=None) -> int:
    stories = c.read_json(stories_path)
    outline = c.read_text(outline_path)
    manuscript = c.read_text(manuscript_path)
    r = evaluate(stories, outline, manuscript)
    # fail-closed belt: when the prover checked ZERO non-N/A stories, cross-check the
    # intake. If the intake declares a real story but none was checked, that is a
    # silent drop — autofail. If no intake is reachable we keep current behavior and
    # log a warning note.
    checked = sum(1 for st in (stories or [])
                  if isinstance(st, dict)
                  and c.is_present(st.get("key_phrase") or st.get("text") or "")
                  and not c.is_na(st.get("key_phrase") or st.get("text") or ""))
    if checked == 0:
        intake = intake if intake is not None else _load_intake(stories_path)
        if intake is None:
            r.note("WARNING: zero non-N/A stories checked and no intake.json found at a "
                   "conventional path — pass --intake to make this check binding")
        elif _intake_declares_story(intake):
            r.fail(AF_STORIES, "the intake declares at least one non-N/A personal story "
                   "but ZERO stories were checked against outline+manuscript (silent drop)")
    return r.emit(as_json)


def self_test() -> int:
    stories = [
        {"id": "STORY-A", "chapter": 1,
         "key_phrase": "rewrote a junior engineer's pull request at 2 a.m."},
        {"id": "STORY-B", "chapter": 6,
         "key_phrase": "handed the launch decision to my team and left the office at five"},
        {"id": "STORY-C", "chapter": 0, "key_phrase": "N/A"},
    ]
    outline = ("Ch1 beat: the night I **rewrote a junior engineer's pull request at 2 a.m.**\n"
               "Ch6 beat: when I finally handed the launch decision to my team and left the "
               "office at five, everything changed.\n")
    manuscript = ("# Chapter 1\nIn my third week I rewrote a junior engineer's pull request at "
                  "2 a.m.\n# Chapter 6\nWhen I handed the launch decision to my team and left the "
                  "office at five, I sat in my car.\n")
    checks = []
    checks.append(("both placed stories PASS (N/A skipped)",
                   evaluate(stories, outline, manuscript).passed))
    # drop story A from the manuscript
    manu_missing = manuscript.replace("rewrote a junior engineer's pull request at 2 a.m.", "did some work")
    res = evaluate(stories, outline, manu_missing)
    checks.append(("story dropped from manuscript AUTOFAILs AF-BK-STORIES",
                   any(cd == AF_STORIES for cd, _ in res.violations)))
    # drop story B from the outline
    out_missing = outline.replace("handed the launch decision to my team and left the office at five",
                                  "made a decision")
    res2 = evaluate(stories, out_missing, manuscript)
    checks.append(("story dropped from outline AUTOFAILs AF-BK-STORIES",
                   any(cd == AF_STORIES for cd, _ in res2.violations)))
    return c.selftest_report("prove_bw_stories", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer personal-story placement gate (Skill 53).")
    ap.add_argument("--stories", help="run/stories.json")
    ap.add_argument("--outline", help="approved outline .md")
    ap.add_argument("--manuscript", help="assembled manuscript .md (all chapters)")
    ap.add_argument("--intake", help="intake.json (optional; enables the zero-checked-stories "
                    "cross-check when stories.json's sibling intake is not reachable)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (args.stories and args.outline and args.manuscript):
        ap.error("--stories, --outline and --manuscript are required (or use --self-test)")
    return prove(args.stories, args.outline, args.manuscript, as_json=args.json,
                 intake=json.loads(Path(args.intake).read_text(encoding="utf-8"))
                 if args.intake else None)


if __name__ == "__main__":
    sys.exit(main())
