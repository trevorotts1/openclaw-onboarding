"""Real API/compiler/editor journal joins for captured textarea/Dropdown fields."""
from contextlib import ExitStack
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock,patch

import form_contact_field_chain as chain
import forms_advanced
import skill6_playwright as runner
from test_contact_field_dependencies import Api,capability,large,dropdown,record


class ContactFormChain(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup);self.root=Path(directory.name)/'chain'
        self.plan={'location_id':'LOC','location_name':'Fixture Account',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
            'expected_form_name':'Existing form','fields':[large()],
            'native_bindings':[{'field_key':'contact.audience','native_query_key':'audience:_who?',
                'expected_label':'Audience','expected_placeholder':'Describe your audience. '}]}
        self.api=Api();self.page=MagicMock();self.page.url=self.plan['start_url'];self.frame=self.page.frame_locator.return_value
        self.title=MagicMock();self.title.count.return_value=1;self.title.input_value.return_value='Existing form'
        self.edit=MagicMock();self.edit.count.return_value=1
        self.frame.get_by_role.side_effect=lambda role,**kw:self.title if role=='textbox' else self.edit
        canvas=self.frame.locator.return_value;canvas.count.return_value=1;canvas.is_visible.return_value=True
        self.canvas=[{'types':['text'],'names':[['INPUT','text','first_name']]},{'types':['submit'],'names':[]}]
    def as_dropdown(self):
        q=dropdown();self.plan['fields']=[q];self.api=Api([record(q)])
        self.plan['native_bindings']=[{'field_key':q['field_key'],'native_query_key':'priority_custom_native',
            'expected_label':'Priority'}]
    def build(self):return chain.build_form_fields(self.plan,self.root,page=self.page,capability=capability(),transport=self.api)
    def native(self):return importlib.import_module('playwright_recipes.'+('large_text_fields' if self.plan['fields'][0]['data_type']=='LARGE_TEXT' else 'dropdown_fields'))
    def receipt(self,page,step):
        self.assertIs(page,self.page)
        api_state=json.loads((self.root/'delivery-state.json').read_text())
        self.assertEqual(api_state['status'],'API_STEPS_COMPLETE')
        native_state=json.loads((self.root/'native/state.json').read_text())
        self.assertEqual(native_state['current_step_status'],'INTENT_RECORDED')
        kind=self.plan['fields'][0]['data_type'];key='large_text_fields' if kind=='LARGE_TEXT' else 'dropdown_fields'
        field=step['payload'][key][0]
        self.assertEqual(field['id'],'NEW0' if kind=='LARGE_TEXT' else 'EXISTING')
        self.assertEqual(field['native_query_key'],self.plan['native_bindings'][0]['native_query_key'])
        self.assertEqual(step['payload']['field_dependencies']['fields'],[{k:field[k] for k in self.native().API_KEYS}])
        self.canvas.append({'types':[kind],'names':[['TEXTAREA' if kind=='LARGE_TEXT' else 'INPUT',None,None]]})
        return {'status':('LARGETEXT_FIELDS_SAVED_AND_REOPENED' if kind=='LARGE_TEXT' else 'DROPDOWN_FIELDS_SAVED_AND_REOPENED'),
            'editor_url':page.url,'fields':[{**{key:field[key] for key in ('id','field_key','data_type','native_query_key')},'placement':'added'}],
            'configuration_sha256':self.native().configuration_hash(step),'independent_readback':'VERIFIED',
            'behavior_verified':False,'submission_verified':False}
    def patches(self,writer=None):
        stack=ExitStack()
        for owner,name in ((chain,'assert_tenant'),(chain,'click'),(runner,'assert_tenant'),(forms_advanced,'_close_object_drawer')):
            stack.enter_context(patch.object(owner,name))
        stack.enter_context(patch.object(forms_advanced,'_canvas_identity',side_effect=lambda _:deepcopy(self.canvas)))
        writer=stack.enter_context(patch.object(self.native(),'configure',side_effect=writer or self.receipt))
        return stack,writer
    def test_large_creation_real_compile_and_journals_replay_aged_inventory_without_reinsert(self):
        stack,writer=self.patches()
        with stack:
            first=self.build();saved=(self.root/'native-field-job.json').read_bytes()
            with patch.object(time,'time',return_value=time.time()+3700):second=self.build()
        self.assertEqual(first['status'],'NEEDS_VERIFICATION');self.assertTrue(second['native_result']['replayed'])
        self.assertEqual((self.root/'native-field-job.json').read_bytes(),saved)
        writer.assert_called_once();self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
    def test_exact_existing_dropdown_schema_joins_captured_fresh_insertion_without_any_post(self):
        self.as_dropdown();stack,writer=self.patches()
        with stack:first=self.build();again=self.build()
        self.assertEqual(first['fields'][0]['options'],['Growth','Clarity']);self.assertTrue(again['native_result']['replayed'])
        self.assertFalse(any(call[0]=='POST' for call in self.api.calls));writer.assert_called_once()
    def test_wrong_form_or_bad_literal_native_binding_prevents_global_schema_write(self):
        for defect in ('name','placeholder','query','family'):
            plan=deepcopy(self.plan)
            if defect=='name':self.title.input_value.return_value='Foreign form'
            elif defect=='placeholder':self.plan['native_bindings'][0]['expected_placeholder']=True
            elif defect=='query':self.plan['native_bindings'][0]['native_query_key']='contains whitespace'
            else:self.plan['fields'].append(dropdown())
            stack,writer=self.patches()
            with self.subTest(defect=defect),stack,self.assertRaises(runner.Stop):self.build()
            self.assertEqual(self.api.calls,[]);writer.assert_not_called();self.plan=plan;self.title.input_value.return_value='Existing form'
    def test_target_changed_during_api_creation_prevents_native_placement(self):
        original=self.api.request
        def request(method,*args,**kwargs):
            result=original(method,*args,**kwargs)
            if method=='POST':self.title.input_value.return_value='Renamed during creation'
            return result
        self.api.request=request;stack,writer=self.patches()
        with stack,self.assertRaisesRegex(runner.Stop,'editor changed'):self.build()
        writer.assert_not_called();self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
    def test_uncertain_native_write_is_not_reinserted_and_api_is_not_recreated(self):
        stack,writer=self.patches(writer=lambda *args:(_ for _ in ()).throw(TimeoutError('uncertain editor save')))
        with stack:
            for _ in range(2):
                with self.assertRaises(runner.Stop):self.build()
        writer.assert_called_once();self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
        self.assertEqual(json.loads((self.root/'native/state.json').read_text())['current_step_status'],'INTENT_RECORDED')
    def test_unproven_legacy_reuse_cannot_become_fresh_completion(self):
        self.as_dropdown()
        def invalid(page,step):
            value=self.receipt(page,step);value['fields'][0]['placement']='reused';return value
        stack,writer=self.patches(writer=invalid)
        with stack,self.assertRaises(runner.Stop):self.build()
        self.assertEqual(json.loads((self.root/'native/state.json').read_text())['results'],[])
    def test_changed_native_binding_cannot_reuse_an_api_evidence_root(self):
        stack,writer=self.patches()
        with stack:
            self.build();count=len(self.api.calls);self.plan['native_bindings'][0]['native_query_key']='another_native_key'
            with self.assertRaisesRegex(runner.Stop,'evidence root belongs'):self.build()
        writer.assert_called_once();self.assertEqual(len(self.api.calls),count)
    def test_native_evidence_symlink_refuses_before_api(self):
        self.root.mkdir(parents=True);outside=self.root.parent/'outside';outside.mkdir();(self.root/'native').symlink_to(outside)
        stack,writer=self.patches()
        with stack,self.assertRaisesRegex(runner.Stop,'symlink'):self.build()
        self.assertEqual(self.api.calls,[]);writer.assert_not_called()


if __name__=='__main__':unittest.main()
