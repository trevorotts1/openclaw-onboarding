"""Survey Number uses its captured profile and preserves slide ownership."""
from copy import deepcopy
from pathlib import Path
import importlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import recipe_cli
import skill6_playwright as runner

native = importlib.import_module('playwright_recipes.survey_widget_families')


def inputs():
    before = {'label':'Count', 'placeholder':'Enter a number', 'short_label':'',
              'query_key':'count', 'custom_field_name':'Count', 'unique_key':'contact.count',
              'required':False, 'hidden':False}
    after = {**before, 'label':'How many seats?', 'short_label':'Seats', 'required':True}
    return {'location_id':'LOC', 'location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder-v2/SURVEY',
        'configuration':{'expected_survey_name':'Approved survey', 'expected_slide_count':2,
            'slide_labels':['P1 - Contact', 'P2 - Details'],
            'widget_fields':{
                'expected':[[], [{'kind':'number', 'index':2, 'properties':before}]],
                'desired':[[], [{'kind':'number', 'index':2, 'properties':after}]]}}}


def step():
    return recipe_cli.compile_recipe('surveys.configure', inputs())['steps'][0]


def receipt(spec):
    plan = native.validate(spec)
    return {'status':'SURVEY_WIDGET_FIELDS_SAVED_AND_REOPENED',
        'editor_url':plan['start_url'], 'configuration_sha256':native.configuration_hash(spec),
        'widget_fields':deepcopy(plan['widget_fields']['desired']),
        'saved_snapshot':[[{'types':['TEXT']}], [{'types':['LARGE_TEXT']}, {'types':['NUMERICAL']}]],
        'independent_readback':'VERIFIED', 'behavior_verified':False, 'submission_verified':False}


class SurveyWidgetFamilies(unittest.TestCase):
    def test_captured_creation_profiles_bind_bot_source_and_monetary(self):
        self.assertEqual(native.CREATION_TILES['bot_protection'], 'Bot protection2')
        self.assertEqual(native.CREATION_TILES['source'], 'Source3')
        self.assertEqual(native.CREATION_TILES['monetary'], 'Monetary2')
        self.assertEqual(native.PROFILES['bot_protection']['type'], 'captcha')
        self.assertEqual(native._identity('bot_protection', {'label':'Bot protection',
            'verification_mode':'interactive'}), '@captcha')
        self.assertEqual(native._identity('source', {'value':'Campaign'}), '@source')
        self.assertEqual(native.PROFILES['monetary']['type'], 'MONETORY')
        self.assertNotIn('width', native.PROFILES['monetary']['properties'])
        self.assertEqual(native.CREATION_TILES['score'], 'Score5')
        self.assertEqual(native.PROFILES['score']['type'], 'SCORE')
        self.assertEqual(native.PROFILES['score']['properties']['label'], '#fieldTitle input')
        self.assertNotIn('width', native.PROFILES['score']['properties'])
        self.assertEqual(native.CREATION_TILES['rating'], 'Rating0')
        self.assertEqual(native.PROFILES['rating']['fixed_identity'], '@rating')
        self.assertTrue(native.PROFILES['rating']['queryless'])
        self.assertEqual(native.PROFILES['rating']['general_selector'], '#rating-general-settings')
        native.validate_creation_question({'label':'Bot protection','verification_mode':'interactive'}, 'bot_protection')
        native.validate_creation_question({'value':'Campaign'}, 'source')
        native.validate_creation_question({'label':'Budget','placeholder':'Enter amount','short_label':'',
            'query_key':'budget','custom_field_name':'Budget','unique_key':'contact.budget',
            'required':False,'hidden':False}, 'monetary')
        native.validate_creation_question({'label':'Score 17cu','placeholder':'Ex: Your Score is 100%',
            'short_label':'','query_key':'score_17cu','required':False,'hidden':False}, 'score')
        native.validate_creation_question({'label':'How was it?','short_label':'','width':100,
            'required':False,'lowest_label':'Low','highest_label':'High'},'rating')

    def test_content_creation_profiles_bind_survey_selectors_and_native_defaults(self):
        self.assertEqual(native.CREATION_TILES['text_heading'],'Text0')
        self.assertEqual(native.PROFILES['text_heading']['type'],'h1')
        self.assertEqual(native.CREATION_TILES['image'],'Image0')
        self.assertEqual(native.PROFILES['image']['sidebar'],'#survey_custom_sidebar')
        self.assertEqual(native.CREATION_TILES['html'],'Html1')
        self.assertEqual(native.CREATION_TILES['picture_choice'],'Picture Choice4')
        self.assertNotIn('width',native.PROFILES['picture_choice']['properties'])
        native.validate_creation_question({'text':'A plain heading'},'text_heading')
        native.validate_creation_question({'label':'Campaign image','image_url':'https://cdn.example/image.png','alt_text':'Campaign'},'image')
        native.validate_creation_question({'label':'Embed','html':'<p>Three lines</p>\n<section>More</section>'},'html')
        picture={'label':'Picture Choice 108fk0','placeholder':'','short_label':'','query_key':'picture_choice_108fk0',
            'required':False,'hidden':False,'options':[{'label':'Option '+str(i),
            'image_url':'https://cdn.example/'+str(i)+'.png','media_button_name':'Approved '+str(i)} for i in (1,2,3)]}
        native.validate_creation_question(picture,'picture_choice')
        default={'label':'Picture Choice 108fk0','placeholder':'','short_label':'','query_key':'picture_choice_108fk0',
            'required':False,'hidden':False,'options':deepcopy(native.PICTURE_CHOICE['defaults']['options'])}
        native._validate_new_default('picture_choice',default)
        wrong=deepcopy(picture);wrong['options'][1]['media_button_name']=''
        with self.assertRaises(runner.Stop):native.validate_creation_question(wrong,'picture_choice')

    def test_url_profile_uses_captured_survey_identity_and_public_configure_compiler(self):
        profile=native.PROFILES['url']
        self.assertEqual(native.CREATION_TILES['url'],'URL6')
        self.assertEqual(profile['type'],'URL')
        self.assertEqual(profile['sidebar'],'#survey_custom_sidebar')
        self.assertEqual(profile['properties']['label'],'#fieldTitle input')
        self.assertEqual(profile['properties']['query_key'],'#fieldQueryKey input')
        self.assertNotIn('width',profile['properties'])
        native.validate_creation_question({'label':'Campaign link','placeholder':'Paste a URL',
            'short_label':'Link','query_key':'campaign_link','required':True,'hidden':False,
            'domain_mode':'allow_only','domains':['example.com']},'url')
        default={'label':'URL 2z47','placeholder':'Enter a URL','short_label':'','query_key':'url_2z47',
            'required':False,'hidden':False,'domain_mode':'allow_all','domains':[]}
        native._validate_new_default('url',default)
        source=inputs();source['configuration']['widget_fields']={
            'expected':[[],[{'kind':'url','index':1,'properties':default}]],
            'desired':[[],[{'kind':'url','index':1,'properties':{**default,'label':'Campaign link'}}]]}
        self.assertEqual(recipe_cli.compile_recipe('surveys.configure',source)['steps'][0]['action'],native.ACTION)

    def test_captured_new_defaults_match_the_generated_native_identities(self):
        cases={
            'bot_protection':deepcopy(native.BOT_PROTECTION['defaults']),
            'source':deepcopy(native.SOURCE['defaults']),
            'monetary':{**deepcopy(native.MONETARY['defaults']),'label':'Monetary 5ccw',
                'query_key':'monetary_5ccw','custom_field_name':'Monetary 5ccw',
                'unique_key':'contact.monetary_5_ccw'},
            'score':{**deepcopy(native.SCORE['defaults']),'label':'Score 17cu',
                'query_key':'score_17cu'},
            'rating':{**deepcopy(native.RATING['defaults']),'label':'Rating rat584 1xx4'},
        }
        for kind,default in cases.items():
            with self.subTest(kind=kind):native._validate_new_default(kind,default)
        wrong=deepcopy(cases['score']);wrong['query_key']='score_other'
        with self.assertRaises(runner.Stop):native._validate_new_default('score',wrong)
        wrong=deepcopy(cases['rating']);wrong['highest_label']='Excellent'
        with self.assertRaises(runner.Stop):native._validate_new_default('rating',wrong)

    def test_captured_survey_date_modes_bind_generated_defaults_and_exact_mode(self):
        cases={
            'date':{**deepcopy(native.SURVEY_DATE['defaults']),'label':'Date 101ir',
                'query_key':'date_101ir','custom_field_name':'Date 101ir','unique_key':'contact.date_101_ir',
                'collection_mode':'date'},
            'date_time':{**deepcopy(native.SURVEY_DATE_TIME['defaults']),'label':'Date & time 101ir',
                'query_key':'date_&_time_101ir','custom_field_name':'Date & time 101ir','unique_key':'contact.date_101_ir',
                'collection_mode':'date_time'},
            'time':{**deepcopy(native.SURVEY_TIME['defaults']),'label':'Time 101ir',
                'query_key':'time_101ir','custom_field_name':'Time 101ir','unique_key':'contact.time_101_ir',
                'collection_mode':'time'}}
        expected_types={'date':'DATE','date_time':'DATE_TIME','time':'TIME'}
        for kind,default in cases.items():
            with self.subTest(kind=kind):
                self.assertEqual(native.PROFILES[kind]['type'],expected_types[kind])
                self.assertEqual(native.CREATION_TILES[kind],'Date & time4')
                native.validate_creation_question({**default,'label':'A requested date/time'},kind)
                native._validate_new_default(kind,default)
                config={'expected_survey_name':'Survey','expected_slide_count':2,
                    'slide_labels':['P1 - One','P2 - Two'],'widget_fields':{
                        'expected':[[{'kind':kind,'index':1,'properties':default}],[]],
                        'desired':[[{'kind':kind,'index':1,'properties':default}],[]]}}
                source={'location_id':'LOC','location_name':'Fixture Account',
                    'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder-v2/SURVEY',
                    'configuration':config}
                self.assertEqual(recipe_cli.compile_recipe('surveys.configure',source)['steps'][0]['action'],native.ACTION)
        wrong=deepcopy(cases['date_time']);wrong['collection_mode']='date'
        with self.assertRaises(runner.Stop):native.validate_creation_question(wrong,'date_time')

    def test_new_date_widget_selects_requested_collect_mode_before_settings_scan(self):
        profile=native.SURVEY_TIME;frame=MagicMock();item=MagicMock();sidebar=MagicMock()
        node=MagicMock();node.count.return_value=1;node.is_visible.return_value=True;node.is_enabled.return_value=True
        sidebar.count.return_value=1;sidebar.is_visible.return_value=True
        state={'mode':'date'};buttons={mode:MagicMock() for mode in ('date','time','date_time')}
        for button in buttons.values():button.count.return_value=1;button.is_visible.return_value=True;button.is_enabled.return_value=True
        buttons['date'].get_attribute.side_effect=lambda name:'dt-segmented-button--active' if state['mode']=='date' else ''
        buttons['time'].get_attribute.side_effect=lambda name:'dt-segmented-button--active' if state['mode']=='time' else ''
        buttons['date_time'].get_attribute.side_effect=lambda name:'dt-segmented-button--active' if state['mode']=='date_time' else ''
        frame.locator.return_value=sidebar;sidebar.locator.side_effect=lambda selector:buttons[
            {'#collect-date':'date','#collect-time':'time','#collect-date-time':'date_time'}[selector]] if selector.startswith('#collect-') else node
        sidebar.get_by_text.return_value=node;item.locator.return_value=node
        def click(target):
            for mode,button in buttons.items():
                if target is button:state['mode']=mode
        with patch.object(native.shared,'click',side_effect=click) as clicked:
            native.shared._set_survey_collection_mode(frame,item,profile)
        self.assertEqual(state['mode'],'time')
        self.assertEqual(clicked.call_count,6)

    def test_date_mode_activation_uses_nested_field_settings_and_captured_preview_count(self):
        for kind,expected_count in (('date',1),('date_time',2),('time',1)):
            profile=native.PROFILES[kind];frame=MagicMock();item=MagicMock();sidebar=MagicMock();node=MagicMock();preview=MagicMock()
            for target in (node,sidebar,preview):
                target.count.return_value=1;target.is_visible.return_value=True;target.is_enabled.return_value=True
            preview.count.return_value=expected_count
            frame.locator.return_value=sidebar;sidebar.get_by_text.return_value=node;sidebar.locator.return_value=node
            item.locator.side_effect=lambda selector:preview if selector==profile['input'] else node
            with self.subTest(kind=kind),patch.object(native.shared,'click') as click:
                native.shared._activate(frame,item,kind,profile=profile)
            item.locator.assert_any_call(profile['input'])
            sidebar.locator.assert_any_call('[data-name="settings"]')
            sidebar.get_by_text.assert_any_call('Content',exact=True)
            self.assertEqual(click.call_count,4)

    def test_noncontact_activation_opens_captured_content_and_settings_anchor(self):
        for kind in ('source','bot_protection'):
            profile=native.PROFILES[kind];frame=MagicMock();item=MagicMock();node=MagicMock()
            node.count.return_value=1;node.is_visible.return_value=True;node.is_enabled.return_value=True
            no_preview_input=MagicMock();no_preview_input.count.return_value=0
            frame.locator.return_value=node;frame.get_by_text.return_value=node;node.get_by_text.return_value=node
            item.locator.side_effect=lambda selector: no_preview_input if selector=='input,textarea,select' else node
            with self.subTest(kind=kind),patch.object(native.shared,'click') as click:
                native.shared._activate(frame,item,kind,profile=profile)
            item.locator.assert_any_call('[aria-label="Open settings"]')
            frame.locator.assert_any_call(profile['sidebar'])
            node.get_by_text.assert_any_call('Content',exact=True)
            self.assertGreaterEqual(click.call_count,3)

    def test_rating_activation_uses_captured_content_preview_and_general_settings(self):
        profile=native.RATING;frame=MagicMock();item=MagicMock();node=MagicMock();rating_inputs=MagicMock()
        node.count.return_value=1;node.is_visible.return_value=True;node.is_enabled.return_value=True
        rating_inputs.count.return_value=2
        frame.locator.return_value=node;frame.get_by_text.return_value=node;node.get_by_text.return_value=node
        item.locator.side_effect=lambda selector:rating_inputs if selector=='input.rating-input' else node
        with patch.object(native.shared,'click') as click:
            native.shared._activate(frame,item,'rating',profile=profile)
        item.locator.assert_any_call('[data-field-type="RATING"]')
        item.locator.assert_any_call('[aria-label="Open settings"]')
        node.get_by_text.assert_any_call('Content',exact=True)
        frame.locator.assert_any_call('#rating-general-settings')
        self.assertGreaterEqual(click.call_count,3)

    def test_number_compiles_with_survey_profile_and_parent_binding(self):
        job = runner.validate_job(recipe_cli.compile_recipe('surveys.configure', inputs()), Path('.'))
        spec = job['steps'][0]
        self.assertEqual(spec['action'], native.ACTION)
        self.assertEqual(native.NUMBER['properties']['label'], '#fieldTitle input')
        self.assertNotIn('width', native.NUMBER['properties'])
        native.validate_receipt(receipt(spec), spec)
        for key in native.COMMON:
            bad = deepcopy(job)
            bad['steps'][0]['payload'][key] += 'foreign'
            with self.subTest(key=key), self.assertRaises(runner.Stop):
                runner.validate_job(bad, Path('.'))

    def test_uncaptured_families_form_width_and_canonical_metadata_refuse(self):
        for key, value in [('kind','checkbox'), ('width',80),
                           ('custom_field_name','Changed global field'), ('unique_key','contact.other')]:
            source = inputs()
            field = source['configuration']['widget_fields']['desired'][1][0]
            if key == 'kind': field[key] = value
            else: field['properties'][key] = value
            with self.subTest(key=key), self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('surveys.configure', source)

    def test_property_edits_preserve_siblings_save_once_and_reopen(self):
        spec = step(); plan = native.validate(spec); frame = MagicMock()
        save = frame.get_by_role.return_value
        save.count.return_value = 1; save.is_visible.return_value = True; save.is_enabled.return_value = True
        before = plan['widget_fields']['expected']; desired = plan['widget_fields']['desired']
        state = {'fields':deepcopy(before)}
        base = receipt(spec)['saved_snapshot']
        def snapshot(*args):
            result = deepcopy(base)
            result[1][1]['label'] = state['fields'][1][0]['properties']['label']
            return result
        def write(*args, **kwargs):
            self.assertEqual(kwargs['profile'], native.NUMBER)
            state['fields'] = deepcopy(desired)
        with patch.object(native,'_frame',return_value=frame), \
                patch.object(native,'_inventory',side_effect=lambda *a:deepcopy(state['fields'])), \
                patch.object(native.survey,'_owners',return_value=MagicMock()), \
                patch.object(native.survey,'snapshot',side_effect=snapshot), \
                patch.object(native.shared,'_write',side_effect=write) as writer, \
                patch.object(native,'reopen_editor') as reopen:
            result = native.configure(MagicMock(), spec)
        writer.assert_called_once(); save.click.assert_called_once(); reopen.assert_called_once()
        self.assertEqual(result['widget_fields'], desired)
        self.assertEqual(result['saved_snapshot'][1][0], base[1][0])

    def test_unknown_family_query_inventory_refuses_rename_before_write(self):
        spec = step()
        spec['payload']['widget_fields']['desired'][1][0]['properties']['query_key'] = 'renamed'
        frame = MagicMock()
        with patch.object(native,'_frame',return_value=frame), \
                patch.object(native,'_inventory',return_value=spec['payload']['widget_fields']['expected']), \
                patch.object(native.survey,'snapshot',return_value=receipt(spec)['saved_snapshot']), \
                patch.object(native.shared,'_write') as writer, self.assertRaises(runner.Stop):
            native.configure(MagicMock(),spec)
        writer.assert_not_called(); frame.get_by_role.assert_not_called()

    def test_runner_completed_replay_reads_fresh_state_and_refuses_drift(self):
        job = runner.validate_job(recipe_cli.compile_recipe('surveys.configure',inputs()), Path('.'))
        spec = job['steps'][0]; saved = receipt(spec); page = MagicMock()
        with tempfile.TemporaryDirectory() as root, patch.object(runner,'assert_tenant'), \
                patch.object(native,'configure',return_value=saved) as writer:
            runner.run_on_page(page,job,root)
            state = Path(root,'state.json'); previous = state.read_bytes()
            with patch.object(native,'reopen_editor') as reopen, \
                    patch.object(native,'_frame',return_value=MagicMock()), \
                    patch.object(native,'_inventory',return_value=[]), self.assertRaises(runner.Stop):
                runner.run_on_page(page,job,root)
            self.assertEqual(state.read_bytes(),previous)
        writer.assert_called_once(); reopen.assert_called_once()


if __name__ == '__main__': unittest.main()
