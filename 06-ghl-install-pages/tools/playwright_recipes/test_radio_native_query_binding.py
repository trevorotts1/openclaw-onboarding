"""Opaque API IDs bind Radio fields; native Query Keys are preserved metadata."""
from copy import deepcopy
import unittest
from unittest.mock import Mock,patch

import forms_advanced as native
from test_object_field_dependencies import payload
from skill6_playwright import Stop


class NativeQueryReaderTests(unittest.TestCase):
    def test_actual_native_query_is_read_without_deriving_it_from_api_key(self):
        frame,item,label,gear,inputs,query=[Mock() for _ in range(6)]
        field=payload()['payload']['object_fields'][0]
        item.locator.return_value=gear;gear.count.return_value=1
        frame.get_by_role.return_value=inputs;inputs.count.return_value=1
        inputs.nth.return_value=query;query.evaluate.return_value='Query Key '
        query.input_value.return_value='legacy_service:_which_offer?'
        with patch.object(native,'_object_wrapper',return_value=(item,label)) as identity, \
             patch.object(native,'click'),patch.object(native,'_close_properties'):
            actual=native._read_object_binding(frame,Mock(),field)
        self.assertEqual(actual,'legacy_service:_which_offer?')
        self.assertNotEqual(actual,field['field_key'].split('.',1)[1])
        self.assertEqual(identity.call_args.args[2],field)

    def test_blank_native_query_is_not_accepted_as_a_binding(self):
        frame,item,label,gear,inputs,query=[Mock() for _ in range(6)]
        item.locator.return_value=gear;gear.count.return_value=1
        frame.get_by_role.return_value=inputs;inputs.count.return_value=1
        inputs.nth.return_value=query;query.evaluate.return_value='Query Key '
        query.input_value.return_value=''
        with patch.object(native,'_object_wrapper',return_value=(item,label)), \
             patch.object(native,'click'),self.assertRaises(Stop):
            native._read_object_binding(frame,Mock(),payload()['payload']['object_fields'][0])


class NativeQueryPreservationTests(unittest.TestCase):
    def exercise(self,queries):
        step=payload();field=step['payload']['object_fields'][0]
        page,frame,scope,title,dialog,search,tile,checkbox=[Mock() for _ in range(8)]
        page.url=step['payload']['start_url']
        title.count.return_value=1;title.input_value.return_value='Existing form'
        frame.get_by_role.return_value=title;scope.count.return_value=1
        dialog.get_by_text.return_value.count.return_value=0
        tile.get_attribute.return_value='true'
        before=[{'types':['RADIO'],'names':[['INPUT','radio',field['id']]]}]
        reopened=[]
        def reopen():reopened.append(True);return frame,scope
        with patch.object(native,'_object_dialog',return_value=(dialog,search)), \
             patch.object(native,'_object_row',return_value=(Mock(),tile,checkbox)), \
             patch.object(native,'_object_wrapper'),patch.object(native,'_close_object_drawer'), \
             patch.object(native,'_canvas_identity',side_effect=lambda _:deepcopy(before)), \
             patch.object(native,'_read_object_binding',side_effect=queries), \
             patch.object(native,'fill'),patch.object(native,'click'):
            try:result=native.configure_object_fields(page,step,frame=frame,canvas_scope=scope,reopen=reopen)
            except Stop as error:result=error
        return result,reopened

    def test_existing_radio_with_non_derived_query_reuses_exact_id_and_preserves_query(self):
        result,reopened=self.exercise(['legacy_query?', 'legacy_query?', 'legacy_query?'])
        self.assertEqual(result['fields'][0]['id'],'radio_field')
        self.assertEqual(result['fields'][0]['placement'],'reused')
        self.assertEqual(result['independent_readback'],'VERIFIED')
        self.assertEqual(reopened,[True])

    def test_query_drift_after_preflight_stops_before_reopen(self):
        result,reopened=self.exercise(['legacy_query?','Changed_query?'])
        self.assertIsInstance(result,Stop);self.assertIn('changed during placement',str(result))
        self.assertEqual(reopened,[])

    def test_saved_native_query_drift_does_not_return_verified(self):
        result,reopened=self.exercise(['legacy_query?','legacy_query?','Changed_saved_query?'])
        self.assertIsInstance(result,Stop);self.assertIn('did not persist',str(result))
        self.assertEqual(reopened,[True])


if __name__=='__main__':unittest.main()
