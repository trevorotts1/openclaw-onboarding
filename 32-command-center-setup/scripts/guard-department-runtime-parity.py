#!/usr/bin/env python3
"""
guard-department-runtime-parity.py — Skill 32 per-department runtime reconciliation guard.

THE GAP THIS CLOSES:
  run-full-install.sh Phase 4's only safety check was a blunt TOTAL COUNT floor
  (`AGENT_COUNT -lt 2`) against openclaw.json's agents.list[]. That check passes
  as long as *some* two agents exist anywhere in agents.list[] — it never
  verifies that EVERY individual department seeded onto the Command Center
  board (a `workspaces` row in mission-control.db, written by seed-workspaces.py
  / seed-dashboard-content.py) has ITS OWN matching runtime entry.

  materialize-dept-agents.sh (folder-scan of 3 hardcoded roots) and
  seed-workspaces.py (departments.json, with its own independent folder-scan
  fallback) are two INDEPENDENT department-discovery mechanisms with NO
  cross-check between them today. If N-2 departments wire correctly and 2
  silently don't, the blunt total-count floor still passes — those 2
  departments get a full board row (Kanban column, a "<Name> Lead" agent row,
  a starter task) and ZERO working OpenClaw runtime behind them. That is
  exactly the `no_specialist_runtime` failure class documented in
  blackceo-command-center's resolveSpecialistSessionKey()
  (src/lib/task-dispatcher.ts): a task assigned to that department's dashboard
  agent can never resolve a runtime session key and is held "routed but not
  dispatched" forever — invisible until a client notices nothing happens for
  that one department.

WHAT THIS SCRIPT DOES:
  For every workspace (department) row in mission-control.db, computes the
  SAME candidate runtime-id variants blackceo-command-center's
  resolveSpecialistSessionKey() tries, in the same order, and checks whether
  ANY of them has a matching `id` in openclaw.json's agents.list[]:

    1. dept-<workspace-slug>          Attempt 1  — dept-prefixed runtime dir
    2. <workspace-slug>               Attempt 1  — bare runtime dir
    3. dept-<canonical-alias-slug>    Attempt 1b — canonical, dept-prefixed
    4. <canonical-alias-slug>         Attempt 1b — canonical, bare
    5. dept-<role-slug>               Attempt 2  — derived from agents.role
    6. <name-slug>                    Attempt 3  — derived from agents.name
                                                    (NOT dept-prefixed)

  canonical-alias-slug is computed with shared-utils/canonical_slug.py — the
  Python mirror of blackceo-command-center's src/lib/routing/canonical-slug.ts
  (both sides are contractually required to stay in sync; importing it
  directly here means this guard can never drift from that mapping on its
  own). role-slug / name-slug come from the dashboard's OWN `agents` table
  (the "<Dept> Lead" / "<Dept> Department Head" rows seed-dashboard-content.py
  writes, persona=`dept-<slug>`), joined on workspace_id — the exact Agent row
  resolveSpecialistSessionKey() receives.

  A department with NO variant present in agents.list[] is reported BY NAME
  and the script exits non-zero (fail-closed).

WHAT IS *NOT* A FAILURE:
  - mission-control.db not found, or its `workspaces` table missing/empty:
    nothing has been seeded onto the board yet, so there is nothing to
    reconcile. Mirrors the WARN-and-continue convention every other Phase-6x
    sub-script in run-full-install.sh already uses for a not-yet-provisioned
    dependency.

WHAT *IS* A HARD FAILURE:
  - one or more departments have a board row but no matching runtime entry
    under any of the 6 variants above (exit 1).
  - mission-control.db has workspaces rows but openclaw.json is missing,
    unreadable, or malformed (exit 2) — we cannot vouch for ANY department's
    runtime in that state, so we refuse to silently pass.

USAGE:
  python3 guard-department-runtime-parity.py
  python3 guard-department-runtime-parity.py --db /path/to/mission-control.db \\
      --config /path/to/openclaw.json
  python3 guard-department-runtime-parity.py --json
  python3 guard-department-runtime-parity.py --quiet

EXIT CODES:
  0 — every department (workspaces row) has a matching runtime entry, or
      there were zero departments to check (DB/table absent or empty).
  1 — one or more departments have a board row but NO matching runtime entry
      under any of the 6 slug variants above ("no_specialist_runtime" class).
  2 — mission-control.db has workspaces rows but openclaw.json is missing,
      unreadable, or malformed — cannot verify ANY department (fail-closed).
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

TAG = "[guard-department-runtime-parity]"

EX_OK = 0
EX_MISMATCH = 1
EX_CONFIG_UNREADABLE = 2

# PRD 1.3 / 1.5: import the SAME shared DB resolver + canonical slug mapper
# every other Skill 32 script uses, so this guard can never see a different
# reality than seed-workspaces.py / materialize-dept-agents.sh do.
_SHARED_UTILS = Path(__file__).resolve().parent.parent.parent / "shared-utils"
sys.path.insert(0, str(_SHARED_UTILS))
try:
    from resolve_db import find_dashboard_db as _shared_find_dashboard_db, is_db_found  # type: ignore
    _HAS_SHARED_RESOLVER = True
except ImportError:
    _HAS_SHARED_RESOLVER = False

try:
    from canonical_slug import canonical_dept_slug  # type: ignore
except ImportError:
    # Inline fallback mirroring seed-workspaces.py's own fallback, so this
    # script still works standalone before shared-utils is on the box.
    def canonical_dept_slug(raw: str) -> str:  # type: ignore
        if not raw or not isinstance(raw, str):
            return ""
        s = raw.strip().lower()
        if s.startswith("dept-"):
            s = s[5:]
        if s.endswith("-dept"):
            s = s[:-5]
        s = s.replace(" ", "-").replace("_", "-")
        s = re.sub(r"-{2,}", "-", s)
        return s.strip("-")


def _detect_oc_root():
    """Mirror materialize-dept-agents.sh platform detection: VPS first, Mac fallback."""
    if os.path.isdir("/data/.openclaw"):
        return "/data/.openclaw"
    home_oc = os.path.join(os.path.expanduser("~"), ".openclaw")
    if os.path.isdir(home_oc):
        return home_oc
    return None


def _resolve_db_path(explicit):
    if explicit:
        return explicit
    if _HAS_SHARED_RESOLVER:
        p = _shared_find_dashboard_db()
        return str(p) if is_db_found(p) else None
    return None


def _resolve_config_path(explicit, oc_root_override):
    if explicit:
        return explicit
    oc_root = oc_root_override or _detect_oc_root()
    return os.path.join(oc_root, "openclaw.json") if oc_root else None


def _slugify(raw):
    """Mirror resolveSpecialistSessionKey's inline slug derivation exactly:
    `.toLowerCase().replace(/\\s+/g, '-').replace(/[^a-z0-9-]/g, '')`
    """
    if not raw:
        return ""
    s = str(raw).lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s


def candidate_variants(workspace_slug, agent_name=None, agent_role=None):
    """Ordered candidate runtime ids for one department, exactly mirroring the
    6 attempts blackceo-command-center's resolveSpecialistSessionKey() tries
    (src/lib/task-dispatcher.ts). Order preserved for readability/debugging;
    the guard treats ANY match as a pass, so order is not itself load-bearing.
    """
    variants = []
    ws = (workspace_slug or "").strip().lower()
    if ws:
        variants.append(f"dept-{ws}")           # Attempt 1  — dept-prefixed
        variants.append(ws)                     # Attempt 1  — bare
        canon = canonical_dept_slug(ws)
        if canon and canon != ws:
            variants.append(f"dept-{canon}")    # Attempt 1b — canonical, dept-prefixed
            variants.append(canon)              # Attempt 1b — canonical, bare

    role_slug = _slugify(agent_role)
    if role_slug:
        variants.append(f"dept-{role_slug}")    # Attempt 2  — from agents.role

    name_slug = _slugify(agent_name)
    if name_slug:
        variants.append(name_slug)              # Attempt 3  — from agents.name (no prefix)

    # De-dup, preserve first-seen order.
    seen = set()
    out = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def load_agent_ids(config_path):
    """Returns (ok, ids_lowercased_set_or_None, error_message_or_None)."""
    if not config_path or not os.path.isfile(config_path):
        return False, None, f"openclaw.json not found at {config_path!r}"
    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, None, f"openclaw.json unreadable/malformed ({config_path}): {e}"

    agent_list = (cfg.get("agents") or {}).get("list") or []
    if not isinstance(agent_list, list):
        return False, None, f"openclaw.json agents.list is not a list ({config_path})"

    ids = set()
    for a in agent_list:
        if isinstance(a, dict) and a.get("id"):
            ids.add(str(a["id"]).strip().lower())
    return True, ids, None


def load_departments(db_path):
    """
    Returns (found: bool, departments: list[dict], note: str | None).

    found=False   -- mission-control.db itself does not exist (nothing to check).
    found=True, departments=[]  -- DB exists but `workspaces` table is missing/
                                    empty (nothing seeded onto the board yet).
    found=True, departments=[...]  -- one dict per department to reconcile:
        {"id": workspace id, "slug": workspace slug, "name": display name,
         "agents": [{"name": ..., "role": ...}, ...]}  (agents list may be
        empty when the dashboard `agents` table doesn't exist / has no rows
        for this workspace yet -- role/name variants are simply skipped then).
    """
    if not db_path or not os.path.isfile(db_path):
        return False, [], f"mission-control.db not found (checked: {db_path or '<none>'})"

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        ws_cols = [r[1] for r in conn.execute("PRAGMA table_info(workspaces)")]
        if not ws_cols:
            conn.close()
            return True, [], "workspaces table not found in mission-control.db (nothing seeded yet)"

        has_type = "type" in ws_cols
        select_cols = ["id", "name", "slug"] + (["type"] if has_type else [])
        rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM workspaces").fetchall()

        # Schema-tolerant join to the DASHBOARD's `agents` table (NOT openclaw.json
        # agents.list[] -- a same-named but unrelated table) to pick up the
        # per-department Agent row's name/role for variants 5 and 6. Missing
        # table/columns degrades gracefully: those two variants are simply
        # unavailable for departments with no linked agent row yet.
        ag_cols = [r[1] for r in conn.execute("PRAGMA table_info(agents)")]
        agents_by_ws = {}
        if ag_cols and "workspace_id" in ag_cols:
            has_name = "name" in ag_cols
            has_role = "role" in ag_cols
            sel = ["workspace_id"] + (["name"] if has_name else []) + (["role"] if has_role else [])
            if len(sel) > 1:
                for arow in conn.execute(f"SELECT {', '.join(sel)} FROM agents"):
                    ws_id = arow["workspace_id"]
                    if ws_id is None:
                        continue
                    agents_by_ws.setdefault(ws_id, []).append({
                        "name": arow["name"] if has_name else None,
                        "role": arow["role"] if has_role else None,
                    })
        conn.close()
    except sqlite3.Error as e:
        return False, [], f"mission-control.db read error: {e}"

    departments = []
    for row in rows:
        if has_type and row["type"] in ("main", "system"):
            continue
        ws_id = row["id"]
        departments.append({
            "id": ws_id,
            "slug": row["slug"] or "",
            "name": row["name"] or row["slug"] or ws_id,
            "agents": agents_by_ws.get(ws_id, []),
        })
    return True, departments, None


def check_parity(departments, agent_ids):
    """Returns (checked_count, mismatches: list[dict])."""
    checked = 0
    mismatches = []
    for d in departments:
        checked += 1
        agent_rows = d["agents"] or [{"name": None, "role": None}]
        matched = False
        variants_tried = []
        for a in agent_rows:
            variants = candidate_variants(d["slug"], a.get("name"), a.get("role"))
            variants_tried = variants
            if any(v in agent_ids for v in variants):
                matched = True
                break
        if not matched:
            mismatches.append({
                "id": d["id"],
                "slug": d["slug"],
                "name": d["name"],
                "variants_tried": variants_tried,
            })
    return checked, mismatches


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Per-department runtime reconciliation guard (Skill 32). Verifies "
                    "EVERY department seeded onto the Command Center board (a workspaces "
                    "row in mission-control.db) has a matching runtime entry in "
                    "openclaw.json agents.list[], using the same slug variants "
                    "blackceo-command-center's resolveSpecialistSessionKey() tries.")
    ap.add_argument("--db", help="path to mission-control.db "
                                 "(default: auto-resolve via shared-utils find_dashboard_db())")
    ap.add_argument("--config", help="path to openclaw.json "
                                     "(default: auto-detect OC_ROOT/openclaw.json)")
    ap.add_argument("--oc-root", help="override OC_ROOT for --config auto-detection")
    ap.add_argument("--quiet", action="store_true", help="one-line PASS summary instead of the full report")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable report to stdout")
    args = ap.parse_args(argv)

    db_path = _resolve_db_path(args.db)
    config_path = _resolve_config_path(args.config, args.oc_root)

    found_db, departments, db_note = load_departments(db_path)

    if not found_db:
        print(f"{TAG} SKIP: {db_note} -- nothing to reconcile yet (not a failure)")
        return EX_OK

    if not departments:
        print(f"{TAG} PASS: {db_note or '0 departments seeded onto the board yet'} -- nothing to reconcile")
        return EX_OK

    ok, agent_ids, cfg_err = load_agent_ids(config_path)
    if not ok:
        print(f"{TAG} FAIL: {len(departments)} department(s) are seeded on the board but "
              f"openclaw.json could not be read ({cfg_err}) -- cannot verify ANY department's "
              f"runtime.", file=sys.stderr)
        for d in departments:
            print(f"  ! {d['name']}  (slug={d['slug']!r}) -- unverifiable (no readable openclaw.json)",
                  file=sys.stderr)
        return EX_CONFIG_UNREADABLE

    checked, mismatches = check_parity(departments, agent_ids)

    if args.json:
        print(json.dumps({
            "checked": checked,
            "mismatches": mismatches,
            "ok": not mismatches,
        }, indent=2))
    elif mismatches:
        print(f"{TAG} FAIL: {len(mismatches)}/{checked} department(s) have a board row but NO "
              f"matching OpenClaw runtime entry (no_specialist_runtime class):", file=sys.stderr)
        for m in mismatches:
            tried = ", ".join(m["variants_tried"]) or "(no candidate slug could be derived)"
            print(f"  ! {m['name']}  (workspace slug={m['slug']!r}, id={m['id']!r})", file=sys.stderr)
            print(f"      tried: {tried}", file=sys.stderr)
        print(f"{TAG} Add a dept-<slug> entry to openclaw.json agents.list[] for each department "
              f"above (re-run materialize-dept-agents.sh) before this box is fully wired.",
              file=sys.stderr)
    else:
        if args.quiet:
            print(f"{TAG} PASS ({checked}/{checked})")
        else:
            print(f"{TAG} PASS: {checked}/{checked} department(s) have a matching OpenClaw runtime entry")

    return EX_MISMATCH if mismatches else EX_OK


if __name__ == "__main__":
    sys.exit(main())
