"""Second native-control batch joins exact inputs to execution and saved replay."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import editor_replay
import host
import recipe_cli
import route
import skill6_playwright as runner


class NativeDynamicIntegrationTests(unittest.TestCase):
    def data(self):
        from test_meeting_dynamic import inputs
        return {**inputs(),'integration_mode':'dynamic_calendar_room'}

    def job(self):
        return runner.validate_job(recipe_cli.compile_recipe('meetings.integrate',self.data()),Path('.'))

    def result(self,step):
        from playwright_recipes.meeting_dynamic import configuration_hash
        plan=step['payload']
        return {'status':'DYNAMIC_MEETING_LOCATION_SAVED_AND_REOPENED',
            'location_id':plan['location_id'],'calendar_id':plan['calendar_id'],'staff_id':plan['staff_id'],
            'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
            'native_location_kind':'Meeting Room','appointment_created':False,'meeting_started':False,
            'dynamic_room_generation_verified':False,'functional_verified':False}

    def test_explicit_native_mode_selects_ui_without_a_generic_profile_or_static_api(self):
        data=self.data();probes={'lanes':{'playwright':{'available':True}},
            'api_capabilities':{'meetings.integrate':{'location_id':data['location_id'],
                'observed_at':time.time(),'supported':True,'provider':'public_api','scope_ok':True,'version':'v3'}}}
        observed,error=host._recipe_readiness('meetings.integrate',data,probes,Path('.'))
        self.assertIsNone(error)
        self.assertEqual(route.decide('meetings.integrate',data['location_id'],observed,inputs=data)['lane'],'playwright')
        self.assertEqual(self.job()['steps'][0]['action'],'native_dynamic_meeting_location')
        bad=deepcopy(data);bad['staff_dependency']['complete']=False
        observed,error=host._recipe_readiness('meetings.integrate',bad,probes,Path('.'))
        self.assertIsNotNone(error)
        self.assertNotEqual(route.decide('meetings.integrate',bad['location_id'],observed,inputs=bad)['lane'],'playwright')

    def test_dynamic_runtime_and_replay_keep_generated_room_proof_pending_without_rebooking(self):
        from playwright_recipes import meeting_dynamic
        job=self.job();step=job['steps'][0]
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(meeting_dynamic,'configure',return_value=self.result(step)) as writer:
            first=runner.run_on_page(object(),job,root);replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION');writer.assert_called_once()

    def test_dynamic_replay_binds_calendar_staff_config_status_and_false_proof(self):
        job=self.job();step=job['steps'][0];receipt=self.result(step)
        safe=editor_replay._result(step,receipt,job)
        self.assertEqual(safe['native_location_kind'],'Meeting Room')
        for change in ({'calendar_id':'OTHER'},{'staff_id':'OTHER'},{'location_id':'OTHER'},
                       {'configuration_sha256':'0'*64},{'native_location_kind':'Custom'},
                       {'status':'DYNAMIC_MEETING_LOCATION_REUSED_AND_REOPENED'},
                       {'appointment_created':True},{'meeting_started':True},
                       {'dynamic_room_generation_verified':True},{'functional_verified':True},
                       {'independent_readback':'REQUIRED'}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)

    def test_completed_dynamic_replay_survives_old_inventory_without_a_new_live_write(self):
        from playwright_recipes import meeting_dynamic
        data=self.data();data['staff_dependency']['observed_at']=time.time()-7200
        job=runner.validate_job(recipe_cli.compile_recipe('meetings.integrate',data),Path('.'))
        step=job['steps'][0];receipt=self.result(step)
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'):
            with patch.object(meeting_dynamic,'configure',return_value=receipt):
                runner.run_on_page(object(),job,root)
            checked=runner.validate_job(recipe_cli.compile_recipe('meetings.integrate',data),Path('.'))
            with patch.object(meeting_dynamic,'configure') as writer:
                replay=runner.run_on_page(object(),checked,root)
            self.assertEqual(replay['status'],'NEEDS_VERIFICATION');writer.assert_not_called()
        with self.assertRaises(runner.Stop):meeting_dynamic.configure(object(),step['payload'])

    def test_dynamic_payload_cannot_override_job_identity(self):
        for key,value in (('location_name','Other'),('location_id','Other')):
            job=self.job();job['steps'][0]['payload'][key]=value
            with self.subTest(key=key),self.assertRaises(runner.Stop):runner.validate_job(job,Path('.'))


class NativeBackgroundIntegrationTests(unittest.TestCase):
    def job(self):
        from test_course_theme_media import inputs
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'asset.png';path.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
            data=inputs(path)
        return runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',data),Path('.'))

    def result(self,step):
        from playwright_recipes.course_theme_media import configuration_hash
        from playwright_recipes.course_theme import editor_url
        plan=step['payload']
        return {'status':'COURSE_THEME_MEDIA_SAVED_AND_REOPENED','editor_url':editor_url(plan),
            'course_id':plan['course_id'],'template_id':plan['template_id'],
            'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
            'background_url_sha256':hashlib.sha256(b'https://example.com/saved.png').hexdigest(),
            'source_sha256':plan['background_image']['sha256'],
            'functional_verified':False,'activation_performed':False}

    def test_background_runtime_and_pending_replay_never_upload_twice(self):
        from playwright_recipes import course_theme_media
        job=self.job();step=job['steps'][0]
        self.assertEqual(step['action'],'native_course_theme_media')
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(course_theme_media,'configure',return_value=self.result(step)) as writer:
            first=runner.run_on_page(object(),job,root);replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION');writer.assert_called_once()

    def test_background_replay_binds_source_course_template_hash_and_native_pending_proof(self):
        job=self.job();step=job['steps'][0];receipt=self.result(step)
        self.assertEqual(editor_replay._result(step,receipt,job)['source_sha256'],receipt['source_sha256'])
        for change in ({'source_sha256':'0'*64},{'configuration_sha256':'0'*64},
                       {'course_id':'OTHER'},{'template_id':'OTHER'},{'background_url_sha256':'bad'},
                       {'background_url_sha256':hashlib.sha256(step['payload']['background_image']['expected_url'].encode()).hexdigest()},
                       {'functional_verified':True},{'activation_performed':True},
                       {'independent_readback':'REQUIRED'}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)

    def test_background_fresh_completion_refuses_unbound_source_without_repeating_upload(self):
        from playwright_recipes import course_theme_media
        job=self.job();step=job['steps'][0];valid=self.result(step)
        invalid=[{'status':valid['status']},{**valid,'source_sha256':'0'*64},
            {**valid,'background_url_sha256':hashlib.sha256(step['payload']['background_image']['expected_url'].encode()).hexdigest()}]
        for receipt in invalid:
            with self.subTest(receipt=receipt),tempfile.TemporaryDirectory() as root, \
                    patch.object(runner,'assert_tenant'),patch.object(course_theme_media,'configure',return_value=receipt) as writer:
                for _ in range(2):
                    with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
                writer.assert_called_once()
                state=json.loads(Path(root,'state.json').read_text())
                self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
                self.assertEqual(state['results'],[])

class CreatedCommunityIntegrationTests(unittest.TestCase):
    def job(self):
        from test_community_creation_identity import step
        fields=step();base=fields.pop('_context');fields.pop('action')
        return runner.validate_job(recipe_cli.compile_recipe('communities.create',{**base,'community':fields}),Path('.'))

    def receipt(self,step):
        digest=hashlib.sha256(step['slug'].encode()).hexdigest()
        return {'status':'GROUP_CREATED_SLUG_IDENTIFIED','name':step['name'],'slug':step['slug'],
            'discovery':False,'deleted':False,'requested_slug_sha256':digest,
            'observed_slug_sha256':digest,'native_name_seen_after_reload':True,'group_status':'Active',
            'identity_source':'native_creation_redirect','slug_identity_verified':True,
            'portal_identity_verified':False,'discovery_verified':False,'independent_readback':'VERIFIED',
            'functional_verified':False,'group_activation_attempted':False,
            'native_deactivation_attempted':False,'inactive_verified':False}

    def test_created_slug_native_result_is_bound_and_completion_keeps_portal_proof_pending(self):
        from playwright_recipes import community_creation
        job=self.job();step=job['steps'][0];receipt=self.receipt(step)
        self.assertEqual(editor_replay._result(step,receipt,job)['identity_source'],'native_creation_redirect')
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(community_creation,'configure',return_value=receipt) as writer:
            first=runner.run_on_page(object(),job,root);replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION');writer.assert_called_once()

    def test_created_slug_replay_requires_observed_binding_and_pending_portal_flags(self):
        job=self.job();step=job['steps'][0];receipt=self.receipt(step)
        for change in ({'observed_slug_sha256':'0'*64},{'identity_source':'name_only'},
                       {'slug_identity_verified':False},{'portal_identity_verified':True},
                       {'discovery_verified':True},{'native_name_seen_after_reload':False},
                       {'independent_readback':'REQUIRED'}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)

class FormEmbedIntegrationTests(unittest.TestCase):
    def job(self):
        from test_form_embed import plan
        data={'location_id':'LOC','location_name':'Fixture Account',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
            'integration':plan()['integration']}
        return runner.validate_job(recipe_cli.compile_recipe('forms.configure',data),Path('.'))

    def receipt(self,step,job):
        from playwright_recipes.form_embed import configuration_hash
        from test_form_embed import state,exported
        code=exported()
        return {'status':'FORM_EMBED_EXPORTED_AND_REREAD','kind':'form_embed',
            'editor_url':job['start_url'],'form_id':'FORM',
            'configuration_sha256':configuration_hash(step),'export_settings':state(),
            'embed_code':code,'embed_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'independent_readback':'VERIFIED','settings_persisted':False,
            'installation_verified':False,'behavior_verified':False,'submission_verified':False}

    def test_embed_export_retains_exact_revalidated_code_on_pending_replay(self):
        from playwright_recipes import form_embed
        job=self.job();step=job['steps'][0];receipt=self.receipt(step,job)
        self.assertEqual(step['action'],'native_form_embed')
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(form_embed,'configure',return_value=receipt) as writer:
            first=runner.run_on_page(object(),job,root);replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION');writer.assert_called_once()
        self.assertEqual(replay['results'][0]['result']['embed_code'],receipt['embed_code'])
        self.assertFalse(replay['results'][0]['result']['settings_persisted'])
        self.assertFalse(replay['results'][0]['result']['installation_verified'])

    def test_embed_receipt_rejects_tampered_code_layout_hash_and_false_installation_claim(self):
        job=self.job();step=job['steps'][0];receipt=self.receipt(step,job)
        for change in ({'embed_code':receipt['embed_code'].replace('/widget/form/FORM','/widget/form/OTHER')},
                       {'embed_sha256':'0'*64},{'configuration_sha256':'0'*64},
                       {'export_settings':{**receipt['export_settings'],'layout':'Standard'}},
                       {'settings_persisted':True},{'installation_verified':True},{'behavior_verified':True},
                       {'editor_url':job['start_url'].replace('/FORM','/OTHER')}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)

    def test_embed_intake_rejects_mixed_field_writes_or_a_foreign_editor(self):
        from test_form_embed import plan
        base={'location_id':'LOC','location_name':'Fixture Account',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
            'integration':plan()['integration']}
        for extra in ({'fields':[]},{'add_fields':['Email']},{'options':{}},{'consent':{}},
                      {'object_fields':[]},{'field_dependencies':{}},{'address_fields':[]}):
            with self.subTest(extra=extra),self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('forms.configure',{**base,**extra})
        data={**base,'start_url':base['start_url'].replace('/FORM','/OTHER')}
        with self.assertRaises(runner.Stop):runner.validate_job(recipe_cli.compile_recipe('forms.configure',data),Path('.'))

class CommunityCourseHostIntegrationTests(unittest.TestCase):
    def data(self):
        from test_community_courses import inputs
        return inputs()

    def probes(self):
        return {'lanes':{'playwright':{'available':True}},'recorded_profiles':[]}

    def receipt(self,data):
        from playwright_recipes.community_courses import _receipt
        return _receipt(data,reused=False,skipped=True)

    def test_native_course_association_requires_portal_context_without_app_auth_seed(self):
        data=self.data()
        with tempfile.TemporaryDirectory() as root,patch.object(host,'execute') as browser:
            outcome=host.run_recipe('communities.configure',data,self.probes(),root,input_dir='.')
        self.assertEqual(outcome['status'],'PORTAL_CONTEXT_REQUIRED');browser.assert_not_called()

    def test_host_selects_portal_writer_without_running_app_tenant_guard(self):
        from playwright_recipes import community_courses
        data=self.data();page=object();context=object()
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant') as app_guard, \
                patch.object(community_courses,'run_courses',return_value=self.receipt(data)) as writer:
            result=host.run_recipe('communities.configure',data,self.probes(),root,
                input_dir='.',page=page,portal_context=context)
        self.assertEqual(result['status'],'NEEDS_VERIFICATION')
        self.assertEqual(result['result']['group_id'],data['course_associations']['expected_group_id'])
        app_guard.assert_not_called();writer.assert_called_once()
        self.assertIs(writer.call_args.kwargs['portal_context'],context)

    def test_portal_course_outcome_cannot_cross_ids_hash_or_claim_communication_or_functional_proof(self):
        from playwright_recipes import community_courses
        data=self.data();receipt=self.receipt(data)
        for change in ({'group_id':'OTHER'},{'course_id':'OTHER'},{'configuration_sha256':'0'*64},
                       {'functional_verified':True},{'communication_attempted':True},
                       {'visibility':'All members'},{'status':'PASS'},{'verification_required':False}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root, \
                    patch.object(community_courses,'run_courses',return_value={**receipt,**change}):
                result=host.run_recipe('communities.configure',data,self.probes(),root,
                    input_dir='.',page=object(),portal_context=object())
            self.assertEqual(result['status'],'NEEDS_BROWSER_RECOVERY')

    def test_generic_community_api_probe_and_provider_cannot_bypass_native_portal_identity(self):
        data=self.data();probes=self.probes()
        probes['api_capabilities']={'communities.configure':{
            'location_id':data['location_id'],'observed_at':time.time(),'supported':True,
            'provider':'public_api','scope_ok':True,'version':'v3'}}
        from unittest.mock import Mock
        provider=Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':data['location_id'],
                                  'objects':[],'verification_required':True})
        with tempfile.TemporaryDirectory() as root:
            outcome=host.run_recipe('communities.configure',data,probes,root,input_dir='.',
                executors={'public_api':provider})
        self.assertEqual(outcome['status'],'PORTAL_CONTEXT_REQUIRED');provider.assert_not_called()
        probes['lanes']={'openclaw_extension':{'available':True,'current':True}}
        with tempfile.TemporaryDirectory() as root:
            outcome=host.run_recipe('communities.configure',data,probes,root,input_dir='.',
                executors={'public_api':provider,'openclaw_extension':provider})
        self.assertEqual(outcome['status'],'COURSE_ASSOCIATION_SCRIPT_ROUTE_REQUIRED');provider.assert_not_called()

    def test_course_association_cannot_drop_other_portal_requests_or_accept_foreign_tenant(self):
        data=self.data();data['details']={}
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('communities.configure',data)
        data=self.data();job=runner.validate_job(recipe_cli.compile_recipe('communities.configure',data),Path('.'))
        job['steps'][0]['payload']['location_name']='OTHER'
        with self.assertRaises(runner.Stop):runner.validate_job(job,Path('.'))
