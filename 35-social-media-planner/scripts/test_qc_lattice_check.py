#!/usr/bin/env python3
"""test_qc_lattice_check.py - U130 mutation-proof test suite."""
from __future__ import annotations
import os, stat, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILURES = []

def check(label, cond, detail=""):
    if cond: print(f"  PASS: {label}")
    else: print(f"  FAIL: {label}" + (f" - {detail}" if detail else "")); FAILURES.append(label)

def _write_script(tmp, name, content):
    p = tmp / name; p.write_text(content, encoding="utf-8"); p.chmod(p.stat().st_mode | stat.S_IEXEC); return p

def _run_script(script, cwd=None):
    return subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=15, cwd=str(cwd) if cwd else None, env={**os.environ, "TESTING": "1"})

GUARDED_LOGIC = r'''#!/usr/bin/env bash
set -u
PASS=0; FAIL=0; SKIP=0
REPO_ROOT_LATTICE="$(cd "$(dirname "$0")/.." && pwd)"
LATTICE_CHECKER="$REPO_ROOT_LATTICE/docs/tools/check_lattice_citation.py"
if [ -f "$LATTICE_CHECKER" ]; then
  echo "GUARD:PASS_PATH"
  PASS=$((PASS+1))
else
  echo "GUARD:SKIP_PATH checker not present in this layout (docs/tools/check_lattice_citation.py not found under $REPO_ROOT_LATTICE; installed-skill layout, not a repo checkout)"
  SKIP=$((SKIP+1))
fi
echo "SKIP=$SKIP"
echo "PASS=$PASS"
exit 0
'''

UNGUARDED_LOGIC = r'''#!/usr/bin/env bash
set -u
PASS=0; FAIL=0; SKIP=0
REPO_ROOT_LATTICE="$(cd "$(dirname "$0")/.." && pwd)"
LATTICE_CHECKER="$REPO_ROOT_LATTICE/docs/tools/check_lattice_citation.py"
echo "GUARD:UNGUARDED_HARD_ASSERT"
python3 "$LATTICE_CHECKER" --repo-root "$REPO_ROOT_LATTICE" --skill 35-social-media-planner -q 2>/dev/null
RC=$?
if [ $RC -eq 0 ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi
echo "RC=$RC"
echo "SKIP=$SKIP"
echo "PASS=$PASS"
echo "FAIL=$FAIL"
exit $RC
'''

REAL_GUARDED = r'''#!/usr/bin/env bash
set -u
PASS=0; FAIL=0; WARN=0; SKIP=0
red(){ printf "\033[31m%s\033[0m\n" "$1"; }
green(){ printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  PASS - $1"; PASS=$((PASS+1)); else red "  FAIL - $1"; FAIL=$((FAIL+1)); fi; }
REPO_ROOT_LATTICE="$(cd "$(dirname "$0")/.." && pwd)"
LATTICE_CHECKER="$REPO_ROOT_LATTICE/docs/tools/check_lattice_citation.py"
if [ -f "$LATTICE_CHECKER" ]; then
  assert "lattice cites hold" "python3 \"$LATTICE_CHECKER\" --repo-root \"$REPO_ROOT_LATTICE\" --skill 35-social-media-planner -q"
else
  echo "  SKIP: checker not present (installed-skill layout)"
  SKIP=$((SKIP+1))
fi
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
exit 0
'''

REAL_UNGUARDED = r'''#!/usr/bin/env bash
set -u
PASS=0; FAIL=0; WARN=0; SKIP=0
red(){ printf "\033[31m%s\033[0m\n" "$1"; }
green(){ printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  PASS - $1"; PASS=$((PASS+1)); else red "  FAIL - $1"; FAIL=$((FAIL+1)); fi; }
REPO_ROOT_LATTICE="$(cd "$(dirname "$0")/.." && pwd)"
LATTICE_CHECKER="$REPO_ROOT_LATTICE/docs/tools/check_lattice_citation.py"
assert "lattice cites hold" "python3 \"$LATTICE_CHECKER\" --repo-root \"$REPO_ROOT_LATTICE\" --skill 35-social-media-planner -q 2>/dev/null"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
exit 0
'''

def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        print("=== Case A: Repo-checkout layout ===")
        repo_root = tmp / "repo"
        (repo_root / "docs" / "tools").mkdir(parents=True)
        (repo_root / "35-social-media-planner").mkdir(parents=True)
        checker = repo_root / "docs" / "tools" / "check_lattice_citation.py"
        checker.write_text("#!/usr/bin/env python3\nimport sys; print('ok'); sys.exit(0)\n")
        checker.chmod(checker.stat().st_mode | stat.S_IEXEC)
        ga = _write_script(repo_root / "35-social-media-planner", "qc_test.sh", GUARDED_LOGIC)
        ra = _run_script(ga, cwd=repo_root / "35-social-media-planner")
        check("A1: GUARD:PASS_PATH", "GUARD:PASS_PATH" in ra.stdout, ra.stdout)
        check("A2: SKIP=0", "SKIP=0" in ra.stdout, ra.stdout)
        check("A3: PASS=1", "PASS=1" in ra.stdout, ra.stdout)
        check("A4: exit 0", ra.returncode == 0, str(ra.returncode))

        print("\n=== Case B: Installed-copy layout ===")
        installed_root = tmp / "installed" / ".openclaw" / "skills"
        skill_dir_b = installed_root / "35-social-media-planner"
        skill_dir_b.mkdir(parents=True)
        gb = _write_script(skill_dir_b, "qc_test.sh", GUARDED_LOGIC)
        rb = _run_script(gb, cwd=skill_dir_b)
        check("B1: GUARD:SKIP_PATH", "GUARD:SKIP_PATH" in rb.stdout, rb.stdout)
        check("B2: installed-skill layout", "installed-skill layout" in rb.stdout, rb.stdout)
        check("B3: SKIP=1", "SKIP=1" in rb.stdout, rb.stdout)
        check("B4: PASS=0", "PASS=0" in rb.stdout, rb.stdout)
        check("B5: exit 0", rb.returncode == 0, str(rb.returncode))

        print("\n=== Mutation proof: UNGUARDED on installed copy ===")
        ug = _write_script(skill_dir_b, "qc_unguarded.sh", UNGUARDED_LOGIC)
        ru = _run_script(ug, cwd=skill_dir_b)
        check("M1: unguarded exits non-zero", ru.returncode != 0, f"rc={ru.returncode}")
        check("M2: UNGUARDED_HARD_ASSERT", "UNGUARDED_HARD_ASSERT" in ru.stdout, ru.stdout)
        check("M3: FAIL=1", "FAIL=1" in ru.stdout, ru.stdout)
        check("M4: SKIP=0", "SKIP=0" in ru.stdout, ru.stdout)

        print("\n=== Re-verify GREEN ===")
        rr = _run_script(gb, cwd=skill_dir_b)
        check("R1: GUARD:SKIP_PATH", "GUARD:SKIP_PATH" in rr.stdout, rr.stdout)
        check("R2: SKIP=1", "SKIP=1" in rr.stdout, rr.stdout)
        check("R3: exit 0", rr.returncode == 0, str(rr.returncode))

        print("\n=== Edge: empty checker file ===")
        edge_root = tmp / "edge_empty"
        (edge_root / "docs" / "tools").mkdir(parents=True)
        (edge_root / "35-social-media-planner").mkdir(parents=True)
        ec = edge_root / "docs" / "tools" / "check_lattice_citation.py"
        ec.write_text(""); ec.chmod(0o644)
        es = _write_script(edge_root / "35-social-media-planner", "qc_test.sh", GUARDED_LOGIC)
        re2 = _run_script(es, cwd=edge_root / "35-social-media-planner")
        check("E1: GUARD:PASS_PATH", "GUARD:PASS_PATH" in re2.stdout, re2.stdout)
        check("E2: SKIP=0", "SKIP=0" in re2.stdout, re2.stdout)

        print("\n=== Edge: checker is directory ===")
        dir_root = tmp / "edge_dir"
        (dir_root / "docs" / "tools").mkdir(parents=True)
        (dir_root / "35-social-media-planner").mkdir(parents=True)
        (dir_root / "docs" / "tools" / "check_lattice_citation.py").mkdir()
        ds = _write_script(dir_root / "35-social-media-planner", "qc_test.sh", GUARDED_LOGIC)
        rd = _run_script(ds, cwd=dir_root / "35-social-media-planner")
        check("D1: GUARD:SKIP_PATH", "GUARD:SKIP_PATH" in rd.stdout, rd.stdout)
        check("D2: SKIP=1", "SKIP=1" in rd.stdout, rd.stdout)

        print("\n=== Integration mutation proof ===")
        real_qc = HERE.parent / "qc-skill35.sh"
        assert real_qc.exists(), f"not found: {real_qc}"
        original = real_qc.read_text(encoding="utf-8")
        check("I1: guard present", 'if [ -f "$LATTICE_CHECKER" ]; then' in original)
        iu = _write_script(skill_dir_b, "qc_int_unguarded.sh", REAL_UNGUARDED)
        riu = _run_script(iu, cwd=skill_dir_b)
        check("I2: unguarded FAIL=1 (RED)", "FAIL=1" in riu.stdout, f"stdout={riu.stdout!r}")
        check("I3: unguarded SKIP=0", "SKIP=0" in riu.stdout, f"stdout={riu.stdout!r}")
        ig = _write_script(skill_dir_b, "qc_int_guarded.sh", REAL_GUARDED)
        rig = _run_script(ig, cwd=skill_dir_b)
        check("I4: guarded SKIP=1 (GREEN)", "SKIP=1" in rig.stdout, f"stdout={rig.stdout!r}")
        check("I5: guarded FAIL=0", "FAIL=0" in rig.stdout, f"stdout={rig.stdout!r}")
        check("I6: guarded exit 0", rig.returncode == 0, str(rig.returncode))
        check("I7: guard intact", 'if [ -f "$LATTICE_CHECKER" ]; then' in original)
        check("I8: SKIP=0 init", "SKIP=0" in original)
        check("I9: SKIP+=1", "SKIP=$((SKIP+1))" in original)

    print()
    if FAILURES:
        print(f"test_qc_lattice_check: {len(FAILURES)} FAILURE(S):")
        for f in FAILURES: print(f"  - {f}")
        return 1
    print("test_qc_lattice_check: ALL CASES PASSED (guard + skip + mutation proof + edge cases)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
