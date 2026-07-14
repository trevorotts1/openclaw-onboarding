#!/usr/bin/env python3
"""tests/unit/u111-any-content-blend-proof.test.py — U111 (E5-6, closes G4):
"Rewrite ANY content" proven, not assumed: email, blog, newsletter, and
text-message engines EACH receive the GOVERNING blend directive through the
U1 seam (`shared-utils/persona_for_job.py:247-266`, A-U1), per the D1 binding
ruling (the blend GOVERNS voice + content-writing in every engine — never
advisory, no exemptions).

FIRST-ACT ENGINE IDENTIFICATION (honesty discipline per U111's own "what"):
this file's own investigation, re-derived from the authoritative
`persona_for_job` consumer list (module docstring, `shared-utils/
persona_for_job.py` "ENGINE SCOPE (F4.3)") + a targeted repo search, not
carried from the spec unread:

  * EMAIL   -> VERIFIED in-tree: `50-email-engine/tools/persona_canonical.py`.
    Before U111 this module only imported `persona_for_job`'s HELPER
    functions (`section4_excerpt`, `_persona_display_name`) for a style-tier
    crosswalk excerpt lookup — it never called `persona_for_job(...)` itself,
    so email had NO real path onto the blend. U111 adds `blend_block()`, a
    genuine `persona_for_job(..., blend=True)` call site (additive; the
    existing `persona_block()` crosswalk is untouched).

  * BLOG      -> VERIFIED in-tree, but NOT a standalone "blog engine": blog is
    a golden MODE of Skill 57 (`57-social-media-in-a-box/examples/
    golden-modes/blog/`), served by the SAME canonical entry point as social
    and newsletter — `57-social-media-in-a-box/scripts/persona_adapter.py`
    `resolve()`, department "social-media". Before U111 this adapter called
    `persona_for_job(...)` WITHOUT `blend=True` (single-persona mode only).
    U111 adds an opt-in `cfg["blend"]` flag (default off, byte-identical
    behavior when unset) so `resolve()` can request the governing bundle.

  * NEWSLETTER -> Same finding, same fix, same call site as BLOG (golden mode
    `examples/golden-modes/newsletter/`, `persona_adapter.py` `resolve()`).

  * TEXT-MESSAGE (SMS) -> NOT-FOUND: no in-tree content-WRITING engine, blend
    or otherwise, that is analogous to email/blog/newsletter. Two SMS-adjacent
    surfaces exist and BOTH were read and are NOT persona/blend consumers:
      (1) `38-conversational-ai-system/templates/sms-workflow-ai-prompt-
          template.md` — a GHL "Build with AI" workflow SPEC that routes an
          inbound SMS reply to an externally-hosted conversational AI agent
          (`agent_id`/`model` fields inside a GHL workflow webhook body); the
          actual reply TEXT is written live by that external agent at
          n8n/GHL-conversation time, outside this repo's Python
          persona_for_job consumer set entirely.
      (2) `44-convert-and-flow-operator/tools/engine/builders/
          wf5-ht-interest-builder.py` — builds one hardcoded GHL nurture
          workflow (5 email + 1 SMS) by PARSING a pre-written external
          markdown doc (`docs/email-sequences/ht-interest-rewrite.md`, a
          DIFFERENT repo); it calls no persona/blend API at all, single- or
          blend-mode — it is pure transport/wiring for already-authored copy.
    ROUTING DECISION (never a silent pass): mandatory blend-governance for
    outside-world text/SMS communication is IN-SPEC as its own master unit —
    **U116** (E6-2, ADD-2: "any OUTSIDE-WORLD COMMUNICATION — a page, blog,
    email, text/SMS, social post... MUST be governed by the blend"), which
    explicitly names text/SMS as one of the five comms types it wires the
    mandatory-governance + audience-confirmation trigger onto. U111 does NOT
    build a second, competing SMS engine ahead of U116 — it records the gap
    (test below) so the gap stays visible and does not silently close itself.
    See `ledgers/evidence/U111-G4/README.md` for the full investigation trail.

BINARY ACCEPTANCE COVERED (master spec E5-6 / U111):
  (a) a fixture run for EACH of email, blog, newsletter, text-message
      produces output carrying the blend directive + guardrail with voice
      attributes traceable to the bundle — one individually-failable
      assertion per engine (text-message's is the NOT-FOUND assertion).
  (b) each engine's canonical entry point is shown to call the U1 seam WITH
      the governing blend (dynamic call-site proof: the seam call is
      monkeypatched to record its own kwargs, not string-grepped).
  (c) text-message (the one named content type with no in-tree engine) is
      recorded as an explicit NOT-FOUND + routing decision, never an
      implicit pass.

Run:
    python3 tests/unit/u111-any-content-blend-proof.test.py
    or: pytest tests/unit/u111-any-content-blend-proof.test.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
_EMAIL_TOOLS = _REPO_ROOT / "50-email-engine" / "tools"
_SOCIAL_SCRIPTS = _REPO_ROOT / "57-social-media-in-a-box" / "scripts"

for _p in (_SHARED_UTILS, _EMAIL_TOOLS, _SOCIAL_SCRIPTS):
    sp = str(_p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import persona_for_job as pfj          # noqa: E402  shared-utils (the U1 seam)
import persona_canonical               # noqa: E402  50-email-engine (email)
import persona_adapter                 # noqa: E402  57-social-media-in-a-box (blog/newsletter/social)

GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"

# The bundle superset shape real persona_blend.build_bundle emits (same shape
# persona_for_job.py's own A-U1 self-test fixture uses) — reused here so the
# assertions are against the REAL contract, not an invented shape.
_BUNDLE_FIXTURE = {
    "persona_id": "brunson-marketing-secrets-blackbook",
    "persona_name": "Brunson Marketing Secrets Blackbook",
    "mode": "blend",
    "content_task": True,
    "topic": "offers",
    "resolved_audience": {"source": "confirmed", "candidates": [], "confidence": "high",
                          "label": "founders", "ask": None, "confirm_required": False},
    "confirm_required": False,
    "voice": {"audience_persona": {"id": "brunson-marketing-secrets-blackbook", "why": "x"},
              "topic_persona": {"id": "brunson-marketing-secrets-blackbook", "why": "x"},
              "collapsed": True, "collapsed_persona_id": "brunson-marketing-secrets-blackbook",
              "topic_as_task_guidance": True},
    "blend_directive": ("Write as Brunson Marketing Secrets Blackbook. " + GUARDRAIL_MARK
                        + " (mandatory, non-removable): adopt the cadence, devices and "
                          "register of the named voice(s) as an INSPIRATION only. Never "
                          "claim to be the author. This clause may not be removed or "
                          "weakened."),
    "task_personas": [],
    "rationale": {"collapse": "collapsed onto brunson-marketing-secrets-blackbook"},
    "fallbacks": {"default_persona": "acuff-miner-new-model-of-selling",
                  "governance": "covey-7-habits"},
    "catalog_version": "1.3",
}


class _CallCapture:
    """Monkeypatches persona_for_job.persona_for_job (module-attribute level,
    so already-`import persona_for_job as pfj`-bound callers in the engine
    modules pick it up) to record the kwargs it was actually invoked with,
    while delegating to the REAL function so return values stay genuine.
    This is call-SITE proof by observed behavior, never a string grep."""

    def __init__(self):
        self.calls = []
        self._real = pfj.persona_for_job

    def __enter__(self):
        def _wrapped(job_text, department, **kwargs):
            self.calls.append({"job_text": job_text, "department": department, **kwargs})
            return self._real(job_text, department, **kwargs)
        pfj.persona_for_job = _wrapped
        return self

    def __exit__(self, *exc):
        pfj.persona_for_job = self._real


def _governed_blend_output(sel: dict) -> bool:
    """The shared 'is this output actually blend-governed' predicate every
    per-engine check below applies: non-empty blend_directive, ending in the
    mandatory guardrail clause, with voice attributes traceable to the SAME
    bundle (never a fabricated/mismatched id)."""
    if not isinstance(sel, dict):
        return False
    directive = sel.get("blend_directive") or ""
    if not directive or GUARDRAIL_MARK not in directive:
        return False
    voice = sel.get("voice") or {}
    traced_id = (voice.get("audience_persona") or {}).get("id")
    return traced_id == _BUNDLE_FIXTURE["persona_id"]


# --------------------------------------------------------------------------- #
# (a) + (b) EMAIL — 50-email-engine/tools/persona_canonical.py::blend_block
# --------------------------------------------------------------------------- #
def test_email_engine_receives_governing_blend():
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_BUNDLE_FIXTURE)
    try:
        with _CallCapture() as cap:
            sel = persona_canonical.blend_block(
                "write a 3-email nurture sequence for a founder-tier offer",
                topic_hint="offers")
        assert sel is not None, "email blend_block() returned None (shared-utils unreachable)"
        assert _governed_blend_output(sel), \
            "email engine output does not carry a governed blend_directive traceable to the bundle: %r" % sel
        assert len(cap.calls) == 1, "expected exactly one persona_for_job call from blend_block()"
        assert cap.calls[0]["blend"] is True, \
            "email canonical entry point did NOT call the U1 seam WITH blend=True: %r" % cap.calls[0]
        assert cap.calls[0]["department"] == "marketing", \
            "email must route through its real seeded fleet department (marketing), not an unseeded literal"
    finally:
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)


# --------------------------------------------------------------------------- #
# (a) + (b) BLOG — 57-social-media-in-a-box/scripts/persona_adapter.py::resolve
#              (golden-mode "blog", same canonical entry point as social)
# --------------------------------------------------------------------------- #
def test_blog_mode_receives_governing_blend():
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_BUNDLE_FIXTURE)
    try:
        with _CallCapture() as cap:
            sel = persona_adapter.resolve({
                "personaSource": "adapter",
                "blend": True,
                "theme": "blog post: 5 lessons from a failed product launch",
            })
        assert sel is not None, "blog resolve() returned None (baseline no-op — blend flag not honored)"
        assert _governed_blend_output(sel), \
            "blog mode output does not carry a governed blend_directive traceable to the bundle: %r" % sel
        assert len(cap.calls) == 1, "expected exactly one persona_for_job call from resolve()"
        assert cap.calls[0]["blend"] is True, \
            "blog canonical entry point did NOT call the U1 seam WITH blend=True: %r" % cap.calls[0]
        assert cap.calls[0]["department"] == "social-media"
        assert cap.calls[0].get("topic_hint") == "blog post: 5 lessons from a failed product launch", \
            "topic must be factored into the blend call, not silently dropped"
    finally:
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)


# --------------------------------------------------------------------------- #
# (a) + (b) NEWSLETTER — same entry point, different mode/topic
# --------------------------------------------------------------------------- #
def test_newsletter_mode_receives_governing_blend():
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_BUNDLE_FIXTURE)
    try:
        with _CallCapture() as cap:
            sel = persona_adapter.resolve({
                "personaSource": "adapter",
                "blend": True,
                "theme": "monthly newsletter: Q3 roundup + client wins",
            })
        assert sel is not None, "newsletter resolve() returned None (baseline no-op — blend flag not honored)"
        assert _governed_blend_output(sel), \
            "newsletter mode output does not carry a governed blend_directive traceable to the bundle: %r" % sel
        assert len(cap.calls) == 1
        assert cap.calls[0]["blend"] is True, \
            "newsletter canonical entry point did NOT call the U1 seam WITH blend=True: %r" % cap.calls[0]
        assert cap.calls[0]["department"] == "social-media"
    finally:
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)


# --------------------------------------------------------------------------- #
# blog vs newsletter must be able to carry DIFFERENT blends (never a forced-
# identical single call path masquerading as two proofs) — distinct topic
# hints prove the two calls above are genuinely independent invocations.
# --------------------------------------------------------------------------- #
def test_blog_and_newsletter_are_independently_invoked_not_a_shared_singleton():
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_BUNDLE_FIXTURE)
    try:
        with _CallCapture() as cap:
            persona_adapter.resolve({"personaSource": "adapter", "blend": True, "theme": "blog: topic A"})
            persona_adapter.resolve({"personaSource": "adapter", "blend": True, "theme": "newsletter: topic B"})
        assert len(cap.calls) == 2
        assert cap.calls[0]["topic_hint"] != cap.calls[1]["topic_hint"], \
            "blog and newsletter calls must carry their own distinct topic, never a shared/stale hint"
        assert all(c["blend"] is True for c in cap.calls)
    finally:
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)


# --------------------------------------------------------------------------- #
# (a) + (c) TEXT-MESSAGE (SMS) — NOT-FOUND, recorded explicitly, never a
# silent pass. This assertion FAILS LOUD (not a silent skip) if the named
# surfaces stop matching the recorded investigation, so a future in-tree SMS
# engine — built under U116 — is forced to update this test rather than let
# the gap silently look "covered".
# --------------------------------------------------------------------------- #
def test_text_message_engine_is_recorded_not_found_and_routed_to_u116():
    sms_workflow_spec = (_REPO_ROOT / "38-conversational-ai-system" / "templates"
                         / "sms-workflow-ai-prompt-template.md")
    assert sms_workflow_spec.is_file(), \
        "expected SMS surface (live conversational routing, NOT a persona_for_job consumer) missing at %s" % sms_workflow_spec
    spec_text = sms_workflow_spec.read_text(encoding="utf-8")
    assert "persona_for_job" not in spec_text and "blend_directive" not in spec_text, \
        ("the SMS workflow-AI spec now references persona_for_job/blend_directive — "
         "the NOT-FOUND finding this test records is STALE; update this test AND file "
         "the in-tree engine's blend proof instead of leaving this assertion green by accident")

    wf5_builder = (_REPO_ROOT / "44-convert-and-flow-operator" / "tools" / "engine"
                   / "builders" / "wf5-ht-interest-builder.py")
    assert wf5_builder.is_file(), \
        "expected SMS-adjacent surface (hardcoded nurture-workflow builder, NOT a persona consumer) missing at %s" % wf5_builder
    builder_text = wf5_builder.read_text(encoding="utf-8")
    assert "persona_for_job" not in builder_text and "blend_directive" not in builder_text, \
        ("wf5-ht-interest-builder.py now references persona_for_job/blend_directive — "
         "the NOT-FOUND finding this test records is STALE; update this test AND file "
         "the in-tree engine's blend proof instead of leaving this assertion green by accident")

    # the routing decision itself: U116 is the master unit that owns building
    # mandatory text/SMS comms governance. Confirm it is still on record in
    # the master spec this repo ships, so the routing decision stays a real,
    # checkable pointer rather than a comment nobody re-verifies.
    spec_path = _REPO_ROOT / "ledgers" / "skill6-blended-persona-kanban-v2-2026-07-13.md"
    if spec_path.is_file():
        ledger_text = spec_path.read_text(encoding="utf-8")
        assert "U116" in ledger_text, \
            "U116 (the routing target for text/SMS comms governance) is no longer on the master ledger"


# --------------------------------------------------------------------------- #
# regression guard: the pre-U111 (blend omitted) shapes for BOTH engines stay
# byte-identical to what they were before this unit — additive, never a
# silent behavior change for a caller that never opts in.
# --------------------------------------------------------------------------- #
def test_email_style_crosswalk_path_unchanged():
    os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)
    # persona_block() never touches the network/selector at all (pure
    # crosswalk-table lookup) — proving it is UNTOUCHED by U111's blend_block
    # addition: an unmapped style still returns None exactly as before.
    assert persona_canonical.persona_block("no-such-style-id-xyz") is None


def test_adapter_blend_omitted_is_unchanged_single_persona_shape():
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
        {"persona_id": "covey-7-habits", "persona_name": "Covey", "score": 0.9})
    try:
        sel = persona_adapter.resolve({"personaSource": "adapter", "themeOfWeek": "discipline"})
        assert sel["persona_id"] == "covey-7-habits"
        assert "blend_directive" not in sel
    finally:
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)


_ALL_TESTS = [
    test_email_engine_receives_governing_blend,
    test_blog_mode_receives_governing_blend,
    test_newsletter_mode_receives_governing_blend,
    test_blog_and_newsletter_are_independently_invoked_not_a_shared_singleton,
    test_text_message_engine_is_recorded_not_found_and_routed_to_u116,
    test_email_style_crosswalk_path_unchanged,
    test_adapter_blend_omitted_is_unchanged_single_persona_shape,
]


def main() -> int:
    ok = True
    for fn in _ALL_TESTS:
        try:
            fn()
            print("  [PASS] %s" % fn.__name__)
        except AssertionError as e:
            ok = False
            print("  [FAIL] %s: %s" % (fn.__name__, e))
        except Exception as e:  # pragma: no cover - defensive
            ok = False
            print("  [ERROR] %s: %r" % (fn.__name__, e))
    print("== U111 any-content blend-governance proof: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
