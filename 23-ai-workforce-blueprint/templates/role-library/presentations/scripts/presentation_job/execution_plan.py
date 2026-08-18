#!/usr/bin/env python3
"""execution_plan.py -- build the phase-execution plan from the manifest (MASTER-SPEC FILE 9).

Turns PIPELINE-MANIFEST.json into a wave-scheduled execution plan:

  * load_phase_dag(manifest_path) -- phases as DAG nodes, edges from phase order
    and artifact dependencies (produces_artifact consumed by later phases).
  * topological_sort (Kahn's algorithm) -- a phase never runs before its
    dependencies; the manifest's `order` values provide the deterministic
    tie-break so the sort is stable across runs.
  * cap_wave_width -- each wave is bounded by the MEASURED capacity of THIS
    client's account (capacity.probe()), never by a constant.
  * build_execution_plan(manifest_path, capacity_probe) -- the full plan.
  * main() -- CLI entry; calls capacity.probe() and prints
    'Execution plan: N waves' (plus the wave breakdown). Exit 0.

WAVE WIDTH IS MEASURED, NOT DECLARED (unit u07)
-----------------------------------------------
This module used to clamp every wave to a hard-coded 16 (one operator's
subagents-per-workflow directive) and to fall back to that same 16 whenever the
capacity probe was unavailable. Both are ways of dispatching a number nobody
measured: on an Ollama-Cloud-$20 box, 16 is five times the account's real
ceiling. The width of each wave is now

    min(number of phases READY in this wave, capacity.probe() available)

and a plan can no longer be built at all without a measurement -- an absent or
unmeasurable probe raises CapacityUnmeasured (AF-CAPACITY-UNMEASURED) instead of
silently substituting a constant. The Kahn dependency logic below is unchanged;
only the width is.

Import as package-relative. Standalone run: `python3 -m presentation_job.execution_plan
--manifest <path>` or `python3 presentation_job/execution_plan.py --manifest <path>`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .state import EXIT_OK, EXIT_USAGE, EXIT_GATE_BLOCKED  # package-relative
except ImportError:
    from state import EXIT_OK, EXIT_USAGE, EXIT_GATE_BLOCKED  # direct file run

try:
    from .capacity import (AUTOFAIL_CODE, UNBOUNDED, CapacityUnmeasured,
                           autofail_payload, is_unbounded, refusal_message,
                           require_available)
except ImportError:  # direct file run from scripts/
    from capacity import (AUTOFAIL_CODE, UNBOUNDED, CapacityUnmeasured,
                          autofail_payload, is_unbounded, refusal_message,
                          require_available)


# ---------------------------------------------------------------------------
# DAG construction
# ---------------------------------------------------------------------------
def _load_raw_phases(manifest_path: str | Path) -> List[dict]:
    """Read phases straight off the manifest JSON.

    Deliberately does NOT go through presentation_job.manifest.Manifest:
    that module is a live-edited unit boundary (U01) and must not become a
    dependency of the plan builder. Manifest freshness is enforced by the
    engine and by manifest_assert.py -- the plan only needs the DAG shape."""
    path = Path(manifest_path)
    if not path.is_file():
        raise FileNotFoundError(f"manifest not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"cannot parse manifest {path}: {exc}") from exc
    phases = raw.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError(f"manifest {path} has no phases list")
    return phases


def load_phase_dag(manifest_path: str | Path) -> Dict[str, List[str]]:
    """Load the manifest's phases as an adjacency map: phase_id -> [dependents].

    Edges come from the manifest `order` field: a phase depends on the phases
    with a lower order in the same family (first segment of the phase id) and
    on the previous phase of the same owning role. This yields a deterministic,
    acyclic dependency graph that follows the manifest's own pipeline sequence.

    The returned map is the Kahn-adjacency: keys are phase ids, values are the
    phases that depend on them. Phases with no dependents have an empty list.
    """
    phases = _load_raw_phases(manifest_path)
    nodes: Dict[str, List[str]] = {}
    by_id: Dict[str, dict] = {}
    for p in phases:
        pid = p.get("id")
        if not isinstance(pid, str) or not pid:
            raise ValueError(f"phase without a string id in {manifest_path}")
        nodes[pid] = []
        by_id[pid] = p

    ordered = sorted(by_id.items(), key=lambda kv: (float(kv[1].get("order", 0)), kv[0]))
    for idx, (pid, ph) in enumerate(ordered):
        role = ph.get("owning_role") or ""
        family = pid.split("-")[0]
        for (qid, qh) in ordered[:idx]:
            same_role = (qh.get("owning_role") or "") == role and role
            same_family = qid.split("-")[0] == family
            if same_role or same_family:
                nodes[qid].append(pid)

    # De-duplicate edges (a pair may be added by both rules).
    for pid in nodes:
        nodes[pid] = list(dict.fromkeys(nodes[pid]))
    return nodes


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------
def topological_sort(dag: Dict[str, List[str]]) -> List[str]:
    """Kahn's algorithm over the phase DAG.

    Returns the phases in dependency order (a deterministic topological
    ordering). Raises ValueError on a cycle. Independent phases are ordered
    by their manifest order (tie-break on the id) so the output is stable.
    """
    indegree: Dict[str, int] = {pid: 0 for pid in dag}
    for pid, deps in dag.items():
        for dep in deps:
            indegree[dep] = indegree.get(dep, 0) + 1

    # Stable: process ready nodes in sorted order so independent phases come
    # out in manifest-order sequence, not in dict-insertion order.
    ready = deque(sorted(pid for pid, deg in indegree.items() if deg == 0))
    order: List[str] = []
    while ready:
        pid = ready.popleft()
        order.append(pid)
        for dep in sorted(dag.get(pid, [])):
            indegree[dep] -= 1
            if indegree[dep] == 0:
                ready.append(dep)
    if len(order) != len(dag):
        cycle = [pid for pid, deg in indegree.items() if deg > 0]
        raise ValueError(f"cycle detected in phase DAG involving: {sorted(cycle)}")
    return order


# ---------------------------------------------------------------------------
# Wave scheduling
# ---------------------------------------------------------------------------
def cap_wave_width(available, ready_items: Optional[int] = None) -> int:
    """The width of ONE wave: min(ready_items, available). No constant involved.

    `available` is the measured ceiling of THIS client's account
    (capacity.probe()['available']) -- a positive int, or the UNBOUNDED
    sentinel for a bring-your-own-key provider with no structural ceiling
    (operator ruling fix/capacity-uncap-byok: "do not limit someone who
    brought their own capacity"). There is deliberately no fallback: an
    unmeasured capacity (`None`) raises CapacityUnmeasured rather than
    substituting a number, because the substituted number is exactly the
    defect this unit exists to remove. `ready_items` is how many phases have
    all their dependencies satisfied right now; when omitted the width is the
    measured ceiling alone.

    UNBOUNDED never becomes the literal wave width: `min(ready_items,
    UNBOUNDED)` always evaluates to `ready_items` (see capacity._Unbounded's
    comparison contract), so a provider with no cap still only dispatches as
    many agents as there is READY work for -- "no cap on the account" is not
    "no bound on one wave". Calling with `ready_items=None` while `available`
    is UNBOUNDED has no ready-item count to bound against, so it raises
    CapacityUnmeasured rather than ever returning an unbounded "width".
    """
    if available is None:
        raise CapacityUnmeasured(
            f"{AUTOFAIL_CODE}: wave width needs a measured capacity, got "
            f"available={available!r}"
        )
    if not is_unbounded(available):
        if isinstance(available, bool) or not isinstance(available, int):
            raise CapacityUnmeasured(
                f"{AUTOFAIL_CODE}: wave width needs a measured capacity, got "
                f"available={available!r}"
            )
        if available < 1:
            raise CapacityUnmeasured(
                f"{AUTOFAIL_CODE}: measured capacity {available} is not dispatchable"
            )
    if ready_items is None:
        if is_unbounded(available):
            raise CapacityUnmeasured(
                f"{AUTOFAIL_CODE}: capacity is UNBOUNDED (bring-your-own-key provider, "
                f"no structural ceiling) -- wave width can only be computed against a "
                f"concrete ready-item count, and is never itself reported as unbounded"
            )
        return available
    return max(1, min(int(ready_items), available))


def _wave_schedule_dag(dag: Dict[str, List[str]], available: int) -> List[List[str]]:
    """Level-scheduled waves: each wave is min(ready, available) phases wide.

    Same Kahn mechanics as topological_sort (indegree bookkeeping, ready set
    processed in sorted order for determinism) -- the DEPENDENCY logic is
    untouched. The only new thing is that the ready set is truncated to the
    measured capacity, and whatever does not fit stays ready for the next wave.
    This replaces the old fixed-width slice of the topological order, which
    could not tell a phase that was READY from one that merely came next.

    With 5 mutually independent phases and available=3 this yields waves of
    3 then 2: the width is driven by the probe, not by a constant.
    """
    indegree: Dict[str, int] = {pid: 0 for pid in dag}
    for pid, deps in dag.items():
        for dep in deps:
            indegree[dep] = indegree.get(dep, 0) + 1

    ready = sorted(pid for pid, deg in indegree.items() if deg == 0)
    waves: List[List[str]] = []
    scheduled = 0
    while ready:
        width = cap_wave_width(available, len(ready))
        wave = ready[:width]
        carried = ready[width:]
        waves.append(wave)
        scheduled += len(wave)
        newly_ready: List[str] = []
        for pid in wave:
            for dep in sorted(dag.get(pid, [])):
                indegree[dep] -= 1
                if indegree[dep] == 0:
                    newly_ready.append(dep)
        ready = sorted(carried + newly_ready)
    if scheduled != len(dag):
        stuck = [pid for pid, deg in indegree.items() if deg > 0]
        raise ValueError(f"cycle detected in phase DAG involving: {sorted(stuck)}")
    return waves


# ---------------------------------------------------------------------------
# Plan builder + report
# ---------------------------------------------------------------------------
def build_execution_plan(manifest_path: str | Path, capacity_probe: Optional[dict] = None) -> dict:
    """Build the execution plan: DAG, topological order, waves, width.

    Args:
        manifest_path: path to PIPELINE-MANIFEST.json
        capacity_probe: result of capacity.probe() (dict). REQUIRED -- passing
            None (or a probe that could not produce a number) raises
            CapacityUnmeasured. There is no constant to fall back to.

    Returns:
        dict with keys: manifest_path, manifest_version, phase_count,
        order (list), waves (list of lists), wave_width, wave_widths,
        dispatchable, available, capacity_probe_mode, capacity_status,
        capacity_provider, capacity_plan.

    Raises:
        CapacityUnmeasured: the probe produced no dispatchable number.
    """
    if capacity_probe is None:
        raise CapacityUnmeasured(
            f"{AUTOFAIL_CODE}: build_execution_plan requires a capacity probe result; "
            f"a plan built without one would dispatch a width nobody measured"
        )
    available = require_available(capacity_probe)

    dag = load_phase_dag(manifest_path)
    order = topological_sort(dag)
    raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    manifest_version = raw.get("manifest_version")

    dispatchable = capacity_probe.get("dispatchable")
    if not isinstance(dispatchable, int) or isinstance(dispatchable, bool):
        dispatchable = available
    probe_mode = str(capacity_probe.get("probe_mode") or "live")

    waves = _wave_schedule_dag(dag, available)
    return {
        "manifest_path": str(Path(manifest_path).resolve()),
        "manifest_version": manifest_version,
        "phase_count": len(order),
        "order": order,
        "waves": waves,
        "wave_width": available,
        "wave_widths": [len(w) for w in waves],
        "dispatchable": dispatchable,
        "available": available,
        "capacity_probe_mode": probe_mode,
        "capacity_status": capacity_probe.get("status"),
        "capacity_provider": capacity_probe.get("provider"),
        "capacity_plan": capacity_probe.get("plan"),
    }


def format_plan_report(plan: dict) -> str:
    """Human-readable plan report."""
    lines = [
        "EXECUTION PLAN -- Presentations department (MASTER-SPEC FILE 9)",
        f"Manifest: {plan['manifest_path']} (v{plan['manifest_version']}, "
        f"{plan['phase_count']} phases)",
        f"Capacity probe: {plan['capacity_probe_mode']} -- status "
        f"{plan.get('capacity_status')}, provider {plan.get('capacity_provider')}, "
        f"plan {plan.get('capacity_plan')}, dispatchable {plan['dispatchable']}, "
        f"available {plan['available']}",
        f"Wave width: min(ready phases, measured available {plan['wave_width']}) "
        f"-> per-wave widths {plan.get('wave_widths')}",
        f"Execution plan: {len(plan['waves'])} waves",
    ]
    for i, wave in enumerate(plan["waves"], 1):
        lines.append(f"  wave {i:>2}: " + ", ".join(wave))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="execution_plan.py",
        description="Build the wave-scheduled execution plan from PIPELINE-MANIFEST.json "
                    "(MASTER-SPEC FILE 9).",
    )
    p.add_argument("--manifest", required=True,
                   help="path to PIPELINE-MANIFEST.json")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not Path(args.manifest).is_file():
        print(f"execution_plan: manifest not found: {args.manifest}", file=sys.stderr)
        return EXIT_USAGE
    try:
        from . import capacity  # package-relative (python3 -m)
    except ImportError:
        import capacity  # direct file run from scripts/
    probe = capacity.probe()
    try:
        plan = build_execution_plan(args.manifest, probe)
    except CapacityUnmeasured:
        # No degradation to a constant. A plan whose width nobody measured is
        # the defect, not the recovery.
        print(f"execution_plan: {refusal_message(probe)}", file=sys.stderr)
        print(json.dumps(autofail_payload(probe), indent=2), file=sys.stderr)
        return EXIT_GATE_BLOCKED
    print(format_plan_report(plan), flush=True)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
