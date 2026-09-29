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
           "looks_like_departments_dir"]


def departments_root_for(workspace):
    """The departments tree for the workspace `workspace`.

    The build state's own companyRoot comes first: build-workforce.py records
    where it wrote (resolve_company_paths -> companyRoot), materialize-dept-
    agents.sh registers the department agents on that tree, so it is the tree
    the agents actually run. Only when the build state names no existing
    <companyRoot>/departments does <workspace>/departments apply.
    $WORKFORCE_BUILD_STATE_FILE overrides the state location, as in the build.
    """
    workspace = Path(workspace)
    state_file = os.environ.get("WORKFORCE_BUILD_STATE_FILE", "").strip() \
        or str(workspace / ".workforce-build-state.json")
    try:
        root = json.loads(Path(state_file).read_text(encoding="utf-8")).get("companyRoot")
    except (OSError, ValueError, AttributeError):
        root = None
    if isinstance(root, str) and os.path.isabs(root) and (Path(root) / "departments").is_dir():
        return Path(root) / "departments"
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
