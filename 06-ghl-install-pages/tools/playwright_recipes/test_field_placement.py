"""Native built-in placement input and saved-identity contracts."""
import unittest
from unittest.mock import Mock, patch
from copy import deepcopy

from skill6_playwright import Stop

import field_placement


class PlacementInputTests(unittest.TestCase):
    def test_authored_labels_are_preserved_without_alias_or_schema_guessing(self):
        step = {'id':'place', 'action':'native_field_placement',
                'add_fields':['Full Name', 'Date of birth', 'Website']}
        value = field_placement.validate(step)
        self.assertEqual(value, step)
        value['add_fields'].append('City')
        self.assertEqual(step['add_fields'], ['Full Name', 'Date of birth', 'Website'])

    def test_ambiguous_or_custom_creation_options_are_rejected_before_browser_work(self):
        for fields in (None, [], 'Full Name', [True], ['Date of Birth'], ['Custom Field'],
                       ['Full Name', 'Full Name'], [{'field':'City', 'required':True}]):
            with self.subTest(fields=fields), self.assertRaises(field_placement.FieldPlacementError):
                field_placement.validate({'add_fields':fields})
        for change in ({'schema':{'name':'Custom'}}, {'allow_schema_creation':True},
                       {'action':'native_fields'}, {'fields':[{'field':'First Name','required':True}]}):
            with self.subTest(change=change), self.assertRaises(field_placement.FieldPlacementError):
                field_placement.validate({'add_fields':['City'], **change})


class QueryIdentityTests(unittest.TestCase):
    def panel(self, rows):
        frame = Mock()
        inputs = frame.get_by_role.return_value
        inputs.count.return_value = len(rows)
        controls = []
        for label, value in rows:
            item = Mock()
            item.evaluate.return_value = label
            item.input_value.return_value = value
            controls.append(item)
        inputs.nth.side_effect = lambda index:controls[index]
        return frame, controls

    def test_reads_query_from_its_native_row_instead_of_fixed_input_index(self):
        frame, controls = self.panel([
            ('Label','Website'), ('Placeholder','https://yourwebsite.com'),
            ('Extra captured option','unchanged'), ('Short Label',''), ('Query Key','website'),
            ('Field Width','100')])
        self.assertEqual(field_placement._query_key(frame), 'website')
        frame.get_by_role.assert_called_once_with('textbox', name='Please Input', exact=True)
        self.assertFalse(any(control.fill.called or control.click.called for control in controls))

    def test_missing_duplicate_or_empty_query_row_is_not_inferred_from_placeholder(self):
        for rows in ([('Placeholder','https://yourwebsite.com')],
                     [('Query Key','website'),('Query Key','website')], [('Query Key','')]):
            frame, controls = self.panel(rows)
            with self.subTest(rows=rows), self.assertRaises(Stop):
                field_placement._query_key(frame)
            self.assertFalse(any(control.fill.called or control.click.called for control in controls))


class NativeNode:
    def __init__(self, frame, kind, index=None, name=None):
        self.frame, self.kind, self.index, self.name = frame, kind, index, name

    def count(self):
        f = self.frame
        if self.kind == 'items':return len(f.items)
        if self.kind == 'back_buttons':return 2 if f.selected is not None else 1
        if self.kind == 'drawer':return int(f.drawer)
        if self.kind == 'tile_labels':return f.tile_count
        if self.kind == 'submit':return sum(item['type'] == 'submit' for item in f.items)
        if self.kind == 'property_inputs':return len(f.property_rows())
        if self.kind == 'address_headers':return len(f.address_queries())
        if self.kind == 'address_query_inputs':return int(f.address_expanded.get(self.name,False))
        if self.kind == 'input':return self.frame.items[self.index].get('input_count',1)
        return 1

    def nth(self, index):
        if self.kind == 'items':return NativeNode(self.frame,'item',index)
        if self.kind == 'input':return NativeNode(self.frame,'group_input',self.index)
        if self.kind == 'address_query_inputs':return NativeNode(self.frame,'address_query',name=self.name)
        if self.kind == 'back_buttons':return NativeNode(self.frame,'back',index)
        if self.kind == 'property_inputs':return NativeNode(self.frame,'property_input',index)
        raise AssertionError(self.kind)

    def locator(self, selector):
        if self.kind == 'item':
            return NativeNode(self.frame, {'[data-field-type]':'type','input':'input',
                '[aria-label="Open settings"]':'gear'}[selector], self.index)
        if self.kind == 'tile_labels' and selector == '..':return NativeNode(self.frame,'source')
        if self.kind in ('address_header','address_header_parent') and selector == '..':
            return NativeNode(self.frame,'address_header_parent' if self.kind == 'address_header' else 'address_item',name=self.name)
        if self.kind == 'drawer' and selector == '.gui__builder-card:visible > .gui__builder-card--label':
            return NativeNode(self.frame,'tile_labels')
        raise AssertionError((self.kind,selector))

    def filter(self, *, has_text):
        if self.kind == 'address_headers':
            labels = [label for label in self.frame.address_queries() if has_text.fullmatch(label)]
            return NativeNode(self.frame,'address_header' if len(labels) == 1 else 'missing_address_header',name=labels[0] if labels else None)
        self.frame.requested_tile_pattern = has_text
        self.frame.requested_tile = next(label for label in field_placement.CAPTURED_FIELDS if has_text.fullmatch(label))
        return self

    def get_attribute(self, name):
        assert self.kind == 'type' and name == 'data-field-type'
        return self.frame.items[self.index]['type']

    def get_by_role(self, role, name=None, exact=True):
        if self.kind == 'address_item':
            assert role == 'textbox' and name == 'Please Input'
            return NativeNode(self.frame,'address_query_inputs',name=self.name)
        assert self.kind == 'drawer' and role == 'button' and name == 'Close'
        return NativeNode(self.frame,'close_drawer')

    def get_by_text(self, text, exact=True):
        assert self.kind == 'drawer' and text == 'Form Element'
        return NativeNode(self.frame,'drawer_title')

    def wait_for(self, **kwargs):
        if self.count() != 1:raise RuntimeError('native fixture control missing')

    def is_visible(self):return bool(self.count())
    def is_enabled(self):return True
    def is_checked(self):return self.frame.items[self.frame.selected].get('enabled',{}).get(self.name,True)
    def bounding_box(self):return {'x':0,'y':0,'width':200,'height':50}

    def input_value(self):
        if self.kind == 'title':return self.frame.name
        if self.kind == 'property_input':return self.frame.property_rows()[self.index][1]
        if self.kind == 'address_query':return self.frame.address_queries()[self.name]
        raise AssertionError(self.kind)

    def evaluate(self, script):
        if self.kind == 'address_query':return 'Query Key '
        assert self.kind == 'property_input'
        return self.frame.property_rows()[self.index][0]

    def click(self, **kwargs):
        f = self.frame
        if self.kind in ('input','group_input'):
            f.selected = self.index
            f.address_expanded = {}
        elif self.kind == 'gear':
            assert f.selected == self.index
            f.return_to_drawer = f.drawer
            f.drawer = False
        elif self.kind == 'back':
            assert self.index == 1
            f.selected = None
            f.drawer = f.return_to_drawer
        elif self.kind == 'address_header':f.address_expanded[self.name] = not f.address_expanded.get(self.name,False)
        elif self.kind == 'add':f.drawer = not f.drawer
        elif self.kind == 'close_drawer':f.drawer = False
        elif self.kind == 'save':
            f.saves += 1
            if not f.lose_save:f.persisted = deepcopy(f.items)
        elif self.kind == 'edit':pass
        else:raise AssertionError('unexpected native click ' + self.kind)

    def press(self, key, **kwargs):
        assert self.kind == 'input' and key == 'Escape'
        self.frame.escapes += 1

    def drag_to(self, target, **kwargs):
        assert self.kind == 'source' and target.kind == 'submit'
        f = self.frame
        f.drags += 1
        f.drop_arguments.append(kwargs)
        index = next(i for i,item in enumerate(f.items) if item['type'] == 'submit')
        if f.requested_tile == 'Address':
            f.items.insert(index, {'type':'group','input_count':6, 'queries':dict(field_placement._ADDRESS_QUERIES)})
        else:
            captured = {'Website':('text','website'), 'Full Name':('text','full_name'), 'Organization':('text','organization'),
                        'Date of birth':('date','date_of_birth'),
                        'City':('text','city'), 'State':('text','state'),
                        'Country':('select','country'), 'Postal Code':('text','postal_code')}
            field_type, key = captured[f.requested_tile]
            f.items.insert(index, {'type':field_type, 'key':f.dragged_key or key})
        f.selected = index
        f.return_to_drawer = True
        f.drawer = False


class NativeFrame:
    def __init__(self, items=None):
        self.items = deepcopy(items if items is not None else [
            {'type':'text','key':'first_name'}, {'type':'email','key':'email'},
            {'type':'terms_and_conditions'}, {'type':'submit'}, {'type':'h1'}])
        self.persisted = deepcopy(self.items)
        self.selected = None
        self.drawer = True
        self.return_to_drawer = False
        self.name = 'ZHC Placement Fixture'
        self.drags = self.saves = self.reopens = self.escapes = 0
        self.drop_arguments = []
        self.dragged_key = None
        self.lose_save = False
        self.tile_count = 1
        self.address_expanded = {}

    def address_queries(self):
        return self.items[self.selected].get('queries',dict(field_placement._ADDRESS_QUERIES))

    def property_rows(self):
        assert self.selected is not None
        item = self.items[self.selected]
        return [('Label','Renamed authored label'),('Placeholder','Renamed placeholder'),
                ('Short Label',''),('Query Key ',item['key']),('Field Width','100')]

    def locator(self, selector):
        if selector == field_placement.CANVAS_ITEMS:return NativeNode(self,'items')
        if selector == field_placement.SUBMIT_DROP:return NativeNode(self,'submit')
        if selector == '.n-collapse-item__header-main':return NativeNode(self,'address_headers')
        raise AssertionError('uncaptured native selector ' + selector)

    def get_by_role(self, role, name=None, exact=True):
        if role == 'dialog':return NativeNode(self,'drawer')
        if role == 'checkbox':return NativeNode(self,'address_enabled',name=name)
        if role == 'textbox':return NativeNode(self,'title' if name == 'Form Name' else 'property_inputs')
        if role == 'tab' and name == 'Edit':return NativeNode(self,'edit')
        if role == 'button':return NativeNode(self, {'Back':'back_buttons','Add Form Element':'add','Save':'save'}[name])
        raise AssertionError((role,name))

    def get_by_text(self, text, exact=True):
        assert text in ('General Settings','Address Fields')
        return NativeNode(self,'properties_title')


class NativePage:
    url = 'https://app.convertandflow.com/v2/location/FIXTURE/form-builder-v2/FORM'
    def __init__(self, frame):self.frame=frame
    def frame_locator(self, selector):
        assert selector == 'iframe[name="form-builder-app"]'
        return self.frame
    def reopen(self, *args):
        self.frame.reopens += 1
        self.frame.items = deepcopy(self.frame.persisted)
        self.frame.selected = None
        self.frame.drawer = True


class WebsitePlacementTests(unittest.TestCase):
    def configure(self, frame):
        page = NativePage(frame)
        with patch('assessments.reopen_editor', side_effect=page.reopen):
            return field_placement.configure(page, {'action':'native_field_placement','add_fields':['Website']})

    def test_one_real_drag_adds_before_submit_and_persists_query_identity(self):
        frame = NativeFrame()
        result = self.configure(frame)
        self.assertEqual(result['status'], 'BUILTIN_FIELDS_SAVED_AND_REOPENED')
        self.assertEqual(result['fields'], [{'field':'Website','query_keys':['website'],'placement':'added'}])
        self.assertFalse(result['submission_verified'])
        self.assertEqual((frame.drags,frame.saves,frame.reopens), (1,1,1))
        self.assertEqual(frame.items[-3], {'type':'text','key':'website'})
        self.assertEqual(frame.drop_arguments[0]['target_position'], {'x':100,'y':1})
        self.assertEqual(frame.requested_tile_pattern.pattern, r'^\s*Website\s*$')

    def test_existing_renamed_website_query_is_reused_without_another_drag_or_save(self):
        frame = NativeFrame()
        self.configure(frame)
        result = self.configure(frame)
        self.assertEqual(result['status'], 'BUILTIN_FIELDS_REUSED_AND_REOPENED')
        self.assertEqual((frame.drags,frame.saves,frame.reopens), (1,1,2))
        self.assertEqual(sum(item.get('key') == 'website' for item in frame.items), 1)

    def test_duplicate_or_wrong_type_query_refuses_before_a_drag(self):
        for items in ([{'type':'text','key':'website'},{'type':'text','key':'website'},{'type':'submit'}],
                      [{'type':'email','key':'website'},{'type':'submit'}]):
            frame = NativeFrame(items)
            with self.subTest(items=items), self.assertRaises(Stop):self.configure(frame)
            self.assertEqual((frame.drags,frame.saves), (0,0))

    def test_unknown_existing_field_type_never_proves_absence(self):
        frame = NativeFrame([{'type':'uncaptured','key':'some_field'},{'type':'submit'}])
        with self.assertRaisesRegex(Stop,'Uncaptured existing'):self.configure(frame)
        self.assertEqual((frame.drags,frame.saves), (0,0))

    def test_uncertain_drag_is_not_repeated_or_saved(self):
        frame = NativeFrame()
        frame.dragged_key = 'unexpected_native_query'
        with self.assertRaisesRegex(Stop,'query identity does not match'):self.configure(frame)
        self.assertEqual((frame.drags,frame.saves), (1,0))

    def test_lost_save_is_not_promoted_to_persisted_or_repeated(self):
        frame = NativeFrame()
        frame.lose_save = True
        with self.assertRaisesRegex(Stop,'did not persist'):self.configure(frame)
        self.assertEqual((frame.drags,frame.saves,frame.reopens), (1,1,1))

    def test_missing_or_ambiguous_tile_or_submit_boundary_stops_without_drag(self):
        for shape in ('duplicate-tile','no-submit'):
            frame = NativeFrame()
            if shape == 'duplicate-tile':frame.tile_count = 2
            else:
                frame.items = [item for item in frame.items if item['type'] != 'submit']
            with self.subTest(shape=shape), self.assertRaises(Stop):self.configure(frame)
            self.assertEqual((frame.drags,frame.saves), (0,0))

    def test_uncaptured_requested_builtin_stops_before_browser_reads(self):
        page = Mock()
        with patch.dict(field_placement.CAPTURED_FIELDS, clear=True):
            with self.assertRaisesRegex(Stop,'still requires field/query capture'):
                field_placement.configure(page, {'add_fields':['City']})
        self.assertEqual(page.mock_calls, [])


class AddressPlacementTests(unittest.TestCase):
    def configure(self, frame, fields=None):
        page = NativePage(frame)
        with patch('assessments.reopen_editor', side_effect=page.reopen):
            return field_placement.configure(page, {'add_fields':fields or ['Address']})

    def test_complete_address_group_places_once_and_reuses_all_five_child_queries(self):
        frame = NativeFrame()
        first = self.configure(frame)
        repeated = self.configure(frame)
        self.assertEqual(first['fields'], [{'field':'Address','query_keys':[
            'address','country','state','city','postal_code'],'placement':'added'}])
        self.assertEqual(repeated['fields'][0]['placement'], 'reused')
        self.assertEqual((frame.drags,frame.saves,frame.reopens), (1,1,2))
        groups = [item for item in frame.items if item['type'] == 'group']
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['queries'], field_placement._ADDRESS_QUERIES)

    def test_standalone_address_overlap_refuses_before_any_browser_call(self):
        for label in ('City','State','Country','Postal Code'):
            page = Mock()
            with self.subTest(label=label), self.assertRaises(field_placement.FieldPlacementError):
                field_placement.configure(page, {'add_fields':['Address',label]})
            self.assertEqual(page.mock_calls, [])

    def test_existing_standalone_child_query_does_not_authorize_duplicate_address_group(self):
        frame = NativeFrame([{'type':'text','key':'city'},{'type':'submit'}])
        with self.assertRaisesRegex(Stop,'overlapping address layout'):self.configure(frame)
        self.assertEqual((frame.drags,frame.saves), (0,0))

    def test_incomplete_or_remapped_group_is_not_reused_or_modified(self):
        changes = ({'input_count':5}, {'enabled':{'City':False}},
                   {'queries':{**field_placement._ADDRESS_QUERIES,'City':'foreign_query'}})
        for changed in changes:
            items = [{'type':'group','input_count':6,'queries':dict(field_placement._ADDRESS_QUERIES),**changed},
                     {'type':'submit'}]
            frame = NativeFrame(items)
            with self.subTest(changed=changed), self.assertRaises(Stop):self.configure(frame)
            self.assertEqual((frame.drags,frame.saves), (0,0))
            self.assertEqual(frame.items, items)

    def test_group_and_simple_fields_are_inventory_checked_after_each_single_drag(self):
        frame = NativeFrame()
        result = self.configure(frame, ['Website','Address'])
        self.assertEqual([field['field'] for field in result['fields']], ['Website','Address'])
        self.assertEqual((frame.drags,frame.saves,frame.reopens), (2,1,1))
        self.assertEqual([item['type'] for item in frame.items[-4:]], ['text','group','submit','h1'])


class AdditionalBuiltinPlacementTests(unittest.TestCase):
    def configure(self, frame, fields):
        page = NativePage(frame)
        with patch('assessments.reopen_editor', side_effect=page.reopen):
            return field_placement.configure(page, {'add_fields':fields})

    def test_captured_organization_and_dob_place_in_authored_order_and_reuse(self):
        frame = NativeFrame()
        fields = ['Organization','Date of birth']
        first = self.configure(frame, fields)
        repeated = self.configure(frame, fields)
        self.assertEqual(first['fields'], [
            {'field':'Organization','query_keys':['organization'],'placement':'added'},
            {'field':'Date of birth','query_keys':['date_of_birth'],'placement':'added'}])
        self.assertEqual([item['placement'] for item in repeated['fields']], ['reused','reused'])
        self.assertEqual((frame.drags,frame.saves,frame.reopens), (2,1,2))
        self.assertEqual(frame.items[-4:-2], [
            {'type':'text','key':'organization'}, {'type':'date','key':'date_of_birth'}])

    def test_full_name_uses_captured_query_without_removing_first_or_last_fields(self):
        frame = NativeFrame([{'type':'text','key':'first_name'}, {'type':'text','key':'last_name'},
                             {'type':'submit'}])
        first = self.configure(frame,['Full Name'])
        repeated = self.configure(frame,['Full Name'])
        self.assertEqual(first['fields'][0]['query_keys'], ['full_name'])
        self.assertEqual(repeated['fields'][0]['placement'], 'reused')
        self.assertEqual([item.get('key') for item in frame.items[:-1]], ['first_name','last_name','full_name'])
        self.assertEqual((frame.drags,frame.saves),(1,1))

    def test_captured_standalone_address_children_place_and_reuse_without_group(self):
        frame = NativeFrame()
        fields = ['City','State','Country','Postal Code']
        first = self.configure(frame,fields)
        repeated = self.configure(frame,fields)
        self.assertEqual([item['query_keys'] for item in first['fields']], [['city'],['state'],['country'],['postal_code']])
        self.assertEqual([item['placement'] for item in repeated['fields']], ['reused'] * 4)
        self.assertEqual((frame.drags,frame.saves,frame.reopens),(4,1,2))
        self.assertGreater(frame.escapes,0)
        self.assertFalse(any(item['type'] == 'group' for item in frame.items))

    def test_existing_group_children_do_not_become_duplicate_standalone_fields(self):
        for label in ('City','State','Country','Postal Code'):
            frame = NativeFrame([{'type':'group','input_count':6,
                'queries':dict(field_placement._ADDRESS_QUERIES)}, {'type':'submit'}])
            with self.subTest(label=label), self.assertRaisesRegex(Stop,'overlapping address layout'):
                self.configure(frame,[label])
            self.assertEqual((frame.drags,frame.saves),(0,0))

    def test_unknown_or_renamed_query_is_not_used_as_proof_a_builtin_is_absent(self):
        frame = NativeFrame([{'type':'text','key':'renamed_homepage'},{'type':'submit'}])
        with self.assertRaisesRegex(Stop,'Uncaptured existing native field query'):
            self.configure(frame,['Website'])
        self.assertEqual((frame.drags,frame.saves),(0,0))

    def test_dob_query_on_a_different_native_type_is_not_reused(self):
        frame = NativeFrame([{'type':'text','key':'date_of_birth'},{'type':'submit'}])
        with self.assertRaisesRegex(Stop,'different field type'):
            self.configure(frame,['Date of birth'])
        self.assertEqual((frame.drags,frame.saves),(0,0))

    def test_unknown_date_input_shape_does_not_trigger_duplicate_creation(self):
        frame = NativeFrame([{'type':'date','key':'date_of_birth','input_count':2},{'type':'submit'}])
        with self.assertRaisesRegex(Stop,'missing or ambiguous'):
            self.configure(frame,['Date of birth'])
        self.assertEqual((frame.drags,frame.saves),(0,0))


if __name__ == '__main__':
    unittest.main()
