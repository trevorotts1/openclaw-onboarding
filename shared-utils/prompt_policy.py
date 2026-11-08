#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prompt_policy.py - THE canonical prompt-policy service (F18, 2026-11-07).

Every gate that measures a prompt, freezes a provider payload, or enforces a copy
profile calls THIS module. No gate keeps a second band, a second counter or a second
freeze. The band is the strict production band:

    ratio = counted_code_points / verified_provider_max
    95 <= ratio*100 <= 100      PASS
    80 <= ratio*100 < 95        PASS with a WARN: warn and expand (BELOW_TARGET names the ADD)
    below 80 percent            FAIL, particularly clear hard failure (BELOW_FLOOR)
    above the documented max    FAIL (ABOVE_MAX)
    maximum UNKNOWN             FAIL, never a silent PASS (UNKNOWN_MAX)

The 80-to-below-95 band is the OWNER RULE's warn-and-expand middle band, restored from the
owner order of 2026-10-05 (07-kie-setup/references/kie-common-rules.md section 12): "Hard floor:
80 percent (below it, reject and rewrite). Hard ceiling: 100 percent (above it, reject).
80 to 95 percent: warn and expand." The order outranks the later code that made 94 percent fail,
and that code never amended the order.

COUNTING (Image Guide v5 convention, one implementation)
  * strip a surrounding document fence (```lang ... ```) and leading YAML front matter
    (metadata that is not part of the request);
  * NFC-normalize, then trim ONCE;
  * count Unicode code points, including internal whitespace, newlines and punctuation;
  * JSON escaping is never applied to the counted string;
  * the returned `counted_text` is the exact string that is submitted and hashed.
  `text_sha256()` hashes the UTF-8 bytes of that same string.

LIMIT RESOLUTION
  The maximum is never hard-coded here. `resolve_limit()` asks the existing Skill 74
  adapter (`kie_live_adapter.py prompt-budget --model ID --json`), which resolves the
  live provider schema first, then its registry snapshot, then the policy owner. A
  caller may pass a pre-resolved `limit` (the shared enforcer caches one per model) or
  a `fallback_max` recorded by a policy owner, and the source is always recorded.

FREEZE / BIND
  `freeze()` measures, hashes and returns the receipt for the FINAL prompt plus the
  canonical payload hash. `assert_payload()` re-derives the prompt from the payload
  that will actually be sent, refuses drift, re-runs the band, and re-hashes the
  payload. A review reference is bound to the same hash, so a review of an earlier
  authored prompt never authorizes a different request. `apply_input_extra()` rejects
  a late prompt override unless the caller asks for full revalidation.

COPY PROFILES ARE SEPARATE
  `evaluate_copy()` enforces a copy profile's own character/word limits on normalized
  visible text. It never touches the image-prompt band and never computes a percentage
  of a model maximum. `cta_requirement()` resolves CTA precedence explicitly: a
  section contract's own prohibition wins over a profile-wide "CTA every section"
  requirement; the profile requirement applies only where the section is silent.

STDLIB ONLY. No secrets read, no network except the adapter subprocess it is asked for.
"""
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import unicodedata

POLICY_VERSION = "prompt-policy/2.0.0"

# The strict production band. Percentages only: never a model maximum.
FLOOR_PERCENT = 95          # integral lower bound: ceil(0.95 * verified maximum)
TARGET_PERCENT = 95         # the target range starts at the same bound
CEILING_PERCENT = 100
HARD_FLOOR_PERCENT = 80     # below this is a particularly clear hard failure

UNITS = ("chars", "bytes", "tokens")

_FENCE_OPEN = re.compile(r"\A\s*```[^\n]*\n")
_FENCE_CLOSE = re.compile(r"\n```\s*\Z")
_FRONT_MATTER = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.S)


class PromptPolicyError(ValueError):
    """The prompt is outside the strict production band."""

    def __init__(self, verdict):
        self.verdict = verdict
        super().__init__(verdict.get("message") or verdict.get("status") or "prompt policy failed")


class PromptOverrideRejected(PromptPolicyError):
    """A later prompt override changed the request after measurement and was refused."""


# --------------------------------------------------------------------------- counting
def strip_document_fence(text):
    """Remove a byte-order mark, a surrounding Markdown fence, and leading front matter.

    Two passes: front matter may precede a fence, or sit INSIDE one. Stripping only in one
    order left fenced metadata in the counted string and inflated the count.
    """
    s = str(text).lstrip("﻿")
    for _ in range(2):
        s = _FRONT_MATTER.sub("", s)
        s = _FENCE_OPEN.sub("", s, count=1)
        s = _FENCE_CLOSE.sub("", s, count=1)
    return s


def normalize_text(text):
    """THE counted string: fence/metadata removed, NFC-normalized, trimmed ONCE."""
    return unicodedata.normalize("NFC", strip_document_fence(text)).strip()


def count_text(text):
    """Unicode code points of the counted string (internal whitespace included)."""
    return len(normalize_text(text))


def count_in_unit(text, unit):
    """Count in the provider's own unit. Tokens are never guessed."""
    if unit == "chars":
        return count_text(text)
    if unit == "bytes":
        return len(normalize_text(text).encode("utf-8"))
    return None  # tokens need a provider tokenizer; an estimate is never a verdict


def text_sha256(text):
    """SHA-256 of the exact counted string that is submitted."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def payload_sha256(payload):
    """Canonical identity of the frozen provider payload."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- band math
def band_numbers(max_chars, *, floor_percent=None, target_min=None, target_max=None):
    """The band for one verified maximum. Integer math: ceiling, never floor rounding."""
    m = int(max_chars)
    pct = FLOOR_PERCENT if floor_percent is None else int(floor_percent)
    floor = -(-m * pct // 100)
    tmin = floor if target_min is None else int(target_min)
    tmax = m if target_max is None else int(target_max)
    return {"max": m, "floor": floor, "target_min": tmin, "target_max": tmax,
            "hard_floor": -(-m * HARD_FLOOR_PERCENT // 100),
            "floor_pct": pct, "ceiling_pct": CEILING_PERCENT}


def _ratio(n, m):
    return round(100.0 * n / m, 4) if m else None


def _verdict(status, ok, n, unit="chars", **kw):
    v = {"ok": ok, "status": status, "count": n, "chars": n if unit == "chars" else kw.pop("chars", None),
         "unit": unit, "max": None, "floor": None, "target_min": None, "target_max": None,
         "hard_floor": None, "add": None, "cut": None, "ratio": None,
         "source": None, "model": None, "provider": None, "schema_version": None,
         "policy_version": POLICY_VERSION, "kind": None, "counted_text": None,
         "prompt_sha256": None, "anatomy": None, "review_ref": None,
         "separate_limit": None, "band_status": None, "warnings": [], "problems": [],
         "message": ""}
    v.update(kw)
    return v


# --------------------------------------------------------------------------- resolver
def find_adapter():
    """Skill 74's live adapter, if installed."""
    env = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    if env is not None:
        return env if env and os.path.isfile(env) else None
    here = os.path.dirname(os.path.abspath(__file__))
    roots = [os.path.abspath(os.path.join(here, "..")), os.environ.get("OPENCLAW_SKILLS_DIR") or "",
             os.path.join(os.path.expanduser("~"), ".openclaw", "skills"), "/data/.openclaw/skills"]
    for r in roots:
        if not r:
            continue
        for name in ("74-kie-live-adapter", "kie-live-adapter"):
            p = os.path.join(r, name, "scripts", "kie_live_adapter.py")
            if os.path.isfile(p):
                return p
    return None


def resolve_limit(model, *, adapter_path=None, fallback_max=None, timeout=90):
    """Resolve the EXACT model's prompt maximum through the existing adapter.

    -> {"max", "unit", "source", "schema_version", "model", "provider", "verbatim",
        "ceiling_only", "band_override", "notes", "ok"}
    A fallback_max is the policy owner's recorded limit and is used only when the
    adapter cannot answer. An unresolvable limit returns ok False with max None.
    """
    out = {"model": model, "max": None, "unit": "chars", "source": None, "schema_version": None,
           "provider": None, "verbatim": False, "ceiling_only": False, "band_override": None,
           "notes": [], "ok": False}
    path = adapter_path if adapter_path is not None else find_adapter()
    if path:
        try:
            p = subprocess.run([sys.executable, path, "prompt-budget", "--model", model, "--json"],
                               capture_output=True, text=True, timeout=timeout,
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            got = json.loads(p.stdout or "{}")
            d = got.get("data") if isinstance(got, dict) else None
            if isinstance(d, dict) and d.get("status"):
                out.update(max=d.get("max"), source=d.get("limit_source"),
                           verbatim=bool(d.get("verbatim")),
                           ceiling_only=d.get("status") == "CEILING_ONLY",
                           schema_version=d.get("schema_version"),
                           provider=d.get("provider") or "kie",
                           band_override=d.get("band_override"),
                           notes=list(got.get("warnings") or []))
                if d.get("max") is None and isinstance(fallback_max, int) and fallback_max > 0:
                    out.update(max=fallback_max, source="policy-owner limit (adapter has none)")
                out["ok"] = isinstance(out["max"], int) and out["max"] > 0
                return out
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            out["notes"].append("Skill 74 prompt-budget unavailable: %s" % exc)
    if isinstance(fallback_max, int) and not isinstance(fallback_max, bool) and fallback_max > 0:
        out.update(max=fallback_max, source=out["source"] or "policy-owner fallback",
                   ok=True,
                   notes=out["notes"] + ["Skill 74 adapter unavailable; limit taken from the policy owner"])
    return out


# --------------------------------------------------------------------------- evaluate
def evaluate(text, *, model=None, provider=None, max_chars=None, max_source=None,
             unit="chars", kind="descriptive", ceiling_only=False, verbatim=False,
             limit=None, fallback_max=None, adapter_path=None, band_override=None,
             separate_limit=None, token_count=None, anatomy=None, review_ref=None,
             schema_version=None):
    """Judge one prompt against the strict production band.

    kind: "descriptive" (band) or "verbatim"/ceiling_only (ceiling only).
    limit: a pre-resolved dict from resolve_limit(); else one is resolved.
    separate_limit: {"unit": "tokens"|"bytes", "max": N} enforced in its own units.
    anatomy: callable(counted_text) -> list of problems (or {"problems": [...]}).
    review_ref: {"prompt_sha256": "..."} bound to the same counted string.
    """
    counted = normalize_text(text)
    if unit not in UNITS:
        raise ValueError("unit must be one of %s, got %r" % (UNITS, unit))
    verbatim = verbatim or kind == "verbatim"
    n = count_in_unit(counted, unit)
    sha = text_sha256(counted)

    resolved = None
    if isinstance(limit, dict) and max_chars is None:
        # A caller's pre-resolved limit (the shared enforcer caches one per model). Honoured
        # only when no explicit maximum was passed, so it can never override the caller.
        max_chars = limit.get("max")
        if max_source is None:
            max_source = limit.get("source")
        if schema_version is None:
            schema_version = limit.get("schema_version")
        if provider is None:
            provider = limit.get("provider")
    elif limit is None and (max_chars is None or band_override is not None):
        resolved = resolve_limit(model, adapter_path=adapter_path, fallback_max=fallback_max)
        if max_chars is None:
            max_chars = resolved.get("max")
        if max_source is None:
            max_source = resolved.get("source")
        if schema_version is None:
            schema_version = resolved.get("schema_version")
        if provider is None:
            provider = resolved.get("provider")
        if band_override is None:
            band_override = resolved.get("band_override")
        if resolved.get("verbatim"):
            verbatim = True
        if resolved.get("ceiling_only"):
            ceiling_only = True

    problems, warnings = [], list((resolved or {}).get("notes") or [])
    base = dict(model=model, provider=provider or "kie", schema_version=schema_version,
                source=max_source, kind=kind, counted_text=counted, prompt_sha256=sha,
                review_ref=review_ref)
    chars = len(counted)

    # -- the provider's separate documented limit, in its own units -------------
    sep = None
    if separate_limit is not None:
        sep = _separate_limit(counted, separate_limit, token_count)
        if not sep["ok"]:
            problems.append(sep["message"])

    # -- token/byte unit that cannot be measured ---------------------------------
    if n is None:
        msg = ("the provider limit for %s is denominated in tokens and no provider-measured "
               "token count was supplied; an estimate is never a verdict (refusing)" % model)
        problems.append(msg)
        v = _verdict("UNITS_UNVERIFIABLE", False, 0, unit, message=msg, problems=problems,
                     warnings=warnings, separate_limit=sep, **base)
        return _finish_anatomy(v, counted, anatomy)

    # -- unknown maximum can never pass ------------------------------------------
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars <= 0:
        msg = ("prompt maximum UNKNOWN for %s: no schema maxLength and no policy-owner limit; "
               "an unknown maximum cannot PASS" % (model,))
        problems.append(msg)
        v = _verdict("UNKNOWN_MAX", False, n, unit, message=msg, problems=problems,
                     warnings=warnings, separate_limit=sep, **base)
        return _finish_anatomy(v, counted, anatomy)

    m = int(max_chars)
    if band_override and all(isinstance(band_override.get(k), int)
                             for k in ("floor", "target_min", "target_max", "hard_max")):
        band = {"max": int(band_override["hard_max"]), "floor": int(band_override["floor"]),
                "target_min": int(band_override["target_min"]),
                "target_max": int(band_override["target_max"]),
                "hard_floor": int(band_override["floor"]),
                "floor_pct": None, "ceiling_pct": CEILING_PERCENT}
    else:
        band = band_numbers(m)
    if band["target_max"] > band["max"]:
        band["target_max"] = band["max"]
    ratio = _ratio(n, band["max"])

    kw = dict(base, max=band["max"],
              floor=None if (verbatim or ceiling_only) else band["floor"],
              target_min=None if (verbatim or ceiling_only) else band["target_min"],
              target_max=band["target_max"], hard_floor=band["hard_floor"], ratio=ratio,
              chars=chars, problems=problems, warnings=warnings, separate_limit=sep,
              source=base["source"] or ("owner-band" if band_override else None))

    if n > band["max"]:
        kw["cut"] = n - band["max"]
        msg = ("prompt is %d %s (%.1f%% of max %d); ABOVE the documented maximum: CUT exactly %d%s"
               % (n, unit, ratio, band["max"], kw["cut"], " chars" if unit == "chars" else " " + unit))
        if band_override and band_override.get("above_hard_max"):
            msg += " (%s)" % band_override["above_hard_max"]
        problems.append(msg)
        return _finish_anatomy(_verdict("ABOVE_MAX", False, n, unit, message=msg, **kw), counted, anatomy)

    if not verbatim and not ceiling_only and n < band["floor"]:
        kw["add"] = band["floor"] - n   # characters to add to reach the 95 percent target
        action = band_override.get("below_floor") if isinstance(band_override, dict) else None
        if action:
            # An owner band's own recorded below-floor action is still a rejection, never a warning.
            msg = ("prompt is %d %s (%.1f%% of max %d), below the owner band floor %d: ADD at least %d "
                   "%s of genuine specification (%s); a warning is not a pass" % (
                       n, unit, ratio, band["max"], band["floor"], kw["add"], unit, action))
            problems.append(msg)
            return _finish_anatomy(_verdict("BELOW_FLOOR", False, n, unit, message=msg, **kw),
                                   counted, anatomy)
        if n < band["hard_floor"]:
            # Owner rule section 12: below 80 percent is the hard reject. Name the clearance of the
            # 80 percent floor AND the 95 percent target, so the rewrite has one destination.
            floor_gap = band["hard_floor"] - n
            msg = ("prompt is %d %s (%.1f%% of max %d), below the %d percent floor: ADD at least %d %s "
                   "of genuine specification to reach %d, and ADD at least %d %s to reach the %d "
                   "target (reject and rewrite, never pad)" % (
                       n, unit, ratio, band["max"], HARD_FLOOR_PERCENT, floor_gap, unit,
                       band["hard_floor"], kw["add"], unit, band["floor"]))
            problems.append(msg)
            return _finish_anatomy(_verdict("BELOW_FLOOR", False, n, unit, message=msg, **kw),
                                   counted, anatomy)
        # 80 <= n < 95: the owner rule's warn-and-expand band. It PASSES with the warning and the
        # characters to add; only below 80 and above the documented maximum are rejections.
        msg = ("prompt is %d %s (%.1f%% of max %d), in the %d to %d percent band: ADD %d %s of genuine "
               "specification to reach the %d target (warn and expand)" % (
                   n, unit, ratio, band["max"], HARD_FLOOR_PERCENT, FLOOR_PERCENT, kw["add"], unit,
                   band["floor"]))
        warnings.append(msg)

    if not verbatim and not ceiling_only and n > band["target_max"]:
        kw["cut"] = n - band["target_max"]
        msg = ("prompt is %d %s (%.1f%% of max %d), above the target ceiling %d: TRIM %d; the "
               "target range is %d-%d" % (n, unit, ratio, band["max"], band["target_max"],
                                          kw["cut"], band["target_min"], band["target_max"]))
        if band_override:
            # An owner band's own recorded action above target is TRIM, never REFUSE; it is
            # reported as TRIM with a warning and never as at-target.
            warnings.append(msg)
            return _finish_anatomy(_verdict("TRIM", True, n, unit, message="",
                                            **dict(kw, warnings=warnings)), counted, anatomy)
        problems.append(msg)
        return _finish_anatomy(_verdict("ABOVE_TARGET", False, n, unit, message=msg, **kw), counted, anatomy)

    if problems:
        msg = "; ".join(problems)
        return _finish_anatomy(_verdict("SEPARATE_LIMIT_FAIL", False, n, unit, message=msg, **kw),
                               counted, anatomy)

    status = ("VERBATIM_EXEMPT" if verbatim else "CEILING_ONLY" if ceiling_only
              else "BELOW_TARGET" if n < band["floor"] else "PASS")
    v = _verdict(status, True, n, unit, message="", **kw)
    if review_ref is not None:
        v = _bind_review(v, sha)
    return _finish_anatomy(v, counted, anatomy)


def _separate_limit(counted, spec, token_count):
    unit = str((spec or {}).get("unit") or "").lower()
    mx = (spec or {}).get("max")
    if not isinstance(mx, int) or isinstance(mx, bool) or mx <= 0:
        return {"unit": unit, "max": None, "count": None, "ok": False,
                "message": "a separate %s limit is documented but its maximum is UNKNOWN; refusing" % (unit or "provider")}
    if unit == "bytes":
        n = len(counted.encode("utf-8"))
    elif unit == "tokens":
        n = token_count if isinstance(token_count, int) and not isinstance(token_count, bool) else None
        if n is None:
            return {"unit": unit, "max": mx, "count": None, "ok": False,
                    "message": ("a separate %d-token limit applies and no provider-measured token count "
                                "was supplied; refusing rather than guessing tokens" % mx)}
    elif unit == "chars":
        n = len(counted)
    else:
        return {"unit": unit, "max": mx, "count": None, "ok": False,
                "message": "separate limit unit %r is not measurable; refusing" % (unit,)}
    ok = n <= mx
    return {"unit": unit, "max": mx, "count": n, "ok": ok,
            "message": "" if ok else "prompt is %d %s, over the separate documented %d-%s limit (CUT %d)" % (
                n, unit, mx, unit, n - mx)}


def _bind_review(verdict, sha):
    ref = verdict.get("review_ref")
    bound = None
    if isinstance(ref, dict):
        bound = ref.get("prompt_sha256")
    elif isinstance(ref, str):
        bound = ref
    if bound is None:
        return verdict
    if bound != sha:
        verdict["ok"] = False
        verdict["status"] = "REVIEW_STALE"
        verdict["problems"] = verdict["problems"] + [
            "the review was performed on prompt sha256 %s but the request carries %s; re-review the "
            "frozen prompt before sending" % (bound, sha)]
        verdict["message"] = "; ".join(verdict["problems"])
    return verdict


def _finish_anatomy(verdict, counted, anatomy):
    """Run the anatomy/quality rules against the SAME counted string, then bind."""
    if anatomy is None:
        return verdict
    try:
        got = anatomy(counted)
    except Exception as exc:  # an anatomy rule that cannot run is a failure, never a pass
        got = ["anatomy check raised %s" % exc]
    if isinstance(got, dict):
        got = got.get("problems") or []
    anatomy_problems = [str(x) for x in (got or [])]
    verdict["anatomy"] = {"ok": not anatomy_problems, "problems": anatomy_problems}
    if anatomy_problems:
        verdict["band_status"] = verdict["status"]   # the length band's own verdict
        verdict["ok"] = False
        if verdict["status"] == "PASS":
            verdict["status"] = "ANATOMY_FAIL"
        verdict["problems"] = verdict["problems"] + anatomy_problems
        verdict["message"] = "; ".join(verdict["problems"])
    return verdict


def require(text, **kw):
    """evaluate() that raises PromptPolicyError unless the verdict passes."""
    v = evaluate(text, **kw)
    if not v["ok"]:
        raise PromptPolicyError(v)
    return v


def problems(text, **kw):
    """Gate form: [] when the prompt passes, else one message naming the exact fix."""
    v = evaluate(text, **kw)
    return [] if v["ok"] else [v["message"] or v["status"]]


def rewrite_to_band(text, rewriter, *, tries=3, **kw):
    """Check; call rewriter(text, verdict) for a new text and check again, up to `tries`."""
    v = evaluate(text, **kw)
    for _ in range(int(tries)):
        if v["ok"]:
            return v["counted_text"], v
        text = rewriter(v["counted_text"], v)
        v = evaluate(text, **kw)
    if v["ok"]:
        return v["counted_text"], v
    raise PromptPolicyError(dict(v, message="%d rewrites did not fix the prompt; escalate. Last: %s"
                                         % (tries, v["message"])))


# --------------------------------------------------------------------------- freeze/bind
def freeze(text, *, model=None, provider=None, max_chars=None, max_source=None, unit="chars",
           kind="descriptive", limit=None, fallback_max=None, adapter_path=None,
           band_override=None, separate_limit=None, token_count=None, anatomy=None,
           review_ref=None, schema_version=None, authored_text=None, job_id=None):
    """Freeze the FINAL prompt and payload identity. Returns the receipt.

    The receipt's "prompt" key is the exact string that must be submitted; its
    "final_prompt_sha256" is the hash of that same string. A review reference is bound
    to it. `authored_text` is optional provenance only and never overrides the final.
    """
    v = evaluate(text, model=model, provider=provider, max_chars=max_chars,
                 max_source=max_source, unit=unit, kind=kind, limit=limit,
                 fallback_max=fallback_max, adapter_path=adapter_path,
                 band_override=band_override, separate_limit=separate_limit,
                 token_count=token_count, anatomy=anatomy, review_ref=review_ref,
                 schema_version=schema_version)
    receipt = {
        "policy_version": POLICY_VERSION,
        "model": model,
        "provider": provider or "kie",
        "schema_version": schema_version,
        "unit": unit,
        "kind": kind,
        "prompt": v["counted_text"],
        "authored_prompt_sha256": text_sha256(authored_text) if authored_text is not None else None,
        "final_prompt_sha256": v["prompt_sha256"],
        "count": v["count"],
        "min": v["floor"],
        "max": v["max"],
        "target_min": v["target_min"],
        "target_max": v["target_max"],
        "ratio": v["ratio"],
        "limit_source": v["source"],
        "anatomy": v["anatomy"],
        "review_ref": review_ref,
        "job_id": job_id,
        "verdict": {k: v[k] for k in ("ok", "status", "band_status", "message", "problems",
                                      "warnings", "separate_limit")},
    }
    receipt["payload_fingerprint_inputs"] = {
        "model": model, "final_prompt_sha256": v["prompt_sha256"], "unit": unit}
    return receipt


def assert_payload(payload, *, frozen=None, input_key="input", prompt_key="prompt",
                   model=None, max_chars=None, max_source=None, unit="chars", kind="descriptive",
                   anatomy=None, review_ref=None, adapter_path=None, fallback_max=None,
                   band_override=None, schema_version=None):
    """Gate the payload that will ACTUALLY be sent. Never trust a self-reported count.

    -> {"ok", "status", "prompt", "prompt_sha256", "payload_sha256", "verdict", "problems"}
    A payload prompt that differs from the frozen prompt is PROMPT_OVERRIDE_REJECTED.
    """
    actual = _payload_prompt(payload, input_key, prompt_key)
    if actual is None:
        return {"ok": False, "status": "NO_PROMPT_IN_PAYLOAD",
                "prompt": None, "prompt_sha256": None,
                "payload_sha256": payload_sha256(payload),
                "problems": ["the frozen payload carries no %s.%s prompt" % (input_key, prompt_key)],
                "verdict": None}
    counted = normalize_text(actual)
    sha = text_sha256(counted)
    probs = []
    if frozen is not None:
        want = frozen.get("final_prompt_sha256")
        if want and want != sha:
            probs.append("payload prompt sha256 %s is not the frozen prompt %s; the request changed "
                         "after measurement and is refused" % (sha, want))
    verdict = evaluate(counted, model=model or (frozen or {}).get("model"),
                       max_chars=max_chars if max_chars is not None else (frozen or {}).get("max"),
                       max_source=max_source or (frozen or {}).get("limit_source"),
                       unit=unit, kind=kind, anatomy=anatomy,
                       review_ref=review_ref if review_ref is not None else (frozen or {}).get("review_ref"),
                       adapter_path=adapter_path, fallback_max=fallback_max,
                       band_override=band_override, schema_version=schema_version)
    ok = not probs and verdict["ok"]
    status = verdict["status"] if not probs else "PROMPT_OVERRIDE_REJECTED"
    return {"ok": ok, "status": status, "prompt": counted, "prompt_sha256": sha,
            "payload_sha256": payload_sha256(payload), "verdict": verdict,
            "problems": probs + list(verdict.get("problems") or [])}


def _payload_prompt(payload, input_key, prompt_key):
    if isinstance(payload, dict):
        inner = payload.get(input_key)
        if isinstance(inner, dict) and prompt_key in inner:
            return inner[prompt_key]
        if prompt_key in payload:
            return payload[prompt_key]
    return None


def apply_input_extra(params, extra, *, prompt_key="prompt", model=None, max_chars=None,
                      max_source=None, unit="chars", kind="descriptive", revalidate=False,
                      adapter_path=None, fallback_max=None, band_override=None,
                      schema_version=None):
    """Resolve a late `input_extra` block against the measured prompt.

    A differing prompt is REJECTED by default (status PROMPT_OVERRIDE_REJECTED). With
    revalidate=True it is fully re-measured and only accepted when it passes the band;
    the returned params then carry the counted string and the new verdict.
    """
    merged = dict(params or {})
    if not isinstance(extra, dict) or not extra:
        return {"ok": True, "status": "NO_OVERRIDE", "params": merged, "verdict": None,
                "revalidated": False, "problems": []}
    if prompt_key not in extra:
        merged.update(extra)
        return {"ok": True, "status": "NO_PROMPT_OVERRIDE", "params": merged, "verdict": None,
                "revalidated": False, "problems": []}
    proposed = extra[prompt_key]
    base = merged.get(prompt_key)
    if base is not None and normalize_text(proposed) == normalize_text(base):
        rest = {k: v for k, v in extra.items() if k != prompt_key}
        merged.update(rest)
        return {"ok": True, "status": "OVERRIDE_NOOP", "params": merged, "verdict": None,
                "revalidated": False, "problems": []}
    if not revalidate:
        msg = ("input_extra replaces the prompt after composition and measurement; the request that "
               "would be sent is not the request that was reviewed or counted. Rejected.")
        return {"ok": False, "status": "PROMPT_OVERRIDE_REJECTED", "params": params,
                "verdict": None, "revalidated": False, "problems": [msg]}
    verdict = evaluate(proposed, model=model, max_chars=max_chars, max_source=max_source,
                       unit=unit, kind=kind, adapter_path=adapter_path,
                       fallback_max=fallback_max, band_override=band_override,
                       schema_version=schema_version)
    if not verdict["ok"]:
        return {"ok": False, "status": "PROMPT_OVERRIDE_REJECTED", "params": params,
                "verdict": verdict, "revalidated": True,
                "problems": ["the overriding prompt does not pass the band: " + verdict["message"]]}
    merged[prompt_key] = verdict["counted_text"]
    rest = {k: v for k, v in extra.items() if k != prompt_key}
    merged.update(rest)
    return {"ok": True, "status": "OVERRIDE_REVALIDATED", "params": merged, "verdict": verdict,
            "revalidated": True, "problems": []}


# --------------------------------------------------------------------------- copy profiles
_SCRIPT_BLOCK = re.compile(r"<script\b.*?</script>", re.I | re.S)
_STYLE_BLOCK = re.compile(r"<style\b.*?</style>", re.I | re.S)
_COMMENT_BLOCK = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")


def visible_text(text):
    """Normalized visible copy: scripts, styles, comments and tags removed."""
    s = _COMMENT_BLOCK.sub(" ", str(text))
    s = _SCRIPT_BLOCK.sub(" ", s)
    s = _STYLE_BLOCK.sub(" ", s)
    s = _TAG.sub(" ", s)
    return normalize_text(s)


def _copy_limits(profile):
    if isinstance(profile, dict):
        if isinstance(profile.get("limits"), list):
            return profile["limits"]
        if any(k in profile for k in ("min", "max", "word_min", "word_max", "char_min", "char_max")):
            return [profile]
    if isinstance(profile, list):
        return profile
    return []


def evaluate_copy(text, profile, *, profile_name=None):
    """Enforce ONE copy profile's own limits on normalized visible text.

    Copy bands are character/word bands only. They are never compared with, or derived
    from, an image model's prompt maximum. -> {"ok", "status", "count", "unit", ...}
    """
    visible = visible_text(text)
    limits = _copy_limits(profile)
    if not limits:
        return {"ok": False, "status": "COPY_PROFILE_UNKNOWN", "kind": "copy",
                "profile": profile_name, "count": len(visible), "unit": "chars",
                "prompt_sha256": text_sha256(visible), "failures": [],
                "message": "copy profile %r carries no min/max limits; refusing to pass it" % (profile_name,)}
    failures, seen = [], []
    for spec in limits:
        if not isinstance(spec, dict):
            continue
        unit = "words" if str(spec.get("unit", "chars")).lower().startswith("word") else "chars"
        lo = spec.get("min", spec.get("char_min" if unit == "chars" else "word_min"))
        hi = spec.get("max", spec.get("char_max" if unit == "chars" else "word_max"))
        n = len(visible.split()) if unit == "words" else len(visible)
        seen.append({"unit": unit, "count": n, "min": lo, "max": hi})
        if isinstance(lo, int) and n < lo:
            failures.append("visible copy is %d %s, under the profile minimum %d" % (n, unit, lo))
        if isinstance(hi, int) and n > hi:
            failures.append("visible copy is %d %s, over the profile maximum %d" % (n, unit, hi))
    status = "PASS" if not failures else ("ABOVE_COPY_MAX" if any("over" in f for f in failures)
                                          else "BELOW_COPY_MIN")
    return {"ok": not failures, "status": status, "kind": "copy", "profile": profile_name,
            "count": seen[0]["count"] if seen else len(visible),
            "unit": seen[0]["unit"] if seen else "chars", "limits": seen,
            "prompt_sha256": text_sha256(visible),
            "failures": failures, "message": "; ".join(failures)}


def cta_requirement(section_spec, profile):
    """Explicit CTA precedence for one section.

    1. The section contract's own prohibition ALWAYS wins (a prover is never deleted).
    2. A profile-wide `cta_every_section` then requires a CTA where the section is silent.
    3. Otherwise the section contract's require/forbid flags govern.
    """
    spec = section_spec or {}
    prof = profile or {}
    if spec.get("forbid_cta") or spec.get("forbid_cta_button"):
        return {"cta": "forbidden", "cta_button": "forbidden",
                "source": "section-contract:forbid", "precedence": "section-over-profile"}
    if prof.get("cta_every_section") is True:
        return {"cta": "required", "cta_button": "optional",
                "source": "profile:cta_every_section", "precedence": "profile-where-silent"}
    return {"cta": "required" if spec.get("requires_cta") else "optional",
            "cta_button": "required" if spec.get("requires_cta_button") else "optional",
            "source": "section-contract", "precedence": "default"}


# --------------------------------------------------------------------------- templates
_SURFACE_LABELS = {
    "production": {"section_labels": False, "part_labels": False, "cta_markers": False,
                   "prompt_markers": False},
    "review": {"section_labels": True, "part_labels": True, "cta_markers": True,
               "prompt_markers": True},
    "internal": {"section_labels": True, "part_labels": True, "cta_markers": True,
                 "prompt_markers": True},
}

_ROLE_TEMPLATES = {
    "image_prompt": {
        "author": ("role=image_prompt phase=author: author the ten-element image prompt to the "
                   "strict band; no section labels, no production markers"),
        "review": ("role=image_prompt phase=review: the review artifact MAY carry section labels and "
                   "the frozen prompt hash; production surfaces may not"),
        "submit": ("role=image_prompt phase=submit: submit the frozen counted string only; a late "
                   "override is rejected unless fully revalidated"),
    },
    "copy": {
        "author": "role=copy phase=author: enforce the copy profile's own character/word limits on visible text",
        "review": "role=copy phase=review: labels allowed; cite the profile name and its limits",
        "submit": "role=copy phase=submit: image prompt bands never apply to copy",
    },
    "review": {
        "author": "role=review phase=author: bind every finding to the frozen prompt/payload hash",
        "review": "role=review phase=review: labels allowed in the artifact",
        "submit": "role=review phase=submit: an earlier authored prompt never authorizes a different request",
    },
}


def label_policy(surface="production"):
    """Resolve the label conflict: review artifacts carry labels, production surfaces do not."""
    key = str(surface or "production").lower()
    if key not in _SURFACE_LABELS:
        raise ValueError("surface must be production, review or internal; got %r" % (surface,))
    return dict(_SURFACE_LABELS[key], surface=key)


def template(role, phase="author"):
    """Role- and phase-specific authoring template text."""
    if role not in _ROLE_TEMPLATES:
        raise ValueError("role must be one of %s; got %r" % (sorted(_ROLE_TEMPLATES), role))
    phases = _ROLE_TEMPLATES[role]
    if phase not in phases:
        raise ValueError("phase must be one of %s; got %r" % (sorted(phases), phase))
    return phases[phase]


# --------------------------------------------------------------------------- self-check
def _self_check():
    """Runnable assert-based check of the four band cases and the counting rule."""
    m = 20000
    b = band_numbers(m)
    assert b["floor"] == 19000, b
    assert b["hard_floor"] == 16000, b
    cases = [
        ("94%", "x" * 18800, True, "BELOW_TARGET"),
        ("80%", "x" * 16000, True, "BELOW_TARGET"),
        ("96%", "x" * 19200, True, "PASS"),
        ("100%", "x" * 20000, True, "PASS"),
        ("101%", "x" * 20001, False, "ABOVE_MAX"),
        ("79%", "x" * 15800, False, "BELOW_FLOOR"),
    ]
    for name, text, ok, status in cases:
        v = evaluate(text, model="self-check", max_chars=m, max_source="self-check")
        assert v["ok"] is ok and v["status"] == status, (name, v)
    warn = evaluate("x" * 18800, model="self-check", max_chars=m, max_source="self-check")
    assert warn["ok"] and warn["add"] == 200 and "ADD 200 chars" in warn["warnings"][0], warn
    assert evaluate("x" * 19000, model="x", max_chars=None, max_source=None,
                    adapter_path="")["status"] == "UNKNOWN_MAX"
    counted = normalize_text("﻿  café\n interior  ")
    assert counted == "café\n interior", repr(counted)
    assert count_text("```json\nabc\n```") == 3
    # metadata INSIDE a fence is still metadata: one pass in the wrong order counted it
    assert normalize_text("```markdown\n---\ntitle: x\n---\nbody\n```") == "body"
    assert normalize_text("---\ntitle: x\n---\n```\nabc\n```") == "abc"
    # a caller's pre-resolved limit is honoured, not ignored
    assert evaluate("x" * 19200, model="x",
                    limit={"max": m, "source": "adapter"})["status"] == "PASS"
    override = apply_input_extra({"prompt": "x" * 19200}, {"prompt": "y" * 19200},
                                 model="self-check", max_chars=m)
    assert override["ok"] is False and override["status"] == "PROMPT_OVERRIDE_REJECTED", override
    print("prompt_policy self-check: PASS (80-94% warns and expands, 96% passes, over-max fails, "
          "unknown refuses, override rejected)")
    return 0


if __name__ == "__main__":
    sys.exit(_self_check())
