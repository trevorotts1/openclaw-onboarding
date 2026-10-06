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

    MASTER_FILES_DIR env var overrides the master_files root before any default.

    Canonical company root (PRD 1.9, owner-confirmed):
        Mac:  ~/Downloads/openclaw-master-files/zero-human-company/<slug>/
        VPS:  /data/openclaw-master-files/zero-human-company/<slug>/
    Nothing WRITES outside this root. Legacy roots are READ-ONLY (migration only).

    OPENCLAW_COMPANY_CONFIG env var overrides the resolved company_config path
    before any company_dir derivation (D8: same override pattern as
    PERSONA_CATEGORIES_PATH / MASTER_FILES_DIR). This is the ONLY way ICP/
    company keys (e.g. company.ideal_customer, read by
    persona_blend.resolve_audience()) reach the persona matcher when no
    on-disk company_dir has been built yet, or the config under test lives
    outside the canonical company_root (CI, sandboxed persona-blend tests,
    an operator pointing at a specific client's company-config.json).

    Returns a dict with these keys:
        root, platform, workspace, skills, secrets,
        master_files, company_root, company_dir,
        coaching_personas, gemini_index, persona_categories,
        departments_json, company_config, org_chart,
        user_md, soul_md, memory_md, agents_md, tools_md, heartbeat_md,
        build_state   (PRD 1.9: path to .workforce-build-state.json)
        dashboard_db  (PRD 1.3: Path to mission-control.db, or None if absent)
    """
    vps_marker = DATA_ROOT / ".openclaw"
    mac_new = Path.home() / ".openclaw"
    mac_legacy = Path.home() / "clawd"

    # --- explicit OPENCLAW_PLATFORM override (mac | vps | mac-legacy) ---
    # An explicit override resolves the platform WITHOUT requiring an installed
    # marker directory on disk. This is the same first-class concept install.sh /
    # update-skills.sh / lib-shared.sh already use, and it lets the static QC gates
    # (qc-assert-repo-consistency.py, test-ws4-departments.sh, etc.) run
    # deterministically on a bare CI runner that has neither ~/.openclaw nor
    # /data/.openclaw. When UNSET, detection is unchanged (the marker checks below
    # run exactly as before — a real Mac or VPS is detected identically). Only the
    # platform/roots are forced; nothing is written, and the legacy /data/clawd
    # resolution fallback (below) still applies for vps.
    _env_platform = os.environ.get("OPENCLAW_PLATFORM", "").strip().lower()

    # --- platform detection ---
    if _env_platform == "vps":
        root = vps_marker
        platform = "vps"
        workspace = root / "workspace"
        _default_master = DATA_ROOT / "openclaw-master-files"
    elif _env_platform in ("mac", "mac-new"):
        root = mac_new
        platform = "mac"
        workspace = root / "workspace"
        _default_master = _home_master_files(root)
    elif _env_platform == "mac-legacy":
        root = mac_legacy
        platform = "mac-legacy"
        workspace = root
        _default_master = Path.home() / "Downloads" / "openclaw-master-files"
    elif vps_marker.exists():
        root = vps_marker
        platform = "vps"
        workspace = root / "workspace"
        # PRD 1.9: VPS master_files lives at /data/openclaw-master-files
        # (NOT inside .openclaw; /data is the persistent Docker volume)
        _default_master = DATA_ROOT / "openclaw-master-files"
    elif mac_new.exists():
        root = mac_new
        platform = "mac"
        workspace = root / "workspace"
        _default_master = _home_master_files(root)
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
        print("Set OPENCLAW_PLATFORM=mac|vps to override (e.g. CI static checks),", file=sys.stderr)
        print("or run the OpenClaw installer before executing this script.", file=sys.stderr)
        raise SystemExit(1)

    # --- MASTER_FILES_DIR override (PRD 1.9) ---
    _env_master = os.environ.get("MASTER_FILES_DIR", "").strip()
    if _env_master:
        master_files = Path(_env_master)
    else:
        master_files = _default_master

    # --- canonical company root (PRD 1.9: always inside master_files) ---
    company_root = master_files / "zero-human-company"

    # --- every place a company tree can live (resolution only, never a write
    # target). company_root above stays the canonical WRITE root; company_dir
    # below is read from the build state first, then these layouts in order.
    # See known_company_roots() / resolve_active_company_dir().
    legacy_company_roots = known_company_roots(platform, workspace)

    # --- derived paths ---
    # PRD 2.7: canonical coaching-personas dir is workspace/data/coaching-personas/
    # (next to the gemini index; aligns with orchestrator + embedding_engine paths).
    coaching_personas = workspace / "data" / "coaching-personas"
    # EMBED-1 (embedding-subsystem hardening): gemini_index is the SAME file the
    # runtime search path reads — embedding_engine.DB_PATH and the prebuilt-index
    # installer (provision-persona-index.sh) both use
    # workspace/data/coaching-personas/gemini-index.sqlite. This key previously
    # pointed at workspace/data/gemini-index.sqlite (no coaching-personas/
    # segment), so gemini-section-indexer.py WROTE embeddings into a DB the
    # search path never reads. One path authority, one DB. See docs/EMBEDDINGS.md.
    gemini_index = coaching_personas / "gemini-index.sqlite"
    # The old, wrong location — kept ONLY so writers can detect + warn about an
    # orphaned DB left behind by pre-fix builds. NEVER write here.
    legacy_gemini_index = workspace / "data" / "gemini-index.sqlite"

    # build_state: the workforce build-state JSON (written by build-workforce.py)
    build_state = workspace / ".workforce-build-state.json"

    company_dir = resolve_active_company_dir(company_root, extra_roots=legacy_company_roots,
                                             workspace=workspace)
    persona_categories = resolve_persona_categories(workspace, root, coaching_personas)

    # --- OPENCLAW_COMPANY_CONFIG override (D8) ---
    # Points company_config directly at a company-config.json file, bypassing
    # company_dir derivation. Read here (not left to callers) so every
    # consumer of get_openclaw_paths() — persona-selector-v2.py's
    # load_company_config(), persona_blend.py's resolve_audience(), Skill 23
    # scripts, and CI/tests — sees the SAME company_config path from a single
    # authority. Unset or blank: falls through to the company_dir-derived
    # path below, exactly as before this override existed.
    _env_company_config = os.environ.get("OPENCLAW_COMPANY_CONFIG", "").strip()
    company_config = (
        Path(_env_company_config) if _env_company_config
        else (company_dir / "company-config.json") if company_dir
        else (workspace / "company-config.json")
    )

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
        "legacy_gemini_index": legacy_gemini_index,
        "persona_categories": persona_categories,
        "departments_json": (
            company_dir / "departments.json"
        ) if company_dir else (workspace / "departments.json"),
        "company_config": company_config,
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


def home_is_overridden() -> bool:
    """
    EMBED-2 (embedding-subsystem hardening): True when $HOME points somewhere
    other than the OS account home directory — i.e. the process is running
    under a SANDBOXED / faked HOME.

    Why this exists: every path in get_openclaw_paths() is HOME-relative on
    Mac, so a test harness that exports HOME=/tmp/sandbox silently redirects
    EVERY read AND write (gemini index, persona-categories.json, blueprints)
    into the sandbox. That is exactly how a full book-to-persona build once
    embedded ~15 personas into a throwaway tree while the live index never
    changed. Writers must treat an overridden HOME as sandbox-by-accident
    unless the operator explicitly opts in (OPENCLAW_SANDBOX=1).
    """
    try:
        import pwd
        real_home = pwd.getpwuid(os.getuid()).pw_dir
    except Exception:
        return False  # non-POSIX / unresolvable — never block on uncertainty
    env_home = os.environ.get("HOME", "")
    if not env_home or not real_home:
        return False
    return os.path.realpath(env_home) != os.path.realpath(real_home)


def assert_live_workspace_for_write(context: str, target_path) -> None:
    """
    EMBED-2 HARD GATE for write paths (indexers, persona builds, registration).

    Contract:
      - OPENCLAW_SANDBOX=1  -> sandbox is EXPLICIT: allowed, with a loud
                               stderr banner naming the resolved target.
      - HOME not overridden -> real box, real home: allowed silently.
      - HOME overridden AND the resolved write target lives under that
        overridden HOME -> SystemExit(4) with a clear message. A real build
        must land in the live workspace; a sandbox must be opted into.

    Read-only consumers must NOT call this — it is for writers only, so
    existing read paths and CI static checks are unaffected.
    """
    target = str(target_path)
    if os.environ.get("OPENCLAW_SANDBOX", "").strip() == "1":
        print(
            f"[detect-platform] SANDBOX MODE (OPENCLAW_SANDBOX=1): {context} "
            f"will write under {target}",
            file=sys.stderr,
        )
        return
    if not home_is_overridden():
        return
    env_home = os.path.realpath(os.environ.get("HOME", ""))
    if not os.path.realpath(target).startswith(env_home + os.sep):
        # Write target is outside the overridden HOME (e.g. /data on VPS) —
        # the HOME override cannot misroute this write.
        return
    print(
        f"ERROR [detect-platform]: {context} resolved its write target to\n"
        f"    {target}\n"
        f"which lives under an OVERRIDDEN $HOME ({os.environ.get('HOME','')}) "
        f"— this is a SANDBOX, not the live workspace.\n"
        f"A real build/index run must write to the live workspace. Either:\n"
        f"  - unset the HOME override to run for real, OR\n"
        f"  - export OPENCLAW_SANDBOX=1 to run in the sandbox ON PURPOSE "
        f"(tests only).\n"
        f"Refusing to write. (embedding-subsystem hard gate EMBED-2)",
        file=sys.stderr,
    )
    raise SystemExit(4)


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

    PRD 2.7: single canonical write target = workspace/data/coaching-personas/persona-categories.json.
    The skill-folder copy (22-book-to-persona-coaching-leadership-system/persona-categories.json)
    is the SHIPPED seed only — copied into the canonical dir on first Skill 22 run and never
    written back. Readers that previously pointed at the skill folder are migrated here.

    Resolution order (first existing path wins):
      1. $PERSONA_CATEGORIES_PATH env var (operator override)
      2. workspace/data/coaching-personas/persona-categories.json  ← CANONICAL (PRD 2.7)
      3. root/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json (shipped seed, READ-ONLY)
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
    print(f"Platform:      {paths['platform']}")
    print(f"Root:          {paths['root']}")
    print(f"Workspace:     {paths['workspace']}")
    print(f"Master files:  {paths['master_files']}")
    print(f"Company root:  {paths['company_root']}")
    print(f"Company dir:   {paths['company_dir']}")
    print(f"Company cfg:   {paths['company_config']}")
    print(f"Build state:   {paths['build_state']}")
    print(f"Dashboard DB:  {paths['dashboard_db']}")
