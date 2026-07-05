#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_cert.py — fail-closed verifier for the Signature Funnel PROCESS-CERTIFICATE
(Skill 49). The certificate is the delivery-blocking proof that EVERY phase ran, in order,
and passed its gate — no certificate, or a tampered one, means the funnel is NOT done
(AF-FUN-PROCESS-INTEGRITY, mirroring the presentations prove-deck certificate).

The orchestrator (run_signature_funnel.py) emits a certificate signed with an HMAC-SHA256
over the phase attestations, keyed by the run-scoped front-door nonce. This prover
re-verifies:
  * the certificate object is well-formed;                      -> AF-FUN-CERT-MISSING
  * phases are contiguous order 0..N with no gaps/dupes;        -> AF-FUN-CERT-PHASE-GAP
  * every phase status is "pass" and all_phases_pass is true;   -> AF-FUN-CERT-PHASE-FAIL
  * the HMAC signature is valid for the provided nonce.         -> AF-FUN-CERT-SIGNATURE

Any failure => the funnel never reaches Complete (AF-FUN-PROCESS-INTEGRITY).

stdlib only. Exit 0 = valid, exit 2 = invalid/tampered, exit 3 = usage/fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

CERT_KIND = "signature-funnel-process-certificate"

# Canonical phase spine — the orchestrator must attest each in this order.
EXPECTED_PHASES = (
    ("P0-INTAKE", "prove_sf_intake.py"),
    ("P1-COPY", "prove_sf_copy.py"),
    ("P2-PROMPTS", "prove_sf_prompt_floor.py"),
    ("P3-IMAGES", "kie_image.py"),          # Skill 47 delegation (provenance checked at P4/P9)
    ("P4-MEDIA", "ghl_media.py"),           # Skill 6 delegation
    ("P5-HTML", "html_fragments"),          # artifact-backed gate (pages/<profile>.fragment.html)
    ("P6-COMPOSE", "prove_sf_graph.py"),    # funnel_graph.json vs MASTERDOC §3
    ("P7-BUILD", "prove_sf_build.py"),      # build_receipt.json (QC >= 8.5 + previews); Skill 6 build
    ("P8-DERIVE", "derived_pages_ledger"),
    ("P9-CERTIFY", "prove_sf_no_pitch.py"),
)


# ── FIX-XC-09e — model-content receipt (the client's OWN strongest model wrote copy) ──
AF_MODEL_TIER = "AF-FUN-MODEL-TIER"
AF_MODEL_NOANTHROPIC = "AF-FUN-MODEL-NOANTHROPIC"
# Execution/content-tier slugs the authoring model must resolve to (not a cheap/simple tier).
EXECUTION_TIERS = {"content", "execution", "exec", "strong", "strongest",
                   "authoring", "primary", "tier-a", "tier_a", "a"}
_ANTHROPIC_PROVIDERS = {"anthropic", "claude"}


def evaluate_model_receipt(receipt: Any) -> List[Tuple[str, str]]:
    """Fail-closed: the run must record that the CLIENT's own execution-tier model wrote the
    copy (routing/model-content-receipt.json). Anthropic is hard-banned by provider FIELD."""
    fails: List[Tuple[str, str]] = []
    if not isinstance(receipt, dict):
        return [(AF_MODEL_TIER, "model-content-receipt is missing/not a JSON object — "
                 "the authoring model was never resolved/recorded (fail-closed)")]
    model = str(receipt.get("model") or receipt.get("model_id") or "").strip()
    provider = str(receipt.get("provider") or "").strip().lower()
    tier = str(receipt.get("tier") or receipt.get("role") or "").strip().lower()
    if not model:
        fails.append((AF_MODEL_TIER, "model-content-receipt names no resolved model id"))
    # Anthropic hard-ban tested on the provider FIELD (not just an id shape).
    if provider in _ANTHROPIC_PROVIDERS or model.lower().startswith(("claude", "anthropic")) \
            or "anthropic" in model.lower():
        fails.append((AF_MODEL_NOANTHROPIC,
                      f"authoring model is Anthropic (provider={provider!r}, model={model!r}) — "
                      "client skills never use Anthropic models"))
    if tier not in EXECUTION_TIERS:
        fails.append((AF_MODEL_TIER,
                      f"authoring tier {tier!r} is not an execution/content tier {sorted(EXECUTION_TIERS)} — "
                      "the client's OWN strongest model must write the copy"))
    return fails


def canonical_payload(cert: Dict[str, Any]) -> bytes:
    """The signed portion = the whole certificate MINUS its 'signature' field, serialized
    deterministically (sorted keys, tight separators). Orchestrator + verifier must agree."""
    c = {k: v for k, v in cert.items() if k != "signature"}
    return json.dumps(c, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign(payload: bytes, nonce: str) -> str:
    return hmac.new(nonce.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify(cert: Any, nonce: Optional[str]) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []
    if not isinstance(cert, dict):
        return [("AF-FUN-CERT-MISSING", "certificate is not a JSON object")]
    if cert.get("certificate") != CERT_KIND:
        fails.append(("AF-FUN-CERT-MISSING", f"not a {CERT_KIND} (got {cert.get('certificate')!r})"))
    for field in ("run_id", "phases", "signature", "issued_at"):
        if field not in cert:
            fails.append(("AF-FUN-CERT-MISSING", f"certificate missing required field '{field}'"))

    phases = cert.get("phases")
    if not isinstance(phases, list) or not phases:
        fails.append(("AF-FUN-CERT-PHASE-GAP", "certificate carries no phases"))
    else:
        orders = []
        for ph in phases:
            if not isinstance(ph, dict):
                fails.append(("AF-FUN-CERT-PHASE-GAP", "a phase entry is not an object"))
                continue
            orders.append(ph.get("order"))
            if str(ph.get("status", "")).strip().lower() != "pass":
                fails.append(("AF-FUN-CERT-PHASE-FAIL",
                              f"phase {ph.get('id')!r} status is {ph.get('status')!r}, not 'pass'"))
        clean_orders = [o for o in orders if isinstance(o, int)]
        if sorted(clean_orders) != list(range(len(orders))):
            fails.append(("AF-FUN-CERT-PHASE-GAP",
                          f"phase orders {orders} are not contiguous 0..{len(orders) - 1} (a phase was skipped)"))

    if cert.get("all_phases_pass") is not True:
        fails.append(("AF-FUN-CERT-PHASE-FAIL", "all_phases_pass is not true"))

    # signature
    sig = cert.get("signature")
    if not isinstance(sig, str) or not sig:
        fails.append(("AF-FUN-CERT-SIGNATURE", "certificate has no signature"))
    elif nonce is None:
        fails.append(("AF-FUN-CERT-SIGNATURE",
                      "no nonce supplied to verify the signature (fail-closed: cannot trust an unverifiable cert)"))
    else:
        expected = sign(canonical_payload(cert), nonce)
        if not hmac.compare_digest(expected, sig):
            fails.append(("AF-FUN-CERT-SIGNATURE",
                          "HMAC signature does not match the nonce — the certificate was tampered or forged"))

    if fails:
        fails.append(("AF-FUN-PROCESS-INTEGRITY", "process certificate invalid — funnel is NOT done"))
    return fails


def evaluate_cert(cert: Any, nonce: Optional[str]) -> Tuple[int, List[Tuple[str, str]]]:
    fails = verify(cert, nonce)
    if not fails:
        return EXIT_OK, []
    # a purely structural absence is fail-closed; a tamper is a violation
    return EXIT_VIOLATION, fails


def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(code: int, fails) -> None:
    if code == EXIT_OK:
        print("PASS: PROCESS-CERTIFICATE valid — every phase ran in order, passed, signature verified.")
        return
    print(f"FAIL: PROCESS-CERTIFICATE invalid ({len(fails)} finding(s)) — funnel is NOT done.")
    for c, m in fails:
        print(f"  [{c}] {m}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def _valid_cert(nonce: str) -> Dict[str, Any]:
    cert = {
        "certificate": CERT_KIND,
        "version": "1.0.0",
        "run_id": "run-selftest-0001",
        "funnel_type": "signature_funnel",
        "funnel_size": 3,
        "skill_version": "1.0.0",
        "issued_at": "2026-07-02T00:00:00Z",
        "nonce_fingerprint": hashlib.sha256(nonce.encode()).hexdigest()[:16],
        "phases": [
            {"id": pid, "prover": prover, "status": "pass", "order": i}
            for i, (pid, prover) in enumerate(EXPECTED_PHASES)
        ],
        "all_phases_pass": True,
    }
    cert["signature"] = sign(canonical_payload(cert), nonce)
    return cert


def self_test() -> int:
    ok = True
    nonce = "selftest-nonce-abc123"

    code, fails = evaluate_cert(_valid_cert(nonce), nonce)
    if code == EXIT_OK:
        print("SELF-TEST ok: valid signed certificate PASSES (exit 0).")
    else:
        ok = False
        print(f"SELF-TEST FAIL: valid cert -> exit {code}: {fails}")

    caught = 0
    # tampered field (breaks signature)
    c = _valid_cert(nonce); c["funnel_size"] = 7
    code, fails = evaluate_cert(c, nonce)
    if code == EXIT_VIOLATION and any(x == "AF-FUN-CERT-SIGNATURE" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: tampered cert -> AF-FUN-CERT-SIGNATURE.")
    else:
        ok = False; print(f"SELF-TEST FAIL: tampered cert -> {fails}")

    # skipped phase (order gap)
    c = _valid_cert(nonce); c["phases"] = c["phases"][:3] + c["phases"][4:]
    c["signature"] = sign(canonical_payload(c), nonce)  # re-sign so we isolate the gap
    code, fails = evaluate_cert(c, nonce)
    if code == EXIT_VIOLATION and any(x == "AF-FUN-CERT-PHASE-GAP" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: skipped-phase cert -> AF-FUN-CERT-PHASE-GAP.")
    else:
        ok = False; print(f"SELF-TEST FAIL: skipped-phase cert -> {fails}")

    # a failing phase
    c = _valid_cert(nonce); c["phases"][2]["status"] = "fail"
    c["signature"] = sign(canonical_payload(c), nonce)
    code, fails = evaluate_cert(c, nonce)
    if code == EXIT_VIOLATION and any(x == "AF-FUN-CERT-PHASE-FAIL" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: failing-phase cert -> AF-FUN-CERT-PHASE-FAIL.")
    else:
        ok = False; print(f"SELF-TEST FAIL: failing-phase cert -> {fails}")

    # wrong nonce
    code, fails = evaluate_cert(_valid_cert(nonce), "the-wrong-nonce")
    if code == EXIT_VIOLATION and any(x == "AF-FUN-CERT-SIGNATURE" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: wrong-nonce -> AF-FUN-CERT-SIGNATURE.")
    else:
        ok = False; print(f"SELF-TEST FAIL: wrong-nonce -> {fails}")

    # FIX-XC-09e — model-content receipt fixtures
    mr_ok = evaluate_model_receipt(
        {"role": "content", "model": "deepseek-v3-chat", "provider": "deepseek", "tier": "content"})
    if not mr_ok:
        print("SELF-TEST ok: valid execution-tier model receipt PASSES.")
    else:
        ok = False; print(f"SELF-TEST FAIL: valid model receipt -> {mr_ok}")
    mr_absent = evaluate_model_receipt(None)
    mr_anthropic = evaluate_model_receipt(
        {"role": "content", "model": "claude-opus-4", "provider": "anthropic", "tier": "content"})
    mr_cheaptier = evaluate_model_receipt(
        {"role": "content", "model": "some-mini", "provider": "openrouter", "tier": "simple"})
    if any(c == AF_MODEL_TIER for c, _ in mr_absent) \
            and any(c == AF_MODEL_NOANTHROPIC for c, _ in mr_anthropic) \
            and any(c == AF_MODEL_TIER for c, _ in mr_cheaptier):
        print("SELF-TEST ok: absent/anthropic/cheap-tier model receipts FAIL fail-closed.")
    else:
        ok = False
        print(f"SELF-TEST FAIL: model receipt negatives -> {mr_absent} / {mr_anthropic} / {mr_cheaptier}")

    print(f"SELF-TEST FIXTURES: 1 valid-pass, {caught}/4 tamper-catch + model-tier receipt")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed verifier for the Signature Funnel PROCESS-CERTIFICATE. "
                    "Exit 0 valid, 2 invalid/tampered, 3 usage.")
    ap.add_argument("--cert", help="path to PROCESS-CERTIFICATE.json ('-' reads stdin)")
    ap.add_argument("--nonce", help="the run-scoped front-door nonce (or set SF_RUN_NONCE)")
    ap.add_argument("--model-receipt", help="path to routing/model-content-receipt.json "
                    "(FIX-XC-09e — proves the client's own execution-tier model wrote the copy)")
    ap.add_argument("--self-test", action="store_true", help="run built-in fixtures and assert")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.cert and not args.model_receipt:
        print("USAGE ERROR: pass --cert <PROCESS-CERTIFICATE.json> and/or --model-receipt (or --self-test).")
        return EXIT_FAILCLOSED

    code = EXIT_OK
    if args.cert:
        nonce = args.nonce or os.environ.get("SF_RUN_NONCE")
        try:
            cert = _load_json(args.cert)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot load certificate {args.cert!r}: {exc}")
            return EXIT_FAILCLOSED
        code, fails = evaluate_cert(cert, nonce)
        _report(code, fails)

    if args.model_receipt:
        try:
            receipt = _load_json(args.model_receipt)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot load model receipt {args.model_receipt!r}: {exc}")
            return EXIT_FAILCLOSED
        mfails = evaluate_model_receipt(receipt)
        if mfails:
            print(f"FAIL: model-content receipt invalid ({len(mfails)} finding(s)) — funnel is NOT done.")
            for c, m in mfails:
                print(f"  [{c}] {m}")
            code = EXIT_VIOLATION
        else:
            print("PASS: model-content receipt valid — client execution-tier model, no Anthropic.")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
