#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: RUNTIME BUILD CHECK  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# The runtime half of the NON-Anthropic build-fix (PRD §6 G-NOANTHROPIC, §7.3).
# The source workflow pinned every extracted call to Anthropic model ids "as
# shipped in source". Those ids are capability TIERS, not prescriptions: at
# client runtime the pipeline resolves each tier to the client's OWN strongest
# NON-Anthropic model. This gate reads the run ledger and hard-fails ANY model
# id that matches /anthropic|claude/i, so an Anthropic id can never reach a
# client box — and enforces the bounded rewrite budget.
#
#   AF-AW-ANTHROPIC            — a model id in RUN-LEDGER.json matches /anthropic|claude/i,
#                                OR an operator credential name is present in the run env.
#   AF-AW-REWRITE-BUDGET       — rewrite_count exceeds the max (2) — runaway rework.
#   AF-AW-PROVENANCE-MISSING   — the ledger records NO resolved model id (empty/absent
#                                stages); model provenance is required (fail-closed, so
#                                the no-Anthropic gate can never pass vacuously).
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: aw_build_check.py <RUN-LEDGER.json> [--json] | aw_build_check.py --self-test
# =============================================================================
"""Fail-closed runtime build check (no-Anthropic + rewrite budget) for Skill 54."""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _aw_common as c  # noqa: E402

AF_ANTHROPIC = "AF-AW-ANTHROPIC"
AF_REWRITE_BUDGET = "AF-AW-REWRITE-BUDGET"
AF_PROVENANCE_MISSING = "AF-AW-PROVENANCE-MISSING"
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"

REWRITE_MAX = 2
_ANTHROPIC_RE = re.compile(r"anthropic|claude", re.I)
# operator credential env names that must NEVER be present on a client run
_OPERATOR_ENV_NAMES = ("OPERATOR_ANTHROPIC_API_KEY", "OPERATOR_API_KEY", "ANTHROPIC_ADMIN_KEY")


def _model_ids(ledger: dict) -> list:
    ids = []
    for stage in ledger.get("stages", []) if isinstance(ledger, dict) else []:
        if isinstance(stage, dict):
            for key in ("model", "model_id", "resolved_model"):
                v = stage.get(key)
                if v:
                    ids.append((stage.get("stage_id", "?"), str(v)))
    return ids


def evaluate(ledger: dict, env=None) -> c.Result:
    env = os.environ if env is None else env
    r = c.Result("aw_build_check")
    ids = _model_ids(ledger)
    # Model-sovereignty is FAIL-CLOSED on missing provenance: an empty ledger (no
    # stages / no resolved model ids) is not "clean" — it is UNPROVEN, so the
    # no-Anthropic scan would vacuously pass on a run that recorded nothing. A run
    # that certifies MUST carry the model provenance it was authored on.
    # (Mirrors Skill-57 AF-SM-PROVENANCE-MISSING and Skill-53's ledger-required fix.)
    if not ids:
        r.fail(AF_PROVENANCE_MISSING, "RUN-LEDGER.json records no resolved model id "
               "(empty/absent stages) — model provenance is REQUIRED; the no-Anthropic "
               "gate cannot pass vacuously on an unproven run")
    for stage_id, model in ids:
        if _ANTHROPIC_RE.search(model):
            r.fail(AF_ANTHROPIC, "stage %s resolved to an Anthropic model id %r — client "
                   "runtime must use the client's strongest NON-Anthropic model" % (stage_id, model))
    for name in _OPERATOR_ENV_NAMES:
        if str(env.get(name, "")).strip():
            r.fail(AF_ANTHROPIC, "operator credential %r present in the run env — a client run "
                   "uses the client's OWN keys only" % name)
    if r.passed and ids:
        r.note("%d resolved model id(s), none Anthropic" % len(ids))

    rc = ledger.get("rewrite_count", 0) if isinstance(ledger, dict) else 0
    try:
        rc = int(rc)
    except (TypeError, ValueError):
        rc = 0
    if rc > REWRITE_MAX:
        r.fail(AF_REWRITE_BUDGET, "rewrite_count %d exceeds the max %d (bounded rework loop)"
               % (rc, REWRITE_MAX))
    else:
        r.note("rewrite_count %d within budget (<=%d)" % (rc, REWRITE_MAX))
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_json(path)).emit(as_json)


def self_test() -> int:
    checks = []
    g = c.read_json(_FIX / "golden" / "RUN-LEDGER.json")
    checks.append(("golden ledger PASS (non-Anthropic, in budget)", evaluate(g).passed))

    a = evaluate(c.read_json(_FIX / "attack" / "ledger_anthropic.json"))
    checks.append(("anthropic model id ledger AUTOFAILs AF-AW-ANTHROPIC",
                   any(code == AF_ANTHROPIC for code, _ in a.violations)))

    b = evaluate(c.read_json(_FIX / "attack" / "ledger_rewrite_over_budget.json"))
    checks.append(("over-budget rewrite ledger AUTOFAILs AF-AW-REWRITE-BUDGET",
                   any(code == AF_REWRITE_BUDGET for code, _ in b.violations)))

    p = evaluate(c.read_json(_FIX / "attack" / "ledger_no_provenance.json"))
    checks.append(("provenance-missing ledger AUTOFAILs AF-AW-PROVENANCE-MISSING",
                   any(code == AF_PROVENANCE_MISSING for code, _ in p.violations)))
    return c.selftest_report("aw_build_check", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Anthology Writer runtime build check (Skill 54).")
    ap.add_argument("path", nargs="?", help="RUN-LEDGER.json to prove")
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
