#!/usr/bin/env python3
"""review_record.py - the one check for "this page was independently reviewed"
(ENF-10; schema signature-launch-review-record/v1).

A caller-typed reviewer string proves nothing (reviewer 'a' vs author 'b' is
two letters). A review record counts ONLY when:
  * its reviewer session id is in the dispatch ledger (a session the harness
    recorded when it dispatched work - not a string the author typed);
  * that reviewer session differs from the author session;
  * it names a reviewer model (matching the ledger entry's model when the
    ledger carries one);
  * it echoes the request it reviewed (request_id), when the caller knows it;
  * it lists the sha256 of EVERY artifact reviewed: a review of nothing, or of
    only some of the artifacts, is not a review of the page.

Dispatch ledger shape: a JSON list of session ids, or
{"sessions": [<id> | {"session_id": ..., "model": ...}, ...]}.

Deterministic, stdlib only. Exit 0 ok, 2 refused, 3 usage.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = "signature-launch-review-record/v1"
_HEX64 = re.compile(r"^[a-f0-9]{64}$")


def ledger_sessions(ledger: Any) -> Dict[str, Dict[str, Any]]:
    """Normalise a dispatch ledger to {session_id: entry}. Anything that is
    not a list or a {"sessions": [...]} object is an empty ledger (fail closed)."""
    items = ledger.get("sessions") if isinstance(ledger, dict) else ledger
    out: Dict[str, Dict[str, Any]] = {}
    for it in items if isinstance(items, list) else []:
        if isinstance(it, str) and it.strip():
            out[it] = {}
        elif isinstance(it, dict) and isinstance(it.get("session_id"), str) \
                and it["session_id"].strip():
            out[it["session_id"]] = it
    return out


def validate_review_record(record: Any, *, ledger: Any, author_session: Any,
                           artifacts: Iterable[Dict[str, Any]],
                           request_id: Optional[str] = None) -> List[str]:
    """Return the list of refusals; empty means the record is accepted."""
    if not isinstance(record, dict):
        return ["review record is absent or not an object"]
    fails: List[str] = []
    if record.get("schema") != SCHEMA:
        fails.append(f"review record schema is not {SCHEMA}")
    sessions = ledger_sessions(ledger)
    reviewer = record.get("reviewer_session")
    if not isinstance(reviewer, str) or not reviewer.strip():
        fails.append("review record names no reviewer_session")
    elif reviewer not in sessions:
        fails.append(f"reviewer session {reviewer!r} is not in the dispatch "
                     "ledger (a typed reviewer string is not an execution "
                     "the harness recorded)")
    elif reviewer == author_session:
        fails.append("reviewer session == author session (an artifact's "
                     "reviewer is never its author)")
    model = record.get("reviewer_model")
    if not isinstance(model, str) or not model.strip():
        fails.append("review record names no reviewer_model")
    elif isinstance(reviewer, str) and sessions.get(reviewer, {}).get("model") \
            not in (None, model):
        fails.append("reviewer_model disagrees with the dispatch ledger's "
                     f"recorded model for session {reviewer!r}")
    if request_id is not None and record.get("request_id") != request_id:
        fails.append("review record does not echo the request it reviewed "
                     f"({record.get('request_id')!r} != {request_id!r})")
    reviewed = record.get("reviewed_artifacts")
    seen = set()
    for a in reviewed if isinstance(reviewed, list) else []:
        sha = a.get("sha256") if isinstance(a, dict) else None
        if isinstance(sha, str) and _HEX64.match(sha):
            seen.add(sha)
        else:
            fails.append("a reviewed_artifacts entry lacks a 64-hex sha256")
    if not seen:
        fails.append("review record lists no reviewed artifact sha256")
    shas = [a.get("sha256") if isinstance(a, dict) else None for a in artifacts]
    if not shas:
        fails.append("the result has no artifacts: nothing was reviewed")
    for sha in shas:
        if sha not in seen:
            fails.append(f"artifact sha256 {str(sha)[:12]}... was not listed "
                         "as reviewed")
    return fails


def main(argv: List[str]) -> int:
    if len(argv) != 4:
        print("usage: review_record.py <record.json> <ledger.json> "
              "<result.json>")
        return 3
    rec, led, res = (json.load(open(p, encoding="utf-8")) for p in argv[1:])
    fails = validate_review_record(
        rec, ledger=led, author_session=res.get("author_session"),
        artifacts=res.get("artifacts") or [], request_id=res.get("request_id"))
    print("\n".join(fails) or "review record accepted")
    return 2 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
