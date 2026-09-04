#!/usr/bin/env python3
"""execution_plan.py -- build the phase-execution plan from the manifest (MASTER-SPEC FILE 9).

Turns PIPELINE-MANIFEST.json into a wave-scheduled execution plan:

  * build_edges(phases) -- the artifact DAG: edge u->v iff produces(u) intersects
    consumes(v), which is how a phase that needs a file waits for the phase
    that makes it. Consumed artifact patterns with no producer at all that are
    not intake files are a manifest defect (static validation: find_unproduced_
    consumed_artifacts / the ValueError raised by load_phase_dag). Intake files
    (raw/source-brief.* and the intake record working/copy/intake.json while it
    is still being rewritten by the intake stages) carry no edges: they are the
    run's inputs, present before the engine starts. Manifest `order` only
    orders phases INTRA-STAGE (deterministic tie-break), it no longer creates
    cross-phase edges.
  * load_phase_dag(manifest_path) -- phases as DAG nodes, edges from the
    artifact graph above (replaces the old name-prefix/role edges, which put
    P8.2-GUIDE and P9-SPEECH in wave one and let P-0.5-RESEARCH wait for a
    phase that runs after it: MASTER Part 8 FIX 8).
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
import fnmatch
import json
import re
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


def _as_artifact_list(value) -> List[str]:
    """Normalize produces_artifact / consumes to a list of pattern strings.

    The manifest declares produces_artifact as either a single string or a
    list of strings (consumes is always a list); both shapes are accepted,
    and a missing field is an empty list. Nothing else is coerced -- a
    non-string entry is skipped, never guessed.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v]
    return []


def _patterns_match(producer_pattern: str, consumed_pattern: str) -> bool:
    """True when a produced artifact satisfies a consumed artifact pattern.

    Exact match, or a glob match in either direction (the producer may declare
    the concrete path while the consumer declares a wildcard -- e.g. producer
    'working/deliverables/PRESENTER-GUIDE.pdf' matching the consumer's glob, or
    producer 'working/research/brief-*.md' matching the consumer's exact same
    glob). fnmatch on the full pattern string in both directions covers both."
    """
    if producer_pattern == consumed_pattern:
        return True
    return (fnmatch.fnmatch(producer_pattern, consumed_pattern)
            or fnmatch.fnmatch(consumed_pattern, producer_pattern))


_RAW_INTAKE_RE = re.compile(r"^raw/")
_INTAKE_RECORD = "working/copy/intake.json"


def _is_intake_file(pattern: str) -> bool:
    """True when the consumed pattern names a run input, not a produced file.

    Two classes are intake (FIX 8, MASTER Part 8):
      * raw/source-brief.* -- the client's source material; no phase produces
        it, so it can never be an edge source and must not trip validation.
      * working/copy/intake.json -- the intake record. It is written by the
        intake stages (P-CONVERTER / P0A-INTAKE / P-SP-CLAIM rewrite it: a
        same-artifact producing stage), so any consumer whose manifest order
        is at or before the record's LAST producer treats it as run input
        (already on disk when the engine starts; the intake driver writes it
        before the run). The freshness rule lives in build_edges."""
    if _RAW_INTAKE_RE.match(pattern):
        return True
    return _patterns_match(pattern, _INTAKE_RECORD)


def _phase_order(phase: dict) -> float:
    try:
        return float(phase.get("order", 0))
    except (TypeError, ValueError):
        return 0.0


def find_unproduced_consumed_artifacts(phases: List[dict]) -> List[str]:
    """Static validation (FIX 8): consumed patterns no phase produces.

    Returns the list of consumed artifact patterns that have NO producer in
    the same manifest and are NOT intake files (raw/*, intake record still in
    its producing stage). A consumer that reads a file nobody makes can never
    succeed -- the manifest declares a dead edge and the defect is in the
    manifest, not the engine. Empty list means every consumed artifact has a
    producer or is a run input. Callers (manifest.load()'s static check,
    the --plan command line) raise their own error type naming these.
    """
    producers: List[str] = []
    for p in phases:
        producers.extend(_as_artifact_list(p.get("produces_artifact")))
    orphans: List[str] = []
    seen: set = set()
    for p in phases:
        for cpat in _as_artifact_list(p.get("consumes")):
            if cpat in seen:
                continue
            if _is_intake_file(cpat):
                continue
            if any(_patterns_match(pp, cpat) for pp in producers):
                continue
            seen.add(cpat)
            orphans.append(cpat)
    return orphans


def build_edges(phases: List[dict]) -> Dict[str, List[str]]:
    """The artifact DAG: edge u -> v iff produces(u) intersects consumes(v).

    MASTER Part 8 FIX 8 replaces the old name-prefix/role edges with
    produces->consumes edges, so a phase that needs a file waits for the phase
    that makes it -- P8.2-GUIDE (consumes *-FINAL.pptx) can no longer sit in
    wave one ahead of P8-ASSEMBLE, and P9-SPEECH (consumes slides_copy.md)
    waits for P4-COPY instead of running in wave one.

    Rules, in order of application per consumed pattern:

      1. Intake files carry no edges (see _is_intake_file).
      2. Same-artifact stage rule: a phase that itself produces a pattern
         matching the consumed pattern belongs to that artifact's producing
         stage and takes no edge from other producers of the same artifact
         (P-SP-CLAIM produces and consumes intake.json -- the claim router is
         part of the intake stage, not a downstream of it).
      3. Intake-record freshness: for consumers of working/copy/intake.json
         whose order is at or before the record's last producer's order, the
         record is a run input and the pattern is skipped (the intake driver
         writes it before the engine starts); consumers ordered AFTER the
         record's last rewrite take edges from its producers (P0B-PRIORITY
         needs the priority_shift answers the rewrite merged in).
      4. Otherwise: any producer u's pattern matching the consumed pattern
         yields edge u -> v (u != v). A consumed pattern with NO producer and
         no intake exemption is a manifest defect -- load_phase_dag raises
         ValueError naming it via find_unproduced_consumed_artifacts.

    The manifest's `order` values no longer create cross-phase edges (that was
    the prefix-collapse defect: every id shares the 'P' segment, so every
    phase "depended" on every earlier phase and the true artifact order was
    ignored); order remains the deterministic tie-break within a wave and, in
    build_edges, the freshness threshold above.

    Returns Kahn-adjacency: keys are phase ids, values are the phases that
    depend on them; a phase with no dependents has an empty list.
    """
    nodes: Dict[str, List[str]] = {}
    by_id: Dict[str, dict] = {}
    for p in phases:
        pid = p.get("id")
        if not isinstance(pid, str) or not pid:
            raise ValueError(f"phase without a string id")
        nodes[pid] = []
        by_id[pid] = p

    producers: List[tuple] = [  # (pattern, phase_id)
        (pat, pid) for pid, p in by_id.items()
        for pat in _as_artifact_list(p.get("produces_artifact"))
    ]

    def _last_producer_order(consumed: str, exclude: Optional[str] = None):
        latest: Optional[float] = None
        for ppat, pid in producers:
            if pid == exclude:
                continue
            if not _patterns_match(ppat, consumed):
                continue
            o = _phase_order(by_id[pid])
            if latest is None or o > latest:
                latest = o
        return latest

    for vp in phases:
        vid = vp["id"]
        own_produces = _as_artifact_list(vp.get("produces_artifact"))
        for cpat in _as_artifact_list(vp.get("consumes")):
            if _is_intake_file(cpat):
                if _patterns_match(cpat, _INTAKE_RECORD):
                    # Freshness rule: only consumers ordered AFTER the last
                    # producer of the record depend on it (rule 3).
                    latest = _last_producer_order(cpat, exclude=vid)
                    if latest is not None and _phase_order(vp) <= latest:
                        continue
                    # Fall through: records past the intake stage are real
                    # dependencies of their latest producer.
                else:
                    continue
            if any(_patterns_match(own, cpat) for own in own_produces):
                # Rule 2: same-artifact producing stage.
                continue
            for ppat, pid in producers:
                if pid == vid:
                    continue
                if not _patterns_match(ppat, cpat):
                    continue
                if vid not in nodes[pid]:
                    nodes[pid].append(vid)

    # De-duplicate edges (a pair may be reached by several matching patterns).
    for pid in nodes:
        nodes[pid] = list(dict.fromkeys(nodes[pid]))
    return nodes


def load_phase_dag(manifest_path: str | Path) -> Dict[str, List[str]]:
    """Load the manifest's phases as an adjacency map: phase_id -> [dependents].

    The DAG is the ARTIFACT graph (build_edges): u -> v exactly when
    produces(u) intersects consumes(v), with intake files exempt and the
    same-artifact producing-stage rule applied. This is FIX 8's replacement
    for the old order/name-prefix edges, which collapsed every id onto the
    same family segment ('P') and let P8.2-GUIDE / P9-SPEECH join wave one.

    The returned map is the Kahn-adjacency: keys are phase ids, values are the
    phases that depend on them. Phases with no dependents have an empty list.

    Orphaned consumed artifacts (a consumed pattern no phase produces that is
    not an intake file) do not produce edges -- they are declared by the
    manifest as pre-existing inputs and are surfaced by the reporting surface
    (find_unproduced_consumed_artifacts) so Manifest.load can raise
    ManifestInvalid on them without the plan-builder itself refusing a
    manifest it can still schedule.
    """
    phases = _load_raw_phases(manifest_path)
    return build_edges(phases)


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------
def topological_sort(dag: Dict[str, List[str]]) -> List[str]:
    """Kahn's algorithm over the phase DAG.

    Returns the phases in dependency order (a deterministic topological
    ordering). Raises ValueError on a cycle. Independent phases are ordered
    by their manifest order (tie-break on the id) so the output is stable.
    (FIX 8: the dag passed in is the artifact graph from build_edges; the
    manifest `order` values are only the deterministic tie-break here, never
    themselves a source of edges.)
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
