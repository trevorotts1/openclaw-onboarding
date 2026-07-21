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
  4. The watchdog prompts (`scripts/watchdog-onboarding-loop.sh`) carry NO second
     copy of the lists at all. The watchdog used to re-type each wave's roster as
     prose; that copy drifted in lockstep with the canonical one, because two
     hand-maintained lists agree only until someone edits one of them. This gate
     originally compared the two copies for equality. Comparing is weaker than
     making a second copy impossible, so the watchdog now interpolates
     `${OC_WAVE<N>_SKILLS}` and this check enforces that structurally:
       4a. every wave prompt must interpolate its own OC_WAVE<N>_SKILLS variable;
       4b. no wave prompt may contain a hardcoded `NN-slug` skill token.
     Drift is then not "detected" — it is unrepresentable.

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

N_WAVES = 6

WAVE_RE = re.compile(r'^OC_WAVE([1-6])_SKILLS="([^"]*)"', re.MULTILINE)
CASE_RE = re.compile(r'^\s*([1-6])\)\s*prompt="(.*)"\s*;;\s*$', re.MULTILINE)
# A skill folder reference: two digits, a dash, then a lowercase slug.
SKILL_TOKEN_RE = re.compile(r"\b(\d{2}-[a-z][a-z0-9]*(?:-[a-z0-9]+)*)\b")
# The single-source interpolation each watchdog wave prompt must use, and the
# indirect expansion that binds it to the canonical OC_WAVE<N>_SKILLS lists.
ROSTER_PLACEHOLDER = "${_roster}"
INDIRECT_EXPANSION = 'OC_WAVE${wave}_SKILLS'

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


def parse_watchdog_prompts(watchdog_text: str) -> dict[int, str]:
    """Extract the prose prompt for each wave branch of build_wave_prompt."""
    return {int(num): prompt for num, prompt in CASE_RE.findall(watchdog_text)}


def hardcoded_skill_tokens(prompt: str) -> list[str]:
    """Folder-shaped tokens (`NN-slug`) literally typed into a watchdog prompt."""
    found: list[str] = []
    for tok in SKILL_TOKEN_RE.findall(prompt):
        if tok not in found:
            found.append(tok)
    return found


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
    missing_waves = [n for n in range(1, N_WAVES + 1) if n not in waves]
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

    print("== watchdog prompts carry no second copy of the wave lists ==")
    if not os.path.isfile(watchdog_path):
        print(f"ENVIRONMENT: {WATCHDOG_REL} not found under {root}")
        return 2

    with open(watchdog_path, encoding="utf-8") as fh:
        watchdog_text = fh.read()
    watchdog_prompts = parse_watchdog_prompts(watchdog_text)

    if not watchdog_prompts:
        print(f"ENVIRONMENT: no wave prompts parsed from {WATCHDOG_REL}")
        return 2

    # The roster must be resolved FROM the canonical variable, by indirect
    # expansion on the wave number. Without this line the prompts could
    # interpolate an unrelated (or empty) variable and still look clean.
    if INDIRECT_EXPANSION in watchdog_text:
        _ok(f"watchdog resolves its roster from {INDIRECT_EXPANSION} (single source)")
    else:
        _fail(
            f"watchdog does not derive its roster from the canonical lists — "
            f"expected the indirect expansion '{INDIRECT_EXPANSION}' in "
            f"{WATCHDOG_REL}. Without it the prompts are a second, "
            f"hand-maintained copy that will drift."
        )
        fail = 1

    for num in sorted(waves):
        if num not in watchdog_prompts:
            _fail(f"Wave {num}: no watchdog prompt found for this wave")
            fail = 1
            continue
        prompt = watchdog_prompts[num]

        # 4a — the prompt must interpolate the roster rather than list skills.
        if ROSTER_PLACEHOLDER not in prompt:
            _fail(
                f"Wave {num}: watchdog prompt does not interpolate "
                f"'{ROSTER_PLACEHOLDER}' — it must render the canonical "
                f"OC_WAVE{num}_SKILLS list, not restate it."
            )
            fail = 1
            continue

        # 4b — and it must not restate any skill name literally.
        hardcoded = hardcoded_skill_tokens(prompt)
        if hardcoded:
            _fail(
                f"Wave {num}: watchdog prompt hardcodes skill name(s) {hardcoded} — "
                f"a second copy of the wave list. Delete them; "
                f"'{ROSTER_PLACEHOLDER}' already renders OC_WAVE{num}_SKILLS."
            )
            fail = 1
            continue

        _ok(
            f"Wave {num}: watchdog prompt renders OC_WAVE{num}_SKILLS "
            f"({len(waves[num])} skills) with no hardcoded copy"
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

_LIB_TMPL = "#!/usr/bin/env bash\n# fixture\n" + "".join(
    'OC_WAVE%d_SKILLS="{w%d}"\n' % (n, n) for n in range(1, N_WAVES + 1)
)

# A compliant watchdog: resolves the roster by indirect expansion, then
# interpolates it. No wave list is ever re-typed.
_WATCHDOG_HEAD = '''#!/usr/bin/env bash
build_wave_prompt() {{
  local wave="$1"
  local _roster_var="OC_WAVE${{wave}}_SKILLS"
  local _roster="${{!_roster_var:-}}"
  _roster="${{_roster// /, }}"
  case "$wave" in
'''
_WATCHDOG_TAIL = '''  esac
}}
'''


def _build_fixture(tmp: str, waves: dict[int, list[str]], dirs: list[str],
                   watchdog: dict[int, list[str]] | None = None,
                   omit_indirect: bool = False) -> str:
    """Build a fixture repo.

    `watchdog` (when given) HARDCODES those skill names into the wave prompts —
    i.e. it reintroduces the second copy this gate forbids. `omit_indirect`
    drops the indirect expansion that binds the roster to the canonical lists.
    """
    root = tempfile.mkdtemp(dir=tmp)
    os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
    for d in dirs:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    with open(os.path.join(root, LIB_REL), "w", encoding="utf-8") as fh:
        fh.write(_LIB_TMPL.format(
            **{f"w{n}": " ".join(waves.get(n, [])) for n in range(1, N_WAVES + 1)}))

    head = _WATCHDOG_HEAD
    if omit_indirect:
        head = head.replace('"OC_WAVE${{wave}}_SKILLS"', '"SOME_OTHER_LIST"')
    body = head.format()
    for n in range(1, N_WAVES + 1):
        if watchdog is not None and n in watchdog:
            roster = ", ".join(watchdog[n])          # the forbidden second copy
        else:
            roster = "${_roster}"
        body += f'    {n}) prompt="[W] Wave {n} skills: {roster}. DO THIS NOW: install them." ;;\n'
    body += _WATCHDOG_TAIL.format()
    with open(os.path.join(root, WATCHDOG_REL), "w", encoding="utf-8") as fh:
        fh.write(body)
    return root


def self_test() -> int:
    tmp = tempfile.mkdtemp(prefix="wave-list-selftest-")
    failures = 0
    try:
        base = {
            1: ["01-alpha"], 2: ["02-bravo"], 3: ["03-charlie"],
            4: ["04-delta"], 5: ["05-echo"], 6: ["06-foxtrot"],
        }
        all_dirs = ["01-alpha", "02-bravo", "03-charlie", "04-delta", "05-echo",
                    "06-foxtrot"]

        cases: list[tuple[str, dict[int, list[str]], list[str], dict | None, bool, int]] = [
            ("clean lists pass", base, all_dirs, None, False, 0),
            (
                "PHANTOM entry (listed skill has no folder at all) fails",
                {**base, 2: ["02-bravo", "11-superdesign"]},
                all_dirs, None, False, 1,
            ),
            (
                "ARCHIVE-DRIFT entry (folder renamed to -ARCHIVED) fails",
                {**base, 3: ["03-charlie", "21-tavily-search"]},
                all_dirs + ["21-tavily-search-ARCHIVED"], None, False, 1,
            ),
            (
                "entry naming an -ARCHIVED folder directly fails",
                {**base, 2: ["02-bravo", "11-superdesign-ARCHIVED"]},
                all_dirs + ["11-superdesign-ARCHIVED"], None, False, 1,
            ),
            (
                "duplicate entry across waves fails",
                {**base, 3: ["03-charlie", "02-bravo"]},
                all_dirs, None, False, 1,
            ),
            (
                "PHANTOM entry in the new Wave 6 fails",
                {**base, 6: ["06-foxtrot", "77-nonexistent"]},
                all_dirs, None, False, 1,
            ),
            (
                "watchdog re-typing a wave list (second copy) fails",
                base, all_dirs, {2: ["02-bravo"]}, False, 1,
            ),
            (
                "watchdog re-typing a list that MATCHES canonical still fails "
                "(a correct second copy is still a second copy)",
                base, all_dirs, {3: ["03-charlie"]}, False, 1,
            ),
            (
                "watchdog roster not bound to OC_WAVE<N>_SKILLS fails",
                base, all_dirs, None, True, 1,
            ),
        ]

        for name, waves, dirs, watchdog, omit_indirect, expected in cases:
            root = _build_fixture(tmp, waves, dirs, watchdog, omit_indirect)
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
