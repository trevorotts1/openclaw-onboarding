#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_intake.py — fail-closed deterministic prover for the Signature Funnel
intake gate (Skill 49). NO AI, NO network, stdlib only.

WHAT IT ENFORCES (the locked, provenance-gated brief that unlocks generation):
  * funnel_type == "signature_funnel".                          -> AF-FUN-INTAKE-TYPE
  * every REQUIRED intake answer is present + non-empty. The required set is gated by
    funnel size (Q1-Q11 + Q15-Q17 always; +Q12/Q13 for 5/7-step; +Q14 for 7-step).
                                                                 -> AF-FUN-INTAKE-MISSING
  * funnel_size is one of 3 / 5 / 7 (Q10).                       -> AF-FUN-INTAKE-SIZE
  * offer_token_ledger is non-empty — the exact offer name(s) from Q1 (the provenance
    seed the no-pitch + provenance gates depend on).             -> AF-FUN-INTAKE-OFFER
  * representation (Q8) is explicitly provided, never assumed.   -> AF-FUN-INTAKE-REPRESENTATION
  * the onboarding TRUTH GATE (Q16) is confirmed: a real community URL, a named bonus,
    and the founder-text confirmed true (Section 11 always promises these four).
                                                                 -> AF-FUN-INTAKE-TRUTHGATE
  * the brief is LOCKED (provenance-gated) before generation.    -> AF-FUN-INTAKE-UNLOCKED

The prover reads either the runtime brief (an `answers` object) or the section spec
(intake/sf-intake-questions.json, a `questions` list). Both resolve through one model.

stdlib only. Exit 0 = pass, exit 2 = autofail, exit 3 = usage/IO (still fail-closed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_TYPE = "AF-FUN-INTAKE-TYPE"
AF_MISSING = "AF-FUN-INTAKE-MISSING"
AF_SIZE = "AF-FUN-INTAKE-SIZE"
AF_OFFER = "AF-FUN-INTAKE-OFFER"
AF_REP = "AF-FUN-INTAKE-REPRESENTATION"
AF_TRUTH = "AF-FUN-INTAKE-TRUTHGATE"
AF_UNLOCKED = "AF-FUN-INTAKE-UNLOCKED"

FUNNEL_TYPE = "signature_funnel"
VALID_SIZES = (3, 5, 7)

# Required intake answer keys (Part 8 sequence). Checkpoint-gated by funnel size.
BASE_REQUIRED = (
    "q1_offer", "q2_price_promise", "q3_pains", "q4_people", "q5_goods",
    "q6_founder_story", "q7_brand_colors", "q8_representation", "q9_voice",
    "q10_funnel_length", "q11_oto1", "q15_reference_images", "q16_truth_gate",
    "q17_confirmation",
)
REQUIRED_5_7 = ("q12_downsell1", "q13_oto2")   # 5-step and 7-step
REQUIRED_7 = ("q14_downsell2",)                # 7-step only

_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INTAKE = _SCRIPT_DIR.parent / "intake" / "sf-intake-questions.json"


def _nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _answered(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    if isinstance(v, bool):
        return True
    return True


def _resolve_size(intake: Dict[str, Any]) -> Optional[int]:
    if isinstance(intake.get("funnel_size"), int):
        return intake["funnel_size"]
    answers = intake.get("answers")
    src = None
    if isinstance(answers, dict):
        src = answers.get("q10_funnel_length") or answers.get("funnel_size")
    src = src if src is not None else intake.get("q10_funnel_length")
    if isinstance(src, int):
        return src
    if _nonempty_str(src):
        for n in VALID_SIZES:
            if str(n) in src:
                return n
    return None


def _required_for(size: Optional[int]) -> Tuple[str, ...]:
    req = list(BASE_REQUIRED)
    if size in (5, 7):
        req += list(REQUIRED_5_7)
    if size == 7:
        req += list(REQUIRED_7)
    return tuple(req)


def _resolve_truth_gate(intake: Dict[str, Any]) -> Any:
    if isinstance(intake.get("truth_gate"), dict):
        return intake["truth_gate"]
    answers = intake.get("answers")
    if isinstance(answers, dict) and isinstance(answers.get("q16_truth_gate"), dict):
        return answers["q16_truth_gate"]
    return None


def evaluate(intake: Any) -> List[Tuple[str, str]]:
    failures: List[Tuple[str, str]] = []
    if not isinstance(intake, dict):
        return [(AF_TYPE, "intake root is not a JSON object")]

    ftype = intake.get("funnel_type")
    if ftype is not None and ftype != FUNNEL_TYPE:
        failures.append((AF_TYPE, f"funnel_type is {ftype!r}, expected {FUNNEL_TYPE!r}"))

    answers = intake.get("answers")
    if isinstance(answers, dict):
        # runtime brief shape — the full locked-brief gate applies.
        size = _resolve_size(intake)
        if size not in VALID_SIZES:
            failures.append((AF_SIZE, f"funnel_size resolves to {size!r}, must be one of {VALID_SIZES}"))
        required = _required_for(size)
        missing = [q for q in required if not _answered(answers.get(q))]
        if missing:
            failures.append((AF_MISSING, "missing/empty required answers: " + ", ".join(missing)))

        rep = answers.get("q8_representation")
        if not _answered(rep) or intake.get("representation_assumed") is True:
            failures.append((AF_REP, "representation (Q8) not explicitly provided — never assumed"))

        ledger = intake.get("offer_token_ledger")
        if not (isinstance(ledger, list) and any(_nonempty_str(x) for x in ledger)):
            failures.append((AF_OFFER, "offer_token_ledger missing/empty — Q1 offer name(s) not declared"))

        tg = _resolve_truth_gate(intake)
        if not isinstance(tg, dict):
            failures.append((AF_TRUTH, "truth gate (Q16) missing — community URL / bonus / founder-text unconfirmed"))
        else:
            if not _nonempty_str(tg.get("community_url")):
                failures.append((AF_TRUTH, "truth gate: community_url missing/empty"))
            if not _nonempty_str(tg.get("bonus")):
                failures.append((AF_TRUTH, "truth gate: bonus not named"))
            if tg.get("founder_text_confirmed") is not True:
                failures.append((AF_TRUTH, "truth gate: founder_text_confirmed is not true"))

        if intake.get("locked") is not True:
            failures.append((AF_UNLOCKED, "brief is not locked (provenance-gated) — generation must not start"))
    else:
        # spec-contract shape: every question id must be defined with a non-empty prompt
        defined = {}
        questions = intake.get("questions")
        if isinstance(questions, list):
            for item in questions:
                if isinstance(item, dict):
                    defined[item.get("id")] = item.get("prompt")
        spec_required = [f"q{i}" for i in range(1, 18)]
        missing = [q for q in spec_required if not _nonempty_str(defined.get(q))]
        if missing:
            failures.append((AF_MISSING, "spec is missing question definitions: " + ", ".join(missing)))

    return failures


def decide_exit(failures) -> int:
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def prove(path: str, as_json: bool = False) -> int:
    p = Path(path)
    if not p.is_file():
        _emit(str(p), [("USAGE", f"intake file not found: {p}")], as_json)
        return EXIT_USAGE
    try:
        intake = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit(str(p), [("USAGE", f"cannot read/parse intake JSON: {exc}")], as_json)
        return EXIT_USAGE
    failures = evaluate(intake)
    _emit(str(p), failures, as_json)
    return decide_exit(failures)


def _emit(source: str, failures, as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "gate": "signature-funnel-intake",
            "source": source,
            "pass": not failures,
            "failures": [{"code": c, "message": m} for c, m in failures],
        }, indent=2))
        return
    print("== Signature Funnel :: intake gate ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — locked brief satisfies the intake gate; generation may unlock.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def _valid_runtime(size: int = 3) -> Dict[str, Any]:
    answers = {
        "q1_offer": "The 5AM Reset — a 21-day morning transformation course",
        "q2_price_promise": "$97; their mornings feel calm and owned within 21 days",
        "q3_pains": "exhausted mornings; broken promises to self; kids watching them stay stuck",
        "q4_people": "founders, parents, creators, leaders who want calm and output",
        "q5_goods": "21 daily modules, 4 live calls, a workbook, a private community",
        "q6_founder_story": "burned out at a desk job; decided at 4:47am; built it for tired builders",
        "q7_brand_colors": "deep emerald green and warm gold",
        "q8_representation": "70% Black women, 20% mixed, 10% men",
        "q9_voice": "bold, warm, street-smart",
        "q10_funnel_length": f"{size}-step",
        "q11_oto1": "The Momentum Accelerator, done-with-you sprint, $197, 40 seats",
        "q15_reference_images": "signature only",
        "q16_truth_gate": {"community_url": "https://community.example.com/reset",
                            "bonus": "the 5-minute morning audio", "founder_text_confirmed": True},
        "q17_confirmation": "approved",
    }
    if size in (5, 7):
        answers["q12_downsell1"] = "recordings-only tier at $47"
        answers["q13_oto2"] = "the in-person retreat, categorically different, $997, 20 seats"
    if size == 7:
        answers["q14_downsell2"] = "single retreat day pass at $297"
    return {
        "funnel_type": "signature_funnel",
        "one_question_per_turn": True,
        "locked": True,
        "funnel_size": size,
        "answers": answers,
        "offer_token_ledger": ["The 5AM Reset"],
    }


def self_test() -> int:
    ok = True

    def check_pass(name, fixture):
        nonlocal ok
        fails = evaluate(fixture)
        good = not fails and decide_exit(fails) == EXIT_PASS
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:16s} -> exit {decide_exit(fails)}"
              + ("" if good else f" (unexpected: {fails})"))

    def check_fail(name, fixture, expect):
        nonlocal ok
        fails = evaluate(fixture)
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:18s} -> codes={codes} (want {expect})")

    print("== self-test: VALID fixtures (must PASS) ==")
    check_pass("3-step", _valid_runtime(3))
    check_pass("5-step", _valid_runtime(5))
    check_pass("7-step", _valid_runtime(7))

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    f = _valid_runtime(3); f["funnel_type"] = "sales_page"
    check_fail("type-mismatch", f, AF_TYPE)

    f = _valid_runtime(3); del f["answers"]["q5_goods"]
    check_fail("missing-answer", f, AF_MISSING)

    f = _valid_runtime(7); del f["answers"]["q14_downsell2"]
    check_fail("missing-d2-on-7step", f, AF_MISSING)

    f = _valid_runtime(3); f["funnel_size"] = 4; f["answers"]["q10_funnel_length"] = "4-step"
    check_fail("bad-size", f, AF_SIZE)

    f = _valid_runtime(3); f["offer_token_ledger"] = []
    check_fail("empty-offer", f, AF_OFFER)

    f = _valid_runtime(3); f["answers"]["q8_representation"] = "   "
    check_fail("no-representation", f, AF_REP)

    f = _valid_runtime(3); f["answers"]["q16_truth_gate"]["founder_text_confirmed"] = False
    check_fail("truth-gate-unconfirmed", f, AF_TRUTH)

    f = _valid_runtime(3); f["locked"] = False
    check_fail("brief-unlocked", f, AF_UNLOCKED)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed prover for the Signature Funnel intake gate.")
    ap.add_argument("intake", nargs="?", default=str(DEFAULT_INTAKE),
                    help="path to the intake/brief JSON (default: intake/sf-intake-questions.json)")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    return prove(args.intake, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
