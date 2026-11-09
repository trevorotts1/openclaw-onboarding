"""Exercise the real DOM projection when selection toggles a native dropdown."""
import json
import shutil
import subprocess
import unittest

import forms_advanced as native


JS='''const fs=require('fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));
function control(data){return {tagName:data.tag,
 getAttribute:key=>Object.hasOwn(data,key)?data[key]:null,
 hasAttribute:key=>Object.hasOwn(data,key),
 matches:selector=>selector==='input.dropdown-input.form-placeholder' && data.tag==='INPUT'
   && (data.classes||[]).includes('dropdown-input') && (data.classes||[]).includes('form-placeholder')};}
function widget(data){return {querySelectorAll:selector=>selector==='[data-field-type]'
 ?data.types.map(type=>({getAttribute:key=>key==='data-field-type'?type:null}))
 :(data.controls||[]).map(control)};}
const fn=eval('('+input.projection+')');
process.stdout.write(JSON.stringify(fn(input.widgets.map(widget))));'''


class Projection:
    def __init__(self,widgets):self.widgets=widgets
    def evaluate_all(self,projection):
        result=subprocess.run([shutil.which('node'),'-e',JS],
            input=json.dumps({'projection':projection,'widgets':self.widgets}),
            text=True,capture_output=True,check=True)
        return json.loads(result.stdout)


class Scope:
    def __init__(self,widgets,*,identity='form-builder-container',nested=None):
        self.widgets,self.identity,self.nested=widgets,identity,nested or []
        self.selectors=[]
    def get_attribute(self,key):return self.identity if key=='id' else None
    def locator(self,selector):
        self.selectors.append(selector)
        return Projection(self.widgets if selector==':scope > .form-field-wrapper'
                          else [*self.widgets,*self.nested])


@unittest.skipUnless(shutil.which('node'),'Node is required to evaluate this offline DOM projection')
class MixedWidgetIdentityTests(unittest.TestCase):
    def test_radio_insertion_deselects_dropdown_without_an_unrelated_identity_failure(self):
        selected={'types':['SINGLE_OPTIONS'],'controls':[{'tag':'INPUT','type':'text',
                   'classes':['dropdown-input','form-placeholder']}]}
        inactive={'types':['SINGLE_OPTIONS'],'controls':[]}
        existing_radio={'types':['RADIO'],'controls':[{'tag':'INPUT','type':'radio','name':'EXISTING_API_ID'}]}
        textarea={'types':['LARGE_TEXT'],'controls':[{'tag':'TEXTAREA'}]}
        new_radio={'types':['RADIO'],'controls':[{'tag':'INPUT','type':'radio','name':'NEW_API_ID'}]}
        before=native._canvas_identity(Scope([selected,existing_radio,textarea]))
        after=native._canvas_identity(Scope([inactive,existing_radio,textarea,new_radio]))
        self.assertEqual(after[:-1],before)
        self.assertEqual(after[-1]['names'],[['INPUT','radio','NEW_API_ID']])
        self.assertEqual(before[-1]['names'],[['TEXTAREA',None,None]])

    def test_normalization_keeps_real_named_controls_and_controls_owned_by_other_widgets(self):
        classes=['dropdown-input','form-placeholder']
        widgets=[{'types':['SINGLE_OPTIONS'],'controls':[{'tag':'INPUT','type':'text','name':'REAL_API_ID','classes':classes}]},
                 {'types':['SINGLE_OPTIONS'],'controls':[{'tag':'INPUT','type':'text','id':'REAL_NATIVE_ID','classes':classes}]},
                 {'types':['RADIO'],'controls':[{'tag':'INPUT','type':'radio','classes':classes}]}]
        result=native._canvas_identity(Scope(widgets))
        self.assertEqual(result[0]['names'],[['INPUT','text','REAL_API_ID']])
        self.assertEqual(result[1]['names'],[['INPUT','text',None]])
        self.assertEqual(result[2]['names'],[['INPUT','radio',None]])

    def test_form_root_excludes_nested_forged_wrappers_without_changing_survey_layout(self):
        actual={'types':['text'],'controls':[{'tag':'INPUT','type':'text','name':'ACTUAL'}]}
        nested={'types':['RADIO'],'controls':[{'tag':'INPUT','type':'radio','name':'NESTED'}]}
        form=Scope([actual],nested=[nested])
        self.assertEqual(len(native._canvas_identity(form)),1)
        self.assertEqual(form.selectors,[':scope > .form-field-wrapper'])
        survey=Scope([actual],identity='survey-slide',nested=[nested])
        self.assertEqual(len(native._canvas_identity(survey)),2)
        self.assertEqual(survey.selectors,['.form-field-wrapper'])


if __name__=='__main__':unittest.main()
