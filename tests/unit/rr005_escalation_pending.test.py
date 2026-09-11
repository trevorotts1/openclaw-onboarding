#!/usr/bin/env python3
# RR-005 — failed EWS escalations stay pending (ONB Skill 60).
# Battery: rerun-failure / no-target / dryrun / lost-response recovery /
# malformed-200 / 401 / 429 / timeout never consume the alert.
# Hermetic: injected admission stubs + transports; tmp state dirs only.
import json, os, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPTS = os.path.join(REPO, "60-zhc-early-warning-system", "scripts")
sys.path.insert(0, SCRIPTS)
import ews_alert as A
import ews_common as C
from ews_ledger import Ledger
FAILS = []
def check(c, n, d=""):
    print(("  ok " if c else "  FAIL ")+n+("" if c else " :: "+str(d)[:220]))
    if not c: FAILS.append(n)
print("== RR-005 ONB: failed escalations stay pending ==")
os.environ["EWS_BOX_NAME"]="rr005-box"; os.environ["FLEET_STANDING_BOX_SLUG"]="box-rr005"
os.environ["EWS_RESCUE_CHAT"]="8888r"; os.environ["EWS_OPERATOR_CHAT"]="9999o"

def stub(status="admitted", ticket="T-1", detail="x", calls=None, op=None):
    def admit(state_dir=None, box="", problem_text="", **kw):
        if calls is not None: calls.append(dict(kw, box=box))
        return {"status":status,"operation_id":op or "op-fixture","ticket_id":ticket,
                "admission_schema":"v1","detail":detail,"reply_digest":"d9"}
    return admit

# 1. rerun failure: failed attempt keeps event OPEN + retry row, second run resends same op
with tempfile.TemporaryDirectory(prefix="rr005-1-") as td:
    with Ledger(td) as led:
        eid=led.record_event("S6","P1","c","config","rerun",tick_ts="2000-01-01T00:00:00+00:00")
    e1=A.escalate(td,sender=lambda *a:(True,"x"),admission=stub("failed",None,"boom"))
    with Ledger(td) as led:
        st=led.conn.execute("SELECT ack_state FROM events WHERE event_id=?",(eid,)).fetchone()[0]
        ops=[dict(r) for r in led.conn.execute("SELECT * FROM escalation_state").fetchall()]
    check(st=="open","1 rerun-failure leaves event OPEN",st)
    check(any(i["event_id"]==eid and i["outcome"]=="attempted" for i in e1),"1 outcome attempted",e1)
    check(len(ops)==1 and ops[0]["attempt"]==1 and ops[0]["next_attempt_at"] and ops[0]["last_error"],"1 escalation row: attempt+next_attempt_at+last_error",ops)
    check(A.escalate_exit_code(e1)==1,"1 nonzero exit on operational failure")
    e1b=A.escalate(td,sender=lambda *a:(True,"x"),admission=stub("admitted","T-R","ok"))
    with Ledger(td) as led:
        st2=led.conn.execute("SELECT ack_state FROM events WHERE event_id=?",(eid,)).fetchone()[0]
        op2=led.get_escalation(ops[0]["operation_id"])
    check(st2=="escalated","1 retry reconciles stable op then accepts",st2)
    check(op2["attempt"]==2 and op2["outcome"]=="accepted" and op2["receipt_ticket_id"]=="T-R","1 same op accepted on retry, receipt stored",op2)

# 2. no-target: missing operator target still escalates via admission; event retryable on failure
with tempfile.TemporaryDirectory(prefix="rr005-2-") as td:
    for k in ("EWS_OPERATOR_CHAT","OPERATOR_TELEGRAM_CHAT_ID","FOUNDER_TELEGRAM_CHAT_ID"): os.environ.pop(k,None)
    f={"signal":"S6","severity":"P1","key_path":"c","class":"config","detail":"nt","dedup_key":"nt-1"}
    A.route_finding(f,td,sender=lambda *a:(True,"x"))
    with Ledger(td) as led:
        eid=led.record_event("S6","P1","c","config","nt2",tick_ts="2000-01-01T00:00:00+00:00")
    e2=A.escalate(td,sender=lambda *a:(True,"x"),admission=stub("failed",None,"down"))
    with Ledger(td) as led:
        st=led.conn.execute("SELECT ack_state FROM events WHERE event_id=?",(eid,)).fetchone()[0]
    check(st=="open","2 no-target source alert stays retryable",st)
    check(any(i["outcome"]=="attempted" for i in e2),"2 outcome attempted",e2)
    os.environ["EWS_OPERATOR_CHAT"]="9999o"

# 3. dryrun: zero mutations, zero network
with tempfile.TemporaryDirectory(prefix="rr005-3-") as td:
    posts=[]
    def adm(**k):
        posts.append(k); return {"status":"admitted","operation_id":"o","ticket_id":"T","admission_schema":"v1","detail":"x","reply_digest":"d"}
    with Ledger(td) as led:
        eid=led.record_event("S6","P1","c","config","dr",tick_ts="2000-01-01T00:00:00+00:00")
        be=led.conn.execute("SELECT COUNT(*) n FROM events").fetchone()["n"]; bj=led.count_admissions()
        bd=led.conn.execute("SELECT COUNT(*) n FROM digests").fetchone()["n"]
        be2=led.conn.execute("SELECT COUNT(*) n FROM escalation_state").fetchone()["n"]
    e3=A.escalate(td,sender=lambda *a:(posts.append("SEND"),(True,"x")[1]),admission=adm,dry_run=True)
    with Ledger(td) as led:
        ae=led.conn.execute("SELECT COUNT(*) n FROM events").fetchone()["n"]; aj=led.count_admissions()
        ad=led.conn.execute("SELECT COUNT(*) n FROM digests").fetchone()["n"]
        ae2=led.conn.execute("SELECT COUNT(*) n FROM escalation_state").fetchone()["n"]
        st=led.conn.execute("SELECT ack_state FROM events WHERE event_id=?",(eid,)).fetchone()[0]
    check(posts==[],"3 dryrun: no network",posts)
    check((ae,aj,ad,ae2)==(be,bj,bd,be2),"3 dryrun: no state change")
    check(any(i["outcome"]=="dry_run" and i["admission_status"]=="dry_run" for i in e3),"3 outcome dry_run",e3)
    check(st=="open","3 dryrun leaves OPEN",st)
    check(A.escalate_exit_code(e3)==0,"3 dryrun exit 0")

# 4. response lost after real admission recovers SAME ticket via stable op
with tempfile.TemporaryDirectory(prefix="rr005-4-") as td:
    client=C.load_rescue_admission(); assert client is not None
    posts=[]
    def flaky(url, body, timeout=None):
        posts.append(json.loads(body.decode()))
        if len(posts)==1: raise client.AdmissionTransportError("response lost (fixture)")
        return '{"accepted":true,"ticketId":"T-REC"}'
    def fc(state_dir=None, box="", problem_text="", **kw):
        return client.admit(state_dir,box=box,problem_text=problem_text,source=kw.get("source","skill-60-ews"),
            signal=kw.get("signal",""),key_path=kw.get("key_path",""),dedup_key=kw.get("dedup_key",""),
            event_id=kw.get("event_id"),tick_ts=kw.get("tick_ts",""),transport=flaky,url="https://intake.invalid/x")
    with Ledger(td) as led:
        eid=led.record_event("S6","P1","c","config","rec",tick_ts="2000-01-01T00:00:00+00:00")
    A.escalate(td,sender=lambda *a:(True,"x"),admission=fc)
    e4=A.escalate(td,sender=lambda *a:(True,"x"),admission=fc)
    check(len(posts)==2 and posts[0]["operation_id"]==posts[1]["operation_id"],"4 recovery reuses stable operation id")
    with Ledger(td) as led:
        st=led.conn.execute("SELECT ack_state FROM events WHERE event_id=?",(eid,)).fetchone()[0]
        row=led.get_escalation(posts[0]["operation_id"])
    check(st=="escalated","4 recovered same event",st)
    check(row and row["outcome"]=="accepted" and row["receipt_ticket_id"]=="T-REC","4 same ticket on op row",row)

# 5. malformed 200 / 401 / 429 / timeout never consume
with tempfile.TemporaryDirectory(prefix="rr005-5-") as td:
    client=C.load_rescue_admission()
    os.environ[client.SECRET_ENV]="fixture-shared-secret-not-a-real-value"
    kinds=[("malformed200",None,'<html>502</html>'),("401",client.AdmissionRefused,'intake HTTP 401: missing message'),
           ("429",client.AdmissionTransportError,'intake HTTP 429: slow'),("timeout",client.AdmissionTransportError,'TimeoutError: t')]
    for name,cls,body in kinds:
        posts=[]
        def tx(url, b, timeout=None, _c=cls, _b=body):
            posts.append(1)
            if _c: raise _c(_b)
            return _b
        def ac(state_dir=None, box="", problem_text="", **kw):
            return client.admit(state_dir,box=box,problem_text=problem_text,source="skill-60-ews",signal="S6",
                key_path="c",dedup_key="k-"+name,event_id=kw.get("event_id"),tick_ts="",transport=tx,url="https://intake.invalid/x")
        with Ledger(td) as led:
            eid=led.record_event("S6","P1","c","config","m-"+name,tick_ts="2000-01-01T00:00:00+00:00",dedup_key="k-"+name)
        esc=A.escalate(td,sender=lambda *a:(True,"x"),admission=ac)
        with Ledger(td) as led:
            st=led.conn.execute("SELECT ack_state FROM events WHERE event_id=?",(eid,)).fetchone()[0]
        it=[i for i in esc if i["event_id"]==eid]
        check(st=="open","5 %s never consumes"%name,st)
        check(bool(it) and it[0]["outcome"] in ("attempted","failed"),"5 %s outcome attempted/failed"%name,it)

    os.environ.pop(client.SECRET_ENV,None)
# 6. missing config = owned deferred setup fault
with tempfile.TemporaryDirectory(prefix="rr005-6-") as td:
    with Ledger(td) as led:
        eid=led.record_event("S6","P1","c","config","mc",tick_ts="2000-01-01T00:00:00+00:00")
        real=C.load_rescue_admission
        C.load_rescue_admission=lambda *a,**k: None
        try: e6=A.escalate(td,sender=lambda *a:(True,"x"),admission=None)
        finally: C.load_rescue_admission=real
        st=led.conn.execute("SELECT ack_state FROM events WHERE event_id=?",(eid,)).fetchone()[0]
        op=[dict(r) for r in led.conn.execute("SELECT * FROM escalation_state").fetchall()]
    check(st=="open","6 missing config stays OPEN",st)
    check(any(i["outcome"]=="deferred" and i["admission_status"]=="client_unavailable" for i in e6),"6 outcome deferred/client_unavailable",e6)
    check(len(op)==1 and op[0]["last_error"],"6 owned setup fault recorded",op)
    check(A.escalate_exit_code(e6)==0,"6 deferred exit 0")

# 7. policy refusal = failed, never accepted
with tempfile.TemporaryDirectory(prefix="rr005-7-") as td:
    e7=A.escalate.__globals__ and None
    with Ledger(td) as led:
        eid=led.record_event("S6","P1","c","config","pr",tick_ts="2000-01-01T00:00:00+00:00")
    esc=A.escalate(td,sender=lambda *a:(True,"x"),admission=stub("refused",None,"policy no"))
    with Ledger(td) as led:
        st=led.conn.execute("SELECT ack_state FROM events WHERE event_id=?",(eid,)).fetchone()[0]
    check(st=="open","7 refusal stays OPEN",st)
    check(any(i["event_id"]==eid and i["outcome"]=="failed" for i in esc),"7 outcome failed",esc)
    check(A.escalate_exit_code(esc)==1,"7 nonzero exit on refusal")

for k in ("EWS_BOX_NAME","FLEET_STANDING_BOX_SLUG","EWS_RESCUE_CHAT","EWS_OPERATOR_CHAT"): os.environ.pop(k,None)
print("RR-005 FAILS=%d"%len(FAILS))
sys.exit(1 if FAILS else 0)
