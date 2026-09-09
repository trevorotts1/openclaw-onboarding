import importlib.util,json,unittest
from pathlib import Path
BASE=Path(__file__).resolve().parents[2]/'35-social-media-planner/config/n8n'
spec=importlib.util.spec_from_file_location('prep',BASE/'prepare-import.py');prep=importlib.util.module_from_spec(spec);spec.loader.exec_module(prep)
class ImportContract(unittest.TestCase):
 def setUp(self):
  self.source=json.loads((BASE/'social-planner-sheet-create.json').read_text());self.credentials={t:{'id':'fixture','name':'sandbox ref'} for t in ['googleDriveOAuth2Api','googleSheetsOAuth2Api']}
 def test_api_allowlist_and_complete_auth_binding(self):
  out=prep.build(self.source,self.credentials,'sandbox-verified')
  self.assertEqual(set(out),{'name','nodes','connections','settings'})
  for n in out['nodes']:
   if n['type'].endswith(('.httpRequest','.googleDrive')):self.assertTrue(n['credentials'])
   if n['type'].endswith('.webhook'):self.assertTrue(n['parameters']['path'].startswith('sandbox-verified/'))
  self.assertFalse(any(n.get('credentials') for n in self.source['nodes']))
 def test_missing_or_secret_credentials_fail_closed(self):
  for value in [{},{'googleDriveOAuth2Api':{'token':'should-not-be-here'}},{**self.credentials,'apiKey':'secret'}]:
   with self.subTest(value=list(value)):
    with self.assertRaises(ValueError):prep.build(self.source,value)
if __name__=='__main__':unittest.main()
