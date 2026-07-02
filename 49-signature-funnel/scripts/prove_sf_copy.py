#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_copy.py — fail-closed deterministic prover for the SACRED 12-section
Trevor Otts Hero funnel copy contract (Skill 49 Signature Funnel).

WHAT IT DOES
------------
Loads the SACRED structure ledger (../structure/funnel_structure.json) and enforces
EVERY section name + char/word band in it against a funnel COPY ledger (the per-page
sections emitted by the Signature Funnel copywriter). A single violation is fail-closed:
the prover prints the named AF-FUN-* code(s) and sys.exit(2). A violating funnel is NOT
run, NOT rendered, NOT built.

The bands are read out of the ledger contract, never hard-coded here. Section names +
bands are reproduced verbatim from SOURCE-FRAMEWORK.md (12-section IP) and
IMPROVED-FRAMEWORK-v2.md Part 5 (Thank-You). Six page profiles: main, upsell, downsell,
upsell-2, downsell-2, thank-you (+ checkout microcopy, which is not 12-section gated).

STRIPPED-LENGTH TEETH (cited)
-----------------------------
The "whitespace can never satisfy a content band" teeth are cloned from the deterministic
stripped-length gate in the presentations build_deck.py (build_deck.py:1082 `if not
prompt.strip(): raise ...`; build_deck.py:1089 `length = len(prompt.strip())`). Every
char band here measures len(str(value).strip()); every word band measures
len(str(value).split()). ANY self-reported count field in the ledger is IGNORED — the
prover always re-measures the actual text.

stdlib only. Exit 0 = pass, exit 2 = contract violation, exit 3 = usage / fail-closed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3


# ---------------------------------------------------------------------------
# Stripped-length teeth — CLONE of build_deck.py:1082-1089.
# ---------------------------------------------------------------------------
def _slen(value: Any) -> int:
    """NON-WHITESPACE length. Padding with spaces/newlines can never satisfy a band."""
    return len(str(value).strip())


def _wcount(value: Any) -> int:
    """Whitespace-delimited word count of the stripped text."""
    return len(str(value).split())


def _norm(value: Any) -> str:
    """Casefold, collapse whitespace, normalize curly apostrophes/quotes to straight."""
    s = str(value)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(s.casefold().split())


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _has_cta(sec: Dict[str, Any]) -> bool:
    """A labeled CTA is present when the section carries a non-empty `cta` field OR the
    copy embeds a 'CTA:' label (the source's 'label the CTA button section' convention)."""
    if _nonempty(sec.get("cta")):
        return True
    return "cta:" in _norm(sec.get("copy", ""))


def _has_cta_button(sec: Dict[str, Any]) -> bool:
    return sec.get("has_cta_button") is True or bool(sec.get("cta_button"))


def _step_text(step: Any) -> str:
    if isinstance(step, str):
        return step
    if isinstance(step, dict):
        return str(step.get("text", ""))
    return str(step)


def _step_kind(step: Any) -> str:
    if isinstance(step, dict):
        return _norm(step.get("kind", ""))
    return ""


def _part_text(part: Any) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        return str(part.get("text", ""))
    return str(part)


# Required Section-11 / Thank-You step kinds and the tolerant keyword sets that also
# satisfy them (a kind counts as present if a step is TAGGED with it OR any of its
# keywords appears in the joined step text — so the mandatory steps cannot be dodged).
_STEP_KIND_KEYWORDS = {
    "share": ["share", "friend"],
    "email_bonus": ["email", "bonus", "inbox"],
    "founder_text": ["personal text", "text from", "founder", "a text"],
    "community": ["community", "join the", "group", "members"],
}


# ---------------------------------------------------------------------------
# Per-section checkers. Each appends (AF-code, message) to `fail`.
# ---------------------------------------------------------------------------
def _check_charband(sec, spec, sid, af, fail, label):
    lo = int(spec.get("char_min", 0))
    hi = int(spec.get("char_max", 10 ** 9))
    n = _slen(sec.get("copy", ""))
    if n < lo or n > hi:
        fail(af, f"{label}: {n} stripped chars, outside the sacred band [{lo}, {hi}]")


def _check_wordmax(sec, spec, af, fail, label, field="copy"):
    hi = int(spec.get("word_max", 10 ** 9))
    n = _wcount(sec.get(field, ""))
    if n > hi:
        fail(af, f"{label}: {n} words, over the sacred maximum of {hi}")


def verify(structure: Dict[str, Any], ledger: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []

    def fail(code: str, msg: str) -> None:
        violations.append((code, msg))

    sections_spec = structure.get("sections") or {}
    repl_spec = structure.get("section8_replacements") or {}
    ty_spec = structure.get("thank_you") or {}
    profiles = structure.get("profiles") or {}

    product_title = ledger.get("product_title") or ledger.get("offer_title") or ""
    pages = ledger.get("pages")
    if not isinstance(pages, list) or not pages:
        fail("AF-FUN-PROFILE-UNKNOWN", "copy ledger has no non-empty 'pages' array")
        return violations, notes

    for page in pages:
        if not isinstance(page, dict):
            fail("AF-FUN-PROFILE-UNKNOWN", "a page entry is not an object")
            continue
        ptype = str(page.get("page_type", "")).strip().lower()
        profile = profiles.get(ptype)
        if not isinstance(profile, dict):
            fail("AF-FUN-PROFILE-UNKNOWN", f"page_type {ptype!r} is not a known profile")
            continue

        # ---- checkout: microcopy only, no 12-section gate --------------------
        if profile.get("microcopy_only"):
            notes.append(f"page '{ptype}': microcopy-only profile — 12-section gate not applied")
            continue

        # ---- thank-you: TY-1 / TY-2 / TY-3 -----------------------------------
        if profile.get("thank_you"):
            _verify_thank_you(page, ty_spec, product_title, fail)
            continue

        # ---- 12-section (main / upsell / downsell / upsell-2 / downsell-2) ----
        required = [int(x) for x in (profile.get("sections") or [])]
        repl_key = profile.get("section8_replacement")
        by_num: Dict[int, Dict[str, Any]] = {}
        order_seen: List[int] = []
        for sec in (page.get("sections") or []):
            if not isinstance(sec, dict):
                fail("AF-FUN-SECTION-MISSING", f"page '{ptype}': a section entry is not an object")
                continue
            num = sec.get("section")
            if not isinstance(num, int):
                fail("AF-FUN-SECTION-ORDER",
                     f"page '{ptype}': a section has a missing/invalid integer 'section' id ({num!r})")
                continue
            by_num[num] = sec
            order_seen.append(num)

        for need in required:
            if need not in by_num:
                fail("AF-FUN-SECTION-MISSING", f"page '{ptype}': required Section {need} is absent")
        for got in order_seen:
            if got not in required:
                fail("AF-FUN-SECTION-EXTRA",
                     f"page '{ptype}': Section {got} is not allowed by the '{ptype}' profile")
        if order_seen and order_seen != sorted(set(order_seen)):
            fail("AF-FUN-SECTION-ORDER",
                 f"page '{ptype}': sections {order_seen} are duplicated or not in ascending order")

        for num in required:
            sec = by_num.get(num)
            if sec is None:
                continue
            _verify_section(num, sec, ptype, sections_spec, repl_key, repl_spec,
                            product_title, fail)

    return violations, notes


def _verify_section(num, sec, ptype, sections_spec, repl_key, repl_spec, product_title, fail):
    # Section 8 on a derived page is the REPLACEMENT block, not Benefit 1.
    if num == 8 and repl_key:
        _verify_section8_replacement(sec, ptype, repl_spec.get(repl_key) or {}, fail)
        return

    spec = sections_spec.get(str(num)) or {}
    label = f"page '{ptype}' Section {num} ({spec.get('name', '?')})"

    if num == 1:
        _check_charband(sec, spec, num, "AF-FUN-SEC1-CHARBAND", fail, label)
        if spec.get("requires_title") and ptype == "main":
            if not product_title or _norm(product_title) not in _norm(sec.get("copy", "")):
                fail("AF-FUN-SEC1-TITLE",
                     f"{label}: does not contain the product title {product_title!r}")
        if spec.get("requires_cta") and not _has_cta(sec):
            fail("AF-FUN-SEC1-CTA", f"{label}: missing a labeled CTA")
        return

    if num in (2, 3, 4):
        _check_charband(sec, spec, num, "AF-FUN-PAIN-CHARBAND", fail, label)
        copy = sec.get("copy", "")
        if spec.get("forbid_question") and "?" in str(copy):
            fail("AF-FUN-PAIN-QUESTION", f"{label}: written in question format ('?' present)")
        if spec.get("second_person") and not re.search(r"\byou\b|\byour\b|\byou'\w+", _norm(copy)):
            fail("AF-FUN-PAIN-2ND-PERSON", f"{label}: not written in 2nd person (no you/your)")
        if spec.get("requires_cta") and not _has_cta(sec):
            fail("AF-FUN-PAIN-CTA", f"{label}: missing a labeled CTA")
        return

    if num == 5:
        _check_wordmax(sec, spec, "AF-FUN-SEC5-WORDS", fail, label)
        lead = _norm(spec.get("lead_phrase", ""))
        if lead:
            body = _norm(sec.get("copy", "")).lstrip('"\'' + " ")
            if not body.startswith(lead):
                fail("AF-FUN-SEC5-LEAD", f"{label}: does not start '{spec.get('lead_phrase')}'")
        if spec.get("requires_cta") and not _has_cta(sec):
            fail("AF-FUN-SEC5-CTA", f"{label}: missing its motivational CTA")
        return

    if num == 6:
        _check_wordmax(sec, spec, "AF-FUN-SEC6-WORDS", fail, label)
        personas = sec.get("personas")
        n = len(personas) if isinstance(personas, list) else -1
        lo, hi = int(spec.get("personas_min", 3)), int(spec.get("personas_max", 6))
        if n < lo or n > hi:
            fail("AF-FUN-SEC6-PERSONAS",
                 f"{label}: {n if n >= 0 else 'missing'} personas, outside [{lo}, {hi}]")
        if spec.get("forbid_cta") and (_has_cta(sec) or _has_cta_button(sec)):
            fail("AF-FUN-SEC6-NO-CTA", f"{label}: carries a CTA (Section 6 forbids any CTA)")
        return

    if num == 7:
        bullets = sec.get("bullets")
        blist = bullets if isinstance(bullets, list) else []
        text7 = str(sec.get("copy", "")) + " " + " ".join(str(b) for b in blist)
        lo, hi = int(spec.get("word_min", 70)), int(spec.get("word_max", 120))
        n = _wcount(text7)
        if n < lo or n > hi:
            fail("AF-FUN-SEC7-WORDS", f"{label}: {n} words, outside [{lo}, {hi}]")
        blo, bhi = int(spec.get("bullets_min", 5)), int(spec.get("bullets_max", 10))
        nb = len(blist)
        if nb < blo or nb > bhi:
            fail("AF-FUN-SEC7-BULLETS", f"{label}: {nb} bullets, outside [{blo}, {bhi}]")
        return

    if num in (8, 9):  # main-page Benefit 1 / Benefit 2
        _check_wordmax(sec, spec, "AF-FUN-BENEFIT-WORDS", fail, label)
        if spec.get("forbid_cta") and (_has_cta(sec) or _has_cta_button(sec)):
            fail("AF-FUN-BENEFIT-NO-CTA", f"{label}: carries a CTA (Benefit 1/2 forbid a CTA)")
        return

    if num == 10:
        _check_wordmax(sec, spec, "AF-FUN-BENEFIT-WORDS", fail, label)
        if spec.get("requires_cta_button") and not _has_cta_button(sec):
            fail("AF-FUN-SEC10-CTA", f"{label}: missing its inspirational CTA button")
        return

    if num == 11:
        _verify_section11(sec, spec, label, fail)
        return

    if num == 12:
        _verify_section12(sec, spec, label, fail)
        return


def _verify_section11(sec, spec, label, fail):
    steps = sec.get("steps")
    slist = steps if isinstance(steps, list) else []
    words = _wcount(" ".join(_step_text(s) for s in slist))
    lo, hi = int(spec.get("word_min", 100)), int(spec.get("word_max", 150))
    if words < lo or words > hi:
        fail("AF-FUN-SEC11-WORDS", f"{label}: {words} words across steps, outside [{lo}, {hi}]")
    if spec.get("forbid_cta_button") and _has_cta_button(sec):
        fail("AF-FUN-SEC11-NO-CTA-BUTTON",
             f"{label}: carries a CTA button (forbidden; step 7 is the in-copy CTA)")
    n = len(slist)
    smin, smax = int(spec.get("steps_min", 5)), int(spec.get("steps_max", 10))
    if n < smin or n > smax:
        fail("AF-FUN-SEC11-STEPS", f"{label}: {n} steps, outside [{smin}, {smax}]")
    clo, chi = int(spec.get("step_char_min", 89)), int(spec.get("step_char_max", 116))
    cap7 = int(spec.get("step7_char_max", 170))
    last = n - 1
    for i, s in enumerate(slist):
        length = _slen(_step_text(s))
        if i == last:
            if length > cap7:
                fail("AF-FUN-SEC11-STEP7",
                     f"{label}: final step {length} chars, over the {cap7}-char cap")
        elif i <= 5:
            if length < clo or length > chi:
                fail("AF-FUN-SEC11-STEPBAND",
                     f"{label}: step {i + 1} is {length} chars, outside [{clo}, {chi}]")
        else:
            if length > cap7:
                fail("AF-FUN-SEC11-STEP7",
                     f"{label}: step {i + 1} is {length} chars, over the {cap7}-char cap")
    # mandatory step kinds (share / email_bonus / founder_text / community)
    required_kinds = spec.get("required_step_kinds") or []
    tagged = {_step_kind(s) for s in slist}
    joined = _norm(" ".join(_step_text(s) for s in slist))
    missing = []
    for kind in required_kinds:
        if kind in tagged:
            continue
        if any(kw in joined for kw in _STEP_KIND_KEYWORDS.get(kind, [])):
            continue
        missing.append(kind)
    if missing:
        fail("AF-FUN-SEC11-REQUIRED-STEPS",
             f"{label}: missing mandatory step kind(s): {', '.join(missing)}")


def _verify_section12(sec, spec, label, fail):
    parts = sec.get("parts")
    plist = parts if isinstance(parts, list) else []
    text12 = " ".join(_part_text(p) for p in plist) if plist else str(sec.get("copy", ""))
    lo, hi = int(spec.get("word_min", 100)), int(spec.get("word_max", 150))
    n = _wcount(text12)
    if n < lo or n > hi:
        fail("AF-FUN-SEC12-WORDS", f"{label}: {n} words, outside [{lo}, {hi}]")
    want = int(spec.get("parts_count", 6))
    if len(plist) != want:
        fail("AF-FUN-SEC12-PARTS", f"{label}: {len(plist)} labeled parts, expected exactly {want}")
    lead = _norm(spec.get("part2_lead", ""))
    if lead and len(plist) >= 2:
        p2 = _norm(_part_text(plist[1])).lstrip('"\'' + " ")
        if not p2.startswith(lead):
            fail("AF-FUN-SEC12-STRUGGLE",
                 f"{label}: part 2 (The Big Struggle) does not start '{spec.get('part2_lead')}'")


def _verify_section8_replacement(sec, ptype, rspec, fail):
    label = f"page '{ptype}' Section 8 (replacement)"
    pattern = rspec.get("name_pattern")
    name = _norm(sec.get("name", ""))
    if pattern == "seven_reasons":
        if not (name.startswith("7 reasons to commit to your") and name.endswith("future")):
            fail("AF-FUN-SEC8REPL-NAME",
                 f"{label}: name {sec.get('name')!r} is not a '7 Reasons To Commit To Your ____ Future' block")
    elif pattern == "when_time_runs_out":
        if name != "when time runs out":
            fail("AF-FUN-SEC8REPL-NAME",
                 f"{label}: name {sec.get('name')!r} is not 'When Time Runs Out'")
    want = int(rspec.get("item_count", 7))
    items = sec.get("items")
    if not isinstance(items, list):
        items = sec.get("bullets") if isinstance(sec.get("bullets"), list) else []
    if len(items) != want:
        fail("AF-FUN-SEC8REPL-COUNT",
             f"{label}: {len(items)} items, expected exactly {want} ({rspec.get('item_kind')})")


def _verify_thank_you(page, ty_spec, product_title, fail):
    by_id: Dict[str, Dict[str, Any]] = {}
    for sec in (page.get("sections") or []):
        if isinstance(sec, dict) and _nonempty(str(sec.get("section", ""))):
            by_id[str(sec.get("section")).strip().upper()] = sec
    # TY-1
    ty1 = by_id.get("TY-1")
    s1 = ty_spec.get("TY-1") or {}
    if ty1 is None:
        fail("AF-FUN-TY1-CHARBAND", "thank-you: TY-1 (The Big Bold Welcome) is absent")
    else:
        n = _slen(ty1.get("copy", ""))
        lo, hi = int(s1.get("char_min", 120)), int(s1.get("char_max", 180))
        if n < lo or n > hi:
            fail("AF-FUN-TY1-CHARBAND", f"thank-you TY-1: {n} chars, outside [{lo}, {hi}]")
        if s1.get("requires_title"):
            if not product_title or _norm(product_title) not in _norm(ty1.get("copy", "")):
                fail("AF-FUN-TY1-TITLE", f"thank-you TY-1: does not name the product title {product_title!r}")
    # TY-2
    ty2 = by_id.get("TY-2")
    s2 = ty_spec.get("TY-2") or {}
    if ty2 is None:
        fail("AF-FUN-TY2-STEPS", "thank-you: TY-2 (What Happens Next) is absent")
    else:
        steps = ty2.get("steps")
        slist = steps if isinstance(steps, list) else []
        lo, hi = int(s2.get("steps_min", 4)), int(s2.get("steps_max", 6))
        if len(slist) < lo or len(slist) > hi:
            fail("AF-FUN-TY2-STEPS", f"thank-you TY-2: {len(slist)} steps, outside [{lo}, {hi}]")
        clo, chi = int(s2.get("step_char_min", 89)), int(s2.get("step_char_max", 116))
        for i, s in enumerate(slist):
            length = _slen(_step_text(s))
            if length < clo or length > chi:
                fail("AF-FUN-TY2-STEPBAND",
                     f"thank-you TY-2: step {i + 1} is {length} chars, outside [{clo}, {chi}]")
    # TY-3
    ty3 = by_id.get("TY-3")
    s3 = ty_spec.get("TY-3") or {}
    if ty3 is None:
        fail("AF-FUN-TY3-CHARBAND", "thank-you: TY-3 (The Big Empowering Close) is absent")
    else:
        n = _slen(ty3.get("copy", ""))
        cap = int(s3.get("char_max", 170))
        if n > cap:
            fail("AF-FUN-TY3-CHARBAND", f"thank-you TY-3: {n} chars, over the {cap}-char cap")


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _default_structure_path() -> Path:
    return Path(__file__).resolve().parent.parent / "structure" / "funnel_structure.json"


def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _load_structure(path_arg: Optional[str]) -> Dict[str, Any]:
    p = Path(path_arg) if path_arg else _default_structure_path()
    return json.loads(p.read_text(encoding="utf-8", errors="replace"))


def _report(violations, notes) -> None:
    for note in notes:
        print(f"NOTE: {note}")
    if not violations:
        print("PASS: funnel copy clears every rule in the SACRED 12-section contract.")
        return
    print(f"FAIL: {len(violations)} copy violation(s) — funnel is NOT run, NOT rendered, NOT built.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test fixtures.
# ---------------------------------------------------------------------------
def _fill(prefix: str, n: int) -> str:
    """Return a string of EXACTLY n stripped chars beginning with `prefix` (no '?')."""
    pad = " and you keep the promise you made to yourself and move it forward"
    s = prefix
    while len(s) < n:
        s += pad
    return s[:n].strip().ljust(n, "x") if len(s[:n].strip()) < n else s[:n]


def _fill_noyou(prefix: str, n: int) -> str:
    """Like _fill but the padding contains no 2nd-person pronoun (for the negative fixture)."""
    pad = " and the hours slip past as the work keeps piling higher on the desk"
    s = prefix
    while len(s) < n:
        s += pad
    return s[:n]


def _valid_main_page() -> Dict[str, Any]:
    title = "The 5AM Reset"
    sections = []
    # Sec 1 — 200 chars, contains title, labeled CTA
    sections.append({"section": 1, "name": "The Big Bold Claim",
                     "copy": _fill(f"{title} hands you calm unhurried mornings and a rested body", 200),
                     "cta": "CTA: Start My Reset"})
    # Sec 2-4 — 200 chars, 2nd person, no '?', CTA
    for num, name in ((2, "The Big Bold Pain 1"), (3, "The Big Bold Pain 2"), (4, "The Big Bold Pain 3")):
        sections.append({"section": num, "name": name,
                         "copy": _fill("You wake exhausted and your day owns you before your feet hit the floor", 200),
                         "cta": "CTA: Start My Reset"})
    # Sec 5 — <=30 words, lead, CTA
    sections.append({"section": 5, "name": "The Big Bold Why",
                     "copy": "That's the reason why you deserve mornings that belong to you and a life that finally moves.",
                     "cta": "CTA: Start My Reset"})
    # Sec 6 — <=30 words, 4 personas, NO cta
    sections.append({"section": 6, "name": "The Big Bold Who",
                     "copy": "Founders who want focus, parents who want calm, creators who want output, leaders who want energy.",
                     "personas": ["founders", "parents", "creators", "leaders"]})
    # Sec 7 — 70-120 words, 6 bullets
    sections.append({"section": 7, "name": "The Big Bold What",
                     "copy": " ".join(["clarity"] * 55),
                     "bullets": ["you get the full daily reset toolkit and guide"] * 6})
    # Sec 8 / 9 — <=30 words, NO cta
    sections.append({"section": 8, "name": "The Big Bold Benefit 1",
                     "copy": "You feel the weight lift this week as your first quiet mornings return calm and steady."})
    sections.append({"section": 9, "name": "The Big Bold Benefit 2",
                     "copy": "You watch the numbers move this quarter as focus turns into finished work and real results."})
    # Sec 10 — <=30 words, CTA button
    sections.append({"section": 10, "name": "The Big Bold Benefit 3",
                     "copy": "You become the person your future was waiting for, unhurried and unstoppable.",
                     "has_cta_button": True, "cta": "CTA: Start My Reset"})
    # Sec 11 — 100-150 words, 7 steps, no button, required kinds
    steps = [
        _fill("Share this reset with one friend who needs calm mornings as much", 100),
        _fill("Check your email for the welcome bonus we send the moment", 100),
        _fill("Watch for a personal text from the founder because it is real", 100),
        _fill("Join the community today and introduce yourself to people walking", 100),
        _fill("Save the date and open module one so momentum starts right", 100),
        _fill("Write your ninety day commitment and keep it where you will", 100),
        "This is your morning and your life, so rise now and let the reset carry you all the way forward from here.",
    ]
    sections.append({"section": 11, "name": "The Big How To", "steps": steps})
    # Sec 12 — 100-150 words, 6 parts, part2 lead
    parts = [
        {"label": "The Big Bold Heartfelt Message", "text": " ".join(["welcome"] * 20)},
        {"label": "The Big Struggle", "text": "I used to be just like you, " + " ".join(["tired"] * 16)},
        {"label": "The Big Decision", "text": " ".join(["decide"] * 20)},
        {"label": "The Big Reason", "text": " ".join(["purpose"] * 20)},
        {"label": "The Big Invite", "text": " ".join(["join"] * 20)},
        {"label": "The Big Passionate Close", "text": " ".join(["welcome"] * 20)},
    ]
    sections.append({"section": 12, "name": "The Big Bold Heartfelt Message", "parts": parts})
    return {"page_type": "main", "sections": sections}


def _valid_upsell_page() -> Dict[str, Any]:
    sections = []
    sections.append({"section": 1, "name": "The Big Bold Claim",
                     "copy": _fill("You just claimed your reset, and this is the one time upgrade that", 200),
                     "cta": "CTA: Yes Upgrade My Order"})
    for num in (2, 3, 4):
        sections.append({"section": num, "name": f"The Big Bold Pain {num - 1}",
                         "copy": _fill("You know the gap between what you bought and what you truly want", 200),
                         "cta": "CTA: Yes Upgrade My Order"})
    sections.append({"section": 5, "name": "The Big Bold Why",
                     "copy": "That's the reason why you take the upgrade now while the door is open and the momentum is real.",
                     "cta": "CTA: Yes Upgrade My Order"})
    sections.append({"section": 6, "name": "The Big Bold Who",
                     "copy": "Doers who want speed, builders who want proximity, leaders who want the shortcut to the result.",
                     "personas": ["doers", "builders", "leaders"]})
    sections.append({"section": 7, "name": "The Big Bold What",
                     "copy": " ".join(["access"] * 55),
                     "bullets": ["you get the accelerated done for you upgrade"] * 6})
    sections.append({"section": 8, "name": "7 Reasons To Commit To Your Unstoppable Future",
                     "items": [f"Reason {i}: you move faster and keep the momentum you started" for i in range(1, 8)],
                     "cta": "CTA: Yes Upgrade My Order"})
    return {"page_type": "upsell", "sections": sections}


def _valid_thank_you_page() -> Dict[str, Any]:
    title = "The 5AM Reset"
    steps = [
        _fill("Check your email for your receipt and the welcome bonus we", 100),
        _fill("Watch for a personal text from the founder and answer it", 100),
        _fill("Join the community below and introduce yourself to everyone", 100),
        _fill("Share this with one friend who needs the reset as much", 100),
    ]
    return {"page_type": "thank-you", "sections": [
        {"section": "TY-1", "copy": _fill(f"It is official, {title} is yours and the decision most people keep postponing you just made", 150)},
        {"section": "TY-2", "steps": steps},
        {"section": "TY-3", "copy": "You made a decision most people keep postponing, and everything you need is on its way. Welcome to the next stage."},
    ]}


def _valid_ledger() -> Dict[str, Any]:
    return {
        "funnel_type": "signature_funnel",
        "funnel_size": 3,
        "product_title": "The 5AM Reset",
        "offer_token_ledger": ["The 5AM Reset"],
        "pages": [_valid_main_page(), _valid_upsell_page(), _valid_thank_you_page()],
    }


def _mut(fn):
    d = _valid_ledger()
    fn(d)
    return d


def _main_secs(d):
    return d["pages"][0]["sections"]


def _sec(d, page_idx, num):
    for s in d["pages"][page_idx]["sections"]:
        if s.get("section") == num:
            return s
    raise KeyError(num)


def _violation_cases():
    def sec1_short(d):
        _sec(d, 0, 1)["copy"] = "too short"
    def sec1_title(d):
        _sec(d, 0, 1)["copy"] = _fill("A calm unhurried morning and a rested body await you when you begin", 200)
    def pain_question(d):
        s = _sec(d, 0, 2); s["copy"] = s["copy"][:-1] + "?"
    def pain_2nd(d):
        _sec(d, 0, 2)["copy"] = _fill_noyou("Mornings feel heavy and the day takes over before anyone can catch a breath at all", 200)
    def sec5_lead(d):
        _sec(d, 0, 5)["copy"] = "You deserve mornings that belong to you and a life that finally moves forward."
    def sec6_personas(d):
        _sec(d, 0, 6)["personas"] = ["only", "two"]
    def sec6_cta(d):
        _sec(d, 0, 6)["cta"] = "CTA: Start My Reset"
    def sec7_bullets(d):
        _sec(d, 0, 7)["bullets"] = ["you get the toolkit"] * 3
    def sec10_button(d):
        s = _sec(d, 0, 10); s["has_cta_button"] = False; s.pop("cta", None)
    def sec11_stepband(d):
        _sec(d, 0, 11)["steps"][0] = "way too short"
    def sec11_required(d):
        s = _sec(d, 0, 11)
        s["steps"] = [_fill("Do a generic morning action and simply keep repeating the same plain thing", 100) for _ in range(6)] + \
                     ["Rise now and let it carry you forward all the way from here today and beyond."]
    def sec12_parts(d):
        _sec(d, 0, 12)["parts"] = _sec(d, 0, 12)["parts"][:5]
    def sec12_struggle(d):
        _sec(d, 0, 12)["parts"][1]["text"] = "My story began somewhere far from where you are standing now today."
    def section_missing(d):
        d["pages"][0]["sections"] = [s for s in _main_secs(d) if s.get("section") != 3]
    def repl_name(d):
        _sec(d, 1, 8)["name"] = "Some Other Heading Entirely"
    def repl_count(d):
        _sec(d, 1, 8)["items"] = _sec(d, 1, 8)["items"][:6]
    def ty1_charband(d):
        _sec(d, 2, "TY-1")["copy"] = "too short welcome"
    def ty2_steps(d):
        _sec(d, 2, "TY-2")["steps"] = _sec(d, 2, "TY-2")["steps"][:2]
    def ty3_charband(d):
        _sec(d, 2, "TY-3")["copy"] = "x" * 200

    return [
        ("sec1_short", "AF-FUN-SEC1-CHARBAND", lambda: _mut(sec1_short)),
        ("sec1_title", "AF-FUN-SEC1-TITLE", lambda: _mut(sec1_title)),
        ("pain_question", "AF-FUN-PAIN-QUESTION", lambda: _mut(pain_question)),
        ("pain_2nd_person", "AF-FUN-PAIN-2ND-PERSON", lambda: _mut(pain_2nd)),
        ("sec5_lead", "AF-FUN-SEC5-LEAD", lambda: _mut(sec5_lead)),
        ("sec6_personas", "AF-FUN-SEC6-PERSONAS", lambda: _mut(sec6_personas)),
        ("sec6_cta", "AF-FUN-SEC6-NO-CTA", lambda: _mut(sec6_cta)),
        ("sec7_bullets", "AF-FUN-SEC7-BULLETS", lambda: _mut(sec7_bullets)),
        ("sec10_button", "AF-FUN-SEC10-CTA", lambda: _mut(sec10_button)),
        ("sec11_stepband", "AF-FUN-SEC11-STEPBAND", lambda: _mut(sec11_stepband)),
        ("sec11_required_steps", "AF-FUN-SEC11-REQUIRED-STEPS", lambda: _mut(sec11_required)),
        ("sec12_parts", "AF-FUN-SEC12-PARTS", lambda: _mut(sec12_parts)),
        ("sec12_struggle", "AF-FUN-SEC12-STRUGGLE", lambda: _mut(sec12_struggle)),
        ("section_missing", "AF-FUN-SECTION-MISSING", lambda: _mut(section_missing)),
        ("repl_name", "AF-FUN-SEC8REPL-NAME", lambda: _mut(repl_name)),
        ("repl_count", "AF-FUN-SEC8REPL-COUNT", lambda: _mut(repl_count)),
        ("ty1_charband", "AF-FUN-TY1-CHARBAND", lambda: _mut(ty1_charband)),
        ("ty2_steps", "AF-FUN-TY2-STEPS", lambda: _mut(ty2_steps)),
        ("ty3_charband", "AF-FUN-TY3-CHARBAND", lambda: _mut(ty3_charband)),
    ]


def run_self_test(structure) -> int:
    ok = True
    v, notes = verify(structure, _valid_ledger())
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid fixture produced {len(v)} violation(s): {v}")
    else:
        print("SELF-TEST ok: valid fixture PASSES (0 violations).")
    n_pass, n_fail = 1 if not v else 0, 0
    cases = _violation_cases()
    for name, expected, build in cases:
        vio, _ = verify(structure, build())
        codes = {c for c, _ in vio}
        if not vio:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")
            n_fail += 1
    print(f"SELF-TEST FIXTURES: {n_pass} valid-pass, {n_fail}/{len(cases)} violation-catch")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed prover for the SACRED 12-section Signature Funnel copy contract. "
                    "Exit 0 = pass, 2 = violation, 3 = usage/fail-closed.")
    ap.add_argument("--ledger", help="path to the funnel COPY ledger JSON ('-' reads stdin)")
    ap.add_argument("--structure", help="path to funnel_structure.json (defaults to ../structure/)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct a VALID fixture (must PASS) + each VIOLATION fixture (must FAIL)")
    args = ap.parse_args(argv)

    if args.self_test:
        try:
            structure = _load_structure(args.structure)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot load structure ledger: {exc}")
            return EXIT_FAILCLOSED
        return run_self_test(structure)

    if not args.ledger:
        print("USAGE ERROR: pass --ledger <ledger.json> (or --self-test).")
        return EXIT_FAILCLOSED
    try:
        structure = _load_structure(args.structure)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load structure ledger: {exc}")
        return EXIT_FAILCLOSED
    try:
        ledger = _load_json(args.ledger)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load copy ledger {args.ledger!r}: {exc}")
        return EXIT_FAILCLOSED
    if not isinstance(ledger, dict):
        print("USAGE/IO ERROR: copy ledger must be a JSON object.")
        return EXIT_FAILCLOSED

    violations, notes = verify(structure, ledger)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
