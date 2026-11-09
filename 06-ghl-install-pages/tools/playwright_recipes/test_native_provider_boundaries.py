"""A broad operation capability cannot replace a concrete native control job."""
from copy import deepcopy
import hashlib
import importlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

import host
import recipe_cli
import skill6_playwright as runner
from test_fourth_control_integration import request,receipt


def form_cases():
    for kind in ('dropdown','large','stack_edit','outcomes'):
        operation,data,module=request(kind)
        yield kind,operation,data,module,'configure'
    from test_form_embed import plan as embed_plan
    from test_object_field_dependencies import payload as radio_plan
    from test_form_tracking import step as tracking_plan
    base={'location_id':'LOC','location_name':'Fixture Account',
          'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM'}
    yield 'embed','forms.configure',{**base,'integration':embed_plan()['integration']},'form_embed','configure'
    yield 'radio_fields','forms.configure',radio_plan()['payload'],'forms_advanced','configure_object_fields'
    yield 'tracking','forms.settings',{**base,**tracking_plan()},'form_tracking','configure'


def probes(operation,data,*,script=True,extension=False):
    return {'lanes':{'playwright':{'available':script},
        'openclaw_extension':{'available':extension,'current':extension}},
        'api_capabilities':{operation:{'location_id':data['location_id'],'observed_at':time.time(),
            'supported':True,'provider':'public_api','scope_ok':True,'version':'v3'}}}


def native_receipt(kind,job,module):
    step=job['steps'][0]
    if kind in ('dropdown','large','stack_edit','outcomes'):return receipt(job,module)
    native=importlib.import_module('playwright_recipes.'+module)
    value={'editor_url':job['start_url'],'independent_readback':'VERIFIED',
           'submission_verified':False,'behavior_verified':False}
    if kind=='tracking':
        return {**value,'status':'FORM_TRACKING_SAVED_AND_REOPENED',
                'configuration_sha256':native.configuration_hash(step)}
    if kind=='embed':
        from test_next_control_integration import FormEmbedIntegrationTests
        return FormEmbedIntegrationTests().receipt(step,job)
    fields=step['payload']['object_fields']
    return {**value,'status':'OBJECT_FIELDS_SAVED_AND_REOPENED',
        'configuration_sha256':native.object_fields_configuration_hash(step),
        'fields':[{**{key:field[key] for key in ('id','field_key','data_type')},'placement':'added'}
                  for field in fields]}


class NativeFormProviderBoundaries(unittest.TestCase):
    def test_full_native_form_receipts_win_over_broad_status_only_api_callback(self):
        for kind,operation,data,module,handler in form_cases():
            job=runner.validate_job(recipe_cli.compile_recipe(operation,data),Path('.'))
            native=importlib.import_module('playwright_recipes.'+module)
            api=Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':data['location_id'],'objects':[]})
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root, \
                 patch.object(runner,'assert_tenant'), \
                 patch.object(native,handler,return_value=native_receipt(kind,job,module)) as writer:
                result=host.run_recipe(operation,data,probes(operation,data),root,input_dir='.',
                    page=object(),executors={'public_api':api})
                self.assertEqual(result['status'],'NEEDS_VERIFICATION',result)
                self.assertEqual(result['route']['lane'],'playwright')
                self.assertTrue(Path(root,'state.json').exists())
                self.assertFalse(Path(root,'provider-state.json').exists())
                api.assert_not_called();writer.assert_called_once()

    def test_missing_script_cannot_turn_native_form_contract_into_generic_provider_completion(self):
        for kind,operation,data,module,_ in form_cases():
            runner.validate_job(recipe_cli.compile_recipe(operation,data),Path('.'))
            for extension in (False,True):
                api=Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':data['location_id'],'objects':[]})
                browser=Mock(return_value={'status':'EDITOR_STEPS_COMPLETE','location_id':data['location_id'],'objects':[]})
                with self.subTest(kind=kind,extension=extension),tempfile.TemporaryDirectory() as root:
                    result=host.run_recipe(operation,data,probes(operation,data,script=False,extension=extension),
                        root,input_dir='.',executors={'public_api':api,'openclaw_extension':browser})
                    self.assertNotIn(result['status'],('API_STEPS_COMPLETE','EDITOR_STEPS_COMPLETE','ALREADY_EXECUTED'),result)
                    self.assertFalse(Path(root,'provider-state.json').exists())
                    api.assert_not_called();browser.assert_not_called()


def other_cases(asset):
    from test_new_control_integration import meeting_input
    from test_course_blocks import inputs as blocks_input
    from test_course_theme_media import inputs as background_input
    from test_quiz_results_integration import BASE as quiz_base,config
    from test_object_field_freshness_integration import survey_data
    from test_survey_ui import rule as survey_rule
    yield 'cohosts','meetings.update',meeting_input()
    setup=meeting_input();setup['meeting'].pop('cohosts')
    yield 'room_setup','meetings.setup',setup
    blocks=blocks_input();yield 'course_blocks','courses.configure_ui',blocks
    theme={key:value for key,value in blocks.items() if key!='custom_blocks'}
    theme.update(expected_values={'template_title':'Inactive theme'},changes={'template_title':'Approved theme'})
    yield 'course_theme','courses.configure_ui',theme
    yield 'course_background','courses.configure_ui',background_input(asset)
    yield 'quiz_result','quizzes.configure',{**quiz_base,'configuration':{'result_page':config()}}
    yield 'survey_fields','surveys.configure',survey_data()
    common={'location_id':'LOC','location_name':'Fixture Account',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder-v2/SURVEY'}
    yield 'survey_single','surveys.configure',{**common,'configuration':survey_rule()}
    form={**common,'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM'}
    yield 'form_css','forms.style',{**form,'custom_css':'input {color:red}'}
    yield 'form_message','forms.submission',{**form,'submission':{'mode':'Message','message':'Approved message'}}
    from test_form_notifications import CONFIG
    yield 'form_notifications','forms.notifications',{**form,'notifications':{'email_notification':deepcopy(CONFIG)}}
    original=survey_rule();metadata={key:original.pop(key) for key in ('expected_slide_count','slide_labels')}
    yield 'survey_stack','surveys.configure',{**common,'configuration':{**metadata,'rules':[original]}}


class OtherNativeProviderBoundaries(unittest.TestCase):
    def test_other_valid_compiled_native_actions_cannot_be_skipped_by_an_api_cap(self):
        with tempfile.TemporaryDirectory() as assets:
            asset=Path(assets,'approved.png');asset.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
            for kind,operation,data in other_cases(asset):
                job=runner.validate_job(recipe_cli.compile_recipe(operation,data),Path('.'))
                self.assertTrue(job['steps'])
                api=Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':data['location_id'],'objects':[]})
                with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root, \
                     patch.object(host,'run_on_page',return_value={'status':'NEEDS_VERIFICATION'}) as native:
                    result=host.run_recipe(operation,data,probes(operation,data),root,input_dir='.',
                        page=object(),executors={'public_api':api})
                    self.assertEqual(result['status'],'NEEDS_VERIFICATION',result)
                    self.assertEqual(result['route']['lane'],'playwright');api.assert_not_called();native.assert_called_once()

    def test_missing_script_cannot_delegate_other_typed_native_jobs_to_generic_providers(self):
        with tempfile.TemporaryDirectory() as assets:
            asset=Path(assets,'approved.png');asset.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
            for kind,operation,data in other_cases(asset):
                runner.validate_job(recipe_cli.compile_recipe(operation,data),Path('.'))
                for extension in (False,True):
                    api=Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':data['location_id'],'objects':[]})
                    browser=Mock(return_value={'status':'EDITOR_STEPS_COMPLETE','location_id':data['location_id'],'objects':[]})
                    with self.subTest(kind=kind,extension=extension),tempfile.TemporaryDirectory() as root:
                        result=host.run_recipe(operation,data,probes(operation,data,script=False,extension=extension),
                            root,input_dir='.',executors={'public_api':api,'openclaw_extension':browser})
                        self.assertNotIn(result['status'],('API_STEPS_COMPLETE','EDITOR_STEPS_COMPLETE','ALREADY_EXECUTED'),result)
                        self.assertFalse(Path(root,'provider-state.json').exists())
                        api.assert_not_called();browser.assert_not_called()

    def test_canonical_course_product_media_keeps_its_api_executor(self):
        import course_media
        from test_course_media import Api,capability
        with tempfile.TemporaryDirectory() as directory:
            asset=Path(directory,'approved.png');asset.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
            data={'location_id':'LOC','location_name':'Fixture Account',
                'start_url':'https://app.convertandflow.com/v2/location/LOC/dashboard',
                'product_id':'COURSE','expected_updated_at':'v1','api_capability':capability(),
                'media_assets':[{'field':'logoImage','file':str(asset),
                    'sha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
                    'name':'Approved logo','expected_url':'https://example.com/old.png'}]}
            api=Api();root=Path(directory,'evidence')
            with patch.object(course_media.delivery,'Skill44Transport',return_value=api), \
                 patch.object(course_media,'_upload',return_value={'http':200,'fileId':'MEDIA','url':'https://example.com/new.png'}) as upload, \
                 patch.object(host,'run_on_page') as native:
                result=host.run_recipe('courses.update',data,probes('courses.update',data),root,input_dir='.')
            self.assertEqual(result['status'],'NEEDS_VERIFICATION',result)
            self.assertEqual(result['route']['lane'],'public_api')
            upload.assert_called_once();native.assert_not_called()
            self.assertTrue(any(call[0]=='PUT' for call in api.calls))


if __name__=='__main__':unittest.main()
