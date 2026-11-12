"""Native inclusive Number ranges and Number targets retain exact predicate identity."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import Mock

from test_form_condition_field_bindings import number_plans, NUMBER
import form_conditions as group
import form_condition_outcomes as outcomes
import recipe_cli
import skill6_playwright as runner


class InclusiveBetweenTests(unittest.TestCase):
    def test_range_and_numeric_target_flow_through_all_existing_condition_handlers(self):
        for module,data in number_plans('Between',['1','10']):
            target=data if module is group else data['rules'][0]
            target['target']=NUMBER['label']
            with self.subTest(module=module.__name__):
                self.assertEqual(module.validate(data),data)
                changed=deepcopy(data)
                (changed if module is group else changed['rules'][0])['clauses'][0]['value']=['2','8']
                self.assertNotEqual(module.configuration_hash(data),module.configuration_hash(changed))
        plan=number_plans('Between',['1','10'])[0][1]
        self.assertEqual(group._expected_rows(plan)[0],['If',NUMBER['label'],'Between','1 And 10'])

    def test_malformed_reversed_or_non_numeric_ranges_refuse_before_browser(self):
        for bounds in ('1 And 10',[],['1'],['10','1'],['NaN','10'],[1,'10'],['1','2','3']):
            for module,data in number_plans('Between',bounds):
                page=Mock()
                with self.subTest(bounds=bounds,module=module.__name__),self.assertRaises(runner.Stop):
                    module.configure(page,data)
                self.assertFalse(page.mock_calls)

    def controls(self):
        modal,owner,source=Mock(),Mock(),Mock();source.count.return_value=1
        wrappers=[Mock(),Mock()];controls=[Mock(),Mock()];boxes=[Mock(),Mock()]
        for side,wrapper,control in zip(('Start','End'),wrappers,controls):
            wrapper.count.return_value=control.count.return_value=1
            wrapper.is_visible.return_value=control.is_visible.return_value=True
            wrapper.get_attribute.return_value='n-input'
            control.get_attribute.side_effect=lambda key,side=side:'text' if key=='type' else side+' Value'
            control.input_value.return_value=''
            wrapper.locator.side_effect=lambda selector,control=control:owner if selector=='..' else control
        for box in boxes:
            box.count.return_value=1;box.is_visible.return_value=True
            box.get_attribute.side_effect=lambda key:'checkbox' if key=='role' else 'true'
        owner.locator.side_effect=lambda selector:owner if selector=='..' else source if selector=='#selectedField-0' else boxes[0] if selector=='#include-start' else boxes[1]
        absent=Mock();absent.count.return_value=0
        modal.locator.side_effect=lambda selector:wrappers[0] if selector=='#inputValueStart-0' else wrappers[1] if selector=='#inputValueEnd-0' else absent
        return modal,controls,boxes

    def test_two_nested_inputs_written_and_read_with_both_endpoint_flags_preserved(self):
        modal,controls,_=self.controls();writes=[]
        clause={'if_field':NUMBER['label'],'operator':'Between','value':['2','8']}
        def fill(control,value):
            writes.append(value);control.input_value.return_value=value
        group._write_clause_value(modal,0,clause,writer=fill)
        group._read_clause_value(modal,0,clause)
        self.assertEqual(writes,['2','8'])
        controls[1].input_value.return_value='9'
        with self.assertRaisesRegex(runner.Stop,'bounds differ'):group._read_clause_value(modal,0,clause)

    def test_exclusive_endpoint_refuses_before_first_value_write(self):
        modal,_,boxes=self.controls()
        boxes[0].get_attribute.side_effect=lambda key:'checkbox' if key=='role' else 'false'
        writer=Mock()
        with self.assertRaisesRegex(runner.Stop,'inclusive'):
            group._write_clause_value(modal,0,{'operator':'Between','value':['2','8']},writer=writer)
        writer.assert_not_called()

    def test_summary_reads_direct_spans_without_nested_and_duplication(self):
        card,rows,row=Mock(),Mock(),Mock()
        card.locator.return_value=rows;rows.count.return_value=1;rows.nth.return_value=row
        row.locator.return_value.evaluate_all.return_value=['If',NUMBER['label'],'Between','2 And 8']
        predicate=outcomes._predicate(card)
        self.assertEqual(predicate['clauses'][0]['value'],['2','8'])
        row.locator.assert_called_once_with(':scope > span')

    def test_existing_compiler_binds_range_values_without_new_action(self):
        condition=number_plans('Between',['2','8'])[1][1]
        inputs={'location_id':'LOC','location_name':'Fixture',
                'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM',
                'condition':condition}
        compiled=runner.validate_job(recipe_cli.compile_recipe('forms.conditions',inputs),Path('.'))
        self.assertEqual(compiled['steps'][0]['rules'][0]['clauses'][0]['value'],['2','8'])


if __name__=='__main__':unittest.main()
