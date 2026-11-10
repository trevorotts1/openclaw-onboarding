"""Explicit Show/Hide permutations reuse captured Delete and author controls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import form_condition_stack as native
import recipe_cli
import skill6_playwright as runner
from test_form_condition_stack import rule
from test_form_condition_card_removal import CardDrawer, instant_wait


def request(order=(1, 0), targets=('Phone', 'Email')):
    previous=[rule(target) for target in targets]
    return {'expected_rules':previous, 'rules':deepcopy([previous[index] for index in order]),
            'recreate_order':list(order)}


class ExplicitOrderTests(unittest.TestCase):
    def test_bad_permutations_and_rule_edits_refuse_before_page_access(self):
        original=request()
        variants=[]
        for value in (True, '1,0', [0], [0,0], [True,0], [-1,0], [2,0]):
            data=deepcopy(original);data['recreate_order']=value;variants.append(data)
        missing=deepcopy(original);missing.pop('expected_rules');variants.append(missing)
        edited=deepcopy(original);edited['rules'][0]['effect']='Show Field';variants.append(edited)
        rich=deepcopy(original);rich['rules'][0]={'effect':'Display custom message','message':'Hello'};variants.append(rich)
        for data in variants:
            page=Mock()
            with self.subTest(data=data),self.assertRaises(runner.Stop):native.configure(page,data)
            self.assertFalse(page.mock_calls)

    def test_explicit_recreation_binding_is_distinct_from_ordinary_edits(self):
        data=request();ordinary={key:value for key,value in data.items() if key!='recreate_order'}
        self.assertNotEqual(native.configuration_hash(data),native.configuration_hash(ordinary))
        self.assertEqual(native.validate(data),data)

    def exercise(self, data, *, stale=False, lost_save=False, fail_author=False, already=False):
        state=CardDrawer(lost_save=lost_save)
        before=native._expected({'rules':data['expected_rules']})
        state.current=deepcopy(native._expected(data) if already else before)
        if stale:state.current[0]['outcome']=['Show Field','Last Name']
        state.persisted=deepcopy(state.current)
        def author(_frame,_dialog,item,current,identity):
            identity();self.assertEqual(current,state.current)
            state.events.append(('author',item['target']))
            if fail_author:raise runner.Stop('simulated uncertain staged authoring')
            state.current.append(native.group._expected(item)[0])
            return deepcopy(state.current)
        page=Mock();page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
        with patch.object(native,'form_builder',return_value=state.frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=state.click), \
             patch.object(native.group,'_inventory',side_effect=lambda _:deepcopy(state.current)), \
             patch.object(native,'wait_until',side_effect=instant_wait),patch.object(native.group,'_wait_for_form_save'), \
             patch.object(native,'reopen_editor',side_effect=state.reopen), \
             patch.object(native,'_author',side_effect=author),patch.object(native,'_edit') as edit:
            try:result=native.configure(page,data)
            except runner.Stop as error:result=error
        edit.assert_not_called()
        return state,result

    def test_reorders_exact_full_stack_saves_once_and_reopens(self):
        data=request();state,result=self.exercise(data)
        self.assertEqual(state.events,[('open_delete',1),('confirm',),('open_delete',0),('confirm',),
            ('author','Email'),('author','Phone'),('save',),('reopen',)])
        self.assertEqual(state.persisted,native._expected(data))
        self.assertEqual(result['configuration_sha256'],native.configuration_hash(data))
        self.assertEqual(result['status'],'CONDITION_STACK_SAVED_AND_REOPENED')
        self.assertFalse(result['behavior_verified']);self.assertFalse(result['submission_verified'])

    def test_unchanged_prefix_is_never_deleted_or_reauthored(self):
        data=request((0,2,1),('Phone','Email','Last Name'));state,result=self.exercise(data)
        self.assertEqual(state.events,[('open_delete',2),('confirm',),('open_delete',1),('confirm',),
            ('author','Last Name'),('author','Email'),('save',),('reopen',)])
        self.assertEqual(state.persisted,native._expected(data));self.assertIsInstance(result,dict)

    def test_already_reordered_stack_is_reused_without_deleting_or_saving(self):
        state,result=self.exercise(request(),already=True)
        self.assertEqual(state.events,[('reopen',)])
        self.assertEqual(result['status'],'CONDITION_STACK_REUSED_AND_REOPENED')

    def test_concurrent_card_drift_stops_before_first_delete(self):
        state,result=self.exercise(request(),stale=True)
        self.assertIsInstance(result,runner.Stop);self.assertEqual(state.events,[])

    def test_partial_stage_failure_never_saves_the_truncated_stack(self):
        state,result=self.exercise(request(),fail_author=True)
        self.assertIsInstance(result,runner.Stop)
        self.assertFalse(any(event[0]=='save' for event in state.events))
        self.assertEqual(len(state.persisted),2)

    def test_lost_outer_save_is_not_success(self):
        state,result=self.exercise(request(),lost_save=True)
        self.assertIsInstance(result,runner.Stop);self.assertIn('did not persist',str(result))
        self.assertEqual(state.persisted,native._expected({'rules':request()['expected_rules']}))

    def test_compiler_and_uncertain_journal_preserve_explicit_order_without_retry(self):
        inputs={'location_id':'LOC','location_name':'Fixture',
            'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM',
            'condition':request()}
        job=runner.validate_job(recipe_cli.compile_recipe('forms.conditions',inputs),Path('.'))
        self.assertEqual(job['steps'][0]['recreate_order'],[1,0])
        from playwright_recipes import form_condition_stack as leaf
        with tempfile.TemporaryDirectory() as directory,patch.object(runner,'assert_tenant'), \
             patch.object(leaf,'configure',side_effect=runner.Stop('partial staged write')) as writer:
            with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,directory)
            state=json.loads((Path(directory)/'state.json').read_text())
            self.assertEqual(state['status'],'NEEDS_BROWSER_RECOVERY')
            self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
            with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,directory)
            self.assertEqual(writer.call_count,1)


if __name__=='__main__':unittest.main()
