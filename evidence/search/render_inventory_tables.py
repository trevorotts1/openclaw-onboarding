#!/usr/bin/env python3
"""Render the search register into the T-01 inventory Markdown.

Reads evidence/current-onboarding-evidence.json and replaces everything between
the two register markers in evidence/t01-interface-inventory.md with a table of
every search: command, scope, exit code, count, verdict and control.

Idempotent: running it twice produces the same file.

Usage: python3 -I evidence/search/render_inventory_tables.py --root <repo>
"""

import argparse
import json
import os
import sys

START = "<!-- SEARCH-REGISTER:START -->"
END = "<!-- SEARCH-REGISTER:END -->"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    opts = parser.parse_args()
    root = os.path.abspath(opts.root)

    with open(os.path.join(root, "evidence", "current-onboarding-evidence.json"), "r", encoding="utf-8") as fh:
        data = json.load(fh)

    lines = []
    lines.append("| # | Search id | Interface | Command | Scope | rc | count | verdict | control |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for index, rec in enumerate(data["searches"], start=1):
        ctl = rec.get("control")
        ctl_text = "-" if not ctl else "%d matches" % ctl["count"]
        command = rec["command"].replace("|", "\\|")
        scope = rec["scope"].replace("|", "\\|")
        lines.append(
            "| %d | `%s` | %s | `%s` | %s | %d | %d | %s | %s |"
            % (index, rec["id"], rec["interface"], command, scope,
               rec["rc"], rec["count"], rec["verdict"], ctl_text)
        )
    table = "\n".join(lines)

    md_path = os.path.join(root, "evidence", "t01-interface-inventory.md")
    with open(md_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if START not in text or END not in text:
        raise SystemExit("register markers missing from %s" % md_path)
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    new_text = head + START + "\n\n" + table + "\n\n" + END + tail
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    print("rendered %d searches into %s" % (len(data["searches"]), md_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
