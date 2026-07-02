#!/usr/bin/env python3
# =============================================================================
# SACRED-STRUCTURE PROVER — Signature Presentation, Phase-3 no-pitch hygiene.
# Deterministic, fail-closed, stdlib-only. NO AI at runtime. NO network.
# Clones the deterministic-stripped-length prover pattern from
#   23-ai-workforce-blueprint/.../presentations/scripts/build_deck.py
# (normalize -> substring/regex match on stripped text -> AF code -> sys.exit).
# =============================================================================
"""
prove_sp_no_pitch.py — enforce PHASE-3 (Transformational Teaching) NO-PITCH hygiene.

Contract source of truth:
  * structure/sp_structure.json   — the SACRED structure ledger. Phase 3 (id
    "teaching") carries  no_pitch:true  and the bridge rule
    ("final teaching step; may promise what comes next; may NOT name a price or
    product").
  * intake/sp-8-questions.json     — q7 captures the EXACT offer/product name(s).
    Those names become the offer-token ledger (runtime:
    working/copy/sp_intake.json -> offer_token_ledger). They are FORBIDDEN in
    Phase 3 and REQUIRED in the Phase-4 pitch.

WHAT THIS PROVER PROVES (fail-closed — a violation is exit NONZERO; the deck is
NOT run, NOT rendered, NOT delivered):

  1. AF-SP-PITCH-IN-TEACH — no q7 offer/product NAME appears on any Phase-3
     (teaching) slide (headline, body, tags, or the suggested_image seed).
  2. AF-SP-PRICE-IN-TEACH — no price/monetary token ($1,997 / 997 dollars /
     $99/mo / USD 497) appears on any Phase-3 slide.
  3. AF-SP-CTA-IN-TEACH  — no enroll/buy/close/scarcity CTA (sale-mechanic)
     language appears on any Phase-3 slide.
  4. AF-SP-BRIDGE        — the Phase-3 -> Phase-4 handoff is well-formed: a
     Phase-4 (pitch) phase exists and the FINAL teaching slide sits directly
     before the FIRST pitch slide (contiguous handoff). The bridge slide, being
     a teaching slide, is ALSO subject to checks 1-3 (it may promise what comes
     next but may NOT name a price or product).

FAIL-CLOSED PRECONDITIONS (exit NONZERO — the prover never PASSES vacuously):
  * a required input (intake / copy ledger) is missing or not valid JSON;
  * the copy ledger carries no teaching-phase slides (AF-SP-TEACH-EMPTY);
  * the offer-token ledger is missing/empty (AF-SP-OFFER-LEDGER-MISSING) — with
    no offer names there is nothing to prove absent, so PASS is forbidden;
  * a teaching or pitch slide lacks a valid integer slide index.

INPUTS:
  --run-dir DIR   resolve intake at  DIR/working/copy/sp_intake.json  (fallback
                  DIR/sp_intake.json) and the copy ledger at
                  DIR/working/copy/sp_structure.json (fallback DIR/sp_structure.json).
  --intake FILE   explicit runtime intake JSON (carries offer_token_ledger).
  --ledger FILE   explicit deck COPY ledger JSON (per-slide entries with
                  slide + phase + copy). This is the emitted copy ledger, NOT the
                  sacred contract of the same base name.
  --contract FILE the SACRED structure ledger (optional; defaults to the repo's
                  structure/sp_structure.json). Only used to derive the teaching
                  and pitch phase ids; defaults are safe if absent.
  --self-test     build in-memory fixtures, assert the VALID one PASSES (exit 0)
                  and each VIOLATION one exits NONZERO. Exit 0 iff all assertions
                  hold.

EXIT CODES:
  0  PASS.
  2  a Phase-3 no-pitch / bridge VIOLATION.
  3  FAIL-CLOSED: a required input could not be verified.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

# ---------------------------------------------------------------------------
# Detection tables. Kept NARROW + specific (mirroring build_deck.py's
# PITCHLESS_FORBIDDEN_TOKENS philosophy) so ordinary teaching copy is not
# over-caught — these are sale-mechanic / offer tokens, not generic value words.
# Matched case-insensitively on the STRIPPED, whitespace-collapsed text.
# ---------------------------------------------------------------------------

# Monetary / price tokens. $1,997  |  997 dollars / 997 usd  |  $99/mo  |  USD 497.
PRICE_RE = re.compile(
    r"""(?ix)
      (?: \$ | us\$ | usd\s* | € | £ ) \s* \d[\d,]* (?:\.\d+)?          # $1,997 / USD 497 / €99
    | \b \d[\d,]* (?:\.\d+)? \s* (?: dollars? | usd | bucks )            # 997 dollars
    | \b \d[\d,]* (?:\.\d+)? \s* (?: /\s*mo | /\s*month | /\s*yr | /\s*year
                                    | per \s+ month | per \s+ year
                                    | a \s+ month | a \s+ year )         # 99/mo, 99 per month
    """
)

# Enroll / buy / close / scarcity CTA + sale-mechanic phrases (normalized).
CTA_TOKENS: Tuple[str, ...] = (
    "enroll now", "enrol now", "enroll today", "enrol today", "enrollment now",
    "buy now", "order now", "purchase now", "get it now", "add to cart",
    "checkout now", "check out now",
    "sign up now", "sign up today", "join now", "join today",
    "register now", "register today",
    "reserve your spot", "reserve your seat", "claim your spot",
    "claim your seat", "save your seat",
    "limited time offer", "limited-time offer", "act now", "act fast",
    "spots left", "seats left", "spots remaining", "seats remaining",
    "money-back guarantee", "money back guarantee", "risk-free guarantee",
    "payment plan", "installment plan", "deposit today", "pay in full",
    "down payment",
    "% off", "percent off", "discount code", "promo code", "coupon code",
    "special offer", "early bird", "flash sale", "sale ends",
    "price goes up", "doors close", "cart closes",
    "enrollment closes", "enrolment closes",
    "click the link", "link in bio", "swipe up to buy",
    "book a call", "schedule a call", "subscribe now",
)

# Minimum usable offer-token length after normalization (a 1-char token would
# match everything — such a "name" is not a real product name).
_MIN_OFFER_TOKEN_LEN = 2


class ProverInputError(Exception):
    """Raised when a required input cannot be verified -> fail-closed (exit 3)."""


# ---------------------------------------------------------------------------
# Deterministic helpers.
# ---------------------------------------------------------------------------
def _norm(text: str) -> str:
    """Casefold + collapse all whitespace. This is the STRIPPED text every match
    is measured against, so padding/formatting can never hide a leak."""
    return " ".join(str(text).casefold().split())


def _iter_strings(node: Any) -> Iterable[str]:
    """Yield every string anywhere inside a slide entry (dict/list/scalar)."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _iter_strings(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _iter_strings(v)


def _slide_blob(slide: dict) -> str:
    """Normalized concatenation of every string on a slide (copy, headline,
    bullets, tags, suggested_image seed, ...). The offer name must not appear
    ANYWHERE on a teaching slide — not even in the image seed."""
    return _norm(" \n ".join(_iter_strings(slide)))


def _slide_num(slide: dict) -> Optional[int]:
    v = slide.get("slide")
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def _load_json(path: Path, label: str) -> Any:
    if not path.exists():
        raise ProverInputError(
            f"AF-SP-INPUT-MISSING: required {label} not found at {path}. "
            "Cannot prove Phase-3 no-pitch hygiene on a missing input -> fail-closed."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ProverInputError(
            f"AF-SP-INPUT-MISSING: {label} at {path} is not readable/valid JSON "
            f"({exc}). An unverifiable input is a HARD ABORT -> fail-closed."
        )


def _phase_ids(contract: Any) -> Tuple[str, str]:
    """Derive (teaching_id, pitch_id) from the sacred contract if present, else
    the fleet defaults ('teaching','pitch'). Teaching = the no_pitch phase;
    pitch = the pitch_included phase (or the phase ordered right after teaching)."""
    teaching_id, pitch_id = "teaching", "pitch"
    if not isinstance(contract, dict):
        return teaching_id, pitch_id
    phases = contract.get("phases")
    if not isinstance(phases, list):
        return teaching_id, pitch_id
    teach_order = None
    for ph in phases:
        if isinstance(ph, dict) and ph.get("no_pitch") is True and isinstance(ph.get("id"), str):
            teaching_id = ph["id"]
            teach_order = ph.get("order")
    found_pitch = False
    for ph in phases:
        if isinstance(ph, dict) and ph.get("pitch_included") is True and isinstance(ph.get("id"), str):
            pitch_id = ph["id"]
            found_pitch = True
    if not found_pitch and isinstance(teach_order, int):
        for ph in phases:
            if isinstance(ph, dict) and ph.get("order") == teach_order + 1 and isinstance(ph.get("id"), str):
                pitch_id = ph["id"]
    return teaching_id.lower(), pitch_id.lower()


def _offer_tokens(intake: Any) -> List[str]:
    """Normalized, deduped offer/product tokens from the q7 offer-token ledger."""
    if not isinstance(intake, dict):
        return []
    raw: List[str] = []
    led = intake.get("offer_token_ledger")
    if isinstance(led, list):
        raw += [x for x in led if isinstance(x, str)]
    q7 = intake.get("q7_offer_products")
    if isinstance(q7, list):
        raw += [x for x in q7 if isinstance(x, str)]
    out: List[str] = []
    seen = set()
    for t in raw:
        n = _norm(t)
        if len(n) >= _MIN_OFFER_TOKEN_LEN and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _slides_of(slides: List[dict], phase_id: str) -> List[dict]:
    return [s for s in slides
            if isinstance(s, dict) and str(s.get("phase", "")).strip().lower() == phase_id]


# ---------------------------------------------------------------------------
# Core evaluation. Pure + deterministic. Returns a list of AF violation strings
# (empty == clean). Raises ProverInputError for fail-closed preconditions.
# ---------------------------------------------------------------------------
def evaluate(intake: Any, ledger: Any, contract: Any) -> List[str]:
    teaching_id, pitch_id = _phase_ids(contract)

    slides = ledger.get("slides") if isinstance(ledger, dict) else ledger
    if not isinstance(slides, list) or not slides:
        raise ProverInputError(
            "AF-SP-LEDGER-EMPTY: the deck copy ledger carries no slides -> "
            "fail-closed (nothing to prove)."
        )

    offer_tokens = _offer_tokens(intake)
    if not offer_tokens:
        raise ProverInputError(
            "AF-SP-OFFER-LEDGER-MISSING: intake carries no non-empty "
            "offer_token_ledger (the exact q7 product name(s)). With no offer "
            "names there is nothing to prove absent from Phase 3 -> a PASS would "
            "be vacuous, so this is fail-closed."
        )

    teaching = _slides_of(slides, teaching_id)
    pitch = _slides_of(slides, pitch_id)

    if not teaching:
        raise ProverInputError(
            f"AF-SP-TEACH-EMPTY: the copy ledger has no Phase-3 ('{teaching_id}') "
            "slides. Phase-3 no-pitch hygiene cannot be proven on an absent phase "
            "-> fail-closed (mislabeling a phase can never buy a PASS)."
        )

    # Every teaching + pitch slide must carry a valid integer index (needed for
    # the bridge handoff and to anchor violation messages).
    teach_nums: List[int] = []
    for s in teaching:
        n = _slide_num(s)
        if n is None:
            raise ProverInputError(
                "AF-SP-SLIDE-INDEX: a Phase-3 teaching slide is missing a valid "
                f"integer 'slide' index: {json.dumps(s)[:160]} -> fail-closed."
            )
        teach_nums.append(n)
    pitch_nums: List[int] = []
    for s in pitch:
        n = _slide_num(s)
        if n is None:
            raise ProverInputError(
                "AF-SP-SLIDE-INDEX: a Phase-4 pitch slide is missing a valid "
                f"integer 'slide' index: {json.dumps(s)[:160]} -> fail-closed."
            )
        pitch_nums.append(n)

    failures: List[str] = []

    # --- Checks 1-3: scan EVERY teaching slide (incl. the bridge) --------------
    for s in sorted(teaching, key=lambda x: _slide_num(x) or 0):
        num = _slide_num(s)
        blob = _slide_blob(s)

        for tok in offer_tokens:
            if tok in blob:
                failures.append(
                    f"AF-SP-PITCH-IN-TEACH: Phase-3 ('{teaching_id}') slide {num} "
                    f"names the offer/product {tok!r}. Phase 3 is NO-PITCH — the q7 "
                    "offer name(s) are forbidden here and belong only in the Phase-4 "
                    "pitch."
                )
                break  # one offer-name hit per slide is enough to fail the gate.

        m = PRICE_RE.search(blob)
        if m:
            failures.append(
                f"AF-SP-PRICE-IN-TEACH: Phase-3 ('{teaching_id}') slide {num} "
                f"contains a price token {m.group(0).strip()!r}. Phase 3 must teach, "
                "not sell — no price/monetary tokens are allowed."
            )

        for cta in CTA_TOKENS:
            if cta in blob:
                failures.append(
                    f"AF-SP-CTA-IN-TEACH: Phase-3 ('{teaching_id}') slide {num} "
                    f"contains sale/enroll CTA language {cta!r}. Phase 3 forbids "
                    "offer/enroll/scarcity calls-to-action."
                )
                break  # one CTA hit per slide is enough.

    # --- Check 4: the Phase-3 -> Phase-4 bridge handoff -----------------------
    if not pitch_nums:
        failures.append(
            "AF-SP-BRIDGE: there are no Phase-4 (pitch) slides, so the Phase-3 -> "
            "Phase-4 bridge handoff cannot be satisfied. The final teaching step "
            "must bridge directly into the pitch."
        )
    else:
        last_teach = max(teach_nums)
        first_pitch = min(pitch_nums)
        if last_teach + 1 != first_pitch:
            failures.append(
                "AF-SP-BRIDGE: the Phase-3 -> Phase-4 handoff is not contiguous "
                f"(last teaching slide {last_teach}, first pitch slide {first_pitch}). "
                "The final teaching step (the bridge) must sit directly before the "
                "first pitch slide with no gap or overlap."
            )

    return failures


def evaluate_paths(intake_path: Path, ledger_path: Path,
                   contract_path: Optional[Path]) -> Tuple[int, List[str]]:
    """Load inputs, evaluate, and return (exit_code, messages) WITHOUT exiting."""
    try:
        intake = _load_json(intake_path, "runtime intake (offer_token_ledger)")
        ledger = _load_json(ledger_path, "deck copy ledger")
        contract: Any = None
        if contract_path is not None and contract_path.exists():
            try:
                contract = _load_json(contract_path, "structure contract")
            except ProverInputError:
                contract = None  # contract is optional; safe defaults apply.
        failures = evaluate(intake, ledger, contract)
    except ProverInputError as exc:
        return EXIT_FAILCLOSED, [str(exc)]
    if failures:
        return EXIT_VIOLATION, failures
    return EXIT_OK, []


# ---------------------------------------------------------------------------
# Self-test — build fixtures on a temp run dir, assert the VALID one PASSES and
# every VIOLATION one exits NONZERO through the REAL load+evaluate path.
# ---------------------------------------------------------------------------
def _fixture_intake(with_offer: bool = True) -> dict:
    return {
        "deck_type": "signature_presentation",
        "offer_token_ledger": (["The Momentum Method", "Momentum Mastermind"]
                               if with_offer else []),
        "answers": {"q7_offer_products": "The Momentum Method and the Momentum Mastermind"},
    }


def _fixture_ledger(variant: str = "valid") -> dict:
    slides: List[dict] = [
        {"slide": 1, "phase": "avatar", "suggested_image": "a weary professional at a late desk", "tags": []},
        {"slide": 2, "phase": "avatar", "suggested_image": "an empty conference room at dawn", "tags": []},
        {"slide": 3, "phase": "story", "suggested_image": "a young dreamer at a window", "tags": []},
        {"slide": 4, "phase": "story", "suggested_image": "a fork in a mountain trail", "tags": []},
    ]
    t5 = {"slide": 5, "phase": "teaching", "label_slide": True,
          "suggested_image": "a bold chapter-title card",
          "copy": "Step One: Name the pattern. Awareness is where momentum begins.",
          "tags": ["STEP_1"]}
    t6 = {"slide": 6, "phase": "teaching",
          "suggested_image": "a person taking one small daily action",
          "copy": "Step Two: Stack one small win each day. Bite by bite.",
          "tags": ["STEP_2"]}
    t7 = {"slide": 7, "phase": "teaching",
          "suggested_image": "a sunrise breaking over an open path",
          "copy": "Final Step: Bring it all together. Everything you have practiced "
                  "points to what comes next.",
          "tags": ["STEP_3", "BRIDGE"]}
    p8 = {"slide": 8, "phase": "pitch",
          "suggested_image": "the program cover",
          "copy": "Introducing The Momentum Method. Enroll now for just $1,997.",
          "tags": ["OFFER"]}
    p9 = {"slide": 9, "phase": "pitch",
          "suggested_image": "a guarantee badge",
          "copy": "Join the Momentum Mastermind today. 30-day money-back guarantee.",
          "tags": ["CLOSE"]}
    slides += [t5, t6, t7, p8, p9]

    if variant == "offer_in_teach":
        t6["copy"] = "Step Two: This is exactly where The Momentum Method changes everything."
    elif variant == "price_in_teach":
        t6["copy"] = "Step Two: Stack your wins. Most people pay $1,997 to learn this."
    elif variant == "cta_in_teach":
        t6["copy"] = "Step Two: Ready to go deeper? Enroll now and reserve your spot."
    elif variant == "bridge_gap":
        # Leave slide 8 unused -> last teaching 7, first pitch 9 -> gap.
        p8["slide"] = 9
        p9["slide"] = 10
    elif variant == "valid":
        pass
    return {"slides": slides}


def _run_fixture(tmp: Path, intake_obj: dict, ledger_obj: dict) -> Tuple[int, List[str]]:
    ip = tmp / "sp_intake.json"
    lp = tmp / "sp_structure.json"
    ip.write_text(json.dumps(intake_obj), encoding="utf-8")
    lp.write_text(json.dumps(ledger_obj), encoding="utf-8")
    code, msgs = evaluate_paths(ip, lp, None)
    return code, msgs


def self_test() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="sp_no_pitch_selftest_"))
    try:
        # (a) VALID fixture -> PASS (exit 0).
        code, msgs = _run_fixture(tmp, _fixture_intake(True), _fixture_ledger("valid"))
        assert code == EXIT_OK, f"VALID fixture must PASS (exit 0), got {code}: {msgs}"
        assert not msgs, f"VALID fixture must have no findings, got {msgs}"
        print("[self-test] VALID fixture -> PASS (exit 0)  OK")

        # (b) VIOLATION fixtures -> each must exit NONZERO.
        cases = [
            ("offer_in_teach", EXIT_VIOLATION, "AF-SP-PITCH-IN-TEACH"),
            ("price_in_teach", EXIT_VIOLATION, "AF-SP-PRICE-IN-TEACH"),
            ("cta_in_teach", EXIT_VIOLATION, "AF-SP-CTA-IN-TEACH"),
            ("bridge_gap", EXIT_VIOLATION, "AF-SP-BRIDGE"),
        ]
        for variant, want_code, want_af in cases:
            code, msgs = _run_fixture(tmp, _fixture_intake(True), _fixture_ledger(variant))
            assert code != EXIT_OK, f"{variant!r} must exit NONZERO, got {code}"
            assert code == want_code, f"{variant!r} expected exit {want_code}, got {code}: {msgs}"
            joined = " || ".join(msgs)
            assert want_af in joined, f"{variant!r} expected {want_af} in findings, got {msgs}"
            print(f"[self-test] VIOLATION {variant!r} -> exit {code} ({want_af})  OK")

        # (c) FAIL-CLOSED: empty offer ledger -> nonzero (exit 3).
        code, msgs = _run_fixture(tmp, _fixture_intake(False), _fixture_ledger("valid"))
        assert code != EXIT_OK, f"empty offer ledger must exit NONZERO, got {code}"
        assert code == EXIT_FAILCLOSED, f"empty offer ledger expected exit {EXIT_FAILCLOSED}, got {code}: {msgs}"
        assert any("AF-SP-OFFER-LEDGER-MISSING" in m for m in msgs), msgs
        print(f"[self-test] FAIL-CLOSED empty-offer-ledger -> exit {code}  OK")

        # (d) FAIL-CLOSED: missing input file -> nonzero (exit 3).
        code, msgs = evaluate_paths(tmp / "does_not_exist.json", tmp / "also_missing.json", None)
        assert code == EXIT_FAILCLOSED, f"missing input expected exit {EXIT_FAILCLOSED}, got {code}: {msgs}"
        print(f"[self-test] FAIL-CLOSED missing-input -> exit {code}  OK")

        print("[self-test] ALL ASSERTIONS PASSED")
        return EXIT_OK
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------
def _repo_root() -> Path:
    # scripts/prove_sp_no_pitch.py  ->  <repo>/scripts  ->  <repo>
    return Path(__file__).resolve().parent.parent


def _resolve_inputs(args) -> Tuple[Path, Path, Optional[Path]]:
    intake = Path(args.intake).expanduser() if args.intake else None
    ledger = Path(args.ledger).expanduser() if args.ledger else None
    contract = Path(args.contract).expanduser() if args.contract else None

    if args.run_dir:
        rd = Path(args.run_dir).expanduser()
        if intake is None:
            cand = rd / "working" / "copy" / "sp_intake.json"
            intake = cand if cand.exists() else rd / "sp_intake.json"
        if ledger is None:
            cand = rd / "working" / "copy" / "sp_structure.json"
            ledger = cand if cand.exists() else rd / "sp_structure.json"

    if contract is None:
        default_contract = _repo_root() / "structure" / "sp_structure.json"
        contract = default_contract if default_contract.exists() else None

    if intake is None or ledger is None:
        raise ProverInputError(
            "AF-SP-INPUT-MISSING: provide --run-dir, or both --intake and --ledger. "
            "The prover needs the runtime intake (offer_token_ledger) and the deck "
            "copy ledger -> fail-closed."
        )
    return intake, ledger, contract


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed prover: Phase-3 (teaching) no-pitch hygiene for a "
                    "Signature Presentation.")
    ap.add_argument("--run-dir", help="run dir holding working/copy/sp_intake.json "
                                       "and working/copy/sp_structure.json")
    ap.add_argument("--intake", help="explicit runtime intake JSON (offer_token_ledger)")
    ap.add_argument("--ledger", help="explicit deck COPY ledger JSON (per-slide entries)")
    ap.add_argument("--contract", help="sacred structure ledger (defaults to repo "
                                       "structure/sp_structure.json)")
    ap.add_argument("--self-test", action="store_true",
                    help="run built-in valid + violation fixtures and assert")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    try:
        intake_path, ledger_path, contract_path = _resolve_inputs(args)
    except ProverInputError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FAILCLOSED

    code, msgs = evaluate_paths(intake_path, ledger_path, contract_path)
    if code == EXIT_OK:
        print("PASS: Phase-3 (teaching) no-pitch hygiene verified — no offer name, "
              "price, or CTA in Phase 3, and the Phase-3->Phase-4 bridge is contiguous.")
    else:
        label = "FAIL-CLOSED" if code == EXIT_FAILCLOSED else "VIOLATION"
        print(f"{label}: Phase-3 no-pitch prover failed:", file=sys.stderr)
        for m in msgs:
            print("  - " + m, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
