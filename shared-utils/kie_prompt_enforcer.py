#!/usr/bin/env python3
"""kie_prompt_enforcer.py - compatibility surface for the ONE canonical prompt policy.

F18 (2026-11-07): the band, the counter and the freeze live in
`shared-utils/prompt_policy.py`. This module is a thin adapter kept so every existing
caller (`KPE.check`, `require`, `problems`, `budget_for`, `rewrite_to_band`,
`check_count`) keeps working while there is still exactly ONE validator. It holds no
band of its own.

Strict production band (policy 2.0.0): 95-100 percent PASSES; below 95 percent FAILS
and must be revised; below 80 percent is a particularly clear hard failure; above the
documented maximum FAILS; an UNKNOWN maximum REFUSES a pass. The old 80-to-below-95
warning-only path is removed.

Numbers come from the existing Skill 74 adapter (`kie_live_adapter.py prompt-budget`):
live schema first, registry snapshot second, policy owner third, and a caller-supplied
`fallback_max` only when the adapter cannot answer. This module caches one resolved
limit per model per process so a render fan-out does not start one process per slide.

STDLIB ONLY. Never reads or prints a key (the adapter resolves it).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import prompt_policy as _policy  # noqa: E402

POLICY_VERSION = _policy.POLICY_VERSION
TIMEOUT = 90  # the first call may read the live catalog and a schema (spaced)
TRIES = 3  # automatic rewrite attempts before escalation (owner rule 12)

# (adapter path, model) -> resolved limit dict from prompt_policy.resolve_limit()
_NUMBERS = {}


def clear_cache():
    _NUMBERS.clear()


class PromptBudgetError(ValueError):
    """The prompt is outside the strict band. str(e) names the exact characters to add or cut."""

    def __init__(self, verdict):
        self.verdict = verdict
        super().__init__(verdict["message"])


class PromptBudgetEscalation(PromptBudgetError):
    """Three automatic rewrites did not bring the prompt into the band: a human decides."""


def budget(max_chars):
    """Band numbers for a verified maximum. Identical to the policy's integer math."""
    return _policy.band_numbers(max_chars)


def find_adapter():
    return _policy.find_adapter()


def _resolve(model, fallback_max=None):
    key = (find_adapter(), model, fallback_max)
    if key in _NUMBERS:
        return _NUMBERS[key]
    got = _policy.resolve_limit(model, adapter_path=find_adapter(), fallback_max=fallback_max,
                                timeout=TIMEOUT)
    if got.get("ok") and got.get("source"):
        _NUMBERS[key] = got
    return got


def _adapter_unavailable(got, model):
    """Resolution failed and no policy-owner limit answered: fail closed."""
    v = _policy.evaluate("", model=model, max_chars=None, limit={"max": None},
                         max_source=got.get("source"))
    v["status"] = "ADAPTER_UNAVAILABLE"
    v["ok"] = False
    v["message"] = ("Skill 74 kie_live_adapter.py prompt-budget is unavailable for %s and no "
                    "policy-owner limit was supplied: refusing (fail closed). Install or update "
                    "Skill 74." % model)
    return v


def check(model, text, kind="descriptive", fallback_max=None):
    """Judge one prompt against the strict band.

    kind: "descriptive" (floor and ceiling) or "verbatim" (ceiling only).
    Returns the policy verdict dict: ok, status, count/chars, max, floor, target_min,
    add, cut, ratio, source, model, schema_version, policy_version, prompt_sha256,
    warnings, message.
    """
    if kind not in ("descriptive", "verbatim"):
        raise ValueError("kind must be 'descriptive' or 'verbatim', got %r" % (kind,))
    text = text if isinstance(text, str) else str(text)
    got = _resolve(model, fallback_max)
    if not got.get("ok") and got.get("max") is None and got.get("source") is None:
        return _adapter_unavailable(got, model)
    verdict = _policy.evaluate(
        text, model=model, unit="chars", kind=kind,
        max_chars=got.get("max"), max_source=got.get("source"),
        limit={"max": got.get("max")},
        verbatim=(kind == "verbatim") or bool(got.get("verbatim")),
        ceiling_only=bool(got.get("ceiling_only")),
        band_override=got.get("band_override"),
        schema_version=got.get("schema_version"),
        provider=got.get("provider"))
    verdict["warnings"] = list(got.get("notes") or []) + list(verdict.get("warnings") or [])
    return verdict


def check_count(model, chars, kind="descriptive", fallback_max=None):
    """check() for a gate that holds a character COUNT (a receipt field) and not the text."""
    return check(model, "x" * int(chars), kind, fallback_max)


def budget_for(model, fallback_max=None):
    """The band numbers for a model without judging a prompt, or None when UNKNOWN."""
    v = check(model, "", "descriptive", fallback_max)
    if v["max"] is None or v["floor"] is None:
        return None
    return {"max": v["max"], "floor": v["floor"], "target_min": v["target_min"], "source": v["source"]}


def require(model, text, kind="descriptive", fallback_max=None):
    """check() that raises PromptBudgetError when the prompt is out of band."""
    v = check(model, text, kind, fallback_max)
    if not v["ok"]:
        raise PromptBudgetError(v)
    return v


def problems(model, text, kind="descriptive", fallback_max=None):
    """Gate form: [] when the prompt is in band, else one message naming the exact fix."""
    v = check(model, text, kind, fallback_max)
    return [] if v["ok"] else [v["message"]]


def rewrite_to_band(model, text, rewriter, kind="descriptive", fallback_max=None, tries=TRIES):
    """Check; call rewriter(text, verdict) for a new text and check again, up to `tries`."""
    v = check(model, text, kind, fallback_max)
    for _ in range(tries):
        if v["ok"]:
            return text, v
        text = rewriter(text, v)
        v = check(model, text, kind, fallback_max)
    if v["ok"]:
        return text, v
    raise PromptBudgetEscalation(dict(
        v, message="%d automatic rewrites did not fix the prompt; escalate. Last verdict: %s"
                   % (tries, v["message"])))


# >>> BEGIN LAST-KNOWN LIMITS (generated by scripts/embed-kie-prompt-enforcer.py; do not edit by hand)
# Registry snapshot of the prompt maxLength per model id (descriptive prompt fields only). A gate passes
# last_known(model) as fallback_max, so the live Skill 74 answer always wins and this table only keeps the
# strict band (95-100 percent passes, an unknown maximum refuses) enforced when the adapter is not installed.
LAST_KNOWN_MAX = {
    "ai-music-api/add-vocals": 1000,
    "ai-music-api/extend": 1000,
    "ai-music-api/generate": 1000,
    "ai-music-api/generate-lyrics": 200,
    "ai-music-api/mashup": 1000,
    "ai-music-api/sounds": 500,
    "ai-music-api/upload-and-cover-audio": 1000,
    "ai-music-api/upload-and-extend-audio": 1000,
    "bytedance/seedance-1.5-pro": 20000,
    "bytedance/seedance-2": 20000,
    "bytedance/seedance-2-5": 30000,
    "bytedance/seedance-2-fast": 20000,
    "bytedance/seedance-2-mini": 20000,
    "bytedance/seedream": 5000,
    "bytedance/seedream-v4-edit": 5000,
    "bytedance/seedream-v4-text-to-image": 5000,
    "bytedance/v1-lite-image-to-video": 10000,
    "bytedance/v1-lite-text-to-video": 10000,
    "bytedance/v1-pro-fast-image-to-video": 10000,
    "bytedance/v1-pro-image-to-video": 10000,
    "bytedance/v1-pro-text-to-video": 10000,
    "flux-2/flex-image-to-image": 5000,
    "flux-2/flex-text-to-image": 5000,
    "flux-2/pro-image-to-image": 5000,
    "flux-2/pro-text-to-image": 5000,
    "gemini-omni-video": 20000,
    "google/gemini-omni-flash-1-1": 20000,
    "google/imagen4": 5000,
    "google/imagen4-fast": 5000,
    "google/imagen4-ultra": 5000,
    "google/nano-banana": 5000,
    "google/nano-banana-edit": 5000,
    "gpt-image-2-5-flare-image-to-image": 20000,
    "gpt-image-2-5-flare-text-to-image": 20000,
    "gpt-image-2-5-sunburst-image-to-image": 20000,
    "gpt-image-2-5-sunburst-text-to-image": 20000,
    "gpt-image-2-image-to-image": 20000,
    "gpt-image-2-text-to-image": 20000,
    "grok-imagine-image-2-0/image-edit": 390000,
    "grok-imagine-image-2-0/segment-edit": 390000,
    "grok-imagine-video-1-5-preview": 4096,
    "grok-imagine/image-to-image": 390000,
    "grok-imagine/image-to-video": 5000,
    "grok-imagine/text-to-image": 5000,
    "grok-imagine/text-to-video": 5000,
    "hailuo/02-image-to-video-pro": 1500,
    "hailuo/02-image-to-video-standard": 1500,
    "hailuo/02-text-to-video-pro": 1500,
    "hailuo/02-text-to-video-standard": 1500,
    "hailuo/2-3-image-to-video-pro": 5000,
    "hailuo/2-3-image-to-video-standard": 5000,
    "happyhorse-1-1/image-to-video": 5000,
    "happyhorse-1-1/reference-to-video": 5000,
    "happyhorse-1-1/text-to-video": 4999,
    "happyhorse/image-to-video": 5000,
    "happyhorse/reference-to-video": 5000,
    "happyhorse/text-to-video": 5000,
    "happyhorse/video-edit": 5000,
    "ideogram/character": 5000,
    "ideogram/character-edit": 5000,
    "ideogram/character-remix": 5000,
    "ideogram/v3-edit": 5000,
    "ideogram/v3-remix": 5000,
    "ideogram/v3-text-to-image": 5000,
    "infinitalk/from-audio": 5000,
    "kling-2.6/image-to-video": 1000,
    "kling-2.6/motion-control": 2500,
    "kling-2.6/text-to-video": 1000,
    "kling-3.0-omni/image-to-video": 3072,
    "kling-3.0-omni/reference-to-video": 3072,
    "kling-3.0-omni/text-to-video": 3072,
    "kling-3.0-omni/transformation": 3072,
    "kling-3.0/motion-control": 2500,
    "kling/ai-avatar-pro": 5000,
    "kling/ai-avatar-standard": 5000,
    "kling/v2-1-master-image-to-video": 5000,
    "kling/v2-1-master-text-to-video": 5000,
    "kling/v2-1-pro": 5000,
    "kling/v2-1-standard": 5000,
    "kling/v2-5-turbo-image-to-video-pro": 2500,
    "kling/v2-5-turbo-text-to-video-pro": 2500,
    "kling/v3-turbo-image-to-video": 2500,
    "kling/v3-turbo-text-to-video": 2500,
    "minimax-h3/image-to-video": 7000,
    "minimax-h3/reference-to-video": 7000,
    "minimax-h3/text-to-video": 7000,
    "nano-banana-2": 20000,
    "nano-banana-2-lite": 20000,
    "nano-banana-pro": 10000,
    "omnihuman-1-5": 300,
    "pixverse-v6/extend": 5000,
    "pixverse-v6/image-to-video": 5000,
    "pixverse-v6/reference-to-video": 5000,
    "pixverse-v6/text-to-video": 5000,
    "pixverse-v6/transition": 5000,
    "qwen/image-edit": 2000,
    "qwen/image-to-image": 5000,
    "qwen/text-to-image": 5000,
    "qwen2-1/image-to-image": 5000,
    "qwen2-1/text-to-image": 5000,
    "qwen2/image-edit": 800,
    "qwen2/text-to-image": 800,
    "qwen3/image-to-image": 5000,
    "qwen3/pro-image-to-image": 5000,
    "qwen3/pro-text-to-image": 5000,
    "qwen3/text-to-image": 5000,
    "runway": 1800,
    "seedream/4.5-edit": 3000,
    "seedream/4.5-text-to-image": 3000,
    "seedream/5-flash-image-to-image": 5000,
    "seedream/5-flash-layer-decomposition": 5000,
    "seedream/5-flash-text-to-image": 5000,
    "seedream/5-lite-image-to-image": 3000,
    "seedream/5-lite-text-to-image": 3000,
    "seedream/5-pro-image-to-image": 5000,
    "seedream/5-pro-layer-decomposition": 5000,
    "seedream/5-pro-text-to-image": 5000,
    "wan/2-2-a14b-image-to-video-turbo": 5000,
    "wan/2-2-a14b-speech-to-video-turbo": 5000,
    "wan/2-2-a14b-text-to-video-turbo": 5000,
    "wan/2-5-image-to-video": 800,
    "wan/2-5-text-to-video": 800,
    "wan/2-6-image-to-video": 5000,
    "wan/2-6-text-to-video": 5000,
    "wan/2-6-video-to-video": 5000,
    "wan/2-7-image": 5000,
    "wan/2-7-image-pro": 5000,
    "wan/2-7-image-to-video": 5000,
    "wan/2-7-r2v": 5000,
    "wan/2-7-text-to-video": 5000,
    "wan/2-7-videoedit": 5000,
    "wan/3-0-video": 20000,
    "wan/3-0-video-prime": 20000,
    "z-image": 1000,
}

def last_known(model):
    """Last-known prompt maxLength for a model id, or None when the id is not in the table."""
    return LAST_KNOWN_MAX.get(model)
# <<< END LAST-KNOWN LIMITS
