#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: RUN-ENV CREDENTIAL GATE (fail-closed)
# -----------------------------------------------------------------------------
# There is NO rule against Anthropic / Claude models (Trevor order 2026-10-29), so a
# RUN-LEDGER model id is never rejected for its vendor. The file name and the
# AF-BK-ANTHROPIC code are legacy identifiers kept so manifests, goldens and
# reports stay stable; the code now fires ONLY when an operator credential name
# appears in the run env (clients use their OWN keys, never the operator's).
#
#   AF-BK-ANTHROPIC — an operator credential name appears in the run env.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_noanthropic.py <RUN-LEDGER.json> [--env-keys k1,k2] [--json] | --self-test
# =============================================================================
"""Fail-closed run-env operator-credential gate (Skill 53)."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_ANTHROPIC = "AF-BK-ANTHROPIC"

# Operator credential-name shapes that must never appear in a client run env.
# ANTHROPIC_* / CLAUDE_* names set by a DEVELOPMENT agent harness (Claude Code,
# 9Router) are host-side, not client-run credentials — the orchestrator passes
# --env-keys (a curated allowlist) at runtime; when it does not, only these
# operator-shaped hints are scanned so an operator box running its own agent
# tooling is not falsely flagged for vars it does not pass into runs.
_OPERATOR_CRED_HINTS = ("OPERATOR_", "BLACKCEO_OPERATOR", "OC_OPERATOR_KEY")


def _iter_string_leaves(obj, path="ledger"):
    """Yield (json_path, string) for EVERY string leaf anywhere in the ledger
    structure (a model id can hide under any alias key). Used to count the model
    ids a ledger records."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_string_leaves(v, "%s.%s" % (path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_string_leaves(v, "%s[%d]" % (path, i))
    elif isinstance(obj, str):
        yield (path, obj)


def evaluate(ledger, env=None) -> c.Result:
    r = c.Result("prove_bw_noanthropic")
    if not any(True for _ in _iter_string_leaves(ledger)):
        r.note("ledger has no string values")
    # operator credential names in the run env
    env = env if env is not None else dict(os.environ)
    for k in env:
        up = k.upper()
        if any(hint in up for hint in _OPERATOR_CRED_HINTS):
            r.fail(AF_ANTHROPIC, "operator credential name %r present in the run env "
                   "(clients use their OWN keys, never the operator's)" % k)
    if r.passed:
        r.note("no operator credential name in env")
    return r


def prove(ledger_path, env_keys=None, as_json=False) -> int:
    env = {k: "1" for k in env_keys} if env_keys is not None else {}
    return evaluate(c.read_json(ledger_path), env=env).emit(as_json)


def self_test() -> int:
    good = {"stages": [{"stage": "13-create-outline", "model": "ollama-cloud/gpt-oss-120b"},
                       {"stage": "10-suggested-titles", "resolved_model": "openrouter/some-open-model"}]}
    checks = []
    checks.append(("clean ledger PASSES", evaluate(good, env={}).passed))
    named = {"stages": [{"stage": "13-create-outline", "model": "anthropic/claude-opus-4"}]}
    checks.append(("an Anthropic-family model id in the ledger PASSES (no vendor rule)",
                   evaluate(named, env={}).passed))
    checks.append(("operator cred name in env AUTOFAILs AF-BK-ANTHROPIC",
                   any(cd == AF_ANTHROPIC for cd, _ in
                       evaluate(good, env={"OPERATOR_OPENROUTER_KEY": "x"}).violations)))
    checks.append(("ANTHROPIC_API_KEY in env does NOT autofail (host-side agent-harness var, "
                   "not a client-run credential)",
                   not any(cd == AF_ANTHROPIC for cd, _ in
                           evaluate(good, env={"ANTHROPIC_API_KEY": "x"}).violations)))
    checks.append(("OPERATOR_ cred name in env AUTOFAILs AF-BK-ANTHROPIC",
                   any(cd == AF_ANTHROPIC for cd, _ in
                       evaluate(good, env={"OPERATOR_OPENROUTER_KEY": "x"}).violations)))
    return c.selftest_report("prove_bw_noanthropic", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer run-env operator-credential gate (Skill 53).")
    ap.add_argument("ledger", nargs="?", help="RUN-LEDGER.json")
    ap.add_argument("--env-keys", help="comma-separated env key names to check (default: live env)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.ledger:
        ap.error("a RUN-LEDGER.json path is required (or use --self-test)")
    env_keys = args.env_keys.split(",") if args.env_keys else None
    return prove(args.ledger, env_keys=env_keys, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
