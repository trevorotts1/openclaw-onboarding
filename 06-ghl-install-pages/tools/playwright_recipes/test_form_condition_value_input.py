"""Native n-input wrappers remain in the DOM for unary conditions."""
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
import unittest
from unittest.mock import Mock

import form_conditions as native
from skill6_playwright import Stop


class Capture(HTMLParser):
    def __init__(self):
        super().__init__();self.wrapper={};self.inputs=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if attrs.get('id')=='inputValue-0':self.wrapper={'tag':tag,**attrs}
        if tag=='input':self.inputs.append(attrs)


def controls(*,binary=False):
    capture=Capture()
    capture.feed((Path(__file__).parent/'fixtures/form-condition-value-captured.html').read_text())
    wrapper,control,modal=Mock(),Mock(),Mock()
    attributes=deepcopy(capture.wrapper)
    if binary:attributes['class']=' '.join(c for c in attributes['class'].split() if c!='invisible')
    wrapper.count.return_value=control.count.return_value=1
    wrapper.get_attribute.side_effect=attributes.get
    control.get_attribute.side_effect=capture.inputs[0].get
    wrapper.is_visible.return_value=control.is_visible.return_value=binary
    wrapper.locator.side_effect={'input.n-input__input-el':control}.__getitem__
    modal.locator.side_effect={'#inputValue-0':wrapper}.__getitem__
    return modal,wrapper,control,capture


class ConditionValueTests(unittest.TestCase):
    def test_real_capture_is_div_with_one_nested_input_not_an_input_with_the_id(self):
        modal,wrapper,control,capture=controls()
        self.assertEqual(capture.wrapper['tag'],'div')
        self.assertEqual(len(capture.inputs),1)
        self.assertIsNone(native._value_input(modal,0,unary=True))
        wrapper.input_value.assert_not_called();control.input_value.assert_not_called()

    def test_binary_writer_receives_the_nested_textbox_and_never_the_wrapper(self):
        modal,wrapper,control,_=controls(binary=True)
        self.assertIs(native._value_input(modal,0),control)
        wrapper.fill.assert_not_called();wrapper.input_value.assert_not_called()

    def test_visible_unary_and_hidden_binary_both_refuse(self):
        for binary,unary in ((True,True),(False,False)):
            modal,*_=controls(binary=binary)
            with self.subTest(binary=binary),self.assertRaises(Stop):native._value_input(modal,0,unary=unary)

    def test_malformed_wrapper_nested_input_and_placeholder_refuse(self):
        for mutation in ('wrapper_class','multiple_inputs','type','placeholder','visible_hidden_control'):
            modal,wrapper,control,_=controls()
            if mutation=='wrapper_class':wrapper.get_attribute.side_effect=lambda key:'unrelated'
            elif mutation=='multiple_inputs':control.count.return_value=2
            elif mutation=='visible_hidden_control':control.is_visible.return_value=True
            else:
                control.get_attribute.side_effect=lambda key,mutation=mutation:(
                    'password' if mutation=='type' and key=='type' else
                    'Other input' if mutation=='placeholder' and key=='placeholder' else
                    {'type':'text','placeholder':'Please Type a value here'}.get(key))
            with self.subTest(mutation=mutation),self.assertRaises(Stop):native._value_input(modal,0,unary=True)

    def test_previously_absent_unary_control_is_retained_without_relaxing_binary(self):
        modal=Mock();modal.locator.return_value.count.return_value=0
        self.assertIsNone(native._value_input(modal,0,unary=True))
        with self.assertRaises(Stop):native._value_input(modal,0)


if __name__=='__main__':unittest.main()
