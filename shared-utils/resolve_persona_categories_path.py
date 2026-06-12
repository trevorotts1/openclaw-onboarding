#!/usr/bin/env python3
"""
resolve_persona_categories_path.py — Shared canonical resolver for persona-categories.json (§1.7)

PURPOSE
    Single source of truth for where persona-categories.json lives.
    Both generate-governing-personas.sh (Skill 23) and orchestrator.py (Skill 22)
    must call this resolver — resolves the persona path drift (§1.7 spec fix):
      orchestrator resolves workspace/data/coaching-personas/
      generate-governing-personas.sh resolves workspace/coaching-personas/
    BOTH are now reconciled here.

CANONICAL RESOLUTION ORDER (§3.1)
    1. <workspace>/data/coaching-personas/persona-categories.json  (canonical, §3.1)
    2. <workspace>/coaching-personas/persona-categories.json       (legacy, still common)
    3. ~/clawd/coaching-personas/persona-categories.json           (dev layout)
    4. ~/Downloads/openclaw-master-files/coaching-personas/persona-categories.json
    5. <skill22-dir>/persona-categories.json                       (shipped seed)

USAGE (Python import)
    from shared_utils.resolve_persona_categories_path import get_persona_categories_path
    path = get_persona_categories_path()  # returns Path or None

USAGE (bash + env)
    PERSONA_CATEGORIES="$(python3 /path/to/resolve_persona_categories_path.py)"
    # Prints the absolute path, or exits 1 if not found

FAIL LOUD
    If fail_loud=True (default when called from CLI): exits 1 with message if absent.
    If fail_loud=False (default when imported): returns None.
"""

import os
import sys
from pathlib import Path


def _openclaw_root() -> Path | None:
    """Locate the OC_ROOT (/data/.openclaw or ~/.openclaw)."""
    if Path("/data/.openclaw").is_dir():
        return Path("/data/.openclaw")
    if (Path.home() / ".openclaw").is_dir():
        return Path.home() / ".openclaw"
    return None


def get_persona_categories_path(fail_loud: bool = False) -> Path | None:
    """
    Locate persona-categories.json via the canonical resolver order (§3.1).

    Returns a Path if found, None if not found (or exits 1 if fail_loud=True).
    """
    oc_root = _openclaw_root()
    workspace = (oc_root / "workspace") if oc_root else None

    # Allow PERSONA_CATEGORIES env override (generate-governing-personas.sh line 21-22)
    env_override = os.environ.get("PERSONA_CATEGORIES", "").strip()
    if env_override and Path(env_override).is_file():
        return Path(env_override)

    candidates = []

    # 1. Canonical: workspace/data/coaching-personas/ (orchestrator.py resolves here)
    if workspace:
        candidates.append(workspace / "data" / "coaching-personas" / "persona-categories.json")
    candidates.append(Path("/data/.openclaw/workspace/data/coaching-personas/persona-categories.json"))
    candidates.append(Path.home() / ".openclaw/workspace/data/coaching-personas/persona-categories.json")

    # 2. Legacy: workspace/coaching-personas/ (generate-governing-personas.sh resolves here)
    if workspace:
        candidates.append(workspace / "coaching-personas" / "persona-categories.json")
    candidates.append(Path("/data/.openclaw/workspace/coaching-personas/persona-categories.json"))
    candidates.append(Path.home() / ".openclaw/workspace/coaching-personas/persona-categories.json")

    # 3. clawd dev layout
    candidates.append(Path.home() / "clawd/coaching-personas/persona-categories.json")
    candidates.append(Path("/data/clawd/coaching-personas/persona-categories.json"))

    # 4. Downloads master-files
    candidates.append(Path.home() / "Downloads/openclaw-master-files/coaching-personas/persona-categories.json")

    # 5. Skill 22 shipped seed (fallback — never mutate this)
    skill22_candidates = [
        Path("/data/.openclaw/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json"),
        Path.home() / ".openclaw/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json",
    ]
    candidates.extend(skill22_candidates)

    for p in candidates:
        if p.is_file():
            return p

    if fail_loud:
        print(
            "FATAL: persona-categories.json not found in any expected location.\n"
            "Resolution order tried:\n" + "\n".join(f"  {p}" for p in candidates),
            file=sys.stderr,
        )
        sys.exit(1)

    return None


def seed_canonical_from_skill22(oc_root: Path | None = None) -> Path | None:
    """
    If the canonical path (workspace/data/coaching-personas/) doesn't exist yet
    but the Skill 22 seed does, copy the seed to the canonical path.
    Returns the canonical path if seeded, None otherwise.
    """
    root = oc_root or _openclaw_root()
    if not root:
        return None

    canonical = root / "workspace" / "data" / "coaching-personas" / "persona-categories.json"
    if canonical.is_file():
        return canonical  # Already exists

    seed_candidates = [
        root / "skills" / "22-book-to-persona-coaching-leadership-system" / "persona-categories.json",
        Path.home() / ".openclaw/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json",
    ]
    seed = next((p for p in seed_candidates if p.is_file()), None)
    if not seed:
        return None

    try:
        canonical.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(str(seed), str(canonical))
        print(f"[resolve-persona-categories] Seeded canonical path from Skill 22: {canonical}")
        return canonical
    except OSError as e:
        print(f"[resolve-persona-categories] WARN: could not seed canonical path: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    # CLI usage: print the resolved path or exit 1
    p = get_persona_categories_path(fail_loud=True)
    print(str(p))
