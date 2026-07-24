#!/usr/bin/env python3
"""
qc-validate-department-docs.py -- Cross-reference DEPARTMENTS.md against department-naming-map.json

Purpose: Validate that every canonical department ID listed in DEPARTMENTS.md
exists in department-naming-map.json's mandatory block, and that every mandatory
department in the naming map appears in DEPARTMENTS.md.

Exit codes:
  0 = clean (DEPARTMENTS.md matches the authoritative naming map)
  1 = drift detected (mismatches found)
  2 = usage error (missing files)

Usage:
  python3 scripts/qc-validate-department-docs.py
    [--departments-md PATH]  default: 23-ai-workforce-blueprint/DEPARTMENTS.md
    [--naming-map PATH]      default: 23-ai-workforce-blueprint/department-naming-map.json
    [--quiet]                suppress OK message
"""

import json
import os
import re
import sys


def resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = script_dir
    while repo_root != "/":
        if os.path.isfile(os.path.join(repo_root, ".git", "HEAD")):
            break
        if os.path.isfile(os.path.join(repo_root, "version")):
            break
        repo_root = os.path.dirname(repo_root)
    return os.path.join(repo_root, path)


def extract_dept_ids_from_md(departments_md_path: str):
    if not os.path.isfile(departments_md_path):
        print(f"ERROR: DEPARTMENTS.md not found at {departments_md_path}", file=sys.stderr)
        sys.exit(2)

    with open(departments_md_path, "r") as f:
        content = f.read()

    pattern = r"\*\*Canonical department IDs\s*\(\d+\s*mandatory\):\*\*.*?\n```\n(.*?)```"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print("ERROR: Could not find canonical department IDs code block in DEPARTMENTS.md", file=sys.stderr)
        sys.exit(2)

    ids_block = match.group(1).strip()
    ids = [id_.strip() for id_ in re.split(r"[,\n]+", ids_block) if id_.strip()]
    return ids


def get_mandatory_ids_from_naming_map(naming_map_path: str):
    if not os.path.isfile(naming_map_path):
        print(f"ERROR: department-naming-map.json not found at {naming_map_path}", file=sys.stderr)
        sys.exit(2)

    with open(naming_map_path, "r") as f:
        data = json.load(f)

    mandatory = data.get("mandatory", {})
    if not mandatory:
        print("ERROR: No 'mandatory' block found in department-naming-map.json", file=sys.stderr)
        sys.exit(2)

    return list(mandatory.keys())


def main():
    departments_md = "23-ai-workforce-blueprint/DEPARTMENTS.md"
    naming_map = "23-ai-workforce-blueprint/department-naming-map.json"
    quiet = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--departments-md" and i + 1 < len(args):
            departments_md = args[i + 1]
            i += 2
        elif args[i] == "--naming-map" and i + 1 < len(args):
            naming_map = args[i + 1]
            i += 2
        elif args[i] == "--quiet":
            quiet = True
            i += 1
        else:
            print(f"Usage: {sys.argv[0]} [--departments-md PATH] [--naming-map PATH] [--quiet]", file=sys.stderr)
            sys.exit(2)

    departments_md = resolve_path(departments_md)
    naming_map = resolve_path(naming_map)

    doc_ids = extract_dept_ids_from_md(departments_md)
    map_ids = get_mandatory_ids_from_naming_map(naming_map)

    doc_set = set(doc_ids)
    map_set = set(map_ids)

    in_doc_not_map = doc_set - map_set
    in_map_not_doc = map_set - doc_set

    has_errors = False

    if not quiet:
        print(f"Validating DEPARTMENTS.md canonical IDs against department-naming-map.json")
        print(f"  Doc IDs found:     {len(doc_ids)}")
        print(f"  Map mandatory IDs: {len(map_ids)}")

    if in_doc_not_map:
        has_errors = True
        print(f"\nFABRICATED IDs (in DEPARTMENTS.md but NOT in naming map):", file=sys.stderr)
        for id_ in sorted(in_doc_not_map):
            print(f"  - {id_}", file=sys.stderr)

    if in_map_not_doc:
        has_errors = True
        print(f"\nMISSING IDs (in naming map but NOT in DEPARTMENTS.md):", file=sys.stderr)
        for id_ in sorted(in_map_not_doc):
            print(f"  - {id_}", file=sys.stderr)

    if len(doc_ids) != len(map_ids):
        has_errors = True
        print(f"\nCOUNT MISMATCH: DEPARTMENTS.md lists {len(doc_ids)} IDs, naming map has {len(map_ids)}", file=sys.stderr)

    if has_errors:
        print(f"\nVALIDATION FAILED: DEPARTMENTS.md does not match department-naming-map.json", file=sys.stderr)
        sys.exit(1)

    if not quiet:
        print(f"\nVALIDATION PASSED: All {len(doc_ids)} canonical IDs match the naming map.")
    sys.exit(0)


if __name__ == "__main__":
    main()
