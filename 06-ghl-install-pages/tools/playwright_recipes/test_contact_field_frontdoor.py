"""Named host/CLI joins use real dependency and native journals, no live writes."""
from contextlib import ExitStack
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import host
import recipe_cli
import skill6_playwright as runner
from test_contact_field_dependencies import capability
import test_form_contact_field_chain as chain_fixture

frontdoor = importlib.import_module('playwright_recipes.contact_field_frontdoor')
forms = importlib.import_module('playwright_recipes.forms_advanced')


class ContactFrontdoor(unittest.TestCase):
    def setUp(self):
        self.fixture = chain_fixture.ContactFormChain(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.root = self.root / 'contact-fields'

    def data(self):
        plan = deepcopy(self.fixture.plan)
        return {**{key:plan[key] for key in frontdoor.COMMON},
            'contact_field_plan':{key:value for key,value in plan.items() if key not in frontdoor.COMMON}}

    def probes(self, lane='playwright'):
        return {'lanes':{lane:{'available':True,'current':True,'enabled':True}},
            'contact_field_capability':capability()}

    def patches(self, writer=None):
        stack = ExitStack()
        for owner,name in ((frontdoor.chain,'assert_tenant'),(frontdoor.chain,'click'),
                (runner,'assert_tenant'),(forms,'_close_object_drawer')):
            stack.enter_context(patch.object(owner, name))
        stack.enter_context(patch.object(forms,'_canvas_identity',
            side_effect=lambda _:deepcopy(self.fixture.canvas)))
        stack.enter_context(patch.object(frontdoor.dependencies,'ContactFieldTransport',
            return_value=self.fixture.api))
        native = stack.enter_context(patch.object(self.fixture.native(),'configure',
            side_effect=writer or self.fixture.receipt))
        return stack, native

    def run_host(self, probes=None, **kwargs):
        return host.run_recipe('forms.configure',self.data(),probes or self.probes(),
            self.root,input_dir='.',page=self.fixture.page,**kwargs)

    def test_compiler_retains_entire_authored_plan_in_one_exclusive_parent_bound_step(self):
        job = runner.validate_job(recipe_cli.compile_recipe('forms.configure',self.data()),Path('.'))
        self.assertEqual(len(job['steps']),1)
        self.assertEqual(job['steps'][0]['action'],frontdoor.ACTION)
        self.assertEqual(job['steps'][0]['payload'],self.fixture.plan)
        self.assertNotIn('capability',json.dumps(job))
        for bad in ({'fields':[{}]},{'options':{'capture':'anything'}},{'field_dependencies':{}},
                {'integration':{}}):
            with self.subTest(bad=bad),self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('forms.configure',{**self.data(),**bad})
        job['steps'][0]['payload']['start_url'] += '_OTHER'
        with self.assertRaises(runner.Stop):runner.validate_job(job,Path('.'))

    def test_nested_owner_or_capability_overrides_refuse_before_transport(self):
        for key in ('location_id','start_url','capability','transport'):
            data = self.data();data['contact_field_plan'][key] = 'override'
            with self.subTest(key=key),self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('forms.configure',data)
        self.assertEqual(self.fixture.api.calls,[])

    def test_real_host_primary_and_page_fallback_complete_once_without_provider_callback(self):
        for kind,lane in (('large','playwright'),('dropdown','openclaw_extension')):
            if kind == 'dropdown':
                self.fixture.as_dropdown()
                self.root = self.root.parent / 'dropdown-run'
                self.fixture.root = self.root / 'contact-fields'
            generic = Mock()
            stack,native = self.patches()
            with self.subTest(kind=kind,lane=lane),stack:
                first = self.run_host(self.probes(lane),executors={lane:generic,'public_api':generic})
                self.assertEqual(first['status'],'NEEDS_VERIFICATION',first)
                self.assertEqual(first['route']['lane'],lane)
                receipt = first['result']['results'][0]['result']
                self.assertEqual(receipt['status'],'CONTACT_FIELDS_SAVED_AND_REOPENED')
                self.assertEqual(receipt['field_count'],1)
                self.assertFalse(receipt['submission_verified'])
                self.assertFalse(receipt['native_placement_required'])
                self.assertTrue(receipt['dependency_api_used'])
                calls = deepcopy(self.fixture.api.calls)
                # Completed outer replay needs neither fresh API access nor a
                # second native insertion; capability is outside input hash.
                repeated = self.run_host({'lanes':self.probes(lane)['lanes']},executors={lane:generic})
                self.assertEqual(repeated['status'],'NEEDS_VERIFICATION',repeated)
                self.assertTrue(repeated['result']['replayed'])
                self.assertEqual(self.fixture.api.calls,calls)
                native.assert_called_once()
            generic.assert_not_called()
            self.assertEqual(sum(call[0]=='POST' for call in self.fixture.api.calls),int(kind=='large'))
            self.assertTrue((self.root/'contact-fields/delivery-state.json').exists())
            self.assertTrue((self.root/'contact-fields/native/state.json').exists())

    def test_missing_or_foreign_capability_stops_before_browser_api_and_recovery_journal(self):
        for cap in (None,{**capability(),'location_id':'OTHER'},
                {**capability(),'scopes':['locations/customFields.readonly']}):
            stack,native = self.patches()
            with self.subTest(cap=cap),stack:
                probes = self.probes();probes['contact_field_capability'] = cap
                result = self.run_host(probes)
                self.assertEqual(result['status'],'CONTACT_FIELD_CAPABILITY_REQUIRED',result)
                self.assertFalse(result['browser_used']);native.assert_not_called()
            self.assertEqual(self.fixture.api.calls,[])
            self.assertFalse(self.root.exists())
        job = runner.validate_job(recipe_cli.compile_recipe('forms.configure',self.data()),Path('.'))
        with self.assertRaises(runner.Stop):runner.execute(job,self.root)
        self.assertFalse((self.root/'auth-runtime').exists())

    def test_uncertain_api_write_cannot_be_repeated_by_fresh_capability_or_lane(self):
        self.fixture.api.uncertain = True
        stack,native = self.patches()
        with stack:
            one = self.run_host();calls = deepcopy(self.fixture.api.calls)
            two = self.run_host(self.probes('agent_browser'))
        self.assertEqual(one['status'],'NEEDS_BROWSER_RECOVERY',one)
        self.assertEqual(two['status'],'NEEDS_BROWSER_RECOVERY',two)
        self.assertEqual(self.fixture.api.calls,calls)
        self.assertEqual(sum(call[0]=='POST' for call in calls),1)
        native.assert_not_called()

    def test_changed_native_binding_or_tampered_receipt_cannot_bless_completed_replay(self):
        stack,native = self.patches()
        with stack:
            self.assertEqual(self.run_host()['status'],'NEEDS_VERIFICATION')
            path = self.root/'state.json';original = path.read_bytes()
            for mutate in (
                lambda value:value['api_fields'][0].update(id='FOREIGN'),
                lambda value:value['native_receipt']['fields'][0].update(native_query_key='foreign'),
                lambda value:value.update(submission_verified=True),
                lambda value:value.update(configuration_sha256='0'*64),
                lambda value:value.pop('native_receipt')):
                saved = json.loads(original)
                mutate(saved['results'][0]['result'])
                path.write_text(json.dumps(saved))
                result = self.run_host()
                self.assertEqual(result['status'],'NEEDS_BROWSER_RECOVERY',result)
                path.write_bytes(original)
            self.fixture.plan['native_bindings'][0]['native_query_key'] = 'different'
            self.assertEqual(self.run_host()['status'],'NEEDS_BROWSER_RECOVERY')
        native.assert_called_once()
        self.assertEqual(sum(call[0]=='POST' for call in self.fixture.api.calls),1)

    def test_generic_providers_cannot_replace_native_chain_or_supply_missing_capability(self):
        for lane in ('public_api','official_mcp','skill44','openclaw_extension','agent_browser','computer_use'):
            callback = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':'LOC','objects':[]})
            with self.subTest(lane=lane):
                value = host.run_recipe('forms.configure',self.data(),self.probes(lane),self.root,
                    input_dir='.',executors={lane:callback})
                self.assertIn(value['status'],('CAPTURED_SCRIPT_ROUTE_REQUIRED','CONTACT_FIELD_CAPABILITY_REQUIRED'))
                callback.assert_not_called()
        self.assertEqual(self.fixture.api.calls,[])

    def test_host_cli_check_validates_runtime_capability_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory);inputs = directory/'inputs.json';probes = directory/'probes.json'
            inputs.write_text(json.dumps(self.data()));probes.write_text(json.dumps(self.probes()))
            args = ['--operation','forms.configure','--inputs',str(inputs),'--probes',str(probes),
                '--evidence-root',str(self.root),'--check']
            with patch('builtins.print') as output:
                self.assertEqual(host.main(args),0)
                self.assertEqual(json.loads(output.call_args.args[0])['status'],'VALIDATED_ONLY')
                probes.write_text(json.dumps({'lanes':self.probes()['lanes']}))
                self.assertEqual(host.main(args),2)
        self.assertFalse(self.root.exists());self.assertEqual(self.fixture.api.calls,[])

    def test_managed_host_forwards_only_runtime_receipt_to_maintained_executor(self):
        outcome = {'status':'NEEDS_VERIFICATION','results':[]}
        probes = self.probes()
        with patch.object(host,'execute',return_value=outcome) as execute:
            value = host.run_recipe('forms.configure',self.data(),probes,self.root,input_dir='.')
        self.assertEqual(value['status'],'NEEDS_VERIFICATION')
        self.assertEqual(execute.call_args.kwargs,{'contact_field_capability':probes['contact_field_capability']})

    def test_completed_managed_replay_uses_saved_identity_without_browser_or_live_capability(self):
        stack,native = self.patches()
        with stack:
            first = self.run_host()
            self.assertEqual(first['status'],'NEEDS_VERIFICATION',first)
            calls = deepcopy(self.fixture.api.calls)
            job = runner.validate_job(recipe_cli.compile_recipe('forms.configure',self.data()),Path('.'))
            with patch.object(frontdoor,'configure') as chain:
                repeated = runner.execute(job,self.root)
            self.assertEqual(repeated['status'],'NEEDS_VERIFICATION')
            self.assertTrue(repeated['replayed']);chain.assert_not_called()
            self.assertEqual(self.fixture.api.calls,calls)
        native.assert_called_once()

    def test_direct_runtime_rejects_mixed_or_foreign_parent_jobs_before_browser(self):
        original = runner.validate_job(recipe_cli.compile_recipe('forms.configure',self.data()),Path('.'))
        for defect in ('mixed','foreign'):
            job = deepcopy(original)
            if defect == 'mixed':job['steps'].append({'id':'other','action':'native_form_tracking'})
            else:job['steps'][0]['payload']['location_name'] = 'Other account'
            with self.subTest(defect=defect),self.assertRaises(runner.Stop):
                runner.execute(job,self.root,contact_field_capability=capability())
        self.assertFalse((self.root/'auth-runtime').exists())


if __name__ == '__main__':unittest.main()
