#!/usr/bin/env python3
"""tests/unit/presentation-intake-trace-wiring.test.py

REGRESSION GUARD — T0-12 / A10: the intake-trace checker was declared advisory.

51-signature-presentation/SKILL.md states that EVERY rule is machine-enforced by
a fail-closed prover and never advisory, yet the intake-trace checker (the rule
that defines this skill's value — choice-first, one question per turn) was the
one rule nothing enforced. prove_sp_routing.py's WIRE_SYMBOLS list did not name
_chk_sp_intake_trace, so --check-wiring could not refuse an engine that dropped
the gate: an eight-question batched interaction that supplied its own intake
RECORD as the only evidence of how the intake was CONDUCTED sailed through every
preflight to a signed certificate.

THE FIX (already on main, commit 1b2664e6): _chk_sp_intake_trace joins
WIRE_SYMBOLS, so check_wiring() refuses an engine that does not DEFINE and
REGISTER the wrapper.

WHAT THIS FILE PROVES (hermetic: staged engine sources in a tempdir; no network,
no box state, nothing outside the checkout is written):

  T1  the REAL engine build_deck.py passes --check-wiring (all five wrappers
      defined + registered, including _chk_sp_intake_trace)
  T2  WIRE_SYMBOLS names _chk_sp_intake_trace (the promotion is load-bearing)
  T3  an engine MISSING the _chk_sp_intake_trace definition -> AF-SP-UNWIRED
  T4  an engine that DEFINES but does not REGISTER _chk_sp_intake_trace ->
      AF-SP-UNWIRED (defined-but-unregistered is still a gap)
  T5  MUTATION PROOF: drop _chk_sp_intake_trace from WIRE_SYMBOLS and the
      missing-wrapper engine from T3 silently PASSES (RED); restore it and the
      engine is refused again (GREEN). This is the exact regression the fix
      closes — without the symbol in the list, the gate can vanish unnoticed.

Run: python3 tests/unit/presentation-intake-trace-wiring.test.py
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL51 = REPO_ROOT / "51-signature-presentation"
PROVER = SKILL51 / "scripts" / "prove_sp_routing.py"
ENGINE = (REPO_ROOT / "23-ai-workforce-blueprint" / "templates" / "role-library"
          / "presentations" / "scripts" / "build_deck.py")

PASSN = 0
FAILN = 0


def pass_(m):
    global PASSN
    PASSN += 1
    print("  PASS: %s" % m)


def fail_(m, extra=""):
    global FAILN
    FAILN += 1
    print("  FAIL: %s" % m)
    if extra:
        print("        %s" % extra)


def _load_prover():
    spec = importlib.util.spec_from_file_location("prove_sp_routing_under_test", PROVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _engine_missing_def(tmp: Path) -> Path:
    """An engine that defines + registers every wrapper EXCEPT the intake-trace
    definition is removed entirely."""
    src = ENGINE.read_text(encoding="utf-8")
    # Drop the def line for the intake-trace wrapper so check_wiring sees no def.
    lines = [ln for ln in src.splitlines()
             if "def _chk_sp_intake_trace(" not in ln]
    p = tmp / "build_deck_no_trace_def.py"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _engine_unregistered(tmp: Path) -> Path:
    """An engine that DEFINES _chk_sp_intake_trace but never REGISTERS it in
    PREFLIGHT_REQUIRED (the '<sym>)' reference is stripped)."""
    src = ENGINE.read_text(encoding="utf-8")
    lines = [ln if "_chk_sp_intake_trace)" not in ln else ln.replace("_chk_sp_intake_trace)", "_REMOVED)")
             for ln in src.splitlines()]
    p = tmp / "build_deck_unregistered.py"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def main() -> int:
    prover = _load_prover()
    tmp = Path(tempfile.mkdtemp(prefix="spwire_"))
    try:
        # ---- T1: real engine passes --check-wiring -------------------------
        if not ENGINE.is_file():
            fail_("T1 engine build_deck.py not found at %s" % ENGINE)
        else:
            failures = prover.check_wiring(ENGINE)
            if failures == []:
                pass_("T1 real engine passes --check-wiring (all five wrappers wired)")
            else:
                fail_("T1 real engine FAILED --check-wiring", str(failures)[:400])

        # ---- T2: WIRE_SYMBOLS names the intake-trace wrapper ---------------
        if "_chk_sp_intake_trace" in prover.WIRE_SYMBOLS:
            pass_("T2 WIRE_SYMBOLS includes _chk_sp_intake_trace (promotion load-bearing)")
        else:
            fail_("T2 _chk_sp_intake_trace missing from WIRE_SYMBOLS", str(prover.WIRE_SYMBOLS))

        # ---- T3: engine missing the definition -> AF-SP-UNWIRED ------------
        if ENGINE.is_file():
            no_def = _engine_missing_def(tmp)
            failures = prover.check_wiring(no_def)
            codes = [c for c, _ in failures]
            msgs = " ".join(m for _, m in failures)
            if prover.AF_UNWIRED in codes and "_chk_sp_intake_trace" in msgs:
                pass_("T3 engine missing _chk_sp_intake_trace def -> AF-SP-UNWIRED")
            else:
                fail_("T3 missing-def engine was NOT refused", str(failures)[:400])

            # ---- T4: defined but not registered -> AF-SP-UNWIRED -----------
            unreg = _engine_unregistered(tmp)
            failures = prover.check_wiring(unreg)
            codes = [c for c, _ in failures]
            msgs = " ".join(m for _, m in failures)
            if prover.AF_UNWIRED in codes and "_chk_sp_intake_trace" in msgs:
                pass_("T4 defined-but-unregistered _chk_sp_intake_trace -> AF-SP-UNWIRED")
            else:
                fail_("T4 unregistered engine was NOT refused", str(failures)[:400])

        # ---- T5: MUTATION PROOF --------------------------------------------
        # Mutate: drop _chk_sp_intake_trace from WIRE_SYMBOLS. The missing-def
        # engine from T3 must now silently PASS (the regression the fix closes).
        original = prover.WIRE_SYMBOLS
        mutated = tuple(s for s in original if s != "_chk_sp_intake_trace")
        prover.WIRE_SYMBOLS = mutated
        try:
            no_def = _engine_missing_def(tmp)
            failures_mutated = prover.check_wiring(no_def)
            if failures_mutated == []:
                pass_("T5 RED: with _chk_sp_intake_trace dropped from WIRE_SYMBOLS, "
                      "the missing-wrapper engine silently passes (regression exposed)")
            else:
                fail_("T5 mutation did not expose the regression", str(failures_mutated)[:400])
        finally:
            prover.WIRE_SYMBOLS = original  # revert

        # Revert proof: with the symbol restored, the engine is refused again.
        no_def = _engine_missing_def(tmp)
        failures_restored = prover.check_wiring(no_def)
        if prover.AF_UNWIRED in [c for c, _ in failures_restored]:
            pass_("T5 GREEN: with WIRE_SYMBOLS restored, the missing-wrapper engine "
                  "is refused again (AF-SP-UNWIRED)")
        else:
            fail_("T5 revert did not restore enforcement", str(failures_restored)[:400])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n=== %d passed, %d failed ===" % (PASSN, FAILN))
    return 1 if FAILN else 0


if __name__ == "__main__":
    sys.exit(main())
