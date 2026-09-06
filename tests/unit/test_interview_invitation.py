import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('invitation',ROOT/'shared-utils/interview_invitation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

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
        self.process_env=patch.dict(os.environ,{'PATH':str(self.bin)+os.pathsep+os.environ['PATH'],'CAPTURE':str(self.capture),'LEDGER':str(self.ledger)},clear=False);self.process_env.start();self.addCleanup(self.process_env.stop)
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
        with patch.dict(os.environ,CLI_BEHAVIOR='timeout'):code,receipt=self.send(timeout=.05)
        self.assertEqual(code,9);self.assertTrue(self.capture.exists());self.assertFalse(self.ledger.exists())
        with self.assertRaises(m.Pending):self.send(force=True)
    def test_exit_zero_without_message_id_is_not_acceptance(self):
        with patch.dict(os.environ,CLI_BEHAVIOR='malformed'):self.assertEqual(self.send()[0],9)
    def test_foreign_recipient_ack_not_accepted(self):
        self.assertIsNone(m.acknowledgement({'messageId':'1','chatId':'foreign'},'123456789'))
    def test_missing_cli_does_not_send_or_write_success(self):
        with patch.object(m.shutil,'which',return_value=None):self.assertEqual(self.send()[0],5)
        self.assertFalse(self.capture.exists());self.assertFalse(self.ledger.exists())
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

if __name__=='__main__':unittest.main()
