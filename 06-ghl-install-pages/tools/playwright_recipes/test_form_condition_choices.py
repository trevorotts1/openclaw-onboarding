"""Native choice predicates bind the actual field identity and exact picklist value."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from test_form_condition_field_bindings import canvas_fixture
import form_condition_fields as fields
import form_conditions as group
import form_condition_stack as stack
import form_condition_outcomes as outcomes
import recipe_cli
import skill6_playwright as runner

SINGLE={'label':'Single choice','field_type':'SINGLE_OPTIONS','query_key':'single_choice'}
MULTI={'label':'Multi choice','field_type':'MULTIPLE_OPTIONS','unique_key':'contact.multi_choice'}
CHECKBOX={'label':'Checkbox choice','field_type':'CHECKBOX','query_key':'checkbox_choice'}
RADIO={'label':'Radio choice','field_type':'RADIO','query_key':'radio_choice'}


def rule(label,value):
    return {'match':'all','clauses':[{'if_field':label,'operator':'Is Equal To','value':value}],
            'effect':'Hide Field','target':label}


class ChoiceBindingTests(unittest.TestCase):
    def test_both_native_identity_forms_work_in_existing_stack_and_outcome_compiler(self):
        for binding,value in ((SINGLE,'Medium'),(MULTI,'Alpha'),(CHECKBOX,'ZHC One'),(RADIO,'Option 1')):
            condition={'field_bindings':[binding],'rules':[rule(binding['label'],value)]}
            for module in (stack,outcomes):
                with self.subTest(type=binding['field_type'],module=module.__name__):
                    self.assertEqual(module.validate(condition),condition)
            data={'location_id':'LOC','location_name':'Fixture',
                'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM','condition':condition}
            compiled=runner.validate_job(recipe_cli.compile_recipe('forms.conditions',data),Path('.'))
            self.assertEqual(compiled['steps'][0]['field_bindings'],[binding])

    def test_wrong_identity_key_or_text_operator_refuses_before_page_access(self):
        malformed=deepcopy(MULTI);malformed['query_key']=malformed.pop('unique_key')
        for binding in (malformed,dict(MULTI,unique_key='bare_key')):
            with self.assertRaises(runner.Stop):fields.validate([binding])
        data={'rules':[rule(SINGLE['label'],'Medium')],'field_bindings':[SINGLE]}
        data['rules'][0]['clauses'][0]['operator']='Contains'
        page=Mock()
        with self.assertRaises(runner.Stop):stack.configure(page,data)
        self.assertFalse(page.mock_calls)

    def test_read_only_preflight_uses_local_query_and_canonical_advanced_unique_key(self):
        from playwright_recipes import form_widget_families as widgets
        bindings=[SINGLE,MULTI]
        fixture=[{**binding,'query_key':binding.get('query_key',binding.get('unique_key'))} for binding in bindings]
        frame,entries,queries,events,click=canvas_fixture(fixture)
        old_locate=frame.locator.side_effect
        frame.locator.side_effect=lambda selector:queries[1] if selector=='#uniqueKey input' else old_locate(selector)
        for item,_,_ in entries:
            old=item.locator.side_effect
            item.locator.side_effect=lambda selector,old=old:old('input.form-control') if selector=='input.dropdown-input' else old(selector)
        with patch.object(fields,'_close_initial'),patch.object(fields,'_close_properties'), \
             patch.object(fields,'click',side_effect=click),patch.object(widgets,'_advanced'):
            self.assertEqual(fields.preflight(frame,bindings,lambda:None),bindings)
            queries[1].input_value.return_value='contact.foreign'
            with self.assertRaisesRegex(runner.Stop,'Unique Key differs'):
                fields.preflight(frame,bindings,lambda:None)
        self.assertFalse(any('fill' in str(call) for call in frame.mock_calls))

    def test_checkbox_and_radio_preflight_bind_existing_choice_owner_and_native_query_key(self):
        for binding in (CHECKBOX,RADIO):
            frame,entries,queries,events,click=canvas_fixture([binding])
            item=entries[0][0];old=item.locator.side_effect
            controls=old('input.form-control');controls.nth.return_value=controls
            controls.is_enabled.return_value=False;controls.get_attribute.return_value='opaque-existing-field-id'
            item.locator.side_effect=lambda selector:controls if selector.startswith('input[type=') else old(selector)
            with self.subTest(kind=binding['field_type']),patch.object(fields,'_close_initial'), \
                 patch.object(fields,'_close_properties'),patch.object(fields,'click',side_effect=click):
                self.assertEqual(fields.preflight(frame,[binding],lambda:None),[binding])
            self.assertEqual(events,[('select',0),('settings',0)])


class ChoiceValueTests(unittest.TestCase):
    def test_value_uses_captured_picklist_and_exact_visible_option_not_text_fill(self):
        modal,frame,missing,picker=Mock(),Mock(),Mock(),Mock()
        missing.count.return_value=0;picker.count.return_value=1;picker.is_visible.return_value=True
        picker.get_attribute.return_value='n-select visible hl-select'
        modal.locator.side_effect=lambda selector:picker if selector=='#picklistOptions-0' else missing
        state={'selected':'Small'}
        clause={'if_field':SINGLE['label'],'operator':'Is Equal To','value':'Medium'}
        def choose(actual_frame,selector,value):
            self.assertIs(actual_frame,frame);self.assertEqual(selector,'#picklistOptions-0')
            state['selected']=value
        writer=Mock()
        with patch.object(group,'_choose',side_effect=choose) as choose, \
             patch.object(group,'_selected',side_effect=lambda _:state['selected']):
            group._write_clause_value(modal,0,clause,writer=writer,frame=frame)
            group._read_clause_value(modal,0,clause)
            state['selected']='Large'
            with self.assertRaisesRegex(runner.Stop,'differs'):group._read_clause_value(modal,0,clause)
        writer.assert_not_called();choose.assert_called_once()

    def test_native_other_sentinel_reads_as_the_saved_other_summary_label(self):
        modal,missing,picker=Mock(),Mock(),Mock()
        missing.count.return_value=0;picker.count.return_value=1;picker.is_visible.return_value=True
        picker.get_attribute.return_value='n-select visible hl-select'
        modal.locator.side_effect=lambda selector:picker if selector=='#picklistOptions-0' else missing
        with patch.object(group,'_selected',return_value='--Other--'):
            group._read_clause_value(modal,0,{'operator':'Is Equal To','value':'Other'})


if __name__=='__main__':unittest.main()
