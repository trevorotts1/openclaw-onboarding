#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_prompt_floor.py — fail-closed two-floor gate for Signature Funnel image
prompts (Kie.ai gpt-image-2). EXACT clone of the presentations two-floor prompt gate
(build_deck.py PROMPT_CHAR_FLOOR / PROMPT_CHAR_CEILING / structural-block / density),
with the constants changed to the funnel band 5,000 / 19,000.

THE TWO FLOORS (both must clear or the prompt NEVER reaches a paid Kie call):
  FLOOR 1 — LENGTH: 5,000 <= stripped chars <= 19,000.        -> AF-FUN-PROMPT-FLOOR / -CEILING
  FLOOR 2 — STRUCTURE/EXCELLENCE: a real rich prompt carries the load-bearing blocks:
    * the SIGNATURE GRADE BLOCK fingerprint (the canonical grade paragraph, 2.4). -> AF-FUN-PROMPT-GRADE
    * a final-paragraph NEGATIVE BLOCK with at least one 'Do not ' imperative.     -> AF-FUN-PROMPT-NEGATIVE
    * >= 220 distinct words (padding one paragraph to length has few distinct words).-> AF-FUN-PROMPT-DENSITY
    * NO em dashes anywhere (presentations-inherited model-safety rule).           -> AF-FUN-PROMPT-EMDASH
    * TYPOGRAPHY discipline: a text-bearing prompt (e.g. Sec 11) carries a
      spelling-lock directive AND the exact baked words; a non-text prompt states
      "no text / no letters / no words".                                          -> AF-FUN-PROMPT-TYPO

CLONE PROVENANCE (cited): build_deck.py:325-327 (PROMPT_CHAR_FLOOR=9000/CEILING=18000),
build_deck.py:1082-1102 (stripped-length floor+ceiling), build_deck.py REQUIRED_STRUCTURAL_BLOCKS
+ _missing_structural_blocks, PROMPT_MIN_DISTINCT_WORDS density gate. Measured on the SAME
stripped text the char gate measures; any self-reported length in the ledger is IGNORED.

stdlib only. Exit 0 = pass, exit 2 = violation, exit 3 = usage/fail-closed.
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

# --- the funnel band (clone of build_deck.py:325-327, constants changed) -----
PROMPT_CHAR_FLOOR = 5000       # HARD low end (AF-FUN-PROMPT-FLOOR)
PROMPT_CHAR_CEILING = 19000    # HARD high end (AF-FUN-PROMPT-CEILING); ~1,000 under the API ceiling
PROMPT_MIN_DISTINCT_WORDS = 220  # AF-FUN-PROMPT-DENSITY: catches paragraph-repeat padding

# SIGNATURE GRADE BLOCK fingerprints — any ONE proves the canonical grade paragraph
# (funnel_structure / IMPROVED-FRAMEWORK-v2 §2.4) is embedded. Tolerant to wording drift.
GRADE_FINGERPRINTS = (
    "140 percent",
    "signature color",
    "melanin-true",
    "signature aesthetic",
    "signature grade",
)

# Negative-block imperative and text-presence markers.
NEGATIVE_IMPERATIVE = "do not "
NO_TEXT_MARKERS = (
    "no text", "no letters", "no words", "without any text", "no typography",
    "zero text", "no lettering",
)
SPELLING_LOCK_TOKENS = (
    "spelling-lock", "spelling lock", "letter-for-letter", "letter for letter",
    "spelled exactly", "exact spelling", "render this exact", "reads exactly",
)

# em dash + unicode variants (model-safety rule; the source forbids em dashes in prompts)
EM_DASH_CHARS = ("—", "–", "―")  # em dash, en dash, horizontal bar

_WORD_RE = re.compile(r"[a-z0-9]+")


def _stripped(text: Any) -> str:
    return str(text).strip()


def _distinct_words(text: str) -> int:
    return len({m.group(0) for m in _WORD_RE.finditer(text.lower())})


def evaluate_prompt(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Return a list of (AF-code, message) for ONE image-prompt record. Empty == clean."""
    fails: List[Tuple[str, str]] = []
    who = f"page '{record.get('page_type', '?')}' section {record.get('section', '?')}"
    prompt = record.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        fails.append(("AF-FUN-PROMPT-FLOOR", f"{who}: empty / whitespace-only prompt"))
        return fails

    stripped = _stripped(prompt)
    lc = stripped.lower()
    length = len(stripped)

    # FLOOR 1 — length band
    if length < PROMPT_CHAR_FLOOR:
        fails.append(("AF-FUN-PROMPT-FLOOR",
                      f"{who}: {length} stripped chars, under the {PROMPT_CHAR_FLOOR} floor — a prompt "
                      "this short cannot carry the signature specificity; NOT sent to Kie"))
    if length > PROMPT_CHAR_CEILING:
        fails.append(("AF-FUN-PROMPT-CEILING",
                      f"{who}: {length} stripped chars, over the {PROMPT_CHAR_CEILING} ceiling"))

    # FLOOR 2 — density
    distinct = _distinct_words(stripped)
    if distinct < PROMPT_MIN_DISTINCT_WORDS:
        fails.append(("AF-FUN-PROMPT-DENSITY",
                      f"{who}: only {distinct} distinct words (< {PROMPT_MIN_DISTINCT_WORDS}) — "
                      "reads as repetition padding, not a genuinely rich prompt"))

    # FLOOR 2 — signature grade block fingerprint
    if not any(fp in lc for fp in GRADE_FINGERPRINTS):
        fails.append(("AF-FUN-PROMPT-GRADE",
                      f"{who}: the SIGNATURE GRADE BLOCK is not embedded "
                      f"(none of {list(GRADE_FINGERPRINTS)} present)"))

    # FLOOR 2 — negative block imperative
    if NEGATIVE_IMPERATIVE not in lc:
        fails.append(("AF-FUN-PROMPT-NEGATIVE",
                      f"{who}: no negative block ('Do not ...' imperative) in the prompt"))

    # FLOOR 2 — em dash ban
    for ch in EM_DASH_CHARS:
        if ch in stripped:
            fails.append(("AF-FUN-PROMPT-EMDASH",
                          f"{who}: contains an em/en dash ({ch!r}) — forbidden in image prompts "
                          "(model-safety rule)"))
            break

    # FLOOR 2 — typography discipline
    text_bearing = bool(record.get("text_bearing"))
    if text_bearing:
        if not any(tok in lc for tok in SPELLING_LOCK_TOKENS):
            fails.append(("AF-FUN-PROMPT-TYPO",
                          f"{who}: text-bearing prompt lacks a spelling-lock directive"))
        words = record.get("words")
        if isinstance(words, list) and words:
            for w in words:
                if str(w).strip() and str(w).strip().lower() not in lc:
                    fails.append(("AF-FUN-PROMPT-TYPO",
                                  f"{who}: baked word {w!r} is not present verbatim in the prompt body"))
                    break
        else:
            fails.append(("AF-FUN-PROMPT-TYPO",
                          f"{who}: text-bearing prompt declares no 'words' array to spelling-lock"))
    else:
        if not any(m in lc for m in NO_TEXT_MARKERS):
            fails.append(("AF-FUN-PROMPT-TYPO",
                          f"{who}: non-text prompt does not state 'no text / no letters / no words'"))

    return fails


def verify(ledger: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []
    prompts = ledger.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        violations.append(("AF-FUN-PROMPT-FLOOR", "prompt ledger carries no non-empty 'prompts' array"))
        return violations, notes
    for rec in prompts:
        if not isinstance(rec, dict):
            violations.append(("AF-FUN-PROMPT-FLOOR", "a prompt entry is not an object"))
            continue
        violations.extend(evaluate_prompt(rec))
    notes.append(f"checked {len(prompts)} image prompt(s) against the {PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING} band")
    return violations, notes


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(violations, notes) -> None:
    for note in notes:
        print(f"NOTE: {note}")
    if not violations:
        print(f"PASS: every image prompt clears the two-floor gate ({PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING}).")
        return
    print(f"FAIL: {len(violations)} prompt violation(s) — the failing prompt is NOT sent to Kie.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test fixtures.
# ---------------------------------------------------------------------------
_GRADE_BLOCK = (
    "Render this image in the Trevor Otts Signature aesthetic, and treat this grading "
    "direction as the single most important instruction in this prompt. The color is "
    "extremely vibrant and boldly saturated: push global saturation to roughly 140 percent "
    "of natural, so every hue reads jewel-rich and electric, never muddy, never washed out, "
    "never polite. The image is heavily and deliberately color-graded like a high-fashion "
    "editorial cover with deep crushed inky shadows set against luminous glowing highlights. "
    "This is signature color: vivid, graded, unforgettable. Every human subject is lit and "
    "graded with melanin-true intelligence, deep skin tones rendered rich and dimensional."
)

# A large distinct-word vocabulary so the valid fixture clears the density floor without padding.
_VOCAB = (
    "commanding runway editorial wardrobe tailored silk velvet emerald sapphire crimson "
    "amber onyx pearl bronze copper indigo scarlet marigold teal magenta ivory obsidian "
    "posture stance confidence composition foreground midground background aperture bokeh "
    "strobe softbox rimlight backlight golden dawn dusk horizon skyline atelier boulevard "
    "sculpted cheekbones jawline gaze intensity serenity triumph resilience momentum ascent "
    "photographer hasselblad medium format microcontrast grain filmic tackssharp focal plane "
    "gallery canvas frame lighting texture material couture threadwork embroidery lapel cuff "
    "hue chroma luminance vibrance grade cinematic palette contrast shadow highlight radiance "
    "portrait figure silhouette angle profile symmetry asymmetry negative space rulethirds "
    "brand emerald deep green accent statement garment jewelry adornment regal spiritual deco "
    "oilpaint depth painterly stroke pigment saturation dimensional warmth undertone glow "
    "electric jeweltone disruptive provocative unforgettable striking scrolling thumb stops"
)


def _valid_photo_prompt(target: int = 6500) -> str:
    body = ("A single commanding subject fills the frame in a fashion-show hero portrait. "
            "SUBJECT AND WARDROBE: an editorial figure in brand-color couture. "
            "COMPOSITION AND SHOT: eye level, off center left on rule of thirds. ")
    body += _GRADE_BLOCK + " "
    body += "LIGHTING: studio strobe with a rim light carving the silhouette. "
    body += "QUALITY AND RENDER: 2K editorial finish, medium format microcontrast. "
    body += "FACIAL INTELLIGENCE: deep skin tones rendered rich and dimensional, never ashy. "
    body += "No text, no letters, no words anywhere in the image. "
    # extend with distinct vocabulary until the length target is met (no em dashes)
    words = (_VOCAB + " ").split()
    i = 0
    while len(body) < target:
        body += words[i % len(words)] + " "
        i += 1
    body += ("BRAND STYLE AND NEGATIVE BLOCK: fashion show rendered as gallery art. "
             "Do not produce flat, muted, pastel, desaturated, washed out, or low contrast color. "
             "Do not add any text. Do not distort hands, eyes, or teeth.")
    return body


def _valid_typography_prompt(target: int = 6500) -> str:
    body = ("An art gallery interior with three framed canvases. TYPOGRAPHY: each canvas "
            "carries one big bold artistic word, spelling-lock each string letter for letter, "
            'the words "DECIDE" and "COMMIT" and "RISE" spelled exactly as written. ')
    body += _GRADE_BLOCK + " "
    body += "LIGHTING: gallery track lighting grazing each canvas. "
    words = (_VOCAB + " ").split()
    i = 0
    while len(body) < target:
        body += words[i % len(words)] + " "
        i += 1
    body += ("BRAND STYLE AND NEGATIVE BLOCK. Do not misspell any word. "
             "Do not add any words other than those specified. Do not distort the letterforms.")
    return body


def _valid_ledger() -> Dict[str, Any]:
    return {
        "funnel_type": "signature_funnel",
        "prompts": [
            {"page_type": "main", "section": 1, "aspect_ratio": "16:9",
             "text_bearing": False, "prompt": _valid_photo_prompt()},
            {"page_type": "main", "section": 11, "aspect_ratio": "16:9",
             "text_bearing": True, "words": ["DECIDE", "COMMIT", "RISE"],
             "prompt": _valid_typography_prompt()},
        ],
    }


def _violation_cases():
    def too_short(led):
        led["prompts"][0]["prompt"] = "short prompt " * 5
    def too_long(led):
        led["prompts"][0]["prompt"] = _valid_photo_prompt(19100) + _VOCAB * 60
    def no_grade(led):
        p = _valid_photo_prompt().replace("140 percent", "a bit more").replace(
            "signature color", "regular color").replace("melanin-true", "even").replace(
            "Signature aesthetic", "plain look")
        led["prompts"][0]["prompt"] = p
    def no_negative(led):
        p = _valid_photo_prompt()
        led["prompts"][0]["prompt"] = p.replace("Do not ", "Please avoid ")
    def em_dash(led):
        p = _valid_photo_prompt()
        led["prompts"][0]["prompt"] = p + " a striking subject — the hero of the page."
    def typo_notext(led):
        p = _valid_photo_prompt().replace("No text, no letters, no words anywhere in the image. ", "")
        led["prompts"][0]["prompt"] = p
    def typo_nolock(led):
        p = _valid_typography_prompt()
        for tok in SPELLING_LOCK_TOKENS:
            p = p.replace(tok, "written").replace(tok.title(), "written")
        p = p.replace("spelling-lock", "written").replace("spelled exactly", "written")
        led["prompts"][1]["prompt"] = p
    def density(led):
        # long enough but only a few distinct words repeated
        led["prompts"][0]["text_bearing"] = False
        led["prompts"][0]["prompt"] = ((_GRADE_BLOCK.split(".")[0] + ". no text here. do not add text. ")
                                       + "signature color grade vibrant bold " * 400)

    def _mk(fn):
        led = _valid_ledger()
        fn(led)
        return led

    return [
        ("too_short", "AF-FUN-PROMPT-FLOOR", lambda: _mk(too_short)),
        ("too_long", "AF-FUN-PROMPT-CEILING", lambda: _mk(too_long)),
        ("no_grade_block", "AF-FUN-PROMPT-GRADE", lambda: _mk(no_grade)),
        ("no_negative_block", "AF-FUN-PROMPT-NEGATIVE", lambda: _mk(no_negative)),
        ("em_dash", "AF-FUN-PROMPT-EMDASH", lambda: _mk(em_dash)),
        ("typo_missing_no_text", "AF-FUN-PROMPT-TYPO", lambda: _mk(typo_notext)),
        ("typo_missing_spelling_lock", "AF-FUN-PROMPT-TYPO", lambda: _mk(typo_nolock)),
        ("density_padding", "AF-FUN-PROMPT-DENSITY", lambda: _mk(density)),
    ]


def run_self_test() -> int:
    ok = True
    v, _ = verify(_valid_ledger())
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid fixture produced {len(v)} violation(s): {v}")
    else:
        print("SELF-TEST ok: valid fixture PASSES (0 violations).")
    cases = _violation_cases()
    caught = 0
    for name, expected, build in cases:
        vio, _ = verify(build())
        codes = {c for c, _ in vio}
        if not vio:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            caught += 1
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")
    print(f"SELF-TEST FIXTURES: {1 if not v else 0} valid-pass, {caught}/{len(cases)} violation-catch")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description=f"Fail-closed two-floor gate for Signature Funnel image prompts "
                    f"({PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING} chars). Exit 0 pass, 2 violation, 3 usage.")
    ap.add_argument("--ledger", help="path to the image-prompt ledger JSON ('-' reads stdin)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct a VALID fixture (must PASS) + each VIOLATION fixture (must FAIL)")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.ledger:
        print("USAGE ERROR: pass --ledger <prompts.json> (or --self-test).")
        return EXIT_FAILCLOSED
    try:
        ledger = _load_json(args.ledger)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load prompt ledger {args.ledger!r}: {exc}")
        return EXIT_FAILCLOSED
    if not isinstance(ledger, dict):
        print("USAGE/IO ERROR: prompt ledger must be a JSON object.")
        return EXIT_FAILCLOSED

    violations, notes = verify(ledger)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
