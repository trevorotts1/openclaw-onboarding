#!/usr/bin/env python3
"""ghl_gate.py — UN-FAKEABLE build verdict reader (Skill 06, B2 fix).

WHY THIS EXISTS
---------------
The fabricated PASS was possible because:
  (a) the gate read raw HTTP shell / stored bytes, not the rendered DOM,
  (b) a 500 was prose-relabeled 'API difference' in a different file,
  (c) the fetcher/verifier injection seam let a stub return all-PASS,
  (d) hand-written ledger/.md could stand in for the verdict.

This module seals (d) structurally: it is a VERDICT READER that reads ONLY
machine-written JSON files and NEVER reads any .md, ledger.json, or prose —
the fabrication channel is simply not an input.  It re-runs the consistency
guard and re-checks every artifact hash before returning a verdict.

USAGE
-----
As a CLI:
    python3 ghl_gate.py verdict  <run_dir>    # print verdict JSON, exit 0=PASS/1=FAIL
    python3 ghl_gate.py require-pass <run_dir>  # exit 0=PASS / non-zero=FAIL

As a library (from v2_dispatcher or any orchestrator):
    from ghl_gate import require_pass
    rc = require_pass(evidence_root)   # 0 = PASS; non-zero = FAIL/MOCK/TAMPERED

WHAT IT READS
-------------
  * scorecard/verify-summary.json    — the summary written by ghl_verify.verify_all
  * logs/final-preview-verify.json   — the raw per-page results (source of truth)
  * scorecard/render-manifest.json   — artifact sha256 binding

WHAT IT NEVER READS
-------------------
  * Any .md file (run-funnel.md, VERIFY-opus-final.md, etc.)
  * Any ledger.json
  * Any prose summary / hand-written report

EXIT CODES
----------
  0  — all checks pass (verdict is LIVE PASS, no tampering)
  1  — overall_pass is False (real build failure)
  2  — trust == 'MOCK' or MOCK-DO-NOT-SHIP sentinel present
  3  — VerifyContradiction (counts mismatch, fabricated row, artifact hash mismatch)
  4  — missing required file(s)
  5  — writer/run_nonce invalid (summary not written by ghl_verify.verify_all)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_verify  # noqa: E402

# The module identity that must appear in any valid summary.
_EXPECTED_WRITER = ghl_verify._WRITER_ID  # "ghl_verify.verify_all"

# Public sentinel — also exported so tests can use getattr(gate, 'MOCK_DO_NOT_SHIP').
MOCK_DO_NOT_SHIP = "MOCK-DO-NOT-SHIP"

# Trust values that are never shippable.
_NON_SHIPPABLE_TRUST = frozenset({"MOCK", MOCK_DO_NOT_SHIP})


class GateVerdictError(RuntimeError):
    """Raised by ``require_pass`` when the gate cannot be passed.  The exit code
    is embedded as ``self.rc`` so the CLI can emit the right exit code."""
    def __init__(self, msg: str, rc: int = 1) -> None:
        super().__init__(msg)
        self.rc = rc


def _read_json(path: str, label: str) -> dict | list:
    """Read a JSON file, raising ``GateVerdictError`` (exit 4) if missing."""
    if not os.path.isfile(path):
        raise GateVerdictError(
            f"GATE FAIL: required file missing: {path!r} ({label})", rc=4
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _gate_verdict(evidence_root: str) -> dict:
    """Read and re-validate the verdict for an evidence tree.

    Returns a dict with at least:
      ``ok`` (bool), ``overall_pass`` (bool), ``trust`` (str),
      ``run_nonce`` (str), ``writer`` (str), ``checks`` (list of check names
      that passed), ``rc`` (int — the CLI exit code this verdict maps to).

    Raises ``GateVerdictError`` on any integrity failure.  Never reads .md /
    ledger.json / prose.
    """
    # ── Load the three machine-written files ──────────────────────────────────
    summary_path = os.path.join(evidence_root, ghl_verify.SUMMARY_REL)
    raw_path = os.path.join(evidence_root, ghl_verify.RAW_REL)
    manifest_path = os.path.join(evidence_root, ghl_verify.RENDER_MANIFEST_REL)
    mock_sentinel = os.path.join(evidence_root, ghl_verify.MOCK_SENTINEL_REL)

    summary = _read_json(summary_path, "scorecard/verify-summary.json")
    if not isinstance(summary, dict):
        raise GateVerdictError("GATE FAIL: verify-summary.json is not a JSON object", rc=4)

    raw = _read_json(raw_path, "logs/final-preview-verify.json")
    if not isinstance(raw, list):
        raise GateVerdictError("GATE FAIL: final-preview-verify.json is not a JSON list", rc=4)

    # render-manifest.json is optional but checked when present.
    render_manifest: dict | None = None
    if os.path.isfile(manifest_path):
        rm = _read_json(manifest_path, "scorecard/render-manifest.json")
        render_manifest = rm if isinstance(rm, dict) else None

    checks_passed: list[str] = []

    # ── Check 1: writer identity ───────────────────────────────────────────────
    writer = summary.get("writer", "")
    run_nonce = summary.get("run_nonce", "")
    if writer != _EXPECTED_WRITER:
        raise GateVerdictError(
            f"GATE FAIL: summary.writer={writer!r} does not match expected "
            f"{_EXPECTED_WRITER!r}.  This summary was NOT written by "
            "ghl_verify.verify_all — it may be hand-written or produced by a "
            "different tool.", rc=5
        )
    if not run_nonce:
        raise GateVerdictError(
            "GATE FAIL: summary.run_nonce is missing or empty.  A valid "
            "ghl_verify.verify_all summary always carries a UUID run_nonce.", rc=5
        )
    checks_passed.append("writer_identity")

    # ── Check 2: trust must not be a mock/non-shippable value ────────────────────
    trust = summary.get("trust", "LIVE")
    if trust in _NON_SHIPPABLE_TRUST or os.path.isfile(mock_sentinel):
        raise GateVerdictError(
            f"GATE FAIL: this evidence tree carries trust={trust!r} or a "
            "MOCK-DO-NOT-SHIP sentinel.  A mock verdict cannot be accepted as a "
            "shippable build pass.", rc=2
        )
    checks_passed.append("trust_not_mock")

    # ── Check 3: raw_sha256 binding ────────────────────────────────────────────
    embedded_raw_sha = summary.get("raw_sha256", "")
    if embedded_raw_sha:
        import hashlib
        with open(raw_path, "rb") as f:
            actual_raw_sha = hashlib.sha256(f.read()).hexdigest()
        if actual_raw_sha != embedded_raw_sha:
            raise GateVerdictError(
                f"GATE FAIL: raw_sha256 mismatch.  summary.raw_sha256="
                f"{embedded_raw_sha!r}, actual sha256 of "
                f"final-preview-verify.json={actual_raw_sha!r}.  The raw log "
                "has been modified after the summary was written.", rc=3
            )
    checks_passed.append("raw_sha256_binding")

    # ── Check 4: consistency guard (re-derive from raw) ────────────────────────
    try:
        ghl_verify.assert_consistent(summary, raw, render_manifest=render_manifest)
    except ghl_verify.VerifyContradiction as e:
        raise GateVerdictError(
            f"GATE FAIL (VerifyContradiction): {e}", rc=3
        ) from e
    checks_passed.append("consistency_guard")

    # ── Check 5: no forbidden override strings ─────────────────────────────────
    # These strings were used to rationalize failures as non-failures.  Their
    # presence anywhere in the summary JSON is a hard reject.
    forbidden_phrases = ("API difference", "type difference", "harmless")
    summary_text = json.dumps(summary)
    for phrase in forbidden_phrases:
        if phrase in summary_text:
            raise GateVerdictError(
                f"GATE FAIL: forbidden phrase {phrase!r} found in summary JSON. "
                "This phrase is associated with overriding real failures.  The "
                "summary is rejected.", rc=3
            )
    checks_passed.append("no_forbidden_overrides")

    # ── Determine final verdict ────────────────────────────────────────────────
    overall_pass = bool(summary.get("overall_pass"))
    rc = 0 if overall_pass else 1

    return {
        "ok": overall_pass,
        "overall_pass": overall_pass,
        "trust": trust,
        "run_nonce": run_nonce,
        "writer": writer,
        "passed": summary.get("passed"),
        "total": summary.get("total"),
        "failed": summary.get("failed"),
        "checks": checks_passed,
        "summary_path": summary_path,
        "raw_path": raw_path,
        "manifest_path": manifest_path if render_manifest is not None else "",
        "rc": rc,
    }


def require_pass(evidence_root: str) -> int:
    """Re-validate the verdict for ``evidence_root`` and return an exit code.

    Returns 0 IFF all checks pass AND overall_pass is True.  Returns non-zero
    on any failure or integrity violation.  Never reads .md / ledger / prose.

    Designed for programmatic use from ``v2_dispatcher.dispatch_one`` — the
    building->verified transition is gated on this returning 0.
    """
    try:
        v = _gate_verdict(evidence_root)
        return v["rc"]
    except GateVerdictError as e:
        return e.rc
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"ghl_gate.require_pass unexpected error: {exc}\n")
        return 4


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ghl_gate",
        description=(
            "UN-FAKEABLE build verdict reader (Skill 06 B2 fix).  Reads ONLY "
            "machine-written JSON files; never reads .md, ledger.json, or prose."
        ),
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("verdict", help="print the gate verdict as JSON")
    p1.add_argument("run_dir", help="evidence root (contains scorecard/ logs/)")

    p2 = sub.add_parser(
        "require-pass",
        help="exit 0 if the verdict is a live PASS; non-zero otherwise",
    )
    p2.add_argument("run_dir")

    args = ap.parse_args(argv)

    try:
        v = _gate_verdict(args.run_dir)
    except GateVerdictError as e:
        sys.stderr.write(f"GATE FAIL: {e}\n")
        return e.rc
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"ghl_gate unexpected error: {exc}\n")
        return 4

    if args.cmd == "verdict":
        print(json.dumps(v, indent=2))
        return v["rc"]

    if args.cmd == "require-pass":
        if v["rc"] == 0:
            print(json.dumps({
                "gate": "PASS",
                "overall_pass": v["overall_pass"],
                "trust": v["trust"],
                "passed": v["passed"],
                "total": v["total"],
                "run_nonce": v["run_nonce"],
                "checks": v["checks"],
            }, indent=2))
        else:
            sys.stderr.write(
                f"GATE FAIL (rc={v['rc']}): overall_pass={v['overall_pass']}, "
                f"trust={v['trust']!r}, checks={v['checks']}\n"
            )
        return v["rc"]

    return 0


if __name__ == "__main__":
    sys.exit(main())
