#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_prompt.py - Skill 67 kie-video prompt validator.

Checks a prompt against a video model's published/observed char caps and the
house band (5000/9000/19000).

RULES (spec 5 & references/prompt-policy.md):
  A. verified cap >= 20000  -> house band 5,000-19,000 (Wan 3.0, Gemini Omni, Seedance 2.5)
  B. verified 5,000-19,999  -> conservative ceiling BELOW hard cap (MiniMax 7K, PixVerse 5K, Wan 2.7 5K, HappyHorse 5K)
  C. verified < 5,000       -> cap-relative guidance, never force 5K (Kling Omni 3072, Kling 2.5/motion 2500)
  D. token cap published    -> tokens estimate (chars/4), never a fake char cap
  E. not published          -> NOT_PUBLISHED / LIVE_PROBE_REQUIRED (Kling 3.0 video, Seedance 2 mini, Veo3, Runway)

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
import sys

VERSION = "1.0.0"

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models.json")

HOUSE_MIN = 5000
HOUSE_TARGET = 9000
HOUSE_MAX = 19000

# Rule classifications
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
    return int(chars / 4.0)


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
        return RULE_A, None, tcap
    if cap_status in ("NOT_PUBLISHED", "UNDETERMINED", "LIVE_PROBE_REQUIRED"):
        return RULE_E, None, None
    return RULE_E, None, None


def validate_body(prompt, model_id, strict):
    entry = by_id_get(model_id)
    if entry is None:
        return {
            "model_id": model_id,
            "cap_status": "UNKNOWN",
            "chars": char_count(prompt),
            "tokens_est": token_estimate(char_count(prompt)),
            "band_min": HOUSE_MIN,
            "band_target": HOUSE_TARGET,
            "band_max": HOUSE_MAX,
            "rule": None,
            "errors": [f"model {model_id!r} not in registry"],
            "warnings": [],
            "valid": False,
        }

    chars = char_count(prompt)
    tokens = token_estimate(chars)
    cap_status = entry.get("cap_status", "NOT_PUBLISHED")
    rule, vcap, tcap = classify(entry)
    display_name = entry.get("display_name", model_id)

    errors = []
    warnings = []
    hard = None

    # HappyHorse Chinese sub-cap: vendor documents 5,000 chars non-Chinese but
    # 2,500 chars Chinese. When the prompt is predominantly CJK and the registry
    # carries vendor_hard_cap_chars_cn, enforce the 2,500 Chinese cap first.
    cn_cap = entry.get("vendor_hard_cap_chars_cn")
    if cn_cap is not None and chars > cn_cap:
        cjk = sum(1 for ch in prompt if "一" <= ch <= "鿿")
        if chars > 0 and cjk / chars > 0.3:
            hard = cn_cap
            errors.append(
                f"prompt is {chars} characters, predominantly Chinese; hard cap for "
                f"{display_name} ({model_id}) is 2,500 Chinese characters (VERIFIED)"
            )

    # Hard-fail on VERIFIED hard char caps (rule A/B/C) — chars > cap -> exit 2
    if vcap is not None and chars > vcap and cap_status == "VERIFIED":
        hard = vcap
        errors.append(
            f"prompt is {chars} characters; hard cap for {display_name} ({model_id}) is {vcap} (VERIFIED)"
        )

    if rule == RULE_A:
        if chars < HOUSE_MIN:
            warnings.append(
                f"prompt {chars} chars is thin vs house band {HOUSE_MIN}-{HOUSE_MAX}; "
                f"add context, target ~{HOUSE_TARGET} (non-fatal)"
            )
        elif chars > HOUSE_MAX:
            if vcap is not None and chars > vcap:
                pass  # already recorded as error
            else:
                warnings.append(
                    f"prompt {chars} chars exceeds house max {HOUSE_MAX}; cap {vcap} — "
                    f"trim before dispatch if needed (non-fatal)"
                )
    elif rule == RULE_B:
        if chars <= vcap and chars >= vcap * 0.98:
            warnings.append(
                f"prompt {chars} chars is at {int(chars * 100 / vcap)}% of hard cap {vcap}; "
                f"leave headroom (target below {vcap})"
            )
        elif chars < HOUSE_MIN:
            warnings.append(
                f"prompt {chars} chars under standard house min {HOUSE_MIN}; model cap is {vcap} (non-fatal)"
            )
    elif rule == RULE_C:
        if chars <= vcap and chars >= vcap * 0.9:
            warnings.append(f"prompt {chars} chars near cap {vcap}; keep headroom")
    elif rule == RULE_D:
        if tcap is not None and tokens > tcap:
            warnings.append(
                f"estimated {tokens} tokens (chars/4) exceeds documented {tcap} token cap for {model_id}; "
                f"trim, and treat as approximate"
            )
    elif rule == RULE_E:
        if cap_status == "LIVE_PROBE_REQUIRED":
            warnings.append(
                f"cap_status LIVE_PROBE_REQUIRED: vendor doc conflict for {model_id} "
                f"(e.g. 1800 vs 2048 chars) — probe live endpoint before long prompts; no invented cap used"
            )
        else:
            warnings.append(
                f"cap_status NOT_PUBLISHED: prompt cap unknown for {model_id} — house band proposed "
                f"(min {HOUSE_MIN}, target {HOUSE_TARGET}, max {HOUSE_MAX}); no invented cap used"
            )

    if strict:
        for w in warnings:
            errors.append("strict: " + w)
        warnings = []

    band_status = "ok"
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


# Module cache
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
# Self-test battery
# ---------------------------------------------------------------------------

def selftest():
    cases = [
        # (name, prompt, model, expected_valid, expected_rule, expect_err, expect_warn, expect_exit2)
        ("wan 3.0 19000 ok",
         "x" * 19000, "wan/3-0-video", True, "A", None, None, False),
        ("wan 3.0 20000 exact ok",
         "x" * 20000, "wan/3-0-video", True, "A", None, "exceeds house max", False),
        ("wan 3.0 21000 exceeds cap",
         "x" * 21000, "wan/3-0-video", False, "A", "hard cap for Wan 3.0 Video", None, True),
        ("kling omni 3000 ok",
         "x" * 3000, "kling-3.0-omni/text-to-video", True, "C", None, None, False),
        ("kling omni 3200 exceeds cap",
         "x" * 3200, "kling-3.0-omni/text-to-video", False, "C", "hard cap", None, True),
        ("pixverse 5000 exact ok",
         "x" * 5000, "pixverse-v6/text-to-video", True, "B", None, None, False),
        ("pixverse 5001 exceeds cap",
         "x" * 5001, "pixverse-v6/text-to-video", False, "B", "hard cap", None, True),
        ("minimax 7000 exact ok",
         "x" * 7000, "minimax-h3/text-to-video", True, "B", None, None, False),
        ("minimax 7001 exceeds cap",
         "x" * 7001, "minimax-h3/text-to-video", False, "B", "hard cap", None, True),
        ("kling 3.0 video not published proposed band",
         "x" * 8000, "kling-3.0/video", True, "E", None, "NOT_PUBLISHED", False),
        ("runway live probe required note",
         "x" * 1500, "runway", True, "E", None, "LIVE_PROBE_REQUIRED", False),
        ("veo3 not published proposed band",
         "x" * 6000, "veo3", True, "E", None, "NOT_PUBLISHED", False),
        ("seedance 2.5 30000 ok",
         "x" * 30000, "bytedance/seedance-2-5", True, "A", None, "exceeds house max", False),
        ("seedance 2.5 30001 exceeds",
         "x" * 30001, "bytedance/seedance-2-5", False, "A", "hard cap", None, True),
        ("unknown model fails",
         "test prompt", "not/a-real-video-model", False, None, "not in registry", None, False),
        ("happyhorse 4000 CJK exceeds Chinese cap",
         "好" * 4000, "happyhorse-1-1/text-to-video", False, "B", "2,500 Chinese characters", None, True),
        ("happyhorse 4000 latin no CN cap",
         "x" * 4000, "happyhorse-1-1/text-to-video", True, "B", None, None, False),
    ]

    failures = []
    for name, prompt, model, exp_valid, exp_rule, exp_err, exp_warn, exp_exit2 in cases:
        res = validate_prompt(prompt, model)
        if res["valid"] != exp_valid:
            failures.append(f"FAIL {name}: expected valid={exp_valid} got {res['valid']} ({res['errors']})")
            continue
        if exp_rule is not None and res.get("rule") != exp_rule:
            failures.append(f"FAIL {name}: expected rule={exp_rule} got={res.get('rule')}")
        if exp_err and not any(exp_err in e for e in res["errors"]):
            failures.append(f"FAIL {name}: expected error {exp_err!r} got {res['errors']}")
        if exp_warn and not any(exp_warn in w for w in res["warnings"]):
            failures.append(f"FAIL {name}: expected warning {exp_warn!r} got {res['warnings']}")
        got_exit2 = res.get("hard_cap_chars") is not None
        if exp_exit2 != got_exit2:
            failures.append(f"FAIL {name}: expected hard-cap-flag={exp_exit2} got={got_exit2}")

    if failures:
        print("validate_prompt.py --self-test FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print(f"validate_prompt.py --self-test: {len(cases)}/{len(cases)} passed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="KIE video prompt validator (skill 67)")
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
