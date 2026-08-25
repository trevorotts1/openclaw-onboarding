#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: NO-ANTHROPIC GATE (fail-closed)
# -----------------------------------------------------------------------------
# ⛔ BINDING: the shipped skill running on a CLIENT box NEVER uses Anthropic models.
# Every model id recorded in RUN-LEDGER.json is checked against /anthropic|claude/i;
# any match fails. The run env is also checked for operator credential names.
#
#   AF-BK-ANTHROPIC — a RUN-LEDGER model id matches /anthropic|claude/i, or an
#                     operator credential name appears in the run env.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_noanthropic.py <RUN-LEDGER.json> [--env-keys k1,k2] [--json] | --self-test
# =============================================================================
"""Fail-closed no-Anthropic model-id gate (Skill 53)."""

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
    structure — not just keys named 'model'. A model id can hide under any alias
    (model_name / modelId / llm / engine / model_used / preflight_tier_map …), so
    the deep scan tests every string value against the ban regex."""
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
    found_any = False
    for jpath, mid in _iter_string_leaves(ledger):
        found_any = True
        if c._ANTHROPIC_RE.search(mid):
            r.fail(AF_ANTHROPIC, "/anthropic|claude/i string %r at %s (client boxes never run "
                   "Anthropic)" % (mid, jpath))
    if not found_any:
        r.note("ledger has no string values (nothing to reject)")
    # operator credential names in the run env
    env = env if env is not None else dict(os.environ)
    for k in env:
        up = k.upper()
        if any(hint in up for hint in _OPERATOR_CRED_HINTS):
            r.fail(AF_ANTHROPIC, "operator credential name %r present in the run env "
                   "(clients use their OWN keys, never the operator's)" % k)
    if r.passed:
        r.note("no /anthropic|claude/i model id; no operator credential name in env")
    return r


def prove(ledger_path, env_keys=None, as_json=False) -> int:
    env = {k: "1" for k in env_keys} if env_keys is not None else {}
    return evaluate(c.read_json(ledger_path), env=env).emit(as_json)


def self_test() -> int:
    good = {"stages": [{"stage": "13-create-outline", "model": "ollama-cloud/gpt-oss-120b"},
                       {"stage": "10-suggested-titles", "resolved_model": "openrouter/some-open-model"}]}
    checks = []
    checks.append(("clean ledger PASSES", evaluate(good, env={}).passed))
    bad = {"stages": [{"stage": "13-create-outline", "model": "anthropic/claude-opus-4"}]}
    checks.append(("anthropic/claude-opus-4 AUTOFAILs AF-BK-ANTHROPIC",
                   any(cd == AF_ANTHROPIC for cd, _ in evaluate(bad, env={}).violations)))
    bad2 = {"stages": [{"stage": "x", "resolved_model": "claude-sonnet-4"}]}
    checks.append(("bare claude-sonnet-4 AUTOFAILs AF-BK-ANTHROPIC",
                   any(cd == AF_ANTHROPIC for cd, _ in evaluate(bad2, env={}).violations)))
    checks.append(("operator cred name in env AUTOFAILs AF-BK-ANTHROPIC",
                   any(cd == AF_ANTHROPIC for cd, _ in
                       evaluate(good, env={"OPERATOR_OPENROUTER_KEY": "x"}).violations)))
    checks.append(("model as LIST value [\"anthropic/claude-opus-4\"] AUTOFAILs",
                   any(cd == AF_ANTHROPIC for cd, _ in evaluate(
                       {"stages": [{"model": ["anthropic/claude-opus-4"]}]}, env={}).violations)))
    checks.append(("NESTED dict model {\"id\": \"anthropic/x\"} AUTOFAILs",
                   any(cd == AF_ANTHROPIC for cd, _ in evaluate(
                       {"stages": [{"model": {"id": "anthropic/claude-x"}}]}, env={}).violations)))
    alias_bad = {"stages": [{"stage": "x", "model_name": "claude-haiku"},
                            {"stage": "y", "modelId": "anthropic/eu.x"},
                            {"stage": "z", "llm": "claude-instant"},
                            {"stage": "w", "engine": "us.anthropic.claude-3"},
                            {"stage": "v", "model_used": "claude-fable"}]}
    checks.append(("alias keys model_name/modelId/llm/engine/model_used ALL AUTOFAILs",
                   all(any(cd == AF_ANTHROPIC for cd, _ in evaluate(
                       {"stages": [s]}, env={}).violations) for s in alias_bad["stages"])))
    tier_bad = {"preflight_tier_map": {"thinking": "claude-opus-5"}}
    checks.append(("preflight_tier_map value claude-opus-5 AUTOFAILs",
                   any(cd == AF_ANTHROPIC for cd, _ in evaluate(tier_bad, env={}).violations)))
    checks.append(("ANTHROPIC_API_KEY in env does NOT autofail (host-side agent-harness var, "
                   "not a client-run credential)",
                   not any(cd == AF_ANTHROPIC for cd, _ in
                           evaluate(good, env={"ANTHROPIC_API_KEY": "x"}).violations)))
    checks.append(("OPERATOR_ cred name in env AUTOFAILs AF-BK-ANTHROPIC",
                   any(cd == AF_ANTHROPIC for cd, _ in
                       evaluate(good, env={"OPERATOR_OPENROUTER_KEY": "x"}).violations)))
    return c.selftest_report("prove_bw_noanthropic", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer no-Anthropic gate (Skill 53).")
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
