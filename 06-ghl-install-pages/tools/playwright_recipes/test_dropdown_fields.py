"""API IDs and native dropdown queries are separate independently bound identities."""
from copy import deepcopy
import time
import unittest
from unittest.mock import Mock,MagicMock,patch

import dropdown_fields as native
from skill6_playwright import Stop


OPTIONS=["Men's Medium (M)","Men's Large (L)","Men's X-Large (XL)","Men's XX-Large (XXL)",
         "Women's Medium (M)","Women's Small (S)","Women's Large (L)",
         "Women's X-Large (XL)","Women's XX-Large (XXL)"]


def plan():
    api={'id':'API_FIELD','name':'Select Your T-shirt Size','field_key':'contact.select_your_tshirt_size',
         'data_type':'SINGLE_OPTIONS','options':deepcopy(OPTIONS)}
    field={**deepcopy(api),'native_query_key':'select_your_t-shirt_size','expected_label':api['name']}
    return {'payload':{'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM',
        'dropdown_fields':[field],
        'field_dependencies':{'status':'VERIFIED','provider':'public_api','location_id':'LOC',
            'operation':'custom_fields.list','http_status':200,'observed_at':time.time(),
            'fields':[api]}}}


class DefinitionTests(unittest.TestCase):
    def test_actual_native_query_can_differ_from_api_key_without_fabricating_canvas_id(self):
        data=plan()
        self.assertEqual(native.validate(data),data)
        self.assertNotEqual(data['payload']['dropdown_fields'][0]['native_query_key'],
                            data['payload']['dropdown_fields'][0]['field_key'].split('.',1)[1])
        self.assertEqual(set(data['payload']['field_dependencies']['fields'][0]),native.API_KEYS)

    def test_native_query_label_and_ordered_options_are_hash_bound(self):
        data=plan();original=native.configuration_hash(data)
        for key,value in [('native_query_key','foreign_native_key'),('expected_label','Different label')]:
            changed=deepcopy(data);changed['payload']['dropdown_fields'][0][key]=value
            self.assertNotEqual(native.configuration_hash(changed),original)
        changed=deepcopy(data);changed['payload']['dropdown_fields'][0]['options'].reverse()
        with self.assertRaisesRegex(Stop,'differs'):native.configuration_hash(changed)

    def test_foreign_stale_or_unproven_dependency_cannot_enter_native_execution(self):
        for change in ({'location_id':'FOREIGN'},{'status':'UNVERIFIED'},
                       {'observed_at':0},{'http_status':True}):
            data=plan();data['payload']['field_dependencies'].update(change);page=Mock()
            with self.subTest(change=change),self.assertRaises(Stop):native.configure(page,data)
            self.assertFalse(page.mock_calls)

    def test_completed_structural_hash_remains_valid_as_receipt_ages(self):
        data=plan();digest=native.configuration_hash(data)
        data['payload']['field_dependencies']['observed_at']=0
        self.assertEqual(native.configuration_hash(data),digest)
        with self.assertRaises(Stop):native.validate(data,require_fresh=True)

    def test_api_type_id_key_and_options_must_match_selected_definition(self):
        for key,value in [('id','OTHER'),('field_key','contact.other'),('data_type','RADIO'),
                          ('name','Different question'),('options',['Different'])]:
            data=plan();data['payload']['field_dependencies']['fields'][0][key]=value
            with self.subTest(key=key),self.assertRaises(Stop):native.validate(data)

    def test_mixed_api_inventory_does_not_authorize_unrelated_type_placement(self):
        data=plan();data['payload']['field_dependencies']['fields'].append(
            {'id':'OTHER','field_key':'contact.other','data_type':'TEXT'})
        self.assertEqual(native.validate(data),data)
        data['payload']['dropdown_fields'][0]['data_type']='TEXT'
        with self.assertRaises(Stop):native.validate(data)

    def test_duplicate_api_or_native_identities_and_ignored_extra_properties_are_refused(self):
        for key,value in [('native_query_key',None),('native_query_key','space key'),('expected_label','')]:
            data=plan();data['payload']['dropdown_fields'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(Stop):native.validate(data)
        data=plan();data['payload']['dropdown_fields'].append(deepcopy(data['payload']['dropdown_fields'][0]))
        with self.assertRaises(Stop):native.validate(data)
        data=plan();data['payload']['dropdown_fields'][0]['canvas_api_id']='invented'
        with self.assertRaises(Stop):native.validate(data)


class PreservationTests(unittest.TestCase):
    def test_added_dropdown_has_no_api_canvas_name_and_can_be_removed_by_observed_index(self):
        field=plan()['payload']['dropdown_fields'][0]
        old={'native_query_key':'old','expected_label':'Old dropdown','options':['A','B']}
        before=[{'types':['text'],'names':[['INPUT','text','first_name']]},
                {'types':['SINGLE_OPTIONS'],'names':[]},{'types':['submit'],'names':[]}]
        after=[before[0],{'types':['SINGLE_OPTIONS'],'names':[]},before[1],before[2]]
        native._preserved(before,[(1,old)],after,[(1,native._expected(field)),(2,old)],[field])

    def test_native_identity_or_ordered_options_mismatch_is_not_adopted_as_requested_field(self):
        field=plan()['payload']['dropdown_fields'][0]
        for key,value in [('native_query_key','other'),('expected_label','Other'),('options',list(reversed(OPTIONS)))]:
            observed=native._expected(field);observed[key]=value
            with self.subTest(key=key),self.assertRaises(Stop):
                native._preserved([],[],[{'types':['SINGLE_OPTIONS'],'names':[]}],[(0,observed)],[field])

    def test_unrequested_widget_identity_or_dropdown_options_drift_is_refused(self):
        field=plan()['payload']['dropdown_fields'][0]
        old={'native_query_key':'old','expected_label':'Old','options':['A','B']}
        before=[{'types':['RADIO'],'names':[['INPUT','radio','PRESERVED_API_ID']]},
                {'types':['SINGLE_OPTIONS'],'names':[]}]
        after=[*deepcopy(before),{'types':['SINGLE_OPTIONS'],'names':[]}]
        old_changed={**old,'options':['Changed']}
        with self.assertRaisesRegex(Stop,'unrelated'):
            native._preserved(before,[(1,old)],after,[(1,old_changed),(2,native._expected(field))],[field])
        after[0]['names'][0][2]='FOREIGN_ID'
        with self.assertRaisesRegex(Stop,'unrelated'):
            native._preserved(before,[(1,old)],after,[(1,old),(2,native._expected(field))],[field])


class ExistingBindingTests(unittest.TestCase):
    def exercise(self,*,disabled=True,corrupt_reopen=False,proven=False):
        data=plan();field=data['payload']['dropdown_fields'][0]
        page,frame,title,scope,dialog,search,tile,checkbox=[Mock() for _ in range(8)]
        page.url=data['payload']['start_url']
        title.count.return_value=1;title.input_value.return_value='Existing form'
        scope.count.return_value=1
        frame.get_by_role.side_effect=lambda role,**kw:title if role=='textbox' else Mock()
        frame.locator.return_value=scope
        dialog.get_by_text.return_value.count.return_value=0
        tile.get_attribute.return_value='true' if disabled else 'false'
        checkbox.get_attribute.return_value='false'
        records=[(0,native._expected(field))]
        canvas=[{'types':['SINGLE_OPTIONS'],'names':[]}]
        reopened=False;clicks=[]
        original_proof=native._prove_existing_owner
        def inventory(*_):
            result=deepcopy(records)
            if reopened and corrupt_reopen:result[0][1]['options']=['Lost saved definition']
            return result
        def reopen(*_):
            nonlocal reopened
            reopened=True
        with patch.object(native,'form_builder',return_value=frame),patch.object(native,'assert_tenant'), \
             patch.object(native,'_close_object_drawer'),patch.object(native,'_inventory',side_effect=inventory), \
             patch.object(native,'_stable_canvas',return_value=canvas), \
             patch.object(native,'_object_dialog',return_value=(dialog,search)), \
             patch.object(native,'_object_row',return_value=(Mock(),tile,checkbox)), \
             patch.object(native,'fill'),patch.object(native,'click',side_effect=clicks.append), \
             patch.object(native,'reopen_editor',side_effect=reopen), \
             patch.object(native,'_prove_existing_owner',side_effect=lambda *args: (
                 {'unique_key':field['field_key'],'custom_field_name':field['name'],
                  'query_key':field['native_query_key'],'label':field['expected_label'],
                  'options':[{'label':option,'value':None} for option in field['options']]}
                 if proven else original_proof(*args))):
            try:result=native.configure(page,data)
            except Stop as error:result=error
        return result,checkbox,clicks

    def test_exact_canonical_join_reuses_existing_owner_without_insertion_or_save(self):
        result,checkbox,clicks=self.exercise(proven=True)
        self.assertEqual(result['fields'][0]['placement'],'reused')
        native.validate_receipt(result,plan())
        checkbox.click.assert_not_called()
        self.assertEqual(len(clicks),1)

    def test_disabled_api_row_cannot_adopt_a_native_widget_without_api_id_provenance(self):
        result,checkbox,_=self.exercise()
        self.assertIsInstance(result,Stop)
        self.assertIn('DROPDOWN_REUSE_IDENTITY_UNVERIFIED',str(result))
        checkbox.click.assert_not_called()

    def test_enabled_api_row_does_not_adopt_a_conflicting_existing_native_query(self):
        result,checkbox,_=self.exercise(disabled=False)
        self.assertIsInstance(result,Stop)
        self.assertIn('conflicts',str(result));checkbox.click.assert_not_called()

    def test_even_matching_caption_and_options_cannot_upgrade_unknown_legacy_reuse(self):
        result,_,_=self.exercise(corrupt_reopen=True)
        self.assertIsInstance(result,Stop)
        self.assertIn('REUSE_IDENTITY_UNVERIFIED',str(result))


class PositiveLegacyAdoptionTests(unittest.TestCase):
    def test_api_picker_identity_joins_only_exact_saved_advanced_native_owner(self):
        from playwright_recipes import form_widget_families as widgets
        field=plan()['payload']['dropdown_fields'][0]
        scope=MagicMock();scope.locator.return_value.count.return_value=1
        record={'unique_key':field['field_key'],'custom_field_name':field['name'],
                'query_key':field['native_query_key'],'label':field['expected_label'],
                'options':[{'label':option,'value':None} for option in field['options']]}
        inventory=[(0,native._expected(field))]
        with patch.object(widgets,'_read',return_value=record) as read:
            self.assertEqual(native._prove_existing_owner(MagicMock(),scope,field,inventory),record)
        read.assert_called_once()
        for key,value in [('unique_key','contact.foreign'),('custom_field_name','Foreign'),
                          ('query_key','foreign'),('label','Foreign'),('options',[])]:
            with self.subTest(key=key),patch.object(widgets,'_read',return_value={**record,key:value}),self.assertRaises(Stop):
                native._prove_existing_owner(MagicMock(),scope,field,inventory)
        with patch.object(widgets,'_read') as read,self.assertRaises(Stop):
            native._prove_existing_owner(MagicMock(),scope,field,inventory+inventory)
        read.assert_not_called()

    def test_positive_reuse_keeps_exact_receipt_identity_and_never_claims_new_insertion(self):
        data=plan();field=data['payload']['dropdown_fields'][0]
        receipt={'status':'DROPDOWN_FIELDS_SAVED_AND_REOPENED','editor_url':data['payload']['start_url'],
            'fields':[{**{key:field[key] for key in ('id','field_key','data_type','native_query_key')},'placement':'reused',
                'reuse_proof':{'unique_key':field['field_key'],'custom_field_name':field['name'],
                    'query_key':field['native_query_key'],'label':field['expected_label'],
                    'options':[{'label':option} for option in field['options']]}}],
            'configuration_sha256':native.configuration_hash(data),'independent_readback':'VERIFIED',
            'behavior_verified':False,'submission_verified':False}
        self.assertEqual(native.validate_receipt(receipt,data)['fields'][0]['placement'],'reused')
        changed=deepcopy(receipt);changed['fields'][0]['id']='FOREIGN'
        with self.assertRaises(Stop):native.validate_receipt(changed,data)


    def test_completed_legacy_replay_reopens_and_checks_join_without_add_or_save(self):
        data=plan();field=data['payload']['dropdown_fields'][0]
        receipt={'status':'DROPDOWN_FIELDS_SAVED_AND_REOPENED','editor_url':data['payload']['start_url'],
            'fields':[{**{key:field[key] for key in ('id','field_key','data_type','native_query_key')},'placement':'reused',
                'reuse_proof':{'unique_key':field['field_key'],'custom_field_name':field['name'],
                    'query_key':field['native_query_key'],'label':field['expected_label'],
                    'options':[{'label':option} for option in field['options']]}}],
            'configuration_sha256':native.configuration_hash(data),'independent_readback':'VERIFIED',
            'behavior_verified':False,'submission_verified':False}
        page=MagicMock();page.url=data['payload']['start_url'];frame=MagicMock()
        frame.get_by_role.return_value.count.return_value=1
        frame.get_by_role.return_value.input_value.return_value='Existing form'
        scope=MagicMock();scope.count.return_value=1;frame.locator.return_value=scope
        tile=MagicMock();tile.get_attribute.return_value='true'
        with patch.object(native,'assert_tenant'),patch.object(native,'form_builder',return_value=frame), \
                patch.object(native,'reopen_editor') as reopen,patch.object(native,'_close_object_drawer'), \
                patch.object(native,'_inventory',return_value=[(0,native._expected(field))]), \
                patch.object(native,'_stable_canvas',return_value=[{'types':['SINGLE_OPTIONS'],'names':[]}]), \
                patch.object(native,'_object_dialog',return_value=(MagicMock(),MagicMock())), \
                patch.object(native,'_object_row',return_value=(MagicMock(),tile,MagicMock())), \
                patch.object(native,'_prove_existing_owner',return_value={'unique_key':field['field_key'],
                    'custom_field_name':field['name'],'query_key':field['native_query_key'],
                    'label':field['expected_label'],'options':[{'label':option,'value':None} for option in field['options']]}) as prove, \
                patch.object(native,'fill'),patch.object(native,'click') as clicked:
            self.assertEqual(native.verify_completed(page,data,receipt),receipt)
            reopen.assert_called_once();prove.assert_called_once()
            self.assertEqual(clicked.call_count,1)
            prove.side_effect=Stop('canonical owner drifted')
            with self.assertRaisesRegex(Stop,'canonical owner drifted'):native.verify_completed(page,data,receipt)


class LegacyReplayRunnerBoundaryTests(unittest.TestCase):
    def test_completed_runner_calls_current_owner_verifier_and_propagates_drift_without_write(self):
        import importlib
        import tempfile
        from pathlib import Path
        import recipe_cli
        import skill6_playwright as runner
        leaf=importlib.import_module('playwright_recipes.dropdown_fields')
        source=plan()['payload']
        job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',source),Path('.'))
        step=job['steps'][0];field=step['payload']['dropdown_fields'][0]
        receipt={'status':'DROPDOWN_FIELDS_SAVED_AND_REOPENED','editor_url':source['start_url'],
            'fields':[{**{key:field[key] for key in ('id','field_key','data_type','native_query_key')},
                       'placement':'reused','reuse_proof':{
                           'unique_key':field['field_key'],'custom_field_name':field['name'],
                           'query_key':field['native_query_key'],'label':field['expected_label'],
                           'options':[{'label':option} for option in field['options']]}}],
            'configuration_sha256':leaf.configuration_hash(step),'independent_readback':'VERIFIED',
            'behavior_verified':False,'submission_verified':False}
        page=MagicMock();page.url=source['start_url']
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(runner,'native_dropdown_fields',return_value=receipt) as writer:
            runner.run_on_page(page,job,root)
            journal=Path(root,'state.json');before=journal.read_bytes()
            with patch.object(leaf,'verify_completed',return_value=receipt) as verify:
                replay=runner.run_on_page(page,job,root)
                self.assertTrue(replay['replayed'])
                verify.assert_called_once_with(page,step,replay['results'][0]['result'])
                verify.side_effect=Stop('Current canonical Dropdown owner drifted')
                with self.assertRaisesRegex(Stop,'canonical Dropdown owner drifted'):
                    runner.run_on_page(page,job,root)
            self.assertEqual(journal.read_bytes(),before)
            writer.assert_called_once()


if __name__=='__main__':unittest.main()
