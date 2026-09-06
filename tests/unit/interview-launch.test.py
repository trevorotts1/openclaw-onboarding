#!/usr/bin/env python3
"""Offline launch contract: fresh state, real SQLite identity, no deployment/network."""
import concurrent.futures, importlib.util, json, os, sqlite3, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('launch',ROOT/'32-command-center-setup/scripts/interview-launch.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Launch(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.state=self.root/'workspace/.workforce-build-state.json';self.app=self.root/'app';self.app.mkdir()
    def tearDown(self):
        if os.environ.get('KEEP_LAUNCH_FIXTURE') == '1' and self._testMethodName == 'test_real_prebuild_uuid_company':
            self.tmp._finalizer.detach()
            print('ISOLATED_LAUNCH_FIXTURE='+str(self.root.resolve()))
        else:self.tmp.cleanup()
    def initialize(self,env=None):m.initialize(self.state,'client-a','Client A','owner@example.test',env or {})
    def test_fresh_atomic_resume(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:self.initialize(),range(4)))
        before=json.loads(self.state.read_text());self.initialize();after=json.loads(self.state.read_text())
        for k in ['companyId','installationId','tenantId','buildId']:self.assertEqual(before[k],after[k])
        self.assertEqual(after['buildType'],'standard-first');self.assertEqual(after['operatorConsent']['source'],'operator-prebuild')
        self.assertIs(after['interviewComplete'],False);self.assertNotIn('buildCompletedAt',after);self.assertNotIn('interviewProgress',after)
    def test_foreign_and_corrupt_unchanged(self):
        self.initialize();before=self.state.read_bytes()
        with self.assertRaises(ValueError):self.initialize({'MC_COMPANY_ID':'foreign'})
        self.assertEqual(before,self.state.read_bytes());self.state.write_text('{')
        with self.assertRaises(ValueError):self.initialize()
        self.assertEqual(self.state.read_text(),'{')
    def test_legacy_not_converted(self):
        self.state.parent.mkdir();self.state.write_text(json.dumps({'companySlug':'client-a','companyId':'legacy-id','buildType':'legacy','interviewComplete':False,'interviewProgress':{'saved':'answer'}}))
        self.initialize();s=json.loads(self.state.read_text());self.assertEqual(s['buildType'],'legacy');self.assertNotIn('operatorConsent',s);self.assertEqual(s['interviewProgress'],{'saved':'answer'})
    def test_real_db_and_environment_binding(self):
        self.initialize();(self.app/'.env.local').write_text('MC_API_TOKEN=fixture-token\n')
        m.provision(self.state,self.app,self.root,{})
        with sqlite3.connect(self.app/'mission-control.db') as db:db.execute('CREATE TABLE companies(id TEXT PRIMARY KEY,name TEXT,slug TEXT UNIQUE)')
        m.bind_database(self.state,self.app);m.bind_database(self.state,self.app)
        s=json.loads(self.state.read_text());values=m.env_read(self.app/'.env.local')
        with sqlite3.connect(self.app/'mission-control.db') as db:self.assertEqual(db.execute('SELECT id,slug FROM companies').fetchall(),[(s['companyId'],'client-a')])
        self.assertEqual(values['MC_COMPANY_ID'],s['companyId']);self.assertNotEqual(s['companyId'],'client-a')
        self.assertEqual(values['OPENCLAW_WORKSPACE_ROOT'],str(self.state.parent.resolve()))
        self.assertNotIn('commandCenterPublicOrigin',s)
    def test_nonempty_unidentified_company_root_not_adopted(self):
        self.initialize();(self.app/'.env.local').write_text('MC_API_TOKEN=fixture-token\n')
        foreign=self.root/'unidentified';foreign.mkdir();(foreign/'owner-content.md').write_text('preserve')
        with self.assertRaises(ValueError):m.provision(self.state,self.app,self.root,{'ZERO_HUMAN_COMPANY_DIR':str(foreign)})
        self.assertFalse((foreign/'company-config.json').exists());self.assertEqual((foreign/'owner-content.md').read_text(),'preserve')
    def test_existing_config_requires_all_identity_aliases_to_match(self):
        self.initialize();state=json.loads(self.state.read_text());own=state['companyId']
        company=self.root/'selected-company';company.mkdir();config=company/'company-config.json'
        envfile=self.app/'.env.local';envfile.write_text('MC_API_TOKEN=fixture-token\n# preserve operator text\n')
        original_env=envfile.read_bytes();original_state=self.state.read_bytes()
        cases=[{}, {'company_id':'foreign'}, {'id':'foreign'}, {'companyId':own,'company_id':'foreign'},
               {'company_id':own,'id':'foreign'}, {'companyId':own,'companySlug':'other'},
               {'companyId':own,'companySlug':'client-a','company_slug':'other'}, {'companyId':own,'slug':'other'},
               {'companyId':own,'id':None}, {'companyId':own,'slug':''}]
        for payload in cases:
            with self.subTest(payload=payload):
                config.write_text(json.dumps(payload));before=config.read_bytes()
                with self.assertRaises(ValueError):m.provision(self.state,self.app,self.root,{'ZERO_HUMAN_COMPANY_DIR':str(company)})
                self.assertEqual(config.read_bytes(),before);self.assertEqual(envfile.read_bytes(),original_env);self.assertEqual(self.state.read_bytes(),original_state)
        config.write_text(json.dumps({'id':own,'company_id':own,'company_slug':'client-a','ownerNote':'preserve'}));before=config.read_bytes()
        m.provision(self.state,self.app,self.root,{'ZERO_HUMAN_COMPANY_DIR':str(company)})
        self.assertEqual(config.read_bytes(),before)
        self.assertIn('MC_PERSONA_COMPANY_CONTEXTS_JSON',m.env_read(envfile))
        foreign_config=self.root/'foreign-context.json';foreign_config.write_text(json.dumps({'company_id':'foreign'}))
        values=m.env_read(envfile);contexts=json.loads(values['MC_PERSONA_COMPANY_CONTEXTS_JSON']);contexts[own]['companyConfig']=str(foreign_config)
        values['MC_PERSONA_COMPANY_CONTEXTS_JSON']=json.dumps(contexts)
        envfile.write_text('\n'.join(key+'='+json.dumps(value) for key,value in values.items())+'\n')
        before_env=envfile.read_bytes();before_state=self.state.read_bytes();before_foreign=foreign_config.read_bytes()
        with self.assertRaises(ValueError):m.provision(self.state,self.app,self.root,{'ZERO_HUMAN_COMPANY_DIR':str(company)})
        self.assertEqual(envfile.read_bytes(),before_env);self.assertEqual(self.state.read_bytes(),before_state);self.assertEqual(foreign_config.read_bytes(),before_foreign)
    def test_shared_company_slug_rejected(self):
        self.initialize();(self.app/'.env.local').write_text('MC_API_TOKEN=fixture-token\n');m.provision(self.state,self.app,self.root,{})
        with sqlite3.connect(self.app/'mission-control.db') as db:
            db.execute('CREATE TABLE companies(id TEXT PRIMARY KEY,name TEXT,slug TEXT UNIQUE)');db.execute("INSERT INTO companies VALUES('foreign','Other','client-a')")
        with self.assertRaises(ValueError):m.bind_database(self.state,self.app)
    def test_two_installations_distinct(self):
        self.initialize();other=self.root/'other/state.json';m.initialize(other,'client-b','Client B','b@example.test',{})
        a=json.loads(self.state.read_text());b=json.loads(other.read_text())
        for key in ('companyId','tenantId','installationId','buildId'):self.assertNotEqual(a[key],b[key])
    @unittest.skipUnless(os.environ.get('RUN_LAUNCH_PREBUILD_FIXTURE') == '1','full canonical prebuild opt-in')
    def test_real_prebuild_uuid_company(self):
        self.initialize();(self.app/'.env.local').write_text('MC_API_TOKEN=fixture-token\n');m.provision(self.state,self.app,self.root,{})
        with sqlite3.connect(self.app/'mission-control.db') as db:
            db.executescript('CREATE TABLE companies(id TEXT PRIMARY KEY,name TEXT,slug TEXT UNIQUE,industry TEXT,config TEXT); CREATE TABLE workspaces(id TEXT PRIMARY KEY,name TEXT,slug TEXT UNIQUE,description TEXT,icon TEXT,company_id TEXT,archived_at TEXT);')
        m.bind_database(self.state,self.app)
        from unittest.mock import patch
        fixture_env=dict(os.environ,HOME=str(self.root/'home'),OPENCLAW_ROOT=str(self.root),PATH='/opt/homebrew/bin:'+os.environ['PATH'])
        (Path(fixture_env['HOME'])/'.openclaw').mkdir(parents=True)
        with patch.dict(os.environ,fixture_env,clear=True):m.prebuild(self.state,self.app,self.root)
        state=json.loads(self.state.read_text());receipt=state['standardPrebuild']['foundationVerification']
        self.assertEqual(set(receipt['workspaceSlugs']),set(state['standardPrebuild']['prebuiltDepartments']))
        with sqlite3.connect(self.app/'mission-control.db') as db:
            lanes={row[0] for row in db.execute('SELECT slug FROM workspaces WHERE company_id=?',(state['companyId'],))}
        self.assertTrue({'app-development','engineering'}.issubset(lanes))
        self.assertTrue(any(a['path']=='departments.json' for a in receipt['artifacts']))
        self.assertIs(state['interviewComplete'],False);self.assertNotIn('buildCompletedAt',state)
    def test_deployed_script_layout_resolves_selected_installation(self):
        import shutil
        from unittest.mock import patch
        installed=self.root/'oc';scripts=installed/'skills/32-command-center-setup/scripts';scripts.mkdir(parents=True)
        shutil.copy2(ROOT/'32-command-center-setup/scripts/interview-launch.py',scripts/'interview-launch.py')
        for name in ('23-ai-workforce-blueprint','shared-utils','22-book-to-persona-coaching-leadership-system'):
            (installed/'skills'/name).symlink_to(ROOT/name,target_is_directory=True)
        (installed/'scripts').mkdir();shutil.copy2(ROOT/'scripts/prebuild-standard-workforce.py',installed/'scripts/prebuild-standard-workforce.py')
        spec=importlib.util.spec_from_file_location('installed_launch',scripts/'interview-launch.py');deployed=importlib.util.module_from_spec(spec);spec.loader.exec_module(deployed)
        self.initialize();(self.app/'.env.local').write_text('MC_API_TOKEN=fixture-token\n');deployed.provision(self.state,self.app,installed,{})
        class CommandCaptured(Exception):pass
        def capture(command,env,check):
            self.assertEqual(Path(command[1]),installed/'scripts/prebuild-standard-workforce.py')
            self.assertEqual(env['ONBOARDING_SKILLS_ROOT'],str((installed/'skills').resolve()))
            self.assertEqual(env['SKILL23_SCRIPTS_DIR'],str((installed/'skills').resolve()/'23-ai-workforce-blueprint/scripts'))
            raise CommandCaptured()
        with patch.object(deployed.subprocess,'run',side_effect=capture):
            with self.assertRaises(CommandCaptured):deployed.prebuild(self.state,self.app,installed)
        if os.environ.get('RUN_LAUNCH_PREBUILD_FIXTURE') == '1':
            shutil.copy2(ROOT/'32-command-center-setup/scripts/seed-workspaces.py',scripts/'seed-workspaces.py')
            with sqlite3.connect(self.app/'mission-control.db') as db:
                db.executescript('CREATE TABLE companies(id TEXT PRIMARY KEY,name TEXT,slug TEXT UNIQUE,industry TEXT,config TEXT); CREATE TABLE workspaces(id TEXT PRIMARY KEY,name TEXT,slug TEXT UNIQUE,description TEXT,icon TEXT,company_id TEXT,archived_at TEXT);')
            deployed.bind_database(self.state,self.app)
            fixture_env=dict(os.environ,HOME=str(self.root/'home'),OPENCLAW_ROOT=str(installed),PATH='/opt/homebrew/bin:'+os.environ['PATH'])
            (Path(fixture_env['HOME'])/'.openclaw').mkdir(parents=True)
            with patch.dict(os.environ,fixture_env,clear=True):deployed.prebuild(self.state,self.app,installed)
            self.assertEqual(json.loads(self.state.read_text())['standardPrebuild']['foundationVerification']['status'],'verified')
    def test_automatic_invitation_runs_sender_only_after_readiness_once(self):
        from unittest.mock import patch
        self.initialize();state=json.loads(self.state.read_text());ids={k:state[k] for k in ('companyId','tenantId','installationId')}
        state['commandCenterPublicOrigin']=dict(ids,origin=state['commandCenterUrl'],verified=True,protocol='interview-launch.v1')
        state['commandCenterTenantVerification']=dict(ids,ready=True)
        self.state.write_text(json.dumps(state))
        scripts=self.root/'skills/23-ai-workforce-blueprint/scripts';scripts.mkdir(parents=True)
        sender=scripts/'send-interview-link.sh'
        sender.write_text("""#!/bin/bash
python3 - <<'STUB'
import json,os,time,sys
from pathlib import Path
ws=Path(os.environ['OPENCLAW_WORKSPACE_ROOT']);state=json.loads((ws/'.workforce-build-state.json').read_text())
p=ws/'company-discovery/.interview-link-sends.log.receipt.json'
if p.exists() and os.environ.get('INTERVIEW_INVITATION_AUTOMATIC')=='1':sys.exit(7)
with (ws/'invocations').open('a') as log:log.write('called\\n')
receipt={k:state[k] for k in ('companyId','tenantId','installationId')}
receipt.update(invitationExpiresAt=int(time.time())+900,status='accepted',messageId='fixture-message',recipientHash='fixture-recipient-hash',origin=state['commandCenterUrl'])
p=ws/'company-discovery/.interview-link-sends.log.receipt.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(receipt))
STUB
""")
        fake_location=str(self.root/'skills/32-command-center-setup/scripts/interview-launch.py')
        with patch.object(m,'__file__',fake_location):
            unready=dict(state);unready['commandCenterTenantVerification']=dict(ids,ready=False);self.state.write_text(json.dumps(unready))
            with self.assertRaises(ValueError):m.invite(self.state,self.root)
            self.assertFalse((self.state.parent/'invocations').exists())
            foreign=dict(state);foreign['commandCenterPublicOrigin']=dict(state['commandCenterPublicOrigin'],companyId='foreign');self.state.write_text(json.dumps(foreign))
            with self.assertRaises(ValueError):m.invite(self.state,self.root)
            self.assertFalse((self.state.parent/'invocations').exists())
            self.state.write_text(json.dumps(dict(state,interviewComplete=True)));m.invite(self.state,self.root)
            self.assertFalse((self.state.parent/'invocations').exists())
            self.state.write_text(json.dumps(state));m.invite(self.state,self.root);m.invite(self.state,self.root)
        self.assertEqual((self.state.parent/'invocations').read_text().splitlines(),['called'])
        self.assertEqual(json.loads(self.state.read_text())['interviewLaunch']['invitation']['messageId'],'fixture-message')
        receipt_path=self.state.parent/'company-discovery/.interview-link-sends.log.receipt.json'
        expired=json.loads(receipt_path.read_text());expired['invitationExpiresAt']=1;receipt_path.write_text(json.dumps(expired))
        with patch.object(m,'__file__',fake_location):
            with self.assertRaisesRegex(ValueError,'renewal-required'):m.invite(self.state,self.root)
        self.assertEqual((self.state.parent/'invocations').read_text().splitlines(),['called'])
        self.assertEqual(json.loads(self.state.read_text())['interviewLaunch']['invitation']['status'],'renewal-required')
        receipt_path.unlink();sender.write_text('#!/bin/bash\nexit 9\n')
        with patch.object(m,'__file__',fake_location):
            with self.assertRaisesRegex(ValueError,'sender exit 9'):m.invite(self.state,self.root)
        self.assertEqual(json.loads(self.state.read_text())['interviewLaunch']['status'],'invitation-pending')
    def test_tunnel_ambiguous_transport_posts_once(self):
        import subprocess
        bindir=self.root/'bin';bindir.mkdir();calls=self.root/'calls'
        (bindir/'cloudflared').write_text('#!/bin/sh\nexit 0\n');(bindir/'cloudflared').chmod(0o755)
        (bindir/'curl').write_text('#!/bin/sh\nprintf "call\\n" >> "$FIXTURE_CALLS"\nexit 28\n');(bindir/'curl').chmod(0o755)
        env=dict(os.environ,PATH=str(bindir)+':'+os.environ['PATH'],OPENCLAW_ROOT=str(self.root/'oc'),CC_TUNNEL_IDEMPOTENCY_KEY='fixture-installation-command-center',CC_TUNNEL_EXPECTED_HOST='client-a.zerohumanworkforce.com',FIXTURE_CALLS=str(calls))
        result=subprocess.run(['bash',str(ROOT/'32-command-center-setup/scripts/create-tunnel.sh'),'client-a','Client A','a@example.test'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertEqual(calls.read_text().splitlines(),['call'])
        self.assertFalse((self.root/'oc/.env').exists())
    def test_missing_state_real_preflight_negative_control(self):
        import subprocess,shlex
        source=(ROOT/'32-command-center-setup/scripts/run-full-install.sh').read_text()
        block=source[source.index('# ---- preflight ----'):source.index('for cmd in jq curl git npm python3;')]
        setup='\n'.join(['UPDATE_ONLY=false','export OPENCLAW_OWNER_NAME=FixtureOwner','OC_ROOT='+shlex.quote(str(self.root)),'STATE_FILE='+shlex.quote(str(self.state)),
            'SKILL_DIR='+shlex.quote(str(ROOT/'32-command-center-setup')),
            'DASHBOARD_DIR='+shlex.quote(str(self.app)),
            'LOG_FILE='+shlex.quote(str(self.root/'preflight.log')),
            'CLIENT_SLUG=client-a','COMPANY_NAME="Client A"','CONTACT_EMAIL=a@example.test',
            'fail_install() { exit 91; }','log() { :; }','cc_security_preflight() { :; }'])
        old='if [[ ! -f "$STATE_FILE" ]]; then exit 1; fi'
        self.assertEqual(subprocess.run(['bash','-c',setup+'\n'+old]).returncode,1)
        self.assertFalse(self.state.exists())
        self.assertEqual(subprocess.run(['bash','-c',setup+'\n'+block]).returncode,0)
        self.assertIs(json.loads(self.state.read_text())['interviewComplete'],False)
        self.assertEqual(json.loads(self.state.read_text())['ownerName'],'FixtureOwner')
        before=self.state.read_bytes()
        result=subprocess.run(['bash','-c',setup+'\nCLIENT_SLUG=foreign\n'+block])
        self.assertEqual(result.returncode,8);self.assertEqual(self.state.read_bytes(),before)
    def test_real_installer_orders_init_before_guard_and_readiness_before_exit(self):
        s=(ROOT/'32-command-center-setup/scripts/run-full-install.sh').read_text()
        self.assertLess(s.index('interview-launch.py" initialize'),s.index('# BLOCK A - LOCKED'))
        gate=s[s.index('  INTERVIEW_COMPLETE=$(state_get'):]
        self.assertLess(gate.index('verify-tenant-readiness.py'),gate.index('cc_launch_stage invite'))
        self.assertLess(gate.index('cc_launch_stage invite'),gate.index('exit 0'))
        self.assertIn('cc_launch_stage bind-database',s)
if __name__=='__main__':unittest.main()
