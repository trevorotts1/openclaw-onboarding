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
      SHORT <= 500, MEDIUM <= 2,800, LONG <= 18,000 characters. An assembled
      prompt over its tier cap is a HARD FAIL (exit 3) — the operator must fall
      back a tier (the MODEL-SPECS auto-fallback rule) rather than silently
      truncate at the endpoint.

  route-check  — DIU ROUTING INTERLOCK (SOP-DIU-611 §D.1 "coded hard stop").
      An audience / webinar / funnel / virtual-event deck CANNOT proceed on the
      DIU Style Rotation Engine (strategy-(b) pipeline). Any such deck routes to
      the Presentations department. Attempting to run one through the DIU is an
      architecture violation → HARD ABORT (exit 2). This is the code behind the
      prose "mechanical gate" the SOP claims.

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
    0 — pass (within cap / legal route / fidelity pass, no 3rd strike).
    2 — routing-interlock violation (AF-DIU-ROUTING-INTERLOCK) or usage error.
    3 — prompt over the tier cap (AF-DIU-PROMPT-CAP) OR a fidelity FAIL that has
        not yet reached the 3rd consecutive strike.
    5 — 3-strike escalation (AF-DIU-3-STRIKE): a dimension failed 3 consecutive
        times — escalate to CDO with the receipt evidence.

USAGE
    python3 diu_validator.py prompt-caps --tier LONG --prompt-file assembled.txt
    python3 diu_validator.py prompt-caps --tier SHORT --prompt "…inline…"
    python3 diu_validator.py route-check --deck-kind webinar
    python3 diu_validator.py fidelity --run-dir RUN --card-id FB-003 \
                --scores-file scores.json [--hard-rule-violation "text on face"]

This is a SCRIPT, not a manifest role/SOP. It has zero third-party imports so it
runs on any box with a stock Python 3.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# 1) PROMPT-LENGTH CAPS — MODEL-SPECS.md tier table (SHORT/MEDIUM/LONG).
# ---------------------------------------------------------------------------
TIER_CAPS = {
    "SHORT": 500,
    "MEDIUM": 2800,
    "LONG": 18000,
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
# main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic DIU enforcement gate (prompt caps, routing "
                    "interlock, fidelity + 3-strike).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("prompt-caps", help="enforce SHORT/MEDIUM/LONG char caps")
    pc.add_argument("--tier", required=True, help="SHORT | MEDIUM | LONG")
    pc.add_argument("--prompt-file", help="path to the assembled prompt")
    pc.add_argument("--prompt", help="inline prompt string")
    pc.set_defaults(func=cmd_prompt_caps)

    rc = sub.add_parser("route-check", help="DIU routing interlock (SOP-DIU-611 D.1)")
    rc.add_argument("--deck-kind", required=True,
                    help="deck kind, e.g. webinar | funnel | brand | campaign")
    rc.set_defaults(func=cmd_route_check)

    fd = sub.add_parser("fidelity", help="fidelity receipt + 3-strike counter")
    fd.add_argument("--run-dir", required=True)
    fd.add_argument("--card-id", required=True)
    fd.add_argument("--scores-file", help="JSON: {dim: score} or [12 numbers]")
    fd.add_argument("--scores", help="inline JSON scores")
    fd.add_argument("--hard-rule-violation", action="append", default=[],
                    help="a hard-rule violation description (repeatable); any one "
                         "fails the whole test")
    fd.set_defaults(func=cmd_fidelity)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
