#!/usr/bin/env python3
# =============================================================================
# SKILL 48 — FACEBOOK/INSTAGRAM AD GENERATOR :: MODEL-SOVEREIGNTY GATE
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED. Mirrors Skill 49's model-content-receipt
# gate (prove_sf_cert.evaluate_model_receipt): an ad run must RECORD that the
# CLIENT's OWN execution-tier model wrote the ad copy, and Anthropic is
# HARD-BANNED. Before this gate the skill only checked the image-model prefix
# (gpt-image-*) and had NO copy-model sovereignty check at all (SK2-12).
#
#   AF-FBAD-MODEL-TIER        — no model-content-receipt, no resolved model id,
#                               or an authoring tier that is not an execution/
#                               content tier (the client's strongest model must
#                               write the copy, not a cheap/simple tier).
#   AF-FBAD-MODEL-NOANTHROPIC — the authoring model resolves to Anthropic
#                               (provider FIELD anthropic/claude, OR the model id
#                               is an Anthropic/claude shape). Client skills NEVER
#                               use Anthropic models.
#
# The receipt is written by the copy phases (S2 bodies / S3 headlines) into the
# run dir. This gate reads it fail-closed: a missing/unrecorded receipt FAILS —
# "the authoring model was never resolved/recorded" is never an implicit pass.
#
# EXIT: 0 PASS / 2 AUTOFAIL / 3 USAGE-IO.
# USAGE:
#   python3 ad_model_sovereignty.py --receipt FILE [--json]
#   python3 ad_model_sovereignty.py --run-dir DIR [--json]
#   python3 ad_model_sovereignty.py --self-test
# =============================================================================
"""Fail-closed model-sovereignty / no-Anthropic gate for the Facebook Ad Generator."""

import argparse
import json
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_MODEL_TIER = "AF-FBAD-MODEL-TIER"
AF_MODEL_NOANTHROPIC = "AF-FBAD-MODEL-NOANTHROPIC"

# Execution/content-tier slugs the authoring model must resolve to (mirrors
# Skill 49's EXECUTION_TIERS) — NOT a cheap/simple/judge tier.
EXECUTION_TIERS = {"content", "execution", "exec", "strong", "strongest",
                   "authoring", "primary", "tier-a", "tier_a", "a"}
_ANTHROPIC_PROVIDERS = {"anthropic", "claude"}

# Standard receipt locations inside an ad run dir (first hit wins).
_RECEIPT_LOCATIONS = (
    "working/routing/model-content-receipt.json",
    "routing/model-content-receipt.json",
    "working/checkpoints/model-content-receipt.json",
)


def evaluate_model_receipt(receipt):
    """Return a list of (AF_CODE, message). Empty list == clean. Fail-closed:
    a non-dict receipt (missing/unrecorded) is an immediate AF_MODEL_TIER."""
    fails = []
    if not isinstance(receipt, dict):
        return [(AF_MODEL_TIER, "model-content-receipt is missing/not a JSON object — "
                 "the authoring model was never resolved/recorded (fail-closed)")]
    model = str(receipt.get("model") or receipt.get("model_id") or "").strip()
    provider = str(receipt.get("provider") or "").strip().lower()
    tier = str(receipt.get("tier") or receipt.get("role") or "").strip().lower()
    if not model:
        fails.append((AF_MODEL_TIER, "model-content-receipt names no resolved model id"))
    # Anthropic hard-ban tested on the provider FIELD and the model id shape.
    if provider in _ANTHROPIC_PROVIDERS or model.lower().startswith(("claude", "anthropic")) \
            or "anthropic" in model.lower():
        fails.append((AF_MODEL_NOANTHROPIC,
                      "authoring model is Anthropic (provider=%r, model=%r) — "
                      "client skills never use Anthropic models" % (provider, model)))
    if tier not in EXECUTION_TIERS:
        fails.append((AF_MODEL_TIER,
                      "authoring tier %r is not an execution/content tier %s — "
                      "the client's OWN strongest model must write the copy"
                      % (tier, sorted(EXECUTION_TIERS))))
    return fails


def _load_receipt_from_run(run_dir):
    """Return (receipt_or_None, source_path_or_None). None receipt when no
    receipt file exists at any standard location — the caller fails closed."""
    rd = Path(run_dir)
    for rel in _RECEIPT_LOCATIONS:
        p = rd / rel
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8")), str(p)
            except (OSError, ValueError):
                return "__unreadable__", str(p)
    return None, None


def _emit(fails, source, as_json):
    passed = not fails
    if as_json:
        print(json.dumps({"gate": "ad-model-sovereignty", "pass": passed,
                          "source": source,
                          "findings": [{"code": c, "message": m} for c, m in fails]}, indent=2))
        return EXIT_PASS if passed else EXIT_AUTOFAIL
    print("== Facebook Ad Generator :: model-sovereignty gate ==")
    if source:
        print("receipt: %s" % source)
    if passed:
        print("RESULT: PASS — client execution-tier model recorded; no Anthropic.")
        return EXIT_PASS
    print("RESULT: FAIL (fail-closed) — %d finding(s):" % len(fails))
    for c, m in fails:
        print("  [%s] %s" % (c, m))
    return EXIT_AUTOFAIL


def run_receipt(receipt_path, as_json=False):
    p = Path(receipt_path)
    if not p.is_file():
        return _emit(evaluate_model_receipt(None), str(p), as_json)
    try:
        receipt = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _emit([(AF_MODEL_TIER, "model-content-receipt unreadable: %s" % exc)],
                     str(p), as_json)
    return _emit(evaluate_model_receipt(receipt), str(p), as_json)


def run_dir(run_directory, as_json=False):
    receipt, source = _load_receipt_from_run(run_directory)
    if receipt == "__unreadable__":
        return _emit([(AF_MODEL_TIER, "model-content-receipt present but unreadable")],
                     source, as_json)
    # A None receipt (no file found) fails closed inside evaluate_model_receipt.
    return _emit(evaluate_model_receipt(receipt), source, as_json)


# =============================================================================
# SELF-TEST — in-memory fixtures.
# =============================================================================
def self_test():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "MISS", name))

    def has(fails, code):
        return any(c == code for c, _ in fails)

    print("== self-test: CLEAN receipts (must pass) ==")
    check("client execution-tier openrouter model -> clean",
          evaluate_model_receipt(
              {"model": "moonshotai/kimi-k2.6", "provider": "openrouter", "tier": "content"}) == [])
    check("ollama-cloud strongest tier -> clean",
          evaluate_model_receipt(
              {"model_id": "kimi-k2.6:cloud", "provider": "ollama-cloud", "role": "authoring"}) == [])

    print("== self-test: FAIL receipts (must be caught) ==")
    check("missing receipt (None) -> AF-FBAD-MODEL-TIER",
          has(evaluate_model_receipt(None), AF_MODEL_TIER))
    check("empty dict -> AF-FBAD-MODEL-TIER",
          has(evaluate_model_receipt({}), AF_MODEL_TIER))
    check("anthropic provider -> AF-FBAD-MODEL-NOANTHROPIC",
          has(evaluate_model_receipt(
              {"model": "some-model", "provider": "anthropic", "tier": "content"}),
              AF_MODEL_NOANTHROPIC))
    check("claude model id -> AF-FBAD-MODEL-NOANTHROPIC",
          has(evaluate_model_receipt(
              {"model": "claude-opus-4-8", "provider": "openrouter", "tier": "content"}),
              AF_MODEL_NOANTHROPIC))
    check("anthropic slash id -> AF-FBAD-MODEL-NOANTHROPIC",
          has(evaluate_model_receipt(
              {"model": "anthropic/claude-3.5-sonnet", "provider": "openrouter", "tier": "content"}),
              AF_MODEL_NOANTHROPIC))
    check("cheap/judge tier -> AF-FBAD-MODEL-TIER",
          has(evaluate_model_receipt(
              {"model": "gemini-3.1-flash-lite", "provider": "gemini", "tier": "judge"}),
              AF_MODEL_TIER))
    check("no model id -> AF-FBAD-MODEL-TIER",
          has(evaluate_model_receipt({"provider": "openrouter", "tier": "content"}),
              AF_MODEL_TIER))

    print("== ad_model_sovereignty self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fail-closed model-sovereignty / no-Anthropic gate (Facebook Ad Generator, Skill 48).")
    ap.add_argument("--receipt", help="path to a model-content-receipt.json")
    ap.add_argument("--run-dir", dest="run_dir", help="ad run dir (searches standard receipt locations)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.receipt:
        return run_receipt(args.receipt, as_json=args.json)
    if args.run_dir:
        return run_dir(args.run_dir, as_json=args.json)
    ap.error("--receipt FILE or --run-dir DIR required (or use --self-test)")


if __name__ == "__main__":
    sys.exit(main())
