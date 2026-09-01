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
from .scan_roots import (
    default_config_path, format_roots_report, ok_roots, resolve_scan_roots,
    split_primary, undetermined_roots,
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


def _find_state_files_multi(roots, depth: int):
    """_find_state_files across every readable root, de-duplicated globally.

    A run dir reachable from two configured roots (an additional root nested
    under the department tree, say) is scanned once, not twice."""
    seen: Set[Path] = set()
    for root in roots:
        for state_path in _find_state_files(root.path, depth):
            resolved = state_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield root, state_path


def watchdog(
    scan_root: Path,
    grace_multiplier: float = 1.5,
    scan_depth: int = 3,
    enforce: bool = False,
    extra_roots=(),
    roots_config=None,
    env=None,
) -> int:
    # run-root-agnostic back-compat: a LIST/tuple passed as scan_root means
    # "these are the roots" (test contract, 2026-08-27); first is primary.
    if isinstance(scan_root, (list, tuple)):
        roots = [Path(r) for r in scan_root]
        scan_root, extra_roots = roots[0], list(roots[1:]) + list(extra_roots)

    """Scan run directories under every configured scan root for stalled jobs.

    scan_root is the PRIMARY root: it owns watchdog-findings.jsonl and heads the
    root list. Additional roots come from extra_roots (CLI), the
    PRESENTATION_SCAN_ROOTS env var, and roots_config -- see scan_roots.py for
    why a single root was the 2026-08-27 blind spot. Every pass logs the roots it
    actually searched, so a future missing root shows up in the findings log
    instead of looking like a clean scan.

    Returns EXIT_WATCHDOG_NO_RUNS (13) whenever scanned == 0 -- UNDETERMINED,
    regardless of --enforce. Zero state.json files found is not the same claim
    as "found jobs and none are stalled"; a wrong --scan-root, an unmounted
    volume, or a path typo must never read the same as a healthy fleet. See
    state.py's EXIT_WATCHDOG_NO_RUNS comment and result.py's CheckResult
    doctrine (health report: unknown is reported as unknown, never as healthy).
    Returns EXIT_STALLED (5) when enforce=True, scanned > 0, and stalls are found.
    Returns EXIT_OK (0) otherwise (warn-mode stage 1, or enforce with zero stalls).

    A root that cannot be read never changes the verdict on any run: it is logged
    as UNDETERMINED and disqualifies the pass from claiming completeness. It
    never causes a deck to be blocked, healed, or failed -- absence from a scan
    this pass could not perform is not evidence about that deck at all.
    """
    if roots_config is None:
        # Default config location: <department>/config/scan-roots.conf beside the
        # scripts dir. Same default run_discovery.py uses; a box adds roots by
        # writing that file, no code change.
        roots_config = default_config_path(Path(__file__).resolve().parent.parent)
    roots = resolve_scan_roots(
        primary=scan_root, extra=extra_roots, env=env, config_path=roots_config,
    )
    # Findings/audit owner: the FIRST chunk of the primary root. For a
    # single-path --scan-root this is the root itself, exactly as before;
    # for an os.pathsep-packed primary (the live plist's SCAN_ROOT shape)
    # the first chunk -- normally the department tree -- owns the files.
    primary_chunks = split_primary(scan_root)
    findings_owner = primary_chunks[0] if primary_chunks else Path(scan_root)
    readable = ok_roots(roots)
    unreadable = undetermined_roots(roots)
    print(format_roots_report(roots, "watchdog"), flush=True)

    findings: list = []
    scanned = 0
    skipped_terminal = 0
    skipped_no_heartbeat = 0
    skipped_bad_timestamp = 0
    healthy = 0

    for _root, state_path in _find_state_files_multi(readable, scan_depth):
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
    root_list = ", ".join(str(r.path) for r in readable) or "(none readable)"
    if scanned == 0:
        print("watchdog: NO state.json found -- check --scan-root and --scan-depth "
              "-- UNDETERMINED, exiting EXIT_WATCHDOG_NO_RUNS (13), NOT a clean pass",
              flush=True)
        print(f"watchdog: roots searched: {root_list}", flush=True)
    else:
        print(f"watchdog: scanned {scanned} state file(s) under {len(readable)} root(s) "
              f"[{root_list}] (depth {scan_depth}); {skipped_terminal} terminal, "
              f"{skipped_no_heartbeat} without a heartbeat, {skipped_bad_timestamp} with an "
              f"unreadable timestamp, {healthy} healthy, {n_stalled} stalled", flush=True)

    findings_path = findings_owner / "watchdog-findings.jsonl"
    # The findings owner may be an env/arg-supplied root that does not exist
    # yet on a pristine box (or in a hermetic test); the alarm channel must
    # never die because the directory was never created (run-root-agnostic,
    # 2026-08-27).
    try:
        findings_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
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
            # Which forests this pass actually searched. Without this, a findings
            # file can only prove what WAS seen -- the 2026-08-27 incident needed
            # it to prove what could not have been seen.
            "scan_roots": [str(getattr(r, "path", r)) for r in readable],
            "scan_roots_undetermined": [str(getattr(r, "path", r)) for r in unreadable],
        }, ensure_ascii=False)
        with open(findings_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    # Coverage audit: one record on EVERY pass, stalls or not, because a clean
    # pass that searched the wrong forest is exactly the failure that has to
    # become greppable. Deliberately a SIBLING file, not a second record type
    # inside watchdog-findings.jsonl: that file is a homogeneous stream of stalls
    # and the way the 2026-08-27 incident was proved was by counting run_dir
    # values per line across it. Mixing in records with no run_dir would have
    # broken the very analysis this fix exists to make possible.
    audit_path = findings_owner / "watchdog-scan-audit.jsonl"
    try:
        with open(audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "record": "scan_audit",
                "scan_roots": [str(getattr(r, "path", r)) for r in readable],
                "scan_roots_undetermined": [
                    {"path": str(r.path), "origin": r.origin, "detail": r.detail}
                    for r in unreadable
                ],
                "scan_depth": scan_depth,
                "scanned": scanned,
                "stalled": n_stalled,
                "complete": not unreadable,
            }, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"watchdog: WARNING could not append scan audit to {audit_path}: {exc}",
              flush=True)

    if findings and os.environ.get("PRESENTATION_NOTIFY_CMD"):
        lines = []
        for run_dir, pid, age, interval, threshold, source, job_id in findings:
            lines.append(
                f"- {job_id}: {pid} at {age} min (threshold {threshold} min, "
                f"interval source: {source})"
            )
        msg = (
            f"Watchdog: {n_stalled} stalled job(s) in {findings_owner}\n"
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
