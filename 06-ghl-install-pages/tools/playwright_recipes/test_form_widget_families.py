"""Captured family schemas, owner boundaries, sibling safety and CLI replay."""
from copy import deepcopy
from pathlib import Path
import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import recipe_cli
import skill6_playwright as runner

native=importlib.import_module('playwright_recipes.form_widget_families')
placement=importlib.import_module('playwright_recipes.field_placement')


def properties(kind):
    profile=native.PROFILES[kind]
    if kind=='text_heading':return {'text':'Approved heading'}
    if kind=='image':return {'label':'Approved Image','image_url':'https://example.com/image.png','alt_text':'Approved image'}
    if kind=='picture_choice':
        return {'label':'Approved Picture','placeholder':'','short_label':'','query_key':'approved_picture',
            'width':100,'required':False,'hidden':False,'options':[
            {'label':'Option 1','image_url':'https://example.com/one.png','alt':'First'},
            {'label':'Option 2','image_url':'https://example.com/two.png','alt':'Second'}]}
    value=deepcopy(profile['defaults'])
    if 'label' in profile['properties']:value['label']='Approved '+profile['tile']
    if 'custom_field_name' in profile['properties']:value['custom_field_name']=value['label']
    if 'unique_key' in profile['properties']:value['unique_key']='contact.approved_'+kind
    if kind=='source':value['value']='Approved fixture source'
    if 'query_key' in profile['properties']:value['query_key']='approved_'+kind
    if kind=='file_upload':value['file_access']='private'
    return value


def inputs(kind='number'):
    value={'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
        'widget_fields':{'expected_form_name':'Approved fixture','expected_fields':[],
                         'fields':[{'kind':kind,'index':None,'desired':properties(kind)}]}}
    if kind=='picture_choice' or native.PROFILES[kind].get('creation_supported') is False:
        value['widget_fields']['expected_fields']=[{'kind':kind,'index':1,'properties':properties(kind)}]
        value['widget_fields']['fields'][0]['index']=1
    return value


def step(kind='number'):
    source=inputs(kind)
    return recipe_cli.compile_recipe('forms.configure',source)['steps'][0]


def receipt(spec):
    plan=native.validate(spec);fields=[];snapshot=[]
    for index,field in enumerate(plan['fields'],1):
        fields.append({'kind':field['kind'],'index':index,'properties':deepcopy(field['desired'])})
        snapshot.append({'types':[native.PROFILES[field['kind']]['type']]})
    return {'status':'FORM_WIDGET_FIELDS_SAVED_AND_REOPENED','editor_url':plan['start_url'],
        'configuration_sha256':native.configuration_hash(spec),'fields':fields,'saved_snapshot':snapshot,
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False}


class FormWidgetFamilies(unittest.TestCase):
    def test_all_four_captured_profiles_compile_and_bind_the_parent_editor(self):
        for kind in native.PROFILES:
            with self.subTest(kind=kind):
                source=inputs(kind);job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',source),Path('.'))
                self.assertEqual(job['steps'][0]['action'],native.ACTION)
                native.validate_receipt(receipt(job['steps'][0]),job['steps'][0])
                for key in native.COMMON:
                    bad=deepcopy(job);bad['steps'][0]['payload'][key]+='foreign'
                    with self.assertRaises(runner.Stop):runner.validate_job(bad,Path('.'))

    def test_actual_family_differences_and_immutable_existing_metadata_refuse_prebrowser(self):
        for kind in ('file_upload','signature'):
            value=properties(kind);value['hidden']=False
            source=inputs(kind);source['widget_fields']['fields'][0]['desired']=value
            with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',source)
        for key,wanted in (('file_access','public'),('unique_key','contact.other'),('custom_field_name','Renamed')):
            source=inputs('file_upload');before=properties('file_upload')
            source['widget_fields']['expected_fields']=[{'kind':'file_upload','index':1,'properties':deepcopy(before)}]
            change=source['widget_fields']['fields'][0];change['index']=1;change['desired'][key]=wanted
            with self.subTest(immutable=key),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',source)
        source=inputs('number');source['widget_fields']['fields'][0]['desired'].update(required=True,hidden=True,hidden_value='42')
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',source)

    def test_only_captured_unique_key_prefix_normalization_is_applied(self):
        node=MagicMock();node.input_value.return_value='';node.get_attribute.return_value='file_upload_120_ee'
        self.assertEqual(native._read_input(node,'unique_key'),'contact.file_upload_120_ee')
        node.input_value.return_value='contact.owned'
        self.assertEqual(native._read_input(node,'unique_key'),'contact.owned')
        node.input_value.return_value='local_key'
        self.assertEqual(native._read_input(node,'query_key'),'local_key')

    def test_file_limits_and_checkbox_special_other_are_typed_distinctly(self):
        file=properties('file_upload');file.update(multiple_files=True,max_files=2,file_types=['pdf'])
        native._properties('file_upload',file)
        file['multiple_files']=False
        with self.assertRaises(runner.Stop):native._properties('file_upload',file)
        check=properties('checkbox');check.update(style='bubble',calculations=True,columns=2,
            options=[{'label':name,'value':str(score)} for name,score in [('One',10),('Two',20),('Three',30)]],
            other={'label':'Other','placeholder':'Describe another option'})
        native._properties('checkbox',check)
        check['other']['label']='Invented editable Other label'
        with self.assertRaises(runner.Stop):native._properties('checkbox',check)

    def test_changed_owner_inventory_stops_before_append_write_or_save(self):
        spec=step();frame=MagicMock()
        with patch.object(native,'_frame',return_value=frame),patch.object(native,'_inventory',return_value=[{'unexpected':True}]),\
                patch.object(native,'_append') as append,patch.object(native,'_write') as write,self.assertRaises(runner.Stop):
            native.configure(MagicMock(),spec)
        append.assert_not_called();write.assert_not_called();frame.get_by_role.assert_not_called()

    def test_creation_preserves_siblings_and_saves_once_then_independently_reopens(self):
        spec=step();desired=properties('number');state={'created':False,'properties':None};frame=MagicMock()
        save=frame.get_by_role.return_value;save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        item=MagicMock();base=[{'types':['text'],'label':'Preserved'}, {'types':['submit']}]
        def snapshot():
            if not state['created']:return deepcopy(base)
            return [deepcopy(base[0]),{'types':['NUMERICAL'],'properties':deepcopy(state['properties'])},deepcopy(base[1])]
        def inventory(*args):
            return ([{'kind':'number','index':2,'properties':deepcopy(state['properties'])}] if state['created'] else [])
        def append(*args):state.update(created=True,properties=deepcopy(desired));return 1,item,deepcopy(desired)
        def write(*args):state['properties']=deepcopy(args[-1])
        def queries(*args,**kwargs):return {'first_name':'text',**({'approved_number':'NUMERICAL'} if state['created'] else {})}
        with patch.object(native,'_frame',return_value=frame),patch.object(native,'_inventory',side_effect=inventory),\
                patch.object(native,'_snapshot',side_effect=lambda *a:snapshot()),patch.object(native,'_append',side_effect=append) as created,\
                patch.object(native,'_write',side_effect=write),patch.object(placement,'_inventory',side_effect=queries),\
                patch.object(native.html_fields,'confirm_save_warning'),patch.object(native,'reopen_editor') as reopen:
            result=native.configure(MagicMock(),spec)
        created.assert_called_once();save.click.assert_called_once();reopen.assert_called_once()
        self.assertEqual(result['fields'],inventory());self.assertEqual(result['saved_snapshot'][0],base[0])

    def test_public_cli_completed_replay_reaches_fresh_verifier_and_refuses_drift(self):
        source=inputs();job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',source),Path('.'))
        spec=job['steps'][0];saved=receipt(spec);page=MagicMock();page.url=source['start_url']
        pw=MagicMock();browser=pw.chromium.connect_over_cdp.return_value;browser.contexts=[types.SimpleNamespace(pages=[page])]
        context=MagicMock();context.__enter__.return_value=pw
        api=types.ModuleType('playwright.sync_api');api.sync_playwright=lambda:context
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value=saved) as write:
            runner.run_on_page(page,job,root);path=Path(root,'state.json');before=path.read_bytes()
            with patch.dict(sys.modules,{'playwright':types.ModuleType('playwright'),'playwright.sync_api':api}),\
                    patch.dict(os.environ,{'GHL_MANAGED_CDP_URL':'http://127.0.0.1:9222','GHL_BROWSER_LOCK_DIR':str(Path(root,'locks'))}),\
                    patch.object(native,'reopen_editor') as reopen,patch.object(native,'_frame',return_value=MagicMock()),\
                    patch.object(native,'_inventory',return_value=[]),self.assertRaises(runner.Stop):
                runner.execute(job,root)
            self.assertEqual(path.read_bytes(),before)
        write.assert_called_once();reopen.assert_called_once();pw.chromium.connect_over_cdp.assert_called_once()


if __name__=='__main__':unittest.main()
