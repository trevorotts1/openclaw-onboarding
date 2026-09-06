#!/usr/bin/env python3
"""Verified public invitation and acknowledged gateway delivery; no direct Bot API.
OpenClaw contract: https://docs.openclaw.ai/message (--message and --json).
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

PROTOCOL = 'interview-launch.v1'
class Pending(ValueError):
    pass

def public_origin(value):
    if not isinstance(value, str): raise Pending('public origin missing')
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('','/'):
        raise Pending('public HTTPS origin required')
    host = p.hostname.lower()
    if host == 'localhost' or host.endswith(('.localhost','.local')) or '.' not in host or p.port == 18789:
        raise Pending('public origin cannot be loopback or gateway')
    try:
        if not ipaddress.ip_address(host).is_global: raise Pending('public origin cannot be private')
    except ValueError as exc:
        if isinstance(exc, Pending): raise
    return 'https://' + p.netloc.lower().rstrip('/'), host

def expected_identity(state, env):
    expected = {}
    for key, variable in [('tenantId','MC_TENANT_ID'),('companyId','MC_COMPANY_ID'),('installationId','MC_INSTALLATION_ID')]:
        stored, ambient = state.get(key), env.get(variable)
        if stored and ambient and stored != ambient: raise Pending(key+' conflict')
        value = stored or ambient
        if not isinstance(value,str) or not value.strip(): raise Pending(key+' missing')
        expected[key] = value
    return expected

def validate_receipt(receipt, expected, host):
    if not isinstance(receipt,dict): raise Pending('readiness receipt must be an object')
    for key,value in dict(expected, host=host, protocol=PROTOCOL, stage='interview').items():
        if receipt.get(key) != value: raise Pending(key+' readiness mismatch')
    if receipt.get('ready') is not True or receipt.get('missing') != []: raise Pending('interview prerequisites pending')
    if type(receipt.get('interviewComplete')) is not bool: raise Pending('explicit interview completion required')
    capabilities = receipt.get('capabilities')
    if not isinstance(capabilities,dict) or any(capabilities.get(key) is not True for key in ['state','localInterviewPrerequisites','enrollment']):
        raise Pending('interview capability or enrollment pending')
    return receipt

def load_service_environment(state, env):
    """Read only the bootstrap-pinned service file; never scan or source secrets."""
    result=dict(env)
    launch=state.get('launchBootstrap') if isinstance(state,dict) else None
    filename=launch.get('serviceEnvPath') if isinstance(launch,dict) else None
    if filename is None:return result
    if not isinstance(filename,str) or not Path(filename).is_absolute(): raise Pending('service environment path invalid')
    allowed={'MC_TENANT_ID','MC_COMPANY_ID','MC_INSTALLATION_ID','MC_TENANT_PUBLIC_URL','MC_API_TOKEN'}
    stored={}
    try:
        file=Path(filename)
        if not file.is_file() or file.stat().st_size>1024*1024: raise Pending('service environment unavailable')
        for line in file.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:continue
            key,value=line.split('=',1);key=key.strip()
            if key not in allowed:continue
            value=value.strip()
            try: value=json.loads(value)
            except ValueError:
                if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
            if not isinstance(value,str) or not value:raise Pending('invalid scoped service environment value')
            if key in stored and stored[key]!=value:raise Pending('duplicate service environment conflict')
            stored[key]=value
    except OSError:raise Pending('pinned service environment unreadable') from None
    for key,variable in [('companyId','MC_COMPANY_ID'),('tenantId','MC_TENANT_ID'),('installationId','MC_INSTALLATION_ID')]:
        if not state.get(key) or stored.get(variable)!=state[key]:raise Pending('service environment identity mismatch')
    if not stored.get('MC_API_TOKEN'):raise Pending('service API token missing')
    for key,value in stored.items():
        if result.get(key) and result[key]!=value:raise Pending('service/invitation environment conflict: '+key)
        result[key]=value
    return result

def resolve_public_origin(state, env, fetch=None):
    if not isinstance(state,dict): raise Pending('canonical workforce state must be an object')
    env=load_service_environment(state,env)
    expected = expected_identity(state,env)
    record = state.get('commandCenterPublicOrigin')
    candidate = None
    if record is not None:
        if not isinstance(record,dict) or record.get('verified') is not True: raise Pending('canonical public origin unverified')
        if record.get('protocol') != PROTOCOL: raise Pending('canonical origin protocol mismatch')
        if any(record.get(k) != v for k,v in expected.items()): raise Pending('canonical origin identity mismatch')
        candidate = record.get('origin')
    candidates = [v for v in [candidate, env.get('MC_TENANT_PUBLIC_URL'), state.get('commandCenterUrl'), env.get('OPENCLAW_DASHBOARD_URL')] if v]
    if not candidates: raise Pending('public interview origin pending')
    origins = [public_origin(v)[0] for v in candidates]
    if len(set(origins)) != 1: raise Pending('public origin configuration conflict')
    origin,host = public_origin(origins[0])
    if env.get('INTERVIEW_GATE_URL') and public_origin(env['INTERVIEW_GATE_URL'])[0] != origin:
        raise Pending('separate readiness origin refused')
    token = env.get('MC_API_TOKEN')
    if not token or '\n' in token or '\r' in token: raise Pending('authenticated readiness token missing or invalid')
    if fetch:
        receipt = fetch(origin+'/api/auth/interview-ready',token)
    else:
        # Credentials go through stdin, never command-line argv or diagnostics.
        escaped = token.replace('\\','\\\\').replace('"','\\"')
        config = 'header = "Authorization: Bearer '+escaped+'"\n'
        try:
            result = subprocess.run(['curl','--disable','--max-filesize','65536','--config','-','--silent','--show-error','--max-time','15','--max-redirs','0','--proto','=https','--write-out','\n%{http_code}',origin+'/api/auth/interview-ready'],input=config,text=True,capture_output=True,timeout=20)
        except (OSError,subprocess.TimeoutExpired): raise Pending('authenticated readiness transport unavailable') from None
        if result.returncode: raise Pending('authenticated readiness transport failed')
        body, _, status = result.stdout.rstrip('\r\n').rpartition('\n')
        if status != '200' or len(body)>65536: raise Pending('authenticated readiness HTTP failure')
        try: receipt=json.loads(body)
        except ValueError: raise Pending('malformed readiness receipt') from None
    validate_receipt(receipt,expected,host)
    if receipt['interviewComplete']: raise Pending('interview already complete')
    if state.get('buildType') == 'standard-first' and (not isinstance(receipt.get('foundation'),dict) or receipt['foundation'].get('ready') is not True):
        raise Pending('standard foundation verification pending')
    return dict(expected,origin=origin,host=host,protocol=PROTOCOL,receipt=receipt)

def issue_invitation(resolved, env, target, metadata=None):
    token=env.get('MC_API_TOKEN','')
    escaped=token.replace('\\','\\\\').replace('"','\\"')
    config='header = "Authorization: Bearer '+escaped+'"\n'
    body=json.dumps({'recipientHash':hashlib.sha256(target.encode()).hexdigest()})
    try:
        result=subprocess.run(['curl','--disable','--max-filesize','65536','--config','-','--silent','--show-error','--max-time','15','--max-redirs','0','--proto','=https','--header','Content-Type: application/json','--data',body,'--write-out','\n%{http_code}',resolved['origin']+'/api/auth/interview-invitation'],input=config,text=True,capture_output=True,timeout=20)
        data,_,status=result.stdout.rstrip('\r\n').rpartition('\n')
        if result.returncode or status!='200' or len(data)>65536: raise Pending('authenticated invitation issuance failed')
        receipt=json.loads(data)
        if not isinstance(receipt,dict): raise Pending('invalid invitation receipt')
        for key in ['tenantId','companyId','installationId','host']:
            if receipt.get(key)!=resolved[key]: raise Pending('invitation identity mismatch')
        if receipt.get('protocol')!='interview-invitation.v1' or receipt.get('oneUse') is not True: raise Pending('invitation protocol mismatch')
        expiry=receipt.get('expiresAt')
        if type(expiry) is not int or not time.time()<expiry<=time.time()+910: raise Pending('invitation expiry invalid')
        url=receipt.get('url','');parsed=urlsplit(url)
        if parsed.scheme+'://'+parsed.netloc!=resolved['origin'] or parsed.path!='/interview' or parsed.query or not parsed.fragment.startswith('enroll='):
            raise Pending('invitation URL binding invalid')
        ticket=parsed.fragment[len('enroll='):]
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',ticket): raise Pending('invalid enrollment token format')
        if metadata is not None: metadata['invitationExpiresAt']=expiry
        return url
    except Pending: raise
    except (OSError,ValueError,subprocess.TimeoutExpired): raise Pending('invitation issuance unverified') from None

def atomic_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,ensure_ascii=False); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def acknowledgement(payload, target):
    if not isinstance(payload,dict) or payload.get('ok') is False or payload.get('dryRun') is True: return None
    # Current CLI wraps provider delivery in payload; older JSON uses result.
    data=payload.get('payload',payload.get('result',payload))
    if not isinstance(data,dict) or data.get('ok') is False or data.get('dryRun') is True: return None
    if any(item.get('status') in ('suppressed','failed','partial','pending') for item in [payload,data]): return None
    message_id=data.get('messageId',data.get('message_id'))
    recipient=data.get('chatId',data.get('chat_id',data.get('to',data.get('target'))))
    channel=data.get('channel',payload.get('channel','telegram'))
    if isinstance(message_id,bool) or not isinstance(message_id,(str,int)) or not str(message_id).strip(): return None
    if str(recipient) != target or channel != 'telegram': return None
    return {'messageId':str(message_id),'channel':'telegram','recipientHash':hashlib.sha256(target.encode()).hexdigest()}

def send_gateway(message, target, ledger, context, force=False, timeout=30, prepare_message=None):
    ledger=Path(ledger); ledger.parent.mkdir(parents=True,exist_ok=True)
    receipt_file=ledger.with_suffix(ledger.suffix+'.receipt.json')
    with open(str(ledger)+'.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous={}
        if receipt_file.exists():
            try: previous=json.loads(receipt_file.read_text())
            except (ValueError,OSError): raise Pending('delivery receipt unreadable; reconcile before retry') from None
        if previous and (any(previous.get(key) != context.get(key) for key in ('origin','companyId','tenantId','installationId'))
                         or previous.get('recipientHash') != hashlib.sha256(target.encode()).hexdigest()):
            raise Pending('delivery receipt identity mismatch; reconcile before retry')
        if previous.get('status') in ('sending','uncertain'):
            raise Pending('delivery uncertain; reconcile acknowledged gateway delivery before retry (FORCE cannot bypass)')
        if previous.get('status')=='accepted' and os.environ.get('INTERVIEW_INVITATION_AUTOMATIC')=='1':
            return 7, {'status':'guarded','reason':'automatic invitation already accepted; manual renewal required if expired'}
        expiry=previous.get('invitationExpiresAt')
        renewal=previous.get('status')=='accepted' and type(expiry) is int and time.time()>=expiry
        if previous.get('status')=='accepted' and not force and not renewal and time.time()-previous.get('epoch',0)<1800:
            return 7, {'status':'guarded','reason':'invitation recently accepted'}
        if ledger.exists() and not force and not renewal:
            try:
                last=ledger.read_text().splitlines()[-1].split('|')[0]
                if time.time()-int(last)<1800:return 7,{'status':'guarded','reason':'invitation recently accepted'}
            except (ValueError,IndexError): raise Pending('legacy delivery ledger malformed; reconcile before retry') from None
        if not shutil.which('openclaw'):return 5,{'status':'failed','reason':'OpenClaw CLI missing; no direct HTTP fallback'}
        if prepare_message: message=prepare_message(message)
        base=dict(context,epoch=int(time.time()),recipientHash=hashlib.sha256(target.encode()).hexdigest(),messageSha256=hashlib.sha256(message.encode()).hexdigest())
        # Persist uncertainty BEFORE invoking a command that might send. Failed receipt
        # or ledger writes after remote acceptance cannot turn a retry into a duplicate.
        atomic_json(receipt_file,dict(base,status='sending'))
        try:
            result=subprocess.run(['openclaw','message','send','--channel','telegram','--target',target,'--message',message,'--json'],capture_output=True,text=True,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired) as exc:
            outcome=dict(base,status='uncertain',reason='gateway '+type(exc).__name__+'; reconcile before retry')
            atomic_json(receipt_file,outcome); return 9,outcome
        try: payload=json.loads(result.stdout)
        except ValueError: payload=None
        ack=acknowledgement(payload,target) if result.returncode==0 else None
        if not ack:
            # An exact CLI usage rejection is known pre-send; other errors may follow acceptance.
            rejected=result.returncode==2 and any(x in result.stderr.lower() for x in ['unknown option','unknown argument','required option'])
            outcome=dict(base,status='rejected' if rejected else 'uncertain',reason='gateway command rejected' if rejected else 'gateway acceptance unverified; reconcile before retry',exitCode=result.returncode)
            atomic_json(receipt_file,outcome); return (6 if rejected else 9),outcome
        outcome=dict(base,status='accepted',**ack)
        atomic_json(receipt_file,outcome)
        try:
            with ledger.open('a') as stream:
                stream.write(f"{base['epoch']}|{context['mode']}|{context['lane']}|{context['origin']}\n");stream.flush();os.fsync(stream.fileno())
        except OSError:
            return 10,dict(outcome,reason='gateway accepted; legacy ledger write failed; acceptance receipt retained')
        return 0,outcome

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['resolve','send']);parser.add_argument('--state',required=True);parser.add_argument('--message-file');parser.add_argument('--target');parser.add_argument('--ledger');parser.add_argument('--resolution-file');parser.add_argument('--mode',default='start');parser.add_argument('--lane',default='legacy')
    args=parser.parse_args()
    try:
        state=json.loads(Path(args.state).read_text())
        env=load_service_environment(state,os.environ)
        resolved=resolve_public_origin(state,env)
        if args.action=='resolve':
            if args.resolution_file: atomic_json(args.resolution_file,{key:resolved[key] for key in ['origin','companyId','tenantId','installationId']})
            print(resolved['origin']);return 0
        if not args.resolution_file: raise Pending('verified message origin snapshot missing')
        pinned=json.loads(Path(args.resolution_file).read_text())
        if pinned != {key:resolved[key] for key in ['origin','companyId','tenantId','installationId']}:
            raise Pending('client identity or origin changed while preparing invitation')
        message=Path(args.message_file).read_text()
        delivery_context=dict(origin=resolved['origin'],companyId=resolved['companyId'],tenantId=resolved['tenantId'],installationId=resolved['installationId'],mode=args.mode,lane=args.lane)
        def enroll(text):
            url=issue_invitation(resolved,env,args.target,delivery_context)
            # Preparation always uses /interview: the browser reloads its persisted
            # tenant state after enrollment; old resume routes do not redeem grants.
            return text.replace(resolved['origin']+'/interview',url)
        code,receipt=send_gateway(message,args.target,args.ledger,delivery_context,os.environ.get('FORCE')=='1',prepare_message=enroll)
        print(json.dumps(receipt));return code
    except (Pending,ValueError,OSError) as exc:
        # Never expose raw CLI, curl, response, credential, recipient or token text.
        reason=str(exc) if isinstance(exc,Pending) else type(exc).__name__
        print('[send-interview-link] PENDING: '+reason,file=sys.stderr);return 8
if __name__=='__main__':sys.exit(main())
