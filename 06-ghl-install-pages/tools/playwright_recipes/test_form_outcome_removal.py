"""Outcome removal composes the captured shared card-delete lifecycle.

These offline checks establish source behavior, not live outcome acceptance.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import editor_replay
import form_condition_outcomes as native
import recipe_cli
import skill6_playwright as runner
from test_form_condition_card_removal import CardDrawer,instant_wait
from test_form_condition_outcomes import record,rule


def previous():
    return [rule('Show Field'),rule(),rule(native.MESSAGE),rule(native.DISQUALIFY)]


class OutcomeDrawer(CardDrawer):
    """Reuse the captured card confirmation with rich outcome inventories."""
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.current=[record(value,'<p><strong>'+value['message']+'</strong></p>'
            if 'message' in value else None) for value in previous()]
        self.persisted=deepcopy(self.current);self.pending_index=None

    def click(self,node):
        if node is self.delete:
            self.events.append(('confirm',))
            self.current.pop(0 if self.wrong_card else self.pending_index)
            self.confirm_open=False
            return
        index=getattr(node,'index',None)
        if type(index) is int:
            self.events.append(('open_delete',index));self.pending_index=index
            self.confirm_open=True
            if self.drift_at_confirm:self.current[2]['rich_html_sha256']='0'*64
            return
        super().click(node)


class RemovalSchemaTests(unittest.TestCase):
    def test_removal_rejects_edits_reordering_unknown_or_ambiguous_retained_cards_before_browser(self):
        before=previous()
        cases=[{'expected_rules':before,'rules':[before[2],before[0]]},
            {'expected_rules':before,'rules':[rule(redirect_url='https://example.com/changed')]},
            {'expected_rules':[before[2],before[2]],'rules':[before[2]]},
            {'expected_rules':False,'rules':[]},
            {'expected_rules':[{'effect':'unknown'}],'rules':[]},
            {'expected_rules':[rule(native.MESSAGE,publish=True)],'rules':[]},
            {'rules':[]}]
        for value in cases:
            page=Mock()
            with self.subTest(value=value),self.assertRaises(runner.Stop):native.configure(page,value)
            self.assertFalse(page.mock_calls)

    def test_all_outcomes_can_be_removed_or_retained_as_an_unchanged_ordered_subset(self):
        before=previous()
        for wanted in ([],before,[before[0],before[3]],[before[2]]):
            data={'expected_rules':before,'rules':wanted}
            self.assertEqual(native.validate(data),data)

    def test_previous_inventory_is_hash_bound_but_legacy_append_hash_remains_unchanged(self):
        before=previous();data={'expected_rules':before,'rules':[before[2]]}
        changed=deepcopy(data);changed['expected_rules'][1]['redirect_url']='https://example.com/other'
        self.assertNotEqual(native.configuration_hash(data),native.configuration_hash(changed))
        from hashlib import sha256
        import json
        self.assertEqual(native.configuration_hash({'rules':before}),
            sha256(json.dumps(before,sort_keys=True,separators=(',',':')).encode()).hexdigest())


class RemovalLifecycleTests(unittest.TestCase):
    def exercise(self,wanted,*,stale=False,reused=False,**options):
        state=OutcomeDrawer(**options);original=deepcopy(state.current)
        data={'expected_rules':previous(),'rules':wanted}
        if stale:state.current[1]['rule']['redirect_url']='https://example.com/stale'
        if reused:
            state.current=[item for item in state.current if item['rule'] in wanted]
            state.persisted=deepcopy(state.current)
        page=Mock();page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
        with patch.object(native,'form_builder',return_value=state.frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=state.click), \
             patch.object(native.stack,'click',side_effect=state.click), \
             patch.object(native,'_inventory',side_effect=lambda _:deepcopy(state.current)), \
             patch.object(native.stack,'wait_until',side_effect=instant_wait), \
             patch.object(native.group,'_wait_for_form_save'), \
             patch.object(native,'reopen_editor',side_effect=state.reopen), \
             patch.object(native,'_author') as append:
            try:result=native.configure(page,data)
            except runner.Stop as error:result=error
        append.assert_not_called()
        return state,result,data,original

    def test_removes_middle_redirect_and_message_preserving_retained_order_and_rich_markup(self):
        before=previous();state,result,data,original=self.exercise([before[0],before[3]])
        self.assertEqual(state.events,[('open_delete',2),('confirm',),('open_delete',1),
            ('confirm',),('save',),('reopen',)])
        self.assertEqual(state.persisted,[original[0],original[3]])
        self.assertEqual(result['status'],'CONDITION_OUTCOMES_SAVED_AND_REOPENED')
        self.assertTrue(native.validate_receipt(result,data))
        self.assertFalse(result['behavior_verified']);self.assertFalse(result['disqualification_executed'])

    def test_deletes_each_outcome_type_through_the_same_scoped_confirmation(self):
        before=previous()
        for index in range(1,len(before)):
            state,result,_,original=self.exercise(before[:index]+before[index+1:])
            self.assertEqual(state.persisted,original[:index]+original[index+1:])
            self.assertEqual([event for event in state.events if event[0]=='open_delete'],[('open_delete',index)])
            self.assertEqual(result['rule_count'],3)

    def test_clear_all_and_already_removed_reuse_require_positive_loaded_empty(self):
        state,result,_,_=self.exercise([])
        self.assertEqual(state.persisted,[]);self.assertEqual(result['rule_count'],0)
        self.assertEqual(state.events.count(('confirm',)),4)
        state,result,_,_=self.exercise([],reused=True)
        self.assertEqual(result['status'],'CONDITION_OUTCOMES_REUSED_AND_REOPENED')
        self.assertEqual(state.events,[('reopen',)])

    def test_stale_complete_inventory_and_confirmation_drift_stop_before_confirmed_removal(self):
        for options in ({'stale':True},{'drift_at_confirm':True}):
            state,result,_,_=self.exercise([previous()[2]],**options)
            self.assertIsInstance(result,runner.Stop)
            self.assertNotIn(('confirm',),state.events);self.assertNotIn(('save',),state.events)

    def test_wrong_deleted_card_and_missing_empty_state_fail_before_outer_save(self):
        for wanted,options in (([previous()[0]],{'wrong_card':True}),([],{'missing_empty':True})):
            state,result,_,_=self.exercise(wanted,**options)
            self.assertIsInstance(result,runner.Stop);self.assertNotIn(('save',),state.events)

    def test_unrecognized_delete_confirmation_never_confirms(self):
        state,result,_,_=self.exercise([previous()[2]],bad_description=True)
        self.assertIsInstance(result,runner.Stop);self.assertNotIn(('confirm',),state.events)

    def test_lost_save_never_returns_a_successful_removal_receipt(self):
        state,result,_,original=self.exercise([],lost_save=True)
        self.assertIsInstance(result,runner.Stop);self.assertIn('did not persist',str(result))
        self.assertEqual(state.persisted,original);self.assertEqual(state.events.count(('save',)),1)


class CompilerReplayTests(unittest.TestCase):
    def test_clear_outcomes_routes_by_previous_inventory_and_replays_without_second_delete(self):
        data={'location_id':'LOC','location_name':'Fixture',
            'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM',
            'condition':{'expected_rules':previous(),'rules':[]}}
        job=runner.validate_job(recipe_cli.compile_recipe('forms.conditions',data),Path('.'))
        step=job['steps'][0];self.assertEqual(step['action'],'native_condition_outcomes')
        from playwright_recipes import form_condition_outcomes as leaf
        receipt={'status':'CONDITION_OUTCOMES_SAVED_AND_REOPENED','kind':'form_condition_outcomes',
            'editor_url':data['start_url'],'rule_count':0,'configuration_sha256':leaf.configuration_hash(step),
            'independent_readback':'VERIFIED','behavior_verified':False,
            'submission_verified':False,'disqualification_executed':False}
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
             patch.object(leaf,'configure',return_value=receipt) as writer:
            first=runner.run_on_page(object(),job,root);replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION');self.assertTrue(replay['replayed'])
        writer.assert_called_once()
        changed=deepcopy(step);changed['expected_rules'][1]['redirect_url']='https://example.com/changed'
        with self.assertRaises(runner.Stop):editor_replay._result(changed,receipt,job)


if __name__=='__main__':unittest.main()
