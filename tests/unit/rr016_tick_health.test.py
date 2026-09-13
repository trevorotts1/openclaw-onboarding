#!/usr/bin/env python3
# RR-016 — dead sentinel detected even when old file readable (ONB Skill 60).
# Battery: old digest stays stale through successful collections; fresh
# advancing ticks healthy; collector outage / sentinel-only outage / reboot /
# malformed / future skew / rapid cycles; one incident per stale episode.
# Hermetic: tmp fleet/state dirs, injected admission stub, no network.
import os, sys, tempfile
sys.dont_write_bytecode = True
HERE=os.path.dirname(os.path.abspath(__file__))
REPO=os.path.abspath(os.path.join(HERE,"..",".."))
SCRIPTS=os.path.join(REPO,"60-zhc-early-warning-system","scripts")
sys.path.insert(0,SCRIPTS)
import ews_fleet as F
from ews_ledger import Ledger
from datetime import datetime, timedelta, timezone
FAILS=[]
def check(c,n,d=""):
    print(("  ok " if c else "  FAIL ")+n+("" if c else " :: "+str(d)[:220]))
    if not c: FAILS.append(n)
print("== RR-016 ONB: tick-age health, not collection time ==")
def fresh_iso(dt=None):
    return (dt or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
def ctx(td):
    os.environ["EWS_STATE_DIR"]=td; os.environ["EWS_FLEET_DIR"]=td+"/ews-fleet"
    os.environ["EWS_RESCUE_CHAT"]="8888r"; os.environ["EWS_OPERATOR_CHAT"]="9999o"
def unctx():
    for k in ("EWS_STATE_DIR","EWS_FLEET_DIR","EWS_RESCUE_CHAT","EWS_OPERATOR_CHAT"): os.environ.pop(k,None)
def adm(calls, status="admitted", ticket="T-DM"):
    def fn(state_dir=None, box="", problem_text="", **kw):
        calls.append(box)
        return {"status":status,"operation_id":"op-dm","ticket_id":ticket if status in ("admitted","replay") else None,
                "admission_schema":"v1","detail":"dm","reply_digest":"d"}
    return fn
ANCIENT="2000-01-01T00:00:00+00:00"

# 1. old digest stays stale through successful collections
with tempfile.TemporaryDirectory(prefix="rr016-1-") as td:
    ctx(td); calls=[]
    F.cmd_ingest("b-stale",{"last_tick_ts":ANCIENT,"by_severity":{}})
    for _ in range(3):
        F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
        F.cmd_ingest("b-stale",{"last_tick_ts":ANCIENT,"by_severity":{}})
    res=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-stale" in res["sentinel_dark"],"1 stale through collections")
    with Ledger(td) as led:
        evs=[dict(r) for r in led.conn.execute("SELECT * FROM events WHERE dedup_key LIKE 'deadman|b-stale%'").fetchall()]
    check(len(evs)==1,"1 one incident per stale episode",len(evs))
    check(len(calls)==1,"1 one admission post per episode",len(calls))
    unctx()

# 2. fresh advancing ticks stay healthy
with tempfile.TemporaryDirectory(prefix="rr016-2-") as td:
    ctx(td); calls=[]
    F.cmd_ingest("b-fresh",{"last_tick_ts":fresh_iso(),"by_severity":{}})
    for i in range(3):
        F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
        F.cmd_ingest("b-fresh",{"last_tick_ts":fresh_iso(datetime.now(timezone.utc)+timedelta(seconds=i+1)),"by_severity":{}})
    res=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-fresh" not in res["sentinel_dark"],"2 fresh advancing healthy")
    check(calls==[],"2 no admission for healthy box",calls)
    unctx()

# 3. collector outage: collector silent for a full horizon with an aging
# tick -> stale/dark (backdate both stamps; cycles run instantly in test).
with tempfile.TemporaryDirectory(prefix="rr016-3-") as td:
    ctx(td); calls=[]
    old=fresh_iso(datetime.now(timezone.utc)-timedelta(hours=5))
    F.cmd_ingest("b-coll",{"last_tick_ts":old,"by_severity":{}})
    import json as _j
    bf=F._box_file("b-coll"); rec=_j.loads(open(bf).read())
    rec["collector_seen_at"]=old; rec["sentinel_tick_at"]=old
    rec["last_verified_progress_at"]=old
    open(bf,"w").write(_j.dumps(rec))
    res=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-coll" in res["sentinel_dark"],"3 collector outage dark",res)
    unctx()

# 4. sentinel-only outage: collector reads succeed, tick frozen -> dark
with tempfile.TemporaryDirectory(prefix="rr016-4-") as td:
    ctx(td); calls=[]
    t0=fresh_iso(datetime.now(timezone.utc)-timedelta(hours=5))
    F.cmd_ingest("b-sentinel",{"last_tick_ts":t0,"by_severity":{}})
    for _ in range(2):
        F.cmd_ingest("b-sentinel",{"last_tick_ts":t0,"by_severity":{}})
        F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    res=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-sentinel" in res["sentinel_dark"],"4 sentinel-only outage dark")
    bf=F._box_file("b-sentinel")
    import json; rec=json.loads(open(bf).read())
    check(rec.get("collector_seen_at")!=rec.get("sentinel_tick_at"),"4 collector vs tick separated")
    unctx()

# 5. reboot: boot id change -> DEGRADED (not healthy), recoverable with new tick
with tempfile.TemporaryDirectory(prefix="rr016-5-") as td:
    ctx(td); calls=[]
    F.cmd_ingest("b-reboot",{"last_tick_ts":fresh_iso(),"boot_id":"boot-A","tick_seq":10,"by_severity":{}})
    F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    F.cmd_ingest("b-reboot",{"last_tick_ts":fresh_iso(),"boot_id":"boot-B","tick_seq":1,"by_severity":{}})
    res=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-reboot" in res["sentinel_dark"],"5 reboot degraded, not healthy")
    F.cmd_ingest("b-reboot",{"last_tick_ts":fresh_iso(datetime.now(timezone.utc)+timedelta(seconds=30)),"boot_id":"boot-B","tick_seq":2,"by_severity":{}})
    unctx()

# 6. malformed timestamp -> UNKNOWN/dark, recoverable
with tempfile.TemporaryDirectory(prefix="rr016-6-") as td:
    ctx(td); calls=[]
    F.cmd_ingest("b-mal",{"last_tick_ts":"not-a-time","by_severity":{}})
    res=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-mal" in res["sentinel_dark"],"6 malformed dark/unknown")
    F.cmd_ingest("b-mal",{"last_tick_ts":fresh_iso(),"by_severity":{}})
    res2=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-mal" not in res2["sentinel_dark"],"6 recovery needs new verified tick",res2)
    unctx()

# 7. future skew -> DEGRADED/dark
with tempfile.TemporaryDirectory(prefix="rr016-7-") as td:
    ctx(td); calls=[]
    fut=fresh_iso(datetime.now(timezone.utc)+timedelta(hours=2))
    F.cmd_ingest("b-fut",{"last_tick_ts":fut,"by_severity":{}})
    res=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-fut" in res["sentinel_dark"],"7 future skew dark/degraded")
    unctx()

# 8. rapid cycles: many cycles, one episode, recoverable
with tempfile.TemporaryDirectory(prefix="rr016-8-") as td:
    ctx(td); calls=[]
    F.cmd_ingest("b-rapid",{"last_tick_ts":ANCIENT,"by_severity":{}})
    for _ in range(6):
        F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    with Ledger(td) as led:
        evs=[dict(r) for r in led.conn.execute("SELECT * FROM events WHERE dedup_key LIKE 'deadman|b-rapid%'").fetchall()]
    check(len(evs)==1,"8 rapid cycles one incident",len(evs))
    F.cmd_ingest("b-rapid",{"last_tick_ts":fresh_iso(),"by_severity":{}})
    res=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-rapid" not in res["sentinel_dark"],"8 recoverable with new tick",res)
    unctx()

# 9. missing tick -> UNKNOWN/dark
with tempfile.TemporaryDirectory(prefix="rr016-9-") as td:
    ctx(td); calls=[]
    F.cmd_ingest("b-miss",{"by_severity":{}})
    res=F.cmd_cycle(sender=lambda *a:(True,"x"),admission=adm(calls))
    check("b-miss" in res["sentinel_dark"],"9 missing tick dark/unknown")
    unctx()

print("RR-016 FAILS=%d"%len(FAILS))
sys.exit(1 if FAILS else 0)
