"""New control paths keep compiler, tenant, runtime and replay contracts joined."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import course_media
import editor_replay
import host
from playwright_recipes import meeting_cohosts
import recipe_cli
import skill6_playwright as runner
from test_course_media import Api, capability


BASE = {'location_id':'LOC', 'location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/dashboard'}


def meeting_input():
    return {**BASE, 'meeting':{'name':'Fixture room', 'slug':'fixture-room',
        'waiting_room':True, 'guest_users':False, 'open_room':False,
        'allow_creation':False, 'expected_room_id':'https://rooms.example/fixture-room',
        'cohosts':{'expected':[{'name':'Old Fixture','email':'old@example.invalid'}],
                   'desired':[{'name':'New Fixture','email':'new@example.invalid'}],
                   'access_change_acknowledged':True}}}


class CoHostIntegrationTests(unittest.TestCase):
    def job(self, data=None):
        return runner.validate_job(recipe_cli.compile_recipe('meetings.update', data or meeting_input()), Path('.'))

    def receipt(self, step):
        return {'status':'COHOSTS_SAVED_AND_REOPENED', 'location_id':'LOC',
            'room_id':'https://rooms.example/fixture-room',
            'configuration_sha256':meeting_cohosts.write_configuration_hash(step['payload']),
            'cohost_count':1, 'addition_count':1, 'removal_count':1,
            'independent_readback':'VERIFIED', 'meeting_started':False,
            'functional_verified':False, 'notification_behavior_verified':False}

    def test_compiler_uses_dedicated_writer_without_an_earlier_metadata_mutation(self):
        job=self.job()
        self.assertEqual([step['action'] for step in job['steps']], ['meeting_cohosts'])
        self.assertEqual(job['steps'][0]['payload']['cohosts'], meeting_input()['meeting']['cohosts'])
        with patch.object(meeting_cohosts,'configure',return_value={'fixture':True}) as writer:
            self.assertEqual(runner.meeting_cohosts(object(),job['steps'][0]), {'fixture':True})
        self.assertEqual(writer.call_args.args[1],job['steps'][0]['payload'])

    def test_creation_and_missing_roster_acknowledgment_are_refused(self):
        data=meeting_input();data['meeting']['allow_creation']=True
        with self.assertRaises(runner.Stop):
            runner.validate_job(recipe_cli.compile_recipe('meetings.setup',data),Path('.'))
        data=meeting_input();data['meeting']['cohosts'].pop('access_change_acknowledged')
        with self.assertRaises(runner.Stop):self.job(data)
        data=meeting_input();data['meeting'].pop('expected_room_id')
        with self.assertRaises(runner.Stop):self.job(data)

    def test_payload_cannot_override_job_identity_or_runner_action(self):
        for change in ({'location_id':'OTHER'}, {'start_url':BASE['start_url'].replace('LOC','OTHER')},
                       {'location_name':'Other'}, {'action':'meeting'}, {'_context':BASE}):
            job=self.job();job['steps'][0]['payload'].update(change)
            with self.subTest(change=change), self.assertRaises(runner.Stop):runner.validate_job(job,Path('.'))

    def test_replay_binds_roster_room_status_counts_and_preserves_pending_proof(self):
        job=self.job();step=job['steps'][0];receipt=self.receipt(step)
        safe=editor_replay._result(step,receipt,job)
        self.assertEqual(safe['room_id'],receipt['room_id'])
        self.assertNotIn('cohosts',safe)
        for change in ({'configuration_sha256':'0'*64}, {'room_id':'https://rooms.example/other'},
                       {'cohost_count':2}, {'addition_count':False}, {'removal_count':0},
                       {'status':'COHOSTS_REUSED_AND_REOPENED'}, {'independent_readback':'REQUIRED'},
                       {'meeting_started':True}, {'functional_verified':True},
                       {'notification_behavior_verified':True}, {'location_id':'OTHER'}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)

    def test_runtime_journals_writer_once_and_replay_never_reassigns(self):
        job=self.job();step=job['steps'][0]
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(meeting_cohosts,'configure',return_value=self.receipt(step)) as writer, \
                patch.object(meeting_cohosts,'verify_completed') as verify:
            page=object();first=runner.run_on_page(page,job,root)
            replay=runner.run_on_page(page,job,root)
            verify.assert_called_once_with(page,step['payload'],self.receipt(step))
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION')
        self.assertTrue(replay['replayed'])
        writer.assert_called_once()


class FormConditionGroupIntegrationTests(unittest.TestCase):
    def job(self):
        data={**BASE, 'start_url':BASE['start_url'].replace('/dashboard','/form-builder-v2/FORM'),
            'condition':{'clauses':[{'if_field':'Email','operator':'Contains','value':'@'},
                                    {'if_field':'First Name','operator':'Is Filled'}],
                         'match':'all','effect':'Hide Field','target':'Last Name'}}
        return runner.validate_job(recipe_cli.compile_recipe('forms.conditions',data),Path('.'))

    def receipt(self,step,job):
        from playwright_recipes.form_conditions import configuration_hash
        return {'status':'CONDITION_GROUP_SAVED_AND_REOPENED','kind':'form_condition_group',
            'editor_url':job['start_url'],'configuration_sha256':configuration_hash(step),
            'clause_count':2,'independent_readback':'VERIFIED',
            'submission_verified':False,'behavior_verified':False}

    def test_compound_form_rule_compiles_and_runtime_dispatches_with_pending_replay(self):
        from playwright_recipes import form_conditions
        job=self.job();step=job['steps'][0]
        self.assertEqual(step['action'],'native_condition_group')
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(form_conditions,'configure',return_value=self.receipt(step,job)) as writer:
            first=runner.run_on_page(object(),job,root)
            replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION')
        writer.assert_called_once()

    def test_group_replay_binds_editor_hash_count_kind_and_pending_proof(self):
        job=self.job();step=job['steps'][0];receipt=self.receipt(step,job)
        for change in ({'configuration_sha256':'0'*64}, {'clause_count':1}, {'kind':'form_condition'},
                       {'editor_url':job['start_url'].replace('/FORM','/OTHER')},
                       {'independent_readback':'REQUIRED'}, {'submission_verified':True},
                       {'behavior_verified':True}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)

    def test_legacy_single_condition_keeps_its_existing_handler(self):
        data={**BASE,'condition':{'if_field':'Email','operator':'Is Filled',
                                 'effect':'Hide Field','target':'Last Name'}}
        job=runner.validate_job(recipe_cli.compile_recipe('forms.conditions',data),Path('.'))
        self.assertEqual(job['steps'][0]['action'],'native_condition')


class CourseMediaHostIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.file=self.root/'approved.png'
        self.file.write_bytes(b'\x89PNG\r\n\x1a\nFIXTURE_APPROVED')
        self.inputs={**BASE,'product_id':'COURSE','expected_updated_at':'v1',
            'api_capability':capability(),
            'media_assets':[{'field':'logoImage','file':str(self.file),
                'sha256':hashlib.sha256(self.file.read_bytes()).hexdigest(),
                'name':'Approved logo','expected_url':'https://example.com/old.png'}]}
        self.probes={'api_capabilities':{'courses.update':{
            'location_id':'LOC','observed_at':time.time(),'supported':True,
            'provider':'public_api','scope_ok':True,'version':'v3'}}}

    def test_host_uses_media_executor_and_pending_bound_replay_without_reupload(self):
        api=Api();root=self.root/'evidence'
        def upload(*args):
            self.assertEqual(json.loads((root/'provider-state.json').read_text())['status'],'PROVIDER_INTENT_RECORDED')
            return {'http':200,'fileId':'MEDIA','url':'https://example.com/new.png'}
        with patch.object(course_media.delivery,'Skill44Transport',return_value=api), \
                patch.object(course_media,'_upload',side_effect=upload) as uploader, \
                patch.object(host,'execute') as browser:
            first=host.run_recipe('courses.update',self.inputs,self.probes,root,input_dir='.')
            count=len(api.calls)
            replay=host.run_recipe('courses.update',self.inputs,self.probes,root,input_dir='.')
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION')
        self.assertTrue(replay['replayed'])
        self.assertEqual(len(api.calls),count);uploader.assert_called_once();browser.assert_not_called()
        self.assertEqual(first['result']['objects'],[{'kind':'course','id':'COURSE'}])

    def test_check_mode_uses_media_schema_without_network_or_evidence(self):
        data=self.root/'inputs.json';probes=self.root/'probes.json';evidence=self.root/'evidence'
        data.write_text(json.dumps(self.inputs));probes.write_text(json.dumps(self.probes))
        argv=['--operation','courses.update','--inputs',str(data),'--probes',str(probes),
              '--evidence-root',str(evidence),'--check']
        output=io.StringIO()
        with redirect_stdout(output),patch.object(course_media.delivery,'Skill44Transport') as api:
            code=host.main(argv)
        self.assertEqual(code,0);self.assertEqual(json.loads(output.getvalue())['status'],'VALIDATED_ONLY')
        self.assertFalse(evidence.exists());api.assert_not_called()

    def test_bad_media_scope_never_uploads_or_enters_browser_fallback(self):
        self.inputs['api_capability']['scopes'].remove('medias.write')
        with patch.object(course_media.delivery,'Skill44Transport') as api,patch.object(host,'execute') as browser:
            result=host.run_recipe('courses.update',self.inputs,self.probes,self.root/'evidence',input_dir='.')
        self.assertEqual(result['status'],'PROVIDER_RECONCILIATION_REQUIRED')
        api.assert_not_called();browser.assert_not_called()

    def test_media_provider_target_is_bound_on_fresh_execution_and_saved_replay(self):
        for objects in ([], [{'kind':'course','id':'OTHER'}],
                        [{'kind':'course','id':'COURSE'},{'kind':'course','id':'COURSE'}]):
            with self.subTest(objects=objects),tempfile.TemporaryDirectory() as directory:
                def provider(**kwargs):
                    return {'status':'API_STEPS_COMPLETE','location_id':'LOC',
                        'objects':objects,'verification_required':True,'functional_verified':False}
                result=host.run_recipe('courses.update',self.inputs,self.probes,directory,
                    input_dir='.',executors={'public_api':provider})
                self.assertEqual(result['status'],'PROVIDER_RECONCILIATION_REQUIRED')
        with tempfile.TemporaryDirectory() as directory:
            def provider(**kwargs):
                return {'status':'API_STEPS_COMPLETE','location_id':'LOC',
                    'objects':[{'kind':'course','id':'COURSE'}],
                    'verification_required':True,'functional_verified':False}
            first=host.run_recipe('courses.update',self.inputs,self.probes,directory,
                input_dir='.',executors={'public_api':provider})
            self.assertEqual(first['status'],'NEEDS_VERIFICATION')
            path=Path(directory)/'provider-state.json';state=json.loads(path.read_text())
            state['outcome']['objects']=[{'kind':'course','id':'OTHER'}]
            path.write_text(json.dumps(state))
            with patch.object(course_media.delivery,'Skill44Transport') as api:
                replay=host.run_recipe('courses.update',self.inputs,self.probes,directory,input_dir='.')
            self.assertEqual(replay['status'],'PROVIDER_RECONCILIATION_REQUIRED')
            api.assert_not_called()

    def test_http_media_executor_does_not_replace_official_mcp(self):
        self.probes['api_capabilities']['courses.update']['provider']='official_mcp'
        with patch.object(course_media.delivery,'Skill44Transport') as api:
            result=host.run_recipe('courses.update',self.inputs,self.probes,self.root/'evidence',input_dir='.')
        self.assertEqual(result['status'],'HANDOFF_REQUIRED');api.assert_not_called()

class CourseBlockIntegrationTests(unittest.TestCase):
    def job(self):
        from test_course_blocks import inputs
        data=inputs()
        data['custom_blocks']['append']=[{
            'heading':'Appended', 'content':'Authored plain text', 'button_text':'Continue',
            'button_url':'https://example.com/next','button_visibility':'show',
            'button_type':'solid','button_alignment':'left'}]
        return runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',data),Path('.'))

    def receipt(self,step):
        from playwright_recipes.course_blocks import configuration_hash
        from playwright_recipes.course_theme import editor_url
        plan=step['payload']
        return {'status':'COURSE_BLOCKS_SAVED_AND_REOPENED','editor_url':editor_url(plan),
            'course_id':plan['course_id'],'template_id':plan['template_id'],
            'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
            'added_block_ids':['GENERATED'],
            'block_ids':[row['id'] for row in plan['custom_blocks']['expected_inventory']]+['GENERATED'],
            'functional_verified':False,'activation_performed':False}

    def test_custom_block_job_is_dedicated_and_replay_binds_generated_ids(self):
        job=self.job();step=job['steps'][0];receipt=self.receipt(step)
        self.assertEqual(step['action'],'native_course_blocks')
        self.assertEqual(editor_replay._result(step,receipt,job)['added_block_ids'],['GENERATED'])
        for change in ({'block_ids':['GENERATED']},{'added_block_ids':[]},
                       {'block_ids':['categoryBlock','BLOCK_A','BLOCK_B','BLOCK_A'],'added_block_ids':['BLOCK_A']},
                       {'course_id':'OTHER'},{'template_id':'OTHER'},{'configuration_sha256':'0'*64},
                       {'functional_verified':True},{'activation_performed':True},
                       {'editor_url':receipt['editor_url'].replace('/COURSE/','/OTHER/')},
                       {'independent_readback':'REQUIRED'}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)

    def test_custom_block_execution_replays_without_appending_a_second_block(self):
        from playwright_recipes import course_blocks
        job=self.job();step=job['steps'][0]
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(course_blocks,'configure',return_value=self.receipt(step)) as writer:
            first=runner.run_on_page(object(),job,root)
            replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION');writer.assert_called_once()

    def test_block_payload_cannot_cross_tenant_or_include_silently_ignored_theme_changes(self):
        from test_course_blocks import inputs
        data=inputs();data['changes']={'hero_title':'Ignored'}
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('courses.configure_ui',data)
        job=self.job();job['steps'][0]['payload']['location_name']='OTHER'
        with self.assertRaises(runner.Stop):runner.validate_job(job,Path('.'))

class FormTrackingIntegrationTests(unittest.TestCase):
    def job(self):
        data={**BASE,'start_url':BASE['start_url'].replace('/dashboard','/form-builder-v2/FORM'),
            'tracking':{'expected':{'pixel_id':''},'changes':{'pixel_id':'123456789'}}}
        return runner.validate_job(recipe_cli.compile_recipe('forms.settings',data),Path('.'))

    def receipt(self,step,job):
        from playwright_recipes.form_tracking import configuration_hash
        return {'status':'FORM_TRACKING_SAVED_AND_REOPENED','editor_url':job['start_url'],
            'configuration_sha256':configuration_hash(step),'independent_readback':'VERIFIED',
            'behavior_verified':False,'submission_verified':False}

    def test_tracking_has_dedicated_dispatch_and_pending_idempotent_replay(self):
        from playwright_recipes import form_tracking
        job=self.job();step=job['steps'][0]
        self.assertEqual(step['action'],'native_form_tracking')
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(form_tracking,'configure',return_value=self.receipt(step,job)) as writer:
            first=runner.run_on_page(object(),job,root)
            replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION');writer.assert_called_once()

    def test_tracking_receipt_binds_hash_editor_and_false_event_proof(self):
        job=self.job();step=job['steps'][0];receipt=self.receipt(step,job)
        for change in ({'configuration_sha256':'0'*64},
                       {'editor_url':receipt['editor_url'].replace('/FORM','/OTHER')},
                       {'behavior_verified':True},{'submission_verified':True},
                       {'independent_readback':'REQUIRED'}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)
