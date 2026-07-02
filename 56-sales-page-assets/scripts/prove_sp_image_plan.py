#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_image_plan.py — fail-closed prover for the Direct-Response IMAGE PLAN (Skill 56).
Closes the legacy engine's slice bug: with the default prompt count of 4, the upsell / downsell
/ high-ticket image slices were all EMPTY (ANALYSIS §7.4). This prover enforces that EVERY
funnel stage gets at least one image and the prompt indices are a contiguous, complete set.
NO AI, stdlib only.

WHAT IT ENFORCES:
  * at least one prompt exists (else fail-closed).              -> AF-SP56-IMGPLAN-EMPTY
  * image_prompt_count is an int in [1,20] and equals len(prompts). -> AF-SP56-IMGPLAN-COUNT
  * prompt indices are contiguous 0..N-1 with no gaps/dupes.    -> AF-SP56-IMGPLAN-INDEX
  * every prompt carries non-empty prompt text.                 -> AF-SP56-IMGPLAN-EMPTY-PROMPT
  * every required stage (main, upsell-1, downsell-1,
    high-ticket) has >= 1 image assigned.                       -> AF-SP56-IMGPLAN-SLICE-EMPTY

Stage is taken from an explicit per-prompt `stage`, else derived from the index via the
canonical slice map (structure/spa-intake.schema.json image_slice_map):
  main [0:4]  upsell-1 [4:8]  downsell-1 [8:10]  high-ticket [10:].

stdlib only. Exit 0 = pass, exit 2 = autofail, exit 3 = usage/IO (still fail-closed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_EMPTY = "AF-SP56-IMGPLAN-EMPTY"
AF_COUNT = "AF-SP56-IMGPLAN-COUNT"
AF_INDEX = "AF-SP56-IMGPLAN-INDEX"
AF_EMPTY_PROMPT = "AF-SP56-IMGPLAN-EMPTY-PROMPT"
AF_SLICE = "AF-SP56-IMGPLAN-SLICE-EMPTY"

REQUIRED_STAGES = ("main", "upsell-1", "downsell-1", "high-ticket")


def _derive_stage(idx: int) -> str:
    if idx < 4:
        return "main"
    if idx < 8:
        return "upsell-1"
    if idx < 10:
        return "downsell-1"
    return "high-ticket"


def _norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or "")).strip().lower()


def _prompt_text(p: Dict[str, Any]) -> str:
    for k in ("prompt_text", "prompt", "text"):
        if p.get(k):
            return str(p[k])
    return ""


def evaluate(plan: Any) -> List[Tuple[str, str]]:
    if not isinstance(plan, dict):
        return [(AF_EMPTY, "plan root is not a JSON object")]
    prompts = plan.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        return [(AF_EMPTY, "no image prompts in the plan (cannot prove slice coverage; fail-closed)")]

    fails: List[Tuple[str, str]] = []
    n = len(prompts)

    declared = plan.get("image_prompt_count")
    if isinstance(declared, bool) or not isinstance(declared, int) or not (1 <= declared <= 20):
        fails.append((AF_COUNT, f"image_prompt_count must be an int in [1,20], got {declared!r}"))
    elif declared != n:
        fails.append((AF_COUNT, f"image_prompt_count {declared} != number of prompts {n}"))

    indices: List[Optional[int]] = []
    stage_hits: Dict[str, int] = {s: 0 for s in REQUIRED_STAGES}
    for pos, p in enumerate(prompts):
        if not isinstance(p, dict):
            fails.append((AF_INDEX, f"prompt at position {pos} is not an object"))
            continue
        idx = p.get("index", pos)
        indices.append(idx if isinstance(idx, int) else None)
        if not _prompt_text(p).strip():
            fails.append((AF_EMPTY_PROMPT, f"prompt index {idx} has empty prompt text"))
        stage = _norm(p.get("stage")) or _norm(_derive_stage(idx if isinstance(idx, int) else pos))
        # normalize to hyphenated required-stage keys
        stage_key = {"upsell1": "upsell-1", "downsell1": "downsell-1",
                     "highticket": "high-ticket"}.get(stage, stage)
        if stage_key in stage_hits:
            stage_hits[stage_key] += 1

    clean = [i for i in indices if isinstance(i, int)]
    if sorted(clean) != list(range(n)):
        fails.append((AF_INDEX, f"prompt indices {indices} are not contiguous 0..{n-1} (gap/dupe/missing)"))

    for s in REQUIRED_STAGES:
        if stage_hits[s] == 0:
            fails.append((AF_SLICE, f"stage {s!r} has 0 images — slice empty (legacy slice bug). "
                                    f"Raise image_prompt_count (>=12) or reassign."))
    return fails


def decide_exit(failures) -> int:
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def prove(path: str, as_json: bool = False) -> int:
    p = Path(path)
    if not p.is_file():
        _emit(str(p), [("USAGE", f"plan not found: {p}")], as_json)
        return EXIT_USAGE
    try:
        plan = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit(str(p), [("USAGE", f"cannot read/parse plan JSON: {exc}")], as_json)
        return EXIT_USAGE
    failures = evaluate(plan)
    _emit(str(p), failures, as_json)
    return decide_exit(failures)


def _emit(source: str, failures, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"gate": "sales-page-assets-image-plan", "source": source,
                          "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print("== Sales Page Assets :: IMAGE PLAN slice coverage ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — contiguous prompt set; every stage slice has >=1 image.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def _valid_plan(n: int = 12) -> Dict[str, Any]:
    return {
        "image_prompt_count": n,
        "prompts": [{"index": i, "stage": _derive_stage(i),
                     "prompt_text": f"A vivid brand image number {i} for the funnel."}
                    for i in range(n)],
    }


def self_test() -> int:
    ok = True

    def check_pass(name, fixture):
        nonlocal ok
        fails = evaluate(fixture)
        good = not fails
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:16s} -> exit {decide_exit(fails)}"
              + ("" if good else f" (unexpected: {fails})"))

    def check_fail(name, fixture, expect):
        nonlocal ok
        fails = evaluate(fixture)
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:22s} -> codes={codes} (want {expect})")

    print("== self-test: VALID fixtures (must PASS) ==")
    check_pass("count-12", _valid_plan(12))
    check_pass("count-16", _valid_plan(16))

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    # legacy default of 4 leaves upsell/downsell/high-ticket empty
    check_fail("legacy-count-4", _valid_plan(4), AF_SLICE)

    f = _valid_plan(12); f["image_prompt_count"] = 11
    check_fail("count-mismatch", f, AF_COUNT)

    f = _valid_plan(12); f["prompts"][5]["index"] = 99
    check_fail("index-gap", f, AF_INDEX)

    f = _valid_plan(12); f["prompts"][10]["prompt_text"] = "   "
    check_fail("empty-prompt", f, AF_EMPTY_PROMPT)

    check_fail("no-prompts", {"image_prompt_count": 0, "prompts": []}, AF_EMPTY)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for the IMAGE PLAN slice coverage.")
    ap.add_argument("--plan", help="path to image_plan.json / prompt_ledger.json")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.plan:
        print("USAGE ERROR: pass --plan <image_plan.json> (or --self-test).")
        return EXIT_USAGE
    return prove(args.plan, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
