"""Large Text binding preserves opaque native punctuation and placeholder spaces."""
from copy import deepcopy
import time
import unittest
from unittest.mock import Mock,patch

import large_text_fields as native
from skill6_playwright import Stop


def plan():
    api={'id':'API_FIELD','name':'Audience preference: Who is your audience?',
         'field_key':'contact.audience_preference_who_is_your_audience','data_type':'LARGE_TEXT'}
    field={**deepcopy(api),'native_query_key':'audience_preference:_who_is_your_audience?',
           'expected_label':api['name'],'expected_placeholder':'Describe the approved audience. '}
    return {'payload':{'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM',
        'large_text_fields':[field],
        'field_dependencies':{'status':'VERIFIED','provider':'public_api','location_id':'LOC',
            'operation':'custom_fields.get','http_status':200,'observed_at':time.time(),'fields':[api]}}}


class DefinitionTests(unittest.TestCase):
    def test_disabled_legacy_api_row_is_not_claimed_as_known_native_reuse(self):
        data=plan();field=data['payload']['large_text_fields'][0]
        page,frame,title,scope,dialog,search,tile,checkbox=[Mock() for _ in range(8)]
        page.url=data['payload']['start_url'];title.count.return_value=1
        title.input_value.return_value='Existing form';scope.count.return_value=1
        frame.get_by_role.return_value=title;frame.locator.return_value=scope
        dialog.get_by_text.return_value.count.return_value=0
        tile.get_attribute.return_value='true'
        with patch.object(native,'form_builder',return_value=frame),patch.object(native,'assert_tenant'), \
             patch.object(native,'_close_object_drawer'),patch.object(native,'click') as click, \
             patch.object(native,'_inventory',return_value=[(0,native._expected(field))]), \
             patch.object(native,'_stable_canvas',return_value=[{'types':['LARGE_TEXT'],'names':[['TEXTAREA',None,None]]}]), \
             patch.object(native,'_object_dialog',return_value=(dialog,search)), \
             patch.object(native,'_object_row',return_value=(Mock(),tile,checkbox)),patch.object(native,'fill'), \
             patch.object(native,'_prove_existing_owner',side_effect=Stop('LARGE_TEXT_REUSE_IDENTITY_UNVERIFIED')), \
             self.assertRaisesRegex(Stop,'LARGE_TEXT_REUSE_IDENTITY_UNVERIFIED'):
            native.configure(page,data)
        self.assertNotIn(checkbox,[call.args[0] for call in click.call_args_list])

    def test_api_definition_has_no_options_and_native_key_punctuation_is_opaque(self):
        data=plan();self.assertEqual(native.validate(data),data)
        field=data['payload']['large_text_fields'][0]
        self.assertIn(':',field['native_query_key']);self.assertIn('?',field['native_query_key'])
        self.assertNotIn('options',data['payload']['field_dependencies']['fields'][0])

    def test_placeholder_trailing_space_is_not_trimmed_or_ignored_by_hash(self):
        data=plan();expected=data['payload']['large_text_fields'][0]['expected_placeholder']
        self.assertTrue(expected.endswith(' '))
        stripped=deepcopy(data);stripped['payload']['large_text_fields'][0]['expected_placeholder']=expected.strip()
        self.assertNotEqual(native.configuration_hash(data),native.configuration_hash(stripped))
        self.assertEqual(native.validate(data)['payload']['large_text_fields'][0]['expected_placeholder'],expected)

    def test_foreign_stale_or_changed_api_definitions_cannot_enter_native_execution(self):
        for change in ({'status':'UNVERIFIED'},{'location_id':'FOREIGN'},
                       {'observed_at':0},{'http_status':True}):
            data=plan();data['payload']['field_dependencies'].update(change);page=Mock()
            with self.subTest(change=change),self.assertRaises(Stop):native.configure(page,data)
            self.assertFalse(page.mock_calls)
        data=plan();data['payload']['field_dependencies']['fields'][0]['data_type']='TEXT'
        with self.assertRaises(Stop):native.validate(data)

    def test_structural_replay_accepts_aged_receipt_but_not_unknown_native_metadata(self):
        data=plan();digest=native.configuration_hash(data)
        data['payload']['field_dependencies']['observed_at']=0
        self.assertEqual(native.configuration_hash(data),digest)
        data['payload']['large_text_fields'][0]['canvas_api_id']='invented'
        with self.assertRaises(Stop):native.validate(data)

    def test_request_api_identity_and_name_must_match_independent_receipt(self):
        for key,value in [('id','OTHER'),('field_key','contact.other'),('name','Other field')]:
            data=plan();data['payload']['field_dependencies']['fields'][0][key]=value
            with self.subTest(key=key),self.assertRaises(Stop):native.validate(data)


class WidgetCaptureTests(unittest.TestCase):
    def fixture(self,*,body_value='',native_id=None,native_name=None,property_drift=False):
        field=plan()['payload']['large_text_fields'][0]
        frame,item,label,kind,textarea,gear,query,title,placeholder=[Mock() for _ in range(9)]
        for node in (label,kind,textarea,gear,query,title,placeholder):node.count.return_value=1
        query.is_visible.return_value=True;title.is_visible.return_value=True
        textarea.input_value.return_value=body_value
        attrs={'aria-label':field['expected_placeholder'],'id':native_id,'name':native_name}
        textarea.get_attribute.side_effect=attrs.get
        query.input_value.return_value=field['native_query_key']
        title.input_value.return_value=field['expected_label']
        placeholder.input_value.return_value=field['expected_placeholder'].strip() if property_drift else field['expected_placeholder']
        item.locator.side_effect={'[data-field-type="LARGE_TEXT"]':label,'[data-field-type]':kind,
            'textarea.form-placeholder.form-control':textarea,'[aria-label="Open settings"]':gear}.__getitem__
        frame.locator.side_effect={'#fieldQueryKey input':query,'#label input':title,
                                  '#fieldPlaceholder input':placeholder}.__getitem__
        return frame,item,field,label,gear

    def test_widget_reads_no_id_textarea_and_exact_property_identity(self):
        frame,item,field,label,gear=self.fixture();clicked=[]
        with patch.object(native,'click',side_effect=clicked.append), \
             patch.object(native,'_close_properties'),patch.object(native,'_close_object_drawer'):
            index,record=native._widget(frame,item,3)
        self.assertEqual(index,3);self.assertEqual(record,native._expected(field))
        self.assertEqual(clicked,[label,gear])
        self.assertTrue(record['expected_placeholder'].endswith(' '))
        self.assertTrue(all(field['native_query_key'] not in call.args[0] for call in frame.locator.call_args_list))

    def test_future_or_foreign_canvas_id_is_not_silently_treated_as_api_binding(self):
        for kwargs in ({'native_id':'API_FIELD'},{'native_name':'API_FIELD'},{'body_value':'Unexpected live value'}):
            frame,item,_,_,_=self.fixture(**kwargs)
            with self.subTest(kwargs=kwargs),patch.object(native,'click'),self.assertRaises(Stop):
                native._widget(frame,item,0)

    def test_trimmed_native_placeholder_property_is_detected_as_identity_drift(self):
        frame,item,_,_,_=self.fixture(property_drift=True)
        with patch.object(native,'click'),self.assertRaisesRegex(Stop,'Placeholder property differ'):
            native._widget(frame,item,0)


class PreservationTests(unittest.TestCase):
    def test_new_textarea_can_be_verified_without_fabricating_an_api_name(self):
        field=plan()['payload']['large_text_fields'][0]
        before=[{'types':['text'],'names':[['INPUT','text','first_name']]}]
        after=[*before,{'types':['LARGE_TEXT'],'names':[['TEXTAREA',None,None]]}]
        native._preserved(before,[],after,[(1,native._expected(field))],[field])

    def test_native_query_or_exact_placeholder_drift_refuses_adoption(self):
        field=plan()['payload']['large_text_fields'][0]
        for key,value in [('native_query_key','other?'),('expected_placeholder',field['expected_placeholder'].strip())]:
            observed=native._expected(field);observed[key]=value
            with self.subTest(key=key),self.assertRaises(Stop):
                native._preserved([],[],[{'types':['LARGE_TEXT'],'names':[]}],[(0,observed)],[field])


if __name__=='__main__':unittest.main()
