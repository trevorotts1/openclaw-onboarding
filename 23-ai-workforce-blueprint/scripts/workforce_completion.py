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
# BU-57 (decision D-7): the presentation runtime is NOT a required check. It is
# probed separately (qc-completeness.sh --deps-only) and recorded, never enforced:
# missing presentation tools are a closeout blocker, not a reason to keep the
# whole company unbuilt.
PRESENTATION_DEPS_CLASS = 'presentation-tools-missing'
DEPS_ONLY_TIMEOUT = 120

def probe_presentation_deps(scripts, env=None):
    """Run only the presentation-dependency block: 0 present, 6 missing, 124 could not run."""
    probe_env = dict(env if env is not None else os.environ)
    probe_env.pop('QC_SKIP_PRESENTATION_DEPS', None)
    try:
        return subprocess.run(['bash', str(scripts / 'qc-completeness.sh'), '--deps-only'],
                              env=probe_env, timeout=DEPS_ONLY_TIMEOUT).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 124
CC_PHASES = ('commandCenterBuildFresh','commandCenterWorkspacesSeeded','commandCenterDepartmentsSynced',
             'commandCenterMdContentSynced','commandCenterDashboardContentSeeded','commandCenterDeptRuntimeParity','commandCenterTenantReady')

class UnownedBuildState(ValueError):
    pass

def has_build_identity(state):
    # Legacy builds may have only their client slug; preserve that existing
    # identity. Operational failure/verification metadata is never ownership.
    return any(isinstance(state.get(key),str) and state[key].strip() not in ('','default')
               for key in ('companyId','companySlug','clientSlug'))

def require_build_identity(state):
    if not has_build_identity(state):
        raise UnownedBuildState('No client build identity exists; complete onboarding intake before build/closeout verification')

# Department subdirectories that are RUNTIME or TOOLING, not build artifacts:
# written after finalize by the workforce itself (presentations/runs/*.json is
# rewritten every few minutes by the scheduler; memory/, conversational-logs/,
# logs/ and artifacts/ by normal work) or re-synced by every update roll
# (scripts/, intake/, fish-audio/, ...). Hashing them made evaluate() report
# changed-or-missing-artifacts minutes after finalize. These are the runtime
# names in verify-wiring.sh NON_ROLE_DIR_NAMES; its content containers (sops/,
# roles/, devils-advocate/, templates/, assets/) stay in the digest.
DEPT_RUNTIME_DIRS=frozenset({'memory','conversational-logs','logs','artifacts','runs','scripts',
                             'intake','fish-audio','release-matrix','contract'})
# v1 hashed every .md/.json under the tree. Evidence recorded without a
# digestVersion is re-checked with v1, so no already-verified build flips on update.
# v3 additionally skips the workforce's own memory/instruction files at any depth:
# the agent rewrites them as it works, and they are state, not build artifacts.
DIGEST_VERSION=3
RUNTIME_FILE_NAMES=frozenset({'MEMORY.md','HEARTBEAT.md','AGENTS.md','TOOLS.md','USER.md','persona-matrix.md','dept-default-models.json'})

def artifact_digest(root,version=DIGEST_VERSION):
    if not root or not Path(root).is_dir():
        return None
    digest=hashlib.sha256(); count=0
    for path in sorted(Path(root).rglob('*')):
        if path.is_file() and not path.is_symlink() and path.suffix in ('.md','.json'):
            rel=path.relative_to(root)
            if version>=2 and len(rel.parts)>2 and rel.parts[1].lower() in DEPT_RUNTIME_DIRS:continue
            if version>=3 and path.name in RUNTIME_FILE_NAMES:continue
            digest.update(str(rel).encode());digest.update(path.read_bytes());count+=1
    return digest.hexdigest() if count else None

# v1 hashed whole canonicalReconciliation and interviewProgress objects, so a
# reconcile timestamp or a late progress stamp un-verified a finished build.
# v2 hashes only the owner's decisions, the chosen departments and the merge
# decisions, and drops interviewProgress. Evidence without inputDigestVersion is
# re-checked with v1, so an already-verified build does not flip on update.
INPUT_DIGEST_VERSION=2
INPUT_DIGEST_V1_KEYS=('companyId','companySlug','interviewComplete','interviewCompletedAt','confirmationsComplete','canonicalReconciliation','interviewAnswers','answers','interviewProgress')

def input_digest(state,version=INPUT_DIGEST_VERSION):
    if version>=2:
        canonical=state.get('canonicalReconciliation')
        canonical=canonical if isinstance(canonical,dict) else {}
        chosen=canonical.get('chosenDepartments')
        chosen=chosen.get('slugs') if isinstance(chosen,dict) else None
        payload={'companyId':state.get('companyId'),'companySlug':state.get('companySlug'),
                 'interviewComplete':state.get('interviewComplete'),'interviewCompletedAt':state.get('interviewCompletedAt'),
                 'confirmationsComplete':state.get('confirmationsComplete'),'interviewAnswers':state.get('interviewAnswers'),
                 'answers':state.get('answers'),
                 'canonicalReconciliation':{'decisions':canonical.get('decisions'),'chosen':chosen,'mergeDecisions':canonical.get('mergeDecisions')}}
    else:
        payload={k:state.get(k) for k in INPUT_DIGEST_V1_KEYS}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

def evaluate(state):
    missing=[];checks=state.get('buildChecks') or {};build_id=state.get('buildId')
    for check in REQUIRED_CHECKS:
        evidence=checks.get(check) or {}
        if not build_id or evidence.get('status')!='pass' or evidence.get('buildId')!=build_id:
            missing.append(check)
    if state.get('interviewComplete') is not True or not eligible_status((state.get('interviewQc') or {}).get('status')):missing.append('interview')
    for key in ('roleLibraryStatus','sopLibraryStatus'):
        if state.get(key)!='done':missing.append(key)
    if state.get('commsAutomationStatus') not in ('done','not-applicable','deferred'):missing.append('communications')
    depts=state.get('departments')
    if not isinstance(depts,list) or not depts or any(not isinstance(d,dict) or d.get('status') not in ('done',) for d in depts):missing.append('departments')
    if state.get('buildType')=='standard-first' and state.get('confirmationsComplete') is not True:missing.append('confirmations')
    evidence=state.get('buildArtifactVerification') or {}
    if evidence.get('inputDigest')!=input_digest(state,evidence.get('inputDigestVersion',1)):missing.append('changed-inputs')
    try:current=artifact_digest(evidence.get('root'),evidence.get('digestVersion',1))
    except OSError:current=None
    if not current or current!=evidence.get('digest'):missing.append('changed-or-missing-artifacts')
    return missing

def finalize(path,check_results=None,artifact_root=None,presentation_deps=None):
    def mutate(state):
        require_build_identity(state)
        now=datetime.now(timezone.utc).isoformat();state.setdefault('buildId',str(uuid.uuid4()))
        if check_results is not None:
            checks=state.setdefault('buildChecks',{})
            for name,rc in check_results.items():
                checks[name]={'status':'pass' if rc==0 else 'failed','returnCode':rc,'checkedAt':now,'buildId':state['buildId']}
            root=artifact_root or (state.get('buildArtifactVerification') or {}).get('root')
            state['buildArtifactVerification']={'root':str(root) if root else None,'digest':artifact_digest(root),'digestVersion':DIGEST_VERSION,'inputDigest':input_digest(state),'inputDigestVersion':INPUT_DIGEST_VERSION}
        if presentation_deps is not None:
            # BU-57: record the non-required probe as a plain integer result, and
            # carry a missing presentation runtime as a closeout blocker instead
            # of failing a required check.
            state.setdefault('buildChecks',{})['presentationDeps']=presentation_deps
            blockers=[b for b in (state.get('closeoutBlockers') or [])
                      if not (isinstance(b,dict) and b.get('class')==PRESENTATION_DEPS_CLASS)]
            if presentation_deps==6:
                blockers.append({'class':PRESENTATION_DEPS_CLASS,'returnCode':6,'recordedAt':now,
                                 'detail':'presentation runtime tools are missing (qc-completeness.sh --deps-only exited 6); closeout cannot render the presentation artifacts until they are installed'})
            if blockers:state['closeoutBlockers']=blockers
            else:state.pop('closeoutBlockers',None)
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
    try:result=update(path,mutate)
    except UnownedBuildState:return False
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
    if not has_build_identity(state):return False
    env=dict(os.environ,WORKFORCE_BUILD_STATE_FILE=str(path),WORKFORCE_PYTHON=sys.executable)
    slug=state.get('companySlug') or state.get('clientSlug')
    if not slug:return finalize(path)
    env['OPENCLAW_COMPANY_SLUG']=slug
    qc_env=dict(env,QC_SKIP_PRESENTATION_DEPS='1')
    commands={'registration':['bash',str(scripts/'verify-wiring.sh'),'--all'],
              'postBuild':[sys.executable,str(scripts/'post-build-role-workspaces.py'),'--company-slug',slug],
              'qc':['bash',str(scripts/'qc-completeness.sh'),'--quiet'],
              'libraries':['bash',str(scripts/'verify-library-gate.sh')]}
    results={}
    for name,command in commands.items():
        try:results[name]=subprocess.run(command,env=(qc_env if name=='qc' else env),timeout=300).returncode
        except (OSError,subprocess.TimeoutExpired):results[name]=124
    deps_rc=probe_presentation_deps(scripts,env)
    root=(read(path).get('buildArtifactVerification') or {}).get('root')
    if not root:
        sys.path.insert(0,str(scripts.parent.parent/'shared-utils'))
        from detect_platform import get_openclaw_paths
        root=str(get_openclaw_paths()['company_root']/slug/'departments')
    return finalize(path,results,root,presentation_deps=deps_rc)

def closeout_artifact_digest(state):
    keys=('infographic1Url','infographic2Url','celebrationVideoUrl','notionRootPageUrl','commandCenterUrl','messagesDelivered','ownerChat')
    return hashlib.sha256(json.dumps({k:state.get(k) for k in keys},sort_keys=True).encode()).hexdigest()

# A closeout is done when the owner has what was delivered. The Notion tree and
# the celebration video are the two legs an owner may never be able to receive (a
# client that never shares a page with the integration; a vendor that keeps
# failing). Those legs are WAIVED and reported instead of blocking the closeout
# forever (decision D-8). Everything else (infographics, delivery confirmation,
# command center) is still required.
CLOSEOUT_LEGS=('notion','celebration-video')
NOTION_WAIVED_PREFIXES=('failed:ownership-unverified','failed:no-shared-page','skipped')

def waived_closeout_legs(state):
    waived=set()
    listed=state.get('closeoutWaivedLegs')
    if isinstance(listed,list):
        waived.update(leg for leg in listed if isinstance(leg,str) and leg in CLOSEOUT_LEGS)
    legs=state.get('closeoutLegStatus')
    notion=legs.get('notion') if isinstance(legs,dict) else None
    if isinstance(notion,str) and notion.startswith(NOTION_WAIVED_PREFIXES):waived.add('notion')
    return [leg for leg in CLOSEOUT_LEGS if leg in waived]

def finalize_closeout(path):
    def mutate(state):
        require_build_identity(state)
        # Closeout judges the build by its settled verification receipt, not by
        # re-evaluating inputs and artifacts: runtime writes after finalize must
        # not un-verify a build that was already verified.
        verification=state.get('completionVerification') or {}
        missing=[]
        if not (isinstance(verification,dict) and verification.get('status')=='verified'
                and verification.get('buildId') and verification.get('buildId')==state.get('buildId')):
            missing.append('build-not-verified')
        if state.get('commandCenterStatus')!='done' or any(state.get(k) is not True for k in CC_PHASES):missing.append('command-center')
        if state.get('qualityHeld'):missing.append('quality-held')
        waived=waived_closeout_legs(state)
        for key,leg in (('infographic1Url',None),('infographic2Url',None),
                        ('celebrationVideoUrl','celebration-video'),('notionRootPageUrl','notion')):
            if leg and leg in waived:continue
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
        if waived:state['closeoutWaivedLegs']=waived
        state.update(closeoutStatus='done',closeoutCompletedAt=now,closeoutPendingSlots=[],closeoutFailureReason=None)
        state.pop('closeoutCriticalFailed',None)
        state['closeoutCleanupPending']=True
        return True
    try:return update(path,mutate)
    except UnownedBuildState:return False

if __name__=='__main__':
    path=sys.argv[1]
    if '--has-identity' in sys.argv:
        present=has_build_identity(read(path))
        print(json.dumps({'identityPresent':present}))
        sys.exit(0 if present else 1)
    verified=finalize_closeout(path) if '--closeout' in sys.argv else refresh(path) if '--refresh' in sys.argv else finalize(path)
    print(json.dumps({'verified':verified}))
    sys.exit(0 if verified else 1)
