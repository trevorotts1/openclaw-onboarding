#!/usr/bin/env python3
"""
reconcile-orphan-shared-utils.py — detect files in the destination shared-utils/
that have NO source counterpart, so canonical DELETIONS propagate.

────────────────────────────────────────────────────────────────────────────
WHY THIS EXISTS
────────────────────────────────────────────────────────────────────────────
shared-utils/ delivery is merge-copy (additive). The updater runs:
    cp -r "$EXTRACTED_DIR/shared-utils/." "$SKILLS_DIR/shared-utils/"
and _ocs_tree_compare checks ``src ⊆ dest`` (source entries missing from the
box). It does NOT check ``dest ⊆ src`` — files canonical has DELETED stay on
the box forever because nothing ever enumerates the destination and asks
"does this file still exist in the source?"

This tool walks the destination and reports or quarantines files with no
source counterpart. It is the directional complement to _ocs_tree_compare.

────────────────────────────────────────────────────────────────────────────
SAFETY MODEL
────────────────────────────────────────────────────────────────────────────
- DRY-RUN IS THE DEFAULT. Without --apply no file is moved; the tool reports
  exactly what it WOULD quarantine.
- BACK UP, NEVER UNLINK. --apply MOVES each orphan under a quarantine
  directory with a timestamped manifest. Restore is supported.
- Denied paths (__pycache__, *.pyc, .git, backups, *.bak, .DS_Store) are
  NEVER matched — they are build artifacts and cold-storage rollback material.
- Symlinks are resolved before comparison.
────────────────────────────────────────────────────────────────────────────

CLI
───
  --src <dir>          source shared-utils/ tree (canonical)
  --dest <dir>         destination shared-utils/ tree (box)
  --apply              actually quarantine (default is DRY-RUN)
  --quarantine-root    where quarantine batches are written
  --restore <dir>      restore a quarantine batch and exit
  --json               machine-readable report on stdout

EXIT CODES
  0   clean — nothing actionable, or --apply completed with no orphans
  10  DRY-RUN: orphans found that --apply would quarantine
  4   at least one CONFLICT / UNREADABLE file
  5   --apply: a quarantine move failed
  1   usage error
  (precedence: 5 > 4 > 10 > 0)
"""

import argparse
import fnmatch
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOL = "reconcile-orphan-shared-utils.py"
QUARANTINE_SCHEMA = "openclaw/shared-utils-orphan-quarantine@1"

# Deny-list components: build artifacts, caches, rollback material.
# Matched with fnmatch against every component of every path.
DENY_COMPONENTS = (
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".orphan-quarantine", ".Trash", ".cache",
    "backups", "openclaw-backups", "master-files", "backup",
    "*.bak", "*.bak-*", "*.bak.*", "*.backup", "*.old",
    "*.pyc", "*.pyo",
    "skills.bak*", "skills-backup-*",
    "updater-src-*",
    ".update-backup*", "*.orig", "*.rej",
)

# Files whose absence in the source is normal (build artifacts, editor temp,
# per-box state) — never reported as orphans.
ALWAYS_EXCLUDE_NAMES = (
    ".DS_Store", "Thumbs.db", ".gitkeep", ".gitignore",
)


def denied(component):
    return any(fnmatch.fnmatch(component, pat) for pat in DENY_COMPONENTS)


def build_source_index(src_dir):
    """Walk the source tree and return a set of all file posix-relative paths."""
    src = Path(src_dir)
    if not src.is_dir():
        return set(), False
    index = set()
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        dirnames[:] = [d for d in dirnames if not denied(d)]
        rel_dir = Path(dirpath).relative_to(src)
        for fname in filenames:
            if fname in ALWAYS_EXCLUDE_NAMES or denied(fname):
                continue
            index.add((rel_dir / fname).as_posix())
    return index, True


def scan_destination(dest_dir, src_dir, source_index):
    """Walk the destination; yield every file whose relative path is NOT in source_index."""
    dest = Path(dest_dir)
    src = Path(src_dir)
    if not dest.is_dir():
        return

    for dirpath, dirnames, filenames in os.walk(dest, followlinks=False):
        dirnames[:] = [d for d in dirnames if not denied(d)]
        for fname in filenames:
            if fname in ALWAYS_EXCLUDE_NAMES or denied(fname):
                continue
            full = Path(dirpath) / fname
            try:
                rel = full.relative_to(dest).as_posix()
            except ValueError:
                continue

            # Denied component anywhere in the path
            if any(denied(c) for c in full.parts):
                continue

            # Symlinks — report, never follow, never remove.
            if full.is_symlink():
                yield {
                    "status": "UNREADABLE",
                    "path": str(full),
                    "rel": rel,
                    "detail": "is a symlink — never followed, never removed",
                }
                continue

            # Resolve check — ensure the file is under the dest root.
            try:
                real = full.resolve()
                real.relative_to(dest.resolve())
            except (OSError, ValueError):
                yield {
                    "status": "UNREADABLE",
                    "path": str(full),
                    "rel": rel,
                    "detail": "resolves outside its destination root",
                }
                continue

            if rel not in source_index:
                yield {
                    "status": "ORPHAN",
                    "path": str(full),
                    "rel": rel,
                }


def quarantine(qroot, orphans, dest_dir, src_dir):
    """Move orphan files to a timestamped quarantine batch. Returns (batch_path, moved, failures)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch = Path(qroot) / ".orphan-quarantine" / ts
    moved, failures = [], []

    for o in orphans:
        src_file = Path(o["path"])
        rel = o["rel"]
        dest_file = batch / "shared-utils" / rel
        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_file), str(dest_file))
        except (OSError, shutil.Error) as e:
            failures.append({"path": o["path"], "rel": rel, "error": str(e)})
            continue
        moved.append({
            "original": o["path"],
            "quarantined_to": str(dest_file),
            "rel": rel,
        })

    if moved or failures:
        try:
            batch.mkdir(parents=True, exist_ok=True)
            (batch / "manifest.json").write_text(json.dumps({
                "schema": QUARANTINE_SCHEMA,
                "tool": TOOL,
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
                "source": str(src_dir),
                "destination": str(dest_dir),
                "restore": f"python3 {TOOL} --restore {batch}",
                "items": moved,
                "failures": failures,
            }, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            failures.append({"path": str(batch / "manifest.json"), "error": str(e)})

    return batch, moved, failures


def restore(batch_dir):
    """Move a quarantine batch back to its original locations."""
    man = Path(batch_dir) / "manifest.json"
    try:
        data = json.loads(man.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot read quarantine manifest {man}: {e}", file=sys.stderr)
        print("RESTORE_STATUS ok=0 restored=0 skipped_present=0 failed=0")
        return 2
    if data.get("schema") != QUARANTINE_SCHEMA:
        print(f"FATAL: {man} is not a shared-utils orphan-quarantine manifest", file=sys.stderr)
        print("RESTORE_STATUS ok=0 restored=0 skipped_present=0 failed=0")
        return 2

    restored = skipped = failed = 0
    for item in data.get("items", []):
        orig = Path(item["original"])
        quar = Path(item["quarantined_to"])
        if orig.exists():
            print(f"  SKIP (already present): {orig}")
            skipped += 1
            continue
        if not quar.is_file():
            print(f"  FAIL (missing from quarantine): {quar}", file=sys.stderr)
            failed += 1
            continue
        try:
            orig.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(quar), str(orig))
        except (OSError, shutil.Error) as e:
            print(f"  FAIL {orig}: {e}", file=sys.stderr)
            failed += 1
            continue
        print(f"  RESTORED: {orig}")
        restored += 1
    print(f"RESTORE_STATUS ok={0 if failed else 1} restored={restored} "
          f"skipped_present={skipped} failed={failed}")
    return 5 if failed else 0


def main():
    ap = argparse.ArgumentParser(
        description="Detect and quarantine files in the destination shared-utils/ "
                    "tree that have no source counterpart (canonical deletions that "
                    "never propagated). Dry-run unless --apply.")
    ap.add_argument("--src", required=False, default=None,
                    help="source shared-utils/ tree (canonical)")
    ap.add_argument("--dest", required=False, default=None,
                    help="destination shared-utils/ tree (box)")
    ap.add_argument("--quarantine-root", default=None,
                    help="where quarantine batches are written")
    ap.add_argument("--apply", action="store_true",
                    help="actually quarantine (default is DRY-RUN)")
    ap.add_argument("--restore", default=None, metavar="BATCH_DIR")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.restore:
        return restore(args.restore)

    if not args.src:
        print("FATAL: --src is required (source shared-utils/ tree)", file=sys.stderr)
        print("RECONCILE_STATUS ok=0 fatal=1 orphans=0 quarantined=0 problems=0")
        return 1
    if not args.dest:
        print("FATAL: --dest is required (destination shared-utils/ tree)", file=sys.stderr)
        print("RECONCILE_STATUS ok=0 fatal=1 orphans=0 quarantined=0 problems=0")
        return 1

    src_dir = args.src
    dest_dir = args.dest
    qroot = Path(args.quarantine_root) if args.quarantine_root else Path(dest_dir).parent

    if not Path(dest_dir).is_dir():
        print("RECONCILE_STATUS ok=1 fatal=0 orphans=0 quarantined=0 problems=0")
        return 0

    source_index, src_ok = build_source_index(src_dir)
    if not src_ok:
        print("FATAL: source directory does not exist or is not readable: " + src_dir,
              file=sys.stderr)
        print("RECONCILE_STATUS ok=0 fatal=1 orphans=0 quarantined=0 problems=0")
        return 1

    orphans = []
    problems = []
    for entry in scan_destination(dest_dir, src_dir, source_index):
        if entry["status"] == "ORPHAN":
            orphans.append(entry)
        elif entry["status"] == "UNREADABLE":
            problems.append(entry)

    batch, moved, failures = None, [], []
    if args.apply and orphans:
        batch, moved, failures = quarantine(qroot, orphans, dest_dir, src_dir)
    moved_originals = {m["original"] for m in moved}

    # ── report ────────────────────────────────────────────────────────────────
    mode = "APPLY" if args.apply else "DRY-RUN (no file moved)"
    print("=" * 78)
    print(f"SHARED-UTILS ORPHAN DETECTION — {mode}")
    print(f"source    : {src_dir}")
    print(f"dest      : {dest_dir}")
    print(f"src files : {len(source_index)}")
    print("=" * 78)

    for o in orphans:
        if not args.apply:
            verb = "WOULD QUARANTINE"
        elif o["path"] in moved_originals:
            verb = "QUARANTINED"
        else:
            verb = "QUARANTINE FAILED"
        print(f"  {verb}: {o['path']}  (no source counterpart)")

    for p in problems:
        print(f"  {p['status']} (KEPT): {p['path']} — {p['detail']}")
    for f in failures:
        print(f"  MOVE FAILED: {f['path']} — {f['error']}")

    if batch and moved:
        print(f"  quarantine batch: {batch}")
        print(f"  restore with    : python3 {TOOL} --restore {batch}")

    print(f"  orphan={len(orphans)} quarantined={len(moved)} "
          f"problems={len(problems)}")

    # ── exit code (5 > 4 > 10 > 0) ────────────────────────────────────────────
    if failures:
        rc = 5
    elif problems:
        rc = 4
    elif orphans and not args.apply:
        rc = 10
    else:
        rc = 0
    ok = 1 if rc in (0, 10) else 0
    print(f"RECONCILE_STATUS ok={ok} fatal=0 orphans={len(orphans)} "
          f"quarantined={len(moved)} problems={len(problems)}")

    if args.json:
        print(json.dumps({
            "schema": "openclaw/shared-utils-orphan-receipt@1",
            "tool": TOOL,
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "apply": args.apply,
            "rc": rc,
            "counts": {
                "orphan": len(orphans),
                "quarantined": len(moved),
                "problems": len(problems),
            },
        }, indent=1))

    return rc


if __name__ == "__main__":
    sys.exit(main())
