#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_prompt_band.py — fail-closed 5,000-19,000 stripped-char gate for Personal
Video Creator likeness / reference-image prompts (cluster universal-sops/video-production).

A CLONE of the repo's two-floor image-prompt band (56-sales-page-assets/scripts/
prove_sp_prompt_floor.py and 49-signature-funnel/scripts/prove_sf_prompt_floor.py,
themselves cloned from the presentations build_deck.py gate), re-pointed at the
likeness-preservation blocks a talking-head reference prompt MUST carry.

THE FLOORS (all must clear or the prompt is NOT sent to the image provider):
  FLOOR 1 — LENGTH: 5,000 <= stripped chars <= 19,000.   -> AF-PVC-PROMPT-FLOOR / -CEILING
  FLOOR 2 — IDENTITY ANCHOR present ("same person"/"identity source"/"reference").
                                                             -> AF-PVC-PROMPT-IDENTITY
  FLOOR 2 — NEGATIVE BLOCK with a 'Do not ' imperative.      -> AF-PVC-PROMPT-IDENTITY
  FLOOR 2 — DENSITY: >= 220 distinct words (no repeat-padding). -> AF-PVC-PROMPT-IDENTITY

Measured on the STRIPPED text; any self-reported length is IGNORED. Reads either a
prompt ledger JSON ({prompts:[{prompt_text|prompt|text,...}]}) or a directory of
*.txt prompt files (--dir). stdlib only. Exit 0 pass, 2 violation, 3 usage/fail-closed.
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

PROMPT_CHAR_FLOOR = 5000       # AF-PVC-PROMPT-FLOOR
PROMPT_CHAR_CEILING = 19000    # AF-PVC-PROMPT-CEILING
PROMPT_MIN_DISTINCT_WORDS = 220  # AF-PVC-PROMPT-IDENTITY (density)

IDENTITY_ANCHORS = (
    "identity source", "same person", "same individual", "reference image",
    "reference photograph", "identity anchor", "match reference", "as the reference",
)
NEGATIVE_IMPERATIVE = "do not "

_WORD_RE = re.compile(r"[a-z0-9]+")


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


def evaluate_prompt(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []
    who = f"prompt '{record.get('name') or record.get('stage') or record.get('index', '?')}'"
    prompt = _prompt_text(record)
    if not prompt:
        fails.append(("AF-PVC-PROMPT-FLOOR", f"{who}: empty / whitespace-only prompt"))
        return fails

    stripped = _stripped(prompt)
    lc = stripped.lower()
    length = len(stripped)

    if length < PROMPT_CHAR_FLOOR:
        fails.append(("AF-PVC-PROMPT-FLOOR",
                      f"{who}: {length} stripped chars, under the {PROMPT_CHAR_FLOOR} floor — "
                      "a likeness prompt this short cannot carry identity specificity; NOT sent to the image provider"))
    if length > PROMPT_CHAR_CEILING:
        fails.append(("AF-PVC-PROMPT-CEILING",
                      f"{who}: {length} stripped chars, over the {PROMPT_CHAR_CEILING} ceiling"))

    if not any(a in lc for a in IDENTITY_ANCHORS):
        fails.append(("AF-PVC-PROMPT-IDENTITY",
                      f"{who}: no identity-anchor phrase (none of {list(IDENTITY_ANCHORS)}) — "
                      "the prompt must anchor the face to the authorized reference"))

    if NEGATIVE_IMPERATIVE not in lc:
        fails.append(("AF-PVC-PROMPT-IDENTITY",
                      f"{who}: no negative block ('Do not ...' imperative) to suppress face drift"))

    distinct = _distinct_words(stripped)
    if distinct < PROMPT_MIN_DISTINCT_WORDS:
        fails.append(("AF-PVC-PROMPT-IDENTITY",
                      f"{who}: only {distinct} distinct words (< {PROMPT_MIN_DISTINCT_WORDS}) — "
                      "reads as repetition padding, not genuine identity detail"))

    return fails


def verify(records: List[Dict[str, Any]]) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    if not records:
        violations.append(("AF-PVC-PROMPT-FLOOR", "no prompts supplied to the band gate"))
        return violations, []
    for rec in records:
        violations.extend(evaluate_prompt(rec))
    return violations, [f"checked {len(records)} likeness prompt(s) against the "
                        f"{PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING} band"]


def _load_ledger(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    if isinstance(data, dict):
        prompts = data.get("prompts")
        if isinstance(prompts, list):
            return [p for p in prompts if isinstance(p, dict)]
        if _prompt_text(data):
            return [data]
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    return []


def _load_dir(dirpath: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in sorted(Path(dirpath).rglob("*.txt")):
        out.append({"name": p.name, "prompt_text": p.read_text(encoding="utf-8", errors="replace")})
    return out


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print(f"PASS: every likeness prompt clears the two-floor gate ({PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING}).")
        return
    print(f"FAIL: {len(violations)} prompt violation(s) — the failing prompt is NOT sent to the image provider.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# --- self-test fixtures ------------------------------------------------------
_IDENTITY = ("Use the supplied authorized reference images as the IDENTITY SOURCE. "
             "Create a photorealistic vertical 9:16 medium close-up of the SAME person. "
             "Preserve the person's exact facial identity as the reference image. ")
_VOCAB = ("cheekbone jawline brow temple forehead nostril philtrum cupid iris pupil sclera "
          "complexion undertone freckle mole dimple crease symmetry proportion contour hollow "
          "hairline parting strand texture wave curl coil density graying sideburn stubble "
          "wardrobe collar lapel blazer linen wool cotton posture shoulder clavicle neckline "
          "softbox keylight rimlight catchlight bokeh aperture focal microcontrast filmic grain "
          "tacksharp medium format editorial gallery cinematic grade palette chroma luminance "
          "calm alert approachable confident warm measured assured direct eyeline camera level "
          "background backdrop seamless studio window dawn dusk neutral charcoal ivory brass "
          "preserve unchanged consistent identical match geometry generic beautify alter "
          "porcelain olive tan ebony fair rosy warm cool matte radiant dewy smooth weathered "
          "almond round hooded upturned downturned monolid lash mascara liner gaze squint "
          "straight aquiline button broad narrow pointed rounded wide thin full plump "
          "arched bushy groomed tapered trimmed stubbled clean angular oval heart diamond "
          "square oblong narrow wide high low flat prominent subtle defined soft sharp "
          "natural groomed tousled sleek braided pinned cropped long short medium layered "
          "auburn chestnut blonde platinum brunette silver salt pepper highlighted balayage "
          "linen blazer cardigan turtleneck oxford denim silk cashmere tweed flannel jersey "
          "navy burgundy emerald mustard sage rust cream black white gray beige camel "
          "windowlight golden hour overcast diffused directional ambient practical tungsten "
          "daylight balanced kelvin shadow highlight midtone specular diffuse gradient falloff "
          "rule thirds centered negative space leading line depth layer foreground midground "
          "environment context office desk shelf plant book lamp chair couch table surface "
          "minimal uncluttered premium polished refined sophisticated understated bold striking "
          "authentic candid trustworthy relatable authoritative executive founder operator "
          "conversation speaking talking articulating enunciating phrasing cadence rhythm "
          "blink saccade microexpression nod tilt lean turn orient face forward frontal "
          "photoreal hyperreal lifelike believable plausible convincing accurate faithful true")


def _rich(target: int = 5600, anchor: bool = True, negative: bool = True) -> str:
    body = _IDENTITY if anchor else "Create a photorealistic vertical 9:19 close-up of a person. "
    vocab = (_VOCAB + " ").split()
    i = 0
    while len(body) < target:
        body += vocab[i % len(vocab)] + " "
        i += 1
    if negative:
        body += ("Do not produce a different person, identity drift, face morph, swapped face, "
                 "altered features, asymmetric eyes, changed teeth, changed hairline, age change, "
                 "skin-tone change, text, watermark, extra people, or an obstructed mouth.")
    return body


def run_self_test() -> int:
    ok = True
    cases = [
        ("valid", [], [{"name": "front_neutral", "prompt_text": _rich()}]),
        ("too_short", ["AF-PVC-PROMPT-FLOOR"], [{"name": "short", "prompt_text": _rich(200)}]),
        ("too_long", ["AF-PVC-PROMPT-CEILING"], [{"name": "long", "prompt_text": _rich(19200)}]),
        ("no_anchor", ["AF-PVC-PROMPT-IDENTITY"], [{"name": "noanchor", "prompt_text": _rich(anchor=False)}]),
        ("no_negative", ["AF-PVC-PROMPT-IDENTITY"], [{"name": "noneg", "prompt_text": _rich(negative=False)}]),
        ("empty", ["AF-PVC-PROMPT-FLOOR"], [{"name": "empty", "prompt_text": "   "}]),
    ]
    for name, expected, recs in cases:
        vio, _ = verify(recs)
        codes = {c for c, _ in vio}
        if not expected and vio:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' produced {sorted(codes)} (expected PASS).")
        elif expected and not (set(expected) & codes):
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            print(f"SELF-TEST ok: '{name}' -> {'PASS' if not vio else sorted(codes)}.")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed 5,000-19,000 band for likeness prompts.")
    ap.add_argument("--ledger", help="prompt ledger JSON ('-' reads stdin)")
    ap.add_argument("--dir", help="directory of *.txt prompt files")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    try:
        if args.ledger:
            if args.ledger == "-":
                data = json.loads(sys.stdin.read())
                records = data.get("prompts", [data]) if isinstance(data, dict) else data
            else:
                records = _load_ledger(args.ledger)
        elif args.dir:
            records = _load_dir(args.dir)
        else:
            print("USAGE ERROR: pass --ledger <json> | --dir <path> | --self-test.")
            return EXIT_FAILCLOSED
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return EXIT_FAILCLOSED

    violations, notes = verify(records)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
