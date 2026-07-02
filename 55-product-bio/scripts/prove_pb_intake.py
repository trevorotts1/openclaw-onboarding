#!/usr/bin/env python3
# =============================================================================
# SKILL 55 — PRODUCT BIO :: INTAKE GATE  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# Enforces PRD §3.3: the four fields the IP actually consumes must be present and
# non-empty BEFORE any bio is authored. Whitespace-only counts as missing. The
# optional fields (client_folder_name / email / phone) are captured but never
# required (O7). A self-attested "complete" flag is never trusted — we check the
# ledger's real values.
#
#   AF-PB-INTAKE-MISSING — any of product_name / product_description /
#                          first_name / last_name missing, empty, or whitespace.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_pb_intake.py <intake.json> [--json] | prove_pb_intake.py --self-test
# =============================================================================
"""Fail-closed intake gate for the Product Bio engine (Skill 55)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pb_common as c  # noqa: E402

AF_INTAKE_MISSING = "AF-PB-INTAKE-MISSING"
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"


def evaluate(intake: dict) -> c.Result:
    r = c.Result("prove_pb_intake")
    if not isinstance(intake, dict):
        r.fail(AF_INTAKE_MISSING, "intake is not a JSON object")
        return r
    for field in c.INTAKE_REQUIRED:
        val = intake.get(field)
        if val is None or not str(val).strip():
            r.fail(AF_INTAKE_MISSING, "required field %r is missing/empty/whitespace" % field)
    if r.passed:
        r.note("all 4 required intake fields present: %s" % ", ".join(c.INTAKE_REQUIRED))
        for opt in ("client_folder_name", "email", "phone"):
            if str(intake.get(opt, "")).strip():
                r.note("optional %s captured (handoff parity only)" % opt)
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_json(path)).emit(as_json)


def self_test() -> int:
    checks = []
    g = _FIX / "golden" / "intake.json"
    a = _FIX / "attack" / "intake_missing.json"
    checks.append(("golden intake PASSes", evaluate(c.read_json(g)).passed))
    res = evaluate(c.read_json(a))
    checks.append(("missing-field intake AUTOFAILs", not res.passed))
    checks.append(("...with AF-PB-INTAKE-MISSING",
                   any(code == AF_INTAKE_MISSING for code, _ in res.violations)))
    return c.selftest_report("prove_pb_intake", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Product Bio intake gate (Skill 55).")
    ap.add_argument("path", nargs="?", help="intake.json to prove")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
