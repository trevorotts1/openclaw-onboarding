#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_cert.py — fail-closed verifier for the Signature Funnel PROCESS-CERTIFICATE
(Skill 49). The certificate is the delivery-blocking proof that EVERY phase ran, in order,
and passed its gate — no certificate, or a tampered one, means the funnel is NOT done
(AF-FUN-PROCESS-INTEGRITY, mirroring the presentations prove-deck certificate).

The orchestrator (run_signature_funnel.py) emits a certificate signed with an HMAC-SHA256
over the phase attestations, keyed by the OPERATOR KEY (ENF-16): a secret file named by
SF_OPERATOR_KEY_FILE that lives outside the run dir and that the AI session is not given.
No caller-supplied nonce keys anything, so a certificate cannot be self-minted with a key the
AI chose. This prover re-verifies:
  * the certificate object is well-formed;                      -> AF-FUN-CERT-MISSING
  * phases are contiguous order 0..N with no gaps/dupes;        -> AF-FUN-CERT-PHASE-GAP
  * every phase status is "pass" and all_phases_pass is true;   -> AF-FUN-CERT-PHASE-FAIL
  * the HMAC signature is valid for the operator key.           -> AF-FUN-CERT-SIGNATURE

Any failure => the funnel never reaches Complete (AF-FUN-PROCESS-INTEGRITY).

stdlib only. Exit 0 = valid, exit 2 = invalid/tampered, exit 3 = usage/fail-closed.
"""

from __future__ import annotations

import argparse
import datetime
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
    ("P3-IMAGES", "kie_live_adapter.py"),   # Skill 66 policy + Skill 74 transport (provenance checked at P4/P9)
    ("P4-MEDIA", "delivery-rail receipt (P4)"),   # signed rail receipts (schema/delivery-rail-receipt.schema.json)
    ("P5-HTML", "html_fragments"),          # artifact-backed gate (pages/<profile>.fragment.html)
    ("P6-COMPOSE", "prove_sf_graph.py"),    # funnel_graph.json vs MASTERDOC §3
    ("P7-BUILD", "delivery-rail receipt (P7)"),   # build_receipt.json (QC >= 8.5 + previews) read against the rail's signed receipts
    ("P8-DERIVE", "derived_pages_ledger"),
    ("P9-CERTIFY", "prove_sf_no_pitch.py"),
)


# ── FIX-XC-09e — model-content receipt (the client's OWN strongest model wrote copy) ──
AF_MODEL_TIER = "AF-FUN-MODEL-TIER"
# Execution/content-tier slugs the authoring model must resolve to (not a cheap/simple tier).
EXECUTION_TIERS = {"content", "execution", "exec", "strong", "strongest",
                   "authoring", "primary", "tier-a", "tier_a", "a"}


KEY_FILE_ENV = "SF_OPERATOR_KEY_FILE"
MIN_KEY_CHARS = 32
MODEL_RECEIPT_REL = os.path.join("routing", "model-content-receipt.json")
MODEL_RECEIPT_SOURCE = "harness-routing-record"
_MODEL_SIGNED_FIELDS = ("role", "model", "provider", "tier", "resolved_from", "run_id",
                        "routing_record_sha256")


def load_operator_key(run_dir: Optional[Path] = None) -> Tuple[Optional[str], str]:
    """(key, reason). The operator key is a >=32-char secret in a file named by
    SF_OPERATOR_KEY_FILE: mode 0600-or-tighter, and never inside the run dir (the run dir is
    the AI-writable surface). Anything short of that returns (None, why) — fail-closed.
    ponytail: same-uid read protection is a deployment property (the launcher account owns the
    key; the AI tool process is not given the path). Upgrade path: a signing service."""
    raw = os.environ.get(KEY_FILE_ENV, "").strip()
    if not raw:
        return None, f"{KEY_FILE_ENV} is not set — no operator key"
    path = Path(raw).expanduser()
    try:
        path = path.resolve(strict=True)
        if not path.is_file():
            return None, "operator key path is not a regular file"
        if run_dir is not None and Path(run_dir).resolve() in path.parents:
            return None, "operator key lives inside the run dir — refused"
        if path.stat().st_mode & 0o077:
            return None, "operator key file is group/other accessible — refused"
        key = path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError) as exc:
        return None, f"operator key unreadable ({exc.__class__.__name__})"
    if len(key) < MIN_KEY_CHARS:
        return None, f"operator key shorter than {MIN_KEY_CHARS} characters"
    return key, ""


def _model_payload(receipt: Dict[str, Any]) -> bytes:
    return json.dumps({k: receipt.get(k) for k in _MODEL_SIGNED_FIELDS},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def mint_model_receipt(run_dir: Path, routing_record: Any, key: str) -> Dict[str, Any]:
    """Write routing/model-content-receipt.json from the HARNESS routing record (role/model/
    provider/tier the router resolved) and sign it with the operator key. The SF_CONTENT_*
    environment variables are never read: a model the AI named is not a routing record."""
    if not isinstance(routing_record, dict):
        raise ValueError("harness routing record is not a JSON object")
    receipt = {
        "role": "content",
        "model": str(routing_record.get("model") or routing_record.get("model_id") or "").strip(),
        "provider": str(routing_record.get("provider") or "").strip().lower(),
        "tier": str(routing_record.get("tier") or routing_record.get("role") or "").strip().lower(),
        "resolved_from": MODEL_RECEIPT_SOURCE,
        "run_id": Path(run_dir).resolve().name,
        "routing_record_sha256": hashlib.sha256(
            json.dumps(routing_record, sort_keys=True).encode("utf-8")).hexdigest(),
        "resolved_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    receipt["harness_sig"] = sign(_model_payload(receipt), key)
    out = Path(run_dir) / MODEL_RECEIPT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def evaluate_model_receipt(receipt: Any, key: Optional[str] = None,
                           run_id: Optional[str] = None) -> List[Tuple[str, str]]:
    """Fail-closed: the run must record that the CLIENT's own execution-tier model wrote the
    copy (routing/model-content-receipt.json), AND the receipt must be the harness-minted,
    operator-key-signed one (ENF-16) — an env-reported or unsigned receipt never passes."""
    fails: List[Tuple[str, str]] = []
    if not isinstance(receipt, dict):
        return [(AF_MODEL_TIER, "model-content-receipt is missing/not a JSON object — "
                 "the authoring model was never resolved/recorded (fail-closed)")]
    model = str(receipt.get("model") or receipt.get("model_id") or "").strip()
    tier = str(receipt.get("tier") or receipt.get("role") or "").strip().lower()
    if not model:
        fails.append((AF_MODEL_TIER, "model-content-receipt names no resolved model id"))
    if tier not in EXECUTION_TIERS:
        fails.append((AF_MODEL_TIER,
                      f"authoring tier {tier!r} is not an execution/content tier {sorted(EXECUTION_TIERS)} — "
                      "the client's OWN strongest model must write the copy"))
    sig = receipt.get("harness_sig")
    if receipt.get("resolved_from") != MODEL_RECEIPT_SOURCE or not isinstance(sig, str) or not sig:
        fails.append((AF_MODEL_TIER,
                      f"model-content-receipt is not a harness routing-record receipt "
                      f"(resolved_from={receipt.get('resolved_from')!r}, signed={bool(sig)}) — "
                      "a model named through the environment is self-reported, not routed"))
    elif key is None:
        fails.append((AF_MODEL_TIER, "no operator key to verify the model-content receipt signature"))
    elif not hmac.compare_digest(sign(_model_payload(receipt), key), sig):
        fails.append((AF_MODEL_TIER, "model-content receipt signature does not match the operator key — forged"))
    elif run_id is not None and receipt.get("run_id") != run_id:
        fails.append((AF_MODEL_TIER, f"model-content receipt is for run {receipt.get('run_id')!r}, not {run_id!r}"))
    return fails


def canonical_payload(cert: Dict[str, Any]) -> bytes:
    """The signed portion = the whole certificate MINUS its 'signature' field, serialized
    deterministically (sorted keys, tight separators). Orchestrator + verifier must agree."""
    c = {k: v for k, v in cert.items() if k != "signature"}
    return json.dumps(c, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign(payload: bytes, key: str) -> str:
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify(cert: Any, key: Optional[str]) -> List[Tuple[str, str]]:
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
    elif key is None:
        fails.append(("AF-FUN-CERT-SIGNATURE",
                      "no operator key to verify the signature (fail-closed: cannot trust an unverifiable cert)"))
    else:
        expected = sign(canonical_payload(cert), key)
        if not hmac.compare_digest(expected, sig):
            fails.append(("AF-FUN-CERT-SIGNATURE",
                          "HMAC signature does not match the operator key — the certificate was tampered or forged"))

    if fails:
        fails.append(("AF-FUN-PROCESS-INTEGRITY", "process certificate invalid — funnel is NOT done"))
    return fails


def evaluate_cert(cert: Any, key: Optional[str]) -> Tuple[int, List[Tuple[str, str]]]:
    fails = verify(cert, key)
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
def _valid_cert(key: str) -> Dict[str, Any]:
    cert = {
        "certificate": CERT_KIND,
        "version": "1.0.0",
        "run_id": "run-selftest-0001",
        "funnel_type": "signature_funnel",
        "funnel_size": 3,
        "skill_version": "1.0.0",
        "issued_at": "2026-07-02T00:00:00Z",
        "operator_key_fingerprint": hashlib.sha256(key.encode()).hexdigest()[:16],
        "phases": [
            {"id": pid, "prover": prover, "status": "pass", "order": i}
            for i, (pid, prover) in enumerate(EXPECTED_PHASES)
        ],
        "all_phases_pass": True,
    }
    cert["signature"] = sign(canonical_payload(cert), key)
    return cert


def self_test() -> int:
    import tempfile
    ok = True
    key = "selftest-operator-key-0123456789abcdef"

    code, fails = evaluate_cert(_valid_cert(key), key)
    if code == EXIT_OK:
        print("SELF-TEST ok: valid signed certificate PASSES (exit 0).")
    else:
        ok = False
        print(f"SELF-TEST FAIL: valid cert -> exit {code}: {fails}")

    caught = 0
    # tampered field (breaks signature)
    c = _valid_cert(key); c["funnel_size"] = 7
    code, fails = evaluate_cert(c, key)
    if code == EXIT_VIOLATION and any(x == "AF-FUN-CERT-SIGNATURE" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: tampered cert -> AF-FUN-CERT-SIGNATURE.")
    else:
        ok = False; print(f"SELF-TEST FAIL: tampered cert -> {fails}")

    # skipped phase (order gap)
    c = _valid_cert(key); c["phases"] = c["phases"][:3] + c["phases"][4:]
    c["signature"] = sign(canonical_payload(c), key)  # re-sign so we isolate the gap
    code, fails = evaluate_cert(c, key)
    if code == EXIT_VIOLATION and any(x == "AF-FUN-CERT-PHASE-GAP" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: skipped-phase cert -> AF-FUN-CERT-PHASE-GAP.")
    else:
        ok = False; print(f"SELF-TEST FAIL: skipped-phase cert -> {fails}")

    # a failing phase
    c = _valid_cert(key); c["phases"][2]["status"] = "fail"
    c["signature"] = sign(canonical_payload(c), key)
    code, fails = evaluate_cert(c, key)
    if code == EXIT_VIOLATION and any(x == "AF-FUN-CERT-PHASE-FAIL" for x, _ in fails):
        caught += 1; print("SELF-TEST ok: failing-phase cert -> AF-FUN-CERT-PHASE-FAIL.")
    else:
        ok = False; print(f"SELF-TEST FAIL: failing-phase cert -> {fails}")

    # wrong key, and NO key (ENF-16: a cert verifies only against the operator key)
    code, fails = evaluate_cert(_valid_cert(key), "a-key-the-ai-chose-0123456789abcdef")
    code2, fails2 = evaluate_cert(_valid_cert(key), None)
    if code == EXIT_VIOLATION and code2 == EXIT_VIOLATION \
            and all(any(x == "AF-FUN-CERT-SIGNATURE" for x, _ in f) for f in (fails, fails2)):
        caught += 1; print("SELF-TEST ok: wrong key / no operator key -> AF-FUN-CERT-SIGNATURE.")
    else:
        ok = False; print(f"SELF-TEST FAIL: wrong/absent key -> {fails} / {fails2}")

    # FIX-XC-09e + ENF-16 — model-content receipt fixtures (harness-minted, operator-signed)
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run-model"
        rd.mkdir()
        rid = rd.resolve().name
        mint_model_receipt(rd, {"model": "deepseek-v3-chat", "provider": "deepseek", "tier": "content"}, key)
        good = json.loads((rd / MODEL_RECEIPT_REL).read_text(encoding="utf-8"))
        mr_ok = evaluate_model_receipt(good, key, rid)
        mr_anthropic = evaluate_model_receipt(  # no vendor rule
            mint_model_receipt(rd, {"model": "claude-opus-4", "provider": "anthropic",
                                    "tier": "content"}, key), key, rid)
        mint_model_receipt(rd, {"model": "some-mini", "provider": "openrouter", "tier": "simple"}, key)
        mr_cheaptier = evaluate_model_receipt(
            json.loads((rd / MODEL_RECEIPT_REL).read_text(encoding="utf-8")), key, rid)
        # the pre-ENF-16 shell shape: named through SF_CONTENT_MODEL env, unsigned
        mr_env = evaluate_model_receipt(
            {"role": "content", "resolved_from": "client-provider-chain", "model": "deepseek-v3-chat",
             "provider": "deepseek", "tier": "content"}, key, rid)
        forged = dict(good, model="forged-model")
        mr_forged = evaluate_model_receipt(forged, key, rid)
        mr_other_run = evaluate_model_receipt(good, key, "some-other-run")
    mr_absent = evaluate_model_receipt(None)
    if not mr_ok:
        print("SELF-TEST ok: valid harness-minted execution-tier model receipt PASSES.")
    else:
        ok = False; print(f"SELF-TEST FAIL: valid model receipt -> {mr_ok}")
    if any(c == AF_MODEL_TIER for c, _ in mr_absent) \
            and not mr_anthropic \
            and any(c == AF_MODEL_TIER for c, _ in mr_cheaptier):
        print("SELF-TEST ok: absent/cheap-tier model receipts FAIL fail-closed; an Anthropic-family model PASSES (no vendor rule).")
    else:
        ok = False
        print(f"SELF-TEST FAIL: model receipt negatives -> {mr_absent} / {mr_anthropic} / {mr_cheaptier}")
    if mr_env and mr_forged and mr_other_run:
        print("SELF-TEST ok: env-named (unsigned), forged and other-run model receipts FAIL.")
    else:
        ok = False
        print(f"SELF-TEST FAIL: self-reported model receipt accepted -> {mr_env} / {mr_forged} / {mr_other_run}")

    print(f"SELF-TEST FIXTURES: 1 valid-pass, {caught}/4 tamper-catch + model-tier receipt")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed verifier for the Signature Funnel PROCESS-CERTIFICATE. "
                    "Exit 0 valid, 2 invalid/tampered, 3 usage. The signature is checked against "
                    f"the operator key named by {KEY_FILE_ENV} (never a caller-supplied nonce).")
    ap.add_argument("--cert", help="path to PROCESS-CERTIFICATE.json ('-' reads stdin)")
    ap.add_argument("--nonce", help="REMOVED (ENF-16): refused; the operator key is the only signing key")
    ap.add_argument("--model-receipt", help="path to routing/model-content-receipt.json "
                    "(FIX-XC-09e — proves the client's own execution-tier model wrote the copy; "
                    "verified against the operator key)")
    ap.add_argument("--mint-model-receipt", metavar="ROUTING_RECORD",
                    help="HARNESS ONLY: write a signed routing/model-content-receipt.json into --run-dir "
                         "from the harness routing record (role/model/provider/tier JSON)")
    ap.add_argument("--run-dir", help="the run dir (for --mint-model-receipt / --model-receipt run binding)")
    ap.add_argument("--self-test", action="store_true", help="run built-in fixtures and assert")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.nonce is not None or os.environ.get("SF_RUN_NONCE"):
        print("USAGE ERROR [AF-FUN-FRONT-DOOR]: --nonce / SF_RUN_NONCE are no longer accepted — "
              f"certificates verify against the operator key ({KEY_FILE_ENV}) only.")
        return EXIT_FAILCLOSED

    if not args.cert and not args.model_receipt and not args.mint_model_receipt:
        print("USAGE ERROR: pass --cert <PROCESS-CERTIFICATE.json> and/or --model-receipt "
              "(or --mint-model-receipt, or --self-test).")
        return EXIT_FAILCLOSED

    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir else None
    key, why = load_operator_key(run_dir)

    if args.mint_model_receipt:
        if run_dir is None or key is None:
            print(f"USAGE ERROR [AF-FUN-MODEL-TIER]: --mint-model-receipt needs --run-dir and the operator key"
                  f"{'' if key else ' (' + why + ')'}.")
            return EXIT_FAILCLOSED
        try:
            mint_model_receipt(run_dir, _load_json(args.mint_model_receipt), key)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot mint from routing record {args.mint_model_receipt!r}: {exc}")
            return EXIT_FAILCLOSED
        print(f"minted {MODEL_RECEIPT_REL} from the harness routing record.")
        if not args.cert and not args.model_receipt:
            return EXIT_OK

    code = EXIT_OK
    if args.cert:
        try:
            cert = _load_json(args.cert)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot load certificate {args.cert!r}: {exc}")
            return EXIT_FAILCLOSED
        code, fails = evaluate_cert(cert, key)
        if key is None:
            fails = [("AF-FUN-CERT-SIGNATURE", f"operator key unavailable: {why}")] + list(fails)
        _report(code, fails)

    if args.model_receipt:
        try:
            receipt = _load_json(args.model_receipt)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot load model receipt {args.model_receipt!r}: {exc}")
            return EXIT_FAILCLOSED
        mfails = evaluate_model_receipt(receipt, key, run_dir.name if run_dir else None)
        if mfails:
            print(f"FAIL: model-content receipt invalid ({len(mfails)} finding(s)) — funnel is NOT done.")
            for c, m in mfails:
                print(f"  [{c}] {m}")
            code = EXIT_VIOLATION
        else:
            print("PASS: model-content receipt valid — client execution-tier model.")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
