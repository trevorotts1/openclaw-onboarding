#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_qc_cert.py — detached, independently-computed QC certificate (Skill 52).

Closes A2 of the delivery-gate finding cluster: before this script existed,
`qc_score` was a bare caller-supplied float (`build_golden.py` hardcoded
`qc_score=9.2`) and the shipped certificate asserted "Independent QC: 9.2
(verifier != author)" with NO independent grader anywhere in the loop — a
fabricated overclaim baked into a signed artifact.

This script IS the independent verifier. It is a SEPARATE program from the
generator (build_golden.py / a real client run) and from the delivery gate
(aa_delivery_gate.py) — "verifier != author" now means something: this file
never writes artifacts, and the number it produces is a DETERMINISTIC
composite over 10 measurable categories of the on-disk run, not an assertion.

Honesty about what this is: it is a structural/provenance composite grade
(completeness, floors, counts, bands, structure, placeholder-cleanliness,
provider purity, section-relevance), NOT a human or LLM semantic read of prose
quality. The certificate says so explicitly (`qc_methodology`) so nobody can
re-read "verifier != author" as "an LLM graded this copy" — it did not.

The certificate is HMAC-signed with the SAME per-run foreman key entry.sh
mints (`<run_dir>/.foreman-key`), so aa_delivery_gate.py can bind it into the
process certificate and refuse to trust a hand-edited score.

stdlib only. Exit 0 = certificate written, 2 = run does not clear the content
gate (qc_score forced to 0.0, certificate still written so the failure is
visible), 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import aa_build_check as build  # noqa: E402

QC_METHODOLOGY = (
    "deterministic 10-category structural/provenance composite computed by "
    "aa_qc_cert.py (a separate program from the generator and the delivery "
    "gate) over the on-disk run; NOT a human or LLM semantic prose-quality "
    "grade."
)


def _manifest_path() -> Path:
    return SKILL_ROOT / "AA-PIPELINE-MANIFEST.json"


def _canon(fields: Dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))


def _hmac(key: bytes, body: str) -> str:
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def _ratio_score(actual: float, floor: float) -> float:
    if floor <= 0:
        return 10.0
    return max(0.0, min(10.0, 10.0 * actual / floor))


# ---------------------------------------------------------------------------
# the 10 categories. Each is scored 0-10 from measurable properties of the
# run; every formula is deterministic and reproducible from the same bytes.
# ---------------------------------------------------------------------------
def score_categories(manifest: Dict[str, Any], run_dir: Path) -> Tuple[Dict[str, float], List[str]]:
    state = build.load_run(str(run_dir))
    artifacts = state["artifacts"]
    stages = {s["stage_id"]: s for s in manifest["stages"]}
    cats: Dict[str, float] = {}
    notes: List[str] = []

    # 1. stage completeness
    have = sum(1 for sid in stages if artifacts.get(sid, "").strip() and sid in state["receipts"])
    cats["stage_completeness"] = 10.0 * have / max(1, len(stages))

    # 2. word-floor margin (average ratio, capped at 10, only floor-bearing stages)
    ratios = []
    for sid, s in stages.items():
        wf = s.get("floors", {}).get("word_floor")
        if wf:
            ratios.append(_ratio_score(build._words(artifacts.get(sid, "")), wf))
    cats["word_floor_margin"] = sum(ratios) / len(ratios) if ratios else 10.0

    # 3. count structure (39-count / headline 12+12+12 / ad_count>=10)
    count_checks = []
    for sid, s in stages.items():
        f = s.get("floors", {})
        txt = artifacts.get(sid, "")
        if f.get("count_39"):
            count_checks.append(10.0 if build._numbered(txt) == list(range(1, 40)) else 0.0)
        if f.get("headline_counts"):
            count_checks.append(10.0 if build._headline_counts(txt) == f["headline_counts"] else 0.0)
        if f.get("ad_count"):
            count_checks.append(_ratio_score(len(build._numbered(txt)), f["ad_count"]))
    cats["count_structure"] = sum(count_checks) / len(count_checks) if count_checks else 10.0

    # 4. image-prompt band compliance
    band_checks = []
    for sid, s in stages.items():
        cb = s.get("floors", {}).get("char_band")
        if cb:
            n = build._chars(artifacts.get(sid, ""))
            band_checks.append(10.0 if cb[0] <= n <= cb[1] else 0.0)
    cats["image_band_compliance"] = sum(band_checks) / len(band_checks) if band_checks else 10.0

    # 5. ad-set category-signature fidelity (only meaningful under apply_repairs)
    if state.get("apply_repairs"):
        cat_checks = []
        import re as _re
        for sid, s in stages.items():
            cat = s.get("floors", {}).get("adset_category")
            if cat:
                cat_checks.append(10.0 if _re.search(_re.escape(cat), artifacts.get(sid, ""), _re.IGNORECASE) else 0.0)
        cats["adset_category_fidelity"] = sum(cat_checks) / len(cat_checks) if cat_checks else 10.0
    else:
        cats["adset_category_fidelity"] = 10.0
        notes.append("adset_category_fidelity: N/A (repairs OFF, faithful-to-live run) -> scored 10")

    # 6. bot-doc structure
    bd_checks = []
    for sid, s in stages.items():
        if s.get("floors", {}).get("botdoc"):
            bd_checks.append(10.0 if not build._botdoc_defects(artifacts.get(sid, "")) else 0.0)
    cats["botdoc_structure"] = sum(bd_checks) / len(bd_checks) if bd_checks else 10.0

    # 7. hero-page structure (12 named sections, in-band)
    hero_checks = []
    for sid, s in stages.items():
        if s.get("floors", {}).get("hero_sections"):
            hero_checks.append(10.0 if not build._hero_sections_defects(artifacts.get(sid, "")) else 0.0)
    cats["hero_structure"] = sum(hero_checks) / len(hero_checks) if hero_checks else 10.0

    # 8. placeholder cleanliness
    leaks = sum(len(build._tokens_left(t)) for t in artifacts.values())
    cats["placeholder_cleanliness"] = 10.0 if leaks == 0 else max(0.0, 10.0 - leaks)

    # 9. provider purity (G-NOANTHROPIC)
    violations, _ = build.verify(manifest, state)
    noanthropic_bad = sum(1 for c, _ in violations if c == "AF-AV-NOANTHROPIC")
    cats["provider_purity"] = 10.0 if noanthropic_bad == 0 else 0.0

    # 10. section relevance (avatar Q1-30 + five-lists)
    rel_checks = []
    for sid, s in stages.items():
        f = s.get("floors", {})
        if f.get("avatar_relevance"):
            defects = build._avatar_relevance_defects(artifacts.get(sid, ""))
            rel_checks.append(_ratio_score(13 - len(defects), 13))
        if f.get("five_list_relevance"):
            defects = build._five_list_defects(artifacts.get(sid, ""))
            rel_checks.append(10.0 if not defects else 0.0)
    cats["section_relevance"] = sum(rel_checks) / len(rel_checks) if rel_checks else 10.0

    return cats, notes


def compute(manifest: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
    state = build.load_run(str(run_dir))
    violations, _ = build.verify(manifest, state)
    content_gate_pass = not violations
    cats, notes = score_categories(manifest, run_dir)
    raw = sum(cats.values()) / len(cats) if cats else 0.0
    qc_score = round(raw, 2) if content_gate_pass else 0.0
    return {
        "qc_score": qc_score,
        "content_gate_pass": content_gate_pass,
        "content_gate_violation_count": len(violations),
        "categories": {k: round(v, 2) for k, v in cats.items()},
        "notes": notes,
        "qc_methodology": QC_METHODOLOGY,
        "verifier": "aa_qc_cert.py",
    }


def build_certificate(manifest: Dict[str, Any], run_dir: Path, run_id: str, key: bytes) -> Dict[str, Any]:
    result = compute(manifest, run_dir)
    fields = {
        "certificate": "avatar-alchemist-qc-cert",
        "run_id": run_id,
        "issued_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **result,
    }
    signature = _hmac(key, _canon(fields))
    return {**fields, "signature": signature}


def verify_signature(cert: Dict[str, Any], key: bytes) -> bool:
    cert = dict(cert)
    sig = cert.pop("signature", None)
    if not sig:
        return False
    return hmac.compare_digest(_hmac(key, _canon(cert)), sig)


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def run_self_test(manifest: Dict[str, Any]) -> int:
    import secrets
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        state = build._synth(manifest, apply_repairs=True)
        (run_dir / "artifacts").mkdir(parents=True)
        (run_dir / "receipts").mkdir(parents=True)
        for sid, txt in state["artifacts"].items():
            (run_dir / "artifacts" / f"{sid}.md").write_text(txt, encoding="utf-8")
            (run_dir / "receipts" / f"G-STAGE-{sid}.json").write_text(
                json.dumps({"stage": sid, "sha256": hashlib.sha256(txt.encode()).hexdigest(),
                            "model": state["models"][sid]}, indent=2), encoding="utf-8")
        (run_dir / "RUN-LEDGER.json").write_text(json.dumps(
            {"run_id": "selftest", "apply_repairs": True,
             "stages": {sid: {"model": state["models"][sid], "receipt": True} for sid in state["artifacts"]}},
            indent=2), encoding="utf-8")

        key = secrets.token_bytes(32)
        cert = build_certificate(manifest, run_dir, "selftest", key)
        if cert["content_gate_pass"] and cert["qc_score"] >= 8.5 and verify_signature(cert, key):
            print(f"SELF-TEST ok: valid run -> qc_score={cert['qc_score']} content_gate_pass=True, "
                  f"signature verifies with the correct key.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: valid run -> {cert}")

        # wrong key must NOT verify (the hand-forged-cert scenario: someone
        # edits qc_score without the real key)
        forged = dict(cert)
        forged["qc_score"] = 9.9
        if verify_signature(forged, key):
            ok = False
            print("SELF-TEST FAIL: a hand-edited qc_score STILL verified (signature not binding).")
        else:
            print("SELF-TEST ok: a hand-edited qc_score (same key, mutated field) fails --verify.")
        if verify_signature(cert, secrets.token_bytes(32)):
            ok = False
            print("SELF-TEST FAIL: a random/wrong key verified a certificate it did not sign.")
        else:
            print("SELF-TEST ok: a wrong/forged key cannot verify a certificate it did not sign.")

        # a content-gate-failing run must score 0.0, never a hardcoded float
        bad_state = build._synth(manifest, apply_repairs=True)
        bad_state["artifacts"]["16-brand-bio"] = ""
        (run_dir / "artifacts" / "16-brand-bio.md").write_text("", encoding="utf-8")
        bad_cert = build_certificate(manifest, run_dir, "selftest-bad", key)
        if bad_cert["qc_score"] == 0.0 and not bad_cert["content_gate_pass"]:
            print("SELF-TEST ok: a content-gate-failing run scores 0.0 (never a hardcoded/optimistic float).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: content-gate-failing run -> {bad_cert}")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist detached, independently-computed QC certificate.")
    ap.add_argument("--run-dir")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--key-file", help="path to the per-run foreman key (entry.sh mints <run_dir>/.foreman-key)")
    ap.add_argument("--out", help="write the signed QC certificate here")
    ap.add_argument("--manifest")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest or _manifest_path()).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load manifest: {exc}")
        return 3
    if args.self_test:
        return run_self_test(manifest)
    if not (args.run_dir and args.key_file):
        print("USAGE ERROR: --run-dir --key-file (or --self-test).")
        return 3
    try:
        key = bytes.fromhex(Path(args.key_file).read_text(encoding="utf-8").strip())
        run_id = args.run_id or Path(args.run_dir).name
        cert = build_certificate(manifest, Path(args.run_dir), run_id, key)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return 3
    if args.out:
        Path(args.out).write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
        print(f"QC-CERTIFICATE written: {args.out}")
    print(f"qc_score={cert['qc_score']} content_gate_pass={cert['content_gate_pass']}")
    return 0 if cert["content_gate_pass"] and cert["qc_score"] >= 8.5 else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
