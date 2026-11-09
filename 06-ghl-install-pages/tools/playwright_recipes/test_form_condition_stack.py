"""Full native rule inventories protect plural-target intent and lost Save."""
from copy import deepcopy
import unittest
from unittest.mock import Mock,patch

import form_condition_stack as native
from skill6_playwright import Stop


def rule(target='Phone',**changes):
    value={'match':'all','clauses':[{'if_field':'First Name','operator':'Is Filled'}],
           'effect':'Hide Field','target':target}
    value.update(changes)
    return value


def plan():return {'rules':[rule('Phone'),rule('Email')]}


class StackSchemaTests(unittest.TestCase):
    def test_one_expression_can_target_two_fields_through_two_ordered_native_rules(self):
        data=plan()
        self.assertEqual(native.validate(data),data)
        self.assertEqual([r['outcome'] for r in native._expected(data)],
                         [['Hide Field','Phone'],['Hide Field','Email']])

    def test_single_and_compound_predicates_have_the_same_exact_source_contract(self):
        data=plan()
        data['rules'][1]=rule('Email',match='any',clauses=[
            {'if_field':'Email','operator':'Contains','value':'@'},
            {'if_field':'First Name','operator':'Is Empty'}])
        self.assertEqual(native.validate(data),data)

    def test_conflicting_or_duplicate_predicates_for_one_target_are_refused(self):
        variants=[{'rules':[rule(),rule()]},
                  {'rules':[rule(),rule(match='any',effect='Show Field')]}]
        clauses=[{'if_field':'Email','operator':'Is Filled'},
                 {'if_field':'First Name','operator':'Is Empty'}]
        variants.append({'rules':[rule(clauses=clauses),
            rule(effect='Show Field',clauses=list(reversed(clauses)))]})
        for data in variants:
            with self.subTest(data=data),self.assertRaisesRegex(Stop,'Duplicate or conflicting'):
                native.validate(data)

    def test_malformed_and_unknown_rule_properties_fail_before_page_reads(self):
        invalid=[{'rules':[]},{'rules':[rule(target=['Email','Phone'])]},
                 {'rules':[{'clauses':[]}]},{'rules':[rule(publish=True)]}]
        for data in invalid:
            page=Mock()
            with self.subTest(data=data),self.assertRaises(Stop):native.configure(page,data)
            self.assertFalse(page.mock_calls)

    def test_configuration_hash_binds_rule_order_and_every_target(self):
        original=plan();reordered=plan();reordered['rules'].reverse()
        self.assertNotEqual(native.configuration_hash(original),native.configuration_hash(reordered))
        changed=plan();changed['rules'][1]['target']='Last Name'
        self.assertNotEqual(native.configuration_hash(original),native.configuration_hash(changed))


class SaveReadbackTests(unittest.TestCase):
    def run_handler(self,*,before=None,lose_save=False,concurrent=False):
        plan_=plan();wanted=native._expected(plan_)
        persisted=deepcopy(before if before is not None else [])
        staged=deepcopy(persisted)
        page,frame,title,save,dialog,button,close=[Mock() for _ in range(7)]
        page.url='https://app.example.com/v2/location/L/form-builder-v2/F'
        title.count.return_value=1;title.input_value.return_value='Fixture'
        save.count.return_value=1;save.is_enabled.return_value=True
        dialog.count.return_value=1;close.count.return_value=1
        dialog.locator.return_value=close
        frame.get_by_role.side_effect=lambda role,**kw:(title if role=='textbox'
            else dialog if role=='dialog' else save if kw.get('name')=='Save' else button)
        appended,saves=[],[]
        def inventory(_):return deepcopy(staged)
        def author(_frame,_dialog,rule_,prefix,identity):
            nonlocal staged
            identity();appended.append(rule_['target'])
            staged=[*deepcopy(prefix),native.group._expected(rule_)[0]]
            if concurrent:staged[0]['outcome']=['Show Field','Last Name']
            return deepcopy(staged)
        def click(node):
            nonlocal persisted
            if node is save:
                saves.append(True)
                if not lose_save:persisted=deepcopy(staged)
        def reopen(*_):
            nonlocal staged
            staged=deepcopy(persisted)
        with patch.object(native,'form_builder',return_value=frame), \
             patch.object(native,'_close_initial'),patch.object(native,'click',side_effect=click), \
             patch.object(native.group,'_inventory',side_effect=inventory), \
             patch.object(native,'_author',side_effect=author), \
             patch.object(native,'reopen_editor',side_effect=reopen):
            try:result=native.configure(page,plan_)
            except Stop as error:result=error
        return result,appended,saves,persisted,wanted

    def test_empty_inventory_appends_each_target_once_and_checks_all_saved_cards(self):
        result,appended,saves,persisted,wanted=self.run_handler()
        self.assertEqual(appended,['Phone','Email'])
        self.assertEqual(saves,[True]);self.assertEqual(persisted,wanted)
        self.assertEqual(result['status'],'CONDITION_STACK_SAVED_AND_REOPENED')
        self.assertEqual(result['rule_count'],2)
        self.assertIs(result['behavior_verified'],False)

    def test_exact_prefix_appends_only_missing_target_and_preserves_first_rule(self):
        before=native._expected(plan())[:1]
        result,appended,_,persisted,wanted=self.run_handler(before=before)
        self.assertEqual(appended,['Email']);self.assertEqual(persisted,wanted)
        self.assertEqual(result['independent_readback'],'VERIFIED')

    def test_existing_complete_stack_reopens_without_repeating_any_append_or_outer_save(self):
        before=native._expected(plan())
        result,appended,saves,_,_=self.run_handler(before=before)
        self.assertEqual((appended,saves),([],[]))
        self.assertEqual(result['status'],'CONDITION_STACK_REUSED_AND_REOPENED')

    def test_unrelated_or_reordered_existing_rule_stops_before_any_append(self):
        for before in (list(reversed(native._expected(plan()))),
                       [{'effect':'Hide Field','rows':[['If','Email','Is Empty']],
                         'outcome':['Hide Field','Last Name']}]):
            result,appended,saves,_,_=self.run_handler(before=before)
            self.assertIsInstance(result,Stop)
            self.assertEqual((appended,saves),([],[]))

    def test_staged_new_cards_are_not_promoted_to_persistence_when_save_is_lost(self):
        result,appended,saves,persisted,_=self.run_handler(lose_save=True)
        self.assertIsInstance(result,Stop)
        self.assertIn('did not persist',str(result))
        self.assertEqual(appended,['Phone','Email']);self.assertEqual(saves,[True])
        self.assertEqual(persisted,[])

    def test_concurrent_first_card_drift_does_not_get_saved_as_the_authored_stack(self):
        result,_,saves,_,_=self.run_handler(concurrent=True)
        self.assertIsInstance(result,Stop)
        self.assertEqual(saves,[])


if __name__=='__main__':unittest.main()
