"""Real location field lists may contain unrelated native widget families."""
from copy import deepcopy
import time
import unittest

import forms_advanced as native
from skill6_playwright import Stop


def payload():
    field = {'id':'radio_field', 'name':'Approved service',
             'field_key':'contact.zhc_service', 'data_type':'RADIO',
             'options':['Coaching', 'Consulting']}
    return {'payload':{
        'location_id':'LOCATION', 'location_name':'Approved location',
        'start_url':'https://app.example.com/v2/location/LOCATION/form-builder-v2/FORM',
        'object_fields':[deepcopy(field)],
        'field_dependencies':{'status':'VERIFIED', 'provider':'public_api',
            'location_id':'LOCATION', 'observed_at':time.time(),
            'operation':'custom_fields.list', 'http_status':200,
            'fields':[field]}}}


class MixedInventoryTests(unittest.TestCase):
    def test_unrelated_field_families_do_not_require_radio_capture(self):
        step = payload()
        step['payload']['field_dependencies']['fields'] += [
            {'id':'text_field', 'field_key':'contact.zhc_notes', 'data_type':'TEXT'},
            {'id':'date_field', 'field_key':'contact.zhc_date', 'data_type':'DATE',
             'options':[]},
        ]
        self.assertEqual(native.validate_object_fields(step), step)

    def test_selected_field_still_requires_complete_captured_definition(self):
        for key, value in [('options',['Changed']), ('data_type','TEXT'),
                           ('name','Other question'), ('field_key','contact.foreign')]:
            with self.subTest(key=key):
                step = payload()
                step['payload']['field_dependencies']['fields'][0][key] = value
                with self.assertRaises(Stop):
                    native.validate_object_fields(step)

    def test_duplicate_identity_or_key_anywhere_in_inventory_is_refused(self):
        for other in [
            {'id':'radio_field', 'field_key':'contact.other', 'data_type':'TEXT'},
            {'id':'other', 'field_key':'contact.zhc_service', 'data_type':'TEXT'},
        ]:
            step = payload()
            step['payload']['field_dependencies']['fields'].append(other)
            with self.subTest(other=other), self.assertRaisesRegex(Stop,'duplicated'):
                native.validate_object_fields(step,require_fresh=True)

    def test_malformed_unrelated_identity_is_not_ignored(self):
        for other in [None, {}, {'id':[], 'field_key':'contact.other'},
                      {'id':'other', 'field_key':None},
                      {'id':'other', 'field_key':'company.other'}]:
            step = payload()
            step['payload']['field_dependencies']['fields'].append(other)
            with self.subTest(other=other), self.assertRaises(Stop):
                native.validate_object_fields(step)

    def test_missing_requested_field_is_not_proven_by_neighbor(self):
        step = payload()
        step['payload']['field_dependencies']['fields'] = [
            {'id':'other', 'field_key':'contact.other', 'data_type':'RADIO'}]
        with self.assertRaisesRegex(Stop,'differ from'):
            native.validate_object_fields(step)

    def test_mixed_inventory_preserves_same_location_freshness_requirement(self):
        for change in [{'location_id':'FOREIGN'}, {'observed_at':0},
                       {'http_status':True}, {'status':'UNVERIFIED'}]:
            step = payload()
            step['payload']['field_dependencies'].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(Stop,'fresh verified'):
                native.validate_object_fields(step,require_fresh=True)

    def test_survey_uses_same_selected_definition_contract(self):
        step = payload()
        step['payload']['start_url'] = step['payload']['start_url'].replace(
            '/form-builder-v2/', '/survey-builder-v2/')
        step['payload']['field_dependencies']['fields'].append(
            {'id':'other', 'field_key':'contact.other', 'data_type':'TEXT'})
        self.assertEqual(native.validate_object_fields(step,kind='survey'),step)


if __name__ == '__main__':
    unittest.main()
