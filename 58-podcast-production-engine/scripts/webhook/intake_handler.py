#!/usr/bin/env python3
# =============================================================================
# PODCAST PRODUCTION ENGINE :: DETERMINISTIC INTAKE HANDLER (fast-ACK contract)
# webhook-design.md Section 6 (fast-ACK) and Section 7 (chain of custody)
# -----------------------------------------------------------------------------
# The single deterministic entry point (NO language model, NO Model Context
# Protocol). It does only fast work: parse, map (mapper.py), tenant-check,
# dedup-claim (ledger.py), persist, and then fire the durable flow. The response
# means "durably recorded," NOT "produced." An episode takes minutes to hours; a
# webhook request is never held open for production, so the 8-concurrent budget
# stays irrelevant even when several submissions land together.
#
# Because the installed Webhooks plugin assigns the flowId (no client-supplied
# id), dedup is the intake LEDGER's exclusive-create claim (authoritative), and
# the job_key rides in the flow's stateJson so get_flow can map it back. This
# handler runs in one of three modes:
#   no-flow      : map + dedup + persist only (the pure fast-ACK; used by the
#                  T1-T9 verification harness and unit fixtures).
#   in-flow      : the plugin already created a flow (upstream posts
#                  action:create_flow); this handler is the flow's FIRST
#                  deterministic step (a Bash call). A fresh accept advances to
#                  Step 1; a duplicate / needs_input / test / wrong-tenant closes
#                  the plugin-created flow so it never runs the pipeline.
#   trigger-flow : direct/degraded senders (no action wrapper); this handler
#                  creates the durable managed flow itself. Because the route binds
#                  sessionKey podcast:intake:<client-slug>, the flow's controllerId
#                  runbook advances Step 1 onward in the podcast agent's OWN turn
#                  (the tool-bearing session), exactly like in-flow. It is NEVER
#                  dispatched via run_task(runtime="subagent"): sub-agents get NO
#                  Model Context Protocol and Step 1 onward is tool-bearing (Convert
#                  and Flow REST, Podbean, custom-field writes, enrollment).
#
# INBOUND SIGNATURE VERIFICATION (webhook authentication):
#   When PODCAST_INTAKE_INBOUND_SECRET is set, every inbound payload MUST carry
#   an X-Podcast-Intake-Signature header formatted as "sha256=<hex hmac of raw
#   payload bytes>". The handler hashes the raw bytes with HMAC-SHA256 and
#   compares using hmac.compare_digest. Missing or invalid signatures are
#   rejected (FAIL CLOSED): no flow is created, and the rejection is logged.
#   When the secret is NOT configured, the handler logs a one-line warning and
#   proceeds without verification (backward compatibility for existing unsigned
#   senders).
#
# Silence discipline: this layer emits ZERO client-facing messages. Operator
# alerts (needs_input, tenant mismatch, 409 exhaustion, ledger corruption) are
# written to a durable operator-alert log for alert-dedup.py to route to the
# founder only; nothing here sends Telegram or bypasses the gateway.
#
# EXIT: 0 accepted/duplicate/accepted-incomplete/quarantined/test (all are 200-
#       class fast-ACKs) / 2 handler error (5xx) / 3 usage.
# USAGE:
#   python3 intake_handler.py handle --payload FILE [--mode no-flow|in-flow|trigger-flow]
#       [--flow-id ID] [--base DIR] [--json] [--signature HEADER_VALUE]
#   python3 intake_handler.py --self-test
# Tenant + test-contact identifiers come from the environment; the tenant value is
# never printed (match / mismatch only).
# =============================================================================
"""Deterministic Podcast Engine intake handler implementing the fast-ACK contract.

Inbound webhook signature verification (HMAC-SHA256):
- Env label: PODCAST_INTAKE_INBOUND_SECRET
- Expected header: X-Podcast-Intake-Signature, format ``sha256=<hex digest>``
- The raw payload bytes are hashed BEFORE any parsing.
- Secret configured -> FAIL CLOSED (missing/invalid signature rejected).
- Secret NOT configured -> warning logged, proceed (backward compat).
- Uses hmac.compare_digest for timing-attack resistance.
"""

import argparse
import hmac
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_key  # noqa: E402
import ledger  # noqa: E402
import mapper  # noqa: E402
from flow_client import FlowClient, FlowError  # noqa: E402

EXIT_OK = 0
EXIT_HANDLER_ERROR = 2
EXIT_USAGE = 3

ENV_LOCATION = "PODCAST_CLIENT_LOCATION_ID"
ENV_TEST_CONTACT = "PODCAST_TEST_CONTACT_ID"
ENV_ROUTE = "PODCAST_INTAKE_ROUTE_ID"
ENV_SESSION = "PODCAST_INTAKE_SESSION_KEY"
ENV_CONTROLLER = "PODCAST_INTAKE_CONTROLLER_ID"
ENV_INBOUND_SECRET = "PODCAST_INTAKE_INBOUND_SECRET"
ENV_MAX_PAYLOAD_BYTES = "PODCAST_INTAKE_MAX_PAYLOAD_BYTES"
ENV_MAX_FIELD_CHARS = "PODCAST_INTAKE_MAX_FIELD_CHARS"

SIGNATURE_HEADER = "X-Podcast-Intake-Signature"
SIGNATURE_PREFIX = "sha256="

MAX_PAYLOAD_BYTES_DEFAULT = 512000
MAX_FIELD_CHARS_DEFAULT = 20000


def _verify_signature(raw_bytes, header_value, secret):
    """Verify an HMAC-SHA256 inbound signature against the raw payload bytes.

    The expected header format is ``sha256=<hex-digest>``. Uses
    hmac.compare_digest for timing-attack resistance.

    Returns True when the signature matches, False on mismatch/malformed header.
    Returns True when secret is None (caller must decide whether to fail open).
    """
    if secret is None:
        return True
    if not header_value or not header_value.startswith(SIGNATURE_PREFIX):
        return False
    digest_hex = header_value[len(SIGNATURE_PREFIX):]
    try:
        expected = hmac.HMAC(secret.encode("utf-8"), raw_bytes, "sha256").hexdigest()
    except Exception:
        return False
    return hmac.compare_digest(expected, digest_hex)


def _read_max_payload_bytes():
    val = os.environ.get(ENV_MAX_PAYLOAD_BYTES)
    if val is None:
        return MAX_PAYLOAD_BYTES_DEFAULT
    try:
        return int(val)
    except (ValueError, TypeError):
        print("WARNING: invalid %s, using default %d" % (ENV_MAX_PAYLOAD_BYTES,
              MAX_PAYLOAD_BYTES_DEFAULT), file=sys.stderr)
        return MAX_PAYLOAD_BYTES_DEFAULT


def _read_max_field_chars():
    val = os.environ.get(ENV_MAX_FIELD_CHARS)
    if val is None:
        return MAX_FIELD_CHARS_DEFAULT
    try:
        return int(val)
    except (ValueError, TypeError):
        print("WARNING: invalid %s, using default %d" % (ENV_MAX_FIELD_CHARS,
              MAX_FIELD_CHARS_DEFAULT), file=sys.stderr)
        return MAX_FIELD_CHARS_DEFAULT


def _check_field_lengths(canonical, max_chars):
    """Check every string field in the canonical dict against the per-field char
    limit. Returns a list of (field_name, actual_length) for over-limit fields."""
    over = []
    for field, value in canonical.items():
        if isinstance(value, str) and len(value) > max_chars:
            over.append((field, len(value)))
    return over


def _iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _alert_log_path(base):
    return ledger.base_dir(base) / "operator-alerts" / "alerts.ndjson"


def emit_operator_alert(condition, base, **details):
    """Record an operator-only alert intent (labels/identifiers only, never a
    secret). alert-dedup.py (a separate slice) reads this log and routes to the
    founder through the gateway. This function never sends a message itself and
    never fails the handler."""
    alert = {"at": _iso_now(), "condition": condition}
    alert.update({k: v for k, v in details.items() if v is not None})
    try:
        path = _alert_log_path(base)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        with open(str(path), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(alert, sort_keys=True) + "\n")
        try:
            os.chmod(str(path), 0o600)
        except OSError:
            pass
    except OSError:
        pass
    return alert


def _is_test_gated(canonical, config):
    """The _test flag is honored ONLY when the contact matches the designated test
    contact recorded at onboarding (Section 8). Otherwise it is ignored and the
    payload is treated as a real submission, so a stray _test can never suppress a
    real episode."""
    test_contact = config.get("test_contact_id")
    return bool(canonical.get("_test")) and bool(test_contact) \
        and str(canonical.get("contact_id")) == str(test_contact)


def _short_circuit_flow(client, config, marker, base, verdict, fail=False,
                        waiting=False, current_step=None, summary=None):
    """In-flow mode only: close (or park) the plugin-created flow so a
    duplicate / needs_input / test / wrong-tenant redelivery never runs the
    pipeline. Idempotent via the 409 guard."""
    if config.get("mode") != "in-flow" or not client or not config.get("flow_id"):
        return
    fid = config["flow_id"]
    if waiting:
        res = client.set_waiting_idempotent(fid, marker, current_step=current_step)
    elif fail:
        res = client.fail_idempotent(fid, marker, blocked_summary=summary)
    else:
        res = client.finish_idempotent(fid, marker)
    verdict["flow_op"] = {"ok": res.get("ok"), "applied_by": res.get("applied_by"),
                          "code": res.get("code")}
    if not res.get("ok"):
        verdict["operator_alert"] = emit_operator_alert(
            "flow_conflict_exhausted", base, job=verdict.get("job"),
            detail=res.get("error"))


def _launch_pipeline(client, config, jk, base, verdict):
    """Fire the durable flow for a fresh accept (or operator retry)."""
    mode = config.get("mode")
    if mode == "in-flow":
        # the plugin already created the flow; record the binding and advance to
        # Step 1 (the controller runbook continues in the podcast agent's turn)
        fid = config.get("flow_id")
        if fid:
            try:
                ledger.update_state(jk, None, base=base, flow_id=fid,
                                    note="bound to plugin flow %s; advancing to Step 1" % fid)
            except ledger.LedgerCorruption:
                pass
            verdict["flow_id"] = fid
        verdict["advance"] = True
        return
    if mode == "trigger-flow" and client:
        # Degraded/direct sender (no upstream action wrapper): the handler creates
        # the durable managed flow itself. The route binds sessionKey
        # podcast:intake:<client-slug>, so the flow is owned by the client's podcast
        # department agent, and its controllerId runbook advances Step 1 onward in
        # that agent's OWN turn -- the tool-bearing session. The compact, pointer-
        # based payload location rides in stateJson (never payload-inlined), so the
        # controller reads the ledger payload directly; no task instruction and no
        # sub-agent dispatch is issued from here. This is the hard sub-agent-no-MCP
        # boundary: run_task(runtime="subagent") would spawn a Model-Context-Protocol
        # -less sub-agent, but Step 1 onward is tool-bearing (Convert and Flow REST,
        # Podbean, custom-field writes, Skill 44 enrollment). Any pure-content
        # delegation (research synthesis, drafting, QC reads that touch only
        # text/files) is spawned BY the controller runbook for that specific
        # sub-step, never by this intake handler.
        payload = str(ledger.payload_path(jk, base))
        state_json = {"engine": "podcast", "job_key": jk,
                      "ledger_payload_path": payload, "advance_from": "step_1_ingest"}
        st, resp = client.create_flow(
            "Podcast Production Engine intake %s" % jk,
            controller_id=config.get("controller_id"),
            status="queued", notify_policy="silent", state_json=state_json)
        if st != 200 or not (resp or {}).get("ok"):
            verdict["operator_alert"] = emit_operator_alert(
                "flow_create_failed", base, job=jk,
                detail=(resp or {}).get("error"))
            return
        flow = client._extract_flow(resp)
        fid = flow.get("flowId")
        try:
            ledger.update_state(jk, None, base=base, flow_id=fid,
                                note="managed flow %s created; controller runbook advances "
                                     "Step 1 in the podcast agent's own turn" % fid)
        except ledger.LedgerCorruption:
            pass
        verdict["flow_id"] = fid
        verdict["advance"] = True
        return
    # no-flow mode: durably recorded, nothing dispatched
    verdict["advance"] = False


def handle(body, config, tables=None, client=None):
    """Run the full deterministic fast-ACK pipeline. Returns the ACK verdict."""
    tables = tables or mapper.load_tables()
    base = config.get("base")
    expected_loc = config.get("expected_location_id")

    result = mapper.map_payload(body, tables, expected_location_id=expected_loc)
    canonical = result["canonical"]

    # Tenant check is HARD: a wrong-tenant payload is quarantined and NOTHING is
    # processed, so cross-client contamination is structurally impossible.
    if result["status"] == "tenant_mismatch":
        qpath = ledger.quarantine(body, "tenant_mismatch", base=base)
        verdict = {"ack_http": 200, "status": "quarantined", "job": None,
                   "quarantine": qpath}
        verdict["operator_alert"] = emit_operator_alert(
            "tenant_mismatch", base,
            detail="payload location_id does not match this client's configured Location ID",
            quarantine=qpath)
        _short_circuit_flow(client, config, {"podcast_webhook_terminal": "quarantined"},
                            base, verdict, fail=True,
                            summary="wrong-tenant payload quarantined")
        return verdict

    # Per-field string-length limit (checked after mapping; Section R-33).
    max_field_chars = _read_max_field_chars()
    over_fields = _check_field_lengths(canonical, max_field_chars)
    if over_fields:
        over_names = [f for f, _ in over_fields]
        verdict = {"ack_http": 200, "status": "rejected", "job": None,
                   "reason": "field_length_limit",
                   "overlimit_fields": over_names}
        verdict["operator_alert"] = emit_operator_alert(
            "field_length_limit", base,
            detail="fields over %d chars: %s" % (max_field_chars,
                  ", ".join(over_names)))
        _short_circuit_flow(client, config,
                            {"podcast_webhook_terminal": "rejected",
                             "reason": "field_length_limit"}, base, verdict,
                            fail=True, summary="over-limit fields rejected")
        return verdict

    # Job key. contact_id anchors it; a needs_input payload missing contact_id gets
    # a degraded no-identity key so it is still persisted and deduped.
    jk, err = job_key.compute_job_key(canonical)
    if err:
        jk = "pd-noident-%s" % job_key.canonical_hash(canonical)

    if result["status"] == "needs_input":
        initial_state = "needs_input"
    elif _is_test_gated(canonical, config):
        initial_state = "test"
    else:
        initial_state = "received"

    retry_flag = bool(canonical.get("retry"))
    try:
        claim = ledger.dedup_claim(jk, canonical, state=initial_state,
                                   retry_flag=retry_flag, base=base)
    except ledger.LedgerCorruption as exc:
        return {"ack_http": 500, "status": "error", "job": jk,
                "operator_alert": emit_operator_alert("ledger_corruption", base,
                                                      job=jk, detail=str(exc))}

    decision = claim["decision"]
    verdict = {"ack_http": 200, "job": jk, "decision": decision,
               "state": claim["record"].get("state")}

    if decision == "duplicate":
        verdict["status"] = "duplicate"
        verdict["delivery_count"] = claim["record"]["attempts"]["delivery_count"]
        _short_circuit_flow(client, config,
                            {"podcast_webhook_terminal": "duplicate", "job_key": jk},
                            base, verdict)
        return verdict

    # A fresh accept (or operator-sanctioned retry of a failed job).
    if initial_state == "needs_input":
        verdict["status"] = "accepted-incomplete"
        verdict["missing"] = result["missing"]
        verdict["operator_alert"] = emit_operator_alert(
            "needs_input", base, job=jk, missing=result["missing"])
        _short_circuit_flow(client, config,
                            {"podcast_webhook_terminal": "needs_input", "job_key": jk},
                            base, verdict, waiting=True, current_step="needs_input")
        return verdict

    if initial_state == "test":
        verdict["status"] = "accepted"
        verdict["test"] = True
        _short_circuit_flow(client, config,
                            {"podcast_webhook_terminal": "test", "job_key": jk},
                            base, verdict)
        return verdict

    verdict["status"] = "accepted"
    if decision == "retry":
        verdict["retry"] = True
    _launch_pipeline(client, config, jk, base, verdict)
    return verdict


# =============================================================================
# CLI
# =============================================================================
def _config_from_env(args):
    return {
        "expected_location_id": os.environ.get(ENV_LOCATION),
        "test_contact_id": os.environ.get(ENV_TEST_CONTACT),
        "route_id": os.environ.get(ENV_ROUTE),
        "session_key": os.environ.get(ENV_SESSION),
        "controller_id": os.environ.get(ENV_CONTROLLER),
        "base": args.base,
        "mode": args.mode,
        "flow_id": args.flow_id,
    }


def _safe_verdict(verdict):
    """The ACK carries no PII and no secret: job key, status, counts, and alert
    labels only. The raw body and canonical answers never appear here."""
    keep = ("ack_http", "status", "job", "decision", "state", "delivery_count",
            "missing", "flow_id", "advance", "test", "retry", "quarantine",
            "flow_op", "operator_alert", "overlimit_fields", "reason")
    return {k: verdict[k] for k in keep if k in verdict}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Podcast Engine deterministic intake handler.")
    ap.add_argument("cmd", nargs="?", choices=("handle",))
    ap.add_argument("--payload", help="path to the raw inbound JSON body")
    ap.add_argument("--mode", choices=("no-flow", "in-flow", "trigger-flow"), default="no-flow")
    ap.add_argument("--flow-id", dest="flow_id", help="in-flow mode: the plugin-created flowId")
    ap.add_argument("--base", help="ledger base dir (default ~/.openclaw/state/podcast-engine)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--signature", help="X-Podcast-Intake-Signature header value for HMAC verification")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.cmd != "handle":
        ap.error("a command is required (handle) or --self-test")
    if not args.payload or not Path(args.payload).is_file():
        ap.error("handle needs --payload FILE")
    try:
        raw_bytes = Path(args.payload).read_bytes()
    except OSError as exc:
        print("FATAL: cannot read --payload: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    # Payload-size limit: checked on the raw bytes BEFORE signature verification
    # and parsing, so a multi-megabyte payload is rejected at the boundary with no
    # further processing (Section R-33).
    max_bytes = _read_max_payload_bytes()
    if len(raw_bytes) > max_bytes:
        print("REJECT: payload size %d exceeds limit %d (%s)" %
              (len(raw_bytes), max_bytes, ENV_MAX_PAYLOAD_BYTES), file=sys.stderr)
        return EXIT_HANDLER_ERROR

    # Inbound HMAC-SHA256 signature verification (before any parsing).
    secret = os.environ.get(ENV_INBOUND_SECRET)
    sig_header = os.environ.get(SIGNATURE_HEADER)
    if args.signature:
        sig_header = args.signature  # CLI override for testing
    if secret is not None:
        if not _verify_signature(raw_bytes, sig_header, secret):
            print("REJECT: inbound signature missing or invalid", file=sys.stderr)
            return EXIT_HANDLER_ERROR
    else:
        print("WARNING: no PODCAST_INTAKE_INBOUND_SECRET configured; proceeding without "
              "inbound signature verification", file=sys.stderr)

    try:
        body = json.loads(raw_bytes)
    except (ValueError) as exc:
        print("FATAL: cannot parse --payload JSON: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    config = _config_from_env(args)
    client = None
    if args.mode in ("in-flow", "trigger-flow"):
        try:
            client = FlowClient(route_id=config.get("route_id"))
        except FlowError as exc:
            print("FATAL: %s" % exc, file=sys.stderr)
            return EXIT_HANDLER_ERROR

    verdict = handle(body, config, client=client)
    ack = _safe_verdict(verdict)
    if args.json:
        print(json.dumps(ack, indent=2, sort_keys=True))
    else:
        print("ack %s %s job=%s" % (verdict.get("ack_http"), verdict.get("status"),
                                    verdict.get("job")))
    return EXIT_OK if verdict.get("ack_http", 500) < 500 else EXIT_HANDLER_ERROR


# =============================================================================
# SELF-TEST (temp base dir, in-memory fake gateway; no live gateway, no real env)
# =============================================================================
def self_test():
    import tempfile
    from flow_client import _FakeGateway
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "MISS", name))

    tables = mapper.load_tables()
    loc = "LOC0000000000000000abcd"
    tmp = tempfile.mkdtemp(prefix="pd-handler-")

    def full_payload(**over):
        data = {
            "mode": "Interview Style Podcast",
            "style": "Counter Intuitive (challenge the obvious)",
            "contactId": "CNThandlertesttest001", "locationId": loc,
            "podcastId": "pb-77", "firstName": "Dana", "show_name": "Quiet Edge",
            "host_name": "Dana", "q1": "Silence is the strategy.",
            "podcast_interview_smiq": "I disclose the AI assist up front.",
        }
        data.update(over)
        return {"data": data}

    base_cfg = {"expected_location_id": loc, "test_contact_id": "CNTtestcontact999",
                "route_id": "podcast-intake-canary",
                "controller_id": "webhooks/podcast-intake-canary",
                "session_key": "podcast:intake:canary", "base": tmp, "mode": "no-flow"}

    # 1) fresh accept (no-flow): 200 accepted, ledger received
    v1 = handle(full_payload(), dict(base_cfg), tables)
    check("fresh accept -> 200 accepted", v1["ack_http"] == 200 and v1["status"] == "accepted")
    check("ledger state received", v1["state"] == "received")
    check("job key has pd- prefix", v1["job"].startswith("pd-"))

    # 2) identical redelivery -> duplicate, no second record
    v2 = handle(full_payload(), dict(base_cfg), tables)
    check("redelivery -> duplicate", v2["status"] == "duplicate" and v2["job"] == v1["job"])
    check("duplicate delivery_count 2", v2["delivery_count"] == 2)

    # 3) one-answer change -> new job (hash sensitivity)
    v3 = handle(full_payload(q1="A different thesis entirely."), dict(base_cfg), tables)
    check("changed answer -> new job", v3["status"] == "accepted" and v3["job"] != v1["job"])

    # 4) missing style -> accepted-incomplete + needs_input + operator alert names it
    v4 = handle({"data": {"mode": "Personal", "contactId": "CNTneedsinput0000001",
                          "locationId": loc, "podcastId": "pb-1", "firstName": "Ann",
                          "q1": "x"}}, dict(base_cfg), tables)
    check("missing style -> accepted-incomplete", v4["status"] == "accepted-incomplete")
    check("needs_input state", v4["state"] == "needs_input" and "style" in v4["missing"])
    check("operator alert emitted for needs_input", v4["operator_alert"]["condition"] == "needs_input")

    # 5) wrong tenant -> quarantined, nothing processed, alert fired
    v5 = handle(full_payload(locationId="SOMEOTHERTENANTID99999"), dict(base_cfg), tables)
    check("wrong tenant -> quarantined", v5["status"] == "quarantined" and v5["job"] is None)
    check("quarantine file exists", Path(v5["quarantine"]).is_file())
    check("tenant alert fired", v5["operator_alert"]["condition"] == "tenant_mismatch")

    # 6) _test flag gated to the designated test contact
    test_cfg = dict(base_cfg); test_cfg["test_contact_id"] = "CNTdesignatedtest01"
    vt = handle(full_payload(contactId="CNTdesignatedtest01", **{"_test": "true"}),
                dict(test_cfg), tables)
    check("test-gated payload -> state test", vt["state"] == "test" and vt.get("test") is True)
    # a stray _test from a NON-test contact is ignored (treated as real)
    vt2 = handle(full_payload(contactId="CNTrealcontact00001", **{"_test": "true"}),
                 dict(test_cfg), tables)
    check("stray _test ignored -> received", vt2["state"] == "received")

    # 7) operator-alert log is a durable operator-only artifact (0600), no secrets
    alog = _alert_log_path(tmp)
    check("operator-alert log written", alog.is_file())
    check("operator-alert log mode 0600", oct(alog.stat().st_mode & 0o777) == "0o600")

    # 8) IN-FLOW mode: the plugin created a flow; a duplicate closes it, an accept advances
    fake = _FakeGateway()
    client = FlowClient(route_id="podcast-intake-canary", transport=fake.transport,
                        sleep=lambda _s: None)
    st, resp = client.create_flow("intake", state_json={"engine": "podcast"})
    fid = client._extract_flow(resp)["flowId"]
    inflow_cfg = dict(base_cfg); inflow_cfg["mode"] = "in-flow"; inflow_cfg["flow_id"] = fid
    tmp2 = tempfile.mkdtemp(prefix="pd-handler-inflow-"); inflow_cfg["base"] = tmp2
    vf1 = handle(full_payload(contactId="CNTinflowaccept0001"), dict(inflow_cfg), tables, client=client)
    check("in-flow fresh accept advances", vf1["status"] == "accepted" and vf1.get("advance") is True)

    st2, resp2 = client.create_flow("intake2", state_json={"engine": "podcast"})
    fid2 = client._extract_flow(resp2)["flowId"]
    dup_cfg = dict(inflow_cfg); dup_cfg["flow_id"] = fid2
    handle(full_payload(contactId="CNTinflowaccept0001"), dict(dup_cfg), tables, client=client)  # first claim
    vf2 = handle(full_payload(contactId="CNTinflowaccept0001"), dict(dup_cfg), tables, client=client)  # redelivery
    check("in-flow duplicate closes its flow", vf2["status"] == "duplicate"
          and vf2.get("flow_op", {}).get("ok") is True
          and fake.flows[fid2]["status"] == "done")

    # 9) TRIGGER-FLOW mode: handler creates the managed flow; its controller runbook
    # advances Step 1 in the podcast agent's OWN turn. The handler dispatches NO
    # sub-agent (sub-agents get no Model Context Protocol; Step 1 onward is tool-bearing).
    tf_cfg = dict(base_cfg); tf_cfg["mode"] = "trigger-flow"
    tmp3 = tempfile.mkdtemp(prefix="pd-handler-trigger-"); tf_cfg["base"] = tmp3
    before = fake.counter
    runs_before = len(fake.task_runtimes)
    vtf = handle(full_payload(contactId="CNTtriggerflow00001"), dict(tf_cfg), tables, client=client)
    check("trigger-flow creates a flow", vtf["status"] == "accepted"
          and vtf.get("flow_id") and fake.counter == before + 1)
    check("trigger-flow advances in the agent's own turn", vtf.get("advance") is True)
    check("trigger-flow dispatches NO sub-agent (no MCP-less run_task)",
          len(fake.task_runtimes) == runs_before)
    rec = ledger.read_record(vtf["job"], tmp3)
    check("trigger-flow records flow_id in ledger", rec.get("flow_id") == vtf["flow_id"])

    # 10) PAYLOAD-SIZE LIMIT: a multi-megabyte payload is rejected BEFORE signature
    # verification or parsing (Section R-33). Override the env to a low limit and
    # verify that raw bytes exceeding it are rejected with EXIT_HANDLER_ERROR.
    small_limit = 200
    os.environ[ENV_MAX_PAYLOAD_BYTES] = str(small_limit)
    tmp_payload_file = tmp + "/oversize_payload.json"
    with open(tmp_payload_file, "w", encoding="utf-8") as fh:
        json.dump({"data": {"mode": "Interview", "contactId": "CNTpayloadtest00001",
                   "locationId": loc, "q1": "x" * (small_limit + 50)}}, fh)
    # Simulate the main() payload-size check path by calling main with test args.
    exit_code = main(["handle", "--payload", tmp_payload_file,
                      "--base", tmp, "--mode", "no-flow"])
    check("oversize payload rejected before signature verification",
          exit_code == EXIT_HANDLER_ERROR)
    # A payload AT the limit should pass; use main() with env vars so the
    # payload-size gate in main() is actually exercised.
    os.environ[ENV_LOCATION] = loc
    at_limit_data = {"data": {"mode": "Interview", "contactId": "CNTattest99",
                     "locationId": loc, "q1": "ok"}}
    with open(tmp_payload_file, "w", encoding="utf-8") as fh:
        json.dump(at_limit_data, fh)
    actual_size = Path(tmp_payload_file).stat().st_size
    os.environ[ENV_MAX_PAYLOAD_BYTES] = str(actual_size)
    exit_code_at = main(["handle", "--payload", tmp_payload_file,
                          "--base", tmp, "--mode", "no-flow"])
    check("payload at limit accepted", exit_code_at == EXIT_OK)
    # Restore the env so later tests are not affected.
    del os.environ[ENV_MAX_PAYLOAD_BYTES]

    # 11) FIELD-CHARACTER LIMIT: a string field exceeding the configurable max is
    # rejected with a clear reason (Section R-33). Override the env to a low limit
    # and verify the verdict.
    small_field_limit = 100
    os.environ[ENV_MAX_FIELD_CHARS] = str(small_field_limit)
    over_field_cfg = dict(base_cfg)
    over_field_tmp = tempfile.mkdtemp(prefix="pd-handler-fieldlimit-")
    over_field_cfg["base"] = over_field_tmp
    vf_over = handle(full_payload(q1="x" * (small_field_limit + 1)),
                     dict(over_field_cfg), tables)
    check("over-limit field rejected", vf_over["status"] == "rejected"
          and vf_over.get("reason") == "field_length_limit"
          and "q1_answer" in vf_over.get("overlimit_fields", []))
    check("over-limit field alert fired",
          vf_over.get("operator_alert", {}).get("condition") == "field_length_limit")
    # A field AT the limit should be accepted.
    vf_at = handle(full_payload(q1="x" * small_field_limit),
                   dict(over_field_cfg), tables)
    check("field at limit accepted", vf_at["status"] == "accepted")
    del os.environ[ENV_MAX_FIELD_CHARS]

    print("== intake_handler self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
