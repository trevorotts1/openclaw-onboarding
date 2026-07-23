#!/usr/bin/env python3
"""
reconcile-orphan-shared-utils.py — make canonical DELETIONS reach the
shared-utils/ trees the updater's additive merge-copy never touches.

────────────────────────────────────────────────────────────────────────────
WHAT IS BROKEN
────────────────────────────────────────────────────────────────────────────
shared-utils/ is delivered by an ADDITIVE merge-copy (update-skills.sh:
`cp -r "$SRC/shared-utils/." "$SKILLS_DIR/shared-utils/"`). The trailing "/."
CREATES files absent on the box and overwrites drifted ones, but never deletes
box-local extras. The post-copy assertion (`_ocs_tree_compare`) only checks
`src ⊆ dest` (every source entry landed) and explicitly treats dest supersets
as fine — so when canonical DELETES a helper, that deletion never propagates:
the file stays on every box forever, sitting where agents read.

This is the shared-utils analogue of reconcile-orphan-library-files.py (the
role-library reconciler), simplified: shared-utils/ is fully canonical-managed
(no client-authored content is expected there), so an orphan is simply a dest
file whose relative path has NO counterpart in the canonical source tree.

────────────────────────────────────────────────────────────────────────────
THE SAFETY MODEL — REPORT OR QUARANTINE, NEVER DELETE IN PLACE
────────────────────────────────────────────────────────────────────────────
This tool touches files on CLIENT MACHINES, so it never deletes anything in
place. It either REPORTS (logs the orphan path) or QUARANTINES (moves the file
aside under a timestamped batch with a manifest, restorable via --restore).
A file is an orphan only when ALL of these hold:

  (a) it is under the --dest tree and no path component is in the cold-backup /
      VCS / cache deny-list;
  (b) it is a regular file (symlinks and unreadable files are UNDECIDABLE and
      are reported loudly, never moved);
  (c) its path RELATIVE TO --dest does NOT exist under --src — proving canonical
      no longer ships it.

Everything with a source counterpart is KEPT, by construction (zero false
positives on a clean tree — a drifted-but-present file is NOT an orphan; drift
is the existing _ocs_tree_compare byte-check's job, not this tool's).

DRY-RUN IS THE DEFAULT.  Without --apply no file is moved; the tool reports
exactly what it WOULD quarantine. BACK UP, NEVER UNLINK: --apply MOVES each
orphan under <quarantine-root>/.orphan-shared-utils-quarantine/<UTC-timestamp>/
with a manifest.json recording every original path + sha; --restore puts them
back. FAIL LOUDLY: an unreadable/symlinked file is rc 4, a failed move is rc 5,
an unusable source tree is rc 2 (nothing touched). IDEMPOTENT: a second run
finds nothing.

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  --src <dir>           canonical source shared-utils/ tree (required)
  --dest <dir>          destination shared-utils/ tree on the box (required)
  --apply               actually quarantine (default is DRY-RUN: report only)
  --quarantine-root <dir>  where batches + the receipt are written
                           (default: the parent of --dest)
  --restore <dir>       restore a quarantine batch directory and exit
  --json                machine-readable report on stdout

EXIT CODES  (precedence: 2 > 5 > 4 > 10 > 0)
  0   clean — no orphans, or --apply completed with no conflicts
  10  DRY-RUN: orphans found that --apply would quarantine
  4   at least one UNREADABLE / symlink file — reported and SKIPPED, never moved
  5   --apply: a quarantine move failed
  2   fatal: source tree unusable — NOTHING was touched
  1   usage error
"""
import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOL = "reconcile-orphan-shared-utils.py"
QUARANTINE_SCHEMA = "openclaw/orphan-shared-utils-quarantine@1"
RECEIPT_SCHEMA = "openclaw/orphan-shared-utils-receipt@1"

# Directory-component deny-list. Matched with fnmatch against EVERY component
# of every path, and used to prune os.walk before descending. Cold backups are
# rollback material: removing them is a bug, not a feature. Mirrors the
# role-library reconciler's deny-list.
DENY_COMPONENTS = (
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".orphan-quarantine", ".orphan-shared-utils-quarantine", ".Trash", ".cache",
    "backups", "openclaw-backups", "master-files", "backup",
    "*.bak", "*.bak-*", "*.bak.*", "*.backup", "*.old",
    "skills.bak*", "skills-backup-*", "*-backup-*", "*-backup",
    "updater-src-*", "*-archive", "departments-archive",
    ".update-backup*", "*.orig", "*.rej",
)

# Files this tool itself writes; never treated as orphans even though canonical
# does not ship them. (The receipt and quarantine batch live at the
# quarantine-root, normally the parent of --dest, so they are not under --dest
# at all — but guard anyway in case --quarantine-root is set inside --dest.)
SELF_ARTIFACTS = (".orphan-shared-utils-receipt.json",)


def denied(component):
    return any(fnmatch.fnmatch(component, pat) for pat in DENY_COMPONENTS)


def content_sha(path):
    """sha256 of a file's bytes (for the quarantine manifest / receipt)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ─── SCAN ─────────────────────────────────────────────────────────────────────

def collect_relpaths(root):
    """-> set of relative POSIX paths of every regular file under root, pruning
    denied directories. Symlinks are followed for directories=False (os.walk
    followlinks=False) so a symlinked dir is not descended; symlinked FILES are
    still yielded here and classified by the caller."""
    root = Path(root)
    out = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not denied(d)]
        for fname in filenames:
            full = Path(dirpath) / fname
            if any(denied(c) for c in full.parts):
                continue
            if fname in SELF_ARTIFACTS:
                continue
            out.add(full.relative_to(root).as_posix())
    return out


def find_orphans(src, dest):
    """-> (orphans, problems). orphans: dest files with no source counterpart.
    problems: symlinks / unreadable files (UNDECIDABLE — reported, never moved)."""
    src = Path(src)
    dest = Path(dest)
    src_paths = collect_relpaths(src)
    orphans, problems = [], []
    for rel in sorted(collect_relpaths(dest)):
        if rel in src_paths:
            continue  # has a source counterpart -> keep (zero false positives)
        full = dest / rel
        if full.is_symlink():
            problems.append({"kind": "UNREADABLE", "path": full.as_posix(),
                             "detail": "is a symlink — never followed, never moved"})
            continue
        try:
            sha = content_sha(full)
        except (OSError, UnicodeDecodeError) as e:
            problems.append({"kind": "UNREADABLE", "path": full.as_posix(),
                             "detail": f"cannot read: {e}"})
            continue
        orphans.append({"path": full.as_posix(), "rel": rel, "content_sha": sha})
    return orphans, problems


# ─── QUARANTINE / RESTORE ─────────────────────────────────────────────────────

def quarantine(qroot, orphans, dest, src):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch = Path(qroot) / ".orphan-shared-utils-quarantine" / ts
    moved, failures = [], []
    for o in orphans:
        src_file = Path(o["path"])
        dest_file = batch / "shared-utils" / o["rel"]
        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_file), str(dest_file))
        except (OSError, shutil.Error) as e:
            failures.append({"path": o["path"], "error": str(e)})
            continue
        moved.append({"original": o["path"], "quarantined_to": str(dest_file),
                      "rel": o["rel"], "content_sha": o["content_sha"]})
    if moved or failures:
        try:
            batch.mkdir(parents=True, exist_ok=True)
            (batch / "manifest.json").write_text(json.dumps({
                "schema": QUARANTINE_SCHEMA,
                "tool": TOOL,
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
                "src": str(src), "dest": str(dest),
                "restore": f"python3 {TOOL} --restore {batch}",
                "items": moved, "failures": failures,
            }, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            failures.append({"path": str(batch / "manifest.json"), "error": str(e)})
    return batch, moved, failures


def restore(batch_dir):
    """Move a quarantine batch back. Never clobbers a file that reappeared."""
    man = Path(batch_dir) / "manifest.json"
    try:
        data = json.loads(man.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot read quarantine manifest {man}: {e}", file=sys.stderr)
        print("RESTORE_STATUS ok=0 restored=0 skipped_present=0 failed=0")
        return 2
    if data.get("schema") != QUARANTINE_SCHEMA:
        print(f"FATAL: {man} is not an orphan-shared-utils quarantine manifest",
              file=sys.stderr)
        print("RESTORE_STATUS ok=0 restored=0 skipped_present=0 failed=0")
        return 2
    restored = skipped = failed = 0
    for item in data.get("items", []):
        src, dest = Path(item["quarantined_to"]), Path(item["original"])
        if dest.exists():
            print(f"  SKIP (already present): {dest}")
            skipped += 1
            continue
        if not src.is_file():
            print(f"  FAIL (missing from quarantine): {src}", file=sys.stderr)
            failed += 1
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        except (OSError, shutil.Error) as e:
            print(f"  FAIL {dest}: {e}", file=sys.stderr)
            failed += 1
            continue
        print(f"  RESTORED: {dest}")
        restored += 1
    print(f"RESTORE_STATUS ok={0 if failed else 1} restored={restored} "
          f"skipped_present={skipped} failed={failed}")
    return 5 if failed else 0


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Report or quarantine shared-utils/ files the canonical source "
                    "tree no longer ships (orphans left behind by the additive "
                    "merge-copy). Dry-run unless --apply. Never deletes in place.")
    ap.add_argument("--src", default=None, help="canonical source shared-utils/ tree")
    ap.add_argument("--dest", default=None, help="destination shared-utils/ tree on the box")
    ap.add_argument("--quarantine-root", default=None,
                    help="where batches + the receipt are written (default: parent of --dest)")
    ap.add_argument("--apply", action="store_true",
                    help="actually quarantine (default is DRY-RUN: report only)")
    ap.add_argument("--restore", default=None, metavar="BATCH_DIR")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.restore:
        return restore(args.restore)

    if not args.src or not args.dest:
        print("usage error: --src and --dest are both required", file=sys.stderr)
        return 1

    src = Path(args.src)
    dest = Path(args.dest)

    def fatal(msg):
        print(f"FATAL: {msg}", file=sys.stderr)
        print("RECONCILE_STATUS ok=0 fatal=1 orphans=0 quarantined=0 problems=0")
        return 2

    if not src.is_dir():
        return fatal(f"source tree {src} is missing or not a directory — refusing to run")

    # A box with no shared-utils/ yet has nothing to reconcile: clean.
    if not dest.is_dir():
        print(f"RECONCILE_STATUS ok=1 fatal=0 orphans=0 quarantined=0 problems=0")
        return 0

    qroot = Path(args.quarantine_root) if args.quarantine_root else dest.parent

    orphans, problems = find_orphans(src, dest)

    batch, moved, failures = None, [], []
    if args.apply and orphans:
        batch, moved, failures = quarantine(qroot, orphans, dest, src)
    moved_paths = {m["original"] for m in moved}

    # ── report ────────────────────────────────────────────────────────────────
    mode = "APPLY" if args.apply else "DRY-RUN (no file moved)"
    print("=" * 78)
    print(f"SHARED-UTILS ORPHAN RECONCILE — {mode}")
    print(f"src  : {src}")
    print(f"dest : {dest}")
    print("=" * 78)
    for o in orphans:
        if not args.apply:
            verb = "WOULD QUARANTINE"
        elif o["path"] in moved_paths:
            verb = "QUARANTINED"
        else:
            verb = "QUARANTINE FAILED"
        print(f"  {verb}: {o['path']}")
    for p in problems:
        print(f"  {p['kind']} (KEPT): {p['path']} — {p['detail']}", file=sys.stderr)
    for f in failures:
        print(f"  MOVE FAILED: {f['path']} — {f['error']}", file=sys.stderr)
    if batch and moved:
        print(f"  quarantine batch: {batch}")
        print(f"  restore with    : python3 {TOOL} --restore {batch}")
    print(f"  orphan={len(orphans)} quarantined={len(moved)} problems={len(problems)}")

    # ── exit code (2 > 5 > 4 > 10 > 0) ────────────────────────────────────────
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

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "tool": TOOL,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "apply": args.apply, "rc": rc, "src": str(src), "dest": str(dest),
        "counts": {"orphan": len(orphans), "quarantined": len(moved),
                   "problems": len(problems)},
        "quarantine_batch": str(batch) if (batch and moved) else None,
        "orphans": [{"path": o["path"], "rel": o["rel"]} for o in orphans],
        "problems": problems,
    }
    try:
        (qroot / ".orphan-shared-utils-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    if args.json:
        print(json.dumps(receipt, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
