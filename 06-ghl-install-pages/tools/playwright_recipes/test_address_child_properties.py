"""Address child properties use captured native controls and preserved state."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

import forms_advanced as native
import field_placement
from skill6_playwright import Stop


def state(**changes):
    result={'label':'Street Address','placeholder':'Enter your full address',
            'short_label':'','required':False,'hidden':False,'hidden_value':None}
    result.update(changes)
    return result


class Control:
    def __init__(self,item,key):self.item,self.key=item,key
    def count(self):return int(self.key!='hidden_value' or self.item.values['hidden'])
    def is_visible(self):return self.count()==1
    def input_value(self):return self.item.values[self.key]
    def evaluate(self,_):
        return {'label':'Label','placeholder':'Placeholder','short_label':'Short Label',
                'hidden_value':'Hidden valuePlease Input'}[self.key]
    def get_attribute(self,name):
        assert name=='aria-checked'
        return 'true' if self.item.values[self.key] else 'false'
    def fill(self,value):
        self.item.events.append(('fill',self.key,value))
        self.item.values[self.key]=value
    def click(self):
        value=not self.item.values[self.key]
        other='hidden' if self.key=='required' else 'required'
        if value and self.item.values[other]:raise AssertionError('Intermediate Required/Hidden conflict')
        self.item.events.append(('click',self.key,value))
        self.item.values[self.key]=value
        if self.key=='hidden':self.item.values['hidden_value']='' if value else None


class Item:
    def __init__(self,values):self.values,self.events=deepcopy(values),[]
    def locator(self,selector):
        mapping={value[0]:key for key,value in native._ADDRESS_TEXT_CONTROLS.items()}
        mapping.update({value:key for key,value in native._ADDRESS_CHECKBOX_CONTROLS.items()})
        mapping['#fieldHiddenvalue input']='hidden_value'
        return Control(self,mapping[selector])


class AddressPropertyTests(unittest.TestCase):
    def step(self,properties=None,expected=None):
        return {'address_fields':[{'field':'Street Address','query_key':'address',
            'properties':properties or {'label':'Street location'},
            'expected_properties':expected or {'label':'Street Address'}}]}

    def test_schema_requires_matching_previous_values_and_binds_them_in_hash(self):
        valid=self.step()
        self.assertEqual(native.validate(valid),valid)
        changed=deepcopy(valid);changed['address_fields'][0]['expected_properties']['label']='Other'
        self.assertNotEqual(native.configuration_hash(valid),native.configuration_hash(changed))
        for broken in [self.step({'width_pct':50},{'width_pct':100}),
                       self.step({'required':1},{'required':False}),
                       self.step({'hidden':True},{'hidden':False}),
                       self.step({'hidden_value':'x'},{'hidden_value':None})]:
            with self.subTest(broken=broken),self.assertRaises(Stop):native.validate(broken)

    def test_captured_text_flags_and_hidden_value_round_trip(self):
        item=Item(state(hidden=True,hidden_value='retained'))
        with patch.object(native,'_child_item',return_value=item):
            _,values=native._child_properties(Mock(),'Street Address')
        self.assertEqual(values,item.values)

    def test_text_edit_preserves_checkbox_states_and_existing_hidden_value(self):
        before=state(hidden=True,hidden_value='retained')
        desired={**before,'label':'Street location','short_label':'Street'}
        item=Item(before)
        with patch.object(native,'_child_item',return_value=item), \
             patch.object(native,'click',side_effect=lambda n:n.click()), \
             patch.object(native,'fill',side_effect=lambda n,v:n.fill(v)):
            native._write_child_properties(Mock(),'Street Address',before,desired)
        self.assertEqual(item.values,desired)
        self.assertEqual(item.events,[('fill','label','Street location'),('fill','short_label','Street')])

    def test_required_is_disabled_before_hidden_is_enabled_and_value_is_authored(self):
        before=state(required=True)
        desired=state(required=False,hidden=True,hidden_value='approved')
        item=Item(before)
        with patch.object(native,'_child_item',return_value=item), \
             patch.object(native,'click',side_effect=lambda n:n.click()), \
             patch.object(native,'fill',side_effect=lambda n,v:n.fill(v)):
            native._write_child_properties(Mock(),'Street Address',before,desired)
        self.assertEqual(item.events,[('click','required',False),('click','hidden',True),
                                      ('fill','hidden_value','approved')])
        self.assertEqual(item.values,desired)

    def test_concurrent_property_change_stops_before_any_edit(self):
        before=state();item=Item(state(label='Concurrent edit'))
        with patch.object(native,'_child_item',return_value=item),self.assertRaisesRegex(Stop,'changed after preflight'):
            native._write_child_properties(Mock(),'Street Address',before,{**before,'label':'Authored'})
        self.assertEqual(item.events,[])

    def test_later_child_previous_value_mismatch_prevents_earlier_query_write(self):
        step=self.step()
        step['address_fields'][0]['query_key']='street_address'
        step['address_fields'].append({'field':'City','query_key':'city',
            'properties':{'label':'Municipality'},'expected_properties':{'label':'Expected city'}})
        items={'Street Address':Item(state()),'City':Item(state(label='Different city'))}
        page,frame=Mock(),Mock();page.url='https://example.com/v2/location/L/form-builder-v2/F'
        frame.get_by_role.return_value.count.return_value=1
        frame.get_by_role.return_value.input_value.return_value='Fixture'
        with patch.object(native,'form_builder',return_value=frame), \
             patch.object(native,'_inventory',return_value={v:'group' for v in native._ADDRESS_QUERIES.values()}), \
             patch.object(native,'_open_address'), \
             patch.object(native,'_snapshot',return_value=dict(native._ADDRESS_QUERIES)), \
             patch.object(native,'_child_item',side_effect=lambda f,l:items[l]), \
             patch.object(native,'fill') as fill,patch.object(native,'click') as click, \
             self.assertRaisesRegex(Stop,'inventoried previous'):
            native.configure(page,step)
        fill.assert_not_called();click.assert_not_called()

    def test_hidden_enable_has_explicit_before_absence_and_authored_default(self):
        step=self.step({'hidden':True,'hidden_value':'approved'},
                       {'hidden':False,'hidden_value':None})
        self.assertEqual(native.validate(step),step)


class AddressAccordionTests(unittest.TestCase):
    def test_known_autocomplete_section_is_accepted_but_unknown_sixth_is_not(self):
        frame,headers,match=Mock(),Mock(),Mock()
        frame.locator.return_value=headers;headers.count.return_value=6
        headers.filter.return_value=match;match.count.return_value=1
        self.assertIs(field_placement._address_headers(frame),headers)
        pattern=headers.filter.call_args.kwargs['has_text']
        self.assertTrue(pattern.fullmatch('Auto Complete AddressNew'))
        self.assertFalse(pattern.fullmatch('Unknown child'))
        match.count.return_value=0
        with self.assertRaisesRegex(Stop,'Unknown extra'):field_placement._address_headers(frame)


if __name__=='__main__':unittest.main()
