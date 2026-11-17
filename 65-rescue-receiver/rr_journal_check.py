#!/usr/bin/env python3
"""rr_journal_check.py - was this instruction interrupted in the middle of an earlier run?

It REPLACES the function _rr_prior_interrupted in 65-rescue-receiver/rescue-poll.sh,
which decided whether to run an agent turn by running "grep -lF" over the journal
folder with errors thrown away. With grep, a journal file that cannot be read looks
exactly like "no earlier attempt", so the turn runs a second time. That is a false
pass.

This script opens every journal row and every done record as JSON. A journal file
that cannot be read or parsed makes the answer UNDETERMINED, and the caller must
then NOT run the turn. A done record that cannot be read only matters when an
unfinished journal row for THIS instruction exists: with no such row the answer is
CLEAR whatever the done folder holds.

ANSWERS (one line of JSON on stdout, and the exit code)
  0   CLEAR          no earlier attempt of this instruction is unfinished
  10  INTERRUPTED    an earlier attempt began its effect and recorded no result;
                     "operation_id" names it. Do not run the turn again.
  3   UNDETERMINED   a journal or done file could not be read or parsed;
                     "unreadable" lists the files. Do not run the turn.
  2   usage error

Usage:
  python3 rr_journal_check.py --journal DIR --done DIR --instruction-id ID
  python3 rr_journal_check.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

UNFINISHED = {"effect_started", "effect_executed"}


def load_rows(directory: str, prefix: str) -> tuple[list[tuple[str, dict]], list[str]]:
    rows: list[tuple[str, dict]] = []
    unreadable: list[str] = []
    try:
        names = sorted(os.listdir(directory))
    except FileNotFoundError:
        return rows, unreadable            # a folder that was never created holds nothing
    except OSError:
        return rows, [directory]
    for name in names:
        if name.startswith(".") or (prefix and not name.startswith(prefix)):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            unreadable.append(path)
            continue
        if isinstance(doc, dict):
            rows.append((name, doc))
        else:
            unreadable.append(path)
    return rows, unreadable


def decide(journal_dir: str, done_dir: str, instruction_id: str) -> dict:
    journal, bad_j = load_rows(journal_dir, "op_")
    # An unreadable JOURNAL is never "no earlier attempt": we cannot know.
    if bad_j:
        return {"verdict": "UNDETERMINED", "unreadable": bad_j}
    open_ops: list[str] = []
    for name, row in journal:
        if row.get("instruction_id") != instruction_id:
            continue
        if row.get("phase") not in UNFINISHED:
            continue
        open_ops.append(row.get("operation_id") if isinstance(row.get("operation_id"), str) else name)
    # No unfinished row for this instruction: the done folder cannot change the answer.
    if not open_ops:
        return {"verdict": "CLEAR", "journal_rows_read": len(journal)}
    done, bad_d = load_rows(done_dir, "")
    if bad_d:
        return {"verdict": "UNDETERMINED", "unreadable": bad_d}
    finished_ops = {d.get("operation_id") for _, d in done if isinstance(d.get("operation_id"), str)}
    for op in open_ops:
        if op in finished_ops:
            continue
        return {"verdict": "INTERRUPTED", "operation_id": op}
    return {"verdict": "CLEAR", "journal_rows_read": len(journal), "done_rows_read": len(done)}


def selftest() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as d:
        j, dn = os.path.join(d, "journal"), os.path.join(d, "done")
        os.makedirs(j)
        os.makedirs(dn)
        ok &= decide(j, dn, "i1")["verdict"] == "CLEAR"
        with open(os.path.join(j, "op_a"), "w") as fh:
            json.dump({"operation_id": "op_a", "phase": "effect_started", "instruction_id": "i1"}, fh)
        ok &= decide(j, dn, "i1")["verdict"] == "INTERRUPTED"
        ok &= decide(j, dn, "i2")["verdict"] == "CLEAR"            # a different instruction never matches
        ok &= decide(j, dn, "i")["verdict"] == "CLEAR"             # a shorter id is not a match
        with open(os.path.join(dn, "abc"), "w") as fh:
            json.dump({"operation_id": "op_a", "verdict": "delivered"}, fh)
        ok &= decide(j, dn, "i1")["verdict"] == "CLEAR"            # the result was recorded
        with open(os.path.join(j, "op_b"), "w") as fh:
            fh.write("{not json")
        ok &= decide(j, dn, "i1")["verdict"] == "UNDETERMINED"     # an unreadable row is never "clear"
        # Case 2: an unreadable JOURNAL is UNDETERMINED, and the answer's
        # "unreadable" list names the journal file's path.
        out = decide(j, dn, "i9")
        ok &= out["verdict"] == "UNDETERMINED" and os.path.join(j, "op_b") in out["unreadable"]
    # Case 1: an unreadable DONE record matters only when an unfinished journal
    # row for THIS instruction exists. With none, the answer is CLEAR.
    with tempfile.TemporaryDirectory() as d2:
        j2, dn2 = os.path.join(d2, "journal"), os.path.join(d2, "done")
        os.makedirs(j2)
        os.makedirs(dn2)
        with open(os.path.join(j2, "op_c"), "w") as fh:
            json.dump({"operation_id": "op_c", "phase": "effect_started", "instruction_id": "i1"}, fh)
        with open(os.path.join(dn2, "broken-done"), "w") as fh:
            fh.write("{not json")
        ok &= decide(j2, dn2, "i9")["verdict"] == "CLEAR"          # no row for i9 -> done is irrelevant
        ok &= decide(j2, dn2, "i1")["verdict"] == "UNDETERMINED"   # the row needs the done record
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal")
    ap.add_argument("--done")
    ap.add_argument("--instruction-id")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.journal and a.done and a.instruction_id):
        print("--journal, --done and --instruction-id are all required", file=sys.stderr)
        return 2
    out = decide(a.journal, a.done, a.instruction_id)
    print(json.dumps(out, sort_keys=True))
    return {"CLEAR": 0, "INTERRUPTED": 10}.get(out["verdict"], 3)


if __name__ == "__main__":
    sys.exit(main())
