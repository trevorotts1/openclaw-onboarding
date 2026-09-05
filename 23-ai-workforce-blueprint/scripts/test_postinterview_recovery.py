"""Bounded regression fixtures for independently reviewed retirement/cleanup gaps."""
import importlib.util,json,os,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from workforce_state import atomic_write,read
REPO=Path(__file__).resolve().parents[2]
SOURCE=(Path(__file__).parent/'retire-confirmed-decline.sh').read_text()
IDENTITY=SOURCE.split("<<'PYIDENTITY'\n",1)[1].split('\nPYIDENTITY',1)[0]
CONFIG=SOURCE.split('"$COMPANY_DIR" "$COMPANY_ID" <<'+"'PY'\n",1)[1].split('\nPY\n',1)[0]
class Recovery(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.company=self.root/'acme-001';self.company.mkdir();self.state=self.root/'state.json';self.db=self.root/'cc.db'
  atomic_write(self.state,{'companySlug':'acme-001'})
  with sqlite3.connect(self.db) as db:db.executescript("CREATE TABLE companies(id TEXT,slug TEXT);INSERT INTO companies VALUES('uuid-own','acme-001'),('uuid-foreign','foreign');")
 def tearDown(self):self.tmp.cleanup()
 def resolve(self):return subprocess.run([sys.executable,'-',str(self.state),str(self.company),str(self.db),'0'],input=IDENTITY,text=True,capture_output=True,timeout=5)
 def test_registry_resolves_uuid_not_display_slug(self):
  result=self.resolve();self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'uuid-own')
 def test_config_and_database_mismatch_refuse(self):
  atomic_write(self.company/'company-config.json',{'companyId':'uuid-foreign','slug':'acme-001'});self.assertNotEqual(self.resolve().returncode,0)
  atomic_write(self.company/'company-config.json',{'company_id':'uuid-own','companyId':'uuid-foreign'});self.assertNotEqual(self.resolve().returncode,0)
 def test_missing_registry_mapping_refuses(self):
  with sqlite3.connect(self.db) as db:db.execute("DELETE FROM companies WHERE id='uuid-own'")
  self.assertNotEqual(self.resolve().returncode,0)
 def test_archive_schema_is_complete_before_mutation(self):
  probe=SOURCE.split("<<'PYSCOPE'\n",1)[1].split('\nPYSCOPE',1)[0]
  with sqlite3.connect(self.db) as db:
   db.executescript("CREATE TABLE workspaces(company_id TEXT,archived_at TEXT,archived_reason TEXT);INSERT INTO workspaces VALUES('uuid-own',NULL,NULL)")
  args=[sys.executable,'-',str(self.db),'uuid-own']
  result=subprocess.run(args,input=probe,text=True,capture_output=True,timeout=5)
  self.assertNotEqual(result.returncode,0)
  with sqlite3.connect(self.db) as db:db.execute('ALTER TABLE workspaces ADD COLUMN updated_at TEXT')
  result=subprocess.run(args,input=probe,text=True,capture_output=True,timeout=5)
  self.assertEqual(result.returncode,0,result.stderr)
 def test_config_read_error_cannot_verify_retirement(self):
  config=self.root/'openclaw.json';config.write_text('{invalid')
  env=dict(os.environ,PYTHONPATH=str(Path(__file__).parent))
  result=subprocess.run([sys.executable,'-',str(config),'["engineering"]',str(self.company),'uuid-own'],input=CONFIG,text=True,capture_output=True,env=env,timeout=5)
  self.assertNotEqual(result.returncode,0)
 def test_other_company_agent_is_preserved(self):
  config=self.root/'openclaw.json';atomic_write(config,{'agents':{'list':[{'id':'dept-engineering','workspace':str(self.company/'departments/engineering')},{'id':'dept-engineering','workspace':str(self.root/'foreign/departments/engineering')}]}})
  env=dict(os.environ,PYTHONPATH=str(Path(__file__).parent))
  result=subprocess.run([sys.executable,'-',str(config),'["engineering"]',str(self.company),'uuid-own'],input=CONFIG,text=True,capture_output=True,env=env,timeout=5)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(len(read(config)['agents']['list']),1);self.assertIn('/foreign/',read(config)['agents']['list'][0]['workspace'])
 def test_prebuild_corrupt_state_preserves_bytes(self):
  import ast
  source=(REPO/'scripts/prebuild-standard-workforce.py').read_text();tree=ast.parse(source)
  names={'_write_prebuild_state','_load_state','_atomic_write_json'}
  nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
  ns={'Path':Path,'json':json,'os':os,'sys':sys,'_resolve_skill23_scripts':lambda:Path(__file__).parent}
  exec(compile(ast.Module(body=nodes,type_ignores=[]),'prebuild','exec'),ns)
  original='{corrupt interview state';self.state.write_text(original)
  with self.assertRaises((ValueError,json.JSONDecodeError)):ns['_write_prebuild_state'](self.state,{'status':'pending'},True)
  self.assertEqual(self.state.read_text(),original)
 def test_cleanup_retries_nudge_before_removing_recovery(self):
  path=REPO/'37-zhc-closeout/scripts/cleanup-closeout.py';spec=importlib.util.spec_from_file_location('cleanup_fixture',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  atomic_write(self.state,{'interviewNudgeUuid':'own-nudge','closeoutResumeUuid':'own-resume','closeoutCleanupPending':True});calls=[]
  self.assertFalse(module.cleanup_records(self.state,lambda identity:calls.append(identity) or False));self.assertEqual(calls,['own-nudge']);self.assertEqual(read(self.state)['closeoutResumeUuid'],'own-resume')
  calls=[];self.assertTrue(module.cleanup_records(self.state,lambda identity:calls.append(identity) or True));self.assertEqual(calls,['own-nudge','own-resume']);self.assertNotIn('closeoutResumeUuid',read(self.state));self.assertFalse(read(self.state)['closeoutCleanupPending'])
if __name__=='__main__':unittest.main()
