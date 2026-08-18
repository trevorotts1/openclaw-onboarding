#!/usr/bin/env python3
"""
trust_boundary_report.py — TRUST BOUNDARY, OBSERVABILITY SURFACE ("obs"): the
operator-facing READ side.

SCOPE: this is the ONLY thing in this file -- turn what
trust_boundary_observability.py recorded (a per-run
working/checkpoints/.trust-boundary-shadow.jsonl, or a raw text log an
operator already has) into a report a human can read in one pass: which
gate(s) diverged, what the legacy path said, what RunFacts said, WHY (the
specific fact named in the reason string), and WHERE that judgement came from
(which existing, unmodified function emitted it). It does not decide
anything, does not gate anything, and its own exit code is never consulted by
any build step -- see --strict below for the one deliberate exception, which
is opt-in and documented as unwired.

This file imports ONLY trust_boundary_observability (this builder's own
module) and the stdlib. It does not import runfacts.py, phase_verifiers.py,
verifier_registry.py, or build_deck.py, and it is not imported BY any of
them -- reading a report never has a code path back into a live run.

USAGE
  Single run, human-readable:
    python3 trust_boundary_report.py --run-dir <path>

  Single run, machine-readable:
    python3 trust_boundary_report.py --run-dir <path> --json

  A raw build/CI log that was never routed through capture_stderr /
  run_and_record (e.g. saved off a CI job after the fact):
    python3 trust_boundary_report.py --log-file build.log

  Every run under a parent directory (fleet-style sweep):
    python3 trust_boundary_report.py --scan-root <path>

EXIT CODES
  0  always, by default -- a report that found would-have-blocked events is
     still a SUCCESSFUL report (the report ran; that's exit 0). This mirrors
     the acceptance rule for this pass: nothing built here may block a run,
     and a report CLI whose own exit code someone might one day wire into a
     build step is exactly that risk if it defaults to nonzero-on-findings.
  2  only on --strict AND at least one would-have-blocked observation found.
     --strict is OFF by default and is not called by anything else in this
     repo -- it exists for an operator (or a future, explicitly-opted-in CI
     step) who wants a report-viewer they can also use as a gate later,
     without this file's default behaviour ever being that gate today.
  1  usage error (bad/missing arguments) or a target that could not be read
     at all (distinct from "read fine, found nothing" -- see below).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

import trust_boundary_observability as obs


def _fmt_observation(o: obs.ShadowObservation) -> str:
    lines = []
    if o.kind == obs.DIVERGENCE_PREFIX:
        flag = "WOULD-HAVE-BLOCKED" if o.would_have_blocked else "divergence (non-blocking direction)"
        lines.append(f"  [{flag}] gate={o.gate}")
        lines.append(f"      legacy   : {o.legacy_verdict}  — {o.legacy_reason}")
        lines.append(f"      runfacts : {o.new_verdict}  — {o.new_reason}")
        lines.append(f"      enforcing={o.enforcing}  source={o.source}  at={o.captured_at}")
        if o.run_dir:
            lines.append(f"      run_dir={o.run_dir}")
    elif o.kind == obs.FINDING_PREFIX:
        lines.append(f"  [SEAL-FINDING] {o.detail}")
        lines.append(f"      source={o.source}  at={o.captured_at}")
        if o.run_dir:
            lines.append(f"      run_dir={o.run_dir}")
    elif o.kind == obs.ERROR_PREFIX:
        lines.append(f"  [SHADOW-ERROR] {o.detail}")
        lines.append(f"      source={o.source}  at={o.captured_at}")
    else:
        lines.append(f"  [UNRECOGNISED] {o.raw_line!r}")
    return "\n".join(lines)


def render_text(observations: List[obs.ShadowObservation], label: str) -> str:
    out = [f"=== trust-boundary shadow report: {label} ==="]
    if not observations:
        out.append("  (no TRUST-BOUNDARY-* observations recorded — either a clean run, "
                    "or nothing has been captured yet for this target)")
        return "\n".join(out)

    would_block = [o for o in observations if o.would_have_blocked]
    findings = [o for o in observations if o.kind == obs.FINDING_PREFIX]
    errors = [o for o in observations if o.kind == obs.ERROR_PREFIX]

    out.append(f"  {len(observations)} observation(s) total: "
               f"{len(would_block)} would-have-blocked, "
               f"{len(findings)} seal-finding(s), {len(errors)} shadow-error(s)")
    out.append("")
    for o in observations:
        out.append(_fmt_observation(o))
        out.append("")

    if would_block:
        out.append("SUMMARY: this run was DETECTED as diverging from what a stricter "
                    "(RunFacts) verdict would have decided, on the gate(s) named above. "
                    "Report-only mode means the run PROCEEDED anyway — nothing was blocked. "
                    "The reason string on each finding names the specific fact; the "
                    "`source` line names the exact function that decided it.")
    else:
        out.append("SUMMARY: no would-have-blocked observations recorded for this target — "
                    "a legitimate run, or no shadow check has run against it yet.")
    return "\n".join(out)


def render_json(observations: List[obs.ShadowObservation], label: str) -> str:
    would_block = [o for o in observations if o.would_have_blocked]
    payload = {
        "label": label,
        "total": len(observations),
        "would_have_blocked_count": len(would_block),
        "observations": [o.to_json() for o in observations],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _run_dirs_under(scan_root: Path) -> List[Path]:
    found = []
    pattern = str(obs.SHADOW_LOG_REL)
    for p in scan_root.rglob(pattern):
        # p is .../<run_dir>/working/checkpoints/.trust-boundary-shadow.jsonl
        run_dir = p.parent.parent.parent
        found.append(run_dir)
    return found


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(
        prog="trust_boundary_report.py",
        description="Operator-facing reader for the trust-boundary shadow observability log.",
    )
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--run-dir", type=Path, help="Report on one run directory's persisted log.")
    target.add_argument("--log-file", type=Path,
                        help="Parse a raw text build/CI log directly (not yet persisted as JSONL).")
    target.add_argument("--scan-root", type=Path,
                        help="Report across every run under this directory that has a persisted log.")
    ap.add_argument("--json", action="store_true", help="Machine-readable output.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit 2 if any would-have-blocked observation is found. "
                         "OFF by default; not called by any build step in this repo.")
    args = ap.parse_args(argv)

    if args.run_dir is not None:
        observations = obs.load_observations(args.run_dir)
        label = str(args.run_dir)
    elif args.log_file is not None:
        if not args.log_file.is_file():
            print(f"error: --log-file not found: {args.log_file}", file=sys.stderr)
            return 1
        observations = []
        for raw in args.log_file.read_text(encoding="utf-8", errors="replace").splitlines():
            o = obs.parse_line(raw)
            if o is not None:
                observations.append(o)
        label = str(args.log_file)
    else:
        scan_root = args.scan_root
        if not scan_root.is_dir():
            print(f"error: --scan-root not a directory: {scan_root}", file=sys.stderr)
            return 1
        observations = []
        run_dirs = _run_dirs_under(scan_root)
        for rd in run_dirs:
            observations.extend(obs.load_observations(rd))
        label = f"{scan_root} ({len(run_dirs)} run dir(s) with a persisted log)"

    if args.json:
        print(render_json(observations, label))
    else:
        print(render_text(observations, label))

    if args.strict and any(o.would_have_blocked for o in observations):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
