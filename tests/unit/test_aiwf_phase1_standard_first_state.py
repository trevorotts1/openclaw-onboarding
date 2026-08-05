#!/usr/bin/env python3
"""Phase 1 verification gate — AI Workforce standard-first redesign (2026-08-04).

Proves the PHASE 1 state-schema contract (master plan section 6, PHASE 1):

  1. build-state-schema.json is valid JSON and the addition is ADDITIVE:
     - top-level `buildType` property exists (enum: legacy / standard-first)
     - top-level `standardPrebuild` block exists (status required; status enum
       pending/done/failed; agentRegistration pinned to the single value
       'deferred'; standardReadyAt / floorVersion / prebuiltDepartments /
       source / operatorConsentRef present)
     - departments[].status enum gained 'prebuilt' WITHOUT losing any of the
       legacy values (pending/building/done/failed)
     - the pre-existing required list (version, interviewComplete, ownerChat,
       departments) is UNCHANGED
  2. Legacy state (ABSENT buildType) parses UNCHANGED:
     - json.load round-trips a legacy fixture byte-for-byte into the same dict
     - build-workforce.py's _load_build_state() returns that same dict for the
       fixture (never raises)
     - _standard_first_mode() returns False for it (legacy lane)
  3. _standard_first_mode() branch table:
     absent / 'legacy' / garbage / non-string / non-dict -> False (legacy lane)
     'standard-first' (case/whitespace tolerant)         -> True
     fail-safe: an unreadable state file                  -> False, never raises
  4. The floor-count drift-guard's REQUIRED anchors in build-state-schema.json
     still match (check-floor-count-consistency.py registers three REQUIRED
     regexes on this file; a rewording there silently breaks the guard).

No pytest dependency (plain asserts + a main runner), so the gate runs on any
box:  python3 tests/unit/test_aiwf_phase1_standard_first_state.py
Exit 0 = all assertions pass; exit 1 = first failure printed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "23-ai-workforce-blueprint"
SCHEMA_PATH = SKILL_DIR / "build-state-schema.json"
BUILD_WORKFORCE = SKILL_DIR / "scripts" / "build-workforce.py"

# A realistic LEGACY build-state fixture: no buildType, no standardPrebuild —
# exactly what every pre-cutover box carries on disk.
LEGACY_STATE = {
    "version": 1,
    "interviewComplete": True,
    "ownerChat": 123456789,
    "companySlug": "legacy-co",
    "departments": [
        {"slug": "marketing", "status": "done"},
        {"slug": "sales", "status": "done"},
    ],
    "roleLibraryStatus": "done",
    "sopLibraryStatus": "done",
    "closeoutStatus": "done",
}

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"  [PASS] {label}")
    else:
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""))
        FAILURES.append(label)


def _load_build_workforce_module():
    """Import build-workforce.py the way the CI harnesses do (spec_from_file_location)."""
    spec = importlib.util.spec_from_file_location("build_workforce_phase1_test", str(BUILD_WORKFORCE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    print("=== AIWF PHASE 1: standardPrebuild block + buildType ===")

    # ------------------------------------------------------------------ 1
    print("--- 1. schema validity + additive shape")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))  # raises if invalid
    check("schema parses as JSON", isinstance(schema, dict))

    props = schema.get("properties", {})
    check("buildType property present", "buildType" in props)
    check(
        "buildType enum is exactly [legacy, standard-first]",
        props.get("buildType", {}).get("enum") == ["legacy", "standard-first"],
        f"got {props.get('buildType', {}).get('enum')!r}",
    )

    sp = props.get("standardPrebuild", {})
    check("standardPrebuild property present", bool(sp))
    check("standardPrebuild is an object schema", sp.get("type") == "object")
    check("standardPrebuild requires ['status']", sp.get("required") == ["status"])
    sp_props = sp.get("properties", {})
    for key in (
        "status", "standardReadyAt", "floorVersion", "prebuiltDepartments",
        "agentRegistration", "source", "operatorConsentRef",
    ):
        check(f"standardPrebuild.{key} present", key in sp_props)
    check(
        "standardPrebuild.status enum is pending/done/failed",
        sp_props.get("status", {}).get("enum") == ["pending", "done", "failed"],
    )
    check(
        "standardPrebuild.agentRegistration pinned to ['deferred']",
        sp_props.get("agentRegistration", {}).get("enum") == ["deferred"],
    )
    check(
        "standardPrebuild forbids extra fields (additionalProperties false)",
        sp.get("additionalProperties") is False,
    )

    dept_status_enum = (
        props.get("departments", {}).get("items", {}).get("properties", {})
        .get("status", {}).get("enum")
    )
    check(
        "departments[].status enum = legacy values + 'prebuilt'",
        dept_status_enum == ["pending", "building", "done", "failed", "prebuilt"],
        f"got {dept_status_enum!r}",
    )
    check(
        "top-level required list UNCHANGED",
        schema.get("required") == ["version", "interviewComplete", "ownerChat", "departments"],
        f"got {schema.get('required')!r}",
    )

    # ------------------------------------------------------------------ 2
    print("--- 2. legacy state (absent buildType) parses unchanged")
    with tempfile.TemporaryDirectory(prefix="aiwf_phase1_") as tmp:
        fixture = Path(tmp) / ".workforce-build-state.json"
        fixture.write_text(json.dumps(LEGACY_STATE, indent=2), encoding="utf-8")

        # Raw JSON parse is byte-faithful.
        raw_loaded = json.loads(fixture.read_text(encoding="utf-8"))
        check("json.load round-trips the legacy fixture unchanged", raw_loaded == LEGACY_STATE)

        bw = _load_build_workforce_module()

        # _load_build_state against the fixture path (point the resolver at it).
        original_path_fn = bw._build_state_path
        bw._build_state_path = lambda: str(fixture)
        try:
            loaded = bw._load_build_state()
            check("_load_build_state returns the legacy fixture unchanged", loaded == LEGACY_STATE)
        finally:
            bw._build_state_path = original_path_fn

        check("legacy state carries no buildType", "buildType" not in raw_loaded)
        check("legacy state carries no standardPrebuild", "standardPrebuild" not in raw_loaded)

        # ---------------------------------------------------------------- 3
        print("--- 3. _standard_first_mode() branch table")
        check("absent buildType -> legacy lane (False)", bw._standard_first_mode(raw_loaded) is False)
        legacy_explicit = dict(raw_loaded)
        legacy_explicit["buildType"] = "legacy"
        check("buildType='legacy' -> legacy lane (False)", bw._standard_first_mode(legacy_explicit) is False)

        sf = dict(raw_loaded)
        sf["buildType"] = "standard-first"
        check("buildType='standard-first' -> True", bw._standard_first_mode(sf) is True)
        sf_pad = dict(raw_loaded)
        sf_pad["buildType"] = "  Standard-First  "
        check("case/whitespace-tolerant match -> True", bw._standard_first_mode(sf_pad) is True)

        garbage = dict(raw_loaded)
        garbage["buildType"] = "standard_first"  # underscore variant is NOT the token
        check("garbage buildType value -> legacy lane (False)", bw._standard_first_mode(garbage) is False)
        nonstr = dict(raw_loaded)
        nonstr["buildType"] = 123
        check("non-string buildType -> legacy lane (False)", bw._standard_first_mode(nonstr) is False)
        check("non-dict state -> legacy lane (False), no raise", bw._standard_first_mode([1, 2, 3]) is False)

        # Explicit dict pass-through (no disk read): the prebuild driver's call shape.
        check("explicit dict pass-through works", bw._standard_first_mode({"buildType": "standard-first"}) is True)

        # Fail-safe on an UNREADABLE/absent state file: the no-argument form loads
        # from disk and must return False, never raise.
        unreadable = Path(tmp) / "missing-state.json"
        bw._build_state_path = lambda: str(unreadable)
        try:
            check("absent state file -> legacy lane (False), no raise", bw._standard_first_mode() is False)
            check("empty build-state ({}) -> legacy lane (False)", bw._standard_first_mode({}) is False)
        finally:
            bw._build_state_path = original_path_fn

    # ------------------------------------------------------------------ 4
    print("--- 4. floor-count drift-guard anchors still match")
    import re
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    anchors = [
        r"canonical floor \(\d+ mandatory \+ \d+ universal-primary = \d+ on-disk, computed live\)",
        r"\(\d+ mandatory \+ \d+ universal-primary; master-orchestrator is never a yes/no/later decision so it is not part of this \d+\)",
        r"Covers mandatory canonical depts AND the \d+ universal-primary vertical depts",
    ]
    for i, pat in enumerate(anchors, 1):
        check(f"REQUIRED anchor {i} matches", re.search(pat, text) is not None)

    print()
    if FAILURES:
        print(f"=== PHASE 1 GATE: {len(FAILURES)} FAILURE(S) ===")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("=== PHASE 1 GATE: ALL PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
