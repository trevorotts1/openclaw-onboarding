#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_reconcile_orphan_shared_utils.py -- U006 coverage.

Proves shared-utils/reconcile-orphan-shared-utils.py makes canonical DELETIONS
reach the additive-merge shared-utils/ tree, without ever deleting in place:

1. AC#3 zero false positives: a CLEAN tree (every dest file has a source
   counterpart) reports NO orphans (rc 0).
2. AC#2 detection: a dest file with NO source counterpart is reported as an
   orphan (rc 10 in dry-run) and is NOT moved (dry-run is the default).
3. AC#3 drift is not an orphan: a file that DIFFERS in content but still exists
   in src is kept (drift is _ocs_tree_compare's job, not this tool's).
4. AC#2 quarantine: --apply MOVES the orphan under a timestamped batch with a
   manifest.json (never deletes in place); the dest no longer holds it.
5. Restore round-trip: --restore puts the quarantined file back.
6. Edge: a symlinked orphan is UNDECIDABLE -- reported (rc 4), never moved.
7. Edge: a missing --src tree is fatal (rc 2), nothing touched.

MUTATION PROOF (verified during development): inverting the keep-condition in
find_orphans (`if rel in src_paths: continue` -> `if rel not in src_paths:
continue`) makes test_clean_tree_no_orphans and test_orphan_detected_dry_run
FAIL (RED); reverting restores GREEN. The orphan test therefore genuinely
guards the detection logic, not just the plumbing.

Run: python3 -m pytest shared-utils/test_reconcile_orphan_shared_utils.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent / "reconcile-orphan-shared-utils.py"


def run_tool(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, text=True, timeout=60,
    )


@pytest.fixture
def trees(tmp_path: Path):
    """A canonical src tree and a dest tree with one shared + one orphan file."""
    src = tmp_path / "src" / "shared-utils"
    dest = tmp_path / "dest" / "shared-utils"
    src.mkdir(parents=True)
    dest.mkdir(parents=True)
    # A file canonical ships (present in both).
    (src / "helper.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (dest / "helper.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    # An ORPHAN: present in dest, absent from src (canonical retired it).
    (dest / "retired_helper.py").write_text("# retired\n", encoding="utf-8")
    return {"root": tmp_path, "src": src, "dest": dest}


# ── AC#3: zero false positives on a clean tree ────────────────────────────────
def test_clean_tree_no_orphans(tmp_path: Path):
    src = tmp_path / "src" / "shared-utils"
    dest = tmp_path / "dest" / "shared-utils"
    src.mkdir(parents=True)
    dest.mkdir(parents=True)
    for name in ("a.py", "b.sh"):
        (src / name).write_text("x", encoding="utf-8")
        (dest / name).write_text("x", encoding="utf-8")

    r = run_tool("--src", str(src), "--dest", str(dest))
    assert r.returncode == 0, r.stderr
    assert "orphan=0" in r.stdout
    # Both files still present (nothing moved on a clean tree).
    assert (dest / "a.py").exists() and (dest / "b.sh").exists()


# ── AC#2: an orphan is detected (dry-run) and NOT moved ───────────────────────
def test_orphan_detected_dry_run(trees):
    r = run_tool("--src", str(trees["src"]), "--dest", str(trees["dest"]))
    assert r.returncode == 10, f"expected dry-run rc 10, got {r.returncode}: {r.stderr}"
    assert "retired_helper.py" in r.stdout
    assert "WOULD QUARANTINE" in r.stdout
    # Dry-run: the orphan is still in place (reported, not moved).
    assert (trees["dest"] / "retired_helper.py").exists()
    # The non-orphan is untouched and never flagged.
    assert (trees["dest"] / "helper.py").exists()


# ── AC#3: content drift is NOT an orphan (zero false positives) ───────────────
def test_drifted_but_present_is_not_orphan(trees):
    # Drift the shared file's CONTENT (still present in src) -> not an orphan.
    (trees["dest"] / "helper.py").write_text("def helper():\n    return 999\n", encoding="utf-8")
    # Remove the true orphan so the only candidate is the drifted file.
    (trees["dest"] / "retired_helper.py").unlink()

    r = run_tool("--src", str(trees["src"]), "--dest", str(trees["dest"]))
    assert r.returncode == 0, f"drift must not be flagged: {r.stdout} {r.stderr}"
    assert "orphan=0" in r.stdout


# ── AC#2: --apply quarantines the orphan (never deletes in place) ─────────────
def test_apply_quarantines_orphan(trees):
    qroot = trees["root"] / "quarantine"
    r = run_tool("--src", str(trees["src"]), "--dest", str(trees["dest"]),
                 "--quarantine-root", str(qroot), "--apply")
    assert r.returncode == 0, r.stderr
    assert "QUARANTINED" in r.stdout
    # The orphan is gone from dest...
    assert not (trees["dest"] / "retired_helper.py").exists()
    # ...and lives under a quarantine batch with a manifest (never deleted).
    batches = list((qroot / ".orphan-shared-utils-quarantine").glob("*"))
    assert len(batches) == 1
    manifest = json.loads((batches[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "openclaw/orphan-shared-utils-quarantine@1"
    assert any(item["rel"] == "retired_helper.py" for item in manifest["items"])
    # The non-orphan is untouched.
    assert (trees["dest"] / "helper.py").exists()


# ── Restore round-trip ────────────────────────────────────────────────────────
def test_restore_round_trip(trees):
    qroot = trees["root"] / "quarantine"
    run_tool("--src", str(trees["src"]), "--dest", str(trees["dest"]),
             "--quarantine-root", str(qroot), "--apply")
    assert not (trees["dest"] / "retired_helper.py").exists()

    batch = next((qroot / ".orphan-shared-utils-quarantine").glob("*"))
    r = run_tool("--restore", str(batch))
    assert r.returncode == 0, r.stderr
    assert "RESTORE_STATUS ok=1" in r.stdout
    # The orphan is back where it started.
    assert (trees["dest"] / "retired_helper.py").exists()


# ── Edge: a symlinked orphan is UNDECIDABLE -- reported, never moved ──────────
def test_symlink_orphan_reported_not_moved(trees):
    target = trees["root"] / "outside-target.py"
    target.write_text("outside", encoding="utf-8")
    link = trees["dest"] / "stray_link.py"
    os.symlink(target, link)

    r = run_tool("--src", str(trees["src"]), "--dest", str(trees["dest"]), "--apply")
    assert r.returncode == 4, f"symlink must be rc 4, got {r.returncode}: {r.stdout} {r.stderr}"
    assert "UNREADABLE" in r.stderr
    # The symlink is still there (never moved/deleted).
    assert link.is_symlink()


# ── Edge: a missing --src tree is fatal (rc 2), nothing touched ───────────────
def test_missing_src_is_fatal(trees):
    missing = trees["root"] / "does-not-exist"
    r = run_tool("--src", str(missing), "--dest", str(trees["dest"]))
    assert r.returncode == 2, r.stderr
    assert "FATAL" in r.stderr
    # Nothing was touched.
    assert (trees["dest"] / "retired_helper.py").exists()
    assert (trees["dest"] / "helper.py").exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
