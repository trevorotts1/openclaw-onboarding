"""Captured survey Text Box List keeps native owner, options and saved identity."""
from copy import deepcopy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
import recipe_cli
import skill6_playwright as runner
native=importlib.import_module('playwright_recipes.survey_widget_families')
front=importlib.import_module('playwright_recipes.survey_creation')


def question():
    return {**deepcopy(native.TEXT_BOX_LIST['defaults']),'label':'List your priorities',
        'short_label':'Priorities','custom_field_name':'Priorities','unique_key':'contact.priorities',
        'required':True,'options':[{'label':'First priority','value':'Launch'},
                                 {'label':'Second priority','value':'Grow'}]}


def inputs():
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder/main',
        'name':'Priorities survey','allow_creation':True,'slide_count':2,
        'question_batches':[{'kind':'text_box_list','target_slide':1,'questions':[question()]}]}


def snapshot():
    return [[{'types':['TEXTBOX_LIST'],'controls':[['INPUT','text',None,'Add values',x['value']]
        for x in question()['options']]}],[]]


class SurveyTextBoxList(unittest.TestCase):
    def test_create_configure_profiles_and_immutable_identity_compile(self):
        source=inputs();job=runner.validate_job(recipe_cli.compile_recipe('surveys.create',source),Path('.'))
        front.validate_runtime(job,None)
        self.assertEqual(native.CREATION_TILES['text_box_list'],'Text Box List2')
        self.assertEqual(native.TEXT_BOX_LIST['properties']['label'],'#fieldTitle input')
        self.assertEqual(native.TEXT_BOX_LIST['sidebar'],'#survey_custom_sidebar')
        config={'expected_survey_name':'ZHC Priorities survey','expected_slide_count':2,
            'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'widget_fields':{
                'expected':[[{'kind':'text_box_list','index':1,'properties':question()}],[]],
                'desired':[[{'kind':'text_box_list','index':1,'properties':{**question(),'required':False}}],[]]}}
        existing={**{k:source[k] for k in native.COMMON},'start_url':source['start_url'].replace('survey-builder/main','survey-builder-v2/EXISTING'),'configuration':config}
        spec=recipe_cli.compile_recipe('surveys.configure',existing)['steps'][0]
        self.assertEqual(spec['action'],native.ACTION)
        config['widget_fields']['desired'][0][0]['properties']['unique_key']='contact.other'
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('surveys.configure',existing)
        bad=inputs();bad['question_batches'][0]['questions'][0]['width']=80
        with self.assertRaises(runner.Stop):front.validate_inputs(bad)

    def test_one_owned_insertion_saves_reopens_and_completed_child_never_reinserts(self):
        plan=front.validate_inputs(inputs());binding={'editor_url':plan['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
            'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'slides':[{'canvas':[]},{'canvas':[]}]}
        target=front._text_plan(plan,binding,plan['question_batches'][0]);state={'created':False,'authored':False}
        frame=MagicMock();owner=MagicMock();wrappers=MagicMock();canvas=MagicMock();dialog=MagicMock();tile=MagicMock();handle=MagicMock();save=MagicMock()
        for node in (canvas,dialog,tile,handle,save,owner.get_by_role.return_value,owner.get_by_text.return_value,dialog.get_by_text.return_value):
            node.count.return_value=1;node.is_visible.return_value=True
        save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,**kw:dialog if role=='dialog' else save
        dialog.locator.return_value=tile;tile.locator.return_value=handle
        wrappers.count.side_effect=lambda:int(state['created'])
        owner.locator.side_effect=lambda selector:wrappers if selector=='.form-field-wrapper' else canvas
        owners=MagicMock();owners.nth.return_value=owner
        handle.drag_to.side_effect=lambda *a,**kw:state.update(created=True)
        original={**deepcopy(native.TEXT_BOX_LIST['defaults']),'label':'Text Box List 3bpl',
            'custom_field_name':'Text Box List 3bpl','unique_key':'contact.text_box_list_3_bpl'}
        with tempfile.TemporaryDirectory() as root,patch.object(native.survey,'_frame',return_value=frame),patch.object(native.survey,'_owners',return_value=owners),patch.object(native.survey,'_close_initial'),patch.object(native.survey,'snapshot',side_effect=lambda *a:snapshot() if state['created'] else [[],[]]),patch.object(native,'read_creation_question',side_effect=lambda *a:question() if state['authored'] else original),patch.object(native.shared,'_write',side_effect=lambda *a,**kw:state.update(authored=True)) as writer,patch.object(native,'reopen_editor') as reopen:
            done=native.configure_creation(MagicMock(),target,root)
            self.assertEqual(native.configure_creation(MagicMock(),target,root),done)
        handle.drag_to.assert_called_once();save.click.assert_called_once();writer.assert_called_once();self.assertEqual(reopen.call_count,2)
        completed=[{'kind':'text_box_list','target_slide':1,'api_fields':[],'native_receipt':done}]
        saved={'slide_labels':binding['slide_labels'],'slides':[
            {'canvas':[{'types':['TEXTBOX_LIST'],'names':[x[:3] for x in snapshot()[0][0]['controls']]}],
             'radio_fields':[],'text_fields':[question()]},{'canvas':[],'radio_fields':[]}]}
        self.assertEqual(front._validate_inventory(saved,plan,binding,completed),saved)
        changed=deepcopy(saved);changed['slides'][0]['canvas'][0]['names'][0][2]='foreign'
        with self.assertRaises(runner.Stop):front._validate_inventory(changed,plan,binding,completed)

    def test_duplicate_canonical_identity_refuses_before_new_shell(self):
        data=inputs();data['question_batches'].append({'kind':'text_box_list','target_slide':2,'questions':[question()]})
        with self.assertRaises(runner.Stop):front.validate_inputs(data)

if __name__=='__main__':unittest.main()
