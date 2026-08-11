#!/usr/bin/env python3
"""execution_plan.py -- build the phase-execution plan from the manifest (MASTER-SPEC FILE 9).

Turns PIPELINE-MANIFEST.json into a wave-scheduled execution plan:

  * load_phase_dag(manifest_path) -- phases as DAG nodes, edges from phase order
    and artifact dependencies (produces_artifact consumed by later phases).
  * topological_sort (Kahn's algorithm) -- a phase never runs before its
    dependencies; the manifest's `order` values provide the deterministic
    tie-break so the sort is stable across runs.
  * cap_wave_width -- each wave respects the measured capacity (available
    agents) and the 16-subagents-per-workflow doctrine.
  * build_execution_plan(manifest_path, capacity_probe) -- the full plan.
  * main() -- CLI entry; calls capacity.probe() and prints
    'Execution plan: N waves' (plus the wave breakdown). Exit 0.

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
    from .state import EXIT_OK, EXIT_USAGE  # package-relative (python3 -m)
except ImportError:
    from state import EXIT_OK, EXIT_USAGE  # direct file run from scripts/

# Sub-agents each workflow may run in parallel -- the operator directive of
# 2026-08-10, mirrored here so a wave width is never larger than the doctrine
# allows even when the measured capacity is (capacity.py computes
# available = min(harness ceiling, provider ceiling, 30 x 16)).
SUBAGENTS_PER_WORKFLOW = 16


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
def cap_wave_width(available: int) -> int:
    """Cap the wave width at the measured capacity and the per-workflow doctrine.

    width = min(available, SUBAGENTS_PER_WORKFLOW). A wave is one workflow, so
    it can never carry more concurrent phases than the doctrine allows per
    workflow -- even when the harness reports a larger available budget.
    """
    if available is None:
        available = SUBAGENTS_PER_WORKFLOW
    return max(1, min(int(available), SUBAGENTS_PER_WORKFLOW))


def _wave_schedule(order: List[str], width: int) -> List[List[str]]:
    """Greedy wave packing of the topological order, width-limited.

    Within a wave, phases are independent by construction (the topological
    order guarantees no edge between them). Returns waves of phase ids."""
    waves: List[List[str]] = []
    for i in range(0, len(order), width):
        waves.append(order[i:i + width])
    return waves


# ---------------------------------------------------------------------------
# Plan builder + report
# ---------------------------------------------------------------------------
def build_execution_plan(manifest_path: str | Path, capacity_probe: Optional[dict] = None) -> dict:
    """Build the execution plan: DAG, topological order, waves, width.

    Args:
        manifest_path: path to PIPELINE-MANIFEST.json
        capacity_probe: result of capacity.probe() (dict). When None, the
            doctrine width (16) is used.

    Returns:
        dict with keys: manifest_path, manifest_version, phase_count,
        order (list), waves (list of lists), wave_width, dispatchable,
        available, capacity_probe_mode.
    """
    dag = load_phase_dag(manifest_path)
    order = topological_sort(dag)
    raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    manifest_version = raw.get("manifest_version")

    if capacity_probe is None:
        available = SUBAGENTS_PER_WORKFLOW
        dispatchable = SUBAGENTS_PER_WORKFLOW
        probe_mode = "none"
    else:
        available = int(capacity_probe.get("available") or SUBAGENTS_PER_WORKFLOW)
        dispatchable = int(capacity_probe.get("dispatchable") or available)
        probe_mode = str(capacity_probe.get("probe_mode") or "live")

    width = cap_wave_width(available)
    waves = _wave_schedule(order, width)
    return {
        "manifest_path": str(Path(manifest_path).resolve()),
        "manifest_version": manifest_version,
        "phase_count": len(order),
        "order": order,
        "waves": waves,
        "wave_width": width,
        "dispatchable": dispatchable,
        "available": available,
        "capacity_probe_mode": probe_mode,
    }


def format_plan_report(plan: dict) -> str:
    """Human-readable plan report."""
    lines = [
        "EXECUTION PLAN -- Presentations department (MASTER-SPEC FILE 9)",
        f"Manifest: {plan['manifest_path']} (v{plan['manifest_version']}, "
        f"{plan['phase_count']} phases)",
        f"Capacity probe: {plan['capacity_probe_mode']} -- dispatchable "
        f"{plan['dispatchable']}, available {plan['available']}",
        f"Wave width: {plan['wave_width']} (capped by doctrine "
        f"{SUBAGENTS_PER_WORKFLOW} per workflow)",
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
        try:
            from . import capacity  # package-relative (python3 -m)
        except ImportError:
            import capacity  # direct file run from scripts/
        probe = capacity.probe()
    except SystemExit as exc:
        # probe exits 2 on missing settings -- degrade to doctrine width rather
        # than failing the plan; the report states probe_mode=none.
        probe = None
    plan = build_execution_plan(args.manifest, probe)
    print(format_plan_report(plan), flush=True)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
