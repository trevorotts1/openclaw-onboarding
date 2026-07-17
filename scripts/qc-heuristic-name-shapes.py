#!/usr/bin/env python3
"""
qc-heuristic-name-shapes.py — ADVISORY, roster-free floor for
scripts/qc-assert-no-client-names.sh.

WHY THIS EXISTS:
  The authoritative check in qc-assert-no-client-names.sh can only catch a
  REAL client name if it is listed in the externalized, gitignored roster
  ($OPENCLAW_CLIENT_ROSTER / ~/.openclaw/client-roster.txt). CI never has
  that roster (see the fail-closed change in qc-assert-no-client-names.sh),
  and even on an operator box the roster can lag a newly onboarded client.
  This script is a second, INDEPENDENT signal that needs no roster at all:
  it flags name-SHAPED content (two-to-four Title Case words) sitting in
  fields/columns/paths whose own label says they hold an identity, or in
  free-text prose shapes a human name is typically attributed in
  ("... for <Name>", "... | <Name> |" table/CSV cells).

WHY IT IS ADVISORY, NOT A GATE (this is the important part):
  This was measured, not assumed. Three variants were dry-run against this
  repo's own tracked tree before this script was written:
    - unscoped "any two Title-Case words" anywhere in tracked prose:
        ~250,000 hits across ~4,650 of ~5,800 files (unusable).
    - the same pattern restricted to the one directory class where the
      real incident this script responds to actually happened
      (ledgers/evidence/**): still tens of hits per handful of files,
      including the operator's own name in a fixture explicitly marked
      "NOT a client" — i.e. the shape cannot tell "operator" from "client".
    - JSON/CSV values restricted to name-anchored keys/headers (name,
      client, owner, contact, assignee, first_name, last_name, ...),
      even after excluding examples/fixtures/templates paths: 40 hits
      across 20 files on a clean main branch, none of them a real name —
      department names, funnel names, persona names, product names.
  A heuristic that fails the build on ~20-30 legitimate files while still
  missing the incident it was written for (see below) is worse than no
  heuristic: it trains reviewers to click past red, which is the exact
  failure mode this whole repair effort exists to close. So this script
  never fails the build. It prints candidates to stderr for a human, and
  always exits 0.

WHAT THIS SCRIPT WOULD NOT HAVE CAUGHT (documented, not hidden):
  The PR that motivated this repair (evidence redaction that missed real
  identities) had those identities embedded inside free-text n8n workflow
  and node LABELS inside audit-report/CSV evidence artifacts — not under
  an identity-shaped key, and indistinguishable by shape from the hundreds
  of ordinary "Branch 1A - <ProductName> <ProductName>" style workflow
  labels in the same files. No roster-free pattern tested here separates
  that signal from that noise. Only the roster-based authoritative check
  (which requires real roster data — never committed to this repo, and
  not something this script or its caller may fabricate or provision) can
  do that reliably. That is reported as an operator decision, not solved
  here.

Usage:
  python3 scripts/qc-heuristic-name-shapes.py --repo-root /path/to/repo
  Always exits 0. Prints one "ADVISORY" line per candidate to stderr, or
  a single "no candidates" line if none were found. Never printed: the
  actual matched name-shaped text — only file, line/field, and shape.
"""
import csv
import json
import os
import re
import sys

# Identity-anchored keys/headers only — deliberately NOT bare "name" (that
# catches department_name/funnel_name/product_name noise measured above).
NAME_KEYS = {
    "client_name", "owner", "owner_name", "contact", "contact_name",
    "full_name", "client", "assignee", "first_name", "last_name",
}

# Prose shapes restricted to the incident's own file class — evidence,
# audit, and ledger artifacts — never run repo-wide (measured: unusable).
PROSE_PATH_MARKERS = ("ledgers/", "evidence", "audit", "report")

EXCLUDE_SUBSTR = (
    "/examples/", "/fixtures/", "/templates/", "/broken-variants/",
    "golden-", "/test/", "/tests/", "_stage1_drafts/",
    "/scripts/qc-assert-no-client-names.sh",
    "/scripts/client-roster.example.txt",
)

VALUE_RE = re.compile(r"^[A-Z][a-z]{1,20}(\s+[A-Z][a-z]{1,20}){1,3}$")
FOR_RE = re.compile(r"\bfor\s+([A-Z][a-z]{1,15}\s+[A-Z][a-z]{1,15})\b")
PIPE_RE = re.compile(r"\|\s*([A-Z][a-z]{1,15}\s+[A-Z][a-z]{1,15})\s*\|")

_DICT_CACHE = None


def _dict_words():
    global _DICT_CACHE
    if _DICT_CACHE is not None:
        return _DICT_CACHE
    words = set()
    for path in ("/usr/share/dict/words",):
        try:
            with open(path, errors="ignore") as fh:
                for line in fh:
                    w = line.strip()
                    if w:
                        words.add(w.lower())
        except OSError:
            continue
    _DICT_CACHE = words
    return words


def _looks_like_name(value):
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not VALUE_RE.match(v):
        return False
    words = _dict_words()
    parts = v.split()
    if words and all(p.lower() in words for p in parts):
        return False  # every word is common English -> a phrase, not a name
    return True


def _excluded(rel_path):
    return any(s in rel_path for s in EXCLUDE_SUBSTR)


def _walk_json(obj, hits, rel):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in NAME_KEYS and _looks_like_name(v):
                hits.append(f"{rel} :: JSON key '{k}' holds a name-shaped value")
            _walk_json(v, hits, rel)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json(item, hits, rel)


def scan_json(path, rel, hits):
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            data = json.load(fh)
    except Exception:
        return
    _walk_json(data, hits, rel)


def scan_csv(path, rel, hits):
    try:
        with open(path, newline="", encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return
            name_cols = [c for c in reader.fieldnames if c and c.strip().lower() in NAME_KEYS]
            if not name_cols:
                return
            for i, row in enumerate(reader, 2):
                for c in name_cols:
                    if _looks_like_name(row.get(c)):
                        hits.append(f"{rel}:{i} :: CSV column '{c}' holds a name-shaped value")
    except Exception:
        return


def scan_prose(path, rel, hits):
    if not any(m in rel for m in PROSE_PATH_MARKERS):
        return
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        return
    for i, line in enumerate(lines, 1):
        if FOR_RE.search(line):
            hits.append(f"{rel}:{i} :: 'for <Name>' prose shape")
        if PIPE_RE.search(line):
            hits.append(f"{rel}:{i} :: '| <Name> |' table/CSV shape")


def _list_tracked(root, patterns):
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files", "--"] + list(patterns),
            capture_output=True, text=True, check=False,
        ).stdout
    except FileNotFoundError:
        return []
    return [line for line in out.splitlines() if line]


def main(argv):
    repo_root = "."
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--repo-root" and i + 1 < len(args):
            repo_root = args[i + 1]
            i += 2
        else:
            i += 1

    hits = []
    for rel in _list_tracked(repo_root, ["*.json"]):
        if _excluded(rel):
            continue
        scan_json(os.path.join(repo_root, rel), rel, hits)
    for rel in _list_tracked(repo_root, ["*.csv"]):
        if _excluded(rel):
            continue
        scan_csv(os.path.join(repo_root, rel), rel, hits)
    for rel in _list_tracked(repo_root, ["*.md", "*.txt", "*.csv", "*.err", "*.log"]):
        if _excluded(rel):
            continue
        scan_prose(os.path.join(repo_root, rel), rel, hits)

    if hits:
        print(
            f"[qc-heuristic-name-shapes] ADVISORY (non-blocking) — {len(hits)} "
            "name-shaped candidate(s) found. These are NOT roster-verified and "
            "include false positives by design (see script header); review by "
            "hand, do not treat as authoritative:",
            file=sys.stderr,
        )
        for h in hits:
            print(f"  ADVISORY: {h}", file=sys.stderr)
    else:
        print(
            "[qc-heuristic-name-shapes] ADVISORY (non-blocking) — no "
            "name-shaped candidates found in the scoped fields/paths. This is "
            "NOT proof of a clean tree; see script header for what this "
            "heuristic cannot see.",
            file=sys.stderr,
        )
    return 0  # always advisory-only; never fails the build


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
