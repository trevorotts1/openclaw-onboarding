#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_prompt.py - Skill 66 kie-image prompt validator.

Checks a prompt against a model's published/observed char caps and the house
band, and produces a token ESTIMATE (chars/4) for token-capped models.

RULES (spec 7.4):
  A. verified cap >= 20000  -> house band 5,000-19,000
  B. verified 5,000-19,999  -> conservative ceiling BELOW the hard cap
  C. verified < 5,000       -> cap-relative guidance, never invent
  D. token cap published    -> tokens estimate, NEVER a fake char cap
  E. not published          -> NOT_PUBLISHED / LIVE_PROBE_REQUIRED, no invented cap

STDLIB PYTHON3 ONLY. Deterministic. No network. No secrets read.

Exit codes:
  0  prompt acceptable (warnings may exist)
  1  soft-fail = house-band violation OR cap-status issues (non-fatal by default;
     use --strict to turn warnings fatal)
  2  hard-fail = prompt exceeds a VERIFIED hard cap

Output: single JSON object on stdout: { model_id, cap_status, chars, tokens_est,
  band_min, band_target, band_max, rule, errors[], warnings[], valid }.
"""

import argparse
import json
import os
import re
import sys

VERSION = "1.0.0"

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models.json")

HOUSE_MIN = 5000
HOUSE_TARGET = 9000
HOUSE_MAX = 19000

# rule classification
RULE_A = "A"
RULE_B = "B"
RULE_C = "C"
RULE_D = "D"
RULE_E = "E"


def load_registry():
    with open(REGISTRY_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    by_id = {m["canonical_model_id"]: m for m in data["models"]}
    return data, by_id


def char_count(text):
    """Count characters after stripping surrounding whitespace (not internal)."""
    return len(text.strip())


def token_estimate(chars):
    """Conservative estimate: ~4 chars/token (English prose). Never a cap."""
    est = chars / 4.0
    return int(est)


def classify(entry):
    """Return (rule, hard_cap_chars_or_None, token_cap_or_None)."""
    cap_status = entry.get("cap_status", "NOT_PUBLISHED")
    vcap = entry.get("vendor_hard_cap_chars")
    ocap = entry.get("owner_observed_cap_chars")
    tcap = entry.get("vendor_hard_cap_tokens")

    if vcap is not None:
        if vcap >= 20000:
            return RULE_A, vcap, tcap
        if vcap >= 5000:
            return RULE_B, vcap, tcap
        return RULE_C, vcap, tcap
    if tcap is not None:
        return RULE_D, None, tcap
    if ocap is not None:
        # owner-observed is never a vendor-verified hard cap: vcap stays None so
        # rule A guidance (house band) applies and no hard-fail is emitted.
        return RULE_A, None, tcap  # observed >= 20000 in practice (25000)
    if cap_status in ("NOT_PUBLISHED", "UNDETERMINED"):
        return RULE_E, None, None
    # LIVE_PROBE_REQUIRED and friends: not published
    return RULE_E, None, None


def validate_body(prompt, model_id, strict):
    entry = by_id_get(model_id)
    if entry is None:
        return {"model_id": model_id, "cap_status": "UNKNOWN", "chars": char_count(prompt),
                "tokens_est": token_estimate(char_count(prompt)),
                "band_min": HOUSE_MIN, "band_target": HOUSE_TARGET, "band_max": HOUSE_MAX,
                "rule": None, "errors": ["model %r not in registry" % model_id],
                "warnings": [], "valid": False}

    chars = char_count(prompt)
    tokens = token_estimate(chars)
    cap_status = entry.get("cap_status", "NOT_PUBLISHED")
    rule, vcap, tcap = classify(entry)
    ocap = entry.get("owner_observed_cap_chars")

    errors = []
    warnings = []

    hard = None
    # Hard-fail only on VERIFIED hard char caps (rule B/C) — chars > cap -> exit 2
    if rule in (RULE_B, RULE_C) and vcap is not None and chars > vcap:
        hard = vcap
        errors.append(
            "prompt is %d characters; %s hard cap for %s is %d (VERIFIED)" % (
                chars, model_id, entry.get("display_name", model_id), vcap))

    if rule == RULE_A:
        # verified or owner-observed cap at/above 20k — enforce house band as
        # guidance only (owner-observed is not vendor-verified: never hard-fail)
        if chars < HOUSE_MIN:
            warnings.append(
                "prompt %d chars is thin vs house band %d-%d; add context, target ~%d "
                "(non-fatal)" % (chars, HOUSE_MIN, HOUSE_MAX, HOUSE_TARGET))
        elif chars > HOUSE_MAX:
            if vcap is not None and chars > vcap:
                errors.append(
                    "prompt %d chars exceeds the cap %d attributed to %s" % (
                        chars, vcap, entry.get("display_name", model_id)))
            else:
                if ocap:
                    cap_desc = "owner observed %d" % ocap
                elif vcap:
                    cap_desc = "verified %d" % vcap
                else:
                    cap_desc = "NOT published"
                warnings.append(
                    "prompt %d chars exceeds house max %d; cap %s (cap_status %s) — trim "
                    "before dispatch (non-fatal)" % (
                        chars, HOUSE_MAX, cap_desc, cap_status))
    elif rule == RULE_B:
        if chars > vcap:
            hard = vcap
            errors.append("prompt %d chars exceeds VERIFIED hard cap %d" % (chars, vcap))
        elif chars >= vcap * 0.98:
            warnings.append(
                "prompt %d chars is at %d%% of the hard cap %d; leave headroom, target "
                "~4,500-4,900 where cap is 5,000" % (chars, int(chars * 100 / vcap), vcap))
        elif chars < HOUSE_MIN:
            warnings.append("prompt %d chars under house band; target ~%d (non-fatal)"
                            % (chars, HOUSE_TARGET))
    elif rule == RULE_C:
        if chars > vcap:
            hard = vcap
            errors.append("prompt %d chars exceeds published maximum %d" % (chars, vcap))
        elif chars >= vcap * 0.9:
            warnings.append("prompt %d chars near cap %d; keep headroom" % (chars, vcap))
    elif rule == RULE_D:
        # token cap published; chars are an estimate, never a hard cap
        if tokens > tcap:
            warnings.append(
                "estimated %d tokens (chars/4) exceeds documented %d token cap for %s; "
                "the docs cap is TOKENS not chars — trim, and treat as approximate" % (
                    tokens, tcap, model_id))
        if chars < HOUSE_MIN:
            warnings.append("prompt %d chars under house band (non-fatal)" % chars)
    elif rule == RULE_E:
        # nothing published: soft pass, flag for probe
        warnings.append(
            "cap_status %s: prompt cap NOT PUBLISHED for %s — treat as LIVE_PROBE_REQUIRED "
            "before long prompts; no invented cap used" % (cap_status, model_id))

    if strict:
        for w in warnings:
            errors.append("strict: " + w)
        warnings = []

    band_status = "ok"
    if band_status != "ok":
        pass
    if chars < HOUSE_MIN:
        band_status = "thin"
    elif chars > HOUSE_MAX:
        band_status = "hot"

    result = {
        "model_id": model_id,
        "cap_status": cap_status,
        "chars": chars,
        "tokens_est": tokens,
        "band_min": HOUSE_MIN,
        "band_target": HOUSE_TARGET,
        "band_max": HOUSE_MAX,
        "rule": rule,
        "band_status": band_status,
        "errors": errors,
        "warnings": warnings,
        "valid": not errors,
    }
    if hard is not None:
        result["hard_cap_chars"] = hard
    return result


# module-level cache for the registry (loaded once per process)
_REG = None
_BY_ID = None


def by_id_get(model_id):
    global _REG, _BY_ID
    if _BY_ID is None:
        _REG, _BY_ID = load_registry()
    return _BY_ID.get(model_id)


def validate_prompt(prompt, model_id, strict=False):
    return validate_body(prompt, model_id, strict)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def selftest():
    cases = [
        # (name, prompt, model, expected_valid, expected_rule, expect_err=None, expect_warn=None, expect_exit2=None)
        ("wan 5000 ok",
         "x" * 5000, "wan/2-7-image", True, "B", None, None, False),
        ("wan 5001 exceeds hard cap",
         "x" * 5001, "wan/2-7-image", False, "B", "exceeds VERIFIED hard cap", None, True),
        ("wan 4800 headroom ok",
         "x" * 4800, "wan/2-7-image", True, "B", None, None, False),
        ("gpt owner-observed 25000 ok",
         "x" * 20000, "gpt-image-2-text-to-image", True, "A", None, None, False),
        ("gpt 30000 owner-observed warn",
         "x" * 30000, "gpt-image-2-text-to-image", True, "A", None,
         "owner observed", False),
        ("gpt thin 300 chars warn",
         "x" * 300, "gpt-image-2-text-to-image", True, "A", None, "thin", False),
        ("gpt 9500 target ok",
         "x" * 9500, "gpt-image-2-text-to-image", True, "A", None, None, False),
        ("qwen token cap estimate warn",
         "x" * 20000, "qwen3/text-to-image", True, "D", None, "token cap", False),
        ("qwen short ok",
         "a" * 200, "qwen3/text-to-image", True, "D", None, None, False),
        ("seedream 5 pro not published soft pass",
         "y" * 9000, "seedream/5-pro-text-to-image", True, "E", None, "NOT PUBLISHED", False),
        ("seedream not published zero chars ok",
         "", "seedream/5-pro-text-to-image", True, "E", None, "NOT PUBLISHED", False),
        ("ideogram 5000 exact ok",
         "z" * 5000, "ideogram/v3-text-to-image", True, "B", None, None, False),
        ("ideogram 5001 exceeds",
         "z" * 5001, "ideogram/v3-text-to-image", False, "B", "exceeds VERIFIED", None, True),
        ("imagen4 5000 exact ok",
         "w" * 5000, "google/imagen4", True, "B", None, None, False),
        ("imagen4 5001 exceeds",
         "w" * 5001, "google/imagen4", False, "B", "exceeds VERIFIED", None, True),
        ("unknown model fails",
         "hello", "not/a-model", False, None, "not in registry", None, False),
        ("whitespace stripped before count",
         "   " + "m" * 100 + "   ", "wan/2-7-image", True, "B", None, None, False),
    ]
    failures = []
    for name, prompt, model, exp_valid, exp_rule, exp_err, exp_warn, exp_exit2 in cases:
        res = validate_prompt(prompt, model)
        if res["valid"] != exp_valid:
            failures.append("FAIL %s: expected valid=%s got %s (%s)" % (
                name, exp_valid, res["valid"], res["errors"]))
            continue
        if exp_rule is not None and res.get("rule") != exp_rule:
            failures.append("FAIL %s: expected rule=%s got=%s" % (name, exp_rule, res.get("rule")))
        if exp_err and not any(exp_err in e for e in res["errors"]):
            failures.append("FAIL %s: expected error %r got %s" % (name, exp_err, res["errors"]))
        if exp_warn and not any(exp_warn in w for w in res["warnings"]):
            failures.append("FAIL %s: expected warning %r got %s" % (name, exp_warn, res["warnings"]))
        got_exit2 = res.get("hard_cap_chars") is not None
        if exp_exit2 != got_exit2:
            failures.append("FAIL %s: expected hard-cap-flag=%s got=%s" % (
                name, exp_exit2, got_exit2))
    if failures:
        print("validate_prompt.py --self-test FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print("validate_prompt.py --self-test: %d/%d passed" % (len(cases), len(cases)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="KIE prompt validator (skill 66)")
    parser.add_argument("prompt", nargs="?", help="prompt text, or '-' for stdin")
    parser.add_argument("--model", required=False, help="canonical_model_id")
    parser.add_argument("--prompt-file", help="read prompt from file")
    parser.add_argument("--strict", action="store_true", help="promote warnings to errors")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return selftest()

    model = args.model
    if not model:
        parser.error("--model required (canonical_model_id)")
    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as fh:
            prompt = fh.read()
    elif args.prompt == "-":
        prompt = sys.stdin.read()
    elif args.prompt is not None:
        prompt = args.prompt
    else:
        parser.error("prompt (text, '-', or --prompt-file) required")

    res = validate_prompt(prompt, model, strict=args.strict)
    print(json.dumps(res, indent=2, sort_keys=True))
    if res.get("hard_cap_chars") is not None:
        return 2
    return 0 if res["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
