#!/usr/bin/env python3
"""Execute the real closeout caller against a strict, offline Notion transport."""
import json, os, pathlib, subprocess, tempfile, unittest
SCRIPT=pathlib.Path(__file__).with_name('create-notion-closeout.sh')
MOCK=r'''#!/usr/bin/env python3
import json,os,sys,pathlib
args=sys.argv[1:];method=args[args.index('-X')+1];url=next(x for x in args if x.startswith('https://'))
headers=pathlib.Path(args[args.index('-K')+1]).read_text()
assert 'Bearer client-test-token' in headers, 'foreign credentials'
data=json.loads(args[args.index('-d')+1]) if '-d' in args else {}
mode=os.environ['MOCK_MODE'];parent='client-parent';root='owned-root'
def page(id,parent,title):return {'object':'page','id':id,'parent':{'page_id':parent},'properties':{'title':{'title':[{'plain_text':title}]}},'archived':False}
with open(os.environ['MOCK_LOG'],'a') as f:f.write(json.dumps({'method':method,'url':url,'body':data})+'\n')
if method=='GET' and url.endswith('/pages/client-parent'):out=page(parent,'client-home','Client Parent')
elif method=='GET' and url.endswith('/pages/owned-root'):out=page(root,'foreign-parent' if mode=='foreign-root' else parent,'Your Zero-Human Company -- Fixture Company')
elif '/search' in url:
 title=data['query'];p=root if title=='5. Departments and Roles' else parent
 out={'object':'list','has_more':mode=='truncated','results':[page('foreign-match','foreign-parent',title)]}
 if mode not in ('foreign-only','fresh','create-failure'):out['results'].append(page('owned-section' if title.startswith('5.') else root,p,title))
 if mode=='ambiguous':out['results'].append(page('second-owned',p,title))
elif method=='GET' and '/blocks/' in url:out={'object':'list','results':[],'has_more':False}
elif method=='PATCH':
 assert url.endswith('/pages/owned-section'),'foreign section mutation';out={'id':'owned-section'}
elif method=='POST' and url.endswith('/pages'):
 assert data['parent']['page_id'] in (parent,root,'child-page'),'foreign parent mutation'
 out={'object':'error','code':'restricted_resource','message':'fixture refuses create'} if mode=='create-failure' else {'id':root if data['parent']['page_id']==parent else 'child-page','object':'page'}
else:raise AssertionError((method,url))
print(json.dumps(out))
'''
class Ownership(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.ws=self.root/'home/.openclaw/workspace';self.ws.mkdir(parents=True)
  self.state=self.ws/'.workforce-build-state.json';self.bin=self.root/'bin';self.bin.mkdir();self.log=self.root/'calls'
  for name,body in [('curl',MOCK),('sleep','#!/bin/sh\nexit 0\n'),('openclaw','#!/bin/sh\nexit 77\n')]:
   p=self.bin/name;p.write_text(body);p.chmod(0o755)
  self.env={**os.environ,'HOME':str(self.root/'home'),'PATH':str(self.bin)+':/opt/homebrew/bin:/usr/bin:/bin','ZHC_STATE_FILE':str(self.state),'NOTION_API_TOKEN':'client-test-token','NOTION_CLOSEOUT_PARENT_PAGE_ID':'client-parent','ZHC_SKIP_TG_PREFLIGHT':'1','MOCK_LOG':str(self.log),'MOCK_MODE':'owned','ZHC_AGENCY_NOTION_TOKEN':'agency-test-token','ZHC_AGENCY_NOTION_PARENT_PAGE_ID':'agency-parent'}
  self.data={'companyId':'company-one','companyName':'Fixture Company','departments':{},'notionCloseoutPageId':'owned-root'};self.save()
 def tearDown(self):self.tmp.cleanup()
 def save(self):self.state.write_text(json.dumps(self.data))
 def run_script(self,refresh=True):return subprocess.run(['/opt/homebrew/bin/bash',str(SCRIPT)]+(['--refresh-workforce-only'] if refresh else []),env=self.env,capture_output=True,text=True,timeout=35)
 def calls(self):return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []
 def test_no_client_parent_never_uses_configured_agency(self):
  self.env.pop('NOTION_CLOSEOUT_PARENT_PAGE_ID');p=self.run_script(False);self.assertEqual(p.returncode,2,p.stderr);self.assertEqual(self.calls(),[]);self.assertTrue(json.loads(self.state.read_text())['notionCloseoutStaged'])
 def test_refresh_ignores_foreign_same_title_and_updates_owned_section(self):
  p=self.run_script();self.assertEqual(p.returncode,0,p.stderr);patches=[x for x in self.calls() if x['method']=='PATCH'];self.assertEqual([x['url'].split('/')[-1] for x in patches],['owned-section'])
 def test_foreign_root_or_ambiguous_search_never_writes(self):
  for mode in ['foreign-root','ambiguous','truncated']:
   with self.subTest(mode=mode):
    self.env['MOCK_MODE']=mode;self.save();self.log.unlink(missing_ok=True);p=self.run_script();self.assertEqual(p.returncode,2,p.stderr);self.assertFalse(any(x['method']=='PATCH' for x in self.calls()))
 def test_recorded_foreign_root_cannot_be_replaced_by_title_search(self):
  self.env['MOCK_MODE']='foreign-only';p=self.run_script(False);self.assertEqual(p.returncode,2,p.stderr);self.assertFalse(any(x['url'].endswith('/pages') for x in self.calls()))
 def test_full_owned_resume_keeps_root_and_persists_company_receipt(self):
  self.data['notionCloseoutStaged']=True;self.save();p=self.run_script(False);self.assertEqual(p.returncode,0,p.stderr[-4000:]);self.assertFalse(json.loads(self.state.read_text())['notionCloseoutStaged']);self.assertFalse(any(x['method']=='POST' and x['body'].get('parent',{}).get('page_id')=='client-parent' for x in self.calls()));self.assertEqual(json.loads(self.state.read_text())['notionOwnership'],{'companyId':'company-one','parentPageId':'client-parent','rootPageId':'owned-root'})
 def run_provisioner(self):return subprocess.run(['/opt/homebrew/bin/bash',str(SCRIPT.with_name('ensure-notion-parent-page.sh'))],env=self.env,capture_output=True,text=True,timeout=15)
 def test_provisioner_missing_parent_does_not_discover_global_page(self):
  self.env.pop('NOTION_CLOSEOUT_PARENT_PAGE_ID');p=self.run_provisioner();self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(self.calls(),[]);self.assertTrue(json.loads(self.state.read_text())['notionParentPagePending']);self.assertFalse((self.ws/'.env').exists())
 def test_provisioner_verifies_explicit_parent_and_preserves_owned_receipt(self):
  self.data['notionOwnership']={'companyId':'company-one','parentPageId':'client-parent','rootPageId':'owned-root'};self.save()
  p=self.run_provisioner();self.assertEqual(p.returncode,0,p.stderr);self.assertIn('NOTION_CLOSEOUT_PARENT_PAGE_ID=client-parent',(self.ws/'.env').read_text());self.assertFalse(json.loads(self.state.read_text())['notionParentPagePending']);self.assertEqual(json.loads(self.state.read_text())['notionOwnership']['rootPageId'],'owned-root');self.assertEqual([x['method'] for x in self.calls()],['GET'])
 def test_provisioner_conflicting_company_and_agency_never_call_api(self):
  self.data['notionOwnership']={'companyId':'foreign-company','parentPageId':'client-parent'};self.save();p=self.run_provisioner();self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(self.calls(),[]);self.assertTrue(json.loads(self.state.read_text())['notionParentPagePending'])
  self.data.pop('notionOwnership');self.save();self.env['NOTION_API_TOKEN']='agency-test-token';p=self.run_provisioner();self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(self.calls(),[])
 def test_root_create_failure_stages_without_switching_to_agency(self):
  self.data.pop('notionCloseoutPageId');self.save();self.env['MOCK_MODE']='create-failure';p=self.run_script(False);self.assertNotEqual(p.returncode,0);self.assertTrue(json.loads(self.state.read_text())['notionCloseoutStaged']);self.assertNotEqual(json.loads(self.state.read_text()).get('notionTier'),2);self.assertTrue(all(x['body'].get('parent',{}).get('page_id','client-parent')=='client-parent' for x in self.calls()))
if __name__=='__main__':unittest.main()
