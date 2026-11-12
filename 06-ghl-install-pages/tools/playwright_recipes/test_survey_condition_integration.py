"""Survey outcomes bind real intake, compiler, runner completion and native replay."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import recipe_cli
import skill6_playwright as runner
from test_survey_condition_outcomes import step as spec,receipt
native=importlib.import_module('playwright_recipes.survey_condition_outcomes')


def request():
    payload=spec()['payload']
    common={key:payload.pop(key) for key in ('location_id','location_name','start_url')}
    return {**common,'configuration':payload}


def job():return runner.validate_job(recipe_cli.compile_recipe('surveys.configure',request()),Path('.'))


class SurveyOutcomeIntegration(unittest.TestCase):
    def test_exact_parent_owned_job_compiles_without_metadata_override(self):
        compiled=job();self.assertEqual(len(compiled['steps']),1)
        self.assertEqual(compiled['steps'][0]['action'],native.ACTION)
        self.assertEqual(compiled['steps'][0]['payload'],spec()['payload'])
        bad=deepcopy(compiled);bad['steps'][0]['payload']['location_id']='foreign'
        with self.assertRaises(runner.Stop):runner.validate_job(bad,Path('.'))
        for mutation in ('owner','mix','options','metadata'):
            data=request()
            if mutation=='owner':data['configuration']['start_url']=data['start_url']
            elif mutation=='mix':data['configuration']['submission']={'mode':'Message','message':'Hi'}
            elif mutation=='metadata':data['configuration']['outcomes']['action']='native_condition_outcomes'
            else:data['options']={'capture_source':'fixture','steps':[]}
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('surveys.configure',data)

    def test_real_runner_completes_once_and_replay_calls_saved_native_verifier(self):
        compiled=job();step=compiled['steps'][0];done=receipt(step);page=Mock()
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'),\
             patch.object(native,'configure',return_value=done) as write:
            first=runner.run_on_page(page,compiled,root)
            self.assertEqual(first['status'],'NEEDS_VERIFICATION')
            path=Path(root,'state.json');saved=path.read_bytes()
            with patch.object(native,'verify_completed',return_value=done) as verify:
                replay=runner.run_on_page(page,compiled,root)
                self.assertTrue(replay['replayed'])
                verify.assert_called_once_with(page,step,done)
                verify.side_effect=runner.Stop('Saved survey condition drifted')
                with self.assertRaisesRegex(runner.Stop,'drifted'):runner.run_on_page(page,compiled,root)
            write.assert_called_once_with(page,step)
            self.assertEqual(path.read_bytes(),saved)

    def test_invalid_fresh_completion_stays_uncertain_and_never_repeats_write(self):
        compiled=job();done=receipt(compiled['steps'][0]);done['outcomes_sha256']='0'*64
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'),\
             patch.object(native,'configure',return_value=done) as write:
            for _ in range(2):
                with self.assertRaises(runner.Stop):runner.run_on_page(Mock(),compiled,root)
            write.assert_called_once()
            state=json.loads(Path(root,'state.json').read_text())
            self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
            self.assertEqual(state['results'],[])


if __name__=='__main__':unittest.main()
