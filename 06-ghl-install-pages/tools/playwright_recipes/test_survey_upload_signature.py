"""Captured survey uploads/signatures bind properties, owners and replay."""
from copy import deepcopy
from pathlib import Path
import tempfile
import importlib
import unittest
from unittest.mock import MagicMock,patch
import recipe_cli
import skill6_playwright as runner
native=importlib.import_module('playwright_recipes.survey_widget_families')
front=importlib.import_module('playwright_recipes.survey_creation')

def properties(kind):
    base={'label':'Agreement','placeholder':'Click to upload' if kind=='file_upload' else 'Sign here',
          'short_label':'','custom_field_name':'Original '+kind,
          'unique_key':'contact.original_'+kind,'required':False}
    if kind=='file_upload':base.update(file_access='public',file_types=['all'],multiple_files=False,max_files=None)
    return base

def inputs(kind):
    before=properties(kind);after={**before,'required':True,'short_label':'Required agreement'}
    if kind=='file_upload':after['file_types']=['pdf','doc']
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder-v2/SURVEY',
        'configuration':{'expected_survey_name':'Approved survey','expected_slide_count':2,
            'slide_labels':['P1 - Contact','P2 - Agreement'],
            'widget_fields':{'expected':[[],[{'kind':kind,'index':2,'properties':before}]],
                             'desired':[[],[{'kind':kind,'index':2,'properties':after}]]}}}

class SurveyUploadSignature(unittest.TestCase):
    def test_profiles_compile_through_parent_runner_and_canonical_keys_stay_immutable(self):
        for kind in ('file_upload','signature'):
            source=inputs(kind)
            job=runner.validate_job(recipe_cli.compile_recipe('surveys.configure',source),Path('.'))
            self.assertEqual(job['steps'][0]['action'],native.ACTION)
            profile=native.PROFILES[kind]
            self.assertEqual(profile['sidebar'],'#survey_custom_sidebar')
            self.assertEqual(profile['properties']['label'],'#fieldTitle input')
            self.assertNotIn('width',profile['properties'])
            changed=deepcopy(source)
            changed['configuration']['widget_fields']['desired'][1][0]['properties']['unique_key']='contact.other'
            with self.subTest(kind=kind),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('surveys.configure',changed)
    def test_upload_enabled_limit_compiles_and_saved_access_change_refuses(self):
        source=inputs('file_upload')
        source['configuration']['widget_fields']['desired'][1][0]['properties'].update(multiple_files=True,max_files=3)
        spec=recipe_cli.compile_recipe('surveys.configure',source)['steps'][0]
        self.assertEqual(native.validate(spec)['widget_fields']['desired'][1][0]['properties']['max_files'],3)
        source['configuration']['widget_fields']['desired'][1][0]['properties']['file_access']='private'
        with self.assertRaisesRegex(runner.Stop,'access is immutable'):recipe_cli.compile_recipe('surveys.configure',source)
    def test_configure_both_families_saves_once_preserves_other_slide_and_reopens(self):
        for kind in ('file_upload','signature'):
            spec=recipe_cli.compile_recipe('surveys.configure',inputs(kind))['steps'][0]
            plan=native.validate(spec);frame=MagicMock();save=frame.get_by_role.return_value
            save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
            state={'fields':deepcopy(plan['widget_fields']['expected'])}
            base=[[{'types':['TEXT']}],[{'types':['LARGE_TEXT']},{'types':[native.PROFILES[kind]['type']]}]]
            def snapshot(*a):
                value=deepcopy(base);value[1][1]['label']=state['fields'][1][0]['properties']['label'];return value
            def write(*a,**kw):
                self.assertEqual(kw['profile'],native.PROFILES[kind]);state['fields']=deepcopy(plan['widget_fields']['desired'])
            with patch.object(native,'_frame',return_value=frame),patch.object(native,'_inventory',side_effect=lambda *a:deepcopy(state['fields'])),patch.object(native.survey,'_owners',return_value=MagicMock()),patch.object(native.survey,'snapshot',side_effect=snapshot),patch.object(native.shared,'_write',side_effect=write) as writer,patch.object(native,'reopen_editor') as reopen:
                result=native.configure(MagicMock(),spec)
            self.assertEqual(result['widget_fields'],plan['widget_fields']['desired'])
            self.assertEqual(result['saved_snapshot'][0],base[0])
            writer.assert_called_once();save.click.assert_called_once();reopen.assert_called_once()
    def test_shared_upload_reader_uses_explicit_survey_sidebar(self):
        frame=MagicMock();panel=frame.locator.return_value
        panel.count.return_value=1;panel.is_visible.return_value=True
        toggle=panel.get_by_role.return_value
        toggle.count.return_value=1;toggle.is_visible.return_value=True;toggle.get_attribute.return_value='false'
        def controls(selector):
            node=MagicMock();node.count.return_value=1;node.is_visible.return_value=True
            if selector.startswith('label.n-radio-button'):node.is_checked.return_value='value="public"' in selector
            elif selector.startswith('#max-file-limit'):node.count.return_value=0
            else:node.get_attribute.return_value='true' if selector.startswith('#all[') else 'false'
            return node
        panel.locator.side_effect=controls
        panel.get_by_text.return_value.count.return_value=1;panel.get_by_text.return_value.is_visible.return_value=True
        self.assertEqual(native.shared._upload_options(frame,sidebar='#survey_custom_sidebar'),{'file_access':'public','file_types':['all'],'multiple_files':False,'max_files':None})
        frame.locator.assert_called_with('#survey_custom_sidebar')

    def test_creation_both_families_one_drag_save_and_fresh_child_replay(self):
        for kind in ('file_upload','signature'):
            value={'location_id':'LOC','location_name':'Fixture Account',
                'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder/main',
                'name':'Agreement survey','allow_creation':True,'slide_count':2,
                'question_batches':[{'kind':kind,'target_slide':1,'questions':[properties(kind)]}]}
            plan=front.validate_inputs(value)
            binding={'editor_url':value['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
                'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'slides':[{'canvas':[]},{'canvas':[]}]}
            target=front._text_plan(plan,binding,plan['question_batches'][0])
            frame=MagicMock();owner=MagicMock();wrappers=MagicMock();canvas=MagicMock();dialog=MagicMock();tile=MagicMock();handle=MagicMock();save=MagicMock()
            for node in (canvas,dialog,tile,handle,save,owner.get_by_role.return_value,
                         owner.get_by_text.return_value,dialog.get_by_text.return_value):
                node.count.return_value=1;node.is_visible.return_value=True
            save.is_enabled.return_value=True
            frame.get_by_role.side_effect=lambda role,**kw:dialog if role=='dialog' else save
            dialog.locator.return_value=tile;tile.locator.return_value=handle
            state={'created':False,'authored':False}
            wrappers.count.side_effect=lambda:int(state['created'])
            owner.locator.side_effect=lambda selector:wrappers if selector=='.form-field-wrapper' else canvas
            owners=MagicMock();owners.nth.return_value=owner
            handle.drag_to.side_effect=lambda *a,**kw:state.update(created=True)
            profile=native.PROFILES[kind];suffix='13785' if kind=='file_upload' else '2c4m'
            original={**deepcopy(profile['defaults']),'label':profile['tile']+' '+suffix,
                'custom_field_name':profile['tile']+' '+suffix,
                'unique_key':'contact.'+profile['key_prefix']+suffix}
            def snapshot(*a):
                return [[{'types':[profile['type']],'controls':[]}],[]] if state['created'] else [[],[]]
            with tempfile.TemporaryDirectory() as root,patch.object(native.survey,'_frame',return_value=frame),patch.object(native.survey,'_owners',return_value=owners),patch.object(native.survey,'_close_initial'),patch.object(native.survey,'snapshot',side_effect=snapshot),patch.object(native,'read_creation_question',side_effect=lambda *a:properties(kind) if state['authored'] else original),patch.object(native.shared,'_write',side_effect=lambda *a,**kw:state.update(authored=True)) as writer,patch.object(native,'reopen_editor') as reopen:
                done=native.configure_creation(MagicMock(),target,root)
                replay=native.configure_creation(MagicMock(),target,root)
            self.assertEqual(done,replay);handle.drag_to.assert_called_once();save.click.assert_called_once()
            writer.assert_called_once();self.assertEqual(reopen.call_count,2)
            dialog.locator.assert_called_once_with('[id="'+native.CREATION_TILES[kind]+'"]')
            completed=[{'kind':kind,'target_slide':1,'api_fields':[],'native_receipt':done}]
            inventory={'slide_labels':binding['slide_labels'],'slides':[
                {'canvas':[{'types':[profile['type']],'names':[]}],'radio_fields':[],'text_fields':[properties(kind)]},
                {'canvas':[],'radio_fields':[]}]}
            self.assertEqual(front._validate_inventory(inventory,plan,binding,completed),inventory)
            wrong=deepcopy(inventory);wrong['slides'][0]['canvas'][0]['types']=['TEXT']
            with self.assertRaises(runner.Stop):front._validate_inventory(wrong,plan,binding,completed)
            self.assertEqual(native.FILE_UPLOAD['input'],'label.custom-file-upload > svg')
            self.assertEqual(native.CREATION_TILES[kind],'File Upload1' if kind=='file_upload' else 'Signature5')
if __name__=='__main__':unittest.main()
