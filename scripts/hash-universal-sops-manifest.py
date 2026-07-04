#!/usr/bin/env python3
"""
hash-universal-sops-manifest.py — content-integrity manifest for universal-sops/.

WHY (embedding-subsystem hardening, corpus 4): the SOP corpora are TWO
different things and only one of them was integrity-covered:

  1. role-library dept SOPs (templates/role-library/<dept>/sops/*.md,
     131 entries) — covered by 23-ai-workforce-blueprint/scripts/
     hash-content-manifest.py (content_sha in _index.json, CI: library-lockstep).
  2. universal-sops/ craft clusters (repo root) — had NO manifest and NO
     content hash at all: an edit (or silent corruption / partial sync) was
     invisible to every gate.

This script closes gap 2 with a SEPARATE, additive manifest —
universal-sops/_content-manifest.json — deliberately NOT wired into the
role-library _index.json (whose count triads and disk-coverage assertions are
scoped to templates/role-library; mixing corpora there would break them).

Usage:
    scripts/hash-universal-sops-manifest.py            # (re)generate manifest
    scripts/hash-universal-sops-manifest.py --check    # verify, exit 1 on drift

Hash: sha256 over CRLF->LF-normalized bytes (same newline tolerance the
role-library hasher applies). Covers every *.md and *.json under
universal-sops/ except the manifest itself.
"""
import argparse
import hashlib
import json
import sys
import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOPS_DIR = REPO_ROOT / "universal-sops"
MANIFEST_PATH = SOPS_DIR / "_content-manifest.json"
COVERED_SUFFIXES = {".md", ".json"}


def _norm_sha(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def discover() -> dict:
    files = {}
    for p in sorted(SOPS_DIR.rglob("*")):
        if not p.is_file() or p.suffix not in COVERED_SUFFIXES:
            continue
        if p == MANIFEST_PATH:
            continue
        rel = p.relative_to(SOPS_DIR).as_posix()
        files[rel] = {"sha256": _norm_sha(p), "bytes": p.stat().st_size}
    return files


def generate() -> int:
    files = discover()
    manifest = {
        "algo": "sha256(CRLF->LF normalized bytes)",
        "generator": "scripts/hash-universal-sops-manifest.py",
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file_count": len(files),
        "files": files,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n",
                             encoding="utf-8")
    print(f"OK wrote {MANIFEST_PATH.relative_to(REPO_ROOT)} ({len(files)} files)")
    return 0


def check() -> int:
    if not MANIFEST_PATH.is_file():
        print(f"FAIL: manifest missing: {MANIFEST_PATH} — run "
              f"scripts/hash-universal-sops-manifest.py to generate it",
              file=sys.stderr)
        return 1
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        recorded = manifest.get("files", {})
    except Exception as e:
        print(f"FAIL: manifest unreadable: {e}", file=sys.stderr)
        return 1
    actual = discover()
    added = sorted(set(actual) - set(recorded))
    removed = sorted(set(recorded) - set(actual))
    changed = sorted(
        rel for rel in set(actual) & set(recorded)
        if actual[rel]["sha256"] != recorded[rel].get("sha256")
    )
    if not (added or removed or changed):
        print(f"PASS: universal-sops content manifest clean "
              f"({len(actual)} files, all sha256 match)")
        return 0
    for rel in added:
        print(f"  ADDED (not in manifest): {rel}", file=sys.stderr)
    for rel in removed:
        print(f"  REMOVED (manifest orphan): {rel}", file=sys.stderr)
    for rel in changed:
        print(f"  CHANGED (stale sha256): {rel}", file=sys.stderr)
    print(
        f"FAIL: universal-sops drift — {len(added)} added / {len(removed)} "
        f"removed / {len(changed)} changed. Re-run "
        f"scripts/hash-universal-sops-manifest.py and commit the manifest "
        f"alongside the content change.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--check", action="store_true",
                        help="verify instead of generate; exit 1 on drift")
    args = parser.parse_args()
    if not SOPS_DIR.is_dir():
        print(f"FAIL: universal-sops dir not found at {SOPS_DIR}", file=sys.stderr)
        return 1
    return check() if args.check else generate()


if __name__ == "__main__":
    sys.exit(main())
