#!/usr/bin/env python3
"""review_record.py - the one check for "this page was independently reviewed"
(ENF-10; schema signature-launch-review-record/v1).

A caller-typed reviewer string proves nothing (reviewer 'a' vs author 'b' is
two letters). A review record counts ONLY when:
  * it carries a recognised SUCCESSFUL verdict - a present-but-any verdict, or
    no verdict at all, is not an approval (S1/W11 admission boundary);
  * its reviewer session id is in the dispatch ledger (a session the harness
    recorded when it dispatched work - not a string the author typed);
  * that reviewer session differs from the author session;
  * it names a reviewer model (matching the ledger entry's model when the
    ledger carries one);
  * it echoes the request it reviewed (request_id), when the caller knows it;
  * it lists the sha256 of EVERY artifact reviewed: a review of nothing, or of
    only some of the artifacts, is not a review of the page;
  * under a policy that requires independence it declares independent review,
    and its reviewer model differs from the author model when the caller knows
    the author model;
  * with exact_artifact_set, it reviewed exactly this artifact set - not that
    set plus bytes that no longer exist.

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
VERDICTS = ("pass", "passed", "approved", "approve", "success", "succeeded",
            "verified")
_HEX64 = re.compile(r"^[a-f0-9]{64}$")


def verdict_of(record: Any) -> Optional[str]:
    """The recognised successful verdict, or None. A bare nonempty string is
    not a verdict: it has to be one of the recognised successes."""
    if not isinstance(record, dict):
        return None
    raw = record.get("verdict", record.get("decision"))
    if isinstance(raw, bool):
        return "pass" if raw else None
    if isinstance(raw, str) and raw.strip().lower() in VERDICTS:
        return raw.strip().lower()
    if record.get("passed") is True:
        return "pass"
    return None


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
                           request_id: Optional[str] = None,
                           author_model: Optional[str] = None,
                           require_independence: bool = False,
                           require_model_independence: bool = False,
                           exact_artifact_set: bool = False) -> List[str]:
    """Return the list of refusals; empty means the record is accepted."""
    if not isinstance(record, dict):
        return ["review record is absent or not an object"]
    fails: List[str] = []
    if record.get("schema") != SCHEMA:
        fails.append(f"review record schema is not {SCHEMA}")
    if verdict_of(record) is None:
        fails.append("review record carries no recognised successful verdict "
                     f"(need one of: {', '.join(VERDICTS)}); any verdict, or a "
                     "declared status, is not a pass")
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
    if require_independence or require_model_independence:
        independence = record.get("independent_review")
        claimed = independence is True or (
            isinstance(independence, str)
            and independence.strip().lower() in ("independent", "separate"))
        if not claimed:
            fails.append("the governing policy requires independent review and "
                         "the record does not declare it")
    if require_model_independence and isinstance(author_model, str) \
            and author_model.strip() and isinstance(model, str) and model.strip():
        if model.strip().lower() == author_model.strip().lower():
            fails.append("reviewer model == author model: a separate session on "
                         "the same model is not model independence")
    if exact_artifact_set:
        current = {sha for sha in shas if isinstance(sha, str)}
        extra = sorted(seen - current)
        if extra:
            fails.append("review record reviewed artifact(s) that are not the "
                         "current artifact set: "
                         + ", ".join(item[:12] + "..." for item in extra))
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
