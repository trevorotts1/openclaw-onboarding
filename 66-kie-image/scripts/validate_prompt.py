#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_prompt.py - Skill 66 kie-image prompt validator (v2.3.0).

Prompt budget (owner rule 12, kie-common-rules.md section 12, owner order 2026-10-05;
re-confirmed as governing in all contexts by owner Decision 1, 2026-10-15 and Q1,
2026-10-17): a prompt should use 95-100% of the model's VERIFIED character maximum.
80% to below 95% PASSES with a warn-and-expand message naming the characters to ADD;
below 80% FAILS hard; above the documented maximum FAILS; an UNKNOWN maximum REFUSES a
pass. This script keeps no band of its own: it calls the shared policy service through
shared-utils/kie_prompt_enforcer.py, which wraps Skill 74 `prompt-budget --check`
(live schema first, registry snapshot second). When that adapter is absent or
unreachable the limit is the models.json cap (live_schema_cap_chars, else
vendor_hard_cap_chars, else owner_observed_cap_chars); with no such cap the verdict is
UNKNOWN_MAX and the prompt is invalid.

  hard floor = ceil(0.80 * max)   below it -> invalid (exit 1), names the exact chars to ADD
  target     = 95%..100% of max   in it     -> PASS
  80% to below 95%                 in it    -> PASS with a WARN naming the exact chars to ADD
  max                              above it -> invalid hard fail (exit 2), names the chars to CUT

The old house band (5,000 / 9,000 / 19,000) is retired by owner order. Token-capped
models (Qwen) get no fake char cap; with no verified character maximum they cannot pass.
STDLIB PYTHON3 ONLY. No secrets read.

Exit codes:  0 acceptable (warnings may exist) | 1 invalid (below the 80% floor, unknown max)
             2 above the maximum (hard)

Output: single JSON object on stdout: { model_id, cap_status, chars, tokens_est, max, floor, target_min,
  target_max, limit_source, status, ratio, prompt_sha256, policy_version, errors[], warnings[], valid }.
"""

import argparse
import json
import os
import re
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

VERSION = "2.3.0"

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models.json")


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


def _result(model_id, cap_status, chars, **kw):
    r = {"model_id": model_id, "cap_status": cap_status, "chars": chars, "tokens_est": token_estimate(chars),
         "max": None, "floor": None, "target_min": None, "target_max": None, "limit_source": None,
         "status": "UNKNOWN", "errors": [], "warnings": [], "valid": True}
    r.update(kw)
    r["valid"] = not r["errors"]
    return r


def _from_verdict(model_id, cap_status, chars, v, warnings):
    """Map a shared-policy verdict onto this validator's result shape."""
    errors = [] if v["ok"] else [v["message"]]
    r = _result(model_id, cap_status, chars, max=v["max"], floor=v["floor"], target_min=v["target_min"],
                target_max=v["max"], limit_source=v["source"], status=v["status"], errors=errors,
                warnings=warnings + list(v["warnings"]), ratio=v.get("ratio"),
                prompt_sha256=v.get("prompt_sha256"), policy_version=v.get("policy_version"))
    if v["status"] == "ABOVE_MAX":
        r["hard_cap_chars"] = v["max"]
    return r


def validate_body(prompt, model_id, strict):
    chars = char_count(prompt)
    entry = by_id_get(model_id)
    # the policy owner's recorded limit: an owner-declared cap outranks the vendor schema (owner
    # ruling 2026-11-08); otherwise the live schema supersedes the N43 owner-confirmed 25,000.
    fb = ((entry or {}).get("owner_prompt_cap_chars") or (entry or {}).get("live_schema_cap_chars")
          or (entry or {}).get("vendor_hard_cap_chars") or (entry or {}).get("owner_observed_cap_chars"))
    v = KPE.check(model_id, prompt, fallback_max=fb)  # Skill 74 prompt-budget --check: live schema, registry, policy owner
    cap = (entry or {}).get("cap_status", "SKILL-74")
    if v["status"] == "ADAPTER_UNAVAILABLE":
        # No verified maximum anywhere: an unknown maximum cannot PASS (F18).
        w = ["Skill 74 adapter unavailable"]
        if entry is not None:
            tcap = entry.get("vendor_hard_cap_tokens")
            if tcap:
                w.append("the documented %d-token limit applies in its own units; this validator has no "
                         "tokenizer and does not convert it to a character cap" % tcap)
            w.append("prompt limit UNKNOWN for %s (cap_status %s): no verified character maximum, "
                     "refusing a pass" % (model_id, cap))
        errs = ([("model %r not in registry" % model_id)] if entry is None else []) + [v["message"]]
        r = _result(model_id, cap, chars, status="UNKNOWN_MAX",
                    limit_source=("models.json:%s" % cap) if entry is not None else "none",
                    errors=errs, warnings=w)
    elif v["status"] == "UNKNOWN_MAX" and entry is None:
        r = _result(model_id, "UNKNOWN", chars, status="UNKNOWN_MAX",
                    errors=["model %r not in registry" % model_id])
    else:
        r = _from_verdict(model_id, cap, chars, v, [])
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
# Bridge off: limits come from models.json (gpt-2.6 owner cap 20,000 as of the 2026-11-08 owner ruling; the
# captured vendor schema says 32,000 and is retained for provenance only; legacy gpt-image-2 20,000 live schema
# (N43 25,000 superseded); wan/ideogram/imagen 5,000 verified; seedream not published -> UNKNOWN).
# Read from models.json, never restated here: rule 12 forbids a gate keeping a character band of its own.
def _registry_cap(model_id):
    ent = by_id_get(model_id) or {}
    return (ent.get("owner_prompt_cap_chars") or ent.get("live_schema_cap_chars")
            or ent.get("vendor_hard_cap_chars") or ent.get("owner_observed_cap_chars"))
CAP_26 = _registry_cap("gpt-image-2-6/sunburst-text-to-image")
_26_95 = int(CAP_26 * 0.95)
_26_96 = int(CAP_26 * 0.96)
_26_94 = int(CAP_26 * 0.94)
_26_80 = int(CAP_26 * 0.80)

STATIC_CASES = [
    ("wan 5000 = max ok", 5000, "wan/2-7-image", True, "PASS", False),
    ("wan 5001 above max", 5001, "wan/2-7-image", False, "ABOVE_MAX", True),
    ("wan 4800 = 96% ok", 4800, "wan/2-7-image", True, "PASS", False),
    ("wan 4700 = 94% warns and expands (owner rule 12)", 4700, "wan/2-7-image", True,
     "BELOW_TARGET", False),
    ("wan 3999 below 80% hard floor rejected", 3999, "wan/2-7-image", False, "BELOW_FLOOR", False),
    ("wan 4000 = 80% warns and expands", 4000, "wan/2-7-image", True, "BELOW_TARGET", False),
    ("gpt-2.6 20000 = owner cap max ok", CAP_26, "gpt-image-2-6/sunburst-text-to-image", True, "PASS", False),
    ("gpt-2.6 19000 = 95% ok", _26_95, "gpt-image-2-6/sunburst-text-to-image", True, "PASS", False),
    ("gpt-2.6 19200 = 96% ok", _26_96, "gpt-image-2-6/sunburst-text-to-image", True, "PASS", False),
    ("gpt-2.6 18800 = 94% warns and expands", _26_94, "gpt-image-2-6/sunburst-text-to-image", True,
     "BELOW_TARGET", False),
    ("gpt-2.6 20001 above owner cap rejected", CAP_26 + 1, "gpt-image-2-6/sunburst-text-to-image", False, "ABOVE_MAX", True),
    ("gpt-2.6 16000 = 80% warns and expands", _26_80, "gpt-image-2-6/sunburst-text-to-image", True,
     "BELOW_TARGET", False),
    ("gpt-2.6 15999 under 80% rejected", _26_80 - 1, "gpt-image-2-6/sunburst-text-to-image", False,
     "BELOW_FLOOR", False),
    ("gpt-2.6 9500 (old house target) now rejected", 9500, "gpt-image-2-6/sunburst-text-to-image", False,
     "BELOW_FLOOR", False),
    ("gpt-2.6 300 chars rejected", 300, "gpt-image-2-6/sunburst-text-to-image", False, "BELOW_FLOOR", False),
    ("legacy gpt-image-2 20000 = live schema max ok", 20000, "gpt-image-2-text-to-image", True, "PASS", False),
    ("legacy gpt-image-2 15999 below its 16000 hard floor", 15999, "gpt-image-2-text-to-image", False,
     "BELOW_FLOOR", False),
    ("legacy gpt-image-2 20001 above max (N43 25,000 superseded)", 20001, "gpt-image-2-text-to-image", False,
     "ABOVE_MAX", True),
    ("ideogram 5000 ok", 5000, "ideogram/v3-text-to-image", True, "PASS", False),
    ("ideogram 5001 above max", 5001, "ideogram/v3-text-to-image", False, "ABOVE_MAX", True),
    ("imagen4 5000 ok", 5000, "google/imagen4", True, "PASS", False),
    ("qwen token-capped: no fake char cap, unknown max REFUSES", 200, "qwen3/text-to-image", False,
     "UNKNOWN_MAX", False),
    ("seedream not published: unknown max REFUSES", 9000, "seedream/5-pro-text-to-image", False,
     "UNKNOWN_MAX", False),
    ("unknown model fails", 5, "not/a-model", False, "UNKNOWN_MAX", False),
]

# Adapter on, answered by a fake Skill 74 that judges like the real CLI: a model 66 has never heard of (the newest
# GPT Image generation) with max 30000, floor 24000, target 28500.
FAKE_ADAPTER = r"""import json, sys
mx, floor, tmin = 30000, 24000, 28500
n = len(sys.stdin.read().strip())
d = {"status": "OK", "max": mx, "floor": floor, "target_min": tmin, "target_max": mx, "limit_source": "live-schema:live", "chars": n}
rc, err = 0, None
if n > mx:
    d.update(status="ABOVE_MAX", exit_code=4, cut=n - mx); rc = 4
    err = {"code": "prompt_above_max", "msg": "prompt is %d chars; max is %d; CUT exactly %d chars" % (n, mx, n - mx)}
elif n < floor:
    d.update(status="BELOW_FLOOR", exit_code=3, add_to_floor=floor - n, add_to_target=tmin - n); rc = 3
    err = {"code": "prompt_below_floor", "msg": "prompt is %d chars; floor is %d: ADD at least %d chars" % (n, floor, floor - n)}
print(json.dumps({"state": "fail" if err else "validated", "warnings": [], "error": err, "data": d}))
sys.exit(rc)
"""
ADAPTER_CASES = [
    ("new model 29000 ok via adapter", 29000, "gpt-image-3-aurora-text-to-image", True, "PASS", False),
    ("new model 23999 under 80% rejected", 23999, "gpt-image-3-aurora-text-to-image", False, "BELOW_FLOOR", False),
    ("new model 28000 = 93% warns and expands", 28000, "gpt-image-3-aurora-text-to-image", True, "BELOW_TARGET", False),
    ("new model 30001 above max rejected", 30001, "gpt-image-3-aurora-text-to-image", False, "ABOVE_MAX", True),
    ("adapter limit beats models.json (gpt-2.5 now 30000)", 20000, "gpt-image-2-6/sunburst-text-to-image", False,
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


def _find_adapter():
    """The sibling Skill 74 adapter, or None. Same resolution rule the bridge uses."""
    env = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    if env is not None and env:
        return env if os.path.isfile(env) else None
    roots = [str(Path(__file__).resolve().parents[2]),
             os.path.join(os.path.expanduser("~"), ".openclaw", "skills"), "/data/.openclaw/skills"]
    for r in roots:
        for name in ("74-kie-live-adapter", "kie-live-adapter"):
            p = os.path.join(r, name, "scripts", "kie_live_adapter.py")
            if os.path.isfile(p):
                return p
    return None

def selftest():
    import tempfile
    failures = []
    saved = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    # Fix plan A5: the adapter is NOT blanked for the whole self-test. A green test that never
    # exercises the live prompt-budget path measures nothing about the live cap.
    os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)
    real = _find_adapter()
    if real is None:
        failures.append("FAIL no sibling Skill 74 adapter resolves: the live prompt-budget path "
                        "was never exercised, so this self-test would measure nothing")
    else:
        res = validate_prompt("x" * 19500, "gpt-image-2-6/sunburst-text-to-image")
        if not res["valid"]:
            failures.append("FAIL 19,500 chars must be compliant at the 20,000 owner cap via the "
                            "live adapter: %s" % res["errors"])
        if res.get("max") != 20000:
            failures.append("FAIL live adapter resolved max=%r, expected the owner cap 20000"
                            % res.get("max"))
        if not str(res.get("limit_source") or "").startswith("owner-ruling:"):
            failures.append("FAIL the live adapter did not answer for the 2.6 cap "
                            "(limit_source=%r) — the models.json fallback was measured instead"
                            % res.get("limit_source"))
    # The models.json fallback is still proven, but explicitly as the FALLBACK path.
    os.environ["KIE_LIVE_ADAPTER_PATH"] = ""
    _run_cases(STATIC_CASES, failures)
    res = validate_prompt("   " + "m" * 4500 + "   ", "wan/2-7-image")
    if res["chars"] != 4500:
        failures.append("FAIL whitespace not stripped before count: %s" % res["chars"])
    res = validate_prompt("x" * 100, "wan/2-7-image")
    if not any("ADD at least 4650" in e for e in res["errors"]):
        failures.append("FAIL below-floor message must name the exact chars to add: %s" % res["errors"])
    res = validate_prompt("x" * 5003, "wan/2-7-image")
    if not any("CUT exactly 3 chars" in e for e in res["errors"]):
        failures.append("FAIL above-max message must name the exact chars to cut: %s" % res["errors"])
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "kie_live_adapter.py")
        with open(script, "w") as fh:
            fh.write(FAKE_ADAPTER)
        os.environ["KIE_LIVE_ADAPTER_PATH"] = script
        _run_cases(ADAPTER_CASES, failures)
        os.environ["KIE_LIVE_ADAPTER_PATH"] = os.path.join(d, "missing.py")  # unreachable adapter -> models.json
        _run_cases([("adapter unreachable: models.json owner cap (2.6 = 20000)", CAP_26,
                     "gpt-image-2-6/sunburst-text-to-image", True, "PASS", False)], failures)
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
