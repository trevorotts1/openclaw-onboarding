#!/usr/bin/env python3
"""Mutation proof for scripts/check-funnel-automation-library-drift.py.

The guard compares the automation template count on disk against the committed
catalog-index.json AND against the pinned EXPECTED_TEMPLATE_COUNT. A bare disk==index
comparison would pass a SYMMETRIC drift (file and row deleted together), so these cases
prove the pin actually holds:

  1. clean tree                      -> guard passes
  2. file deleted, index row kept    -> fails (disk drift)
  3. index row deleted, file kept    -> fails (index drift)
  4. file AND index row deleted      -> fails (symmetric drift, caught only by the pin)

Each case runs the real guard against a throwaway tree built from the real library
(automation templates copied so they can be mutated; everything else symlinked).

Run: python3 tests/unit/funnel-automation-library-drift-guard.test.py
Exit 0 = all four cases behaved; exit 1 = a case regressed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / "scripts" / "check-funnel-automation-library-drift.py"
AUTO_REL = Path("44-convert-and-flow-operator") / "automation-templates"
AUTO_INDEX_REL = AUTO_REL / "_matcher" / "catalog-index.json"


def _build_tree(tmp: Path) -> Path:
    """Real library, automation side copied (mutable), the rest symlinked."""
    root = tmp / "repo"
    root.mkdir()

    shared = root / "shared-utils"
    os.symlink(REPO / "shared-utils", shared)
    # persona_crosswalk resolves its canonical persona table relative to the repo root.
    os.symlink(REPO / "22-book-to-persona-coaching-leadership-system",
               root / "22-book-to-persona-coaching-leadership-system")

    funnel = root / "06-ghl-install-pages"
    funnel.mkdir()
    os.symlink(REPO / "06-ghl-install-pages" / "funnel-templates", funnel / "funnel-templates")
    (funnel / "tools").mkdir()
    os.symlink(REPO / "06-ghl-install-pages" / "tools" / "catalog-index.json",
               funnel / "tools" / "catalog-index.json")

    (root / "44-convert-and-flow-operator").mkdir()
    shutil.copytree(REPO / AUTO_REL, root / AUTO_REL, symlinks=True)
    return root


def _sample_template(root: Path) -> tuple[Path, str, str]:
    """First template (group, id, file path) in index order — deterministic."""
    idx = json.loads((root / AUTO_INDEX_REL).read_text(encoding="utf-8"))
    entry = idx["templates"][0]
    group, tid = entry["group"], entry["id"]
    for fn in sorted(os.listdir(root / AUTO_REL / group)):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        doc = json.loads((root / AUTO_REL / group / fn).read_text(encoding="utf-8"))
        if (doc.get("id") or fn[:-5]) == tid:
            return root / AUTO_REL / group / fn, group, tid
    raise AssertionError(f"index row {group}/{tid} has no file on disk")


def _drop_index_row(root: Path, group: str, tid: str) -> None:
    path = root / AUTO_INDEX_REL
    idx = json.loads(path.read_text(encoding="utf-8"))
    idx["templates"] = [t for t in idx["templates"]
                        if not (t["group"] == group and t["id"] == tid)]
    path.write_text(json.dumps(idx, indent=2) + "\n", encoding="utf-8")


def _run_guard(root: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-I", str(GUARD), "--repo-root", str(root)],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _case_clean(tmp: Path) -> None:
    root = _build_tree(tmp)
    rc, out = _run_guard(root)
    assert rc == 0, f"clean tree must pass, got rc={rc}\n{out}"
    assert "automation(49)" in out, f"success line must print the pinned count:\n{out}"


def _case_disk_drift(tmp: Path) -> None:
    root = _build_tree(tmp)
    path, _group, _tid = _sample_template(root)
    path.unlink()
    rc, out = _run_guard(root)
    assert rc != 0, f"file deleted with row kept must FAIL\n{out}"
    assert "phantom" in out or "count drift" in out, f"failure must name the drift:\n{out}"


def _case_index_drift(tmp: Path) -> None:
    root = _build_tree(tmp)
    _path, group, tid = _sample_template(root)
    _drop_index_row(root, group, tid)
    rc, out = _run_guard(root)
    assert rc != 0, f"row deleted with file kept must FAIL\n{out}"
    assert "orphan" in out or "count drift" in out, f"failure must name the drift:\n{out}"


def _case_symmetric_drift(tmp: Path) -> None:
    root = _build_tree(tmp)
    path, group, tid = _sample_template(root)
    path.unlink()
    _drop_index_row(root, group, tid)
    rc, out = _run_guard(root)
    assert rc != 0, (f"file AND row deleted together must FAIL on the pinned count "
                     f"(disk and index are equal but wrong)\n{out}")
    assert "expected 49" in out, f"failure must name the pinned count:\n{out}"


CASES = (
    ("clean tree", _case_clean),
    ("disk drift (file deleted, row kept)", _case_disk_drift),
    ("index drift (row deleted, file kept)", _case_index_drift),
    ("symmetric drift (file + row deleted)", _case_symmetric_drift),
)


def main() -> int:
    failures = []
    for name, case in CASES:
        tmp = Path(tempfile.mkdtemp(prefix="s38-44-drift-guard-"))
        try:
            case(tmp)
            print(f"ok   {name}")
        except AssertionError as exc:
            failures.append(name)
            print(f"FAIL {name}: {exc}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print(f"\nFAILED: {failures}")
        return 1
    print(f"\nOK — {len(CASES)} drift-guard cases behaved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
