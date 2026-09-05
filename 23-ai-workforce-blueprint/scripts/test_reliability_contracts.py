"""Isolated production-helper regressions for onboarding/closeout reliability."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parent))
from workforce_state import read,commit,atomic_write,update,StateConflict
from workforce_completion import finalize,finalize_closeout,closeout_artifact_digest,REQUIRED_CHECKS,CC_PHASES
from generated_context import refresh_context,write_new
REPO=Path(__file__).resolve().parents[2]

def increment(args):
    path,key=args
    update(path,lambda s:s.update({key:s.get(key,0)+1}))

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class Reliability(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.state=self.root/'state.json';self.art=self.root/'company'/'departments';self.art.mkdir(parents=True);(self.art/'role.md').write_text('Current fixture role')
        atomic_write(self.state,{'companyId':'fixture','companySlug':'fixture','buildId':'build-1','interviewComplete':True,'interviewQc':{'status':'pass'},'interviewCompletedAt':'now','roleLibraryStatus':'done','sopLibraryStatus':'done','commsAutomationStatus':'not-applicable','departments':[{'slug':'engineering','status':'done'}]})
    def tearDown(self):self.temp.cleanup()
    def passed(self):return finalize(self.state,{k:0 for k in REQUIRED_CHECKS},self.art)
    def test_missing_and_failed_checks_never_complete(self):
        for value in (None,1,124,127):
            for check in REQUIRED_CHECKS:
                results={k:0 for k in REQUIRED_CHECKS};results[check]=value
                self.assertFalse(finalize(self.state,results,self.art));self.assertNotIn('buildCompletedAt',read(self.state))
    def test_all_checks_and_comms_required(self):
        self.assertTrue(self.passed());update(self.state,lambda s:s.update(commsAutomationStatus='pending'))
        self.assertFalse(finalize(self.state));self.assertNotIn('buildCompletedAt',read(self.state))
    def test_false_historical_stamp_cleared(self):
        update(self.state,lambda s:s.update(buildCompletedAt='old'))
        self.assertFalse(finalize(self.state));self.assertNotIn('buildCompletedAt',read(self.state))
    def test_changed_artifact_and_answers_invalidate(self):
        self.assertTrue(self.passed());(self.art/'role.md').write_text('Changed after verification')
        self.assertFalse(finalize(self.state));self.assertTrue(self.passed())
        update(self.state,lambda s:s.update(interviewCompletedAt='new'))
        self.assertFalse(finalize(self.state))
    def test_interview_eligibility_table(self):
        from interview_eligibility import eligible_status,eligible_returncode
        for value in ('pass','needs-review'):self.assertTrue(eligible_status(value))
        for value in ('pending','fail','error','',None):self.assertFalse(eligible_status(value))
        for value in (0,2):self.assertTrue(eligible_returncode(value))
        for value in (1,3,124,127,None):self.assertFalse(eligible_returncode(value))
        update(self.state,lambda s:s.update(interviewQc={'status':'needs-review','issues':['advisory']}));self.assertTrue(self.passed())
        self.assertEqual(read(self.state)['interviewQc']['issues'],['advisory'])
    def test_standard_confirmations(self):
        update(self.state,lambda s:s.update(buildType='standard-first'))
        self.assertFalse(self.passed());update(self.state,lambda s:s.update(confirmationsComplete=True));self.assertTrue(self.passed())
    def test_runner_claim_survives_parent_death_until_child_finishes(self):
        import signal,time
        claim=str(self.state)+'.runner';helper=Path(__file__).parent/'workforce_state.py';marker=self.root/'child-finished'
        code="import os,sys,time;from workforce_state import owns_runner;assert owns_runner(sys.argv[1]);print('held',flush=True);time.sleep(1);open(sys.argv[2],'w').write('finished')"
        env=dict(os.environ,PYTHONPATH=str(helper.parent),WORKFORCE_STATE_LOCK_TIMEOUT='0.01')
        process=subprocess.Popen([sys.executable,str(helper),'run',claim,sys.executable,'-c',code,claim,str(marker)],env=env,stdout=subprocess.PIPE,text=True)
        self.assertEqual(process.stdout.readline().strip(),'held')
        process.kill();process.wait(timeout=3)
        blocked=subprocess.run([sys.executable,str(helper),'run',claim,sys.executable,'-c','pass'],env=env,capture_output=True,timeout=3)
        self.assertEqual(blocked.returncode,75)
        deadline=time.monotonic()+4
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.05)
        self.assertTrue(marker.exists())
        free=subprocess.run([sys.executable,str(helper),'run',claim,sys.executable,'-c','pass'],env=env,capture_output=True,timeout=3)
        self.assertEqual(free.returncode,0,free.stderr)
        process.stdout.close()
    def test_snapshot_merge_preserves_independent_answers(self):
        a=read(self.state);b=read(self.state);a['answer']='saved';commit(self.state,a);b['resumeAttempts']=3;commit(self.state,b)
        self.assertEqual(read(self.state)['answer'],'saved');self.assertEqual(read(self.state)['resumeAttempts'],3)
    def test_snapshot_conflict_rejects_stale_overwrite(self):
        a=read(self.state);b=read(self.state);a['companySlug']='a';b['companySlug']='b';commit(self.state,a)
        with self.assertRaises(StateConflict):commit(self.state,b)
        self.assertEqual(read(self.state)['companySlug'],'a')
    def test_concurrent_process_state_writes(self):
        with ProcessPoolExecutor(max_workers=4) as pool:list(pool.map(increment,[(str(self.state),'counter')]*20))
        self.assertEqual(read(self.state)['counter'],20)
    def test_managed_context_preserves_owner_edits(self):
        target=self.root/'IDENTITY.md';target.write_text('Owner identity paragraph\n')
        refresh_context(target,'fixture',{'department_tools':'A'});refresh_context(target,'fixture',{'department_tools':'B'})
        self.assertIn('Owner identity paragraph',target.read_text());self.assertIn('**department tools:** B',target.read_text());self.assertNotIn('**department tools:** A',target.read_text())
        target.write_text(target.read_text().replace('department tools:** B','department tools:** owner override'))
        with self.assertRaises(ValueError):refresh_context(target,'fixture',{'department_tools':'C'})
    def test_repair_does_not_overwrite_memory(self):
        target=self.root/'MEMORY.md';target.write_text('Real owner history');self.assertFalse(write_new(target,'generic'));self.assertEqual(target.read_text(),'Real owner history')
    def test_closeout_requires_current_board_quality_and_receipt(self):
        self.assertTrue(self.passed())
        def ready(s):
            s.update({k:True for k in CC_PHASES});s.update(commandCenterStatus='done',infographic1Url='one',infographic2Url='two',celebrationVideoUrl='video',notionRootPageUrl='doc',commandCenterUrl='https://fixture.invalid')
            s['telegramDeliveryVerification']={'status':'pass','authority':'gateway-json-registry','buildId':s['buildId'],'artifactDigest':closeout_artifact_digest(s),'results':[{'n':n,'verdict':'pass-present','messageId':str(n)} for n in (1,6,7)]}
        update(self.state,ready);self.assertTrue(finalize_closeout(self.state))
        update(self.state,lambda s:s.update(qualityHeld=['orgchart']));self.assertFalse(finalize_closeout(self.state));self.assertEqual(read(self.state)['closeoutStatus'],'partial')
        update(self.state,lambda s:s.update(qualityHeld=[],commandCenterStatus='done-degraded'));self.assertFalse(finalize_closeout(self.state))
        update(self.state,lambda s:s.update(commandCenterStatus='done',infographic1Url='new'));self.assertFalse(finalize_closeout(self.state))
    def test_missing_gateway_authority_cannot_verify(self):
        state=self.root/'receipt.json';atomic_write(state,{'ownerChat':'fixture','messagesDelivered':[{'n':n,'messageId':'fake','chatId':'fixture','ts':'2026-09-05T00:00:00Z','status':'send-failed'} for n in (1,6,7)]})
        env=dict(os.environ,ZHC_STATE_FILE=str(state),ZHC_LOG_FILE=str(self.root/'log'),ZHC_TG_REGISTRY=str(self.root/'absent'))
        run=subprocess.run(['bash',str(REPO/'37-zhc-closeout/scripts/verify-telegram-delivery.sh')],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertNotEqual(run.returncode,0)
    def test_missing_registry_clears_previous_success(self):
        update(self.state,lambda s:s.update(telegramDeliveryVerification={'status':'pass'}))
        env=dict(os.environ,ZHC_STATE_FILE=str(self.state),ZHC_LOG_FILE=str(self.root/'log'),ZHC_TG_REGISTRY=str(self.root/'absent'))
        run=subprocess.run(['bash',str(REPO/'37-zhc-closeout/scripts/verify-telegram-delivery.sh')],env=env,capture_output=True,timeout=10)
        self.assertEqual(run.returncode,7);self.assertEqual(read(self.state)['telegramDeliveryVerification']['status'],'pending')
    def test_real_gateway_receipts_bind_chat_artifact_and_build(self):
        from datetime import datetime,timezone
        update(self.state,lambda s:s.update(ownerChat='owner',messagesDelivered=[{'n':n,'messageId':str(n),'chatId':'owner','status':'sent','ts':datetime.now(timezone.utc).isoformat()} for n in (1,6,7)]))
        registry=self.root/'registry.json';atomic_write(registry,{'owner':{str(n):1788620000000 for n in (1,6,7)}})
        env=dict(os.environ,ZHC_STATE_FILE=str(self.state),ZHC_LOG_FILE=str(self.root/'log'),ZHC_TG_REGISTRY=str(registry))
        run=subprocess.run(['bash',str(REPO/'37-zhc-closeout/scripts/verify-telegram-delivery.sh')],env=env,capture_output=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr);receipt=read(self.state)['telegramDeliveryVerification']
        self.assertEqual(receipt['status'],'pass');self.assertEqual(receipt['buildId'],'build-1');self.assertEqual(len(receipt['results']),3)
        update(self.state,lambda s:s.pop('telegramDeliveryReceipts',None)) # A different chat cannot establish previously unverified delivery.
        atomic_write(registry,{'other':{str(n):1788620000000 for n in (1,6,7)}})
        run=subprocess.run(['bash',str(REPO/'37-zhc-closeout/scripts/verify-telegram-delivery.sh')],env=env,capture_output=True,timeout=10)
        self.assertNotEqual(run.returncode,0);self.assertEqual(read(self.state)['telegramDeliveryVerification']['status'],'fail')
    def test_tenant_probe_requires_exact_identity(self):
        m=load('tenant_fixture',REPO/'32-command-center-setup/scripts/verify-tenant-readiness.py')
        env={'MC_TENANT_ID':'tenant','MC_COMPANY_ID':'fixture','MC_INSTALLATION_ID':'install','MC_TENANT_PUBLIC_URL':'https://client.invalid:443','MC_API_TOKEN':'fixture-only'}
        response={'ready':True,'missing':[],'tenantId':'tenant','companyId':'fixture','installationId':'install','host':'client.invalid','kind':'self','protocol':'interview.v1'}
        self.assertTrue(m.verify(read(self.state),env,lambda:response)['ready'])
        for key in ('tenantId','companyId','installationId','host','protocol'):
            changed=dict(response);changed[key]='foreign';self.assertFalse(m.verify(read(self.state),env,lambda:changed)['ready'])
        self.assertFalse(m.verify(read(self.state),{},lambda:response)['ready'])
    def test_matrix_claims_only_domain_matching_and_honest_preview(self):
        source=(REPO/'23-ai-workforce-blueprint/scripts/build-workforce.py').read_text();tree=ast.parse(source)
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='generate_persona_matrix')
        from datetime import datetime
        ns={'os':os,'datetime':datetime,'DEPARTMENTS_DIR':str(self.root),'sys':sys};exec(compile(ast.Module(body=[node],type_ignores=[]),'builder','exec'),ns)
        catalog={'version':'fixture-v1','personas':{str(n):{'author':'A','book':'B','domain':['marketing'],'perspective':['fixture']} for n in range(12)}}
        ns['generate_persona_matrix']({'marketing':{'emoji':'M','name':'Marketing','head':'Lead'},'unmapped':{'emoji':'U','name':'Unmapped','head':'Lead'}},catalog,'Fixture')
        text=(self.root/'persona-matrix.md').read_text();self.assertIn('Preview shows 10 of 12',text);self.assertIn('ID: `0`',text);self.assertIn('qualification pending',text)
        self.assertNotIn('already been verified',text);self.assertIn('None yet',text.split('Unmapped')[1])
    def test_unsupported_retirement_status_cannot_complete(self):
        update(self.state,lambda s:s.update(departments=[{'slug':'engineering','status':'retired'}]))
        self.assertFalse(self.passed())
    def test_explicit_company_does_not_fall_back(self):
        platform=load('fixture_platform',REPO/'shared-utils/detect_platform.py');(self.root/'other').mkdir()
        old=os.environ.get('OPENCLAW_COMPANY_SLUG');os.environ['OPENCLAW_COMPANY_SLUG']='missing'
        try:self.assertIsNone(platform.resolve_active_company_dir(self.root))
        finally:
            if old is None:os.environ.pop('OPENCLAW_COMPANY_SLUG',None)
            else:os.environ['OPENCLAW_COMPANY_SLUG']=old
    def test_skeleton_is_not_complete_role(self):
        source=(REPO/'scripts/prebuild-standard-workforce.py').read_text();tree=ast.parse(source);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_dept_has_roles'];ns={};exec(compile(ast.Module(body=nodes,type_ignores=[]),'prebuild','exec'),ns)
        dept=self.root/'engineering';dept.mkdir();(dept/'ROSTER.md').write_text('skeleton');self.assertFalse(ns['_dept_has_roles'](dept))
    def test_reviewer_scope_and_revision(self):
        m=load('fixture_move',REPO/'32-command-center-setup/scripts/move-task.py');db=sqlite3.connect(':memory:')
        db.executescript("CREATE TABLE tasks(id TEXT,status TEXT,assigned_agent_id TEXT,created_by_agent_id TEXT,workspace_id TEXT,company_id TEXT);CREATE TABLE agents(id TEXT,workspace_id TEXT,role_type TEXT);CREATE TABLE workspaces(id TEXT,company_id TEXT);CREATE TABLE task_deliverables(id TEXT,task_id TEXT,sha256 TEXT,path TEXT,updated_at TEXT);INSERT INTO tasks VALUES('t','review','builder','creator','eng','fixture');INSERT INTO workspaces VALUES('eng','fixture');INSERT INTO agents VALUES('qc','eng','qc'),('foreign','sales','qc'),('builder','eng','qc'),('writer','eng','specialist');INSERT INTO task_deliverables VALUES('d','t','hash',NULL,'1');")
        for actor in ('','absent','builder','foreign','writer'):
            self.assertEqual(m.cmd_signoff(db,SimpleNamespace(task='t',by=actor,role=m.DA_ROLE,verdict='pass',note='')),2)
        self.assertEqual(m.cmd_signoff(db,SimpleNamespace(task='t',by='qc',role=m.DA_ROLE,verdict='pass',note='')),0);self.assertTrue(m._has_passing_da_signoff(db,'t'))
        db.execute("UPDATE task_deliverables SET sha256='new'");self.assertFalse(m._has_passing_da_signoff(db,'t'))

class RoutingTransport(unittest.TestCase):
    def test_retry_identity_permanent_error_and_deadline(self):
        import http.server, threading, time
        bodies=[];statuses=[503,200]
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                bodies.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                status=statuses.pop(0) if statuses else 200
                if status==999:
                    time.sleep(3);return
                self.send_response(status);self.send_header('Retry-After','0');self.end_headers()
                self.wfile.write(b'{}')
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                env=dict(os.environ,HOME=td,MC_API_TOKEN='fixture-only',WEBHOOK_SECRET='fixture-only',MC_ROUTE_EVENT_ID='fixture-event',MC_ROUTE_INGEST_URL=f'http://127.0.0.1:{server.server_port}/api/tasks/ingest',MC_ROUTE_CONNECT_TIMEOUT='1',MC_ROUTE_REQUEST_TIMEOUT='1',MC_ROUTE_TOTAL_TIMEOUT='2')
                cmd=['bash',str(REPO/'scripts/mc-route.sh'),'engineering','same title','fixture instructions']
                result=subprocess.run(cmd,env=env,capture_output=True,timeout=8)
                self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(len(bodies),2);self.assertEqual(bodies[0],bodies[1]);self.assertEqual(bodies[0]['idempotency_key'],'fixture-event')
                bodies.clear();statuses[:]=[401]
                self.assertNotEqual(subprocess.run(cmd,env=env,capture_output=True,timeout=8).returncode,0);self.assertEqual(len(bodies),1)
                bodies.clear();statuses[:]=[999,999];start=time.monotonic()
                self.assertNotEqual(subprocess.run(cmd,env=env,capture_output=True,timeout=8).returncode,0);self.assertLess(time.monotonic()-start,4)
                env.pop('MC_ROUTE_EVENT_ID');bodies.clear();statuses[:]=[200,200]
                for _ in range(2):self.assertEqual(subprocess.run(cmd,env=env,capture_output=True,timeout=8).returncode,0)
                self.assertNotEqual(bodies[0]['idempotency_key'],bodies[1]['idempotency_key'])
        finally:server.shutdown();server.server_close()

class RetirementScope(unittest.TestCase):
    def test_actual_archive_query_scopes_company(self):
        source=(REPO/'23-ai-workforce-blueprint/scripts/retire-confirmed-decline.sh').read_text()
        marker='if ! python3 - "$DB_PATH" "$TARGETS_JSON" "$COMPANY_ID" <<'+"'PY'"+'\n'
        code=source.split(marker,1)[1].split('\nPY\n',1)[0]
        with tempfile.TemporaryDirectory() as td:
            dbpath=Path(td)/'fixture.db';db=sqlite3.connect(dbpath)
            db.executescript("CREATE TABLE workspaces(id TEXT,slug TEXT,company_id TEXT,archived_at TEXT,archived_reason TEXT,updated_at TEXT);INSERT INTO workspaces VALUES('a-eng','engineering','a',NULL,NULL,NULL),('b-eng','engineering','b',NULL,NULL,NULL);")
            subprocess.run([sys.executable,'-',str(dbpath),'["engineering"]','a'],input=code,text=True,capture_output=True,check=True)
            self.assertEqual(db.execute('SELECT company_id,archived_at IS NOT NULL FROM workspaces ORDER BY company_id').fetchall(),[('a',1),('b',0)])

if __name__=='__main__':unittest.main()
