#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_certificate.py — the P16-CERTIFY phase gate declared in
CWFE-MANIFEST.json (``"gate": "scripts/prove_certificate.py"``,
``"py_symbol": "prove_certificate.verify"``, ``"af_code": "AF-CWFE-P16-CERTIFY"``).
Also the cross-cutting AF-CWFE-SECRET-LEAK enforcement point the manifest
names (``"enforced_by": "scripts/prove_certificate.py (later unit) +
repository secret-scan gates"``, ``"py_symbol":
"prove_certificate.assert_no_secret_values"``) — this IS that later unit.

WHAT THIS MODULE IS (build unit U20)
-------------------------------------
A deterministic prover AGGREGATOR plus the signed PROCESS-CERTIFICATE
emitter. Given a run_dir, it:

  1. re-runs EVERY declared upstream phase gate (P0-ENVIRONMENT..
     P15-PRODUCTION, i.e. CWFE-MANIFEST.json's 16 phases with order < 16)
     against that SAME run_dir, through the identical subprocess contract
     run_cinematic_web_funnel.py's own orchestrator uses
     (``<gate> --run-dir <run_dir>``, exit 0 => PASS) — it never trusts a
     prior phase-status.json or any agent's claim that a phase passed;
  2. runs the AF-CWFE-SECRET-LEAK scan across every text-like artifact
     under run_dir, reusing build_site.SECRET_PATTERNS (the same detector
     prove_deployment.py already reuses — one detector, not a fork);
  3. writes ``certificate-status.json`` into run_dir on EVERY invocation
     (pass or fail), so a rejected certification attempt still leaves a
     fully evidence-bearing audit trail, matching every other prove_*.py
     in this skill (e.g. prove_p0_environment.py's environment-receipt.json);
  4. FAILS CLOSED — returns False, emits NO certificate — the instant any
     upstream gate is missing, fails, or a secret value is found, or the
     run-scoped front-door nonce file (ADR-6, ``<run_dir>/.cwfe_run_nonce``)
     is absent/empty. A red gate anywhere in the spine, or an unauthorized
     (non-front-door) run, can NEVER produce a certificate;
  5. only when every upstream gate is clean does it build a 17-phase
     (P0..P16) certificate object, validate it against
     ``structure/process-certificate.schema.json`` (created by this unit —
     it did not exist before U20), sign it with a REAL HMAC-SHA256 keyed by
     the run-scoped nonce, validate the SIGNED object against the same
     schema again (defense in depth), and atomically write
     ``PROCESS-CERTIFICATE.json``.

``verify(cert, nonce)`` is the standalone re-verifier the manifest's
py_symbol names — independently re-checks a certificate ALREADY on disk
(schema shape, phase contiguity/status, ``all_phases_pass``, and the HMAC
signature) without re-running any gate. This is what a later merge-ticket
check, a restart/resume audit, or a QC pass should call to confirm a
certificate was never tampered with after the fact.

KNOWN INTEGRATION SEAM (documented, not silently hidden — U20 is
restricted to files under scripts/ + references/, so it cannot fix this
itself): run_cinematic_web_funnel.py (skill root, outside this build
unit's file area) still calls its own inline ``_emit_certificate()`` after
its phase loop finishes, using a nonce-keyed sha256 "seed" hash — its own
comment already says this is "upgraded to a proper HMAC scheme when the
certificate prover lands (P16-CERTIFY gate)". Because that inline call
runs immediately AFTER this script returns PASS for the P16 phase, on a
live orchestrated run it will OVERWRITE the real, schema-validated,
HMAC-signed certificate this module just wrote with its own simpler
placeholder object. Fixing that requires editing run_cinematic_web_funnel.py
itself, which is out of scope for this unit (U20=scripts/, U21=tests/) —
flagged here for the integrator/next unit rather than silently patched.
Standalone invocation (``python3 scripts/prove_certificate.py --run-dir
<dir>``) is unaffected by this seam and always produces the real signed
certificate.

CLI
---
  --run-dir DIR      phase-gate mode (CWFE-MANIFEST.json uniform gate
                      contract): aggregate + certify DIR. Exit 0 = PASS
                      (certificate written), 2 = FAIL (withheld).
  --verify PATH       standalone mode: re-verify an existing
                      PROCESS-CERTIFICATE.json ('-' reads stdin). Combine
                      with --nonce, or with --run-dir to read the nonce
                      from <run-dir>/.cwfe_run_nonce.
  --self-test         offline fixture + real-repository self-test.

stdlib only (ADR-5). Exit 0 = PASS/valid, 2 = FAIL/invalid, 3 = usage error.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent            # .../scripts
_SKILL_DIR = _SCRIPT_DIR.parent                            # .../62-cinematic-web-funnel-engine
_MANIFEST_PATH = _SKILL_DIR / "CWFE-MANIFEST.json"
_SCHEMA_PATH = _SKILL_DIR / "structure" / "process-certificate.schema.json"

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_SCRIPT_DIR / "lib") not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR / "lib"))

import json_schema_lite as jsl  # noqa: E402  (scripts/lib, mirrors state_engine.py's own import)
import state_engine as _state_engine  # noqa: E402  (reuse the one atomic-write implementation)
import build_site as _build_site  # noqa: E402  (reuse SECRET_PATTERNS — one detector, not a fork)

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

PY = sys.executable or "python3"

CERT_KIND = "cinematic-web-funnel-process-certificate"
CERT_SCHEMA_VERSION = "1.0.0"
SIGNATURE_ALGORITHM = "HMAC-SHA256"

# This module's own diagnostic AF codes. Not pre-declared as manifest phase
# entries (there is exactly one phase entry, P16-CERTIFY/AF-CWFE-P16-CERTIFY,
# for the phase itself) — mirrors the established repository pattern of a
# certificate verifier owning a richer internal failure taxonomy than the
# single phase-level AF code (see 49-signature-funnel/scripts/prove_sf_cert.py:
# AF-FUN-CERT-MISSING/-PHASE-GAP/-PHASE-FAIL/-SIGNATURE alongside the single
# phase-level AF-FUN-PROCESS-INTEGRITY).
AF_CERT_MISSING = "AF-CWFE-CERT-MISSING"
AF_CERT_PHASE_GAP = "AF-CWFE-CERT-PHASE-GAP"
AF_CERT_PHASE_FAIL = "AF-CWFE-CERT-PHASE-FAIL"
AF_CERT_SIGNATURE = "AF-CWFE-CERT-SIGNATURE"
AF_CERT_NO_NONCE = "AF-CWFE-CERT-NO-NONCE"
AF_CERT_SCHEMA = "AF-CWFE-CERT-SCHEMA"
# Declared verbatim in CWFE-MANIFEST.json's cross_cutting_af_codes — reused
# here, not renamed, so the two files stay traceable to each other by string.
AF_SECRET_LEAK = "AF-CWFE-SECRET-LEAK"
AF_PROCESS_INTEGRITY = "AF-CWFE-PROCESS-INTEGRITY"

_SECRET_SCAN_SKIP_DIRS = {"node_modules", ".git", ".next", "__pycache__", ".venv", "dist", "build"}
_SECRET_SCAN_EXTENSIONS = {
    ".json", ".md", ".txt", ".log", ".ts", ".tsx", ".js", ".jsx",
    ".py", ".sh", ".env", ".yml", ".yaml", ".html", ".css",
}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Manifest loading / phase spine
# ---------------------------------------------------------------------------
def _load_manifest() -> Dict[str, Any]:
    if not _MANIFEST_PATH.exists():
        raise FileNotFoundError(f"CWFE-MANIFEST.json not found at {_MANIFEST_PATH}")
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def _phase_spine(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    phases = manifest.get("phases") or []
    return sorted(phases, key=lambda p: p.get("order", -1))


# ---------------------------------------------------------------------------
# Aggregation — re-run every upstream gate against the SAME run_dir
# ---------------------------------------------------------------------------
def _run_gate_subprocess(skill_dir: Path, run_dir: Path, gate_rel: str) -> Tuple[str, str]:
    """Deliberately re-implements run_cinematic_web_funnel._run_phase_gate's
    exact contract (subprocess `<gate> --run-dir <run_dir>`, rc==0 => PASS)
    rather than importing it, because that orchestrator lives outside this
    build unit's scripts/ file area — this aggregator's verdict must never
    silently diverge from what the live orchestrator would decide for the
    same phase on the same run_dir, so the two are kept in exact parity by
    inspection rather than coupling across the file-area boundary."""
    if not gate_rel:
        return "FAIL", "phase declares no gate"
    gate_path = skill_dir / gate_rel
    if not gate_path.exists():
        return "GATE-SCRIPT-MISSING", f"{gate_rel} not found on disk under {skill_dir}"
    proc = subprocess.run(
        [PY, str(gate_path), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
    )
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    detail = tail[-1] if tail else f"rc={proc.returncode}"
    if proc.returncode == 0:
        return "PASS", detail
    return "FAIL", f"{gate_rel} rc={proc.returncode} :: {detail}"


def _aggregate_gates(
    run_dir: Path, skill_dir: Path, phases: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], bool]:
    """Runs every phase's gate INDEPENDENTLY (no short-circuit on the first
    failure) so the resulting certificate-status.json is a complete picture
    of the whole spine, not just the first red light — an aggregator's job
    is exhaustive collection, unlike the live orchestrator's own no-skip
    stop-at-first-non-pass sequencing, which is a DIFFERENT and correct
    behavior for that DIFFERENT job (enforcing strict in-order execution)."""
    results: List[Dict[str, Any]] = []
    all_pass = True
    for phase in sorted(phases, key=lambda p: p.get("order", -1)):
        status, detail = _run_gate_subprocess(skill_dir, run_dir, phase.get("gate", ""))
        if status != "PASS":
            all_pass = False
        results.append(
            {
                "id": phase.get("id", "?"),
                "order": phase.get("order", -1),
                "name": phase.get("name", ""),
                "af_code": phase.get("af_code", ""),
                "gate": phase.get("gate") or "",
                "status": status,
                "detail": detail,
                "checked_at": _now(),
            }
        )
    return results, all_pass


# ---------------------------------------------------------------------------
# AF-CWFE-SECRET-LEAK — cross-cutting scan across every artifact under run_dir
# ---------------------------------------------------------------------------
def assert_no_secret_values(run_dir: Path) -> List[str]:
    """CWFE-MANIFEST.json cross_cutting_af_codes names this exact symbol
    (`prove_certificate.assert_no_secret_values`) as the AF-CWFE-SECRET-LEAK
    enforcement point. Walks every text-like file under run_dir (skipping
    build/dependency directories and binary media by extension) and reuses
    build_site.SECRET_PATTERNS — the SAME detector prove_deployment.py
    already reuses for its own receipt scan — so a secret VALUE (never just
    its presence by name) can never slip past certification. Findings never
    include the matched text itself, only the file and which pattern
    tripped, so a failed scan can never itself become a leak (spec 20:
    'never log secret values')."""
    findings: List[str] = []
    run_dir = Path(run_dir)
    if not run_dir.exists():
        return findings
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SECRET_SCAN_SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _SECRET_SCAN_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(run_dir))
        for pattern in _build_site.SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{rel}: matched secret pattern {pattern.pattern!r}")
    return findings


# ---------------------------------------------------------------------------
# Final artifact index (spec Section 16: "signed process certificate and
# final artifact index")
# ---------------------------------------------------------------------------
def _artifact_filenames(phases_all: List[Dict[str, Any]]) -> List[str]:
    """Derives the set of expected artifact filenames straight from each
    phase's own `produces_artifact` string in CWFE-MANIFEST.json (e.g.
    "cost-ledger.json (signed/recorded paid-call authorization)" ->
    "cost-ledger.json"), excluding P16 itself (PROCESS-CERTIFICATE.json does
    not exist yet while this function runs to help build it). No filename is
    invented here; every one traces back to the manifest, deduplicated
    (cost-ledger.json and deployment-receipt.json each legitimately appear
    twice, once per phase that touches them)."""
    names: List[str] = []
    for phase in phases_all:
        if phase.get("order") == 16:
            continue
        produced = phase.get("produces_artifact") or ""
        name = produced.split(" (", 1)[0].strip()
        if name and name not in names:
            names.append(name)
    return names


def _build_artifact_index(run_dir: Path, phases_all: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    index: List[Dict[str, Any]] = []
    seen_paths: set = set()
    for name in _artifact_filenames(phases_all):
        for match in sorted(run_dir.rglob(name)):
            if not match.is_file():
                continue
            rel = str(match.relative_to(run_dir))
            if rel in seen_paths:
                continue
            seen_paths.add(rel)
            data = match.read_bytes()
            index.append(
                {
                    "path": rel,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            )
    return index


def _resolve_run_id(run_dir: Path) -> str:
    for match in run_dir.rglob("project-manifest.json"):
        try:
            data = json.loads(match.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pid = data.get("project_id")
        if isinstance(pid, str) and pid.strip():
            return pid.strip()
        break
    return run_dir.name or "unknown-run"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
_SCHEMA_CACHE: Optional[Dict[str, Any]] = None


def _load_schema() -> Dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        if not _SCHEMA_PATH.exists():
            raise FileNotFoundError(f"process-certificate schema missing at {_SCHEMA_PATH}")
        _SCHEMA_CACHE = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE


def _validate_schema(cert: Dict[str, Any]) -> List[str]:
    return jsl.validate(cert, _load_schema())


# ---------------------------------------------------------------------------
# Signing (HMAC-SHA256 keyed by the run-scoped front-door nonce — the real
# scheme run_cinematic_web_funnel.py's own inline placeholder names as the
# thing it is "upgraded to ... when the certificate prover lands")
# ---------------------------------------------------------------------------
def canonical_payload(cert: Dict[str, Any]) -> bytes:
    """The signed portion = the whole certificate MINUS its 'signature'
    field, serialized deterministically (sorted keys, tight separators).
    Signer and verifier must agree exactly, or every certificate this module
    ever writes would fail its own re-verification."""
    c = {k: v for k, v in cert.items() if k != "signature"}
    return json.dumps(c, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign(payload: bytes, nonce: str) -> str:
    return hmac.new(nonce.encode("utf-8"), payload, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# evaluate() — the uniform phase-gate contract (P16-CERTIFY)
# ---------------------------------------------------------------------------
def evaluate(
    run_dir: "str | Path",
    *,
    manifest: Optional[Dict[str, Any]] = None,
    skill_dir: Optional["str | Path"] = None,
) -> Tuple[bool, str]:
    """Runs the full P16-CERTIFY aggregation against run_dir and, only on a
    completely clean spine, writes the signed PROCESS-CERTIFICATE.json.
    Writes certificate-status.json on EVERY invocation (pass or fail) so a
    rejected run still leaves full evidence behind.

    `manifest` / `skill_dir` are injectable ONLY for --self-test's offline
    fixture path (see self_test() below); the real CLI/orchestrator path
    always uses the real CWFE-MANIFEST.json and this skill's own directory."""
    run_dir = Path(run_dir)
    skill_dir_path = Path(skill_dir) if skill_dir is not None else _SKILL_DIR
    manifest_obj = manifest if manifest is not None else _load_manifest()

    phases_all = _phase_spine(manifest_obj)
    if len(phases_all) != 17:
        return False, (
            f"[{AF_CERT_PHASE_GAP}] manifest declares {len(phases_all)} phase(s), "
            f"expected 17 (P0..P16) — refusing to certify against a malformed spine"
        )
    upstream = [p for p in phases_all if p.get("order", -1) != 16]
    p16 = next((p for p in phases_all if p.get("order") == 16), None)
    if len(upstream) != 16 or p16 is None:
        return False, (
            f"[{AF_CERT_PHASE_GAP}] manifest phase spine malformed for certification "
            f"(need exactly orders 0..15 plus one order=16 entry, found {len(upstream)} "
            f"upstream + {'1' if p16 else '0'} terminal)"
        )

    results, all_pass = _aggregate_gates(run_dir, skill_dir_path, upstream)
    secret_findings = assert_no_secret_values(run_dir)

    run_dir.mkdir(parents=True, exist_ok=True)
    status_record = {
        "generated_at": _now(),
        "run_dir": str(run_dir),
        "upstream_phases": results,
        "all_upstream_pass": all_pass,
        "secret_scan_findings": secret_findings,
    }
    _state_engine.atomic_write_json(run_dir / "certificate-status.json", status_record)

    if not all_pass:
        failing = [r for r in results if r["status"] != "PASS"]
        detail = "; ".join(f"{r['id']}={r['status']}({r['af_code']})" for r in failing)
        return False, (
            f"[{AF_CERT_PHASE_FAIL}] {len(failing)}/16 upstream phase gate(s) "
            f"not PASS — certificate withheld (fail-closed): {detail}"
        )

    if secret_findings:
        return False, (
            f"[{AF_SECRET_LEAK}] {len(secret_findings)} potential secret VALUE(S) found "
            f"under run_dir — certificate withheld (fail-closed): "
            + "; ".join(secret_findings[:5])
            + (" ..." if len(secret_findings) > 5 else "")
        )

    nonce_path = run_dir / ".cwfe_run_nonce"
    nonce = nonce_path.read_text(encoding="utf-8").strip() if nonce_path.exists() else ""
    if not nonce:
        return False, (
            f"[{AF_CERT_NO_NONCE}] no usable front-door nonce at {nonce_path} — a "
            f"certificate may only be signed for a run that went through the canonical "
            f"front door (ADR-6); certificate withheld"
        )

    p16_entry = {
        "id": p16.get("id", "P16-CERTIFY"),
        "order": 16,
        "name": p16.get("name", "Certification"),
        "af_code": p16.get("af_code", "AF-CWFE-P16-CERTIFY"),
        "gate": p16.get("gate") or "scripts/prove_certificate.py",
        "status": "PASS",
        "detail": (
            "all 16 upstream phase gates independently re-evaluated PASS on this "
            "run_dir; no secret values found; certificate aggregated, schema-validated, "
            "and HMAC-signed"
        ),
        "checked_at": _now(),
    }
    all_entries = results + [p16_entry]

    cert: Dict[str, Any] = {
        "schema_version": CERT_SCHEMA_VERSION,
        "certificate": CERT_KIND,
        "skill": manifest_obj.get("skill", "62-cinematic-web-funnel-engine"),
        "manifest_version": manifest_obj.get("manifest_version", "unknown"),
        "run_id": _resolve_run_id(run_dir),
        "issued_at": _now(),
        "nonce_fingerprint": hashlib.sha256(nonce.encode("utf-8")).hexdigest()[:16],
        "phases": all_entries,
        "all_phases_pass": True,
        "artifact_index": _build_artifact_index(run_dir, phases_all),
        "signature_algorithm": SIGNATURE_ALGORITHM,
    }

    pre_sign_errors = _validate_schema({**cert, "signature": "0" * 64})
    if pre_sign_errors:
        return False, (
            f"[{AF_CERT_SCHEMA}] constructed certificate fails its own schema before "
            f"signing (internal bug, should never happen): {pre_sign_errors[:3]}"
        )

    cert["signature"] = sign(canonical_payload(cert), nonce)

    post_sign_errors = _validate_schema(cert)
    if post_sign_errors:
        return False, (
            f"[{AF_CERT_SCHEMA}] signed certificate fails its own schema "
            f"(internal bug, should never happen): {post_sign_errors[:3]}"
        )

    _state_engine.atomic_write_json(run_dir / "PROCESS-CERTIFICATE.json", cert)
    return True, (
        f"PROCESS-CERTIFICATE.json written — 17/17 phases PASS, "
        f"{len(cert['artifact_index'])} artifact(s) indexed, run_id={cert['run_id']}"
    )


# ---------------------------------------------------------------------------
# verify() — standalone re-verification of an ALREADY-EMITTED certificate
# (the exact py_symbol CWFE-MANIFEST.json declares: "prove_certificate.verify")
# ---------------------------------------------------------------------------
def verify(cert: Any, nonce: Optional[str]) -> List[Tuple[str, str]]:
    """Independently re-checks a certificate already on disk: schema shape,
    phase contiguity 0..16, every phase status literally PASS,
    all_phases_pass literally true, and (when a nonce is supplied) the HMAC
    signature. Never re-runs a gate — that is evaluate()'s job. Mirrors
    49-signature-funnel/scripts/prove_sf_cert.py's verify() shape."""
    fails: List[Tuple[str, str]] = []
    if not isinstance(cert, dict):
        return [(AF_CERT_MISSING, "certificate is not a JSON object")]

    schema_errors = _validate_schema(cert)
    if schema_errors:
        fails.append((AF_CERT_MISSING, f"certificate fails schema: {'; '.join(schema_errors[:5])}"))
        return fails  # shape is broken enough that semantic checks would be meaningless

    if cert.get("certificate") != CERT_KIND:
        fails.append((AF_CERT_MISSING, f"not a {CERT_KIND!r} (got {cert.get('certificate')!r})"))

    phases = cert.get("phases") or []
    orders = [p.get("order") for p in phases]
    clean_orders = sorted(o for o in orders if isinstance(o, int))
    if clean_orders != list(range(17)):
        fails.append((AF_CERT_PHASE_GAP, f"phase orders {orders} are not contiguous 0..16"))
    non_pass = [p for p in phases if p.get("status") != "PASS"]
    if non_pass:
        fails.append(
            (
                AF_CERT_PHASE_FAIL,
                f"{len(non_pass)} phase(s) not PASS: "
                + ", ".join(f"{p.get('id')}={p.get('status')}" for p in non_pass),
            )
        )
    if cert.get("all_phases_pass") is not True:
        fails.append((AF_CERT_PHASE_FAIL, "all_phases_pass is not true"))

    sig = cert.get("signature")
    if nonce is None:
        fails.append((AF_CERT_SIGNATURE, "no nonce supplied — cannot verify signature (fail-closed)"))
    else:
        expected_fp = hashlib.sha256(nonce.encode("utf-8")).hexdigest()[:16]
        if cert.get("nonce_fingerprint") != expected_fp:
            fails.append((AF_CERT_SIGNATURE, "nonce fingerprint does not match the supplied nonce"))
        expected_sig = sign(canonical_payload(cert), nonce)
        if not isinstance(sig, str) or not hmac.compare_digest(expected_sig, sig):
            fails.append((AF_CERT_SIGNATURE, "HMAC signature does not match — certificate tampered or forged"))

    if fails:
        fails.append((AF_PROCESS_INTEGRITY, "process certificate invalid — engine run is NOT certified"))
    return fails


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def _write_fixture_gate(path: Path, *, exit_code: int, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"print({message!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )


def _synthetic_manifest(gate_rel_by_order: Dict[int, str]) -> Dict[str, Any]:
    """Builds a 17-phase manifest identical in SHAPE to CWFE-MANIFEST.json
    but pointing every gate at a synthetic fixture script, so the self-test
    can exercise the full aggregation/schema/sign/tamper-detection path
    offline without needing every real upstream phase (intake, content,
    budget, media generation, ffmpeg, site build, deployment, browser QC) to
    have genuinely run end to end on this machine — that full live run is
    U26's real live proof project, not this unit's job (spec 19.2: mocked
    fixtures only, no live paid provider calls)."""
    phases = []
    for i in range(17):
        phases.append(
            {
                "id": f"P{i}-FIXTURE",
                "order": i,
                "name": f"Fixture phase {i}",
                "af_code": f"AF-CWFE-FIXTURE-{i}",
                "gate": gate_rel_by_order[i],
                "produces_artifact": f"fixture-artifact-{i}.json (self-test only)",
            }
        )
    return {
        "skill": "62-cinematic-web-funnel-engine",
        "manifest_version": "1.0.0-selftest",
        "phases": phases,
    }


def self_test() -> int:  # noqa: C901 — a self-test naturally enumerates many small cases
    ok = True

    # ---- Part A: all 16 fixture gates PASS -> certificate emitted + valid ----
    with tempfile.TemporaryDirectory() as td:
        fixture_skill_dir = Path(td) / "fixture-skill"
        run_dir = Path(td) / "run"
        run_dir.mkdir(parents=True)
        nonce = "selftest-nonce-" + hashlib.sha256(b"cwfe-u20-selftest").hexdigest()[:24]
        (run_dir / ".cwfe_run_nonce").write_text(nonce, encoding="utf-8")

        gate_map: Dict[int, str] = {}
        for i in range(16):
            rel = f"fixtures/gate{i}.py"
            gate_map[i] = rel
            _write_fixture_gate(fixture_skill_dir / rel, exit_code=0, message=f"fixture gate {i} PASS")
        gate_map[16] = "scripts/prove_certificate.py"  # label only — P16 is never subprocess-invoked
        manifest = _synthetic_manifest(gate_map)

        passed, detail = evaluate(run_dir, manifest=manifest, skill_dir=fixture_skill_dir)
        cert_path = run_dir / "PROCESS-CERTIFICATE.json"
        if passed and cert_path.exists():
            print("SELF-TEST ok: all-16-fixtures-PASS -> certificate emitted.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: expected certificate emission, got passed={passed} detail={detail}")

        status_rec = json.loads((run_dir / "certificate-status.json").read_text())
        if status_rec.get("all_upstream_pass") is True and not status_rec.get("secret_scan_findings"):
            print("SELF-TEST ok: certificate-status.json records a clean aggregation.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: certificate-status.json unexpectedly dirty: {status_rec}")

        cert = json.loads(cert_path.read_text())
        if not _validate_schema(cert):
            print("SELF-TEST ok: emitted certificate matches process-certificate.schema.json.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: emitted certificate fails its own schema: {_validate_schema(cert)}")

        vfails = verify(cert, nonce)
        if not vfails:
            print("SELF-TEST ok: verify() accepts the genuinely-signed certificate with the correct nonce.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: verify() rejected a valid certificate: {vfails}")

        tampered = json.loads(json.dumps(cert))
        tampered["phases"][3]["status"] = "FAIL"
        tfails = verify(tampered, nonce)
        if any(c == AF_CERT_SIGNATURE for c, _ in tfails) or any(c == AF_CERT_PHASE_FAIL for c, _ in tfails):
            print("SELF-TEST ok: tampering with a phase status is caught by verify().")
        else:
            ok = False
            print(f"SELF-TEST FAIL: tampered cert not caught: {tfails}")

        # A duplicated `order` value (17 items still present, so schema's own
        # minItems/maxItems=17 shape check cannot catch this one — it must be
        # verify()'s own contiguity check that does) exercises AF_CERT_PHASE_GAP
        # distinctly from a plain wrong-item-count case, which the schema
        # itself already rejects before verify()'s semantic checks even run.
        gap = json.loads(json.dumps(cert))
        gap["phases"][6]["order"] = gap["phases"][5]["order"]
        gap["signature"] = sign(canonical_payload(gap), nonce)  # re-sign so we isolate the gap, not the sig
        gfails = verify(gap, nonce)
        if any(c == AF_CERT_PHASE_GAP for c, _ in gfails):
            print("SELF-TEST ok: a duplicated phase order (gap elsewhere) is caught by verify().")
        else:
            ok = False
            print(f"SELF-TEST FAIL: duplicated-order cert not caught: {gfails}")

        # A plain wrong item count IS caught, but at the schema layer
        # (AF_CERT_MISSING), one step before verify()'s own contiguity check
        # — proving the two layers together leave no gap between them.
        short = json.loads(json.dumps(cert))
        short["phases"] = short["phases"][:5] + short["phases"][6:]
        short["signature"] = sign(canonical_payload(short), nonce)
        sfails = verify(short, nonce)
        if any(c == AF_CERT_MISSING for c, _ in sfails):
            print("SELF-TEST ok: a wrong phase count (16 instead of 17) is caught at the schema layer.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: wrong-count cert not caught: {sfails}")

        wfails = verify(cert, "not-the-real-nonce")
        if any(c == AF_CERT_SIGNATURE for c, _ in wfails):
            print("SELF-TEST ok: wrong nonce is rejected by verify().")
        else:
            ok = False
            print(f"SELF-TEST FAIL: wrong-nonce cert not caught: {wfails}")

        no_nonce_fails = verify(cert, None)
        if any(c == AF_CERT_SIGNATURE for c, _ in no_nonce_fails):
            print("SELF-TEST ok: verify() with no nonce fails closed (cannot trust an unverifiable cert).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: no-nonce verify() did not fail closed: {no_nonce_fails}")

        gfails2 = verify({"not": "a certificate"}, nonce)
        if gfails2:
            print("SELF-TEST ok: a malformed object is rejected by verify().")
        else:
            ok = False
            print("SELF-TEST FAIL: malformed object incorrectly accepted")

    # ---- Part B: one fixture gate FAILs -> certificate withheld ----
    with tempfile.TemporaryDirectory() as td:
        fixture_skill_dir = Path(td) / "fixture-skill"
        run_dir = Path(td) / "run"
        run_dir.mkdir(parents=True)
        (run_dir / ".cwfe_run_nonce").write_text("nonce-b", encoding="utf-8")
        gate_map = {}
        for i in range(16):
            rel = f"fixtures/gate{i}.py"
            gate_map[i] = rel
            _write_fixture_gate(fixture_skill_dir / rel, exit_code=(2 if i == 7 else 0), message=f"gate {i}")
        gate_map[16] = "scripts/prove_certificate.py"
        manifest = _synthetic_manifest(gate_map)
        passed, detail = evaluate(run_dir, manifest=manifest, skill_dir=fixture_skill_dir)
        cert_path = run_dir / "PROCESS-CERTIFICATE.json"
        if not passed and not cert_path.exists() and AF_CERT_PHASE_FAIL in detail:
            print("SELF-TEST ok: one FAILing phase gate withholds the certificate (fail-closed).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: a failing gate did not withhold the certificate (passed={passed}, cert exists={cert_path.exists()}, detail={detail})")

    # ---- Part C: one fixture gate MISSING (never written) -> withheld ----
    with tempfile.TemporaryDirectory() as td:
        fixture_skill_dir = Path(td) / "fixture-skill"
        run_dir = Path(td) / "run"
        run_dir.mkdir(parents=True)
        (run_dir / ".cwfe_run_nonce").write_text("nonce-c", encoding="utf-8")
        gate_map = {}
        for i in range(16):
            rel = f"fixtures/gate{i}.py"
            gate_map[i] = rel
            if i != 12:
                _write_fixture_gate(fixture_skill_dir / rel, exit_code=0, message=f"gate {i}")
            # i == 12 deliberately never written -> GATE-SCRIPT-MISSING
        gate_map[16] = "scripts/prove_certificate.py"
        manifest = _synthetic_manifest(gate_map)
        passed, detail = evaluate(run_dir, manifest=manifest, skill_dir=fixture_skill_dir)
        status_rec = json.loads((run_dir / "certificate-status.json").read_text())
        missing = [r for r in status_rec["upstream_phases"] if r["status"] == "GATE-SCRIPT-MISSING"]
        if not passed and not (run_dir / "PROCESS-CERTIFICATE.json").exists() and len(missing) == 1 and missing[0]["order"] == 12:
            print("SELF-TEST ok: one missing phase gate withholds the certificate and is recorded in certificate-status.json.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: missing-gate case mishandled (passed={passed}, missing={missing})")

    # ---- Part D: front-door nonce file absent -> withheld even with all-green gates ----
    with tempfile.TemporaryDirectory() as td:
        fixture_skill_dir = Path(td) / "fixture-skill"
        run_dir = Path(td) / "run"
        run_dir.mkdir(parents=True)
        # deliberately NO .cwfe_run_nonce file
        gate_map = {}
        for i in range(16):
            rel = f"fixtures/gate{i}.py"
            gate_map[i] = rel
            _write_fixture_gate(fixture_skill_dir / rel, exit_code=0, message=f"gate {i}")
        gate_map[16] = "scripts/prove_certificate.py"
        manifest = _synthetic_manifest(gate_map)
        passed, detail = evaluate(run_dir, manifest=manifest, skill_dir=fixture_skill_dir)
        if not passed and AF_CERT_NO_NONCE in detail and not (run_dir / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: missing front-door nonce file withholds the certificate even with all-green fixture gates.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: missing-nonce case mishandled (passed={passed}, detail={detail})")

    # ---- Part E: a leaked secret VALUE anywhere under run_dir -> withheld ----
    with tempfile.TemporaryDirectory() as td:
        fixture_skill_dir = Path(td) / "fixture-skill"
        run_dir = Path(td) / "run"
        run_dir.mkdir(parents=True)
        (run_dir / ".cwfe_run_nonce").write_text("nonce-e", encoding="utf-8")
        gate_map = {}
        for i in range(16):
            rel = f"fixtures/gate{i}.py"
            gate_map[i] = rel
            _write_fixture_gate(fixture_skill_dir / rel, exit_code=0, message=f"gate {i}")
        gate_map[16] = "scripts/prove_certificate.py"
        manifest = _synthetic_manifest(gate_map)
        # a plausible-looking leaked secret VALUE, planted in a receipt-shaped file
        (run_dir / "leftover-debug-notes.json").write_text(
            json.dumps({"note": "sk-" + ("a" * 32)}), encoding="utf-8"
        )
        passed, detail = evaluate(run_dir, manifest=manifest, skill_dir=fixture_skill_dir)
        if not passed and AF_SECRET_LEAK in detail and not (run_dir / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: a leaked secret value under run_dir withholds the certificate even with all-green fixture gates.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: secret-leak case mishandled (passed={passed}, detail={detail})")
        # the finding itself must never echo the actual secret VALUE
        if "sk-" + ("a" * 32) not in detail:
            print("SELF-TEST ok: the failure detail does not itself echo the leaked secret value.")
        else:
            ok = False
            print("SELF-TEST FAIL: the failure detail echoed the raw secret value — this would itself be a leak")

    # ---- Part F: real repository — prove today's genuine fail-closed state (no fixtures) ----
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        run_dir.mkdir(parents=True)
        (run_dir / ".cwfe_run_nonce").write_text("real-repo-selftest-nonce", encoding="utf-8")
        passed, detail = evaluate(run_dir)  # defaults: REAL CWFE-MANIFEST.json + REAL skill dir
        cert_path = run_dir / "PROCESS-CERTIFICATE.json"
        status_path = run_dir / "certificate-status.json"
        if not passed and not cert_path.exists() and status_path.exists():
            rec = json.loads(status_path.read_text())
            non_pass = [r["id"] for r in rec["upstream_phases"] if r["status"] != "PASS"]
            print(
                "SELF-TEST ok: the REAL repository, against a bare run_dir with only a nonce "
                f"file, correctly withholds the certificate today (non-PASS phases: {non_pass}); "
                "expected — a bare run_dir carries none of the real upstream artifacts "
                "(locked intake, approved content, approved budget, generated media, built "
                "site, deployment) a genuine project run would have produced."
            )
        else:
            ok = False
            print(
                f"SELF-TEST FAIL: the real repository unexpectedly certified a bare run_dir "
                f"(passed={passed}) — this would be a serious fail-closed regression, investigate immediately"
            )

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_json_arg(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P16-CERTIFY phase gate + PROCESS-CERTIFICATE aggregator/signer for "
        "the Cinematic and Web Funnel Engine. Invoked by run_cinematic_web_funnel.py as "
        "`prove_certificate.py --run-dir <dir>`."
    )
    parser.add_argument("--run-dir", help="phase-gate mode: aggregate + certify this run_dir")
    parser.add_argument("--verify", metavar="CERT_JSON_PATH", help="standalone mode: re-verify an existing PROCESS-CERTIFICATE.json ('-' for stdin)")
    parser.add_argument("--nonce", help="nonce for --verify mode (falls back to <run-dir>/.cwfe_run_nonce if --run-dir is also given)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if args.verify:
        try:
            cert = _load_json_arg(args.verify)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot load certificate {args.verify!r}: {exc}", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        nonce = args.nonce
        if nonce is None and args.run_dir:
            nonce_path = Path(args.run_dir) / ".cwfe_run_nonce"
            if nonce_path.exists():
                nonce = nonce_path.read_text(encoding="utf-8").strip()
        fails = verify(cert, nonce)
        if fails:
            print(f"FAIL: PROCESS-CERTIFICATE invalid ({len(fails)} finding(s)).")
            for code, msg in fails:
                print(f"  [{code}] {msg}")
            sys.exit(EXIT_FAIL)
        print("PASS: PROCESS-CERTIFICATE valid — every phase PASS, signature verified.")
        sys.exit(EXIT_OK)

    if not args.run_dir:
        print("USAGE ERROR: --run-dir is required (unless --self-test or --verify)", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"USAGE ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    if not run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir is not a directory: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    passed, detail = evaluate(run_dir)
    if passed:
        print(f"[PASS] P16-CERTIFY — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] P16-CERTIFY — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
