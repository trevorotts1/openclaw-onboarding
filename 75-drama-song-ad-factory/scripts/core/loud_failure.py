"""loud_failure -- no silent failure, ever (Trevor's rule, skill 75).

Anything that goes wrong or is skipped records a NAMED entry here and prints it
at once to stderr. The final receipt carries every entry (attach), a FAILURE
flips the receipt to outcome "error", and a WARNING stays visible. Stdlib only.

  fail(code, detail)  -- a gate or step broke; the run must not look clean
  warn(code, detail)  -- a deliberate, documented fail-soft path (for example a
                         Command Center board that cannot be reached); still
                         printed as a WARNING line and listed in the receipt
"""
import json
import os
import sys

_ENTRIES = []


def _add(kind, code, detail):
    entry = {"kind": kind, "code": str(code), "detail": str(detail)}
    _ENTRIES.append(entry)
    line = "%s %s: %s" % (kind, entry["code"], entry["detail"])
    print(line, file=sys.stderr)
    path = os.environ.get("DSAF_FAILURE_LOG")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:      # the log itself failing is also loud
            print("WARNING FAILURE_LOG_UNWRITABLE: %s: %s" % (path, exc),
                  file=sys.stderr)
    return entry


def fail(code, detail=""):
    return _add("FAILURE", code, detail)


def warn(code, detail=""):
    return _add("WARNING", code, detail)


def entries():
    return list(_ENTRIES)


def reset():
    del _ENTRIES[:]


def lines():
    return ["%s %s: %s" % (e["kind"], e["code"], e["detail"]) for e in _ENTRIES]


def attach(receipt):
    """Put every entry on the receipt. A FAILURE turns an ok receipt into an
    error receipt, so a broken gate can never ship a clean-looking result."""
    fails = [e for e in _ENTRIES if e["kind"] == "FAILURE"]
    warns = [e for e in _ENTRIES if e["kind"] == "WARNING"]
    receipt["failures"] = fails
    receipt["warnings"] = warns
    if fails and receipt.get("outcome") == "ok":
        receipt["outcome"] = "error"
        receipt["reason_code"] = "LOUD_FAILURE"
        receipt["next_action"] = "; ".join(
            "%s: %s" % (e["code"], e["detail"]) for e in fails)
    return receipt
