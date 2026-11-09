#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pin_gate.py - the checks behind .github/workflows/sf-prover-pin-gate.yml (Document 3 section 9).

ONE composition, never a second one. Every job below asks `front_door.py` (the writer and the checker of
49-signature-funnel/scripts/SF-PROVER-PIN.sha256) for the file list, the digest routine and the pin rules:
`front_door.pin_files`, `front_door.compute_pin`, `front_door._PIN_SPEC`. Nothing here retypes a glob into
a private list, and nothing here writes the pin. `pin_gate.py` may not mint: the only mint is the `mint`
job of .github/workflows/sf-prover-pin-authority.yml.

Subcommands, one per gate job, each with the exact failure strings of Document 3 lines 1546-1576:

  digest   pin-digest        recompute and compare; on mismatch name every drifted file from the last
                             commit that modified the pin line
  shape    pin-shape         the artifact is exactly one 64-character lowercase hex digest
  coverage pin-coverage      both directions: a file matching a pin rule is composed, and a composed file
                             matches a pin rule
  scope    pin-scope-vouched Branch A: every file whose behaviour the pin is used to vouch for is composed
                             (FIX-16; expected red on the tree measured 2026-11-08 until the composition is
                             widened and re-minted)
  suite    suite             one invocation, one expected count: python3 -m pytest 83-black-friday-launcher -q
                             with 672 collected, 0 failed, 0 errors

Exit status: 0 pass, 1 gate finding, 2 the check could not run (never silently a pass).
# ponytail: coverage re-applies `_PIN_SPEC` by path rather than calling `pin_files` a second time, so it
# catches a glob expansion that silently drops a file and a `pin_files` hand-edit that adds one. A file the
# rules genuinely do not name (e.g. 83-black-friday-launcher/launcher_core/check_rules/*.py today) is a
# composition-widening decision owned by FIX-16/NFX-006, not a gate finding. Upgrade path: when the
# composition is widened, `_PIN_SPEC` changes and this check moves with it, with no edit here.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
import front_door as fd  # noqa: E402  (the single composition; imported, never copied)

SKILL_DIR = _HERE.parents[1]
REPO_ROOT = _HERE.parents[2]
PIN_REL = "49-signature-funnel/scripts/SF-PROVER-PIN.sha256"
EXPECTED_COLLECTED = 672
SUITE_TARGET = "83-black-friday-launcher"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SKIP_WALK = {".git", "__pycache__", ".pytest_cache", "node_modules"}

# FIX-16 Branch A: the behaviour files the pin is used to vouch for. Document 3 line 1558-1566.
SCOPE_GLOBS = (
    "**/copy_forms.py",
    "**/page_role.py",
    "**/shared_page_service.py",
    "**/build_production_request.py",
    "**/references/copy-specs/**/*.json",
)

# front_door's logical name prefix -> (its `_PIN_SPEC` tree key, its repository directory). A logical
# name is `<prefix>/<path inside that tree>`, so this is the only translation the gate needs.
_TREES = (("shared/contract", "contract", "shared-utils/signature_launch_contract"),
          ("shared/launch", "launch", "shared-utils/signature_launch"),
          ("49", "49", "49-signature-funnel"),
          ("83", "83", "83-black-friday-launcher"))


# ---------------------------------------------------------------- helpers

def _composed(skill_dir: Path = SKILL_DIR) -> List[Tuple[str, Path]]:
    """The composition, from the writer/checker itself."""
    return fd.pin_files(Path(skill_dir))


def _split(logical: str) -> Tuple[str, str, str]:
    """`49/scripts/front_door.py` -> (`49`, `49-signature-funnel/scripts/front_door.py`, `scripts/front_door.py`).

    Longest prefix first: `shared/contract` must win over no other candidate, and `49` must not capture a
    name that belongs to `shared/*`.
    """
    for prefix, key, base in _TREES:
        if logical.startswith(prefix + "/"):
            rest = logical[len(prefix) + 1:]
            return key, f"{base}/{rest}", rest
    raise KeyError(f"not a composed tree name: {logical}")


def _repo_rel(logical: str) -> str:
    return _split(logical)[1]


_KEY_PREFIX = {key: prefix for prefix, key, _base in _TREES}


def _glob_re(pattern: str) -> re.Pattern:
    """`**` crosses directories, `*` and `?` do not. Used for the FIX-16 scope globs only."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif pattern.startswith("**", i):
            out.append(".*"); i += 2
        elif pattern[i] == "*":
            out.append("[^/]*"); i += 1
        elif pattern[i] == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(pattern[i])); i += 1
    return re.compile("^" + "".join(out) + "$")


def _walk_files(base: Path):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_WALK)
        for fn in sorted(filenames):
            yield Path(dirpath) / fn


# ---------------------------------------------------------------- jobs

def check_digest(skill_dir: Path = SKILL_DIR) -> int:
    """Recompute the whole-tree digest and compare it to the one line of the pin file."""
    pin_file = Path(skill_dir) / "scripts" / fd.PIN_NAME
    if not pin_file.is_file():
        print(f"PIN-DIGEST NO BASELINE: pin file is missing ({PIN_REL})")
        return 1
    expected = "".join(pin_file.read_text(encoding="utf-8").split())
    computed = fd.compute_pin(Path(skill_dir))
    if expected == computed:
        print(f"PIN-DIGEST OK: {computed} over {len(_composed(skill_dir))} composed files")
        return 0
    print(f"PIN-DIGEST MISMATCH: expected {expected} from {PIN_REL}, computed {computed}")
    return 0 if _name_drift(Path(skill_dir)) == 0 else 1


def _git(args: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _name_drift(skill_dir: Path) -> int:
    """Print one line per differing file against the last commit that modified the pin line."""
    proc = _git(["log", "-1", "--format=%H", "--", PIN_REL], REPO_ROOT)
    base = proc.stdout.strip()
    if proc.returncode != 0 or not base:
        print("PIN-DIGEST NO BASELINE: cannot resolve the commit that last modified the pin; "
              "run the authorised re-mint")
        return 1
    current = {name: fd._sha(path) for name, path in _composed(skill_dir)}
    worktree = Path(tempfile.mkdtemp(prefix="pin-baseline-", dir=str(Path(tempfile.gettempdir()))))
    added = False
    try:
        add = _git(["worktree", "add", "--detach", str(worktree), base], REPO_ROOT)
        if add.returncode != 0:
            print(f"PIN-DIGEST NO BASELINE: cannot read commit {base} ({add.stderr.strip()[:200]}); "
                  "run the authorised re-mint")
            return 1
        added = True
        base_skill = worktree / "49-signature-funnel"
        try:
            baseline = {name: fd._sha(path) for name, path in fd.pin_files(base_skill)}
        except (SystemExit, OSError) as exc:  # a tree that cannot be resolved is not a comparison
            print(f"PIN-DIGEST NO BASELINE: commit {base} has no resolvable composition ({exc}); "
                  "run the authorised re-mint")
            return 1
        drifted = 0
        for name in sorted(set(current) | set(baseline)):
            want, got = baseline.get(name, "absent"), current.get(name, "absent")
            if want != got:
                drifted += 1
                print(f"PIN-DIGEST DRIFTED FILE: {_repo_rel(name)}  expected {want}  actual {got}")
        if drifted:
            print(f"PIN-DIGEST: {drifted} composed file(s) differ from the pin baseline {base[:12]}; "
                  "the authorised re-mint is the only path that fixes this")
        return drifted
    finally:
        if added:
            _git(["worktree", "remove", str(worktree)], REPO_ROOT)
        else:
            try:
                worktree.rmdir()
            except OSError:
                pass


def check_shape(skill_dir: Path = SKILL_DIR) -> int:
    """The artifact holds one digest and nothing else."""
    pin_file = Path(skill_dir) / "scripts" / fd.PIN_NAME
    try:
        raw = pin_file.read_text(encoding="utf-8")
    except OSError:
        print(f"PIN-SHAPE: {PIN_REL} must contain exactly one sha256 line; found 0 lines")
        return 1
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if len(lines) != 1:
        print(f"PIN-SHAPE: {PIN_REL} must contain exactly one sha256 line; found {len(lines)} lines")
        return 1
    value = lines[0].strip()
    if not _HEX64.match(value):
        print(f"PIN-SHAPE: value is not 64 lowercase hex characters: {value}")
        return 1
    print(f"PIN-SHAPE OK: one sha256 line ({len(value)} hex characters)")
    return 0


def _match_rules(key: str, rel: str) -> List[str]:
    """Every `_PIN_SPEC` rule for this tree that names `rel`, as `<subdir>/<glob>` strings.

    A rule is a directory plus a basename glob, exactly as `Path.glob` reads it: `*` never crosses a
    separator, so a file in a subdirectory the rule does not name matches nothing.
    """
    parent, _, name = rel.rpartition("/")
    hits = []
    for _prefix, spec_key, rules in fd._PIN_SPEC:
        if spec_key != key:
            continue
        for sub, pattern in rules:
            if parent == sub and fnmatch.fnmatchcase(name, pattern):
                hits.append(f"{sub}/{pattern}" if sub else pattern)
    return hits


def check_coverage(skill_dir: Path = SKILL_DIR) -> int:
    """Both directions over the composition rules the checker itself uses."""
    skill_dir = Path(skill_dir)
    composed = {name for name, _ in _composed(skill_dir)}
    found = 0
    for _prefix, key, _rules in fd._PIN_SPEC:
        base = fd._skill_dirs(skill_dir)[key]
        for path in _walk_files(base):
            rel = path.relative_to(base).as_posix()
            if fd._is_test(path.name):
                continue
            # A path that a rule names but that cannot be read as a file (a broken symlink, a directory
            # named like a script) is a MISSING finding, not a silent skip: the walker therefore does not
            # filter on readability, and the composition (which requires a readable file) does.
            rules = _match_rules(key, rel)
            logical = f"{_KEY_PREFIX[key]}/{rel}"
            if rules and logical not in composed:
                found += 1
                print(f"PIN-COVERAGE MISSING: {_repo_rel(logical)} matches {rules[0]} but is not in the pin "
                      "composition")
    for name in sorted(composed):
        key, _repo, rel = _split(name)
        if _match_rules(key, rel):
            continue
        found += 1
        print(f"PIN-COVERAGE EXTRA: {_repo_rel(name)} is in the pin composition but matches no "
              "launch-path rule")
    if found:
        print(f"PIN-COVERAGE: {found} finding(s); the composition and the launch-path rules disagree")
        return 1
    print(f"PIN-COVERAGE OK: {len(composed)} composed files, both directions clean")
    return 0


def check_scope(skill_dir: Path = SKILL_DIR) -> int:
    """FIX-16 Branch A: every behaviour file the pin is used to vouch for is part of the composition."""
    composed = {_repo_rel(name) for name, _ in _composed(Path(skill_dir))}
    compiled = [(g, _glob_re(g)) for g in SCOPE_GLOBS]
    gaps = 0
    for path in _walk_files(REPO_ROOT):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for glob, rx in compiled:
            if rx.match(rel) and rel not in composed:
                gaps += 1
                print(f"PIN-SCOPE GAP: {rel} is a launch-path behaviour file (matches {glob}) but is not in "
                      "the pin composition. Add it in the same commit as the authorised re-mint, or narrow "
                      "the claim as FIX-16 Branch B requires.")
    if gaps:
        print(f"PIN-SCOPE: {gaps} behaviour file(s) outside the composition")
        return 1
    print("PIN-SCOPE OK: every FIX-16 Branch A behaviour file is in the pin composition")
    return 0


def _counts(text: str) -> Dict[str, int]:
    """The pytest summary groups: passed, failed, error(s), skipped, xfailed, xpassed."""
    out: Dict[str, int] = {}
    for number, word in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)\b", text):
        key = "error" if word.startswith("error") else word
        out[key] = out.get(key, 0) + int(number)
    return out


def check_suite(repo_root: Path = REPO_ROOT) -> int:
    """One named invocation and one named expected count (Document 3 section 9 job 5)."""
    try:
        import pytest  # noqa: F401
    except ImportError:
        print(f"SUITE RUNNER UNKNOWN: pytest is unavailable or collected nothing; identify the "
              f"repository's runner and pin it in this job before the gate can pass")
        return 2
    proc = subprocess.run([sys.executable, "-m", "pytest", SUITE_TARGET, "-q"], cwd=str(repo_root),
                          capture_output=True, text=True)
    print(proc.stdout)
    if proc.stderr.strip():
        print(proc.stderr, file=sys.stderr)
    counts = _counts(proc.stdout)
    collected = sum(counts.get(k, 0) for k in ("passed", "failed", "error", "skipped", "xfailed", "xpassed"))
    if proc.returncode == 5 or collected == 0:
        print("SUITE RUNNER UNKNOWN: pytest is unavailable or collected nothing; identify the "
              "repository's runner and pin it in this job before the gate can pass")
        return 2
    failed, errors = counts.get("failed", 0), counts.get("error", 0)
    if failed or errors:
        print(f"SUITE RED: {failed} failed, {errors} errors — a re-mint over red bytes is a forgery")
        return 1
    if collected != EXPECTED_COLLECTED:
        print(f"SUITE COUNT MISMATCH: expected {EXPECTED_COLLECTED} collected, got {collected}; "
              "re-baseline in the same commit that changes the count, with the measured number in the "
              "commit message")
        return 1
    print(f"SUITE OK: {collected} collected, 0 failed, 0 errors")
    return 0


CHECKS = {"digest": check_digest, "shape": check_shape, "coverage": check_coverage,
          "scope": check_scope, "suite": check_suite}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="pin_gate.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("check", choices=sorted(CHECKS))
    ap.add_argument("--skill-dir", default=str(SKILL_DIR),
                    help="the Skill 49 directory to check (default: this checkout's)")
    ap.add_argument("--repo-root", default=str(REPO_ROOT), help="checkout root (default: this checkout's)")
    a = ap.parse_args(argv)
    if a.check == "suite":
        return check_suite(Path(a.repo_root))
    return CHECKS[a.check](Path(a.skill_dir))


if __name__ == "__main__":
    raise SystemExit(main())
