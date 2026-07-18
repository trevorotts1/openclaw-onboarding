#!/usr/bin/env python3
"""
qc-check-whatsapp-json.py — CI guard helper: a single tracked .json file must
not have plugins.entries.whatsapp.enabled == true (FLEET-STANDARDS.md §3 —
WhatsApp is permanently banned fleet-wide; the Hostinger wrapper auto-installs
WhatsApp on every boot when it sees this shape, causing a QR-scan crash-loop
that takes the entire gateway down).

Usage: python3 scripts/qc-check-whatsapp-json.py <file.json>
  exit 0 — no violation: a ZERO-BYTE file (not applicable), OR the file
           parses as JSON and is NOT plugins.entries.whatsapp.enabled:true
  exit 1 — REAL violation: file parses as a dict AND
           plugins.entries.whatsapp.enabled is truthy
  exit 2 — FAIL CLOSED: a NON-EMPTY file that could not be parsed
           (OSError/UnicodeError/JSONDecodeError) — distinct from both a
           real violation (1) and "not applicable" (0); the caller must
           treat this as a failure, not a silent pass

Extracted from qc-static.yml (FLEET-STANDARDS §3 step) as a real, independently
testable script file instead of an inline `python3 -c "..."` multi-line
string embedded in the workflow YAML. The prior inline version let
json.load()'s parse exception (JSONDecodeError, UnicodeDecodeError, etc.)
propagate as an uncaught traceback — python3 then exits non-zero for ANY
unparseable file, indistinguishable from the real "enabled:true" exit(1)
signal, so a 0-byte/malformed tracked .json (e.g. a legitimate empty
evidence artifact from a failed API call) was misread as a WhatsApp
fleet-ban violation: a guard crash was being reported as a product violation.

A zero-byte file (e.g. a verbatim-archived empty API-response body under
ledgers/evidence/) is genuinely not applicable and exits 0. A NON-EMPTY file
that fails to parse is NOT given the same pass: a genuinely corrupt/unreadable
tracked JSON file could otherwise never trip the fleet-ban gate, so it fails
closed (exit 2) instead of being silently waved through.
"""
import json
import sys

# Sentinel returned by has_whatsapp_enabled() for a non-empty file that
# failed to parse — distinct from True (real violation) and False (OK).
MALFORMED = "malformed"


def has_whatsapp_enabled(path: str):
    """Return True for a REAL violation (parses as a dict with
    plugins.entries.whatsapp.enabled truthy), False for "no violation"
    (zero-byte file, or parses cleanly without the flag set), or the
    MALFORMED sentinel for a non-empty file that failed to parse — that
    case must fail closed, never be treated as "OK"."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return MALFORMED
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        return MALFORMED
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
    result = has_whatsapp_enabled(argv[1])
    if result is MALFORMED:
        return 2
    return 1 if result else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
