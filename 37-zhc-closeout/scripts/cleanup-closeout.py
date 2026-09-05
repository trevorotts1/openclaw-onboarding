#!/usr/bin/env python3
"""Retry recorded cleanup after verified completion; retain the recovery cron last."""
from __future__ import annotations
from pathlib import Path
import subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'23-ai-workforce-blueprint/scripts'))
from workforce_state import read,update

def cleanup_records(path,remove):
    failures=[]
    # Keep the recovery scheduler until all other recorded cleanup succeeds.
    for key,registered,pending in [('interviewNudgeUuid','interviewNudgeRegisteredAt','interviewNudgeCleanupPending'),('closeoutResumeUuid','closeoutResumeRegisteredAt','closeoutCleanupPending')]:
        state=read(path);identity=state.get(key)
        if key=='closeoutResumeUuid' and failures:break
        if not identity:
            if state.get(pending) is True and key=='interviewNudgeUuid':failures.append(key+': identity missing')
            continue
        try:removed=remove(identity)
        except Exception:removed=False
        if removed:
            def clear(current):
                if current.get(key)!=identity:raise ValueError('cleanup identity changed')
                current.pop(key,None);current[registered]=None;current[pending]=False
            update(path,clear)
        else:
            failures.append(key)
            update(path,lambda current:current.update({pending:True}))
    update(path,lambda current:current.update(closeoutCleanupPending=bool(failures),closeoutCleanupFailures=failures))
    return not failures

def main():
    from workforce_completion import finalize_closeout
    path=sys.argv[1]
    if not finalize_closeout(path):return 1
    def remove(identity):
        return subprocess.run(['openclaw','cron','rm',identity],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20).returncode==0
    return 0 if cleanup_records(path,remove) else 1
if __name__=='__main__':raise SystemExit(main())
