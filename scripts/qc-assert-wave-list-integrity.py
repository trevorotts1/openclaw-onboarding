#!/usr/bin/env python3
"""qc-assert-wave-list-integrity.py — every wave-list entry must be a real skill.

WHY THIS EXISTS
---------------
`lib-onboarding-state.sh` defines the canonical five install waves
(`OC_WAVE1_SKILLS` .. `OC_WAVE5_SKILLS`). A wave passes only when every skill it
names satisfies the per-wave goal, and goal condition (b) is:

    (b) Each skill's folder is present on disk in $OC_SKILLS_DIR

So a wave list that names a folder which does not exist can NEVER pass. Not on a
slow box, not on a healthy box, not ever — and the onboarding watchdog re-fires
and takes a strike on every cycle, forever, on every box in the fleet.

That is not hypothetical. v12.26.0 (commit 0e53c677) archived skill 11
(SuperDesign) and skill 21 (Tavily Search) by renaming their folders to
`11-superdesign-ARCHIVED` / `21-tavily-search-ARCHIVED`. That commit updated
README.md, install.sh, update-skills.sh, cc-compat.json, the version markers and
the CHANGELOG — and CHANGELOG.md even recorded the intended outcome:

    "Install waves updated: Wave 2 drops from 11 to 10 skills (11-superdesign
     removed); Wave 3 drops from 15 to 14 skills (21-tavily-search removed)."

...but it never touched `lib-onboarding-state.sh`. The wave lists kept naming
`11-superdesign` and `21-tavily-search`, folders that had ceased to exist, and
Wave 2 and Wave 3 were wedged fleet-wide from that commit until this gate landed.
Nothing noticed, because the only CI check on the wave lists (qc-static.yml
"PRD-2.13") asserted that the *variable names* were present as substrings — never
that their *contents* resolved to anything real.

WHAT THIS GATE ENFORCES
-----------------------
  1. Every name in every OC_WAVE<N>_SKILLS list resolves to a real directory at
     the repo root.
  2. No wave list names an ARCHIVED skill — neither directly (a name ending in
     `-ARCHIVED`) nor by the exact drift signature above (name `X` is absent but
     `X-ARCHIVED` exists, i.e. the skill was retired and the list was not updated).
  3. No skill is listed twice, within a wave or across waves.
  4. The duplicated wave lists hardcoded in the watchdog prompts
     (`scripts/watchdog-onboarding-loop.sh`) match the canonical lists exactly.
     The watchdog carried its own copy of Wave 2 and Wave 3, and that copy drifted
     in lockstep with the canonical one; a second copy is a second thing to rot.

Exit codes:
  0  — every wave-list entry resolves to a real, non-archived skill directory
  1  — INVARIANT VIOLATED
  2  — environment error (inputs not found / unparseable)

Usage:
  python3 scripts/qc-assert-wave-list-integrity.py             # scan repo root
  python3 scripts/qc-assert-wave-list-integrity.py --root DIR  # scan DIR
  python3 scripts/qc-assert-wave-list-integrity.py --self-test # embedded tests

Wired into:
  - .github/workflows/wave-list-integrity-guard.yml (push/PR)
  - .github/workflows/qc-static.yml ("PRD-2.13", tightened to call this gate)

v1.0.0
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

LIB_REL = "lib-onboarding-state.sh"
WATCHDOG_REL = "scripts/watchdog-onboarding-loop.sh"

WAVE_RE = re.compile(r'^OC_WAVE([1-5])_SKILLS="([^"]*)"', re.MULTILINE)
CASE_RE = re.compile(r'^\s*([1-5])\)\s*prompt="(.*)"\s*;;\s*$', re.MULTILINE)
# A skill folder reference: two digits, a dash, then a lowercase slug.
SKILL_TOKEN_RE = re.compile(r"\b(\d{2}-[a-z][a-z0-9]*(?:-[a-z0-9]+)*)\b")

ARCHIVED_SUFFIX = "-ARCHIVED"


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def parse_wave_lists(lib_text: str) -> dict[int, list[str]]:
    """Extract OC_WAVE<N>_SKILLS assignments from lib-onboarding-state.sh."""
    waves: dict[int, list[str]] = {}
    for num, body in WAVE_RE.findall(lib_text):
        waves[int(num)] = body.split()
    return waves


def parse_watchdog_lists(watchdog_text: str) -> dict[int, list[str]]:
    """Extract the skill names hardcoded in each watchdog wave prompt.

    The prompts are prose, so we scan each `case` branch for folder-shaped
    tokens (`NN-slug`) rather than trying to parse the sentence structure.
    """
    lists: dict[int, list[str]] = {}
    for num, prompt in CASE_RE.findall(watchdog_text):
        found: list[str] = []
        for tok in SKILL_TOKEN_RE.findall(prompt):
            if tok not in found:
                found.append(tok)
        lists[int(num)] = found
    return lists


def check(root: str) -> int:
    lib_path = os.path.join(root, LIB_REL)
    watchdog_path = os.path.join(root, WATCHDOG_REL)

    if not os.path.isfile(lib_path):
        print(f"ENVIRONMENT: {LIB_REL} not found under {root}")
        return 2

    with open(lib_path, encoding="utf-8") as fh:
        lib_text = fh.read()

    waves = parse_wave_lists(lib_text)
    if not waves:
        print(f"ENVIRONMENT: no OC_WAVE<N>_SKILLS assignments parsed from {LIB_REL}")
        return 2
    missing_waves = [n for n in range(1, 6) if n not in waves]
    if missing_waves:
        print(f"ENVIRONMENT: wave list(s) not parsed: {missing_waves}")
        return 2

    fail = 0
    seen: dict[str, int] = {}

    print("== wave-list entries resolve to real skill directories ==")
    for num in sorted(waves):
        entries = waves[num]
        if not entries:
            _fail(f"Wave {num}: list is empty")
            fail = 1
            continue
        for entry in entries:
            label = f"Wave {num}: {entry}"

            if entry in seen:
                _fail(f"{label} — duplicate, already listed in Wave {seen[entry]}")
                fail = 1
                continue
            seen[entry] = num

            if entry.endswith(ARCHIVED_SUFFIX):
                _fail(
                    f"{label} — ARCHIVED skills must NOT be installed by a wave. "
                    f"Remove it from OC_WAVE{num}_SKILLS."
                )
                fail = 1
                continue

            path = os.path.join(root, entry)
            if os.path.isdir(path):
                _ok(label)
                continue

            fail = 1
            if os.path.isdir(path + ARCHIVED_SUFFIX):
                _fail(
                    f"{label} — folder does not exist; it was ARCHIVED to "
                    f"'{entry}{ARCHIVED_SUFFIX}'. Wave {num} can NEVER pass while this "
                    f"entry stands (goal condition (b): folder present on disk). "
                    f"Remove it from OC_WAVE{num}_SKILLS."
                )
            else:
                _fail(
                    f"{label} — folder does not exist at repo root. Wave {num} can "
                    f"NEVER pass while this entry stands (goal condition (b): folder "
                    f"present on disk). Fix the name or remove the entry."
                )

    print("== watchdog prompt lists match the canonical wave lists ==")
    if not os.path.isfile(watchdog_path):
        print(f"ENVIRONMENT: {WATCHDOG_REL} not found under {root}")
        return 2

    with open(watchdog_path, encoding="utf-8") as fh:
        watchdog_lists = parse_watchdog_lists(fh.read())

    if not watchdog_lists:
        print(f"ENVIRONMENT: no wave prompts parsed from {WATCHDOG_REL}")
        return 2

    for num in sorted(waves):
        if num not in watchdog_lists:
            _fail(f"Wave {num}: no watchdog prompt found for this wave")
            fail = 1
            continue
        canonical = set(waves[num])
        actual = set(watchdog_lists[num])
        if canonical == actual:
            _ok(f"Wave {num}: watchdog prompt lists the same {len(canonical)} skills")
            continue
        fail = 1
        extra = sorted(actual - canonical)
        absent = sorted(canonical - actual)
        detail = []
        if extra:
            detail.append(f"names the watchdog has but the wave list does not: {extra}")
        if absent:
            detail.append(f"names the wave list has but the watchdog does not: {absent}")
        _fail(
            f"Wave {num}: watchdog prompt has drifted from OC_WAVE{num}_SKILLS — "
            + "; ".join(detail)
        )

    if fail:
        print("\nWAVE-LIST INTEGRITY: FAIL")
        print(
            "A wave whose list names a folder that does not exist can never pass on "
            "any box, and the onboarding watchdog takes a strike every cycle."
        )
    else:
        total = sum(len(v) for v in waves.values())
        print(f"\nWAVE-LIST INTEGRITY: PASS ({total} entries across {len(waves)} waves)")
    return fail


# ---------------------------------------------------------------------------
# Embedded self-test: proves the gate FAILS on a phantom entry and PASSES clean.
# ---------------------------------------------------------------------------

_LIB_TMPL = '''#!/usr/bin/env bash
# fixture
OC_WAVE1_SKILLS="{w1}"
OC_WAVE2_SKILLS="{w2}"
OC_WAVE3_SKILLS="{w3}"
OC_WAVE4_SKILLS="{w4}"
OC_WAVE5_SKILLS="{w5}"
'''

_WATCHDOG_TMPL = '''#!/usr/bin/env bash
build_wave_prompt() {{
  case "$1" in
    1) prompt="[W] Wave 1 skills: {w1c}. DO THIS NOW: install them." ;;
    2) prompt="[W] Wave 2 skills: {w2c}. DO THIS NOW: install them." ;;
    3) prompt="[W] Wave 3 skills: {w3c}. DO THIS NOW: install them." ;;
    4) prompt="[W] Wave 4 skills: {w4c}. DO THIS NOW: install them." ;;
    5) prompt="[W] Wave 5 skills: {w5c}. DO THIS NOW: install them." ;;
  esac
}}
'''


def _build_fixture(tmp: str, waves: dict[int, list[str]], dirs: list[str],
                   watchdog: dict[int, list[str]] | None = None) -> str:
    root = tempfile.mkdtemp(dir=tmp)
    os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
    for d in dirs:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    with open(os.path.join(root, LIB_REL), "w", encoding="utf-8") as fh:
        fh.write(_LIB_TMPL.format(**{f"w{n}": " ".join(waves.get(n, [])) for n in range(1, 6)}))
    wd = watchdog if watchdog is not None else waves
    with open(os.path.join(root, WATCHDOG_REL), "w", encoding="utf-8") as fh:
        fh.write(_WATCHDOG_TMPL.format(
            **{f"w{n}c": ", ".join(wd.get(n, [])) for n in range(1, 6)}))
    return root


def self_test() -> int:
    tmp = tempfile.mkdtemp(prefix="wave-list-selftest-")
    failures = 0
    try:
        base = {
            1: ["01-alpha"], 2: ["02-bravo"], 3: ["03-charlie"],
            4: ["04-delta"], 5: ["05-echo"],
        }
        all_dirs = ["01-alpha", "02-bravo", "03-charlie", "04-delta", "05-echo"]

        cases: list[tuple[str, dict[int, list[str]], list[str], dict | None, int]] = [
            ("clean lists pass", base, all_dirs, None, 0),
            (
                "PHANTOM entry (listed skill has no folder at all) fails",
                {**base, 2: ["02-bravo", "11-superdesign"]},
                all_dirs, None, 1,
            ),
            (
                "ARCHIVE-DRIFT entry (folder renamed to -ARCHIVED) fails",
                {**base, 3: ["03-charlie", "21-tavily-search"]},
                all_dirs + ["21-tavily-search-ARCHIVED"], None, 1,
            ),
            (
                "entry naming an -ARCHIVED folder directly fails",
                {**base, 2: ["02-bravo", "11-superdesign-ARCHIVED"]},
                all_dirs + ["11-superdesign-ARCHIVED"], None, 1,
            ),
            (
                "duplicate entry across waves fails",
                {**base, 3: ["03-charlie", "02-bravo"]},
                all_dirs, None, 1,
            ),
            (
                "watchdog prompt drifted from canonical list fails",
                base, all_dirs,
                {**base, 2: ["02-bravo", "99-ghost"]}, 1,
            ),
        ]

        for name, waves, dirs, watchdog, expected in cases:
            root = _build_fixture(tmp, waves, dirs, watchdog)
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--root", root],
                capture_output=True, text=True,
            )
            got = proc.returncode
            if got == expected:
                print(f"  ✓ self-test: {name} (exit {got})")
            else:
                print(f"  ✗ self-test: {name} — expected exit {expected}, got {got}")
                print("      ---- gate output ----")
                for line in proc.stdout.splitlines():
                    print(f"      {line}")
                failures += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(f"\nSELF-TEST: FAIL ({failures} case(s))")
        return 1
    print("\nSELF-TEST: PASS (gate fails on phantom/archived/duplicate/drift, passes clean)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=None, help="repo root to scan")
    ap.add_argument("--self-test", action="store_true", help="run embedded tests")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return check(root)


if __name__ == "__main__":
    sys.exit(main())
