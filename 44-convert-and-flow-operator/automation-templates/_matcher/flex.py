#!/usr/bin/env python3
"""flex.py — intent-mode detection + flexibility decision mapping.

SHARED CORE for the Skill-44 automation matcher (this folder) AND the Skill-6 funnel
matcher (06-ghl-install-pages/tools/funnel_matcher.py — same logic is mirrored inline
there so the funnel-matcher patch stays a single self-contained file).

CORE PRINCIPLE — FLEXIBILITY
----------------------------
Every template/persona/sequence is a GUIDE and a RESOURCE, NEVER a rule or a
requirement. It must NOT dominate the user's desire. Three modes:

  1. EXPLICIT_USER_SPEC      -> the user told us exactly what they want. Do THAT.
                                The closest template is returned only as an optional
                                reference; it is NEVER imposed/overridden onto the
                                user's choice.  decision = HONOR_USER.
  2. UNSURE_WANTS_SUGGESTION -> the user is unsure. SUGGEST the proven template +
                                WHY, then let them decide.  decision = SUGGEST_TEMPLATE
                                (await confirm).
  3. HANDS_OFF_DO_IT_ALL     -> 'just do it'. Build the whole thing from the template.
                                decision = USE_TEMPLATE.

Always overridable, mixable, customizable, ignorable. It assists; it never dominates.
If nothing fits -> CREATE_NEW (+ save back). The matcher NEVER blocks a build.

This module is stdlib-only, deterministic, no network. It does NO scoring — it only
detects the mode and maps (mode, has_confident_match) -> a flexibility decision.
"""
from __future__ import annotations
import re
from typing import Any

# ── intent modes ─────────────────────────────────────────────────────────────
MODE_EXPLICIT = "EXPLICIT_USER_SPEC"
MODE_UNSURE = "UNSURE_WANTS_SUGGESTION"
MODE_HANDSOFF = "HANDS_OFF_DO_IT_ALL"
MODES = (MODE_EXPLICIT, MODE_UNSURE, MODE_HANDSOFF)

# ── decisions ────────────────────────────────────────────────────────────────
DEC_HONOR_USER = "HONOR_USER"        # EXPLICIT: build the user's spec; template = optional ref
DEC_SUGGEST = "SUGGEST_TEMPLATE"     # UNSURE + confident match: recommend + why, await confirm
DEC_USE = "USE_TEMPLATE"             # HANDS_OFF + confident match: build it all from the template
DEC_CREATE_NEW = "CREATE_NEW"        # nothing fits: build net-new, save back

# Cue phrases. Order of precedence at detect time: EXPLICIT > HANDS_OFF > UNSURE > default.
_HANDSOFF_CUES = [
    "just do it", "just build", "just make it", "just set it up", "the full", "handle it",
    "you handle", "take care of it", "do it all", "do the rest", "do everything",
    "build the whole", "the whole", "whole thing", "whole funnel", "complete funnel",
    "full funnel", "full sequence", "set it all up", "set up everything",
    "set and forget", "turnkey", "done for me", "done-for-you", "dfy", "your call",
    "you decide", "you choose", "whatever you think", "whatever's best",
    "whatever is best", "best practice", "do what's best", "do what is best",
    "make it happen", "i trust you", "up to you", "surprise me", "go ahead and build",
    "build it out", "wire it all", "all of it",
]
_UNSURE_CUES = [
    "not sure", "unsure", "no idea", "don't know", "dont know", "what do you recommend",
    "what would you recommend", "what would you suggest", "what do you suggest",
    "any suggestions", "any recommendation", "recommend", "suggest", "which one",
    "which should", "what should i", "what should we", "help me decide", "help me pick",
    "what are my options", "what are the options", "options", "thinking about",
    "maybe", "considering", "torn between", "should i use", "is there a", "what's best",
    "what is best", "advice", "guidance", "not certain", "kind of want",
]
# A *user-provided spec* is the strongest EXPLICIT signal (a dict the user filled in).
_EXPLICIT_SPEC_KEYS = ("spec", "sequence", "steps", "user_steps", "user_sequence",
                       "user_spec", "my_sequence", "exact_steps")
_EXPLICIT_CUES = [
    "exactly", "specifically", "to the letter", "as written", "do not change",
    "don't change", "dont change", "no changes", "must be", "must have", "has to",
    "i want it to", "i need it to", "use my", "use these", "here's my", "heres my",
    "here is my", "my own", "my exact", "follow this", "follow my", "build this:",
    "build exactly", "this exact", "these exact", "only these", "only the", "just the",
    "strictly", "verbatim", "i already have", "i have a spec", "per my spec",
    "do it this way", "the way i want", "i'll specify", "i will specify",
]


def _request_text(request: Any) -> str:
    if isinstance(request, str):
        return request.lower()
    if isinstance(request, dict):
        parts = [str(request.get(k, "")) for k in
                 ("text", "brief", "goal", "intent", "description", "ask", "message")]
        return " ".join(p for p in parts if p).lower()
    return str(request or "").lower()


def _has_user_spec(request: Any) -> bool:
    """True if the user handed us a structured/own sequence to honor verbatim."""
    if not isinstance(request, dict):
        return False
    for k in _EXPLICIT_SPEC_KEYS:
        v = request.get(k)
        if isinstance(v, (list, tuple)) and len(v) >= 1:
            return True
        if isinstance(v, str) and v.strip():
            return True
    return False


def _numbered_steps(text: str) -> int:
    """Count user-authored ordered steps (e.g. '1. ... 2. ...') — a spec signal."""
    return len(re.findall(r"(?:^|\s)(?:[1-9]\d?[\.\)]|step\s*[1-9])", text))


def _any(text: str, cues: list[str]) -> str | None:
    for c in cues:
        if c in text:
            return c
    return None


def detect_mode(request: Any, override: str | None = None) -> dict:
    """Detect the intent mode for a request.

    Returns ``{mode, reason, cue}``. Precedence (least-dominating default):
      explicit override > user-provided spec / EXPLICIT cues > HANDS_OFF cues >
      UNSURE cues > default UNSURE.

    The DEFAULT is UNSURE on purpose: when we cannot tell, the least-dominating move
    is to SUGGEST (recommend + await confirm), never to silently impose a template
    or auto-build. This is the flexibility principle as a tie-breaker.
    """
    if override in MODES:
        return {"mode": override, "reason": "explicit caller/user override", "cue": override}

    text = _request_text(request)

    # 1) EXPLICIT — the user gave their own spec, or said 'exactly/use my/...'.
    if _has_user_spec(request):
        return {"mode": MODE_EXPLICIT, "reason": "user supplied an explicit spec/sequence",
                "cue": "user_spec"}
    if _numbered_steps(text) >= 2:
        return {"mode": MODE_EXPLICIT, "reason": "user wrote their own ordered steps",
                "cue": "numbered_steps"}
    cue = _any(text, _EXPLICIT_CUES)
    if cue:
        return {"mode": MODE_EXPLICIT, "reason": f"explicit-spec cue: '{cue}'", "cue": cue}

    # 2) HANDS_OFF — 'just do it / your call / build the whole thing'.
    cue = _any(text, _HANDSOFF_CUES)
    if cue:
        return {"mode": MODE_HANDSOFF, "reason": f"hands-off cue: '{cue}'", "cue": cue}

    # 3) UNSURE — 'not sure / what do you recommend / which one'.
    cue = _any(text, _UNSURE_CUES)
    if cue:
        return {"mode": MODE_UNSURE, "reason": f"unsure cue: '{cue}'", "cue": cue}

    # 4) default — UNSURE (least-dominating: suggest, never impose/auto-build).
    return {"mode": MODE_UNSURE, "reason": "no strong cue -> default to suggest (never impose)",
            "cue": None}


def decide(mode: str, *, has_confident_match: bool, has_any_match: bool = False) -> dict:
    """Map (mode, match availability) -> a flexibility decision.

    Returns a decision bundle::

        {decision, imposes_on_user, override_allowed, await_confirm,
         build_from_template, template_role, note}

    Invariants (the flexibility contract):
      * imposes_on_user is ALWAYS False — the matcher never overrides a user's desire.
      * override_allowed is ALWAYS True — every output is overridable/mixable/ignorable.
      * the matcher NEVER blocks: the worst case is CREATE_NEW (build net-new + save).
    """
    base = {"imposes_on_user": False, "override_allowed": True}

    if mode == MODE_EXPLICIT:
        # Honor the user's spec. If a template happens to be close, return it ONLY as
        # an optional reference — never impose it onto their choice.
        return {**base, "decision": DEC_HONOR_USER,
                "await_confirm": False, "build_from_template": False,
                "template_role": ("optional_reference" if has_any_match else "none"),
                "note": "User has an explicit desire — build exactly that. Closest template is "
                        "an optional reference only; it is never imposed or overridden onto "
                        "the user's choice."}

    if mode == MODE_HANDSOFF:
        if has_confident_match:
            return {**base, "decision": DEC_USE,
                    "await_confirm": False, "build_from_template": True,
                    "template_role": "build_source",
                    "note": "User wants it handled ('just do it') and a proven template fits — "
                            "build the whole thing from it (still fully overridable after)."}
        return {**base, "decision": DEC_CREATE_NEW,
                "await_confirm": False, "build_from_template": False,
                "template_role": "none",
                "note": "User wants it handled but nothing fits well — create a net-new "
                        "automation and save it back so the library grows."}

    # UNSURE
    if has_confident_match:
        return {**base, "decision": DEC_SUGGEST,
                "await_confirm": True, "build_from_template": False,
                "template_role": "suggested",
                "note": "User is unsure — suggest the proven template and explain why, then "
                        "let the user decide. Do NOT build until they confirm."}
    return {**base, "decision": DEC_CREATE_NEW,
            "await_confirm": True, "build_from_template": False,
            "template_role": "none",
            "note": "User is unsure and nothing fits — propose creating a net-new automation; "
                    "await confirm before building, then save it back."}


def flex_principle() -> dict:
    """The flexibility manifesto, machine-readable (logged with every decision)."""
    return {
        "core": "Every template is a GUIDE and a RESOURCE, never a rule or a requirement. "
                "It assists; it never dominates the user's desire.",
        "modes": {
            MODE_EXPLICIT: "Do exactly what the user wants; template is an optional reference only.",
            MODE_UNSURE: "Suggest the proven template + why; let the user decide.",
            MODE_HANDSOFF: "Build the whole thing from the template.",
        },
        "always": "Overridable, mixable, customizable, ignorable. Never blocks a build.",
    }


# ── tiny self-test ───────────────────────────────────────────────────────────
def _selftest() -> int:
    cases = [
        ("just build me the whole webinar follow-up", MODE_HANDSOFF),
        ("not sure what follow-up I need — what do you recommend?", MODE_UNSURE),
        ("I want exactly these 3 emails, do not change the order", MODE_EXPLICIT),
        ({"text": "set this up", "steps": ["email 1", "email 2"]}, MODE_EXPLICIT),
        ("build a soap opera sequence for new leads", MODE_UNSURE),   # neutral -> default UNSURE
        ("you decide, turnkey please", MODE_HANDSOFF),
        ("here's my sequence, follow this to the letter", MODE_EXPLICIT),
        ({"text": "step 1 welcome, step 2 bond, step 3 pitch"}, MODE_EXPLICIT),
    ]
    ok = 0
    for req, want in cases:
        got = detect_mode(req)["mode"]
        flag = "ok " if got == want else "FAIL"
        ok += got == want
        print(f"[{flag}] want={want:<24} got={got:<24} :: {str(req)[:46]}")
    # decision matrix
    print("\ndecision matrix:")
    for m in MODES:
        for hc in (True, False):
            d = decide(m, has_confident_match=hc, has_any_match=True)
            assert d["imposes_on_user"] is False and d["override_allowed"] is True
            print(f"  {m:<24} confident={hc!s:<5} -> {d['decision']}")
    print(f"\n{ok}/{len(cases)} mode cases passed")
    print("SELFTEST PASS" if ok == len(cases) else "SELFTEST FAIL")
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
