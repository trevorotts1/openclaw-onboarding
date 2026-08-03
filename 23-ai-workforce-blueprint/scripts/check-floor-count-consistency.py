#!/usr/bin/env python3
"""
check-floor-count-consistency.py — CI DRIFT-GUARD: no doc/comment may state a
department-FLOOR count that disagrees with the count DERIVED LIVE from
department-naming-map.json.

WHY THIS EXISTS (the bug it kills — the OQ-7 "28-vs-29" discrepancy)
-------------------------------------------------------------------
The department floor is authoritative in ONE place — department-naming-map.json —
and is derived at runtime by list-canonical-departments.py / department-floor.py
(mandatory depts + universal-primary vertical-pack depts). Naming map v2.6.1
demoted the real-estate `listings` dept from universal-primary to industry-gated,
so the live floor dropped 29 -> 28 (universal-primary 7 -> 6).

But several docs/comments ALSO wrote the floor as *prose* ("22 mandatory + 7
universal-primary = 29"). Prose does not recompute. When the naming map moved to
v2.6.1 the prose went stale and now DISAGREES with the derived count — a reader
of build-state-schema.json sees 29 while the code enforces 28. That silent
divergence is exactly the OQ-7 drift.

There are TWO existing guards near this, and NEITHER closes this gap:
  * scripts/check-floor-count-drift.py (repo root) only checks department-floor.py's
    OWN output strings — it never looks at build-state-schema.json / CHANGELOG.
  * qc-assert-repo-consistency.py's Issue-#10 forbidden-literal scan only reads
    INSTRUCTIONS.md, and uses a HARDCODED blocklist of stale phrasings ("= 29"),
    which is itself a number that would rot if the floor changed again.

This guard is DIFFERENT and complementary: it DERIVES the floor fresh from the
naming map (never re-hardcodes a number) and ASSERTS that every registered
doc/comment that *quotes* the floor equals the derived value. The count lives in
exactly ONE authoritative place; every doc is checked against it.

HOW IT WORKS
------------
1. DERIVE the canonical floor by importing list-canonical-departments.py from the
   skill-under-test and calling its own functions (load_naming_map / get_mandatory
   / get_universal_primaries). No integer is hardcoded here — change the naming
   map and this guard's expectation moves with it automatically.
2. Walk DOC_FLOOR_REGISTRY (below): a small, explicit, easy-to-extend list of the
   exact doc/comment locations that state a floor count, each with a surgical
   anchor regex and which derived value each captured number must equal.
3. FAIL loudly (exit 5) listing every mismatched file:line if any doc disagrees.
   Pass quietly (exit 0) if all agree. Exit 2 on a load/derive failure OR when a
   REQUIRED anchor no longer matches (a doc was reworded and the registry must be
   updated — this refuses to silently pass on a moved anchor).

DELIBERATELY NOT FLAGGED (see registry comments for the reasoning)
  * CHANGELOG.md historical, version-scoped release entries ("v12.7.0 raised the
    floor 28 -> 29"). Those are FROZEN HISTORY and were accurate for their release;
    rewriting them would corrupt the changelog and the guard would never pass even
    after the real fix (which ADDS a new entry, it does not edit old ones). The
    CHANGELOG is registered with an OPTIONAL standing-sentinel check instead.
  * Negative-test fixtures that intentionally PLANT a stale string to prove another
    guard bites (e.g. test-repo-consistency.sh T6), and the Issue-#10 forbidden
    -literal blocklist inside qc-assert-repo-consistency.py.
  * Prose that DEFERS to the script ("run list-canonical-departments.py for the
    current count") — that is the CORRECT pattern and hardcodes no number.

USAGE
  python3 check-floor-count-consistency.py                 # human report + PASS/FAIL
  python3 check-floor-count-consistency.py --json          # machine-readable verdict
  python3 check-floor-count-consistency.py --skill-dir DIR # check an explicit skill dir
                                                            # (used by the sandbox tests / CI checkout)

EXIT CODES
  0  every registered doc agrees with the derived floor (or an optional sentinel is absent)
  5  DRIFT FOUND — at least one doc states a count that disagrees. file:line printed.
  2  could not derive the floor, a registered file is missing, or a REQUIRED anchor
     no longer matches (registry is stale — update the anchor).

Read-only. Never writes. Idempotent.
"""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# DOC_FLOOR_REGISTRY — the ONE explicit list of doc/comment locations that quote
# the department floor as prose. To add a new location: append an entry with the
# file (relative to the skill dir), a WHY note, and one or more assertions. Each
# assertion's `regex` MUST contain named groups; `groups` maps each named group to
# the derived key its captured integer must equal:
#     "floor"              -> ON-DISK total floor (mandatory + universal-primary;
#                              department-floor.py's number; includes the
#                              never-declinable master-orchestrator)
#     "mandatory"          -> ON-DISK mandatory canonical dept count
#     "universal_primary"  -> universal-primary vertical-pack dept count (same
#                              in both tiers)
#     "buildable_floor"    -> the INTERVIEW-DECLINABLE floor build-workforce.py
#                              actually unions into selected_departments
#                              (on-disk floor minus master-orchestrator)
#     "buildable_mandatory" -> the INTERVIEW-DECLINABLE mandatory dept count
#
# `required` (default True): if the regex does not match, that is REGISTRY ROT —
# the doc was reworded and the anchor moved — and the guard FAILS (exit 2) rather
# than silently passing. Set `required=False` for an OPTIONAL sentinel that may be
# absent (used for the append-only CHANGELOG).
# ─────────────────────────────────────────────────────────────────────────────
DOC_FLOOR_REGISTRY = [
    {
        "file": "build-state-schema.json",
        "why": (
            "canonicalReconciliation.description hardcodes BOTH tiers as prose "
            "(on-disk 'N mandatory + M universal-primary = F on-disk, computed "
            "live' and the buildable parenthetical). This is the OQ-7 drift site: "
            "it once read 22 + 7 = 29 while the live naming map derived 22 + 6 = "
            "28. No other guard covers this schema file."
        ),
        "assertions": [
            {
                "label": "canonicalReconciliation.description on-disk floor prose",
                "regex": re.compile(
                    r"canonical floor \((?P<mandatory>\d+) mandatory \+ "
                    r"(?P<universal_primary>\d+) universal-primary = (?P<floor>\d+) on-disk, computed live\)"
                ),
                "groups": {
                    "mandatory": "mandatory",
                    "universal_primary": "universal_primary",
                    "floor": "floor",
                },
            },
            {
                "label": "canonicalReconciliation.description buildable-floor prose",
                "regex": re.compile(
                    r"\((?P<buildable_mandatory>\d+) mandatory \+ (?P<universal_primary2>\d+) "
                    r"universal-primary; master-orchestrator is never a yes/no/later decision "
                    r"so it is not part of this (?P<buildable_floor>\d+)\)"
                ),
                "groups": {
                    "buildable_mandatory": "buildable_mandatory",
                    "universal_primary2": "universal_primary",
                    "buildable_floor": "buildable_floor",
                },
            },
            {
                "label": "decisions.description universal-primary count prose",
                "regex": re.compile(
                    r"Covers mandatory canonical depts AND the (?P<universal_primary>\d+) "
                    r"universal-primary vertical depts"
                ),
                "groups": {"universal_primary": "universal_primary"},
            },
        ],
    },
    {
        "file": "scripts/qc-assert-repo-consistency.py",
        "why": (
            "The repo-consistency gate's own module docstring states BOTH tiers as "
            "prose (naming-map's raw mandatory count, the buildable count this "
            "gate's floor_dept_ids() actually gates, and department-floor.py's "
            "separate on-disk number). Registered so the gate's own documentation "
            "can never silently drift from the counts it enforces and derives from."
        ),
        "assertions": [
            {
                "label": "module docstring FLOOR line",
                "regex": re.compile(
                    r"`\.mandatory` \((?P<mandatory>\d+),.*?leaving (?P<buildable_mandatory>\d+)\) \+ the "
                    r"(?P<universal_primary>\d+) universal-primary\s+vertical-pack depts = "
                    r"(?P<buildable_floor>\d+) gated here\. department-floor\.\s*py's separate ON-DISK floor is "
                    r"(?P<floor>\d+)",
                    re.DOTALL,
                ),
                "groups": {
                    "mandatory": "mandatory",
                    "buildable_mandatory": "buildable_mandatory",
                    "universal_primary": "universal_primary",
                    "buildable_floor": "buildable_floor",
                    "floor": "floor",
                },
            },
        ],
    },
    {
        "file": "scripts/build-workforce.py",
        "why": (
            "The builder's CANONICAL DEPARTMENT FLOOR banner comment states the "
            "ON-DISK floor as prose ('standard: N mandatory + M universal-primary-"
            "vertical = F'). Registered so the builder's headline comment can never "
            "drift from department-floor.py's on-disk count (load_canonical_floor() "
            "itself, a few lines below this banner, builds the SEPARATE buildable-"
            "23 set — see that function's own docstring, not registered here since "
            "it is code, not quotable prose)."
        ),
        "assertions": [
            {
                "label": "CANONICAL DEPARTMENT FLOOR banner comment",
                "regex": re.compile(
                    r"CANONICAL DEPARTMENT FLOOR \(standard: (?P<mandatory>\d+) mandatory \+ "
                    r"(?P<universal_primary>\d+) universal-primary-vertical = (?P<floor>\d+)\)"
                ),
                "groups": {
                    "mandatory": "mandatory",
                    "universal_primary": "universal_primary",
                    "floor": "floor",
                },
            },
        ],
    },
    {
        "file": "scripts/department-floor.py",
        "why": (
            "The ON-DISK floor checker's own module docstring states the floor it "
            "enforces as prose. This is the single most load-bearing floor number "
            "in the repo (every other on-disk-floor doc defers to this script) so "
            "its own headline can never be allowed to drift from what it actually "
            "computes."
        ),
        "assertions": [
            {
                "label": "module docstring FLOOR line",
                "regex": re.compile(
                    r"FLOOR \(computed live from department-naming-map\.json v[\d.]+\): "
                    r"(?P<floor>\d+) departments =\n(?P<mandatory>\d+) mandatory canonical \+ "
                    r"(?P<universal_primary>\d+) universal-primary vertical-pack"
                ),
                "groups": {
                    "mandatory": "mandatory",
                    "universal_primary": "universal_primary",
                    "floor": "floor",
                },
            },
        ],
    },
    {
        "file": "scripts/list-canonical-departments.py",
        "why": (
            "The user-facing 'run this to see the current floor' printer states "
            "the floor as prose in its own docstring. Every other doc in this "
            "registry tells the reader to defer to this script; the script itself "
            "must never be allowed to drift from what it prints."
        ),
        "assertions": [
            {
                "label": "docstring live-derivation line",
                "regex": re.compile(
                    r"live naming map \((?P<mandatory>\d+) \+ (?P<universal_primary>\d+) = "
                    r"(?P<floor>\d+) for naming map v[\d.]+\)"
                ),
                "groups": {
                    "mandatory": "mandatory",
                    "universal_primary": "universal_primary",
                    "floor": "floor",
                },
            },
        ],
    },
    {
        "file": "SKILL.md",
        "why": (
            "Skill 23's own top-level SKILL.md states BOTH tiers as prose in its "
            "'What This Skill Does' section, read by every agent that loads this "
            "skill. Registered so the skill's own headline description can never "
            "silently misrepresent the floor it builds to."
        ),
        "assertions": [
            {
                "label": "reconciliation-engine paragraph floor prose",
                "regex": re.compile(
                    r"declinable floor = (?P<buildable_floor>\d+) \[(?P<buildable_mandatory>\d+) "
                    r"mandatory \+ (?P<universal_primary>\d+) universal-primary\]; "
                    r"department-floor\.py's on-disk floor is (?P<floor>\d+)"
                ),
                "groups": {
                    "buildable_floor": "buildable_floor",
                    "buildable_mandatory": "buildable_mandatory",
                    "universal_primary": "universal_primary",
                    "floor": "floor",
                },
            },
        ],
    },
    {
        "file": "INSTRUCTIONS.md",
        "why": (
            "CLIENT-FACING: the interviewer executes INSTRUCTIONS.md verbatim, so "
            "its OPT-OUT WARNING (read aloud to owners deciding whether to decline "
            "a floor department) is the single highest-stakes floor-count site in "
            "the repo. Also covered by qc-assert-repo-consistency.py's Issue #10 "
            "forbidden-literal scan, but that guard only catches RETIRED phrasing; "
            "this registry entry additionally proves the CURRENT number is right."
        ),
        "assertions": [
            {
                "label": "OPT-OUT WARNING floor prose",
                "regex": re.compile(
                    r"any of the (?P<buildable_floor>\d+) declinable: the "
                    r"(?P<buildable_mandatory>\d+) mandatory \+ the (?P<universal_primary>\d+) "
                    r"universal-primary verticals — the Master Orchestrator is the naming "
                    r"map's (?P<mandatory>\d+)th mandatory dept"
                ),
                "groups": {
                    "buildable_floor": "buildable_floor",
                    "buildable_mandatory": "buildable_mandatory",
                    "universal_primary": "universal_primary",
                    "mandatory": "mandatory",
                },
            },
        ],
    },
    {
        "file": "DEPARTMENTS.md",
        "why": (
            "The Stage-1 pipeline diagram states the buildable mandatory count. "
            "Also independently proven by tests/unit/u052-department-doc-"
            "validation.test.sh (exact-set-equality against department-naming-"
            "map.json, mirrored exclusion for master-orchestrator) — this registry "
            "entry additionally catches the DIAGRAM prose that test does not read."
        ),
        "assertions": [
            {
                "label": "Stage 1 pipeline diagram",
                "regex": re.compile(
                    r"Stage 1: Canonical Floor \│  ← (?P<buildable_mandatory>\d+) mandatory departments"
                ),
                "groups": {"buildable_mandatory": "buildable_mandatory"},
            },
        ],
    },
    {
        "file": "ZHC-BUILDOUT-EXPERIENCE.md",
        "why": (
            "The owner-facing buildout-experience doc states both the on-disk and "
            "buildable tiers as prose."
        ),
        "assertions": [
            {
                "label": "on-disk floor prose",
                "regex": re.compile(
                    r"departments \((?P<mandatory>\d+) mandatory \+ (?P<universal_primary>\d+) "
                    r"universal-primary — v2\.8\.0 registered",
                    re.DOTALL,
                ),
                "groups": {"mandatory": "mandatory", "universal_primary": "universal_primary"},
            },
            {
                "label": "buildable floor prose",
                "regex": re.compile(
                    r"actually unions in is (?P<buildable_floor>\d+) \((?P<buildable_mandatory>\d+) "
                    r"mandatory \+ (?P<universal_primary>\d+) universal-primary\), since Master",
                    re.DOTALL,
                ),
                "groups": {
                    "buildable_floor": "buildable_floor",
                    "buildable_mandatory": "buildable_mandatory",
                    "universal_primary": "universal_primary",
                },
            },
        ],
    },
    {
        "file": "department-wiring/podcast-engine/wiring.json",
        "why": (
            "Skill 58's floor_invariant asserts the ON-DISK expected_floor_count "
            "as a machine-readable literal (proof text also references "
            "department-floor.py --json, whose own output is the ground truth)."
        ),
        "assertions": [
            {
                "label": "floor_invariant.expected_floor_count + composition",
                "regex": re.compile(
                    r'"expected_floor_count": (?P<floor>\d+),\s*\n\s*"composition": '
                    r'"(?P<mandatory>\d+) mandatory \+ (?P<universal_primary>\d+) '
                    r'universal-primary-vertical"'
                ),
                "groups": {
                    "mandatory": "mandatory",
                    "universal_primary": "universal_primary",
                    "floor": "floor",
                },
            },
        ],
    },
    {
        "file": "department-wiring/anthology-engine/wiring.json",
        "why": (
            "Skill 59's floor_invariant asserts the ON-DISK expected_floor_count "
            "the same way podcast-engine's does. verify-anthology-engine-wiring.py "
            "cross-checks this value against a LIVE department-floor.py --json call "
            "at runtime (not registered here — that is code, not quotable prose)."
        ),
        "assertions": [
            {
                "label": "floor_invariant.expected_floor_count + composition",
                "regex": re.compile(
                    r'"expected_floor_count": (?P<floor>\d+),\s*\n\s*"composition": '
                    r'"(?P<mandatory>\d+) mandatory \+ (?P<universal_primary>\d+) '
                    r'universal-primary-vertical"'
                ),
                "groups": {
                    "mandatory": "mandatory",
                    "universal_primary": "universal_primary",
                    "floor": "floor",
                },
            },
        ],
    },
    {
        "file": "department-wiring/podcast-engine/README.md",
        "why": "Skill 58's human-readable wiring doc states the on-disk floor as prose.",
        "assertions": [
            {
                "label": "floor prose (mandatory + universal = floor)",
                "regex": re.compile(
                    r"on top of the (?P<mandatory>\d+) mandatory departments "
                    r"\(\d+ \+ (?P<universal_primary>\d+) = (?P<floor>\d+)\)",
                    re.DOTALL,
                ),
                "groups": {
                    "mandatory": "mandatory",
                    "universal_primary": "universal_primary",
                    "floor": "floor",
                },
            },
        ],
    },
    {
        "file": "department-wiring/anthology-engine/README.md",
        "why": "Skill 59's human-readable wiring doc states the on-disk floor as prose.",
        "assertions": [
            {
                "label": "'fleet's N-department floor' prose",
                "regex": re.compile(r"fleet's (?P<floor>\d+)-department floor\. Anthology \(skill 59\)"),
                "groups": {"floor": "floor"},
            },
        ],
    },
    {
        "file": "skill-department-map.json",
        "why": (
            "The Anthology Engine (skill 59) entry states, as prose, that it is "
            "never one of the mandatory-or-universal-primary departments — the "
            "counts in that disclaimer must track the live floor."
        ),
        "assertions": [
            {
                "label": "anthology-engine 'never one of' disclaimer",
                "regex": re.compile(
                    r"never one of the (?P<mandatory>\d+) mandatory or "
                    r"(?P<universal_primary>\d+) universal-primary departments and "
                    r"department-naming-map"
                ),
                "groups": {"mandatory": "mandatory", "universal_primary": "universal_primary"},
            },
        ],
    },
    {
        "file": "scripts/qc-completeness.sh",
        "why": (
            "The v10.15.26 HARD DEPARTMENT FLOOR comment states the mandatory "
            "count as prose right above the code that imports department-floor.py "
            "as the actual source of truth — the comment must never fall behind "
            "the code it is explaining."
        ),
        "assertions": [
            {
                "label": "expected-floor comment",
                "regex": re.compile(
                    r"the expected floor = (?P<mandatory>\d+) mandatory "
                    r"\(department-naming-map\.json v[\d.]+\) \+ the"
                ),
                "groups": {"mandatory": "mandatory"},
            },
        ],
    },
    {
        "file": "scripts/verify-zhc-standard.sh",
        "why": (
            "The step-2 HARD DEPARTMENT FLOOR comment states the mandatory count "
            "as prose right above the code that shells out to department-floor.py "
            "as the actual source of truth."
        ),
        "assertions": [
            {
                "label": "3-dept-on-disk-workforce-FAILS comment",
                "regex": re.compile(
                    r"the (?P<mandatory>\d+) mandatory \(department-\s*#?\s*"
                    r"naming-map\.json v[\d.]+\) \+ the",
                    re.DOTALL,
                ),
                "groups": {"mandatory": "mandatory"},
            },
        ],
    },
    {
        "file": "scripts/verify-role-library.sh",
        "why": (
            "Check 1's derived-minimum-role-count comment states the mandatory/"
            "universal-primary composition as prose (the actual threshold is "
            "derived from _index.json at runtime, never hardcoded -- this "
            "registry entry only guards the EXPLANATORY prose above it)."
        ),
        "assertions": [
            {
                "label": "Check 1 comment composition",
                "regex": re.compile(
                    r"as of department-naming-map\.json v[\d.]+\) (?P<mandatory>\d+)\s*\n#\s*"
                    r"mandatory \+ (?P<universal_primary>\d+) universal-primary",
                    re.DOTALL,
                ),
                "groups": {"mandatory": "mandatory", "universal_primary": "universal_primary"},
            },
        ],
    },
    {
        "file": "CHANGELOG.md",
        "why": (
            "The CHANGELOG is append-only release history. Its existing floor "
            "mentions are VERSION-SCOPED and were accurate for their release "
            "('v12.7.0 raised the floor 28 -> 29') — they are frozen history and "
            "MUST NOT be rewritten, so per-line historical entries are intentionally "
            "NOT scanned. Instead, if a maintainer wants a STANDING current-floor "
            "line in the changelog, add a machine-checkable sentinel comment "
            "'<!-- canonical-floor: N -->' and this guard will enforce N == derived "
            "floor. Absent -> reported as skipped, not a failure (this repo's "
            "skill-level 23-ai-workforce-blueprint/CHANGELOG.md already carries "
            "the sentinel; the repo-root CHANGELOG.md does not and is skipped)."
        ),
        "assertions": [
            {
                "label": "standing canonical-floor sentinel (optional)",
                "regex": re.compile(r"<!--\s*canonical-floor:\s*(?P<floor>\d+)\s*-->"),
                "groups": {"floor": "floor"},
                "required": False,
            },
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Floor derivation — reuse list-canonical-departments.py's OWN logic. Never
# re-hardcode the count: change the naming map and this expectation moves with it.
# ─────────────────────────────────────────────────────────────────────────────
def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Ids that are mandatory in department-naming-map.json but carry NO interview
# decline path (provisioned outside selected_departments) -- see build-workforce.
# load_canonical_floor()'s docstring. Kept in exactly one place so both derived
# tiers below (on-disk vs buildable) can never drift apart from each other or
# from the exclusion build-workforce.py / qc-assert-repo-consistency.py apply.
_FLOOR_ONLY_NONBUILDABLE_IDS = {"ceo", "master-orchestrator", "dept-ceo"}


def derive_floor(skill_dir):
    """
    Return (derived_dict, error). derived_dict has keys:
      floor, mandatory, universal_primary  -- the ON-DISK floor department-
        floor.py enforces: every id in department-naming-map.json's `mandatory`
        block (v2.8.0: 24, including the never-declinable master-orchestrator)
        plus the universal-primary vertical-pack depts.
      buildable_floor, buildable_mandatory -- the INTERVIEW-DECLINABLE floor
        build-workforce.reconcile_canonical_floor() / apply_vertical_packs()
        actually union into selected_departments: the same mandatory set MINUS
        _FLOOR_ONLY_NONBUILDABLE_IDS, plus the same universal-primary depts.
        universal_primary is identical in both tiers (no universal-primary dept
        is ever floor-only).
      naming_map_version, source.
    On failure returns (None, "message").
    """
    lister_path = Path(skill_dir) / "scripts" / "list-canonical-departments.py"
    if not lister_path.exists():
        return None, f"deriver not found: {lister_path}"
    try:
        lister = _load_module("list_canonical_departments_guard", lister_path)
        nm = lister.load_naming_map()
        mandatory = lister.get_mandatory(nm)
        universal = lister.get_universal_primaries(nm)
    except SystemExit as exc:
        # load_naming_map() calls sys.exit(1) if the map is missing/unparseable.
        return None, f"list-canonical-departments.py could not load the naming map (exit {exc.code})"
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"error deriving floor via list-canonical-departments.py: {exc}"
    buildable_mandatory = [
        d for d in mandatory if d["id"] not in _FLOOR_ONLY_NONBUILDABLE_IDS
    ]
    derived = {
        "floor": len(mandatory) + len(universal),
        "mandatory": len(mandatory),
        "universal_primary": len(universal),
        "buildable_floor": len(buildable_mandatory) + len(universal),
        "buildable_mandatory": len(buildable_mandatory),
        "naming_map_version": nm.get("version", "unknown"),
        "source": str(Path(skill_dir) / "department-naming-map.json"),
    }
    return derived, None


def _line_of(text, offset):
    return text.count("\n", 0, offset) + 1


# ─────────────────────────────────────────────────────────────────────────────
# Registry evaluation
# ─────────────────────────────────────────────────────────────────────────────
def evaluate(skill_dir, derived):
    """
    Return (checks, load_errors).
      checks:      list of per-assertion result dicts (status OK / MISMATCH / SKIPPED)
      load_errors: list of strings for missing files or unmatched REQUIRED anchors
                   (registry rot) — these force exit 2, distinct from a value drift.
    """
    skill_dir = Path(skill_dir)
    checks = []
    load_errors = []

    for entry in DOC_FLOOR_REGISTRY:
        rel = entry["file"]
        path = skill_dir / rel
        if not path.exists():
            load_errors.append(f"registered file missing: {rel}")
            continue
        text = path.read_text(encoding="utf-8")

        for assertion in entry["assertions"]:
            required = assertion.get("required", True)
            m = assertion["regex"].search(text)
            if m is None:
                if required:
                    load_errors.append(
                        f"{rel}: REQUIRED anchor '{assertion['label']}' no longer "
                        f"matches — the doc was reworded; update DOC_FLOOR_REGISTRY."
                    )
                else:
                    checks.append({
                        "file": rel,
                        "line": None,
                        "label": assertion["label"],
                        "status": "SKIPPED",
                        "detail": "optional anchor absent",
                    })
                continue

            for group_name, derived_key in assertion["groups"].items():
                found = int(m.group(group_name))
                expected = derived[derived_key]
                line = _line_of(text, m.start(group_name))
                status = "OK" if found == expected else "MISMATCH"
                checks.append({
                    "file": rel,
                    "line": line,
                    "label": assertion["label"],
                    "quantity": derived_key,
                    "found": found,
                    "expected": expected,
                    "status": status,
                })

    return checks, load_errors


def main(argv):
    ap = argparse.ArgumentParser(
        description="Assert every registered doc's stated department-floor count "
                    "equals the count derived live from department-naming-map.json."
    )
    ap.add_argument(
        "--skill-dir",
        default=str(Path(__file__).resolve().parent.parent),
        help="Path to the 23-ai-workforce-blueprint skill dir (default: parent of scripts/).",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = ap.parse_args(argv)

    skill_dir = Path(args.skill_dir).resolve()

    derived, err = derive_floor(skill_dir)
    if err:
        if args.json:
            print(json.dumps({"verdict": "ERROR", "error": err, "exit_code": 2}, indent=2))
        else:
            print(f"[FAIL] could not derive canonical floor: {err}", file=sys.stderr)
        return 2

    checks, load_errors = evaluate(skill_dir, derived)
    mismatches = [c for c in checks if c["status"] == "MISMATCH"]

    if load_errors:
        exit_code = 2
        verdict = "ERROR"
    elif mismatches:
        exit_code = 5
        verdict = "FAIL"
    else:
        exit_code = 0
        verdict = "PASS"

    if args.json:
        print(json.dumps({
            "verdict": verdict,
            "derived": derived,
            "registry_files": [e["file"] for e in DOC_FLOOR_REGISTRY],
            "checks": checks,
            "mismatches": mismatches,
            "load_errors": load_errors,
            "exit_code": exit_code,
        }, indent=2))
        return exit_code

    # Human-readable
    d = derived
    print("=" * 72)
    print("Canonical floor DOC/PROSE consistency guard (OQ-7 drift-guard)")
    print("=" * 72)
    print(f"Derived floor (live from naming map v{d['naming_map_version']}): "
          f"{d['floor']}  = {d['mandatory']} mandatory + {d['universal_primary']} universal-primary")
    print(f"Source of truth: {d['source']}")
    print("-" * 72)

    if load_errors:
        print("REGISTRY / LOAD ERRORS (guard cannot run reliably — fix these):", file=sys.stderr)
        for e in load_errors:
            print(f"  ✗ {e}", file=sys.stderr)
        print("", file=sys.stderr)

    if mismatches:
        print("FLOOR-COUNT DRIFT DETECTED — these docs disagree with the derived floor:",
              file=sys.stderr)
        for c in mismatches:
            print(
                f"  ✗ {c['file']}:{c['line']}  [{c['label']}] "
                f"states {c['quantity']}={c['found']} but derived {c['quantity']}={c['expected']}",
                file=sys.stderr,
            )
        print("", file=sys.stderr)
        print("FIX: the department floor is authoritative ONLY in "
              "department-naming-map.json. Update the stale doc prose to match the "
              "derived count (or, better, make it defer to "
              "scripts/list-canonical-departments.py).", file=sys.stderr)

    if not load_errors and not mismatches:
        skipped = [c for c in checks if c["status"] == "SKIPPED"]
        ok = [c for c in checks if c["status"] == "OK"]
        print(f"[PASS] {len(ok)} floor-count assertion(s) across "
              f"{len(DOC_FLOOR_REGISTRY)} registered file(s) agree with the derived floor "
              f"({len(skipped)} optional sentinel(s) absent, skipped).")

    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
