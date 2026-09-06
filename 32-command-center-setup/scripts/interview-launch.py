#!/usr/bin/env python3
"""Client-owned launch stages. No messages, provider calls, or readiness fabrication."""
from __future__ import annotations
import argparse, hashlib, json, os, re, secrets, sqlite3, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '23-ai-workforce-blueprint/scripts'))
from workforce_state import read, update, atomic_write, lock
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared-utils"))
from canonical_slug import canonical_dept_slug


def now(): return datetime.now(timezone.utc).isoformat()
def public_origin(value):
    import ipaddress
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/'):
        raise ValueError('an explicit public HTTPS origin is required')
    if p.hostname == 'localhost' or p.hostname.endswith(('.localhost', '.local')):
        raise ValueError('local hostname is not a public invitation origin')
    try:
        address = ipaddress.ip_address(p.hostname)
    except ValueError: pass
    else:
        if not address.is_global: raise ValueError('non-public address is not an invitation origin')
    return 'https://' + p.netloc.lower()


def initialize(path, slug, name, email, env):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug): raise ValueError('invalid client slug')
    if not name.strip() or not email.strip(): raise ValueError('explicit installation owner metadata is required')
    def mutate(s):
        for key in ('companySlug', 'clientSlug'):
            if s.get(key) and s[key] != slug: raise ValueError('existing company slug conflicts; refusing identity replacement')
        fresh = not s or set(s).issubset({'stateRevision'})
        for key, variable in [('companyId','MC_COMPANY_ID'), ('tenantId','MC_TENANT_ID'), ('installationId','MC_INSTALLATION_ID')]:
            value = env.get(variable)
            if s.get(key) and value and s[key] != value: raise ValueError(key + ' conflicts with installation configuration')
            if not s.get(key):
                if key == 'companyId' and not fresh and not value and not s.get('launchBootstrap'):
                    raise ValueError('existing state needs explicit canonical MC_COMPANY_ID; refusing to invent legacy ownership')
                s[key] = value or str(uuid.uuid4())
            if s[key] == 'default': raise ValueError('default identity cannot provision a client')
        s.setdefault('companySlug', slug); s.setdefault('clientSlug', slug)
        s.setdefault('companyName', name); s.setdefault('contactEmail', email)
        s.setdefault('interviewComplete', False)
        s.setdefault('buildId', str(uuid.uuid4()))
        s.setdefault('launchBootstrap', {'version':1, 'createdAt':now(), 'status':'identity-allocated'})
        # A requested hostname is not proof that DNS/tunnel exists. The strict
        # authenticated verifier alone promotes it into commandCenterPublicOrigin.
        if fresh:
            s.setdefault('commandCenterUrl', public_origin(env.get('MC_TENANT_PUBLIC_URL') or 'https://'+slug+'.zerohumanworkforce.com'))
        lane = env.get('ONBOARDING_LANE') or ('standard-first' if fresh else None)
        if lane and lane not in ('standard-first', 'legacy'): raise ValueError('ONBOARDING_LANE must be standard-first or legacy')
        if lane and s.get('buildType') and s['buildType'] != lane:
            raise ValueError('existing lane requires the explicit prebuild legacy-conversion workflow')
        if lane: s.setdefault('buildType', lane)
        if fresh and lane == 'standard-first':
            # This is the operator's actual fresh-install invocation under the
            # standard-first installation policy, never owner interview consent.
            import pwd
            s['operatorConsent'] = dict(decision='prebuild',source='operator-prebuild',decidedAt=now(),decidedBy=pwd.getpwuid(os.getuid()).pw_name,sessionId=s['installationId']+':initial-install',policyVersion='interview-launch.v1',requestedAction='fresh-standard-first-install')
        s.setdefault('interviewLaunch', {})['status'] = 'provisioning-pending'
    update(path, mutate)


def env_read(path):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' not in line or line.lstrip().startswith('#'): continue
            k, v = line.split('=',1)
            try: v = json.loads(v)
            except (ValueError, TypeError): v = v.strip().strip("'\"")
            values[k.strip()] = str(v)
    return values


def verify_company_config(value, company_id, slug):
    """Every present alias must corroborate the same explicit owner."""
    if not isinstance(value, dict): raise ValueError('company config identity conflict: expected an object')
    identities=[value[key] for key in ('companyId','company_id','id') if key in value]
    if not identities or any(not isinstance(value,str) or not value.strip() or value!=company_id for value in identities):
        raise ValueError('company config identity conflict: canonical ownership is missing or inconsistent')
    slugs=[value[key] for key in ('companySlug','company_slug','slug') if key in value]
    if any(not isinstance(value,str) or not value.strip() or value!=slug for value in slugs):
        raise ValueError('company config slug conflict')


def provision(path, app, root, env):
    s = read(path); target = app / '.env.local'
    with lock(target):
        values = env_read(target); original_values=dict(values)
        def preserve(key, value):
            if values.get(key) and values[key] != value: raise ValueError(key + ' conflicts with this installation')
            values[key] = value
        for key, variable in [('companyId','MC_COMPANY_ID'), ('tenantId','MC_TENANT_ID'), ('installationId','MC_INSTALLATION_ID')]:
            preserve(variable, s[key])
        preserve('OPENCLAW_WORKSPACE_PATH', str(Path(path).resolve().parent))
        preserve('OPENCLAW_WORKSPACE_ROOT', str(Path(path).resolve().parent))
        preserve('WORKFORCE_BUILD_STATE_PATH', str(Path(path).resolve()))
        preserve('OPENCLAW_ROOT', str(root.resolve()))
        values.setdefault('OPENCLAW_SKILL23_SCRIPTS', str(Path(__file__).resolve().parents[2]/'23-ai-workforce-blueprint/scripts'))
        company = Path(env.get('ZERO_HUMAN_COMPANY_DIR') or s.get('companyRoot') or values.get('ZERO_HUMAN_COMPANY_DIR') or root / 'workspace/zero-human-company' / s['companySlug']).resolve()
        if s.get('companyRoot') and Path(s['companyRoot']).resolve() != company: raise ValueError('company root conflict')
        values.setdefault('DATABASE_PATH', str(app / 'mission-control.db'))
        if env.get('DATABASE_PATH'):
            preserve('DATABASE_PATH', str(Path(env['DATABASE_PATH']).resolve()))
        preserve('ZERO_HUMAN_COMPANY_DIR', str(company))
        company.mkdir(parents=True, exist_ok=True)
        config = company/'company-config.json'
        if config.exists():
            existing = json.loads(config.read_text())
            verify_company_config(existing,s['companyId'],s['companySlug'])
        else:
            if any(company.iterdir()): raise ValueError('nonempty company root lacks a matching identity config; refusing adoption')
            atomic_write(config, {**{k:s[k] for k in ('companyId','companySlug','companyName')},'name':s['companyName'],'slug':s['companySlug']})
        catalog = Path(__file__).resolve().parents[2]/'22-book-to-persona-coaching-leadership-system/persona-categories.json'
        canonical = json.loads(catalog.read_text())
        if not canonical.get('personas'): raise ValueError('canonical persona catalog missing')
        contexts = json.loads(values.get('MC_PERSONA_COMPANY_CONTEXTS_JSON') or '{}')
        context = dict(companyRoot=str(company),companyConfig=str(config),companySlug=s['companySlug'],personaCatalog=str(catalog))
        if s['companyId'] in contexts:
            existing_context=contexts[s['companyId']]
            if existing_context.get('companySlug')!=s['companySlug'] or Path(existing_context.get('companyRoot','')).resolve()!=company:
                raise ValueError('existing persona context belongs to a different company root/slug')
            for key in ('companyConfig','personaCatalog'):
                if not Path(existing_context.get(key,'')).is_absolute() or not Path(existing_context[key]).is_file():
                    raise ValueError('existing persona context path unavailable: '+key)
            verify_company_config(json.loads(Path(existing_context['companyConfig']).read_text()),s['companyId'],s['companySlug'])
        else: contexts[s['companyId']] = context
        values['MC_PERSONA_COMPANY_CONTEXTS_JSON'] = json.dumps(contexts,separators=(',',':'))
        values.setdefault('MC_TENANT_SESSION_SECRET', secrets.token_urlsafe(48))
        # The existing installer owns API token generation and agent mirroring.
        if not values.get('MC_API_TOKEN'): raise ValueError('client API token must be provisioned before tenant configuration')
        candidate = env.get('MC_TENANT_PUBLIC_URL') or values.get('MC_TENANT_PUBLIC_URL') or s.get('commandCenterUrl')
        if candidate:
            origin = public_origin(candidate); host = urlsplit(origin).hostname
            registry = json.loads(values.get('MC_TENANT_REGISTRY_JSON') or env.get('MC_TENANT_REGISTRY_JSON') or '{}')
            registration = dict(kind='self', **{k:s[k] for k in ('tenantId','companyId','installationId')})
            if host in registry:
                if any(registry[host].get(k) != v for k,v in registration.items()): raise ValueError('public host is registered to a different identity')
            else: registry[host] = registration
            values['MC_TENANT_REGISTRY_JSON'] = json.dumps(registry,separators=(',',':'))
            preserve('MC_TENANT_PUBLIC_URL', origin)
        text = target.read_text() if target.exists() else ''
        updates={k:v for k,v in values.items() if original_values.get(k)!=v}
        lines = [line for line in text.splitlines() if line.split('=',1)[0].strip() not in updates]
        lines.extend(k+'='+json.dumps(v,ensure_ascii=False) for k,v in updates.items())
        import tempfile
        fd, temporary = tempfile.mkstemp(dir=app, prefix='.launch-env-')
        with os.fdopen(fd,'w') as handle:
            handle.write('\n'.join(lines)+'\n'); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary,target); target.chmod(0o600)
    def record(current):
        if any(current.get(k)!=s.get(k) for k in ('companyId','installationId','tenantId')): raise ValueError('identity changed while provisioning')
        current['companyRoot'] = str(company)
        current['launchBootstrap']['status'] = 'service-configured'
        current['launchBootstrap']['serviceEnvPath'] = str(target.resolve())
        if candidate: current['commandCenterUrl'] = origin  # candidate only; never a verified receipt
    update(path,record)


def bind_database(path, app):
    s = read(path); values = env_read(app/'.env.local'); dbpath = Path(values['DATABASE_PATH'])
    if not dbpath.is_absolute(): dbpath = app/dbpath
    db = sqlite3.connect('file:'+str(dbpath)+'?mode=rw', uri=True)
    with db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT id,slug FROM companies WHERE id=? OR slug=?',(s['companyId'],s['companySlug'])).fetchall()
        if any(r!=(s['companyId'],s['companySlug']) for r in row): raise ValueError('company database identity conflict')
        db.execute('INSERT OR IGNORE INTO companies(id,name,slug) VALUES(?,?,?)',(s['companyId'],s['companyName'],s['companySlug']))
    db.close()
    update(path,lambda current: current['launchBootstrap'].update(status='company-bound',databasePath=str(dbpath)))


def prebuild(path, app, root):
    s=read(path)
    if s.get('interviewComplete') is True: return
    if s.get('buildType') != 'standard-first':
        if s.get('buildType') == 'legacy': return
        raise ValueError('onboarding lane pending: explicitly configure ONBOARDING_LANE and operator consent')
    consentfile=os.environ.get('ONBOARDING_OPERATOR_CONSENT_FILE')
    if not consentfile:
        if not s.get('operatorConsent'): raise ValueError('standard-first requires explicit operator consent file')
        consentfile=str(Path(path).parent/'.standard-prebuild-operator-consent.json')
        atomic_write(consentfile,s['operatorConsent'])
    skills_root=Path(__file__).resolve().parents[2]
    engine=skills_root/'scripts/prebuild-standard-workforce.py'
    if not engine.is_file(): engine=root/'scripts/prebuild-standard-workforce.py'
    if not engine.is_file(): raise ValueError('delivered prebuild engine missing from selected installation scripts')
    values=env_read(app/'.env.local'); company=Path(s['companyRoot'])
    (company/'departments').mkdir(parents=True,exist_ok=True)
    child=dict(os.environ,STANDARD_FIRST_ONBOARDING='1',ONBOARDING_SKILLS_ROOT=str(skills_root),SKILL23_SCRIPTS_DIR=str(skills_root/'23-ai-workforce-blueprint/scripts'),MC_COMPANY_ID=s['companyId'],ZERO_HUMAN_COMPANY_DIR=str(company),OPENCLAW_WORKSPACE_ROOT=str(Path(path).parent))
    command=[sys.executable,str(engine),'--operator-consent-file',consentfile,'--company-dir',str(company),'--departments-dir',str(company/'departments'),'--company-slug',s['companySlug'],'--company-name',s['companyName'],'--build-state-file',str(path),'--db',values['DATABASE_PATH'],'--apply','--json']
    subprocess.run(command,env=child,check=True)
    # Verify the current materialization and same-company board after every resume.
    s=read(path); slugs=s['standardPrebuild']['prebuiltDepartments']; artifacts=[]
    chosen=company/'departments.json'
    artifacts.append({'path':'departments.json','sha256':hashlib.sha256(chosen.read_bytes()).hexdigest()})
    with sqlite3.connect('file:'+values['DATABASE_PATH']+'?mode=rw',uri=True) as db:
        for slug in slugs:
            if not db.execute('SELECT 1 FROM workspaces WHERE slug=? AND company_id=? AND archived_at IS NULL',(canonical_dept_slug(slug),s['companyId'])).fetchone(): raise ValueError('prebuild workspace ownership verification failed: '+slug)
            directory=company/'departments'/slug
            dept_artifacts=sorted(directory.rglob('SOUL.md'))
            if not dept_artifacts: raise ValueError('prebuild canonical artifact missing: '+slug)
            for artifact in dept_artifacts:
                if not artifact.read_bytes(): raise ValueError('empty canonical artifact: '+slug)
                artifact.resolve().relative_to(company.resolve())
                artifacts.append({'path':artifact.relative_to(company).as_posix(),'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()})
    if not artifacts: raise ValueError('empty foundation')
    receipt=dict(version=1,status='verified',companyId=s['companyId'],buildId=s['buildId'],artifacts=artifacts,workspaceSlugs=slugs)
    def record(current):
        if any(current.get(k)!=s.get(k) for k in ('companyId','tenantId','installationId','buildId')) or current['standardPrebuild'].get('prebuiltDepartments')!=slugs:
            raise ValueError('build identity changed during foundation verification')
        current['standardPrebuild']['foundationVerification']=receipt
    update(path,record)


def invite(path, root):
    state=read(path)
    if state.get('interviewComplete') is True or state.get('buildCompletedAt'): return
    expected={k:state.get(k) for k in ('companyId','tenantId','installationId')}
    origin=state.get('commandCenterPublicOrigin') or {}
    if not all(expected.values()) or origin.get('verified') is not True or origin.get('protocol')!='interview-launch.v1' or any(origin.get(k)!=v for k,v in expected.items()):
        raise ValueError('invitation requires the exact authenticated public-origin receipt')
    verification=state.get('commandCenterTenantVerification') or {}
    if verification.get('ready') is not True or any(verification.get(k)!=v for k,v in expected.items()):
        raise ValueError('invitation requires current tenant/interview prerequisites')
    receipt_path=Path(path).parent/'company-discovery/.interview-link-sends.log.receipt.json'
    def accepted():
        if not receipt_path.is_file(): return None
        receipt=json.loads(receipt_path.read_text())
        if any(receipt.get(k)!=v for k,v in dict(expected,origin=origin['origin']).items()):
            raise ValueError('invitation delivery receipt identity/origin conflict')
        return receipt if receipt.get('status')=='accepted' and receipt.get('messageId') and receipt.get('recipientHash') else None
    # The sender resolves today's owner and validates the receipt recipient even
    # on automatic resumes. Automatic mode never repeats an acknowledged send.
    sender=Path(__file__).resolve().parents[2]/'23-ai-workforce-blueprint/scripts/send-interview-link.sh'
    env=dict(os.environ,OPENCLAW_ROOT=str(root),OPENCLAW_WORKSPACE_ROOT=str(Path(path).parent),INTERVIEW_INVITATION_AUTOMATIC='1')
    env.pop('FORCE',None)
    result=subprocess.run(['bash',str(sender)],env=env,capture_output=True,text=True)
    result_code=result.returncode
    receipt=accepted() if result_code in (0,7,10) else None
    import time
    expiry=receipt.get('invitationExpiresAt') if receipt else None
    if receipt is None or type(expiry) is not int or expiry<=time.time():
        reason='renewal-required' if receipt else 'pending'
        update(path,lambda current: current.setdefault('interviewLaunch',{}).update(status='invitation-pending',invitation={'status':reason,'senderExitCode':result_code,'checkedAt':now()}))
        raise ValueError('invitation '+reason+'; sender exit '+str(result_code)+' (inspect scoped delivery receipt; unknown acceptance is never retried blindly)')
    def record(current):
        if any(current.get(k)!=v for k,v in expected.items()): raise ValueError('identity changed during invitation delivery')
        current.setdefault('interviewLaunch',{}).update(status='invitation-accepted',invitation={k:receipt[k] for k in ('status','messageId','recipientHash','companyId','tenantId','installationId','origin','invitationExpiresAt')})
        current['interviewLaunch']['invitation']['senderExitCode']=result_code
    update(path,record)


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['initialize','provision','bind-database','prebuild','invite']);p.add_argument('--state',type=Path,required=True);p.add_argument('--app',type=Path);p.add_argument('--root',type=Path);p.add_argument('--slug');p.add_argument('--name');p.add_argument('--email');a=p.parse_args()
    try:
        if a.stage=='initialize':
            env=dict(os.environ)
            if a.app:
                stored=env_read(a.app/'.env.local')
                for key in ('MC_COMPANY_ID','MC_TENANT_ID','MC_INSTALLATION_ID','MC_TENANT_PUBLIC_URL'):
                    if env.get(key) and stored.get(key) and env[key]!=stored[key]: raise ValueError('service identity conflict: '+key)
                    if stored.get(key): env[key]=stored[key]
            initialize(a.state,a.slug,a.name,a.email,env)
        elif a.stage=='provision': provision(a.state,a.app,a.root,os.environ)
        elif a.stage=='bind-database': bind_database(a.state,a.app)
        elif a.stage=='invite': invite(a.state,a.root)
        else: prebuild(a.state,a.app,a.root)
        print(json.dumps({'stage':a.stage,'status':'complete'}));return 0
    except Exception as exc:
        print(json.dumps({'stage':a.stage,'status':'pending','reason':str(exc)}),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
