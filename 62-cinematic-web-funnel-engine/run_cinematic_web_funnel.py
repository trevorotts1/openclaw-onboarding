#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_cinematic_web_funnel.py — the deterministic Cinematic and Web Funnel Engine
orchestrator (Skill 62).

A no-skip, manifest-driven state machine. It loads CWFE-MANIFEST.json, walks the
phase spine P0..P16 IN ORDER, and for each phase shells that phase's declared
`gate` script if it exists on disk. A missing or failing gate aborts the
run (fail-closed) and NO certificate is written, so an incomplete or
non-compliant run can never reach Certified.

CERTIFICATE OWNERSHIP (ONE signed certificate, ONE signing scheme): the
P16-CERTIFY gate — scripts/prove_certificate.py — is the SOLE emitter of the
signed PROCESS-CERTIFICATE.json. When the orchestrator runs P16 as a phase gate
(`prove_certificate.py --run-dir <run_dir>`), that prover re-aggregates the
whole spine and, only on a fully-clean run, writes the REAL HMAC-SHA256-signed
certificate (keyed by the run-scoped front-door nonce). This orchestrator must
therefore NEVER mint its own certificate: after the phase loop finishes green it
only PRESERVES and independently re-verifies the prover's certificate (through
`prove_certificate.py --verify`), never overwriting it with a placeholder. An
earlier build of this file signed its own weak nonce-keyed sha256 "seed" hash
here and clobbered the real certificate; that reconciliation is now done — the
finale is `_finalize_certificate()`, not a second signer.

FRONT-DOOR NONCE (ADR-6, required): the canonical entry shell
(cinematic-web-funnel-entry.sh) writes a run-scoped 0600 nonce file
(<run-dir>/.cwfe_run_nonce) and passes its value with --nonce. This orchestrator
refuses to run unless the supplied nonce matches that file's content exactly —
a direct `python3 run_cinematic_web_funnel.py` call without the front-door nonce
dies with AF-CWFE-FRONT-DOOR. This is the mechanism the task calls "reject
direct script exec without a run nonce."

DELEGATION SEAMS (never forked here): phase gate scripts named in the manifest
own their own logic; this orchestrator's job is sequencing, nonce enforcement,
and certificate emission — never business logic for a phase.

Run-dir outputs:
  phase-status.json       — per-phase result ledger, written after every attempt
  PROCESS-CERTIFICATE.json — emitted ONLY when every mandatory phase passes

stdlib only. Exit 0 = certified, 2 = a phase gate failed/missing, 3 = front-door/usage.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_MANIFEST_PATH = _SCRIPT_DIR / "CWFE-MANIFEST.json"

EXIT_OK = 0
EXIT_GATE_FAIL = 2
EXIT_FRONT_DOOR = 3

PY = sys.executable or "python3"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _die_front_door(msg: str) -> None:
    print(f"ABORT [AF-CWFE-FRONT-DOOR]: {msg}", file=sys.stderr)
    sys.exit(EXIT_FRONT_DOOR)


def _load_manifest() -> Dict[str, Any]:
    if not _MANIFEST_PATH.exists():
        _die_front_door(f"CWFE-MANIFEST.json not found at {_MANIFEST_PATH}")
    try:
        with _MANIFEST_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        _die_front_door(f"CWFE-MANIFEST.json is not valid JSON: {exc}")
    return {}  # unreachable, keeps type-checkers calm


def _validate_manifest(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Validate the phase spine is contiguous P0..P16 with unique AF codes.
    Returns the phases sorted by `order`. Dies fail-closed on any violation —
    a malformed manifest must never silently produce a partial or reordered run."""
    phases = manifest.get("phases")
    if not isinstance(phases, list) or not phases:
        _die_front_door("manifest has no phases[] array")
    phases_sorted = sorted(phases, key=lambda p: p.get("order", -1))
    orders = [p.get("order") for p in phases_sorted]
    if orders != list(range(len(orders))):
        _die_front_door(f"manifest phase order is not contiguous starting at 0: {orders}")
    if len(phases_sorted) != 17:
        _die_front_door(f"manifest must declare exactly 17 phases (P0..P16), found {len(phases_sorted)}")
    ids = [p.get("id") for p in phases_sorted]
    if ids[0] != "P0-ENVIRONMENT" or ids[-1] != "P16-CERTIFY":
        _die_front_door(f"manifest phase ids do not start at P0-ENVIRONMENT / end at P16-CERTIFY: {ids}")
    af_codes = [p.get("af_code") for p in phases_sorted]
    af_codes += [c.get("af_code") for c in manifest.get("cross_cutting_af_codes", [])]
    if len(af_codes) != len(set(af_codes)):
        _die_front_door("manifest has duplicate AF codes across phases/cross_cutting_af_codes")
    if any(code is None for code in af_codes):
        _die_front_door("manifest has a phase or cross-cutting entry missing af_code")
    return phases_sorted


def _require_nonce(run_dir: Path, supplied_nonce: str) -> None:
    """ADR-6 enforcement point. Dies AF-CWFE-FRONT-DOOR unless the supplied
    --nonce matches the front door's run-scoped nonce file exactly."""
    nonce_file = run_dir / ".cwfe_run_nonce"
    if not supplied_nonce:
        _die_front_door(
            "no --nonce supplied. This orchestrator must never be invoked directly; "
            "run it through cinematic-web-funnel-entry.sh, which mints the run-scoped nonce."
        )
    if not nonce_file.exists():
        _die_front_door(
            f"no front-door nonce file at {nonce_file}. Run through cinematic-web-funnel-entry.sh."
        )
    on_disk = nonce_file.read_text(encoding="utf-8").strip()
    if supplied_nonce.strip() != on_disk:
        _die_front_door("supplied --nonce does not match the front door's nonce file")


def _run_phase_gate(run_dir: Path, phase: Dict[str, Any]) -> Tuple[str, str]:
    """Run a single phase's declared gate script. Returns (status, detail).
    status is one of: PASS, FAIL, GATE-SCRIPT-MISSING."""
    gate_rel = phase.get("gate")
    if not gate_rel:
        return "FAIL", f"phase {phase.get('id')} declares no gate"
    gate_path = _SCRIPT_DIR / gate_rel
    if not gate_path.exists():
        return (
            "GATE-SCRIPT-MISSING",
            f"{gate_rel} not found — {phase.get('af_code')} (phase not yet implemented in this build unit)",
        )
    proc = subprocess.run(
        [PY, str(gate_path), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
    )
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    detail = tail[-1] if tail else f"rc={proc.returncode}"
    if proc.returncode == 0:
        return "PASS", detail
    return "FAIL", f"{gate_rel} rc={proc.returncode} :: {detail} — {phase.get('af_code')}"


def _write_phase_status(run_dir: Path, results: List[Dict[str, Any]]) -> None:
    payload = {"generated_at": _now(), "phases": results}
    (run_dir / "phase-status.json").write_text(
        json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8"
    )


_CERT_PROVER = _SCRIPT_DIR / "scripts" / "prove_certificate.py"


def _finalize_certificate(run_dir: Path) -> Tuple[bool, str]:
    """Preserve + independently re-verify the certificate the P16-CERTIFY gate
    (scripts/prove_certificate.py) already wrote during the phase loop.

    This orchestrator NEVER signs or overwrites the certificate itself — the
    P16 prover is the sole emitter of the real HMAC-SHA256-signed
    PROCESS-CERTIFICATE.json (keyed by the run-scoped front-door nonce). Here we
    only confirm that certificate is on disk and re-verify it through the
    prover's own standalone ``--verify`` path (nonce read from
    <run_dir>/.cwfe_run_nonce), so there is exactly ONE certificate and ONE
    signing scheme. Fail-closed: a missing certificate, or one that fails
    re-verification, aborts the run WITHOUT fabricating a placeholder."""
    cert_path = run_dir / "PROCESS-CERTIFICATE.json"
    if not cert_path.exists():
        return False, (
            "every phase passed but the P16-CERTIFY gate left no PROCESS-CERTIFICATE.json on disk — "
            "refusing to fabricate a placeholder certificate (the prover is the sole certificate emitter)"
        )
    proc = subprocess.run(
        [PY, str(_CERT_PROVER), "--verify", str(cert_path), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
    )
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    detail = tail[-1] if tail else f"rc={proc.returncode}"
    if proc.returncode != 0:
        return False, f"the emitted PROCESS-CERTIFICATE.json failed independent re-verification :: {detail}"
    return True, detail


def run_pipeline(run_dir: Path, nonce: str) -> int:
    _require_nonce(run_dir, nonce)
    manifest = _load_manifest()
    phases = _validate_manifest(manifest)

    results: List[Dict[str, Any]] = []
    overall_ok = True
    for phase in phases:
        status, detail = _run_phase_gate(run_dir, phase)
        results.append(
            {
                "id": phase.get("id"),
                "order": phase.get("order"),
                "name": phase.get("name"),
                "af_code": phase.get("af_code"),
                "status": status,
                "detail": detail,
                "checked_at": _now(),
            }
        )
        print(f"[{status}] {phase.get('id')} — {detail}")
        if status != "PASS":
            overall_ok = False
            break  # no-skip means IN ORDER; stop at the first non-pass, never skip ahead

    _write_phase_status(run_dir, results)

    if overall_ok and len(results) == len(phases):
        finalized, detail = _finalize_certificate(run_dir)
        if finalized:
            print(f"RESULT: CERTIFIED — PROCESS-CERTIFICATE.json (HMAC-SHA256, prover-signed) preserved and re-verified. {detail}")
            return EXIT_OK
        print(f"RESULT: NOT CERTIFIED — {detail}", file=sys.stderr)
        return EXIT_GATE_FAIL

    print("RESULT: NOT CERTIFIED — a phase gate failed or is not yet implemented.", file=sys.stderr)
    return EXIT_GATE_FAIL


def self_test() -> int:
    """Manifest-load + phase-order integrity self-test. Requires no run directory
    and no phase gate scripts — this only proves the orchestrator's own mechanics."""
    manifest = _load_manifest()
    phases = _validate_manifest(manifest)
    print(f"  [PASS] CWFE-MANIFEST.json loads and validates: {len(phases)} phases, contiguous order 0..16")
    ids = [p["id"] for p in phases]
    expected_prefixes = [f"P{i}-" for i in range(17)]
    for prefix, pid in zip(expected_prefixes, ids):
        if not pid.startswith(prefix):
            print(f"  [FAIL] phase id {pid} does not start with expected prefix {prefix}", file=sys.stderr)
            return EXIT_GATE_FAIL
    print("  [PASS] every phase id carries its correct P<N>- prefix in order")
    print("RESULT: PASS — orchestrator self-test green.")
    return EXIT_OK


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cinematic and Web Funnel Engine orchestrator (Skill 62). "
        "Never invoke directly — use cinematic-web-funnel-entry.sh."
    )
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--nonce", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if not args.run_dir:
        _die_front_door("--run-dir is required")
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        _die_front_door(f"--run-dir does not exist: {run_dir}")

    sys.exit(run_pipeline(run_dir, args.nonce))


if __name__ == "__main__":
    main()
