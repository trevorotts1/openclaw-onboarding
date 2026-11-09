"""Real dependency provisioning/compiler/editor journals join safely for forms."""
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock,patch

import form_radio_chain as chain
import forms_advanced
import skill6_playwright as runner
from playwright_recipes import forms_advanced as native_form
from test_radio_dependencies import Api,capability,question


class FormRadioChainTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.root=Path(directory.name)/'chain'
        self.api=Api();self.page=MagicMock()
        self.plan={'location_id':'LOC','location_name':'Fixture Account',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
            'expected_form_name':'Existing form','questions':[question()]}
        self.page.url=self.plan['start_url']
        self.frame=self.page.frame_locator.return_value
        self.title=MagicMock();self.title.count.return_value=1
        self.title.input_value.return_value='Existing form'
        self.edit=MagicMock();self.edit.count.return_value=1
        self.frame.get_by_role.side_effect=lambda role,**kw:self.title if role=='textbox' else self.edit
        canvas=self.frame.locator.return_value;canvas.count.return_value=1;canvas.is_visible.return_value=True
        self.canvas=[{'types':['text'],'names':[['INPUT','text','first_name']]},
                     {'types':['submit'],'names':[]}]

    def build(self):
        return chain.build_form_questions(self.plan,self.root,page=self.page,
            capability=capability(),transport=self.api)

    def receipt(self,page,step):
        self.assertTrue((self.root/'delivery-state.json').exists())
        field=step['payload']['object_fields'][0]
        self.assertEqual(field['id'],'NEW0')
        self.assertEqual(step['payload']['field_dependencies']['fields'],[field])
        self.canvas.append({'types':['RADIO'],'names':[['INPUT','radio',field['id']]]})
        return {'status':'OBJECT_FIELDS_SAVED_AND_REOPENED','editor_url':page.url,
            'fields':[{'id':field['id'],'field_key':field['field_key'],
                       'data_type':'RADIO','placement':'added'}],
            'configuration_sha256':native_form.object_fields_configuration_hash(step),
            'independent_readback':'VERIFIED','submission_verified':False}

    def patches(self,writer=None):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch.object(chain,'assert_tenant'))
        stack.enter_context(patch.object(chain,'click'))
        stack.enter_context(patch.object(runner,'assert_tenant'))
        stack.enter_context(patch.object(forms_advanced,'_close_object_drawer'))
        stack.enter_context(patch.object(forms_advanced,'_canvas_identity',side_effect=lambda _:deepcopy(self.canvas)))
        native=stack.enter_context(patch.object(native_form,'configure_object_fields',side_effect=writer or self.receipt))
        return stack,native

    def test_real_api_and_native_job_chain_replays_after_receipt_ages_without_reinsertion(self):
        stack,writer=self.patches()
        with stack:
            first=self.build()
            with patch.object(time,'time',return_value=time.time()+3700):replay=self.build()
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(first['native_result']['status'],'NEEDS_VERIFICATION')
        self.assertTrue(replay['native_result']['replayed'])
        self.assertIs(replay['native_placement_required'],False)
        writer.assert_called_once()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
        self.assertEqual(len(self.canvas),3)

    def test_wrong_form_name_prevents_global_contact_field_creation(self):
        self.title.input_value.return_value='Foreign form'
        stack,writer=self.patches()
        with stack,self.assertRaisesRegex(runner.Stop,'exact existing form name'):self.build()
        self.assertEqual(self.api.calls,[]);writer.assert_not_called()

    def test_missing_owner_canvas_stops_before_api(self):
        self.frame.locator.return_value.count.return_value=0
        stack,writer=self.patches()
        with stack,self.assertRaisesRegex(runner.Stop,'existing owner canvas'):self.build()
        self.assertEqual(self.api.calls,[]);writer.assert_not_called()

    def test_form_changes_during_provisioning_prevent_native_insertion(self):
        original=self.api.request
        def request(*args,**kwargs):
            result=original(*args,**kwargs)
            if args[0]=='POST':self.title.input_value.return_value='Renamed during API creation'
            return result
        self.api.request=request
        stack,writer=self.patches()
        with stack,self.assertRaisesRegex(runner.Stop,'target changed'):self.build()
        writer.assert_not_called()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)

    def test_uncertain_native_writer_never_recreates_schema_or_repeats_insertion(self):
        stack,writer=self.patches(writer=TimeoutError('native Save uncertain'))
        with stack:
            with self.assertRaises(runner.Stop):self.build()
            previous=len(self.api.calls)
            with self.assertRaises(runner.Stop):self.build()
        writer.assert_called_once()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
        self.assertTrue(all(call[0]=='GET' for call in self.api.calls[previous:]))

    def test_changed_chain_identity_does_not_reuse_another_form_evidence(self):
        stack,writer=self.patches()
        with stack:
            self.build()
            previous=len(self.api.calls)
            self.plan['expected_form_name']='Other form'
            with self.assertRaisesRegex(runner.Stop,'another form'):self.build()
        self.assertEqual(len(self.api.calls),previous)
        writer.assert_called_once()

    def test_native_evidence_symlink_is_rejected_before_api(self):
        self.root.mkdir()
        (self.root/'native-question-job.json').symlink_to(self.root/'foreign.json')
        stack,writer=self.patches()
        with stack,self.assertRaisesRegex(runner.Stop,'symlink'):self.build()
        self.assertEqual(self.api.calls,[]);writer.assert_not_called()


if __name__=='__main__':unittest.main()
