"""Shared, fail-closed build and closeout verification (Python 3.9+)."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from workforce_state import update, read, atomic_write
from interview_eligibility import eligible_status

REQUIRED_CHECKS = ('registration', 'postBuild', 'qc', 'libraries')
CC_PHASES = ('commandCenterBuildFresh','commandCenterWorkspacesSeeded','commandCenterDepartmentsSynced',
             'commandCenterMdContentSynced','commandCenterDashboardContentSeeded','commandCenterDeptRuntimeParity','commandCenterTenantReady')

def artifact_digest(root):
    if not root or not Path(root).is_dir():
        return None
    digest=hashlib.sha256(); count=0
    for path in sorted(Path(root).rglob('*')):
        if path.is_file() and not path.is_symlink() and path.suffix in ('.md','.json'):
            digest.update(str(path.relative_to(root)).encode());digest.update(path.read_bytes());count+=1
    return digest.hexdigest() if count else None

def input_digest(state):
    keys=('companyId','companySlug','interviewComplete','interviewCompletedAt','confirmationsComplete','canonicalReconciliation','interviewAnswers','answers','interviewProgress')
    return hashlib.sha256(json.dumps({k:state.get(k) for k in keys},sort_keys=True).encode()).hexdigest()

def evaluate(state):
    missing=[];checks=state.get('buildChecks') or {};build_id=state.get('buildId')
    for check in REQUIRED_CHECKS:
        evidence=checks.get(check) or {}
        if not build_id or evidence.get('status')!='pass' or evidence.get('buildId')!=build_id:
            missing.append(check)
    if state.get('interviewComplete') is not True or not eligible_status((state.get('interviewQc') or {}).get('status')):missing.append('interview')
    for key in ('roleLibraryStatus','sopLibraryStatus'):
        if state.get(key)!='done':missing.append(key)
    if state.get('commsAutomationStatus') not in ('done','not-applicable'):missing.append('communications')
    depts=state.get('departments')
    if not isinstance(depts,list) or not depts or any(not isinstance(d,dict) or d.get('status') not in ('done',) for d in depts):missing.append('departments')
    if state.get('buildType')=='standard-first' and state.get('confirmationsComplete') is not True:missing.append('confirmations')
    evidence=state.get('buildArtifactVerification') or {}
    if evidence.get('inputDigest')!=input_digest(state):missing.append('changed-inputs')
    try:current=artifact_digest(evidence.get('root'))
    except OSError:current=None
    if not current or current!=evidence.get('digest'):missing.append('changed-or-missing-artifacts')
    return missing

def finalize(path,check_results=None,artifact_root=None):
    def mutate(state):
        now=datetime.now(timezone.utc).isoformat();state.setdefault('buildId',str(uuid.uuid4()))
        if check_results is not None:
            checks=state.setdefault('buildChecks',{})
            for name,rc in check_results.items():
                checks[name]={'status':'pass' if rc==0 else 'failed','returnCode':rc,'checkedAt':now,'buildId':state['buildId']}
            root=artifact_root or (state.get('buildArtifactVerification') or {}).get('root')
            state['buildArtifactVerification']={'root':str(root) if root else None,'digest':artifact_digest(root),'inputDigest':input_digest(state)}
        missing=evaluate(state)
        state['completionVerification']={'version':1,'buildId':state['buildId'],'companyId':state.get('companyId'),
                                         'status':'verified' if not missing else 'pending','checkedAt':now,'unmetRequirements':missing,'inputDigest':input_digest(state),'artifactDigest':(state.get('buildArtifactVerification') or {}).get('digest')}
        if missing:
            state.pop('buildCompletedAt',None)
            if state.get('closeoutStatus') in ('done','sent'):state['closeoutStatus']='partial'
        else:
            state.setdefault('buildCompletedAt',now)
            if state.get('closeoutStatus') not in ('generating','partial','sent','done'):state['closeoutStatus']='pending'
        return not missing
    result=update(path,mutate)
    # Resume completion also updates the exact company/build progress record.
    state=read(path);root=(state.get('buildArtifactVerification') or {}).get('root')
    if root:
        target=Path(root).parent/'build-progress.json'
        try:progress=json.loads(target.read_text()) if target.is_file() else {}
        except (ValueError,OSError):progress={}
        progress.update(stage='complete' if result else 'qc',company_slug=state.get('companySlug'),build_id=state.get('buildId'),
                        completion_verification=state['completionVerification'],updated_at=state['completionVerification']['checkedAt'],
                        message='Your workforce is verified.' if result else 'Required workforce checks are still pending.')
        if result:progress['completed_at']=state['buildCompletedAt']
        else:progress.pop('completed_at',None)
        atomic_write(target,progress)
    return result

def refresh(path):
    """Recheck old/failed builds without trusting historical stamps. Bounded subprocesses."""
    state=read(path);scripts=Path(__file__).parent
    env=dict(os.environ,WORKFORCE_BUILD_STATE_FILE=str(path),WORKFORCE_PYTHON=sys.executable)
    slug=state.get('companySlug') or state.get('clientSlug')
    if not slug:return finalize(path)
    env['OPENCLAW_COMPANY_SLUG']=slug
    commands={'registration':['bash',str(scripts/'verify-wiring.sh'),'--all'],
              'postBuild':[sys.executable,str(scripts/'post-build-role-workspaces.py'),'--company-slug',slug],
              'qc':['bash',str(scripts/'qc-completeness.sh'),'--quiet'],
              'libraries':['bash',str(scripts/'verify-library-gate.sh')]}
    results={}
    for name,command in commands.items():
        try:results[name]=subprocess.run(command,env=env,timeout=300).returncode
        except (OSError,subprocess.TimeoutExpired):results[name]=124
    root=(read(path).get('buildArtifactVerification') or {}).get('root')
    if not root:
        sys.path.insert(0,str(scripts.parent.parent/'shared-utils'))
        from detect_platform import get_openclaw_paths
        root=str(get_openclaw_paths()['company_root']/slug/'departments')
    return finalize(path,results,root)

def closeout_artifact_digest(state):
    keys=('infographic1Url','infographic2Url','celebrationVideoUrl','notionRootPageUrl','commandCenterUrl','messagesDelivered','ownerChat')
    return hashlib.sha256(json.dumps({k:state.get(k) for k in keys},sort_keys=True).encode()).hexdigest()

def finalize_closeout(path):
    def mutate(state):
        missing=evaluate(state)
        if state.get('commandCenterStatus')!='done' or any(state.get(k) is not True for k in CC_PHASES):missing.append('command-center')
        if state.get('qualityHeld'):missing.append('quality-held')
        for key in ('infographic1Url','infographic2Url','celebrationVideoUrl','notionRootPageUrl'):
            if not state.get(key):missing.append(key)
        delivery=state.get('telegramDeliveryVerification') or {}
        if (delivery.get('status')!='pass' or delivery.get('authority') not in ('gateway-json-registry','gateway-sqlite-plugin-state')
            or delivery.get('buildId')!=state.get('buildId')
            or delivery.get('artifactDigest')!=closeout_artifact_digest(state)
            or any(not any(r.get('n')==slot and r.get('verdict') in ('pass-present','pass-verified-receipt') and r.get('messageId') for r in delivery.get('results',[]) if isinstance(r,dict)) for slot in (1,6,7))):
            missing.append('delivery-unverified-or-stale')
        now=datetime.now(timezone.utc).isoformat()
        state['closeoutVerification']={'version':1,'buildId':state.get('buildId'),'status':'verified' if not missing else 'pending',
                                      'checkedAt':now,'unmetRequirements':missing}
        if missing:
            if state.get('closeoutStatus') in ('done','sent'):state['closeoutStatus']='partial'
            return False
        state.update(closeoutStatus='done',closeoutCompletedAt=now,closeoutPendingSlots=[],closeoutFailureReason=None)
        state.pop('closeoutCriticalFailed',None)
        state['closeoutCleanupPending']=True
        return True
    return update(path,mutate)

if __name__=='__main__':
    path=sys.argv[1]
    verified=finalize_closeout(path) if '--closeout' in sys.argv else refresh(path) if '--refresh' in sys.argv else finalize(path)
    print(json.dumps({'verified':verified}))
    sys.exit(0 if verified else 1)
