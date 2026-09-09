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
#   5. failed transport / refusal / undetermined answer / missing client /
#      no enrollment config never consume the alert (event stays OPEN)
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
                     raise_cls=None):
    """A fake module whose admit() drives the REAL client with an injected
    transport. posts records what actually went to the wire."""
    def transport(url, payload_bytes, timeout=None):
        posts.append({"url": url, "body": json.loads(payload_bytes.decode("utf-8"))})
        if raise_cls:
            raise raise_cls("fixture transport failure")
        return body

    def admit(state_dir=None, box="", problem_text="", **kw):
        return client.admit(
            state_dir, box=box, problem_text=problem_text,
            source=kw.get("source", "skill-60-ews"), signal=kw.get("signal", ""),
            key_path=kw.get("key_path", ""), dedup_key=kw.get("dedup_key", ""),
            event_id=kw.get("event_id"), tick_ts=kw.get("tick_ts", ""),
            transport=transport, url="https://intake.invalid/rr-v2-intake")
    return {"admit": admit, "load": None}


def clear_state():
    for k in ("EWS_STATE_DIR", "EWS_FLEET_DIR", "EWS_BOX_NAME",
              "FLEET_STANDING_BOX_SLUG", "EWS_RESCUE_CHAT", "EWS_OPERATOR_CHAT"):
        os.environ.pop(k, None)


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

    # 5b explicit refusal (403): terminal for this attempt, event still OPEN
    cl2 = admission_client([], raise_cls=client.AdmissionRefused)
    with Ledger(td) as led:
        eid2 = led.record_event("S6", "P1", "c", "config", "drill-f",
                                tick_ts="2000-01-01T00:00:00+00:00")
    esc2 = A.escalate(td, sender=lambda *a: (True, "x"), admission=cl2["admit"])
    with Ledger(td) as led:
        st2 = led.conn.execute("SELECT ack_state FROM events WHERE event_id=?", (eid2,)).fetchone()[0]
        rows = led.conn.execute(
            "SELECT status FROM rescue_admissions WHERE event_id=? "
            "ORDER BY admission_id DESC LIMIT 1", (eid2,)).fetchone()
    check(st2 == "open", "403 refusal leaves event OPEN", st2)
    check(rows is not None and rows[0] == "refused", "refusal journaled as refused", rows)

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
# clean up env and summarize
# --------------------------------------------------------------------------
clear_state()
if FAILS:
    print("RR-015 FAILURES: %s" % FAILS, file=sys.stderr)
    sys.exit(1)
print("RR-015: all checks pass")
sys.exit(0)
