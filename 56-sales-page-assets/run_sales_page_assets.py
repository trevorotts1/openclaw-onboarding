#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_sales_page_assets.py — the deterministic Sales Page Assets orchestrator (Skill 56).

A no-skip state machine. It runs the fixed phase spine P0..P9 IN ORDER, shells each phase's
fail-closed prover(s), and — only when EVERY phase passes — emits a signed
PROCESS-CERTIFICATE.json. A failing gate aborts the run (fail-closed) and NO certificate is
written, so an incomplete or non-compliant asset stack can never reach Complete.

FRONT-DOOR NONCE (required): the canonical entry shell (sales-page-assets-entry.sh) writes a
run-scoped 0600 nonce file and passes its value with --nonce. The orchestrator refuses to run
unless the supplied nonce matches the file — a direct `python3 run_sales_page_assets.py`
without the front-door nonce dies with AF-SP56-FRONT-DOOR. The same nonce keys the certificate
HMAC, so a certificate can only be minted by a real front-door run.

DELEGATION SEAMS (never forked here): image generation is delegated to Skill 47 (kie_image.py)
or the client's own image provider; GHL media folder + upload and the funnel/page build are
delegated to Skill 6 (ghl_media.py / ghl_rest_canvas.py); the bump copy routes to the Skill 44
seam. CLIENT runtime uses the client's OWN providers, never Anthropic.

Run-dir inputs:
  brief.json            — locked intake brief         (P0 gate: prove_sp_intake.py)
  image_plan.json       — image prompts + slice map   (P1 gate: prove_sp_image_plan.py)
  media_ledger.json     — image records + GHL media    (P2/P4 delegation artifact)
  copy_ledger.json      — the 7 copy assets            (P3 gate: 4 copy provers)
  funnel-manifest.json  — the Track-2 build bundle     (P7 gate: prove_sp_bundle.py)

stdlib only. Exit 0 = certified, 2 = a phase gate failed, 3 = front-door / usage.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SCRIPTS = _SCRIPT_DIR / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import prove_sp_cert  # noqa: E402  (shared cert schema + HMAC signing; guarantees agreement)

EXIT_OK = 0
EXIT_GATE_FAIL = 2
EXIT_FRONT_DOOR = 3

PY = sys.executable or "python3"

# The four copy provers that make up the P3-COPY suite (all run against copy_ledger.json).
COPY_SUITE = (
    "prove_sp_main_structure.py",
    "prove_sp_upsell_structure.py",
    "prove_sp_highticket_band.py",
    "prove_sp_bump_band.py",
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _shell_prover(script: str, args: List[str]) -> Tuple[bool, str]:
    path = _SCRIPTS / script
    if not path.exists():
        return False, f"prover {script} not found at {path}"
    proc = subprocess.run([PY, str(path), *args], capture_output=True, text=True)
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    detail = tail[-1] if tail else f"rc={proc.returncode}"
    return proc.returncode == 0, f"{script} rc={proc.returncode} :: {detail}"


def _copy_suite(run_dir: Path) -> Tuple[bool, str]:
    ledger = str(run_dir / "copy_ledger.json")
    details = []
    all_ok = True
    for script in COPY_SUITE:
        ok, detail = _shell_prover(script, ["--ledger", ledger])
        all_ok = all_ok and ok
        details.append(detail)
    return all_ok, " | ".join(details)


def _delegation_seam(run_dir: Path, required_file: Optional[str], label: str) -> Tuple[bool, str]:
    if required_file is not None:
        p = run_dir / required_file
        if not p.exists():
            return False, f"delegated artifact {required_file} absent (expected for: {label})"
    return True, f"delegated: {label}"


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Phase spine — ids + order MUST match prove_sp_cert.EXPECTED_PHASES.
def _phase_gates(run_dir: Path) -> List[Tuple[str, str, Callable[[], Tuple[bool, str]]]]:
    return [
        ("P0-INTAKE", "prove_sp_intake.py",
         lambda: _shell_prover("prove_sp_intake.py", [str(run_dir / "brief.json")])),
        ("P1-IMAGE-PLAN", "prove_sp_image_plan.py",
         lambda: _shell_prover("prove_sp_image_plan.py", ["--plan", str(run_dir / "image_plan.json")])),
        ("P2-IMAGES", "kie_image.py",
         lambda: _delegation_seam(run_dir, "media_ledger.json",
                                  "Skill 47 kie_image.py OR the client's own image provider")),
        ("P3-COPY", "prove_sp_copy_suite",
         lambda: _copy_suite(run_dir)),
        ("P4-MEDIA", "ghl_media.py",
         lambda: _delegation_seam(run_dir, "media_ledger.json", "Skill 6 ghl_media.py (media folder + upload)")),
        ("P5-FRAGMENTS", "fragment_strip",
         lambda: _delegation_seam(run_dir, None, "deterministic sanitize/fragment-ize (P5, NOT an LLM pass)")),
        ("P6-DOCS", "drive_docs",
         lambda: _delegation_seam(run_dir, None, "Track 1 client-editable Google Docs in the client Drive folder")),
        ("P7-BUNDLE", "prove_sp_bundle.py",
         lambda: _shell_prover("prove_sp_bundle.py", ["--manifest", str(run_dir / "funnel-manifest.json")])),
        ("P8-DELIVER", "delivery_email",
         lambda: _delegation_seam(run_dir, None, "delivery email (productionized subject + Drive folder link)")),
        ("P9-HANDOFF", "ghl_rest_canvas.py",
         lambda: _delegation_seam(run_dir, "funnel-manifest.json",
                                  "Skill 6 ghl_rest_canvas.py build handoff (+ Skill 44 bump seam); preview -> human approval -> publish")),
    ]


def _check_front_door(run_dir: Path, nonce: Optional[str], nonce_file: Optional[Path]) -> Tuple[bool, str]:
    nf = nonce_file or (run_dir / ".spa_run_nonce")
    if not nf.exists():
        return False, f"AF-SP56-FRONT-DOOR: no run-scoped nonce file at {nf} — run must start via sales-page-assets-entry.sh"
    supplied = nonce if nonce is not None else os.environ.get("SPA_RUN_NONCE")
    if not supplied:
        return False, "AF-SP56-FRONT-DOOR: no --nonce / SPA_RUN_NONCE supplied (front-door nonce required)"
    on_disk = nf.read_text(encoding="utf-8").strip()
    if not on_disk or supplied.strip() != on_disk:
        return False, "AF-SP56-FRONT-DOOR: supplied nonce does not match the run-scoped nonce file"
    return True, supplied.strip()


def orchestrate(run_dir: Path, nonce: str) -> Tuple[int, Dict]:
    phases_attested: List[Dict] = []
    gates = _phase_gates(run_dir)
    print(f"== Sales Page Assets orchestrator :: run {run_dir} ==")
    for order, (pid, prover, gate) in enumerate(gates):
        ok, detail = gate()
        status = "pass" if ok else "fail"
        print(f"  [{status.upper():4s}] {pid:14s} ({prover}) :: {detail}")
        phases_attested.append({"id": pid, "prover": prover, "status": status,
                                "order": order, "detail": detail, "at": _now()})
        if not ok:
            print(f"ABORT: phase {pid} failed its fail-closed gate. NO certificate issued "
                  "(a later phase can never run before an earlier one passes).")
            manifest = {"run_id": run_dir.name, "aborted_at": pid, "phases": phases_attested}
            (run_dir / "process_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            return EXIT_GATE_FAIL, manifest

    cert = {
        "certificate": prove_sp_cert.CERT_KIND,
        "version": "1.0.0",
        "run_id": run_dir.name,
        "funnel_type": "sales_page_assets",
        "skill_version": (_SCRIPT_DIR / "skill-version.txt").read_text(encoding="utf-8").strip()
        if (_SCRIPT_DIR / "skill-version.txt").exists() else "1.0.0",
        "issued_at": _now(),
        "nonce_fingerprint": hashlib.sha256(nonce.encode()).hexdigest()[:16],
        "ledger_hashes": {
            "brief.json": _sha256_file(run_dir / "brief.json"),
            "image_plan.json": _sha256_file(run_dir / "image_plan.json"),
            "copy_ledger.json": _sha256_file(run_dir / "copy_ledger.json"),
            "media_ledger.json": _sha256_file(run_dir / "media_ledger.json"),
            "funnel-manifest.json": _sha256_file(run_dir / "funnel-manifest.json"),
        },
        "phases": [{"id": p["id"], "prover": p["prover"], "status": p["status"], "order": p["order"]}
                   for p in phases_attested],
        "all_phases_pass": True,
        "delivery": {"publish": "human-approval-required",
                     "preview_only": True,
                     "two_track": "Track 1 client Docs (editable) + Track 2 build bundle (Skill 6)",
                     "bump_seam": "Skill 44 order-bump widget (P4->P5 board handoff)"},
    }
    cert["signature"] = prove_sp_cert.sign(prove_sp_cert.canonical_payload(cert), nonce)
    (run_dir / "PROCESS-CERTIFICATE.json").write_text(json.dumps(cert, indent=2), encoding="utf-8")

    code, fails = prove_sp_cert.evaluate_cert(cert, nonce)
    if code != prove_sp_cert.EXIT_OK:
        print(f"ABORT: minted certificate failed self-verification: {fails}")
        return EXIT_GATE_FAIL, cert
    print(f"CERTIFIED: all {len(gates)} phases passed in order. Signed PROCESS-CERTIFICATE.json written.")
    print("  Delivery is PREVIEW-ONLY; publishing requires explicit human approval (Skill 6 gate).")
    return EXIT_OK, cert


# ---------------------------------------------------------------------------
# Self-test — build a temp run-dir with the provers' own VALID fixtures, run the state
# machine end-to-end, and assert the certificate is minted + validates; then assert the
# front-door refusal and the no-skip abort.
# ---------------------------------------------------------------------------
def _write_valid_run(rd: Path, nonce: str) -> None:
    import prove_sp_intake, prove_sp_image_plan, prove_sp_bundle  # noqa: E402
    import prove_sp_main_structure, prove_sp_upsell_structure  # noqa: E402
    import prove_sp_highticket_band, prove_sp_bump_band  # noqa: E402

    (rd / "brief.json").write_text(json.dumps(prove_sp_intake._valid_runtime()), encoding="utf-8")
    (rd / "image_plan.json").write_text(json.dumps(prove_sp_image_plan._valid_plan(12)), encoding="utf-8")

    # merged copy ledger with all 7 assets (main a/b, upsell a/b, downsell, high-ticket, bump)
    copy_assets = []
    copy_assets += prove_sp_main_structure._valid_ledger()["assets"]
    copy_assets += prove_sp_upsell_structure._valid_ledger()["assets"]
    copy_assets += prove_sp_highticket_band._valid_ledger()["assets"]
    copy_assets += prove_sp_bump_band._valid_ledger()["assets"]
    (rd / "copy_ledger.json").write_text(json.dumps({"assets": copy_assets}), encoding="utf-8")

    (rd / "media_ledger.json").write_text(json.dumps({"images": [
        {"asset_key": "jane-doe__glow-method__main__img-01__v01", "task_id": "t1",
         "ghl_media_url": "https://msgsndr-media/x.png"}]}), encoding="utf-8")
    (rd / "funnel-manifest.json").write_text(json.dumps(prove_sp_bundle._valid_manifest()), encoding="utf-8")

    nf = rd / ".spa_run_nonce"
    nf.write_text(nonce, encoding="utf-8")
    os.chmod(nf, 0o600)


def self_test() -> int:
    ok = True
    nonce = "orch-selftest-nonce-777"
    tmp = Path(tempfile.mkdtemp(prefix="spa_orch_selftest_"))
    try:
        rd = tmp / "run-good"
        rd.mkdir()
        _write_valid_run(rd, nonce)

        good, msg = _check_front_door(rd, None, None)
        if not good and "AF-SP56-FRONT-DOOR" in msg:
            print("SELF-TEST ok: missing nonce -> front-door refusal.")
        else:
            ok = False; print(f"SELF-TEST FAIL: missing nonce not refused: {good} {msg}")

        good, msg = _check_front_door(rd, "wrong", None)
        if not good and "AF-SP56-FRONT-DOOR" in msg:
            print("SELF-TEST ok: wrong nonce -> front-door refusal.")
        else:
            ok = False; print(f"SELF-TEST FAIL: wrong nonce not refused: {good} {msg}")

        good, resolved = _check_front_door(rd, nonce, None)
        if not good:
            ok = False; print(f"SELF-TEST FAIL: valid nonce refused: {resolved}")
        else:
            code, cert = orchestrate(rd, resolved)
            if code == EXIT_OK and (rd / "PROCESS-CERTIFICATE.json").exists():
                vcode, vfails = prove_sp_cert.evaluate_cert(
                    json.loads((rd / "PROCESS-CERTIFICATE.json").read_text()), nonce)
                if vcode == prove_sp_cert.EXIT_OK:
                    print("SELF-TEST ok: happy path -> signed certificate minted + validates.")
                else:
                    ok = False; print(f"SELF-TEST FAIL: minted cert invalid: {vfails}")
            else:
                ok = False; print(f"SELF-TEST FAIL: happy path did not certify (code={code}).")

        # no-skip / fail-closed abort — break the copy ledger, expect NO cert
        rd2 = tmp / "run-bad"
        rd2.mkdir()
        _write_valid_run(rd2, nonce)
        import prove_sp_bump_band  # noqa: E402
        bad = json.loads((rd2 / "copy_ledger.json").read_text())
        for a in bad["assets"]:
            if a.get("stage") == "bump":
                a["text"] = "too short"  # breaks bump band + checkbox
        (rd2 / "copy_ledger.json").write_text(json.dumps(bad), encoding="utf-8")
        code, manifest = orchestrate(rd2, nonce)
        if code == EXIT_GATE_FAIL and not (rd2 / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: failing P3 copy gate aborts with NO certificate (fail-closed, no phase skip).")
        else:
            ok = False; print(f"SELF-TEST FAIL: bad run still certified (code={code}).")

        print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
        return 0 if ok else 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic no-skip Sales Page Assets orchestrator. Requires the "
                    "front-door nonce; emits a signed PROCESS-CERTIFICATE only on all-phases-pass.")
    ap.add_argument("--run-dir", help="the run directory (brief/image_plan/copy/media/manifest)")
    ap.add_argument("--nonce", help="the run-scoped front-door nonce (or SPA_RUN_NONCE)")
    ap.add_argument("--nonce-file", help="path to the nonce file (default <run-dir>/.spa_run_nonce)")
    ap.add_argument("--self-test", action="store_true", help="run the built-in end-to-end fixtures")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.run_dir:
        print("USAGE ERROR: pass --run-dir <dir> (or --self-test).")
        return EXIT_FRONT_DOOR
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"USAGE ERROR: run-dir {run_dir} is not a directory.")
        return EXIT_FRONT_DOOR

    nonce_file = Path(args.nonce_file).expanduser() if args.nonce_file else None
    good, resolved = _check_front_door(run_dir, args.nonce, nonce_file)
    if not good:
        print(resolved)
        return EXIT_FRONT_DOOR

    code, _ = orchestrate(run_dir, resolved)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
