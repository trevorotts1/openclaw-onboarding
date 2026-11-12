import copy
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

from ghl_order_elements import _SELFTEST_GRAPH
from playwright_recipes.native_purchase_flow import prepare_flow, dispatch_flow, verify_journey
from playwright_recipes.skill6_playwright import Stop


class PurchaseFlowTests(unittest.TestCase):
    def test_journey_graph_and_sandbox_guards(self):
        def event(role, outcome, dest, charge=None):
            return {'role': role, 'outcome': outcome, 'next_page_id': dest,
                    'native_session_id': 'sess', 'charge_id': charge,
                    'provider_verified': True, 'explicit': True}
        evidence = {'environment': 'sandbox', 'provider_test_mode_verified': True,
                    'provider_evidence_ref': 'provider-record', 'published_journey_evidence_ref': 'trace',
                    'location_id': 'LOC_TEST', 'native_session_id': 'sess',
                    'confirmation_page_id': 'SELFTEST-TY', 'confirmation_observed': True,
                    'page_bindings': {r:{'status':'PASS','location_id':'LOC_TEST',
                        'graph_page_id':pid,'native_page_id':pid,'native_step_id':'step-'+r,'source':'readback'}
                        for r,pid in [('checkout','SELFTEST-CHECKOUT'),('upsell_1','SELFTEST-U1'),
                            ('downsell_1','SELFTEST-D1'),('upsell_2','SELFTEST-U2'),('thank_you','SELFTEST-TY')]},
                    'duplicate_prevention': {'repeat_attempt_observed': True, 'provider_verified': True,
                        'evidence_ref': 'provider-replay', 'successful_charge_ids': ['c1']},
                    'events': [event('checkout', 'payment_succeeded', 'SELFTEST-U1', 'c1'),
                               event('upsell_1', 'explicit_decline', 'SELFTEST-D1'),
                               event('downsell_1', 'payment_succeeded', 'SELFTEST-U2', 'c2'),
                               event('upsell_2', 'explicit_decline', 'SELFTEST-TY')]}
        self.assertTrue(verify_journey(_SELFTEST_GRAPH, evidence)['ok'])
        for change in ('live', 'duplicate', 'session', 'failed', 'confirmation'):
            bad = copy.deepcopy(evidence)
            if change == 'live': bad['environment'] = 'live'
            if change == 'duplicate': bad['events'][2]['charge_id'] = 'c1'
            if change == 'session': bad['events'][1]['native_session_id'] = 'other'
            if change == 'failed': bad['events'][1]['outcome'] = 'payment_failed'
            if change == 'confirmation': bad['confirmation_page_id'] = 'other'
            self.assertFalse(verify_journey(_SELFTEST_GRAPH, bad)['ok'], change)

    def test_journal_stops_uncertain_retry_and_resumes_completed(self):
        stage = {'id':'checkout', 'depends_on':[], 'job':{}}
        flow = {'graph_hash':'graph','location_id':'LOC_TEST','stages':[stage]}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'journal.json'
            with self.assertRaises(RuntimeError):
                dispatch_flow(flow, path, lambda _: (_ for _ in ()).throw(RuntimeError('disconnect')))
            with self.assertRaises(Stop): dispatch_flow(flow, path, lambda _: {'status':'EDITOR_STEPS_COMPLETE'})
            path.unlink()
            calls = []
            dispatch_flow(flow, path, lambda s: calls.append(s) or {'status':'EDITOR_STEPS_COMPLETE'})
            dispatch_flow(flow, path, lambda s: calls.append(s))
            self.assertEqual(len(calls), 1)

    def test_shared_host_routes_real_compiled_stage_and_journals(self):
        import host
        stage = {'id':'layout', 'kind':'design', 'role':'checkout', 'operation':'pages.layout',
                 'inputs':{'location_id':'LOC_TEST', 'location_name':'Test',
                           'start_url':'https://app.example/v2/location/LOC_TEST/page-builder/SELFTEST-CHECKOUT',
                           'layout':{'section_id':'section_fixture','columns':2}}, 'depends_on':[]}
        data = {'location_id':'LOC_TEST', 'route_graph':_SELFTEST_GRAPH, 'stages':[stage]}
        probes = {'api_capabilities':{}, 'lanes':{'playwright':{'available':True}}}
        with tempfile.TemporaryDirectory() as root:
            with patch.object(host, 'run_on_page', return_value={'status':'EDITOR_STEPS_COMPLETE'}) as run:
                result = host.run_recipe('checkout.purchase_flow', data, probes, root, input_dir='.', page=SimpleNamespace(url=stage['inputs']['start_url']))
            self.assertEqual(result['status'], 'FLOW_STAGES_COMPLETE')
            self.assertTrue(result['verification_required'])
            self.assertEqual(run.call_args.args[1]['steps'][0]['action'], 'page_layout')
            self.assertTrue((Path(root)/'purchase-flow-journal.json').exists())

    def test_decline_target_must_be_graph_edge(self):
        data = {'location_id':'LOC_TEST','page_id':'SELFTEST-U1',
                'start_url':'https://app.example/v2/location/LOC_TEST/page-builder/SELFTEST-U1',
                'purchase_action':{'kind':'decline','target_step_id':'SELFTEST-TY'}}
        stage = {'id':'decline','kind':'decline','role':'upsell_1',
                 'operation':'checkout.configure_native','inputs':data,'depends_on':[]}
        with self.assertRaises(Stop): prepare_flow(_SELFTEST_GRAPH, [stage])

    def test_folder_host_requires_real_scoped_leaf_and_journal(self):
        import host
        import playwright_recipes.page_folders as folders
        probes = {'api_capabilities':{},'lanes':{'playwright':{'available':True}}}
        data = {'location_id':'LOC_TEST','location_name':'Test',
                'start_url':'https://app.example/v2/location/LOC_TEST/funnels-websites/funnels',
                'folder_name':'Test folder','allow_creation':True}
        with tempfile.TemporaryDirectory() as root:
            with patch.object(folders, 'ensure_folder', return_value={'id':'f'}) as ensure, patch('playwright_recipes.skill6_playwright.assert_tenant'):
                result = host.run_recipe('funnels.create_folder', data, probes, root,
                                         input_dir='.', page=SimpleNamespace(goto=lambda *a,**k: None))
            self.assertEqual(result['status'], 'EDITOR_STEPS_COMPLETE')
            self.assertEqual(ensure.call_args.kwargs['journal_path'], Path(root).resolve()/'folder.json')
            bad = dict(data, allow_creation=False)
            self.assertEqual(host.run_recipe('funnels.create_folder', bad, probes, root,
                                             input_dir='.', page=object())['status'], 'STOP_INVALID_INPUT')

    def test_pending_payment_verification_does_not_block_saved_editor_stage(self):
        stage = {'id':'checkout', 'depends_on':[], 'job':{}}
        flow = {'graph_hash':'graph','location_id':'LOC_TEST','stages':[stage]}
        receipt = {'status':'NEEDS_VERIFICATION','result':{'status':'NEEDS_VERIFICATION',
                    'current_step_status':'FINISHED','results':[{'id':'native_checkout'}]}}
        with tempfile.TemporaryDirectory() as d:
            state = dispatch_flow(flow, Path(d)/'journal.json', lambda _: receipt)
            self.assertEqual(state['stages']['checkout']['status'], 'complete')
            self.assertEqual(state['stages']['checkout']['receipt']['status'], 'NEEDS_VERIFICATION')

    def test_graph_native_mapping_and_separate_action_controls(self):
        from copy import deepcopy
        from test_pages_checkout import inputs
        graph = deepcopy(_SELFTEST_GRAPH)
        bindings = {role:{'status':'PASS','location_id':'LOC_TEST','graph_page_id':pid,
                   'native_page_id':page,'native_step_id':step,'source':'readback'}
                    for role,pid,page,step in [('upsell_1','SELFTEST-U1','actual-u1','step-u1'),
                                               ('upsell_2','SELFTEST-U2','actual-u2','step-u2'),
                                               ('downsell_1','SELFTEST-D1','actual-d1','step-d1')]}
        data = inputs();data.update(location_id='LOC_TEST',page_id='actual-u1',step_id='step-u1',
                    start_url='https://app.example/v2/location/LOC_TEST/page-builder/actual-u1')
        data['checkout_contract'].update(location_id='LOC_TEST',upsell_step_id='step-u1')
        data['purchase_action']={'kind':'accept','target_step_id':'step-u2'}
        stage = {'id':'accept','kind':'purchase','role':'upsell_1','operation':'checkout.configure_native',
                 'inputs':data,'depends_on':[]}
        decline = deepcopy(stage);decline.update(id='decline',kind='decline',depends_on=['accept'])
        decline['inputs']['purchase_action']={'kind':'decline','target_step_id':'step-d1'}
        with self.assertRaises(Stop): prepare_flow(graph,[stage,decline],bindings)
        decline['inputs']['component_id']='other-native-control'
        result=prepare_flow(graph,[stage,decline],bindings)
        self.assertEqual(len(result['stages']),2)
        decline['inputs']['purchase_action']['target_step_id']='SELFTEST-D1'
        with self.assertRaises(Stop): prepare_flow(graph,[stage,decline],bindings)

    def test_checkout_style_inputs_reach_native_compiler(self):
        from playwright_recipes.recipe_cli import compile_recipe
        from test_checkout_ui import inputs
        data=inputs();data.pop('mode');data.pop('products')
        data['theme_preset']='Clay'
        self.assertEqual(compile_recipe('checkout.configure_ui',data)['steps'][0]['payload']['theme_preset'],'Clay')
        data.pop('theme_preset');data['theme_colors']={'accent':'#123456'};data['theme_typography']={'headline_size_desktop':32,'alignment':'center'}
        data['contact_field_order']=['fullName','email','phone','company','address','country','state','city','zip']
        payload=compile_recipe('checkout.configure_ui',data)['steps'][0]['payload']
        self.assertEqual(payload['theme_colors']['accent'], '#123456')
        self.assertEqual(payload['contact_field_order'][-1], 'zip')
        self.assertEqual(payload['theme_typography']['alignment'], 'center')

    def test_flow_rejects_wrong_binding_and_path_ids(self):
        stage = {'id':'../bad','kind':'checkout','role':'checkout','operation':'checkout.configure_native',
                 'inputs':{'location_id':'LOC_TEST','page_id':'SELFTEST-CHECKOUT'},'depends_on':[]}
        with self.assertRaises(Stop): prepare_flow(_SELFTEST_GRAPH, [stage])
        stage['id'] = 'ok'; stage['inputs']['page_id'] = 'wrong'
        with self.assertRaises(Stop): prepare_flow(_SELFTEST_GRAPH, [stage])

if __name__ == '__main__': unittest.main()
