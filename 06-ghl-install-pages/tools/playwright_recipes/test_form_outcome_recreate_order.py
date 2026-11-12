"""Explicit non-rich outcome permutations compose captured delete/author controls."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import form_condition_outcomes as native
import recipe_cli
import skill6_playwright as runner
from test_form_outcome_removal import OutcomeDrawer, instant_wait
from test_form_condition_outcomes import rule, record


def request():
    previous=[rule('Show Field'),rule(),rule('Hide Field',target='Email')]
    return {'expected_rules':previous,'rules':[previous[0],previous[2],previous[1]],
            'recreate_order':[0,2,1]}


class RecreateTests(unittest.TestCase):
    def exercise(self, *, reused=False, stale=False, lost_save=False, fail_author=False):
        data=request();state=OutcomeDrawer(lost_save=lost_save)
        state.current=[record(item) for item in data['rules' if reused else 'expected_rules']]
        if stale:state.current[1]['rule']['redirect_url']='https://example.com/drift'
        state.persisted=deepcopy(state.current)
        def author(_frame,_dialog,item,current,identity,**_options):
            identity();self.assertEqual(current,state.current)
            state.events.append(('author',item['effect']))
            if fail_author:raise runner.Stop('uncertain staged write')
            state.current.append(record(item));return deepcopy(state.current)
        page=Mock();page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
        with patch.object(native,'form_builder',return_value=state.frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=state.click), \
             patch.object(native.stack,'click',side_effect=state.click), \
             patch.object(native,'_inventory',side_effect=lambda _:deepcopy(state.current)), \
             patch.object(native.stack,'wait_until',side_effect=instant_wait), \
             patch.object(native.group,'_wait_for_form_save'), \
             patch.object(native,'reopen_editor',side_effect=state.reopen), \
             patch.object(native,'_author',side_effect=author),patch.object(native,'_edit') as edit:
            try:result=native.configure(page,data)
            except runner.Stop as error:result=error
        edit.assert_not_called();return state,result,data

    def test_exact_suffix_recreation_preserves_prefix_saves_once_and_reopens(self):
        state,result,data=self.exercise()
        self.assertEqual(state.events,[('open_delete',2),('confirm',),('open_delete',1),('confirm',),
            ('author','Hide Field'),('author',native.REDIRECT),('save',),('reopen',)])
        self.assertEqual(state.persisted,[record(item) for item in data['rules']])
        self.assertTrue(native.validate_receipt(result,data))

    def test_reused_order_performs_no_delete_author_or_outer_save(self):
        state,result,_=self.exercise(reused=True)
        self.assertEqual(state.events,[('reopen',)])
        self.assertEqual(result['status'],'CONDITION_OUTCOMES_REUSED_AND_REOPENED')

    def test_stale_or_partial_stage_does_not_save(self):
        for options in ({'stale':True},{'fail_author':True}):
            state,result,_=self.exercise(**options)
            self.assertIsInstance(result,runner.Stop);self.assertNotIn(('save',),state.events)

    def test_lost_save_refuses_success(self):
        _,result,_=self.exercise(lost_save=True)
        self.assertIsInstance(result,runner.Stop);self.assertIn('did not persist',str(result))

    def test_bad_permutations_or_edits_refuse_before_browser(self):
        invalid=[]
        for order in (True,[0,0,1],[0,True,1],[1,0],[-1,0,1]):
            data=request();data['recreate_order']=order;invalid.append(data)
        data=request();data['rules'][1]=rule(native.MESSAGE);invalid.append(data)
        for data in invalid:
            page=Mock()
            with self.subTest(data=data),self.assertRaises(runner.Stop):native.configure(page,data)
            self.assertFalse(page.mock_calls)

    def test_message_permutation_validates_before_actual_markup_preflight(self):
        previous=[rule(),rule(native.MESSAGE)]
        request={'expected_rules':previous,'rules':list(reversed(previous)),'recreate_order':[1,0]}
        self.assertEqual(native.validate(request)['recreate_order'],[1,0])

    def test_compiler_and_hash_preserve_explicit_permutation(self):
        data=request()
        job=runner.validate_job(recipe_cli.compile_recipe('forms.conditions',{
            'location_id':'LOC','location_name':'Fixture',
            'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM',
            'condition':data}),Path('.'))
        self.assertEqual(job['steps'][0]['action'],'native_condition_outcomes')
        self.assertEqual(job['steps'][0]['recreate_order'],[0,2,1])
        ordinary={key:value for key,value in data.items() if key!='recreate_order'}
        with self.assertRaises(runner.Stop):native.validate(ordinary)
        self.assertEqual(native.configuration_hash(data),native.configuration_hash(job['steps'][0]))


if __name__=='__main__':unittest.main()
