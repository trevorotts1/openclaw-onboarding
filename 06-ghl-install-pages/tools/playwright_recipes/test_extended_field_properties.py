"""Captured simple-field editing: identity, preflight and saved read-back contracts.

This is an offline native-control model. It does not claim a client browser run.
"""
from copy import deepcopy
from unittest.mock import Mock, patch
import unittest

import assessments as a
import skill6_playwright as runner


# Independently transcribed from the native captures, not generated from the
# implementation's name/key/type table.
CAPTURED = {
    'Full Name': ('text', 'Enter your full name', 'full_name'),
    'Organization': ('text', 'Enter your organization', 'organization'),
    'Website': ('text', 'https://yourwebsite.com', 'website'),
    'Date of birth': ('date', 'DD / MM / YYYY', 'date_of_birth'),
    'City': ('text', 'Enter your city', 'city'),
    'State': ('text', 'Enter your state', 'state'),
    'Country': ('select', 'Enter your country', 'country'),
    'Postal Code': ('text', 'ZIP or postal code', 'postal_code'),
}


def field(name, *, required=False, hidden=False, default='retained value'):
    kind, placeholder, key = CAPTURED[name]
    values = [name, placeholder, '', key, '100']
    if hidden:
        values.append(default)
    return {'type':kind, 'values':values, 'required':required, 'hidden':hidden}


class Node:
    def __init__(self, frame, kind, *, item=None, index=None, name=None):
        self.frame, self.kind, self.item = frame, kind, item
        self.index, self.name = index, name

    def count(self):
        if self.kind == 'dialog':return int(self.frame.drawer)
        if self.kind == 'targets':return len(self.frame.matches(self.name))
        if self.kind == 'items':return len(self.frame.fields)
        if self.kind == 'properties':return len(self.frame.selected['values'])
        if self.kind == 'backs':return 2 if self.frame.selected is not None else 1
        if self.kind == 'canvas_inputs':return self.item.get('input_count',1)
        if self.kind == 'missing':return 0
        return 1

    def nth(self, index):
        if self.kind == 'properties':return Node(self.frame,'property',index=index)
        if self.kind == 'items':return Node(self.frame,'wrapper',item=self.frame.fields[index])
        if self.kind == 'backs':return Node(self.frame,'back',index=index)
        raise AssertionError((self.kind,index))

    def locator(self, selector):
        if self.kind == 'targets':
            assert selector == a.FIELD_WRAPPER
            matches = self.frame.matches(self.name)
            assert len(matches) == 1
            return Node(self.frame,'missing' if matches[0].get('outside_canvas') else 'wrapper',item=matches[0])
        if self.kind == 'missing':return Node(self.frame,'missing')
        if self.kind == 'wrapper':
            kinds = {'[data-field-type]':'field_type', 'input':'canvas_inputs',
                     '[aria-label="Open settings"]':'gear'}
            return Node(self.frame,kinds[selector],item=self.item)
        raise AssertionError((self.kind,selector))

    def get_by_text(self, text, *, exact):
        assert self.kind == 'dialog' and text == 'Form Element' and exact
        return Node(self.frame,'drawer_heading')

    def get_by_role(self, role, *, name, exact):
        assert self.kind == 'dialog' and role == 'button' and name == 'Close' and exact
        return Node(self.frame,'close_drawer')

    def get_attribute(self, attribute):
        assert self.kind == 'field_type' and attribute == 'data-field-type'
        return self.item['type']

    def evaluate(self, _):
        assert self.kind == 'property'
        labels = ['Label', 'Placeholder', 'Short LabelPlease Input', 'Query Key ', 'Field Width%', 'Hidden value']
        if self.frame.selected.get('drift') and self.index == 3:return 'Different control'
        return labels[self.index]

    def input_value(self):
        if self.kind == 'title':return 'Fixture native properties'
        if self.kind == 'property':return self.frame.selected['values'][self.index]
        raise AssertionError(self.kind)

    def fill(self, value):
        assert self.kind == 'property'
        self.frame.writes.append(('value', self.index, value))
        self.frame.selected['values'][self.index] = value

    def is_checked(self):
        assert self.kind == 'checkbox'
        return self.frame.selected[self.name.lower()]

    def set_checked(self, value):
        assert self.kind == 'checkbox'
        key = self.name.lower()
        other = 'required' if key == 'hidden' else 'hidden'
        if value and self.frame.selected[other]:
            raise AssertionError('Intermediate required/hidden conflict')
        self.frame.writes.append((key,value))
        self.frame.selected[key] = value
        if key == 'hidden':
            values = self.frame.selected['values']
            if value and len(values) == 5:values.append('')
            if not value and len(values) == 6:values.pop()

    def click(self, **_):
        f = self.frame
        if self.kind == 'targets':
            assert self.count() == 1
            f.selected = f.matches(self.name)[0]
        elif self.kind == 'canvas_inputs':f.selected = self.item
        elif self.kind == 'gear':
            assert f.selected is self.item
            f.panel_opens += 1
            if f.change_on_open == f.panel_opens:
                f.selected['values'][0] = 'Concurrent outside edit'
        elif self.kind == 'back':
            assert self.index == 1
            f.selected = None
            f.drawer = f.restore_drawer
        elif self.kind == 'close_drawer':f.drawer = False
        elif self.kind == 'save':
            f.saves += 1
            if not f.lose_save:f.persisted = deepcopy(f.fields)
        elif self.kind == 'edit':pass
        else:raise AssertionError(('click',self.kind))

    def press(self, key, **_):
        assert self.kind in ('targets','canvas_inputs') and key == 'Escape'
        self.frame.escapes.append(self.frame.selected['type'])

    def wait_for(self, **_):
        assert self.count() == 1, ('missing native control',self.kind)

    def is_visible(self):return self.count() == 1
    def is_enabled(self):return True


class Frame:
    def __init__(self, fields, *, lose_save=False):
        self.fields = deepcopy(fields)
        self.persisted = deepcopy(fields)
        self.selected = None
        self.drawer = True
        self.restore_drawer = True
        self.writes = []
        self.saves = self.reopens = self.panel_opens = 0
        self.escapes = []
        self.lose_save = lose_save
        self.change_on_open = None
        self.readback_corruption = None

    def matches(self, placeholder):
        return [item for item in self.fields if item['values'][1] == placeholder]

    def locator(self, selector):
        assert selector == '#form-builder-container > .form-field-wrapper'
        return Node(self,'items')

    def get_by_placeholder(self, text, *, exact):
        assert exact
        return Node(self,'targets',name=text)

    def get_by_role(self, role, *, name=None, exact=True):
        assert exact
        if role == 'dialog':return Node(self,'dialog')
        if role == 'textbox':return Node(self,'title' if name == 'Form Name' else 'properties')
        if role == 'checkbox':return Node(self,'checkbox',name=name)
        if role == 'tab' and name == 'Edit':return Node(self,'edit')
        if role == 'button' and name == 'Back':return Node(self,'backs')
        if role == 'button' and name == 'Save':return Node(self,'save')
        raise AssertionError((role,name))

    def get_by_text(self, text, *, exact):
        assert exact and text == 'General Settings'
        return Node(self,'heading')

    def reopen(self, *_):
        self.reopens += 1
        self.fields = deepcopy(self.persisted)
        self.selected = None
        self.drawer = True
        if self.readback_corruption:self.readback_corruption(self.fields)


class ExtendedFieldProperties(unittest.TestCase):
    def run_fields(self, frame, fields):
        page = Mock()
        page.url = 'https://app.convertandflow.com/v2/location/FIXTURE/form-builder-v2/FORM_FIXTURE'
        with patch.object(runner,'form_builder',return_value=frame), \
             patch.object(a,'reopen_editor',side_effect=frame.reopen) as reopen:
            result = a.configure_fields(page,{'action':'native_fields','fields':fields})
        reopen.assert_called_once_with(page,'form','Fixture native properties',page.url)
        return result

    def test_all_eight_captured_builtin_properties_save_and_reopen(self):
        for name in CAPTURED:
            with self.subTest(field=name):
                f = Frame([field(name)])
                result = self.run_fields(f,[{'field':name,'label':'Fixture '+name,
                    'placeholder':'Authored '+name,'short_label':'Client','width_pct':50,'required':True}])
                self.assertEqual(f.fields[0]['values'], ['Fixture '+name,'Authored '+name,'Client',CAPTURED[name][2],'50'])
                self.assertTrue(f.fields[0]['required'])
                self.assertEqual((f.saves,f.reopens),(1,1))
                self.assertEqual(result['fields'],[name])
                self.assertIs(result['submission_verified'],False)
                if name in ('Country','Date of birth'):self.assertTrue(f.escapes)

    def test_hidden_default_and_other_fields_are_preserved(self):
        f = Frame([field('Website',hidden=True),field('Date of birth',required=True)])
        untouched = deepcopy(f.fields[1])
        self.run_fields(f,[{'field':'Website','label':'Homepage'}])
        self.assertEqual(f.fields[0]['values'][5],'retained value')
        self.assertTrue(f.fields[0]['hidden'])
        self.assertFalse(f.fields[0]['required'])
        self.assertEqual(f.fields[1],untouched)
        self.assertEqual(f.writes,[('value',0,'Homepage')])

    def test_explicit_hidden_default_and_exclusion_order_are_verified(self):
        f = Frame([field('Website',required=True)])
        self.run_fields(f,[{'field':'Website','required':False,'hidden':True,'hidden_value':'author default'}])
        self.assertFalse(f.fields[0]['required'])
        self.assertTrue(f.fields[0]['hidden'])
        self.assertEqual(f.fields[0]['values'][5],'author default')
        self.assertEqual(f.writes[0],('required',False))

    def test_missing_and_duplicate_placeholder_anchors_refuse_without_writes(self):
        for items in ([field('Organization')],[field('Website'),field('Website')]):
            with self.subTest(items=items):
                f = Frame(items)
                with self.assertRaisesRegex(runner.Stop,'absent or ambiguous'):
                    self.run_fields(f,[{'field':'Website','label':'Homepage'}])
                self.assertEqual((f.writes,f.saves),([],0))

    def test_wrong_type_or_composite_shape_refuses_without_property_writes(self):
        for changes in ({'type':'email'},{'type':'group','input_count':6},{'input_count':2}):
            with self.subTest(changes=changes):
                f = Frame([{**field('Website'),**changes}])
                with self.assertRaisesRegex(runner.Stop,'different native type or composite'):
                    self.run_fields(f,[{'field':'Website','label':'Homepage'}])
                self.assertEqual((f.writes,f.saves),([],0))

    def test_matching_input_outside_direct_native_canvas_cannot_be_edited(self):
        item = field('Website');item['outside_canvas'] = True
        f = Frame([item])
        with self.assertRaisesRegex(runner.Stop,'different native type or composite'):
            self.run_fields(f,[{'field':'Website','label':'Homepage'}])
        self.assertEqual((f.writes,f.saves),([],0))

    def test_later_wrong_query_prevents_earlier_field_write(self):
        wrong = field('Date of birth');wrong['values'][3] = 'unknown_date'
        f = Frame([field('Website'),wrong])
        with self.assertRaisesRegex(runner.Stop,'identity differs'):
            self.run_fields(f,[{'field':'Website','label':'Homepage'},{'field':'Date of birth','required':True}])
        self.assertEqual((f.writes,f.saves),([],0))

    def test_later_required_hidden_conflict_prevents_earlier_field_write(self):
        f = Frame([field('Website'),field('Date of birth',hidden=True)])
        with self.assertRaisesRegex(runner.Stop,'required and hidden'):
            self.run_fields(f,[{'field':'Website','label':'Homepage'},{'field':'Date of birth','required':True}])
        self.assertEqual((f.writes,f.saves),([],0))

    def test_renamed_existing_anchor_needs_exact_supplied_identity(self):
        item = field('Website');item['values'][1] = 'Existing URL';item['values'][3] = 'client_url'
        f = Frame([item])
        with self.assertRaises(runner.Stop):
            self.run_fields(f,[{'field':'Website','label':'Homepage'}])
        self.assertEqual(f.writes,[])
        self.run_fields(f,[{'field':'Website','label':'Homepage',
            'current_placeholder':'Existing URL','current_query_key':'client_url'}])
        self.assertEqual(f.fields[0]['values'][1:4],['Existing URL','','client_url'])

    def test_schema_query_and_placeholder_collisions_refuse_before_browser(self):
        cases = [
            [{'field':'Website','query_key':''}],
            [{'field':'Website','query_key':'white space'}],
            [{'field':'Website','query_key':'organization'}],
            [{'field':'Website','query_key':'custom'},{'field':'Organization','query_key':'custom'}],
            [{'field':'Website','query_key':'organization'},{'field':'Organization','query_key':'website'}],
            [{'field':'Website','placeholder':'Enter your organization'},
             {'field':'Organization','placeholder':'https://yourwebsite.com'}],
            [{'field':'Address','label':'Location'}],
        ]
        for fields in cases:
            with self.subTest(fields=fields), patch.object(runner,'form_builder') as builder:
                with self.assertRaises(a.AssessmentError):a.configure_fields(Mock(),{'fields':fields})
                builder.assert_not_called()

    def test_property_row_drift_on_later_field_prevents_earlier_write(self):
        item = field('Country');item['drift'] = True
        f = Frame([field('Website'),item])
        with self.assertRaisesRegex(runner.Stop,'property order changed'):
            self.run_fields(f,[{'field':'Website','label':'Homepage'},{'field':'Country','required':True}])
        self.assertEqual((f.writes,f.saves),([],0))

    def test_field_changed_after_preflight_stops_before_property_write(self):
        f = Frame([field('Website')]);f.change_on_open = 2
        with self.assertRaisesRegex(runner.Stop,'changed after preflight'):
            self.run_fields(f,[{'field':'Website','label':'Homepage'}])
        self.assertEqual((f.writes,f.saves),([],0))

    def test_lost_save_and_changed_reopened_type_cannot_report_success(self):
        f = Frame([field('Website')],lose_save=True)
        with self.assertRaises(runner.Stop):self.run_fields(f,[{'field':'Website','label':'Homepage'}])
        self.assertEqual((f.saves,f.reopens),(1,1))
        f = Frame([field('Website')]);f.readback_corruption = lambda items:items[0].update(type='email')
        with self.assertRaises(runner.Stop):self.run_fields(f,[{'field':'Website','label':'Homepage'}])
        self.assertEqual((f.saves,f.reopens),(1,1))

    def test_actual_unrequested_renamed_query_blocks_requested_query_change(self):
        item = field('Organization');item['values'][3] = 'shared_query'
        f = Frame([field('Website'),item])
        with self.assertRaisesRegex(runner.Stop,'already belongs'):
            self.run_fields(f,[{'field':'Website','query_key':'shared_query'}])
        self.assertEqual((f.writes,f.saves),([],0))

    def test_actual_unrequested_renamed_placeholder_blocks_requested_change(self):
        item = field('Organization');item['values'][1] = 'Shared prompt'
        f = Frame([field('Website'),item])
        with self.assertRaisesRegex(runner.Stop,'placeholder is already present'):
            self.run_fields(f,[{'field':'Website','placeholder':'Shared prompt'}])
        self.assertEqual((f.writes,f.saves),([],0))

    def test_query_update_preserves_unrequested_custom_keys_and_verifies_inventory(self):
        custom = field('Organization');custom['values'][3] = 'other_custom_key'
        f = Frame([field('Website'),custom])
        self.run_fields(f,[{'field':'Website','query_key':'authored_homepage'}])
        self.assertEqual([item['values'][3] for item in f.fields],['authored_homepage','other_custom_key'])
        self.assertEqual((f.saves,f.reopens),(1,1))

    def test_uninventoried_type_blocks_query_change_but_allows_other_known_field_properties(self):
        custom = field('Organization');custom['type'] = 'uncaptured_file_upload'
        f = Frame([field('Website'),custom])
        with self.assertRaisesRegex(runner.Stop,'Uncaptured existing native field type'):
            self.run_fields(f,[{'field':'Website','query_key':'authored_homepage'}])
        self.assertEqual((f.writes,f.saves),([],0))
        self.run_fields(f,[{'field':'Website','label':'Homepage'}])
        self.assertEqual(f.fields[1],custom)

    def test_reopened_unrequested_query_drift_refuses_success(self):
        custom = field('Organization');custom['values'][3] = 'other_custom_key'
        f = Frame([field('Website'),custom])
        def corrupt(items):items[1]['values'][3] = 'unexpected_other_key'
        f.readback_corruption = corrupt
        with self.assertRaisesRegex(runner.Stop,'query inventory did not persist'):
            self.run_fields(f,[{'field':'Website','query_key':'authored_homepage'}])
        self.assertEqual((f.saves,f.reopens),(1,1))

    def test_extended_properties_do_not_expand_uncaptured_condition_menu(self):
        for label in CAPTURED:
            with self.subTest(label=label), self.assertRaises(a.AssessmentError):
                a.validate_condition({'effect':'Hide Field','if_field':label,
                    'operator':'Is Filled','target':'Last Name'})


if __name__ == '__main__':unittest.main()
