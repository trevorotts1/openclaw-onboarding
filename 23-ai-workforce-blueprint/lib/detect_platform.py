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

import os
from pathlib import Path

# The VPS / container data volume. A module constant only so tests can point
# it at a fixture; production code never reassigns it.
DATA_ROOT = Path("/data")


def _home_master_files(root: Path) -> Path:
    """~/Downloads/openclaw-master-files -- except in a container whose only
    persistent storage is the ~/.openclaw volume (Contabo: HOME is the image's
    temporary layer, so ~/Downloads is wiped by every recreate; one client's
    whole company folder was lost that way). There it lives on the volume."""
    downloads = Path.home() / "Downloads"
    if os.path.ismount(root) and not os.path.ismount(downloads):
        return root / "openclaw-master-files"
    return downloads / "openclaw-master-files"


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
    import os
    vps_root = DATA_ROOT / ".openclaw"
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

    # --- explicit OPENCLAW_PLATFORM override (mac | vps | mac-legacy) ---
    # An explicit override resolves the platform WITHOUT requiring an installed
    # marker directory on disk — the same first-class concept install.sh /
    # update-skills.sh / lib-shared.sh already use. It lets the static QC gates
    # (qc-assert-repo-consistency.py, test-ws4-departments.sh, etc.) run
    # deterministically on a bare CI runner that has neither ~/.openclaw nor
    # /data/.openclaw. When UNSET, detection is unchanged (the marker checks below
    # run exactly as before — a real Mac or VPS is detected identically, including
    # the v12.29.0 legacy /data/clawd resolution). Only the platform/roots are
    # forced; nothing is written.
    _env_platform = os.environ.get("OPENCLAW_PLATFORM", "").strip().lower()

    if _env_platform == "vps":
        root = vps_root
        platform = "vps"
        master_files = Path("/data/.openclaw/master-files")
        company_root = Path("/data/.openclaw/workspace/zero-human-company")
        workspace = root / "workspace"
        legacy_company_roots.append(Path("/data/clawd/zero-human-company"))
    elif _env_platform in ("mac", "mac-new"):
        root = mac_new
        platform = "mac"
        master_files = Path.home() / "Downloads" / "openclaw-master-files"
        workspace = root / "workspace"
        if mac_legacy.exists():
            company_root = mac_legacy / "zero-human-company"
        else:
            company_root = workspace / "zero-human-company"
    elif _env_platform == "mac-legacy":
        root = mac_legacy
        platform = "mac-legacy"
        master_files = Path.home() / "Downloads" / "openclaw-master-files"
        workspace = root
        company_root = mac_legacy / "zero-human-company"
    elif vps_root.exists():
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
        print("Set OPENCLAW_PLATFORM=mac|vps to override (e.g. CI static checks),")
        print("or run the OpenClaw installer before executing this script.")
        raise SystemExit(1)

    # PRD 2.7: canonical coaching-personas dir is workspace/data/coaching-personas/
    coaching_personas = workspace / "data" / "coaching-personas"
    # EMBED-1: gemini_index is the SAME file embedding_engine.DB_PATH reads and
    # provision-persona-index.sh installs — coaching-personas/gemini-index.sqlite.
    # (Kept in lockstep with shared-utils/detect_platform.py; the old
    # workspace/data/gemini-index.sqlite value routed indexer WRITES to a DB the
    # search path never reads.)
    gemini_index = coaching_personas / "gemini-index.sqlite"
    legacy_gemini_index = workspace / "data" / "gemini-index.sqlite"  # detect-only; NEVER write

    # company_dir: the SAME order as shared-utils/detect_platform.py (build state
    # first, then the canonical master-files tree, then the other layouts).
    # This copy's own company_root is kept as one more candidate, last.
    _known = known_company_roots(platform, workspace) + legacy_company_roots + [company_root]
    company_dir = resolve_active_company_dir(_known[0], extra_roots=_known[1:], workspace=workspace)
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
        "legacy_gemini_index": legacy_gemini_index,
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


# ── COMPANY-DIR RESOLUTION (one order, byte-identical in shared-utils/ and
# 23-ai-workforce-blueprint/lib/ copies of this module; a test pins that) ──

def build_state_company(workspace=None):
    """(companyRoot, companySlug) recorded in .workforce-build-state.json.

    The build knows where it wrote: resolve_company_paths() in build-workforce.py
    records companyRoot + companySlug on every run. companyRoot is returned only
    when it is an absolute, existing directory; either value may be None.
    """
    import json
    cands = [os.environ.get("WORKFORCE_BUILD_STATE_FILE", "").strip()]
    if workspace:
        cands.append(str(Path(workspace) / ".workforce-build-state.json"))
    cands += [str(DATA_ROOT / ".openclaw" / "workspace" / ".workforce-build-state.json"),
              str(Path.home() / ".openclaw" / "workspace" / ".workforce-build-state.json")]
    for cand in cands:
        if not cand:
            continue
        try:
            state = json.loads(Path(cand).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(state, dict):
            continue
        root = state.get("companyRoot")
        root = Path(root) if isinstance(root, str) and os.path.isabs(root) and os.path.isdir(root) else None
        slug = state.get("companySlug") or state.get("clientSlug")
        return root, (slug if isinstance(slug, str) and slug else None)
    return None, None


def known_company_roots(platform, workspace):
    """Every layout a company tree can live in on this platform, canonical first.

      1. <master-files>/zero-human-company  where build-workforce.py writes
         (Mac ~/Downloads/openclaw-master-files, VPS /data/openclaw-master-files,
         $MASTER_FILES_DIR when set)
      2. <workspace>/zero-human-company      Contabo /home/node and older VPS builds
      3. legacy clawd tree                   ~/clawd (Mac) or /data/clawd (VPS)
    """
    mf = os.environ.get("MASTER_FILES_DIR", "").strip()
    if mf:
        master = Path(mf)
    elif platform == "vps":
        master = DATA_ROOT / "openclaw-master-files"
    else:
        master = _home_master_files(Path.home() / ".openclaw")
    legacy = DATA_ROOT / "clawd" if platform == "vps" else Path.home() / "clawd"
    roots = []
    for r in (master / "zero-human-company", Path(workspace) / "zero-human-company",
              legacy / "zero-human-company"):
        if r not in roots:
            roots.append(r)
    return roots


def resolve_active_company_dir(company_root: Path, extra_roots=None, workspace=None):
    """
    Resolve the active per-company ZHC folder. Nothing is moved or written.

    Order:
        0. The build state's own companyRoot (the build knows where it wrote),
           unless $OPENCLAW_COMPANY_SLUG names a different company.
        1. $OPENCLAW_COMPANY_SLUG -> <root>/<slug>/ in the first root that has
           it; an explicit company never falls back to another tenant. Then the
           build state's companySlug the same way (a hint: falls through).
        2. No slug: the single company in the first root that holds any.
           Several companies there require an explicit identity -> None.

    Roots are company_root first, then extra_roots (known_company_roots()).
    Returns Path or None.
    """
    roots = [company_root]
    for r in (extra_roots or []):
        if r not in roots:
            roots.append(r)

    state_root, state_slug = build_state_company(workspace)
    env_slug = os.environ.get("OPENCLAW_COMPANY_SLUG")
    if state_root is not None and (not env_slug or state_root.name == env_slug):
        return state_root

    for slug in (env_slug, state_slug):
        if not slug:
            continue
        if Path(slug).name != slug or slug in ('.', '..'):
            if slug == env_slug:
                return None
            continue
        for root in roots:
            candidate = root / slug
            if candidate.is_dir():
                return candidate
        if slug == env_slug:
            return None  # An explicit company must never fall back to another tenant.

    for root in roots:
        if not root.exists():
            continue
        subdirs = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
        if not subdirs:
            continue
        if len(subdirs) == 1:
            return subdirs[0]
        return None  # Multiple companies require an explicit identity.
    return None


if __name__ == "__main__":
    paths = get_openclaw_paths()
    print(f"Platform: {paths['platform']}")
    print(f"Root: {paths['root']}")
    print(f"Workspace: {paths['workspace']}")
    print(f"Company root: {paths['company_root']}")
    print(f"Master files: {paths['master_files']}")
