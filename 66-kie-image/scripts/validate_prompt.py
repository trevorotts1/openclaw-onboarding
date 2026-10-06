#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_prompt.py - Skill 66 kie-image prompt validator (v1.1.0).

Prompt budget (owner order 2026-10-05): a prompt uses 95-100% of the model's character max and is
never below 80% of it. The limit comes from Skill 74 `prompt-budget` (live schema first, registry
snapshot second); when that adapter is absent or unreachable the limit is the models.json cap
(vendor_hard_cap_chars, else owner_observed_cap_chars). Unknown limit -> UNKNOWN warning, no floor.

  floor = ceil(0.80 * max)   below it  -> invalid (exit 1), prints the exact chars to ADD
  target = 95%..100% of max  80-95%    -> valid with a warning to expand
  max                        above it  -> invalid hard fail (exit 2), prints the exact chars to CUT

The old house band (5,000 / 9,000 / 19,000) is retired by this order. Token-capped models (Qwen) get a
token estimate warning only (never a fake char cap). STDLIB PYTHON3 ONLY. No secrets read.

Exit codes:  0 acceptable (warnings may exist) | 1 invalid (below floor, unknown model, strict warning)
             2 above the maximum (hard)

Output: single JSON object on stdout: { model_id, cap_status, chars, tokens_est, max, floor, target_min,
  target_max, limit_source, status, errors[], warnings[], valid }.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter_bridge  # noqa: E402  (Skill 74 bridge; optional at runtime)

VERSION = "2.2.0"

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models.json")

FLOOR_PCT, TARGET_PCT = 80, 95  # percent of the model max (integer math, no float rounding surprises)


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


def budget(max_chars):
    return {"max": max_chars, "floor": -(-max_chars * FLOOR_PCT // 100),
            "target_min": -(-max_chars * TARGET_PCT // 100), "target_max": max_chars}


def _result(model_id, cap_status, chars, **kw):
    r = {"model_id": model_id, "cap_status": cap_status, "chars": chars, "tokens_est": token_estimate(chars),
         "max": None, "floor": None, "target_min": None, "target_max": None, "limit_source": None,
         "status": "UNKNOWN", "errors": [], "warnings": [], "valid": True}
    r.update(kw)
    r["valid"] = not r["errors"]
    return r


def _from_budget(model_id, cap_status, chars, d, source, warnings):
    """Apply the budget to a character count. d: max/floor/target_min (or only max for verbatim fields)."""
    mx, floor, tmin = d["max"], d.get("floor"), d.get("target_min")
    errors, status = [], "OK"
    if chars > mx:
        status = "ABOVE_MAX"
        errors.append("prompt is %d chars; max is %d; CUT exactly %d chars" % (chars, mx, chars - mx))
    elif floor is not None and chars < floor:
        status = "BELOW_FLOOR"
        errors.append("prompt is %d chars (%.1f%% of max %d); floor is %d (80%%): ADD at least %d chars "
                      "(%d to reach the 95%% target of %d)" % (chars, 100.0 * chars / mx, mx, floor, floor - chars,
                                                               tmin - chars, tmin))
    elif tmin is not None and chars < tmin:
        status = "BELOW_TARGET"
        warnings = warnings + ["prompt is %d chars (%.1f%% of max); target is 95-100%%: add %d chars to reach %d" % (
            chars, 100.0 * chars / mx, tmin - chars, tmin)]
    r = _result(model_id, cap_status, chars, max=mx, floor=floor, target_min=tmin, target_max=mx,
                limit_source=source, status=status, errors=errors, warnings=warnings)
    if status == "ABOVE_MAX":
        r["hard_cap_chars"] = mx
    return r


def validate_body(prompt, model_id, strict):
    chars = char_count(prompt)
    # 1. Skill 74 prompt-budget (live schema, then registry snapshot, then policy owner)
    got = adapter_bridge.prompt_budget(model_id, prompt.strip())
    if got is not None:
        d = got["data"]
        w = list(got.get("warnings") or [])
        entry = by_id_get(model_id)
        cap = (entry or {}).get("cap_status", "SKILL-74")
        if d.get("max") is None:
            r = _result(model_id, cap, chars, status=d.get("status", "UNKNOWN"), limit_source=d.get("limit_source"),
                        warnings=w)
        else:
            r = _from_budget(model_id, cap, chars, d, "skill-74:" + str(d.get("limit_source")), w)
    else:
        # 2. models.json fallback: the policy-owner cap recorded for this model
        entry = by_id_get(model_id)
        if entry is None:
            return _result(model_id, "UNKNOWN", chars, errors=["model %r not in registry" % model_id], status="UNKNOWN")
        cap = entry.get("cap_status", "NOT_PUBLISHED")
        # KIE's live schema (20,000 for legacy gpt-image-2) supersedes the N43 owner-confirmed 25,000 as of 2026-10-05
        mx = (entry.get("live_schema_cap_chars") or entry.get("vendor_hard_cap_chars")
              or entry.get("owner_observed_cap_chars"))
        w = ["Skill 74 adapter unavailable; limit taken from models.json (%s)" % cap]
        if mx:
            r = _from_budget(model_id, cap, chars, budget(mx), "models.json:%s" % cap, w)
        else:
            tcap = entry.get("vendor_hard_cap_tokens")
            if tcap and token_estimate(chars) > tcap:
                w.append("estimated %d tokens (chars/4) exceeds documented %d token cap for %s; the docs cap is TOKENS "
                         "not chars: trim, and treat as approximate" % (token_estimate(chars), tcap, model_id))
            w.append("prompt limit UNKNOWN for %s (cap_status %s): no floor enforced; no cap invented" % (model_id, cap))
            r = _result(model_id, cap, chars, status="UNKNOWN", limit_source="models.json:%s" % cap, warnings=w)
    if strict:
        r["errors"] += ["strict: " + x for x in r["warnings"]]
        r["warnings"] = []
        r["valid"] = not r["errors"]
    return r


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

# (name, prompt chars, model, expected_valid, expected_status, expected_hard_cap_flag)
# Bridge off: limits come from models.json (gpt-2.5 20,000 DOCS; legacy gpt-image-2 20,000 live schema (N43 25,000 superseded);
# wan/ideogram/imagen 5,000 verified; seedream not published -> UNKNOWN).
STATIC_CASES = [
    ("wan 5000 = max ok", 5000, "wan/2-7-image", True, "OK", False),
    ("wan 5001 above max", 5001, "wan/2-7-image", False, "ABOVE_MAX", True),
    ("wan 4800 in target ok", 4800, "wan/2-7-image", True, "OK", False),
    ("wan 3999 below 80% floor rejected", 3999, "wan/2-7-image", False, "BELOW_FLOOR", False),
    ("wan 4000 = floor ok (warn expand)", 4000, "wan/2-7-image", True, "BELOW_TARGET", False),
    ("gpt-2.5 20000 = max ok", 20000, "gpt-image-2-5-sunburst-text-to-image", True, "OK", False),
    ("gpt-2.5 19000 = 95% ok", 19000, "gpt-image-2-5-sunburst-text-to-image", True, "OK", False),
    ("gpt-2.5 20001 above max rejected", 20001, "gpt-image-2-5-sunburst-text-to-image", False, "ABOVE_MAX", True),
    ("gpt-2.5 16000 = 80% floor ok (warn expand)", 16000, "gpt-image-2-5-sunburst-text-to-image", True,
     "BELOW_TARGET", False),
    ("gpt-2.5 15999 under 80% rejected", 15999, "gpt-image-2-5-sunburst-text-to-image", False, "BELOW_FLOOR", False),
    ("gpt-2.5 9500 (old house target) now rejected", 9500, "gpt-image-2-5-sunburst-text-to-image", False,
     "BELOW_FLOOR", False),
    ("gpt-2.5 300 chars rejected", 300, "gpt-image-2-5-sunburst-text-to-image", False, "BELOW_FLOOR", False),
    ("legacy gpt-image-2 20000 = live schema max ok", 20000, "gpt-image-2-text-to-image", True, "OK", False),
    ("legacy gpt-image-2 15999 below its 16000 floor", 15999, "gpt-image-2-text-to-image", False, "BELOW_FLOOR", False),
    ("legacy gpt-image-2 20001 above max (N43 25,000 superseded)", 20001, "gpt-image-2-text-to-image", False,
     "ABOVE_MAX", True),
    ("ideogram 5000 ok", 5000, "ideogram/v3-text-to-image", True, "OK", False),
    ("ideogram 5001 above max", 5001, "ideogram/v3-text-to-image", False, "ABOVE_MAX", True),
    ("imagen4 5000 ok", 5000, "google/imagen4", True, "OK", False),
    ("qwen token-capped: no fake char cap, no floor", 200, "qwen3/text-to-image", True, "UNKNOWN", False),
    ("seedream not published: UNKNOWN, no floor", 9000, "seedream/5-pro-text-to-image", True, "UNKNOWN", False),
    ("seedream not published zero chars ok", 0, "seedream/5-pro-text-to-image", True, "UNKNOWN", False),
    ("unknown model fails", 5, "not/a-model", False, "UNKNOWN", False),
]

# Bridge on, answered by a fake Skill 74: a model 66 has never heard of (the newest GPT Image generation).
FAKE_BUDGET = {"state": "validated", "warnings": [], "data": {"status": "OK", "max": 30000, "floor": 24000,
                                                                "target_min": 28500, "target_max": 30000,
                                                                "limit_source": "live-schema:live"}}
ADAPTER_CASES = [
    ("new model 29000 ok via adapter", 29000, "gpt-image-3-aurora-text-to-image", True, "OK", False),
    ("new model 23999 under 80% rejected", 23999, "gpt-image-3-aurora-text-to-image", False, "BELOW_FLOOR", False),
    ("new model 30001 above max rejected", 30001, "gpt-image-3-aurora-text-to-image", False, "ABOVE_MAX", True),
    ("adapter limit beats models.json (gpt-2.5 now 30000)", 20000, "gpt-image-2-5-sunburst-text-to-image", False,
     "BELOW_FLOOR", False),
]


def _run_cases(cases, failures):
    for name, n, model, exp_valid, exp_status, exp_hard in cases:
        res = validate_prompt("x" * n, model)
        if res["valid"] != exp_valid or (exp_status and res["status"] != exp_status):
            failures.append("FAIL %s: expected valid=%s status=%s got valid=%s status=%s (%s)" % (
                name, exp_valid, exp_status, res["valid"], res["status"], res["errors"]))
        elif exp_hard != (res.get("hard_cap_chars") is not None):
            failures.append("FAIL %s: expected hard-cap-flag=%s" % (name, exp_hard))
    return failures


def selftest():
    import tempfile
    failures = []
    saved = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    os.environ["KIE_LIVE_ADAPTER_PATH"] = ""
    _run_cases(STATIC_CASES, failures)
    res = validate_prompt("   " + "m" * 4500 + "   ", "wan/2-7-image")
    if res["chars"] != 4500:
        failures.append("FAIL whitespace not stripped before count: %s" % res["chars"])
    res = validate_prompt("x" * 100, "wan/2-7-image")
    if not any("ADD at least 3900" in e for e in res["errors"]):
        failures.append("FAIL below-floor message must name the exact chars to add: %s" % res["errors"])
    res = validate_prompt("x" * 5003, "wan/2-7-image")
    if not any("CUT exactly 3 chars" in e for e in res["errors"]):
        failures.append("FAIL above-max message must name the exact chars to cut: %s" % res["errors"])
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "kie_live_adapter.py")
        with open(script, "w") as fh:
            fh.write("import os, sys\nsys.stdout.write(open(os.path.join(os.path.dirname(__file__), 'answer.json')).read())\n")
        with open(os.path.join(d, "answer.json"), "w") as fh:
            json.dump(FAKE_BUDGET, fh)
        os.environ["KIE_LIVE_ADAPTER_PATH"] = script
        _run_cases(ADAPTER_CASES, failures)
        os.environ["KIE_LIVE_ADAPTER_PATH"] = os.path.join(d, "missing.py")  # unreachable adapter -> models.json
        _run_cases([("adapter unreachable: models.json limit", 20000, "gpt-image-2-5-sunburst-text-to-image", True, "OK",
                     False)], failures)
    if saved is None:
        os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)
    else:
        os.environ["KIE_LIVE_ADAPTER_PATH"] = saved
    total = len(STATIC_CASES) + len(ADAPTER_CASES) + 4
    if failures:
        print("validate_prompt.py --self-test FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print("validate_prompt.py --self-test: %d/%d passed" % (total, total))
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
