#!/usr/bin/env python3
"""
prove-deck.py — PROCESS-INTEGRITY PROVER for the presentations pipeline.

Called by run_signature_deck.py at P9-DELIVER (before the delivery gate) and as
a standalone runner-gate CI step. Verifies that the FULL pipeline was actually
executed — not just that the final artifact exists — by inspecting:

  1. process_manifest.json attestation chain — every governed phase must be
     attested (or carry an owner-authorized skip).
  2. phase_reports.json — every phase that declares client_report must have both
     a "start" record and a "done" record (no silent drops).
  3. Substance verifiers (phase_verifiers.py) — each attested phase produced
     non-trivially substantive output.

AUTOFAIL CODES EMITTED BY THIS RUNNER (enforced_by:"runner", py_symbol:null):
  AF-PHASE-REPORT-MISSING  — a governed phase with client_report has ZERO records
                              in phase_reports.json
  AF-PHASE-REPORT-START    — a governed phase has a done record but no start record
  AF-PHASE-REPORT-DONE     — a governed phase has a start record but no done record
  AF-PROCESS-INTEGRITY     — process_manifest.json attestation chain is
                              missing, malformed, incomplete, or inconsistent with
                              the manifest's governed phases

EXIT CODES
  0 — all integrity checks pass
  1 — one or more checks failed (details printed to stderr)

USAGE
  python3 prove-deck.py --run-dir DIR [--manifest MANIFEST_JSON]
  python3 prove-deck.py --selftest
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent

MANIFEST_PATH = (
    HERE.parents[3]
    / "universal-sops"
    / "presentation-slide-craft"
    / "PIPELINE-MANIFEST.json"
)

# ---------------------------------------------------------------------------
# Manifest loader
# ---------------------------------------------------------------------------

def _load_manifest(override: Optional[Path] = None) -> dict:
    p = override or MANIFEST_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        _fatal(f"cannot load manifest from {p}: {exc}")


# ---------------------------------------------------------------------------
# Process manifest helpers
# ---------------------------------------------------------------------------

def _load_pm(run_dir: Path) -> Optional[dict]:
    p = run_dir / "working" / "checkpoints" / "process_manifest.json"
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return None
        return obj
    except Exception:
        return None


def _load_phase_reports(run_dir: Path) -> list:
    p = run_dir / "working" / "checkpoints" / "phase_reports.json"
    if not p.exists():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            return obj
        return []
    except Exception:
        return []


def _load_skip_approvals(run_dir: Path) -> dict:
    p = run_dir / "working" / "checkpoints" / "phase_skip_approvals.json"
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return obj
        return {}
    except Exception:
        return {}


def _fatal(msg: str) -> None:
    print(f"[prove-deck] FATAL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def _warn(msg: str) -> None:
    print(f"[prove-deck] FAIL: {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Check 1: Attestation chain integrity → AF-PROCESS-INTEGRITY
# ---------------------------------------------------------------------------

def _check_process_integrity(run_dir: Path, phases: list, skip_approvals: dict) -> list:
    """Returns list of AF-PROCESS-INTEGRITY failure strings."""
    failures = []
    pm = _load_pm(run_dir)
    if pm is None:
        failures.append(
            "AF-PROCESS-INTEGRITY: process_manifest.json not found or unreadable at "
            f"{run_dir / 'working' / 'checkpoints' / 'process_manifest.json'}. "
            "The attestation chain is entirely absent — no phase was provably run "
            "under the governed runner."
        )
        return failures

    attestations = pm.get("phase_attestations", [])
    if not isinstance(attestations, list):
        failures.append(
            "AF-PROCESS-INTEGRITY: process_manifest.json has 'phase_attestations' "
            "but it is not a list — manifest is malformed."
        )
        return failures

    attested_ids = {
        a["phase_id"] for a in attestations
        if isinstance(a, dict) and "phase_id" in a
    }

    # Every governed phase must be attested or owner-skip-approved.
    for ph in phases:
        pid = ph.get("id", "")
        if not pid:
            continue
        if pid in attested_ids:
            continue
        if pid in skip_approvals and skip_approvals[pid].get("owner_approved"):
            continue
        failures.append(
            f"AF-PROCESS-INTEGRITY: phase {pid!r} (order={ph.get('order')}) has "
            "no attestation record and no owner-authorized skip — the attestation "
            "chain is incomplete."
        )

    return failures


# ---------------------------------------------------------------------------
# Check 2: Phase report presence → AF-PHASE-REPORT-MISSING / START / DONE
# ---------------------------------------------------------------------------

def _check_phase_reports(run_dir: Path, phases: list) -> list:
    """Returns list of AF-PHASE-REPORT-* failure strings."""
    failures = []
    reports = _load_phase_reports(run_dir)

    # Build a map: phase_id -> set of record kinds
    phase_kinds: dict[str, set] = {}
    for rec in reports:
        if not isinstance(rec, dict):
            continue
        pid = rec.get("phase_id", "")
        kind = rec.get("kind", "")
        if pid and kind:
            phase_kinds.setdefault(pid, set()).add(kind)

    for ph in phases:
        pid = ph.get("id", "")
        if not pid:
            continue
        # Only governed phases with a client_report declaration need reports.
        if not isinstance(ph.get("client_report"), dict):
            continue
        kinds = phase_kinds.get(pid, set())
        if not kinds:
            failures.append(
                f"AF-PHASE-REPORT-MISSING: phase {pid!r} declares client_report "
                "but has zero records in phase_reports.json — the client was never "
                "informed of phase start or completion."
            )
            continue
        if "start" not in kinds:
            failures.append(
                f"AF-PHASE-REPORT-START: phase {pid!r} has a done record but no "
                "'start' record in phase_reports.json — the start report was dropped."
            )
        if "done" not in kinds:
            failures.append(
                f"AF-PHASE-REPORT-DONE: phase {pid!r} has a start record but no "
                "'done' record in phase_reports.json — the phase was never marked "
                "complete to the client."
            )

    return failures


# ---------------------------------------------------------------------------
# Check 3: Substance verifiers (phase_verifiers.py)
# ---------------------------------------------------------------------------

def _check_substance(run_dir: Path, phases: list) -> list:
    """Returns list of substance failure strings."""
    try:
        sys.path.insert(0, str(HERE))
        import phase_verifiers as pv
    except ImportError as exc:
        return [f"[prove-deck] Cannot import phase_verifiers: {exc}"]
    failures_raw = pv.verify_all_phases(run_dir, phases)
    return [f"substance check failed for {pid}: {reason}" for pid, reason in failures_raw]


# ---------------------------------------------------------------------------
# Main prover
# ---------------------------------------------------------------------------

def prove(run_dir: Path, manifest_override: Optional[Path] = None) -> list:
    """Run all integrity checks. Returns list of failure strings (empty = all pass)."""
    manifest = _load_manifest(manifest_override)
    phases = manifest.get("phases", [])
    skip_approvals = _load_skip_approvals(run_dir)

    failures = []
    failures.extend(_check_process_integrity(run_dir, phases, skip_approvals))
    failures.extend(_check_phase_reports(run_dir, phases))
    failures.extend(_check_substance(run_dir, phases))
    return failures


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _selftest() -> None:
    """Deterministic self-tests. All must pass. Exits 0 on success, 1 on failure."""
    test_fails = []

    # -- Test 1: missing process_manifest.json => AF-PROCESS-INTEGRITY --
    with tempfile.TemporaryDirectory(prefix="prove_deck_t1_") as tmp:
        rd = Path(tmp)
        phases = [{"id": "P0A-INTAKE", "order": 0.1, "produces_artifact": "working/copy/intake.json"}]
        skip = {}
        r = _check_process_integrity(rd, phases, skip)
        if not any("AF-PROCESS-INTEGRITY" in s for s in r):
            test_fails.append("T1: missing process_manifest should trigger AF-PROCESS-INTEGRITY")

    # -- Test 2: complete attestation chain => no AF-PROCESS-INTEGRITY --
    with tempfile.TemporaryDirectory(prefix="prove_deck_t2_") as tmp:
        rd = Path(tmp)
        (rd / "working" / "checkpoints").mkdir(parents=True)
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({
                "phase_attestations": [
                    {"phase_id": "P0A-INTAKE", "status": "artifact_present"}
                ]
            })
        )
        phases = [{"id": "P0A-INTAKE", "order": 0.1}]
        r = _check_process_integrity(rd, phases, {})
        if r:
            test_fails.append(f"T2: complete chain should pass, got: {r}")

    # -- Test 3: phase with client_report and no records => AF-PHASE-REPORT-MISSING --
    with tempfile.TemporaryDirectory(prefix="prove_deck_t3_") as tmp:
        rd = Path(tmp)
        phases = [{"id": "P0A-INTAKE", "order": 0.1, "client_report": {"start_template": "x"}}]
        r = _check_phase_reports(rd, phases)
        if not any("AF-PHASE-REPORT-MISSING" in s for s in r):
            test_fails.append("T3: missing reports should trigger AF-PHASE-REPORT-MISSING")

    # -- Test 4: phase with only start report => AF-PHASE-REPORT-DONE --
    with tempfile.TemporaryDirectory(prefix="prove_deck_t4_") as tmp:
        rd = Path(tmp)
        (rd / "working" / "checkpoints").mkdir(parents=True)
        (rd / "working" / "checkpoints" / "phase_reports.json").write_text(
            json.dumps([{"phase_id": "P0A-INTAKE", "kind": "start"}])
        )
        phases = [{"id": "P0A-INTAKE", "order": 0.1, "client_report": {"start_template": "x", "done_template": "y"}}]
        r = _check_phase_reports(rd, phases)
        if not any("AF-PHASE-REPORT-DONE" in s for s in r):
            test_fails.append("T4: missing done report should trigger AF-PHASE-REPORT-DONE")

    # -- Test 5: phase with only done report => AF-PHASE-REPORT-START --
    with tempfile.TemporaryDirectory(prefix="prove_deck_t5_") as tmp:
        rd = Path(tmp)
        (rd / "working" / "checkpoints").mkdir(parents=True)
        (rd / "working" / "checkpoints" / "phase_reports.json").write_text(
            json.dumps([{"phase_id": "P0A-INTAKE", "kind": "done"}])
        )
        phases = [{"id": "P0A-INTAKE", "order": 0.1, "client_report": {"start_template": "x", "done_template": "y"}}]
        r = _check_phase_reports(rd, phases)
        if not any("AF-PHASE-REPORT-START" in s for s in r):
            test_fails.append("T5: missing start report should trigger AF-PHASE-REPORT-START")

    # -- Test 6: both start and done records => no failures --
    with tempfile.TemporaryDirectory(prefix="prove_deck_t6_") as tmp:
        rd = Path(tmp)
        (rd / "working" / "checkpoints").mkdir(parents=True)
        (rd / "working" / "checkpoints" / "phase_reports.json").write_text(
            json.dumps([
                {"phase_id": "P0A-INTAKE", "kind": "start"},
                {"phase_id": "P0A-INTAKE", "kind": "done"},
            ])
        )
        phases = [{"id": "P0A-INTAKE", "order": 0.1, "client_report": {"start_template": "x", "done_template": "y"}}]
        r = _check_phase_reports(rd, phases)
        if r:
            test_fails.append(f"T6: both start+done should pass, got: {r}")

    # -- Test 7: phase without client_report => no report failures --
    with tempfile.TemporaryDirectory(prefix="prove_deck_t7_") as tmp:
        rd = Path(tmp)
        phases = [{"id": "P4-RENDER", "order": 4.9}]  # no client_report key
        r = _check_phase_reports(rd, phases)
        if r:
            test_fails.append(f"T7: phase without client_report should not trigger report failures, got: {r}")

    if test_fails:
        for f in test_fails:
            print(f"[prove-deck selftest] FAIL: {f}", file=sys.stderr)
        sys.exit(1)
    print("[prove-deck selftest] PASS — all self-tests passed.", flush=True)
    sys.exit(0)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Presentations pipeline process-integrity prover.")
    parser.add_argument("--run-dir", help="Run directory (working/checkpoints must be inside).")
    parser.add_argument("--manifest", help="Override path to PIPELINE-MANIFEST.json.")
    parser.add_argument("--selftest", action="store_true", help="Run built-in self-tests.")
    args = parser.parse_args()

    if args.selftest:
        _selftest()

    if not args.run_dir:
        parser.error("--run-dir is required (or use --selftest).")

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        _fatal(f"--run-dir not found: {run_dir}")

    manifest_override = Path(args.manifest).resolve() if args.manifest else None

    print(f"[prove-deck] checking process integrity for run dir: {run_dir}", flush=True)
    failures = prove(run_dir, manifest_override)
    if not failures:
        print("[prove-deck] PASS — process integrity verified.", flush=True)
        sys.exit(0)

    print(f"\n[prove-deck] {len(failures)} integrity failure(s):", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
