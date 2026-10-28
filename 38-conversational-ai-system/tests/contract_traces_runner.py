#!/usr/bin/env python3
"""Minimal focused trace runner for fixtures/contract-traces.json.

Executes every case in the fixture through the reference gate for its family and
compares the computed outcome with the case's own `expected`. It is a trace
runner, not a smoke test: a case whose inputs are corrupted so the rule no longer
produces `expected` FAILS with a non-zero exit and the case id in the message.

Scope note (deliberate): this runner executes the CONTRACT RULES, not the shipped
product handlers. Binding C-F03 / C-F12 to actual product code is a separate,
independently reviewed job. Nothing here marks an acceptance row PASS.

Usage
  python3 38-conversational-ai-system/tests/contract_traces_runner.py \
      [--fixture fixtures/contract-traces.json] [--verbose]

Exit codes
  0 = every case produced its expected outcome
  1 = at least one case violated its expected outcome
  2 = usage / IO / fixture-shape error (never a pass)

Stdlib only: the qc-static runner installs nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FAMILY_RE = re.compile(r"^F-(\d{2})[A-Z]?$")
REQUIRED_TOP = ("schema_version", "status", "cases")


def _need(case, *keys):
    missing = [k for k in keys if k not in case]
    if missing:
        raise ValueError(f"{case.get('fixture_id', '?')}: missing key(s) {missing}")
    return [case[k] for k in keys]


# --- F-03: admission / crash / unknown send ---------------------------------
def trace_f03(c):
    (persisted, acked, crashed, send_result) = _need(
        c,
        "durable_state_persisted_before_ack",
        "admission_acked",
        "crash_after_ack",
        "send_result",
    )
    if acked and not persisted:
        return "ACK_BEFORE_DURABLE_STATE_REFUSED"
    if send_result == "SENT":
        return "NO_RESEND_ON_RECOVERY"
    if crashed and send_result == "UNKNOWN":
        return "RECONCILE_UNKNOWN_EFFECT_SINGLE_SEND"
    if send_result in ("FAILED_NOT_SENT", "NOT_SENT"):
        return "FRESH_GATE_RETRY_SAME_ACTION"
    return "HOLD_FOR_OWNER"


# --- F-04: common dispatch gate variants ------------------------------------
def trace_f04(c):
    (changed_binding, global_stop, owner_current, channel_eligible) = _need(
        c, "changed_binding", "global_stop", "owner_current", "channel_eligible"
    )
    if global_stop:
        return "SUPPRESSED"
    if not owner_current:
        return "SUPPRESSED"
    if not channel_eligible:
        return "SUPPRESSED"
    if changed_binding:
        return "QUARANTINED"
    return "ALLOWED"


# --- F-05: closing_final final-action reservation ---------------------------
def trace_f05(c):
    (reserved, action_id, stop_arrived) = _need(
        c, "reserved_action_id", "action_id", "stop_arrived"
    )
    if stop_arrived:
        return "SUPPRESSED"
    if action_id != reserved:
        return "SUPPRESSED"
    return "CHECK_COMMON_GATE_NOT_BYPASS"


# --- F-06: one SMS ask receipt lifecycle ------------------------------------
def trace_f06(c):
    (sms_ask_state,) = _need(c, "sms_ask_state")
    if sms_ask_state == "unknown":
        return "RECONCILE_SAME_ACTION_NO_NEW_ASK"
    if sms_ask_state == "failed_not_sent":
        return "FRESH_GATE_SAME_ACTION"
    return "SEND_NEW_ASK"


# --- F-07: original gift independent of bonus readiness ---------------------
def trace_f07(c):
    (original_valid, bonus_capability) = _need(c, "original_resource_valid", "bonus_capability")
    if original_valid and bonus_capability != "VERIFIED":
        return "ORIGINAL_INDEPENDENT_BONUS_NOT_READY"
    if original_valid and bonus_capability == "VERIFIED":
        return "ORIGINAL_AND_BONUS_READY"
    return "ORIGINAL_NOT_READY"


# --- F-08: comment-only, no drip to an ignored opener -----------------------
def trace_f08(c):
    (comment_only, customer_reply) = _need(c, "comment_only", "customer_reply")
    if comment_only and not customer_reply:
        return "OPENER_ONLY_NO_DRIP"
    if comment_only and customer_reply:
        return "DRIP_ALLOWED"
    return "NOT_COMMENT_ONLY"


# --- F-12: revision-safe upgrade / rollback (compare-and-swap) --------------
def trace_f12(c):
    # The two revision keys are mandatory for every F-12 case. The rollback keys
    # are optional so the pre-existing F-12A case (conflict only, no rollback
    # intent recorded) keeps its exact shape and is never rewritten by a runner.
    (wrote, current) = _need(c, "upgrade_wrote_config_revision", "current_client_config_revision")
    rollback = c.get("rollback_requested", False)
    fix_after = c.get("client_fix_after_upgrade", False)
    if wrote != current:
        return "CAS_CONFLICT_FORWARD_REPAIR"
    if rollback and fix_after:
        return "ROLLBACK_REFUSED_NO_STALE_OVERWRITE"
    if rollback:
        return "ROLLBACK_CAS_SAFE"
    return "CAS_OK"


TRACES = {
    "03": trace_f03,
    "04": trace_f04,
    "05": trace_f05,
    "06": trace_f06,
    "07": trace_f07,
    "08": trace_f08,
    "12": trace_f12,
}


def family_of(fixture_id):
    m = FAMILY_RE.match(fixture_id or "")
    if not m:
        return None
    return m.group(1)


def load_fixture(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("fixture root must be an object")
    for k in REQUIRED_TOP:
        if k not in data:
            raise ValueError(f"fixture root missing key {k!r}")
    cases = data["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("fixture 'cases' must be a non-empty list")
    return data


def run(fixture_path, verbose=False):
    data = load_fixture(fixture_path)
    # Other units own other families in this same fixture on main (T-18 owns F-02 and
    # F-05 and reports the rest SKIP). Scope this runner to the families it defines so
    # a shared fixture never makes it report a false violation, and never let an
    # empty scope look like a pass.
    owned = [c for c in data["cases"] if TRACES.get(family_of(c.get("fixture_id"))) is not None]
    unowned = [c for c in data["cases"] if TRACES.get(family_of(c.get("fixture_id"))) is None]
    for c in unowned:
        if verbose:
            print(f"SKIP {c.get('fixture_id')}: family owned by another runner")
    if not owned:
        print("TRACE VIOLATION: no case belongs to a family this runner owns")
        return 1
    data = dict(data, cases=owned)
    seen = set()
    failures = []
    skipped = []
    passed = 0

    for case in data["cases"]:
        fid = case.get("fixture_id")
        if not fid:
            failures.append(("?", "case has no fixture_id", None, None))
            continue
        if fid in seen:
            failures.append((fid, "duplicate fixture_id", None, None))
            continue
        seen.add(fid)

        fam = family_of(fid)
        trace = TRACES.get(fam)
        if trace is None:
            failures.append((fid, f"no trace for family {fam!r}", None, case.get("expected")))
            continue
        if "expected" not in case:
            failures.append((fid, "case has no expected", None, None))
            continue

        try:
            got = trace(case)
        except ValueError as exc:
            failures.append((fid, str(exc), None, case.get("expected")))
            continue

        if got != case["expected"]:
            failures.append((fid, "trace outcome != expected", got, case["expected"]))
        else:
            passed += 1
            if verbose:
                print(f"PASS {fid}: {got}")

    total = len(data["cases"])
    print(f"contract-traces: {passed}/{total} cases matched expected")
    for fid, fam in skipped:
        print(f"SKIP {fid}: no trace in this runner for family {fam!r} — NOT a pass")
    for fid, why, got, exp in failures:
        print(f"FAIL {fid}: {why}")
        if got is not None or exp is not None:
            print(f"     computed={got!r} expected={exp!r}")
    if failures:
        print(f"TRACE VIOLATION: {len(failures)} case(s) did not produce their expected outcome")
        return 1
    if passed == 0:
        print(f"TRACE ABORT: no case was executed ({len(skipped)} skipped) — this is never a pass")
        return 2
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run fixtures/contract-traces.json cases.")
    ap.add_argument(
        "--fixture",
        default="fixtures/contract-traces.json",
        help="path to the contract traces fixture (default: fixtures/contract-traces.json)",
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    try:
        return run(args.fixture, verbose=args.verbose)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ABORT: cannot read fixture {args.fixture}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
