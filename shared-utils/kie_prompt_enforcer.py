#!/usr/bin/env python3
"""kie_prompt_enforcer.py - the ONE Python enforcer of KIE prompt rule 12 (owner order 2026-10-05).

Every gate that checks the length of a KIE prompt imports this module. No gate keeps its own floor,
ceiling or band. The numbers come from Skill 74 `kie_live_adapter.py prompt-budget --check` (live
schema first, registry snapshot second, policy owner third); this module only runs that command and
turns its exit code into a verdict.

Rule 12 in one paragraph: a DESCRIPTIVE prompt (image prompt, video prompt, music style) is 95 to 100
percent of the model's maxLength, hard floor 80 percent (reject below), hard ceiling 100 percent (reject
above). A VERBATIM field (text-to-speech script, user lyrics) is exempt from the floor and keeps only the
ceiling. A model whose limit is UNKNOWN has no floor. Prompt writers rewrite automatically up to 3 tries
using the exact add/cut counts, then escalate (see rewrite_to_band).

Adapter exit codes: 0 in range, 3 below the floor (prints the characters to ADD), 4 above the max
(prints the characters to CUT). STDLIB ONLY. Never reads or prints a key (the adapter resolves it).

Environment: KIE_LIVE_ADAPTER_PATH overrides the adapter location. The empty string disables the
adapter; then only a caller-supplied fallback_max (the policy owner's recorded limit) can answer, and
without one the verdict is ADAPTER_UNAVAILABLE and ok is False (fail closed).
"""
import json
import os
import subprocess
import sys

FLOOR_PCT, TARGET_PCT = 80, 95  # percent of the model max; integer math, same as the adapter
TIMEOUT = 90  # the first call may read the live catalog and a schema (spaced); later calls hit the cache
TRIES = 3  # rewrite attempts before escalation (owner rule 12)


# The adapter is asked once per model per process. Its answer carries the model's numbers (max, floor, target); later
# prompts for that model are judged locally with the same arithmetic as its --check (a render fan-out would otherwise
# start one process per slide). tests/unit/kie-prompt-enforcer-and-gates.test.py proves the two agree.
_NUMBERS = {}  # (adapter path, model) -> {max, floor, target_min, verbatim, source, warnings}


def clear_cache():
    _NUMBERS.clear()


class PromptBudgetError(ValueError):
    """The prompt is outside the rule 12 band. str(e) names the exact characters to add or cut."""

    def __init__(self, verdict):
        self.verdict = verdict
        super().__init__(verdict["message"])


class PromptBudgetEscalation(PromptBudgetError):
    """Three automatic rewrites did not bring the prompt into the band: a human decides."""


def budget(max_chars):
    """Floor and target for a model max. Identical integer math to the adapter's budget()."""
    m = int(max_chars)
    return {"max": m, "floor": -(-m * FLOOR_PCT // 100), "target_min": -(-m * TARGET_PCT // 100), "target_max": m}


def find_adapter():
    env = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    if env is not None:
        return env if env and os.path.isfile(env) else None
    here = os.path.dirname(os.path.abspath(__file__))
    roots = [os.path.abspath(os.path.join(here, "..")), os.environ.get("OPENCLAW_SKILLS_DIR") or "",
             os.path.join(os.path.expanduser("~"), ".openclaw", "skills"), "/data/.openclaw/skills"]
    for r in roots:
        for name in ("74-kie-live-adapter", "kie-live-adapter"):
            p = os.path.join(r, name, "scripts", "kie_live_adapter.py") if r else ""
            if p and os.path.isfile(p):
                return p
    return None


def _run_adapter(model, text):
    """-> (returncode, parsed JSON) or None when the adapter cannot answer."""
    path = find_adapter()
    if not path:
        return None
    try:
        p = subprocess.run([sys.executable, path, "prompt-budget", "--model", model, "--check", "--prompt-file", "-",
                            "--json"], input=text, capture_output=True, text=True, timeout=TIMEOUT,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        got = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if not (isinstance(got.get("data"), dict) and got["data"].get("status")):
        return None
    return p.returncode, got


def _verdict(status, chars, **kw):
    v = {"ok": True, "status": status, "chars": chars, "max": None, "floor": None, "target_min": None,
         "add": None, "cut": None, "source": None, "warnings": [], "message": ""}
    v.update(kw)
    return v


def _from_numbers(model, chars, mx, source, verbatim, warnings, nums=None):
    """Apply the band to a character count from known numbers: the adapter's own (nums) or, as the policy owner's
    fallback, a max alone. Messages match the adapter's."""
    b = nums if nums and nums.get("floor") is not None else budget(mx)
    if chars > mx:
        return _verdict("ABOVE_MAX", chars, ok=False, max=mx, cut=chars - mx, source=source, warnings=warnings,
                        message="prompt is %d chars; max is %d; CUT exactly %d chars" % (chars, mx, chars - mx))
    if not verbatim and chars < b["floor"]:
        return _verdict("BELOW_FLOOR", chars, ok=False, max=mx, floor=b["floor"], target_min=b["target_min"],
                        add=b["floor"] - chars, source=source, warnings=warnings,
                        message="prompt is %d chars (%.1f%% of max %d); floor is %d: ADD at least %d chars (%d to reach "
                                "the 95%% target of %d)" % (chars, 100.0 * chars / mx, mx, b["floor"],
                                                           b["floor"] - chars, b["target_min"] - chars, b["target_min"]))
    st = "OK"
    if not verbatim and chars < b["target_min"]:
        st = "BELOW_TARGET"
        warnings = warnings + ["prompt is %d chars; target is 95-100%% of %d: add %d chars" % (
            chars, mx, b["target_min"] - chars)]
    return _verdict(st, chars, max=mx, floor=None if verbatim else b["floor"],
                    target_min=None if verbatim else b["target_min"], source=source, warnings=warnings)


def check(model, text, kind="descriptive", fallback_max=None):
    """Judge one prompt against rule 12. kind: "descriptive" (floor and ceiling) or "verbatim" (ceiling only).
    Returns a verdict dict: ok, status, chars, max, floor, target_min, add, cut, source, warnings, message.
    ok is False for BELOW_FLOOR, ABOVE_MAX and ADAPTER_UNAVAILABLE. BELOW_TARGET (80 to 95 percent) is ok with a warning."""
    if kind not in ("descriptive", "verbatim"):
        raise ValueError("kind must be 'descriptive' or 'verbatim', got %r" % (kind,))
    text = text if isinstance(text, str) else str(text)
    nums = _NUMBERS.get((find_adapter(), model))
    if nums:
        return _from_numbers(model, len(text.strip()), nums["max"], nums["source"], kind == "verbatim" or nums["verbatim"],
                             list(nums["warnings"]), nums)
    return _check_uncached(model, text, kind, fallback_max)


def _check_uncached(model, text, kind, fallback_max):
    chars = len(text.strip())
    verbatim = kind == "verbatim"
    got = _run_adapter(model, text)
    if got is None:
        if isinstance(fallback_max, int) and fallback_max > 0:
            return _from_numbers(model, chars, fallback_max, "policy-owner fallback (Skill 74 adapter unavailable)",
                                 verbatim, ["Skill 74 adapter unavailable; limit taken from the policy owner's record"])
        return _verdict("ADAPTER_UNAVAILABLE", chars, ok=False,
                        message="Skill 74 kie_live_adapter.py prompt-budget is unavailable for %s and no policy-owner limit "
                                "was supplied: refusing (fail closed). Install or update Skill 74." % model)
    rc, r = got
    d = r["data"]
    warns = list(r.get("warnings") or [])
    mx = d.get("max")
    src = d.get("limit_source")
    if isinstance(mx, int) and (isinstance(d.get("floor"), int) or d.get("status") == "VERBATIM"):
        _NUMBERS[(find_adapter(), model)] = {"max": mx, "floor": d.get("floor"), "target_min": d.get("target_min"),
                                             "verbatim": d.get("status") == "VERBATIM", "source": src, "warnings": warns}
    if rc == 4:
        return _verdict("ABOVE_MAX", chars, ok=False, max=mx, cut=d.get("cut"), source=src, warnings=warns,
                        message=(r.get("error") or {}).get("msg") or "prompt above max")
    if rc == 3:
        if verbatim:  # exempt from the floor; the ceiling already passed
            return _verdict("VERBATIM_EXEMPT", chars, max=mx, source=src, warnings=warns)
        return _verdict("BELOW_FLOOR", chars, ok=False, max=mx, floor=d.get("floor"), target_min=d.get("target_min"),
                        add=d.get("add_to_floor"), source=src, warnings=warns,
                        message=(r.get("error") or {}).get("msg") or "prompt below floor")
    if mx is None and isinstance(fallback_max, int) and fallback_max > 0 and d.get("status") in ("UNKNOWN", "NO_PROMPT_FIELD"):
        # the adapter knows no limit for this model: the policy owner's recorded limit (Skill 66, 67, 68 models.json) applies
        return _from_numbers(model, chars, fallback_max, "policy-owner limit (the adapter has none)", verbatim, warns)
    if r.get("state") == "fail":  # the adapter itself failed (bad request): never read as a pass
        return _verdict("ADAPTER_UNAVAILABLE", chars, ok=False, warnings=warns,
                        message="Skill 74 prompt-budget failed for %s: %s" % (model, (r.get("error") or {}).get("msg")))
    st = d.get("status") or "OK"
    return _verdict(st if st != "VERBATIM" else "VERBATIM_EXEMPT", chars, max=mx, floor=d.get("floor"),
                    target_min=d.get("target_min"), source=src, warnings=warns)


def budget_for(model, fallback_max=None):
    """The rule 12 numbers for a model without judging a prompt: {max, floor, target_min, source}, or None when
    the limit is UNKNOWN (no schema limit and no policy-owner limit) or the adapter is unavailable. A writer uses
    this to size a prompt (for example to split one prompt across several authoring units)."""
    v = check(model, "", "descriptive", fallback_max)
    if v["max"] is None or v["floor"] is None:
        return None
    return {"max": v["max"], "floor": v["floor"], "target_min": v["target_min"], "source": v["source"]}


def require(model, text, kind="descriptive", fallback_max=None):
    """check() that raises PromptBudgetError (a ValueError) when the prompt is out of the band."""
    v = check(model, text, kind, fallback_max)
    if not v["ok"]:
        raise PromptBudgetError(v)
    return v


def problems(model, text, kind="descriptive", fallback_max=None):
    """Gate form: [] when the prompt is in the band, else one message that names the exact add or cut count."""
    v = check(model, text, kind, fallback_max)
    return [] if v["ok"] else [v["message"]]


def rewrite_to_band(model, text, rewriter, kind="descriptive", fallback_max=None, tries=TRIES):
    """Prompt-writer loop: check; when out of band call rewriter(text, verdict) for a new text and check again,
    up to `tries` rewrites (default 3). The verdict carries the exact add / cut counts for the rewriter.
    Returns (text, verdict) once in band; raises PromptBudgetEscalation after the last failed rewrite."""
    v = check(model, text, kind, fallback_max)
    for _ in range(tries):
        if v["ok"]:
            return text, v
        text = rewriter(text, v)
        v = check(model, text, kind, fallback_max)
    if v["ok"]:
        return text, v
    raise PromptBudgetEscalation(dict(v, message="%d automatic rewrites did not fix the prompt; escalate. Last verdict: %s"
                                      % (tries, v["message"])))
