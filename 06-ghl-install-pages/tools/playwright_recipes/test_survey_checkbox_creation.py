"""Captured survey Checkbox lifecycle through the shared family adapter."""
from copy import deepcopy
from pathlib import Path
import importlib
import tempfile
import unittest
from unittest.mock import MagicMock,patch

import host
import recipe_cli
import skill6_playwright as runner
import test_survey_creation as legacy

front=importlib.import_module('playwright_recipes.survey_creation')
native=importlib.import_module('playwright_recipes.survey_widget_families')


def question():
    return {**deepcopy(native.CHECKBOX['defaults']), 'label':'Choose your services', 'short_label':'Services',
        'query_key':'services', 'custom_field_name':'Services', 'unique_key':'contact.services',
        'required':True, 'style':'bubble', 'calculations':True, 'columns':2,
        'options':[{'label':'Design','value':'10'},{'label':'Automation','value':'20'}],
        'other':{'label':'Other','placeholder':'Describe another service'}}


def inputs():
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder/main',
        'name':'Services survey','allow_creation':True,'slide_count':2,
        'question_batches':[{'kind':'checkbox','target_slide':1,'questions':[question()]}]}


def configuration():
    from test_survey_widget_families import inputs as existing
    source=existing()
    for mode in ('expected','desired'):
        source['configuration']['widget_fields'][mode]=[[],[{'kind':'checkbox','index':2,'properties':question()}]]
    return source


def snapshot():
    return [[{'types':['CHECKBOX'], 'controls':[
        ['INPUT','checkbox',None,None,'Design'], ['INPUT','checkbox',None,None,'Automation'],
        ['INPUT','checkbox',None,None,'Other'], ['INPUT','text',None,'Describe another service','']]}],[]]


def receipt(plan):
    return {'status':'SURVEY_CHECKBOX_SAVED_AND_REOPENED','editor_url':plan['start_url'],
        'target_slide':plan['target_slide'],'question':deepcopy(plan['question']),
        'configuration_sha256':native._creation_hash(plan),'saved_snapshot':snapshot(),'independent_readback':'VERIFIED'}


class SurveyCheckboxCreation(unittest.TestCase):
    def test_checkbox_creation_and_existing_edits_compile_with_survey_metadata(self):
        job=recipe_cli.compile_recipe('surveys.create',inputs())
        front.validate_runtime(job,None)
        self.assertEqual(native.CHECKBOX['sidebar'],'#survey_custom_sidebar')
        self.assertEqual(native.CREATION_TILES['checkbox'],'Checkbox2')
        self.assertNotIn('width',native.CHECKBOX['properties'])
        from test_survey_widget_families import inputs as existing
        source=existing()
        for mode in ('expected','desired'):
            source['configuration']['widget_fields'][mode]=[[],[{'kind':'checkbox','index':2,'properties':question()}]]
        spec=recipe_cli.compile_recipe('surveys.configure',source)['steps'][0]
        self.assertEqual(spec['action'],'native_survey_widget_fields')
        source['configuration']['widget_fields']['desired'][1][0]['properties']['unique_key']='contact.foreign'
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('surveys.configure',source)
        for key,value in [('width',80),('other',{'label':'Invented','placeholder':'Other'}),('calculations',False)]:
            bad=inputs();bad['question_batches'][0]['questions'][0][key]=value
            with self.subTest(key=key),self.assertRaises(runner.Stop):front.validate_inputs(bad)

    def test_checkbox_creation_uses_one_drag_save_and_fresh_child_replay(self):
        plan=front.validate_inputs(inputs());binding={'editor_url':plan['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
            'slide_labels':['P1 - Slide 1','P2 - Slide 2']}
        target=front._text_plan(plan,binding,plan['question_batches'][0]);state={'created':False,'authored':False}
        frame=MagicMock();owner=MagicMock();wrappers=MagicMock();canvas=MagicMock();dialog=MagicMock();tile=MagicMock();handle=MagicMock();save=MagicMock()
        for node in (canvas,dialog,tile,handle,save,owner.get_by_role.return_value,owner.get_by_text.return_value,
                     dialog.get_by_text.return_value):node.count.return_value=1;node.is_visible.return_value=True
        save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,**kw:dialog if role=='dialog' else save
        dialog.locator.return_value=tile;tile.locator.return_value=handle
        wrappers.count.side_effect=lambda:int(state['created'])
        owner.locator.side_effect=lambda selector:wrappers if selector=='.form-field-wrapper' else canvas
        owners=MagicMock();owners.nth.return_value=owner
        handle.drag_to.side_effect=lambda *a,**kw:state.update(created=True)
        original={**deepcopy(native.CHECKBOX['defaults']),'label':'Checkbox 12abc','custom_field_name':'Checkbox 12abc',
            'unique_key':'contact.checkbox_12_abc','query_key':'checkbox_12abc'}
        def current(*args):
            if not state['created']:return [[],[]]
            value=snapshot();value[0][0]['label']=question()['label'] if state['authored'] else original['label'];return value
        with tempfile.TemporaryDirectory() as root,patch.object(native.survey,'_frame',return_value=frame), \
                patch.object(native.survey,'_owners',return_value=owners),patch.object(native.survey,'_close_initial'), \
                patch.object(native.survey,'snapshot',side_effect=current), \
                patch.object(native,'read_creation_question',side_effect=lambda *a:question() if state['authored'] else original), \
                patch.object(native.shared,'_write',side_effect=lambda *a,**kw:state.update(authored=True)) as write, \
                patch.object(native,'reopen_editor') as reopen:
            result=native.configure_creation(MagicMock(),target,root)
            replay=native.configure_creation(MagicMock(),target,root)
        self.assertEqual(result,replay);handle.drag_to.assert_called_once();save.click.assert_called_once()
        write.assert_called_once();self.assertEqual(write.call_args.kwargs['profile']['sidebar'],'#survey_custom_sidebar')
        self.assertEqual(reopen.call_count,2);dialog.locator.assert_called_once_with('[id="Checkbox2"]')

    def test_host_creates_one_shell_and_whole_checkbox_inventory_replays_without_api(self):
        harness=legacy.WholeSurveyCreation('test_two_radio_target_slides_create_once_and_whole_saved_inventory_is_bound')
        harness.setUp();self.addCleanup(harness.doCleanups);harness.data=inputs();harness.page.url=harness.data['start_url']
        harness.shell={'editor_url':harness.editor,'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'slides':[{'canvas':[]},{'canvas':[]}]}
        def blank(page,plan,root):
            harness.shell_calls+=1;page.url=harness.editor
            runner.secure_json(Path(root)/'blank-shell-state.json',{'schema':'skill6-empty-survey-shell/1',
                'configuration_sha256':front.blank._fingerprint(plan),'status':'SAVED_AND_REOPENED','binding':harness.shell})
            return deepcopy(harness.shell)
        saved={'slide_labels':harness.shell['slide_labels'],'slides':[
            {'canvas':[{'types':['CHECKBOX'],'names':[control[:3] for control in snapshot()[0][0]['controls']]}],
             'radio_fields':[],'text_fields':[question()]},{'canvas':[],'radio_fields':[]}]}
        probes={'lanes':{'playwright':{'available':True,'current':True,'enabled':True}}}
        with harness.patches(),patch.object(front.blank,'configure',side_effect=blank), \
                patch.object(native,'configure_creation',side_effect=lambda page,plan,root:receipt(plan)) as leaf, \
                patch.object(front,'_inventory',return_value=saved),patch.object(front.radio,'Skill44RadioTransport') as api:
            result=host.run_recipe('surveys.create',harness.data,probes,harness.root,input_dir=harness.temp.name,page=harness.page)
            replay=host.run_recipe('surveys.create',harness.data,probes,harness.root,input_dir=harness.temp.name,page=harness.page)
        api.assert_not_called();leaf.assert_called_once();self.assertEqual(harness.shell_calls,1);self.assertTrue(replay['result']['replayed'])
        completed=result['result']['results'][0]['result']
        bad=deepcopy(completed['saved_inventory']);bad['slides'][0]['canvas'][0]['names'].pop()
        with self.assertRaises(runner.Stop):front._validate_inventory(bad,front.validate_inputs(inputs()),harness.shell,completed['question_batches'])


if __name__=='__main__':unittest.main()
