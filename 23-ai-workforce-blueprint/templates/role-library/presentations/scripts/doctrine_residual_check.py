#!/usr/bin/env python3
"""
doctrine_residual_check.py — GUARD B: RETIRED-DOCTRINE RESIDUAL LINT.

================================================================================
A doctrine VALUE that has been retired (e.g. the old hook ">= 7 times" FLOOR that
produced the reference-case 40-slide footer-stamping) must never quietly creep
back into the Presentations tree as a LIVE instruction. Retiring a value is a
contract: the value is registered in retired-doctrine-patterns.json, and this
check greps the tree for it. Any occurrence that is NOT explicitly framed as
history/retirement (no allowed_context_marker on the line or within the
configured context window) is an OFFENDER and fails CI non-zero.
================================================================================

ZERO third-party deps (stdlib json / re / glob / pathlib only).

REGISTRY: ../retired-doctrine-patterns.json  (sibling of the scripts dir)
  {
    "context_window": <int lines around a match to scan for a marker>,
    "allowed_context_markers": [<substring markers, case-insensitive>],
    "patterns": [
      {"id","why","pattern"(regex),"scope"(glob),
       "near"(optional substring that must ALSO appear on the match line),
       "allowed_context_markers"(optional per-pattern override)}
    ]
  }

SCOPE globs are resolved relative to the presentations/ root (the registry's
parent dir). A match is an OFFENDER when the matched line carries the retired
value AND (a) — when a `near` term is set — that term is present on the line,
AND (b) NEITHER the matched line NOR any line within +/- context_window lines
contains an allowed_context_marker.

EXIT CODES:
    0 — clean: every retired-value occurrence is framed as history/retirement.
    1 — one or more OFFENDERS: a retired value present as a LIVE instruction.
    2 — could not run (missing/unparseable registry, bad regex).

USAGE:
    python3 doctrine_residual_check.py            # human report
    python3 doctrine_residual_check.py --json      # machine-readable
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../presentations/scripts
PRES_DIR = HERE.parent                            # .../presentations
REGISTRY = PRES_DIR / "retired-doctrine-patterns.json"


def _fatal(msg):
    print(f"FATAL (doctrine_residual_check cannot run): {msg}", file=sys.stderr)
    sys.exit(2)


def load_registry():
    if not REGISTRY.exists():
        _fatal(f"retired-doctrine-patterns.json not found (looked at {REGISTRY}).")
    try:
        reg = json.loads(REGISTRY.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"retired-doctrine-patterns.json is not valid JSON: {exc}")
    if "patterns" not in reg or not isinstance(reg["patterns"], list):
        _fatal("registry missing a 'patterns' list.")
    return reg


def _markers_for(reg, pat):
    markers = pat.get("allowed_context_markers")
    if markers is None:
        markers = reg.get("allowed_context_markers", [])
    return [m.lower() for m in markers]


def _has_marker(lines, idx, window, markers):
    """True if any line within +/- window of `idx` contains an allowed marker."""
    lo = max(0, idx - window)
    hi = min(len(lines), idx + window + 1)
    blob = "\n".join(lines[lo:hi]).lower()
    return any(m in blob for m in markers)


def run_check(reg):
    offenders = []   # {id, file, line_no, line, why}
    scanned_files = 0
    window = int(reg.get("context_window", 2))

    for pat in reg["patterns"]:
        pid = pat.get("id", "<no-id>")
        scope = pat.get("scope", "**/*.md")
        near = pat.get("near")
        near_l = near.lower() if near else None
        markers = _markers_for(reg, pat)
        try:
            rx = re.compile(pat["pattern"], re.IGNORECASE | re.MULTILINE)
        except re.error as exc:
            _fatal(f"pattern {pid!r} has an invalid regex: {exc}")

        for fpath in sorted(PRES_DIR.glob(scope)):
            if not fpath.is_file():
                continue
            scanned_files += 1
            try:
                text = fpath.read_text(errors="replace")
            except Exception:  # noqa: BLE001
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if not rx.search(line):
                    continue
                # A `near` term (e.g. 'hook') must ALSO be on the line — this is
                # what keeps the value-pattern (a bare '7 times') from matching an
                # unrelated context (confidence_score >= 7, decorative '7 times').
                if near_l and near_l not in line.lower():
                    continue
                if _has_marker(lines, i, window, markers):
                    continue  # framed as history/retirement — allowed
                offenders.append({
                    "id": pid,
                    "file": str(fpath.relative_to(PRES_DIR)),
                    "line_no": i + 1,
                    "line": line.strip()[:240],
                    "why": pat.get("why", ""),
                })

    return offenders, scanned_files


def main():
    as_json = "--json" in sys.argv[1:]
    reg = load_registry()
    offenders, scanned = run_check(reg)

    if as_json:
        print(json.dumps({
            "clean": not offenders,
            "patterns": [p.get("id") for p in reg["patterns"]],
            "files_scanned": scanned,
            "offenders": offenders,
        }, indent=2))
    else:
        if not offenders:
            print("=== doctrine_residual_check: RETIRED-DOCTRINE RESIDUAL LINT (Guard B) ===")
            print(f"patterns: {len(reg['patterns'])}  scope-file-scans: {scanned}")
            print("CLEAN — every retired-value occurrence is framed as history/retirement "
                  "(carries an allowed_context_marker). No retired doctrine is present as a "
                  "live instruction.")
        else:
            print("=== doctrine_residual_check: RETIRED-DOCTRINE RESIDUAL DETECTED ===",
                  file=sys.stderr)
            for o in offenders:
                print(f"  OFFENDER [{o['id']}] {o['file']}:{o['line_no']}: {o['line']}",
                      file=sys.stderr)
                if o["why"]:
                    print(f"      why retired: {o['why']}", file=sys.stderr)
            print(f"\n{len(offenders)} offender(s). A retired doctrine value is present as a "
                  "LIVE instruction. Either remove it, or — if it is genuinely a historical "
                  "note — add an allowed_context_marker (retired / replaced / historical / "
                  "do not re-introduce) on the line or within the context window. See "
                  "retired-doctrine-patterns.json.", file=sys.stderr)

    sys.exit(1 if offenders else 0)


if __name__ == "__main__":
    main()
