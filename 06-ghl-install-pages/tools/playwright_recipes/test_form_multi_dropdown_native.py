"""Native Multi Dropdown descriptor and actual mixed-dropdown snapshot projection."""
from copy import deepcopy
from pathlib import Path
import importlib
import json
import shutil
import subprocess
import unittest
import skill6_playwright as runner
import recipe_cli
from test_form_widget_families import inputs, receipt
from test_form_widget_dropdown_snapshot import JS
from test_mixed_widget_canvas_identity import Scope
import forms_advanced

native=importlib.import_module('playwright_recipes.form_widget_families')


class MultiDropdownContracts(unittest.TestCase):
    def test_creation_binds_canonical_identity_without_invented_local_query_or_hidden(self):
        source=inputs('multi_dropdown');job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',source),Path('.'))
        spec=job['steps'][0];desired=spec['payload']['fields'][0]['desired']
        self.assertNotIn('query_key',desired);self.assertEqual(native._key('multi_dropdown'),'unique_key')
        self.assertEqual(native.PROFILES['multi_dropdown']['type'],'MULTIPLE_OPTIONS')
        saved=receipt(spec);native.validate_receipt(saved,spec)
        for key,value in (('query_key','invented_local_key'),('hidden',False),('style','bubble')):
            bad=deepcopy(source);bad['widget_fields']['fields'][0]['desired'][key]=value
            with self.subTest(key=key),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',bad)
        bad=deepcopy(saved);bad['fields'][0]['properties']['unique_key']='contact.foreign'
        with self.assertRaises(runner.Stop):native.validate_receipt(bad,spec)

    def test_existing_canonical_identity_is_immutable_but_captured_choices_are_editable(self):
        source=inputs('multi_dropdown');previous=deepcopy(source['widget_fields']['fields'][0]['desired'])
        source['widget_fields']['expected_fields']=[{'kind':'multi_dropdown','index':2,'properties':previous}]
        change=source['widget_fields']['fields'][0];change['index']=2
        change['desired'].update(calculations=True,options=[{'label':'First','value':'1'},{'label':'Second','value':'2'}])
        recipe_cli.compile_recipe('forms.configure',source)
        change['desired']['unique_key']='contact.foreign'
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',source)

    def test_api_canvas_identity_preserves_multi_dropdown_across_selection(self):
        selected={'types':['MULTIPLE_OPTIONS'],'controls':[{'tag':'INPUT','type':'text',
            'classes':['dropdown-input','form-placeholder']}]}
        inactive={'types':['MULTIPLE_OPTIONS'],'controls':[]}
        self.assertEqual(forms_advanced._canvas_identity(Scope([selected])),forms_advanced._canvas_identity(Scope([inactive])))


class Scene:
    def __init__(self):
        self.selected=0
        self.controls=[{'tag':'INPUT','type':'text','placeholder':'Choose one','disabled':False,
                        'classes':['dropdown-input','form-placeholder'],'value':''},
                       {'tag':'INPUT','type':'text','placeholder':'Choose many','disabled':False,
                        'classes':['dropdown-input','form-placeholder'],'value':''}]
    def locator(self,selector):assert selector==native.CANVAS_ITEMS;return self
    def count(self):return 2
    def nth(self,index):return Item(self,index)
    def evaluate_all(self,projection):return self.project(projection)
    def project(self,projection,*,single=None):
        widgets=[{'types':[kind],'controls':[self.controls[i]] if self.selected==i else []}
                 for i,kind in enumerate(('SINGLE_OPTIONS','MULTIPLE_OPTIONS'))]
        if single is not None:widgets=[widgets[single]]
        script=JS.replace('input.widgets.map(widget)','input.single?widget(input.widgets[0]):input.widgets.map(widget)')
        done=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({
            'projection':projection,'widgets':widgets,'single':single is not None}),capture_output=True,text=True,check=True)
        return json.loads(done.stdout)


class Item:
    def __init__(self,scene,index):self.scene,self.index=scene,index
    def locator(self,selector):assert selector=='[data-field-type]';return self
    def count(self):return 1
    def is_visible(self):return True
    def wait_for(self,**kwargs):pass
    def click(self,**kwargs):self.scene.selected=self.index
    def evaluate(self,projection):return self.scene.project(projection,single=self.index)


class MixedDropdownSnapshot(unittest.TestCase):
    def test_selected_state_preserves_all_attributes_without_selection_false_drift(self):
        scene=Scene();before=native._snapshot(scene)
        scene.selected=1;scene.controls[0]['value']='Transient preview choice'
        self.assertEqual(before,native._snapshot(scene))
        scene.controls[1]['placeholder']='Concurrent placeholder edit'
        self.assertNotEqual(before,native._snapshot(scene))
        scene.controls[1]['placeholder']='Choose many';scene.controls[0]['disabled']=True
        self.assertNotEqual(before,native._snapshot(scene))
        self.assertEqual(len(before[0]['controls']),1);self.assertEqual(len(before[1]['controls']),1)


if __name__=='__main__':unittest.main()
