#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_prompt_floor.py — fail-closed two-floor gate for Sales Page Assets image
prompts (Skill 56). A CLONE of the Signature-Funnel two-floor prompt gate
(49/scripts/prove_sf_prompt_floor.py, itself cloned from the presentations
build_deck.py PROMPT_CHAR_FLOOR / CEILING / structural-block / density gate), with the
signature GRADE fingerprint PARAMETERIZED on the client's own brand color
(${INTAKE.primary_brand_color}) instead of the Trevor Otts fixed signature color — a
sales-page image is graded to the CLIENT's brand, not a house style. (FIX-XC-04e.)

Closes the Skill 56 gap the funnel/image analysis flagged: P1 previously proved image-plan
SLICE COVERAGE only (prove_sp_image_plan.py) and never STRENGTH, so ~250-char generic
prompts sailed through to a paid image call. This prover is wired as the SECOND P1 gate.

THE TWO FLOORS (both must clear or the prompt NEVER reaches a paid image call):
  FLOOR 1 — LENGTH: 5,000 <= stripped chars <= 19,000.        -> AF-SP56-PROMPT-FLOOR / -CEILING
  FLOOR 2 — STRUCTURE / EXCELLENCE: a genuinely rich prompt carries the load-bearing blocks:
    * a BRAND-GRADE BLOCK fingerprint (the color-grade discipline paragraph).      -> AF-SP56-PROMPT-GRADE
    * the CLIENT brand color named in the prompt when the ledger declares one
      (parameterized on ${INTAKE.primary_brand_color}).                            -> AF-SP56-PROMPT-BRANDCOLOR
    * a NEGATIVE BLOCK with at least one 'Do not ' imperative.                      -> AF-SP56-PROMPT-NEGATIVE
    * >= 220 distinct words (padding one paragraph to length has few distinct words).-> AF-SP56-PROMPT-DENSITY
    * NO em dashes anywhere (model-safety rule inherited from presentations).       -> AF-SP56-PROMPT-EMDASH
    * TYPOGRAPHY discipline: a text-bearing prompt carries a spelling-lock directive
      AND the exact baked words; a non-text prompt states "no text / no letters".   -> AF-SP56-PROMPT-TYPO

Measured on the SAME stripped text the char gate measures; any self-reported length in the
ledger is IGNORED. Reads image_plan.json / a prompt ledger: prompts[].prompt_text|prompt|text.

stdlib only. Exit 0 = pass, exit 2 = violation, exit 3 = usage/fail-closed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

# --- the sales-page band (clone of the funnel band 5,000 / 19,000) -----------
PROMPT_CHAR_FLOOR = 5000       # HARD low end (AF-SP56-PROMPT-FLOOR)
PROMPT_CHAR_CEILING = 19000    # HARD high end (AF-SP56-PROMPT-CEILING); ~1,000 under the API ceiling
PROMPT_MIN_DISTINCT_WORDS = 220  # AF-SP56-PROMPT-DENSITY: catches paragraph-repeat padding

# BRAND-GRADE BLOCK fingerprints — any ONE proves a real color-grade discipline paragraph is
# embedded. Brand-agnostic (the grade is to the CLIENT brand color, which is checked separately).
GRADE_FINGERPRINTS = (
    "brand-grade",
    "brand grade",
    "color-graded",
    "color graded",
    "signature aesthetic",
    "editorial grade",
    "graded like",
    "brand color",
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
_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{3,8}$")


def _stripped(text: Any) -> str:
    return str(text).strip()


def _distinct_words(text: str) -> int:
    return len({m.group(0) for m in _WORD_RE.finditer(text.lower())})


def _prompt_text(record: Dict[str, Any]) -> str:
    for k in ("prompt_text", "prompt", "text"):
        v = record.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _brand_color_tokens(color: Any) -> List[str]:
    """Human color words to require verbatim in each prompt. A bare hex (#12332B) is not a
    describable word, so it imposes no per-prompt token requirement (grade block still required)."""
    s = str(color or "").strip()
    if not s or _HEX_RE.match(s):
        return []
    return [t for t in re.findall(r"[a-z]+", s.lower()) if len(t) >= 3]


def evaluate_prompt(record: Dict[str, Any], brand_tokens: List[str]) -> List[Tuple[str, str]]:
    """Return a list of (AF-code, message) for ONE image-prompt record. Empty == clean."""
    fails: List[Tuple[str, str]] = []
    who = f"stage '{record.get('stage', '?')}' index {record.get('index', '?')}"
    prompt = _prompt_text(record)
    if not prompt:
        fails.append(("AF-SP56-PROMPT-FLOOR", f"{who}: empty / whitespace-only prompt"))
        return fails

    stripped = _stripped(prompt)
    lc = stripped.lower()
    length = len(stripped)

    # FLOOR 1 — length band
    if length < PROMPT_CHAR_FLOOR:
        fails.append(("AF-SP56-PROMPT-FLOOR",
                      f"{who}: {length} stripped chars, under the {PROMPT_CHAR_FLOOR} floor — a prompt "
                      "this short cannot carry the brand specificity; NOT sent to the image provider"))
    if length > PROMPT_CHAR_CEILING:
        fails.append(("AF-SP56-PROMPT-CEILING",
                      f"{who}: {length} stripped chars, over the {PROMPT_CHAR_CEILING} ceiling"))

    # FLOOR 2 — density
    distinct = _distinct_words(stripped)
    if distinct < PROMPT_MIN_DISTINCT_WORDS:
        fails.append(("AF-SP56-PROMPT-DENSITY",
                      f"{who}: only {distinct} distinct words (< {PROMPT_MIN_DISTINCT_WORDS}) — "
                      "reads as repetition padding, not a genuinely rich prompt"))

    # FLOOR 2 — brand-grade block fingerprint
    if not any(fp in lc for fp in GRADE_FINGERPRINTS):
        fails.append(("AF-SP56-PROMPT-GRADE",
                      f"{who}: the BRAND-GRADE BLOCK is not embedded "
                      f"(none of {list(GRADE_FINGERPRINTS)} present)"))

    # FLOOR 2 — client brand color named (parameterized on ${INTAKE.primary_brand_color})
    for tok in brand_tokens:
        if tok not in lc:
            fails.append(("AF-SP56-PROMPT-BRANDCOLOR",
                          f"{who}: the client brand color word {tok!r} is not named in the prompt — "
                          "the image must be graded to the client's own brand color"))
            break

    # FLOOR 2 — negative block imperative
    if NEGATIVE_IMPERATIVE not in lc:
        fails.append(("AF-SP56-PROMPT-NEGATIVE",
                      f"{who}: no negative block ('Do not ...' imperative) in the prompt"))

    # FLOOR 2 — em dash ban
    for ch in EM_DASH_CHARS:
        if ch in stripped:
            fails.append(("AF-SP56-PROMPT-EMDASH",
                          f"{who}: contains an em/en dash ({ch!r}) — forbidden in image prompts "
                          "(model-safety rule)"))
            break

    # FLOOR 2 — typography discipline
    text_bearing = bool(record.get("text_bearing"))
    if text_bearing:
        if not any(tok in lc for tok in SPELLING_LOCK_TOKENS):
            fails.append(("AF-SP56-PROMPT-TYPO",
                          f"{who}: text-bearing prompt lacks a spelling-lock directive"))
        words = record.get("words")
        if isinstance(words, list) and words:
            for w in words:
                if str(w).strip() and str(w).strip().lower() not in lc:
                    fails.append(("AF-SP56-PROMPT-TYPO",
                                  f"{who}: baked word {w!r} is not present verbatim in the prompt body"))
                    break
        else:
            fails.append(("AF-SP56-PROMPT-TYPO",
                          f"{who}: text-bearing prompt declares no 'words' array to spelling-lock"))
    else:
        if not any(m in lc for m in NO_TEXT_MARKERS):
            fails.append(("AF-SP56-PROMPT-TYPO",
                          f"{who}: non-text prompt does not state 'no text / no letters / no words'"))

    return fails


def verify(ledger: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []
    prompts = ledger.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        violations.append(("AF-SP56-PROMPT-FLOOR", "prompt ledger carries no non-empty 'prompts' array"))
        return violations, notes
    brand_tokens = _brand_color_tokens(ledger.get("primary_brand_color"))
    for rec in prompts:
        if not isinstance(rec, dict):
            violations.append(("AF-SP56-PROMPT-FLOOR", "a prompt entry is not an object"))
            continue
        violations.extend(evaluate_prompt(rec, brand_tokens))
    tail = f" (brand color words required: {brand_tokens})" if brand_tokens else ""
    notes.append(f"checked {len(prompts)} image prompt(s) against the "
                 f"{PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING} band{tail}")
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
    print(f"FAIL: {len(violations)} prompt violation(s) — the failing prompt is NOT sent to the image provider.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test fixtures. The valid ledger is ALSO a slice-complete, contiguous 12-prompt plan
# so it doubles as the orchestrator self-test / golden compliant image_plan.
# ---------------------------------------------------------------------------
BRAND_COLOR = "deep evergreen"

_GRADE_BLOCK = (
    "Grade this image to the client BRAND-GRADE discipline and treat the grading direction as "
    "the single most important instruction in this prompt. Color-graded like a premium editorial "
    "cover: push saturation so the signature aesthetic reads rich and confident, never muddy, "
    "never washed out, never polite. The dominant brand color is deep evergreen, carried through "
    "the palette, the accents, and the mood, set against warm brass highlights and deep crushed "
    "shadows. This is the brand color made cinematic: deliberate, graded, unforgettable."
)

# A large distinct-word vocabulary so the valid fixture clears the density floor without padding.
_VOCAB = (
    "commanding editorial wardrobe tailored linen wool evergreen brass amber onyx pearl bronze "
    "copper indigo scarlet marigold teal ivory obsidian posture stance confidence composition "
    "foreground midground background aperture bokeh strobe softbox rimlight backlight golden dawn "
    "dusk horizon skyline atelier boulevard sculpted cheekbones jawline gaze intensity serenity "
    "triumph resilience momentum ascent photographer medium format microcontrast grain filmic "
    "tacksharp focal plane gallery canvas frame lighting texture material weave threadwork lapel "
    "cuff hue chroma luminance vibrance grade cinematic palette contrast shadow highlight radiance "
    "portrait figure silhouette angle profile symmetry balance negative rulethirds studio window "
    "desk notebook workspace order calm founder operator system architecture blueprint machine "
    "gear cadence rhythm clarity depth painterly pigment saturation warmth undertone glow electric "
    "jeweltone striking scrolling thumbstopping premium uncluttered deliberate quiet certainty "
    "morning coffee raking oak paperweight template toolkit workbook lamp couch headphones session "
    "recording sprint partner checklist fork road fog sky open rising decisive sovereign steward"
)


def _rich_prompt(scene: str, target: int = 5600, text_bearing: bool = False,
                 words=None) -> str:
    body = scene + " "
    body += _GRADE_BLOCK + " "
    body += ("COMPOSITION AND SHOT: eye level, subject off center on the rule of thirds, generous "
             "negative space, a clean premium frame with deep evergreen and warm brass tones. ")
    body += ("LIGHTING: soft directional window light with a gentle rim carving the silhouette, "
             "controlled brass highlights and rich evergreen midtones. ")
    body += ("QUALITY AND RENDER: 2K editorial finish, medium format microcontrast, filmic grain, "
             "tacksharp focal plane, painterly depth. ")
    if text_bearing:
        ws = words or ["DECIDE", "COMMIT", "RISE"]
        body += ("TYPOGRAPHY: spelling-lock each string letter for letter, the words "
                 + " and ".join(f'"{w}"' for w in ws)
                 + " spelled exactly as written, no other lettering anywhere. ")
    else:
        body += "No text, no letters, or words anywhere in the image. "
    # extend with distinct vocabulary until the length target is met (no em dashes)
    vocab = (_VOCAB + " ").split()
    i = 0
    while len(body) < target:
        body += vocab[i % len(vocab)] + " "
        i += 1
    body += ("BRAND STYLE AND NEGATIVE BLOCK: rendered as gallery-grade brand art in deep evergreen. "
             "Do not produce flat, muted, pastel, desaturated, washed out, or low contrast color. "
             "Do not distort hands, eyes, or teeth. Do not add any unintended text.")
    return body


_STAGE_SCENES = [
    ("main", "A calm dawn-lit home office from a low three-quarter angle, one clean desk with a single "
             "open notebook and a cooling cup of coffee, communicating quiet order and one clear first move."),
    ("main", "A close overhead shot of two hands calmly closing a laptop, the screen showing a simple "
             "weekly rhythm rather than a cluttered inbox, communicating relief and control."),
    ("main", "A minimalist flat-lay of a slim workbook, labeled operating-template cards fanned out, and a "
             "brass paperweight on warm oak, premium and uncluttered, a system you can hold and use today."),
    ("main", "A wide aspirational shot of a solo operator at a large window at golden hour, shoulders "
             "relaxed, an orderly workspace reflected faintly behind, the mood of a founder ahead of the day."),
    ("upsell-1", "A dynamic side-lit portrait of a build partner and an operator reviewing a single "
                 "template on a shared screen, both leaning in with focus, a guided sprint underway."),
    ("upsell-1", "A tight macro of a checklist where the first items are firmly checked and one glows as "
                 "the active step, momentum installed step by deliberate step rather than all at once."),
    ("upsell-1", "An energetic split composition showing a stalled idle gear on the dim left and the same "
                 "gear turning brightly on the right, a clean metaphor for an engine going from parked to running."),
    ("upsell-1", "A confident three-quarter portrait of a founder mid-decision at a standing desk, one hand "
                 "on a printed cadence map, the quiet certainty of someone no longer guessing at what matters."),
    ("downsell-1", "A soft empathetic still of an open door with warm light spilling onto a pair of "
                   "headphones and a printed session guide on a low table, a smaller door held open without pressure."),
    ("downsell-1", "A calm evening scene of one person listening to a recorded session on a couch with a "
                   "notebook and a single lamp, self-paced and private, the same road walked patiently."),
    ("high-ticket", "A cinematic editorial wide shot of an architect table at dusk holding a large blueprint "
                    "of an interlocking machine, a single figure studying it with quiet authority, the operator "
                    "who has become the architect of the whole system."),
    ("high-ticket", "A striking two-road composition seen from behind a lone figure at a fork, one path worn "
                    "and dim leading into busy fog, the other rising into clean gold light and open sky, the "
                    "closing metaphor of the sovereign choice."),
]


def _valid_plan(n: int = 12) -> Dict[str, Any]:
    prompts = []
    for i in range(n):
        stage, scene = _STAGE_SCENES[i % len(_STAGE_SCENES)]
        prompts.append({"index": i, "stage": stage, "prompt_text": _rich_prompt(scene)})
    return {"funnel_type": "sales_page_assets", "image_prompt_count": n,
            "primary_brand_color": BRAND_COLOR, "prompts": prompts}


def _valid_ledger() -> Dict[str, Any]:
    return _valid_plan(12)


def _violation_cases():
    def too_short(led):
        led["prompts"][0]["prompt_text"] = "deep evergreen brand-grade hero. No text. Do not distort. " * 4
    def too_long(led):
        led["prompts"][0]["prompt_text"] = _rich_prompt(_STAGE_SCENES[0][1], target=19200) + (_VOCAB * 60)
    def no_grade(led):
        # a long, dense, brand-colored prompt that OMITS every grade-block fingerprint.
        body = (_STAGE_SCENES[0][1] + " The palette is dominated by deep evergreen with warm brass "
                "accents, rich and confident, never muddy, never washed out. No text, no letters, or "
                "words anywhere in the image. ")
        vocab = (_VOCAB + " ").split()
        i = 0
        while len(body) < 5600:
            body += vocab[i % len(vocab)] + " "
            i += 1
        body += "Do not distort hands, eyes, or teeth. Do not add any unintended text."
        led["prompts"][0]["prompt_text"] = body
    def no_brand_color(led):
        led["prompts"][0]["prompt_text"] = _rich_prompt(_STAGE_SCENES[0][1]).replace(
            "deep evergreen", "neutral gray").replace("evergreen", "gray").replace("deep", "flat")
    def no_negative(led):
        led["prompts"][0]["prompt_text"] = _rich_prompt(_STAGE_SCENES[0][1]).replace("Do not ", "Please avoid ")
    def em_dash(led):
        led["prompts"][0]["prompt_text"] = _rich_prompt(_STAGE_SCENES[0][1]) + " a striking subject — the hero."
    def typo_notext(led):
        led["prompts"][0]["prompt_text"] = _rich_prompt(_STAGE_SCENES[0][1]).replace(
            "No text, no letters, or words anywhere in the image. ", "")
    def typo_nolock(led):
        p = _rich_prompt(_STAGE_SCENES[0][1], text_bearing=True, words=["DECIDE", "COMMIT", "RISE"])
        for tok in SPELLING_LOCK_TOKENS:
            p = p.replace(tok, "written")
        led["prompts"][0] = {"index": 0, "stage": "main", "text_bearing": True,
                             "words": ["DECIDE", "COMMIT", "RISE"], "prompt_text": p}
    def density(led):
        led["prompts"][0]["prompt_text"] = (
            _GRADE_BLOCK + " deep evergreen. No text here. Do not add text. "
            + "signature color grade vibrant bold " * 400)

    def _mk(fn):
        led = _valid_ledger()
        fn(led)
        return led

    return [
        ("too_short", "AF-SP56-PROMPT-FLOOR", lambda: _mk(too_short)),
        ("too_long", "AF-SP56-PROMPT-CEILING", lambda: _mk(too_long)),
        ("no_grade_block", "AF-SP56-PROMPT-GRADE", lambda: _mk(no_grade)),
        ("no_brand_color", "AF-SP56-PROMPT-BRANDCOLOR", lambda: _mk(no_brand_color)),
        ("no_negative_block", "AF-SP56-PROMPT-NEGATIVE", lambda: _mk(no_negative)),
        ("em_dash", "AF-SP56-PROMPT-EMDASH", lambda: _mk(em_dash)),
        ("typo_missing_no_text", "AF-SP56-PROMPT-TYPO", lambda: _mk(typo_notext)),
        ("typo_missing_spelling_lock", "AF-SP56-PROMPT-TYPO", lambda: _mk(typo_nolock)),
        ("density_padding", "AF-SP56-PROMPT-DENSITY", lambda: _mk(density)),
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
        description=f"Fail-closed two-floor gate for Sales Page Assets image prompts "
                    f"({PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING} chars). Exit 0 pass, 2 violation, 3 usage.")
    ap.add_argument("--ledger", help="path to image_plan.json / a prompt ledger ('-' reads stdin)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct a VALID fixture (must PASS) + each VIOLATION fixture (must FAIL)")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.ledger:
        print("USAGE ERROR: pass --ledger <image_plan.json> (or --self-test).")
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
