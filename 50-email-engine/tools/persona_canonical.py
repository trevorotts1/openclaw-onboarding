#!/usr/bin/env python3
"""persona_canonical.py — crosswalk a Skill-50 email tone-STYLE id to a REAL
canonical persona id (F4.3); also the Skill-50 GOVERNING-BLEND call site (U111).

The Email Engine keeps its own mature tone-STYLE library + lexical matcher (the
right tool to pick the style tier). What it lacked was a bridge from those 12
styles to the canonical 81-persona library, so email selections never joined the
persona adherence/learning loop. This module is that bridge: it reads the shared
``shared-utils/persona-crosswalk.json`` ``email_persona_styles`` map (the same
crosswalk mechanism skills 06/44 use for templates) and returns the canonical id
+ Section-4 governance excerpt when one exists. A style with no canonical
counterpart returns ``None`` and the engine keeps its style-tier behavior — never
a fabricated mapping.

U111 (closes G4 — "any content" blend-governance proof): ``persona_block`` above
resolves STRUCTURE (which of the 12 email tone-tiers a style maps to); it never
asked the U1 seam for the GOVERNING blend. Per the D1 binding ruling (the blend
GOVERNS voice + content-writing in every engine, never advisory), ``blend_block``
below is the email engine's canonical entry point onto the U1 blend seam
(``shared-utils/persona_for_job.py:247-266``, A-U1): it calls
``persona_for_job(..., blend=True)`` and returns the bundle superset
(``blend_directive`` ending in the mandatory GUARDRAIL_CLAUSE, ``voice``,
``resolved_audience``, ``task_personas``) VERBATIM so the email write-path can
adopt it without a shape migration — mirroring the exact call the funnel-copy
seam (``49-signature-funnel/scripts/copy_persona_blend_seam.py``) already makes.
``persona_block``'s style-tier crosswalk is untouched (STRUCTURE stays local);
only the VOICE now has a genuine blend-mode path out of this module.

stdlib-only; resolves the shared crosswalk across install layouts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent


def _shared_utils_dir() -> "Path | None":
    cands = [
        os.environ.get("SHARED_UTILS_DIR", "").strip(),
        str(_SKILL_DIR.parent / "shared-utils"),                    # repo checkout
        str(Path.home() / ".openclaw" / "skills" / "shared-utils"),  # Mac install
        "/data/.openclaw/skills/shared-utils",                       # VPS install
        str(Path.home() / "clawd" / "skills" / "shared-utils"),      # legacy
    ]
    for c in cands:
        if c and (Path(c) / "persona-crosswalk.json").exists():
            return Path(c)
    return None


def _crosswalk() -> dict:
    d = _shared_utils_dir()
    if d is None:
        return {}
    try:
        return json.loads((d / "persona-crosswalk.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def canonical_for_style(style_id: str) -> "str | None":
    """Canonical persona id for an email tone-style id, or None if unmapped."""
    if not style_id:
        return None
    xwalk = _crosswalk()
    return (xwalk.get("email_persona_styles") or {}).get(str(style_id).strip()) or None


def persona_block(style_id: str) -> "dict | None":
    """Certificate-ready persona block for a resolved email style, or None.

    Shape: {style_id, persona_id, persona_name, section4_excerpt, source}. The
    Section-4 excerpt is loaded via the shared persona_for_job helper when it and
    the persona library are reachable; it is best-effort (empty on a bare box)."""
    cid = canonical_for_style(style_id)
    if not cid:
        return None
    name, excerpt = cid.replace("-", " ").title(), ""
    d = _shared_utils_dir()
    if d is not None:
        try:
            import sys
            sys.path.insert(0, str(d))
            import persona_for_job as pfj  # type: ignore
            excerpt = pfj.section4_excerpt(cid)
            name = pfj._persona_display_name(cid) or name
        except Exception:
            pass
    return {
        "style_id": style_id,
        "persona_id": cid,
        "persona_name": name,
        "section4_excerpt": excerpt,
        "source": "email-style-crosswalk",
    }


def _load_pfj():
    """Import the shared U1 seam module across install layouts, or None."""
    d = _shared_utils_dir()
    if d is None:
        return None
    try:
        import sys
        sys.path.insert(0, str(d))
        import persona_for_job as pfj  # type: ignore
        return pfj
    except Exception:
        return None


def blend_block(job_text: str, *, department: str = "marketing",
                sop_slug: "str | None" = None,
                topic_hint: "str | None" = None) -> "dict | None":
    """U111 — the email engine's GOVERNING-BLEND call site (D1 ruling).

    Calls the U1 seam's ``blend=True`` branch (A-U1) so an email write-path can
    consume the governing blend directive + guardrail, exactly like the funnel-
    copy seam does. ``department`` defaults to "marketing" — Skill 50's real,
    seeded fleet department (``skill-department-map.json``; PRIMARY role
    email-campaign-strategist; locked in by ``test_department_routing.py``) —
    NEVER the unseeded literal "email".

    Returns the bundle superset VERBATIM (``blend_directive``, ``voice``,
    ``resolved_audience``, ``task_personas``, plus the back-compat
    ``persona_id``/``persona_name`` mirror) when the seam is reachable and
    resolves a bundle; returns the seam's own governed single-persona fallback
    dict when the seam degrades (never naked — same fail-closed contract as
    ``persona_for_job`` itself); returns ``None`` only when the seam module
    cannot be imported at all (a bare box with no shared-utils reachable —
    the caller then keeps today's style-tier-only behavior, never a crash)."""
    pfj = _load_pfj()
    if pfj is None:
        return None
    return pfj.persona_for_job(job_text, department, sop_slug=sop_slug,
                               blend=True, topic_hint=topic_hint)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(persona_block(sys.argv[1]) or {"unmapped": sys.argv[1]}, indent=2))
    else:
        print("usage: persona_canonical.py <persona-style-id>")
