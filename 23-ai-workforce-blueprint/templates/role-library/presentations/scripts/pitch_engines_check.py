#!/usr/bin/env python3
"""
pitch_engines_check.py — mechanical detection for the net-new PITCH-ENGINE
auto-fails authored in SOP-PITCH-06-PITCH-ENGINES.md.

DOCTRINE: a rule that cannot be mechanically checked is not a rule. Each engine
below resolves to a BINARY auto-fail with an EXACT detection method against a
named data file / regex / count / arithmetic. The *verdict* of any irreducibly
perceptual sub-rule (e.g. "does the guarantee FEEL felt") is left to the copy/
vision QC specialist and LOGGED; the GATEABLE half checked here is fully
deterministic.

WHY A SEPARATE SCRIPT (not build_deck.py): the renderer's path is load-bearing
for a live render job and must not be touched. These checks are owned by the QC
specialists and invoked at the 8.5 gate (Phase 1Q copy-QC, Phase 6 deck re-verify,
Phase Speech-QC). The codes are registered in PIPELINE-MANIFEST.autofails with
enforced_by:"qc_check" / py_symbol:null — exactly like the AF-DEN / AF-HOOK / AF-OBI
copy-QC battery — so sync_check.py's A3 (build_deck py_symbol existence) does NOT
fire on them, and B2 never fires because build_deck.py does not cite them.

Exit codes:
  0  all checks pass (or DEFER — required input artifact absent at this phase)
  4  one or more PITCH-ENGINE auto-fails triggered (distinct from build_deck 1/2/3)

Usage:
  python3 pitch_engines_check.py --run-dir <deck_run_dir> [--json] [--phase 1Q|6|SPEECH-QC]

A "run dir" is the per-deck working tree that holds:
  working/copy/intake.json
  working/copy/price_ladder.json
  working/copy/offer_stack.json
  working/copy/slides_copy.md          (arc-tagged copy)
  working/copy/method_name_approval.json   (optional)
  working/delivery/PRESENTERS-SPEECH.md    (for the speech-hook count)
"""
import argparse
import json
import re
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_FAIL = 4

# ---------------------------------------------------------------------------
# Tunable constants (mirror the SOP-PITCH-06 doctrine numbers)
# ---------------------------------------------------------------------------
SPEECH_HOOK_MIN = 5          # the hook must be "sung" at least 5x in the speech
SPEECH_HOOK_MAX = 20         # ... and at most 20x (over-singing is wallpaper)
DURATION_RE = re.compile(r'\b\d+\s*(?:day|week|month|session|hour|minute)s?\b', re.I)
NUMBER_RE = re.compile(r'\b\d[\d,]*\b')
# generic refund-template phrases that, AS THE WHOLE GUARANTEE FRAME, fail
GUARANTEE_GENERIC_RE = re.compile(
    r'money[\s-]*back|30[\s-]*day(?:s)?\b|satisfaction\s+guaranteed|full\s+refund|no[\s-]*questions[\s-]*asked',
    re.I,
)
# felt-stakes personal-loss frame tokens (the "3,285 mornings left" device family)
FELT_STAKES_FRAME_TOKENS = (
    "mornings", "left", "remaining", "never get back", "running out",
    "every day you wait", "missed", "lose", "losing", "gone", "slipping",
    "by the time", "before it's too late", "won't come back",
)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------
def _load_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"__parse_error__": True}


def _load_text(p: Path):
    if not p.exists():
        return None
    return p.read_text()


def _arc_tags_in_order(copy_text: str):
    """Return an ordered list of (slide_index, [TAGS]) from arc-tagged slide copy.
    Tags are read from `<!-- ARC: TAG1 TAG2 -->` markers or `[ARC:TAG]` inline
    markers, whichever the copy uses; both are scanned. Slide order = appearance."""
    tags = []
    # slide delimiter: a line beginning with '## Slide' or '---' between blocks.
    # We treat each ARC marker as positioned at its character offset, which
    # preserves monotonic slide order for the ordering checks below.
    for m in re.finditer(r'(?:<!--\s*ARC:\s*([^>]+?)\s*-->|\[ARC:\s*([^\]]+?)\s*\])',
                          copy_text):
        raw = (m.group(1) or m.group(2) or "")
        toks = [t.strip().upper() for t in re.split(r'[\s,]+', raw) if t.strip()]
        tags.append((m.start(), toks))
    return tags


def _flat_tag_positions(arc_tags):
    """Map TAG -> sorted list of character offsets where it appears."""
    pos = {}
    for off, toks in arc_tags:
        for t in toks:
            pos.setdefault(t, []).append(off)
    for t in pos:
        pos[t].sort()
    return pos


# ---------------------------------------------------------------------------
# The checks. Each returns a list of failure dicts (empty = pass) or the
# sentinel {"defer": reason} when its required input is absent at this phase.
# ---------------------------------------------------------------------------
def chk_cadence(run):
    """AF-CADENCE — the ordered pitch loop, PER RUNG.
    For each adjacent DROP pair, the window between them must carry, IN
    MONOTONIC SLIDE ORDER: VALUE_ADD -> PROMISE -> REPITCH_MINI -> COST_OF_INACTION.
    Order violation / missing beat / out-of-sequence beat = fail, naming the rung."""
    ladder = run["price_ladder"]
    stack = run["offer_stack"]
    copy_text = run["slides_copy"]
    if ladder is None or copy_text is None:
        return [{"defer": "price_ladder.json or slides_copy.md absent"}]
    rungs = ladder.get("rungs") or []
    drops = [r for r in rungs if str(r.get("kind", "")).upper() in ("DROP", "FINAL")
             or str(r.get("type", "")).upper() in ("DROP", "FINAL")]
    # fall back: any rung carrying a target_slide is a price beat
    if not drops:
        drops = [r for r in rungs if r.get("target_slide") is not None]
    if len(drops) < 2:
        return []  # a single-rung offer has no inter-rung loop to order
    drops = sorted(drops, key=lambda r: r.get("target_slide", 0))
    arc_tags = _arc_tags_in_order(copy_text)
    # crude slide-offset -> we use ARC marker offsets and the rung target_slide
    # index parity: the Nth DROP's window is the arc-tag span between the Nth and
    # (N+1)th price-beat markers. We approximate windows by splitting arc_tags on
    # LADDER/DROP/FINAL markers in order.
    BEAT_ORDER = ["VALUE_ADD", "PROMISE", "REPITCH_MINI", "COST_OF_INACTION"]
    PRICE_MARKERS = {"DROP", "DROP1", "DROP2", "DROP3", "FINAL", "LADDER"}
    # build the sequence of (offset, tokenset)
    seq = arc_tags
    # find indices of price markers
    price_idx = [i for i, (_, toks) in enumerate(seq)
                 if any(t in PRICE_MARKERS for t in toks)]
    fails = []
    if len(price_idx) < 2:
        return [{"code": "AF-CADENCE", "rung": None,
                 "detail": "fewer than two price-beat arc markers found in "
                           "slides_copy.md; the per-rung cadence loop cannot be "
                           "verified. Tag each price beat (LADDER/DROP/FINAL)."}]
    for n in range(len(price_idx) - 1):
        lo = price_idx[n]
        hi = price_idx[n + 1]
        window = seq[lo + 1:hi]
        window_tokens_in_order = [toks for _, toks in window]
        # walk required beats in order, consuming the window monotonically
        cursor = 0
        missing = []
        misordered = []
        for beat in BEAT_ORDER:
            found_at = None
            for j in range(cursor, len(window_tokens_in_order)):
                if beat in window_tokens_in_order[j]:
                    found_at = j
                    break
            if found_at is None:
                # maybe present but BEFORE the cursor => out of order
                earlier = any(beat in window_tokens_in_order[j]
                              for j in range(0, cursor))
                if earlier:
                    misordered.append(beat)
                else:
                    missing.append(beat)
            else:
                cursor = found_at + 1
        if missing or misordered:
            fails.append({
                "code": "AF-CADENCE",
                "rung": n + 1,
                "detail": f"rung {n+1} cadence loop broken — "
                          f"missing={missing or '[]'} misordered={misordered or '[]'} "
                          f"(required order: {' -> '.join(BEAT_ORDER)}).",
            })
    return fails


def chk_cost_of_inaction(run):
    """AF-NO-COST-OF-INACTION — promote offer SOP 9.6 from 'flag' to a gate.
    price_ladder.json.cost_of_inaction_slide must be present, non-null, and the
    referenced slide must carry a COST_OF_INACTION arc beat in slides_copy.md."""
    ladder = run["price_ladder"]
    copy_text = run["slides_copy"]
    if ladder is None:
        return [{"defer": "price_ladder.json absent"}]
    slot = ladder.get("cost_of_inaction_slide", None)
    if slot is None:
        return [{"code": "AF-NO-COST-OF-INACTION", "detail":
                 "price_ladder.json.cost_of_inaction_slide is null/absent — the "
                 "deck never states the cost of NOT acting (offer SOP 9.6)."}]
    if copy_text is not None:
        pos = _flat_tag_positions(_arc_tags_in_order(copy_text))
        if "COST_OF_INACTION" not in pos:
            return [{"code": "AF-NO-COST-OF-INACTION", "detail":
                     "cost_of_inaction_slide is set but no COST_OF_INACTION arc "
                     "beat is tagged in slides_copy.md."}]
    return []


def chk_guarantee_generic(run):
    """AF-GUARANTEE-GENERIC — mechanical anti-generic half.
    The guarantee slide copy must NOT be ONLY a refund-template phrase; it must
    carry a named, felt, client-specific stake string (guarantee_felt_frame)."""
    ladder = run["price_ladder"]
    if ladder is None:
        return [{"defer": "price_ladder.json absent"}]
    g = ladder.get("guarantee") or {}
    statement = (g.get("statement") or "").strip()
    if not statement:
        return []  # presence is owned by copy QC c20 / AF-DEN battery, not here
    felt = (g.get("guarantee_felt_frame") or "").strip()
    # strip the generic template phrases; if nothing substantive remains AND no
    # felt frame was supplied, it is a bare refund template => fail.
    residue = GUARANTEE_GENERIC_RE.sub("", statement).strip(" .,-—:;")
    if not felt and len(residue) < 12:
        return [{"code": "AF-GUARANTEE-GENERIC", "detail":
                 "guarantee is a bare refund-template phrase "
                 f"({statement!r}) with no client-specific felt frame "
                 "(guarantee_felt_frame). Make it a guarantee they can FEEL."}]
    return []


def chk_branded_method(run):
    """AF-NO-BRANDED-METHOD + AF-METHOD-FABRICATED.
    - AF-METHOD-FABRICATED: a NAMED_METHOD beat on a slide with neither a
      client-supplied intake.named_methodology nor an owner_approved:true record.
    - AF-NO-BRANDED-METHOD: generic intake content but ZERO method beat at all."""
    intake = run["intake"]
    copy_text = run["slides_copy"]
    approval = run["method_approval"]
    if copy_text is None:
        return [{"defer": "slides_copy.md absent"}]
    pos = _flat_tag_positions(_arc_tags_in_order(copy_text))
    has_method_beat = "NAMED_METHOD" in pos or "BRANDED_METHOD" in pos
    client_supplied = bool((intake or {}).get("named_methodology"))
    owner_approved = bool((approval or {}).get("owner_approved") is True)
    fails = []
    if has_method_beat and not client_supplied and not owner_approved:
        fails.append({"code": "AF-METHOD-FABRICATED", "detail":
                      "a NAMED_METHOD beat appears on a slide but there is neither "
                      "intake.named_methodology nor an owner_approved:true record in "
                      "method_name_approval.json — silent fabrication is banned."})
    if not has_method_beat and not client_supplied:
        # intake content is generic (no client method) AND no proposed/approved beat
        fails.append({"code": "AF-NO-BRANDED-METHOD", "detail":
                      "no NAMED_METHOD beat and no client methodology — generic "
                      "content ships at generic prices. PROPOSE a branded-method "
                      "name for owner approval (do not leave the deck method-less)."})
    return fails


def chk_time_to_result(run):
    """AF-NO-TIME-TO-RESULT — the EXPECTATION beat.
    An EXPECTATION arc beat must exist whose copy carries a duration token sourced
    from intake.time_to_result (never fabricated)."""
    intake = run["intake"]
    copy_text = run["slides_copy"]
    if copy_text is None:
        return [{"defer": "slides_copy.md absent"}]
    arc = _arc_tags_in_order(copy_text)
    pos = _flat_tag_positions(arc)
    if "EXPECTATION" not in pos:
        return [{"code": "AF-NO-TIME-TO-RESULT", "detail":
                 "no EXPECTATION arc beat — the deck never states how long the "
                 "result takes (e.g. '8 weeks to final, a shift in 2')."}]
    # the EXPECTATION beat's surrounding text must carry a duration token
    off = pos["EXPECTATION"][0]
    window = copy_text[off: off + 600]
    if not DURATION_RE.search(window):
        return [{"code": "AF-NO-TIME-TO-RESULT", "detail":
                 "EXPECTATION beat present but carries no time-to-result duration "
                 "token (day/week/month/session). State the real timeframe."}]
    # anti-fabrication: intake should declare it
    if intake is not None and not intake.get("time_to_result"):
        return [{"code": "AF-NO-TIME-TO-RESULT", "detail":
                 "EXPECTATION beat states a timeframe but intake.time_to_result is "
                 "absent — the timeframe must come from intake, never fabricated."}]
    return []


def chk_felt_stakes(run):
    """AF-NO-FELT-STAKES — the EMOTIONAL engine.
    A FELT_STAKES beat must exist BEFORE the first ladder beat, pairing a concrete
    number with a personal-loss frame token (the 'mornings left' device)."""
    copy_text = run["slides_copy"]
    if copy_text is None:
        return [{"defer": "slides_copy.md absent"}]
    arc = _arc_tags_in_order(copy_text)
    pos = _flat_tag_positions(arc)
    if "FELT_STAKES" not in pos:
        return [{"code": "AF-NO-FELT-STAKES", "detail":
                 "no FELT_STAKES beat — the deck never makes the audience FEEL the "
                 "cost in human terms before the offer."}]
    felt_off = pos["FELT_STAKES"][0]
    # must precede the first ladder/price beat
    ladder_offs = []
    for k in ("LADDER", "DROP", "DROP1", "ANCHOR"):
        ladder_offs.extend(pos.get(k, []))
    if ladder_offs and felt_off > min(ladder_offs):
        return [{"code": "AF-NO-FELT-STAKES", "detail":
                 "FELT_STAKES beat appears AFTER the first price/ladder beat; the "
                 "felt-stakes moment must land before the offer."}]
    window = copy_text[felt_off: felt_off + 600]
    has_number = bool(NUMBER_RE.search(window))
    has_frame = any(tok in window.lower() for tok in FELT_STAKES_FRAME_TOKENS)
    if not (has_number and has_frame):
        return [{"code": "AF-NO-FELT-STAKES", "detail":
                 "FELT_STAKES beat present but does not pair a concrete number with "
                 "a personal-loss frame (e.g. '3,285 mornings left'). "
                 f"number={has_number} loss_frame={has_frame}."}]
    return []


def chk_villain(run):
    """AF-NO-VILLAIN — STORY engine, villain-before-hero ordering.
    A VILLAIN/antagonist beat must exist AND precede the HERO/solution beat."""
    copy_text = run["slides_copy"]
    if copy_text is None:
        return [{"defer": "slides_copy.md absent"}]
    pos = _flat_tag_positions(_arc_tags_in_order(copy_text))
    villain = pos.get("VILLAIN") or pos.get("ANTAGONIST")
    hero = pos.get("HERO") or pos.get("SOLUTION")
    if not villain:
        return [{"code": "AF-NO-VILLAIN", "detail":
                 "no VILLAIN beat — no one cares about the hero until they meet the "
                 "villain. Name the antagonist before the solution."}]
    if hero and min(villain) > min(hero):
        return [{"code": "AF-NO-VILLAIN", "detail":
                 "VILLAIN beat appears AFTER the HERO/solution beat; the villain "
                 "must be introduced first."}]
    return []


def chk_speech_hook_count(run):
    """AF-SPEECH-HOOK-COUNT — the hook is SUNG 5-20x in the spoken speech.
    Count char-exact hook occurrences in PRESENTERS-SPEECH.md against intake.hook."""
    intake = run["intake"]
    speech = run["speech"]
    if speech is None:
        return [{"defer": "PRESENTERS-SPEECH.md absent (pre-speech phase)"}]
    hook = ((intake or {}).get("hook") or "").strip()
    if not hook:
        return [{"defer": "intake.hook absent"}]
    count = speech.count(hook)
    if count < SPEECH_HOOK_MIN:
        return [{"code": "AF-SPEECH-HOOK-COUNT", "detail":
                 f"hook sung only {count}x in the speech (floor {SPEECH_HOOK_MIN}). "
                 "Sing the canonical hook verbatim at least 5 times across the talk."}]
    if count > SPEECH_HOOK_MAX:
        return [{"code": "AF-SPEECH-HOOK-COUNT", "detail":
                 f"hook sung {count}x in the speech (ceiling {SPEECH_HOOK_MAX}). "
                 "Over-singing turns the refrain into wallpaper."}]
    return []


CHECKS = {
    "1Q": [chk_cadence, chk_cost_of_inaction, chk_guarantee_generic,
           chk_branded_method, chk_time_to_result, chk_felt_stakes, chk_villain],
    "6": [chk_cadence, chk_cost_of_inaction, chk_guarantee_generic,
          chk_branded_method, chk_time_to_result, chk_felt_stakes, chk_villain],
    "SPEECH-QC": [chk_speech_hook_count],
}
# default = run everything
ALL_CHECKS = [chk_cadence, chk_cost_of_inaction, chk_guarantee_generic,
              chk_branded_method, chk_time_to_result, chk_felt_stakes,
              chk_villain, chk_speech_hook_count]


def load_run(run_dir: Path):
    cp = run_dir / "working" / "copy"
    return {
        "intake": _load_json(cp / "intake.json"),
        "price_ladder": _load_json(cp / "price_ladder.json"),
        "offer_stack": _load_json(cp / "offer_stack.json"),
        "slides_copy": _load_text(cp / "slides_copy.md"),
        "method_approval": _load_json(cp / "method_name_approval.json"),
        "speech": _load_text(run_dir / "working" / "delivery" / "PRESENTERS-SPEECH.md"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--phase", default="all",
                    choices=["1Q", "6", "SPEECH-QC", "all"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    run = load_run(run_dir)
    checks = ALL_CHECKS if args.phase == "all" else CHECKS[args.phase]

    fails = []
    defers = []
    for fn in checks:
        for r in fn(run):
            if "defer" in r:
                defers.append({"check": fn.__name__, "reason": r["defer"]})
            else:
                fails.append(r)

    if args.json:
        print(json.dumps({
            "phase": args.phase,
            "pass": not fails,
            "fails": fails,
            "defers": defers,
        }, indent=2))
    else:
        if fails:
            print("=== pitch_engines_check: PITCH-ENGINE AUTO-FAILS ===", file=sys.stderr)
            for f in fails:
                print(f"  {f['code']}: {f['detail']}", file=sys.stderr)
        else:
            print("pitch_engines_check: PASS"
                  + (f" ({len(defers)} deferred)" if defers else ""))
            for d in defers:
                print(f"  DEFER {d['check']}: {d['reason']}")

    sys.exit(EXIT_FAIL if fails else EXIT_PASS)


if __name__ == "__main__":
    main()
