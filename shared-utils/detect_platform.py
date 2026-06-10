"""
Platform detection for OpenClaw Python scripts.

Import this at the top of every Python script that needs to resolve paths:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "shared-utils"))
    from detect_platform import get_openclaw_paths
    paths = get_openclaw_paths()

Returns a dict with all standard paths. Raises SystemExit with a clear error
if no platform can be detected.

PRD 1.9 (v11.4.0): get_openclaw_paths() is now the ONLY path authority.
  - Canonical company root = master_files/zero-human-company/ on both platforms.
  - MASTER_FILES_DIR env var is honored before any default.
  - build_state key added (workforce build-state JSON path).
  - Nothing in this module writes outside master_files (legacy roots are
    READ-ONLY via get_legacy_company_roots() — used only by the migration
    script, item 1.10).
"""

import os
import sys
from pathlib import Path


def get_openclaw_paths() -> dict:
    """
    Detect the OpenClaw platform and return all standard paths.

    Detection priority:
        1. /data/.openclaw exists -> VPS (Hostinger Docker)
        2. ~/.openclaw exists -> Mac (new install)
        3. ~/clawd exists -> Mac (legacy install)

    MASTER_FILES_DIR env var overrides the master_files root before any default.

    Canonical company root (PRD 1.9, owner-confirmed):
        Mac:  ~/Downloads/openclaw-master-files/zero-human-company/<slug>/
        VPS:  /data/openclaw-master-files/zero-human-company/<slug>/
    Nothing WRITES outside this root. Legacy roots are READ-ONLY (migration only).

    Returns a dict with these keys:
        root, platform, workspace, skills, secrets,
        master_files, company_root, company_dir,
        coaching_personas, gemini_index, persona_categories,
        departments_json, company_config, org_chart,
        user_md, soul_md, memory_md, agents_md, tools_md, heartbeat_md,
        build_state   (PRD 1.9: path to .workforce-build-state.json)
        dashboard_db  (PRD 1.3: Path to mission-control.db, or None if absent)
    """
    vps_marker = Path("/data/.openclaw")
    mac_new = Path.home() / ".openclaw"
    mac_legacy = Path.home() / "clawd"

    # --- platform detection ---
    if vps_marker.exists():
        root = vps_marker
        platform = "vps"
        workspace = root / "workspace"
        # PRD 1.9: VPS master_files lives at /data/openclaw-master-files
        # (NOT inside .openclaw; /data is the persistent Docker volume)
        _default_master = Path("/data/openclaw-master-files")
    elif mac_new.exists():
        root = mac_new
        platform = "mac"
        workspace = root / "workspace"
        _default_master = Path.home() / "Downloads" / "openclaw-master-files"
    elif mac_legacy.exists():
        root = mac_legacy
        platform = "mac-legacy"
        workspace = root
        _default_master = Path.home() / "Downloads" / "openclaw-master-files"
    else:
        print("ERROR: Cannot detect OpenClaw platform.", file=sys.stderr)
        print("None of these directories exist:", file=sys.stderr)
        print("  - /data/.openclaw (expected on VPS / Hostinger Docker)", file=sys.stderr)
        print("  - ~/.openclaw (expected on Mac, new install)", file=sys.stderr)
        print("  - ~/clawd (expected on Mac, legacy install)", file=sys.stderr)
        print("Run the OpenClaw installer before executing this script.", file=sys.stderr)
        raise SystemExit(1)

    # --- MASTER_FILES_DIR override (PRD 1.9) ---
    _env_master = os.environ.get("MASTER_FILES_DIR", "").strip()
    if _env_master:
        master_files = Path(_env_master)
    else:
        master_files = _default_master

    # --- canonical company root (PRD 1.9: always inside master_files) ---
    company_root = master_files / "zero-human-company"

    # --- derived paths ---
    coaching_personas = workspace / "coaching-personas"
    gemini_index = workspace / "data" / "gemini-index.sqlite"

    # build_state: the workforce build-state JSON (written by build-workforce.py)
    build_state = workspace / ".workforce-build-state.json"

    company_dir = resolve_active_company_dir(company_root)
    persona_categories = resolve_persona_categories(workspace, root, coaching_personas)

    # PRD 1.3: resolve dashboard DB through the single shared resolver.
    try:
        from resolve_db import find_dashboard_db
        dashboard_db = find_dashboard_db()
    except ImportError:
        dashboard_db = None

    return {
        "root": root,
        "platform": platform,
        "workspace": workspace,
        "skills": root / "skills",
        "secrets": root / "secrets",
        "master_files": master_files,
        "company_root": company_root,
        "company_dir": company_dir,
        "coaching_personas": coaching_personas,
        "gemini_index": gemini_index,
        "persona_categories": persona_categories,
        "departments_json": (
            company_dir / "departments.json"
        ) if company_dir else (workspace / "departments.json"),
        "company_config": (
            company_dir / "company-config.json"
        ) if company_dir else (workspace / "company-config.json"),
        "org_chart": (
            company_dir / "ORG-CHART.md"
        ) if company_dir else (workspace / "ORG-CHART.md"),
        "user_md": workspace / "USER.md",
        "soul_md": workspace / "SOUL.md",
        "memory_md": workspace / "MEMORY.md",
        "agents_md": workspace / "AGENTS.md",
        "tools_md": workspace / "TOOLS.md",
        "heartbeat_md": workspace / "HEARTBEAT.md",
        # PRD 1.9: workforce build-state
        "build_state": build_state,
        # PRD 1.3: dashboard_db is None when not installed, Path object when found.
        "dashboard_db": dashboard_db,
    }


def get_legacy_company_roots() -> list:
    """
    Return all known LEGACY company roots, for READ-ONLY migration use only.
    (PRD 1.10: discover companies built before the canonical root was adopted.)

    NEVER write new companies here. Only the migration script (1.10) reads
    these in order to move companies into the canonical root.

    Returns a list of Path objects that may or may not exist on disk.
    """
    home = Path.home()
    candidates = [
        home / "clawd" / "zero-human-company",       # v9.6.0+ canonical (legacy)
        home / "clawd" / "zhc",                       # short alias (legacy)
        Path("/data/.openclaw/workspace/zero-human-company"),  # old VPS canonical
        Path("/data/clawd/zero-human-company"),        # VPS variant
        home / ".openclaw" / "workspace" / "zero-human-company",  # Mac workspace variant
    ]
    return candidates


def resolve_persona_categories(workspace: Path, root: Path, coaching_personas: Path) -> Path:
    """
    Resolve persona-categories.json.

    Resolution order (first existing path wins):
      1. $PERSONA_CATEGORIES_PATH env var (operator override)
      2. workspace/coaching-personas/persona-categories.json (runtime/post-install canonical)
      3. root/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json (shipped)
      4. workspace/22-book-to-persona-coaching-leadership-system/persona-categories.json (legacy)
      5. candidates[0] — returned as the "canonical-but-missing" stub so callers can
         warn with the exact expected path.
    """
    if os.environ.get("PERSONA_CATEGORIES_PATH"):
        p = Path(os.environ["PERSONA_CATEGORIES_PATH"])
        if p.exists():
            return p
    candidates = [
        coaching_personas / "persona-categories.json",
        root / "skills" / "22-book-to-persona-coaching-leadership-system" / "persona-categories.json",
        workspace / "22-book-to-persona-coaching-leadership-system" / "persona-categories.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # canonical-but-missing path (warns elsewhere)


def resolve_active_company_dir(company_root: Path):
    """
    Resolve the active per-company ZHC folder under company_root.

    Resolution order:
        1. $OPENCLAW_COMPANY_SLUG env var -> company_root/<slug>/
        2. Single subdir under company_root -> that one
        3. Most-recently-modified subdir under company_root
        4. None (no company built yet)

    Returns Path or None.
    """
    if not company_root.exists():
        return None
    slug = os.environ.get("OPENCLAW_COMPANY_SLUG")
    if slug:
        candidate = company_root / slug
        if candidate.is_dir():
            return candidate
    subdirs = [p for p in company_root.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if not subdirs:
        return None
    if len(subdirs) == 1:
        return subdirs[0]
    return max(subdirs, key=lambda p: p.stat().st_mtime)


if __name__ == "__main__":
    paths = get_openclaw_paths()
    print(f"Platform:      {paths['platform']}")
    print(f"Root:          {paths['root']}")
    print(f"Workspace:     {paths['workspace']}")
    print(f"Master files:  {paths['master_files']}")
    print(f"Company root:  {paths['company_root']}")
    print(f"Company dir:   {paths['company_dir']}")
    print(f"Build state:   {paths['build_state']}")
    print(f"Dashboard DB:  {paths['dashboard_db']}")
