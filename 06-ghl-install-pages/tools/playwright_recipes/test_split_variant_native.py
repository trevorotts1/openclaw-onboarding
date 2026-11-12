"""Bounded integration coverage for captured inactive same-step split variants."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import editor_replay
import recipe_cli
import skill6_playwright as runner
from playwright_recipes import split_variant as native


def inputs():
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/funnels-websites/funnels/FUNNEL/steps/STEP/overview',
        'funnel_id':'FUNNEL','step_id':'STEP','funnel_name':'Approved funnel',
        'page_name':'Approved page','step_url':'https://example.com/approved',
        'control_page_id':'CONTROL','expected_variant_id':None,'allow_creation':True,
        'expected_control_traffic':100,'control_traffic':100,
        'expected_active':False,'active':False,'traffic_change_authorized':False}


def job(data=None):
    return runner.validate_job(recipe_cli.compile_recipe('funnels.split_variant',data or inputs()),Path('.'))


def receipt(step):
    return native._receipt(step,{'control_page_id':'CONTROL','variant_page_id':'VARIANT',
        'control_traffic':100,'active':False},created=step['payload']['expected_variant_id'] is None)


class NativeSplitIntegration(unittest.TestCase):
    def test_compiler_preserves_exact_plan_and_rejects_cross_editor_or_mixed(self):
        compiled=job(); self.assertEqual(compiled['steps'][0]['payload'],inputs())
        self.assertEqual(compiled['steps'][0]['action'],'native_split_variant')
        foreign=deepcopy(compiled);foreign['steps'][0]['payload']['location_name']='Other tenant'
        with self.assertRaises(runner.Stop):runner.validate_job(foreign,Path('.'))
        wrong=inputs();wrong['start_url']=wrong['start_url'].replace('/STEP/','/OTHER/')
        with self.assertRaises(runner.Stop):job(wrong)
        mixed=inputs();mixed['options']={'steps':[]}
        with self.assertRaises(runner.Stop):job(mixed)

    def test_activation_requires_authored_traffic_authorization_and_valid_baseline(self):
        invalid = ({'active':True,'control_traffic':50},
            {'expected_active':True,'active':False,'expected_control_traffic':50},
            {'expected_control_traffic':50}, {'active':True,'control_traffic':100})
        for changes in invalid:
            data=inputs();data.update(changes)
            with self.subTest(changes=changes):
                with self.assertRaises(runner.Stop):
                    recipe_cli.compile_recipe('funnels.split_variant',data)
                compiled=job();compiled['steps'][0]['payload']=data
                with self.assertRaises(runner.Stop):runner.validate_job(compiled,Path('.'))
        data=inputs();data.update(active=True,control_traffic=49,traffic_change_authorized=True)
        self.assertTrue(job(data)['steps'][0]['payload']['active'])

    def test_full_receipt_binding_and_fresh_replay_inventory(self):
        compiled=job();step=compiled['steps'][0];saved=receipt(step)
        self.assertEqual(editor_replay._result(step,saved,compiled),saved)
        for key,value in [('control_page_id','OTHER'),('variant_page_id','CONTROL'),
                ('configuration_sha256','0'*64),('control_traffic',50),('active',True),('created',False)]:
            bad={**saved,key:value}
            with self.subTest(key=key),self.assertRaises(runner.Stop):
                editor_replay._result(step,bad,compiled)
        page=Mock()
        with tempfile.TemporaryDirectory() as directory,patch.object(runner,'assert_tenant'), \
                patch.object(native,'configure',return_value=saved) as configure, \
                patch.object(native,'verify_completed',return_value=saved) as verify:
            runner._run_on_page(page,compiled,directory)
            runner._run_on_page(page,compiled,directory)
            configure.assert_called_once();verify.assert_called_once_with(page,step,saved)

    def test_reuse_receipt_requires_existing_variant_and_no_creation(self):
        data=inputs();data.update(expected_variant_id='VARIANT',allow_creation=False)
        step=job(data)['steps'][0];saved=receipt(step)
        self.assertEqual(saved['status'],'SPLIT_VARIANT_REUSED_AND_REOPENED')
        self.assertEqual(native.validate_receipt(saved,step),saved)
        page=Mock();observed={'variant_present':True,'control_page_id':'CONTROL',
            'variant_page_id':'VARIANT','control_traffic':100,'active':False}
        with patch.object(native,'read_inventory',return_value=observed),patch.object(native,'_create') as create:
            self.assertEqual(native.configure(page,step),saved)
        create.assert_not_called()


if __name__=='__main__':unittest.main()
