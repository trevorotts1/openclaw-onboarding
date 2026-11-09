#!/usr/bin/env python3
"""T-08 / F5 proof instrument: the trusted-contact-mapping gate decision.

One instrument, N trees. Run once per tree against that tree's own skill
directory, never against a checked-out overlay:

    python3 -I evidence/W05/f5_proof.py <tree>/38-conversational-ai-system A
    python3 -I evidence/W05/f5_proof.py <tree>/38-conversational-ai-system B

Exit 0 only when every case in the chosen set holds; exit 1 otherwise, so a
tree that regresses cannot be reported as passing. One line per case prints the
observed code/decision/reason/errors beside the expected shape, so a reader can
audit the count instead of trusting it.

The case list is part of the measurement. Two sets are shipped because the
original 1/8 -> 4/8 -> 8/8 table was produced with set B, whose only pre-fix
"held" case is the non-string one, and it held by accident: the pre-fix error
text is `$gate: unexpected property 'trusted_contact_mapping_evidence_id'`,
which CONTAINS the key name, so an `any(<key> in e)` assertion is satisfied by
the rejection message itself. Set A replaces that case with the
format-mark-only (U+200B) whitespace variant, which no error text can satisfy
by accident. Set A is the independent case list; set B is kept only so the
historical table can be reproduced exactly (1/8 -> 4/8 -> 8/8). The end state
is 8/8 under both sets.

Case set A (independent, canonical):
  C1 absent key           -> INVALID_GATE naming the field
  C2 null                 -> SUPPRESSED / NO_TRUSTED_CONTACT_MAPPING, errors []
  C3 ""                   -> SUPPRESSED / NO_TRUSTED_CONTACT_MAPPING, errors []
  C4 "   "                -> SUPPRESSED / NO_TRUSTED_CONTACT_MAPPING, errors []
  C5 " \\t\\n"             -> SUPPRESSED / NO_TRUSTED_CONTACT_MAPPING, errors []
  C6 U+200B only          -> SUPPRESSED / NO_TRUSTED_CONTACT_MAPPING, errors []
  C7 "ev-tcm-1"           -> code 0, DISPATCHED / GATE_ALLOWED
  C8 "  ev-tcm-1  "       -> code 0, DISPATCHED / GATE_ALLOWED

Case set B (the historical list; identical except C6 -> B6):
  B6 non-string (123)     -> INVALID_GATE naming the field
"""
from __future__ import annotations

import copy
import io
import contextlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

KEY = "trusted_contact_mapping_evidence_id"
ZWS = "​"

CASES_A = [
    ("C1-absent-key", "__DELETE__", 1, "INVALID_GATE", None, KEY),
    ("C2-null", "__NULL__", 1, "SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING", None),
    ("C3-empty-string", "", 1, "SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING", None),
    ("C4-space", "   ", 1, "SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING", None),
    ("C5-tab-newline", " \t\n", 1, "SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING", None),
    ("C6-format-mark-only", ZWS, 1, "SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING", None),
    ("C7-real-id", "ev-tcm-1", 0, "DISPATCHED", "GATE_ALLOWED", None),
    ("C8-padded-real-id", "  ev-tcm-1  ", 0, "DISPATCHED", "GATE_ALLOWED", None),
]

CASES_B = [
    ("B1-absent-key", "__DELETE__", 1, "INVALID_GATE", None, KEY),
    ("B2-null", "__NULL__", 1, "SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING", None),
    ("B3-empty-string", "", 1, "SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING", None),
    ("B4-space", "   ", 1, "SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING", None),
    ("B5-tab-newline", " \t\n", 1, "SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING", None),
    ("B6-non-string", "__INT__", 1, "INVALID_GATE", None, KEY),
    ("B7-real-id", "ev-tcm-1", 0, "DISPATCHED", "GATE_ALLOWED", None),
    ("B8-padded-real-id", "  ev-tcm-1  ", 0, "DISPATCHED", "GATE_ALLOWED", None),
]

CASE_SETS = {"A": CASES_A, "B": CASES_B}


def run_case(contracts, fixtures, action, name, value, exp_code, exp_dec, exp_reason, exp_err):
    gate_src = json.loads((fixtures / "gates" / "person-allow.json").read_text(encoding="utf-8"))
    gate = copy.deepcopy(gate_src)
    if value == "__DELETE__":
        gate.pop(KEY, None)
    elif value == "__NULL__":
        gate[KEY] = None
    elif value == "__INT__":
        gate[KEY] = 123
    else:
        gate[KEY] = value

    tmp = Path(tempfile.mkdtemp(prefix="t08-f5-probe-"))
    try:
        gpath = tmp / "gate.json"
        gpath.write_text(json.dumps(gate), encoding="utf-8")
        ledger = str(tmp / "ledger.json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = contracts.main([
                "dispatch", "--action", action, "--gate", str(gpath),
                "--ledger", ledger, "--now", "2026-10-24T10:01:00Z",
            ])
        try:
            payload = json.loads(buf.getvalue())
        except json.JSONDecodeError:
            payload = {"raw": buf.getvalue()[:200]}

        dec = payload.get("decision", "<missing>")
        reason = payload.get("reason", "<missing>")
        errors = payload.get("errors", "<missing>")

        ok, why = True, []
        if code != exp_code:
            ok = False
            why.append("code=%s want=%s" % (code, exp_code))
        if dec != exp_dec:
            ok = False
            why.append("decision=%s want=%s" % (dec, exp_dec))
        if exp_reason is not None and reason != exp_reason:
            ok = False
            why.append("reason=%r want=%r" % (reason, exp_reason))
        if exp_err is not None:
            if not (isinstance(errors, list) and any(exp_err in e for e in errors)):
                ok = False
                why.append("errors=%r want one containing %r" % (errors, exp_err))
        if exp_reason == "NO_TRUSTED_CONTACT_MAPPING" and errors != []:
            ok = False
            why.append("errors=%r want []" % (errors,))

        print("  %-22s %-4s code=%s decision=%s reason=%r errors=%r %s"
              % (name, "HELD" if ok else "MISS", code, dec, reason, errors,
                 ("| " + "; ".join(why)) if why else ""))
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).resolve()
    set_name = sys.argv[2] if len(sys.argv) > 2 else "A"
    if set_name not in CASE_SETS:
        print("unknown case set %r (choose A or B)" % set_name)
        return 2
    cases = CASE_SETS[set_name]
    tools = root / "tools"
    sys.path.insert(0, str(tools))
    import pb_contracts as contracts  # noqa: WPS433

    fixtures = tools / "tests" / "fixtures" / "pb-contracts"
    action = str(fixtures / "outbound" / "person-gift.json")

    print("tree=%s set=%s" % (root, set_name))
    held = sum(
        1 if run_case(contracts, fixtures, action, *case) else 0 for case in cases
    )
    print("RESULT set=%s held=%d/%d" % (set_name, held, len(cases)))
    return 0 if held == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
