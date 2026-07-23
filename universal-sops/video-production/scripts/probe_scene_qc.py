#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_scene_qc.py — fail-closed scene-QC ledger gate (Personal Video Creator cluster,
universal-sops/video-production). Reads 11_qc/scene_qc.csv and HARD-FAILS (AF-PVC-SCENE-QC)
unless EVERY TALKING_HEAD scene has decision == PASS AND a recorded lip_sync_offset_frames
<= max_offset (default 2). A missing/blank offset on a talking-head scene is a fail (the
offset must be measured, not assumed). Exit 0 pass, 2 violation, 3 usage/fail-closed.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3
MAX_OFFSET = 2.0


def verify(rows: List[dict], max_offset: float = MAX_OFFSET) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    talking = 0
    for row in rows:
        stype = (row.get("scene_type") or "").strip().upper()
        if stype != "TALKING_HEAD":
            continue
        talking += 1
        sid = (row.get("scene_id") or "?").strip()
        decision = (row.get("decision") or "").strip().upper()
        offset_raw = (row.get("lip_sync_offset_frames") or "").strip()
        if decision != "PASS":
            violations.append(("AF-PVC-SCENE-QC", f"{sid}: decision is '{decision or '(blank)'}', not PASS"))
        if offset_raw == "":
            violations.append(("AF-PVC-SCENE-QC", f"{sid}: lip_sync_offset_frames not recorded (must be measured)"))
            continue
        try:
            offset = abs(float(offset_raw))
        except ValueError:
            violations.append(("AF-PVC-SCENE-QC", f"{sid}: lip_sync_offset_frames '{offset_raw}' is not a number"))
            continue
        if offset > max_offset:
            violations.append(("AF-PVC-SCENE-QC", f"{sid}: lip_sync_offset_frames {offset} > {max_offset}"))
    if talking == 0:
        violations.append(("AF-PVC-SCENE-QC", "scene_qc.csv has no TALKING_HEAD rows"))
    return violations, [f"checked {talking} TALKING_HEAD scene(s)"]


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: every talking-head scene is PASS with a measured offset within tolerance.")
        return
    print(f"FAIL: {len(violations)} scene-QC violation(s).")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


_VALID = [
    {"scene_id": "scene_001", "scene_type": "TALKING_HEAD", "decision": "PASS", "lip_sync_offset_frames": "1"},
    {"scene_id": "scene_002", "scene_type": "BROLL_GENERATED", "decision": "PASS", "lip_sync_offset_frames": ""},
    {"scene_id": "scene_003", "scene_type": "TALKING_HEAD", "decision": "PASS", "lip_sync_offset_frames": "2"},
]


def run_self_test() -> int:
    ok = True
    v, _ = verify(_VALID)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid -> {v}")
    else:
        print("SELF-TEST ok: valid -> PASS")

    retry = [dict(_VALID[0], decision="RETRY_LIPSYNC")]
    v, _ = verify(retry)
    if not any("not PASS" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: retry -> {v}")
    else:
        print("SELF-TEST ok: retry -> AF-PVC-SCENE-QC")

    nooffset = [dict(_VALID[0], lip_sync_offset_frames="")]
    v, _ = verify(nooffset)
    if not any("not recorded" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: no-offset -> {v}")
    else:
        print("SELF-TEST ok: no-offset -> AF-PVC-SCENE-QC")

    bigoffset = [dict(_VALID[0], lip_sync_offset_frames="4")]
    v, _ = verify(bigoffset)
    if not any("> 2" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: big-offset -> {v}")
    else:
        print("SELF-TEST ok: big-offset -> AF-PVC-SCENE-QC")

    v, _ = verify([{"scene_id": "b1", "scene_type": "BROLL_GENERATED", "decision": "PASS"}])
    if {c for c, _ in v} != {"AF-PVC-SCENE-QC"}:
        ok = False
        print(f"SELF-TEST FAIL: no-talking -> {v}")
    else:
        print("SELF-TEST ok: no-talking -> AF-PVC-SCENE-QC")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed scene-QC ledger gate.")
    ap.add_argument("--scene-qc", help="path to 11_qc/scene_qc.csv")
    ap.add_argument("--project-dir", help="project root")
    ap.add_argument("--max-offset", type=float, default=MAX_OFFSET)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    path = None
    if args.scene_qc:
        path = Path(args.scene_qc)
    elif args.project_dir:
        path = Path(args.project_dir) / "11_qc" / "scene_qc.csv"
    if not path or not path.exists():
        print(f"USAGE/IO ERROR: scene_qc.csv not found ({path}).")
        return EXIT_FAILCLOSED
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))
    violations, notes = verify(rows, args.max_offset)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
