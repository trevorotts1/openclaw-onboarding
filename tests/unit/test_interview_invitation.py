import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('invitation',ROOT/'shared-utils/interview_invitation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

# Installed both here and through sitecustomize in every fixture Python child.
# This is deliberately independent of CLI discovery/PATH: tests cannot execute a
# real CLI or curl, even if a resolver regression points at an absolute host file.
FIXTURE_GUARD = r'''import os, pathlib, shutil, sys

def fixture_audit(event, args):
    selected = os.environ.get('INVITATION_FIXTURE_ROOT')
    if not selected: return
    root = pathlib.Path(selected).resolve()
    if event.startswith('socket.') and event not in ('socket.__new__',):
        raise RuntimeError('fixture network access denied')
    if event not in ('subprocess.Popen', 'os.exec', 'os.posix_spawn'): return
    executable = str(args[0])
    env = args[3] if event == 'subprocess.Popen' else args[-1]
    env = os.environ if env is None else env
    resolved = pathlib.Path(shutil.which(executable, path=env.get('PATH', '')) or executable).resolve()
    interpreters = {pathlib.Path(sys.executable).resolve(), pathlib.Path('/bin/bash').resolve(), pathlib.Path('/usr/bin/bash').resolve()}
    # Other Python versions selected by the shell are allowed only as interpreter
    # entrypoints; their sitecustomize inherits this same guard.
    python = shutil.which('python3', path=env.get('PATH', ''))
    if python: interpreters.add(pathlib.Path(python).resolve())
    if resolved not in interpreters and root not in resolved.parents:
        raise RuntimeError('fixture rejected non-fixture executable')
    for key in ('HOME', 'OPENCLAW_ROOT', 'OC_ROOT', 'OC_CONFIG'):
        value = env.get(key)
        if value and pathlib.Path(value).resolve() != root and root not in pathlib.Path(value).resolve().parents:
            raise RuntimeError('fixture rejected foreign runtime environment')
    if env.get('INVITATION_FIXTURE_ROOT') != selected or pathlib.Path(env.get('PYTHONPATH', '')).resolve() != root / 'guard':
        raise RuntimeError('fixture guard missing in child environment')

sys.addaudithook(fixture_audit)
'''
exec(FIXTURE_GUARD)

class InvitationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.state={'companyId':'client-a','tenantId':'tenant-a','installationId':'install-a','commandCenterUrl':'https://client.example.com','interviewComplete':False}
        self.env={'MC_API_TOKEN':'fixture-secret'}
        self.receipt=dict(companyId='client-a',tenantId='tenant-a',installationId='install-a',host='client.example.com',protocol=m.PROTOCOL,stage='interview',ready=True,missing=[],interviewComplete=False,capabilities={'state':True,'localInterviewPrerequisites':True,'enrollment':True,'providerLiveness':'unverified'})
        self.bin=self.root/'bin';self.bin.mkdir();self.ledger=self.root/'discovery'/'sends.log'
        self.context={'origin':'https://client.example.com','companyId':'client-a','tenantId':'tenant-a','installationId':'install-a','mode':'start','lane':'legacy'}
        self.capture=self.root/'capture.json'
        self.cli=self.bin/'openclaw'
        self.cli.write_text('#!'+sys.executable+'''\nimport sys,json,os,time
args=sys.argv[1:]
if args==['--version']:print(os.environ.get('FIXTURE_CLI_VERSION','2026.9.2'));sys.exit(0)
assert '--file' not in args
assert args[:2]==['message','send']
assert '--json' in args
assert args[args.index('--channel')+1]=='telegram'
message=args[args.index('--message')+1];target=args[args.index('--target')+1]
json.dump({'message':message,'target':target},open(os.environ['CAPTURE'],'w'))
behavior=os.environ.get('CLI_BEHAVIOR','success')
if behavior=='timeout':time.sleep(2)
if behavior=='reject':print('unknown option --not-supported fixture-secret',file=sys.stderr);sys.exit(2)
if behavior=='ambiguous':print('Bearer fixture-secret failed',file=sys.stderr);sys.exit(1)
if behavior=='malformed':print('{}');sys.exit(0)
if behavior=='ledgerfail':os.mkdir(os.environ['LEDGER'])
print(json.dumps({'channel':'telegram','payload':{'ok':True,'messageId':'fixture-message-1','chatId':target}}))
''');self.cli.chmod(0o755)
        guard=self.root/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(FIXTURE_GUARD)
        fixture_env={key:value for key,value in os.environ.items() if not key.startswith(('OPENCLAW_','OC_','MC_','CF_ACCESS_')) and key not in ('FORCE','INTERVIEW_INVITATION_AUTOMATIC')}
        fixture_env.update(HOME=str(self.root),OPENCLAW_ROOT=str(self.root/'.openclaw'),PATH=str(self.bin)+os.pathsep+os.environ['PATH'],CAPTURE=str(self.capture),LEDGER=str(self.ledger),INVITATION_FIXTURE_ROOT=str(self.root),PYTHONPATH=str(guard))
        self.process_env=patch.dict(os.environ,fixture_env,clear=True);self.process_env.start();self.addCleanup(self.process_env.stop)
    def test_fixture_rejects_absolute_host_executable_before_launch(self):
        with self.assertRaisesRegex(RuntimeError,'non-fixture executable'):
            subprocess.run(['/usr/bin/true'],check=True)
        self.assertFalse(self.capture.exists())

    def test_fixture_child_cannot_execute_host_cli_or_open_network(self):
        code="import subprocess,socket;\nfor operation in (lambda:subprocess.run(['/usr/bin/true']),lambda:socket.create_connection(('127.0.0.1',9))):\n try:operation()\n except RuntimeError:print('blocked')\n else:raise AssertionError('fixture guard bypassed')"
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),['blocked','blocked'])

    def config_version(self,version='2026.9.2'):
        runtime=self.root/'selected-runtime';runtime.mkdir(exist_ok=True)
        (runtime/'openclaw.json').write_text(json.dumps({'meta':{'lastTouchedVersion':version}}))
        return runtime

    def test_selected_current_cli_wins_over_old_path_shadow(self):
        runtime=self.config_version()
        current=runtime/'npm-global/bin/openclaw';current.parent.mkdir(parents=True)
        current.write_text(self.cli.read_text());current.chmod(0o755)
        self.cli.write_text(self.cli.read_text().replace("'2026.9.2'","'2026.7.1-2'"))
        with patch.dict(os.environ,OPENCLAW_ROOT=str(runtime)):
            executable,child=m.resolve_openclaw_cli(dict(os.environ))
            self.assertEqual(executable,str(current.resolve()))
            self.assertEqual(child['OPENCLAW_ROOT'],str(runtime))
            self.assertEqual(self.send()[0],0)

    def test_stale_explicit_cli_pin_fails_closed_before_mint(self):
        runtime=self.config_version()
        with patch.dict(os.environ,OPENCLAW_ROOT=str(runtime),OPENCLAW_BIN=str(self.cli),FIXTURE_CLI_VERSION='2026.7.1-2'):
            prepared=[]
            with self.assertRaisesRegex(m.Pending,'older'):
                self.send(prepare_message=lambda text:prepared.append(text) or text)
            self.assertEqual(prepared,[]);self.assertFalse(self.capture.exists())

    def test_native_current_cli_after_stale_path_is_verified(self):
        runtime=self.config_version();native=self.root/'native/openclaw';native.parent.mkdir()
        native.write_text(self.cli.read_text());native.chmod(0o755)
        self.cli.write_text(self.cli.read_text().replace("'2026.9.2'","'2026.7.1-2'"))
        with patch.dict(os.environ,OPENCLAW_ROOT=str(runtime)),patch.object(m,'native_openclaw_candidates',return_value=[native]):
            self.assertEqual(m.resolve_openclaw_cli(dict(os.environ))[0],str(native.resolve()))

    def test_foreign_or_invalid_client_root_pins_reject_before_version_probe(self):
        with patch.object(m.subprocess,'run') as run:
            for extra in ({'OPENCLAW_ROOT':'relative'},{'OPENCLAW_ROOT':str(self.root/'a'),'OC_ROOT':str(self.root/'b')}):
                with self.subTest(extra=extra),self.assertRaises(m.Pending):m.resolve_openclaw_cli(dict(os.environ,**extra))
            run.assert_not_called()

    def test_cloudflare_credentials_are_only_in_curl_stdin_for_both_requests(self):
        import time
        credentials=dict(self.env,CF_ACCESS_CLIENT_ID='fixture-access-id',CF_ACCESS_CLIENT_SECRET='fixture-access-secret')
        ticket=dict(protocol='interview-invitation.v1',tenantId='tenant-a',companyId='client-a',installationId='install-a',host='client.example.com',expiresAt=int(time.time())+86400,oneUse=True,url='https://client.example.com/interview#enroll=fixture.signature')
        with patch.object(m.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,json.dumps(self.receipt)+'\n200',''),subprocess.CompletedProcess([],0,json.dumps(ticket)+'\n200','')]) as run:
            resolved=m.resolve_public_origin(self.state,credentials)
            m.issue_invitation(resolved,credentials,'123456789')
        self.assertEqual(run.call_count,2)
        for call in run.call_args_list:
            argv=call.args[0];config=call.kwargs['input']
            self.assertNotIn('fixture-access',str(argv));self.assertNotIn('fixture-secret',str(argv))
            self.assertIn('CF-Access-Client-Id: fixture-access-id',config)
            self.assertIn('CF-Access-Client-Secret: fixture-access-secret',config)
            self.assertIn('Authorization: Bearer fixture-secret',config)
            self.assertNotIn('--location',argv)

    def test_partial_or_injected_access_credentials_reject_before_network(self):
        for extra in ({'CF_ACCESS_CLIENT_ID':'id'},{'CF_ACCESS_CLIENT_SECRET':'secret'},{'CF_ACCESS_CLIENT_ID':'id','CF_ACCESS_CLIENT_SECRET':''},{'CF_ACCESS_CLIENT_ID':'id','CF_ACCESS_CLIENT_SECRET':'bad\nheader'}):
            with self.subTest(extra=extra),patch.object(m.subprocess,'run') as run,self.assertRaisesRegex(m.Pending,'complete valid'):
                m.resolve_public_origin(self.state,dict(self.env,**extra))
            run.assert_not_called()

    def test_access_redirect_is_auth_required_without_following_or_minting(self):
        for status in ('302','303','307'):
            with self.subTest(status=status),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'<html>Access login</html>\n'+status,'')) as run:
                with self.assertRaisesRegex(m.Pending,'public authentication required'):m.resolve_public_origin(self.state,self.env)
                self.assertEqual(run.call_count,1)
                with self.assertRaisesRegex(m.Pending,'public authentication required'):m.issue_invitation(self.resolve(),self.env,'123456789')

    def resolve(self,receipt=None,state=None,env=None):
        return m.resolve_public_origin(state or self.state,env or self.env,lambda endpoint,token: self.receipt if receipt is None else receipt)
    def send(self,**kwargs):return m.send_gateway('Hi Zoë — 👋\n\nYour interview: https://client.example.com/interview\n','123456789',self.ledger,self.context,**kwargs)
    def test_verified_state_without_ambient_dashboard_resolves(self):
        result=self.resolve();self.assertEqual(result['origin'],'https://client.example.com');self.assertEqual(result['receipt']['capabilities']['providerLiveness'],'unverified')
    def test_invalid_receipts(self):
        for bad in [{},{'error':'no'},[],dict(self.receipt,companyId='foreign'),dict(self.receipt,installationId='other'),dict(self.receipt,tenantId='other'),dict(self.receipt,host='foreign.example.com'),dict(self.receipt,protocol='interview.v1'),dict(self.receipt,ready=False),dict(self.receipt,interviewComplete=None),dict(self.receipt,interviewComplete=True),dict(self.receipt,capabilities={})]:
            with self.subTest(receipt=bad),self.assertRaises(m.Pending):self.resolve(receipt=bad)
    def test_loopback_private_gateway_and_malformed_urls(self):
        for value in ['http://localhost:4000','https://127.0.0.1','https://[::1]','https://10.0.0.1','https://client.example.com:18789','https://user:secret@client.example.com','https://client.example.com/path','https://client.example.com?token=secret']:
            with self.subTest(url=value),self.assertRaises(m.Pending):self.resolve(state=dict(self.state,commandCenterUrl=value))
    def test_missing_and_conflicting_origins_are_pending(self):
        for state,env in [(dict(self.state,commandCenterUrl=None),self.env),(self.state,dict(self.env,OPENCLAW_DASHBOARD_URL='https://other.example.com')),(self.state,dict(self.env,INTERVIEW_GATE_URL='https://other.example.com')),(self.state,dict(self.env,MC_COMPANY_ID='foreign'))]:
            with self.subTest(state=state,env=env),self.assertRaises(m.Pending):self.resolve(state=state,env=env)
    def test_canonical_origin_must_match_state_identity(self):
        record=dict(self.context,verified=True);record['installationId']='foreign'
        with self.assertRaises(m.Pending):self.resolve(state=dict(self.state,commandCenterPublicOrigin=record))
    def test_strict_cli_preserves_message_and_acknowledgement(self):
        code,receipt=self.send();self.assertEqual(code,0);self.assertEqual(receipt['status'],'accepted');self.assertEqual(receipt['messageId'],'fixture-message-1')
        captured=json.loads(self.capture.read_text());self.assertEqual(captured['message'],'Hi Zoë — 👋\n\nYour interview: https://client.example.com/interview\n');self.assertEqual(captured['target'],'123456789')
        self.assertEqual(self.send()[0],7)
    def test_cli_rejection_is_redacted(self):
        with patch.dict(os.environ,CLI_BEHAVIOR='reject'):code,receipt=self.send()
        self.assertEqual(code,6);self.assertNotIn('fixture-secret',json.dumps(receipt));self.assertFalse(self.ledger.exists())
    def test_ambiguous_failure_blocks_force_retry(self):
        with patch.dict(os.environ,CLI_BEHAVIOR='ambiguous'):code,receipt=self.send()
        self.assertEqual(code,9);self.assertNotIn('fixture-secret',json.dumps(receipt))
        with self.assertRaises(m.Pending):self.send(force=True)
    def test_timeout_after_possible_acceptance_remains_uncertain(self):
        real_run=m.subprocess.run
        def lose_response_after_acceptance(argv,**kwargs):
            # First prove the isolated provider accepted; then simulate its reply
            # being lost at the timeout boundary. No startup-timing race.
            accepted=real_run(argv,**dict(kwargs,timeout=5))
            self.assertEqual(accepted.returncode,0,accepted.stderr)
            raise subprocess.TimeoutExpired(argv,kwargs['timeout'])
        with patch.object(m.subprocess,'run',side_effect=lose_response_after_acceptance):
            code,receipt=self.send(timeout=.05)
        self.assertEqual(code,9);self.assertTrue(self.capture.exists());self.assertFalse(self.ledger.exists())
        with self.assertRaises(m.Pending):self.send(force=True)
    def test_exit_zero_without_message_id_is_not_acceptance(self):
        with patch.dict(os.environ,CLI_BEHAVIOR='malformed'):self.assertEqual(self.send()[0],9)
    def test_foreign_recipient_ack_not_accepted(self):
        self.assertIsNone(m.acknowledgement({'messageId':'1','chatId':'foreign'},'123456789'))
    def test_missing_cli_does_not_send_or_write_success(self):
        with patch.object(m.shutil,'which',return_value=None),patch.object(m,'native_openclaw_candidates',return_value=[]):self.assertEqual(self.send()[0],5)
        self.assertFalse(self.capture.exists());self.assertFalse(self.ledger.exists())
    def test_explicit_cli_pin_beats_path_and_preserves_gateway_environment(self):
        pinned=self.root/'pinned cli';pinned.write_text(self.cli.read_text());pinned.chmod(0o755)
        env=dict(os.environ,OPENCLAW_BIN=str(pinned),OPENCLAW_ROOT=str(self.root/'own-root'),OPENCLAW_GATEWAY_TOKEN='own-fixture-token')
        executable,child=m.resolve_openclaw_cli(env)
        self.assertEqual(executable,str(pinned.resolve()))
        self.assertEqual(child['OPENCLAW_ROOT'],env['OPENCLAW_ROOT'])
        self.assertEqual(child['OPENCLAW_GATEWAY_TOKEN'],env['OPENCLAW_GATEWAY_TOKEN'])
        real_run=m.subprocess.run
        with patch.dict(os.environ,env,clear=True),patch.object(m.subprocess,'run',wraps=real_run) as invoked:
            self.assertEqual(self.send()[0],0)
            self.assertEqual(invoked.call_args.args[0][0],str(pinned.resolve()))
            self.assertEqual(invoked.call_args.kwargs['env']['OPENCLAW_ROOT'],env['OPENCLAW_ROOT'])

    def test_bad_explicit_pin_refuses_before_minting_or_fallback(self):
        not_executable=self.root/'not-executable';not_executable.write_text('fixture')
        for value in ('', 'relative/openclaw', str(self.root/'missing'), str(not_executable)):
            with self.subTest(pin=value),patch.dict(os.environ,OPENCLAW_BIN=value),patch.object(m,'native_openclaw_candidates') as fallback:
                prepared=[]
                with self.assertRaisesRegex(m.Pending,'OPENCLAW_BIN'):
                    self.send(prepare_message=lambda text:prepared.append(text) or text)
                fallback.assert_not_called();self.assertEqual(prepared,[])
                self.assertFalse(self.capture.exists())
                self.assertFalse(self.ledger.with_suffix(self.ledger.suffix+'.receipt.json').exists())

    def test_minimal_path_discovers_own_npm_bin_and_invokes_absolute_target(self):
        npm=self.root/'.npm-global/bin';npm.mkdir(parents=True)
        wrapper=npm/'openclaw';wrapper.symlink_to(self.cli)
        env=dict(os.environ,HOME=str(self.root),PATH='/usr/bin:/bin')
        env.pop('OPENCLAW_BIN',None)
        with patch.dict(os.environ,env,clear=True):
            executable,child=m.resolve_openclaw_cli(dict(os.environ))
            self.assertEqual(executable,str(self.cli.resolve()))
            self.assertEqual(child['PATH'].split(os.pathsep)[0],str(npm))
            self.assertEqual(self.send()[0],0)
        self.assertTrue(self.capture.exists())

    def test_native_fallback_uses_only_selected_candidates_with_minimal_path(self):
        env=dict(os.environ,HOME=str(self.root),PATH='/usr/bin:/bin')
        env.pop('OPENCLAW_BIN',None)
        with patch.dict(os.environ,env,clear=True),patch.object(m,'native_openclaw_candidates',return_value=[self.cli]):
            self.assertEqual(self.send()[0],0)
        paths=m.native_openclaw_candidates({'HOME':str(self.root)})
        self.assertEqual(paths[-2:],[Path('/opt/homebrew/bin/openclaw'),Path('/usr/local/bin/openclaw')])
        self.assertTrue(all(str(p).startswith(str(self.root)) for p in paths[:-2]))

    def test_post_ack_ledger_failure_retains_acceptance(self):
        with patch.dict(os.environ,CLI_BEHAVIOR='ledgerfail'):code,receipt=self.send()
        self.assertEqual(code,10);self.assertEqual(receipt['status'],'accepted');self.assertEqual(self.send()[0],7)
    def test_receipt_write_failure_prevents_send(self):
        with patch.object(m,'atomic_json',side_effect=OSError('fixture disk full')):
            with self.assertRaises(OSError):self.send()
        self.assertFalse(self.capture.exists())
    def test_actual_shell_uses_authenticated_origin_and_owner_resolver(self):
        service=self.root/'service.env';service.write_text('MC_API_TOKEN=fixture-secret\nMC_COMPANY_ID=client-a\nMC_TENANT_ID=tenant-a\nMC_INSTALLATION_ID=install-a\n')
        self.root.joinpath('.workforce-build-state.json').write_text(json.dumps(dict(self.state,launchBootstrap={'serviceEnvPath':str(service)})))
        fake=self.bin/'curl';fake.write_text('#!'+sys.executable+'\nimport sys,json,time\nconfig=sys.stdin.read()\nassert "Authorization: Bearer fixture-secret" in config\nassert "--location" not in sys.argv\n'+'data=json.loads('+repr(json.dumps(self.receipt))+')\n'+'if sys.argv[-1].endswith("/api/auth/interview-invitation"):\n data={"protocol":"interview-invitation.v1","tenantId":"tenant-a","companyId":"client-a","installationId":"install-a","host":"client.example.com","expiresAt":int(time.time())+900,"oneUse":True,"url":"https://client.example.com/interview#enroll=fixture.signature"}\nelse: assert sys.argv[-1]=="https://client.example.com/api/auth/interview-ready"\nprint(json.dumps(data))\nprint("200")\n');fake.chmod(0o755)
        env=dict(os.environ,HOME=str(self.root),OPENCLAW_WORKSPACE_ROOT=str(self.root),OPENCLAW_OWNER_CHAT_ID='123456789',MC_API_TOKEN='fixture-secret')
        env.pop('MC_API_TOKEN',None)  # fresh installer writes a service token, not ambient shell export
        run=subprocess.run(['bash',str(ROOT/'23-ai-workforce-blueprint/scripts/send-interview-link.sh'),'--dry-run'],env=env,text=True,capture_output=True)
        self.assertEqual(run.returncode,0,run.stderr);self.assertIn('https://client.example.com/interview',run.stdout);self.assertNotIn('fixture-secret',run.stdout+run.stderr);self.assertFalse(self.capture.exists())
        sent=subprocess.run(['bash',str(ROOT/'23-ai-workforce-blueprint/scripts/send-interview-link.sh')],env=env,text=True,capture_output=True)
        self.assertEqual(sent.returncode,0,sent.stderr);self.assertEqual(json.loads(sent.stdout)['status'],'accepted');self.assertEqual(json.loads(self.capture.read_text())['target'],'123456789');self.assertIn('#enroll=fixture.signature',json.loads(self.capture.read_text())['message']);self.assertNotIn('fixture.signature',sent.stdout+sent.stderr)
    def test_concurrent_invocations_send_once(self):
        script="import sys;sys.path.insert(0,sys.argv[1]);import interview_invitation as m,json;print(m.send_gateway('same message','123456789',sys.argv[2],json.loads(sys.argv[3]))[0])"
        args=[sys.executable,'-c',script,str(ROOT/'shared-utils'),str(self.ledger),json.dumps(self.context)]
        first=subprocess.Popen(args,stdout=subprocess.PIPE,text=True);second=subprocess.Popen(args,stdout=subprocess.PIPE,text=True)
        results={first.communicate(timeout=10)[0].strip(),second.communicate(timeout=10)[0].strip()}
        self.assertEqual(results,{'0','7'});self.assertEqual(len(self.ledger.read_text().splitlines()),1)
    def test_accepted_receipt_write_failure_keeps_sending_fence(self):
        write=m.atomic_json
        def fail_after_send(path,value):
            if value.get('status')=='accepted':raise OSError('fixture receipt write failed')
            return write(path,value)
        with patch.object(m,'atomic_json',side_effect=fail_after_send):
            with self.assertRaises(OSError):self.send()
        self.assertTrue(self.capture.exists());self.assertFalse(self.ledger.exists())
        with self.assertRaises(m.Pending):self.send(force=True)
    def test_prepared_origin_cannot_change_before_send(self):
        state=self.root/'state.json';state.write_text(json.dumps(self.state))
        message=self.root/'message';message.write_text('client message')
        snapshot=self.root/'resolution.json';snapshot.write_text(json.dumps(dict(self.context,origin='https://other.example.com')))
        argv=['interview_invitation.py','send','--state',str(state),'--message-file',str(message),'--target','123456789','--ledger',str(self.ledger),'--resolution-file',str(snapshot)]
        with patch.object(sys,'argv',argv),patch.object(m,'resolve_public_origin',return_value=dict(self.context)):
            self.assertEqual(m.main(),8)
        self.assertFalse(self.capture.exists())
    def test_suppressed_message_is_not_acknowledged(self):
        self.assertIsNone(m.acknowledgement({'status':'suppressed','messageId':'1','chatId':'123456789'},'123456789'))
    def test_standard_first_requires_actual_foundation_receipt(self):
        with self.assertRaises(m.Pending):self.resolve(state=dict(self.state,buildType='standard-first'))
        self.assertEqual(self.resolve(state=dict(self.state,buildType='standard-first'),receipt=dict(self.receipt,foundation={'ready':True,'missing':[]}))['origin'],'https://client.example.com')
    def test_invitation_issuance_rejects_foreign_identity_and_url(self):
        resolved=self.resolve();import time
        good=dict(protocol='interview-invitation.v1',tenantId='tenant-a',companyId='client-a',installationId='install-a',host='client.example.com',expiresAt=int(time.time())+900,oneUse=True,url='https://client.example.com/interview#enroll=fixture.signature')
        for bad in [dict(good,companyId='foreign'),dict(good,url='https://foreign.example.com/interview#enroll=fixture.signature'),dict(good,expiresAt=1),dict(good,oneUse=False),dict(good,url='https://client.example.com/interview')]:
            with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(bad)+'\n200','')),self.assertRaises(m.Pending):m.issue_invitation(resolved,self.env,'123456789')
    def test_bootstrap_service_token_handoff_without_ambient_secret(self):
        service=self.root/'service.env';service.write_text('MC_API_TOKEN="fixture-secret"\nMC_COMPANY_ID="client-a"\nMC_TENANT_ID="tenant-a"\nMC_INSTALLATION_ID="install-a"\nMC_TENANT_PUBLIC_URL="https://client.example.com"\n')
        state=dict(self.state,launchBootstrap={'serviceEnvPath':str(service)})
        env=m.load_service_environment(state,{})
        self.assertEqual(env['MC_API_TOKEN'],'fixture-secret');self.assertEqual(self.resolve(state=state,env={'UNRELATED':'value'})['companyId'],'client-a')
        with self.assertRaises(m.Pending):m.load_service_environment(state,{'MC_API_TOKEN':'another-client-token'})
        service.write_text(service.read_text().replace('client-a','foreign'))
        with self.assertRaises(m.Pending):m.load_service_environment(state,{})
    def test_service_environment_is_data_and_missing_pin_never_scans(self):
        service=self.root/'service.env';service.write_text('MC_API_TOKEN=$(touch /tmp/never-execute-invitation-env)\nMC_COMPANY_ID=client-a\nMC_TENANT_ID=tenant-a\nMC_INSTALLATION_ID=install-a\n')
        state=dict(self.state,launchBootstrap={'serviceEnvPath':str(service)})
        self.assertEqual(m.load_service_environment(state,{})['MC_API_TOKEN'],'$(touch /tmp/never-execute-invitation-env)')
        service.unlink()
        with self.assertRaises(m.Pending):m.load_service_environment(state,{})
        self.assertEqual(m.load_service_environment(self.state,{}),{})
    def test_known_expired_accepted_invitation_can_renew_without_force(self):
        import time
        now=int(time.time());self.context['invitationExpiresAt']=now+900
        self.assertEqual(self.send()[0],0);self.assertEqual(self.send()[0],7)
        with patch.object(m.time,'time',return_value=now+901):self.assertEqual(self.send()[0],0)
        self.assertEqual(len(self.ledger.read_text().splitlines()),2)
    def test_automatic_invitation_never_renews_expired_accepted_receipt(self):
        self.context['invitationExpiresAt']=1;self.assertEqual(self.send()[0],0)
        with patch.dict(os.environ,{'INTERVIEW_INVITATION_AUTOMATIC':'1'}):self.assertEqual(self.send(force=True)[0],7)
        self.assertEqual(len(self.ledger.read_text().splitlines()),1)
    def test_foreign_receipt_cannot_reuse_cooldown_or_expiry(self):
        self.assertEqual(self.send()[0],0)
        receipt=self.ledger.with_suffix(self.ledger.suffix+'.receipt.json')
        original=json.loads(receipt.read_text());original['invitationExpiresAt']=1
        for key in ('origin','companyId','tenantId','installationId','recipientHash'):
            with self.subTest(key=key):
                receipt.write_text(json.dumps(dict(original,**{key:'foreign'})))
                with self.assertRaisesRegex(m.Pending,'identity mismatch'):self.send(force=True)
        self.assertEqual(len(self.ledger.read_text().splitlines()),1)
    def test_curl_http_errors_and_redirects_refused(self):
        for stdout in [json.dumps(self.receipt)+'\n302',json.dumps(self.receipt)+'\n403','{}\n200','not-json\n200']:
            with self.subTest(output=stdout),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout,'')),self.assertRaises(m.Pending):m.resolve_public_origin(self.state,self.env)

    def test_issuer_accepts_old_and_new_ttl_but_rejects_unbounded_expiry(self):
        resolved=self.resolve()
        good=dict(protocol='interview-invitation.v1',tenantId='tenant-a',companyId='client-a',installationId='install-a',host='client.example.com',oneUse=True,url='https://client.example.com/interview#enroll=fixture.signature')
        for seconds in (900,86400,86410):
            with self.subTest(seconds=seconds),patch.object(m.time,'time',return_value=100000),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(dict(good,expiresAt=100000+seconds))+'\n200','')):
                metadata={}
                self.assertEqual(m.issue_invitation(resolved,self.env,'123456789',metadata),good['url'])
                self.assertEqual(metadata['invitationExpiresAt'],100000+seconds)
        for expiry in (100000,100000+86411,100000+172800,True,'186400'):
            with self.subTest(expiry=expiry),patch.object(m.time,'time',return_value=100000),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(dict(good,expiresAt=expiry))+'\n200','')):
                with self.assertRaisesRegex(m.Pending,'expiry invalid'):m.issue_invitation(resolved,self.env,'123456789')

    def prepare_shell_resume_fixture(self,ttl=86400):
        runtime=self.root/"client's runtime"
        workspace=self.root/"client's workspace & records"
        runtime.mkdir();workspace.mkdir()
        service=runtime/'service.env'
        service.write_text('MC_API_TOKEN=fixture-secret\nMC_COMPANY_ID=client-a\nMC_TENANT_ID=tenant-a\nMC_INSTALLATION_ID=install-a\n')
        (runtime/'openclaw.json').write_text(json.dumps({'agents':{'defaults':{'workspace':str(workspace)}}}))
        state=workspace/'.workforce-build-state.json'
        state.write_text(json.dumps(dict(self.state,companySlug='client-a',launchBootstrap={'serviceEnvPath':str(service)},savedAnswers={'question-1':'Existing client answer'},interviewSessionId='same-client-session')))
        # A plausible unrelated HOME workspace must never be selected.
        foreign=self.root/'.openclaw/workspace'
        foreign.mkdir(parents=True)
        foreign_state=foreign/'.workforce-build-state.json'
        foreign_state.write_text(json.dumps(dict(self.state,companyId='foreign-company')))
        mint_log=self.root/'issued.log'
        fake=self.bin/'curl'
        fake.write_text('#!'+sys.executable+'\nimport sys,json,time,os\nconfig=sys.stdin.read()\nassert "Authorization: Bearer fixture-secret" in config\n'+'data=json.loads('+repr(json.dumps(self.receipt))+')\n'+
            'if sys.argv[-1].endswith("/api/auth/interview-invitation"):\n with open(os.environ["MINT_LOG"],"a") as out: out.write("issued\\n")\n data={"protocol":"interview-invitation.v1","tenantId":"tenant-a","companyId":"client-a","installationId":"install-a","host":"client.example.com","expiresAt":int(time.time())+int(os.environ["FIXTURE_TTL"]),"oneUse":True,"url":"https://client.example.com/interview#enroll=fixture.signature"}\nelse: assert sys.argv[-1]=="https://client.example.com/api/auth/interview-ready"\nprint(json.dumps(data))\nprint("200")\n')
        fake.chmod(0o755)
        env={key:value for key,value in os.environ.items() if not key.startswith(('OPENCLAW_','OC_','MC_')) and key not in ('FORCE','INTERVIEW_INVITATION_AUTOMATIC')}
        env.update(HOME=str(self.root),OPENCLAW_ROOT=str(runtime),OPENCLAW_OWNER_CHAT_ID='123456789',MINT_LOG=str(mint_log),FIXTURE_TTL=str(ttl))
        return state,foreign_state,mint_log,env

    def invoke_sender(self,env,*args):
        return subprocess.run(['/bin/bash',str(ROOT/'23-ai-workforce-blueprint/scripts/send-interview-link.sh'),*args],env=env,capture_output=True,text=True,timeout=20)

    def test_resume_renew_keeps_saved_identity_answers_and_stable_authenticated_entry(self):
        state,foreign,mints,env=self.prepare_shell_resume_fixture()
        before=state.read_bytes();foreign_before=foreign.read_bytes()
        first=self.invoke_sender(env)
        self.assertEqual(first.returncode,0,first.stderr)
        receipt_path=state.parent/'company-discovery/.interview-link-sends.log.receipt.json'
        accepted=json.loads(receipt_path.read_text())
        self.assertGreater(accepted['invitationExpiresAt']-accepted['epoch'],86390)
        guarded=self.invoke_sender(env,'--resume')
        self.assertEqual(guarded.returncode,7,guarded.stderr)
        self.assertIn('--renew',guarded.stdout)
        renewed=self.invoke_sender(env,'--renew')
        self.assertEqual(renewed.returncode,0,renewed.stderr)
        message=json.loads(self.capture.read_text())['message']
        self.assertIn('Welcome back',message)
        self.assertEqual(message.count('#enroll='),1)
        self.assertIn('after signing in: https://client.example.com/interview\n',message)
        self.assertIn('resume my interview',message)
        self.assertIn('expires on ',message);self.assertIn(' UTC.',message)
        self.assertNotIn('{{INVITATION_VALIDITY}}',message)
        self.assertEqual(state.read_bytes(),before);self.assertEqual(foreign.read_bytes(),foreign_before)
        self.assertEqual(len(mints.read_text().splitlines()),2)
        self.assertNotIn('fixture.signature',renewed.stdout+renewed.stderr)

    def test_old_15_minute_issuer_has_truthful_expiry_and_can_renew_expired_link(self):
        state,_,mints,env=self.prepare_shell_resume_fixture(ttl=900)
        first=self.invoke_sender(env)
        self.assertEqual(first.returncode,0,first.stderr)
        receipt_path=state.parent/'company-discovery/.interview-link-sends.log.receipt.json'
        accepted=json.loads(receipt_path.read_text())
        from datetime import datetime,timezone
        deadline=datetime.fromtimestamp(accepted['invitationExpiresAt'],timezone.utc).strftime('%b %d, %Y at %H:%M UTC')
        self.assertIn(deadline,json.loads(self.capture.read_text())['message'])
        self.assertNotIn('24 hours',json.loads(self.capture.read_text())['message'])
        accepted['invitationExpiresAt']=1;receipt_path.write_text(json.dumps(accepted))
        resumed=self.invoke_sender(env,'--resume')
        self.assertEqual(resumed.returncode,0,resumed.stderr)
        self.assertEqual(len(mints.read_text().splitlines()),2)

    def test_explicit_renew_cannot_bypass_unknown_delivery_or_foreign_receipt(self):
        state,_,mints,env=self.prepare_shell_resume_fixture()
        receipt_path=state.parent/'company-discovery/.interview-link-sends.log.receipt.json'
        receipt_path.parent.mkdir(parents=True)
        import hashlib
        base=dict(self.context,recipientHash=hashlib.sha256(b'123456789').hexdigest(),epoch=1,invitationExpiresAt=1)
        for previous in (dict(base,status='uncertain'),dict(base,status='sending'),dict(base,status='accepted',companyId='foreign')):
            receipt_path.write_text(json.dumps(previous))
            rejected=self.invoke_sender(env,'--renew')
            self.assertEqual(rejected.returncode,8,rejected.stderr)
            self.assertFalse(mints.exists());self.assertFalse(self.capture.exists())
            self.assertEqual(json.loads(receipt_path.read_text()),previous)

    def test_conflicting_selected_workspace_pins_refuse_before_issue_or_delivery(self):
        state,foreign,mints,env=self.prepare_shell_resume_fixture()
        env.update(OPENCLAW_WORKSPACE_ROOT=str(state.parent),OPENCLAW_WORKSPACE_PATH=str(foreign.parent))
        result=self.invoke_sender(env,'--renew')
        self.assertEqual(result.returncode,8,result.stderr)
        self.assertFalse(mints.exists());self.assertFalse(self.capture.exists())

    def test_completed_interview_refuses_renew_without_changing_answers(self):
        state,_,mints,env=self.prepare_shell_resume_fixture()
        data=json.loads(state.read_text());data['interviewComplete']=True;state.write_text(json.dumps(data))
        before=state.read_bytes()
        result=self.invoke_sender(env,'--renew')
        self.assertEqual(result.returncode,3,result.stderr)
        self.assertFalse(mints.exists());self.assertFalse(self.capture.exists())
        self.assertEqual(state.read_bytes(),before)

if __name__=='__main__':unittest.main()
