#!/usr/bin/env python3
"""
diu_validator.py — DETERMINISTIC DESIGN-INTELLIGENCE-UNIT (DIU) ENFORCEMENT GATE.

================================================================================
Skill 45's binding gates were prose-only (prompt char tiers, the SOP-DIU-611
"coded hard stop" routing interlock, the >=4.0 fidelity gate + 3-strike loop).
Prose is not a gate. This is OUR stdlib-only code (no third-party deps) that turns
those three rules into MECHANICAL gates with receipts on disk and exit codes —
mirroring Skill 47's executive_producer.py pattern (deterministic, fail-soft
never; a violation is a hard non-zero exit an agent cannot narrate past).
================================================================================

WHAT IT ENFORCES (three sub-commands)

  prompt-caps  — PROMPT-LENGTH CAPS (MODEL-SPECS.md §"tier table").
      SHORT <= 500, MEDIUM <= 2,800, LONG <= 19,000 characters. An assembled
      prompt over its tier cap is a HARD FAIL (exit 3) — the operator must fall
      back a tier (the MODEL-SPECS auto-fallback rule) rather than silently
      truncate at the endpoint.

  prompt-band  — GRAPHICS IMAGE PROTOCOL (GIP) PROMPT BANDS (_system/prompt-bands.json).
      The MAX-only cap tiers were necessary but not SUFFICIENT: a one-line prompt
      could reach Kie.ai/GPT-Image 2 unchallenged (no MIN floor anywhere in graphics).
      This is the graphics analogue of the Presentations 9,000-char floor gate. A
      prompt is checked against its asset-class BAND:
        * length below the band MIN  -> HARD FAIL (exit 3, AF-GIP-PROMPT-FLOOR):
          NOT submitted, NOT rendered — re-author (never truncate up to the floor).
        * length above the band MAX  -> HARD FAIL (exit 3, AF-DIU-PROMPT-CAP): fall
          back a tier per MODEL-SPECS, do not ship a prompt the endpoint truncates.
        * a QUALITY defect (independent of length, exactly like AF-P13/P14/P-DENSITY)
          -> HARD FAIL (exit 6, AF-GIP-PROMPT-QUALITY): the negative block must name
          >= 6 of the 8 defect classes; a text-bearing band requires a per-string
          spelling-lock and the verbatim copy baked in; distinct-word density must
          clear the band floor (anti-padding); and when style reference images are
          attached (--style-ref) the STYLE-REFERENCE-ONLY directive is mandatory
          (MODEL-SPECS §4). Clearing the floor is NECESSARY, never SUFFICIENT.
          Two text-bearing bands exist because one endpoint cannot serve both:
          `text_bearing_long` (5,000-19,000) targets GPT-Image 2 T2I/I2I; the
          mandatory Ideogram V3 DESIGN quote-card/text-led route (see
          social-media-designs/_RULES.md) targets `text_bearing_medium`
          (1,600-4,500) instead, sized to Ideogram's own verified 5,000-char API
          cap (MODEL-SPECS.md) — GK-20 band<->routing reconciliation.

  route-check  — DIU ROUTING INTERLOCK (SOP-DIU-611 §D.1 "coded hard stop").
      An audience / webinar / funnel / sales / virtual-event deck CANNOT proceed on
      the DIU Style Rotation Engine (strategy-(b) pipeline). Any such deck routes to
      the Presentations department. Attempting to run one through the DIU is an
      architecture violation → HARD ABORT (exit 2). This is the code behind the
      prose "mechanical gate" the SOP claims.

  consent-check — CONSENT + MINOR + PII GATE (PHOTO-SHOOT-SOP.md §1, fail-closed).
      Real-person likeness generation requires documented+dated consent, an
      attested-adult subject (Minors = HARD NO), and an at-rest protection
      attestation on the biometric IDENTITY store. Any missing/negative/ambiguous
      field, or an absent IDENTITY file, is a HARD FAIL (exit 4) — generation must
      not proceed. Converts the prose consent rule into a coded hard stop.

  fidelity     — FIDELITY-SCORE RECEIPT + 3-STRIKE COUNTER (TEST-PROTOCOL.md §5).
      A card reaches `production` only when: average across all 12 dimensions
      >= 4.0 AND no single dimension < 3 AND ZERO hard-rule violations (one
      violation = automatic fail). Every test appends a RECEIPT to
      working/checkpoints/diu_fidelity_receipts.json (institutional memory —
      receipts are never deleted). The gate then reads the receipt history and
      counts CONSECUTIVE failures per (card, dimension): three consecutive
      failures on the same dimension = ESCALATE to the Chief Design Officer
      (exit 5) — "do not silently keep burning generations." A passing test on a
      dimension resets its streak.

EXIT CODES
    0 — pass (within cap / legal route / consent OK / fidelity pass, no 3rd strike;
        prompt-band: within [MIN, MAX] AND clears every quality tooth).
    2 — routing-interlock violation (AF-DIU-ROUTING-INTERLOCK) or usage error.
    3 — prompt over the tier cap (AF-DIU-PROMPT-CAP) OR under the band floor
        (AF-GIP-PROMPT-FLOOR) OR a fidelity FAIL that has not yet reached the 3rd
        consecutive strike.
    4 — consent/minor/PII gate failure (AF-DIU-CONSENT): consent unconfirmed, a
        minor, or the biometric IDENTITY store is unprotected — fail closed.
    5 — 3-strike escalation (AF-DIU-3-STRIKE): a dimension failed 3 consecutive
        times — escalate to CDO with the receipt evidence.
    6 — prompt-band QUALITY failure (AF-GIP-PROMPT-QUALITY): the length cleared the
        band but a quality tooth (8-class negative block / spelling-lock / verbatim
        copy / density / style-reference-only) did not — re-author, do not submit.

USAGE
    python3 diu_validator.py prompt-caps --tier LONG --prompt-file assembled.txt
    python3 diu_validator.py prompt-caps --tier SHORT --prompt "…inline…"
    python3 diu_validator.py prompt-band --band text_bearing_long \
                --prompt-file assembled.txt --copy "Stop Guessing." [--style-ref]
    python3 diu_validator.py prompt-band --band text_bearing_medium \
                --prompt-file assembled.txt --copy "Stop Guessing." [--style-ref]
    python3 diu_validator.py prompt-band --band medium --prompt "…inline…" [--run-dir RUN]
    python3 diu_validator.py route-check --deck-kind webinar
    python3 diu_validator.py fidelity --run-dir RUN --card-id FB-003 \
                --scores-file scores.json [--hard-rule-violation "text on face"]

This is a SCRIPT, not a manifest role/SOP. It has zero third-party imports so it
runs on any box with a stock Python 3.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# 1) PROMPT-LENGTH CAPS — MODEL-SPECS.md tier table (SHORT/MEDIUM/LONG).
# ---------------------------------------------------------------------------
TIER_CAPS = {
    "SHORT": 500,
    "MEDIUM": 2800,
    "LONG": 19000,
}


def cmd_prompt_caps(args) -> int:
    tier = (args.tier or "").strip().upper()
    if tier not in TIER_CAPS:
        print(f"FATAL: --tier must be one of {sorted(TIER_CAPS)} (got {args.tier!r}).",
              file=sys.stderr)
        return 2
    if args.prompt_file:
        p = Path(args.prompt_file)
        if not p.is_file():
            print(f"FATAL: --prompt-file not found: {p}", file=sys.stderr)
            return 2
        prompt = p.read_text(encoding="utf-8")
    elif args.prompt is not None:
        prompt = args.prompt
    else:
        print("FATAL: pass --prompt-file PATH or --prompt STR.", file=sys.stderr)
        return 2

    cap = TIER_CAPS[tier]
    n = len(prompt)
    if n > cap:
        over = n - cap
        print("!" * 78, file=sys.stderr)
        print(f"FATAL AF-DIU-PROMPT-CAP: assembled {tier}-tier prompt is {n} chars, "
              f"OVER the {cap}-char cap by {over}. Per MODEL-SPECS.md, fall back one "
              f"tier (LONG->MEDIUM->SHORT) and re-assemble — do NOT ship a prompt that "
              f"the endpoint will silently truncate.", file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        return 3
    print(f"OK: {tier}-tier prompt is {n}/{cap} chars (within cap).")
    return 0


# ---------------------------------------------------------------------------
# 2) DIU ROUTING INTERLOCK — SOP-DIU-611 §D.1 (coded hard stop).
# ---------------------------------------------------------------------------
# Deck kinds that MUST route to the Presentations department and CANNOT run on
# the DIU Style Rotation Engine. Matched case-insensitively as whole words so
# "webinar-deck", "virtual event", "sales funnel", "audience deck" all trip it.
_INTERLOCK_TERMS = [
    "webinar",
    "funnel",
    "sales",          # SKILL.md §"NOT owned by Skill 45" names sales decks; a bare
                      # "sales deck" must trip the interlock, not only "sales funnel".
    "audience",
    "virtual event",
    "virtual-event",
]
# DIU-legal deck kinds (informational — the Rotation Engine's own domain).
_DIU_LEGAL = ["strategy", "brand", "campaign", "pitch", "portfolio", "internal"]


def cmd_route_check(args) -> int:
    kind = (args.deck_kind or "").strip().lower()
    if not kind:
        print("FATAL: --deck-kind is required (e.g. webinar, brand, campaign).",
              file=sys.stderr)
        return 2
    for term in _INTERLOCK_TERMS:
        if re.search(r"(?:^|[^a-z])" + re.escape(term) + r"(?:$|[^a-z])", kind):
            print("!" * 78, file=sys.stderr)
            print(f"FATAL AF-DIU-ROUTING-INTERLOCK: a {args.deck_kind!r} deck matches a "
                  f"CLIENT-WEBINAR-DECK-SOP archetype ({term!r}) and CANNOT proceed on the "
                  f"DIU Style Rotation Engine (strategy-(b) pipeline). Per SOP-DIU-611 §D.1 "
                  f"this is a mechanical gate, not a preference: HALT the DIU workflow and "
                  f"route to CDO for forwarding to the Presentations Director. Proceeding "
                  f"would assemble the deck from bare backgrounds + overlay text boxes — an "
                  f"AUTO-FAIL at final QC.", file=sys.stderr)
            print("!" * 78, file=sys.stderr)
            return 2
    print(f"OK: deck-kind {args.deck_kind!r} is DIU-routable "
          f"(no CLIENT-WEBINAR-DECK-SOP archetype match). Rotation Engine may proceed.")
    return 0


# ---------------------------------------------------------------------------
# 2b) CONSENT + MINOR + PII GATE — PHOTO-SHOOT-SOP.md §1 (fail-closed).
# ---------------------------------------------------------------------------
# Generating a REAL person's likeness (personal-photo-shoot) is gated on documented
# consent, an ABSOLUTE minor prohibition (Minors = HARD NO), and protection of the
# biometric IDENTITY store. These were prose-only rules an agent could proceed past.
# This is the coded hard stop: it reads the client's IDENTITY.md and FAILS CLOSED
# (exit 4, AF-DIU-CONSENT) on ANY missing / negative / ambiguous field, or if the file
# is absent. Consent that "cannot be confirmed" must block, never default open.
_CONSENT_YES = {"granted", "yes", "true", "documented", "on-file", "on_file", "confirmed"}
_NOT_MINOR_TOK = {"no", "false", "adult", "18+", "over-18", "over_18"}
_MINOR_TOK = {"yes", "true", "minor", "under-18", "under_18"}
_ADULT_YES = {"yes", "true", "adult", "18+", "over-18", "over_18", "confirmed"}
_PROTECT_OK = {"encrypted-at-rest", "encrypted_at_rest", "encrypted", "restricted",
               "redacted", "access-restricted", "access_restricted"}


def _scan_field(text, keys):
    """Return the lowercased value of the first `key: value` line whose key exactly
    matches one of `keys` (case-insensitive; tolerant of markdown bullets/bold/backticks)."""
    keyset = set(keys)
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*# ").strip()
        m = re.match(r"[*_`\s]*([A-Za-z][A-Za-z0-9 _/-]*?)[*_`\s]*:\s*(.+?)\s*$", line)
        if not m:
            continue
        k = m.group(1).strip().lower().replace(" ", "_").replace("-", "_")
        if k in keyset:
            return m.group(2).strip().lower().strip("*_` ")
    return None


def cmd_consent_check(args) -> int:
    p = Path(args.identity_file)
    problems = []
    if not p.is_file():
        print("!" * 78, file=sys.stderr)
        print(f"FATAL AF-DIU-CONSENT: IDENTITY file not found: {p}. Consent CANNOT be "
              f"confirmed -> fail closed; do NOT generate this person's likeness.",
              file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        return 4
    text = p.read_text(encoding="utf-8")

    # (1) Documented consent + a consent date.
    consent = _scan_field(text, ["consent", "consent_status"])
    consent_toks = set(re.split(r"[^a-z0-9+]+", consent)) if consent else set()
    if not (consent_toks & _CONSENT_YES):
        problems.append(f"consent status missing/negative (got {consent!r}); need an affirmative "
                        f"'Consent: granted'")
    consent_date = _scan_field(text, ["consent_date"])
    if not (consent_date and re.search(r"\d{4}-\d{2}-\d{2}", consent_date)):
        problems.append("no consent date present (need 'Consent date: YYYY-MM-DD')")

    # (2) Minor gate — HARD NO. Fail closed unless the subject is EXPLICITLY attested adult.
    minor = _scan_field(text, ["minor", "subject_is_minor", "is_minor"])
    adult = _scan_field(text, ["adult", "age_verified_adult", "age_confirmed_adult"])
    minor_tok = minor.split()[0] if minor else ""
    adult_tok = adult.split()[0] if adult else ""
    is_minor = (minor_tok in _MINOR_TOK) or (adult_tok in {"no", "false"})
    is_adult = (minor_tok in _NOT_MINOR_TOK) or (adult_tok in _ADULT_YES)
    if is_minor:
        problems.append("subject is flagged a MINOR -> HARD NO (PHOTO-SHOOT-SOP §1): likeness "
                        "generation is PROHIBITED without explicit owner + legal sign-off")
    elif not is_adult:
        problems.append("subject age not attested adult (need 'Minor: no' or "
                        "'Age verified adult: yes'); minors are HARD NO -> fail closed")

    # (3) Biometric PII protection — the IDENTITY store holds likeness descriptors; require an
    # explicit at-rest protection attestation so raw biometric PII is never assumed plaintext-OK.
    protection = _scan_field(text, ["storage_protection", "storage", "identity_storage"])
    protect_toks = set(re.split(r"[^a-z0-9+]+", protection)) if protection else set()
    if not (protect_toks & _PROTECT_OK):
        problems.append(f"IDENTITY biometric store protection not attested (got {protection!r}); "
                        f"need 'Storage protection: encrypted-at-rest' — descriptors must not be "
                        f"stored plaintext")

    if problems:
        print("!" * 78, file=sys.stderr)
        print(f"FATAL AF-DIU-CONSENT: {p} FAILS the fail-closed consent/minor/PII gate "
              f"(PHOTO-SHOOT-SOP §1). Do NOT generate this person's likeness:", file=sys.stderr)
        for i, pr in enumerate(problems, 1):
            print(f"  {i}. {pr}", file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        return 4
    print(f"OK: consent documented + dated, subject attested adult, IDENTITY store protection "
          f"declared -> likeness generation may proceed ({p}).")
    return 0


# ---------------------------------------------------------------------------
# 3) FIDELITY RECEIPT + 3-STRIKE — TEST-PROTOCOL.md §5.
# ---------------------------------------------------------------------------
# The 12 style dimensions the RAW PNG is graded on.
DIMENSIONS = [
    "render", "composition", "subject", "color", "grading", "lighting",
    "typography", "layering", "subject_background", "negative_space",
    "workflow", "unity",
]
FIDELITY_AVG_MIN = 4.0     # average across all 12 dimensions
FIDELITY_DIM_MIN = 3       # no single dimension may score below this
STRIKE_LIMIT = 3           # 3 consecutive fails on one dimension -> escalate


def _receipts_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "diu_fidelity_receipts.json"


def _load_receipts(run_dir: Path) -> list:
    p = _receipts_path(run_dir)
    if not p.exists():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(obj, dict):
        obj = obj.get("receipts", [])
    return obj if isinstance(obj, list) else []


def _normalize_scores(raw) -> dict:
    """Accept {dim: score} (extra/aliased keys tolerated) or an ordered list of
    12 numbers. Returns {dim: int} for the canonical 12 dimensions."""
    scores = {}
    if isinstance(raw, list):
        if len(raw) != len(DIMENSIONS):
            raise ValueError(
                f"score list has {len(raw)} entries; expected {len(DIMENSIONS)} "
                f"(one per dimension, in order: {DIMENSIONS}).")
        for dim, val in zip(DIMENSIONS, raw):
            scores[dim] = int(val)
        return scores
    if isinstance(raw, dict):
        def _key(k):
            return str(k).strip().lower().replace("-", "_").replace(" ", "_")
        by_norm = {_key(k): v for k, v in raw.items()}
        missing = [d for d in DIMENSIONS if d not in by_norm]
        if missing:
            raise ValueError(f"scores missing dimension(s): {missing}. "
                             f"All 12 required: {DIMENSIONS}.")
        for dim in DIMENSIONS:
            scores[dim] = int(by_norm[dim])
        return scores
    raise ValueError("scores must be a JSON object {dim: score} or a list of 12 numbers.")


def cmd_fidelity(args) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir not found: {run_dir}", file=sys.stderr)
        return 2
    card_id = (args.card_id or "").strip()
    if not card_id:
        print("FATAL: --card-id is required.", file=sys.stderr)
        return 2

    if args.scores_file:
        sp = Path(args.scores_file)
        if not sp.is_file():
            print(f"FATAL: --scores-file not found: {sp}", file=sys.stderr)
            return 2
        raw = json.loads(sp.read_text(encoding="utf-8"))
    elif args.scores:
        raw = json.loads(args.scores)
    else:
        print("FATAL: pass --scores-file PATH or --scores JSON.", file=sys.stderr)
        return 2

    try:
        scores = _normalize_scores(raw)
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    for dim, val in scores.items():
        if val < 1 or val > 5:
            print(f"FATAL: dimension {dim!r} score {val} out of range 1-5.",
                  file=sys.stderr)
            return 2

    hard_violations = [v for v in (args.hard_rule_violation or []) if str(v).strip()]
    avg = round(sum(scores.values()) / len(scores), 3)
    below_min = sorted([d for d, v in scores.items() if v < FIDELITY_DIM_MIN])
    # A dimension "fails" this test if it is below the floor. Hard-rule violations
    # fail the WHOLE test regardless of scores (they are not per-dimension).
    failed_dims = below_min
    passed = (avg >= FIDELITY_AVG_MIN and not below_min and not hard_violations)

    receipt = {
        "card_id": card_id,
        "scores": scores,
        "avg": avg,
        "below_min_dimensions": below_min,
        "hard_rule_violations": hard_violations,
        "failed_dimensions": failed_dims,
        "passed": passed,
        "avg_min": FIDELITY_AVG_MIN,
        "dim_min": FIDELITY_DIM_MIN,
        "tested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    # Append (never clobber) — receipts are the card's institutional memory.
    prior = _load_receipts(run_dir)
    ledger = prior + [receipt]
    rp = _receipts_path(run_dir)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps({"receipts": ledger}, indent=2) + "\n", encoding="utf-8")

    # 3-strike counter — consecutive fails per dimension for THIS card, across the
    # full receipt history (including this one). A pass on a dimension resets it.
    streaks = {d: 0 for d in DIMENSIONS}
    max_streak = 0
    escalate_dims = []
    for rec in ledger:
        if rec.get("card_id") != card_id:
            continue
        rec_failed = set(rec.get("failed_dimensions") or [])
        # A hard-rule violation fails EVERY graded dimension for streak purposes
        # (the whole PNG is rejected), so a repeated hard-rule miss also escalates.
        if rec.get("hard_rule_violations"):
            rec_failed = set(DIMENSIONS)
        for d in DIMENSIONS:
            if d in rec_failed:
                streaks[d] += 1
                if streaks[d] >= STRIKE_LIMIT and d not in escalate_dims:
                    escalate_dims.append(d)
            else:
                streaks[d] = 0
        max_streak = max(max_streak, max(streaks.values()))

    print(f"=== FIDELITY TEST — card {card_id} ===")
    print(f"  avg={avg} (min {FIDELITY_AVG_MIN})  below-floor dims={below_min or 'none'}  "
          f"hard-rule violations={hard_violations or 'none'}")
    print(f"  receipt appended -> {rp}")

    if escalate_dims:
        print("!" * 78, file=sys.stderr)
        print(f"ESCALATE AF-DIU-3-STRIKE: card {card_id} has {STRIKE_LIMIT} consecutive "
              f"failed fidelity tests on dimension(s) {sorted(escalate_dims)}. Per "
              f"TEST-PROTOCOL.md §5, STOP patching and escalate to the Chief Design "
              f"Officer with the receipt evidence at {rp} — do not silently keep burning "
              f"generations. CDO decides: retire the card, escalate to owner, or authorize "
              f"a different approach.", file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        return 5

    if not passed:
        print(f"FAIL AF-DIU-FIDELITY: card {card_id} did not reach production "
              f"(need avg>={FIDELITY_AVG_MIN}, no dim<{FIDELITY_DIM_MIN}, zero hard-rule "
              f"violations). Patch the failed dimension(s) and re-run only the failed "
              f"test. Consecutive-fail streak so far: {max_streak}/{STRIKE_LIMIT}.",
              file=sys.stderr)
        return 3

    print(f"PASS: card {card_id} meets production fidelity (avg {avg}, no floor breach, "
          f"no hard-rule violation).")
    return 0


# ---------------------------------------------------------------------------
# 4) GRAPHICS IMAGE PROTOCOL (GIP) PROMPT BANDS — _system/prompt-bands.json.
# ---------------------------------------------------------------------------
# The MAX-only cap tiers (cmd_prompt_caps) let a one-line prompt reach the paid API
# unchallenged: there was NO minimum floor anywhere in graphics. This is the graphics
# analogue of the Presentations 9,000-char floor + quality gate (build_deck.py /
# prompt_gate.py), driven by the per-asset-class bands in prompt-bands.json. The gate
# is TWO independent halves, mirroring presentations exactly:
#   (1) LENGTH — a HARD MIN floor (AF-GIP-PROMPT-FLOOR) + the MAX cap (AF-DIU-PROMPT-CAP).
#   (2) QUALITY — length-independent teeth (AF-GIP-PROMPT-QUALITY): the 8-class negative
#       block, per-string spelling-lock + verbatim copy (text-bearing bands), distinct-word
#       density, and the mandatory style-reference-only directive when refs are attached.
# Clearing the floor is NECESSARY, never SUFFICIENT.

# The default location of the bands config, relative to this script (skill 45 layout:
# scripts/diu_validator.py + library/_system/prompt-bands.json). A --bands-file override
# exists for tests; the on-box runtime always uses the shipped default.
_BANDS_PATH = Path(__file__).resolve().parent.parent / "library" / "_system" / "prompt-bands.json"

# AF-GIP-QUALITY tokens — the EIGHT mandatory negative-block defect CLASSES. Adapted from
# the presentations 8-class negative block (build_deck.py / prompt_gate NEGATIVE_BLOCK_CLASS_
# TOKENS). A class is "named" when >=1 of its tolerant tokens is present in the prompt. The
# band gate requires the negative block to name at least GIP_MIN_NEGATIVE_CLASSES of the 8.
GIP_NEGATIVE_CLASS_TOKENS = {
    "garbled/misspelled text": [
        "misspell", "garble", "letter-for-letter", "letter for letter",
        "render every quoted", "exactly as written", "render every letter", "no invented text"],
    "logo mutation": [
        "logo", "monogram", "tagline lockup", "reference mark", "redraw",
        "redesign", "recolor", "restyle", "reinterpret", "invent a"],
    "anatomical artifacts": [
        "finger", "fused hand", "malformed", "anatom", "distorted facial",
        "mismatched eye", "asymmetric eye", "distorted teeth", "extra limb", "body proportion"],
    "contrast/legibility": [
        "busy", "cluttered", "high-detail background", "compete", "behind any text",
        "text zone", "scrim", "legib", "negative space", "contrast"],
    "placeholder/bracket tokens": [
        "bracketed token", "square bracket", "placeholder", "tbd", "build note",
        "to supply", "pending token", "insert token", "owner to confirm"],
    "demographic default / skin-tone fidelity": [
        "demographic", "skin tone", "skin-tone", "representation", "lighten",
        "ashen", "desaturate", "mono-cast", "mono cast", "deep skin"],
    "watermark / universal baseline": [
        "watermark", "emoji", "clipart", "default font", "calibri", "arial",
        "times new roman", "system default", "ui artifact", "user-interface"],
    "style-drift": [
        "style drift", "style-drift", "off-brand", "off brand", "off-palette",
        "off palette", "deviate from the style", "inconsistent style", "outside the style card",
        "outside the brand", "palette drift"],
}
GIP_MIN_NEGATIVE_CLASSES = 6  # per spec: the negative block must name >= 6 of the 8 classes.

# Per-string SPELLING-LOCK marker tokens (text-bearing bands). At least one must be present.
GIP_SPELLING_LOCK_TOKENS = [
    "spelling-lock", "spelling lock", "letter-for-letter", "letter for letter",
    "render this exact string", "reads exactly", "render every quoted text string exactly",
    "spelled exactly", "exact spelling", "render every letter", "correctly spelled",
]

# STYLE-REFERENCE-ONLY directive tokens (mandatory whenever refs are attached for style —
# MODEL-SPECS §4 "MANDATORY … applies equally to GPT-Image 2 I2I").
GIP_STYLE_REF_ONLY_TOKENS = [
    "style reference only", "style-reference only", "style-reference-only",
    "only as style reference", "as style reference", "only for style reference",
    "do not copy their subjects", "do not copy their faces", "do not copy their text",
    "reference for color grading",
]

# Forbidden hardcoded demographic-default landmines (AF-R3, ported from prompt_gate). A prompt
# must never bake in a default demographic split — representation comes from the client's
# captured audience/casting ledger.
GIP_FORBIDDEN_DEMOGRAPHIC_DEFAULTS = [
    "60/30/10", "60-30-10", "default demographic", "default ethnicity", "default race",
    "default skin tone", "default skin-tone", "standard demographic mix",
    "standard representation mix", "assume the audience is", "assumed demographic",
    "inferred demographic", "system default demographic",
]

_GIP_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'\-]+")


def _gip_norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def load_bands(bands_file=None) -> dict:
    """Load and validate prompt-bands.json. Returns the {band_id: band} mapping.
    Raises FileNotFoundError / ValueError (fail loud — a missing/broken bands config is a
    hard stop, never a silent default)."""
    p = Path(bands_file) if bands_file else _BANDS_PATH
    if not p.is_file():
        raise FileNotFoundError(
            f"prompt-bands.json not found at {p} — the GIP band config is required "
            "(ship 45-design-intelligence-library/library/_system/prompt-bands.json).")
    obj = json.loads(p.read_text(encoding="utf-8"))
    bands = obj.get("bands") if isinstance(obj, dict) else None
    if not isinstance(bands, dict) or not bands:
        raise ValueError(f"{p}: no 'bands' object — malformed prompt-bands config.")
    return bands


def _resolve_band(band_id: str, bands: dict) -> dict:
    key = (band_id or "").strip()
    if key not in bands:
        raise ValueError(
            f"unknown band {band_id!r} — valid bands: {sorted(bands)}. "
            "Declare 'ASSET: <class> | BAND: <band-id>' on the prompt's first line (SOP-GIP-01).")
    return bands[key]


def _is_text_bearing(band: dict) -> bool:
    return bool(band.get("text_bearing"))


def band_length_problems(prompt_text: str, band: dict, band_id: str) -> list:
    """LENGTH half. Returns a list of (af_code, message). AF-GIP-PROMPT-FLOOR when under the
    band MIN; AF-DIU-PROMPT-CAP when over the band MAX. Empty when within [MIN, MAX]."""
    problems = []
    stripped = prompt_text.strip()
    n = len(stripped)
    mn = int(band.get("min", 0))
    mx = int(band.get("max", 0))
    if not stripped:
        problems.append(("AF-GIP-PROMPT-FLOOR",
                         f"prompt is empty / whitespace-only — carries none of the mandatory "
                         f"per-asset {band_id} spec (band floor {mn})."))
        return problems
    if n < mn:
        problems.append(("AF-GIP-PROMPT-FLOOR",
                         f"prompt is {n} chars, UNDER the {band_id} band floor of {mn}. Too short "
                         f"to carry the rich per-asset spec — NOT submitted, NOT rendered. "
                         f"Re-author (never truncate up to the floor)."))
    if mx and n > mx:
        problems.append(("AF-DIU-PROMPT-CAP",
                         f"prompt is {n} chars, OVER the {band_id} band cap of {mx}. Fall back a "
                         f"tier per MODEL-SPECS — do not ship a prompt the endpoint truncates."))
    return problems


def band_quality_problems(prompt_text: str, band: dict, band_id: str,
                          copy_val=None, style_ref: bool = False) -> list:
    """QUALITY half (length-independent, AF-GIP-PROMPT-QUALITY). Returns a list of fatal
    problem strings (empty = clears every quality tooth). Teeth:
      * the negative block must name >= GIP_MIN_NEGATIVE_CLASSES of the 8 defect classes;
      * a text-bearing band requires a per-string spelling-lock directive AND the verbatim
        copy baked into the body (when copy is supplied);
      * distinct-word density must clear the band's min_distinct_words floor (anti-padding);
      * when style refs are attached (style_ref), the style-reference-only directive is
        MANDATORY (MODEL-SPECS §4);
      * no forbidden hardcoded demographic-default landmine (AF-R3)."""
    prompt_lc = prompt_text.lower()
    problems = []

    # (a) 8-class negative block coverage.
    named = [cls for cls, toks in GIP_NEGATIVE_CLASS_TOKENS.items()
             if any(t in prompt_lc for t in toks)]
    if len(named) < GIP_MIN_NEGATIVE_CLASSES:
        missing = [c for c in GIP_NEGATIVE_CLASS_TOKENS if c not in named]
        problems.append(
            f"AF-GIP-PROMPT-QUALITY: negative block names only {len(named)}/8 defect classes "
            f"(floor {GIP_MIN_NEGATIVE_CLASSES}); a final-paragraph 'Do not…' block must cover "
            f"at least {GIP_MIN_NEGATIVE_CLASSES}. Not yet named: {', '.join(missing)}.")

    # (b) distinct-word density (anti paste-repetition padding).
    floor_words = int(band.get("min_distinct_words", 0))
    distinct = len(set(_GIP_WORD_RE.findall(prompt_lc)))
    if floor_words and distinct < floor_words:
        problems.append(
            f"AF-GIP-PROMPT-QUALITY: only {distinct} distinct words (band floor {floor_words}) "
            "— a long file with few distinct words is paste-repetition padding, not a rich spec.")

    # (c) text-bearing bands: spelling-lock + verbatim copy baked in.
    if _is_text_bearing(band):
        if not any(t in prompt_lc for t in GIP_SPELLING_LOCK_TOKENS):
            problems.append(
                "AF-GIP-PROMPT-QUALITY: text-bearing band but NO per-string spelling-lock "
                "directive (e.g. 'render this exact string, letter-for-letter, correctly "
                "spelled') — every verbatim on-image string must be spelling-locked (SOP-GIP-01 "
                "element 5). A verbatim string without its lock is an AUTO-FAIL.")
        if copy_val is not None:
            strings = copy_val if isinstance(copy_val, list) else [copy_val]
            prompt_norm = _gip_norm_ws(prompt_text)
            missing_copy = []
            for c in strings:
                cn = _gip_norm_ws(c)
                if len(cn) < 3:
                    continue
                if cn not in prompt_norm:
                    missing_copy.append(str(c) if len(str(c)) <= 60 else str(c)[:57] + "...")
            if missing_copy:
                problems.append(
                    "AF-GIP-PROMPT-QUALITY: the asset's exact copy is NOT baked into the prompt "
                    "body verbatim (kie.ai must bake the words, never overlaid): "
                    + " | ".join(missing_copy))

    # (d) style-reference-only directive when refs attached for style.
    if style_ref and not any(t in prompt_lc for t in GIP_STYLE_REF_ONLY_TOKENS):
        problems.append(
            "AF-GIP-PROMPT-QUALITY: style reference image(s) attached (--style-ref) but the "
            "STYLE-REFERENCE-ONLY directive is absent (MODEL-SPECS §4, MANDATORY for GPT-Image 2 "
            "I2I / Nano Banana 2): add 'Use the attached images only as style reference for color "
            "grading, lighting, and composition — do not copy their subjects, faces, or text.'")

    # (e) forbidden hardcoded demographic-default landmine (AF-R3).
    for landmine in GIP_FORBIDDEN_DEMOGRAPHIC_DEFAULTS:
        if landmine.lower() in prompt_lc:
            problems.append(
                f"AF-GIP-PROMPT-QUALITY: forbidden hardcoded demographic default {landmine!r} "
                "(AF-R3) — representation must come from the client's captured audience / casting "
                "ledger, never a baked-in default split.")
            break

    return problems


def band_problems(prompt_text: str, band: dict, band_id: str,
                  copy_val=None, style_ref: bool = False) -> dict:
    """Accumulating (non-raising) form used by the prover and the CLI. Returns
    {'length': [(code, msg), ...], 'quality': [msg, ...]} — empty lists = clears the whole
    band gate."""
    return {
        "length": band_length_problems(prompt_text, band, band_id),
        "quality": band_quality_problems(prompt_text, band, band_id, copy_val, style_ref),
    }


def _band_receipts_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "diu_prompt_band_receipts.json"


def cmd_prompt_band(args) -> int:
    band_id = (args.band or "").strip()
    if not band_id:
        print("FATAL: --band is required (e.g. text_bearing_long | text_bearing_medium | "
              "visual_long | medium | short_draft).", file=sys.stderr)
        return 2
    try:
        bands = load_bands(args.bands_file)
        band = _resolve_band(band_id, bands)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    if args.prompt_file:
        p = Path(args.prompt_file)
        if not p.is_file():
            print(f"FATAL: --prompt-file not found: {p}", file=sys.stderr)
            return 2
        prompt = p.read_text(encoding="utf-8")
    elif args.prompt is not None:
        prompt = args.prompt
    else:
        print("FATAL: pass --prompt-file PATH or --prompt STR.", file=sys.stderr)
        return 2

    copy_val = args.copy or None
    res = band_problems(prompt, band, band_id, copy_val=copy_val, style_ref=bool(args.style_ref))
    length_probs = res["length"]
    quality_probs = res["quality"]
    n = len(prompt.strip())

    # Receipt on disk (institutional memory) — mirrors the fidelity/prompt-caps receipt pattern.
    if args.run_dir:
        run_dir = Path(args.run_dir).resolve()
        if run_dir.is_dir():
            receipt = {
                "band": band_id,
                "chars": n,
                "min": band.get("min"),
                "max": band.get("max"),
                "distinct_words": len(set(_GIP_WORD_RE.findall(prompt.lower()))),
                "text_bearing": _is_text_bearing(band),
                "style_ref": bool(args.style_ref),
                "length_problems": [f"{c}: {m}" for c, m in length_probs],
                "quality_problems": quality_probs,
                "passed": not length_probs and not quality_probs,
                "tested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            rp = _band_receipts_path(run_dir)
            prior = []
            if rp.exists():
                try:
                    obj = json.loads(rp.read_text(encoding="utf-8"))
                    prior = obj.get("receipts", []) if isinstance(obj, dict) else (obj or [])
                except Exception:  # noqa: BLE001
                    prior = []
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps({"receipts": prior + [receipt]}, indent=2) + "\n",
                          encoding="utf-8")

    if not length_probs and not quality_probs:
        print(f"OK: {band_id} prompt is {n}/{band.get('max')} chars (floor {band.get('min')}), "
              f"clears the GIP band + quality gate.")
        return 0

    print("!" * 78, file=sys.stderr)
    # LENGTH failures take precedence for the exit code (a floor/cap breach is not run at all).
    if length_probs:
        codes = sorted({c for c, _ in length_probs})
        print(f"FATAL {'/'.join(codes)}: {band_id} prompt FAILS the GIP band length gate — it is "
              f"NOT submitted, NOT rendered. Re-author.", file=sys.stderr)
        for code, msg in length_probs:
            print(f"  - {code}: {msg}", file=sys.stderr)
    if quality_probs:
        print(f"FATAL AF-GIP-PROMPT-QUALITY: {band_id} prompt cleared/failed length but has "
              f"{len(quality_probs)} quality defect(s) (independent of length):", file=sys.stderr)
        for msg in quality_probs:
            print(f"  - {msg}", file=sys.stderr)
    print("!" * 78, file=sys.stderr)
    # Exit 3 when a floor/cap breach is present (fold under AF-GIP-PROMPT-FLOOR / AF-DIU-PROMPT-CAP);
    # otherwise exit 6 for a pure quality failure (AF-GIP-PROMPT-QUALITY).
    return 3 if length_probs else 6


# ---------------------------------------------------------------------------
# 5) SELF-TEST — smoke-test every gate in one command.
# ---------------------------------------------------------------------------
def cmd_self_test(_args) -> int:
    """Run a self-contained smoke test of every enforcement gate.
    Returns 0 when all tests pass, non-zero on the first failure."""
    failures = []

    # (a) Caps are correct: SHORT=500, MEDIUM=2800, LONG=19000.
    expected = {"SHORT": 500, "MEDIUM": 2800, "LONG": 19000}
    if TIER_CAPS != expected:
        failures.append(f"TIER_CAPS mismatch: {TIER_CAPS} != {expected}")
    else:
        print("SELF-TEST OK: TIER_CAPS correct (SHORT=500, MEDIUM=2800, LONG=19000).")

    # (b) Prompt-band max for text_bearing_long is 19000.
    try:
        bands = load_bands()
        tbl = bands.get("text_bearing_long")
        if tbl is None:
            failures.append("text_bearing_long band missing from prompt-bands.json")
        elif tbl.get("max") != 19000:
            failures.append(f"text_bearing_long.max != 19000 (got {tbl.get('max')})")
        elif tbl.get("min") != 5000:
            failures.append(f"text_bearing_long.min != 5000 (got {tbl.get('min')})")
        else:
            print("SELF-TEST OK: text_bearing_long band floor=5000, max=19000.")
    except(Exception) as exc:  # noqa: BLE001
        failures.append(f"prompt-bands load failed: {exc}")

    # (c) Text-bearing bands never route to nano-banana-2.
    for bid, band in bands.items():
        if _is_text_bearing(band) and "nano-banana-2" in band.get("endpoints", []):
            failures.append(f"{bid}: nano-banana-2 in endpoints on text-bearing band (GK-20).")
    print("SELF-TEST OK: no text-bearing band routes to nano-banana-2 (GK-20 reconciled).")

    # (d) prompt-caps: a 19,500-char "long" prompt must be over cap.
    cap_rc = cmd_prompt_caps(_FakeArgs(prompt="x" * 19500, tier="LONG"))
    if cap_rc != 3:
        failures.append(f"prompt-caps: 19,500-char LONG prompt should exit 3, got {cap_rc}")
    else:
        print("SELF-TEST OK: prompt-caps catches 19,500-char LONG over-cap (exit 3).")

    # (e) prompt-caps: a 18,500-char "long" prompt must pass.
    cap_rc2 = cmd_prompt_caps(_FakeArgs(prompt="x" * 18500, tier="LONG"))
    if cap_rc2 != 0:
        failures.append(f"prompt-caps: 18,500-char LONG prompt should exit 0, got {cap_rc2}")
    else:
        print("SELF-TEST OK: prompt-caps passes 18,500-char LONG prompt.")

    # (f) route-check: a "webinar deck" must be rejected.
    rc_rc = cmd_route_check(_FakeArgs(deck_kind="webinar deck"))
    if rc_rc != 2:
        failures.append(f"route-check: 'webinar deck' should exit 2, got {rc_rc}")
    else:
        print("SELF-TEST OK: route-check rejects webinar deck (exit 2).")

    # (g) route-check: a "brand deck" must pass.
    rc_rc2 = cmd_route_check(_FakeArgs(deck_kind="brand deck"))
    if rc_rc2 != 0:
        failures.append(f"route-check: 'brand deck' should exit 0, got {rc_rc2}")
    else:
        print("SELF-TEST OK: route-check passes brand deck (exit 0).")

    # (h) prompt-band: a 1,000-char text_bearing_long prompt must fail the floor.
    pb_rc = cmd_prompt_band(_FakeArgs(
        band="text_bearing_long", prompt="x" * 1000))
    if pb_rc != 3:
        failures.append(f"prompt-band: 1,000-char text_bearing_long prompt should exit 3 (floor), got {pb_rc}")
    else:
        print("SELF-TEST OK: prompt-band floor rejects 1,000-char text_bearing_long prompt.")

    # (i) consent-check: a missing identity file must fail closed.
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tf:
        tf.write(b"")
        tmpf = tf.name
    try:
        os.unlink(tmpf)
        cc_rc = cmd_consent_check(_FakeArgs(identity_file=tmpf))
        if cc_rc != 4:
            failures.append(f"consent-check: missing IDENTITY file should exit 4, got {cc_rc}")
        else:
            print("SELF-TEST OK: consent-check fails closed on missing IDENTITY file (exit 4).")
    finally:
        pass

    if failures:
        print("\nSELF-TEST FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nSELF-TEST ALL PASSED.")
    return 0


class _FakeArgs:
    """Lightweight namespace for self-test argument simulation."""
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.__dict__.setdefault("prompt_file", None)
        self.__dict__.setdefault("bands_file", None)
        self.__dict__.setdefault("copy", [])
        self.__dict__.setdefault("style_ref", False)
        self.__dict__.setdefault("run_dir", None)


# ---------------------------------------------------------------------------
# 5) SELF-TEST -- smoke-test every gate in one command.
# ---------------------------------------------------------------------------
def cmd_self_test(_args) -> int:
    """Run a self-contained smoke test of every enforcement gate.
    Returns 0 when all tests pass, non-zero on the first failure."""
    failures = []

    # (a) Caps are correct: SHORT=500, MEDIUM=2800, LONG=19000.
    expected = {"SHORT": 500, "MEDIUM": 2800, "LONG": 19000}
    if TIER_CAPS != expected:
        failures.append(f"TIER_CAPS mismatch: {TIER_CAPS} != {expected}")
    else:
        print("SELF-TEST OK: TIER_CAPS correct (SHORT=500, MEDIUM=2800, LONG=19000).")

    # (b) Prompt-band max for text_bearing_long is 19000.
    try:
        bands = load_bands()
        tbl = bands.get("text_bearing_long")
        if tbl is None:
            failures.append("text_bearing_long band missing from prompt-bands.json")
        elif tbl.get("max") != 19000:
            failures.append(f"text_bearing_long.max != 19000 (got {tbl.get('max')})")
        elif tbl.get("min") != 5000:
            failures.append(f"text_bearing_long.min != 5000 (got {tbl.get('min')})")
        else:
            print("SELF-TEST OK: text_bearing_long band floor=5000, max=19000.")
    except(Exception) as exc:  # noqa: BLE001
        failures.append(f"prompt-bands load failed: {exc}")

    # (c) Text-bearing bands never route to nano-banana-2.
    for bid, band in bands.items():
        if _is_text_bearing(band) and "nano-banana-2" in band.get("endpoints", []):
            failures.append(
                f"{bid}: nano-banana-2 in endpoints on text-bearing band (GK-20).")
    print("SELF-TEST OK: no text-bearing band routes to nano-banana-2 (GK-20 reconciled).")

    # (d) prompt-caps: a 19,500-char "long" prompt must be over cap.
    cap_rc = cmd_prompt_caps(_FakeArgs(prompt="x" * 19500, tier="LONG"))
    if cap_rc != 3:
        failures.append(f"prompt-caps: 19,500-char LONG prompt should exit 3, got {cap_rc}")
    else:
        print("SELF-TEST OK: prompt-caps catches 19,500-char LONG over-cap (exit 3).")

    # (e) prompt-caps: a 18,500-char "long" prompt must pass.
    cap_rc2 = cmd_prompt_caps(_FakeArgs(prompt="x" * 18500, tier="LONG"))
    if cap_rc2 != 0:
        failures.append(f"prompt-caps: 18,500-char LONG prompt should exit 0, got {cap_rc2}")
    else:
        print("SELF-TEST OK: prompt-caps passes 18,500-char LONG prompt.")

    # (f) route-check: a "webinar deck" must be rejected.
    rc_rc = cmd_route_check(_FakeArgs(deck_kind="webinar deck"))
    if rc_rc != 2:
        failures.append(f"route-check: 'webinar deck' should exit 2, got {rc_rc}")
    else:
        print("SELF-TEST OK: route-check rejects webinar deck (exit 2).")

    # (g) route-check: a "brand deck" must pass.
    rc_rc2 = cmd_route_check(_FakeArgs(deck_kind="brand deck"))
    if rc_rc2 != 0:
        failures.append(f"route-check: 'brand deck' should exit 0, got {rc_rc2}")
    else:
        print("SELF-TEST OK: route-check passes brand deck (exit 0).")

    # (h) prompt-band: a 1,000-char text_bearing_long prompt must fail the floor.
    pb_rc = cmd_prompt_band(_FakeArgs(
        band="text_bearing_long", prompt="x" * 1000))
    if pb_rc != 3:
        failures.append(f"prompt-band: 1,000-char text_bearing_long prompt should exit 3 (floor), got {pb_rc}")
    else:
        print("SELF-TEST OK: prompt-band floor rejects 1,000-char text_bearing_long prompt.")

    # (i) consent-check: a missing identity file must fail closed.
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tf:
        tf.write(b"")
        tmpf = tf.name
    try:
        os.unlink(tmpf)
        cc_rc = cmd_consent_check(_FakeArgs(identity_file=tmpf))
        if cc_rc != 4:
            failures.append(f"consent-check: missing IDENTITY file should exit 4, got {cc_rc}")
        else:
            print("SELF-TEST OK: consent-check fails closed on missing IDENTITY file (exit 4).")
    finally:
        pass

    if failures:
        print("\nSELF-TEST FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nSELF-TEST ALL PASSED.")
    return 0


class _FakeArgs:
    """Lightweight namespace for self-test argument simulation."""
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.__dict__.setdefault("prompt_file", None)
        self.__dict__.setdefault("bands_file", None)
        self.__dict__.setdefault("copy", [])
        self.__dict__.setdefault("style_ref", False)
        self.__dict__.setdefault("run_dir", None)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic DIU enforcement gate (prompt caps, GIP prompt "
                    "bands, routing interlock, consent/minor/PII, fidelity + 3-strike).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("prompt-caps", help="enforce SHORT/MEDIUM/LONG char caps")
    pc.add_argument("--tier", required=True, help="SHORT | MEDIUM | LONG")
    pc.add_argument("--prompt-file", help="path to the assembled prompt")
    pc.add_argument("--prompt", help="inline prompt string")
    pc.set_defaults(func=cmd_prompt_caps)

    pb = sub.add_parser("prompt-band",
                        help="enforce the GIP per-asset-class prompt band (MIN floor + MAX cap "
                             "+ quality teeth)")
    pb.add_argument("--band", required=True,
                    help="text_bearing_long | text_bearing_medium | visual_long | medium | "
                         "short_draft")
    pb.add_argument("--prompt-file", help="path to the assembled prompt")
    pb.add_argument("--prompt", help="inline prompt string")
    pb.add_argument("--copy", action="append", default=[],
                    help="a verbatim on-image copy string that must be baked into the prompt "
                         "body (repeatable; enforced on text-bearing bands)")
    pb.add_argument("--style-ref", action="store_true",
                    help="style reference image(s) are attached -> require the mandatory "
                         "style-reference-only directive (MODEL-SPECS §4)")
    pb.add_argument("--run-dir", help="optional run dir for the band receipt "
                                      "(working/checkpoints/diu_prompt_band_receipts.json)")
    pb.add_argument("--bands-file", help="override path to prompt-bands.json (tests only)")
    pb.set_defaults(func=cmd_prompt_band)

    rc = sub.add_parser("route-check", help="DIU routing interlock (SOP-DIU-611 D.1)")
    rc.add_argument("--deck-kind", required=True,
                    help="deck kind, e.g. webinar | funnel | brand | campaign")
    rc.set_defaults(func=cmd_route_check)

    cc = sub.add_parser("consent-check",
                        help="fail-closed consent + minor + PII gate (PHOTO-SHOOT-SOP §1)")
    cc.add_argument("--identity-file", required=True,
                    help="path to the client's personal-photo-shoot IDENTITY.md")
    cc.set_defaults(func=cmd_consent_check)

    fd = sub.add_parser("fidelity", help="fidelity receipt + 3-strike counter")
    fd.add_argument("--run-dir", required=True)
    fd.add_argument("--card-id", required=True)
    fd.add_argument("--scores-file", help="JSON: {dim: score} or [12 numbers]")
    fd.add_argument("--scores", help="inline JSON scores")
    fd.add_argument("--hard-rule-violation", action="append", default=[],
                    help="a hard-rule violation description (repeatable); any one "
                         "fails the whole test")
    fd.set_defaults(func=cmd_fidelity)

    st = sub.add_parser("self-test", help="smoke-test every enforcement gate")
    st.set_defaults(func=cmd_self_test)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
