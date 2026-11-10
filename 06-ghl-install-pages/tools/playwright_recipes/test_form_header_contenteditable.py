"""A real typed form writer accepts the captured contenteditable owner header."""
from copy import deepcopy
from unittest.mock import Mock,patch
import unittest

import assessments
import form_condition_stack as native
from skill6_playwright import Stop
from test_form_condition_card_removal import CardDrawer,instant_wait
from test_form_condition_stack import rule


class FormHeader:
    def __init__(self,*,editable=True,role='textbox',label='Form Name'):
        self.name='Fixture';self.editable=editable;self.role=role;self.label=label
        self.input_reads=0;self.text_reads=0

    def count(self):return 1
    def wait_for(self,**_):pass
    def get_attribute(self,key):
        return {'contenteditable':'true' if self.editable else None,
                'role':self.role,'aria-label':self.label}.get(key)
    def inner_text(self):
        self.text_reads+=1;return self.name
    def input_value(self):
        self.input_reads+=1
        if self.editable:raise AssertionError('A contenteditable DIV has no native input value')
        return self.name


class FormHeaderHandlerTests(unittest.TestCase):
    def exercise(self,header,*,drift=False):
        state=CardDrawer();state.title=header
        page=Mock();page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
        data={'expected_rules':[rule('Phone'),rule('Email')],'rules':[rule('Phone')]}
        def click(node):
            state.click(node)
            if drift and type(getattr(node,'index',None)) is int:header.name='Different form'
        with patch.object(native,'form_builder',return_value=state.frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=click), \
             patch.object(native.group,'_inventory',side_effect=lambda _:deepcopy(state.current)), \
             patch.object(native,'wait_until',side_effect=instant_wait), \
             patch.object(native.group,'_wait_for_form_save'), \
             patch.object(native,'reopen_editor',side_effect=state.reopen):
            try:result=native.configure(page,data)
            except (Stop,assessments.AssessmentError) as error:result=error
        return state,result

    def test_captured_contenteditable_form_header_survives_real_delete_save_reopen_handler(self):
        header=FormHeader();state,result=self.exercise(header)
        self.assertEqual(result['status'],'CONDITION_STACK_SAVED_AND_REOPENED')
        self.assertEqual(state.events,[('open_delete',1),('confirm',),('save',),('reopen',)])
        self.assertGreater(header.text_reads,1);self.assertEqual(header.input_reads,0)

    def test_legacy_native_input_header_still_uses_native_value(self):
        header=FormHeader(editable=False);_,result=self.exercise(header)
        self.assertEqual(result['independent_readback'],'VERIFIED')
        self.assertGreater(header.input_reads,1);self.assertEqual(header.text_reads,0)

    def test_contenteditable_role_and_label_mismatch_fail_before_first_card_mutation(self):
        for header in (FormHeader(role='button'),FormHeader(label='Field Label')):
            state,result=self.exercise(header)
            self.assertIsInstance(result,assessments.AssessmentError);self.assertEqual(state.events,[])
            self.assertEqual(header.input_reads,0)

    def test_contenteditable_title_change_before_confirmation_prevents_delete_and_save(self):
        header=FormHeader();state,result=self.exercise(header,drift=True)
        self.assertIsInstance(result,Stop)
        self.assertEqual(state.events,[('open_delete',1)])
        self.assertEqual(header.input_reads,0)


if __name__=='__main__':unittest.main()
