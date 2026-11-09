"""Compound native rules bind every clause, connector and outcome."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

import form_conditions as native
from skill6_playwright import Stop


def plan(**changes):
    result = {'action':'native_condition_group','match':'all',
              'effect':'Hide Field','target':'Last Name',
              'clauses':[{'if_field':'Email','operator':'Contains','value':'@'},
                         {'if_field':'First Name','operator':'Is Filled'}]}
    result.update(changes)
    return result


class GroupSchemaTests(unittest.TestCase):
    def test_mixed_binary_and_unary_clauses_preserve_the_full_authored_rule(self):
        source = plan(match='any')
        self.assertEqual(native.validate(source),source)
        self.assertEqual(native._expected_rows(source),
                         [['If','Email','Contains','@'],['Or','First Name','Is Filled']])
        cloned = native.validate(source)
        cloned['clauses'][0]['value']='changed'
        self.assertEqual(source['clauses'][0]['value'],'@')

    def test_configuration_hash_binds_values_connectors_order_effect_and_target(self):
        base = plan()
        changes = [plan(match='any'),plan(effect='Show Field'),plan(target='Phone')]
        value = plan();value['clauses'][0]['value']='example.com';changes.append(value)
        reordered = plan();reordered['clauses'].reverse();changes.append(reordered)
        self.assertEqual(len({native.configuration_hash(x) for x in [base,*changes]}),6)
        with_id = plan();with_id['id']='runtime-step-id'
        self.assertEqual(native.configuration_hash(with_id),native.configuration_hash(base))

    def test_invalid_groups_are_refused_before_any_browser_access(self):
        invalid = [plan(clauses=[]),plan(clauses=[{'if_field':'Email','operator':'Is Filled'}]),
                   plan(match='nested'),plan(target=['Email','Phone']),plan(effect='Redirect'),
                   plan(clauses=[{'if_field':'Unknown','operator':'Is Filled'},
                                 {'if_field':'Email','operator':'Is Empty'}])]
        for value in ('',None,False,'  @','@\n'):
            item=plan();item['clauses'][0]['value']=value;invalid.append(item)
        ignored=plan();ignored['clauses'][1]['value']='ignored';invalid.append(ignored)
        duplicated=plan();duplicated['clauses'][1]=deepcopy(duplicated['clauses'][0]);invalid.append(duplicated)
        for item in invalid:
            page=Mock()
            with self.subTest(item=item),self.assertRaises(Stop):
                native.configure(page,item)
            self.assertFalse(page.mock_calls)

    def test_menu_fields_are_bound_to_the_observed_source_inventory(self):
        for field in ('Website','Organization','Full Name','Date of birth'):
            item=plan();item['clauses'][1]['if_field']=field
            self.assertEqual(native.validate(item),item)


class InventoryTests(unittest.TestCase):
    def dialog(self,rules):
        dialog, cards, no_rules=Mock(),Mock(),Mock()
        cards.count.return_value=len(rules)
        no_rules.count.return_value=int(not rules)
        dialog.locator.return_value=cards
        dialog.get_by_text.return_value=no_rules
        card_nodes=[]
        for rule in rules:
            card,heading,rows,outcome,edit,delete= [Mock() for _ in range(6)]
            heading.count.return_value=outcome.count.return_value=1
            edit.count.return_value=delete.count.return_value=1
            heading.inner_text.return_value=rule['effect']
            rows.count.return_value=len(rule['rows'])
            row_nodes=[]
            for tokens in rule['rows']:
                row=Mock();row.locator.return_value.evaluate_all.return_value=tokens
                row_nodes.append(row)
            rows.nth.side_effect=row_nodes.__getitem__
            outcome.locator.return_value.evaluate_all.return_value=rule['outcome']
            selectors={'#edit-condition':edit,'#delete-condition':delete,
                       '.text-sm.font-semibold':heading,'.condition-summary-row':rows,
                       native.OUTCOME:outcome}
            card.locator.side_effect=selectors.__getitem__
            card_nodes.append(card)
        cards.nth.side_effect=card_nodes.__getitem__
        return dialog,no_rules,card_nodes

    def test_reads_all_cards_including_binary_values_and_exact_connector_order(self):
        expected=native._expected(plan(match='any'))
        dialog,_,_=self.dialog(expected)
        self.assertEqual(native._inventory(dialog),expected)
        self.assertEqual(native._inventory(dialog)[0]['rows'][0][-1],'@')

    def test_empty_inventory_requires_the_native_empty_state(self):
        dialog,empty,_=self.dialog([])
        self.assertEqual(native._inventory(dialog),[])
        empty.count.return_value=0
        with self.assertRaisesRegex(Stop,'refusing inferred absence'):
            native._inventory(dialog)

    def test_a_matching_rule_does_not_hide_an_unrelated_second_card(self):
        matching=native._expected(plan())
        unrelated=deepcopy(matching[0]);unrelated['outcome']=['Hide Field','Phone']
        dialog,_,_=self.dialog([*matching,unrelated])
        self.assertNotEqual(native._inventory(dialog),matching)

    def test_contradictory_empty_state_does_not_prove_a_clean_condition_set(self):
        dialog,empty,_=self.dialog(native._expected(plan()))
        empty.count.return_value=1
        with self.assertRaisesRegex(Stop,'conflicts'):
            native._inventory(dialog)


if __name__=='__main__':
    unittest.main()
