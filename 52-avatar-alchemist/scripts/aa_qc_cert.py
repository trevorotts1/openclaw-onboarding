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

# SK2-16 — the ONE canonical Anthropic model-id detector lives in
# shared-utils/assert_model_sovereignty.py. Fail-closed vendored fallback (same
# canonical pattern) so detection can never silently weaken if shared-utils is
# not resolvable at runtime.
sys.path.insert(0, str(SKILL_ROOT.parent / "shared-utils"))
try:
    from assert_model_sovereignty import is_anthropic_model  # type: ignore  # noqa: E402
except Exception:  # noqa: BLE001
    import re as _re
    _AA_ANTHROPIC_RE = _re.compile(r"anthropic|claude|\b(?:opus|sonnet|haiku)\b", _re.IGNORECASE)

    def is_anthropic_model(model_id) -> bool:  # type: ignore
        return bool(_AA_ANTHROPIC_RE.search(str(model_id or "")))

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
            _cap = s.get("floors", {}).get("bot_msg_char_cap")
            bd_checks.append(10.0 if not build._botdoc_defects(artifacts.get(sid, ""), msg_cap=_cap) else 0.0)
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


# ===========================================================================
# FIX-XC-03d — the SEMANTIC QC leg. The structural composite above is
# mathematically binary (0.0 on a content-gate fail, ~10 on a pass) and never
# discriminates prose QUALITY, so "independent QC >= 8.5" was not a real
# quality bar. This adds the missing second leg: a DETACHED QC-SEMANTIC.json
# produced by an independent VERIFIER sub-agent (!= any stage author), running
# the client's own TIER-A model, applying the 10-category OpenClaw QC Protocol
# to EACH artifact. The verifier model id is recorded + G-NOANTHROPIC-checked,
# the full verifier transcript's sha256 is embedded, and the whole certificate
# is HMAC-signed with the per-run foreman key. aa_delivery_gate.py requires
# BOTH certificates, with the semantic score >= 8.5, before it will deliver.
#
# The LLM verifier itself is the ONE non-deterministic seam (--verifier-cmd, or
# an operator/verifier-supplied --judgment-file). `synth_semantic_judgment` is a
# DETERMINISTIC stand-in used ONLY by the golden builder and the self-tests
# (never a client run) so the offline fixtures can exercise the signed cert +
# the delivery-gate binding without a live model.
# ===========================================================================
OPENCLAW_QC_CATEGORIES = [
    "accuracy", "completeness", "clarity", "consistency", "actionability",
    "structure", "tone_fidelity", "relevance", "depth", "polish",
]
# a CLIENT tier-A id placeholder for the deterministic stand-in verifier; a real
# run records the client box's own tier-A model. NEVER an Anthropic id.
VERIFIER_TIER_A_DEFAULT = "ollama-cloud/qwen3-235b"


def synth_semantic_judgment(manifest: Dict[str, Any], run_dir: Path,
                            verifier_model: str = VERIFIER_TIER_A_DEFAULT,
                            base: float = 9.0) -> Dict[str, Any]:
    """DETERMINISTIC stand-in verifier judgment (golden builder + self-tests only).
    Emits a full 10-category score per artifact plus a transcript."""
    state = build.load_run(str(run_dir))
    per: Dict[str, Any] = {}
    author_models: Dict[str, str] = {}
    transcript_lines: List[str] = [f"OpenClaw QC Protocol semantic verification (verifier={verifier_model})"]
    for s in manifest["stages"]:
        sid = s["stage_id"]
        cats = {c: round(float(base), 2) for c in OPENCLAW_QC_CATEGORIES}
        score = round(sum(cats.values()) / len(cats), 2)
        per[sid] = {"categories": cats, "score": score}
        author_models[sid] = state["models"].get(sid, "")
        transcript_lines.append(f"{sid}: {score} :: " + ", ".join(f"{k}={v}" for k, v in cats.items()))
    return {"verifier_model": verifier_model, "per_artifact": per,
            "author_models": author_models, "transcript": "\n".join(transcript_lines)}


def _run_verifier_cmd(cmd: str, run_dir: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """The real seam: run the verifier sub-agent command (the run-dir path on
    AA_RUN_DIR, the artifact index on stdin) and parse a judgment JSON from
    stdout: {"verifier_model","per_artifact":{sid:{categories,score}},"transcript"}."""
    import os
    import subprocess
    state = build.load_run(str(run_dir))
    stdin_payload = json.dumps({"artifacts": {sid: state["artifacts"].get(sid, "")
                                              for sid in (s["stage_id"] for s in manifest["stages"])}})
    proc = subprocess.run(cmd, shell=True, input=stdin_payload, capture_output=True, text=True,
                          env={**os.environ, "AA_RUN_DIR": str(run_dir)})
    if proc.returncode != 0:
        raise RuntimeError(f"--verifier-cmd rc={proc.returncode}: {proc.stderr.strip()[:200]}")
    judgment = json.loads(proc.stdout)
    judgment.setdefault("author_models", {sid: state["models"].get(sid, "")
                                          for sid in (s["stage_id"] for s in manifest["stages"])})
    judgment.setdefault("transcript", proc.stdout)
    return judgment


def compute_semantic(judgment: Dict[str, Any]) -> Dict[str, Any]:
    per = judgment.get("per_artifact", {})
    scores = [float(v.get("score", 0.0)) for v in per.values()]
    return {
        "semantic_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "semantic_min": round(min(scores), 2) if scores else 0.0,
        "artifact_count": len(per),
    }


def build_semantic_certificate(manifest: Dict[str, Any], run_dir: Path, run_id: str,
                               key: bytes, judgment: Dict[str, Any]) -> Dict[str, Any]:
    agg = compute_semantic(judgment)
    transcript = str(judgment.get("transcript", ""))
    fields: Dict[str, Any] = {
        "certificate": "avatar-alchemist-qc-semantic",
        "run_id": run_id,
        "issued_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "protocol": "OpenClaw QC Protocol (10-category, per-artifact)",
        "categories": OPENCLAW_QC_CATEGORIES,
        "verifier_role": "independent verifier sub-agent (!= any stage author)",
        "verifier_model": str(judgment.get("verifier_model", "")),
        "semantic_score": agg["semantic_score"],
        "semantic_min": agg["semantic_min"],
        "semantic_floor": 8.5,
        "artifact_count": agg["artifact_count"],
        "per_artifact_scores": {sid: round(float(v.get("score", 0.0)), 2)
                                for sid, v in judgment.get("per_artifact", {}).items()},
        "author_models": judgment.get("author_models", {}),
        "transcript_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
    }
    fields["signature"] = _hmac(key, _canon(fields))
    return fields


def verify_semantic_signature(cert: Dict[str, Any], key: bytes) -> bool:
    cert = dict(cert)
    sig = cert.pop("signature", None)
    if not sig:
        return False
    return hmac.compare_digest(_hmac(key, _canon(cert)), sig)


def semantic_verifier_is_anthropic(cert: Dict[str, Any]) -> bool:
    # SK2-16 — defer to the one canonical detector (shared-utils).
    return is_anthropic_model(cert.get("verifier_model", ""))


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

        # --- FIX-XC-03d: the SEMANTIC leg -----------------------------------
        # rebuild a clean run first (the bad-cert block above blanked 16-brand-bio)
        good_state = build._synth(manifest, apply_repairs=True)
        for sid, txt in good_state["artifacts"].items():
            (run_dir / "artifacts" / f"{sid}.md").write_text(txt, encoding="utf-8")
        judgment = synth_semantic_judgment(manifest, run_dir, base=9.0)
        sem = build_semantic_certificate(manifest, run_dir, "selftest", key, judgment)
        if (sem["semantic_score"] >= 8.5 and verify_semantic_signature(sem, key)
                and not semantic_verifier_is_anthropic(sem)
                and sem["artifact_count"] == len(manifest["stages"])
                and len(sem["transcript_sha256"]) == 64):
            print(f"SELF-TEST ok: (FIX-XC-03d) semantic cert -> score={sem['semantic_score']} over "
                  f"{sem['artifact_count']} artifacts (10-cat OpenClaw QC), verifier "
                  f"{sem['verifier_model']!r} (non-Anthropic), transcript sha256 bound, HMAC verifies.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: semantic cert -> {sem}")
        # a hand-edited semantic score breaks the signature
        forged_sem = dict(sem); forged_sem["semantic_score"] = 9.99
        if verify_semantic_signature(forged_sem, key):
            ok = False
            print("SELF-TEST FAIL: a hand-edited semantic_score STILL verified.")
        else:
            print("SELF-TEST ok: a hand-edited semantic_score fails signature verification.")
        # an Anthropic verifier model is detectable (delivery gate rejects it)
        anthro_sem = build_semantic_certificate(manifest, run_dir, "selftest", key,
                                                synth_semantic_judgment(manifest, run_dir,
                                                                        verifier_model="anthropic/claude-3-5-sonnet"))
        if semantic_verifier_is_anthropic(anthro_sem):
            print("SELF-TEST ok: an Anthropic verifier model id is detected (G-NOANTHROPIC on the semantic leg).")
        else:
            ok = False
            print("SELF-TEST FAIL: an Anthropic verifier model id was NOT detected.")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist detached, independently-computed QC certificate.")
    ap.add_argument("--run-dir")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--key-file", help="path to the per-run foreman key (entry.sh mints <run_dir>/.foreman-key)")
    ap.add_argument("--out", help="write the signed QC certificate here")
    ap.add_argument("--manifest")
    ap.add_argument("--semantic", action="store_true",
                    help="build the SEMANTIC QC certificate (QC-SEMANTIC.json) from an independent "
                         "verifier sub-agent instead of the structural composite (FIX-XC-03d)")
    ap.add_argument("--judgment-file", help="with --semantic: a verifier-produced judgment JSON")
    ap.add_argument("--verifier-cmd", help="with --semantic: verifier sub-agent command (client TIER-A "
                                           "model; run-dir on AA_RUN_DIR, artifacts on stdin, judgment JSON on stdout)")
    ap.add_argument("--synth", action="store_true",
                    help="with --semantic: DETERMINISTIC stand-in judgment (golden builder / tests ONLY)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest or _manifest_path()).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load manifest: {exc}")
        return 3
    if args.self_test:
        return run_self_test(manifest)

    if args.semantic:
        if not (args.run_dir and args.key_file):
            print("USAGE ERROR: --semantic requires --run-dir --key-file.")
            return 3
        try:
            key = bytes.fromhex(Path(args.key_file).read_text(encoding="utf-8").strip())
            run_dir = Path(args.run_dir)
            run_id = args.run_id or run_dir.name
            if args.judgment_file:
                judgment = json.loads(Path(args.judgment_file).read_text(encoding="utf-8"))
            elif args.verifier_cmd:
                judgment = _run_verifier_cmd(args.verifier_cmd, run_dir, manifest)
            elif args.synth:
                judgment = synth_semantic_judgment(manifest, run_dir)
            else:
                print("USAGE ERROR: --semantic needs one of --judgment-file / --verifier-cmd / --synth.")
                return 3
            sem = build_semantic_certificate(manifest, run_dir, run_id, key, judgment)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: {exc}")
            return 3
        if semantic_verifier_is_anthropic(sem):
            print(f"REFUSED: verifier model {sem['verifier_model']!r} is an Anthropic id (G-NOANTHROPIC).")
            return 2
        if args.out:
            Path(args.out).write_text(json.dumps(sem, indent=2) + "\n", encoding="utf-8")
            print(f"QC-SEMANTIC written: {args.out}")
        print(f"semantic_score={sem['semantic_score']} (min {sem['semantic_min']}) "
              f"verifier={sem['verifier_model']}")
        return 0 if sem["semantic_score"] >= 8.5 else 2

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
