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
"""

from pathlib import Path


def get_openclaw_paths() -> dict:
    """
    Detect the OpenClaw platform and return all standard paths.

    Detection priority:
        1. /data/.openclaw exists -> VPS (Hostinger Docker)
        2. ~/.openclaw exists -> Mac (new install)
        3. ~/clawd exists -> Mac (legacy install)

    Returns a dict with these keys:
        root, platform, workspace, skills, secrets, master_files,
        company_root, coaching_personas, gemini_index, persona_categories,
        departments_json, company_config, org_chart, user_md, soul_md,
        memory_md, agents_md, tools_md, heartbeat_md
    """
    vps_root = Path("/data/.openclaw")
    mac_new = Path.home() / ".openclaw"
    mac_legacy = Path.home() / "clawd"

    if vps_root.exists():
        root = vps_root
        platform = "vps"
        master_files = Path("/data/.openclaw/master-files")
        company_root = Path("/data/.openclaw/workspace/zero-human-company")
        workspace = root / "workspace"
    elif mac_new.exists():
        root = mac_new
        platform = "mac"
        master_files = Path.home() / "Downloads" / "openclaw-master-files"
        workspace = root / "workspace"
        # Legacy clawd company root takes priority if it exists
        if mac_legacy.exists():
            company_root = mac_legacy / "zero-human-company"
        else:
            company_root = workspace / "zero-human-company"
    elif mac_legacy.exists():
        root = mac_legacy
        platform = "mac-legacy"
        master_files = Path.home() / "Downloads" / "openclaw-master-files"
        workspace = root
        company_root = mac_legacy / "zero-human-company"
    else:
        print("ERROR: Cannot detect OpenClaw platform.")
        print("None of these directories exist:")
        print("  - /data/.openclaw (expected on VPS / Hostinger Docker)")
        print("  - ~/.openclaw (expected on Mac, new install)")
        print("  - ~/clawd (expected on Mac, legacy install)")
        print("Run the OpenClaw installer before executing this script.")
        raise SystemExit(1)

    coaching_personas = workspace / "coaching-personas"
    gemini_index = workspace / "data" / "gemini-index.sqlite"

    company_dir = resolve_active_company_dir(company_root)
    persona_categories = resolve_persona_categories(workspace, root, coaching_personas)

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
        "departments_json": (company_dir / "departments.json") if company_dir else (workspace / "departments.json"),
        "company_config": (company_dir / "company-config.json") if company_dir else (workspace / "company-config.json"),
        "org_chart": (company_dir / "ORG-CHART.md") if company_dir else (workspace / "ORG-CHART.md"),
        "user_md": workspace / "USER.md",
        "soul_md": workspace / "SOUL.md",
        "memory_md": workspace / "MEMORY.md",
        "agents_md": workspace / "AGENTS.md",
        "tools_md": workspace / "TOOLS.md",
        "heartbeat_md": workspace / "HEARTBEAT.md",
    }


def resolve_persona_categories(workspace: Path, root: Path, coaching_personas: Path) -> Path:
    """
    Resolve persona-categories.json. v10.8.0 P0-5 fix: previously the path
    pointed only at workspace/coaching-personas/persona-categories.json,
    which doesn't exist on a fresh install. The file ships in Skill 22's
    folder (22-book-to-persona-coaching-leadership-system/persona-categories.json)
    and is COPIED to the coaching-personas workspace folder when Skill 22 runs.

    Resolution order (first existing path wins):
      1. $PERSONA_CATEGORIES_PATH env var (operator override)
      2. workspace/coaching-personas/persona-categories.json (runtime/post-install canonical)
      3. root/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json (shipped)
      4. workspace/22-book-to-persona-coaching-leadership-system/persona-categories.json (legacy)
      5. coaching-personas (the original location — returned as a "next-best" stub even if missing)
    """
    import os
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
        1. $OPENCLAW_COMPANY_SLUG env var → company_root/<slug>/
        2. Single subdir under company_root → that one
        3. Most-recently-modified subdir under company_root
        4. None (no company built yet)

    Returns Path or None.
    """
    import os
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
    print(f"Platform: {paths['platform']}")
    print(f"Root: {paths['root']}")
    print(f"Workspace: {paths['workspace']}")
    print(f"Company root: {paths['company_root']}")
    print(f"Master files: {paths['master_files']}")
