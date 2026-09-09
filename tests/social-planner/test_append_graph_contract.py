"""Full n8n export graph regressions; no provider credentials or network."""
import copy,json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WORKFLOW=ROOT/'35-social-media-planner/config/n8n/social-planner-row-append.json'
RUNNER=Path(__file__).parent/'fixtures/append_graph_runner.cjs'
BASE=dict(sheetId='sheet_123',company_id='company_1',cycle_id='week1',content_revision='rev1',account_id='ig1',platform='Instagram',account_name='Main IG',format='post',scheduled_local='2026-09-10 09:00',scheduled_utc='2026-09-10T13:00:00Z',state='Scheduled',qc_state='PASS',title='=UNTRUSTED()',notes='client notes')
def run(bodies,**kwargs):
 p=subprocess.run(['node',str(RUNNER)],input=json.dumps(dict(workflow=str(WORKFLOW),bodies=bodies,**kwargs)),text=True,capture_output=True)
 if p.returncode:raise AssertionError(p.stderr)
 return json.loads(p.stdout)
class GraphTests(unittest.TestCase):
 def test_text_and_duplicate_replay_preserve_key_and_raw_values(self):
  r=run([BASE,dict(BASE,state='Published')])
  self.assertTrue(all(x['response']['success'] for x in r['runs']))
  self.assertEqual(r['runs'][0]['response']['row_key'],'week1::rev1::ig1')
  self.assertEqual(r['runs'][1]['response']['mode'],'upserted')
  self.assertEqual(len(r['state']['Posts']),2)
  self.assertEqual(r['state']['Posts'][1][10],'Published')
  self.assertEqual(r['state']['Weekly Overview'][1][3],'=UNTRUSTED()')
 def test_other_accounts_and_unknown_platform_stay_separate(self):
  r=run([BASE,dict(BASE,account_id='ig2',account_name='Second IG'),dict(BASE,account_id='future',platform='New Platform',account_name='Future')])
  self.assertEqual(len(r['state']['Posts']),4)
  overview=r['state']['Weekly Overview'][1]
  self.assertEqual(overview[7],'Main IG: Scheduled; Second IG: Scheduled')
  self.assertEqual(overview[10],'')
  self.assertIn('Future: PASS',overview[16])
 def test_image_append_and_replay_formula_matches_manifest_and_dimensions(self):
  b=dict(BASE,asset=dict(kind='image',asset_id='image1',preview_url='https://assets.cdn.filesafe.space/public/image.jpg'))
  r=run([b,b]);self.assertTrue(r['runs'][-1]['response']['success']);self.assertEqual(len(r['state']['Images']),2)
  formulas=[x for x in r['writes'] if x['name']=='Write Trusted IMAGE Formula (F24)']
  self.assertEqual(len(formulas),2);self.assertTrue(all('/Images!P2?' in x['url'] for x in formulas))
  dims=[q['updateDimensionProperties'] for x in r['writes'] for q in x.get('body',{}).get('requests',[]) if 'updateDimensionProperties'in q]
  self.assertTrue(any(d['range']['sheetId']==303 and d['range']['dimension']=='ROWS' and d['range']['startIndex']==1 for d in dims))
 def test_video_uses_actual_tab_and_finishes_resize_and_response(self):
  b=dict(BASE,asset=dict(kind='video',asset_id='vid1',preview_url='https://cdn.example.org/poster.jpg',poster_url='https://cdn.example.org/poster.jpg',watch_url='https://cc.example.org/client/video/vid1',youtube=True,published_url='https://youtube.com/watch?v=123'))
  r=run([b,b]);self.assertTrue(r['runs'][-1]['response']['success']);self.assertEqual(len(r['state']['Videos']),2)
  writes=[x for x in r['writes'] if x['name']=='Write Poster + Watch Video (batchUpdate)']
  self.assertEqual(len(writes),2)
  for x in writes:
   for q in x['body']['requests']:
    self.assertEqual(q['updateCells']['start']['sheetId'],404)
    self.assertEqual(q['updateCells']['start']['rowIndex'],1)
    self.assertNotIn(' | YouTube',q['updateCells']['rows'][0]['values'][0]['userEnteredValue']['formulaValue'])
  self.assertIn('Resolve Posts Sheet ID',r['runs'][-1]['trace'])
 def test_invalid_poster_reports_partial_but_preserves_posts(self):
  b=dict(BASE,asset=dict(kind='video',preview_url='https://cdn.example.org/x.jpg',poster_url='https://cdn.example.org/"bad',watch_url='https://cc.example.org/video/1'))
  r=run([b]);self.assertTrue(r['runs'][0]['response']['partial']);self.assertEqual(r['runs'][0]['response']['asset_repair']['repair_state'],'asset_poster_url_invalid');self.assertEqual(len(r['state']['Posts']),2)
 def test_tenant_metadata_mismatch_and_missing_fail_before_write(self):
  for metadata in [[],[dict(metadataKey='skill35_company_id',metadataValue='other')]]:
   r=run([BASE],metadata=metadata);self.assertFalse(r['runs'][0]['response']['success']);self.assertEqual(r['writes'],[])
 def test_missing_required_tab_fails_before_write(self):
  r=run([BASE],missingTabs=['Posts']);self.assertFalse(r['runs'][0]['response']['success']);self.assertEqual(r['writes'],[])
 def test_metadata_errors_have_actionable_repair(self):
  for status,expected in [(403,'sheet_access_denied'),(404,'sheet_not_found'),(503,'transient')]:
   r=run([BASE],failAt='Verify Sheet Metadata (F14)',statusCode=status);self.assertEqual(r['runs'][0]['response']['repair_state'],expected);self.assertEqual(r['writes'],[])
 def test_resize_error_preserves_receipt_and_reports_warning(self):
  r=run([BASE],failAt='Resize Columns + Row (batchUpdate)');self.assertTrue(r['runs'][0]['response']['success']);self.assertFalse(r['runs'][0]['response']['formatting_applied'])
 def test_header_corruption_foreign_rows_and_duplicate_keys_fail_closed(self):
  header=json.loads(WORKFLOW.read_text())['contract']['posts_schema']
  row=['week1::rev1::ig1','company_1','week1','rev1','ig1','Instagram','Main IG','post','','','Scheduled','PASS','','']
  for rows in [[['bad header']], [header,row,row],[header,row[:1]+['other']+row[2:]]]:
   state={'Posts':rows,'Weekly Overview':[],'Images':[],'Videos':[]}
   r=run([BASE],state=state);self.assertFalse(r['runs'][0]['response']['success']);self.assertEqual(r['writes'],[])
 def test_lost_append_response_replay_reads_committed_key(self):
  r=run([BASE,BASE],failAfterAt='Append Posts Row')
  self.assertFalse(r['runs'][0]['response']['success'])
  self.assertTrue(r['runs'][1]['response']['success'])
  self.assertEqual(r['runs'][1]['response']['mode'],'upserted')
  self.assertEqual(len(r['state']['Posts']),2)
 def test_text_does_not_require_images_or_videos(self):
  r=run([BASE],missingTabs=['Images','Videos']);self.assertTrue(r['runs'][0]['response']['success'])
 def test_absent_notes_preserves_existing_client_note(self):
  b=dict(BASE);b.pop('notes')
  r=run([BASE,b]);self.assertEqual(r['state']['Weekly Overview'][1][19],'client notes')
 def test_expiring_media_surfaces_repair_without_blocking_posts(self):
  b=dict(BASE,asset=dict(kind='image',preview_url='https://cdn.example.org/image.jpg?X-Amz-Expires=30'))
  r=run([b]);self.assertTrue(r['runs'][0]['response']['partial']);self.assertEqual(len(r['state']['Posts']),2);self.assertEqual(r['state']['Images'],[])
 def test_upsert_preserves_existing_dimensions(self):
  r=run([BASE,BASE]);self.assertNotIn('Resize Columns + Row (batchUpdate)',r['runs'][1]['trace'])
 def test_all_connections_and_error_ports_are_canonical(self):
  w=json.loads(WORKFLOW.read_text())
  for n in w['nodes']:
   if n['type'].endswith('.httpRequest'):
    self.assertNotIn('retryOnFail',n['parameters'])
    self.assertEqual(len(w['connections'][n['name']]['main']),2)
    if ':append?' in n['parameters']['url']:self.assertFalse(n.get('retryOnFail',False))
  self.assertTrue(all(isinstance(c,dict) and 'main'in c for c in w['connections'].values()))
if __name__=='__main__':unittest.main()
