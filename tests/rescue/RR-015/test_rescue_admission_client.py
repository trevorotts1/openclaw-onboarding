#!/usr/bin/env python3
# tests/rescue/RR-015/test_rescue_admission_client.py
#
# RR-015 — EWS stale P1 and fleet dead-man each create ONE canonical rescue
# ticket with a validated receipt through the SHARED admission client
# (scripts/lib/rescue_admission.py), via a mocked/staging admission endpoint.
# Cases (QC.md RR-015 + SPEC RR-015 exact repair):
#   1. stale P1 escalate -> exactly one admission post, one journaled granted
#      receipt, event acked escalated ONLY on admission (never on a send)
#   2. fleet dead-man -> exactly one admission post + receipt, event acked on
#      receipt; a second silent box does NOT double-fire the same episode
#   3. replay / return-path identity: same event -> same operation_id, same
#      box, same source; a re-post carries the SAME identity (intake can fold)
#   4. gateway unavailable does NOT block the healthy outbound HTTP path: the
#      sender stub raising changes NOTHING about an admitted receipt
#   5. failed transport / policy refusal / undetermined answer / missing client
#      / missing enrollment never consume the alert (event stays OPEN); a
#      MISSING ENROLLMENT is recorded as pending repair WITH AN OWNER and is
#      never reported as an admission (RR-015 exact repair)
#   8. duplicate fold -> replay: accepted + ack-eligible, never a refusal
#   9. header selection follows what the LIVE intake READS: x-rescue-secret by
#      default (verified against the shipped FLEET export); the unread v2
#      per-enrollment headers are emitted ONLY on explicit opt-in
#   6. dry-run changes no state (no ack, no admission post, no journal row)
#   7. nine-field legacy contract present; client versioned; credential VALUES
#      never journaled (names/shapes only in diagnostics)
#
# Hermetic: every transport is injected; no network, no model, no credentials.
# Run: python3 tests/rescue/RR-015/test_rescue_admission_client.py
import json
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCRIPTS = os.path.join(REPO, "60-zhc-early-warning-system", "scripts")
sys.path.insert(0, SCRIPTS)

import ews_alert as A          # noqa: E402
import ews_common as C        # noqa: E402
import ews_fleet as F         # noqa: E402
from ews_ledger import Ledger  # noqa: E402

FAILS = []


def ok(name):
    print("  ok %s" % name)


def fail(name, detail=""):
    print("  FAIL %s %s" % (name, detail))
    FAILS.append(name + ((" :: " + str(detail)[:200]) if detail else ""))


def check(cond, name, detail=""):
    if cond:
        ok(name)
    else:
        fail(name, detail)


print("== RR-015 ONB: EWS rescue admission (stale P1 + dead-man) ==")

client = C.load_rescue_admission()
check(client is not None, "shared admission client loads via ews_common")
check(getattr(client, "RESCUE_ADMISSION_CLIENT_VERSION", "") == "1.0.0",
      "admission client versioned 1.0.0")
check(getattr(client, "build_payload", None) is not None, "client exposes build_payload")
check(client.DEFAULT_WEBHOOK_URL.endswith("rr-v2-intake"),
      "default intake path is the canonical rr-v2-intake webhook")

os.environ["EWS_BOX_NAME"] = "rr015-drill-box"
os.environ["FLEET_STANDING_BOX_SLUG"] = "box-rr015-canonical"
os.environ["EWS_RESCUE_CHAT"] = "8888rescue-drill"
os.environ["EWS_OPERATOR_CHAT"] = "9999op-drill"


def admission_client(posts, status=200, body='{"accepted":true,"ticketId":"T-RR015"}',
                     raise_cls=None, refuse_detail="fixture transport failure"):
    """A fake module whose admit() drives the REAL client with an injected
    transport. posts records what actually went to the wire."""
    def transport(url, payload_bytes, timeout=None):
        posts.append({"url": url, "body": json.loads(payload_bytes.decode("utf-8"))})
        if raise_cls:
            raise raise_cls(refuse_detail)
        return body

    def admit(state_dir=None, box="", problem_text="", **kw):
        return client.admit(
            state_dir, box=box, problem_text=problem_text,
            source=kw.get("source", "skill-60-ews"), signal=kw.get("signal", ""),
            key_path=kw.get("key_path", ""), dedup_key=kw.get("dedup_key", ""),
            event_id=kw.get("event_id"), tick_ts=kw.get("tick_ts", ""),
            transport=transport, url="https://intake.invalid/rr-v2-intake")
    return {"admit": admit, "load": None}


CRED_ENVS = (client.BOX_CRED_ENV, client.BOX_ID_ENV, client.SECRET_ENV,
             client.V2_HEADERS_ENV)


def _raise_unauth():
    """Fixture transport: the LIVE intake's fail-closed auth answer."""
    raise client.AdmissionRefused('intake HTTP 403: {"status":"unauthorized"}')


def clear_state():
    for k in ("EWS_STATE_DIR", "EWS_FLEET_DIR", "EWS_BOX_NAME",
              "FLEET_STANDING_BOX_SLUG", "EWS_RESCUE_CHAT", "EWS_OPERATOR_CHAT"):
        os.environ.pop(k, None)
    for k in CRED_ENVS:
        os.environ.pop(k, None)


def creds(schema="v1", value="fixture-shared-secret-not-a-real-value"):
    """Pin the admission credential for ONE case so the schema the client
    presents is knowable: 'v1' shared secret, 'v2' per-enrollment pair, or
    'none' (no credential anywhere). Returns the prior env for restore().

    RR-015 drills must never depend on ambient credentials: a case asserting a
    POLICY refusal is only meaningful when a credential was actually presented
    -- with none, the same refusal is correctly reported as no_enrollment."""
    saved = {k: os.environ.get(k) for k in CRED_ENVS}
    for k in CRED_ENVS:
        os.environ.pop(k, None)
    if schema == "v1":
        os.environ[client.SECRET_ENV] = value
    elif schema == "v2":
        os.environ[client.BOX_CRED_ENV] = value
        os.environ[client.BOX_ID_ENV] = "box-enroll-fixture"
    return saved


def restore(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# --------------------------------------------------------------------------
# CASE 1: stale P1 -> exactly one admission, one receipt, ack ONLY on receipt
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c1-") as td:
    posts = []
    cl = admission_client(posts)
    with Ledger(td) as led:
        eid = led.record_event("S6", "P1", "config.owner", "config", "drill-a",
                               tick_ts="2000-01-01T00:00:00+00:00")
    esc = A.escalate(td, sender=lambda *a: (True, "fake-sent"), admission=cl["admit"])
    check(any(e["event_id"] == eid and e["admission_status"] == "admitted" for e in esc),
          "stale P1 admitted (one receipt)", esc)
    check(len(posts) == 1, "exactly one admission post for one stale P1", len(posts))
    p = posts[0]["body"]
    check(p["boxName"] == "box-rr015-canonical", "payload identity is the ENROLLED slug", p.get("boxName"))
    check(p["machine"]["ews_event_id"] == eid, "payload carries the source event id", p.get("machine"))
    check(p["operation_id"], "payload carries a stable operation id")
    check({k for k in ("action", "person", "clientName", "agentName", "boxName",
                       "boxType", "openclawVersion", "problem", "alreadyTried",
                       "returnTo")} <= set(p),
          "nine-field legacy contract present in the payload")
    with Ledger(td) as led:
        st = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid,)).fetchone()[0]
        row = led.latest_admission(p["operation_id"])
    check(st == "escalated", "event acked escalated ONLY on the validated receipt", st)
    check(row is not None and row["status"] == "admitted" and row["ticket_id"] == "T-RR015"
          and row["reply_digest"], "journal row: admitted + ticket + digest (never the body)")
    clear_state()

# --------------------------------------------------------------------------
# CASE 2: dead-man -> exactly one admission; second silent box separate episode
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c2-") as td:
    posts = []
    cl = admission_client(posts)
    os.environ["EWS_STATE_DIR"] = td
    os.environ["EWS_FLEET_DIR"] = os.path.join(td, "ews-fleet")
    os.environ["EWS_RESCUE_CHAT"] = "8888rescue-drill"
    os.environ["EWS_OPERATOR_CHAT"] = "9999op-drill"
    os.environ["FLEET_STANDING_BOX_SLUG"] = "box-rr015-operator-aggregator"
    F.cmd_ingest("box-dm-one", {"last_tick_ts": "2000-01-01T00:00:00+00:00", "by_severity": {}})
    F.cmd_cycle(sender=lambda *a: (True, "fake"), admission=cl["admit"])   # cycle 1
    F.cmd_cycle(sender=lambda *a: (True, "fake"), admission=cl["admit"])   # cycle 2 -> dark
    check(len(posts) == 1, "dead-man fires exactly ONE admission post", len(posts))
    check(posts[0]["body"]["source"] == "skill-60-ews-fleet",
          "dead-man admission is the fleet source", posts[0]["body"].get("source"))
    with Ledger(td) as led:
        evs = [dict(r) for r in led.conn.execute(
            "SELECT * FROM events WHERE dedup_key='deadman|box-dm-one' ORDER BY event_id").fetchall()]
    check(evs and evs[0]["ack_state"] == "escalated", "dead-man event escalated on receipt")
    # a third cycle does NOT re-post the same episode (dedup; new silent episode
    # events stay open but do not double-fire admission for the same box)
    before = len(posts)
    F.cmd_cycle(sender=lambda *a: (True, "fake"), admission=cl["admit"])   # cycle 3
    with Ledger(td) as led:
        evs3 = [dict(r) for r in led.conn.execute(
            "SELECT * FROM events WHERE dedup_key='deadman|box-dm-one' ORDER BY event_id").fetchall()]
    check(all(e["ack_state"] in ("escalated", "open") for e in evs3),
          "dead-man cycle 3 keeps events owned (escalated or open, never lost)")
    # failed admission on the next episode -> OPEN, but no post is made for a
    # healthy box's resumed report
    clear_state()

# --------------------------------------------------------------------------
# CASE 3: replay/return-path identity — same event -> same operation id.
# "Response lost after real admission recovers the same ticket": the FIRST
# attempt fails at the transport (event stays OPEN), the SECOND succeeds.
# Both posts must carry the SAME operation id + box + source event id so the
# intake can fold the replay onto the one ticket instead of minting two.
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c3-") as td:
    os.environ["FLEET_STANDING_BOX_SLUG"] = "box-rr015-canonical"
    posts = []

    def flaky_transport(url, payload_bytes, timeout=None):
        posts.append(json.loads(payload_bytes.decode("utf-8")))
        if len(posts) == 1:
            raise client.AdmissionTransportError("response lost (fixture)")
        return '{"accepted":true,"ticketId":"T-RR015-RECOVER"}'

    def flaky_client(state_dir=None, box="", problem_text="", **kw):
        return client.admit(
            state_dir, box=box, problem_text=problem_text,
            source=kw.get("source", "skill-60-ews"), signal=kw.get("signal", ""),
            key_path=kw.get("key_path", ""), dedup_key=kw.get("dedup_key", ""),
            event_id=kw.get("event_id"), tick_ts=kw.get("tick_ts", ""),
            transport=flaky_transport, url="https://intake.invalid/rr-v2-intake")

    with Ledger(td) as led:
        eid = led.record_event("S6", "P1", "config.owner", "config", "drill-c",
                               tick_ts="2000-01-01T00:00:00+00:00")
    esc1 = A.escalate(td, sender=lambda *a: (True, "x"), admission=flaky_client)
    with Ledger(td) as led:
        st1 = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid,)).fetchone()[0]
    check(st1 == "open", "lost response leaves the event OPEN for recovery", st1)
    esc2 = A.escalate(td, sender=lambda *a: (True, "x"), admission=flaky_client)
    check(len(posts) == 2, "recovery attempt posts again", len(posts))
    check(posts[0]["operation_id"] == posts[1]["operation_id"],
          "recovery carries the SAME operation identity (intake folds, one ticket)")
    check(posts[0]["boxName"] == posts[1]["boxName"] == "box-rr015-canonical",
          "return-path identity preserved across the recovery attempt")
    check(posts[0]["machine"]["ews_event_id"] == eid == posts[1]["machine"]["ews_event_id"],
          "source event identity preserved across the recovery attempt")
    with Ledger(td) as led:
        st2 = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid,)).fetchone()[0]
    check(st2 == "escalated", "recovered admission acked the SAME event exactly once", st2)
    with Ledger(td) as led:
        rows = [dict(r) for r in led.conn.execute(
            "SELECT status FROM rescue_admissions WHERE event_id=? ORDER BY admission_id",
            (eid,)).fetchall()]
    check([r["status"] for r in rows] == ["failed", "admitted"],
          "journal: failed attempt then admitted recovery (same operation)", rows)
    check(posts[1]["boxName"] == "box-rr015-canonical",
          "recovery box identity is the enrolled slug")
    clear_state()

# --------------------------------------------------------------------------
# CASE 4: gateway unavailable does NOT block the healthy outbound HTTP path
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c4-") as td:
    posts = []
    cl = admission_client(posts)

    def dead_gateway(*a, **k):
        raise OSError("gateway down (fixture)")

    with Ledger(td) as led:
        eid = led.record_event("S6", "P1", "config.owner", "config", "drill-d",
                               tick_ts="2000-01-01T00:00:00+00:00")
    esc = A.escalate(td, sender=dead_gateway, admission=cl["admit"])
    check(len(posts) == 1, "admission POST happens even when the gateway send raises",
          len(posts))
    check(any(e["event_id"] == eid and e["admission_status"] == "admitted" for e in esc),
          "admitted receipt stands despite gateway failure", esc)
    clear_state()

# --------------------------------------------------------------------------
# CASE 5: failure classes NEVER consume the alert
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c5-") as td:
    # No case in this block may depend on ambient credentials: pin a v1 shared
    # secret (5e overrides to "none") so the schema the client presents, and
    # therefore the refusal-class split, is genuinely exercised.
    _c5_saved = creds("v1")

    # 5a transport failure
    posts = []
    cl = admission_client(posts, raise_cls=client.AdmissionTransportError)
    with Ledger(td) as led:
        eid = led.record_event("S6", "P1", "c", "config", "drill-e",
                               tick_ts="2000-01-01T00:00:00+00:00")
    esc = A.escalate(td, sender=lambda *a: (True, "x"), admission=cl["admit"])
    with Ledger(td) as led:
        st = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid,)).fetchone()[0]
    check(st == "open", "transport failure leaves event OPEN (retry-eligible)", st)
    check(any(e["event_id"] == eid and e["admission_status"] == "failed" for e in esc),
          "transport failure status failed", esc)

    # 5b explicit POLICY refusal (400: missing message): reached, terminal for
    # this attempt, event still OPEN -- and NOT reclassified as an enrollment
    # repair, because a credential WAS presented and the reason is not
    # auth-shaped.
    cl2 = admission_client([], raise_cls=client.AdmissionRefused,
                           refuse_detail="intake HTTP 400: missing message")
    with Ledger(td) as led:
        eid2 = led.record_event("S6", "P1", "c", "config", "drill-f",
                                tick_ts="2000-01-01T00:00:00+00:00")
    esc2 = A.escalate(td, sender=lambda *a: (True, "x"), admission=cl2["admit"])
    with Ledger(td) as led:
        st2 = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid2,)).fetchone()[0]
        rows = led.conn.execute(
            "SELECT status FROM rescue_admissions WHERE event_id=? "
            "ORDER BY admission_id DESC LIMIT 1", (eid2,)).fetchone()
    check(st2 == "open", "policy refusal leaves event OPEN", st2)
    check(rows is not None and rows[0] == "refused",
          "policy refusal journaled as refused (never as an enrollment repair)", rows)
    check(not any(e["admission_status"] == "no_enrollment" for e in esc2),
          "a policy refusal is NOT misreported as a missing enrollment", esc2)

    # 5c undetermined answer (HTML): never a success, never a refusal
    cl3 = admission_client([], body="<html>502 Bad Gateway</html>")
    with Ledger(td) as led:
        eid3 = led.record_event("S6", "P1", "c", "config", "drill-g",
                                tick_ts="2000-01-01T00:00:00+00:00")
    esc3 = A.escalate(td, sender=lambda *a: (True, "x"), admission=cl3["admit"])
    with Ledger(td) as led:
        st3 = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid3,)).fetchone()[0]
    check(st3 == "open", "undetermined HTML answer leaves event OPEN", st3)
    check(any(e["event_id"] == eid3 and e["admission_status"] == "failed" for e in esc3),
          "undetermined answer classified failed, never admitted", esc3)

    # 5d missing client (shared client absent) -> client_unavailable, OPEN
    with Ledger(td) as led:
        eid4 = led.record_event("S6", "P1", "c", "config", "drill-h",
                                tick_ts="2000-01-01T00:00:00+00:00", dedup_key="drill-h")
        real = C.load_rescue_admission

        def _none(*a, **k):
            return None
        C.load_rescue_admission = _none
        try:
            esc4 = A.escalate(td, sender=lambda *a: (True, "x"), admission=None)
        finally:
            C.load_rescue_admission = real
    with Ledger(td) as led:
        st4 = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid4,)).fetchone()[0]
    check(st4 == "open", "missing client leaves event OPEN (owned setup fault)", st4)
    check(any(e["event_id"] == eid4 and e["admission_status"] == "client_unavailable"
              for e in esc4), "missing client reported client_unavailable", esc4)

    # 5e NO ENROLLMENT at the EWS path: a box the intake will not authenticate
    # (403 unauthorized) has a MISSING ENROLLMENT, which RR-015 says must be
    # recorded as a PENDING REPAIR WITH AN OWNER -- visible, retryable, and
    # never reported as an admission (and never as a generic refusal).
    creds("none")
    cl5 = admission_client([], raise_cls=client.AdmissionRefused,
                           refuse_detail='intake HTTP 403: {"status":"unauthorized"}')
    with Ledger(td) as led:
        eid5 = led.record_event("S6", "P1", "c", "config", "drill-k",
                                tick_ts="2000-01-01T00:00:00+00:00", dedup_key="drill-k")
    esc5 = A.escalate(td, sender=lambda *a: (True, "x"), admission=cl5["admit"])
    with Ledger(td) as led:
        st5 = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid5,)).fetchone()[0]
        dg = [dict(r) for r in led.conn.execute(
            "SELECT kind,payload FROM digests WHERE dedup_key=?", ("drill-k",)).fetchall()]
        adm5 = led.conn.execute(
            "SELECT status,detail FROM rescue_admissions WHERE event_id=? "
            "ORDER BY admission_id DESC LIMIT 1", (eid5,)).fetchone()
    check(st5 == "open", "missing enrollment leaves the event OPEN (retry-eligible)", st5)
    check(any(e["event_id"] == eid5 and e["admission_status"] == "no_enrollment" for e in esc5),
          "missing enrollment reported no_enrollment, never as an admission", esc5)
    check(not any(e["admission_status"] == "admitted" for e in esc5),
          "a missing enrollment is NEVER reported as an admission", esc5)
    kinds5 = [d["kind"] for d in dg]
    check("rescue_admission_pending_repair" in kinds5,
          "missing enrollment recorded as pending repair (digest)", kinds5)
    check(not any(k == "rescue_admission_ticket" for k in kinds5),
          "no admission ticket digest is minted for a missing enrollment", kinds5)
    pr = [d for d in dg if d["kind"] == "rescue_admission_pending_repair"]
    check(bool(pr) and client.REPAIR_OWNER_ENROLLMENT in (pr[0]["payload"] or "")
          and "action=" in (pr[0]["payload"] or ""),
          "pending-repair record carries an OWNER and a next action", pr)
    check(adm5 is not None and adm5["status"] == "no_enrollment",
          "journal: the attempt is status no_enrollment (not refused/failed)", adm5)
    restore(_c5_saved)

    # 5f CLIENT level: v2-only enrollment (credential pair, v2 headers OFF by
    # default because the live intake reads only x-rescue-secret) -> the box
    # cannot authenticate -> no_enrollment + pending-repair owner, and NOT
    # ack-eligible, so no caller can mark an event escalated on it.
    creds("v2")
    r6 = client.admit(td, box="box-rr015-canonical", problem_text="drill-l",
                      source="skill-60-ews", signal="S6", dedup_key="drill-l",
                      event_id=4242, transport=lambda *a, **k: _raise_unauth(),
                      url="https://intake.invalid/rr-v2-intake")
    check(r6["status"] == "no_enrollment",
          "v2-only box with the live intake reports no_enrollment", r6.get("status"))
    check(r6.get("pending_repair") is True
          and r6.get("repair_owner") == client.REPAIR_OWNER_ENROLLMENT
          and bool(r6.get("repair_action")),
          "no_enrollment receipt carries pending_repair + owner + action", r6)
    check(not C.admission_is_ack_eligible(r6["status"]),
          "no_enrollment is NOT ack-eligible (never an admission)")
    check(C.admission_is_pending_repair(r6["status"]),
          "no_enrollment is recognised as a pending repair by the shared vocabulary")
    check(not client.is_auth_refusal("intake HTTP 400: missing message")
          and client.is_auth_refusal('intake HTTP 403: {"status":"unauthorized"}'),
          "auth-shaped refusals are distinguished from policy refusals")
    clear_state()

# --------------------------------------------------------------------------
# CASE 6: dry-run changes no state (escalate path)
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c6-") as td:
    posts = []
    cl = admission_client(posts)
    with Ledger(td) as led:
        eid = led.record_event("S6", "P1", "c", "config", "drill-i",
                               tick_ts="2000-01-01T00:00:00+00:00")
        before_ev = led.conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        before_j = led.count_admissions()
        before_d = led.conn.execute("SELECT COUNT(*) AS n FROM digests").fetchone()["n"]
    esc = A.escalate(td, sender=lambda *a: (True, "x"), admission=cl["admit"], dry_run=True)
    with Ledger(td) as led:
        after_ev = led.conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        after_j = led.count_admissions()
        after_d = led.conn.execute("SELECT COUNT(*) AS n FROM digests").fetchone()["n"]
    check(len(posts) == 0, "dry-run posts nothing", len(posts))
    check(after_ev == before_ev and after_j == before_j and after_d == before_d,
          "dry-run changes no state (no event, no journal, no digest)")
    check(any(e["event_id"] == eid and e["admission_status"] == "dry_run" for e in esc),
          "dry-run reports admission_status dry_run", esc)
    with Ledger(td) as led:
        st = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid,)).fetchone()[0]
    check(st == "open", "dry-run leaves the P1 event OPEN", st)
    clear_state()

# --------------------------------------------------------------------------
# CASE 7: credential VALUES never in the journal/payload/detail
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c7-") as td:
    os.environ["FLEET_STANDING_BOX_SLUG"] = "box-rr015-canonical"
    os.environ["RR_BOX_CRED"] = "fixture-cred-value-not-a-real-secret-00000000000000"
    os.environ["RR_BOX_ID"] = "box-enroll-0001"
    posts = []

    def tx(url, payload_bytes, timeout=None):
        posts.append(payload_bytes.decode("utf-8"))
        return '{"accepted":true,"ticketId":"T-X","authSchema":"v2"}'

    r = client.admit(td, box="box-rr015-canonical", problem_text="drill j",
                     source="skill-60-ews", signal="S6", dedup_key="drill-j",
                     event_id=999, transport=tx,
                     url="https://intake.invalid/rr-v2-intake")
    check(r["admission_schema"] == "v2", "v2 per-enrollment schema resolved", r)
    check("fixture-cred-value-not-a-real-secret" not in posts[0],
          "credential value never placed in the payload body")
    with Ledger(td) as led:
        raw = led.db_path.read_bytes() if hasattr(led, "db_path") else b""
        rows = [dict(x) for x in led.conn.execute(
            "SELECT * FROM rescue_admissions WHERE event_id=999").fetchall()]
    joined = json.dumps(rows) + json.dumps(r)
    check("fixture-cred-value-not-a-real-secret" not in joined,
          "credential value never journaled")
    check(r["ticket_id"] == "T-X", "receipt carries the ticket id")
    clear_state()

# --------------------------------------------------------------------------
# CASE 8: duplicate fold -> REPLAY (accepted + ack-eligible, never a refusal)
# The live intake answers a re-post of the same operation_id with HTTP 200
# {"accepted":true,"status":"duplicate_ignored"}: the ticket already existed.
# RR-015 replays must preserve identity and must NOT be reported as a fresh
# admission, nor as a refusal -- and they MUST still be ack-eligible, because a
# fold proves a durable ticket exists.
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c8-") as td:
    creds("v1")
    posts = []
    cl = admission_client(
        posts, body='{"accepted":true,"status":"duplicate_ignored","ticketId":"T-RR015-EXISTING"}')
    with Ledger(td) as led:
        eid = led.record_event("S6", "P1", "c", "config", "drill-m",
                               tick_ts="2000-01-01T00:00:00+00:00", dedup_key="drill-m")
    esc = A.escalate(td, sender=lambda *a: (True, "x"), admission=cl["admit"])
    with Ledger(td) as led:
        st = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid,)).fetchone()[0]
        rows = [dict(r) for r in led.conn.execute(
            "SELECT status,ticket_id FROM rescue_admissions WHERE event_id=? "
            "ORDER BY admission_id", (eid,)).fetchall()]
    check(len(posts) == 1, "replay case posts once", len(posts))
    check(any(e["event_id"] == eid and e["admission_status"] == "replay" for e in esc),
          "duplicate fold reported replay", esc)
    check(not any(e["admission_status"] in ("refused", "failed") for e in esc),
          "a duplicate fold is never reported as a refusal or a failure", esc)
    check(any(e["ticket_id"] == "T-RR015-EXISTING" for e in esc),
          "replay carries the EXISTING ticket id", esc)
    check(st == "escalated",
          "replay is ack-eligible: a fold proves a durable ticket exists", st)
    check([r["status"] for r in rows] == ["replay"],
          "journal: duplicate fold journaled under its own status", rows)
    clear_state()

# --------------------------------------------------------------------------
# CASE 9: the credential HEADER this client sends is decided by what the LIVE
# intake READS, not by which credential the box happens to hold.
# Verified against the shipped FLEET export `rescue/workflows/RR-01-intake.json`
# node "Webhook Auth Check", which reads ONLY x-rescue-secret and fails closed
# with 403 {"status":"unauthorized"}; the RR-003 v2 per-enrollment headers
# (X-RR-Box-Cred / X-RR-Box-Id) are declared in the identity schema but NOT read
# by the live intake. Emitting them by default turned a healthy escalation into
# a 403, so the default is x-rescue-secret and v2 is opt-in
# (EWS_RESCUE_ADMISSION_SEND_V2_HEADERS=1) until an intake-side reader lands --
# that FLEET export change belongs to the manifest/export owner.
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c9-") as td:
    import urllib.request

    seen = []

    class _Resp:
        status = 200

        def read(self, n):
            return b'{"accepted":true,"ticketId":"T-HDR"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    _real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = lambda req, timeout=None: (seen.append(req.headers), _Resp())[1]
    try:
        clear_state()
        os.environ[client.SECRET_ENV] = "fixture-v1-secret-value"
        client.urllib_transport("https://intake.invalid/rr-v2-intake", b"{}")
        h1 = {k.lower() for k in seen[-1]}
        check(any("rescue-secret" in k for k in h1) and not any("rr-box" in k for k in h1),
              "v1 credential sends x-rescue-secret, never unread v2 headers", h1)

        # a box holding BOTH falls back to the secret the live intake accepts
        os.environ[client.BOX_CRED_ENV] = "fixture-cred-value-not-real"
        os.environ[client.BOX_ID_ENV] = "box-enroll-fixture"
        client.urllib_transport("https://intake.invalid/rr-v2-intake", b"{}")
        h2 = {k.lower() for k in seen[-1]}
        check(any("rescue-secret" in k for k in h2) and not any("rr-box" in k for k in h2),
              "v2 pair + shared secret falls back to the accepted v1 header", h2)

        # v2 pair and NO shared secret: no header the live intake accepts, so
        # the honest outcome is no_enrollment -- NOT a silent unauthenticated
        # post that the intake 403s as an anonymous caller.
        os.environ.pop(client.SECRET_ENV, None)
        client.urllib_transport("https://intake.invalid/rr-v2-intake", b"{}")
        h3 = {k.lower() for k in seen[-1]}
        check(not any("rr-box" in k for k in h3),
              "an unread v2 header is never emitted while the intake cannot read it", h3)

        # explicit opt-in is the seam the intake-side reader lands behind
        os.environ[client.SECRET_ENV] = "fixture-v1-secret-value"
        os.environ[client.V2_HEADERS_ENV] = "1"
        check(client.sends_v2_headers() is True, "v2 header emission is opt-in via env")
        client.urllib_transport("https://intake.invalid/rr-v2-intake", b"{}")
        h4 = {k.lower() for k in seen[-1]}
        check(any("rr-box-cred" in k for k in h4) and any("rr-box-id" in k for k in h4),
              "opt-in emits the v2 per-enrollment headers", h4)
        clear_state()
        check(client.sends_v2_headers() is False,
              "v2 header emission is OFF by default (live intake reads only x-rescue-secret)")
    finally:
        urllib.request.urlopen = _real_urlopen

# --------------------------------------------------------------------------
# CASE 10: the intake's boxEnrolled verdict rides EVERY accepted body and must
# be SURFACED, never swallowed. RR-01 mints the ticket anyway when the resolved
# box has no usable rr_box_auth row, and RR-01's own contract says a caller must
# not read accepted:true as "a fix is coming" when boxEnrolled is false (RR-02
# then fails closed NEEDS_HUMAN). A durable ticket still exists, so the receipt
# stays ack-eligible (status admitted) -- but the enrollment miss and the owned
# repair action must land in the receipt and the journal detail.
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory(prefix="rr015-c10-") as td:
    creds("v1")
    posts = []
    cl = admission_client(
        posts,
        body='{"accepted":true,"ticketId":"T-RR015-NOENR","status":"accepted",'
             '"boxEnrolled":false,"boxEnrollmentReason":"not_enrolled"}')
    with Ledger(td) as led:
        eid = led.record_event("S6", "P1", "c", "config", "drill-n",
                               tick_ts="2000-01-01T00:00:00+00:00", dedup_key="drill-n")
    esc = A.escalate(td, sender=lambda *a: (True, "x"), admission=cl["admit"])
    with Ledger(td) as led:
        st = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid,)).fetchone()[0]
        rows = [dict(r) for r in led.conn.execute(
            "SELECT status,ticket_id,detail FROM rescue_admissions WHERE event_id=? "
            "ORDER BY admission_id", (eid,)).fetchall()]
    rec = [e for e in esc if e["event_id"] == eid]
    check(any(e["admission_status"] == "admitted" for e in rec),
          "an enrollment miss with a durable ticket is still admitted", esc)
    check(any(e.get("box_enrolled") is False for e in rec),
          "boxEnrolled:false is surfaced on the receipt", esc)
    check(any(e.get("box_enrollment_reason") == "not_enrolled" for e in rec),
          "the intake's enrollment reason is surfaced on the receipt", esc)
    check(any(e["ticket_id"] == "T-RR015-NOENR" for e in rec),
          "the durable ticket id survives the enrollment miss", esc)
    check(st == "escalated",
          "an enrollment miss with a durable ticket stays ack-eligible", st)
    check("box_enrolled=false" in (rows[0]["detail"] if rows else ""),
          "the enrollment repair action lands in the journal detail", rows)
    clear_state()

# CASE 10b: the dead-man -> admission path must surface the same verdict.
with tempfile.TemporaryDirectory(prefix="rr015-c10b-") as td:
    creds("v1")
    posts = []
    cl = admission_client(
        posts,
        body='{"accepted":true,"ticketId":"T-RR015-DM-NOENR","status":"accepted",'
             '"boxEnrolled":false,"boxEnrollmentReason":"not_enrolled"}')
    os.environ["EWS_STATE_DIR"] = td
    os.environ["EWS_FLEET_DIR"] = os.path.join(td, "ews-fleet")
    os.environ["EWS_RESCUE_CHAT"] = "8888rescue-drill"
    os.environ["EWS_OPERATOR_CHAT"] = "9999op-drill"
    os.environ["FLEET_STANDING_BOX_SLUG"] = "box-rr015-operator-aggregator"
    F.cmd_ingest("box-dm-enroll", {"last_tick_ts": "2000-01-01T00:00:00+00:00", "by_severity": {}})
    F.cmd_cycle(sender=lambda *a: (True, "fake"), admission=cl["admit"])
    F.cmd_cycle(sender=lambda *a: (True, "fake"), admission=cl["admit"])
    check(len(posts) == 1, "dead-man enrollment miss posts exactly once", len(posts))
    with Ledger(td) as led:
        evs = [dict(r) for r in led.conn.execute(
            "SELECT * FROM events WHERE dedup_key='deadman|box-dm-enroll'").fetchall()]
    check(evs and evs[0]["ack_state"] == "escalated",
          "dead-man enrollment miss with a durable ticket stays ack-eligible",
          evs)
    clear_state()

# --------------------------------------------------------------------------
# clean up env and summarize
# --------------------------------------------------------------------------
clear_state()
if FAILS:
    print("RR-015 FAILURES: %s" % FAILS, file=sys.stderr)
    sys.exit(1)
print("RR-015: all checks pass")
sys.exit(0)
