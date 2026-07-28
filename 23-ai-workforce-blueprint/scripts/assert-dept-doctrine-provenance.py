#!/usr/bin/env python3
"""
assert-dept-doctrine-provenance.py -- U004 Phase 1

Warn-mode census: for a department's sops/ and scripts/ directories,
classify every non-.bak entry against a source-root index of same-basename
files, producing four disjoint buckets: identical, fork, orphan, broken-symlink.

Rule 3.5: exits 0 (warn-mode).  --enforce exits 3 when orphan + broken-symlink > 0.

CONTRACT:
  --dept-dir <path>       the department root (e.g. .../departments/Presentations)
  --source-root <path>    the skills root to index (e.g. ~/.openclaw/skills)
  --json                  machine output (one JSON object per subdirectory)
  --enforce               exit 3 on any orphan or broken symlink
"""

import argparse
import hashlib
import json
import os
import sys


def walk_index(source_root):
    """Build a dict of basename -> set of SHA-256 hex digests for every
    non-.bak file-or-link under source_root (recursive, excluding .git,
    __pycache__, node_modules)."""
    index = {}
    exclude_dirs = {".git", "__pycache__", "node_modules"}
    for dirpath, dirnames, _filenames in os.walk(source_root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        try:
            entries = os.listdir(dirpath)
        except OSError:
            continue
        for name in entries:
            if ".bak" in name:
                continue
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or os.path.isfile(full):
                try:
                    with open(full, "rb") as fh:
                        digest = hashlib.sha256(fh.read()).hexdigest()
                except (OSError, PermissionError):
                    continue
                index.setdefault(name, set()).add(digest)
    return index


def sha256_file(path):
    """Return the SHA-256 hex digest of a file's contents."""
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except (OSError, PermissionError):
        return None


def census_dir(subdir, index):
    """Walk depth-1 of subdir, classifying every non-.bak entry that is
    either a file or a symlink, into four buckets."""
    identical = 0
    fork = 0
    orphan = 0
    broken_symlink = 0

    try:
        entries = os.listdir(subdir)
    except OSError:
        return {"identical": 0, "fork": 0, "orphan": 0, "broken_symlink": 0}

    for name in sorted(entries):
        if ".bak" in name:
            continue
        full = os.path.join(subdir, name)

        if os.path.islink(full):
            if not os.path.exists(full):
                broken_symlink += 1
                continue
            try:
                resolved = os.path.realpath(full)
            except OSError:
                broken_symlink += 1
                continue
            if not os.path.isfile(resolved):
                broken_symlink += 1
                continue
            digest = sha256_file(resolved)
        elif os.path.isfile(full):
            digest = sha256_file(full)
        else:
            continue

        if digest is None:
            orphan += 1
            continue

        known_digests = index.get(name)
        if known_digests is None:
            orphan += 1
        elif digest in known_digests:
            identical += 1
        else:
            fork += 1

    return {"identical": identical, "fork": fork, "orphan": orphan, "broken_symlink": broken_symlink}


def main():
    parser = argparse.ArgumentParser(description="U004 -- dept doctrine provenance assertion")
    parser.add_argument("--dept-dir", required=True, help="Department root directory")
    parser.add_argument("--source-root", required=True, help="Skills source root for indexing")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--enforce", action="store_true", help="Exit 3 when orphan + broken-symlink > 0")
    args = parser.parse_args()

    dept_dir = os.path.abspath(args.dept_dir)
    source_root = os.path.abspath(args.source_root)

    index = walk_index(source_root)

    results = {}
    for sub in ("sops", "scripts"):
        sub_path = os.path.join(dept_dir, sub)
        counts = census_dir(sub_path, index)
        total = counts["identical"] + counts["fork"] + counts["orphan"] + counts["broken_symlink"]
        counts["total"] = total
        results[sub] = counts

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for sub in ("sops", "scripts"):
            c = results[sub]
            print(f"{dept_dir}/{sub}/:")
            print(f"  identical      = {c['identical']}")
            print(f"  fork           = {c['fork']}")
            print(f"  orphan         = {c['orphan']}")
            print(f"  broken-symlink = {c['broken_symlink']}")
            print(f"  {c['identical']} + {c['fork']} + {c['orphan']} + {c['broken_symlink']} = {c['total']}")

    if args.enforce:
        any_orphan = results["sops"]["orphan"] + results["scripts"]["orphan"]
        any_broken = results["sops"]["broken_symlink"] + results["scripts"]["broken_symlink"]
        if any_orphan + any_broken > 0:
            sys.exit(3)

    sys.exit(0)


if __name__ == "__main__":
    main()
