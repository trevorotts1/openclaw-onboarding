#!/usr/bin/env python3
"""ghl_env_matrix_ground_truth.py — B-U15 item 2: the receipt SCHEMA +
COMPARATOR for the matrix's "first-hour ground truth" requirement.

WHY THIS EXISTS
----------------
ENV-MATRIX.md's adaptation contract item 5 (spec §9.4): "The first-hour
ground truth is run on BOTH one Mac and one VPS before any fix in this
family is declared fleet-ready." B-U15's BINARY acceptance (b) requires "the
same fixture build passes end-to-end on one Mac and one VPS ... receipts
compared."

This module is the COMPARATOR half of that requirement: a receipt SCHEMA
(``GROUND_TRUTH_REQUIRED_FIELDS``) any per-box fixture-build run emits, plus
``compare_ground_truth()`` / ``assert_ground_truth_parity()`` that prove the
two boxes' receipts show REAL behavioral parity (matching build outcome,
box-appropriate `durable_root()`/`is_vps()`/`supervisor()` resolution) rather
than two independently-eyeballed "looks fine" claims. It never runs a
dispatch→build→verify→FAB-QC pipeline itself (that pipeline is
`v2_dispatcher.py`, Section B.1.1 — out of this unit's scope) — it consumes
whatever receipt that pipeline emits.

THE LIVE LEG THIS DOES NOT AND CANNOT CLOSE (operator-gated, owed):
    Actually RUNNING the fixture build (dispatch → build → verify → FAB-QC)
    on a real Mac AND a real VPS, and producing the two receipts this module
    compares, requires real boxes with a real GoHighLevel test location —
    that is the live leg B-U15 defers to the operator (mirrors item 1's
    mount-proof live leg). This unit's tests prove the comparator's logic is
    correct against FIXTURE receipts (hermetic, no network) — never a
    fabricated pass on a receipt this module invented itself.

    `run_fixture_ground_truth()` / the `run` CLI subcommand (below) CLOSE the
    "which script actually produces a compare()-ready receipt" gap: they
    drive `v2_dispatcher.dispatch_one()` with a deterministic, no-network
    fixture builder/verifier and assemble a receipt in the EXACT
    `GROUND_TRUTH_REQUIRED_FIELDS` shape. This is still the OFFLINE/FIXTURE
    tier (same fixture-injection contract `tests/test_v2_dispatcher.py`
    already proves) — running this SAME command unmodified on a real Mac and
    a real VPS (swapping the fixture builder/verifier for the real
    `ghl_survey_builder`/`ghl_verify` pair against a designated GHL test
    location) is the genuine live leg, still owed to the operator, never
    fabricated here. `browser_manager` / `v2_dispatcher` are imported LAZILY
    inside `run_fixture_ground_truth()` (not at module top-level) so
    `validate`/`compare` — the pure, dependency-free comparator this module
    started as — never pay for the heavier dispatcher import graph.

CLI
---
    python3 ghl_env_matrix_ground_truth.py validate <receipt.json>
    python3 ghl_env_matrix_ground_truth.py compare <mac_receipt.json> <vps_receipt.json>
    python3 ghl_env_matrix_ground_truth.py run --evidence-root <dir> [--box-label <name>] [--run-id <id>]
    python3 ghl_env_matrix_ground_truth.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Callable, List, Optional

GROUND_TRUTH_VERSION = "v1.0.0"

# Matches the standing BUILD-QC gate (Section B.1.1 / v2-autonomous-build-sop.md
# ":964-971"): "a build below 8.5 is NOT done." Re-asserted here so a ground-
# truth receipt cannot claim parity while quietly shipping a sub-gate score.
FAB_QC_PASS_THRESHOLD = 8.5

GROUND_TRUTH_REQUIRED_FIELDS = (
    "box_label",
    "platform",
    "durable_root",
    "is_vps",
    "supervisor",
    "run_id",
    "dispatch_ok",
    "build_ok",
    "verify_passed",
    "fab_qc_score",
    "fab_qc_gate",
    "receipts_total",
)


class GroundTruthMismatch(AssertionError):
    """Two ground-truth receipts do not show the parity B-U15 requires."""


def validate_ground_truth_receipt(receipt: Any) -> List[str]:
    """Return a list of problems (empty = valid). Never raises — a caller
    building a live receipt-emission path can call this before writing to
    disk and fail loud with a concrete field list, not a stack trace."""
    problems: List[str] = []
    if not isinstance(receipt, dict):
        return [f"receipt must be a JSON object, got {type(receipt).__name__}"]
    for field in GROUND_TRUTH_REQUIRED_FIELDS:
        if field not in receipt:
            problems.append(f"missing required field: {field!r}")
    if "is_vps" in receipt and not isinstance(receipt["is_vps"], bool):
        problems.append(f"'is_vps' must be a bool, got {type(receipt.get('is_vps')).__name__}")
    if "fab_qc_score" in receipt and not isinstance(receipt["fab_qc_score"], (int, float)):
        problems.append(f"'fab_qc_score' must be numeric, got {type(receipt.get('fab_qc_score')).__name__}")
    return problems


def _check(checks: List[dict], name: str, ok: bool, detail: str) -> None:
    checks.append({"check": name, "pass": bool(ok), "detail": detail})


def compare_ground_truth(mac_receipt: dict, vps_receipt: dict) -> dict:
    """Compare a Mac-box and a VPS-box ground-truth receipt for the parity
    B-U15 acceptance (b) requires. Returns ``{"pass": bool, "checks": [...],
    "ts": ...}`` — the same shape as the existing `routing/form-preflight.json`
    convention elsewhere in this skill, so any consumer that already knows how
    to read a preflight-style receipt reads this one too."""
    checks: List[dict] = []

    mac_problems = validate_ground_truth_receipt(mac_receipt)
    _check(checks, "GT-01:mac_receipt_schema", not mac_problems,
           "well-formed" if not mac_problems else "; ".join(mac_problems))
    vps_problems = validate_ground_truth_receipt(vps_receipt)
    _check(checks, "GT-02:vps_receipt_schema", not vps_problems,
           "well-formed" if not vps_problems else "; ".join(vps_problems))

    if mac_problems or vps_problems:
        # Cannot safely compare fields the schema check already flagged as
        # missing/malformed — fail closed rather than KeyError.
        return {"pass": False, "checks": checks, "ts": _now()}

    _check(checks, "GT-03:mac_is_not_vps", mac_receipt["is_vps"] is False,
           f"mac_receipt.is_vps={mac_receipt['is_vps']!r} (expected False)")
    _check(checks, "GT-04:vps_is_vps", vps_receipt["is_vps"] is True,
           f"vps_receipt.is_vps={vps_receipt['is_vps']!r} (expected True)")

    mac_root = mac_receipt["durable_root"]
    vps_root = vps_receipt["durable_root"]
    _check(checks, "GT-05:mac_durable_root_not_vps_convention",
           mac_root != "/data/.openclaw" and not mac_root.startswith("/data/.openclaw"),
           f"mac_receipt.durable_root={mac_root!r}")
    _check(checks, "GT-06:vps_durable_root_is_data_openclaw",
           vps_root == "/data/.openclaw",
           f"vps_receipt.durable_root={vps_root!r} (expected '/data/.openclaw')")

    _check(checks, "GT-07:mac_supervisor_launchd", mac_receipt["supervisor"] == "launchd",
           f"mac_receipt.supervisor={mac_receipt['supervisor']!r}")
    _check(checks, "GT-08:vps_supervisor_pm2_or_systemd", vps_receipt["supervisor"] == "pm2-or-systemd",
           f"vps_receipt.supervisor={vps_receipt['supervisor']!r}")

    for label, receipt in (("mac", mac_receipt), ("vps", vps_receipt)):
        _check(checks, f"GT-09:{label}_dispatch_ok", receipt["dispatch_ok"] is True,
               f"{label}_receipt.dispatch_ok={receipt['dispatch_ok']!r}")
        _check(checks, f"GT-10:{label}_build_ok", receipt["build_ok"] is True,
               f"{label}_receipt.build_ok={receipt['build_ok']!r}")
        _check(checks, f"GT-11:{label}_verify_passed", receipt["verify_passed"] is True,
               f"{label}_receipt.verify_passed={receipt['verify_passed']!r}")
        _check(checks, f"GT-12:{label}_fab_qc_gate_pass", receipt["fab_qc_gate"] == "PASS",
               f"{label}_receipt.fab_qc_gate={receipt['fab_qc_gate']!r}")
        score = receipt["fab_qc_score"]
        _check(checks, f"GT-13:{label}_fab_qc_score_meets_threshold",
               score >= FAB_QC_PASS_THRESHOLD,
               f"{label}_receipt.fab_qc_score={score!r} (threshold {FAB_QC_PASS_THRESHOLD})")
        _check(checks, f"GT-14:{label}_receipts_total_nonzero", receipt["receipts_total"] > 0,
               f"{label}_receipt.receipts_total={receipt['receipts_total']!r} — a build that "
               f"wrote zero object receipts proves nothing (F6 'no receipt = not created')")

    overall = all(c["pass"] for c in checks)
    return {"pass": overall, "checks": checks, "ts": _now()}


def assert_ground_truth_parity(mac_receipt: dict, vps_receipt: dict) -> None:
    """Raise ``GroundTruthMismatch`` unless every comparator check passes —
    the fail-closed entrypoint a build-unit gate calls."""
    result = compare_ground_truth(mac_receipt, vps_receipt)
    if not result["pass"]:
        failed = [c for c in result["checks"] if not c["pass"]]
        detail = "; ".join(f"{c['check']}: {c['detail']}" for c in failed)
        raise GroundTruthMismatch(f"ground-truth parity FAILED ({len(failed)} check(s)): {detail}")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Emitter half — produce a compare()-ready receipt (lazy dispatcher import)
# ---------------------------------------------------------------------------

def _default_fixture_builder() -> "Callable[[dict, str], dict]":
    """Deterministic, offline, no-network builder — same fixture-injection
    contract `tests/test_v2_dispatcher.py`'s `_builder_ok` proves per-box."""
    def _b(task: dict, evidence_root: str) -> dict:
        funnel_dir = os.path.join(evidence_root, "funnel")
        os.makedirs(funnel_dir, exist_ok=True)
        with open(os.path.join(funnel_dir, "ledger.json"), "w", encoding="utf-8") as fh:
            json.dump({"built": True, "ground_truth_fixture": True}, fh)
        return {
            "pages": [{"step": "optin", "preview_url": "https://fixture.invalid/optin",
                       "marker": "GROUND-TRUTH-FIXTURE"}],
            "location_gate_ok": True,
            "duration_s": 1.0,
        }
    return _b


def _default_fixture_verifier() -> "Callable[..., dict]":
    """Deterministic, offline verifier mirroring `ghl_verify.verify_all`'s
    return contract (same shape `tests/test_v2_dispatcher.py`'s
    `_fake_verifier` uses)."""
    def _v(evidence_root: str, pages: Any, **_kw: Any) -> dict:
        summary = {"overall_pass": True, "passed": 1, "total": 1, "failed": 0}
        scorecard_dir = os.path.join(evidence_root, "scorecard")
        os.makedirs(scorecard_dir, exist_ok=True)
        summary_path = os.path.join(scorecard_dir, "verify-summary.json")
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh)
        return {"raw": [], "summary": summary, "raw_path": "", "summary_path": summary_path}
    return _v


def run_fixture_ground_truth(
    evidence_root: str,
    *,
    box_label: Optional[str] = None,
    run_id: Optional[str] = None,
    builder: "Callable[[dict, str], dict] | None" = None,
    verifier: "Callable[..., dict] | None" = None,
    task: Optional[dict] = None,
    env: Optional[dict] = None,
    isdir: Optional[Callable[[str], bool]] = None,
) -> dict:
    """Drive `v2_dispatcher.dispatch_one()` (imported LAZILY — see module
    docstring) through ONE fixture build and assemble a receipt in the exact
    `GROUND_TRUTH_REQUIRED_FIELDS` shape `compare_ground_truth()` consumes.

    `fab_qc_score` / `fab_qc_gate` are an HONEST FIXTURE PLACEHOLDER (the
    default fixture builder/verifier never run a real FAB-QC pass) — the
    receipt's own `fab_qc_note` says so explicitly, never silently presented
    as a genuine quality verdict. A real live run replaces `builder`/
    `verifier` with `ghl_survey_builder`/`ghl_verify` (real FAB-QC scoring
    included) against a designated GHL test location.
    """
    import uuid

    # Lazy — see module docstring: keeps validate/compare dependency-free.
    _TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
    if _TOOLS_DIR not in sys.path:
        sys.path.insert(0, _TOOLS_DIR)
    import browser_manager as bm  # noqa: E402
    import v2_dispatcher as disp  # noqa: E402

    _run_id = run_id or f"gt-{uuid.uuid4().hex[:12]}"
    _task = task if task is not None else {
        "id": f"env-matrix-ground-truth-{_run_id}",
        "brand": "Fictional Ground-Truth Co",
        "location_id": "LOCATIONgroundtruth0",
        "brief": "B-U15 item 2 fixture ground-truth build",
    }
    _builder = builder if builder is not None else _default_fixture_builder()
    _verifier = verifier if verifier is not None else _default_fixture_verifier()

    result = disp.dispatch_one(_task, evidence_root, builder=_builder, verifier=_verifier)

    receipts_total = 0
    if os.path.isdir(evidence_root):
        for _root, _dirs, files in os.walk(evidence_root):
            receipts_total += sum(1 for f in files if f.endswith(".json"))

    dispatch_ok = result.state == "verified"
    build_ok = result.state != "FAILED"
    # NOTE: v2_dispatcher.dispatch_one() already flattens the verifier's
    # return value onto DispatchResult.verify (it extracts `verify_out["summary"]`
    # internally before constructing the result — see dispatch_one's own
    # `summary = verify_out["summary"] if ... else verify_out` line), so
    # `result.verify` IS the summary dict directly; it has no further nested
    # "summary" key to unwrap.
    verify_passed = bool((result.verify or {}).get("overall_pass"))

    return {
        "box_label": box_label,
        "platform": sys.platform,
        "durable_root": bm.durable_root(env=env, isdir=isdir),
        "is_vps": bm.is_vps(env=env, isdir=isdir),
        "supervisor": bm.supervisor(env=env),
        "run_id": _run_id,
        "dispatch_ok": dispatch_ok,
        "build_ok": build_ok,
        "verify_passed": verify_passed,
        "fab_qc_score": 9.0 if verify_passed else 0.0,
        "fab_qc_gate": "PASS" if verify_passed else "FAIL",
        "fab_qc_note": (
            "FIXTURE PLACEHOLDER — the offline fixture build never runs a real "
            "FAB-QC pass; this field is a deterministic stand-in, never a "
            "genuine quality verdict. A live run (real builder/verifier "
            "injected) replaces this with shared-utils/fab_qc.py's real score."
        ),
        "receipts_total": receipts_total,
        "dispatch_state": result.state,
        "dispatch_reason": result.reason,
        "evidence_root": evidence_root,
        "live": False,
        "ts": _now(),
    }


def ground_truth_receipt_path(evidence_root: str) -> str:
    return os.path.join(evidence_root, "routing", "env-matrix-ground-truth-receipt.json")


def write_ground_truth_receipt(evidence_root: str, receipt: dict) -> str:
    path = ground_truth_receipt_path(evidence_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
    os.replace(tmp_path, path)
    return path


# ---------------------------------------------------------------------------
# Self-test — no network, no live boxes (fixture receipts only)
# ---------------------------------------------------------------------------
def _selftest() -> int:
    errors: List[str] = []

    def _fixture(**overrides) -> dict:
        base = {
            "box_label": "fixture-mac",
            "platform": "darwin",
            "durable_root": "/Users/fixture/.openclaw",
            "is_vps": False,
            "supervisor": "launchd",
            "run_id": "gt-fixture-1",
            "dispatch_ok": True,
            "build_ok": True,
            "verify_passed": True,
            "fab_qc_score": 9.2,
            "fab_qc_gate": "PASS",
            "receipts_total": 5,
        }
        base.update(overrides)
        return base

    mac = _fixture()
    vps = _fixture(
        box_label="fixture-vps", platform="linux",
        durable_root="/data/.openclaw", is_vps=True, supervisor="pm2-or-systemd",
        run_id="gt-fixture-2",
    )

    # 1. Well-formed matching receipts -> overall pass, every check passes.
    result = compare_ground_truth(mac, vps)
    if not result["pass"]:
        errors.append(f"matching mac+vps receipts should compare pass=True: {result}")
    if not all(c["pass"] for c in result["checks"]):
        errors.append(f"expected all checks to pass on a clean fixture pair: {result['checks']}")

    # 2. assert_ground_truth_parity does not raise on a clean pair.
    try:
        assert_ground_truth_parity(mac, vps)
    except GroundTruthMismatch as exc:
        errors.append(f"assert_ground_truth_parity should not raise on a clean pair: {exc}")

    # 3. validate_ground_truth_receipt: missing field surfaces by name.
    broken = dict(mac)
    del broken["fab_qc_score"]
    problems = validate_ground_truth_receipt(broken)
    if not any("fab_qc_score" in p for p in problems):
        errors.append(f"missing fab_qc_score should be reported: {problems}")

    # 4. compare_ground_truth fails closed (never KeyErrors) on a malformed receipt.
    result = compare_ground_truth(broken, vps)
    if result["pass"] is not False:
        errors.append(f"malformed mac receipt should fail the comparison, got {result}")

    # 5. Swapped is_vps (Mac box reporting is_vps=True) is caught, not silently passed.
    bad_mac = _fixture(is_vps=True)
    result = compare_ground_truth(bad_mac, vps)
    if result["pass"] is not False:
        errors.append("a Mac receipt claiming is_vps=True should fail GT-03")
    gt03 = next(c for c in result["checks"] if c["check"] == "GT-03:mac_is_not_vps")
    if gt03["pass"] is not False:
        errors.append(f"GT-03 should specifically fail: {gt03}")

    # 6. Wrong durable_root convention on the VPS side is caught.
    bad_vps = _fixture(box_label="bad-vps", platform="linux", is_vps=True,
                        supervisor="pm2-or-systemd", durable_root="/Users/wrong/.openclaw")
    result = compare_ground_truth(mac, bad_vps)
    if result["pass"] is not False:
        errors.append("a VPS receipt with a Mac-shaped durable_root should fail GT-06")

    # 7. A sub-threshold FAB-QC score fails the parity check (the standing 8.5 gate).
    low_score_vps = _fixture(box_label="low-vps", platform="linux", is_vps=True,
                              supervisor="pm2-or-systemd", durable_root="/data/.openclaw",
                              fab_qc_score=7.9, fab_qc_gate="FAIL")
    result = compare_ground_truth(mac, low_score_vps)
    if result["pass"] is not False:
        errors.append("a sub-8.5 fab_qc_score should fail the parity comparison")
    try:
        assert_ground_truth_parity(mac, low_score_vps)
        errors.append("assert_ground_truth_parity must raise on a sub-8.5 score")
    except GroundTruthMismatch:
        pass

    # 8. Zero receipts_total (vacuous "pass") is caught (F6 discipline).
    vacuous_vps = _fixture(box_label="vacuous-vps", platform="linux", is_vps=True,
                            supervisor="pm2-or-systemd", durable_root="/data/.openclaw",
                            receipts_total=0)
    result = compare_ground_truth(mac, vacuous_vps)
    if result["pass"] is not False:
        errors.append("receipts_total=0 should fail the parity comparison (F6: no receipt = not created)")

    # 9. A non-dict receipt fails closed with a clear message, never a crash.
    problems = validate_ground_truth_receipt(["not", "a", "dict"])
    if not problems:
        errors.append("a non-dict receipt should report at least one problem")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — ground-truth receipt schema + comparator verified (no network, no live boxes)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_env_matrix_ground_truth",
        description="B-U15 item 2: first-hour ground-truth receipt schema + Mac-vs-VPS comparator.",
    )
    p.add_argument("--selftest", action="store_true", help="Run the no-network self-test and exit.")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("validate", help="Validate one ground-truth receipt file.")
    sp.add_argument("receipt_path")

    sp2 = sub.add_parser("compare", help="Compare a Mac and a VPS ground-truth receipt file.")
    sp2.add_argument("mac_receipt_path")
    sp2.add_argument("vps_receipt_path")

    sp3 = sub.add_parser(
        "run",
        help="OFFLINE/FIXTURE: run one dispatch->build->verify fixture cycle on THIS "
             "box and write a compare()-ready receipt (the operator-run --live leg "
             "swaps in a real builder/verifier — see module docstring).",
    )
    sp3.add_argument("--evidence-root", required=True)
    sp3.add_argument("--box-label", default=None)
    sp3.add_argument("--run-id", default=None)

    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.cmd == "run":
        receipt = run_fixture_ground_truth(
            args.evidence_root, box_label=args.box_label, run_id=args.run_id,
        )
        out = write_ground_truth_receipt(args.evidence_root, receipt)
        print(json.dumps(receipt, indent=2))
        print(f"[ghl_env_matrix_ground_truth] receipt written: {out}", file=sys.stderr)
        return 0 if (receipt["dispatch_ok"] and receipt["build_ok"] and receipt["verify_passed"]) else 1

    if args.cmd == "validate":
        with open(args.receipt_path, encoding="utf-8") as fh:
            receipt = json.load(fh)
        problems = validate_ground_truth_receipt(receipt)
        if problems:
            for prob in problems:
                print(f"  INVALID: {prob}", file=sys.stderr)
            return 1
        print("valid")
        return 0

    if args.cmd == "compare":
        with open(args.mac_receipt_path, encoding="utf-8") as fh:
            mac = json.load(fh)
        with open(args.vps_receipt_path, encoding="utf-8") as fh:
            vps = json.load(fh)
        result = compare_ground_truth(mac, vps)
        print(json.dumps(result, indent=2))
        return 0 if result["pass"] else 1

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
