#!/usr/bin/env python3
"""Privacy scanner (unit S75-W01-U2).

Scans text artifacts for the classes the repair spec bans from shared
artifacts: person names, private run/host/chat identities, home directories,
SSH aliases, chat IDs, access-bearing URLs and one-off overrides. Technical
failure descriptions pass untouched; the scanner reports CLASSES AND
LOCATIONS ONLY -- matched values are never echoed, because echoing a private
value into a report would leak the very thing being scanned for.

Person-name screening runs against a denylist supplied at scan time
(``--denylist``); the denylist itself lives in private scratch and is never
part of any shared artifact.

Usage:
  python3 privacy/scan.py --scope <label> --denylist <file> <path> [<path> ...]

Prints one JSON object on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import re

# Patterns built from fragments so this detector never matches itself.
PATTERNS = {
    "home_directory": re.compile("(/Use" + "rs/|/ho" + "me/|/Vol" + "umes/|C:\\\\Use" + "rs\\\\|" + "~" + chr(92) + "/[A-Za-z])"),
    "ssh_alias": re.compile(r"\brescue-[a-z]+(?:-[a-z]+)+\b|\b[a-z]{2,}-mac\b"),
    "chat_id": re.compile(r"-100\d{6,}|\b\d{7,}\b"),
    "access_bearing_url": re.compile(
        r"https?://[^\s\"']*([?&](access_token|api_key|apikey|token|secret|password|sig|signature|credential)=|://[^/\s\"']+:[^@\s\"']+@)",
        re.I),
    "run_or_host_identity": re.compile(r"\brun-20\d{6}[-\d]*\b|\bhost:[0-9]+:[0-9]+\b"),
    "one_off_override": re.compile(
        r"\b[A-Z0-9_]*(OVERRIDE|BYPASS|EXEMPT)[A-Z0-9_]*\s*[:=]\s*[\"']?(?!<|synthetic|none)[A-Za-z0-9_./-]+"),
}
SUFFIXES = (".py", ".json", ".md", ".txt", ".sh", ".yml", ".yaml")


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for dirpath, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d != ".git"]
                for fn in files:
                    if fn.endswith(SUFFIXES):
                        yield os.path.join(dirpath, fn)
        elif os.path.isfile(p):
            yield p


def scan(scope, paths, denylist):
    names = []
    if denylist:
        with open(denylist, encoding="utf-8") as f:
            names = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    # Case-sensitive: person and run identities are capitalized proper nouns;
    # a case-insensitive match would flag the technical word "lyric" against a
    # same-spelled name. The report records this limitation.
    name_rx = [re.compile(r"\b" + re.escape(n) + r"\b") for n in names]
    findings = []
    files = 0
    for path in iter_files(paths):
        files += 1
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                for cls, rx in PATTERNS.items():
                    if rx.search(line):
                        findings.append({"file": path, "line": i, "class": cls})
                for rx in name_rx:
                    if rx.search(line):
                        findings.append({"file": path, "line": i, "class": "person_or_run_name"})
                        break
    return {"scope": scope, "files_scanned": files,
            "denylist_terms": len(names), "findings": findings,
            "findings_by_class": _count(findings)}


def _count(findings):
    out = {}
    for f in findings:
        out[f["class"]] = out.get(f["class"], 0) + 1
    return dict(sorted(out.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", required=True)
    ap.add_argument("--denylist")
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()
    print(json.dumps(scan(a.scope, a.paths, a.denylist), indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
