#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: INTAKE GATE  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# Enforces PRD §3.3: the four fields the pipeline actually consumes must be
# present and non-empty BEFORE any tone/title/chapter is authored. Whitespace-
# only counts as missing. A self-attested "complete" flag is never trusted — we
# check the ledger's real values.
#
# It also enforces the credential rule (D7): a client's provider keys are
# resolved per box from the client's OWN OpenClaw config, never taken through
# intake. Any credential-shaped intake key fails closed.
#
#   AF-AW-INTAKE-MISSING    — any of anthology_title / first_name / last_name /
#                             chapter_premise missing, empty, or whitespace.
#   AF-AW-INTAKE-CREDENTIAL — an intake key looks like a secret (api_key, token,
#                             openrouter, password, ...). Keys never ride intake.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_aw_intake.py <intake.json> [--json] | prove_aw_intake.py --self-test
# =============================================================================
"""Fail-closed intake gate for the Anthology Writer (Skill 54)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _aw_common as c  # noqa: E402

AF_INTAKE_MISSING = "AF-AW-INTAKE-MISSING"
AF_INTAKE_CREDENTIAL = "AF-AW-INTAKE-CREDENTIAL"
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"


def evaluate(intake: dict) -> c.Result:
    r = c.Result("prove_aw_intake")
    if not isinstance(intake, dict):
        r.fail(AF_INTAKE_MISSING, "intake is not a JSON object")
        return r
    for field in c.INTAKE_REQUIRED:
        val = intake.get(field)
        if val is None or not str(val).strip():
            r.fail(AF_INTAKE_MISSING, "required field %r is missing/empty/whitespace" % field)
    cred = c.credential_shaped_keys(intake)
    for k in cred:
        r.fail(AF_INTAKE_CREDENTIAL,
               "credential-shaped intake key %r is forbidden — client provider keys are "
               "resolved per box from the client's own config, never via intake" % k)
    if r.passed:
        r.note("all 4 required intake fields present: %s" % ", ".join(c.INTAKE_REQUIRED))
        stories = c.story_phrases(intake)
        r.note("personal_stories: %d real anchor(s) to place (N/A slots skipped)" % len(stories))
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_json(path)).emit(as_json)


def self_test() -> int:
    checks = []
    g = _FIX / "golden" / "intake.json"
    checks.append(("golden intake PASSes", evaluate(c.read_json(g)).passed))

    a = evaluate(c.read_json(_FIX / "attack" / "intake_missing.json"))
    checks.append(("missing-field intake AUTOFAILs", not a.passed))
    checks.append(("...with AF-AW-INTAKE-MISSING",
                   any(code == AF_INTAKE_MISSING for code, _ in a.violations)))

    cr = evaluate(c.read_json(_FIX / "attack" / "intake_credential.json"))
    checks.append(("credential-shaped intake AUTOFAILs", not cr.passed))
    checks.append(("...with AF-AW-INTAKE-CREDENTIAL",
                   any(code == AF_INTAKE_CREDENTIAL for code, _ in cr.violations)))
    return c.selftest_report("prove_aw_intake", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Anthology Writer intake gate (Skill 54).")
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
