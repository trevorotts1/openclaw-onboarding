"""Real host/compiler/journal boundaries for captured native control additions."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import editor_replay
import host
import recipe_cli
import skill6_playwright as runner


def request(kind):
    if kind == 'outcomes':
        from test_form_condition_outcomes import rule
        return 'forms.conditions', {
            'location_id':'LOC','location_name':'Fixture Account',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
            'condition':{'rules':[rule(),rule('Display custom message')]}}, 'form_condition_outcomes'
    if kind in ('stack_edit','stack_shrink'):
        from test_form_condition_stack_edits import edit_plan
        condition = edit_plan()
        if kind == 'stack_shrink':
            condition['expected_rules'][0]['clauses'].append({'if_field':'Email','operator':'Is Filled'})
        return 'forms.conditions', {
            'location_id':'LOC','location_name':'Fixture Account',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
            'condition':condition}, 'form_condition_stack'
    factories = {
        'short':('test_quiz_text_questions','step','short_answer_questions','quiz_text_questions'),
        'choice':('test_quiz_choice_questions','step','multiple_choice_questions','quiz_choice_questions'),
        'radio':('test_quiz_radio_creation','step','multiple_choice_questions','quiz_choice_questions'),
        'yes_no':('test_quiz_radio_creation','step','multiple_choice_questions','quiz_choice_questions'),
        'quiz_dropdown':('test_quiz_dropdown_creation','step','multiple_choice_questions','quiz_choice_questions'),
        'quiz_multi':('test_quiz_multi_dropdown','step','multiple_choice_questions','quiz_choice_questions'),
        'written':('test_quiz_written_questions','step','written_answer_questions','quiz_written_questions'),
        'dropdown':('test_dropdown_fields','plan',None,'dropdown_fields'),
        'large':('test_large_text_fields','plan',None,'large_text_fields'),
    }
    fixture,factory,key,module = factories[kind]
    create = getattr(importlib.import_module(fixture),factory)
    payload = (create(2) if kind == 'yes_no' else create())['payload']
    if key is None:
        return 'forms.configure', payload, module
    common = {key:payload.pop(key) for key in ('location_id','location_name','start_url')}
    return 'quizzes.configure', {**common,'configuration':{key:payload}}, module


def compiled(kind):
    operation,data,module = request(kind)
    return runner.validate_job(recipe_cli.compile_recipe(operation,data),Path('.'))


def receipt(job,module):
    step = job['steps'][0]
    native = importlib.import_module('playwright_recipes.'+module)
    value = {'editor_url':job['start_url'],'configuration_sha256':native.configuration_hash(step),
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False}
    action = step['action']
    if action in ('native_dropdown_fields','native_large_text_fields'):
        key = 'dropdown_fields' if action == 'native_dropdown_fields' else 'large_text_fields'
        value.update(status=('DROPDOWN_FIELDS_SAVED_AND_REOPENED' if key == 'dropdown_fields'
            else 'LARGETEXT_FIELDS_SAVED_AND_REOPENED'),
            fields=[{**{key:field[key] for key in ('id','field_key','data_type','native_query_key')},
                'placement':'added'} for field in step['payload'][key]])
    elif action.startswith('quiz_'):
        value.update(status={'quiz_short_answers':'QUIZ_SHORT_ANSWERS_SAVED_AND_REOPENED',
            'quiz_multiple_choices':'QUIZ_MULTIPLE_CHOICES_SAVED_AND_REOPENED',
            'quiz_written_answers':'QUIZ_WRITTEN_ANSWERS_SAVED_AND_REOPENED'}[action],
            kind=action,question_count=len(step['payload']['questions']),
            target_page=step['payload']['target_page'],dependency_api_used=False)
    else:
        outcome = action == 'native_condition_outcomes'
        value.update(status=('CONDITION_OUTCOMES_SAVED_AND_REOPENED' if outcome
            else 'CONDITION_STACK_SAVED_AND_REOPENED'),
            kind='form_condition_outcomes' if outcome else 'form_condition_stack',rule_count=len(step['rules']))
        if outcome:value['disqualification_executed'] = False
    return value


KINDS = ('short','choice','radio','yes_no','quiz_dropdown','quiz_multi','written','dropdown','large','outcomes','stack_edit','stack_shrink')


class FourthControls(unittest.TestCase):
    def test_real_compiler_routes_each_full_request_without_dropping_previous_inventory(self):
        actions = ('quiz_short_answers','quiz_multiple_choices','quiz_multiple_choices','quiz_multiple_choices','quiz_multiple_choices','quiz_multiple_choices','quiz_written_answers',
            'native_dropdown_fields','native_large_text_fields','native_condition_outcomes','native_condition_stack','native_condition_stack')
        for kind,action in zip(KINDS,actions):
            with self.subTest(kind=kind):
                job = compiled(kind)
                self.assertEqual([step['action'] for step in job['steps']],[action])
        _,data,_ = request('stack_edit')
        self.assertEqual(compiled('stack_edit')['steps'][0]['expected_rules'],data['condition']['expected_rules'])

    def test_quiz_creation_refuses_mixed_controls_and_parent_owner_overrides(self):
        for kind in ('short','choice','radio','yes_no','quiz_dropdown','quiz_multi','written'):
            operation,data,_ = request(kind)
            key = next(iter(data['configuration']))
            invalid = []
            other = deepcopy(data);other['configuration']['result_page'] = {};invalid.append(other)
            other = deepcopy(data);other['configuration'][key]['location_id'] = 'FOREIGN';invalid.append(other)
            other = deepcopy(data);other['options'] = {'capture':'foreign'};invalid.append(other)
            for bad in invalid:
                with self.subTest(kind=kind,bad=bad),self.assertRaises(runner.Stop):
                    recipe_cli.compile_recipe(operation,bad)

    def test_native_payloads_cannot_cross_parent_location_or_editor(self):
        for kind in ('short','choice','radio','yes_no','quiz_dropdown','quiz_multi','written','dropdown','large'):
            job = compiled(kind);job['steps'][0]['payload']['start_url'] += '_FOREIGN'
            with self.subTest(kind=kind),self.assertRaises(runner.Stop):runner.validate_job(job,Path('.'))

    def test_real_host_executes_once_and_replays_pending_without_a_second_write(self):
        for kind in KINDS:
            operation,data,module = request(kind);job = compiled(kind)
            native = importlib.import_module('playwright_recipes.'+module)
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root, \
                    patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value=receipt(job,module)) as write:
                probes = {'lanes':{'playwright':{'available':True}},'api_capabilities':{operation:{
                    'location_id':data['location_id'],'observed_at':time.time(),'supported':True,
                    'provider':'public_api','scope_ok':True,'version':'v3'}}}
                provider = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':data['location_id'],'objects':[]})
                first = host.run_recipe(operation,data,probes,root,input_dir='.',page=object(),executors={'public_api':provider})
                with patch('time.time',return_value=time.time()+3700):
                    repeated = host.run_recipe(operation,data,probes,root,input_dir='.',page=object(),executors={'public_api':provider})
                self.assertEqual(first['status'],'NEEDS_VERIFICATION',first)
                self.assertEqual(repeated['status'],'NEEDS_VERIFICATION',repeated)
                write.assert_called_once()
                provider.assert_not_called()
                self.assertFalse(Path(root,'provider-state.json').exists())
                saved = json.loads(Path(root,'state.json').read_text())
                self.assertEqual(saved['current_step_status'],'FINISHED')
                self.assertEqual(saved['status'],'NEEDS_VERIFICATION')

    def test_native_quiz_creation_cannot_delegate_to_an_api_or_generic_browser_provider(self):
        for kind in ('short','choice','radio','yes_no','quiz_multi','written'):
            operation,data,_ = request(kind)
            for lane in ('public_api','official_mcp','skill44','openclaw_extension','agent_browser','computer_use'):
                probes = {'lanes':{lane:{'available':True,'current':True,'enabled':True}},
                    'api_capabilities':{operation:{'location_id':'LOC','observed_at':time.time(),
                        'supported':True,'provider':'public_api','scope_ok':True,'version':'v3'}}}
                provider = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':'LOC','objects':[]})
                with self.subTest(kind=kind,lane=lane),tempfile.TemporaryDirectory() as root:
                    result = host.run_recipe(operation,data,probes,root,input_dir='.',executors={lane:provider})
                    self.assertEqual(result['status'],'CAPTURED_SCRIPT_ROUTE_REQUIRED',result)
                    provider.assert_not_called()
                    self.assertFalse(Path(root,'provider-state.json').exists())
                # The host boundary remains independent of routing correctness.
                with self.subTest(forced_lane=lane,kind=kind),tempfile.TemporaryDirectory() as root, \
                        patch.object(host,'decide',return_value={'lane':lane,'operation':operation}):
                    result = host.run_recipe(operation,data,probes,root,input_dir='.',executors={lane:provider})
                    self.assertEqual(result['status'],'CAPTURED_SCRIPT_ROUTE_REQUIRED',result)
                    provider.assert_not_called()

    def test_invalid_native_quiz_inputs_and_bound_authorization_failures_never_fall_back(self):
        for kind in ('short','choice','written'):
            operation,data,_ = request(kind)
            key = next(iter(data['configuration']))
            invalids = ('invalid','malformed_list','missing_request','null_configuration')
            for variant in (*invalids,401,403):
                value = deepcopy(data)
                cap = {'location_id':'LOC','observed_at':time.time(),'supported':True,
                    'provider':'public_api','scope_ok':True,'version':'v3'}
                if variant == 'invalid':value['configuration'][key]['target_page'] = 99
                elif variant == 'malformed_list':value['configuration'] = [key]
                elif variant == 'missing_request':value['configuration'][key] = None
                elif variant == 'null_configuration':value['configuration'] = None
                else:cap['http_status'] = variant
                provider = Mock()
                with self.subTest(kind=kind,variant=variant),tempfile.TemporaryDirectory() as root,patch.object(host,'run_on_page') as native:
                    result = host.run_recipe(operation,value,{'lanes':{'playwright':{'available':True}},
                        'api_capabilities':{operation:cap}},root,input_dir='.',page=object(),executors={'public_api':provider})
                    self.assertEqual(result['status'],'STOP_INVALID_INPUT' if variant in invalids else 'STOP_AUTH',result)
                    native.assert_not_called();provider.assert_not_called()

    def test_status_only_fresh_result_is_not_completion_and_cannot_be_retried(self):
        for kind in KINDS:
            operation,data,module = request(kind);job = compiled(kind)
            native = importlib.import_module('playwright_recipes.'+module)
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root, \
                    patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value={'status':receipt(job,module)['status']}) as write:
                probes = {'lanes':{'playwright':{'available':True}}}
                first = host.run_recipe(operation,data,probes,root,input_dir='.',page=object())
                second = host.run_recipe(operation,data,probes,root,input_dir='.',page=object())
                self.assertEqual(first['status'],'NEEDS_BROWSER_RECOVERY')
                self.assertEqual(second['status'],'NEEDS_BROWSER_RECOVERY')
                write.assert_called_once()
                state = json.loads(Path(root,'state.json').read_text())
                self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
                self.assertEqual(state['results'],[])

    def test_malformed_first_quiz_receipts_stop_without_blessing_or_second_insertion(self):
        for kind in ('short','choice','radio','yes_no','quiz_dropdown','quiz_multi','written'):
            job = compiled(kind);_,_,module = request(kind)
            native = importlib.import_module('playwright_recipes.'+module)
            for change in ({'question_count':True},{'target_page':2},{'kind':'quiz'},
                    {'configuration_sha256':'0'*64},{'editor_url':job['start_url']+'_OTHER'},
                    {'dependency_api_used':True},{'submission_verified':True},{'behavior_verified':True}):
                with self.subTest(kind=kind,change=change),tempfile.TemporaryDirectory() as root, \
                        patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value={**receipt(job,module),**change}) as write:
                    for _ in range(2):
                        with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
                    write.assert_called_once()

    def test_completed_native_field_receipts_cannot_adopt_unproven_legacy_reuse(self):
        for kind in ('dropdown','large'):
            job = compiled(kind);_,_,module = request(kind);value = receipt(job,module)
            value['fields'][0]['placement'] = 'reused'
            with self.subTest(kind=kind),self.assertRaises(runner.Stop):
                editor_replay._result(job['steps'][0],value,job)

    def test_third_batch_payment_and_course_media_require_complete_fresh_receipts(self):
        from test_course_block_media import inputs
        from test_form_order_confirmation import plan
        with tempfile.TemporaryDirectory() as assets:
            image = Path(assets,'approved.png');image.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
            payment = plan()['payload']
            base = {key:payment.pop(key) for key in ('location_id','location_name','start_url')}
            cases = (
                ('courses.configure_ui',inputs(image),'course_block_media','COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED'),
                ('forms.submission',{**base,'submission':{'mode':'Order Confirmation',**payment}},
                    'form_order_confirmation','ORDER_CONFIRMATION_SAVED_AND_REOPENED'),
            )
            for operation,data,module,status in cases:
                job = runner.validate_job(recipe_cli.compile_recipe(operation,data),Path('.'))
                native = importlib.import_module('playwright_recipes.'+module)
                with self.subTest(module=module),tempfile.TemporaryDirectory() as root, \
                        patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value={'status':status}) as write:
                    for _ in range(2):
                        with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
                    write.assert_called_once()
                    state = json.loads(Path(root,'state.json').read_text())
                    self.assertEqual(state['results'],[])
                    self.assertEqual(state['current_step_status'],'INTENT_RECORDED')

    def test_complete_third_batch_media_and_payment_receipts_stay_pending_on_first_run_and_replay(self):
        from test_course_block_media import inputs
        from test_form_order_confirmation import plan
        with tempfile.TemporaryDirectory() as assets:
            image = Path(assets,'approved.png');image.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
            cases = (
                {'action':'native_course_block_media','payload':inputs(image)},
                plan(),
            )
            for step in cases:
                payload = step['payload'];action = step['action']
                module = 'course_block_media' if action == 'native_course_block_media' else 'form_order_confirmation'
                native = importlib.import_module('playwright_recipes.'+module)
                job = runner.validate_job({**{key:payload[key] for key in ('location_id','location_name','start_url')},
                    'steps':[{'id':'only_step',**step}]},Path('.'))
                value = {'configuration_sha256':native.configuration_hash(payload if action == 'native_course_block_media' else step),
                    'independent_readback':'VERIFIED'}
                if action == 'native_course_block_media':
                    operation,data = 'courses.configure_ui',payload
                    value.update(status='COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED',editor_url=native.theme.editor_url(payload),
                        course_id=payload['course_id'],template_id=payload['template_id'],block_id='BLOCK_A',
                        source_sha256=payload['custom_block_image']['sha256'],image_url_sha256='a'*64,
                        functional_verified=False,activation_performed=False)
                else:
                    contract = payload['checkout_contract']
                    common = {key:payload[key] for key in ('location_id','location_name','start_url')}
                    operation,data = 'forms.submission',{**common,'submission':{'mode':'Order Confirmation',
                        **{key:item for key,item in payload.items() if key not in common}}}
                    value.update(status='ORDER_CONFIRMATION_SAVED_AND_REOPENED',editor_url=payload['start_url'],
                        form_id=payload['form_id'],product_id=contract['product_id'],price_id=contract['price_id'],
                        price_identity='UNIQUE_CATALOG_PRICE',conditional_precedence_present=False,
                        conditional_precedence_acknowledged=False,payment_verified=False,
                        behavior_verified=False,submission_verified=False)
                with self.subTest(action=action),tempfile.TemporaryDirectory() as root, \
                        patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value=value) as write:
                    probes = {'lanes':{'playwright':{'available':True}},'api_capabilities':{operation:{
                        'location_id':payload['location_id'],'observed_at':time.time(),'supported':True,
                        'provider':'public_api','scope_ok':True,'version':'v3'}}}
                    provider = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':payload['location_id'],'objects':[]})
                    for _ in range(2):
                        self.assertEqual(host.run_recipe(operation,data,probes,root,input_dir='.',page=object(),
                            executors={'public_api':provider})['status'],'NEEDS_VERIFICATION')
                    write.assert_called_once()
                    provider.assert_not_called()

    def test_condition_outcome_flags_hash_count_and_expected_stack_are_bound(self):
        job = compiled('outcomes');step = job['steps'][0];value = receipt(job,'form_condition_outcomes')
        for change in ({'disqualification_executed':True},{'disqualification_executed':0},
                {'rule_count':True},{'configuration_sha256':'0'*64},{'kind':'form_condition_stack'}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**value,**change},job)
        job = compiled('stack_edit');value = receipt(job,'form_condition_stack')
        job['steps'][0]['expected_rules'][0]['effect'] = 'Show Field'
        with self.assertRaises(runner.Stop):editor_replay._result(job['steps'][0],value,job)

    def test_new_community_identity_status_requires_complete_fresh_native_proof(self):
        from test_community_creation_identity import step
        data = step();common = data.pop('_context');data.pop('action')
        job = runner.validate_job(recipe_cli.compile_recipe('communities.create',
            {**common,'community':data}),Path('.'))
        for status in ('GROUP_CREATED_SLUG_IDENTIFIED','GROUP_REUSED_IDENTITY_CONFIRMED'):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as root, \
                    patch.object(runner,'assert_tenant'),patch.object(runner,'community',return_value={'status':status}) as write:
                for _ in range(2):
                    with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
                write.assert_called_once()
                state = json.loads(Path(root,'state.json').read_text())
                self.assertEqual(state['results'],[])
                self.assertEqual(state['current_step_status'],'INTENT_RECORDED')

    def test_multi_unique_key_and_resize_plan_bind_primary_fallback_and_replay(self):
        from test_quiz_multi_dropdown import authored
        for count in (2,3,4):
            for fallback in (False,True):
                operation,data,module = request('quiz_multi')
                plan = data['configuration']['multiple_choice_questions']
                plan['questions']=[authored(count)]
                plan.update(create_page=True,new_page_label='Page 2',target_page=2)
                job = runner.validate_job(recipe_cli.compile_recipe(operation,data),Path('.'))
                step = job['steps'][0]
                self.assertEqual(step['payload']['questions'],plan['questions'])
                self.assertNotIn('query_key',step['payload']['questions'][0])
                self.assertNotIn('hidden',step['payload']['questions'][0])
                native = importlib.import_module('playwright_recipes.'+module)
                provider = Mock(return_value={'status':'EDITOR_STEPS_COMPLETE','location_id':data['location_id'],'objects':[]})
                probes = {'lanes':{'playwright':{'available':not fallback},
                    'openclaw_extension':{'available':fallback,'current':fallback}}}
                with self.subTest(count=count,fallback=fallback),tempfile.TemporaryDirectory() as root, \
                        patch.object(runner,'assert_tenant'):
                    page = object()
                    def owned_write(actual_page,actual_step):
                        self.assertIs(actual_page,page)
                        self.assertEqual(actual_step,step)
                        self.assertEqual(json.loads(Path(root,'state.json').read_text())['current_step_status'],'INTENT_RECORDED')
                        return receipt(job,module)
                    with patch.object(native,'configure',side_effect=owned_write) as write:
                        first = host.run_recipe(operation,data,probes,root,input_dir='.',page=page,
                            executors={'public_api':provider,'openclaw_extension':provider})
                        state_path = Path(root,'state.json');saved = state_path.read_bytes()
                        repeated = host.run_recipe(operation,data,probes,root,input_dir='.',page=page,
                            executors={'public_api':provider,'openclaw_extension':provider})
                        self.assertEqual(first['status'],'NEEDS_VERIFICATION',first)
                        self.assertEqual(repeated['status'],'NEEDS_VERIFICATION',repeated)
                        self.assertEqual(state_path.read_bytes(),saved)
                        write.assert_called_once();provider.assert_not_called()
                        changed = deepcopy(job)
                        changed['steps'][0]['payload']['questions'][0]['unique_key']='foreign_literal'
                        with self.assertRaises(runner.Stop):runner.run_on_page(page,changed,root)
                        state = json.loads(saved)
                        state['results'][0]['result']['configuration_sha256']='0'*64
                        state_path.write_text(json.dumps(state))
                        with self.assertRaises(runner.Stop):runner.run_on_page(page,job,root)
                        write.assert_called_once()

    def test_explicit_new_page_intent_survives_frontdoor_hash_and_completed_replay(self):
        for kind in ('short','choice','quiz_dropdown','quiz_multi','written'):
            operation,data,module = request(kind)
            key = next(iter(data['configuration']))
            authored = data['configuration'][key]
            authored.update(create_page=True,new_page_label='Page 2',target_page=2)
            original = deepcopy(data)
            job = runner.validate_job(recipe_cli.compile_recipe(operation,data),Path('.'))
            step = job['steps'][0]
            self.assertEqual(data,original)
            self.assertIs(step['payload']['create_page'],True)
            self.assertEqual(step['payload']['new_page_label'],'Page 2')
            self.assertEqual(step['payload']['target_page'],2)
            self.assertEqual(len(step['payload']['pages']),1)
            native = importlib.import_module('playwright_recipes.'+module)
            value = receipt(job,module)
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root, \
                    patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value=value) as write:
                first = host.run_recipe(operation,data,{'lanes':{'playwright':{'available':True}}},
                    root,input_dir='.',page=object())
                repeated = host.run_recipe(operation,data,{'lanes':{'playwright':{'available':True}}},
                    root,input_dir='.',page=object())
                self.assertEqual(first['status'],'NEEDS_VERIFICATION',first)
                self.assertEqual(repeated['status'],'NEEDS_VERIFICATION',repeated)
                write.assert_called_once()
                path = Path(root,'state.json');state = json.loads(path.read_text())
                saved = state['results'][0]['result']
                self.assertEqual(saved['target_page'],2)
                self.assertEqual(saved['configuration_sha256'],native.configuration_hash(step))
                saved['target_page'] = 1;path.write_text(json.dumps(state))
                with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
                write.assert_called_once()


if __name__ == '__main__':unittest.main()
