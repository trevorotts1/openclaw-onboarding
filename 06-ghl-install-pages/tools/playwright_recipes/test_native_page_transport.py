"""A measured fallback transport may run the same native leaf and journal.

These are interface tests using a compatible caller-owned Page double. They do
not claim that a live extension session exposes the required Page interface.
"""
import importlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

import host
import recipe_cli
import skill6_playwright as runner
from test_native_provider_boundaries import native_receipt
from test_fourth_control_integration import request


class Iframe:
    def __init__(self,count):self.n=count
    def count(self):return self.n
    def wait_for(self,*,state,timeout):
        if state!='visible' or self.n!=1:raise AssertionError('Wrong native editor frame')


class OwnedPage:
    def __init__(self,url):self.url=url;self.lookups=[]
    def locator(self,selector):
        self.lookups.append(selector)
        if selector not in ('iframe[name="form-builder-app"]','iframe[name="survey-builder-app"]',
                            'iframe[name="quiz-builder-app"]','iframe[name="funnel-builder"]'):
            raise AssertionError('Unexpected transport selector '+selector)
        return Iframe(int(selector=='iframe[name="form-builder-app"]'))


def observed(lane,data):
    return {'lanes':{'playwright':{'available':False},lane:{'available':True,
        'current':lane=='openclaw_extension','enabled':lane=='computer_use'}},
        'api_capabilities':{'forms.configure':{'location_id':data['location_id'],
            'observed_at':time.time(),'supported':True,'provider':'public_api',
            'scope_ok':True,'version':'v3'}}}


class NativePageTransport(unittest.TestCase):
    def test_measured_transport_uses_exact_page_native_leaf_intent_and_strict_aged_replay(self):
        for lane in ('openclaw_extension','agent_browser','computer_use'):
            operation,data,module=request('dropdown')
            job=runner.validate_job(recipe_cli.compile_recipe(operation,data),Path('.'))
            leaf=importlib.import_module('playwright_recipes.'+module)
            page=OwnedPage(data['start_url']);api=Mock();generic=Mock()
            with self.subTest(lane=lane),tempfile.TemporaryDirectory() as root:
                path=Path(root,'state.json')
                def write(actual_page,step):
                    self.assertIs(actual_page,page)
                    self.assertEqual(step,job['steps'][0])
                    state=json.loads(path.read_text())
                    self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
                    self.assertEqual(state['current_step'],step['id'])
                    self.assertEqual(state['results'],[])
                    return native_receipt('dropdown',job,module)
                with patch.object(leaf,'configure',side_effect=write) as writer, \
                     patch.object(leaf,'verify_completed',side_effect=lambda page,step,result:leaf.validate_receipt(result,step)) as verify:
                    first=host.run_recipe(operation,data,observed(lane,data),root,input_dir='.',
                        page=page,executors={'public_api':api,lane:generic})
                    self.assertEqual(first['status'],'NEEDS_VERIFICATION',first)
                    self.assertEqual(first['route']['lane'],lane)
                    before=path.read_bytes()
                    aged=data['field_dependencies']['observed_at']+7200
                    with patch('time.time',return_value=aged):
                        second=host.run_recipe(operation,data,observed(lane,data),root,input_dir='.',
                            page=page,executors={'public_api':api,lane:generic})
                    self.assertEqual(second['status'],'NEEDS_VERIFICATION',second)
                    self.assertTrue(second['result']['replayed'])
                    self.assertEqual(path.read_bytes(),before)
                    writer.assert_called_once()
                    verify.assert_called_once_with(page,job['steps'][0],native_receipt('dropdown',job,module))
                self.assertGreater(len(page.lookups),3)
                self.assertFalse(Path(root,'provider-state.json').exists())
                # A changed live owner must refuse replay rather than write again.
                with patch.object(leaf,'configure') as writer, \
                     patch.object(leaf,'verify_completed',side_effect=runner.Stop('owner drift')) as verify:
                    drift=host.run_recipe(operation,data,observed(lane,data),root,input_dir='.',
                        page=page,executors={'public_api':api,lane:generic})
                self.assertEqual(drift['status'],'NEEDS_BROWSER_RECOVERY',drift)
                verify.assert_called_once();writer.assert_not_called()
                self.assertEqual(path.read_bytes(),before)
                # A completed native journal cannot authorize a different field.
                state=json.loads(path.read_text());state['results'][0]['result']['fields'][0]['id']='OTHER_API_ID'
                path.write_text(json.dumps(state))
                with patch.object(leaf,'configure') as writer:
                    rejected=host.run_recipe(operation,data,observed(lane,data),root,input_dir='.',
                        page=page,executors={'public_api':api,lane:generic})
                self.assertEqual(rejected['status'],'NEEDS_BROWSER_RECOVERY',rejected)
                writer.assert_not_called();api.assert_not_called();generic.assert_not_called()

    def test_compatible_page_does_not_promote_status_only_leaf_or_retry_uncertain_write(self):
        operation,data,module=request('dropdown');leaf=importlib.import_module('playwright_recipes.'+module)
        page=OwnedPage(data['start_url']);generic=Mock()
        with tempfile.TemporaryDirectory() as root,patch.object(leaf,'configure',
                return_value={'status':'DROPDOWN_FIELDS_SAVED_AND_REOPENED'}) as writer:
            for _ in range(2):
                result=host.run_recipe(operation,data,observed('openclaw_extension',data),root,
                    input_dir='.',page=page,executors={'openclaw_extension':generic})
                self.assertEqual(result['status'],'NEEDS_BROWSER_RECOVERY',result)
            writer.assert_called_once();generic.assert_not_called()
            state=json.loads(Path(root,'state.json').read_text())
            self.assertEqual(state['status'],'NEEDS_BROWSER_RECOVERY')
            self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
            self.assertEqual(state['results'],[])


if __name__=='__main__':unittest.main()
