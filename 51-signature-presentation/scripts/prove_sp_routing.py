#!/usr/bin/env python3
"""
prove_sp_routing.py -- P-SP-CLAIM routing/claim gate.

WORK-ITEM-06: This prover runs UNCONDITIONALLY for EVERY deck (does NOT defer).
If the run carries signature-presentation signals (an sp_intake.json, a set
Signature frame, a frame-selection question, or a 'signature presentation'
request) but intake.json does NOT declare deck_type == signature_presentation,
fail-closed AF-SP-TYPE-UNDECLARED.

A non-signature deck with no SP signal passes untouched.

Called by build_deck._chk_sp_claim() and by deck-intake-driver.py at --complete.
The evaluate_run_dir() function is the single entry point imported by both callers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    """Read a JSON file, returning None on any failure."""
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
            return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _read_intake_json(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Read working/copy/intake.json."""
    return _read_json(run_dir / "working" / "copy" / "intake.json")


# ---------------------------------------------------------------------------
# SP signal detection -- the four indicators that a deck IS signature
# ---------------------------------------------------------------------------
def _sp_signals_present(run_dir: Path) -> bool:
    """Return True if ANY signature-presentation signal is detected in the run
    directory. The presence of ANY of these signals means the run carries SP
    intent, and the claim gate must fire if deck_type is not declared.

    Signals checked:
      1. working/copy/sp_intake.json exists (the atomic SP intake record)
      2. A signature_frame is set in intake.json (rulebook|vault|quest|original)
      3. A frame-selection question was answered (signature_frame in ledger)
      4. The intake ledger records a 'signature presentation' request
    """
    # Signal 1: sp_intake.json exists
    if (run_dir / "working" / "copy" / "sp_intake.json").is_file():
        return True

    intake = _read_intake_json(run_dir)
    if intake:
        # Signal 2: a signature_frame is set in intake
        sig_frame = intake.get("signature_frame")
        if sig_frame and sig_frame in ("rulebook", "vault", "quest", "original"):
            return True

        # Signal 3: presentation_type declares signature
        if intake.get("presentation_type") == "signature":
            return True

    # Signal 4: intake ledger records signature intent
    ledger = _read_json(run_dir / "working" / "interview" / "intake_ledger.json")
    if ledger:
        entries = ledger.get("entries") or {}
        sp_entries = ledger.get("sp_entries") or {}
        # frame selection question answered
        if "signature_frame" in entries or "signature_frame" in sp_entries:
            return True
        # presentation_type declared as signature
        ptype_e = entries.get("presentation_type", {})
        if isinstance(ptype_e, dict) and ptype_e.get("value") == "signature":
            return True
        # sp_mode set (QUICK or IN-DEPTH -- the signature choice-first question)
        if "sp_mode" in sp_entries:
            return True

    return False


# ---------------------------------------------------------------------------
# evaluate_run_dir -- the single entry point
# ---------------------------------------------------------------------------
def evaluate_run_dir(run_dir: Path) -> List[Tuple[str, str]]:
    """P-SP-CLAIM: the routing/claim gate. Runs UNCONDITIONALLY for EVERY deck.

    Returns a list of (code, reason) tuples for each failure found.
    Empty list = PASS (no claim-gate violation).

    Rules:
      1. If NO SP signals are present: PASS (empty list). This is a non-SP deck.
      2. If SP signals ARE present but intake.json does not declare
         deck_type == signature_presentation: FAIL AF-SP-TYPE-UNDECLARED.
         The deck has signature intent but omitted the magic word, which
         makes every downstream SP gate defer (no-op).
      3. If SP signals ARE present AND deck_type == signature_presentation:
         PASS (the claim is declared and the SP gates will engage).
    """
    sp_present = _sp_signals_present(run_dir)

    if not sp_present:
        return []

    intake = _read_intake_json(run_dir)
    declared = intake and intake.get("deck_type") == "signature_presentation"

    if declared:
        return []

    # SP signals present but deck_type not declared -- the claim gap.
    # This is the highest-severity skip: a signature deck built through the
    # generic path by omitting the magic word.
    reason_parts = ["AF-SP-TYPE-UNDECLARED: signature-presentation signals "
                    "detected but intake.json does not declare "
                    "deck_type == signature_presentation."]

    if (run_dir / "working" / "copy" / "sp_intake.json").is_file():
        reason_parts.append(
            "working/copy/sp_intake.json is present -- this is a signature "
            "deck with an atomic SP intake record.")

    if intake:
        reason_parts.append(
            f"intake.json.deck_type is {intake.get('deck_type')!r} "
            f"(must be 'signature_presentation' for the SP gates to engage).")
    else:
        reason_parts.append(
            "intake.json is absent -- deck_type was never set by the intake "
            "driver. Run deck-intake-driver.py --next/--answer/--complete "
            "to set it.")

    reason_parts.append(
        "Omitting the magic word makes every SP gate defer (no-op) -- "
        "a signature deck would build with zero SP enforcement.")

    return [("AF-SP-TYPE-UNDECLARED", " ".join(reason_parts))]


# ---------------------------------------------------------------------------
# evaluate -- alternate entry for direct sp_intake.json validation
# ---------------------------------------------------------------------------
def evaluate(sp_intake_path: Path) -> List[Tuple[str, str]]:
    """Validate a standalone sp_intake.json record (used by prove_sp_intake
    compatibility path). This function is a thin wrapper that directly validates
    the record; it does NOT run the claim gate (use evaluate_run_dir for that).

    Returns list of (code, reason) failures. Empty list on pass.
    """
    obj = _read_json(sp_intake_path)
    if obj is None:
        return [("AF-SP-8Q-MISSING",
                 f"sp_intake.json is missing or unreadable at {sp_intake_path}")]

    failures = []

    # Check for required fields
    if not obj.get("signature_frame"):
        failures.append(("AF-SP-8Q-SPLIT",
                         "sp_intake.json has no signature_frame -- the frame "
                         "must be selected and recorded atomically."))

    if not obj.get("record_committed_atomically") and not obj.get("one_block"):
        failures.append(("AF-SP-8Q-SPLIT",
                         "sp_intake.json is not marked as an atomic commit -- "
                         "the 8 Questions + frame must be ONE record, never "
                         "split across multiple writes."))

    # Check mode declaration
    mode = obj.get("mode", "")
    if mode not in ("QUICK", "IN-DEPTH"):
        failures.append(("AF-SP-8Q-SPLIT",
                         f"sp_intake.json mode is {mode!r} -- must be QUICK "
                         f"or IN-DEPTH."))

    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    """CLI entry. Usage: python3 prove_sp_routing.py --run-dir <DIR> [--json]

    Also supports legacy: python3 prove_sp_routing.py <sp_intake.json>
    for direct record validation (prove_sp_intake compatibility).
    """
    import argparse
    p = argparse.ArgumentParser(
        prog="prove_sp_routing.py",
        description="P-SP-CLAIM: Signature-Presentation routing/claim gate. "
                    "Runs for EVERY deck -- fail-closed AF-SP-TYPE-UNDECLARED "
                    "when SP signals exist but deck_type is not declared.")
    p.add_argument("--run-dir", type=Path,
                   help="the deck's run directory (for evaluate_run_dir)")
    p.add_argument("--json", action="store_true",
                   help="output as JSON")
    p.add_argument("file", nargs="?", type=Path,
                   help="direct sp_intake.json path (for evaluate)")
    args = p.parse_args()

    if args.run_dir:
        run_dir = args.run_dir.expanduser().resolve()
        failures = evaluate_run_dir(run_dir)
    elif args.file:
        failures = evaluate(args.file.expanduser().resolve())
    else:
        p.print_help()
        return 2

    if args.json:
        import json as _json
        print(_json.dumps({
            "status": "PASS" if not failures else "FAIL",
            "failures": [{"code": c, "reason": r} for c, r in failures],
        }, indent=2))
    else:
        if not failures:
            print("PASS: no SP claim-gate violation.")
        else:
            for code, reason in failures:
                print(f"FAIL [{code}]: {reason}")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
