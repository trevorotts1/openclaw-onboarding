"""Choice-schema creation never launders uncertainty into another POST."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import radio_dependencies as radio
from skill6_playwright import Stop


def question(name='Service',key='contact.service',identity=None):
    return {'name':name,'field_key':key,'data_type':'RADIO','options':['Coaching','Consulting'],
            'expected_id':identity,'allow_creation':identity is None}


def capability():
    sample={'id':'MEASURED','locationId':'LOC','dataType':'RADIO','picklistOptions':['A','B']}
    return {'schema':'skill44-radio-fallback-capability/1','location_id':'LOC',
        'provider':'skill44_legacy','auth_kind':'location_pit',
        'scopes':['locations/customFields.readonly','locations/customFields.write'],'observed_at':time.time(),'source':'fixture measurement, never client proof',
        'operations':{key:{'method':method,'path':path,'version':'2021-07-28',
            'http_status':status,'response_sha256':'f'*64,'sample':deepcopy(sample) if key!='list' else None}
            for key,method,path,status in (('list','GET',radio.LIST_PATH,200),
                ('get','GET',radio.GET_PATH,200),('create','POST',radio.CREATE_PATH,201))}}


def record(q,identity='FIELD'):
    return {'id':identity,'locationId':'LOC','model':'contact','name':q['name'],
            'fieldKey':q['field_key'],'dataType':'RADIO','picklistOptions':q['options']}


class Api:
    def __init__(self,fields=None):
        self.fields=deepcopy(fields or []);self.calls=[];self.uncertain=False;self.drift=False
    def version_for(self,method,path):
        return '2021-07-28'
    def request(self,method,path,*,location_id,version,body=None):
        self.calls.append((method,path,location_id,version,deepcopy(body)))
        if path=='/locations/LOC/customFields':
            return {'http_status':200,'body':{'customFields':deepcopy(self.fields)}}
        if method=='POST':
            result=record(question(body['name'],'contact.'+body['name'].lower()),'NEW'+str(len(self.fields)))
            result['picklistOptions']=deepcopy(body['options']);self.fields.append(result)
            if self.uncertain:raise TimeoutError('POST outcome unknown')
            return {'http_status':201,'body':{'customField':deepcopy(result)}}
        identity=path.rsplit('/',1)[-1]
        result=deepcopy(next(field for field in self.fields if field['id']==identity))
        if self.drift:result['picklistOptions']=['Unrequested','Altered']
        return {'http_status':200,'body':{'customField':result}}


class RadioDependencies(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)/'run';self.plan={'location_id':'LOC','questions':[question()]}
        self.api=Api()
    def provision(self,plan=None,cap=None,api=None):
        return radio.provision_radio(plan or self.plan,self.root,capability=cap or capability(),transport=api or self.api)
    def test_authored_radio_creates_once_reads_exact_options_and_replays_get_only(self):
        result=self.provision();posts=[call for call in self.api.calls if call[0]=='POST']
        self.assertEqual(len(posts),1)
        self.assertEqual(posts[0][4],{'locationId':'LOC','name':'Service','dataType':'RADIO',
                                    'objectKey':'contact','options':['Coaching','Consulting']})
        self.assertEqual(result['object_fields'][0]['id'],'NEW0')
        self.assertEqual(result['field_dependencies']['operation'],'custom_fields.get')
        self.assertEqual(result['field_dependencies']['http_status'],200)
        count=len(self.api.calls);again=self.provision()
        self.assertTrue(again['native_placement_required'])
        self.assertTrue(all(call[0]=='GET' for call in self.api.calls[count:]))
    def test_exact_existing_identity_reuses_without_post(self):
        q=question(identity='FIELD');api=Api([record(q)])
        result=self.provision({'location_id':'LOC','questions':[q]},api=api)
        self.assertEqual(result['object_fields'][0]['id'],'FIELD')
        self.assertFalse(any(call[0]=='POST' for call in api.calls))
    def test_expected_absence_does_not_silently_adopt_name_collision(self):
        for value in (record(question()),record(question('Other','contact.service'))):
            api=Api([value])
            with self.subTest(value=value),self.assertRaises(Stop):self.provision(api=api)
            self.assertFalse(any(call[0]=='POST' for call in api.calls))
    def test_missing_later_reuse_refuses_before_first_schema_creation(self):
        plan={'location_id':'LOC','questions':[question(),question('Other','contact.other','MISSING')]}
        with self.assertRaises(Stop):self.provision(plan)
        self.assertFalse(any(call[0]=='POST' for call in self.api.calls))
    def test_route_version_scope_and_measured_options_evidence_are_required(self):
        for mutate in (lambda c:c.update(location_id='OTHER'),lambda c:c.update(auth_kind='agency_pit'),
            lambda c:c.update(scopes=['locations/customFields.readonly']),lambda c:c.update(observed_at=0),
            lambda c:c['operations']['create'].update(version='v3'),
            lambda c:c['operations']['create'].update(path='/locations/{locationId}/customFields'),
            lambda c:c['operations']['get']['sample'].update(picklistOptions=['DIFFERENT','B']),
            lambda c:c['operations']['create'].update(http_status=True),
            lambda c:c['operations']['create'].update(supported=True)):
            api=Api();cap=capability();mutate(cap)
            with self.subTest(cap=cap),self.assertRaises(Stop):self.provision(cap=cap,api=api)
            self.assertFalse(any(call[0]=='POST' for call in api.calls))
    def test_uncertain_post_retains_intent_and_never_lists_or_posts_again(self):
        self.api.uncertain=True
        with self.assertRaises(TimeoutError):self.provision()
        state=json.loads((self.root/'delivery-state.json').read_text())
        self.assertEqual(state['status'],'NEEDS_RECONCILIATION')
        count=len(self.api.calls)
        with self.assertRaises(Stop):self.provision()
        self.assertEqual(len(self.api.calls),count)
    def test_wrong_generated_key_or_lost_options_retains_created_id_for_reconciliation(self):
        self.plan['questions'][0]['field_key']='contact.different'
        with self.assertRaises(Stop):self.provision()
        state=json.loads((self.root/'delivery-state.json').read_text())
        self.assertEqual(state['created_id'],'NEW0')
        self.assertEqual(state['status'],'NEEDS_RECONCILIATION')
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
    def test_completed_schema_drift_never_recreates_field(self):
        self.provision();self.api.drift=True
        with self.assertRaises(Stop):self.provision()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
    def test_foreign_malformed_or_duplicate_inventory_never_authorizes_absence(self):
        for value in ([{**record(question()),'locationId':'OTHER'}],
                      [record(question()),record(question())],[{'name':'Missing identity'}]):
            api=Api(value)
            with self.subTest(value=value),self.assertRaises(Stop):self.provision(api=api)
            self.assertFalse(any(call[0]=='POST' for call in api.calls))
    def test_global_name_appearing_after_preflight_stops_before_post(self):
        original=self.api.request
        state={'lists':0}
        def concurrent(method,path,**kwargs):
            if path=='/locations/LOC/customFields':
                state['lists']+=1
                if state['lists']==2:self.api.fields.append(record(question(),'OTHER_AUTHOR'))
            return original(method,path,**kwargs)
        self.api.request=concurrent
        with self.assertRaisesRegex(Stop,'appeared after preflight'):self.provision()
        self.assertFalse(any(call[0]=='POST' for call in self.api.calls))

    def test_later_bad_options_stop_before_any_api_call(self):
        self.plan['questions'].append(question('Other','contact.other'))
        self.plan['questions'][1]['options']=['duplicate','duplicate']
        with self.assertRaises(Stop):self.provision()
        self.assertEqual(self.api.calls,[])
    def test_only_captured_text_radio_schema_is_accepted(self):
        for mode in ('image','wrong_model','wrong_options'):
            q=question(identity='FIELD');seen=record(q)
            if mode=='image':seen['optionDisplayType']='TEXT_WITH_IMAGE'
            elif mode=='wrong_model':seen['model']='opportunity'
            else:seen['picklistOptions']=['Changed','Options']
            api=Api([seen])
            with self.subTest(mode=mode),self.assertRaises(Stop):
                self.provision({'location_id':'LOC','questions':[q]},api=api)
            self.assertFalse(any(call[0]=='POST' for call in api.calls))


if __name__=='__main__':unittest.main()
