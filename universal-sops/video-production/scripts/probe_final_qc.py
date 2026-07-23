#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_final_qc.py — fail-closed final-QC meta-gate (Personal Video Creator cluster,
universal-sops/video-production). Reads 11_qc/final_qc.md and HARD-FAILS (AF-PVC-FINAL-QC)
unless:
  * EVERY checkbox is ticked ('- [x]'); any '- [ ]' is a fail
  * the file carries the 'ALL PROBES PASSED' attestation marker (the executor records that
    every cluster probe_*.py exited 0 for this project)
Optionally verifies a probes receipt JSON (--probes-receipt) where every probe exit code == 0.
Exit 0 pass, 2 violation, 3 usage/fail-closed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3
PROBES_MARKER = "ALL PROBES PASSED"

REQUIRED_PROBES = [
    "probe_consent", "probe_no_secrets", "probe_manifest", "probe_environment",
    "probe_prompt_band", "probe_frame_plan", "probe_segment_duration", "probe_video_clip",
    "probe_lipsync_offset", "probe_picture_duration", "probe_audio_master", "probe_scene_qc",
    "probe_final_technical",
]


def verify(final_qc_text: str, receipt: dict | None = None) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []

    unchecked = re.findall(r"^\s*-\s*\[ \]\s*(.*)$", final_qc_text, re.MULTILINE)
    checked = re.findall(r"^\s*-\s*\[x\]\s*(.*)$", final_qc_text, re.IGNORECASE | re.MULTILINE)
    notes.append(f"{len(checked)} checked / {len(unchecked)} unchecked final-QC item(s)")
    for item in unchecked:
        violations.append(("AF-PVC-FINAL-QC", f"unchecked final-QC item: {item.strip()[:80]}"))

    if PROBES_MARKER not in final_qc_text:
        violations.append(("AF-PVC-FINAL-QC",
                           f"final_qc.md lacks the '{PROBES_MARKER}' attestation (every cluster probe must exit 0)"))

    if receipt is not None:
        results = receipt.get("probes", receipt)
        if isinstance(results, dict):
            for name in REQUIRED_PROBES:
                code = results.get(name)
                if code is None:
                    violations.append(("AF-PVC-FINAL-QC", f"probes receipt missing result for {name}"))
                elif int(code) != 0:
                    violations.append(("AF-PVC-FINAL-QC", f"probe {name} exited {code} (expected 0)"))

    return violations, notes


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: every final-QC item is attested and all probes passed.")
        return
    print(f"FAIL: {len(violations)} final-QC violation(s) — the job may NOT be marked complete.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


_VALID = """# Final QC
## Authorization
- [x] Likeness consent verified
- [x] Voice consent verified
## Technical
- [x] Video codec approved
- [x] Duration matches

ALL PROBES PASSED
"""


def run_self_test() -> int:
    ok = True
    v, _ = verify(_VALID)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid -> {v}")
    else:
        print("SELF-TEST ok: valid -> PASS")

    unchecked = _VALID.replace("- [x] Duration matches", "- [ ] Duration matches")
    v, _ = verify(unchecked)
    if not any("unchecked" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: unchecked -> {v}")
    else:
        print("SELF-TEST ok: unchecked -> AF-PVC-FINAL-QC")

    nomarker = _VALID.replace("ALL PROBES PASSED", "")
    v, _ = verify(nomarker)
    if not any(PROBES_MARKER in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: no-marker -> {v}")
    else:
        print("SELF-TEST ok: no-marker -> AF-PVC-FINAL-QC")

    good_receipt = {"probes": {n: 0 for n in REQUIRED_PROBES}}
    v, _ = verify(_VALID, good_receipt)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: good-receipt -> {v}")
    else:
        print("SELF-TEST ok: good-receipt -> PASS")

    bad_receipt = {"probes": {n: 0 for n in REQUIRED_PROBES}}
    bad_receipt["probes"]["probe_lipsync_offset"] = 2
    v, _ = verify(_VALID, bad_receipt)
    if not any("probe_lipsync_offset" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: bad-receipt -> {v}")
    else:
        print("SELF-TEST ok: bad-receipt -> AF-PVC-FINAL-QC")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed final-QC meta-gate.")
    ap.add_argument("--final-qc", help="path to 11_qc/final_qc.md")
    ap.add_argument("--project-dir", help="project root")
    ap.add_argument("--probes-receipt", help="optional JSON receipt of probe exit codes")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    path = None
    if args.final_qc:
        path = Path(args.final_qc)
    elif args.project_dir:
        path = Path(args.project_dir) / "11_qc" / "final_qc.md"
    if not path or not path.exists():
        print(f"USAGE/IO ERROR: final_qc.md not found ({path}).")
        return EXIT_FAILCLOSED
    text = path.read_text(encoding="utf-8", errors="replace")
    receipt = None
    if args.probes_receipt:
        try:
            receipt = json.loads(Path(args.probes_receipt).read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot read probes receipt: {exc}")
            return EXIT_FAILCLOSED
    violations, notes = verify(text, receipt)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
