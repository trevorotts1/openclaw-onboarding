#!/usr/bin/env python3
"""C-F03 / C-F12 contract-trace runner, computed from the shipped product.

Owner: unit PBB-1706. Scope: the two trace families in this unit's title,
F-03 (admission persisted before ack, crash-after-ack, unknown send) and
F-12 (revision-safe upgrade / rollback), nothing else.

Every outcome is COMPUTED by calling the shipped product, never echoed from the
case's own `expected`:

  * durable_store.DurableStore + reconciliation
        - an ACK is impossible without a durable action row (illegal transition);
        - a process death with an open attempt is swept to `unknown`, and an
          unknown action can never be claimed, so recovery cannot double-send;
        - resolving `applied` persists dispatch + ack receipts and acknowledges
          without claiming completion, on the SAME action identity;
        - resolving `not_applied` requeues the SAME action id for a fresh gate.
  * compat_guard.cas_update / forward_repair / ProtectedStateError
        - a writer holding a stale writer_generation is refused and writes no
          bytes, so a rollback can never overwrite a newer client fix;
        - a migration never drops or rewrites protected customer state.

Cases of other families (F-02, F-04, F-05, F-06, F-07, F-08) are reported SKIP
and are not counted as passes. t18_contract_traces_runner.py owns F-02 and F-05;
this runner does not claim them.

Exit codes: 0 every owned case matched; 1 at least one owned case violated; 2
usage, IO or fixture-shape abort (never a pass). Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
TOOLS = SKILL_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

FAMILY = re.compile(r"^F-(03|12)[A-Z]?$")

# Protected customer state that no rollback may touch (compat_guard owns the list;
# repeated here only to seed a realistic record and to assert on the outcome).
SEED_DATA = {
    "config_revision": "rev_a",
    "consent": {"dm": "granted", "sms": "granted"},
    "counters": {"reminders_sent": 2},
    "suppression": {"global": False},
}


class Abort(RuntimeError):
    """Fixture or input shape is unusable; report rc 2, never a result."""


def product():
    try:
        import compat_guard
        import durable_store
        import reconciliation
    except Exception as exc:  # noqa: BLE001 - report, never guess
        raise Abort("cannot import the product tools from %s: %s: %s"
                    % (TOOLS, type(exc).__name__, exc))
    return durable_store, reconciliation, compat_guard


def _need(case, *keys):
    missing = [k for k in keys if k not in case]
    if missing:
        raise Abort("%s: missing key(s) %s" % (case.get("fixture_id", "?"), missing))
    return [case[k] for k in keys]


# --------------------------------------------------------------------------
# F-03: durable admission before ack, crash after ack, unknown send
# --------------------------------------------------------------------------


def compute_f03(case, scratch, prod):
    durable_store, reconciliation, _compat = prod
    fid = case["fixture_id"]
    persisted, acked, crashed, send_result = _need(
        case, "durable_state_persisted_before_ack", "admission_acked",
        "crash_after_ack", "send_result")
    fails = []
    db = Path(scratch) / ("f03-%s.sqlite" % fid)
    store = durable_store.DurableStore(str(db))
    ack_receipt = {"provider": "ghl", "provider_receipt_id": "ack-%s" % fid}
    try:
        # limb 1: an ACK with no durable action row is refused by the product.
        # The case asks whether the product can ack before persisting; the only
        # way to find out is to ask it to.
        if acked and not persisted:
            try:
                store.record_ack("act-%s" % fid, ack_receipt, now=100.0)
            except durable_store.DurableStoreError:
                refused = True
            else:
                refused = False
            if not refused:
                fails.append("product acknowledged an action with no durable row")
            return ("ACK_BEFORE_DURABLE_STATE_REFUSED" if refused
                    else "ACK_WITHOUT_DURABLE_STATE"), fails

        row, created = store.create_intent(
            logical_intent_key="f03-%s" % fid, idempotency_key="f03-%s" % fid,
            tenant_id="tenant-f03", scope="person_directed",
            canonical_contact_id="contact-f03", content_sha256="sha-f03-%s" % fid)
        aid = row["action_id"]
        if not created:
            fails.append("first intent was not created")

        if send_result == "SENT":
            # A completed send is already durable: recovery must not re-send it.
            store.queue(aid, now=200.0)
            claim = store.claim_for_dispatch(aid, "w1", now=201.0, lease_seconds=10)
            if claim is None or not store.begin_attempt(aid, claim["fence"], "w1",
                                                        now=202.0):
                fails.append("could not open the send attempt")
            store.record_dispatch(aid, claim["fence"],
                                  {"provider": "ghl", "provider_receipt_id": "d-%s" % fid},
                                  now=203.0)
            store.record_ack(aid, ack_receipt, now=204.0)
            if reconciliation.needs_reconciliation(store, aid, now=300.0):
                fails.append("a sent+acked action was reported as needing reconciliation")
            if store.claim_for_dispatch(aid, "w2", now=301.0) is not None:
                fails.append("a sent action was re-claimable: a second send is possible")
            kinds = set(store.receipts(aid))
            if not {"dispatch", "ack"} <= kinds:
                fails.append("dispatch and ack receipts are not both persisted: %r" % kinds)
            return "NO_RESEND_ON_RECOVERY", fails

        if send_result in ("FAILED_NOT_SENT", "NOT_SENT"):
            # The provider does not have it: the SAME action goes back to queued
            # and the next dispatch needs a fresh gate.
            store.queue(aid, now=400.0)
            claim = store.claim_for_dispatch(aid, "w1", now=401.0, lease_seconds=1)
            if claim is None or not store.begin_attempt(aid, claim["fence"], "w1",
                                                        now=402.0):
                fails.append("could not open the send attempt")
            reconciliation.resolve_unknown(
                store, aid, lambda _ctx: "not_applied", now=500.0)
            after = store.get_action(aid)
            if after["state"] != durable_store.STATE_QUEUED:
                fails.append("not_applied did not requeue the action: %r" % after["state"])
            if after["action_id"] != aid:
                fails.append("not_applied minted a different action id")
            if store.claim_for_dispatch(aid, "w2", now=501.0) is None:
                fails.append("requeued action could not be claimed for a fresh gate")
            return "FRESH_GATE_RETRY_SAME_ACTION", fails

        if crashed and send_result == "UNKNOWN":
            # Crash between provider acceptance and receipt persistence: the
            # restart sweep must make the action truthfully unknown, and nothing
            # may re-claim it. Reconciliation then settles it from provider
            # history on the SAME identity, exactly once.
            store.queue(aid, now=600.0)
            claim = store.claim_for_dispatch(aid, "w1", now=601.0, lease_seconds=1)
            if claim is None or not store.begin_attempt(aid, claim["fence"], "w1",
                                                        now=602.0):
                fails.append("could not open the send attempt")
            swept = reconciliation.sweep_inflight(store, now=700.0)
            if aid not in swept:
                fails.append("the restart sweep did not promote the dead send: %r" % (swept,))
            if store.get_action(aid)["state"] != durable_store.STATE_UNKNOWN:
                fails.append("state after sweep is %r, not unknown"
                             % store.get_action(aid)["state"])
            if not reconciliation.needs_reconciliation(store, aid, now=701.0):
                fails.append("an unknown action was not reported as needing reconciliation")
            if store.claim_for_dispatch(aid, "w2", now=702.0) is not None:
                fails.append("an unknown action was re-claimable: recovery could double-send")
            out = reconciliation.resolve_unknown(
                store, aid,
                lambda ctx: {"outcome": "applied",
                             "receipt": {"provider": "ghl",
                                         "provider_receipt_id": "p-%s" % ctx[
                                             "idempotency_key"]}},
                now=703.0)
            if out.status != reconciliation.R_APPLIED:
                fails.append("provider-applied resolution returned %r" % out.status)
            if store.get_action(aid)["state"] != durable_store.STATE_ACKNOWLEDGED:
                fails.append("resolved action is %r, not acknowledged"
                             % store.get_action(aid)["state"])
            if store.get_action(aid)["state"] == durable_store.STATE_COMPLETED:
                fails.append("reconciliation claimed completion; it may only acknowledge")
            kinds = set(store.receipts(aid))
            if kinds != {"dispatch", "ack"}:
                fails.append("expected separate dispatch+ack receipts, got %r" % kinds)
            attempts = store.attempts(aid)
            if len(attempts) != 1:
                fails.append("expected exactly one send attempt, got %d" % len(attempts))
            if store.claim_for_dispatch(aid, "w3", now=704.0) is not None:
                fails.append("a resolved action was re-claimable: a second send is possible")
            return "RECONCILE_UNKNOWN_EFFECT_SINGLE_SEND", fails

        # No product limb settles this shape; hold, never guess.
        return "HOLD_FOR_OWNER", fails
    finally:
        store.close()


# --------------------------------------------------------------------------
# F-12: revision-safe upgrade / rollback (compare-and-swap generation)
# --------------------------------------------------------------------------


def _seed_record(path, compat_guard):
    data = dict(SEED_DATA)
    record = {"version": 1, "writer_generation": 0, "data": data}
    path.write_bytes(compat_guard.canonical_bytes(record))


def _bytes(path):
    return path.read_bytes()


def compute_f12(case, scratch, prod):
    _store, _recon, compat_guard = prod
    fid = case["fixture_id"]
    wrote, current = _need(case, "upgrade_wrote_config_revision",
                           "current_client_config_revision")
    rollback = bool(case.get("rollback_requested", False))
    fix_after = bool(case.get("client_fix_after_upgrade", False))
    fails = []

    path = Path(scratch) / ("f12-%s.json" % fid)
    _seed_record(path, compat_guard)
    seed_bytes = _bytes(path)

    # the upgrade: write the revision it actually wrote, at the generation it holds
    upgraded = compat_guard.cas_update(
        path, 0,
        lambda d: dict(d, config_revision=wrote),
        known_version=1)
    if upgraded["data"]["config_revision"] != wrote:
        fails.append("upgrade did not persist the revision it wrote")
    gen_after_upgrade = upgraded["writer_generation"]

    def client_fix(gen, revision):
        return compat_guard.cas_update(
            path, gen, lambda d: dict(d, config_revision=revision), known_version=1)

    if wrote != current:
        # A newer client fix landed on top. A rollback still holding the upgrade's
        # generation must be refused, and must not change a byte.
        fixed = client_fix(gen_after_upgrade, current)
        before = _bytes(path)
        refused = False
        try:
            client_fix(gen_after_upgrade, wrote)          # stale generation
        except compat_guard.StaleWriteError:
            refused = True
        except compat_guard.CompatError as exc:
            fails.append("expected a stale-write refusal, got %s" % type(exc).__name__)
            refused = True
        if not refused:
            fails.append("a stale writer overwrote a newer client fix")
        if _bytes(path) != before:
            fails.append("a refused stale write changed the record bytes")
        report = compat_guard.forward_repair(path, {}, known_version=1)
        if report.get("status") != "ok" or report.get("wrote"):
            fails.append("forward repair on a current record reported %r" % report.get("status"))
        if compat_guard.read_record(path)["data"]["config_revision"] != current:
            fails.append("forward repair changed the client fix")
        return "CAS_CONFLICT_FORWARD_REPAIR", fails

    if rollback and fix_after:
        fixed = client_fix(gen_after_upgrade, current)
        before = _bytes(path)
        refused = False
        try:
            client_fix(gen_after_upgrade, wrote)
        except compat_guard.StaleWriteError:
            refused = True
        except compat_guard.CompatError:
            refused = True
        if not refused:
            fails.append("rollback overwrote the client fix after upgrade")
        # a rollback that tries to drop protected state is refused on its own terms
        protected_refused = False
        try:
            compat_guard.cas_update(
                path, fixed["writer_generation"],
                lambda d: {k: v for k, v in d.items() if k != "consent"},
                known_version=1)
        except compat_guard.ProtectedStateError:
            protected_refused = True
        except compat_guard.CompatError as exc:
            fails.append("expected a protected-state refusal, got %s"
                         % type(exc).__name__)
            protected_refused = True
        if not protected_refused:
            fails.append("a rollback dropped protected customer state")
        if _bytes(path) != before:
            fails.append("a refused rollback changed the record bytes")
        return "ROLLBACK_REFUSED_NO_STALE_OVERWRITE", fails

    if rollback:
        after = client_fix(gen_after_upgrade, wrote)
        if after["data"]["config_revision"] != wrote:
            fails.append("rollback did not restore the prior revision")
        if after["writer_generation"] <= gen_after_upgrade:
            fails.append("rollback did not advance the writer generation")
        for key in ("consent", "counters", "suppression", "config_revision"):
            if key in SEED_DATA and after["data"].get(key) != SEED_DATA[key]:
                fails.append("a safe rollback changed %r" % key)
        if compat_guard.read_record(path)["version"] < 1:
            fails.append("rollback corrupted the record version")
        return "ROLLBACK_CAS_SAFE", fails

    after = client_fix(gen_after_upgrade, current)
    if after["data"]["config_revision"] != current:
        fails.append("compare-and-swap did not persist the current revision")
    for key in ("consent", "counters", "suppression"):
        if after["data"].get(key) != SEED_DATA[key]:
            fails.append("the upgrade changed protected state %r" % key)
    if _bytes(path) == seed_bytes:
        fails.append("the upgrade wrote no bytes; nothing was compared")
    return "CAS_OK", fails


COMPUTE = {"F-03": compute_f03, "F-12": compute_f12}


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
    parser.add_argument("--fixture", default=str(
        SKILL_ROOT.parent / "fixtures" / "contract-traces.json"))
    parser.add_argument("--scratch", default=None,
                        help="directory for the product sqlite/record files")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    try:
        fixture = load_fixture(args.fixture)
        scratch = Path(args.scratch) if args.scratch else Path(
            tempfile.mkdtemp(prefix="f03-f12-traces-"))
        scratch.mkdir(parents=True, exist_ok=True)
        prod = product()
    except Abort as exc:
        print("ABORT: %s" % exc)
        return 2

    owned = matched = skipped = 0
    violations = []
    for case in fixture["cases"]:
        fid = case["fixture_id"]
        m = FAMILY.match(fid)
        if not m:
            skipped += 1
            if args.verbose:
                print("SKIP %s: not an F-03 / F-12 family case" % fid)
            continue
        owned += 1
        try:
            computed, fails = COMPUTE["F-" + m.group(1)](case, scratch, prod)
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

    print("f03-f12-contract-traces: %d/%d owned cases matched (%d skipped,"
          " fixture status %r)"
          % (matched, owned, skipped, fixture["status"]))
    if violations:
        print("TRACE VIOLATION: %d owned case(s) did not produce their expected"
              " outcome" % len(violations))
        return 1
    if owned == 0:
        print("TRACE VIOLATION: fixture holds none of the F-03 / F-12 cases")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
