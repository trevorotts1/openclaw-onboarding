"""API dependency identities and native placement keep independent journals."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import radio_dependencies as radio
import skill6_playwright as runner
import survey_fields
from playwright_recipes import survey_fields as native_survey
from test_radio_dependencies import Api, capability, question


class RadioSurveyChain(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)/'chain';self.api=Api();self.page=MagicMock()
        self.plan={'location_id':'LOC','location_name':'Fixture Account',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder-v2/SURVEY',
            'expected_slide_count':1,'slide_labels':['P1 - Existing question slide'],
            'target_slide':1,'questions':[question()]}
        self.page.url=self.plan['start_url']
        title=self.page.frame_locator.return_value.get_by_role.return_value
        title.count.return_value=1;title.input_value.return_value='Existing survey'
    def receipt(self,page,step):
        self.assertTrue((self.root/'delivery-state.json').exists())
        self.assertEqual(step['payload']['object_fields'][0]['id'],'NEW0')
        self.assertEqual(step['payload']['field_dependencies']['fields'],step['payload']['object_fields'])
        return {'status':'SURVEY_OBJECT_FIELDS_SAVED_AND_REOPENED','kind':'survey_object_fields',
            'editor_url':page.url,'target_slide':1,'field_count':1,
            'configuration_sha256':native_survey.configuration_hash(step),
            'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False}
    def build(self,**kwargs):
        return radio.build_survey_questions(self.plan,self.root,page=self.page,
            capability=capability(),transport=self.api,**kwargs)
    def test_provision_chain_freezes_native_identity_and_replays_without_second_placement(self):
        with patch.object(runner,'assert_tenant'),patch.object(survey_fields,'_close_initial'), \
                patch.object(survey_fields,'_owner'), \
                patch.object(native_survey,'configure',side_effect=self.receipt) as writer:
            first=self.build()
            later=time.time()+3700
            with patch.object(time,'time',return_value=later):
                replay=self.build()
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(first['native_result']['status'],'NEEDS_VERIFICATION')
        self.assertTrue(replay['native_result']['replayed'])
        self.assertFalse(replay['native_placement_required']);writer.assert_called_once()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
    def test_native_slide_preflight_failure_prevents_global_schema_creation(self):
        with patch.object(runner,'assert_tenant'),patch.object(survey_fields,'_close_initial'), \
                patch.object(survey_fields,'_owner',side_effect=Stop('wrong native slide')):
            with self.assertRaises(Stop):self.build()
        self.assertEqual(self.api.calls,[])
    def test_uncertain_native_stage_never_recreates_schema_or_repeats_placement(self):
        with patch.object(runner,'assert_tenant'),patch.object(survey_fields,'_close_initial'), \
                patch.object(survey_fields,'_owner'), \
                patch.object(native_survey,'configure',side_effect=TimeoutError('native save uncertain')) as writer:
            with self.assertRaises(Stop):self.build()
            calls=len(self.api.calls)
            with self.assertRaises(Stop):self.build()
        writer.assert_called_once()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
        self.assertTrue(all(call[0]=='GET' for call in self.api.calls[calls:]))
    def test_wrong_editor_and_native_evidence_symlink_stop_before_api(self):
        self.page.url=self.page.url.replace('SURVEY','OTHER')
        with self.assertRaises(Stop):self.build()
        self.page.url=self.plan['start_url']
        self.root.mkdir(exist_ok=True);(self.root/'native').symlink_to(self.root/'foreign')
        with self.assertRaises(Stop):self.build()
        self.assertEqual(self.api.calls,[])


Stop=runner.Stop
if __name__=='__main__':unittest.main()
