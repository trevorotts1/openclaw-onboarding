#!/usr/bin/env python3
"""Reconciliation sweep for board card divergence.

Scans run directories under ``--scan-root`` for jobs whose board card was never
created or whose card status is behind the local state. Matches on
``deck_slug`` (``source_ref`` / ``external_session_id``), never on title ---
because ``cc_board``'s idempotency key is ``sha256(source_ref + title)``, an
edited title yields a different key and a naive re-ingest would **MINT A
DUPLICATE**.

**A reconciliation sweep exists to stop live divergence, not to reconstruct a
board's past.**  Minting cards for historical run dirs is how a sweep turns
into a mass-import, and a board that has been deliberately cleared must stay
cleared.  ``--max-age-hours`` (default 72) enforces this.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _deck_slug(run_dir: Path, state: Dict[str, Any]) -> Optional[str]:
    """The title-independent board handle."""
    return (
        (state.get("intake") or {}).get("deck_slug")
        or (_read_json(run_dir / "working" / "copy" / "intake.json") or {}).get("deck_slug")
        or None
    )


def _task_id_anywhere(state: Dict[str, Any], manifest: Dict[str, Any]) -> bool:
    if (state.get("board") or {}).get("task_id"):
        return True
    if manifest.get("cc_task_id"):
        return True
    return False


def _derive_target_status(state: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    terminal = state.get("terminal")
    if terminal == "BLOCKED":
        return "blocked", "P4-RENDER", "Job blocked (sweep reconciled)"
    if terminal == "DONE":
        return "review", "TERMINAL", "All gates passed (sweep reconciled)"
    phases = state.get("phases") or []
    if any(isinstance(p, dict) and p.get("status") in ("running", "done") for p in phases):
        return "in_progress", "P4-RENDER", "Rendering in progress (sweep reconciled)"
    return None, None, None


def _is_engine_run_dir(state: Dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        return False
    jid = state.get("job_id", "")
    if not isinstance(jid, str) or not jid.startswith("pj_"):
        return False
    if state.get("terminal") == "DONE":
        return False
    return True


def _has_failed_advance(run_dir: Path) -> bool:
    """Check whether cc-board.json holds an unsuperseded ok:false status movement."""
    import cc_board as _ccb
    p = _ccb._movements_path(run_dir)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    movements = data.get("movements") if isinstance(data, dict) else None
    if not isinstance(movements, list):
        return False
    last_failed = None
    for m in movements:
        if not isinstance(m, dict) or m.get("kind") != "status":
            continue
        if m.get("ok"):
            last_failed = None
        else:
            last_failed = m
    return last_failed is not None


# Outcome constants
OUTCOME_BOARD_DISABLED = "board_disabled"
OUTCOME_NOT_A_RUN_DIR = "not_a_run_dir"
OUTCOME_TOO_OLD = "too_old"
OUTCOME_CARD_MISSING = "card_missing"
OUTCOME_CARD_BEHIND = "card_behind"
OUTCOME_CONSISTENT = "consistent"


def _classify(run_dir, state, manifest, max_age_hours, board_enabled, state_schema_version):
    if not _is_engine_run_dir(state):
        return OUTCOME_NOT_A_RUN_DIR
    if state.get("schema_version") != state_schema_version:
        return OUTCOME_NOT_A_RUN_DIR
    slug = _deck_slug(run_dir, state)
    if slug is None:
        return OUTCOME_NOT_A_RUN_DIR
    if not board_enabled:
        return OUTCOME_BOARD_DISABLED
    created_at = state.get("created_at")
    if created_at:
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc).astimezone() - created_dt.astimezone(timezone.utc)).total_seconds() / 3600
            if age_hours > max_age_hours:
                return OUTCOME_TOO_OLD
        except (ValueError, OverflowError):
            pass
    if _task_id_anywhere(state, manifest):
        if _has_failed_advance(run_dir):
            return OUTCOME_CARD_BEHIND
        return OUTCOME_CONSISTENT
    return OUTCOME_CARD_MISSING


def _write_finding(scan_root, run_dir, outcome, applied, detail=""):
    p = Path(scan_root) / "reconcile-findings.jsonl"
    entry = {"run_dir": str(run_dir), "outcome": outcome, "applied": applied, "detail": detail}
    try:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        print(f"[sweep] could not write findings to {p}", file=sys.stderr, flush=True)


def _walk_state_files(root, depth):
    if depth < 0:
        return
    sp = root / "state.json"
    if sp.is_file():
        yield root, sp
    if depth == 0:
        return
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.is_dir() or entry.is_symlink():
            if entry.is_symlink():
                real = entry.resolve()
                if real.is_dir():
                    yield from _walk_state_files(real, depth - 1)
                continue
            yield from _walk_state_files(entry, depth - 1)


def reconcile_sweep(scan_root, max_age_hours=72.0, apply=False, scan_depth=2):
    import cc_board as _ccb
    from .state import STATE_SCHEMA_VERSION

    if isinstance(scan_root, str):
        scan_root = Path(scan_root)
    scan_root = scan_root.expanduser().resolve()

    cfg = _ccb.board_config(os.environ)
    if cfg is None:
        print("reconcile-board: board disabled (COMMAND_CENTER_URL/MISSION_CONTROL_URL unset) -- nothing to do")
        return 0

    board_enabled = True

    seen = set()
    entries = []
    for run_dir, sp in _walk_state_files(scan_root, scan_depth):
        rp = run_dir.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        entries.append((run_dir, sp))

    if not entries:
        print(f"reconcile-board: NO state.json found -- check --scan-root and --scan-depth (depth={scan_depth})")
        return 0

    counts = {
        OUTCOME_NOT_A_RUN_DIR: 0, OUTCOME_TOO_OLD: 0,
        OUTCOME_CARD_MISSING: 0, OUTCOME_CARD_BEHIND: 0, OUTCOME_CONSISTENT: 0,
    }
    deduped_count = 0
    applied_count = 0
    failed_count = 0

    for run_dir, state_path in entries:
        outcome = OUTCOME_NOT_A_RUN_DIR
        detail = ""
        state = {}
        try:
            state = _read_json(state_path)
            if state is None:
                outcome = OUTCOME_NOT_A_RUN_DIR
                detail = "state.json unreadable"
            else:
                manifest = _ccb._read_manifest(run_dir)
                outcome = _classify(run_dir, state, manifest, max_age_hours, board_enabled, STATE_SCHEMA_VERSION)
        except Exception:
            outcome = OUTCOME_NOT_A_RUN_DIR
            detail = f"classification error: {traceback.format_exc().strip().splitlines()[-1]}"

        applied = False
        action_detail = ""

        if outcome == OUTCOME_CARD_MISSING and apply:
            try:
                slug = _deck_slug(run_dir, state)
                title = (state.get("intake") or {}).get("deck_title") or slug or "Untitled"
                description = f"Sweep-created card for {slug}"
                manifest_before = _ccb._read_manifest(run_dir)
                had_task_before = bool(manifest_before.get("cc_task_id"))
                task_id = _ccb.ingest_deck_task(run_dir, slug, title, description, priority="normal", env=os.environ)
                if task_id:
                    if had_task_before:
                        deduped_count += 1
                        action_detail = "deduped (a card already existed)"
                    else:
                        action_detail = "created"
                    target_status, phase_id, note = _derive_target_status(state)
                    if target_status and target_status in _ccb.CC_TASK_STATUSES:
                        assert target_status != "done", "sweep: refusing to set status='done'"
                        _ccb.patch_phase(run_dir, task_id, phase_id, target_status, note, env=os.environ)
                    applied = True
                    applied_count += 1
            except Exception as exc:
                outcome = "card_create_failed"
                detail = f"ingest/patch failed: {exc}"
                failed_count += 1

        if outcome == OUTCOME_CARD_BEHIND and apply:
            try:
                rc = _ccb.reconcile(run_dir)
                if rc == 0:
                    applied = True
                    applied_count += 1
                    action_detail = "replayed ok"
                else:
                    action_detail = f"replay failed (rc={rc})"
                    failed_count += 1
            except Exception as exc:
                action_detail = f"reconcile raised: {exc}"
                failed_count += 1

        if outcome in (OUTCOME_CARD_MISSING, OUTCOME_CARD_BEHIND):
            _write_finding(scan_root, run_dir, outcome, applied, action_detail or detail or outcome)

        counts[outcome] = counts.get(outcome, 0) + 1
        line = f"  {run_dir.name:<30} -> {outcome}"
        if action_detail:
            line += f" ({action_detail})"
        elif detail:
            line += f" ({detail})"
        print(line, flush=True)

    total = len(entries)
    parts = []
    for k in (OUTCOME_CARD_MISSING, OUTCOME_CARD_BEHIND, OUTCOME_CONSISTENT, OUTCOME_TOO_OLD, OUTCOME_NOT_A_RUN_DIR):
        if k in counts:
            parts.append(f"{counts[k]} {k}")
    summary = (f"reconcile-board: scanned {total} run dir(s) under {scan_root} "
               f"(depth {scan_depth}); {', '.join(parts)}; applied: {applied_count}")
    if deduped_count:
        summary += f"; DEDUPED: {deduped_count} (Guard A may be too loose -- a card existed that the local record did not know about)"
    if failed_count:
        summary += f"; FAILED: {failed_count}"
    print(summary, flush=True)
    return 0
