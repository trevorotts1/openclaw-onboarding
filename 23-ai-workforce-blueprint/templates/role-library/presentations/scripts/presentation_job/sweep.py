"""Board reconciliation sweep.

A sweep exists to stop live divergence, not to reconstruct a board's past.
Minting cards for historical run dirs is how a sweep turns into a mass-import,
and a board that has been deliberately cleared must stay cleared.

This sweep scans a root directory for run dirs whose board card is missing
or behind. It classifies every run dir into exactly one of six outcomes and
takes action only under --apply. It never touches state.json, never makes
its own HTTP calls, and never sets "done" on a card.
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .state import (
    _read_json,
    STATE_SCHEMA_VERSION,
    EXIT_OK,
    EXIT_SWEEP_NO_RUNS,
    EXIT_SWEEP_HAD_FAILURES,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deck_slug(run_dir: Path, state: dict) -> Optional[str]:
    """The title-independent board handle: cc_board sends it as BOTH source_ref and
    external_session_id (cc_board.py:496,499). NEVER derive a match from the card title --
    the idempotency key is sha256(source_ref + title) (:488), so an edited title yields a
    different key and a naive re-ingest would MINT A DUPLICATE."""
    slug = (state.get("intake") or {}).get("deck_slug")
    if slug:
        return str(slug)
    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    if intake and isinstance(intake, dict):
        slug = intake.get("deck_slug")
        if slug:
            return str(slug)
    return None


def _resolve_task_id(state: dict, run_dir: Path) -> Optional[str]:
    """A card counts as existing when EITHER state['board']['task_id'] OR
    process_manifest.json's cc_task_id is present -- either one alone is enough."""
    tid = (state.get("board") or {}).get("task_id")
    if tid:
        return str(tid)
    mf = _read_json(run_dir / "working" / "checkpoints" / "process_manifest.json")
    if mf and isinstance(mf, dict) and mf.get("cc_task_id"):
        return str(mf["cc_task_id"])
    return None


def _is_valid_engine_dir(run_dir: Path) -> Tuple[bool, Optional[dict]]:
    """Guard A: a run dir qualifies only when state.json exists, parses, carries
    a job_id beginning 'pj_', and has the right schema_version. Returns (ok, state_dict)."""
    st = _read_json(run_dir / "state.json")
    if not st or not isinstance(st, dict):
        return False, None
    job_id = st.get("job_id", "")
    if not isinstance(job_id, str) or not job_id.startswith("pj_"):
        return False, None
    if st.get("schema_version") != STATE_SCHEMA_VERSION:
        return False, None
    return True, st


def _target_status(state: dict) -> Optional[str]:
    """Derive the target board status from what state.json already proves.
    Never returns 'done' -- the producer stops at 'review'."""
    terminal = state.get("terminal")
    if terminal == "BLOCKED":
        return "blocked"
    if terminal == "DONE":
        return "review"  # never "done"
    phases = state.get("phases") or []
    for p in phases:
        if isinstance(p, dict) and p.get("status") in ("running", "done"):
            return "in_progress"
    return None


def _find_run_dirs(scan_root: Path, scan_depth: int) -> List[Path]:
    """Find all directories containing state.json up to scan_depth levels below
    scan_root. Each directory is counted once -- a symlinked run dir reachable
    at two depths appears once."""
    found: Set[Path] = set()
    # Use resolve() to collapse symlinks
    scan_root = scan_root.resolve()
    for state_file in list(scan_root.rglob("state.json")):
        run_dir = state_file.parent.resolve()
        # Only include if relative depth <= scan_depth
        try:
            rel = run_dir.relative_to(scan_root)
        except ValueError:
            continue
        depth = len(rel.parts)
        if depth > scan_depth:
            continue
        found.add(run_dir)
    return sorted(found)


def _classify(
    run_dir: Path,
    state: dict,
    now: datetime,
    max_age_hours: float,
) -> Tuple[str, Optional[str]]:
    """Classify a single run dir. Returns (outcome, detail_string_or_None)."""
    # --- Terminal DONE with no card: do not ingest ---
    if state.get("terminal") == "DONE":
        task_id = _resolve_task_id(state, run_dir)
        if not task_id:
            return "not_a_run_dir", "finished job, no card needed"

    # --- Guard B: max age ---
    created_str = state.get("created_at")
    if created_str:
        try:
            created = datetime.fromisoformat(created_str).astimezone(timezone.utc)
            age_hours = (now - created).total_seconds() / 3600.0
            if age_hours > max_age_hours:
                return "too_old", f"created {age_hours:.1f}h ago"
        except (ValueError, TypeError):
            pass

    # --- Check for existing task_id ---
    task_id = _resolve_task_id(state, run_dir)

    if task_id:
        # Card exists. Check if it is behind.
        movements_path = run_dir / "working" / "checkpoints" / "cc-board.json"
        movements_data = _read_json(movements_path)
        if movements_data and isinstance(movements_data, dict):
            movements = movements_data.get("movements")
            if isinstance(movements, list):
                last_failed = None
                for m in movements:
                    if not isinstance(m, dict) or m.get("kind") != "status":
                        continue
                    if m.get("ok"):
                        last_failed = None
                    else:
                        last_failed = m
                if last_failed is not None:
                    return "card_behind", f"task_id={task_id}"
        return "consistent", f"task_id={task_id}"

    # --- Card missing ---
    return "card_missing", None


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def reconcile_sweep(
    scan_root: Path,
    *,
    scan_depth: int = 2,
    apply: bool = False,
    max_age_hours: float = 72.0,
) -> int:
    """Scan --scan-root for jobs whose board card is missing or behind.

    FAIL-SOFT: one bad run dir never ends the sweep -- the loop keeps going
    and every remaining run dir still gets classified. But "kept going" is
    not the same claim as "everything is fine", so the return code names
    exactly one of three distinct outcomes:

      EXIT_OK (0)               -- scanned >=1 run dir, none raised.
      EXIT_SWEEP_NO_RUNS (10)   -- scanned 0 run dirs. UNDETERMINED: this is
                                    not evidence the fleet is healthy, it is
                                    evidence the sweep checked nothing. Never
                                    treat this as a pass.
      EXIT_SWEEP_HAD_FAILURES (11) -- scanned >=1 run dir but at least one
                                    raised an unexpected error while being
                                    classified or reconciled.
    """

    # --- Import cc_board and BoardMirror lazily ---
    import cc_board as _ccb
    from .board import BoardMirror

    now = datetime.now(timezone.utc)

    # --- Board disabled check ---
    cfg = _ccb.board_config(os.environ)
    if cfg is None:
        print("reconcile-board: board_disabled", flush=True)
        board_enabled = False
    else:
        board_enabled = True

    # --- Find run dirs ---
    run_dirs = _find_run_dirs(scan_root, scan_depth)
    scanned = len(run_dirs)

    if scanned == 0:
        print(
            f"reconcile-board: UNDETERMINED -- NO state.json found under "
            f"{scan_root} (depth {scan_depth}) -- 0 run dirs were checked, "
            f"this is NOT a pass -- check --scan-root and --scan-depth",
            flush=True,
        )
        return EXIT_SWEEP_NO_RUNS

    # --- Classification ---
    outcomes: Dict[str, List[Tuple[Path, Optional[str]]]] = {
        "not_a_run_dir": [],
        "too_old": [],
        "card_missing": [],
        "card_behind": [],
        "consistent": [],
        "failure": [],
    }

    created_count = 0
    deduped_count = 0
    replay_failed_count = 0

    findings_lines: List[str] = []
    findings_path = scan_root / "reconcile-findings.jsonl"

    for run_dir in run_dirs:
        try:
            # Guard A: validate engine dir
            is_valid, state = _is_valid_engine_dir(run_dir)
            if not is_valid:
                outcomes["not_a_run_dir"].append((run_dir, None))
                print(f"  skipped: not_a_run_dir   {run_dir}", flush=True)
                continue

            # Check for slug
            slug = _deck_slug(run_dir, state)
            if slug is None:
                outcomes["not_a_run_dir"].append((run_dir, "no deck_slug resolvable"))
                print(f"  skipped: not_a_run_dir   {run_dir} (no deck_slug)", flush=True)
                continue

            outcome, detail = _classify(run_dir, state, now, max_age_hours)
            label = detail or ""
            print(f"  {outcome:<16} {run_dir} {label}", flush=True)

            outcomes.setdefault(outcome, []).append((run_dir, detail))

            # --- Actionable (card_missing or card_behind) -> always write findings ---
            is_actionable = outcome in ("card_missing", "card_behind")

            if is_actionable:
                finding = {
                    "run_dir": str(run_dir),
                    "outcome": outcome,
                    "deck_slug": slug,
                    "applied": False,
                }

            if outcome == "card_missing" and apply and board_enabled:
                title = (state.get("intake") or {}).get("deck_title", slug)
                try:
                    task_id = _ccb.ingest_deck_task(
                        str(run_dir),
                        slug,
                        title,
                        f"Reconciliation sweep: deck {slug}",
                        priority="normal",
                        env=os.environ,
                    )
                except Exception as exc:
                    print(
                        f"  FAILED: card_missing ingest raised {type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    outcomes["failure"].append(
                        (run_dir, f"ingest failed: {type(exc).__name__}")
                    )
                    finding["applied"] = False
                else:
                    if task_id:
                        created_count += 1
                        finding["applied"] = True
                        finding["task_id"] = task_id
                        print(f"    -> created task_id={task_id}", flush=True)
                    else:
                        # ingest returns None on failure; check if it was deduped or failed
                        finding["applied"] = False

            elif outcome == "card_behind" and apply and board_enabled:
                task_id = _resolve_task_id(state, run_dir)
                finding["task_id"] = task_id
                try:
                    rc = _ccb.reconcile(str(run_dir))
                except Exception as exc:
                    print(
                        f"  FAILED: card_behind reconcile raised {type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    outcomes["failure"].append(
                        (run_dir, f"reconcile failed: {type(exc).__name__}")
                    )
                    finding["applied"] = False
                else:
                    if rc == 0:
                        finding["applied"] = True
                    else:
                        replay_failed_count += 1
                        finding["applied"] = False
                        print(f"    -> reconcile returned 1 (replay still failed)", flush=True)

            if is_actionable:
                findings_lines.append(json.dumps(finding, ensure_ascii=False))

        except Exception as exc:
            outcomes.setdefault("failure", []).append(
                (run_dir, f"{type(exc).__name__}: {exc}")
            )
            print(
                f"  FAILED: {type(exc).__name__}: {exc}   {run_dir}",
                flush=True,
            )

    # --- Write findings ---
    if findings_lines:
        try:
            with open(findings_path, "a", encoding="utf-8") as fh:
                for line in findings_lines:
                    fh.write(line + "\n")
        except OSError as exc:
            print(
                f"reconcile-board: could not write findings file: {exc}",
                file=__import__("sys").stderr,
                flush=True,
            )

    # --- Summary with denominator ---
    counts = {k: len(v) for k, v in outcomes.items()}
    total = sum(counts.values())
    applied_total = created_count + (
        counts.get("card_behind", 0) - replay_failed_count
    )

    parts = [
        f"scanned {scanned} run dir(s) under {scan_root} (depth {scan_depth})",
        f"card_missing: {counts.get('card_missing', 0)}",
        f"card_behind: {counts.get('card_behind', 0)}",
        f"consistent: {counts.get('consistent', 0)}",
        f"too_old: {counts.get('too_old', 0)}",
        f"not_a_run_dir: {counts.get('not_a_run_dir', 0)}",
    ]
    if counts.get("failure", 0):
        parts.append(f"failure: {counts['failure']}")
    if deduped_count:
        parts.append(f"deduped: {deduped_count} (Guard A might be too loose)")

    # applied: G only with --apply
    parts.append(f"applied: {applied_total}" if apply else "applied: 0")
    print(f"reconcile-board: {'; '.join(parts)}", flush=True)

    if deduped_count:
        print(
            "reconcile-board: WARNING — deduped count > 0. "
            "Cards existed that the local record did not know about. "
            "Guard A may be too loose.",
            flush=True,
        )

    if counts.get("failure", 0):
        print(
            f"reconcile-board: FAILED -- {counts['failure']} run dir(s) raised "
            f"an unexpected error while being classified/reconciled (see "
            f"'FAILED:' lines above) -- this is NOT a pass",
            flush=True,
        )
        return EXIT_SWEEP_HAD_FAILURES

    return EXIT_OK
