"""Portal and payment control integration preserves exact intent and proof."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

import editor_replay
import host
import recipe_cli
import skill6_playwright as runner


class PaymentOutcomeIntegrationTests(unittest.TestCase):
    def job(self):
        from test_form_order_confirmation import plan
        data=plan()['payload']
        base={key:data.pop(key) for key in ('location_id','location_name','start_url')}
        base['submission']={'mode':'Order Confirmation',**data}
        return runner.validate_job(recipe_cli.compile_recipe('forms.submission',base),Path('.'))

    def receipt(self,step):
        from playwright_recipes.form_order_confirmation import configuration_hash
        data=step['payload'];contract=data['checkout_contract']
        return {'status':'ORDER_CONFIRMATION_SAVED_AND_REOPENED','editor_url':data['start_url'],
            'form_id':data['form_id'],'product_id':contract['product_id'],'price_id':contract['price_id'],
            'price_identity':'UNIQUE_CATALOG_PRICE','configuration_sha256':configuration_hash(step),
            'independent_readback':'VERIFIED','conditional_precedence_present':False,
            'conditional_precedence_acknowledged':False,'payment_verified':False,
            'submission_verified':False,'behavior_verified':False}

    def test_payment_owned_mode_has_its_own_writer_and_pending_noncharging_replay(self):
        from playwright_recipes import form_order_confirmation
        job=self.job();step=job['steps'][0]
        self.assertEqual(step['action'],'native_order_confirmation')
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(form_order_confirmation,'configure',return_value=self.receipt(step)) as writer:
            first=runner.run_on_page(object(),job,root);second=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION');self.assertEqual(second['status'],'NEEDS_VERIFICATION')
        writer.assert_called_once()

    def test_payment_receipt_binds_catalog_form_status_hash_and_false_payment_proof(self):
        job=self.job();step=job['steps'][0];receipt=self.receipt(step)
        for change in ({'form_id':'OTHER'},{'product_id':'OTHER'},{'price_id':'OTHER'},
                       {'price_identity':'NATIVE_FORM_PRICE_GUESSED'},{'configuration_sha256':'0'*64},
                       {'payment_verified':True},{'submission_verified':True},{'behavior_verified':True},
                       {'status':'ORDER_CONFIRMATION_REUSED_AND_REOPENED'},
                       {'conditional_precedence_present':True}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)

    def test_order_confirmation_payload_cannot_cross_parent_identity(self):
        job=self.job();job['steps'][0]['payload']['location_name']='OTHER'
        with self.assertRaises(runner.Stop):runner.validate_job(job,Path('.'))

    def test_catalog_auth_refusal_is_terminal_and_never_changes_execution_lane(self):
        from ghl_auth import AuthBridgeError
        inputs={'location_id':'LOC','location_name':'Fixture',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
            'settings':{'allow_custom_sticky_contact':False}}
        # Use a captured ordinary switch name from the real owning registry.
        inputs['settings']={next(iter(runner.FORM_SETTINGS)):False}
        probes={'lanes':{'playwright':{'available':True},'openclaw_extension':{'available':True,'current':True}}}
        provider=Mock()
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(runner,'form_settings',side_effect=AuthBridgeError('fixture denial')) as writer:
            first=host.run_recipe('forms.settings',inputs,probes,root,input_dir='.',page=object(),
                executors={'openclaw_extension':provider})
            second=host.run_recipe('forms.settings',inputs,probes,root,input_dir='.',page=object(),
                executors={'openclaw_extension':provider})
            state=json.loads((Path(root)/'state.json').read_text())
            self.assertEqual(state['error_type'],'AuthBridgeError')
            self.assertTrue((Path(root)/'auth-stop.json').exists())
        self.assertEqual(first['status'],'STOP_AUTH');self.assertEqual(second['status'],'STOP_AUTH_CONTEXT')
        provider.assert_not_called();writer.assert_called_once()


class ConditionStackIntegrationTests(unittest.TestCase):
    def job(self):
        from test_form_condition_stack import plan
        inputs={'location_id':'LOC','location_name':'Fixture',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
            'condition':plan()}
        return runner.validate_job(recipe_cli.compile_recipe('forms.conditions',inputs),Path('.'))

    def receipt(self,step,job):
        from playwright_recipes.form_condition_stack import configuration_hash
        return {'status':'CONDITION_STACK_SAVED_AND_REOPENED','kind':'form_condition_stack',
            'editor_url':job['start_url'],'rule_count':len(step['rules']),
            'configuration_sha256':configuration_hash(step),'independent_readback':'VERIFIED',
            'submission_verified':False,'behavior_verified':False}

    def test_ordered_multi_target_rules_dispatch_once_then_replay_bound_pending_receipt(self):
        from playwright_recipes import form_condition_stack
        job=self.job();step=job['steps'][0];self.assertEqual(step['action'],'native_condition_stack')
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(form_condition_stack,'configure',return_value=self.receipt(step,job)) as writer:
            first=runner.run_on_page(object(),job,root);second=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION');self.assertEqual(second['status'],'NEEDS_VERIFICATION')
        writer.assert_called_once()
        for change in ({'rule_count':1},{'kind':'form_condition_group'},{'configuration_sha256':'0'*64},
                       {'behavior_verified':True},{'submission_verified':True}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**self.receipt(step,job),**change},job)


class CustomBlockMediaIntegrationTests(unittest.TestCase):
    def job(self):
        from test_course_block_media import inputs
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'approved.png';path.write_bytes(b'\x89PNG\r\n\x1a\nFIXTURE')
            data=inputs(path)
        return runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',data),Path('.'))

    def receipt(self,step):
        from playwright_recipes.course_block_media import configuration_hash
        from playwright_recipes.course_theme import editor_url
        plan=step['payload'];asset=plan['custom_block_image']
        return {'status':'COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED','editor_url':editor_url(plan),
            'course_id':plan['course_id'],'template_id':plan['template_id'],'block_id':asset['block_id'],
            'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
            'source_sha256':asset['sha256'],'image_url_sha256':hashlib.sha256(b'https://example.com/new.png').hexdigest(),
            'functional_verified':False,'activation_performed':False}

    def test_uuid_bound_media_dispatch_and_completed_replay_do_not_upload_twice(self):
        from playwright_recipes import course_block_media
        job=self.job();step=job['steps'][0]
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(course_block_media,'configure',return_value=self.receipt(step)) as writer:
            first=runner.run_on_page(object(),job,root);second=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION');self.assertEqual(second['status'],'NEEDS_VERIFICATION')
        writer.assert_called_once()
        receipt=self.receipt(step)
        for change in ({'block_id':'OTHER'},{'source_sha256':'0'*64},{'configuration_sha256':'0'*64},
                       {'image_url_sha256':hashlib.sha256(step['payload']['custom_block_image']['expected_url'].encode()).hexdigest()},
                       {'functional_verified':True},{'activation_performed':True}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)


class BrandingHostIntegrationTests(unittest.TestCase):
    def data(self):
        from test_community_branding import inputs
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'approved.png';path.write_bytes(b'\x89PNG\r\n\x1a\nFIXTURE')
            data=inputs(path)
        return data

    def receipt(self,data):
        from playwright_recipes.community_branding import _receipt
        return _receipt(data,{'logo':'https://example.com/new.png','favicon':None,'cover':None})

    def probes(self,data):
        return {'lanes':{'playwright':{'available':True}},'api_capabilities':{
            'communities.configure':{'location_id':data['location_id'],'observed_at':time.time(),
                'supported':True,'provider':'public_api','scope_ok':True,'version':'v3'}}}

    def test_branding_requires_native_same_session_context_despite_a_generic_api_probe(self):
        from playwright_recipes import community_branding
        data=self.data();provider=Mock()
        with tempfile.TemporaryDirectory() as root,patch.object(host,'execute') as browser:
            result=host.run_recipe('communities.configure',data,self.probes(data),root,input_dir='.',
                executors={'public_api':provider})
        self.assertEqual(result['status'],'PORTAL_CONTEXT_REQUIRED');provider.assert_not_called();browser.assert_not_called()
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant') as guard, \
                patch.object(community_branding,'run_branding',return_value=self.receipt(data)) as writer:
            result=host.run_recipe('communities.configure',data,self.probes(data),root,input_dir='.',
                page=object(),portal_context=object())
        self.assertEqual(result['status'],'NEEDS_VERIFICATION');writer.assert_called_once();guard.assert_not_called()

    def test_branding_outcome_binds_asset_hashes_changed_slots_and_preserved_siblings(self):
        from playwright_recipes import community_branding
        data=self.data();receipt=self.receipt(data)
        for change in ({'source_sha256':{'logo':'0'*64}},{'branding_slots':['cover']},
                       {'preview_sha256':{'logo':None,'favicon':None,'cover':None}},
                       {'preview_sha256':{'logo':'1'*64,'favicon':'2'*64,'cover':None}},
                       {'configuration_sha256':'0'*64},{'functional_verified':True},
                       {'communication_attempted':True},{'controls_verified':1}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root, \
                    patch.object(community_branding,'run_branding',return_value={**receipt,**change}):
                result=host.run_recipe('communities.configure',data,self.probes(data),root,input_dir='.',
                    page=object(),portal_context=object())
            self.assertEqual(result['status'],'NEEDS_BROWSER_RECOVERY')
