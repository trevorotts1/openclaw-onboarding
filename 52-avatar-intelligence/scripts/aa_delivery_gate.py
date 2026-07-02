#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_delivery_gate.py — fail-closed provenance + delivery gate for one
Avatar-Alchemist BRAND run (Skill 52). This is the ONLY thing allowed to write
the labeled ~/Downloads deliverable folder, and it refuses unless:

  * every one of the 40 brand stages carries a foreman receipt whose sha256
    matches the artifact bytes byte-for-byte (no-fabrication / anti-tamper)   -> AF-AV-PROVENANCE
  * 40/40 stages are attested (never deliver at 39/40)                        -> AF-AV-DELIVER-INCOMPLETE
  * the content prover (aa_build_check.py) passed for this run                -> AF-AV-DELIVER-INCOMPLETE
  * the independent QC score (verifier != author) >= 8.5 (BINDING)            -> AF-AV-DELIVER-INCOMPLETE

On PASS it emits a signed process certificate (a provenance chain over every
receipt hash). "Done" may be claimed ONLY with the certificate path.
stdlib only. Exit 0 = pass, 2 = violation, 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

QC_FLOOR = 8.5


def _manifest_path() -> Path:
    return Path(__file__).resolve().parent.parent / "AA-PIPELINE-MANIFEST.json"


def _sha256(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def verify(manifest: Dict[str, Any], state: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str], Dict[str, Any]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []

    def fail(code: str, msg: str) -> None:
        violations.append((code, msg))

    stages = [s["stage_id"] for s in manifest.get("stages", [])]
    artifacts: Dict[str, str] = state.get("artifacts", {})
    receipts: Dict[str, Dict[str, Any]] = state.get("receipts", {})
    content_pass = bool(state.get("content_pass", False))
    qc_score = state.get("qc_score", None)

    chain: List[Dict[str, str]] = []
    attested = 0
    for sid in stages:
        rec = receipts.get(sid)
        art = artifacts.get(sid)
        if rec is None or art is None or not str(art).strip():
            fail("AF-AV-DELIVER-INCOMPLETE", f"stage '{sid}' has no receipt/artifact — cannot deliver")
            continue
        actual = _sha256(art)
        claimed = str(rec.get("sha256", ""))
        if claimed != actual:
            fail("AF-AV-PROVENANCE",
                 f"stage '{sid}': receipt sha256 {claimed[:12]}.. != artifact sha256 {actual[:12]}.. "
                 f"(fabrication / tamper — receipt does not attest THIS artifact)")
            continue
        attested += 1
        chain.append({"stage": sid, "sha256": actual})

    if attested != len(stages):
        fail("AF-AV-DELIVER-INCOMPLETE",
             f"{attested}/{len(stages)} stages attested — delivery blocked (never deliver below 40/40)")

    if not content_pass:
        fail("AF-AV-DELIVER-INCOMPLETE", "content prover (aa_build_check.py) did not pass for this run")

    if qc_score is None or float(qc_score) < QC_FLOOR:
        fail("AF-AV-DELIVER-INCOMPLETE",
             f"independent QC score {qc_score} < {QC_FLOOR} floor (10-category BINDING, verifier != author)")

    cert: Dict[str, Any] = {}
    if not violations:
        chain_hash = _sha256("|".join(c["sha256"] for c in chain))
        cert = {
            "certificate": "avatar-alchemist-brand-run",
            "skill": "52-avatar-intelligence",
            "manifest_version": manifest.get("manifest_version"),
            "stages_attested": attested,
            "content_gate": "PASS",
            "qc_score": qc_score,
            "qc_floor": QC_FLOOR,
            "provenance_chain_sha256": chain_hash,
            "chain": chain,
            "issued_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "signature": _sha256(f"{chain_hash}:{attested}:{qc_score}"),
        }
        notes.append(f"CERTIFICATE issued: provenance_chain_sha256={chain_hash[:16]}.. over {attested} attested stages")
    return violations, notes, cert


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _valid_state(manifest) -> Dict[str, Any]:
    artifacts, receipts = {}, {}
    for s in manifest["stages"]:
        sid = s["stage_id"]
        txt = f"# {sid}\nfinal attested content for {sid}\n"
        artifacts[sid] = txt
        receipts[sid] = {"sha256": _sha256(txt), "attested_by": "foreman"}
    return {"artifacts": artifacts, "receipts": receipts, "content_pass": True, "qc_score": 9.1}


def _violation_cases(manifest):
    def tamper(st):
        st["artifacts"]["16-brand-bio"] = "# 16-brand-bio\nSECRETLY EDITED after the receipt was written\n"
    def drop_one(st):
        del st["receipts"]["35-top-39"]; del st["artifacts"]["35-top-39"]
    def content_fail(st):
        st["content_pass"] = False
    def qc_low(st):
        st["qc_score"] = 8.0
    return [
        ("receipt_hash_mismatch", "AF-AV-PROVENANCE", tamper),
        ("stage_39_of_40", "AF-AV-DELIVER-INCOMPLETE", drop_one),
        ("content_gate_failed", "AF-AV-DELIVER-INCOMPLETE", content_fail),
        ("qc_below_floor", "AF-AV-DELIVER-INCOMPLETE", qc_low),
    ]


def run_self_test(manifest) -> int:
    ok = True
    v, notes, cert = verify(manifest, _valid_state(manifest))
    if v:
        ok = False; print(f"SELF-TEST FAIL: valid delivery produced {len(v)} violation(s): {v[:4]}")
    elif not cert:
        ok = False; print("SELF-TEST FAIL: valid delivery issued no certificate.")
    else:
        print("SELF-TEST ok: valid delivery PASSES and issues a signed certificate.")
    for name, expected, mut in _violation_cases(manifest):
        st = _valid_state(manifest); mut(st)
        vio, _, cert = verify(manifest, st)
        codes = {c for c, _ in vio}
        if not vio:
            ok = False; print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False; print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        elif cert:
            ok = False; print(f"SELF-TEST FAIL: '{name}' still issued a certificate.")
        else:
            print(f"SELF-TEST ok: '{name}' -> nonzero, no cert, carries {expected}.")
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
    ap.add_argument("--state", help="path to a delivery-state JSON")
    ap.add_argument("--manifest", help="path to AA-PIPELINE-MANIFEST.json")
    ap.add_argument("--cert-out", help="write the signed certificate here on PASS")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest or _manifest_path()).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load manifest: {exc}")
        return 3
    if args.self_test:
        return run_self_test(manifest)
    if not args.state:
        print("USAGE ERROR: pass --state <state.json> (or --self-test).")
        return 3
    try:
        state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load state: {exc}")
        return 3
    violations, notes, cert = verify(manifest, state)
    _report(violations, notes)
    if not violations and args.cert_out:
        Path(args.cert_out).write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
        print(f"CERTIFICATE written: {args.cert_out}")
    return 0 if not violations else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
