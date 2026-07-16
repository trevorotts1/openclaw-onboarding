#!/usr/bin/env python3
"""page_qc.py — Page-QC v2: the SEMANTIC scorer FAB-QC cannot be (B-U11 / U25).

FAB-QC (fab_qc.py) is STRUCTURAL: it counts words, checks placeholders, checks a
persona name landed in a log. It cannot tell flat copy from moving copy. Page-QC v2
is the semantic layer on top: it asks the client's OWN judge model (never Anthropic —
client-skill sovereignty) to score conversion likelihood, emotional strength, voice
fidelity, image congruence, search-engine-optimization strength, and whole-page
coherence.

This module **extends, never replaces** the existing gates:
  - `ghl_verify` stays the hard mechanical floor (render/soundness).
  - FAB-QC (`fab_qc.py`) stays the structural gate (D1-D6, scored 8.5).
  - Page-QC (this module) is scored AFTER FAB-QC, on the SAME evidence tree,
    producing `scorecard/page-qc.json`. It is invoked by `qc-built-funnel.sh`
    behind the `PAGE_QC_ENABLED=1` flag (revert = unset the flag).

JUDGE: the client's own judge model via `06-ghl-install-pages/tools/model_router.py`'s
`qc` role (MiniMax M3 vision-capable, probe-gated -> OpenRouter MiniMax M3 -> Gemini
3.5 Flash last-resort). NEVER Anthropic (model_router's `assert_no_anthropic` is called
on every ladder build). judge != writer, per the standing Quality-Control protocol.

SIX DIMENSIONS (weights sum to 100; each scored 0-10):
  S1 Conversion likelihood      25 — offer clarity, call-to-action prominence, friction,
                                      urgency/risk-reversal, message-market match.
  S2 Emotional strength         20 — declared emotional register, concrete/sensory
                                      language, story presence.
  S3 Voice/persona fidelity     15 — judged against the blend directive (the semantic
                                      upgrade of D4); degrades to template-hint judging
                                      when no blend directive is present.
  S4 Image quality & congruence 15 — vision: render correctness, on-brand palette,
                                      placeholder penalty. A broken-image finding is a
                                      DETERMINISTIC sub-check (runs key-free).
  S5 Search-engine-optimization
     strength                   15 — keyword intent vs page goal, heading structure;
                                      STRENGTH, not presence (existing gates check
                                      presence only).
  S6 Whole-page coherence       10 — hook -> value -> proof -> close scroll narrative,
                                      section order vs the template `copyFramework`.

Threshold: 8.5 — the standing fleet bar (QC-PROTOCOL.md / fab_qc.THRESHOLD), never a
new one. Hard misses: S1 <= 3; any S4 broken-image finding; S3 <= 3 on a task carrying
a blend directive.

DETERMINISM GUARD: every semantic dimension is judged TWICE; a spread > 1.5 triggers a
third pass and the verdict is the MEDIAN. A judge call that fails to return a
schema-valid `{"score": 0-10, "reasoning": str}` after its allotted passes is a
FAIL-CLOSED hard miss for that dimension (the key IS present — a malformed response is
a real gate problem, not an availability problem).

NO JUDGE KEY -> the WHOLE scorecard SKIPs honestly: `available=False`,
`score=None`, `passed=None`, verdict `"page_qc: unavailable (no judge key)"` — NEVER a
fabricated numeric score (SKIP-not-fabricate). Key PRESENCE is checked by NAME only
(OLLAMA_CLOUD_API_KEY / OPENROUTER_API_KEY); the value is never read into a log line.

FIX LOOP: on FAIL, name the lowest dimension + concrete gaps; bounded re-author,
verifier != author, <= MAX_REAUTHOR_ATTEMPTS (mirrors fab_qc.MAX_REAUTHOR_ATTEMPTS = 5).

stdlib-only. The only network calls are the judge HTTP calls themselves (skipped
entirely when a `judge_fn` is injected, e.g. every unit test).
"""
from __future__ import annotations

import base64
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import Callable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import fab_qc  # noqa: E402 — sibling scorer; reuse Dim + the evidence-tree loader

try:
    from key_resolver import resolve_key  # noqa: E402
except ImportError:  # pragma: no cover — resolver is optional (env-only fallback)
    resolve_key = None  # type: ignore[assignment]

Dim = fab_qc.Dim  # same shape (name, weight, score, hard_miss, observed) + .earned

THRESHOLD = fab_qc.THRESHOLD  # 8.5 — never a new threshold
assert THRESHOLD == 8.5

W = {"S1": 25, "S2": 20, "S3": 15, "S4": 15, "S5": 15, "S6": 10}
assert sum(W.values()) == 100

DETERMINISM_SPREAD = 1.5          # two-pass spread above this triggers a third pass
MAX_REAUTHOR_ATTEMPTS = fab_qc.MAX_REAUTHOR_ATTEMPTS  # 5 — single canonical source

HTTP_TIMEOUT_SECONDS = 45
OLLAMA_CLOUD_CHAT_PATH = "/chat/completions"
OPENROUTER_CHAT_PATH = "/chat/completions"

# judge_fn(dimension_key: str, payload: dict) -> {"score": 0-10, "reasoning": str} | {"error": str}
JudgeFn = Callable[[str, dict], Optional[dict]]


# --------------------------------------------------------------------------- #
# key presence — SET/NOT-SET only, NEVER the value itself
# --------------------------------------------------------------------------- #
def has_judge_key(env: Optional[dict] = None) -> bool:
    """True iff a judge-capable key is resolvable (Ollama Cloud OR OpenRouter).

    ``env`` (when given) is the ONLY source consulted — this is the test seam
    (pass ``env={}`` to simulate a no-key box deterministically, independent of
    whatever happens to be set on the real host). ``env=None`` (production) also
    consults ``key_resolver`` (openclaw.json / .env files), matching the rest of
    the fleet's key-presence pattern.
    """
    if env is not None:
        return bool(env.get("OLLAMA_CLOUD_API_KEY") or env.get("OPENROUTER_API_KEY"))
    if os.environ.get("OLLAMA_CLOUD_API_KEY") or os.environ.get("OPENROUTER_API_KEY"):
        return True
    if resolve_key is not None:
        try:
            if resolve_key("OLLAMA_CLOUD_API_KEY", exact=True):
                return True
            if resolve_key("openrouter"):
                return True
        except Exception:  # noqa: BLE001 — key presence must never raise
            return False
    return False


# --------------------------------------------------------------------------- #
# determinism guard — two-pass, third-pass-on-spread, median
# --------------------------------------------------------------------------- #
def _valid_judge_result(r) -> bool:
    if not isinstance(r, dict) or r.get("error"):
        return False
    try:
        f = float(r.get("score"))
    except (TypeError, ValueError):
        return False
    return 0.0 <= f <= 10.0


def _score_via_judge(dim_key: str, payload: dict, judge_fn: JudgeFn) -> dict:
    """Call ``judge_fn`` up to 3x (always 2; a 3rd only when the 2-pass spread
    exceeds ``DETERMINISM_SPREAD``). Returns ``{"score": float|None, "reasoning": str}``
    — ``score is None`` means the judge is present but failed to return a schema-valid
    result across its allotted passes (fail-closed hard miss for the caller, NOT a
    SKIP — the key is present)."""
    r1 = judge_fn(dim_key, payload)
    r2 = judge_fn(dim_key, payload)
    if not _valid_judge_result(r1) or not _valid_judge_result(r2):
        bad = r1 if not _valid_judge_result(r1) else r2
        err = (bad or {}).get("error") or (bad or {}).get("reasoning") or "unparseable judge response"
        return {"score": None, "reasoning": f"judge call failed after 2 passes: {err}",
                "passes": [r1, r2]}
    s1, s2 = float(r1["score"]), float(r2["score"])
    if abs(s1 - s2) > DETERMINISM_SPREAD:
        r3 = judge_fn(dim_key, payload)
        if _valid_judge_result(r3):
            s3 = float(r3["score"])
            final = statistics.median([s1, s2, s3])
            reasoning = (f"spread {abs(s1 - s2):.2f} > {DETERMINISM_SPREAD} triggered a 3rd pass; "
                         f"median of 3 = {final:.2f}. " + str(r3.get("reasoning", "")))[:500]
            passes = [r1, r2, r3]
        else:
            # 3rd pass itself failed to parse: fall back to the median of the two
            # VALID passes we do have — still honest, still never fabricated.
            final = statistics.median([s1, s2])
            reasoning = (f"spread {abs(s1 - s2):.2f} > {DETERMINISM_SPREAD} triggered a 3rd pass; "
                         f"3rd pass unparseable, median of first 2 = {final:.2f}")
            passes = [r1, r2, r3]
    else:
        final = statistics.median([s1, s2])
        reasoning = str(r1.get("reasoning", "") or r2.get("reasoning", ""))[:500]
        passes = [r1, r2]
    return {"score": round(final, 2), "reasoning": reasoning, "passes": passes}


# --------------------------------------------------------------------------- #
# deterministic sub-check: broken images (runs KEY-FREE, even with no judge)
# --------------------------------------------------------------------------- #
def _detect_broken_images(inp: dict) -> list:
    """Broken-image findings from the images/manifest.json record family (a manifest
    record with an explicit ``broken`` flag or an HTTP status >= 400) plus any
    ``data-img-broken="true"`` marker left in captured DOM. Deterministic — needs
    no judge, no network."""
    broken: list = []
    for rec in inp.get("image_manifest", []) or []:
        if not isinstance(rec, dict):
            continue
        status = rec.get("http_status")
        try:
            status_broken = status is not None and int(status) >= 400
        except (TypeError, ValueError, OverflowError):
            # TypeError:  None/list/dict/other non-coercible shapes
            # ValueError: non-numeric strings, NaN (int(float('nan')) raises this)
            # OverflowError: +-Infinity (int(float('inf')) raises this, NOT
            #                 ValueError — json.load decodes bare `Infinity` /
            #                 `-Infinity` / `NaN` tokens to Python floats by
            #                 default, so a manifest record can carry any of
            #                 these). A plain huge int/float never raises here —
            #                 Python ints are arbitrary precision — so no extra
            #                 magnitude guard is needed.
            status_broken = False  # never crash the scorer on a malformed http_status
        is_broken = bool(rec.get("broken")) or status_broken
        if is_broken:
            broken.append(rec.get("cdn_url") or rec.get("path") or "unknown")
    dom = inp.get("dom_html", "") or ""
    if not isinstance(dom, str):
        dom = ""  # non-string dom_html: never crash the scorer
    for m in re.finditer(r'data-img-broken="true"[^>]*?(?:src|data-src)="([^"]+)"', dom):
        broken.append(m.group(1))
    return broken


def _all_copy_text(inp: dict) -> list:
    return fab_qc._texts_of(inp.get("artifact", {}) or {})  # noqa: SLF001 — sibling module


# --------------------------------------------------------------------------- #
# S1 — conversion likelihood
# --------------------------------------------------------------------------- #
def score_s1(inp: dict, judge_fn: JudgeFn) -> Dim:
    payload = {
        "dimension": "S1 conversion likelihood",
        "criteria": ("offer clarity, call-to-action prominence, friction, "
                     "urgency/risk-reversal, message-market match"),
        "copy": _all_copy_text(inp),
        "conversion_goal": inp.get("conversion_goal", ""),
    }
    r = _score_via_judge("S1", payload, judge_fn)
    if r["score"] is None:
        return Dim("S1 Conversion likelihood", W["S1"], 0.0, True,
                   f"judge unavailable/unparseable — fail-closed HARD MISS: {r['reasoning']}")
    hard = r["score"] <= 3.0
    observed = f"judge score={r['score']}/10; {r['reasoning']}"
    if hard:
        observed += " — HARD MISS (S1 <= 3)"
    return Dim("S1 Conversion likelihood", W["S1"], r["score"], hard, observed)


# --------------------------------------------------------------------------- #
# S2 — emotional strength
# --------------------------------------------------------------------------- #
def score_s2(inp: dict, judge_fn: JudgeFn) -> Dim:
    payload = {
        "dimension": "S2 emotional strength",
        "criteria": "declared emotional register, concrete/sensory language, story presence",
        "copy": _all_copy_text(inp),
    }
    r = _score_via_judge("S2", payload, judge_fn)
    if r["score"] is None:
        return Dim("S2 Emotional strength", W["S2"], 0.0, True,
                   f"judge unavailable/unparseable — fail-closed HARD MISS: {r['reasoning']}")
    observed = f"judge score={r['score']}/10; {r['reasoning']}"
    return Dim("S2 Emotional strength", W["S2"], r["score"], False, observed)


# --------------------------------------------------------------------------- #
# S3 — voice / persona fidelity (judged against the blend directive)
# --------------------------------------------------------------------------- #
def score_s3(inp: dict, judge_fn: JudgeFn) -> Dim:
    blend = inp.get("blend_directive") or {}
    payload = {
        "dimension": "S3 voice/persona fidelity",
        "criteria": "copy is judged against the assigned blend's voice attributes",
        "blend_directive": blend,
        "copy": _all_copy_text(inp),
    }
    degraded = not blend
    if degraded:
        payload["note"] = "no blend directive present — degrade to template-hint judging"
        payload["template_hint"] = (inp.get("template") or {}).get("copyFramework", {})
    r = _score_via_judge("S3", payload, judge_fn)
    if r["score"] is None:
        return Dim("S3 Voice/persona fidelity", W["S3"], 0.0, True,
                   f"judge unavailable/unparseable — fail-closed HARD MISS: {r['reasoning']}")
    # Hard miss only fires when a blend directive was actually assigned (D1 scope):
    # a degraded/template-hint judgment with no blend to fail is never hard-missed.
    hard = (r["score"] <= 3.0) and not degraded
    observed = f"judge score={r['score']}/10; blend_present={not degraded}; {r['reasoning']}"
    if hard:
        observed += " — HARD MISS (S3 <= 3 on a task carrying a blend directive)"
    return Dim("S3 Voice/persona fidelity", W["S3"], r["score"], hard, observed)


# --------------------------------------------------------------------------- #
# S4 — image quality & congruence (deterministic broken-image gate + vision judge)
# --------------------------------------------------------------------------- #
def score_s4(inp: dict, judge_fn: JudgeFn) -> Dim:
    broken = _detect_broken_images(inp)
    if broken:
        return Dim("S4 Image quality & congruence", W["S4"], 0.0, True,
                   f"broken-image finding(s): {broken} — HARD MISS (S4)")
    if not (inp.get("screenshot_b64") or inp.get("screenshot_path")):
        return Dim("S4 Image quality & congruence", W["S4"], 10.0, False,
                   "no images/screenshot in build evidence — N/A, scored 10")
    payload = {
        "dimension": "S4 image quality & congruence",
        "criteria": "render correctness, on-brand palette per the theme, placeholder penalty",
        "theme_palette": inp.get("theme_palette", []),
        "_image_b64": inp.get("screenshot_b64"),
    }
    r = _score_via_judge("S4", payload, judge_fn)
    if r["score"] is None:
        return Dim("S4 Image quality & congruence", W["S4"], 0.0, True,
                   f"judge unavailable/unparseable — fail-closed HARD MISS: {r['reasoning']}")
    observed = f"judge score={r['score']}/10; {r['reasoning']}"
    return Dim("S4 Image quality & congruence", W["S4"], r["score"], False, observed)


# --------------------------------------------------------------------------- #
# S5 — search-engine-optimization strength (strength, not presence)
# --------------------------------------------------------------------------- #
def score_s5(inp: dict, judge_fn: JudgeFn) -> Dim:
    payload = {
        "dimension": "S5 search-engine-optimization strength",
        "criteria": "keyword intent vs page goal, heading structure — STRENGTH not presence",
        "seo_panel": inp.get("seo_panel", {}),
        "conversion_goal": inp.get("conversion_goal", ""),
        "copy": _all_copy_text(inp),
    }
    r = _score_via_judge("S5", payload, judge_fn)
    if r["score"] is None:
        return Dim("S5 Search-engine-optimization strength", W["S5"], 0.0, True,
                   f"judge unavailable/unparseable — fail-closed HARD MISS: {r['reasoning']}")
    observed = f"judge score={r['score']}/10; {r['reasoning']}"
    return Dim("S5 Search-engine-optimization strength", W["S5"], r["score"], False, observed)


# --------------------------------------------------------------------------- #
# S6 — whole-page coherence
# --------------------------------------------------------------------------- #
def score_s6(inp: dict, judge_fn: JudgeFn) -> Dim:
    payload = {
        "dimension": "S6 whole-page coherence",
        "criteria": ("hook -> value -> proof -> close scroll narrative; section order vs "
                     "the template copyFramework; a mobile-viewport capture was taken"),
        "copy_framework": (inp.get("template") or {}).get("copyFramework", {}),
        "page_count": len((inp.get("artifact") or {}).get("pages", []) or []),
        "mobile_capture_present": bool(inp.get("mobile_screenshot_b64")),
    }
    r = _score_via_judge("S6", payload, judge_fn)
    if r["score"] is None:
        return Dim("S6 Whole-page coherence", W["S6"], 0.0, True,
                   f"judge unavailable/unparseable — fail-closed HARD MISS: {r['reasoning']}")
    observed = f"judge score={r['score']}/10; {r['reasoning']}"
    return Dim("S6 Whole-page coherence", W["S6"], r["score"], False, observed)


_SCORERS = (score_s1, score_s2, score_s3, score_s4, score_s5, score_s6)


# --------------------------------------------------------------------------- #
# U117 (E6-3/G9) — Comms-artifact QC + per-part-governance / audience-prompt
# conformance invariant. Extends Page-QC v2 (this module, U25) AND the FAB-QC
# voice-grounding gate (fab_qc.py, U19 — via its extracted, reused
# `voice_persona_grounded` predicate) with FOUR ADDITIONAL checks specific to
# an outside-world COMMUNICATION artifact (U116's five `comms_type`s: page,
# blog, email, sms, social): correct PER-PART persona governance (U115),
# blend ACTUALLY USED (semantic — the upgrade of D4/S3), TOPIC CONSIDERED,
# and AUDIENCE CONFIRMED (U116). Each is a HARD-MISS-ONLY check (weight 0,
# same "excluded from the weighted S1-S6 total, never disturbs weights-sum-
# to-100" posture the anti-copy guard uses in fab_qc.py) — this module's own
# six-dimension weighted score is UNTOUCHED by any of this.
#
# Additive / flag-gated behind COMMS_QC_CONFORMANCE=1 (this unit's own
# `revert:` clause — unset/non-"1" degrades `grade_comms_conformance` to a
# pure no-op: `applicable=False`, no checks run, byte-identical to pre-U117
# page_qc.py for every existing caller).
#
# Three of the four checks are DETERMINISTIC and run KEY-FREE regardless of
# judge availability (part->blend match, topic slot populated, audience
# recorded — BINARY acceptance (f)); only "blend actually used" is SEMANTIC
# and needs a judge — it SKIPs honestly (never a fabricated score) with no
# judge key, and a SKIP never blocks the other three (same SKIP-not-
# fabricate / SKIP-never-blocks doctrine as the rest of this module).
# --------------------------------------------------------------------------- #
COMMS_QC_CONFORMANCE_FLAG = "COMMS_QC_CONFORMANCE"


def comms_qc_enabled(env: Optional[dict] = None) -> bool:
    """Revert switch (this unit's `revert:` clause): the four comms checks
    only run when `COMMS_QC_CONFORMANCE=1`; unset (or any other value)
    degrades `grade_comms_conformance` to a no-op — QC returns to plain
    U25/U26/U19 behavior, no code revert needed."""
    e = env if env is not None else os.environ
    return str(e.get(COMMS_QC_CONFORMANCE_FLAG, "0")).strip() == "1"


def check_part_governance(inp: dict) -> Dim:
    """C1 — per-part persona governance (extends U115): the artifact's
    declared `part_id` must be governed by ITS OWN assigned blend — the
    `routing/part-persona-map.json` record (U115's `write_part_persona_map`
    shape: `{part_id, part_role, voice_persona_id, topic_persona_id,
    audience_label, audience_source, stage, reason}`) for that `part_id` —
    never another part's blend. A comms artifact carries the persona it was
    ACTUALLY written under as `inp['used_voice_persona_id']` (or, absent
    that, `inp['bundle']['persona_id']` — the governing bundle's own voice
    persona field).

    N/A (pass, scored 10, `hard_miss=False`) when no per-part context is
    supplied at all (`part_id` blank or `part_persona_map` empty) — a
    single-part / non-multi-part comms artifact has no per-part invariant to
    violate; this mirrors every other N/A-scores-10 dimension in this
    module (S1-S6) and in `fab_qc.py`.
    """
    part_id = str(inp.get("part_id") or "").strip()
    part_map = inp.get("part_persona_map") or []
    if not part_id or not part_map:
        return Dim("C1 Per-part persona governance", 0, 10.0, False,
                   "no per-part context supplied (part_id/part_persona_map absent) — N/A, scored 10")

    used_persona = str(inp.get("used_voice_persona_id")
                       or (inp.get("bundle") or {}).get("persona_id") or "").strip()
    record = next((r for r in part_map
                   if isinstance(r, dict) and str(r.get("part_id")) == part_id), None)
    if record is None:
        return Dim("C1 Per-part persona governance", 0, 0.0, True,
                   f"part_id {part_id!r} has no entry in part_persona_map — HARD MISS "
                   f"(cannot prove per-part governance)")
    if not used_persona:
        return Dim("C1 Per-part persona governance", 0, 0.0, True,
                   f"no used_voice_persona_id recorded for part {part_id!r} — HARD MISS")

    assigned = str(record.get("voice_persona_id") or "").strip()
    match = bool(assigned) and assigned == used_persona
    observed = (f"part {part_id!r}: assigned persona {assigned!r}; artifact written under "
                f"{used_persona!r}; match={match}")
    if not match:
        observed += " — HARD MISS (written under the wrong part's blend)"
    return Dim("C1 Per-part persona governance", 0, 10.0 if match else 0.0, not match, observed)


def check_topic_considered(inp: dict) -> Dim:
    """C2 — topic considered: the topic slot was populated for this comms
    artifact before writing (U116's `_derive_topic`/`topic_factored`
    contract). Deterministic, key-free — reads `inp['topic']` (falling back
    to the governing `bundle`'s own `topic` field)."""
    topic = str(inp.get("topic") or (inp.get("bundle") or {}).get("topic") or "").strip()
    if topic:
        return Dim("C2 Topic considered", 0, 10.0, False, f"topic slot populated: {topic!r}")
    return Dim("C2 Topic considered", 0, 0.0, True,
               "topic slot empty/unpopulated — HARD MISS (topic not factored before writing)")


def check_audience_confirmed(inp: dict) -> Dim:
    """C3 — audience confirmed: `audience_source` recorded `standard` or
    `specific` (U116's `resolve_comms_audience` contract — the ADD-2 prompt
    having fired). Deterministic, key-free — reads `inp['audience_source']`
    (falling back to the governing `bundle`'s own `audience_source` field,
    the same key `comms_audience_trigger.build_comms_trigger` stamps onto
    the returned bundle)."""
    src = str(inp.get("audience_source")
             or (inp.get("bundle") or {}).get("audience_source") or "").strip()
    if src in ("standard", "specific"):
        return Dim("C3 Audience confirmed", 0, 10.0, False, f"audience_source={src!r} recorded")
    return Dim("C3 Audience confirmed", 0, 0.0, True,
               f"no valid audience_source recorded (got {src!r}) — HARD MISS "
               f"(audience-confirmation prompt did not fire / was not recorded)")


def score_blend_used(inp: dict, judge_fn: Optional[JudgeFn]) -> Optional[Dim]:
    """C4 — blend ACTUALLY USED: the semantic upgrade of FAB-QC D4 (name-
    match in a log line) and this module's own S3 (general voice/persona
    fidelity) — the bundle's declared voice ATTRIBUTES (`voice_style` /
    `voice_attributes` on the `blend_directive`) must semantically trace
    through into the copy, judged by the client's own judge, not merely
    matched by name.

    Reuses `fab_qc.voice_persona_grounded` (U19's extracted predicate) as a
    DETERMINISTIC evidence signal handed to the judge alongside the voice
    attributes — real reuse of the grounding mechanism, never a second
    independent name-match rule — but the PASS/FAIL verdict itself is the
    judge's semantic call, not the deterministic signal alone (a copy body
    could name-match the persona id yet still fail to reflect its actual
    voice attributes, or vice-versa on a paraphrased/pseudonymous byline).

    Returns `None` (SKIP, never a fabricated score) when no `judge_fn` is
    available — the caller MUST treat `None` as "unavailable", never as a
    pass or a hard miss (SKIP-not-fabricate, same as every other judged
    dimension in this module)."""
    if judge_fn is None:
        return None
    blend = inp.get("blend_directive") or (inp.get("bundle") or {}).get("blend_directive") or {}
    voice_persona_id = str(inp.get("used_voice_persona_id")
                           or (inp.get("bundle") or {}).get("persona_id") or "")
    copy_text = inp.get("copy")
    if copy_text is None:
        copy_text = _all_copy_text(inp)
    elif isinstance(copy_text, str):
        copy_text = [copy_text]
    joined = " ".join(str(t) for t in copy_text)
    name_grounded = fab_qc.voice_persona_grounded(joined, voice_persona_id)

    payload = {
        "dimension": "C4 blend actually used",
        "criteria": ("the bundle's declared voice attributes (voice_style) must trace "
                     "through into the copy — a SEMANTIC check, not a name match"),
        "voice_persona_id": voice_persona_id,
        "voice_style": blend.get("voice_style") or blend.get("voice_attributes") or {},
        "name_grounded_deterministic_signal": name_grounded,
        "copy": copy_text,
    }
    r = _score_via_judge("C4", payload, judge_fn)
    if r["score"] is None:
        return Dim("C4 Blend actually used", 0, 0.0, True,
                   f"judge unavailable/unparseable — fail-closed HARD MISS: {r['reasoning']}")
    hard = r["score"] <= 3.0
    observed = f"judge score={r['score']}/10; name_grounded={name_grounded}; {r['reasoning']}"
    if hard:
        observed += " — HARD MISS (C4 <= 3, voice attributes do not trace to the bundle)"
    return Dim("C4 Blend actually used", 0, r["score"], hard, observed)


def validate_comms_schema(result: dict) -> bool:
    """Hand-rolled structural validation (stdlib-only, mirrors `validate_schema`
    above). Raises AssertionError naming the violation; returns True on a
    valid document."""
    assert result.get("tool") == "page_qc_comms", "tool must be 'page_qc_comms'"
    if not result.get("applicable"):
        assert result.get("passed") is None, "not-applicable result must carry no passed verdict"
        assert result.get("checks") == {}, "not-applicable result carries no checks"
        return True
    assert result.get("threshold") == THRESHOLD, "threshold must be 8.5 (never a new one)"
    assert isinstance(result.get("passed"), bool), "applicable result must carry a bool passed"
    checks = result.get("checks") or {}
    for key in ("part_governance", "topic_considered", "audience_confirmed", "blend_used"):
        assert key in checks, f"comms conformance missing check {key!r}"
    bu = checks["blend_used"]
    assert isinstance(bu.get("available"), bool), "blend_used.available must be bool"
    if not bu["available"]:
        assert bu.get("score") is None, "unavailable blend_used must never carry a numeric score"
        assert bu.get("passed") is None, "unavailable blend_used must never carry a passed verdict"
    return True


def grade_comms_conformance(inp: dict, *, judge_fn: Optional[JudgeFn] = None,
                            env: Optional[dict] = None) -> dict:
    """U117 (E6-3/G9) — the public entry point for the comms-artifact QC +
    per-part-governance / audience-prompt conformance invariant. Scores a
    COMMUNICATION artifact on the four checks above and returns a structured
    scorecard a review-lane gate (the CC-side U26 QC-contract, out of scope
    for this repo leg) can read `passed` from directly.

    `inp` keys (all optional, degrade honestly — see each check's own
    docstring): `part_id`, `part_persona_map` (U115's routing/part-persona-
    map.json shape), `used_voice_persona_id`, `bundle` (U116's governed
    bundle — `build_comms_trigger(...)['bundle']`), `topic`,
    `audience_source`, `blend_directive`, `copy`.

    `applicable=False` (no checks run) when `COMMS_QC_CONFORMANCE` is not
    `"1"` — the additive/flag-gated revert path, byte-identical to pre-U117
    `page_qc.py` for every existing caller.
    """
    if not comms_qc_enabled(env):
        return {"tool": "page_qc_comms", "applicable": False,
                "verdict": "comms conformance: not applicable (COMMS_QC_CONFORMANCE off)",
                "checks": {}, "hard_misses": [], "passed": None}

    active_judge = judge_fn
    if active_judge is None and has_judge_key(env):
        active_judge = _default_http_judge_factory(env)

    c1 = check_part_governance(inp)
    c2 = check_topic_considered(inp)
    c3 = check_audience_confirmed(inp)
    c4 = score_blend_used(inp, active_judge)   # None -> SKIP, never blocks

    hard_misses = [d.name for d in (c1, c2, c3) if d.hard_miss]
    det_passed = not hard_misses

    if c4 is None:
        blend_used_result = {"available": False, "score": None, "passed": None, "hard_miss": False,
                             "observed": "blend_used: unavailable (no judge key) — SKIP, not scored"}
        overall_passed = det_passed   # a SKIP never blocks (this module's own SKIP doctrine)
    else:
        blend_used_result = {"available": True, "score": c4.score, "passed": not c4.hard_miss,
                             "hard_miss": c4.hard_miss, "observed": c4.observed}
        if c4.hard_miss:
            hard_misses.append(c4.name)
        overall_passed = det_passed and not c4.hard_miss

    checks = {
        "part_governance": asdict(c1) | {"earned": c1.earned},
        "topic_considered": asdict(c2) | {"earned": c2.earned},
        "audience_confirmed": asdict(c3) | {"earned": c3.earned},
        "blend_used": blend_used_result,
    }
    result = {
        "tool": "page_qc_comms",
        "applicable": True,
        "threshold": THRESHOLD,
        "verdict": "comms conformance: PASS" if overall_passed else "comms conformance: FAIL",
        "checks": checks,
        "hard_misses": hard_misses,
        "passed": overall_passed,
    }
    validate_comms_schema(result)
    return result


# --------------------------------------------------------------------------- #
# schema-lite validator (BINARY acceptance (a): scorecard/page-qc.json validates)
# --------------------------------------------------------------------------- #
def validate_schema(result: dict) -> bool:
    """Hand-rolled structural validation (stdlib-only, no jsonschema dependency —
    matches the rest of the fleet's deterministic-scorer convention). Raises
    AssertionError naming the violation; returns True on a valid document."""
    assert result.get("tool") == "page_qc", "tool must be 'page_qc'"
    assert result.get("threshold") == THRESHOLD, "threshold must be 8.5"
    assert isinstance(result.get("available"), bool), "available must be bool"
    assert isinstance(result.get("verdict"), str) and result["verdict"], "verdict must be a non-empty str"
    if not result["available"]:
        assert result.get("score") is None, "unavailable scorecard must never carry a numeric score"
        assert result.get("passed") is None, "unavailable scorecard must never carry a passed verdict"
        assert result.get("dimensions") == [], "unavailable scorecard carries no dimension scores"
        return True
    assert isinstance(result.get("score"), (int, float)), "available scorecard must carry a numeric score"
    assert isinstance(result.get("passed"), bool), "available scorecard must carry a bool passed"
    dims = result.get("dimensions")
    assert isinstance(dims, list) and len(dims) == 6, "exactly six dimensions"
    seen_weight = 0
    for d in dims:
        for key in ("name", "weight", "score", "hard_miss", "observed", "earned"):
            assert key in d, f"dimension missing key {key!r}"
        seen_weight += d["weight"]
    assert seen_weight == 100, f"dimension weights must sum to 100, got {seen_weight}"
    return True


# --------------------------------------------------------------------------- #
# grade() — the public entry point
# --------------------------------------------------------------------------- #
def grade(inp: dict, *, judge_fn: Optional[JudgeFn] = None, env: Optional[dict] = None) -> dict:
    """Score a build on the six Page-QC v2 semantic dimensions.

    ``inp`` keys (all optional, degrade gracefully): ``artifact`` (fab-artifact shape,
    same as fab_qc), ``template``, ``conversion_goal``, ``blend_directive``,
    ``seo_panel``, ``theme_palette``, ``image_manifest`` (list of
    ``{cdn_url|path, http_status|broken}``), ``dom_html``, ``screenshot_b64``,
    ``mobile_screenshot_b64``.

    ``judge_fn``: inject a deterministic stub for tests. ``None`` in production resolves
    the real HTTP judge via model_router's ``qc`` role IFF a judge key is present;
    with no key anywhere, the WHOLE scorecard SKIPs (see module docstring).
    """
    active_judge = judge_fn
    if active_judge is None and has_judge_key(env):
        active_judge = _default_http_judge_factory(env)

    if active_judge is None:
        broken = _detect_broken_images(inp)
        return {
            "tool": "page_qc",
            "threshold": THRESHOLD,
            "available": False,
            "verdict": "page_qc: unavailable (no judge key)",
            "score": None,
            "passed": None,
            "hard_misses": [],
            "deterministic_findings": {"broken_images": broken},
            "dimensions": [],
        }

    dims = [fn(inp, active_judge) for fn in _SCORERS]
    weighted = round(sum(d.earned for d in dims), 2)         # 0-100
    score_10 = round(weighted / 10.0, 2)                      # 0-10
    hard_misses = [d.name for d in dims if d.hard_miss]
    passed = (score_10 >= THRESHOLD) and not hard_misses
    lowest = min(dims, key=lambda d: (d.score - (100 if d.hard_miss else 0)))
    result = {
        "tool": "page_qc",
        "threshold": THRESHOLD,
        "available": True,
        "verdict": "page_qc: PASS" if passed else "page_qc: FAIL",
        "weighted_score_100": weighted,
        "score": score_10,
        "passed": passed,
        "hard_misses": hard_misses,
        "lowest_dimension": lowest.name,
        "deterministic_findings": {"broken_images": _detect_broken_images(inp)},
        "dimensions": [asdict(d) | {"earned": d.earned} for d in dims],
    }
    validate_schema(result)
    return result


# --------------------------------------------------------------------------- #
# default HTTP judge — model_router (role='qc') + a real chat-completion call
# --------------------------------------------------------------------------- #
class _JudgeKeyMissing(Exception):
    pass


_model_router_cache = None  # None=untried, False=unavailable, module=loaded


def _load_model_router():
    global _model_router_cache
    if _model_router_cache is not None:
        return _model_router_cache if _model_router_cache is not False else None
    tools_dir = os.path.normpath(os.path.join(_HERE, "..", "06-ghl-install-pages", "tools"))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import model_router  # type: ignore
        _model_router_cache = model_router
        return model_router
    except Exception:  # noqa: BLE001 — fail-soft, caller treats as no judge
        _model_router_cache = False
        return None


def _extract_message(payload: dict) -> str:
    """Extract text from an OpenAI-compatible chat-completion payload (mirrors
    llm_score._extract_message's crash-guard order for thinking-model responses)."""
    try:
        msg = payload["choices"][0]["message"]
        content = msg.get("content")
        if content is not None and str(content).strip():
            return str(content).strip()
        rd = msg.get("reasoning_details")
        if rd and isinstance(rd, list):
            parts = [str(b.get("text") or b.get("thinking") or "") for b in rd if isinstance(b, dict)]
            joined = "\n".join(p for p in parts if p).strip()
            if joined:
                return joined
        reasoning = msg.get("reasoning")
        if reasoning and str(reasoning).strip():
            return str(reasoning).strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    return ""


def _parse_qc_json(text: str) -> dict:
    """Pull {score(0-10), reasoning} out of a judge response. Resilient to fluff."""
    if not text:
        return {"score": None, "reasoning": "empty response"}
    try:
        obj = json.loads(text)
        score = float(obj.get("score"))
        if 0.0 <= score <= 10.0:
            return {"score": score, "reasoning": str(obj.get("reasoning", ""))[:400]}
    except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
        pass
    m = re.search(r'\{[^{}]*"score"\s*:\s*([0-9.]+)[^{}]*\}', text)
    if m:
        try:
            score = float(m.group(1))
            if 0.0 <= score <= 10.0:
                rm = re.search(r'"reasoning"\s*:\s*"([^"]*)"', text)
                reasoning = rm.group(1) if rm else "parsed from non-JSON"
                return {"score": score, "reasoning": reasoning[:400]}
        except ValueError:
            pass
    return {"score": None, "reasoning": f"parse failed: {text[:200]}"}


def _judge_key_for(provider: str, env: dict):
    if provider == "ollama-cloud":
        return env.get("OLLAMA_CLOUD_API_KEY") or (
            resolve_key("OLLAMA_CLOUD_API_KEY", exact=True) if resolve_key else None)
    if provider == "openrouter":
        return env.get("OPENROUTER_API_KEY") or (resolve_key("openrouter") if resolve_key else None)
    return None


def _call_chat(provider: str, base_url: str, slug: str, prompt: str, *,
               image_b64: Optional[str] = None, env: Optional[dict] = None) -> str:
    e = env if env is not None else os.environ
    api_key = _judge_key_for(provider, e)
    if not api_key:
        raise _JudgeKeyMissing(f"{provider} key not set")
    if provider == "ollama-cloud":
        url = base_url.rstrip("/") + OLLAMA_CLOUD_CHAT_PATH
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    elif provider == "openrouter":
        url = base_url.rstrip("/") + OPENROUTER_CHAT_PATH
        headers = {
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/trevorotts1/openclaw-onboarding",
            "X-Title": "OpenClaw Page-QC v2",
        }
    else:
        raise _JudgeKeyMissing(f"unknown provider {provider!r}")

    content = prompt
    if image_b64:
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]
    body = {
        "model": slug,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "max_tokens": 300,
        "reasoning": {"exclude": True},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        raw = resp.read().decode("utf-8")
    return _extract_message(json.loads(raw))


def _build_prompt(dim_key: str, payload: dict) -> str:
    body = {k: v for k, v in payload.items() if not k.startswith("_")}
    return (
        "You are Page-QC v2, a strict semantic quality judge for a marketing page. "
        f"Score dimension {dim_key} on a 0-10 scale using the criteria and evidence below. "
        "Respond with ONLY a JSON object, no prose outside it: "
        '{"score": <number 0-10>, "reasoning": "<=40 words>"}.\n\n'
        f"EVIDENCE:\n{json.dumps(body, ensure_ascii=False)[:6000]}"
    )


def _default_http_judge_factory(env: Optional[dict] = None) -> Optional[JudgeFn]:
    """Build a real judge_fn wired to model_router's qc-role ladder. Returns None
    (fail-soft -> caller treats the whole scorecard as unavailable) if model_router
    itself cannot be imported."""
    router = _load_model_router()
    if router is None:
        return None
    e = env if env is not None else os.environ
    try:
        ladder = router.build_ladder(e, role="qc")   # never Anthropic (asserted inside)
    except Exception:  # noqa: BLE001
        return None

    def _judge(dim_key: str, payload: dict) -> dict:
        prompt = _build_prompt(dim_key, payload)
        image_b64 = payload.get("_image_b64")
        last_err = "no rung produced a parseable score"
        for rung in ladder:
            for model in rung.get("models", []):
                try:
                    text = _call_chat(rung["provider"], rung["base_url"], model["slug"],
                                       prompt, image_b64=image_b64, env=e)
                except _JudgeKeyMissing as exc:
                    last_err = str(exc)
                    continue
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                        json.JSONDecodeError, OSError) as exc:
                    last_err = f"{model['slug']}: {type(exc).__name__}: {exc}"
                    continue
                parsed = _parse_qc_json(text)
                if parsed.get("score") is not None:
                    parsed["model"] = model["slug"]
                    return parsed
                last_err = f"{model['slug']}: {parsed.get('reasoning', 'unparseable')}"
        return {"score": None, "error": last_err, "reasoning": last_err}

    return _judge


# --------------------------------------------------------------------------- #
# operator visibility — qc_starved event on SKIP (fail-soft, opt-in via --task-id)
# --------------------------------------------------------------------------- #
def _load_cc_board():
    tools_dir = os.path.normpath(os.path.join(_HERE, "..", "06-ghl-install-pages", "tools"))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import cc_board  # type: ignore
        return cc_board
    except Exception:  # noqa: BLE001
        return None


def post_qc_starved_event(task_id: str, *, env: Optional[dict] = None, board=None) -> bool:
    """Emit ONE `qc_starved`-class operator-visibility event onto the CC card when
    Page-QC SKIPped for lack of a judge key — never silent, never a fabricated score.
    FAIL-SOFT: never raises; a False return never blocks the build."""
    tid = (task_id or "").strip()
    if not tid:
        return False
    b = board if board is not None else _load_cc_board()
    if b is None:
        return False
    try:
        return bool(b.post_activity(
            tid, "updated",
            "QC: page_qc unavailable (no judge key) — SKIP, not scored (qc_starved)",
            metadata={"qc_gate": "page-qc", "qc_starved": True},
            env=env,
        ))
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# evidence-tree loader (mirrors fab_qc.load_inputs_from_evidence + page-qc extras)
# --------------------------------------------------------------------------- #
def _load_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _first_seo_meta(o):
    if isinstance(o, dict):
        if "seoMeta" in o and isinstance(o["seoMeta"], dict):
            return o["seoMeta"]
        for v in o.values():
            found = _first_seo_meta(v)
            if found:
                return found
    elif isinstance(o, list):
        for v in o:
            found = _first_seo_meta(v)
            if found:
                return found
    return None


def load_inputs_from_evidence(evidence_root: str) -> dict:
    fab_inp = fab_qc.load_inputs_from_evidence(evidence_root, "funnel")
    artifact = fab_inp.get("artifact", {}) or {}
    md = fab_inp.get("match_decision", {}) or {}
    template = fab_inp.get("template") or {}

    image_manifest: list = []
    dom_html = ""
    seo_panel: dict = {}
    for root, _dirs, files in os.walk(evidence_root):
        for fn in files:
            fp = os.path.join(root, fn)
            if fn == "manifest.json" and os.path.basename(root) == "images":
                data = _load_json(fp)
                if isinstance(data, list):
                    image_manifest.extend(r for r in data if isinstance(r, dict))
            elif fn.endswith("-preview.html"):
                try:
                    with open(fp, encoding="utf-8", errors="replace") as f:
                        dom_html += f.read()
                except OSError:
                    pass
            elif fn.endswith(".json") and not seo_panel:
                found = _first_seo_meta(_load_json(fp))
                if found:
                    seo_panel = found

    screenshot_b64 = None
    shots_dir = os.path.join(evidence_root, "screenshots")
    if os.path.isdir(shots_dir):
        pngs = sorted(f for f in os.listdir(shots_dir) if f.lower().endswith(".png"))
        if pngs:
            try:
                with open(os.path.join(shots_dir, pngs[0]), "rb") as f:
                    screenshot_b64 = base64.b64encode(f.read()).decode("ascii")
            except OSError:
                pass

    return {
        "artifact": artifact,
        "template": template,
        "match_decision": md,
        "conversion_goal": md.get("conversion_goal") or template.get("conversionGoal") or "",
        "blend_directive": md.get("blend_directive") or md.get("voice_bundle") or {},
        "image_manifest": image_manifest,
        "dom_html": dom_html,
        "screenshot_b64": screenshot_b64,
        "seo_panel": seo_panel,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Page-QC v2 — six-dimension semantic scorer for a funnel/page build (>=8.5)")
    ap.add_argument("--evidence", help="evidence root dir")
    ap.add_argument("--inputs", help="pre-assembled page-qc-input.json (testing)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gate", action="store_true",
                     help="exit 1 when AVAILABLE and score<8.5/hard-miss; a SKIP never blocks")
    ap.add_argument("--task-id", default="",
                     help="CC task UUID; posts one qc_starved event on SKIP (fail-soft)")
    ap.add_argument("--comms", action="store_true",
                     help="U117 (E6-3/G9): score --inputs as a comms conformance check "
                          "instead of the six-dimension page scorecard (needs "
                          "COMMS_QC_CONFORMANCE=1)")
    a = ap.parse_args(argv)

    if a.inputs:
        inp = _load_json(a.inputs) or {}
    elif a.evidence:
        inp = load_inputs_from_evidence(a.evidence)
    else:
        ap.error("one of --evidence or --inputs is required")
        return 2

    if a.comms:
        result = grade_comms_conformance(inp)
        if a.json:
            print(json.dumps(result, indent=2))
        else:
            print(result["verdict"])
            for name, chk in result.get("checks", {}).items():
                print(f"  {name:<20} {chk}")
        if a.gate and result["applicable"] and not result["passed"]:
            return 1
        return 0

    result = grade(inp)

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Page-QC v2: {result['verdict']} (threshold {THRESHOLD})")
        for d in result.get("dimensions", []):
            flag = "HARD-MISS" if d["hard_miss"] else f"{d['score']:.1f}/10"
            print(f"  {d['name']:<38} w={d['weight']:>2} {flag:<10} {d['observed']}")
        if result["available"] and not result["passed"]:
            print(f"  -> lowest: {result.get('lowest_dimension')}; hard_misses={result['hard_misses']}")

    if not result["available"] and a.task_id:
        post_qc_starved_event(a.task_id)

    if a.gate and result["available"] and not result["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
