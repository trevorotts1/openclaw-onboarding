"""Full expected stacks bind same-count native card edits and saved readback."""
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import Mock,patch

import form_condition_stack as native
from test_form_condition_stack import plan,rule
from skill6_playwright import Stop


def edit_plan():
    before=plan()['rules']
    desired=deepcopy(before)
    desired[0]=rule('Phone',effect='Show Field',clauses=[{'if_field':'Email','operator':'Contains','value':'@'}])
    return {'expected_rules':before,'rules':desired}


class EditSchemaTests(unittest.TestCase):
    def test_malformed_expected_inventory_refuses_before_browser(self):
        mismatch=edit_plan();mismatch['expected_rules']={'unknown':'inventory'}
        for data in (mismatch,):
            page=Mock()
            with self.subTest(data=data),self.assertRaises(Stop):native.configure(page,data)
            self.assertFalse(page.mock_calls)

    def test_captured_tail_clause_removal_is_now_an_explicit_supported_edit(self):
        shrinking=edit_plan();shrinking['expected_rules'][0]['clauses'].append(
            {'if_field':'Email','operator':'Is Empty'})
        self.assertEqual(native.validate(shrinking),shrinking)

    def test_hash_binds_previous_stack_and_retains_legacy_append_hash(self):
        data=edit_plan();changed=deepcopy(data);changed['expected_rules'][0]['effect']='Show Field'
        self.assertNotEqual(native.configuration_hash(data),native.configuration_hash(changed))
        legacy=plan()
        expected=hashlib.sha256(json.dumps(legacy['rules'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(native.configuration_hash(legacy),expected)

    def test_conflicting_previous_rules_can_be_corrected_without_fabricating_a_clean_before_state(self):
        data=edit_plan();data['expected_rules']=[rule('Phone'),rule('Phone',effect='Show Field')]
        self.assertEqual(native.validate(data),data)


class EditPipelineTests(unittest.TestCase):
    def exercise(self,*,stale=False,lost=False):
        data=edit_plan();before=native._expected({'rules':data['expected_rules']})
        saved=deepcopy(before);staged=deepcopy(before)
        if stale:staged[1]['outcome']=['Hide Field','Last Name']
        page,frame,title,save,dialog,button,close=[Mock() for _ in range(7)]
        page.url='https://app.example.com/v2/location/L/form-builder-v2/F'
        title.count.return_value=1;title.input_value.return_value='Fixture'
        save.count.return_value=1;save.is_enabled.return_value=True
        dialog.count.return_value=1;close.count.return_value=1;dialog.locator.return_value=close
        frame.get_by_role.side_effect=lambda role,**kw:title if role=='textbox' else dialog if role=='dialog' else save if kw.get('name')=='Save' else button
        edited,saves=[],[]
        def edit(_frame,_dialog,index,previous,desired,current,identity):
            nonlocal staged
            identity();self.assertEqual(current,staged)
            self.assertEqual(previous,data['expected_rules'][index])
            edited.append(index);staged[index]=native.group._expected(desired)[0]
            return deepcopy(staged)
        def click(node):
            nonlocal saved
            if node is save:
                saves.append(True)
                if not lost:saved=deepcopy(staged)
        def reopen(*_):
            nonlocal staged
            staged=deepcopy(saved)
        with patch.object(native,'form_builder',return_value=frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=click), \
             patch.object(native.group,'_inventory',side_effect=lambda _:deepcopy(staged)), \
             patch.object(native,'_edit',side_effect=edit),patch.object(native,'_author') as append, \
             patch.object(native,'reopen_editor',side_effect=reopen):
            try:result=native.configure(page,data)
            except Stop as error:result=error
        return result,edited,saves,saved,before,data,append

    def test_edits_only_changed_card_without_appending_or_changing_untouched_sibling(self):
        result,edited,saves,saved,before,data,append=self.exercise()
        self.assertEqual(edited,[0]);self.assertEqual(saves,[True]);append.assert_not_called()
        self.assertEqual(saved[1],before[1]);self.assertEqual(saved,native._expected(data))
        self.assertEqual(result['status'],'CONDITION_STACK_SAVED_AND_REOPENED')
        self.assertEqual(result['rule_count'],2)
        self.assertEqual(result['configuration_sha256'],native.configuration_hash(data))

    def test_stale_sibling_prevents_first_card_edit_and_outer_save(self):
        result,edited,saves,_,_,_,append=self.exercise(stale=True)
        self.assertIsInstance(result,Stop);self.assertIn('complete expected previous',str(result))
        self.assertEqual((edited,saves),([],[]));append.assert_not_called()

    def test_staged_edit_with_lost_outer_save_fails_independent_readback(self):
        result,edited,saves,saved,before,_,_=self.exercise(lost=True)
        self.assertIsInstance(result,Stop);self.assertIn('did not persist',str(result))
        self.assertEqual(edited,[0]);self.assertEqual(saves,[True]);self.assertEqual(saved,before)


class ModalBeforeGuardTests(unittest.TestCase):
    def test_actual_edit_modal_mismatch_stops_before_first_predicate_write(self):
        data=edit_plan();current=native._expected({'rules':data['expected_rules']})
        frame,dialog,cards,card,edit,modal=[Mock() for _ in range(6)]
        dialog.locator.return_value=cards;cards.count.return_value=2;cards.nth.return_value=card
        card.locator.return_value=edit;edit.count.return_value=1
        frame.get_by_role.return_value=modal;modal.count.return_value=1
        with patch.object(native,'click') as click,patch.object(native.group,'_inventory',return_value=current), \
             patch.object(native.group,'_modal_state',side_effect=Stop('stale native modal')), \
             patch.object(native.group,'_choose') as choose,patch.object(native,'fill') as fill, \
             self.assertRaisesRegex(Stop,'stale native modal'):
            native._edit(frame,dialog,0,data['expected_rules'][0],data['rules'][0],current,lambda:None)
        choose.assert_not_called();fill.assert_not_called()
        self.assertEqual(click.call_count,1) # Opening the existing card is read-only.


if __name__=='__main__':unittest.main()
