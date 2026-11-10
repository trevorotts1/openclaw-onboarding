"""Execute the real DOM snapshot projection against captured dropdown shapes."""
from copy import deepcopy
import json
import shutil
import subprocess
import unittest
from unittest.mock import MagicMock
import importlib
import skill6_playwright  # Establish the shared tools package import path.

native=importlib.import_module('playwright_recipes.form_widget_families')

JS='''const fs=require('fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));
function element(data){return {tagName:data.tag||'DIV',textContent:data.text||'',
 value:data.value||'',checked:data.checked||false,required:data.required||false,disabled:data.disabled||false,
 getAttribute:key=>Object.hasOwn(data,key)?data[key]:null,
 hasAttribute:key=>Object.hasOwn(data,key),closest:selector=>selector==='#options-card'&&data.popup?{}:null,
 matches:selector=>selector==='input.dropdown-input.form-placeholder'&&data.tag==='INPUT'
  &&(data.classes||[]).includes('dropdown-input')&&(data.classes||[]).includes('form-placeholder')};}
function widget(data){const rows={'[data-field-type]':data.types.map(type=>element({'data-field-type':type,text:'Dropdown'})),
 '.short-label':[], 'input,textarea,select':data.controls.map(element),'label,.label-container':[],canvas:[]};
 return {style:{width:'100%'},querySelectorAll:selector=>rows[selector],querySelector:selector=>rows[selector][0]};}
process.stdout.write(JSON.stringify(eval('('+input.projection+')')(input.widgets.map(widget))));'''


class DropdownSnapshotPreservation(unittest.TestCase):
    def test_only_selection_value_is_normalized_and_sibling_attributes_remain_protected(self):
        frame=MagicMock();native._snapshot(frame)
        projection=frame.locator.return_value.evaluate_all.call_args.args[0]
        control={'tag':'INPUT','type':'text','placeholder':'Choose a size','aria-label':'Dropdown',
                 'classes':['dropdown-input','form-placeholder'],'value':'','disabled':False,'required':False}
        def snapshot(*controls):
            completed=subprocess.run([shutil.which('node'),'-e',JS],
                input=json.dumps({'projection':projection,'widgets':[{'types':['SINGLE_OPTIONS'],'controls':controls}]}),
                capture_output=True,text=True,check=True)
            return json.loads(completed.stdout)
        before=snapshot(control)
        self.assertEqual(before,snapshot({**control,'value':'Small'}))
        for key,value in (('disabled',True),('placeholder','Changed'),('required',True),
                          ('aria-label','Changed'),('type','number')):
            with self.subTest(attribute=key):self.assertNotEqual(before,snapshot({**control,key:value}))
        self.assertEqual(before,snapshot(control,{'tag':'INPUT','popup':True,'value':'transient option edit'}))
        named={**deepcopy(control),'name':'REAL_FIELD'}
        self.assertNotEqual(snapshot(named),snapshot({**named,'value':'Changed real value'}))


if __name__=='__main__':unittest.main()
