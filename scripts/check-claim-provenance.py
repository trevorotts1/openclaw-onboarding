#!/usr/bin/env python3
"""check-claim-provenance.py -- ADVISORY claim-provenance linter.

Scans report-like text (ledgers, docs, changelog entries) for claims that
carry no provenance, and prints warnings. It is ADVISORY BY DESIGN: the
default exit code is always 0. It labels; it never halts work. That is an
operator ruling (advisory chosen over blocking, 2026-07-19), not an
implementation shortcut.

What it flags (each rule exists because the failure actually happened):

  R1 VERDICT-WITHOUT-EVIDENCE
     An uppercase verdict token -- "GATE RESULT", "PASS", "PASSED",
     "VERIFIED", "CONFIRMED", "GREEN", "DONE", "MERGED", or a check-mark --
     with no evidence token on the same line or within 2 lines.
     Incident: "GATE RESULT: PASS" written into a ledger AND a changelog
     from a run that had actually errored on a missing argument.

  R2 COUNT-WITHOUT-SOURCE
     A number attached to a counted noun ("50 pending", "34 boxes",
     "units: 28") with no adjacent evidence token. Incident: a footer said
     50 pending; a structured recount said 3.

  R3 ESTIMATE-WITHOUT-BASIS
     A duration estimate ("2-3 hours") with no `basis=` and no GUESS
     label. Incident: "2-3 hours" relayed unchecked from a subagent.

  R4 CAPABILITY-ASSERTION-WITHOUT-TEST
     A narrow set of high-signal capability phrases ("no API exists",
     "does not support", "cannot be done", "no way to") with no
     `tested=` marker, evidence token, or UNTESTED/UNKNOWN label.
     Incidents: "no API exists" (it did); "an agent can delete the post"
     (it could not).

Evidence tokens (any one, on the flagged line or within 2 lines):
  - a backtick span (a command or a path): `openclaw doctor`
  - a key marker: evidence:  src=  cmd=  exit=  basis=  tested=
  - a git sha (7-40 hex chars), a PR/run reference (#123), or a URL
  - a file path with a common artifact extension (.log .json .out .err ...)
  - an explicit [PROVEN: ...] tag

Honesty labels EXEMPT a line entirely: UNVERIFIED, UNKNOWN, UNTESTED,
GUESS, CLAIMED. The label IS the compliance -- this tool enforces
labeling, not omniscience.

Suppression: the literal token `claim-ok` anywhere on a line suppresses
all rules for that line (use `<!-- claim-ok: reason -->` in markdown, e.g.
for deliberate bad examples in teaching docs).

Usage:
  python3 scripts/check-claim-provenance.py FILE [FILE ...]
      Whole-file scan.
  python3 scripts/check-claim-provenance.py --diff BASE_REF
      Scan only lines ADDED relative to BASE_REF (what CI runs on a
      pull request). Scope is limited to ledgers/**, docs/**, and
      CHANGELOG.md so 62 skill directories of prose do not drown the
      signal.
  Add --strict to exit 1 when findings exist (for anyone who later wants
  a blocking mode; CI does NOT use it).

Output: plain "file:line [RULE] message" lines, plus GitHub Actions
::warning annotations and a step summary when running inside Actions.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

# ---------------------------------------------------------------- evidence

EVIDENCE_RES = [
    re.compile(r"`[^`]+`"),                                  # backtick span
    re.compile(r"\b(?:evidence|src|cmd|exit|basis|tested)\s*[:=]", re.I),
    re.compile(r"\bexit code\b", re.I),
    re.compile(r"\b[0-9a-f]{7,40}\b"),                        # git sha
    re.compile(r"#\d+\b"),                                    # PR / issue ref
    re.compile(r"https?://\S+"),
    re.compile(r"\b[\w./-]+\.(?:log|json|txt|out|err|sh|py|yml|yaml|sqlite)\b"),
    re.compile(r"\[PROVEN:", re.I),
]

# Labels that make a line honest on their own. Enforce labeling, not truth.
EXEMPT_RE = re.compile(
    r"\b(?:UNVERIFIED|UNKNOWN|UNTESTED|GUESS|CLAIMED)\b|claim-ok"
)

CONTEXT = 2  # lines of surrounding context in which evidence may live

# ------------------------------------------------------------------- rules

R1_VERDICT_RE = re.compile(
    r"GATE RESULT|\bPASS(?:ED)?\b|\bVERIFIED\b|\bCONFIRMED\b"
    r"|\bGREEN\b|\bDONE\b|\bMERGED\b|✅"
)
R2_COUNT_RE = re.compile(
    r"\b\d+\s+(?:pending|units?|boxes|files|clients|agents|episodes"
    r"|workflows|records|rows|errors|failures|checks|skills|tasks)\b"
    r"|\b(?:pending|failed|open|remaining|total)\s*[:=]\s*\d+\b",
    re.I,
)
R3_ESTIMATE_RE = re.compile(
    r"\b\d+\s*(?:-|–|to)\s*\d+\s*(?:hours?|hrs?|minutes?|mins?|days?|weeks?)\b"
    r"|\bETA\b.*?\d",
    re.I,
)
R4_CAPABILITY_RE = re.compile(
    r"\bno API exists\b|\bAPI does not exist\b|\bno way to\b"
    r"|\bnot possible\b|\bcannot be done\b|\bdoes(?:n't| not) support\b",
    re.I,
)

RULES = [
    ("R1", R1_VERDICT_RE, "verdict without evidence -- cite the artifact, command, or exit code that produced it"),
    ("R2", R2_COUNT_RE, "count without source -- state the command and the definition behind the number, or label it UNVERIFIED"),
    ("R3", R3_ESTIMATE_RE, "estimate without basis -- add basis= or the word GUESS"),
    ("R4", R4_CAPABILITY_RE, "capability assertion without a test -- add tested= evidence or label it UNKNOWN"),
]

SCOPE_PREFIXES = ("ledgers/", "docs/")
SCOPE_FILES = ("CHANGELOG.md",)


def in_scope(path: str) -> bool:
    return path.startswith(SCOPE_PREFIXES) or path in SCOPE_FILES


def has_evidence_near(lines: list[str], idx: int) -> bool:
    lo = max(0, idx - CONTEXT)
    hi = min(len(lines), idx + CONTEXT + 1)
    window = "\n".join(lines[lo:hi])
    return any(r.search(window) for r in EVIDENCE_RES)


def scan_lines(path: str, lines: list[str], only_lines: set[int] | None):
    """Yield (path, lineno, rule_id, message, text) findings."""
    for idx, line in enumerate(lines):
        lineno = idx + 1
        if only_lines is not None and lineno not in only_lines:
            continue
        if EXEMPT_RE.search(line):
            continue
        for rule_id, rule_re, message in RULES:
            if rule_re.search(line) and not has_evidence_near(lines, idx):
                yield (path, lineno, rule_id, message, line.strip())
                break  # one finding per line is enough


def added_lines_vs(base_ref: str) -> dict[str, set[int]]:
    """Map path -> set of line numbers added relative to merge-base(base, HEAD)."""
    base = subprocess.check_output(
        ["git", "merge-base", base_ref, "HEAD"], text=True
    ).strip()
    diff = subprocess.check_output(
        ["git", "diff", "--unified=0", "--no-color", base, "HEAD"], text=True
    )
    added: dict[str, set[int]] = {}
    path = None
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:]
        elif raw.startswith("@@") and path is not None:
            m = re.search(r"\+(\d+)(?:,(\d+))?", raw)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                added.setdefault(path, set()).update(range(start, start + count))
    return added


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    argv = [a for a in argv if a != "--strict"]

    targets: list[tuple[str, set[int] | None]] = []
    if argv and argv[0] == "--diff":
        if len(argv) < 2:
            print("usage: check-claim-provenance.py --diff BASE_REF [--strict]",
                  file=sys.stderr)
            return 2
        for path, lns in sorted(added_lines_vs(argv[1]).items()):
            if in_scope(path) and path.endswith((".md", ".txt")) and os.path.exists(path):
                targets.append((path, lns))
    else:
        targets = [(p, None) for p in argv]
        if not targets:
            print(__doc__)
            return 0

    findings = []
    for path, only in targets:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError as exc:
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
            continue
        findings.extend(scan_lines(path, lines, only))

    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    for path, lineno, rule_id, message, text in findings:
        print(f"{path}:{lineno} [{rule_id}] {message}\n    > {text}")
        if gha:
            print(f"::warning file={path},line={lineno},"
                  f"title=claim-provenance {rule_id}::{message}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("## Claim-provenance (advisory -- never blocks)\n\n")
            if findings:
                fh.write(f"{len(findings)} unproven claim(s) flagged. "
                         "Add provenance or an UNVERIFIED/UNKNOWN label.\n\n")
                for path, lineno, rule_id, message, _ in findings:
                    fh.write(f"- `{path}:{lineno}` **{rule_id}** {message}\n")
            else:
                fh.write("No unproven claims detected in the scanned lines.\n")

    if findings:
        print(f"\n{len(findings)} advisory finding(s). "
              "This check never blocks; label or cite and move on.")
    return 1 if (strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
