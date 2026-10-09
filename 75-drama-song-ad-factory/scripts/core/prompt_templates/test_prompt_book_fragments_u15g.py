#!/usr/bin/env python3
"""U15g: book and printed-page prompt fragments
(design 20-OPUS-PROMPT-TEMPLATE-SYSTEM, unit table U15g).

Book prompt wording lives in ONE place: the ``BOOK_CLOSED`` /
``BOOK_OPEN_MOTION`` / ``PRINTED_PAGES`` fragments of
``models/minimax-h3.json``. This proves the three acceptance points and the
gate they imply:

  (a) a ``product-book`` spec that does NOT carry the book blocks is REFUSED
      at assembly (the shot type declares ``required_blocks_when_book``) --
      today it silently assembles and PASSes the band;
  (b) a ``product-book`` prompt carries exactly one bracket group and only
      the two moves the shot type allows: ``[Static shot]`` or ``[Push in]``
      (``[Pan left]`` is refused by name);
  (c) the fragments themselves carry the U10 contract lines: spine left,
      right-to-left opening, never mirrored, rotation <= 15 degrees.

Plus the U15g absorb rule in one assertion: the fragments are read through
one loader, never restated.

Stdlib only, offline, no paid calls, no network.

Run: python3 scripts/core/prompt_templates/test_prompt_book_fragments_u15g.py
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_CACHE = os.path.join(CORE, "__pycache__")
if os.path.isdir(_CACHE):
    for _n in os.listdir(_CACHE):
        if _n.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _n))
            except OSError:
                pass

import prompt_templates as PT  # noqa: E402

if not hasattr(PT, "assemble_h3"):
    print("FAIL: U15g needs assemble_h3: %r (base tree)"
          % getattr(PT, "__file__", PT))
    sys.exit(1)

FIX = PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
FAILS = []
H3 = "minimax-h3/image-to-video"
BOOK_SHOT = "product-book"
#: The three fragments the unit names (design U15g).
BOOK_FRAGMENTS = ("BOOK_CLOSED", "BOOK_OPEN_MOTION", "PRINTED_PAGES")

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def _chars():
    return json.loads((FIX / "sample-characters.json").read_text("utf-8"))

def _spec(name):
    return json.loads((FIX / ("%s.json" % name)).read_text("utf-8"))

def _book_spec():
    """The golden product-book spec, fresh for every test."""
    return _spec("product-book-S09")

def _frag():
    return PT.load("model", "minimax-h3")["fragments"]

# ---- (c) the fragments carry the U10 contract lines -----------------------
def test_fragments_carry_the_u10_contract():
    frag = _frag()
    check("the three U15g fragments all exist in minimax-h3.json",
          all(k in frag and frag[k] for k in BOOK_FRAGMENTS),
          [k for k in BOOK_FRAGMENTS if not frag.get(k)])
    closed = frag.get("BOOK_CLOSED", "")
    motion = frag.get("BOOK_OPEN_MOTION", "")
    pages = frag.get("PRINTED_PAGES", "")
    check("(c) BOOK_CLOSED: spine on the left edge",
          "spine is on the left" in closed, closed[:120])
    check("(c) BOOK_CLOSED: never mirrored",
          "never mirrored" in closed, closed[:160])
    check("(c) BOOK_CLOSED: rotation <= fifteen degrees",
          "fifteen degrees" in closed, closed[-120:])
    check("(c) BOOK_OPEN_MOTION: opens from right to left",
          "right to left" in motion, motion[:160])
    check("(c) PRINTED_PAGES: text stays upright, not mirrored",
          "not mirrored" in pages and "upright" in pages, pages[:160])
    check("(c) PRINTED_PAGES: no blank pages (U11 page contract)",
          "no blank pages" in pages, pages[:200])
    # The fragments are the single home: one loader, no second dialect.
    src = open(os.path.join(CORE, "prompt_templates", "prompt_templates.py"),
               encoding="utf-8").read()
    check("the fragments are read through one loader (frag[...]), not "
          "re-spelled as literals in the assembler",
          src.count('frag["BOOK_CLOSED"]') >= 1
          and "The spine is on the left edge of the book" not in src,
          src.count('frag["BOOK_CLOSED"]'))

# ---- (b) the book prompt's camera ---------------------------------------
def test_book_prompt_camera_is_static_or_push_in_only():
    chars = _chars()
    spec = _book_spec()
    prompt, sections = PT.assemble_h3(spec, chars)
    v = PT.check(prompt, sections, model=spec["model"])
    groups = re.findall(r"\[[^\]]*\]", prompt)
    check("the golden book prompt PASSes the band",
          v["verdict"] == "PASS", (v["verdict"], v["reasons"]))
    check("(b) exactly one bracket group in the book prompt",
          len(groups) == 1, groups)
    check("(b) the bracket group is a camera move the shot type allows "
          "([Static shot] or [Push in])",
          groups and groups[0].strip("[]").split(",")[0].strip()
          in [c.strip("[]") for c in
              PT.load("shot_type", BOOK_SHOT)["camera_allowed"]],
          groups)
    # [Push in] is the other allowed move; it must not be refused.
    pushed = copy.deepcopy(spec)
    pushed["camera"] = {"command": "[Push in]",
                        "plain": "The camera pushes in very slowly on the "
                                 "book, no other move."}
    try:
        p2, s2 = PT.assemble_h3(pushed, chars)
        check("(b) [Push in] assembles for product-book", bool(p2), len(p2))
    except PT.PromptTemplateError as e:
        check("(b) [Push in] assembles for product-book", False, str(e))
    # A pan is NOT allowed for a book shot.
    panned = copy.deepcopy(spec)
    panned["camera"] = {"command": "[Pan left]",
                        "plain": "The camera pans left across the book."}
    try:
        PT.assemble_h3(panned, chars)
        check("(b) [Pan left] is refused for product-book", False, "assembled")
    except PT.PromptTemplateError as e:
        check("(b) [Pan left] is refused for product-book",
              e.code == "CAMERA_NOT_ALLOWED_FOR_SHOT_TYPE", str(e))

# ---- (a) a book spec without the fragments is refused --------------------
def test_book_spec_without_the_fragments_is_refused():
    chars = _chars()
    # (a1) no `book` key at all: the shot type demands the block.
    nobook = _book_spec()
    nobook.pop("book", None)
    nobook.pop("pages", None)
    try:
        prompt, sections = PT.assemble_h3(nobook, chars)
        v = PT.check(prompt, sections, model=nobook["model"])
        check("(a) a product-book spec with NO book block is REFUSED",
              False, "assembled %d chars, verdict=%s"
                     % (len(prompt), v["verdict"]))
    except PT.PromptTemplateError as e:
        check("(a) a product-book spec with NO book block is REFUSED",
              e.code == "BOOK_FRAGMENTS_REQUIRED", str(e))
    # (a2) book set to a value the assembler does not know: never silently
    # drop the block.
    badbook = _book_spec()
    badbook["book"] = "half-open"
    try:
        prompt, sections = PT.assemble_h3(badbook, chars)
        check("(a) an unknown `book` value is REFUSED, never dropped",
              False, "assembled %d chars" % len(prompt))
    except PT.PromptTemplateError as e:
        check("(a) an unknown `book` value is REFUSED, never dropped",
              e.code in ("BOOK_FRAGMENTS_REQUIRED", "BOOK_VALUE_INVALID"),
              str(e))
    # (a3) the open book also needs the pages block (shot type declares it).
    nopages = _book_spec()
    nopages.pop("pages", None)
    try:
        prompt, sections = PT.assemble_h3(nopages, chars)
        check("(a) an open book with NO pages block is REFUSED",
              False, "assembled %d chars" % len(prompt))
    except PT.PromptTemplateError as e:
        check("(a) an open book with NO pages block is REFUSED",
              e.code == "BOOK_FRAGMENTS_REQUIRED", str(e))
    # (a4) a NON-book shot type is untouched: dropping `book` from a
    # talking-closeup must still assemble (the gate is per shot type).
    other = _spec("talking-closeup-S07")
    other.pop("book", None)
    other.pop("pages", None)
    try:
        p, s = PT.assemble_h3(other, chars)
        check("(a) a non-book shot type is unaffected by the gate",
              bool(p), len(p))
    except PT.PromptTemplateError as e:
        check("(a) a non-book shot type is unaffected by the gate",
              False, str(e))

# ---- the open book's own sections --------------------------------------
def test_open_book_sections_carry_the_fragments():
    chars = _chars()
    spec = _book_spec()
    prompt, sections = PT.assemble_h3(spec, chars)
    lines = [l for l in prompt.split("\n") if l.startswith("Book orientation")]
    check("the assembled book prompt carries a Book orientation section",
          len(lines) == 1, len(lines))
    body = lines[0] if lines else ""
    check("the Book orientation section carries BOOK_CLOSED",
          _frag()["BOOK_CLOSED"] in body, body[:80])
    check("the Book orientation section carries BOOK_OPEN_MOTION (open)",
          _frag()["BOOK_OPEN_MOTION"] in body, body[:80])
    check("the assembled prompt carries PRINTED_PAGES",
          _frag()["PRINTED_PAGES"] in prompt, prompt[:80])
    # closed book: no open motion, no pages
    closed = _book_spec()
    closed["book"] = "closed"
    closed.pop("pages", None)
    p2, s2 = PT.assemble_h3(closed, chars)
    body2 = [l for l in p2.split("\n") if l.startswith("Book orientation")][0]
    check("a CLOSED book carries BOOK_CLOSED but not the open motion",
          _frag()["BOOK_CLOSED"] in body2
          and _frag()["BOOK_OPEN_MOTION"] not in body2, body2[:80])
    check("a CLOSED book carries no printed-pages block",
          _frag()["PRINTED_PAGES"] not in p2, "")

# ---- the Kling path obeys the same gate ---------------------------------
def test_kling_book_path_obeys_the_same_gate():
    chars = _chars()
    kling = PT.load("model", "kling-video")
    model = kling["applies_to"][0]
    nobook = _book_spec()
    nobook["model"] = model
    nobook.pop("book", None)
    nobook.pop("pages", None)
    try:
        p, s = PT.assemble_kling_video(nobook, chars)
        check("a Kling product-book without the book block is REFUSED",
              False, "assembled %d chars" % len(p))
    except PT.PromptTemplateError as e:
        check("a Kling product-book without the book block is REFUSED",
              e.code == "BOOK_FRAGMENTS_REQUIRED", str(e))
    good = _book_spec()
    good["model"] = model
    try:
        p, s = PT.assemble_kling_video(good, chars)
        check("a Kling product-book with the fragments assembles",
              bool(p) and _frag()["BOOK_CLOSED"] in p, len(p))
        check("the Kling book prompt carries no bracket syntax",
              "[" not in p, p[:120])
    except PT.PromptTemplateError as e:
        check("a Kling product-book with the fragments assembles",
              False, str(e))

def main():
    test_fragments_carry_the_u10_contract()
    test_book_prompt_camera_is_static_or_push_in_only()
    test_book_spec_without_the_fragments_is_refused()
    test_open_book_sections_carry_the_fragments()
    test_kling_book_path_obeys_the_same_gate()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS: U15g book fragments, one home, refused when absent.")
    return 0

if __name__ == "__main__":
    sys.exit(main())