"""Stall watchdog -- scans run directories, reports on jobs whose heartbeat is stale,
and when --enforce is passed, marks the CC board card as blocked via cc_board.patch_phase().

Findings are appended to a separate watchdog-findings.jsonl and a summary notification
is dispatched via PRESENTATION_NOTIFY_CMD when configured. With --enforce, each stalled
run's task_id is resolved from state.json (board.task_id) and process_manifest.json
(cc_task_id), and cc_board.patch_phase(run_dir, task_id, phase_id, "blocked", reason)
is called -- fail-soft, never blocking the scan.

Staging (Rule 3.5 -- warn-mode before fail-closed):
  stage 1 (original unit): report, exit 0.  Run it for one week against real runs.
  stage 2 (drive to zero) : U014 lands the in-loop checkpoint; false alarms go to zero.
  stage 3 (flip / WI-04a fix): --enforce is wired in the launchd script; a stall
    exits 5 AND marks the CC card as blocked.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

from .result import CheckResult
from .state import _read_json, EXIT_OK, EXIT_STALLED, EXIT_WATCHDOG_NO_RUNS
from .manifest import (
    PHASE_BUDGET_MINUTES, DEFAULT_PHASE_BUDGET_MINUTES, MAX_HEARTBEAT_INTERVAL_MINUTES,
)


def _find_state_files(scan_root: Path, depth: int):
    """Bounded walk -- NOT rglob, which can stall for minutes on a large tree."""
    seen: Set[Path] = set()
    for d in range(1, depth + 1):
        for state_path in scan_root.glob("/".join(["*"] * d) + "/state.json"):
            resolved = state_path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield state_path


def _find_state_files_multi(scan_roots, depth: int):
    """Bounded walk across MULTIPLE roots (run-root-agnostic, 2026-08-27).

    DOCTRINE (binding): the roots are the union of everywhere the caller says
    runs may live; a run found under any root is checked, and absence in every
    root is NOT proof a run does not exist (callers keep scanned == 0 as
    UNDETERMINED, EXIT_WATCHDOG_NO_RUNS). Dedup across roots; an unreadable
    root contributes nothing and never ends the scan."""
    seen: Set[Path] = set()
    for root in scan_roots:
        try:
            for state_path in _find_state_files(root, depth):
                try:
                    resolved = state_path.resolve()
                except OSError:
                    resolved = state_path
                if resolved not in seen:
                    seen.add(resolved)
                    yield state_path
        except OSError:
            # Unreadable root -- fail-soft, never fatal to the other roots.
            continue


def watchdog(
    scan_root,
    grace_multiplier: float = 1.5,
    scan_depth: int = 3,
    enforce: bool = False,
) -> int:
    """Scan run directories under one root (Path) or several roots (list of
    Path) for stalled jobs.

    Returns EXIT_WATCHDOG_NO_RUNS (13) whenever scanned == 0 -- UNDETERMINED,
    regardless of --enforce. Zero state.json files found is not the same claim
    as "found jobs and none are stalled"; a wrong --scan-root, an unmounted
    volume, or a path typo must never read the same as a healthy fleet. And
    since 2026-08-27 (run-root-agnostic doctrine): absence inside every
    scanned root is NEVER proof a run does not exist -- a run may live outside
    every configured root (this box: ~/webinar-decks/<client>/<deck>/<date>),
    so scanned == 0 must never block, heal, fail, or alarm on its own. See
    state.py's EXIT_WATCHDOG_NO_RUNS comment and result.py's CheckResult
    doctrine (health report: unknown is reported as unknown, never as healthy).
    Returns EXIT_STALLED (5) when enforce=True, scanned > 0, and stalls are found.
    Returns EXIT_OK (0) otherwise (warn-mode stage 1, or enforce with zero stalls).
    """
    roots = list(scan_root) if isinstance(scan_root, (list, tuple)) else [scan_root]
    findings: list = []
    scanned = 0
    skipped_terminal = 0
    skipped_no_heartbeat = 0
    skipped_bad_timestamp = 0
    healthy = 0

    for state_path in _find_state_files_multi(roots, scan_depth):
        scanned += 1
        st = _read_json(state_path)
        if not st:
            skipped_bad_timestamp += 1
            continue
        if st.get("terminal") in ("DONE", "BLOCKED"):
            skipped_terminal += 1
            continue
        hb = st.get("heartbeat") or {}
        last = hb.get("last_checkpoint_at")
        pid = hb.get("current_phase") or st.get("current_phase") or "?"
        if not last:
            skipped_no_heartbeat += 1
            continue
        try:
            age_min = (datetime.now(timezone.utc) -
                       datetime.fromisoformat(last).astimezone(timezone.utc)).total_seconds() / 60
        except (ValueError, TypeError):
            skipped_bad_timestamp += 1
            continue

        interval = hb.get("interval_minutes")
        source = hb.get("interval_source") or "state"
        # HARDEN G3 + per-phase follow-up: reject not just <=0 but anything past THIS
        # phase's own ceiling -- min(MAX_HEARTBEAT_INTERVAL_MINUTES, that phase's
        # PHASE_BUDGET_MINUTES entry), not the flat engine-wide 240 max. The flat max
        # let a 15-minute phase's poisoned/foreign-written interval_minutes:240 sail
        # through unchanged and blind the stall check for that phase alone.
        # Phase.heartbeat_interval_minutes (manifest.py) now refuses an insane value at the
        # source, but the watchdog is read-only (Super Spec 8.3) and must independently distrust
        # whatever it finds on disk -- a state.json written before this fix, or by any other
        # writer, could still carry a poisoned interval_minutes. Without this bound a value like
        # 999999999 sails past `interval <= 0` unchanged and blinds the stall check for millennia.
        phase_ceiling = min(MAX_HEARTBEAT_INTERVAL_MINUTES,
                             PHASE_BUDGET_MINUTES.get(pid, DEFAULT_PHASE_BUDGET_MINUTES))
        if (not isinstance(interval, (int, float)) or isinstance(interval, bool)
                or interval <= 0 or interval > phase_ceiling):
            interval = PHASE_BUDGET_MINUTES.get(pid, DEFAULT_PHASE_BUDGET_MINUTES)
            source = ("budget_table" if pid in PHASE_BUDGET_MINUTES
                      else f"DEFAULT_{DEFAULT_PHASE_BUDGET_MINUTES}min_NO_ENTRY_FOR_{pid}")
        threshold = interval * grace_multiplier
        if age_min > threshold:
            findings.append((state_path.parent, pid, round(age_min, 1),
                             interval, round(threshold, 1), source,
                             st.get("job_id", "?")))
        else:
            healthy += 1

    for run_dir, pid, age, interval, threshold, source, job_id in findings:
        print(f"STALLED {run_dir}: phase {pid} last checkpointed {age} min ago "
              f"(threshold {threshold} min = interval {interval} x grace {grace_multiplier}; "
              f"interval source: {source})", flush=True)

    n_stalled = len(findings)
    if scanned == 0:
        roots_str = ", ".join(str(r) for r in roots)
        print("watchdog: NO state.json found under any of "
              f"[{roots_str}] -- check --scan-root / PRESENTATION_SCAN_ROOTS "
              "and --scan-depth -- UNDETERMINED, exiting EXIT_WATCHDOG_NO_RUNS "
              "(13), NOT a clean pass -- absence inside the scanned root(s) is "
              "never proof a run does not exist",
              flush=True)
    else:
        print(f"watchdog: scanned {scanned} state file(s) under "
              f"{', '.join(str(r) for r in roots)} "
              f"(depth {scan_depth}); {skipped_terminal} terminal, {skipped_no_heartbeat} "
              f"without a heartbeat, {skipped_bad_timestamp} with an unreadable timestamp, "
              f"{healthy} healthy, {n_stalled} stalled", flush=True)

    # Findings land beside the first root that actually exists (multi-root,
    # 2026-08-27): roots[0] may be missing while runs were found under a later
    # root, and open(..., "a") would then crash the whole scan on a missing dir.
    findings_path = None
    for _root in roots:
        try:
            if _root.is_dir():
                findings_path = _root / "watchdog-findings.jsonl"
                break
        except OSError:
            continue
    if findings_path is None and findings:
        print("watchdog: no scannable root dir exists -- stall findings kept to "
              "stdout only (no watchdog-findings.jsonl written)", flush=True)
    if findings_path is not None:
        for run_dir, pid, age, interval, threshold, source, job_id in findings:
            line = json.dumps({
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "run_dir": str(run_dir),
                "phase": pid,
                "age_minutes": age,
                "threshold_minutes": threshold,
                "interval_minutes": interval,
                "interval_source": source,
                "job_id": job_id,
            }, ensure_ascii=False)
            with open(findings_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    if findings and os.environ.get("PRESENTATION_NOTIFY_CMD"):
        lines = []
        for run_dir, pid, age, interval, threshold, source, job_id in findings:
            lines.append(
                f"- {job_id}: {pid} at {age} min (threshold {threshold} min, "
                f"interval source: {source})"
            )
        msg = (
            f"Watchdog: {n_stalled} stalled job(s) in {', '.join(str(r) for r in roots)}\n"
            + "\n".join(lines)
        )
        from .report import dispatch
        dispatch("watchdog", "stall", msg)

    # WI-04a fix: when --enforce is on, mark each stalled job's CC card as blocked.
    # Resolve the task_id from state.json (board.task_id) first, then fall back to
    # process_manifest.json (cc_task_id). Each call is fail-soft -- a board error
    # never stops the scan of the remaining stalled jobs.
    blocked_count = 0
    if enforce and findings:
        try:
            import cc_board as _ccb
        except ImportError:
            _ccb = None
        _cfg = _ccb.board_config(os.environ) if _ccb else None
        if _cfg is not None:
            for run_dir, pid, age, interval, threshold, source, job_id in findings:
                task_id = None
                # 1) state.json -> board.task_id (the canonical source after open_card)
                st = _read_json(run_dir / "state.json")
                if st and isinstance(st, dict):
                    task_id = (st.get("board") or {}).get("task_id")
                # 2) process_manifest.json -> cc_task_id (the fallback)
                if not task_id:
                    try:
                        tm = _ccb._read_manifest(run_dir) if _ccb else {}
                        task_id = tm.get("cc_task_id") if isinstance(tm, dict) else None
                    except Exception:
                        task_id = None
                if task_id:
                    reason = (
                        f"Watchdog: heartbeat stale -- phase {pid} last checkpointed "
                        f"{age} min ago (threshold {threshold} min)"
                    )
                    _ccb.patch_phase(
                        run_dir, str(task_id), str(pid), "blocked", reason, env=os.environ
                    )
                    blocked_count += 1
        if blocked_count:
            print(f"watchdog: enforce -- issued {blocked_count} blocked patch(es)", flush=True)
        elif _cfg is None:
            print("watchdog: enforce -- board disabled (COMMAND_CENTER_URL/MISSION_CONTROL_URL "
                  "unset); no blocked patches issued", flush=True)
        elif not findings:
            print("watchdog: enforce -- no stalls found, no blocked patches issued", flush=True)
        else:
            print("watchdog: enforce -- no task_ids resolved; no blocked patches issued",
                  flush=True)

    if enforce and findings:
        print(f"watchdog: enforce={enforce} n_stalled={n_stalled} blocked_count={blocked_count}",
              flush=True)

    # B5 fix: `scanned == 0` is UNDETERMINED, not a pass, and NOT the same
    # exit code as "scanned N, 0 stalled" -- even under --enforce, where the
    # old code's `EXIT_STALLED if (enforce and findings) else EXIT_OK` made
    # scanned=0 (findings == []) indistinguishable from a genuinely healthy
    # fleet. This branch is checked first and wins regardless of enforce,
    # mirroring EXIT_SWEEP_NO_RUNS in sweep.py (unconditional on --apply).
    scan_result = (
        CheckResult.UNDETERMINED if scanned == 0
        else (CheckResult.FAIL if findings else CheckResult.PASS)
    )
    if scan_result is CheckResult.UNDETERMINED:
        return EXIT_WATCHDOG_NO_RUNS
    return EXIT_STALLED if (enforce and scan_result is CheckResult.FAIL) else EXIT_OK
