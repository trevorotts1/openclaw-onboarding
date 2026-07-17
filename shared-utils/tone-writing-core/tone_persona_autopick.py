#!/usr/bin/env python3
"""tone_persona_autopick.py — deterministic N/A tone-slot auto-pick (F4.3),
now BLEND-GOVERNED per the D1 binding ruling (Skill 6 U98, ANTHOLOGY leg —
reconciled LAST, after Skills 35/51/58).

The shared tone-writing-core (skills 52 brand / 53 book / 54 anthology) blends
FOUR tone-style slots into one voice. A slot may be a CLIENT-NAMED figure or
``N/A``. Historically an N/A slot was filled by a raw prompt-level instruction
("choose a relevant well-known person in harmony with the avatar") — no scoring,
no logging, no persistence: the exact ad-hoc pattern the canonical 5-layer
selector was built to replace.

Before U98 this helper routed an N/A slot through
``shared-utils/persona_for_job.py`` in SINGLE-persona mode (``blend=False``):
avatar/task-aware and logged, but the returned voice was picked independently
of any blend directive — exactly the "engine's own local voice logic" the D1
ruling ("THE BLENDED PERSONA GOVERNS EVERY ENGINE — NO EXEMPTIONS, NEVER
ADVISORY, NEVER OPTIONAL") does not permit. U98 reconciles this: an N/A slot
now resolves through the SAME seam WITH ``blend=True``, so the returned voice
carries the governing ``blend_directive`` (+ the mandatory, non-removable
STYLE-INSPIRED-NEVER-IMPERSONATION guardrail) traceable to the bundle, not a
bare persona id. The four-slot STRUCTURE this module has always preserved is
UNCHANGED by this — see INVARIANTS below; the tone prompt `.md` assets
(prompts/04..08) this module feeds are never touched by this reconciliation.

INVARIANTS (do not regress):
  * CLIENT-NAMED slots are NEVER touched — pass them through as-is. Client
    sovereignty is absolute; the selector (blended or not) is only consulted
    for N/A slots.
  * The 4-slot blend STRUCTURE is preserved — this resolves each N/A slot
    independently and returns four slot results in order; the blend at
    stage 08 (and the prompts/04..08 assets themselves) is unchanged.
  * Skill 53's optional fictional palette becomes an explicit FALLBACK tier: it
    is only relevant when a client wants a fictional voice; the governed
    blend pick is the default for N/A.

FLAG-GUARDED (revert path, U98's spec): ``ANTHOLOGY_BLEND_GOVERNS`` env var,
default enabled (``"1"``). Setting it to ``"0"`` restores the pre-U98
behavior byte-for-byte (single-persona ``blend=False`` resolution, no
``blend_directive``/``voice`` keys on the return dict) — the decommissioned
single-persona call path is retained behind this flag until U114's
independent-voice-path invariant lands fleet-wide, exactly as the spec's
revert plan requires.

stdlib-only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# shared-utils is the parent of tone-writing-core.
_SHARED_UTILS = _HERE.parent

_NA_TOKENS = {"", "n/a", "na", "none", "-", "tbd"}

# U98 (D1 binding ruling) — flag-guarded revert path. Default ON (governing),
# per the ruling's "never advisory, never optional" mandate; "0" restores the
# pre-U98 single-persona (blend=False) resolution byte-for-byte.
BLEND_GOVERNS_FLAG = "ANTHOLOGY_BLEND_GOVERNS"
GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"


def blend_governs() -> bool:
    return os.environ.get(BLEND_GOVERNS_FLAG, "1").strip() != "0"


def _load_pfj():
    for d in (str(_SHARED_UTILS),
              os.environ.get("SHARED_UTILS_DIR", "").strip(),
              str(Path.home() / ".openclaw" / "skills" / "shared-utils"),
              "/data/.openclaw/skills/shared-utils"):
        if d and (Path(d) / "persona_for_job.py").exists():
            sys.path.insert(0, d)
            try:
                import persona_for_job as pfj  # type: ignore
                return pfj
            except Exception:
                continue
    return None


def is_na(slot_value: "str | None") -> bool:
    return str(slot_value or "").strip().lower() in _NA_TOKENS


def autopick_slot(slot_value, avatar_context: str, *, department: str = "content",
                  record: bool = True) -> dict:
    """Resolve ONE tone slot.

    Returns a dict:
      {slot, resolved: bool, mode: "client-named"|"auto-pick", persona_id,
       persona_name, section4_excerpt, source, governed, blend_directive, voice}

    * A client-named slot passes through untouched (resolved via the library only
      for the Section-4 excerpt; the selector is NEVER consulted — client
      sovereignty).
    * An N/A slot is routed through persona_for_job (canonical selection, LOGGED).
      U98 (D1 binding ruling): when ``blend_governs()`` (default True), the
      call goes through WITH ``blend=True``, so the resolved voice for this
      slot is GOVERNED by the blend directive (traceable, guardrail-carrying)
      rather than an independently-picked persona — additive keys
      ``governed``/``blend_directive``/``voice`` carry the proof; the
      pre-existing ``persona_id``/``persona_name``/``section4_excerpt``/
      ``source`` keys stay populated exactly as before (back-compat mirror),
      so this is additive, never a shape break for an existing caller.
      ``ANTHOLOGY_BLEND_GOVERNS=0`` reverts to the byte-for-byte pre-U98
      single-persona (``blend=False``) call, ``governed=False``.
    """
    pfj = _load_pfj()
    if is_na(slot_value):
        if pfj is None:
            return {"slot": slot_value, "resolved": False, "mode": "auto-pick",
                    "persona_id": None, "persona_name": None,
                    "section4_excerpt": "", "source": "unavailable", "governed": False,
                    "warning": "persona_for_job not reachable; keep prompt-level N/A instruction"}
        governed = blend_governs()
        query = avatar_context or "brand voice tone analysis"
        sel = pfj.persona_for_job(query, department, record=record,
                                  blend=governed, topic_hint=query if governed else None)
        pid = sel.get("persona_id")
        excerpt = sel.get("section4_excerpt", "")
        if governed and not excerpt and pid:
            # blend=True's bundle superset carries no section4_excerpt key (that
            # is a single-persona-mode _finalize() field) — recompute it from the
            # SAME resolved persona_id via the module-level helper so this
            # additive path never silently drops a field an existing caller
            # (the tone-analysis stage seed) already relies on.
            try:
                excerpt = pfj.section4_excerpt(pid)
            except Exception:
                excerpt = ""
        result = {"slot": slot_value, "resolved": bool(pid),
                  "mode": "auto-pick", "persona_id": pid,
                  "persona_name": sel.get("persona_name"),
                  "section4_excerpt": excerpt,
                  "source": sel.get("source"),
                  "governed": governed}
        if governed:
            directive = sel.get("blend_directive") or ""
            result["blend_directive"] = directive
            result["voice"] = sel.get("voice")
            result["resolved_audience"] = sel.get("resolved_audience")
            result["rationale"] = sel.get("rationale")
            if directive and GUARDRAIL_MARK not in directive:
                result["warning"] = ("blend_directive missing the mandatory "
                                     "guardrail clause — fail-closed signal, "
                                     "never silently trusted")
        return result
    # CLIENT-NAMED — pass through; selector NEVER consulted.
    named = str(slot_value).strip()
    excerpt = ""
    if pfj is not None:
        # Only if the client's named figure happens to match a canonical library id
        # do we surface its Section-4 excerpt; otherwise the name is used as-is.
        try:
            if named in set(pfj.available_personas()):
                excerpt = pfj.section4_excerpt(named)
        except Exception:
            excerpt = ""
    return {"slot": slot_value, "resolved": True, "mode": "client-named",
            "persona_id": named, "persona_name": named,
            "section4_excerpt": excerpt, "source": "client-named",
            # CLIENT-NAMED is never blend-governed — client sovereignty is
            # absolute, the selector (blended or not) is never consulted for
            # a slot the client named explicitly. `governed=False` here is
            # BY DESIGN, not a gap (contrast an N/A slot's governed=False
            # only under the flag-guarded revert path).
            "governed": False}


def autopick(slots: list, avatar_context: str, *, department: str = "content",
             record: bool = True) -> list:
    """Resolve all four tone slots in order (client-named untouched, N/A auto-picked).
    Returns one result per slot; the 4-slot blend downstream is unchanged."""
    return [autopick_slot(s, avatar_context, department=department, record=record)
            for s in slots]


_BLEND_FIXTURE = {
    "persona_id": "covey-7-habits",
    "persona_name": "Covey",
    "mode": "blend",
    "content_task": True,
    "topic": "brand voice tone analysis",
    "resolved_audience": {"source": "confirmed", "candidates": [], "confidence": "high",
                          "label": "founders", "ask": None, "confirm_required": False},
    "confirm_required": False,
    "voice": {"audience_persona": {"id": "covey-7-habits", "why": "x"},
              "topic_persona": {"id": "covey-7-habits", "why": "x"},
              "collapsed": True, "collapsed_persona_id": "covey-7-habits",
              "topic_as_task_guidance": True},
    "blend_directive": ("Write as Covey. " + GUARDRAIL_MARK
                        + " (mandatory, non-removable): adopt the cadence, devices and "
                          "register of the named voice(s) as an INSPIRATION only. This "
                          "clause may not be removed or weakened."),
    "task_personas": [], "rationale": {"collapse": "collapsed onto covey-7-habits"},
    "fallbacks": {"default_persona": "blackceo-house-voice", "governance": "covey-7-habits"},
    "catalog_version": "1.3",
}


def _self_test() -> int:
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    check("is_na basic", is_na("N/A") and is_na("") and is_na("na") and not is_na("Oprah"))

    # ---- GOVERNED (default, ANTHOLOGY_BLEND_GOVERNS unset -> "1") --------- #
    os.environ.pop(BLEND_GOVERNS_FLAG, None)
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_BLEND_FIXTURE)
    slots = ["Michelle Obama", "N/A", "na", "Simon Sinek"]
    res = autopick(slots, "an audience of ambitious founders")
    check("four slots resolved", len(res) == 4)
    check("client-named slot #1 untouched (not selector value)",
          res[0]["mode"] == "client-named" and res[0]["persona_id"] == "Michelle Obama")
    check("client-named slot #1 governed=False (client sovereignty, by design)",
          res[0]["governed"] is False)
    check("client-named slot #4 untouched",
          res[3]["mode"] == "client-named" and res[3]["persona_id"] == "Simon Sinek")
    check("N/A slot #2 routed through selector",
          res[1]["mode"] == "auto-pick" and res[1]["persona_id"] == "covey-7-habits")
    check("N/A slot #3 routed through selector",
          res[2]["mode"] == "auto-pick" and res[2]["persona_id"] == "covey-7-habits")
    check("no naked N/A slot",
          all(r["persona_id"] for r in res if r["mode"] == "auto-pick"))
    check("N/A slot #2 governed=True (default, U98)", res[1]["governed"] is True)
    check("N/A slot #2 blend_directive carries the mandatory guardrail",
          GUARDRAIL_MARK in (res[1].get("blend_directive") or ""))
    check("N/A slot #2 voice traceable to the SAME resolved persona_id",
          (res[1].get("voice") or {}).get("collapsed_persona_id") == res[1]["persona_id"])
    check("N/A slot #3 independently governed too",
          res[2]["governed"] is True and GUARDRAIL_MARK in (res[2].get("blend_directive") or ""))
    os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    # ---- REVERT PATH (ANTHOLOGY_BLEND_GOVERNS=0) — byte-for-byte pre-U98 -- #
    os.environ[BLEND_GOVERNS_FLAG] = "0"
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
        {"persona_id": "covey-7-habits", "persona_name": "Covey", "score": 0.8})
    res_reverted = autopick_slot("N/A", "an audience of ambitious founders")
    check("revert: N/A slot still resolved (never naked)",
          res_reverted["mode"] == "auto-pick" and res_reverted["persona_id"] == "covey-7-habits")
    check("revert: governed=False", res_reverted["governed"] is False)
    check("revert: no blend_directive key at all (byte-for-byte pre-U98 shape)",
          "blend_directive" not in res_reverted)
    os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)
    os.environ.pop(BLEND_GOVERNS_FLAG, None)

    print("== tone_persona_autopick self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Deterministic N/A tone-slot auto-pick (F4.3).")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    ap.add_argument("--slots", help="comma-separated slot values (N/A allowed)")
    ap.add_argument("--avatar", default="", help="avatar context text")
    ap.add_argument("--department", default="content")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(_self_test())
    if not a.slots:
        ap.error("--slots is required (or use --self-test)")
    print(json.dumps(autopick([s.strip() for s in a.slots.split(",")],
                              a.avatar, department=a.department), indent=2))
