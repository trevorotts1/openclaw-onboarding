#!/usr/bin/env python3
"""Durable, receiver-owned Telegram notification sender for Rescue Rangers.

This deliberately has no knowledge of an agent reply.  A trusted receiver supplies
the origin and body, and this journal witnesses the gateway invocation itself.
"""
from __future__ import annotations
import argparse, fcntl, hashlib, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path

MAX_RETRIES = 3

def canon(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def now(): return time.time()

def private_dir(path):
    path.mkdir(parents=True, exist_ok=True); os.chmod(path, 0o700)

def atomic(path, value):
    private_dir(path.parent)
    fd, temp = tempfile.mkstemp(prefix=".new-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, sort_keys=True, separators=(",", ":")); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
        dfd=os.open(path.parent, os.O_RDONLY); os.fsync(dfd); os.close(dfd)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def path_for(root, op): return Path(root) / "operations" / (op + ".json")
def read(path):
    with path.open(encoding="utf-8") as f: return json.load(f)

def origin(value):
    if not isinstance(value, dict) or value.get("authorized") is not True or value.get("channel") != "telegram": raise ValueError("trusted origin must be authorized telegram origin")
    out={k:value[k] for k in ("channel","account","target") if isinstance(value.get(k),str) and value[k]}
    if len(out)!=3: raise ValueError("trusted origin needs account and target")
    for k in ("thread_id","reply_to"):
        if isinstance(value.get(k), (str,int)) and str(value[k]): out[k]=str(value[k])
    # Paths can be retained only as read-only corroboration metadata; they are
    # never used to accept an arbitrary receipt as delivery proof.
    for k in ("session_store","state_db"):
        if isinstance(value.get(k),str) and os.path.isabs(value[k]): out[k]=value[k]
    return out

def operation(args):
    try: trusted=origin(json.loads(args.origin_json))
    except (ValueError,json.JSONDecodeError) as e: raise SystemExit("invalid trusted origin: %s" % e)
    ids={k:getattr(args,k) for k in ("incident_id","instruction_id","attempt_id","attempt_generation","idempotency_key")}
    if not all(isinstance(v,str) and v for v in ids.values()) or not args.body: raise SystemExit("identity and body are required")
    op=digest("\0".join([*ids.values(), canon(trusted), args.body]))
    return op, {"schema":1,"operation_id":op,"identity":ids,"origin":trusted,"body":args.body,
                "body_digest":digest(args.body),"created_at":now(),"state":"pending","send_attempts":0,
                "next_retry_at":now(),"report_state":"pending"}

def enqueue(args):
    op, item=operation(args); p=path_for(args.state_dir,op)
    exists=p.exists()
    if exists: item=read(p)
    else: atomic(p,item)
    print(canon({"operation_id":item["operation_id"], "state":item["state"], "created":not exists}))

def message_id(value, origin):
    # Accept only the CLI's affirmative envelope, never a diagnostic/nested
    # historic receipt which happens to carry an id.
    if not isinstance(value,dict) or value.get("ok") is False or value.get("dry_run") is True: return None
    result=value.get("result",value)
    if not isinstance(result,dict) or result.get("ok") is False or result.get("dry_run") is True: return None
    mid=result.get("messageId",result.get("message_id"))
    if not isinstance(mid,(str,int)) or not str(mid): return None
    if result.get("channel") not in (None,"telegram"): return None
    if result.get("account") not in (None,origin["account"]): return None
    if result.get("target",result.get("chatId")) not in (None,origin["target"]): return None
    return str(mid)

def invoke(item, executable, timeout):
    o=item["origin"]; cmd=[executable,"message","send","--json","--channel","telegram","--account",o["account"],"--target",o["target"],"--message",item["body"]]
    if "thread_id" in o: cmd += ["--thread-id",o["thread_id"]]
    if "reply_to" in o: cmd += ["--reply-to",o["reply_to"]]
    started=now()
    try:
        r=subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return "unconfirmed", {"failure_reason":"send_timeout_ambiguous","started_at":started,"finished_at":now()}
    except OSError as e:
        return "failed", {"failure_reason":"exec_error","error":str(e),"started_at":started,"finished_at":now()}
    evidence={"exit_code":r.returncode,"stdout_digest":digest(r.stdout),"stderr_digest":digest(r.stderr),"started_at":started,"finished_at":now()}
    try: parsed=json.loads(r.stdout); mid=message_id(parsed,o)
    except (ValueError,TypeError): parsed=None; mid=None
    if r.returncode == 0 and mid:
        evidence.update({"gateway_response":parsed,"message_id":mid}); return "delivered", evidence
    evidence["failure_reason"]="gateway_response_missing_message_id" if r.returncode==0 else "gateway_exit_nonzero"
    return "failed", evidence

def public(item):
    o=item["origin"]; e=item.get("gateway_evidence",{})
    report_state={"delivered":"confirmed","unconfirmed":"pending","failed":"failed"}.get(item["state"],"pending")
    identity=dict(item["identity"]); identity["generation"]=identity.pop("attempt_generation")
    return {"action":"notification", **identity, "operation_id":item["operation_id"], "notification":{
      "status":report_state,"channel":"telegram","account":o["account"],"target":o["target"],
      "thread_id":o.get("thread_id"),"reply_to":o.get("reply_to"),"message_id":e.get("message_id"),"body_digest":item["body_digest"],"delivered_at":e.get("finished_at"),"failure_reason":e.get("failure_reason")}}

def tick(args):
    root=Path(args.state_dir)/"operations"; private_dir(root); out=[]; reports=[]
    lock=Path(args.state_dir)/"tick.lock"; private_dir(lock.parent)
    with lock.open("a+") as lockfile:
     os.chmod(lock,0o600)
     try: fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
     except BlockingIOError:
        print(canon({"operations":[],"pending_reports":[],"busy":True})); return
     sent=False
     for p in sorted(root.glob("*.json")):
        item=read(p)
        if item["state"] == "sending":
            item["state"]="unconfirmed"; item["gateway_evidence"]={"failure_reason":"crash_after_send_ambiguous","finished_at":now()}; atomic(p,item)
            if item.get("report_state") == "pending": reports.append(public(item))
            out.append(item); continue
        if item["state"] in ("delivered","unconfirmed"):
            if item.get("report_state") == "pending": reports.append(public(item))
            out.append(item); continue
        if item["state"] == "failed" and item["send_attempts"] >= args.max_retries:
            if item.get("report_state") == "pending": reports.append(public(item))
            out.append(item); continue
        if item.get("next_retry_at",0)>now() or sent: out.append(item); continue
        item["send_attempts"] += 1; item["state"]="sending"; item["send_started_at"]=now(); atomic(p,item)
        state,evidence=invoke(item,args.openclaw_bin,args.timeout_seconds)
        item["state"]=state; item["gateway_evidence"]=evidence
        if state=="failed" and item["send_attempts"]<args.max_retries: item["next_retry_at"]=now()+min(300,2**item["send_attempts"])
        atomic(p,item); out.append(item)
        sent=True
        if state in ("delivered","unconfirmed") or (state=="failed" and item["send_attempts"]>=args.max_retries): reports.append(public(item))
    print(canon({"operations":[{"operation_id":x["operation_id"],"state":x["state"],"send_attempts":x["send_attempts"],"next_retry_at":x.get("next_retry_at")} for x in out],"pending_reports":reports}))

def confirm(args):
    if not re.fullmatch(r"[0-9a-f]{64}",args.operation_id): raise SystemExit("invalid operation")
    p=path_for(args.state_dir,args.operation_id)
    if not p.exists(): raise SystemExit("unknown operation")
    item=read(p); item["report_state"]="confirmed"; item["report_confirmed_at"]=now(); atomic(p,item)
    print(canon({"operation_id":args.operation_id,"report_state":"confirmed"}))

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="command",required=True)
    e=sub.add_parser("enqueue"); e.add_argument("--state-dir",required=True); e.add_argument("--origin-json",required=True); e.add_argument("--incident-id",required=True); e.add_argument("--instruction-id",required=True); e.add_argument("--attempt-id",required=True); e.add_argument("--attempt-generation",required=True); e.add_argument("--idempotency-key",required=True); e.set_defaults(func=enqueue)
    t=sub.add_parser("tick"); t.add_argument("--state-dir",required=True); t.add_argument("--openclaw-bin",required=True); t.add_argument("--timeout-seconds",type=float,default=15); t.add_argument("--max-retries",type=int,default=MAX_RETRIES); t.set_defaults(func=tick)
    c=sub.add_parser("report-confirm"); c.add_argument("--state-dir",required=True); c.add_argument("--operation-id",required=True); c.set_defaults(func=confirm)
    args=ap.parse_args()
    # Notification text is deliberately stdin only: it must not be exposed in
    # process listings or command logs while a poll is running.
    if args.command == "enqueue": args.body=sys.stdin.read()
    args.func(args)
if __name__ == "__main__": main()
