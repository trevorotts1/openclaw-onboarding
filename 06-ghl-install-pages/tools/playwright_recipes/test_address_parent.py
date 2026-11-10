"""Parent Address preservation, fresh receipt and public CLI replay contracts."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import address_parent as native
import editor_replay
import recipe_cli
import skill6_playwright as runner


def inputs():
    children={label:{'query_key':query,'label':label,'placeholder':'','short_label':'',
        'required':False,'hidden':False,'hidden_value':None} for label,query in native.child._ADDRESS_QUERIES.items()}
    return {'location_id':'LOC','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
        'address_parent':{'form_name':'Fixture form',
            'expected_inventory':{**{query:'group' for query in native.child._ADDRESS_QUERIES.values()},'email':'email'},
            'expected_children':children,
            'expected_controls':{'autocomplete':False,'search_required':False},
            'controls':{'autocomplete':True,'search_required':True}}}


def step():
    data=inputs()
    return {'id':'address1','action':'native_address_parent','payload':{
        **{key:data[key] for key in ('location_id','location_name','start_url')},**data['address_parent']}}


class ParentContracts(unittest.TestCase):
    def test_compiler_binds_full_inventory_and_rejects_unbound_or_invalid_profiles(self):
        data=inputs();job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',data),Path('.'))
        self.assertEqual(job['steps'][0]['payload'],step()['payload'])
        for change in ('extra_step','foreign_payload','non_boolean','missing_child'):
            invalid=deepcopy(job)
            if change=='extra_step':invalid['steps'].append({'id':'navigate1','action':'navigate','area':'Sites'})
            elif change=='foreign_payload':invalid['steps'][0]['payload']['location_name']='Foreign'
            elif change=='non_boolean':invalid['steps'][0]['payload']['controls']['autocomplete']=1
            else:invalid['steps'][0]['payload']['expected_children'].pop('City')
            with self.subTest(change=change),self.assertRaises(runner.Stop):runner.validate_job(invalid,Path('.'))
        data['fields']=[{'field':'First Name','required':False}]
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',data)

    def test_options_cannot_be_silently_discarded_by_parent_address_compilation(self):
        data=inputs()
        data['options']={'capture_source':'separate fixture','steps':[]}
        with self.assertRaisesRegex(runner.Stop,'independent preservation-bound job'):
            recipe_cli.compile_recipe('forms.configure',data)

    def test_receipt_requires_full_bound_controls_and_false_behavior_claims(self):
        plan=step();page=Mock();page.url=plan['payload']['start_url'];receipt=native._receipt(page,plan)
        self.assertEqual(native.validate_receipt(receipt,plan),receipt)
        for key,value in [('controls',{'autocomplete':1,'search_required':True}),
                          ('behavior_verified',True),('configuration_sha256','0'*64),
                          ('editor_url',page.url+'other')]:
            bad={**receipt,key:value}
            with self.subTest(key=key),self.assertRaises(runner.Stop):native.validate_receipt(bad,plan)
        changed=deepcopy(plan);changed['payload']['expected_children']['City']['placeholder']='changed'
        with self.assertRaises(runner.Stop):native.validate_receipt(receipt,changed)

    def test_fresh_runner_validates_receipt_and_completed_replay_reads_current_native_state(self):
        job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',inputs()),Path('.'))
        from playwright_recipes import address_parent as leaf
        page=Mock();page.url=job['start_url'];receipt=leaf._receipt(page,job['steps'][0])
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
             patch.object(leaf,'configure',return_value=receipt) as writer, \
             patch.object(leaf,'verify',return_value=receipt) as verify:
            runner.run_on_page(page,job,root)
            replay=runner.run_on_page(page,job,root)
            self.assertTrue(replay['replayed']);writer.assert_called_once();verify.assert_called_once()
            verify.side_effect=runner.Stop('native sibling drift')
            with self.assertRaises(runner.Stop):runner.run_on_page(page,job,root)
            self.assertEqual(writer.call_count,1)

    def test_familiar_but_unbound_fresh_receipt_leaves_uncertain_journal(self):
        job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',inputs()),Path('.'))
        from playwright_recipes import address_parent as leaf
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
             patch.object(leaf,'configure',return_value={'status':'ADDRESS_PARENT_SAVED_AND_REOPENED'}) as writer:
            with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
            with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
            writer.assert_called_once()

    def test_invalid_public_execute_refuses_before_browser_import(self):
        job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',inputs()),Path('.'))
        job['steps'][0]['payload']['location_name']='Foreign'
        with tempfile.TemporaryDirectory() as root,patch.dict('sys.modules',{'browser_manager':None}), \
             self.assertRaisesRegex(runner.Stop,'parent job'):
            runner.execute(job,root)


    def test_public_execute_completed_replay_acquires_page_and_checks_fresh_state(self):
        import os
        import sys
        import types
        job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',inputs()),Path('.'))
        from playwright_recipes import address_parent as leaf
        page=Mock();page.url=job['start_url'];receipt=leaf._receipt(page,job['steps'][0])
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
             patch.object(leaf,'configure',return_value=receipt) as writer:
            runner.run_on_page(page,job,root)
            pw=Mock();pw.chromium.connect_over_cdp.return_value.contexts=[types.SimpleNamespace(pages=[page])]
            manager=Mock();manager.__enter__=Mock(return_value=pw);manager.__exit__=Mock(return_value=False)
            package=types.ModuleType('playwright');package.__path__=[]
            sync=types.ModuleType('playwright.sync_api');sync.sync_playwright=Mock(return_value=manager)
            with patch.dict(sys.modules,{'playwright':package,'playwright.sync_api':sync}), \
                 patch.dict(os.environ,{'GHL_MANAGED_CDP_URL':'http://127.0.0.1:9222','GHL_BROWSER_LOCK_DIR':root+'/locks'}), \
                 patch.object(leaf,'verify',side_effect=runner.Stop('current native controls drifted')) as verify:
                with self.assertRaisesRegex(runner.Stop,'drifted'):runner.execute(job,root)
                verify.assert_called_once();writer.assert_called_once()


class LifecycleTests(unittest.TestCase):
    def exercise(self,before,wanted,*,lost=False,child_drift=False):
        plan=step();data=plan['payload'];data['expected_controls']=dict(before);data['controls']=dict(wanted)
        current=dict(before);persisted=dict(before);events=[]
        frame=Mock();frame.get_by_role.return_value.count.return_value=1
        frame.get_by_role.return_value.is_enabled.return_value=True
        page=Mock();page.url=data['start_url']
        class Switch:
            def __init__(self,key):self.key=key
            def get_attribute(self,name):
                if name=='class':return 'n-switch--disabled' if self.key=='search_required' and not current['autocomplete'] else 'n-switch'
                if name=='aria-checked':return 'true' if current[self.key] else 'false'
        controls={key:Switch(key) for key in native.FLAGS}
        def observed(_):return controls,dict(current)
        def click(node):
            if isinstance(node,Switch):
                if 'disabled' in node.get_attribute('class'):raise AssertionError('disabled native switch clicked')
                current[node.key]=not current[node.key];events.append(('toggle',node.key))
                if node.key=='autocomplete' and not current[node.key]:current['search_required']=False
            else:
                events.append(('save',))
                if not lost:persisted.update(current)
        def reopen(*_):current.update(persisted);events.append(('reopen',))
        children=deepcopy(data['expected_children'])
        if child_drift:children['City']['placeholder']='concurrent mutation'
        with patch.object(native,'_open',return_value=frame), \
             patch.object(native,'_controls',side_effect=observed), \
             patch.object(native,'_children',return_value=children), \
             patch.object(native,'read_editor_title',return_value=data['form_name']), \
             patch.object(native,'assert_tenant'),patch.object(native,'click',side_effect=click), \
             patch.object(native.child,'_close_properties'),patch.object(native.child,'_close_initial'), \
             patch.object(native.child,'_inventory',return_value=data['expected_inventory']), \
             patch.object(native,'reopen_editor',side_effect=reopen), \
             patch('form_conditions._wait_for_form_save'):
            try:result=native.configure(page,plan)
            except runner.Stop as error:result=error
        return current,events,result

    def test_parent_on_precedes_mandatory_and_parent_off_clears_in_one_click(self):
        for before,wanted,expected in [
            ({'autocomplete':False,'search_required':False},{'autocomplete':True,'search_required':True},
             [('toggle','autocomplete'),('toggle','search_required'),('save',),('reopen',)]),
            ({'autocomplete':True,'search_required':True},{'autocomplete':False,'search_required':False},
             [('toggle','autocomplete'),('save',),('reopen',)])]:
            current,events,result=self.exercise(before,wanted)
            self.assertEqual(current,wanted);self.assertEqual(events,expected);self.assertIsInstance(result,dict)

    def test_desired_state_reuses_without_save_and_lost_save_or_child_drift_refuses(self):
        before={'autocomplete':True,'search_required':True}
        _,events,result=self.exercise(before,before)
        self.assertEqual(events,[('reopen',)]);self.assertIsInstance(result,dict)
        wanted={'autocomplete':False,'search_required':False}
        _,events,result=self.exercise(before,wanted,lost=True)
        self.assertIsInstance(result,runner.Stop);self.assertEqual(events.count(('save',)),1)
        _,events,result=self.exercise(before,wanted,child_drift=True)
        self.assertIsInstance(result,runner.Stop);self.assertEqual(events,[])


if __name__=='__main__':unittest.main()
