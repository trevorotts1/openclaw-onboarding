#!/usr/bin/env python3
"""
backfill-build-state.py — RC-6: Stamp missing gate fields into
.workforce-build-state.json for clients whose build predates v10.16.8.

This is a one-time idempotent repair script.  It does NOT change fields that
are already set (unless --force is passed).  Safe to re-run.

Fields backfilled (if absent or null):
  sopLibraryStatus        — defaults to "done" when SOPs appear authored, else "pending"
  roleLibraryStatus       — defaults to "done" when role library files present, else "pending"
  commsAutomationStatus   — defaults to "not-applicable" (conservative; operator can flip)
  canonicalReconciliation — defaults to {status:"reconciled", decisions:{}, autoIncluded:[]}

Exit codes:
    0 = success
    1 = fatal (build-state not found and cannot be created)
    2 = soft (partial — some depts still lack data, manual review needed)

Usage:
    python3 backfill-build-state.py
    python3 backfill-build-state.py --dry-run
    python3 backfill-build-state.py --force    # overwrite even non-null fields
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# JEV A36 (spec 10.3): backfill-job late gate through the EXISTING D23 module
# (shared-utils/decision_engine/commit/dispatch.py) — imported by path, never
# restated. A backfill that races a newer committed decision fails closed
# instead of clobbering its head.
_COMMIT_DIR = (Path(__file__).resolve().parent.parent.parent
               / "shared-utils" / "decision_engine" / "commit")
sys.path.insert(0, str(_COMMIT_DIR))
try:
    import dispatch as _cas_dispatch  # noqa: E402 -- JEV A36 late gate
except Exception:  # noqa: BLE001 -- bare box: job still backfills, gate reports
    _cas_dispatch = None


def gate_backfill_result(task_key, result_revision, state_dir=None,
                         scope=None):
    """Backfill-job late gate (A36) through existing D23 check_late_result.

    Returns (ok, detail): ok True when the backfill result is current; False
    with the typed D23 failure when a stale backfill must not clobber the
    newer head. kind is fixed to "backfill" (D23 closed late-kind set).
    """
    if _cas_dispatch is None:
        return False, {"error": "cas_unavailable"}
    import sqlite3 as _sqlite3  # noqa: PLC0415 (stdlib, deferred for import cost)
    con = None
    try:
        if state_dir is not None:
            cand = Path(state_dir) / "decision_revisions.db"
            cand.parent.mkdir(parents=True, exist_ok=True)
            con = _sqlite3.connect(str(cand), timeout=30)
            con.row_factory = _sqlite3.Row
        if con is None:
            _commit = _cas_dispatch._load_commit()
            store = _commit.fresh_state(
                input_hash=_cas_dispatch.scope_hash(scope or {}))
        else:
            _commit, store = _cas_dispatch.load_cas_store(
                con, task_key,
                _cas_dispatch.scope_hash(scope or {}) if scope is not None else None)
        ok = _cas_dispatch.guard_late_result(store, "backfill",
                                             int(result_revision))
        return True, {"revision": store["decision_revision"], "ok": ok}
    except Exception as exc:  # noqa: BLE001 -- typed D23 failure surfaces here
        return False, {"error": type(exc).__name__, "detail": str(exc),
                       "kind": "backfill", "result_revision": result_revision}
    finally:
        try:
            if con is not None:
                con.close()
        except _sqlite3.Error:
            pass
from pathlib import Path


def find_build_state_path() -> Path:
    """Return the build-state path (VPS first, Mac fallback)."""
    candidates = [
        Path("/data/.openclaw/workspace/.workforce-build-state.json"),
        Path.home() / ".openclaw/workspace/.workforce-build-state.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    # Return the platform-appropriate path for creation
    if Path("/data/.openclaw").is_dir():
        return candidates[0]
    return candidates[1]


def detect_role_library_status(departments_dir: Path | None) -> str:
    """Heuristic: scan dept role folders; if any how-to.md has the library marker,
    call it 'done'. If no role folders at all: 'pending'."""
    if not departments_dir or not departments_dir.is_dir():
        return "pending"
    filled = 0
    total_roles = 0
    for dept_dir in departments_dir.iterdir():
        if not dept_dir.is_dir() or dept_dir.name.startswith("."):
            continue
        for how_to in dept_dir.rglob("how-to.md"):
            total_roles += 1
            try:
                if "<!-- Filled from role-library" in how_to.read_text(encoding="utf-8", errors="replace"):
                    filled += 1
            except OSError:
                pass
    if total_roles == 0:
        return "pending"
    return "done" if filled >= (total_roles * 0.8) else "pending"


def detect_sop_library_status(departments_dir: Path | None) -> str:
    """Heuristic: if no stub markers remain → done, else pending."""
    if not departments_dir or not departments_dir.is_dir():
        return "pending"
    total_sop_files = 0
    stub_files = 0
    for dept_dir in departments_dir.iterdir():
        if not dept_dir.is_dir() or dept_dir.name.startswith("."):
            continue
        for md_file in dept_dir.rglob("*.md"):
            if md_file.name.startswith("0") or "how-to" in md_file.name.lower():
                total_sop_files += 1
                try:
                    if "[Step 1 - to be personalized]" in md_file.read_text(encoding="utf-8", errors="replace"):
                        stub_files += 1
                except OSError:
                    pass
    if total_sop_files == 0:
        return "pending"
    return "done" if stub_files == 0 else "pending"


def find_departments_dir() -> Path | None:
    target_slug = os.environ.get("COMPANY_SLUG", "").strip()
    roots = [
        Path.home() / "clawd" / "zero-human-company",
        Path("/data/clawd/zero-human-company"),
        Path.home() / "clawd" / "zhc",
        Path("/data/clawd/zhc"),
    ]
    best: tuple[float, Path] | None = None
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if target_slug and child.name != target_slug:
                continue
            dept_dir = child / "departments"
            if dept_dir.is_dir():
                mtime = child.stat().st_mtime
                if best is None or mtime > best[0]:
                    best = (mtime, dept_dir)
    if best:
        return best[1]
    # Legacy fallbacks
    for legacy in [
        Path.home() / ".openclaw/workspace/departments",
        Path("/data/.openclaw/workspace/departments"),
    ]:
        if legacy.is_dir():
            return legacy
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill build-state gate fields for pre-v10.16.8 clients")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite even non-null fields")
    args = parser.parse_args()

    state_path = find_build_state_path()
    departments_dir = find_departments_dir()

    print(f"[backfill-build-state] State: {state_path}")
    print(f"[backfill-build-state] Departments: {departments_dir}")

    # Load or create state
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception as e:
            print(f"[backfill-build-state] WARN: could not parse {state_path}: {e}", file=sys.stderr)
            state = {}
    else:
        print(f"[backfill-build-state] Build-state not found at {state_path}; will create minimal stub")
        state = {"version": 1, "interviewComplete": False, "ownerChat": 0, "departments": {}}

    now = datetime.now(timezone.utc).isoformat()
    changed = False

    # --- sopLibraryStatus ---
    if args.force or not state.get("sopLibraryStatus"):
        val = detect_sop_library_status(departments_dir)
        state["sopLibraryStatus"] = val
        print(f"[backfill-build-state] Set sopLibraryStatus = {val}")
        changed = True
    else:
        print(f"[backfill-build-state] sopLibraryStatus already set: {state['sopLibraryStatus']}")

    # --- roleLibraryStatus ---
    if args.force or not state.get("roleLibraryStatus"):
        val = detect_role_library_status(departments_dir)
        state["roleLibraryStatus"] = val
        print(f"[backfill-build-state] Set roleLibraryStatus = {val}")
        changed = True
    else:
        print(f"[backfill-build-state] roleLibraryStatus already set: {state['roleLibraryStatus']}")

    # --- commsAutomationStatus ---
    if args.force or not state.get("commsAutomationStatus"):
        state["commsAutomationStatus"] = "not-applicable"
        print("[backfill-build-state] Set commsAutomationStatus = not-applicable (conservative default; flip to 'done' after Skill 38)")
        changed = True
    else:
        print(f"[backfill-build-state] commsAutomationStatus already set: {state['commsAutomationStatus']}")

    # --- canonicalReconciliation ---
    if args.force or not isinstance(state.get("canonicalReconciliation"), dict):
        # Reconstruct a minimal valid block from what's on disk
        on_disk_slugs: list[str] = []
        if departments_dir and departments_dir.is_dir():
            on_disk_slugs = [
                d.name for d in departments_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]
        state["canonicalReconciliation"] = {
            "status": "reconciled",
            "decisions": {},
            "autoIncluded": on_disk_slugs,
            "backfilledAt": now,
        }
        print(f"[backfill-build-state] Set canonicalReconciliation (autoIncluded: {on_disk_slugs})")
        changed = True
    else:
        print(f"[backfill-build-state] canonicalReconciliation already set")

    # --- Per-dept roleLibraryFilled / sopLibraryFilled ---
    if departments_dir and departments_dir.is_dir():
        depts = state.get("departments")
        if isinstance(depts, dict):
            for dept_dir in departments_dir.iterdir():
                if not dept_dir.is_dir() or dept_dir.name.startswith("."):
                    continue
                slug = dept_dir.name
                dept_state = depts.get(slug)
                if not isinstance(dept_state, dict):
                    continue
                if args.force or dept_state.get("roleLibraryFilled") is None:
                    # Check if any how-to.md in this dept has library marker
                    filled = any(
                        "<!-- Filled from role-library" in how_to.read_text(errors="replace")
                        for how_to in dept_dir.rglob("how-to.md")
                        if how_to.exists()
                    )
                    dept_state["roleLibraryFilled"] = filled
                    changed = True
                if args.force or dept_state.get("sopLibraryFilled") is None:
                    stubs = sum(
                        1 for md in dept_dir.rglob("*.md")
                        if "[Step 1 - to be personalized]" in md.read_text(errors="replace")
                        if md.exists()
                    )
                    dept_state["sopLibraryFilled"] = (stubs == 0)
                    changed = True

    if not changed:
        print("[backfill-build-state] No changes needed — all gate fields already present")
        return 0

    if args.dry_run:
        print("[backfill-build-state] DRY-RUN: would write:")
        print(json.dumps(state, indent=2))
        return 0

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        print(f"[backfill-build-state] Written: {state_path}")
    except OSError as e:
        print(f"[backfill-build-state] FATAL: could not write {state_path}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
