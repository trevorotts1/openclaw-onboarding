"""Captured survey dropdown profiles share option and owned-creation machinery."""
from copy import deepcopy
from pathlib import Path
import importlib
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock,patch

import recipe_cli
import skill6_playwright as runner
from test_form_single_dropdown_native import Panel as FormPanel
from test_form_widget_dropdown_snapshot import JS

front=importlib.import_module('playwright_recipes.survey_creation')
native=importlib.import_module('playwright_recipes.survey_widget_families')
options=importlib.import_module('playwright_recipes.form_single_dropdown_native')


def question(kind):
    profile=native.PROFILES[kind]
    value={**deepcopy(profile['defaults']),'label':'Choose '+kind,'short_label':'Choice',
           'custom_field_name':'Approved '+kind,'unique_key':'contact.approved_'+kind,'required':True,
           'options':[{'label':'First','value':None},{'label':'Second','value':None}]}
    if 'query_key' in profile['properties']:value['query_key']='approved_'+kind
    return value


def inputs(kind='single_dropdown'):
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder/main',
        'name':'Preference survey','allow_creation':True,'slide_count':2,
        'question_batches':[{'kind':kind,'target_slide':1,'questions':[question(kind)]}]}


def configuration(kind):
    from test_survey_widget_families import inputs as base
    source=base()
    for mode in ('expected','desired'):
        source['configuration']['widget_fields'][mode]=[[],[{'kind':kind,'index':1,'properties':question(kind)}]]
    source['configuration']['widget_fields']['desired'][1][0]['properties']['label']='Updated label'
    return source


def snapshot(kind):return [[{'types':[native.PROFILES[kind]['type']],
                            'controls':[['INPUT',None,None,native.PROFILES[kind]['defaults']['placeholder'],'']]}],[]]


class SurveyPanel(FormPanel):
    def locator(self,selector):
        if selector=='#survey_custom_sidebar':return self
        if selector=='#form_custom_sidebar':raise AssertionError('Survey writer selected form sidebar')
        return super().locator(selector)


class SurveyDropdowns(unittest.TestCase):
    def test_both_dropdowns_create_and_configure_with_exact_survey_profiles(self):
        for kind,tile in [('single_dropdown','Single Dropdown0'),('multi_dropdown','Multi Dropdown1')]:
            with self.subTest(kind=kind):
                job=runner.validate_job(recipe_cli.compile_recipe('surveys.create',inputs(kind)),Path('.'))
                front.validate_runtime(job,None)
                self.assertEqual(native.CREATION_TILES[kind],tile)
                self.assertEqual(native.PROFILES[kind]['properties']['label'],'#fieldTitle input')
                self.assertNotIn('width',native.PROFILES[kind]['properties'])
                self.assertNotIn('hidden',native.PROFILES[kind]['flags'])
                spec=recipe_cli.compile_recipe('surveys.configure',configuration(kind))['steps'][0]
                self.assertEqual(spec['action'],native.ACTION)
                changed=configuration(kind);changed['configuration']['widget_fields']['desired'][1][0]['properties']['unique_key']='contact.foreign'
                with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('surveys.configure',changed)
        self.assertNotIn('query_key',question('multi_dropdown'))
        for extra in ({'hidden':False},{'width':80},{'query_key':'invented_local_key'}):
            bad=inputs('multi_dropdown');bad['question_batches'][0]['questions'][0].update(extra)
            with self.assertRaises(runner.Stop):front.validate_inputs(bad)
        duplicate=inputs();duplicate['question_batches'].append({'kind':'multi_dropdown','target_slide':2,'questions':[question('multi_dropdown')]})
        duplicate['question_batches'][1]['questions'][0]['unique_key']=question('single_dropdown')['unique_key']
        with self.assertRaises(runner.Stop):front.validate_inputs(duplicate)

    def test_shared_option_writer_uses_survey_sidebar_for_complete_choice_lifecycle(self):
        before={'calculations':False,'options':[{'label':'Option '+str(i),'value':None} for i in (1,2,3)]}
        desired={'calculations':True,'options':[{'label':'One','value':'10'},{'label':'Two','value':'20'}]}
        panel=SurveyPanel(before)
        with patch.object(options,'click',side_effect=panel.click),patch.object(options,'fill',side_effect=panel.fill):
            options.write_options(panel,before,desired,sidebar='#survey_custom_sidebar')
            self.assertEqual(options.read_options(panel,sidebar='#survey_custom_sidebar'),desired)
        self.assertEqual([e for e in panel.events if e[0] in ('switch','remove','add')],[('switch',None),('remove',2)])

    def test_both_creations_drag_full_tile_from_captured_icon_save_once_and_replay(self):
        for kind in ('single_dropdown','multi_dropdown'):
            with self.subTest(kind=kind):
                plan=front.validate_inputs(inputs(kind));binding={'editor_url':plan['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
                    'slide_labels':['P1 - Slide 1','P2 - Slide 2']}
                target=front._text_plan(plan,binding,plan['question_batches'][0]);state={'created':False,'authored':False}
                frame=MagicMock();owner=MagicMock();wrappers=MagicMock();canvas=MagicMock();dialog=MagicMock();tile=MagicMock();icon=MagicMock();save=MagicMock()
                for node in (canvas,dialog,tile,icon,save,owner.get_by_role.return_value,owner.get_by_text.return_value,dialog.get_by_text.return_value):
                    node.count.return_value=1;node.is_visible.return_value=True
                save.is_enabled.return_value=True
                tile.bounding_box.return_value={'x':100,'y':100,'width':160,'height':100}
                icon.bounding_box.return_value={'x':120,'y':110,'width':32,'height':32}
                frame.get_by_role.side_effect=lambda role,**kw:dialog if role=='dialog' else save
                dialog.locator.return_value=tile;tile.locator.return_value=icon
                wrappers.count.side_effect=lambda:int(state['created'])
                owner.locator.side_effect=lambda selector:wrappers if selector=='.form-field-wrapper' else canvas
                owners=MagicMock();owners.nth.return_value=owner
                tile.drag_to.side_effect=lambda *a,**kw:state.update(created=True)
                profile=native.PROFILES[kind];suffix='12abc' if kind=='single_dropdown' else '12ab'
                original={**deepcopy(profile['defaults']),'label':profile['tile']+' '+suffix,
                    'custom_field_name':profile['tile']+' '+suffix,'unique_key':'contact.'+profile['key_prefix']+suffix}
                if 'query_key' in profile['properties']:original['query_key']=profile['key_prefix']+suffix
                def current(*args):
                    if not state['created']:return [[],[]]
                    result=snapshot(kind);result[0][0]['label']=question(kind)['label'] if state['authored'] else original['label'];return result
                with tempfile.TemporaryDirectory() as root,patch.object(native.survey,'_frame',return_value=frame), \
                        patch.object(native.survey,'_owners',return_value=owners),patch.object(native.survey,'_close_initial'), \
                        patch.object(native.survey,'snapshot',side_effect=current), \
                        patch.object(native,'read_creation_question',side_effect=lambda *a:question(kind) if state['authored'] else original), \
                        patch.object(native.shared,'_write',side_effect=lambda *a,**kw:state.update(authored=True)) as write, \
                        patch.object(native,'reopen_editor') as reopen:
                    result=native.configure_creation(MagicMock(),target,root)
                    replay=native.configure_creation(MagicMock(),target,root)
                self.assertEqual(result,replay);tile.drag_to.assert_called_once_with(canvas,timeout=45000,source_position={'x':36.0,'y':26.0})
                save.click.assert_called_once();write.assert_called_once();self.assertEqual(reopen.call_count,2)
                dialog.locator.assert_called_once_with('[id="'+native.CREATION_TILES[kind]+'"]')

    def test_whole_inventory_binds_multiselect_canonical_identity_and_both_saved_controls(self):
        value=inputs();value['question_batches'].append({'kind':'multi_dropdown','target_slide':2,'questions':[question('multi_dropdown')]})
        plan=front.validate_inputs(value);binding={'editor_url':value['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
            'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'slides':[{'canvas':[]},{'canvas':[]}]}
        completed=[];saved={'slide_labels':binding['slide_labels'],'slides':[]}
        for index,kind in enumerate(('single_dropdown','multi_dropdown')):
            target=front._text_plan(plan,binding,plan['question_batches'][index]);snap=[[],[]];snap[index]=snapshot(kind)[0]
            receipt={'status':'SURVEY_'+kind.upper()+'_SAVED_AND_REOPENED','editor_url':binding['editor_url'],'target_slide':index+1,
                'question':question(kind),'configuration_sha256':native._creation_hash(target),'saved_snapshot':snap,'independent_readback':'VERIFIED'}
            native.validate_creation_receipt(receipt,target)
            completed.append({'kind':kind,'target_slide':index+1,'api_fields':[],'native_receipt':receipt})
            saved['slides'].append({'canvas':[{'types':[native.PROFILES[kind]['type']],'names':[['INPUT',None,None]]}],
                                    'radio_fields':[],'text_fields':[question(kind)]})
        self.assertEqual(front._validate_inventory(saved,plan,binding,completed),saved)
        bad=deepcopy(saved);bad['slides'][1]['text_fields'][0]['unique_key']='contact.foreign'
        with self.assertRaises(runner.Stop):front._validate_inventory(bad,plan,binding,completed)
        bad=deepcopy(saved);bad['slides'][1]['canvas'][0]['names']=[['INPUT','text','foreign']]
        with self.assertRaises(runner.Stop):front._validate_inventory(bad,plan,binding,completed)

    def test_survey_dropdown_projection_normalizes_only_popup_selection(self):
        control={'tag':'INPUT','placeholder':'Choose','classes':['dropdown-input','form-placeholder'],'value':''}
        def project(controls):
            done=subprocess.run([shutil.which('node'),'-e',JS],input=json.dumps({'projection':native.survey._SNAPSHOT_PROJECTION,
                'widgets':[{'types':['MULTIPLE_OPTIONS'],'controls':controls}]}),capture_output=True,text=True,check=True)
            return json.loads(done.stdout)
        baseline=project([control])
        self.assertEqual(baseline,project([{**control,'value':'Transient selected text'},{'tag':'INPUT','popup':True,'value':'Inline option'}]))
        self.assertNotEqual(baseline,project([{**control,'placeholder':'Changed'}]))
        self.assertNotEqual(project([{**control,'name':'FIELD','value':'One'}]),project([{**control,'name':'FIELD','value':'Two'}]))


if __name__=='__main__':unittest.main()
