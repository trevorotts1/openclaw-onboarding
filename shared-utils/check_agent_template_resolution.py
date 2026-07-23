#!/usr/bin/env python3
"""
check_agent_template_resolution.py — Agent soul/identity template resolution gate.

Scans all agent SOUL.md and IDENTITY.md files for unresolved generator template
placeholders ({{UPPER_CASE}} tokens). Any file containing such markers is an
UNSAFE agent.

Usage:
    python3 check_agent_template_resolution.py --base REPO_ROOT [--json]

Exit: 0=clean, 3=violations found
"""

import argparse
import os
import re
import sys

_TEMPLATE_MARKER_RE = re.compile(r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}")


def find_markers(text: str) -> list[str]:
    return sorted(set(_TEMPLATE_MARKER_RE.findall(text)))


def check_file(filepath: str) -> dict | None:
    if not os.path.isfile(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as fh:
        content = fh.read()
    markers = find_markers(content)
    if not markers:
        return None
    marker_lines: dict[str, list[int]] = {}
    for lineno, line in enumerate(content.splitlines(), 1):
        for m in _TEMPLATE_MARKER_RE.findall(line):
            marker_lines.setdefault(m, []).append(lineno)
    return {
        "file": filepath,
        "marker_count": len(markers),
        "markers": markers,
        "occurrences": sum(len(v) for v in marker_lines.values()),
        "details": marker_lines,
    }


def scan_directory(base_dir: str) -> list[dict]:
    violations: list[dict] = []
    for root, _dirs, files in os.walk(base_dir):
        for fname in files:
            if fname in {"SOUL.md", "IDENTITY.md"}:
                v = check_file(os.path.join(root, fname))
                if v:
                    violations.append(v)
    return violations


def main() -> None:
    p = argparse.ArgumentParser(description="Check agent SOUL.md/IDENTITY.md for unresolved markers.")
    p.add_argument("--base", default=None, help="Repo root for specialist scan.")
    p.add_argument("--scan", default=None, help="Scan a directory tree.")
    p.add_argument("--json", action="store_true", help="JSON output.")
    args = p.parse_args()

    violations: list[dict] = []
    if args.scan:
        violations = scan_directory(args.scan)
    elif args.base:
        sd = os.path.join(args.base, "42-personal-assistant-library", "specialists")
        if os.path.isdir(sd):
            violations = scan_directory(sd)
        else:
            print(f"ERROR: {sd} not found", file=sys.stderr)
            sys.exit(2)
    else:
        p.print_help()
        sys.exit(1)

    if args.json:
        import json
        print(json.dumps({"violations": len(violations), "details": violations, "clean": not violations}, indent=2, default=str))
    elif not violations:
        print("OK: All agent SOUL.md / IDENTITY.md files are free of unresolved template markers.")
    else:
        print(f"BLOCKED: {len(violations)} file(s) contain unresolved template markers.")
        for v in violations:
            print(f"  {v['file']}: {v['markers']}")
    sys.exit(0 if not violations else 3)


if __name__ == "__main__":
    main()
