#!/usr/bin/env python3
"""
qc-check-whatsapp-json.py — CI guard helper: a single tracked .json file must
not have plugins.entries.whatsapp.enabled == true (FLEET-STANDARDS.md §3 —
WhatsApp is permanently banned fleet-wide; the Hostinger wrapper auto-installs
WhatsApp on every boot when it sees this shape, causing a QR-scan crash-loop
that takes the entire gateway down).

Usage: python3 scripts/qc-check-whatsapp-json.py <file.json>
  exit 0 — no violation (file parses and is NOT plugins.entries.whatsapp.enabled:true,
           OR the file could not be parsed as JSON at all)
  exit 1 — REAL violation: file parses as a dict AND
           plugins.entries.whatsapp.enabled is truthy

Extracted from qc-static.yml (FLEET-STANDARDS §3 step) as a real, independently
testable script file instead of an inline `python3 -c "..."` multi-line
string embedded in the workflow YAML. The prior inline version let
json.load()'s parse exception (JSONDecodeError, UnicodeDecodeError, etc.)
propagate as an uncaught traceback — python3 then exits non-zero for ANY
unparseable file, indistinguishable from the real "enabled:true" exit(1)
signal, so a 0-byte/malformed tracked .json (e.g. a legitimate empty
evidence artifact from a failed API call) was misread as a WhatsApp
fleet-ban violation. A file that FAILS TO PARSE is simply unassessable —
that is not a whatsapp violation and must not fail the guard.
"""
import json
import sys


def has_whatsapp_enabled(path: str) -> bool:
    """Return True only for a REAL violation: the file parses as a JSON
    object and plugins.entries.whatsapp.enabled is truthy. Any parse
    failure (empty file, malformed JSON, non-UTF8, missing file, etc.)
    returns False — "can't parse" is never treated as "enabled: true"."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    return bool(
        data.get("plugins", {})
        .get("entries", {})
        .get("whatsapp", {})
        .get("enabled")
    )


def main(argv):
    if len(argv) != 2:
        print("usage: qc-check-whatsapp-json.py <file.json>", file=sys.stderr)
        return 2
    return 1 if has_whatsapp_enabled(argv[1]) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
