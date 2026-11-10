"""Documented v3 bodies, exact identities and no-repeat global field writes."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contact_field_dependencies as fields
from skill6_playwright import Stop


def large(identity=None,name='Audience',key='contact.audience'):
    return {'name':name,'field_key':key,'data_type':'LARGE_TEXT','placeholder':'Describe your audience. ',
        'expected_id':identity,'allow_creation':identity is None}


def dropdown(identity='EXISTING'):
    return {'name':'Priority','field_key':'contact.priority','data_type':'SINGLE_OPTIONS',
        'options':['Growth','Clarity'],'expected_id':identity,'allow_creation':False}


def capability():
    return {'schema':fields.CAPABILITY,'location_id':'LOC','provider':'public_api','auth_kind':'location_pit',
        'version':'v3','status':'PASS','source':'offline fixture, not client capability proof',
        'scopes':['locations/customFields.readonly','locations/customFields.write'],
        'checked_at':datetime.now(timezone.utc).isoformat()}


def record(field,identity='EXISTING'):
    return {'id':identity,'locationId':'LOC','model':'contact','name':field['name'],
        'fieldKey':field['field_key'],'dataType':field['data_type'],
        **({'placeholder':field['placeholder']} if field['data_type']=='LARGE_TEXT' else {'picklistOptions':deepcopy(field['options'])})}


class Api:
    def __init__(self,rows=None):self.rows=deepcopy(rows or []);self.calls=[];self.uncertain=False;self.drift=False
    def request(self,method,path,*,location_id,body=None,query=None):
        self.calls.append((method,path,location_id,deepcopy(body),deepcopy(query)))
        if method=='POST':
            assert set(body)=={'name','dataType','placeholder','model'}
            assert body['dataType']=='LARGE_TEXT' and body['model']=='contact'
            value=record(large(name=body['name'],key='contact.'+body['name'].lower()),'NEW'+str(len(self.rows)))
            value['placeholder']=body['placeholder'];self.rows.append(value)
            if self.uncertain:raise TimeoutError('uncertain POST')
            return {'http_status':201,'body':{'customField':deepcopy(value)}}
        if path=='/locations/LOC/customFields':
            assert query=={'model':'contact'}
            return {'http_status':200,'body':{'customFields':deepcopy(self.rows)}}
        assert query is None
        value=deepcopy(next(row for row in self.rows if row['id']==path.rsplit('/',1)[-1]))
        if self.drift:value['name']='Changed field'
        return {'http_status':200,'body':{'customField':value}}


class FieldDependencies(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);self.root=Path(folder.name)/'evidence'
        self.plan={'location_id':'LOC','fields':[large()]};self.api=Api()
    def provision(self,plan=None,cap=None,api=None):
        return fields.provision_fields(plan or self.plan,self.root,capability=cap or capability(),transport=api or self.api)
    def test_documented_large_body_creates_once_and_completed_replay_gets_only(self):
        first=self.provision();count=len(self.api.calls);second=self.provision()
        self.assertEqual(first['fields'],second['fields']);self.assertEqual(first['fields'][0]['id'],'NEW0')
        posts=[call for call in self.api.calls if call[0]=='POST'];self.assertEqual(len(posts),1)
        self.assertEqual(posts[0][1:4],('/locations/LOC/customFields','LOC',{'name':'Audience','dataType':'LARGE_TEXT','placeholder':'Describe your audience. ','model':'contact'}))
        self.assertTrue(all(call[0]=='GET' for call in self.api.calls[count:]));self.assertNotIn('options',first['fields'][0])
    def test_exact_dropdown_reuse_preserves_order_and_never_posts(self):
        q=dropdown();api=Api([record(q)]);cap=capability();cap['scopes']=['locations/customFields.readonly']
        value=self.provision({'location_id':'LOC','fields':[q]},cap=cap,api=api)
        self.assertEqual(value['fields'][0]['options'],q['options']);self.assertFalse(any(call[0]=='POST' for call in api.calls))
    def test_dropdown_creation_and_bad_later_inputs_stop_before_api(self):
        for change in ({'expected_id':None,'allow_creation':True},{'allow_creation':True},{'options':['same','same']},{'picklistOptions':['A','B']}):
            q=dropdown();q.update(change);api=Api()
            with self.subTest(change=change),self.assertRaises(Stop):self.provision({'location_id':'LOC','fields':[large(),q]},api=api)
            self.assertEqual(api.calls,[])
    def test_missing_later_reuse_or_existing_name_never_creates_fallback(self):
        for rows,plan in (([],{'location_id':'LOC','fields':[large(),large('ABSENT','Other','contact.other')]}),([record(large())],self.plan)):
            api=Api(rows)
            with self.subTest(rows=rows),self.assertRaises(Stop):self.provision(plan,api=api)
            self.assertFalse(any(call[0]=='POST' for call in api.calls))
    def test_readback_binds_model_tenant_key_type_placeholder_and_option_order(self):
        for key,value in (('model','opportunity'),('locationId','OTHER'),('fieldKey','contact.other'),('dataType','TEXT'),('placeholder','Trimmed space')):
            q=large('EXISTING');row=record(q);row[key]=value;api=Api([row])
            with self.subTest(key=key),self.assertRaises(Stop):self.provision({'location_id':'LOC','fields':[q]},api=api)
        q=dropdown();row=record(q);row['picklistOptions'].reverse()
        with self.assertRaises(Stop):self.provision({'location_id':'LOC','fields':[q]},api=Api([row]))
    def test_foreign_duplicate_or_malformed_list_never_proves_absence(self):
        for rows in ([{**record(large()),'locationId':'OTHER'}],[record(large()),record(large())],[{'name':'No ID'}]):
            api=Api(rows)
            with self.subTest(rows=rows),self.assertRaises(Stop):self.provision(api=api)
            self.assertFalse(any(call[0]=='POST' for call in api.calls))
    def test_fresh_scope_version_provider_auth_and_real_status_required(self):
        for change in ({'location_id':'OTHER'},{'version':'2021-07-28'},{'provider':'official_mcp'},
            {'auth_kind':'agency_pit'},{'status':True},{'checked_at':(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()},
            {'checked_at':'invalid'},{'scopes':['locations/customFields.readonly']}):
            cap=capability();cap.update(change);api=Api()
            with self.subTest(change=change),self.assertRaises(Stop):self.provision(cap=cap,api=api)
            self.assertFalse(any(call[0]=='POST' for call in api.calls))
    def test_uncertain_post_retains_intent_without_another_call(self):
        self.api.uncertain=True
        with self.assertRaises(TimeoutError):self.provision()
        count=len(self.api.calls)
        with self.assertRaises(Stop):self.provision()
        self.assertEqual(len(self.api.calls),count);self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
        self.assertEqual(json.loads((self.root/'delivery-state.json').read_text())['status'],'NEEDS_RECONCILIATION')
    def test_wrong_generated_key_retains_created_id_without_retry(self):
        self.plan['fields'][0]['field_key']='contact.different'
        with self.assertRaises(Stop):self.provision()
        self.assertEqual(json.loads((self.root/'delivery-state.json').read_text())['created_id'],'NEW0')
        with self.assertRaises(Stop):self.provision()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
    def test_concurrent_name_after_preflight_prevents_post(self):
        original=self.api.request;seen={'lists':0}
        def request(method,path,**kwargs):
            if method=='GET' and path.endswith('customFields'):
                seen['lists']+=1
                if seen['lists']==2:self.api.rows.append(record(large(),'OTHER_WRITER'))
            return original(method,path,**kwargs)
        self.api.request=request
        with self.assertRaisesRegex(Stop,'appeared after preflight'):self.provision()
        self.assertFalse(any(call[0]=='POST' for call in self.api.calls))
    def test_completed_drift_and_retargeted_reuse_do_not_recreate(self):
        self.provision();self.api.drift=True
        with self.assertRaises(Stop):self.provision()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
        with self.assertRaisesRegex(Stop,'exact authored field ID'):fields._get(self.api,{'location_id':'LOC'},large('EXPECTED'),'DIFFERENT')
    def test_dry_run_and_symlink_journal_do_not_call_api(self):
        with patch.dict('os.environ',{'CAF_DRY_RUN':'true'}),self.assertRaises(Stop):self.provision()
        self.assertEqual(self.api.calls,[])
        target=self.root.parent/'outside';target.write_text('{}');self.root.mkdir(exist_ok=True);(self.root/'delivery-state.json').symlink_to(target)
        with self.assertRaises(Stop):self.provision()
        self.assertEqual(self.api.calls,[])


if __name__=='__main__':unittest.main()
