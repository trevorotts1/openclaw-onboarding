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

    # Legacy read-only company roots — resolution fallback ONLY (never the write
    # target). Several VPS clients' real workforces still live at the legacy tree
    # /data/clawd/zero-human-company/<slug>/. company_root is NOT repointed here;
    # but if the canonical company_root holds no company we resolve company_dir
    # from the legacy tree so the gate/updater audit the REAL workforce instead of
    # an empty stub (which produced false department-floor FAIL alerts).
    # Resolution only — nothing is moved or migrated. Mac path logic is unchanged.
    legacy_company_roots = []

    if vps_root.exists():
        root = vps_root
        platform = "vps"
        master_files = Path("/data/.openclaw/master-files")
        company_root = Path("/data/.openclaw/workspace/zero-human-company")
        workspace = root / "workspace"
        legacy_company_roots.append(Path("/data/clawd/zero-human-company"))
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

    # PRD 2.7: canonical coaching-personas dir is workspace/data/coaching-personas/
    coaching_personas = workspace / "data" / "coaching-personas"
    gemini_index = workspace / "data" / "gemini-index.sqlite"

    company_dir = resolve_active_company_dir(company_root, extra_roots=legacy_company_roots)
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
    Resolve persona-categories.json.

    PRD 2.7: single canonical write target = workspace/data/coaching-personas/persona-categories.json.
    The skill-folder copy is the SHIPPED seed (READ-ONLY); it is copied into the canonical
    dir on first Skill 22 run and never written back to.

    Resolution order (first existing path wins):
      1. $PERSONA_CATEGORIES_PATH env var (operator override)
      2. workspace/data/coaching-personas/persona-categories.json  ← CANONICAL (PRD 2.7)
      3. root/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json (shipped seed)
      4. workspace/22-book-to-persona-coaching-leadership-system/persona-categories.json (legacy)
      5. candidates[0] — canonical-but-missing stub so callers can warn with the exact expected path
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


def resolve_active_company_dir(company_root: Path, extra_roots=None):
    """
    Resolve the active per-company ZHC folder.

    Scans the canonical company_root FIRST, then any legacy roots in extra_roots
    (read-only resolution fallback — used on VPS boxes whose real workforce still
    lives at /data/clawd/zero-human-company/<slug>/). The canonical root is always
    preferred; a legacy root is only used when the canonical root holds no company.
    Nothing is moved or migrated — this picks the root that ACTUALLY contains the
    client's company dir so the gate/updater audit the real tree, not an empty stub.

    Per-root resolution order:
        1. $OPENCLAW_COMPANY_SLUG env var → <root>/<slug>/
        2. Single subdir under <root> → that one
        3. Most-recently-modified subdir under <root>
        4. None (no company built yet under that root)

    Returns Path or None.
    """
    import os
    roots = [company_root]
    for r in (extra_roots or []):
        if r not in roots:
            roots.append(r)

    # Pass 1: if an explicit slug is requested, prefer whichever root actually
    # HAS that slug (canonical first) before any mtime-based guessing.
    slug = os.environ.get("OPENCLAW_COMPANY_SLUG")
    if slug:
        for root in roots:
            candidate = root / slug
            if candidate.is_dir():
                return candidate

    # Pass 2: no slug match — pick the active company from the first root that
    # holds one (canonical preferred; legacy roots only as a fallback).
    for root in roots:
        if not root.exists():
            continue
        subdirs = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
        if not subdirs:
            continue
        if len(subdirs) == 1:
            return subdirs[0]
        return max(subdirs, key=lambda p: p.stat().st_mtime)
    return None


if __name__ == "__main__":
    paths = get_openclaw_paths()
    print(f"Platform: {paths['platform']}")
    print(f"Root: {paths['root']}")
    print(f"Workspace: {paths['workspace']}")
    print(f"Company root: {paths['company_root']}")
    print(f"Master files: {paths['master_files']}")
