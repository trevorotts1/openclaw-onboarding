#!/usr/bin/env python3
"""check_lattice_citation.py -- U89/GK-27 QC citation tripwire.

Verifies, for one skill directory, that:
  1. the skill's SKILL.md carries the one-line pointer to
     docs/CONTENT-CONVERSATION-LATTICE.md (no content duplication -- pointers
     only, per the standing reference-links doctrine), and
  2. every relationship-lattice edge citation this skill OWNS still points at
     real, unchanged ground truth: either an exact line still contains the
     substring the lattice doc quotes, or a file the edge depends on still
     exists on disk.

This is the drift tripwire: if a cited SKILL.md/INSTALL.md/CHANGELOG.md/etc.
line is edited so the quoted substring no longer appears there, or a file the
doc cites is deleted, this script FAILS for the owning skill until the
manifest (docs/lattice-citations.json) and the lattice doc's edge table are
both updated to match the new ground truth. It never fabricates a PASS.

Reads its data from docs/lattice-citations.json (see that file's "_purpose").
Pure stdlib -- no network, no live-box dependency, safe on a fresh clone.

Exit codes:
  0 -- pointer present AND every citation this skill owns still holds.
  1 -- one or more citations failed the tripwire, or the pointer is missing.
  2 -- usage/environment error (bad --skill name, manifest not found, etc).

Usage:
  check_lattice_citation.py --repo-root DIR --skill SKILL_DIR_NAME [--manifest PATH] [--edge-id ID [...]] [-q]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_manifest(manifest_path: Path) -> dict:
    with manifest_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def check_pointer(repo_root: Path, skill: str, pointer_spec: dict, quiet: bool) -> bool:
    target = repo_root / skill / pointer_spec["file"]
    must_contain = pointer_spec["must_contain"]
    if not target.is_file():
        if not quiet:
            print(f"  FAIL pointer -- {target} does not exist")
        return False
    text = target.read_text(encoding="utf-8", errors="replace")
    ok = must_contain in text
    if not quiet:
        status = "PASS" if ok else "FAIL"
        print(f"  {status} pointer -- {skill}/{pointer_spec['file']} contains lattice-doc pointer")
    return ok


def check_line_citation(repo_root: Path, citation: dict, quiet: bool) -> bool:
    file_rel = citation["file"]
    target = repo_root / file_rel
    line_no = citation["line"]
    must_contain = citation["must_contain"]
    if not target.is_file():
        if not quiet:
            print(f"  FAIL citation -- {file_rel}:{line_no} -- file does not exist")
        return False
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    if line_no < 1 or line_no > len(lines):
        if not quiet:
            print(f"  FAIL citation -- {file_rel}:{line_no} -- file only has {len(lines)} line(s) (DRIFT)")
        return False
    actual = lines[line_no - 1]
    ok = must_contain in actual
    if not quiet:
        status = "PASS" if ok else "FAIL"
        detail = "" if ok else f" -- expected substring not found on that line (DRIFT): {must_contain!r}"
        print(f"  {status} citation -- {file_rel}:{line_no}{detail}")
    return ok


def check_exists_citation(repo_root: Path, citation: dict, quiet: bool) -> bool:
    file_rel = citation["file"]
    target = repo_root / file_rel
    ok = target.is_file()
    if not quiet:
        status = "PASS" if ok else "FAIL"
        print(f"  {status} citation -- {file_rel} exists")
    return ok


def check_citation(repo_root: Path, citation: dict, quiet: bool) -> bool:
    if citation.get("exists"):
        return check_exists_citation(repo_root, citation, quiet)
    if "line" in citation and "must_contain" in citation:
        return check_line_citation(repo_root, citation, quiet)
    raise ValueError(f"malformed citation entry (needs either 'exists' or 'line'+'must_contain'): {citation!r}")


def run(repo_root: Path, skill: str, manifest: dict, edge_ids: list[str] | None, quiet: bool) -> int:
    all_ok = True

    pointer_spec = manifest.get("skill_pointers", {}).get(skill)
    if pointer_spec is None:
        print(f"ERROR: unknown skill {skill!r} -- not present in skill_pointers of manifest", file=sys.stderr)
        return 2
    if not check_pointer(repo_root, skill, pointer_spec, quiet):
        all_ok = False

    owned_edges = [e for e in manifest.get("edges", []) if e.get("owner_skill") == skill]
    if edge_ids:
        owned_edges = [e for e in owned_edges if e["id"] in edge_ids]

    if not owned_edges and not quiet:
        print(f"  (no lattice edges owned by {skill})")

    for edge in owned_edges:
        if not quiet:
            print(f"  -- edge {edge['id']}: {edge['label']}")
        for citation in edge.get("citations", []):
            if not check_citation(repo_root, citation, quiet):
                all_ok = False

    return 0 if all_ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", required=True, help="path to the repo checkout root")
    parser.add_argument("--skill", required=True, help="skill directory name, e.g. 35-social-media-planner")
    parser.add_argument("--manifest", default=None, help="path to lattice-citations.json (default: <repo-root>/docs/lattice-citations.json)")
    parser.add_argument("--edge-id", action="append", default=None, help="restrict edge citation checks to this edge id (repeatable); pointer check always runs")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress per-check lines, print only the final result")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else (repo_root / "docs" / "lattice-citations.json")

    if not manifest_path.is_file():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        return 2

    manifest = load_manifest(manifest_path)

    if not args.quiet:
        print(f"=== lattice citation tripwire -- {args.skill} ===")

    rc = run(repo_root, args.skill, manifest, args.edge_id, args.quiet)

    if not args.quiet:
        print("PASS" if rc == 0 else "FAIL", f"-- lattice citation tripwire for {args.skill}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
