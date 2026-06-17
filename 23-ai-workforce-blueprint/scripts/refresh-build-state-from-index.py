#!/usr/bin/env python3
"""
refresh-build-state-from-index.py — Skill 23 AI Workforce Blueprint (§1.3)

PURPOSE
    Re-syncs .workforce-build-state.json from the authoritative _index.json
    + on-disk dept directories. Called by converge after every add-*.sh run.

    This is the single derivation step: _index.json (authoritative) → build-state
    (derived). The org-chart, infographic, and Notion closeout are downstream of
    build-state and are rendered by converge after this script runs.

WHAT IT DOES
    1. Loads _index.json (authoritative dept→roles list)
    2. Loads existing .workforce-build-state.json (FAIL LOUD if absent — box
       must have been built first)
    3. For each dept in _index.json: upserts an entry in state["departments"],
       preserving the existing array OR keyed-object shape (matches file's shape)
    4. Per-dept roleLibraryFilled/sopLibraryFilled set via backfill-build-state heuristics
    5. Recomputes any top-level totals the renderers read
    6. Atomically writes the updated state
    7. Exits 0, prints "changed=<0|1>" on stdout

USAGE
    python3 refresh-build-state-from-index.py
    python3 refresh-build-state-from-index.py --dry-run
    python3 refresh-build-state-from-index.py --verbose
    python3 refresh-build-state-from-index.py --strict   (default: gate status:done on library+wiring)
    python3 refresh-build-state-from-index.py --counts-only  (update counts only, never flip status)

EXIT CODES
    0 — success
    1 — FATAL (no build-state found, malformed files, etc.)
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ─── Path resolvers ──────────────────────────────────────────────────────────

def find_build_state_path() -> Path:
    """Resolve the build-state JSON path (env override first, then VPS, then Mac)."""
    # Test/override hook: lets the acceptance suite point at a sandbox state file.
    env_override = os.environ.get("WORKFORCE_BUILD_STATE_PATH")
    if env_override:
        return Path(env_override)
    candidates = [
        Path("/data/.openclaw/workspace/.workforce-build-state.json"),
        Path.home() / ".openclaw/workspace/.workforce-build-state.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[1] if Path.home().is_dir() else candidates[0]


def find_index_json_path() -> Path | None:
    """Locate the role-library _index.json (env override first, then VPS, then Mac)."""
    # Test/override hook: lets the acceptance suite point at a sandbox index.
    env_override = os.environ.get("WORKFORCE_INDEX_PATH")
    if env_override and Path(env_override).is_file():
        return Path(env_override)
    candidates = [
        Path("/data/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json"),
        Path.home() / ".openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def find_departments_dir() -> Path | None:
    """Locate the on-disk departments directory."""
    workspace_candidates = [
        Path("/data/.openclaw/workspace/agents/main/departments"),
        Path.home() / ".openclaw/workspace/agents/main/departments",
        Path("/data/.openclaw/workspace/departments"),
        Path.home() / ".openclaw/workspace/departments",
    ]
    for c in workspace_candidates:
        if c.is_dir():
            return c
    return None


# ─── Per-dept status heuristics (reused from backfill-build-state.py) ────────

def detect_role_library_status(dept_dir: Path) -> str:
    """Heuristic: if how-to.md still has [PENDING — FILL FROM LIBRARY], it's pending."""
    if not dept_dir or not dept_dir.is_dir():
        return "pending"
    filled = 0
    total = 0
    for how_to in dept_dir.rglob("how-to.md"):
        total += 1
        try:
            content = how_to.read_text(encoding="utf-8", errors="replace")
            if "PENDING — FILL FROM LIBRARY" not in content and "PENDING" not in content:
                filled += 1
        except OSError:
            pass
    if total == 0:
        return "pending"
    return "done" if filled >= (total * 0.8) else "pending"


def count_roles_on_disk(dept_dir: Path) -> int:
    """
    DEFECT #5 (build-state honesty): count the role folders that ACTUALLY exist
    on disk for a department, so rolesDone reflects DISK TRUTH and can never be
    set to the planned count while the workspace is empty. A role folder is any
    direct subdir that carries a how-to.md (the role's entry point), excluding
    department-level helper dirs (sops/, memory/, _archive, etc.).
    """
    if not dept_dir or not dept_dir.is_dir():
        return 0
    SKIP = {"sops", "memory", "_archive", "_index", "_compliance_audit",
            "_pending_rewrite", "_stage1_drafts"}
    n = 0
    for child in dept_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name in SKIP or child.name.startswith((".", "_")):
            continue
        if (child / "how-to.md").is_file():
            n += 1
    return n


def detect_sop_library_status(dept_dir: Path) -> str:
    """Heuristic: if SOP/ files exist and none are empty stubs, it's done."""
    if not dept_dir or not dept_dir.is_dir():
        return "pending"
    sop_files = list(dept_dir.rglob("SOP/*.md"))
    sop_files = [f for f in sop_files if f.name != "00-INDEX.md"]
    if not sop_files:
        return "pending"
    stub_count = 0
    for f in sop_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            if "[Step 1 - to be personalized]" in content or len(content.strip()) < 100:
                stub_count += 1
        except OSError:
            pass
    return "done" if stub_count == 0 else "pending"


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-sync .workforce-build-state.json from _index.json + on-disk dirs")
    parser.add_argument("--dry-run", action="store_true", help="No writes, just report")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--strict", action="store_true", default=True,
                        help="Gate status:done on library+wiring booleans from the build-state (default ON)")
    parser.add_argument("--counts-only", action="store_true",
                        help="Update role counts only; never touch status field")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()

    # Load _index.json
    index_path = find_index_json_path()
    if not index_path:
        print("FATAL: _index.json not found — install Skill 23 first.", file=sys.stderr)
        sys.exit(1)
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot read _index.json at {index_path}: {e}", file=sys.stderr)
        sys.exit(1)

    index_depts = idx.get("departments", {})
    if args.verbose:
        print(f"[refresh-build-state] _index.json: {len(index_depts)} depts, "
              f"total_roles={idx.get('total_roles', '?')}")

    # Load build-state (FAIL LOUD if absent)
    state_path = find_build_state_path()
    if not state_path.exists():
        print(f"FATAL: .workforce-build-state.json not found at {state_path}. "
              f"This box must be built with Skill 23 before converge can refresh it.", file=sys.stderr)
        sys.exit(1)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot read build-state at {state_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"[refresh-build-state] build-state loaded from {state_path}")

    # Detect departments shape (array vs keyed-object) and preserve it
    existing_depts = state.get("departments", {})
    if isinstance(existing_depts, list):
        dept_shape = "array"
        # Convert to dict for uniform processing
        existing_depts_dict = {
            (d.get("slug") or d.get("id") or str(i)): d
            for i, d in enumerate(existing_depts)
        }
    else:
        dept_shape = "object"
        existing_depts_dict = dict(existing_depts) if existing_depts else {}

    if args.verbose:
        print(f"[refresh-build-state] departments shape: {dept_shape}, "
              f"existing={len(existing_depts_dict)}")

    # Locate on-disk departments dir for heuristic checks
    depts_dir = find_departments_dir()

    # Upsert each dept from _index.json into build-state
    changed = False
    for slug, idx_entry in index_depts.items():
        dept_roles = idx_entry.get("roles", [])
        roles_count = len(dept_roles)

        # Get on-disk dept dir for heuristic checks
        dept_on_disk = (depts_dir / slug) if depts_dir else None
        rl_status = detect_role_library_status(dept_on_disk)
        sop_status = detect_sop_library_status(dept_on_disk)
        # DEFECT #5: rolesDone reflects DISK TRUTH, not the planned count.
        roles_on_disk = count_roles_on_disk(dept_on_disk)

        if slug in existing_depts_dict:
            # Upsert: update role counts and statuses, preserve other fields
            entry = existing_depts_dict[slug]
            # C1: Read library/wiring booleans from the gates (written by
            # verify-library-gate.sh / verify-wiring.sh), not the local heuristics.
            # Fall back to the heuristic only if gate fields are absent.
            gate_rl_filled = entry.get("roleLibraryFilled")
            gate_sop_filled = entry.get("sopLibraryFilled")
            gate_wiring = entry.get("wiringStatus", "")
            # If gate fields are missing, seed from heuristic (first-run fallback)
            if gate_rl_filled is None:
                gate_rl_filled = (rl_status == "done")
            if gate_sop_filled is None:
                gate_sop_filled = (sop_status == "done")

            # C2: Gate status:done on all three conditions (library + wiring)
            if args.counts_only:
                # --counts-only: never touch status
                new_status = entry.get("status", "building")
            elif args.strict:
                wiring_done = (gate_wiring == "done")
                dept_done = bool(gate_rl_filled) and bool(gate_sop_filled) and wiring_done
                new_status = "done" if dept_done else entry.get("status", "building")
            else:
                new_status = "done"  # legacy/non-strict: count-based

            # DEFECT #5 (honesty hard floor): a dept can NEVER be "done" while 0
            # roles are on disk, regardless of gate booleans or --strict mode.
            # status:"done" with rolesDone:0 was the exact fiction the canary hit.
            if roles_on_disk == 0 and new_status == "done":
                new_status = entry.get("status", "building")
                if new_status == "done":
                    new_status = "building"

            if (entry.get("rolesPlanned") != roles_count or
                    entry.get("rolesDone") != roles_on_disk or
                    entry.get("status") != new_status):
                entry["rolesPlanned"] = roles_count
                entry["rolesDone"] = roles_on_disk
                entry["status"] = new_status
                entry["roleLibraryFilled"] = gate_rl_filled
                entry["sopLibraryFilled"] = gate_sop_filled
                entry["updatedAt"] = now
                existing_depts_dict[slug] = entry
                changed = True
                if args.verbose:
                    print(f"  updated dept: {slug} (planned={roles_count}, "
                          f"onDisk={roles_on_disk}, status={new_status})")
        else:
            # New dept — add with full shape
            # C2: New depts start as "building" — gates must pass before done
            name = " ".join(w.capitalize() for w in slug.replace("-", " ").split())
            _new_rl = (rl_status == "done")
            _new_sop = (sop_status == "done")
            if args.counts_only:
                _new_status = "building"
            elif args.strict:
                # New dept: wiring is not yet done (no entry), so status=building
                _new_status = "building"
            else:
                _new_status = "done"
            # DEFECT #5: honesty floor also applies to new depts — never "done"
            # with 0 roles on disk.
            if roles_on_disk == 0 and _new_status == "done":
                _new_status = "building"
            existing_depts_dict[slug] = {
                "slug": slug,
                "name": name,
                "status": _new_status,
                "rolesPlanned": roles_count,
                "rolesDone": roles_on_disk,
                "roleLibraryFilled": _new_rl,
                "sopLibraryFilled": _new_sop,
                "wiringStatus": "pending",
                "emoji": "",
                "createdAt": now,
                "updatedAt": now,
            }
            changed = True
            if args.verbose:
                print(f"  added dept: {slug} (planned={roles_count}, "
                      f"onDisk={roles_on_disk}, status={_new_status})")

    # Recompute totals
    total_roles = sum(len(d.get("roles", [])) for d in index_depts.values())
    if state.get("totalRoles") != total_roles or state.get("totalDepartments") != len(index_depts):
        state["totalRoles"] = total_roles
        state["totalDepartments"] = len(index_depts)
        changed = True

    # Write back in original shape
    if dept_shape == "array":
        state["departments"] = list(existing_depts_dict.values())
    else:
        state["departments"] = existing_depts_dict

    state["lastRefreshedAt"] = now
    state["refreshSource"] = "refresh-build-state-from-index.py"

    if args.dry_run:
        print(f"[DRY-RUN] Would write {state_path} (changed={changed})")
        print(f"changed={1 if changed else 0}")
        return

    if changed:
        # Atomic write
        state_dir = state_path.parent
        fd, tmp_path = tempfile.mkstemp(prefix=".build-state.", suffix=".json.tmp",
                                        dir=str(state_dir))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, str(state_path))
        except OSError as e:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink(missing_ok=True)
            print(f"FATAL: write failed: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"[refresh-build-state] Updated {state_path} ({len(index_depts)} depts, "
              f"total_roles={total_roles})")
    else:
        if args.verbose:
            print("[refresh-build-state] No changes needed — build-state is current")

    print(f"changed={1 if changed else 0}")


if __name__ == "__main__":
    main()
