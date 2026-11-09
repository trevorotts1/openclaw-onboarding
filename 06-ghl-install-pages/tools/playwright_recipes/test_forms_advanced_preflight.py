"""Existing native field binding must be proven before another insertion."""
import unittest
from unittest.mock import Mock, patch

import forms_advanced
from skill6_playwright import Stop


class ObjectBindingPreflightTests(unittest.TestCase):
    def fixture(self):
        page, frame, scope, dialog, search = (Mock() for _ in range(5))
        page.url = 'https://app.convertandflow.com/v2/location/L/form-builder-v2/F'
        title = frame.get_by_role.return_value
        title.count.return_value = 1
        title.input_value.return_value = 'Existing form'
        frame.locator.return_value.count.return_value = 0
        scope.count.return_value = 1
        dialog.get_by_text.return_value.count.return_value = 0
        existing = {'id':'existing','field_key':'contact.existing','data_type':'RADIO',
                    'name':'Existing question','options':['Yes','No']}
        pending = {'id':'pending','field_key':'contact.pending','data_type':'RADIO',
                   'name':'New question','options':['A','B']}
        rows = {}
        for field, disabled in ((existing, True), (pending, False)):
            row, tile, checkbox = Mock(), Mock(), Mock()
            tile.get_attribute.return_value = 'true' if disabled else 'false'
            checkbox.get_attribute.return_value = 'false'
            rows[field['id']] = row, tile, checkbox
        payload = {'start_url':page.url, 'object_fields':[existing,pending]}
        return page, frame, scope, dialog, search, existing, pending, rows, {'payload':payload}

    def run_fixture(self, fixture, reader, click):
        page, frame, scope, dialog, search, existing, pending, rows, plan = fixture
        with patch.object(forms_advanced,'validate_object_fields',return_value=plan), \
                patch.object(forms_advanced,'_canvas_identity',return_value=[]), \
                patch.object(forms_advanced,'_object_dialog',return_value=(dialog,search)), \
                patch.object(forms_advanced,'_object_row',side_effect=lambda d,s,f:rows[f['id']]), \
                patch.object(forms_advanced,'_object_wrapper'), \
                patch.object(forms_advanced,'_close_object_drawer'), \
                patch.object(forms_advanced,'fill'), \
                patch.object(forms_advanced,'_read_object_binding',side_effect=reader), \
                patch.object(forms_advanced,'click',side_effect=click):
            forms_advanced.configure_object_fields(page,plan,frame=frame,canvas_scope=scope)

    def test_wrong_existing_binding_stops_before_pending_checkbox_selection(self):
        fixture = self.fixture()
        selections = []
        def refuse(*args):
            raise Stop('Existing native Query Key is wrong')
        def select(control):
            selections.append(control)
            raise AssertionError('Pending field was selected before existing binding validation')
        with self.assertRaisesRegex(Stop,'Query Key is wrong'):
            self.run_fixture(fixture,refuse,select)
        self.assertEqual(selections, [])
        self.assertFalse(fixture[7]['pending'][2].click.called)

    def test_existing_binding_is_read_before_first_pending_selection(self):
        fixture = self.fixture()
        events = []
        def read(frame, scope, field):
            events.append(('binding',field['id']))
            return 'actual_native_query'
        def select(control):
            self.assertIs(control,fixture[7]['pending'][2])
            events.append(('select','pending'))
            raise Stop('Insertion boundary reached')
        with self.assertRaisesRegex(Stop,'Insertion boundary reached'):
            self.run_fixture(fixture,read,select)
        self.assertEqual(events,[('binding','existing'),('select','pending')])


if __name__ == '__main__':
    unittest.main()
