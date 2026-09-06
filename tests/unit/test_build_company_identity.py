"""Execute the real setup function under a fresh isolated process/environment."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class CompanyIdentity(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.state=self.root/'state.json';self.uuid='485d0bfa-e620-45f6-958d-90b20fb303bd'
  self.company=self.root/'pinned-client';self.company.mkdir();(self.company/'company-config.json').write_text(json.dumps({'company_id':self.uuid}))
  self.state.write_text(json.dumps({'companyRoot':str(self.company),'companyId':self.uuid,'companySlug':'client-a','interviewComplete':True,'interviewProgress':{'answer':'preserve'}}))
  self.env=dict(os.environ,HOME=str(self.root/'home'),MASTER_FILES_DIR=str(self.root/'master'),OPENCLAW_ROOT=str(self.root/'runtime'),OPENCLAW_WORKSPACE_ROOT=str(self.root/'workspace'),WORKFORCE_BUILD_STATE_FILE=str(self.state))
  for key in ('MC_COMPANY_ID','ZERO_HUMAN_COMPANY_DIR','OPENCLAW_COMPANY_SLUG'):self.env.pop(key,None)
 def execute(self):
  script="""import importlib.util,sys,os,json,subprocess
spec=importlib.util.spec_from_file_location('real_builder',sys.argv[1]);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.resolve_company_paths('Display name is not the database ID')
print(module.COMPANY_DIR)
print(subprocess.check_output([sys.executable,'-c',\"import os;print(os.environ['MC_COMPANY_ID'])\"],text=True).strip())
"""
  return subprocess.run([sys.executable,'-c',script,str(ROOT/'23-ai-workforce-blueprint/scripts/build-workforce.py')],env=self.env,text=True,capture_output=True,timeout=15)
 def test_canonical_uuid_reaches_real_child_environment(self):
  result=self.execute();self.assertEqual(result.returncode,0,result.stderr);self.assertIn(self.uuid,result.stdout);self.assertIn(str(self.company),result.stdout)
  state=json.loads(self.state.read_text());self.assertEqual(state['companyId'],self.uuid);self.assertEqual(state['interviewProgress']['answer'],'preserve')
  self.assertTrue((self.company/'departments').is_dir())
 def test_foreign_ambient_id_refuses_before_state_or_department_mutation(self):
  self.env['MC_COMPANY_ID']='foreign-company';before=self.state.read_bytes();result=self.execute()
  self.assertNotEqual(result.returncode,0);self.assertIn('state/environment identity mismatch',result.stderr)
  self.assertEqual(self.state.read_bytes(),before);self.assertFalse((self.company/'departments').exists())
 def test_foreign_root_or_root_config_refuses_before_mutation(self):
  before=self.state.read_bytes();self.env['ZERO_HUMAN_COMPANY_DIR']=str(self.root/'foreign')
  result=self.execute();self.assertNotEqual(result.returncode,0);self.assertIn('root mismatch',result.stderr)
  self.assertEqual(self.state.read_bytes(),before);self.assertFalse((self.root/'foreign').exists())
  self.env.pop('ZERO_HUMAN_COMPANY_DIR');(self.company/'company-config.json').write_text(json.dumps({'company_id':'foreign'}))
  result=self.execute();self.assertNotEqual(result.returncode,0);self.assertIn('config identity mismatch',result.stderr)
  self.assertEqual(self.state.read_bytes(),before);self.assertFalse((self.company/'departments').exists())
if __name__=='__main__':unittest.main()
