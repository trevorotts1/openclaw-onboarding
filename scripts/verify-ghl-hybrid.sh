#!/usr/bin/env bash
# ============================================================
# verify-ghl-hybrid.sh — end-to-end verifier, GHL Hybrid public adapter
# ============================================================
#
# WHAT IT PROVES (five assertions, each one discriminating):
#   A1  the public adapter imports against the REAL OPERATIONS registry and
#       carries one real read through a declared fake transport, with the
#       Version taken from the registry row (never from the caller).
#   A2  one real WRITE runs, and it is only "ok" because its read-back
#       verified — not because the POST returned 2xx.
#   A3  a failed write yields unknown_outcome and is reconcile-only: a retry
#       with the same idempotency key is refused, a fresh key over the same
#       canonical intent is refused, and reconcile() is the only forward path.
#   A4  capability denial is explicit and pre-transport, for both a read and a
#       write that has enablement but no canary evidence.
#   A5  any failed assertion exits non-zero AND names the assertion plus a
#       reason (proved by running this verifier again as a child process).
#
# DISCRIMINATION
#   --discriminate ID   breaks exactly that assertion's property and REQUIRES
#                       the verifier to report that assertion (and only that
#                       one) as failed.  Exit 0 means the check bites; exit 5
#                       means the check is inert.
#   --break ID          runs with ID's property deliberately broken (used by
#                       A5 and by --discriminate).
#
# Everything here is offline.  The only transport is the repo's own
# tests/_public_contract_fakes.FakeTransport; no socket is opened, no
# credential is read, and the synthetic tenant/token in those fakes are the
# only identifiers involved.
#
# Exit codes: 0 pass, 2 usage/environment failure, 3 assertion failure,
#             5 discrimination failure.
# ============================================================

set -uo pipefail   # NOT -e: failures are data we report, not aborts.

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE="$REPO_ROOT/44-convert-and-flow-operator/tools/engine"

usage() {
  cat >&2 <<'EOF'
usage: verify-ghl-hybrid.sh [--break A1|A2|A3|A4|A5] [--discriminate ID]
EOF
}

MODE="run"; BREAK="none"; DISC=""; WFIN021_BREAK_EXIT=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --break)        [ "$#" -ge 2 ] || { usage; exit 2; }; BREAK="$2"; shift 2 ;;
    --discriminate) [ "$#" -ge 2 ] || { usage; exit 2; }; MODE="disc"; DISC="$2"; shift 2 ;;
    --child)        shift ;;                       # A5 child run marker
    --break-exit)   WFIN021_BREAK_EXIT=1; shift ;; # A5's deliberate defect
    -h|--help)      usage; exit 0 ;;
    *) echo "FAIL harness: unknown argument '$1'" >&2; usage; exit 2 ;;
  esac
done

case "$BREAK" in A1|A2|A3|A4|A5|none) ;; *)
  echo "FAIL harness: unknown --break id '$BREAK' (expected A1..A5 or none)" >&2; exit 2 ;; esac
if [ "$MODE" = "disc" ]; then
  case "$DISC" in A1|A2|A3|A4|A5) ;; *)
    echo "FAIL harness: unknown --discriminate id '$DISC' (expected A1..A5)" >&2; exit 2 ;; esac
  # discriminating assertion ID means breaking ID's property and requiring ID
  # (and only ID) to be reported as failed.
  BREAK="$DISC"
fi

# ── environment, each failure named ─────────────────────────────────────────
if [ ! -d "$ENGINE" ]; then
  echo "FAIL harness: engine tree missing at $ENGINE" >&2; exit 2
fi
if [ ! -f "$ENGINE/tests/_public_contract_fakes.py" ]; then
  echo "FAIL harness: shared fake transport missing: $ENGINE/tests/_public_contract_fakes.py" >&2; exit 2
fi
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "FAIL harness: python3 not found on PATH (set PYTHON_BIN)" >&2; exit 2
fi
if [ ! -f "$SCRIPT_PATH" ]; then
  echo "FAIL harness: cannot resolve own path for the A5 child run" >&2; exit 2
fi

export WFIN021_BREAK_EXIT
exec "$PYTHON_BIN" -I - "$ENGINE" "$BREAK" "$SCRIPT_PATH" "$MODE" "$DISC" <<'PY'
"""verify-ghl-hybrid.sh body — offline, five discriminating assertions."""

import json
import os
import re
import subprocess
import sys
import traceback

ENGINE, BREAK, SCRIPT, MODE, DISC = sys.argv[1:6]
IS_CHILD = os.environ.get("WFIN021_CHILD") == "1"

sys.path.insert(0, ENGINE)
sys.path.insert(0, os.path.join(ENGINE, "tests"))

EXIT_USAGE, EXIT_ASSERT, EXIT_DISC = 2, 3, 5

try:
    import _public_contract_fakes as fakes
    from cli_anything.gohighlevel.public.operations import OPERATIONS
    from cli_anything.gohighlevel.public.result import Status
    from cli_anything.gohighlevel.public.readback import ReadbackSpec, ReadbackStatus
    from cli_anything.gohighlevel.public.capability import Capability, CapabilityGate
    from cli_anything.gohighlevel.public.errors import ReconciliationRequired
except Exception as exc:  # noqa: BLE001 — an import failure IS the finding
    print("FAIL harness: adapter import failed: %s: %s" % (type(exc).__name__, exc))
    traceback.print_exc()
    sys.exit(EXIT_USAGE)

TENANT = fakes.SYNTHETIC_TENANT
SECRET = fakes.SYNTHETIC_TOKEN
JSON = b'{"ok":true}'

# ── result collection ───────────────────────────────────────────────────────
RESULTS = []  # [(assertion_id, ok, reason)]


def check(failures, label, condition, reason):
    """Append a reason on a false condition; never raises."""
    if not condition:
        failures.append("%s (%s)" % (reason, label))
    return bool(condition)


def run_assertion(assertion_id, fn):
    try:
        failures = fn()
    except Exception as exc:  # noqa: BLE001 — a raised assertion is a failure
        RESULTS.append((assertion_id, False, "%s: %s" % (type(exc).__name__, exc)))
        return
    if failures:
        RESULTS.append((assertion_id, False, "; ".join(failures)))
    else:
        RESULTS.append((assertion_id, True, ""))


def readback_expect(values):
    return {"customValues": values}


# ── A1: real read through the real registry ─────────────────────────────────
def a1_real_read():
    failures = []
    check(failures, "registry", bool(OPERATIONS),
          "OPERATIONS registry imported empty")
    check(failures, "registry-size", len(OPERATIONS) > 0,
          "OPERATIONS registry has zero rows")
    if failures:
        return failures

    op = "locations.get"
    if op not in OPERATIONS:
        return ["registry row missing: %s" % op]
    row = OPERATIONS[op]

    body = json.dumps({"location": {"id": TENANT, "name": "WF21 fixture"}}).encode()
    status, wire = 200, body
    if BREAK == "A1":
        status, wire = 500, b'{"error":"fixture-500"}'

    transport = fakes.FakeTransport([fakes.resp(status, wire, {"content-type": "application/json"})])
    adapter = fakes.make_adapter(
        transport, OPERATIONS, gate=fakes.enabled_gate([row]))
    result = adapter.call(operation_id=op, tenant=fakes.fake_tenant(TENANT),
                          path_params={"locationId": TENANT})

    check(failures, "registry-identity", adapter._operations is OPERATIONS,
          "adapter is not bound to the real OPERATIONS registry")
    check(failures, "status", result.status is Status.ok,
          "read status was %s, expected ok" % result.status.value)
    check(failures, "http", result.http_status == 200,
          "read http_status was %r, expected 200" % (result.http_status,))
    check(failures, "version-from-row", result.version_header == row.version,
          "version_header %r != registry row version %r"
          % (result.version_header, row.version))
    check(failures, "one-call", transport.call_count == 1,
          "transport saw %d calls, expected 1" % transport.call_count)
    if transport.requests:
        wire_call = transport.requests[0]
        check(failures, "method", wire_call["method"] == row.method,
              "wire method %r != row method %r" % (wire_call["method"], row.method))
        check(failures, "wire-version", wire_call["version"] == row.version,
              "wire Version %r != row version %r"
              % (wire_call["version"], row.version))
        check(failures, "wire-tenant", TENANT in str(wire_call["url"]),
              "tenant not present in the resolved path %r" % wire_call["url"])
    envelope = json.dumps(result.evidence, default=str)
    check(failures, "no-secret-in-envelope", SECRET not in envelope,
          "the synthetic credential value leaked into the result envelope")
    return failures


# ── A2: real write, ok only because the read-back verified ─────────────────
def a2_real_write():
    failures = []
    write_op, read_op = "custom_values.create", "custom_values.list"
    for op in (write_op, read_op):
        if op not in OPERATIONS:
            return ["registry row missing: %s" % op]

    created = json.dumps({"customValue": {"name": "wf21-probe"}}).encode()
    verified = json.dumps(readback_expect([{"name": "wf21-probe", "value": "1"}])).encode()
    if BREAK == "A2":
        # the POST succeeds, the read-back contradicts it: the write must not
        # be called ok on the strength of a 2xx alone.
        verified = json.dumps(readback_expect([{"name": "someone-else"}])).encode()

    transport = fakes.FakeTransport([
        fakes.resp(201, created, {"content-type": "application/json"}),
        fakes.resp(200, verified, {"content-type": "application/json"}),
    ])
    gate = fakes.enabled_gate([OPERATIONS[write_op]])
    adapter = fakes.make_adapter(transport, OPERATIONS, gate=gate)
    spec = ReadbackSpec(operation_id=read_op,
                        target_params={"locationId": TENANT},
                        expect=readback_expect([{"name": "wf21-probe", "value": "1"}]))
    result = adapter.call(
        operation_id=write_op, tenant=fakes.fake_tenant(TENANT),
        path_params={"locationId": TENANT},
        body={"name": "wf21-probe", "value": "1"},
        idempotency_key=fakes.issue_key(write_op), readback=spec)

    check(failures, "status", result.status is Status.ok,
          "write status was %s, expected ok" % result.status.value)
    check(failures, "readback-verified",
          result.readback is not None and result.readback.result is ReadbackStatus.verified,
          "read-back was %r, expected verified"
          % (None if result.readback is None else result.readback.result.value))
    check(failures, "two-calls", transport.call_count == 2,
          "transport saw %d calls, expected write+read-back = 2" % transport.call_count)
    if transport.call_count == 2:
        check(failures, "write-method", transport.requests[0]["method"] == OPERATIONS[write_op].method,
              "write method %r != row %r"
              % (transport.requests[0]["method"], OPERATIONS[write_op].method))
        check(failures, "readback-method", transport.requests[1]["method"] == "GET",
              "read-back method %r != GET" % transport.requests[1]["method"])
        check(failures, "readback-version",
              transport.requests[1]["version"] == OPERATIONS[read_op].version,
              "read-back Version %r != row version %r"
              % (transport.requests[1]["version"], OPERATIONS[read_op].version))
    check(failures, "evidence-readback", result.evidence.get("readback") == "verified",
          "evidence readback was %r, expected 'verified'" % (result.evidence.get("readback"),))
    return failures


# ── A3: failed write -> unknown_outcome, and reconcile-only ────────────────
def a3_unknown_outcome_is_reconcile_only():
    failures = []
    write_op, read_op = "custom_fields.create", "custom_fields.list"
    for op in (write_op, read_op):
        if op not in OPERATIONS:
            return ["registry row missing: %s" % op]

    expect = {"customFields": [{"name": "wf21-probe"}]}
    verified = json.dumps(expect).encode()
    timeout = fakes.resp(None, b"", error_kind="timeout")
    ok_write = fakes.resp(200, json.dumps({"customField": {"name": "wf21-probe"}}).encode())
    if BREAK == "A3":
        timeout = ok_write  # the write appears to succeed: nothing to reconcile

    transport = fakes.FakeTransport([timeout, fakes.resp(200, verified)])
    gate = fakes.enabled_gate([OPERATIONS[write_op]])
    adapter = fakes.make_adapter(transport, OPERATIONS, gate=gate)
    spec = ReadbackSpec(operation_id=read_op,
                        target_params={"locationId": TENANT}, expect=expect)
    tenant = fakes.fake_tenant(TENANT)
    body = {"name": "wf21-probe", "dataType": "TEXT"}
    key = fakes.issue_key(write_op)

    def attempt(use_key, use_body):
        return adapter.call(operation_id=write_op, tenant=tenant,
                            path_params={"locationId": TENANT}, body=use_body,
                            idempotency_key=use_key, readback=spec)

    first = attempt(key, body)
    if not check(failures, "unknown-outcome", first.status is Status.unknown_outcome,
                 "failed write reported %s, expected unknown_outcome"
                 % first.status.value):
        return failures
    check(failures, "transport-rule", (first.error or {}).get("rule") == "transport_timeout",
          "error rule was %r, expected transport_timeout" % ((first.error or {}).get("rule"),))
    check(failures, "readback-not-performed",
          first.readback is not None
          and first.readback.detail.get("reason") == "not_performed",
          "read-back detail reason was %r, expected not_performed"
          % (None if first.readback is None else first.readback.detail.get("reason"),))

    # reconcile-only, way 1: the same idempotency key must be refused.
    try:
        attempt(key, body)
        failures.append("retry on the same idempotency key was allowed (expected ReconciliationRequired)")
    except ReconciliationRequired as exc:
        check(failures, "same-key-detail", exc.detail.get("receipt_id") == first.receipt_id,
              "ReconciliationRequired named receipt %r, expected %r"
              % (exc.detail.get("receipt_id"), first.receipt_id))
    except Exception as exc:  # noqa: BLE001
        failures.append("same-key retry raised %s, expected ReconciliationRequired"
                        % type(exc).__name__)

    # reconcile-only, way 2: a fresh key over the same canonical intent.
    second = attempt(fakes.issue_key(write_op), body)
    check(failures, "fresh-key-denied", second.status is Status.denied,
          "fresh-key retry reported %s, expected denied" % second.status.value)
    check(failures, "unreconciled-rule",
          (second.error or {}).get("rule") == "unreconciled_intent_exists",
          "fresh-key rule was %r, expected unreconciled_intent_exists"
          % ((second.error or {}).get("rule"),))
    check(failures, "unreconciled-receipt",
          (second.error or {}).get("receipt_id") == first.receipt_id,
          "fresh-key denial did not name the prior receipt %r"
          % (first.receipt_id,))

    # the one forward path.
    reconciled = adapter.reconcile(first)
    check(failures, "reconcile-status", reconciled.status is Status.ok,
          "reconcile reported %s, expected ok" % reconciled.status.value)
    check(failures, "reconcile-flag", reconciled.evidence.get("reconcile") is True,
          "reconcile receipt does not carry reconcile=True")
    check(failures, "reconcile-from",
          reconciled.evidence.get("reconciled_from") == first.receipt_id,
          "reconcile receipt names %r, expected %r"
          % (reconciled.evidence.get("reconciled_from"), first.receipt_id))
    return failures


# ── A4: capability denial is explicit and pre-transport ────────────────────
def a4_denial_is_explicit():
    failures = []

    read_op = "custom_values.list"
    if read_op not in OPERATIONS:
        return ["registry row missing: %s" % read_op]

    transport = fakes.FakeTransport()
    if BREAK == "A4":
        gate = fakes.enabled_gate([OPERATIONS[read_op]])
    else:
        gate = CapabilityGate(tenant=TENANT)  # default-deny
    adapter = fakes.make_adapter(transport, OPERATIONS, gate=gate)
    denied = adapter.call(operation_id=read_op, tenant=fakes.fake_tenant(TENANT),
                          path_params={"locationId": TENANT})

    check(failures, "read-denied", denied.status is Status.denied,
          "ungranted read reported %s, expected denied" % denied.status.value)
    err = denied.error or {}
    check(failures, "rule", err.get("rule") == "capability_disabled",
          "denial rule was %r, expected capability_disabled" % (err.get("rule"),))
    for field in ("reason", "owner", "unblock"):
        value = err.get(field)
        check(failures, "explicit-%s" % field,
              isinstance(value, str) and value.strip() != "",
              "denial does not explain '%s' (silence is not an outcome)" % field)
    check(failures, "pre-transport",
          denied.evidence.get("refused_before_transport") is True,
          "denial is not marked refused_before_transport")
    check(failures, "no-wire", transport.call_count == 0,
          "a denied read still reached the transport (%d calls)" % transport.call_count)

    # a write with enablement but no canary evidence must be refused the same
    # explicit way, before transport.
    write_op = "custom_fields.create"
    if write_op not in OPERATIONS:
        failures.append("registry row missing: %s" % write_op)
        return failures
    weak = Capability(operation_id=write_op, contract_verified=True,
                      adapter_built=True, offline_tests_passed=True,
                      read_verified=True, canary_verified=False, enabled=True)
    gate2 = CapabilityGate(tenant=TENANT)
    gate2.put(weak)
    transport2 = fakes.FakeTransport()
    adapter2 = fakes.make_adapter(transport2, OPERATIONS, gate=gate2)
    spec = ReadbackSpec(operation_id="custom_fields.list",
                        target_params={"locationId": TENANT},
                        expect={"customFields": [{"name": "wf21-probe"}]})
    no_canary = adapter2.call(
        operation_id=write_op, tenant=fakes.fake_tenant(TENANT),
        path_params={"locationId": TENANT},
        body={"name": "wf21-probe", "dataType": "TEXT"},
        idempotency_key=fakes.issue_key(write_op), readback=spec)
    check(failures, "write-without-canary-denied", no_canary.status is Status.denied,
          "write without canary evidence reported %s, expected denied"
          % no_canary.status.value)
    check(failures, "write-denial-rule",
          (no_canary.error or {}).get("rule") == "capability_disabled",
          "write denial rule was %r, expected capability_disabled"
          % ((no_canary.error or {}).get("rule"),))
    check(failures, "write-pre-transport", transport2.call_count == 0,
          "a capability-denied write still reached the transport")
    return failures


# ── A5: failures exit non-zero and name the assertion ──────────────────────
def a5_failure_is_loud():
    if IS_CHILD:
        return []  # the child's own assertions are what it reports

    failures = []
    cmd = ["/bin/bash", SCRIPT, "--break", "A1", "--child"]
    if BREAK == "A5":
        cmd.append("--break-exit")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                          env=dict(os.environ, WFIN021_CHILD="1"))
    lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
    named = next((ln for ln in lines if ln.startswith("FAIL")), None)
    check(failures, "child-exit", proc.returncode != 0,
          "a failing child run exited 0 instead of non-zero%s"
          % ("" if named is None else " (child said: %s)" % named[:120]))
    check(failures, "child-names-assertion", "FAIL A1" in proc.stdout,
          "the failing child did not name the assertion in its output")
    check(failures, "child-names-reason",
          re.search(r"^FAIL A1: \S.*$", proc.stdout, re.MULTILINE) is not None,
          "the failing child printed no reason after 'FAIL A1: '")
    return failures


ASSERTIONS = [
    ("A1", a1_real_read),
    ("A2", a2_real_write),
    ("A3", a3_unknown_outcome_is_reconcile_only),
    ("A4", a4_denial_is_explicit),
    ("A5", a5_failure_is_loud),
]

for assertion_id, fn in ASSERTIONS:
    run_assertion(assertion_id, fn)

for assertion_id, ok, reason in RESULTS:
    if ok:
        print("PASS %s" % assertion_id)
    else:
        print("FAIL %s: %s" % (assertion_id, reason))

failed = [aid for aid, ok, _ in RESULTS if not ok]

if MODE == "disc":
    # exactly the deliberately broken assertion must fail, and only it.
    if failed == [DISC]:
        reason = next(r for aid, ok, r in RESULTS if aid == DISC)
        print("DISCRIMINATED %s: %s" % (DISC, reason))
        sys.exit(0)
    print("NOT-DISCRIMINATED %s: mutated run failed %s, expected exactly [%s]"
          % (DISC, failed or "nothing", DISC))
    sys.exit(EXIT_DISC)

if failed:
    if os.environ.get("WFIN021_BREAK_EXIT") == "1":
        sys.exit(0)  # A5's deliberate break: swallow the failure
    print("FAIL harness: %d assertion(s) failed: %s" % (len(failed), ",".join(failed)))
    sys.exit(EXIT_ASSERT)

print("OK: %d/%d assertions passed" % (len(RESULTS), len(ASSERTIONS)))
sys.exit(0)
PY
