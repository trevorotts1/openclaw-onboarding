#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_delivery_gate.py — fail-closed provenance + delivery gate for one
Avatar-Alchemist BRAND run (Skill 52). This is the ONLY thing allowed to write
the labeled ~/Downloads deliverable folder, and it refuses unless:

  * a valid front-door nonce (minted by entry.sh for THIS run) is presented
    and is consumed on success (single use)                       -> AF-AV-CERT-NO-FRONT-DOOR
  * the gate-integrity check (pinned gates unmodified) passes RIGHT NOW,
    not merely "at some point during the run"                     -> AF-AV-CERT-GATE-DRIFT
  * every one of the 40 brand stages carries a foreman receipt LOADED FROM
    DISK (run_dir/receipts/G-STAGE-*.json — never the caller's in-memory
    dict) whose sha256 matches the artifact bytes READ FROM DISK
    (run_dir/artifacts/*.md) byte-for-byte. Receipt and artifact are two
    INDEPENDENT files on disk; a receipt can never be tautologically
    recomputed from the same text it attests.                     -> AF-AV-PROVENANCE
  * 40/40 stages are attested (never deliver at 39/40)             -> AF-AV-DELIVER-INCOMPLETE
  * the content prover (aa_build_check.py) is RUN BY THIS GATE, right now,
    against the on-disk run — never a caller-supplied boolean      -> AF-AV-DELIVER-INCOMPLETE
  * a DETACHED, HMAC-signed QC certificate (aa_qc_cert.py — a separate
    program, "verifier != author") is present, its own signature verifies,
    it is bound to this run_id, and its score >= 8.5 (BINDING)     -> AF-AV-CERT-QC-INVALID
  * (if a delivery folder is supplied) every shipped file's sha256, read
    fresh from disk, is bound into the certificate and cross-checked
    against aa_package.py's own MANIFEST.json                     -> AF-AV-DELIVERY-MISMATCH

On PASS it emits a certificate whose "signature" is an HMAC-SHA256 over the
full canonical body (chain + qc + content-gate + manifest hash + nonce hash +
delivery-folder hash + issued_utc), keyed by the per-run foreman key
(`run_dir/.foreman-key`, minted ONLY by entry.sh — never embedded in the
certificate itself). `--verify-cert` independently re-checks that signature.
"Done" may be claimed ONLY with a certificate that PASSES `--verify-cert`.

Threat model, stated honestly: this is an offline, stdlib-only, single-box
tool with no server-side secret vault. A fully-privileged local user who can
read `run_dir/.foreman-key` can still forge a signature. What this gate
actually buys: (1) the trivial "compute a public keyless sha256 yourself"
forgery the QC review reproduced no longer works — you need the key file,
which only entry.sh mints, (2) even WITH the key, you cannot swap in garbage
receipts/artifacts/QC-score/delivery bytes and get a clean PASS, because
every one of those is now re-derived from disk by this gate itself rather
than trusted from the caller, and (3) the front-door nonce + live
gate-integrity check mean the certificate is unmintable outside a run that
genuinely went through entry.sh's fail-closed sequence.

stdlib only. Exit 0 = pass, 2 = violation, 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import aa_build_check as build          # noqa: E402
import aa_gate_integrity_check as gic   # noqa: E402
import aa_qc_cert as qc                 # noqa: E402

QC_FLOOR = 8.5

# every AF-AV-* code this module's own --self-test proves REJECTS a bad
# fixture (used by test_aa_preflight.py's "declared subset-of tested" meta-check).
TESTED_AF_CODES = {
    "AF-AV-PROVENANCE", "AF-AV-DELIVER-INCOMPLETE", "AF-AV-CERT-NO-FRONT-DOOR",
    "AF-AV-CERT-GATE-DRIFT", "AF-AV-CERT-UNSIGNED", "AF-AV-CERT-QC-INVALID",
    "AF-AV-CERT-SEMANTIC", "AF-AV-DELIVERY-MISMATCH",
}

SEMANTIC_FLOOR = 8.5


def _manifest_path() -> Path:
    return SKILL_ROOT / "AA-PIPELINE-MANIFEST.json"


def _sha256(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canon(fields: Dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))


def _hmac(key: bytes, body: str) -> str:
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def _manifest_hash(manifest: Dict[str, Any]) -> str:
    return _sha256(_canon(manifest))


# ---------------------------------------------------------------------------
# disk loaders — every one of these reads FRESH bytes off disk; nothing here
# ever trusts an in-memory dict the caller could have hand-assembled.
# ---------------------------------------------------------------------------
def _load_receipts_and_chain(manifest: Dict[str, Any], run_dir: Path) -> Tuple[List[Dict[str, str]], List[Tuple[str, str]]]:
    violations: List[Tuple[str, str]] = []
    chain: List[Dict[str, str]] = []
    stages = [s["stage_id"] for s in manifest.get("stages", [])]
    art_dir = run_dir / "artifacts"
    rec_dir = run_dir / "receipts"
    for sid in stages:
        art_path = art_dir / f"{sid}.md"
        rec_path = rec_dir / f"G-STAGE-{sid}.json"
        if not art_path.is_file() or not rec_path.is_file():
            violations.append(("AF-AV-DELIVER-INCOMPLETE",
                                f"stage '{sid}' has no on-disk receipt/artifact file — cannot deliver"))
            continue
        try:
            actual = _sha256(art_path.read_text(encoding="utf-8"))
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            violations.append(("AF-AV-DELIVER-INCOMPLETE", f"stage '{sid}': cannot read receipt/artifact: {exc}"))
            continue
        claimed = str(rec.get("sha256", ""))
        if claimed != actual:
            violations.append(("AF-AV-PROVENANCE",
                                f"stage '{sid}': on-disk receipt sha256 {claimed[:12]}.. != on-disk artifact "
                                f"sha256 {actual[:12]}.. (fabrication / tamper — receipt does not attest THIS "
                                f"file on disk)"))
            continue
        chain.append({"stage": sid, "sha256": actual})
    if len(chain) != len(stages):
        violations.append(("AF-AV-DELIVER-INCOMPLETE",
                            f"{len(chain)}/{len(stages)} stages attested on disk — delivery blocked "
                            f"(never deliver below 40/40)"))
    return chain, violations


def _load_nonce(nonce_path: Optional[Path]) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    if nonce_path is None or not nonce_path.is_file():
        return None, [("AF-AV-CERT-NO-FRONT-DOOR",
                        "no front-door nonce file at the given path — a certificate cannot be minted "
                        "outside a run entry.sh actually started")]
    nonce = nonce_path.read_text(encoding="utf-8").strip()
    if len(nonce) < 16:
        return None, [("AF-AV-CERT-NO-FRONT-DOOR", "front-door nonce is present but too short (<16 chars)")]
    return nonce, []


def _load_key(key_path: Optional[Path]) -> Tuple[Optional[bytes], List[Tuple[str, str]]]:
    if key_path is None or not key_path.is_file():
        return None, [("AF-AV-CERT-UNSIGNED",
                        "no per-run foreman key file (.foreman-key, minted ONLY by entry.sh) — "
                        "cannot sign a certificate outside the guarded front door")]
    try:
        key = bytes.fromhex(key_path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None, [("AF-AV-CERT-UNSIGNED", "foreman key file is not valid hex")]
    if len(key) < 32:
        return None, [("AF-AV-CERT-UNSIGNED", f"foreman key is only {len(key)} bytes (<32, CSPRNG too short)")]
    return key, []


def _load_qc_cert(run_dir: Path, run_id: str, key: bytes) -> Tuple[Optional[Dict[str, Any]], List[Tuple[str, str]]]:
    p = run_dir / "QC-CERTIFICATE.json"
    if not p.is_file():
        return None, [("AF-AV-CERT-QC-INVALID",
                        "no detached QC-CERTIFICATE.json (aa_qc_cert.py) — qc_score can never be a bare "
                        "caller-supplied float")]
    try:
        cert = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, [("AF-AV-CERT-QC-INVALID", f"QC-CERTIFICATE.json does not parse: {exc}")]
    if not qc.verify_signature(cert, key):
        return None, [("AF-AV-CERT-QC-INVALID",
                        "QC-CERTIFICATE.json signature does NOT verify against the run's foreman key "
                        "(hand-edited or minted with a different/no key)")]
    if cert.get("run_id") != run_id:
        return None, [("AF-AV-CERT-QC-INVALID",
                        f"QC-CERTIFICATE.json run_id {cert.get('run_id')!r} != this run {run_id!r} "
                        f"(a cert cannot be replayed across runs)")]
    if not cert.get("content_gate_pass"):
        return cert, [("AF-AV-CERT-QC-INVALID", "QC-CERTIFICATE.json content_gate_pass is False")]
    score = cert.get("qc_score")
    if score is None or float(score) < QC_FLOOR:
        return cert, [("AF-AV-CERT-QC-INVALID",
                        f"independent QC score {score} < {QC_FLOOR} floor (10-category BINDING, "
                        f"verifier != author)")]
    return cert, []


def _load_qc_semantic(run_dir: Path, run_id: str, key: bytes) -> Tuple[Optional[Dict[str, Any]], List[Tuple[str, str]]]:
    """FIX-XC-03d: the SECOND, semantic certificate. Requires QC-SEMANTIC.json
    (aa_qc_cert.py --semantic), produced by an independent verifier sub-agent
    (!= any author) on the client's TIER-A model applying the 10-category
    OpenClaw QC Protocol. Its own HMAC signature must verify against the run
    key, it must be bound to THIS run_id, the verifier model must be
    non-Anthropic, and the aggregate semantic score must clear the 8.5 floor."""
    p = run_dir / "QC-SEMANTIC.json"
    if not p.is_file():
        return None, [("AF-AV-CERT-SEMANTIC",
                        "no QC-SEMANTIC.json — the structural composite is mathematically binary and is "
                        "NOT a prose-quality bar; delivery requires the independent semantic verifier leg")]
    try:
        cert = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, [("AF-AV-CERT-SEMANTIC", f"QC-SEMANTIC.json does not parse: {exc}")]
    if not qc.verify_semantic_signature(cert, key):
        return None, [("AF-AV-CERT-SEMANTIC",
                        "QC-SEMANTIC.json signature does NOT verify against the run's foreman key "
                        "(hand-edited or minted with a different/no key)")]
    if cert.get("run_id") != run_id:
        return None, [("AF-AV-CERT-SEMANTIC",
                        f"QC-SEMANTIC.json run_id {cert.get('run_id')!r} != this run {run_id!r}")]
    if qc.semantic_verifier_is_anthropic(cert):
        return cert, [("AF-AV-CERT-SEMANTIC",
                        f"semantic verifier model {cert.get('verifier_model')!r} is an Anthropic id "
                        f"(G-NOANTHROPIC — the verifier must run on the client's own TIER-A model)")]
    score = cert.get("semantic_score")
    if score is None or float(score) < SEMANTIC_FLOOR:
        return cert, [("AF-AV-CERT-SEMANTIC",
                        f"semantic QC score {score} < {SEMANTIC_FLOOR} floor (10-category OpenClaw QC "
                        f"Protocol, independent verifier != author, BINDING)")]
    return cert, []


def _delivery_manifest(deliver_dir: Path) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    """Re-hash every shipped file FRESH from disk (never trust aa_package's own
    claimed MANIFEST.json blindly — cross-check it)."""
    violations: List[Tuple[str, str]] = []
    files: Dict[str, str] = {}
    for p in sorted(deliver_dir.rglob("*")):
        if p.is_file() and p.name not in ("PROCESS-CERTIFICATE.json", "PROCESS-CERTIFICATE.md"):
            files[p.relative_to(deliver_dir).as_posix()] = _sha256_bytes(p.read_bytes())
    claimed_manifest = deliver_dir / "MANIFEST.json"
    if claimed_manifest.is_file():
        try:
            claimed = json.loads(claimed_manifest.read_text(encoding="utf-8")).get("files", {})
            for fn, meta in claimed.items():
                fresh = files.get(fn)
                if fresh is not None and meta.get("sha256") != fresh:
                    violations.append(("AF-AV-DELIVERY-MISMATCH",
                                        f"delivered file {fn!r}: MANIFEST.json claims {meta.get('sha256', '')[:12]}.. "
                                        f"but on-disk bytes hash to {fresh[:12]}.. (swapped/tampered deliverable)"))
        except Exception as exc:  # noqa: BLE001
            violations.append(("AF-AV-DELIVERY-MISMATCH", f"MANIFEST.json unreadable: {exc}"))
    return files, violations


# ---------------------------------------------------------------------------
# core verify
# ---------------------------------------------------------------------------
def verify(manifest: Dict[str, Any], *, run_dir: Path, run_id: str,
           deliver_dir: Optional[Path] = None,
           nonce_path: Optional[Path] = None, key_path: Optional[Path] = None,
           gate_check_fn: Optional[Callable[[], int]] = None,
           ) -> Tuple[List[Tuple[str, str]], List[str], Dict[str, Any]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []
    gate_check_fn = gate_check_fn or gic.check

    # 1) front door: nonce + live gate-integrity re-check (not "trust the caller")
    nonce, nv = _load_nonce(nonce_path)
    violations += nv
    gate_rc = gate_check_fn()
    if gate_rc != 0:
        violations.append(("AF-AV-CERT-GATE-DRIFT",
                            f"aa_gate_integrity_check failed RIGHT NOW (rc={gate_rc}) — a certificate "
                            f"cannot be minted while a pinned gate is modified"))

    # 2) key
    key, kv = _load_key(key_path)
    violations += kv

    # 3) provenance chain, loaded from disk, never the caller's dict
    chain, cv = _load_receipts_and_chain(manifest, run_dir)
    violations += cv
    attested = len(chain)

    # 4) content prover run BY THIS GATE against the on-disk run
    content_state = build.load_run(str(run_dir))
    content_violations, _ = build.verify(manifest, content_state)
    content_pass = not content_violations
    if not content_pass:
        violations.append(("AF-AV-DELIVER-INCOMPLETE",
                            f"content prover (aa_build_check.py), re-run by this gate against the on-disk "
                            f"run, found {len(content_violations)} violation(s): {content_violations[:3]}"))

    # 5) detached, signed QC certificate (never a bare float) — BOTH legs:
    #    the structural composite (QC-CERTIFICATE.json) AND the independent
    #    semantic verifier (QC-SEMANTIC.json, FIX-XC-03d). Delivery requires both.
    qc_cert = None
    qc_score = None
    qc_semantic = None
    qc_semantic_score = None
    if key is not None:
        qc_cert, qv = _load_qc_cert(run_dir, run_id, key)
        violations += qv
        if qc_cert:
            qc_score = qc_cert.get("qc_score")
        qc_semantic, sv = _load_qc_semantic(run_dir, run_id, key)
        violations += sv
        if qc_semantic:
            qc_semantic_score = qc_semantic.get("semantic_score")
    else:
        violations.append(("AF-AV-CERT-QC-INVALID", "cannot verify QC-CERTIFICATE.json without a valid key"))
        violations.append(("AF-AV-CERT-SEMANTIC", "cannot verify QC-SEMANTIC.json without a valid key"))

    # 6) delivery-folder binding (if a delivery dir is supplied)
    delivery_files: Dict[str, str] = {}
    if deliver_dir is not None and deliver_dir.is_dir():
        delivery_files, dv = _delivery_manifest(deliver_dir)
        violations += dv

    cert: Dict[str, Any] = {}
    if not violations:
        chain_hash = _sha256("|".join(c["sha256"] for c in chain))
        delivery_hash = _sha256(_canon(delivery_files)) if delivery_files else None
        fields: Dict[str, Any] = {
            "certificate": "avatar-alchemist-brand-run",
            "skill": "52-avatar-alchemist",
            "run_id": run_id,
            "manifest_version": manifest.get("manifest_version"),
            "manifest_sha256": _manifest_hash(manifest),
            "stages_attested": attested,
            "content_gate": "PASS",
            "qc_score": qc_score,
            "qc_floor": QC_FLOOR,
            "qc_semantic_score": qc_semantic_score,
            "qc_semantic_floor": SEMANTIC_FLOOR,
            "qc_semantic_signature": qc_semantic.get("signature") if qc_semantic else None,
            "qc_cert_signature": qc_cert.get("signature") if qc_cert else None,
            "provenance_chain_sha256": chain_hash,
            "chain": chain,
            "front_door_nonce_sha256": _sha256(nonce) if nonce else None,
            "delivery_manifest_sha256": delivery_hash,
            "delivery_file_count": len(delivery_files),
            "issued_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        fields["signature"] = _hmac(key, _canon(fields))
        cert = fields
        notes.append(f"CERTIFICATE issued: provenance_chain_sha256={chain_hash[:16]}.. over {attested} "
                      f"attested stages, HMAC-signed with the per-run foreman key")
        # consume the nonce: single use, so this exact front-door pass cannot
        # mint a second certificate for a since-tampered re-run. This is NOT
        # best-effort: if the nonce cannot be consumed (read-only run dir, a
        # racing consumer, a filesystem error), the single-use guarantee is
        # unenforceable, so we WITHHOLD the certificate and fail closed with
        # AF-AV-CERT-NO-FRONT-DOOR rather than mint a cert whose nonce could be
        # replayed to mint a second one.
        if nonce_path is not None and nonce_path.is_file():
            try:
                nonce_path.rename(nonce_path.with_suffix(nonce_path.suffix + ".consumed"))
            except OSError as exc:
                violations.append(("AF-AV-CERT-NO-FRONT-DOOR",
                                   f"the single-use front-door nonce could not be consumed "
                                   f"({exc.__class__.__name__}: {exc}) — the certificate is WITHHELD "
                                   f"because a nonce that cannot be retired could be replayed to mint a "
                                   f"second certificate"))
                cert = {}
                notes.append("CERTIFICATE WITHHELD: nonce non-consumable (single-use guarantee unenforceable)")

    return violations, notes, cert


def verify_cert(cert_path: Path, key_path: Path, *, deep_run_dir: Optional[Path] = None,
                 manifest: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[str]]:
    """--verify-cert: independently recompute the HMAC over the cert's own
    canonical body (every field except 'signature') and compare. This is the
    check the QC review found MISSING entirely — a hand-forged cert (with a
    self-computed keyless sha256, or any signature not derived from the real
    per-run key) now fails here, not just "goes unchecked"."""
    problems: List[str] = []
    try:
        cert = json.loads(cert_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, [f"cannot read/parse certificate: {exc}"]
    try:
        key = bytes.fromhex(key_path.read_text(encoding="utf-8").strip())
    except Exception as exc:  # noqa: BLE001
        return False, [f"cannot read key file: {exc}"]
    body = {k: v for k, v in cert.items() if k != "signature"}
    expected = _hmac(key, _canon(body))
    actual = cert.get("signature", "")
    if not hmac.compare_digest(expected, str(actual)):
        problems.append(f"signature mismatch: cert claims {str(actual)[:16]}.. but HMAC(key, body) = {expected[:16]}..")
    if deep_run_dir is not None and manifest is not None:
        chain, cv = _load_receipts_and_chain(manifest, deep_run_dir)
        chain_hash = _sha256("|".join(c["sha256"] for c in chain))
        if cv:
            problems.append(f"deep re-verify: run_dir no longer clears provenance ({cv[:2]})")
        elif chain_hash != cert.get("provenance_chain_sha256"):
            problems.append("deep re-verify: recomputed provenance_chain_sha256 does not match the cert "
                             "(artifacts changed since the cert was issued)")
    return (len(problems) == 0), problems


# ---------------------------------------------------------------------------
# self-test — builds a REAL on-disk run/receipts/key/nonce/QC-cert fixture (no
# tautology: artifacts and receipts are two independent files on disk) and
# reproduces + blocks every forgery the QC review found, plus the new gates.
# ---------------------------------------------------------------------------
def _write_fixture(tmp: Path, manifest: Dict[str, Any], *, apply_repairs: bool = True) -> Dict[str, Any]:
    import secrets
    run_dir = tmp / "run"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "receipts").mkdir(parents=True)
    state = build._synth(manifest, apply_repairs=apply_repairs)
    for sid, txt in state["artifacts"].items():
        (run_dir / "artifacts" / f"{sid}.md").write_text(txt, encoding="utf-8")
        (run_dir / "receipts" / f"G-STAGE-{sid}.json").write_text(json.dumps(
            {"stage": sid, "sha256": _sha256(txt), "model": state["models"][sid], "attested_by": "foreman"},
            indent=2), encoding="utf-8")
    (run_dir / "RUN-LEDGER.json").write_text(json.dumps(
        {"run_id": "selftest-run", "apply_repairs": apply_repairs,
         "stages": {sid: {"model": state["models"][sid], "receipt": True} for sid in state["artifacts"]}},
        indent=2), encoding="utf-8")
    key = secrets.token_bytes(32)
    key_path = run_dir / ".foreman-key"
    key_path.write_text(key.hex(), encoding="utf-8")
    nonce_path = run_dir / ".entry-nonce"
    nonce_path.write_text(secrets.token_hex(24), encoding="utf-8")
    qc_cert = qc.build_certificate(manifest, run_dir, "selftest-run", key)
    (run_dir / "QC-CERTIFICATE.json").write_text(json.dumps(qc_cert, indent=2), encoding="utf-8")
    # the SECOND, semantic certificate (FIX-XC-03d) — deterministic stand-in
    # verifier judgment (offline fixture only, never a client run).
    sem = qc.build_semantic_certificate(manifest, run_dir, "selftest-run", key,
                                        qc.synth_semantic_judgment(manifest, run_dir))
    (run_dir / "QC-SEMANTIC.json").write_text(json.dumps(sem, indent=2), encoding="utf-8")
    deliver_dir = tmp / "deliver"
    import aa_package as package
    package.assemble(manifest, state["artifacts"], "Test", "Fixture", deliver_dir)
    return {"run_dir": run_dir, "deliver_dir": deliver_dir, "key_path": key_path,
            "nonce_path": nonce_path, "key": key, "run_id": "selftest-run"}


def run_self_test(manifest: Dict[str, Any]) -> int:
    import tempfile
    ok = True

    def _fresh_gate_ok() -> int:
        return 0

    def _fresh_gate_drift() -> int:
        return 2

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fx = _write_fixture(tmp, manifest)
        v, notes, cert = verify(manifest, run_dir=fx["run_dir"], run_id=fx["run_id"],
                                 deliver_dir=fx["deliver_dir"], nonce_path=fx["nonce_path"],
                                 key_path=fx["key_path"], gate_check_fn=_fresh_gate_ok)
        if v or not cert or "signature" not in cert:
            ok = False; print(f"SELF-TEST FAIL: valid fixture -> violations={v} cert_present={bool(cert)}")
        else:
            print("SELF-TEST ok: valid on-disk run PASSES and issues an HMAC-signed certificate.")
        cert_path = tmp / "cert.json"
        cert_path.write_text(json.dumps(cert, indent=2), encoding="utf-8")
        good, problems = verify_cert(cert_path, fx["key_path"])
        if good:
            print("SELF-TEST ok: --verify-cert independently re-verifies the real certificate's signature.")
        else:
            ok = False; print(f"SELF-TEST FAIL: --verify-cert rejected a genuine certificate: {problems}")

        # (repro) the EXACT QC-reported forgery: hand-write a self-consistent
        # cert with a keyless sha256 "signature" (the old scheme) and confirm
        # --verify-cert REJECTS it.
        forged_old_scheme = dict(cert)
        forged_old_scheme["qc_score"] = 9.9
        forged_old_scheme["signature"] = _sha256(f"{cert['provenance_chain_sha256']}:{cert['stages_attested']}:9.9")
        fpath = tmp / "forged_old_scheme.json"
        fpath.write_text(json.dumps(forged_old_scheme, indent=2), encoding="utf-8")
        good, problems = verify_cert(fpath, fx["key_path"])
        if not good:
            print("SELF-TEST ok: (REPRO) the QC-reported keyless-sha256 hand-forgery is REJECTED by --verify-cert.")
        else:
            ok = False; print("SELF-TEST FAIL: the keyless-sha256 hand-forgery was NOT rejected.")

        # (repro) mint a cert entirely OUTSIDE the front door: no nonce, no key
        v2, _, cert2 = verify(manifest, run_dir=fx["run_dir"], run_id=fx["run_id"],
                               deliver_dir=None, nonce_path=None, key_path=None,
                               gate_check_fn=_fresh_gate_ok)
        codes2 = {c for c, _ in v2}
        if cert2 == {} and "AF-AV-CERT-NO-FRONT-DOOR" in codes2:
            print("SELF-TEST ok: (REPRO) minting outside the front door (no nonce/key) is REFUSED, no cert.")
        else:
            ok = False; print(f"SELF-TEST FAIL: no-front-door mint -> codes={codes2} cert={bool(cert2)}")

    # --- single-defect mutations (fresh fixture each time) ------------------
    def mk():
        td = tempfile.mkdtemp()
        return Path(td), _write_fixture(Path(td), manifest)

    cases = []

    def tamper_after_receipts(tmp, fx):
        # the A3 fix, proven non-tautological: rewrite an ARTIFACT on disk
        # AFTER its receipt was written, without touching the receipt.
        p = fx["run_dir"] / "artifacts" / "16-brand-bio.md"
        p.write_text("# 16-brand-bio\nSECRETLY EDITED after the receipt was written\n", encoding="utf-8")
    cases.append(("provenance_tamper_after_receipt", "AF-AV-PROVENANCE", tamper_after_receipts))

    def drop_receipt(tmp, fx):
        (fx["run_dir"] / "receipts" / "G-STAGE-35-top-39.json").unlink()
    cases.append(("stage_39_of_40", "AF-AV-DELIVER-INCOMPLETE", drop_receipt))

    def content_fail(tmp, fx):
        (fx["run_dir"] / "artifacts" / "16-brand-bio.md").write_text("", encoding="utf-8")
        # keep the receipt matching so this trips CONTENT (empty artifact), not provenance
        (fx["run_dir"] / "receipts" / "G-STAGE-16-brand-bio.json").write_text(
            json.dumps({"stage": "16-brand-bio", "sha256": _sha256(""), "model": "ollama-cloud/qwen3-235b"}),
            encoding="utf-8")
    cases.append(("content_gate_failed", "AF-AV-DELIVER-INCOMPLETE", content_fail))

    def missing_qc_cert(tmp, fx):
        (fx["run_dir"] / "QC-CERTIFICATE.json").unlink()
    cases.append(("qc_cert_missing", "AF-AV-CERT-QC-INVALID", missing_qc_cert))

    def forged_qc_cert(tmp, fx):
        # (repro) hand-edit the QC score up without the key -> signature breaks
        p = fx["run_dir"] / "QC-CERTIFICATE.json"
        c = json.loads(p.read_text())
        c["qc_score"] = 9.9
        p.write_text(json.dumps(c, indent=2), encoding="utf-8")
    cases.append(("qc_cert_hand_edited_score", "AF-AV-CERT-QC-INVALID", forged_qc_cert))

    def missing_nonce(tmp, fx):
        fx["nonce_path"].unlink()
    cases.append(("missing_front_door_nonce", "AF-AV-CERT-NO-FRONT-DOOR", missing_nonce))

    def missing_semantic_cert(tmp, fx):
        (fx["run_dir"] / "QC-SEMANTIC.json").unlink()
    cases.append(("qc_semantic_missing", "AF-AV-CERT-SEMANTIC", missing_semantic_cert))

    def hand_edited_semantic(tmp, fx):
        # (repro) hand-edit the semantic score up without the key -> signature breaks
        p = fx["run_dir"] / "QC-SEMANTIC.json"
        c = json.loads(p.read_text())
        c["semantic_score"] = 9.99
        p.write_text(json.dumps(c, indent=2), encoding="utf-8")
    cases.append(("qc_semantic_hand_edited_score", "AF-AV-CERT-SEMANTIC", hand_edited_semantic))

    def low_semantic_score(tmp, fx):
        # a genuinely low semantic grade (re-signed with the real key) must still
        # be REFUSED — the leg is a real 8.5 quality bar, not just a signature check.
        c = qc.build_semantic_certificate(manifest, fx["run_dir"], fx["run_id"], fx["key"],
                                          qc.synth_semantic_judgment(manifest, fx["run_dir"], base=6.0))
        (fx["run_dir"] / "QC-SEMANTIC.json").write_text(json.dumps(c, indent=2), encoding="utf-8")
    cases.append(("qc_semantic_below_floor", "AF-AV-CERT-SEMANTIC", low_semantic_score))

    def anthropic_verifier(tmp, fx):
        c = qc.build_semantic_certificate(manifest, fx["run_dir"], fx["run_id"], fx["key"],
                                          qc.synth_semantic_judgment(manifest, fx["run_dir"],
                                                                     verifier_model="anthropic/claude-3-5-sonnet"))
        (fx["run_dir"] / "QC-SEMANTIC.json").write_text(json.dumps(c, indent=2), encoding="utf-8")
    cases.append(("qc_semantic_anthropic_verifier", "AF-AV-CERT-SEMANTIC", anthropic_verifier))

    def forged_nonce(tmp, fx):
        # (repro) the exact QC reproduction: hand-write a 16-char nonce file
        fx["nonce_path"].write_text("XXXXXXXXXXXXXXXX", encoding="utf-8")
    # a hand-written-but-well-formed nonce still passes length/presence (that
    # check alone was always weak) — the REAL protection is that this same
    # scenario, run through aa_director.py's real dispatch, now re-verifies
    # deps/bypass-scan/hash-pin itself (see aa_director.py's own self-test).
    # Documented here, not asserted as a delivery-gate violation.

    def missing_key(tmp, fx):
        fx["key_path"].unlink()
    cases.append(("missing_foreman_key", "AF-AV-CERT-UNSIGNED", missing_key))

    def short_key(tmp, fx):
        fx["key_path"].write_text("deadbeef", encoding="utf-8")
    cases.append(("foreman_key_too_short", "AF-AV-CERT-UNSIGNED", short_key))

    def wrong_run_id(tmp, fx):
        fx["run_id_override"] = "some-other-run"
    cases.append(("qc_cert_run_id_mismatch", "AF-AV-CERT-QC-INVALID", wrong_run_id))

    def swapped_deliverable(tmp, fx):
        # a shipped file is tampered on disk AFTER aa_package.py wrote
        # MANIFEST.json — the stale claimed hash must be caught, not trusted.
        target = next(p for p in fx["deliver_dir"].glob("*.md") if p.name != "00-INDEX.md")
        target.write_text("# TAMPERED DELIVERABLE\nswapped after packaging.\n", encoding="utf-8")
    cases.append(("delivered_file_swapped_after_manifest", "AF-AV-DELIVERY-MISMATCH", swapped_deliverable))

    for name, expected, mut in cases:
        tmp, fx = mk()
        try:
            mut(tmp, fx)
            run_id = fx.get("run_id_override", fx["run_id"])
            v, _, cert = verify(manifest, run_dir=fx["run_dir"], run_id=run_id,
                                 deliver_dir=fx["deliver_dir"], nonce_path=fx["nonce_path"],
                                 key_path=fx["key_path"], gate_check_fn=_fresh_gate_ok)
            codes = {c for c, _ in v}
            if not v:
                ok = False; print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
            elif expected not in codes:
                ok = False; print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
            elif cert:
                ok = False; print(f"SELF-TEST FAIL: '{name}' still issued a certificate.")
            else:
                print(f"SELF-TEST ok: '{name}' -> nonzero, no cert, carries {expected}.")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    # gate-integrity drift (live, injected — proves aa_director-style real
    # re-verification, not "trust that it passed earlier")
    tmp, fx = mk()
    try:
        v, _, cert = verify(manifest, run_dir=fx["run_dir"], run_id=fx["run_id"],
                             deliver_dir=fx["deliver_dir"], nonce_path=fx["nonce_path"],
                             key_path=fx["key_path"], gate_check_fn=_fresh_gate_drift)
        codes = {c for c, _ in v}
        if "AF-AV-CERT-GATE-DRIFT" in codes and not cert:
            print("SELF-TEST ok: 'gate_integrity_drift_at_issuance' -> nonzero, no cert, carries AF-AV-CERT-GATE-DRIFT.")
        else:
            ok = False; print(f"SELF-TEST FAIL: gate-drift case -> {sorted(codes)} cert={bool(cert)}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # read-only-run-dir: a run whose nonce CANNOT be consumed (rename fails) must
    # WITHHOLD the certificate and fail closed AF-AV-CERT-NO-FRONT-DOOR — a nonce
    # that cannot be retired could otherwise be replayed to mint a second cert
    # (AVATAR-05 i: the old code swallowed the OSError in `except: pass`).
    import os as _os
    import stat as _stat
    tmp, fx = mk()
    made_ro = False
    try:
        rd = fx["run_dir"]
        _os.chmod(rd, _stat.S_IRUSR | _stat.S_IXUSR)  # r-x: reads ok, no rename in-dir
        made_ro = True
        # sanity: only assert the behavior on a fs/uid where the dir is really
        # non-writable (rename of the nonce actually fails). Skip if we can still
        # write (e.g. running as root), so the test is honest, never vacuous.
        try:
            probe = rd / ".ro-probe"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            print("SELF-TEST skip: 'read_only_run_dir' — dir still writable here (root/fs), "
                  "cannot exercise a real rename failure.")
        except OSError:
            v, _, cert = verify(manifest, run_dir=rd, run_id=fx["run_id"],
                                 deliver_dir=fx["deliver_dir"], nonce_path=fx["nonce_path"],
                                 key_path=fx["key_path"], gate_check_fn=_fresh_gate_ok)
            codes = {c for c, _ in v}
            if "AF-AV-CERT-NO-FRONT-DOOR" in codes and not cert:
                print("SELF-TEST ok: 'read_only_run_dir' -> nonce non-consumable, cert WITHHELD, "
                      "carries AF-AV-CERT-NO-FRONT-DOOR.")
            else:
                ok = False
                print(f"SELF-TEST FAIL: read-only-run-dir case -> {sorted(codes)} cert={bool(cert)}")
    finally:
        if made_ro:
            try:
                _os.chmod(fx["run_dir"], _stat.S_IRWXU)  # restore so rmtree can clean up
            except OSError:
                pass
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: delivery gate clears — ~/Downloads write authorized.")
        return
    print(f"FAIL: {len(violations)} delivery violation(s) — ~/Downloads write REFUSED, no certificate.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Avatar-Alchemist provenance + delivery gate.")
    ap.add_argument("--run-dir", help="run dir (artifacts/, receipts/, .entry-nonce, .foreman-key, QC-CERTIFICATE.json)")
    ap.add_argument("--run-id", help="run id to bind (default: run-dir basename)")
    ap.add_argument("--deliver-dir", help="assembled delivery folder (for the delivery-manifest binding)")
    ap.add_argument("--nonce-file", help="path to the front-door nonce (default: <run-dir>/.entry-nonce)")
    ap.add_argument("--key-file", help="path to the per-run foreman key (default: <run-dir>/.foreman-key)")
    ap.add_argument("--manifest", help="path to AA-PIPELINE-MANIFEST.json")
    ap.add_argument("--cert-out", help="write the signed certificate here on PASS")
    ap.add_argument("--verify-cert", help="independently re-verify a certificate's signature (fail-closed)")
    ap.add_argument("--deep", action="store_true", help="with --verify-cert: also re-verify the provenance chain against --run-dir")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest or _manifest_path()).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load manifest: {exc}")
        return 3
    if args.self_test:
        return run_self_test(manifest)
    if args.verify_cert:
        if not args.key_file:
            print("USAGE ERROR: --verify-cert requires --key-file.")
            return 3
        deep_dir = Path(args.run_dir) if (args.deep and args.run_dir) else None
        good, problems = verify_cert(Path(args.verify_cert), Path(args.key_file),
                                      deep_run_dir=deep_dir, manifest=manifest if deep_dir else None)
        if good:
            print("VERIFY-CERT PASS: signature is valid for this certificate + key.")
            return 0
        print("VERIFY-CERT FAIL: certificate signature does NOT verify.")
        for p in problems:
            print(f"  {p}")
        return 2
    if not args.run_dir:
        print("USAGE ERROR: pass --run-dir <dir> (or --self-test / --verify-cert).")
        return 3
    run_dir = Path(args.run_dir)
    run_id = args.run_id or run_dir.name
    nonce_path = Path(args.nonce_file) if args.nonce_file else (run_dir / ".entry-nonce")
    key_path = Path(args.key_file) if args.key_file else (run_dir / ".foreman-key")
    deliver_dir = Path(args.deliver_dir) if args.deliver_dir else None
    violations, notes, cert = verify(manifest, run_dir=run_dir, run_id=run_id, deliver_dir=deliver_dir,
                                      nonce_path=nonce_path, key_path=key_path)
    _report(violations, notes)
    if not violations and args.cert_out:
        Path(args.cert_out).write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
        print(f"CERTIFICATE written: {args.cert_out}")
    return 0 if not violations else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
