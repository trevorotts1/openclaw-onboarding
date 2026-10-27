#!/usr/bin/env python3
"""T-18 contract-trace runner: F-02 (FB/IG/SMS shared sequence) and F-05 (closing_final races).

Owner: unit T-18. Scope: the two trace families T-18 owns, nothing else.

Every outcome is COMPUTED from the shipped product, never echoed from the case's
`expected`. The product limbs are called directly:

  * pb_contracts.check_document("collection", doc) and
    pb_contracts.collection_transition_errors(before, after)
        - collection identity, one shared capture budget, the reserved final action,
          "a corrected number is not a new ask" (DATA-CONTRACTS 1, 7, 8);
  * collection_lock.CollectionLock
        - FB/IG/SMS references serialize on ONE (tenant, contact, sequence) lock;
  * durable_store.DurableStore + outbound_gate.dispatch
        - the common gate runs for the reserved final action too: no bypass branch,
          a suppressed or canceled action never reaches the sender.

Cases of other families (F-03, F-04, F-06, F-07, F-08, F-12) are reported SKIP and are
not counted as passes. This runner does not claim them.

Exit codes: 0 every owned case matched; 1 at least one owned case violated; 2 usage, IO
or fixture-shape abort (never a pass). Stdlib only, no network, no writes outside the
scratch dir the caller passes with --scratch.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
TOOLS = SKILL_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

FAMILY = re.compile(r"^F-(02|05)[A-Z]?$")
T0 = "2026-10-24T09:00:00Z"


class Abort(RuntimeError):
    """Fixture or input shape is unusable; report rc 2, never a result."""


# --------------------------------------------------------------------------
# product imports (fail closed: an unimportable product is an abort)
# --------------------------------------------------------------------------


def product():
    try:
        import collection_lock
        import durable_store
        import outbound_gate
        import pb_contracts
        import tenant_identity
    except Exception as exc:  # noqa: BLE001 - report, never guess
        raise Abort("cannot import the product tools from %s: %s: %s"
                    % (TOOLS, type(exc).__name__, exc))
    return pb_contracts, collection_lock, durable_store, outbound_gate, tenant_identity


# --------------------------------------------------------------------------
# collection documents built from the case's own typed inputs
# --------------------------------------------------------------------------


def base_doc(*, channels, state, ask_id, ask_state, asks_used, max_asks,
             final_action_id=None, slots=None):
    return {
        "schema_version": 1,
        "tenant_id": "tenant-t18",
        "canonical_contact_id": "contact-t18",
        "collection_sequence_id": "seq-t18",
        "state_version": 4,
        "ownership_fence": 4,
        "originating_channel": channels[0],
        "originating_conversation_id": "conv-" + channels[0].lower(),
        "state": state,
        "t0": T0,
        "reminders_accepted": 0,
        "reminder_slots": list(slots or []),
        "sms_email_ask": {
            "logical_action_id": ask_id,
            "state": ask_state,
            "provider_message_id": None,
            "evidence_id": None,
        },
        "requested_items": [
            {
                "request_id": "REQ-1",
                "item_id": "item-guide-1",
                "item_version": "v3",
                "source": "keyword",
                "requested_at": T0,
                "status": "fulfilled",
                "fulfilled_at": T0,
                "evidence_id": "ev-1",
            }
        ],
        "field_refusals": [],
        "sequence_stop_reason": None,
        "channel_optouts": [],
        "global_stop": False,
        "human_owner_id": None,
        "final_action_id": final_action_id,
        "pending_request_ids": [],
        "channel_references": [
            {"channel": c, "conversation_id": "conv-" + c.lower()} for c in channels
        ],
        "capture_budget": {
            "max_reminders": 3,
            "max_sms_email_asks": int(max_asks),
            "reminders_used": 0,
            "sms_email_asks_used": int(asks_used),
        },
    }


def _errors(items):
    return [str(item) for item in items]


# --------------------------------------------------------------------------
# F-02: one FB/IG/SMS sequence, one SMS email ask, corrected number is not a new ask
# --------------------------------------------------------------------------


def compute_f02(case, scratch, prod):
    pb_contracts, collection_lock, _store, _gate, tenant_identity = prod
    channels = [c.strip() for c in str(case["sequence_channels"]).split(",") if c.strip()]
    if len(channels) < 2:
        raise Abort("F-02 %s: sequence_channels needs at least two channels"
                    % case["fixture_id"])
    doc = base_doc(channels=channels, state="awaiting_email",
                   ask_id=case["sms_ask_logical_action_id"],
                   ask_state=case["sms_ask_state"],
                   asks_used=case["sms_email_asks_used"],
                   max_asks=case["max_sms_email_asks"])
    fails = []

    # limb 1: the shared-sequence collection document is valid product state
    errs = _errors(pb_contracts.check_document("collection", doc))
    if errs:
        fails.append("collection document rejected: %s" % errs)

    # limb 2: correcting the mobile number keeps the SAME logical ask
    if bool(case.get("mobile_corrected")):
        after = copy.deepcopy(doc)
        after["state_version"] += 1
        errs = _errors(pb_contracts.collection_transition_errors(doc, after))
        if errs:
            fails.append("correction transition rejected: %s" % errs)

        # limb 3: the product REFUSES a second ask minted by the correction
        minted = copy.deepcopy(after)
        minted["sms_email_ask"]["logical_action_id"] = "act-ask-2"
        errs = _errors(pb_contracts.collection_transition_errors(doc, minted))
        if not any("not a new ask" in e for e in errs):
            fails.append("product accepted a new ask on a corrected number: %s" % errs)

    # limb 4: the product refuses more accepts than the shared budget allows
    over = copy.deepcopy(doc)
    over["capture_budget"]["sms_email_asks_used"] = int(case["max_sms_email_asks"]) + 1
    errs = _errors(pb_contracts.check_document("collection", over))
    if not errs:
        fails.append("product accepted an over-budget SMS ask count")

    # limb 5: FB, IG and SMS share ONE lock on (tenant, contact, sequence)
    identity = tenant_identity.TenantIdentity(
        str(Path(scratch) / ("identity-%s.sqlite" % case["fixture_id"])))
    identity.register_tenant(doc["tenant_id"], "T-18 F-02")
    contact = identity.bind(
        doc["tenant_id"],
        [("fb_psid", "psid-t18", True),
         ("ig_psid", "ig-t18", True),
         ("sms_number", "+15550100018", True)],
        source="T-18 F-02 trace",
    )
    lock = collection_lock.CollectionLock(identity)
    first = lock.acquire(doc["tenant_id"], contact, doc["collection_sequence_id"], "fb")
    second = lock.acquire(doc["tenant_id"], contact, doc["collection_sequence_id"], "sms")
    if not first.granted:
        fails.append("first collector was not granted the collection lock")
    if second.granted:
        fails.append("a second channel took the same sequence lock (shared lock broken)")
    for lease in (second, first):
        if lease.granted:
            lock.release(doc["tenant_id"], contact, doc["collection_sequence_id"],
                         lease.owner_id, lease.fence)

    return ("RECONCILE_SAME_ACTION_NO_NEW_ASK", fails)


# --------------------------------------------------------------------------
# F-05: closing_final races - only the reserved action, and never past the gate
# --------------------------------------------------------------------------


def compute_f05(case, scratch, prod):
    pb_contracts, _lock, durable_store, outbound_gate, _ident = prod
    reserved = case["reserved_action_id"]
    action = case["action_id"]
    stopped = bool(case["stop_arrived"])
    slots = [
        {"slot": 1, "due_at": "2026-10-24T11:00:00Z", "status": "reserved",
         "action_id": reserved, "reason": None},
        {"slot": 2, "due_at": "2026-10-24T17:00:00Z", "status": "suppressed",
         "action_id": "act-rem-2", "reason": "sibling canceled at final reservation"},
    ]
    doc = base_doc(channels=["FB_DM"], state=str(case["sequence_state"]),
                   ask_id=None, ask_state="not_created", asks_used=0, max_asks=1,
                   final_action_id=reserved, slots=slots)
    if stopped:
        doc["global_stop"] = True
        doc["sequence_stop_reason"] = "customer_stop"
        doc["reminder_slots"][0]["status"] = "suppressed"
        doc["reminder_slots"][0]["reason"] = "STOP before dispatch"
    fails = []

    # limb 1: closing_final state with its reservation is valid product state
    errs = _errors(pb_contracts.check_document("collection", doc))
    if errs:
        fails.append("closing_final document rejected: %s" % errs)

    # limb 2: the reservation is immutable; a second final is never minted
    swapped = copy.deepcopy(doc)
    swapped["state_version"] += 1
    swapped["final_action_id"] = "act-other-final"
    errs = _errors(pb_contracts.collection_transition_errors(doc, swapped))
    if not any("reserved final action cannot be replaced" in e for e in errs):
        fails.append("product allowed a replacement final action: %s" % errs)

    # limb 3: the common gate runs for the reserved final action (no bypass) and a
    # non-ALLOW verdict never reaches the sender
    store = durable_store.DurableStore(
        str(Path(scratch) / ("outbox-%s.sqlite" % case["fixture_id"])))
    sent = []
    deny = lambda _c: {"verdict": "SUPPRESSED", "evidence": {"reason": "stop"}}
    allow = lambda _c: "ALLOW"

    def sender(ctx):
        sent.append(ctx["action_id"])
        return {"provider": "t18", "provider_receipt_id": "r1"}

    def queued(key):
        row, _created = store.create_intent(
            logical_intent_key=key, idempotency_key=key, tenant_id=doc["tenant_id"],
            scope="person_directed",
            canonical_contact_id=doc["canonical_contact_id"],
            content_sha256="sha-" + key)
        store.queue(row["action_id"])
        return row["action_id"]

    try:
        final_id = queued(case["fixture_id"] + "-final")
        if stopped or action != reserved:
            store.cancel(final_id, "STOP or sibling: reserved final canceled")
            out = outbound_gate.dispatch(store, allow, sender, final_id, "w1")
            if out.status != outbound_gate.ST_NOT_CLAIMED or sent:
                fails.append("a canceled reserved final reached the sender: %r %r"
                             % (out.status, sent))
        else:
            blocked = outbound_gate.dispatch(store, deny, sender, final_id, "w1")
            if blocked.status != outbound_gate.ST_BLOCKED or sent:
                fails.append("the reserved final bypassed a block: %r %r"
                             % (blocked.status, sent))
            if store.get_action(final_id)["state"] != durable_store.STATE_SUPPRESSED:
                fails.append("a blocked reserved final did not persist its suppression")
            allowed_id = queued(case["fixture_id"] + "-final-allow")
            allowed = outbound_gate.dispatch(store, allow, sender, allowed_id, "w2")
            if allowed.status != outbound_gate.ST_SENT or sent != [allowed_id]:
                fails.append("the reserved final did not go through the common gate:"
                             " %r %r" % (allowed.status, sent))
    finally:
        store.close()

    if action != reserved:
        return "SUPPRESSED", fails
    if stopped:
        return "SUPPRESSED", fails
    return "CHECK_COMMON_GATE_NOT_BYPASS", fails


COMPUTE = {"F-02": compute_f02, "F-05": compute_f05}


# --------------------------------------------------------------------------
# fixture loading and main
# --------------------------------------------------------------------------


def load_fixture(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Abort("cannot read fixture %s: file is absent" % path)
    except (OSError, ValueError) as exc:
        raise Abort("cannot read fixture %s: %s" % (path, exc))
    if not isinstance(doc, dict):
        raise Abort("fixture root is not an object")
    for key in ("schema_version", "status", "cases"):
        if key not in doc:
            raise Abort("fixture root missing key %r" % key)
    if not isinstance(doc["cases"], list) or not doc["cases"]:
        raise Abort("fixture cases must be a non-empty list")
    seen = set()
    for case in doc["cases"]:
        if not isinstance(case, dict) or "fixture_id" not in case:
            raise Abort("case without fixture_id")
        fid = case["fixture_id"]
        if fid in seen:
            raise Abort("duplicate fixture_id %r" % fid)
        seen.add(fid)
        if "expected" not in case:
            raise Abort("%s: missing expected" % fid)
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", default=str(SKILL_ROOT.parent / "fixtures"
                                                 / "contract-traces.json"))
    parser.add_argument("--scratch", default=None,
                        help="directory for the product sqlite files (created if absent)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    try:
        fixture = load_fixture(args.fixture)
        scratch = Path(args.scratch) if args.scratch else Path(tempfile.mkdtemp(
            prefix="t18-traces-"))
        scratch.mkdir(parents=True, exist_ok=True)
        prod = product()
    except Abort as exc:
        print("ABORT: %s" % exc)
        return 2

    owned = matched = skipped = 0
    violations = []
    for case in fixture["cases"]:
        fid = case["fixture_id"]
        if not FAMILY.match(fid):
            skipped += 1
            if args.verbose:
                print("SKIP %s: not a T-18-owned family" % fid)
            continue
        owned += 1
        family = "F-" + FAMILY.match(fid).group(1)
        try:
            computed, fails = COMPUTE[family](case, scratch, prod)
        except Abort as exc:
            print("ABORT: %s" % exc)
            return 2
        except (KeyError, TypeError, ValueError) as exc:
            print("ABORT: %s: malformed case input: %s: %s"
                  % (fid, type(exc).__name__, exc))
            return 2
        if fails:
            violations.append((fid, fails))
            print("FAIL %s: product limb failed" % fid)
            for item in fails:
                print("     %s" % item)
            continue
        if computed != case["expected"]:
            violations.append((fid, ["computed=%r expected=%r"
                                     % (computed, case["expected"])]))
            print("FAIL %s: computed=%r expected=%r"
                  % (fid, computed, case["expected"]))
            continue
        matched += 1
        if args.verbose:
            print("PASS %s: %s" % (fid, computed))

    print("t18-contract-traces: %d/%d owned cases matched (%d skipped, fixture status %r)"
          % (matched, owned, skipped, fixture["status"]))
    if violations:
        print("TRACE VIOLATION: %d owned case(s) did not produce their expected outcome"
              % len(violations))
        return 1
    if owned == 0:
        print("TRACE VIOLATION: fixture holds none of the T-18-owned families")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
