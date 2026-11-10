"""Owned Number survey creation uses the existing shell and whole receipt."""
from copy import deepcopy
from pathlib import Path
import importlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import recipe_cli
import skill6_playwright as runner
import host
import test_survey_creation as legacy

front=importlib.import_module('playwright_recipes.survey_creation')
native=importlib.import_module('playwright_recipes.survey_widget_families')


def question():
    return {'label':'How many attendees?', 'placeholder':'Enter a number', 'short_label':'Attendees',
        'query_key':'attendees', 'custom_field_name':'Attendee count', 'unique_key':'contact.attendee_count',
        'required':True, 'hidden':False}


def inputs():
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder/main',
        'name':'Attendance survey','allow_creation':True,'slide_count':2,
        'question_batches':[{'kind':'number','target_slide':1,'questions':[question()]}]}


def leaf_receipt(plan):
    return {'status':'SURVEY_NUMBER_SAVED_AND_REOPENED', 'editor_url':plan['start_url'],
        'target_slide':plan['target_slide'], 'question':deepcopy(plan['question']),
        'configuration_sha256':native._creation_hash(plan),
        'saved_snapshot':[[{'types':['NUMERICAL']}],[]], 'independent_readback':'VERIFIED'}


class SurveyNumberCreation(unittest.TestCase):
    def test_one_number_drag_saves_reopens_and_completed_child_never_reinserts(self):
        plan=front.validate_inputs(inputs());binding={'editor_url':plan['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
            'slide_labels':['P1 - Slide 1','P2 - Slide 2']}
        target=front._text_plan(plan,binding,plan['question_batches'][0]);state={'created':False,'authored':False}
        frame=MagicMock();owner=MagicMock();wrappers=MagicMock();canvas=MagicMock();dialog=MagicMock();tile=MagicMock();handle=MagicMock();save=MagicMock()
        for node in (canvas,dialog,tile,handle,save,owner.get_by_role.return_value,owner.get_by_text.return_value,
                     dialog.get_by_text.return_value):
            node.count.return_value=1;node.is_visible.return_value=True
        save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,**kw:dialog if role=='dialog' else save
        dialog.locator.return_value=tile;tile.locator.return_value=handle
        wrappers.count.side_effect=lambda:int(state['created'])
        owner.locator.side_effect=lambda selector:wrappers if selector=='.form-field-wrapper' else canvas
        owners=MagicMock();owners.nth.return_value=owner
        handle.drag_to.side_effect=lambda *a,**kw:state.update(created=True)
        original={**question(),'label':'Number 12abc','custom_field_name':'Number 12abc','unique_key':'contact.number_12_abc',
            'query_key':'number_12abc','required':False,'short_label':''}
        def snapshot(*args):
            return [[{'types':['NUMERICAL'],'label':question()['label'] if state['authored'] else original['label']}] if state['created'] else [],[]]
        with tempfile.TemporaryDirectory() as root,patch.object(native.survey,'_frame',return_value=frame), \
                patch.object(native.survey,'_owners',return_value=owners),patch.object(native.survey,'_close_initial'), \
                patch.object(native.survey,'snapshot',side_effect=snapshot), \
                patch.object(native,'read_creation_question',side_effect=lambda *a:question() if state['authored'] else original), \
                patch.object(native.shared,'_write',side_effect=lambda *a,**kw:state.update(authored=True)) as write, \
                patch.object(native,'reopen_editor') as reopen:
            result=native.configure_creation(MagicMock(),target,root)
            replay=native.configure_creation(MagicMock(),target,root)
        self.assertEqual(replay,result);handle.drag_to.assert_called_once();save.click.assert_called_once();write.assert_called_once()
        self.assertEqual(reopen.call_count,2)

    def test_number_compiles_without_radio_api_and_rejects_unmeasured_mixed_owner(self):
        job=recipe_cli.compile_recipe('surveys.create',inputs())
        with patch.object(front.radio,'validate_capability') as api:
            front.validate_runtime(job,None)
        api.assert_not_called()
        self.assertEqual(job['steps'][0]['action'],'native_survey_creation')
        for mutation in ('width','mixed','duplicate'):
            value=inputs()
            if mutation=='width':value['question_batches'][0]['questions'][0]['width']=80
            elif mutation=='mixed':
                from test_survey_text_questions import question as text
                value['question_batches'].append({'kind':'text','target_slide':1,'questions':[text()]})
            else:value['question_batches'].append(deepcopy(value['question_batches'][0]))
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):front.validate_inputs(value)

    def test_whole_saved_inventory_binds_number_type_properties_and_slide(self):
        plan=front.validate_inputs(inputs());binding={'editor_url':plan['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
            'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'slides':[{'canvas':[]},{'canvas':[]}]}
        completed=[{'kind':'number','target_slide':1,'api_fields':[],'native_receipt':{}}]
        saved={'slide_labels':binding['slide_labels'],'slides':[
            {'canvas':[{'types':['NUMERICAL'],'names':[['INPUT',None,None]]}],'radio_fields':[],'text_fields':[question()]},
            {'canvas':[],'radio_fields':[]}]}
        self.assertEqual(front._validate_inventory(saved,plan,binding,completed),saved)
        for mutation in ('family','properties','owner'):
            bad=deepcopy(saved)
            if mutation=='family':bad['slides'][0]['canvas'][0]['types']=['TEXT']
            elif mutation=='properties':bad['slides'][0]['text_fields'][0]['query_key']='other'
            else:bad['slides'].reverse()
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):front._validate_inventory(bad,plan,binding,completed)

    def test_host_owned_creation_and_completed_replay_keep_one_shell_and_no_api(self):
        harness=legacy.WholeSurveyCreation('test_two_radio_target_slides_create_once_and_whole_saved_inventory_is_bound')
        harness.setUp();self.addCleanup(harness.doCleanups)
        harness.data=inputs();harness.page.url=harness.data['start_url']
        harness.shell={'editor_url':harness.editor,'slide_labels':['P1 - Slide 1','P2 - Slide 2'],
            'slides':[{'canvas':[]},{'canvas':[]}]}
        def blank(page,plan,root):
            harness.shell_calls+=1;page.url=harness.editor
            runner.secure_json(Path(root)/'blank-shell-state.json',{'schema':'skill6-empty-survey-shell/1',
                'configuration_sha256':front.blank._fingerprint(plan),'status':'SAVED_AND_REOPENED','binding':harness.shell})
            return deepcopy(harness.shell)
        saved={'slide_labels':harness.shell['slide_labels'],'slides':[
            {'canvas':[{'types':['NUMERICAL'],'names':[['INPUT',None,None]]}],'radio_fields':[],'text_fields':[question()]},
            {'canvas':[],'radio_fields':[]}]}
        probes={'lanes':{'playwright':{'available':True,'current':True,'enabled':True}}}
        with harness.patches(),patch.object(front.blank,'configure',side_effect=blank), \
                patch.object(native,'configure_creation',side_effect=lambda page,plan,root:leaf_receipt(plan)) as leaf, \
                patch.object(front,'_inventory',return_value=saved),patch.object(front.radio,'Skill44RadioTransport') as api:
            result=host.run_recipe('surveys.create',harness.data,probes,harness.root,input_dir=harness.temp.name,page=harness.page)
            replay=host.run_recipe('surveys.create',harness.data,probes,harness.root,input_dir=harness.temp.name,page=harness.page)
        api.assert_not_called();leaf.assert_called_once();self.assertEqual(harness.shell_calls,1)
        self.assertEqual(result['result']['results'][0]['result']['question_batches'][0]['kind'],'number')
        self.assertTrue(replay['result']['replayed'])

    def test_uncertain_number_child_journal_never_inserts_or_saves_again(self):
        plan=front.validate_inputs(inputs());binding={'editor_url':plan['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
            'slide_labels':['P1 - Slide 1','P2 - Slide 2']}
        target=front._text_plan(plan,binding,plan['question_batches'][0])
        with tempfile.TemporaryDirectory() as root:
            runner.secure_json(Path(root)/'number-state.json',{'configuration_sha256':native._creation_hash(target),'status':'INTENT_RECORDED'})
            page=MagicMock();frame=MagicMock()
            with patch.object(native.survey,'_frame',return_value=frame),self.assertRaises(runner.Stop):
                native.configure_creation(page,target,root)
            frame.get_by_role.assert_not_called();page.mouse.down.assert_not_called()


if __name__=='__main__':unittest.main()
