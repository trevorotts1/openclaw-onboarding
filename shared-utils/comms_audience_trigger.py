#!/usr/bin/env python3
"""comms_audience_trigger.py — U116 (E6-2; implements operator ruling ADD-2;
closes G8): the communication TRIGGER + audience-confirmation contract on the
content-engine seam (U1/A-U1, `shared-utils/persona_for_job.py`), fired
whenever the system produces an OUTSIDE-WORLD COMMUNICATION — a page, blog,
email, text/SMS, or social post (any externally-facing written communication).

Per the D1 binding ruling (the blend GOVERNS voice + content-writing in every
engine, never advisory, no exemptions) and its ADD-2 extension, every one of
the five comms types this module enumerates MUST, before writing:

  (1) be GOVERNED by the blend — mandatory, never advisory. This module wraps
      `persona_blend.build_bundle(..., force_content_task=True)` so a comms
      artifact is ALWAYS blend-governed even when its task text happens to
      dodge the `is_content_task()` keyword heuristic (e.g. a bare "opt-in
      page" brief with none of that heuristic's signal words in it).
  (2) ALWAYS factor the TOPIC into blend selection — the topic slot is
      populated for every comms artifact, never skipped. `build_comms_trigger`
      REFUSES (never silently writes) when no topic signal is resolvable —
      see `_derive_topic` below.
  (3) BEFORE writing, PROMPT the operator/client with the audience-
      confirmation question — `STANDARD_OR_SPECIFIC_PROMPT` — DEFAULTING to
      the standard (onboarding-ICP-resolved) audience but allowing a
      per-message override. The prompt reuses the shipped confirm-door
      machinery: it is `persona_blend.resolve_audience`'s own always-confirm
      doctrine, re-framed as the standard-vs-specific fork this unit adds.
      The choice is recorded as `audience_source` = "standard" | "specific"
      on the returned bundle — the default-to-standard path is a RECORDED
      decision, never a silent skip.

Fail-closed honesty (per the unit's own "what"): a comms artifact written
without the topic factored, or without an audience decision recorded, is a
Quality-Control finding (U117) — this module NEVER writes one; it returns a
`refused=True` result instead, so the caller can hand the refusal to U117's
comms-QC lane rather than silently producing an ungoverned artifact.

SMS/TEXT-MESSAGE ROUTING DECISION (this unit's first act, per its own "what":
"this unit therefore OWNS the SMS-engine decision... never a silent gap")
-----------------------------------------------------------------------------
U111 (E5-6/G4) read both SMS-adjacent surfaces in full and confirmed NEITHER
is a persona/blend-consuming content-WRITING engine:
  * `38-conversational-ai-system/templates/sms-workflow-ai-prompt-template.md`
    — a GHL "Build with AI" workflow spec; the live reply text is written by
    an EXTERNALLY-hosted conversational agent at n8n/GHL-conversation time,
    entirely outside this repo's Python `persona_for_job` consumer set.
  * `44-convert-and-flow-operator/tools/engine/builders/
    wf5-ht-interest-builder.py` — pure transport/wiring for an already-
    authored nurture workflow; calls no persona/blend API at all.

DECISION: ROUTE, do not build a second, bespoke SMS-writing engine. SMS
("sms") is wired as a first-class `comms_type` value in `COMMS_TYPES`,
handled by this SAME generic trigger — the identical call site email/blog/
social already ride (`build_comms_trigger("sms", ...)` calls the U1 seam
exactly like the others). Reasoning, stated plainly:
  1. No in-tree SMS content-WRITING engine exists to attach a blend call
     site to (U111's NOT-FOUND finding, re-confirmed by this unit — see the
     regression assertion in the test file, which fails loud if either named
     surface starts referencing persona_for_job/blend_directive without this
     module being updated to match).
  2. This repo's own standing constraint is REPO/CODE SIDE ONLY — never
     deploy live n8n, never call live GHL/Podbean/n8n. Building a full
     parallel SMS engine (a tone-tier library, live-send wiring, etc., on
     the scale of Skill 50's email engine) is disproportionate to what this
     unit needs to prove and would require exactly the live-infra reach this
     repo may not touch.
  3. The governance CONTRACT this module builds is engine-agnostic: whichever
     concrete surface eventually SENDS the SMS (a future dedicated engine, or
     GHL's existing Build-with-AI SMS workflow once it is repointed to write
     its own text instead of delegating to an external agent) adopts mandatory
     governance the moment it calls `build_comms_trigger("sms", ...)` — the
     same one call every other comms type already makes. No SMS text is
     written ungoverned; there is simply no in-tree writer to govern yet.

Additive / flag-gated (revert doctrine, per this unit's own `revert:`):
sits behind `COMMS_AUDIENCE_PROMPT` (default ON — set to "0"/"false"/"off"/
"no" to revert). When the flag is off, `build_comms_trigger` degrades to a
plain `persona_blend.build_bundle(...)` pass-through — "today's per-task
audience resolution" — with no `force_content_task`, no topic-refusal gate,
and `audience_source=None`. Reuses the SHIPPED confirm-door machinery
(`persona_blend.resolve_audience`); this module adds NO new door.

stdlib-only, deterministic, no network of its own. Importable as a library
and runnable as a CLI (`--self-test`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

# --------------------------------------------------------------------------- #
# The five outside-world comms types ADD-2 names verbatim: "a page, blog,
# email, text/SMS, social post, or any externally-facing written
# communication". "sms" carries the routing decision documented above.
# --------------------------------------------------------------------------- #
COMMS_TYPES = ("page", "blog", "email", "sms", "social")

# A human-readable label per type, chosen so each one is guaranteed to hit
# `persona_blend.is_content_task()`'s WORD/PHRASE signal set on its own —
# used only to seed a sensible default `topic_hint` fragment when the caller
# supplies none at all with real task-text signal (see `_derive_topic`);
# NEVER overrides an explicit topic_hint or genuine task-text topic signal.
COMMS_TYPE_LABELS = {
    "page": "landing page",
    "blog": "blog",
    "email": "email",
    "sms": "text message",
    "social": "social post",
}

# Sensible default department per comms type — reused ONLY when the caller
# does not supply its own `department` kwarg. Mirrors the real seeded fleet
# departments other units already pinned (email -> "marketing" per U111's
# `persona_canonical.blend_block`; blog/social -> "social-media" per U111's
# `persona_adapter.resolve`). "page" defaults to "web-development" (D23's own
# named department for scoped funnel/page work); "sms" reuses "marketing"
# (nurture/marketing is SMS's dominant real-world use, and it is the same
# seeded department email already uses — no new, unseeded department invented
# for a type with no in-tree writer yet).
COMMS_TYPE_DEPARTMENTS = {
    "page": "web-development",
    "blog": "social-media",
    "email": "marketing",
    "sms": "marketing",
    "social": "social-media",
}

# ADD-2's exact audience-confirmation question (verbatim from the spec).
STANDARD_OR_SPECIFIC_PROMPT = (
    "Should I use your standard audience, or is there a specific/different "
    "audience you want this message for?"
)

# The revert flag (this unit's `revert:` clause). Default ON.
COMMS_AUDIENCE_PROMPT_FLAG = "COMMS_AUDIENCE_PROMPT"
_FALSY = {"0", "false", "off", "no"}


def flag_enabled() -> bool:
    """True unless COMMS_AUDIENCE_PROMPT is explicitly set to a falsy value.
    Default-ON: the mandatory comms-trigger contract is the shipped behavior;
    reverting means flipping this env var, never editing code."""
    v = os.environ.get(COMMS_AUDIENCE_PROMPT_FLAG, "").strip().lower()
    return v not in _FALSY


# --------------------------------------------------------------------------- #
# dynamic import of persona_blend.py — box-portable, mirrors the exact
# candidate-path pattern `50-email-engine/tools/persona_canonical.py` and
# `49-signature-funnel/scripts/copy_persona_blend_seam.py` already use to
# reach a sibling skill directory from shared-utils/across install layouts.
# --------------------------------------------------------------------------- #
def _blend_scripts_dir() -> "Path | None":
    cands = [
        os.environ.get("PERSONA_BLEND_SCRIPTS_DIR", "").strip(),
        str(_REPO_ROOT / "23-ai-workforce-blueprint" / "scripts"),
        str(Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint" / "scripts"),
        "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts",
        str(Path.home() / "clawd" / "skills" / "23-ai-workforce-blueprint" / "scripts"),
    ]
    for c in cands:
        if c and (Path(c) / "persona_blend.py").exists():
            return Path(c)
    return None


def _load_persona_blend():
    """Import persona_blend.py. Returns None (never raises) when unreachable —
    a bare box with no shared-utils/23-ai-workforce-blueprint reachable at
    all; the caller then refuses rather than fabricate governance."""
    d = _blend_scripts_dir()
    if d is None:
        return None
    try:
        sp = str(d)
        if sp not in sys.path:
            sys.path.insert(0, sp)
        import persona_blend as _pb  # type: ignore
        return _pb
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# (2) topic ALWAYS factored — never skipped. A refusal, never a silent write.
# --------------------------------------------------------------------------- #
def _derive_topic(pb, comms_type: str, task_text: str, topic_hint: str) -> "tuple[str, bool]":
    """Resolve (topic, topic_factored). An explicit, non-blank `topic_hint`
    always counts. Absent that, the task text must carry REAL topic signal —
    at least one content token beyond the comms-type's own generic label
    words (e.g. "email"/"blog"/"page") — or this returns topic_factored=False
    so the caller refuses rather than write under a bare/generic topic."""
    hint = (topic_hint or "").strip()
    if hint:
        return hint, True

    label_tokens = pb._tokens(COMMS_TYPE_LABELS.get(comms_type, comms_type))
    task_tokens = pb._tokens(task_text or "")
    real_signal = task_tokens - label_tokens
    if real_signal:
        # Prefer the task's own content tokens (deterministic, sorted for a
        # stable topic string) as the topic — real signal, never fabricated.
        return ", ".join(sorted(real_signal)), True
    return "", False


# --------------------------------------------------------------------------- #
# (3) the standard-vs-specific audience-confirmation fork.
# --------------------------------------------------------------------------- #
def resolve_comms_audience(pb, catalog: dict, company_cfg: dict, soul_text: str = "",
                           *, audience_override: str = "") -> dict:
    """Resolve the standard-vs-specific audience choice for ONE comms message.

    A non-blank `audience_override` is a per-message SPECIFIC audience named
    for this one write — `audience_source="specific"`. Absent that, the
    STANDARD (onboarding-ICP-resolved) audience is used by default —
    `audience_source="standard"` — reusing `persona_blend.resolve_audience`'s
    own always-confirm resolution verbatim (this module invents no new
    audience-resolution logic, only the standard-vs-specific framing on top).

    Returns {audience_source, prompt, chosen_audience, resolve_audience}.
    Never fabricates an audience — `chosen_audience` may be None when
    `resolve_audience` itself resolves nothing (an honest "unknown standard
    audience", not a silent invention).
    """
    override = (audience_override or "").strip()
    if override:
        ra = pb.resolve_audience(catalog, company_cfg, soul_text, audience_override=override)
        return {
            "audience_source": "specific",
            "prompt": STANDARD_OR_SPECIFIC_PROMPT,
            "chosen_audience": ra.get("label"),
            "resolve_audience": ra,
        }
    ra = pb.resolve_audience(catalog, company_cfg, soul_text)
    return {
        "audience_source": "standard",
        "prompt": STANDARD_OR_SPECIFIC_PROMPT,
        "chosen_audience": ra.get("label"),
        "resolve_audience": ra,
    }


# --------------------------------------------------------------------------- #
# the trigger — the ONE call site every comms-producing write path calls.
# --------------------------------------------------------------------------- #
def build_comms_trigger(comms_type: str, task_text: str, department: str = None, *,
                        paths: dict = None, db_path=None, catalog: dict = None,
                        company_cfg: dict = None, soul_text: str = "",
                        audience_override: str = "", topic_hint: str = "",
                        use_llm: bool = True, record: bool = True,
                        max_task_personas: int = 10, variety: bool = True) -> dict:
    """Fire the U116 communication trigger for ONE outside-world comms write.

    Returns a dict:
      {comms_type, flag_enabled, refused, refusal_reason, topic_factored,
       topic, audience_confirmation, bundle}

    `bundle` is the governed `persona_blend.build_bundle(...)` superset
    (with `audience_source` / `audience_confirmation_prompt` / `comms_type`
    additionally stamped on it) when `refused` is False; `None` when refused
    — the caller MUST NOT write the artifact in that case (fail-closed).

    Raises ValueError for an unknown `comms_type` (a caller-programming
    error — distinct from the RUNTIME refusal conditions above, which are
    legitimate recorded outcomes, not exceptions).
    """
    if comms_type not in COMMS_TYPES:
        raise ValueError(
            "comms_type %r not in the five outside-world comms types %r"
            % (comms_type, COMMS_TYPES))

    dept = department or COMMS_TYPE_DEPARTMENTS[comms_type]

    pb = _load_persona_blend()
    if pb is None:
        return {
            "comms_type": comms_type, "flag_enabled": flag_enabled(),
            "refused": True, "refusal_reason": "blend_module_unreachable",
            "topic_factored": False, "topic": "", "audience_confirmation": None,
            "bundle": None,
        }

    enabled = flag_enabled()

    if not enabled:
        # Revert path — today's per-task audience resolution, unchanged.
        bundle = pb.build_bundle(
            task_text, dept, paths=paths, db_path=db_path, use_llm=use_llm,
            record=record, max_task_personas=max_task_personas, variety=variety,
            topic_hint=topic_hint, audience_override=audience_override)
        return {
            "comms_type": comms_type, "flag_enabled": False, "refused": False,
            "refusal_reason": None, "topic_factored": None,
            "topic": bundle.get("topic"), "audience_confirmation": None,
            "bundle": bundle,
        }

    # ── mandatory path ──────────────────────────────────────────────────────
    topic, topic_factored = _derive_topic(pb, comms_type, task_text, topic_hint)
    if not topic_factored:
        return {
            "comms_type": comms_type, "flag_enabled": True, "refused": True,
            "refusal_reason": "topic_not_factored", "topic_factored": False,
            "topic": "", "audience_confirmation": None, "bundle": None,
        }

    # catalog/company_cfg default to the same live resolution build_bundle
    # itself would use, so resolve_comms_audience reasons over the real ICP —
    # resolved via the selector module persona_blend already loads lazily.
    sel = pb._selector()
    _paths = paths if paths is not None else sel.get_openclaw_paths()
    _catalog = catalog if catalog is not None else pb.load_catalog(_paths)
    _company_cfg = company_cfg if company_cfg is not None else (sel.load_company_config(_paths) or {})
    _soul_text = soul_text
    if not _soul_text:
        try:
            soul_p = _paths.get("soul_md") if isinstance(_paths, dict) else None
            if soul_p and Path(soul_p).exists():
                _soul_text = Path(soul_p).read_text(encoding="utf-8", errors="replace")
        except Exception:
            _soul_text = ""

    audience_conf = resolve_comms_audience(
        pb, _catalog, _company_cfg, _soul_text, audience_override=audience_override)

    if audience_conf.get("audience_source") not in ("standard", "specific"):
        # Defensive — resolve_comms_audience always returns one of the two;
        # this is the fail-closed backstop the BINARY acceptance (d) requires
        # so "no audience decision recorded" can never silently pass through.
        return {
            "comms_type": comms_type, "flag_enabled": True, "refused": True,
            "refusal_reason": "audience_not_recorded", "topic_factored": True,
            "topic": topic, "audience_confirmation": audience_conf, "bundle": None,
        }

    bundle_audience_override = (
        audience_override.strip()
        if audience_conf["audience_source"] == "specific" else "")

    bundle = pb.build_bundle(
        task_text, dept, paths=paths, db_path=db_path, use_llm=use_llm,
        record=record, max_task_personas=max_task_personas, variety=variety,
        topic_hint=topic, audience_override=bundle_audience_override,
        force_content_task=True)

    bundle["audience_source"] = audience_conf["audience_source"]
    bundle["audience_confirmation_prompt"] = STANDARD_OR_SPECIFIC_PROMPT
    bundle["comms_type"] = comms_type

    return {
        "comms_type": comms_type, "flag_enabled": True, "refused": False,
        "refusal_reason": None, "topic_factored": True, "topic": topic,
        "audience_confirmation": audience_conf, "bundle": bundle,
    }


# --------------------------------------------------------------------------- #
# CLI self-test
# --------------------------------------------------------------------------- #
def _self_test() -> int:
    """Hermetic-ish smoke test (uses the real persona_blend module + its own
    selector/decompose lazy-load, so it degrades gracefully off-platform —
    the full fixture-driven acceptance battery lives in
    tests/unit/u116-comms-audience-trigger-proof.test.py)."""
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    check("COMMS_TYPES has the 5 ADD-2 comms types",
          set(COMMS_TYPES) == {"page", "blog", "email", "sms", "social"})
    check("STANDARD_OR_SPECIFIC_PROMPT is the exact ADD-2 question",
          STANDARD_OR_SPECIFIC_PROMPT == (
              "Should I use your standard audience, or is there a "
              "specific/different audience you want this message for?"))

    try:
        build_comms_trigger("carrier-pigeon", "write something", "marketing")
        check("unknown comms_type raises ValueError", False)
    except ValueError:
        check("unknown comms_type raises ValueError", True)

    pb = _load_persona_blend()
    if pb is None:
        print("  [SKIP] persona_blend.py unreachable — live build_comms_trigger checks skipped")
    else:
        topic, factored = _derive_topic(pb, "email", "write an email", "")
        check("bare comms-type-only task text -> topic NOT factored", not factored)
        topic, factored = _derive_topic(pb, "email", "write an email about Q3 budgeting wins", "")
        check("real task-text signal -> topic factored", factored and "budgeting" in topic)
        topic, factored = _derive_topic(pb, "email", "write an email", "Q3 budgeting wins")
        check("explicit topic_hint always factors", factored and topic == "Q3 budgeting wins")

    print("== comms_audience_trigger self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="U116 (E6-2, ADD-2) communication trigger + audience-"
                    "confirmation prompt for outside-world comms.")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(_self_test())
    ap.print_help()
