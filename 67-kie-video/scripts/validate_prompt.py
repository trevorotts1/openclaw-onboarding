#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_prompt.py - Skill 67 kie-video prompt validator.

KIE prompt rule 12 (owner order 2026-10-05): a descriptive video prompt is 95 to 100 percent of the
model's character max, never below 80 percent, never above 100 percent. This script keeps no band of its own:
it calls the shared enforcer shared-utils/kie_prompt_enforcer.py, which wraps Skill 74
`kie_live_adapter.py prompt-budget --check` (live schema, registry snapshot). When the adapter has no limit
for a model, the policy-owner limit recorded in models.json applies (vendor_hard_cap_chars, else
owner_observed_cap_chars). A model with no limit anywhere is UNKNOWN: warning, no floor.
The retired 5,000 / 9,000 / 19,000 house band is gone.

RULE LABELS (informational, from models.json cap_status):
  A. verified cap >= 20000  B. verified 5,000-19,999  C. verified < 5,000
  D. token cap published (tokens estimate chars/4, never a fake char cap)
  E. not published (NOT_PUBLISHED / LIVE_PROBE_REQUIRED: UNKNOWN, no floor)

STDLIB PYTHON3 ONLY. No secrets read (the adapter resolves its own key).

Exit codes:
  0  prompt acceptable (warnings may exist)
  1  invalid: below the 80 percent floor (prints the chars to ADD), unknown model, or a --strict warning
  2  hard-fail: above the model max (prints the chars to CUT)

Output: single JSON object on stdout: { model_id, cap_status, chars, tokens_est, max, floor, target_min,
  limit_source, status, rule, errors[], warnings[], valid }.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _load_enforcer():
    """Find shared-utils/kie_prompt_enforcer.py (repo checkout or installed skills tree) and import it."""
    envd = os.environ.get("OPENCLAW_SKILLS_DIR")
    dirs = [p / "shared-utils" for p in Path(__file__).resolve().parents]
    dirs += ([Path(envd) / "shared-utils"] if envd else []) + [
        Path.home() / ".openclaw" / "skills" / "shared-utils", Path("/data/.openclaw/skills/shared-utils")]
    for d in dirs:
        if (d / "kie_prompt_enforcer.py").is_file():
            sys.path.insert(0, str(d))
            import kie_prompt_enforcer
            return kie_prompt_enforcer
    raise ImportError("shared-utils/kie_prompt_enforcer.py not found; install or update the onboarding skills")


KPE = _load_enforcer()

VERSION = "2.1.0"

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models.json")

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
    chars = char_count(prompt)
    tokens = token_estimate(chars)
    if entry is None:
        return {"model_id": model_id, "cap_status": "UNKNOWN", "chars": chars, "tokens_est": tokens, "rule": None,
                "status": "UNKNOWN", "errors": [f"model {model_id!r} not in registry"], "warnings": [], "valid": False}

    cap_status = entry.get("cap_status", "NOT_PUBLISHED")
    rule, vcap, tcap = classify(entry)
    display_name = entry.get("display_name", model_id)
    errors, warnings, hard = [], [], None

    # HappyHorse Chinese sub-cap: vendor documents 5,000 chars non-Chinese but 2,500 chars Chinese. When the
    # prompt is predominantly CJK and the registry carries vendor_hard_cap_chars_cn, enforce 2,500 first.
    cn_cap = entry.get("vendor_hard_cap_chars_cn")
    if cn_cap is not None and chars > cn_cap:
        cjk = sum(1 for ch in prompt if "一" <= ch <= "鿿")
        if chars > 0 and cjk / chars > 0.3:
            hard = cn_cap
            errors.append(f"prompt is {chars} characters, predominantly Chinese; hard cap for "
                          f"{display_name} ({model_id}) is 2,500 Chinese characters (VERIFIED)")

    # Rule 12 through the shared enforcer: live schema / registry, else the policy-owner limit in models.json
    fb = vcap or entry.get("live_schema_cap_chars") or entry.get("owner_observed_cap_chars")
    v = KPE.check(model_id, prompt, fallback_max=fb)
    status, limit_source = v["status"], v["source"]
    if v["status"] == "ADAPTER_UNAVAILABLE":  # adapter absent and no policy-owner limit: UNKNOWN, no floor
        status, limit_source = "UNKNOWN", "models.json:%s" % cap_status
        warnings.append("Skill 74 adapter unavailable and no limit recorded in models.json: prompt limit UNKNOWN for "
                        "%s (cap_status %s); no floor enforced; no cap invented" % (model_id, cap_status))
        if cap_status == "LIVE_PROBE_REQUIRED":
            warnings.append("cap_status LIVE_PROBE_REQUIRED: vendor doc conflict for %s; probe the live endpoint before "
                            "long prompts" % model_id)
    else:
        warnings.extend(v["warnings"])
        if not v["ok"]:
            errors.append(v["message"])
            if v["status"] == "ABOVE_MAX":
                hard = v["max"]
    if rule == RULE_D and tcap is not None and tokens > tcap:
        warnings.append(f"estimated {tokens} tokens (chars/4) exceeds documented {tcap} token cap for {model_id}; "
                        f"trim, and treat as approximate")

    if strict:
        for w in warnings:
            errors.append("strict: " + w)
        warnings = []

    result = {"model_id": model_id, "cap_status": cap_status, "chars": chars, "tokens_est": tokens,
              "max": v["max"], "floor": v["floor"], "target_min": v["target_min"], "limit_source": limit_source,
              "status": status, "rule": rule, "errors": errors, "warnings": warnings, "valid": not errors}
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
    # Adapter off: limits come from models.json (the policy owner), so the cases are deterministic.
    saved = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    os.environ["KIE_LIVE_ADAPTER_PATH"] = ""
    cases = [
        # (name, prompt, model, expected_valid, expected_status, expect_err, expect_exit2)
        ("wan 3.0 (20000) 19000 = 95% ok", "x" * 19000, "wan/3-0-video", True, "OK", None, False),
        ("wan 3.0 20000 = max ok", "x" * 20000, "wan/3-0-video", True, "OK", None, False),
        ("wan 3.0 20001 above max", "x" * 20001, "wan/3-0-video", False, "ABOVE_MAX", "CUT exactly 1 chars", True),
        ("wan 3.0 15999 = 79.99% below floor", "x" * 15999, "wan/3-0-video", False, "BELOW_FLOOR", "ADD at least 1 chars", False),
        ("wan 3.0 16000 = 80% floor ok (warn expand)", "x" * 16000, "wan/3-0-video", True, "BELOW_TARGET", None, False),
        ("wan 3.0 9000 (old house target) now rejected", "x" * 9000, "wan/3-0-video", False, "BELOW_FLOOR", None, False),
        ("kling omni 3072 = max ok", "x" * 3072, "kling-3.0-omni/text-to-video", True, "OK", None, False),
        ("kling omni 3073 above max", "x" * 3073, "kling-3.0-omni/text-to-video", False, "ABOVE_MAX", "CUT exactly 1 chars", True),
        ("kling omni 2457 below 80% floor", "x" * 2457, "kling-3.0-omni/text-to-video", False, "BELOW_FLOOR", "ADD at least 1 chars", False),
        ("pixverse 5000 = max ok", "x" * 5000, "pixverse-v6/text-to-video", True, "OK", None, False),
        ("pixverse 5001 above max", "x" * 5001, "pixverse-v6/text-to-video", False, "ABOVE_MAX", "CUT exactly 1 chars", True),
        ("pixverse 3999 below floor", "x" * 3999, "pixverse-v6/text-to-video", False, "BELOW_FLOOR", None, False),
        ("minimax 7000 = max ok", "x" * 7000, "minimax-h3/text-to-video", True, "OK", None, False),
        ("minimax 7001 above max", "x" * 7001, "minimax-h3/text-to-video", False, "ABOVE_MAX", None, True),
        ("kling 3.0 video not published: UNKNOWN, no floor", "x" * 800, "kling-3.0/video", True, "UNKNOWN", None, False),
        ("runway live probe required: UNKNOWN, no floor", "x" * 1500, "runway", True, "UNKNOWN", None, False),
        ("veo3 not published: UNKNOWN, no floor", "x" * 60, "veo3", True, "UNKNOWN", None, False),
        ("seedance 2.5 30000 = max ok", "x" * 30000, "bytedance/seedance-2-5", True, "OK", None, False),
        ("seedance 2.5 30001 above max", "x" * 30001, "bytedance/seedance-2-5", False, "ABOVE_MAX", None, True),
        ("seedance 2.5 23999 below floor", "x" * 23999, "bytedance/seedance-2-5", False, "BELOW_FLOOR", None, False),
        ("unknown model fails", "test prompt", "not/a-real-video-model", False, "UNKNOWN", "not in registry", False),
        ("happyhorse 4000 CJK exceeds Chinese cap", "好" * 4000, "happyhorse-1-1/text-to-video", False, None,
         "2,500 Chinese characters", True),
        ("happyhorse 4000 latin = 80% ok (no CN cap)", "x" * 4000, "happyhorse-1-1/text-to-video", True, "BELOW_TARGET", None, False),
    ]
    failures = []
    for name, prompt, model, exp_valid, exp_status, exp_err, exp_exit2 in cases:
        res = validate_prompt(prompt, model)
        if res["valid"] != exp_valid:
            failures.append(f"FAIL {name}: expected valid={exp_valid} got {res['valid']} ({res['errors']})")
            continue
        if exp_status is not None and res.get("status") != exp_status:
            failures.append(f"FAIL {name}: expected status={exp_status} got={res.get('status')}")
        if exp_err and not any(exp_err in e for e in res["errors"]):
            failures.append(f"FAIL {name}: expected error {exp_err!r} got {res['errors']}")
        if exp_exit2 != (res.get("hard_cap_chars") is not None):
            failures.append(f"FAIL {name}: expected hard-cap-flag={exp_exit2}")
    if saved is None:
        os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)
    else:
        os.environ["KIE_LIVE_ADAPTER_PATH"] = saved
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
