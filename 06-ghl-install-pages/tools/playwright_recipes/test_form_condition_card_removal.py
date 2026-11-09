"""Captured card Delete confirmation protects complete inventories and clear-all."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import form_condition_stack as native
import editor_replay
import recipe_cli
import skill6_playwright as runner
from test_form_condition_stack import rule


class CardDrawer:
    """Measured two-dialog Delete lifecycle, with independent saved inventory."""
    def __init__(self,*,missing_empty=False,wrong_card=False,drift_at_confirm=False,lost_save=False,bad_description=False):
        self.current=native._expected({'rules':[rule('Phone'),rule('Email')]})
        self.persisted=deepcopy(self.current);self.events=[];self.open=True;self.confirm_open=False
        self.missing_empty=missing_empty;self.wrong_card=wrong_card;self.drift_at_confirm=drift_at_confirm
        self.lost_save=lost_save;self.bad_description=bad_description
        self.frame,self.dialogs,self.drawer,self.confirm,self.heading,self.close,self.cancel,self.delete,self.header_close,self.image,self.title,self.outer_save,self.open_button,self.tab=[Mock() for _ in range(14)]
        self.title.count.return_value=1;self.title.input_value.return_value='Fixture'
        self.outer_save.count.return_value=1;self.outer_save.is_enabled.return_value=True
        self.close.count.return_value=self.cancel.count.return_value=self.delete.count.return_value=self.header_close.count.return_value=1
        self.delete.inner_text.return_value='Delete';self.cancel.inner_text.return_value='Cancel'
        self.delete.is_enabled.return_value=True
        self.image.count.side_effect=lambda:int(not self.missing_empty and not self.current)
        self.image.get_attribute.return_value='/assets/no-conditions-13c5d8b2.png'
        self.drawer.count.side_effect=lambda:int(self.open)
        self.confirm.count.side_effect=lambda:int(self.confirm_open)
        self.heading.count.side_effect=lambda:int(self.confirm_open)
        self.dialogs.count.side_effect=lambda:int(self.open)+int(self.confirm_open)
        self.dialogs.filter.side_effect=lambda **kwargs:self.confirm if kwargs['has'] is self.heading else self.drawer
        self.frame.locator.side_effect=lambda selector:self.close if selector=='#conditional-logic-save-close' else self.fail(selector)
        self.frame.get_by_role.side_effect=self.role
        for node in (self.drawer,self.dialogs):
            node.locator.side_effect=self.locator
            node.get_by_text.side_effect=self.empty_text
            node.get_by_role.side_effect=lambda role,**kwargs:self.image if role=='img' and kwargs.get('name')=='No conditions yet' else self.fail(role)
        self.confirm.locator.side_effect={'#modal-footer-btn-negative-action':self.cancel,
            '#modal-footer-btn-positive-action':self.delete,'#modal-header-modal-close-btn':self.header_close}.__getitem__
        self.confirm.get_by_text.side_effect=lambda text,**kwargs:Mock(count=lambda:int(text=='Are you sure you want to delete this condition?' and not self.bad_description))

    def fail(self,message):raise AssertionError(message)

    def role(self,role,**kwargs):
        if role=='dialog':return self.dialogs
        if role=='heading' and kwargs.get('name')=='Delete Condition':return self.heading
        if role=='textbox':return self.title
        if role=='button' and kwargs.get('name')=='Save':return self.outer_save
        if role=='button' and kwargs.get('name')=='Open Conditional Logic':return self.open_button
        return self.tab

    def empty_text(self,text,**kwargs):
        markers=('No existing conditions yet',"You're free to roam without the rules - at least for now")
        return Mock(count=lambda:int(not self.current and not self.missing_empty and text in markers))

    def locator(self,selector):
        if selector=='#conditional-logic-save-close':return self.close
        if selector==native.group.CARD:
            cards=Mock();cards.count.side_effect=lambda:len(self.current)
            def card(index):
                node,remove=Mock(),Mock();remove.count.return_value=1;remove.index=index
                node.locator.side_effect=lambda selector:remove if selector=='#delete-condition' else self.fail(selector)
                return node
            cards.nth.side_effect=card;return cards
        self.fail(selector)

    def click(self,node):
        if node is self.open_button:self.open=True;return
        if node is self.tab:return
        if node is self.close:self.open=False;return
        if node is self.outer_save:
            self.events.append(('save',))
            if not self.lost_save:self.persisted=deepcopy(self.current)
            return
        if node is self.delete:
            self.events.append(('confirm',));self.current.pop(0 if self.wrong_card else -1);self.confirm_open=False;return
        index=getattr(node,'index',None)
        if type(index) is int:
            self.events.append(('open_delete',index));self.confirm_open=True
            if self.drift_at_confirm:self.current[0]['outcome']=['Show Field','Last Name']
            return
        self.fail('Unexpected Delete lifecycle click')

    def reopen(self,*_):
        self.events.append(('reopen',));self.current=deepcopy(self.persisted);self.open=False


def instant_wait(fn,message):
    if not fn():raise runner.Stop(message)


class CardDeleteTests(unittest.TestCase):
    def run_delete(self,state,before):
        with patch.object(native,'click',side_effect=state.click), \
             patch.object(native.group,'_inventory',side_effect=lambda _:deepcopy(state.current)), \
             patch.object(native,'wait_until',side_effect=instant_wait):
            return native._delete_tail(state.frame,state.drawer,before,lambda:None)

    def test_scoped_tail_delete_uses_second_confirmation_and_preserves_exact_prefix(self):
        state=CardDrawer();before=deepcopy(state.current)
        self.assertEqual(self.run_delete(state,before),before[:-1])
        self.assertEqual(state.events,[('open_delete',1),('confirm',)])
        self.assertEqual(state.current,before[:-1])

    def test_clear_last_card_requires_actual_positive_loaded_empty_content(self):
        for missing in (False,True):
            state=CardDrawer(missing_empty=missing);state.current=state.current[:1]
            before=deepcopy(state.current)
            if missing:
                with self.assertRaisesRegex(runner.Stop,'positive loaded-empty'):self.run_delete(state,before)
            else:self.assertEqual(self.run_delete(state,before),[])
            self.assertEqual(state.events,[('open_delete',0),('confirm',)])

    def test_delete_confirmation_rechecks_every_card_before_the_first_destructive_click(self):
        state=CardDrawer(drift_at_confirm=True);before=deepcopy(state.current)
        with self.assertRaisesRegex(runner.Stop,'before Delete confirmation'):self.run_delete(state,before)
        self.assertEqual(state.events,[('open_delete',1)])

    def test_wrong_removed_card_fails_even_when_count_drops_by_exactly_one(self):
        state=CardDrawer(wrong_card=True);before=deepcopy(state.current)
        with self.assertRaisesRegex(runner.Stop,'wrong card'):self.run_delete(state,before)
        self.assertEqual(state.events,[('open_delete',1),('confirm',)])

    def test_unrecognized_confirmation_text_or_labels_never_click_delete(self):
        for bad_description,bad_label in ((True,False),(False,True)):
            state=CardDrawer(bad_description=bad_description);before=deepcopy(state.current)
            if bad_label:state.delete.inner_text.return_value='Delete everything'
            with self.assertRaises(runner.Stop):self.run_delete(state,before)
            self.assertEqual(state.events,[('open_delete',1)])

    def test_stale_before_inventory_never_opens_delete_confirmation(self):
        state=CardDrawer();before=deepcopy(state.current);before[0]['outcome']=['Hide Field','Last Name']
        with self.assertRaisesRegex(runner.Stop,'before the requested'):self.run_delete(state,before)
        self.assertEqual(state.events,[])


class CardContractionLifecycleTests(unittest.TestCase):
    def exercise(self,desired,**options):
        state=CardDrawer(**options)
        data={'expected_rules':[rule('Phone'),rule('Email')],'rules':desired}
        page=Mock();page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
        with patch.object(native,'form_builder',return_value=state.frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=state.click),patch.object(native.group,'_inventory',side_effect=lambda _:deepcopy(state.current)), \
             patch.object(native,'wait_until',side_effect=instant_wait),patch.object(native.group,'_wait_for_form_save'), \
             patch.object(native,'reopen_editor',side_effect=state.reopen),patch.object(native,'_edit') as edit, \
             patch.object(native,'_author') as append:
            try:result=native.configure(page,data)
            except runner.Stop as error:result=error
        edit.assert_not_called();append.assert_not_called()
        return state,result,data

    def test_contracts_multiple_cards_and_saves_only_once_before_independent_reopen(self):
        state,result,data=self.exercise([rule('Phone')])
        self.assertEqual(state.events,[('open_delete',1),('confirm',),('save',),('reopen',)])
        self.assertEqual(state.persisted,native._expected(data));self.assertEqual(result['rule_count'],1)
        self.assertEqual(result['status'],'CONDITION_STACK_SAVED_AND_REOPENED')

    def test_clear_all_confirms_each_tail_and_requires_positive_empty_after_reopen(self):
        state,result,data=self.exercise([])
        self.assertEqual(state.events,[('open_delete',1),('confirm',),('open_delete',0),('confirm',),('save',),('reopen',)])
        self.assertEqual(state.persisted,[]);self.assertEqual(result['rule_count'],0)
        self.assertEqual(result['configuration_sha256'],native.configuration_hash(data))
        self.assertFalse(result['behavior_verified']);self.assertFalse(result['submission_verified'])

    def test_lost_save_does_not_promote_unsaved_card_removal_to_persistence(self):
        state,result,_=self.exercise([],lost_save=True)
        self.assertIsInstance(result,runner.Stop);self.assertIn('did not persist',str(result))
        self.assertEqual(len(state.persisted),2)

    def test_missing_empty_state_stops_before_outer_save(self):
        state,result,_=self.exercise([],missing_empty=True)
        self.assertIsInstance(result,runner.Stop);self.assertFalse(any(event[0]=='save' for event in state.events))


class ClearCompilerReplayTests(unittest.TestCase):
    def job(self):
        data={'location_id':'LOC','location_name':'Fixture',
            'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM',
            'condition':{'expected_rules':[rule('Phone'),rule('Email')],'rules':[]}}
        return runner.validate_job(recipe_cli.compile_recipe('forms.conditions',data),Path('.'))

    def test_empty_desired_stack_compiles_only_with_explicit_complete_expected_inventory(self):
        job=self.job();self.assertEqual(job['steps'][0]['rules'],[])
        self.assertEqual(len(job['steps'][0]['expected_rules']),2)
        page=Mock()
        with self.assertRaises(runner.Stop):native.configure(page,{'rules':[]})
        self.assertFalse(page.mock_calls)

    def test_clear_all_receipt_binds_zero_count_and_replays_without_deleting_again(self):
        from playwright_recipes import form_condition_stack as leaf
        job=self.job();step=job['steps'][0]
        receipt={'status':'CONDITION_STACK_SAVED_AND_REOPENED','kind':'form_condition_stack',
            'editor_url':job['start_url'],'rule_count':0,'configuration_sha256':leaf.configuration_hash(step),
            'independent_readback':'VERIFIED','submission_verified':False,'behavior_verified':False}
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
             patch.object(leaf,'configure',return_value=receipt) as writer:
            first=runner.run_on_page(object(),job,root);replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION');self.assertTrue(replay['replayed'])
        writer.assert_called_once()
        changed=deepcopy(step);changed['expected_rules'][0]['target']='Last Name'
        with self.assertRaises(runner.Stop):editor_replay._result(changed,receipt,job)


if __name__=='__main__':unittest.main()
