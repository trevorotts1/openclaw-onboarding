#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_cert.py — fail-closed verifier for the Sales Page Assets PROCESS-CERTIFICATE
(Skill 56). The certificate is the delivery-blocking proof that EVERY phase ran, in order,
and passed its gate — no certificate, or a tampered one, means the asset stack is NOT done
(AF-SP56-PROCESS-INTEGRITY, mirroring the Skill 49 / presentations certificate).

The orchestrator (run_sales_page_assets.py) emits a certificate signed with an HMAC-SHA256
over the phase attestations, keyed by the run-scoped front-door nonce. This prover re-verifies:
  * the certificate object is well-formed;                      -> AF-SP56-CERT-MISSING
  * phases are contiguous order 0..N with no gaps/dupes;        -> AF-SP56-CERT-PHASE-GAP
  * every phase status is "pass" and all_phases_pass is true;   -> AF-SP56-CERT-PHASE-FAIL
  * the HMAC signature is valid for the provided nonce.         -> AF-SP56-CERT-SIGNATURE

Any failure => the asset stack never reaches Complete (AF-SP56-PROCESS-INTEGRITY).

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

CERT_KIND = "sales-page-assets-process-certificate"

# Canonical phase spine — the orchestrator must attest each in this order.
# (Delegated seams: P2 images -> Skill 47 / client image provider; P4 media + P9 build -> Skill 6.)
EXPECTED_PHASES = (
    ("P0-INTAKE",     "prove_sp_intake.py"),
    ("P1-IMAGE-PLAN", "prove_sp_image_plan.py"),
    ("P2-IMAGES",     "kie_image.py"),          # Skill 47 / client image provider
    ("P3-COPY",       "prove_sp_copy_suite"),   # main-8 + upsell-9 + high-ticket band + bump band
    ("P4-MEDIA",      "ghl_media.py + prove_sp_media.py"),  # Skill 6 delegation + FIX-IMG-02 provenance/coverage gate
    ("P5-FRAGMENTS",  "fragment_strip"),        # deterministic sanitize/fragment-ize (P5, NOT an LLM pass)
    ("P6-DOCS",       "drive_docs"),            # Track 1 (client-editable Google Docs)
    ("P7-BUNDLE",     "prove_sp_bundle.py"),    # Track 2 (build bundle + funnel-manifest)
    ("P8-DELIVER",    "delivery_email"),        # productionized subject + folder link
    ("P9-HANDOFF",    "ghl_rest_canvas.py"),    # Skill 6 build handoff (+ Skill 44 bump seam)
)


# ── FIX-XC-09e — model-content receipt (the client's OWN strongest model wrote copy) ──
AF_MODEL_TIER = "AF-SP56-MODEL-TIER"
AF_MODEL_NOANTHROPIC = "AF-SP56-MODEL-NOANTHROPIC"
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
        return [("AF-SP56-CERT-MISSING", "certificate is not a JSON object")]
    if cert.get("certificate") != CERT_KIND:
        fails.append(("AF-SP56-CERT-MISSING", f"not a {CERT_KIND} (got {cert.get('certificate')!r})"))
    for field in ("run_id", "phases", "signature", "issued_at"):
        if field not in cert:
            fails.append(("AF-SP56-CERT-MISSING", f"certificate missing required field '{field}'"))

    phases = cert.get("phases")
    if not isinstance(phases, list) or not phases:
        fails.append(("AF-SP56-CERT-PHASE-GAP", "certificate carries no phases"))
    else:
        orders = []
        for ph in phases:
            if not isinstance(ph, dict):
                fails.append(("AF-SP56-CERT-PHASE-GAP", "a phase entry is not an object"))
                continue
            orders.append(ph.get("order"))
            if str(ph.get("status", "")).strip().lower() != "pass":
                fails.append(("AF-SP56-CERT-PHASE-FAIL",
                              f"phase {ph.get('id')!r} status is {ph.get('status')!r}, not 'pass'"))
        clean_orders = [o for o in orders if isinstance(o, int)]
        if sorted(clean_orders) != list(range(len(orders))):
            fails.append(("AF-SP56-CERT-PHASE-GAP",
                          f"phase orders {orders} are not contiguous 0..{len(orders) - 1} (a phase was skipped)"))

    if cert.get("all_phases_pass") is not True:
        fails.append(("AF-SP56-CERT-PHASE-FAIL", "all_phases_pass is not true"))

    sig = cert.get("signature")
    if not isinstance(sig, str) or not sig:
        fails.append(("AF-SP56-CERT-SIGNATURE", "certificate has no signature"))
    elif nonce is None:
        fails.append(("AF-SP56-CERT-SIGNATURE",
                      "no nonce supplied to verify the signature (fail-closed: cannot trust an unverifiable cert)"))
    else:
        expected = sign(canonical_payload(cert), nonce)
        if not hmac.compare_digest(expected, sig):
            fails.append(("AF-SP56-CERT-SIGNATURE",
                          "HMAC signature does not match the nonce — the certificate was tampered or forged"))

    if fails:
        fails.append(("AF-SP56-PROCESS-INTEGRITY", "process certificate invalid — asset stack is NOT done"))
    return fails


def evaluate_cert(cert: Any, nonce: Optional[str]) -> Tuple[int, List[Tuple[str, str]]]:
    fails = verify(cert, nonce)
    if not fails:
        return EXIT_OK, []
    return EXIT_VIOLATION, fails


def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(code: int, fails) -> None:
    if code == EXIT_OK:
        print("PASS: PROCESS-CERTIFICATE valid — every phase ran in order, passed, signature verified.")
        return
    print(f"FAIL: PROCESS-CERTIFICATE invalid ({len(fails)} finding(s)) — asset stack is NOT done.")
    for c, m in fails:
        print(f"  [{c}] {m}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def _valid_cert(nonce: str) -> Dict[str, Any]:
    cert = {
        "certificate": CERT_KIND,
        "version": "1.0.0",
        "run_id": "jane-doe__glow-method__run-20260702-01",
        "funnel_type": "sales_page_assets",
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
    c = _valid_cert(nonce); c["funnel_type"] = "signature_funnel"
    code, fails = evaluate_cert(c, nonce)
    if code == EXIT_VIOLATION and any(x == "AF-SP56-CERT-SIGNATURE" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: tampered cert -> AF-SP56-CERT-SIGNATURE.")
    else:
        ok = False; print(f"SELF-TEST FAIL: tampered cert -> {fails}")

    c = _valid_cert(nonce); c["phases"] = c["phases"][:3] + c["phases"][4:]
    c["signature"] = sign(canonical_payload(c), nonce)
    code, fails = evaluate_cert(c, nonce)
    if code == EXIT_VIOLATION and any(x == "AF-SP56-CERT-PHASE-GAP" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: skipped-phase cert -> AF-SP56-CERT-PHASE-GAP.")
    else:
        ok = False; print(f"SELF-TEST FAIL: skipped-phase cert -> {fails}")

    c = _valid_cert(nonce); c["phases"][2]["status"] = "fail"
    c["signature"] = sign(canonical_payload(c), nonce)
    code, fails = evaluate_cert(c, nonce)
    if code == EXIT_VIOLATION and any(x == "AF-SP56-CERT-PHASE-FAIL" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: failing-phase cert -> AF-SP56-CERT-PHASE-FAIL.")
    else:
        ok = False; print(f"SELF-TEST FAIL: failing-phase cert -> {fails}")

    code, fails = evaluate_cert(_valid_cert(nonce), "the-wrong-nonce")
    if code == EXIT_VIOLATION and any(x == "AF-SP56-CERT-SIGNATURE" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: wrong-nonce -> AF-SP56-CERT-SIGNATURE.")
    else:
        ok = False; print(f"SELF-TEST FAIL: wrong-nonce -> {fails}")

    # FIX-XC-09e — model-content receipt fixtures
    mr_ok = evaluate_model_receipt(
        {"role": "content", "model": "deepseek-v3-chat", "provider": "deepseek", "tier": "content"})
    mr_absent = evaluate_model_receipt(None)
    mr_anthropic = evaluate_model_receipt(
        {"role": "content", "model": "claude-opus-4", "provider": "anthropic", "tier": "content"})
    mr_cheaptier = evaluate_model_receipt(
        {"role": "content", "model": "some-mini", "provider": "openrouter", "tier": "simple"})
    if not mr_ok and any(c == AF_MODEL_TIER for c, _ in mr_absent) \
            and any(c == AF_MODEL_NOANTHROPIC for c, _ in mr_anthropic) \
            and any(c == AF_MODEL_TIER for c, _ in mr_cheaptier):
        print("SELF-TEST ok: model-tier receipt (valid pass; absent/anthropic/cheap fail).")
    else:
        ok = False
        print(f"SELF-TEST FAIL: model receipt -> {mr_ok}/{mr_absent}/{mr_anthropic}/{mr_cheaptier}")

    print(f"SELF-TEST FIXTURES: 1 valid-pass, {caught}/4 tamper-catch + model-tier receipt")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed verifier for the Sales Page Assets PROCESS-CERTIFICATE. "
                    "Exit 0 valid, 2 invalid/tampered, 3 usage.")
    ap.add_argument("--cert", help="path to PROCESS-CERTIFICATE.json ('-' reads stdin)")
    ap.add_argument("--nonce", help="the run-scoped front-door nonce (or set SPA_RUN_NONCE)")
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
        nonce = args.nonce or os.environ.get("SPA_RUN_NONCE")
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
            print(f"FAIL: model-content receipt invalid ({len(mfails)} finding(s)) — asset stack is NOT done.")
            for c, m in mfails:
                print(f"  [{c}] {m}")
            code = EXIT_VIOLATION
        else:
            print("PASS: model-content receipt valid — client execution-tier model, no Anthropic.")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
