"""Execute actual exported Code/HTTP expressions; mock only Google I/O."""
import json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WORKFLOW=ROOT/'35-social-media-planner/config/n8n/social-planner-sheet-create.json'
RUNNER=Path(__file__).parent/'fixtures/create_graph_runner.cjs'
BODY=dict(brandName='Sandbox Company',clientEmail='sandbox@example.invalid',company_id='sandbox_one',planner_kind='social',templateSheetId='template_123',timezone='America/New_York')
def run(bodies=None,**kw):
 p=subprocess.run(['node',str(RUNNER)],input=json.dumps(dict(workflow=str(WORKFLOW),bodies=bodies or [BODY],**kw)),text=True,capture_output=True,check=True)
 return json.loads(p.stdout)
class CreateGraph(unittest.TestCase):
 def test_new_copy_real_context_and_valid_formatting(self):
  r=run();self.assertEqual(r['runs'][0]['response']['status'],'success');self.assertEqual(len(r['state']['files']),1)
  s=r['state']['sheets']['created_1'];self.assertEqual({x['properties']['title'] for x in s['sheets']},{'This Week','Weekly Overview','Posts','Images','Videos'})
  self.assertEqual(next(x['metadataValue'] for x in s['developerMetadata'] if x['metadataKey']=='skill35_company_id'),'sandbox_one')
  fmt=next(x['body']['requests'] for x in r['writes'] if x['name']=='Provision Formatting (F25 batchUpdate)')
  self.assertTrue(any(x.get('updateSpreadsheetProperties',{}).get('properties',{}).get('timeZone')=='America/New_York' for x in fmt))
 def test_ready_replay_preserves_data_and_dimensions(self):
  r=run([BODY,BODY]);self.assertEqual([x['response']['deduped'] for x in r['runs']],[False,True]);self.assertEqual(len(r['state']['files']),1)
  self.assertEqual(sum(x['name']=='Provision Formatting (F25 batchUpdate)' for x in r['writes']),1)
 def test_two_clients_do_not_share_artifacts(self):
  r=run([BODY,{**BODY,'company_id':'sandbox_two'}]);self.assertNotEqual(*[x['response']['sheetId'] for x in r['runs']])
 def test_response_lost_after_copy_resumes_without_duplicate(self):
  r=run([BODY,BODY],failAfterAt='Copy Template Sheet');self.assertEqual([x['response']['status'] for x in r['runs']],['error','success']);self.assertEqual(len(r['state']['files']),1);self.assertTrue(r['runs'][1]['response']['deduped'])
 def test_format_failure_does_not_mark_ready_or_share(self):
  r=run(failAt='Provision Formatting (F25 batchUpdate)');self.assertEqual(r['runs'][0]['response']['status'],'error');self.assertEqual(r['state']['files'][0]['appProperties']['skill35_provisioning_state'],'initializing');self.assertFalse(any(x['name']=='Set Anyone Can Edit' for x in r['writes']))
 def test_retry_pending_format_and_ready_receipt(self):
  r=run([BODY,BODY],failAt='This Week Sizing (batchUpdate)');self.assertEqual([x['response']['status'] for x in r['runs']],['error','success']);self.assertEqual(len(r['state']['files']),1)
 def test_share_failure_no_false_success(self):
  r=run(failAt='Set Anyone Can Edit');self.assertEqual(r['runs'][0]['response']['status'],'error');self.assertEqual(r['state']['files'][0]['appProperties']['skill35_provisioning_state'],'formatted')
 def test_all_upstream_failures_are_explicit(self):
  for name in ['Drive Readback (find existing)','Verify Provisioned Sheet','Tag Provisioning Key']:
   with self.subTest(node=name):self.assertEqual(run(failAt=name)['runs'][0]['response']['status'],'error')
 def test_template_identity_and_access_classification(self):
  for status,label in [(403,'template_access_denied'),(404,'template_not_found'),(503,'transient')]:
   with self.subTest(status=status):self.assertEqual(run(failAt='Verify Template Access (F14)',statusCode=status)['runs'][0]['response']['repair_state'],label)
 def test_injection_and_invalid_timezone_rejected_before_writes(self):
  for field,value in [('company_id',"abc' or trashed=false"),('planner_kind','a::b'),('timezone','Nowhere/Invalid')]:
   with self.subTest(field=field):
    r=run([{**BODY,field:value}]);self.assertEqual(r['runs'][0]['response']['status'],'error');self.assertFalse(r['writes'])
 def test_unowned_existing_file_requires_migration(self):
  r=run(state={'files':[{'id':'legacy','appProperties':{'skill35_provisioning_key':'sandbox_one::social'}}],'sheets':{}});self.assertEqual(r['runs'][0]['response']['status'],'error');self.assertFalse(r['writes'])
 def test_missing_metadata_on_ready_replay_fails_closed(self):
  first=run();state=first['state'];state['sheets']['created_1']['developerMetadata']=[]
  r=run(state=state);self.assertEqual(r['runs'][0]['response']['status'],'error');self.assertFalse(r['writes'])
 def test_duplicate_matching_files_are_never_arbitrarily_selected(self):
  first=run();state=first['state'];state['files'].append(state['files'][0].copy());r=run(state=state)
  self.assertEqual(r['runs'][0]['response']['status'],'error');self.assertFalse(r['writes'])
 def test_gallery_external_fetch_enabled_and_summary_survives_appended_rows(self):
  r=run();fmt=next(x['body']['requests'] for x in r['writes'] if x['name']=='Provision Formatting (F25 batchUpdate)')
  self.assertTrue(any(x.get('updateSpreadsheetProperties',{}).get('properties',{}).get('importFunctionsExternalUrlAccessAllowed') is True for x in fmt))
  summary=next(x['body']['requests'] for x in r['writes'] if x['name']=='This Week Sizing (batchUpdate)')
  formulas=[v['userEnteredValue'].get('formulaValue','') for q in summary if 'updateCells'in q for row in q['updateCells']['rows'] for v in row['values']]
  self.assertTrue(any('Posts!K:K' in f for f in formulas))
  self.assertFalse(any('Posts!K2:' in f or 'Posts!I2:' in f for f in formulas))
 def test_inherited_merged_headers_are_unmerged_before_headers_and_ready_replay(self):
  r=run([BODY,BODY],templateTabs=['This Week','Weekly Overview','Posts','Images','Videos'],templateMerged=True)
  self.assertTrue(all(x['response']['status']=='success' for x in r['runs']))
  self.assertTrue(all(not s.get('merges') for s in r['state']['sheets']['created_1']['sheets']))
 def test_every_existing_tab_metadata_branch(self):
  r=run(templateTabs=['This Week','Weekly Overview','Posts','Images','Videos']);self.assertEqual(r['runs'][0]['response']['status'],'success')
 def test_shared_copy_never_reformatted_after_final_tag_failure(self):
  r=run([BODY,BODY],failAt='Tag Provisioning Key')
  self.assertEqual([x['response']['status'] for x in r['runs']],['error','success'])
  self.assertEqual(sum(x['name']=='Provision Formatting (F25 batchUpdate)' for x in r['writes']),1)
 def test_ready_missing_tabs_or_headers_no_false_success(self):
  for kind in ['tabs','headers']:
   state=run()['state']
   if kind=='tabs':state['sheets']['created_1']['sheets']=[x for x in state['sheets']['created_1']['sheets'] if x['properties']['title']!='Posts']
   else:state['sheets']['created_1']['headers']['Posts'][0]='wrong'
   self.assertEqual(run(state=state)['runs'][0]['response']['status'],'error')
 def test_missing_share_is_repaired_without_reformatting(self):
  state=run()['state'];state['files'][0]['shared']=False
  r=run(state=state);self.assertEqual(r['runs'][0]['response']['status'],'success');self.assertTrue(r['state']['files'][0]['shared'])
  self.assertFalse(any(x['name']=='Provision Formatting (F25 batchUpdate)' for x in r['writes']))
 def test_invalid_template_fails_before_creating_file(self):
  for m in [{'mimeType':'text/plain'},{'trashed':True},{'id':'another_template'}]:
   r=run(templateMetadata=m);self.assertEqual(r['runs'][0]['response']['status'],'error');self.assertFalse(r['state']['files'])
if __name__=='__main__':unittest.main()
