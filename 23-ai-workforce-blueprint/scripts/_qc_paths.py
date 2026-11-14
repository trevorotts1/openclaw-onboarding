#!/usr/bin/env python3
"""_qc_paths.py — the ONE definition of "which departments tree is live".

Added v20.0.80.

WHY THIS MODULE EXISTS
----------------------
The floor-fill repair pipeline reads and writes exactly one departments tree:

    detect-stale-artifacts.py:326   departments_root = Path(workspace) / "departments"
    floor-fill-driver.py:170-171    /data/.openclaw/workspace/departments   (VPS/Docker)
                                    $HOME/.openclaw/workspace/departments   (Mac, and any
                                                                             $HOME-rooted
                                                                             container layout)
    migrate-existing-workforce.sh:138-140   FF_WS_ROOT/departments

The QC checker resolved a DIFFERENT tree — every candidate in
_qc_company_info.py was zero-human-company-shaped, and
department-floor.resolve_departments_dir() read a detect_platform key that does
not exist ("workspace_root") and so fell back to ~/clawd. Measured on the live
fleet: 13 of 18 reachable boxes had the checker and the repairer pointed at two
different directories, and on 10 of them the gate reported floor departments
MISSING that were present on disk the whole time.

A checker that does not measure the tree the repairer maintains cannot audit the
repair. Both consumers now import these helpers so the decision exists once and
the two can never drift apart again.

Deliberately dependency-free (stdlib only) and side-effect-free on import, so it
is safe to import from a gate and testable without a real /data volume.
"""

import json
import os
from pathlib import Path

__all__ = ["live_departments_dir", "departments_root_for", "platform_workspace",
           "looks_like_departments_dir", "resolve_live_departments_dir"]


def _registered_agents(cfg):
    """(id, entry) for every registered agent in BOTH roster shapes:
    `agents.entries` (OpenClaw 2026.9.x, keyed by id, no "id" in the body) and
    legacy `agents.list[]`. Same union as update-skills.sh _registry_snapshot();
    entries wins when both carry an id. Copied from
    refresh-build-state-from-index.py so both readers agree on the roster."""
    agents = cfg.get("agents") if isinstance(cfg, dict) else None
    if not isinstance(agents, dict):
        return []
    out, seen = [], set()
    entries = agents.get("entries")
    for k, v in (entries.items() if isinstance(entries, dict) else ()):
        if isinstance(v, dict) and str(k).lower() not in seen:
            out.append((str(k), v)); seen.add(str(k).lower())
    lst = agents.get("list")
    for a in (lst if isinstance(lst, list) else ()):
        if isinstance(a, dict) and a.get("id") and str(a["id"]).lower() not in seen:
            out.append((str(a["id"]), a)); seen.add(str(a["id"]).lower())
    return out


def _dept_slugs(state):
    """The department slugs the build state lists (`slug`, else `id`)."""
    out = []
    entries = state.get("departments") if isinstance(state, dict) else None
    for d in (entries if isinstance(entries, list) else ()):
        if not isinstance(d, dict):
            continue
        slug = d.get("slug") or d.get("id")
        if isinstance(slug, str) and slug.strip():
            out.append(slug.strip())
    return out


def _score_tree(root, slugs):
    """How many of the state's departments live in `root`; with no state
    departments, how many of its sub-folders hold at least one role how-to.md."""
    if slugs:
        return sum(1 for s in slugs
                   if (root / s).is_dir() or (root / f"{s}-dept").is_dir())
    try:
        children = [c for c in root.iterdir() if c.is_dir()]
    except OSError:
        return 0
    return sum(1 for c in children if next(c.glob("*/how-to.md"), None) is not None)


def resolve_live_departments_dir(state, workspace, config_path=None):
    """Where the company's departments actually live: (folder or None, reason).

    The ONE resolver every caller uses (BU-103, WF-124). Rule, in order:

    1. AGENTS FIRST. The roster in `config_path` (default
       <parent of workspace>/openclaw.json) is ground truth: for every `dept-*`
       agent whose `workspace` is an existing folder, its parent is a candidate
       tree. Exactly one distinct parent -> that folder, reason "agents".
    2. Otherwise SCORE the three fixed candidates (existing folders only,
       de-duplicated by resolved path): <companyRoot>/departments when absolute,
       <workspaceRoot>/departments, <workspace>/departments. A candidate's score
       is how many of the state's department slugs it holds (bare or `-dept`);
       with no state departments, how many sub-folders hold a */how-to.md.
    3. Highest score wins; a tie keeps the earlier candidate. No candidate
       exists -> (None, "none").
    """
    state = state if isinstance(state, dict) else {}
    workspace = Path(workspace)
    if config_path is None:
        config_path = workspace.parent / "openclaw.json"
    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = None
    parents, seen = [], set()
    for aid, entry in _registered_agents(cfg):
        if not aid.startswith("dept-"):
            continue
        ws = entry.get("workspace")
        if not isinstance(ws, str) or not ws.strip() or not Path(ws).is_dir():
            continue
        parent = Path(ws).resolve().parent
        if str(parent) not in seen:
            seen.add(str(parent)); parents.append(parent)
    if len(parents) == 1:
        return parents[0], "agents"

    candidates, cseen = [], set()

    def add(p):
        try:
            resolved = Path(p).resolve()
        except OSError:
            return
        if str(resolved) in cseen or not resolved.is_dir():
            return
        cseen.add(str(resolved)); candidates.append(resolved)

    root = state.get("companyRoot")
    if isinstance(root, str) and os.path.isabs(root):
        add(Path(root) / "departments")
    ws_root = state.get("workspaceRoot")
    if isinstance(ws_root, str) and ws_root.strip():
        add(Path(ws_root) / "departments")
    add(workspace / "departments")

    slugs = _dept_slugs(state)
    best, best_score = None, -1
    for cand in candidates:
        score = _score_tree(cand, slugs)
        if score > best_score:
            best, best_score = cand, score
    if best is None:
        return None, "none"
    return best, "scored"


def departments_root_for(workspace):
    """The departments tree for the workspace `workspace`.

    Delegates to resolve_live_departments_dir() so this reader and every other
    reader of the tree agree by construction (BU-103): the registered dept
    agents first, then the build state's own companyRoot, then the workspace.
    Only when nothing exists does <workspace>/departments apply (the write
    target of a fresh install).
    $WORKFORCE_BUILD_STATE_FILE overrides the state location, as in the build.
    """
    workspace = Path(workspace)
    state_file = os.environ.get("WORKFORCE_BUILD_STATE_FILE", "").strip() \
        or str(workspace / ".workforce-build-state.json")
    try:
        state = json.loads(Path(state_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    live, _reason = resolve_live_departments_dir(state, workspace)
    if live is not None:
        return live
    return workspace / "departments"


def live_departments_dir(data_openclaw=Path("/data/.openclaw"), home=None):
    """Return the departments tree the build wrote and the repair pipeline maintains.

    departments_root_for() decides WITHIN the workspace: the build state's own
    companyRoot/departments first, else <workspace>/departments. Which workspace
    follows the rule below, byte-identical to floor-fill-driver.py:170-171 and
    migrate-existing-workforce.sh:138-139 — the PRESENCE of /data/.openclaw
    decides — so the checker and the repairer can never disagree about which
    tree is live:

        /data/.openclaw/workspace/departments   when /data/.openclaw exists
        <home>/.openclaw/workspace/departments  otherwise

    That single rule covers every box type in the fleet:
      * VPS / Docker on the /data volume  -> the /data branch
      * Docker running as the `node` user -> the $HOME branch, because
        /home/node/.openclaw IS $HOME/.openclaw for that user
      * Mac (both the ~/.openclaw layout and legacy ~/clawd boxes that have
        since grown a workspace tree) -> the $HOME branch

    `data_openclaw` and `home` are injectable ONLY so both branches can be
    exercised in tests without a real /data volume or a real home directory.
    Production callers pass neither and get the live rule.

    NOTE: the returned path is NOT guaranteed to exist. Callers must test it —
    a box that never grew a workspace tree legitimately has none, and must fall
    through to the older zero-human-company layouts rather than be told its
    workforce is missing.
    """
    return departments_root_for(platform_workspace(data_openclaw, home))


def platform_workspace(data_openclaw=Path("/data/.openclaw"), home=None):
    """The OpenClaw workspace (build state + shared core files): the rule above."""
    data_openclaw = Path(data_openclaw)
    if data_openclaw.is_dir():
        return data_openclaw / "workspace"
    return (Path(home) if home is not None else Path.home()) / ".openclaw" / "workspace"


def looks_like_departments_dir(p):
    """True when `p` is plausibly a departments ROOT rather than a company dir.

    _qc_company_info.py's non-standard-layout fallback used to accept a
    company dir AS the departments dir with no test at all, despite a comment
    claiming one ("Check if it contains role-like subdirs directly" — the check
    was never written). A box whose build stopped before departments/ was
    created then had its COMPANY dir enumerated as the department floor: one
    live box resolved a company dir holding a single role folder plus
    departments.json, so QC measured a 2-entry "departments tree" and declared
    the entire mandatory floor missing.

    Shape test — the same one department-floor.resolve_departments_dir()
    already applies:
      * at least two real subdirectories (a departments root always has many;
        a half-built company dir has one or none), AND
      * no how-to.md directly inside — that file marks a single DEPARTMENT
        directory, never a departments root.

    This is deliberately a REJECT-only guard. It can turn a wrong answer into
    "no answer" (the caller then reports no workforce, loudly), never a missing
    department into a present one.
    """
    try:
        p = Path(p)
        if not p.is_dir():
            return False
        subdirs = [d for d in p.iterdir()
                   if d.is_dir() and not d.name.startswith((".", "_"))]
        return len(subdirs) >= 2 and not (p / "how-to.md").exists()
    except Exception:
        return False


def _cli_workspace():
    """The workspace the installer means: the OpenClaw env pins, else the
    platform rule (same order as the package contract, section 2.1)."""
    for key in ("OPENCLAW_WORKSPACE_ROOT", "OPENCLAW_WORKSPACE_PATH"):
        value = os.environ.get(key, "").strip()
        if value:
            return Path(value)
    return platform_workspace()


if __name__ == "__main__":
    import sys

    if "--print-live-departments-dir" in sys.argv[1:]:
        _live = departments_root_for(_cli_workspace())
        if Path(_live).is_dir():
            print(_live)
        sys.exit(0)
