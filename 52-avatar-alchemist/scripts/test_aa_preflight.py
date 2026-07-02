#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_aa_preflight.py — the Avatar-Alchemist negative test suite (Skill 52).

Drives EVERY fail-closed prover's --self-test in-process: it asserts each VALID
fixture PASSES and each crafted BAD fixture FAILS with its expected AF-AV-* code.
A gate without a failing test does not ship (PRD 7). This is what CI
(qc-avatar-alchemist.sh) runs to keep the gates honest.

Run:  python3 scripts/test_aa_preflight.py
Exit 0 = every gate proven (valid passes, every bad fixture fails); 1 = a gate is broken.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import aa_intake_gate as intake            # noqa: E402
import aa_build_check as build             # noqa: E402
import aa_delivery_gate as delivery        # noqa: E402
import aa_links_gate as links              # noqa: E402

MANIFEST = json.loads((ROOT / "AA-PIPELINE-MANIFEST.json").read_text(encoding="utf-8"))


def main() -> int:
    print("=== G0-INTAKE + G0-VERSION (aa_intake_gate.py) ===")
    rc_intake = intake.run_self_test()
    print("\n=== content invariants (aa_build_check.py) ===")
    rc_build = build.run_self_test(MANIFEST)
    print("\n=== provenance + delivery (aa_delivery_gate.py) ===")
    rc_deliver = delivery.run_self_test(MANIFEST)
    print("\n=== stage-02 link gate (aa_links_gate.py, fail-soft + empty=fail-closed) ===")
    rc_links = links.run_self_test()

    # cross-check: manifest <-> prompts-dir lockstep (40/40) and AF-code coverage.
    print("\n=== manifest <-> prompts lockstep + AF-code coverage ===")
    ok = True
    prompt_dirs = {p.name for p in (ROOT / "prompts").iterdir() if p.is_dir()}
    stage_ids = {s["stage_id"] for s in MANIFEST["stages"]}
    if prompt_dirs != stage_ids:
        ok = False
        print(f"LOCKSTEP FAIL: prompts/ dirs {len(prompt_dirs)} != manifest stages {len(stage_ids)} "
              f"(missing {stage_ids - prompt_dirs}; extra {prompt_dirs - stage_ids})")
    else:
        print(f"LOCKSTEP ok: 40/40 prompt dirs match manifest stages ({len(stage_ids)}).")
    for sid in stage_ids:
        for f in ("system.md", "methodology.md", "user.md"):
            if not (ROOT / "prompts" / sid / f).is_file():
                ok = False; print(f"LOCKSTEP FAIL: {sid}/{f} missing")
    enf = json.loads((ROOT / "AVATAR-MANIFEST.json").read_text(encoding="utf-8"))
    declared = set(enf["af_codes"])
    used = set()
    for ph in enf["phases"]:
        used.update(ph["af"])
    if used - declared:
        ok = False; print(f"AF FAIL: phases reference undeclared codes {used - declared}")
    else:
        print(f"AF ok: {len(declared)} AF-AV codes declared; every phase code is covered.")

    total = rc_intake + rc_build + rc_deliver + rc_links + (0 if ok else 1)
    print("\nNEGATIVE-SUITE RESULT:", "PASS (exit 0)" if total == 0 else "FAIL (exit 1)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
