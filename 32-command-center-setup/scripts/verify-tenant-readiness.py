#!/usr/bin/env python3
"""Verify the client-owned Command Center identity; never enroll or invent IDs."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'23-ai-workforce-blueprint/scripts'))
from workforce_state import read,update
from datetime import datetime,timezone

class AccessRedirect(Exception):
    """The public host answered with a redirect to its own Cloudflare Access login."""

class ReceiverRefused(Exception):
    """The Command Center answered 403/503 with a JSON body naming why (its `missing[]` or `error`)."""
    def __init__(self,status,names):super().__init__('HTTP '+str(status));self.status,self.names=status,names

def _probe(url,headers,timeout=15):
    """GET one readiness receipt without ever following a redirect (the bearer token must not leave this origin).

    A redirect to *.cloudflareaccess.com raises AccessRedirect; a 403/503 with a JSON body raises ReceiverRefused
    carrying the receiver's own reason names; any other failure is the plain urllib error."""
    import re,urllib.error,urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    try:
        with urllib.request.build_opener(NoRedirect()).open(Request(url,headers=headers),timeout=timeout) as response:
            if response.status!=200:raise ValueError('readiness status is not 200')
            return json.loads(response.read(65537))
    except urllib.error.HTTPError as exc:
        if exc.code in (301,302,303,307,308):
            login=urlsplit(exc.headers.get('Location') or '')
            if login.scheme=='https' and (login.hostname or '').lower().endswith('.cloudflareaccess.com'):exc.close();raise AccessRedirect() from None
        if exc.code in (403,503):
            try:body=json.loads(exc.read(65537))
            except (ValueError,OSError):body=None
            if isinstance(body,dict):
                names=body.get('missing') if isinstance(body.get('missing'),list) and body.get('missing') else [body.get('error')]
                names=[n for n in names if isinstance(n,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',n)][:20]
                exc.close();raise ReceiverRefused(exc.code,names or ['no reason given']) from None
        raise

def verify(state,env,fetch=None,local_fetch=None):
    expected={'tenantId':env.get('MC_TENANT_ID'),'companyId':state.get('companyId') or env.get('MC_COMPANY_ID'),
              'installationId':env.get('MC_INSTALLATION_ID')}
    url=env.get('MC_TENANT_PUBLIC_URL') or state.get('commandCenterUrl') or ''
    parsed=urlsplit(url)
    missing=[k for k,v in expected.items() if not isinstance(v,str) or not v.strip()]
    if not env.get('MC_API_TOKEN'):missing.append('MC_API_TOKEN')
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:missing.append('client HTTPS origin')
    if state.get('companyId') and env.get('MC_COMPANY_ID') and state['companyId']!=env['MC_COMPANY_ID']:missing.append('company identity conflict')
    if missing:return {'ready':False,'missing':missing}
    host=parsed.hostname.lower();path='/api/auth/tenant-ready'+('?requireRemoteReceiver=1' if env.get('MC_REQUIRE_REMOTE_RECEIVER')=='1' else '')
    auth={'Authorization':'Bearer '+env['MC_API_TOKEN']}
    def network():return _probe('https://'+parsed.netloc+path,auth)
    def loopback():
        # The Command Center resolves its tenant from the Host header plus the bearer token, so the on-box request
        # carries the public Host. Same endpoint, same receipt, same identity checks below.
        port=str(env.get('DASHBOARD_PORT') or env.get('CC_PORT') or 4000)
        if not port.isdigit() or not 0<int(port)<65536:raise ValueError('invalid Command Center port')
        return _probe('http://127.0.0.1:'+port+path,dict(auth,Host=parsed.netloc))
    via='public'
    try:
        try:receipt=fetch() if fetch else network()
        except AccessRedirect:
            # Cloudflare Access fronts the public host and answers every unauthenticated request with a 302 to its
            # login: that says nothing about readiness. Ask the Command Center itself, on this box.
            via='loopback';receipt=(local_fetch or loopback)()
    except ReceiverRefused as exc:return {'ready':False,'missing':['receiver refused readiness (HTTP '+str(exc.status)+'): '+', '.join(exc.names)]}
    except Exception as exc:return {'ready':False,'missing':['authenticated readiness probe failed'+(' (loopback, public host is behind Cloudflare Access)' if via=='loopback' else '')+': '+type(exc).__name__]}
    for key,value in dict(expected,host=host,kind='self',protocol='interview.v1').items():
        if receipt.get(key)!=value:missing.append(key+' mismatch')
    if receipt.get('ready') is not True or receipt.get('missing')!=[]:missing.append('receiver readiness')
    return dict(expected,host=host,ready=not missing,missing=missing,protocol='interview.v1',probe=via)

# ==============================================================================
# Startability gate (item 04): "can this box actually start the interview?"
#
# Readiness used to be the finish line, and it was reachable while the
# Command Center was down (exit 78 stale/missing build manifest), while the
# host registry had no Access identity, and while invitation issuance
# deterministically returned 409. An installer and a guide could both sign off
# on a box whose client could never open the interview.
#
# This mode answers the real question with four bounded, independently failing
# checks and one proof file:
#   1. the CANONICAL pm2 process is online in the expected app directory,
#   2. the expected local port answers /api/health with the expected payload,
#   3. the exact authenticated PUBLIC readiness receipt passes and the Access
#      identity is registered (no missing_registry_identity, and
#      capabilities.invitationIssuable when the issuer reports it),
#   4. a REAL invitation mints through the existing sender's mint-only mode,
#      is accepted by the existing validator, and the ticket is discarded.
#
# --no-send is not optional decoration: it is the assertion that this gate
# sends nothing. Calling --startability without --no-send is refused, so the
# gate can never be the thing that delivers a client message.
# ==============================================================================
ALLOWED_HEALTH_STATUS=('ok',)
PROTOCOL='interview-launch.v1'
STARTABILITY_PROOF_NAME='.interview-startability.proof.json'

def _bounded_json(url,headers=None,timeout=10):
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    request=Request(url,headers=headers or {})
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=timeout) as response:
        if response.status!=200:raise ValueError('status is not 200')
        return json.loads(response.read(65537))

def _pm2_canonical_online(app_dir,app_name='blackceo-command-center'):
    """True only when the named process is online AND lives in this app dir."""
    import subprocess
    try:
        result=subprocess.run(['pm2','jlist'],capture_output=True,text=True,timeout=20)
    except (OSError,subprocess.TimeoutExpired):return False,'pm2 unavailable or unresponsive'
    if result.returncode!=0:return False,'pm2 jlist failed'
    try:processes=json.loads(result.stdout or '[]')
    except ValueError:return False,'pm2 listing unreadable'
    expected=str(Path(app_dir).resolve())
    for process in processes if isinstance(processes,list) else []:
        env=process.get('pm2_env') or {}
        if env.get('name')!=app_name:continue
        if env.get('status')!='online':return False,app_name+' is '+str(env.get('status'))+' (rebuild or config repair required; never a blind restart loop)'
        if str(Path(env.get('cwd','')).resolve())!=expected:return False,app_name+' runs from '+str(env.get('cwd'))+' instead of '+expected
        return True,'online'
    return False,app_name+' is not registered'

def _local_health(port):
    """The local health payload this deployment is expected to serve."""
    try:receipt=_bounded_json('http://127.0.0.1:'+str(port)+'/api/health')
    except Exception as exc:return False,'local /api/health probe failed: '+type(exc).__name__
    if not isinstance(receipt,dict):return False,'local health payload is not an object'
    if receipt.get('status') not in ALLOWED_HEALTH_STATUS:return False,'local health status is '+repr(receipt.get('status'))
    pending=(receipt.get('migrations') or {}).get('pending') if isinstance(receipt.get('migrations'),dict) else None
    if isinstance(pending,list) and pending:return False,'local migrations are pending'
    return True,'ok'

def _mint_only_proof(sender,state_file,target):
    """Run the sender's mint-only mode and validate the sanitized summary."""
    import subprocess
    try:
        result=subprocess.run(['bash',str(sender),'--mint-only'],capture_output=True,text=True,env=dict(os.environ,OPENCLAW_OWNER_CHAT_ID=target) if target else None,timeout=90)
    except (OSError,subprocess.TimeoutExpired) as exc:return False,'mint-only probe failed: '+type(exc).__name__
    lines=[line for line in (result.stdout or '').splitlines() if line.startswith('{')]
    if result.returncode!=0 or not lines:
        reason=(result.stderr or '').strip().splitlines()[-1:] or ['no receipt']
        return False,'invitation did not mint: '+reason[0][:200]
    try:summary=json.loads(lines[-1])
    except ValueError:return False,'mint summary unreadable'
    if summary.get('status')!='minted':return False,'mint summary status is '+repr(summary.get('status'))
    if summary.get('ticket')!='discarded':return False,'mint summary did not discard the ticket'
    if summary.get('delivery')!='not-attempted':return False,'mint summary reports a delivery attempt'
    return True,summary

def startability(before,env,args):
    """Four bounded checks; every failure is its own named reason."""
    checks={}
    failed=[]
    app_dir=Path(args.app_dir).resolve() if args.app_dir else None
    if app_dir is None:
        return {'ready':False,'missing':['--app-dir is required with --startability'],'checks':{}}
    ok,why=_pm2_canonical_online(app_dir,args.pm2_app);checks['canonical_process']={'ok':ok,'detail':why}
    if not ok:failed.append('canonical_process')
    ok,why=_local_health(args.port);checks['local_health']={'ok':ok,'detail':why}
    if not ok:failed.append('local_health')
    # Public authenticated readiness + registered Access identity (item 13).
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shared-utils'))
    from interview_invitation import resolve_public_origin,Pending
    resolved=None
    try:
        resolved=resolve_public_origin(before,env);receipt=dict(resolved['receipt'])
    except Pending as exc:
        receipt={'ready':False,'missing':[str(exc)]}
    capabilities=receipt.get('capabilities') if isinstance(receipt.get('capabilities'),dict) else {}
    identity_missing=[]
    # Identity is compared HERE, not inherited from the probe: a receipt for a
    # wrong host, company or installation must fail this gate on its own, even
    # when the probe itself returned 200.
    # The resolver's own identity is authoritative when present: a receipt
    # nested under a foreign host/installation must fail even though the nested
    # receipt body still names the registered host.
    r = resolved if isinstance(resolved, dict) else {}
    origin=r.get('origin') or env.get('MC_TENANT_PUBLIC_URL') or before.get('commandCenterUrl') or ''
    expected_host=(r.get('host') or urlsplit(origin).hostname or '').lower()
    expected_identity={'companyId':r.get('companyId') or before.get('companyId') or env.get('MC_COMPANY_ID'),
                       'tenantId':r.get('tenantId') or before.get('tenantId') or env.get('MC_TENANT_ID'),
                       'installationId':r.get('installationId') or before.get('installationId') or env.get('MC_INSTALLATION_ID'),
                       'host':expected_host}
    if not expected_host:missing_identity=['client origin host']
    else:
        missing_identity=[key+' mismatch' for key,value in expected_identity.items() if receipt.get(key)!=value]
        missing_identity+=['protocol mismatch'] if receipt.get('protocol')!=PROTOCOL else []
    if missing_identity:identity_missing.extend(missing_identity)
    if 'missing_registry_identity' in (receipt.get('warnings') or []):identity_missing.append('missing_registry_identity')
    if receipt.get('ready') is not True or receipt.get('missing')!=[]:identity_missing.append('public readiness')
    if receipt.get('interviewComplete') is not False:identity_missing.append('interview completion state')
    # capability.enrollment false means the issuer itself refuses issuance
    if capabilities.get('enrollment') is not True:identity_missing.append('enrollment capability')
    # New issuers state it explicitly; an older issuer is judged on the triple.
    if 'invitationIssuable' in capabilities and capabilities.get('invitationIssuable') is not True:
        identity_missing.append('invitation not issuable')
    checks['public_readiness']={'ok':not identity_missing,'detail':identity_missing or 'exact authenticated readiness with a registered Access identity'}
    if identity_missing:failed.append('public_readiness')
    # Real mint through the existing sender, ticket discarded, nothing sent.
    sender=Path(__file__).resolve().parents[2]/'23-ai-workforce-blueprint/scripts/send-interview-link.sh'
    chat=os.environ.get('OPENCLAW_OWNER_CHAT_ID') or (before.get('ownerChat') if isinstance(before.get('ownerChat'),str) else None)
    ok,detail=_mint_only_proof(sender,args.state,chat)
    checks['invitation_mint']={'ok':ok,'detail':detail}
    if not ok:failed.append('invitation_mint')
    # T-40 shared readiness projection: installed/running/live are three
    # distinct states, and the stored proof is checked for invalidation —
    # a rebind, disconnect or upgrade must make a stale proof read invalid.
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shared-utils'))
    import shared_readiness
    prior_proof=None
    prior_path=Path(args.state).parent/'company-discovery'/STARTABILITY_PROOF_NAME
    if prior_path.exists():
        try:candidate=json.loads(prior_path.read_text())
        except ValueError:candidate=None
        if isinstance(candidate,dict) and isinstance(candidate.get('readinessProjection'),dict):
            prior_proof=candidate['readinessProjection']
    projection=shared_readiness.project(
        surface='command-center.startability',
        binding=str(expected_identity.get('host') or ''),
        version=str(before.get('buildId') or ''),
        installed=checks['canonical_process']['ok'],
        running=checks['local_health']['ok'],
        live=checks['public_readiness']['ok'],
        prior=prior_proof)
    stale=[]
    if prior_proof is not None and not shared_readiness.proof_valid(prior_proof,projection):
        stale=['previous proof invalidated: '+','.join(projection['events'] or ['identity'])]
    # C5 step 2: the tenant's Messenger Page is a readiness FACT, recorded on the
    # readiness record under the account binding revision that owns it. The Page
    # id and revision are supplied to the installer (never guessed); a Page id
    # that was recorded under a different revision, or a different Page id, is
    # REFUSED here and reported — the door never outlives the binding that made
    # it. No supplied Page id records nothing and invents nothing.
    prior_page=prior_proof.get('pageBinding') if isinstance(prior_proof,dict) else None
    page_record=dict(prior_page) if isinstance(prior_page,dict) else {}
    page_id=str(env.get('MC_MESSENGER_PAGE_ID') or '').strip()
    page_revision=str(env.get('MC_ACCOUNT_BINDING_REVISION') or '').strip()
    page_binding,page_errors=None,[]
    if page_id and page_revision:
        identity_record={'tenant_id':str(before.get('tenantId') or env.get('MC_TENANT_ID') or ''),
                         'account_id':str(before.get('companyId') or env.get('MC_COMPANY_ID') or ''),
                         'messenger_page_id':page_id,
                         'account_binding_revision':page_revision}
        page_binding,page_errors=shared_readiness.page_binding_from_record(identity_record)
        if page_binding is not None:
            if not page_record:
                page_record={'binding':page_revision,
                             'tenant_id':page_binding.tenant_id,
                             'account_id':page_binding.account_id}
            page_record,page_errors=shared_readiness.record_page_binding(page_record,page_binding)
    if page_errors:
        failed.append('page_binding')
        checks['page_binding']={'ok':False,'detail':page_errors}
    elif page_binding is not None:
        checks['page_binding']={'ok':True,
                                'detail':'Page '+page_binding.page_id+' recorded at '+page_revision}
    proof={'protocol':'interview-startability.v1','stage':'startability','ready':not failed,'missing':failed,
           'checks':checks,'host':receipt.get('host'),'companyId':before.get('companyId'),
           'tenantId':before.get('tenantId'),'installationId':before.get('installationId'),
           'buildId':before.get('buildId'),'checkedAt':datetime.now(timezone.utc).isoformat(),
           'ownerHash':hashlib.sha256(chat.encode()).hexdigest() if isinstance(chat,str) and chat else None,
           'readinessProjection':projection,'pageBinding':page_record,
           'invalidatedPriorProofs':stale,
           'ticket':'discarded','delivery':'not-attempted'}
    # Scoped, sanitized proof only: no secrets, no ticket, no recipient value.
    proof_path=Path(args.state).parent/'company-discovery'/STARTABILITY_PROOF_NAME
    proof_path.parent.mkdir(parents=True,exist_ok=True)
    proof_path.write_text(json.dumps(proof,indent=1,sort_keys=True)+'\n')
    return dict(proof,proofPath=str(proof_path))

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('state');parser.add_argument('--interview',action='store_true');parser.add_argument('--env-file',type=Path)
    parser.add_argument('--startability',action='store_true');parser.add_argument('--no-send',action='store_true')
    parser.add_argument('--app-dir');parser.add_argument('--pm2-app',default='blackceo-command-center');parser.add_argument('--port',type=int,default=None)
    args=parser.parse_args();path=args.state;before=read(path);env=dict(os.environ)
    # The on-box Command Center port: --port, else the installer's DASHBOARD_PORT / CC_PORT, else the CC default.
    ambient=env.get('DASHBOARD_PORT') or env.get('CC_PORT') or ''
    args.port=args.port or (int(ambient) if ambient.isdigit() else 4000);env['DASHBOARD_PORT']=str(args.port)
    if args.env_file:
        import importlib.util
        spec=importlib.util.spec_from_file_location('launch',Path(__file__).with_name('interview-launch.py'))
        launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)
        stored=launch.env_read(args.env_file)
        for key in ('MC_TENANT_ID','MC_COMPANY_ID','MC_INSTALLATION_ID','MC_TENANT_PUBLIC_URL','MC_API_TOKEN'):
            if key in stored and env.get(key) and stored[key]!=env[key]:
                print(json.dumps({'ready':False,'missing':['service/installer environment conflict: '+key]}));return 1
        env.update(stored)
    if args.startability:
        if not args.no_send:
            print(json.dumps({'ready':False,'missing':['--startability requires --no-send: this gate must never deliver a client message']}));return 1
        receipt=startability(before,env,args)
        print(json.dumps(receipt));return 0 if receipt.get('ready') else 1
    resolved=None
    if args.interview:
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shared-utils'))
        from interview_invitation import resolve_public_origin,Pending
        try:
            resolved=resolve_public_origin(before,env)
            receipt=dict(resolved['receipt'])
        except Pending as exc: receipt={'ready':False,'missing':[str(exc)]}
    else: receipt=verify(before,env)
    def record(state):
        if any(state.get(k)!=before.get(k) for k in ('companyId','tenantId','installationId','buildId')):
            receipt.update(ready=False,missing=['build identity changed during probe'])
        checked=datetime.now(timezone.utc).isoformat()
        state['commandCenterTenantReady']=receipt['ready']
        state['commandCenterTenantVerification']=dict(receipt,buildId=state.get('buildId'),checkedAt=checked)
        if args.interview:
            state.setdefault('interviewLaunch',{}).update(status='prerequisites-verified' if receipt['ready'] else 'readiness-pending',providerLiveness='unverified',checkedAt=checked)
            if receipt['ready']:
                state['commandCenterPublicOrigin']={**{k:resolved[k] for k in ('origin','tenantId','companyId','installationId','protocol')},'verified':True,'checkedAt':checked}
                state['commandCenterUrl']=resolved['origin']
                state['commandCenterPhase6hStatus']='verified'
            else:
                state.pop('commandCenterPublicOrigin',None)
    update(path,record)
    print(json.dumps(receipt))
    return 0 if receipt['ready'] else 1
if __name__=='__main__':raise SystemExit(main())
