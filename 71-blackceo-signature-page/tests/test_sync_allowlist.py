#!/usr/bin/env python3
"""Pin the Item 27 sync classification for the onb_only guard module.

The allowlist (repo-integration/skill71-sync-allowlist.json) classifies
files by glob, and the parity checker's classify() matches those globs
against each file's FULL relative path. The onb_only entry for the
onboarding-only guard module originally carried the bare file name
("two_strike_adapter.py") while the file's real path in the skill tree
is "scripts/two_strike_adapter.py", so the entry matched nothing: the
file classified neutral, the sync treated it as copyable, and the
sync's onb_only refusal never engaged for the real path.

These tests pin the cured behavior. They never import or execute
scripts/two_strike_adapter.py; the checker is loaded by path exactly
the way the sync engine loads it.
"""
import fnmatch
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent

_spec = importlib.util.spec_from_file_location(
    "check_skill71_parity", REPO_ROOT / "scripts" / "check-skill71-parity.py")
_parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_parity)
classify = _parity.classify

CLASSES = json.loads(
    (ROOT / _parity.ALLOWLIST_REL).read_text(encoding="utf-8"))["classes"]

REAL_REL = "scripts/two_strike_adapter.py"


def test_two_strike_real_path_classifies_onb_only():
    got = classify(REAL_REL, CLASSES)
    assert got == "onb_only", f"classify({REAL_REL!r}) = {got!r}, want 'onb_only'"


def test_onb_only_globs_match_the_real_tree_file():
    globs = CLASSES["onb_only"]["globs"]
    real = [str(p.relative_to(ROOT)) for p in ROOT.rglob("two_strike_adapter.py")
            if p.is_file() and "__pycache__" not in p.parts]
    if not real and ROOT.parents[1].name == ".claude":
        # 999 edition: onb_only means the file must be ABSENT here (the
        # parity checker fails if it is present), so the absence is the pass.
        return
    assert real, "no two_strike_adapter.py found in the skill tree"
    for rel in real:
        assert classify(rel, CLASSES) == "onb_only", \
            f"real tree file {rel!r} does not classify onb_only"
    for g in globs:
        assert any(fnmatch.fnmatch(rel, g) for rel in real), \
            f"onb_only glob {g!r} matches no real tree file {real}"


def test_sync_refusal_path_engages():
    # The sync engine refuses while (nine_skill / glob) is a file for any
    # onb_only glob. Reproduce that exact check against a fixture 999
    # skill tree carrying the file at its real path.
    globs = CLASSES["onb_only"]["globs"]
    with tempfile.TemporaryDirectory() as td:
        nine_skill = Path(td)
        target = nine_skill / REAL_REL
        target.parent.mkdir(parents=True)
        target.write_text("# fixture path only; never executed\n", encoding="utf-8")
        assert any((nine_skill / g).is_file() for g in globs), \
            "sync onb_only refusal would NOT engage for the real path"
    with tempfile.TemporaryDirectory() as td:
        nine_skill = Path(td)
        assert not any((nine_skill / g).is_file() for g in globs), \
            "sync onb_only refusal fired against an empty 999 tree"


def test_representative_neutral_still_neutral():
    for rel in ("scripts/stage_gate.py", "references/stage-contract.json"):
        got = classify(rel, CLASSES)
        assert got == "neutral", f"classify({rel!r}) = {got!r}, want 'neutral'"


def main():
    tests = [
        test_two_strike_real_path_classifies_onb_only,
        test_onb_only_globs_match_the_real_tree_file,
        test_sync_refusal_path_engages,
        test_representative_neutral_still_neutral,
    ]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(f"ALL PASS: {len(tests)} sync allowlist tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
