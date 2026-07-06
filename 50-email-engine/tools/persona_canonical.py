#!/usr/bin/env python3
"""persona_canonical.py — crosswalk a Skill-50 email tone-STYLE id to a REAL
canonical persona id (F4.3).

The Email Engine keeps its own mature tone-STYLE library + lexical matcher (the
right tool to pick the style tier). What it lacked was a bridge from those 12
styles to the canonical 81-persona library, so email selections never joined the
persona adherence/learning loop. This module is that bridge: it reads the shared
``shared-utils/persona-crosswalk.json`` ``email_persona_styles`` map (the same
crosswalk mechanism skills 06/44 use for templates) and returns the canonical id
+ Section-4 governance excerpt when one exists. A style with no canonical
counterpart returns ``None`` and the engine keeps its style-tier behavior — never
a fabricated mapping.

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


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(persona_block(sys.argv[1]) or {"unmapped": sys.argv[1]}, indent=2))
    else:
        print("usage: persona_canonical.py <persona-style-id>")
