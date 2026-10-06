#!/usr/bin/env python3
"""T7 helper for tests/unit/unify-backup-retention.test.sh.

Exercises the REAL _unify_backup / _unify_bak_keep out of
23-ai-workforce-blueprint/scripts/create_role_workspaces.py. That module pulls
in vendored siblings at import time, so the two helpers are sliced out by text
and exec'd -- the code under test is still the shipped code, byte for byte.

Asserts:
  1. first call makes a backup and removes the original
  2. an IDENTICAL later file is NOT copied again (content already preserved)
     and the original is still removed
  3. changed content DOES make a new backup
  4. the set is pruned to the 3 newest
  5. UNIFY_BAK_KEEP overrides the count
Exit 0 = pass.
"""
import filecmp
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(os.environ["REPO_ROOT"])
SRC = REPO_ROOT / "23-ai-workforce-blueprint/scripts/create_role_workspaces.py"

text = SRC.read_text()
start = text.index("UNIFY_BAK_KEEP_DEFAULT = 3")
end = text.index("def _link_shared_files_only(")
ns = {"filecmp": filecmp, "os": os, "datetime": datetime, "Path": Path}
exec(compile(text[start:end], str(SRC), "exec"), ns)  # noqa: S102
_unify_backup = ns["_unify_backup"]

fails = []


def check(cond, label):
    print(("    ok   " if cond else "    FAIL ") + label)
    if not cond:
        fails.append(label)


def baks(p):
    return sorted(p.parent.glob(p.name + ".bak-unify-*"))


with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    f = d / "AGENTS.md"

    f.write_text("body v1\n")
    bak1 = _unify_backup(f)
    check(bak1 is not None and not f.exists() and len(baks(f)) == 1,
          "first call backs up and removes the original")

    # Same bytes again (the daily loop): must NOT write a second copy.
    f.write_text("body v1\n")
    bak2 = _unify_backup(f)
    check(bak2 is None and not f.exists() and len(baks(f)) == 1,
          "identical content -> no second backup, original still removed")

    # Changed bytes: must back up.
    f.write_text("body v2\n")
    bak3 = _unify_backup(f)
    check(bak3 is not None and len(baks(f)) == 2,
          "changed content -> a new backup")

    # Seed enough to exercise the prune.
    for i in range(1, 5):
        (d / f"AGENTS.md.bak-unify-2025010{i}-000000").write_text(f"old {i}\n")
    f.write_text("body v3\n")
    _unify_backup(f)
    check(len(baks(f)) == 3, f"pruned to 3 newest (got {len(baks(f))})")
    check(not (d / "AGENTS.md.bak-unify-20250101-000000").exists(),
          "the oldest seeded backup was deleted")

    os.environ["UNIFY_BAK_KEEP"] = "1"
    f.write_text("body v4\n")
    _unify_backup(f)
    check(len(baks(f)) == 1, f"UNIFY_BAK_KEEP=1 -> 1 kept (got {len(baks(f))})")
    del os.environ["UNIFY_BAK_KEEP"]

    # Nothing but this target's own unify backups is ever touched.
    other = d / "TOOLS.md.bak-unify-20250101-000000"
    other.write_text("sibling\n")
    manual = d / "AGENTS.md.bak-manual"
    manual.write_text("manual\n")
    f.write_text("body v5\n")
    _unify_backup(f)
    check(other.exists() and manual.exists(),
          "sibling + non-unify backups survive the prune")

sys.exit(1 if fails else 0)
