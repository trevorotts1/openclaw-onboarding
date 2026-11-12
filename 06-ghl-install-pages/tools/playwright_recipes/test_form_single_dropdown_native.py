"""Native Single Dropdown creation and owned choice editing use the shared writer."""
from copy import deepcopy
from pathlib import Path
import re
import unittest
from unittest.mock import MagicMock, patch
import importlib

import recipe_cli
import skill6_playwright as runner
native=importlib.import_module('playwright_recipes.form_widget_families')
leaf=importlib.import_module('playwright_recipes.form_single_dropdown_native')
placement=importlib.import_module('playwright_recipes.field_placement')
from test_form_widget_families import inputs, properties, receipt


class Node:
    def __init__(self,panel,kind,index=None):self.panel,self.kind,self.index=panel,kind,index
    def count(self):
        if self.kind=='labels':return len(self.panel.values['options'])
        if self.kind=='value':return int(self.panel.values['calculations'])
        return 1
    def is_visible(self):return self.count()>0
    def is_enabled(self):return self.kind!='remove' or len(self.panel.values['options'])>1
    def get_attribute(self,key):
        if key=='aria-checked':return 'true' if self.panel.values['calculations'] else 'false'
        raise AssertionError(key)
    def input_value(self):return self.panel.values['options'][self.index]['label' if self.kind=='label' else 'value']
    def locator(self,selector):
        if selector=='..':return self
        if selector=='button#remove-option':return Node(self.panel,'remove',self.index)
        raise AssertionError(selector)
    def get_by_role(self,role):assert role=='switch';return Node(self.panel,'switch')
    def press(self,key):assert key=='Tab'


class Panel(Node):
    def __init__(self,values):self.values=deepcopy(values);self.events=[];super().__init__(self,'panel')
    def get_by_text(self,label,exact=True):
        if label=='Options':return Node(self,'pane')
        assert label=='Enable calculations';return Node(self,'calculation-label')
    def locator(self,selector):
        if selector=='#form_custom_sidebar':return self
        if selector=='[id^="option-label-"] input':return Node(self,'labels')
        if selector=='button#add-option':return Node(self,'add')
        match=re.fullmatch(r'#option-(label|value)-(\d+)( input)?',selector)
        if match:return Node(self,match[1],int(match[2]))
        raise AssertionError(selector)
    def click(self,node):
        if node.kind=='pane':return
        self.events.append((node.kind,node.index))
        if node.kind=='switch':
            self.values['calculations']=not self.values['calculations']
            for option in self.values['options']:option['value']='' if self.values['calculations'] else None
        elif node.kind=='add':
            self.values['options'].append({'label':'Option '+str(len(self.values['options'])+1),
                'value':'' if self.values['calculations'] else None})
        elif node.kind=='remove':self.values['options'].pop(node.index)
        else:raise AssertionError(node.kind)
    def fill(self,node,value):
        self.events.append(('fill_'+node.kind,node.index))
        self.values['options'][node.index]['label' if node.kind=='label' else 'value']=value


class NativeDropdownTests(unittest.TestCase):
    def test_profile_compiles_as_owned_native_creation_without_api_option_schema(self):
        job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',inputs('single_dropdown')),Path('.'))
        self.assertEqual(job['steps'][0]['action'],native.ACTION)
        self.assertEqual(job['steps'][0]['payload']['fields'][0]['index'],None)
        native.validate_receipt(receipt(job['steps'][0]),job['steps'][0])
        for unsupported in ({'hidden':False},{'style':'bubble'},{'other':None}):
            data=inputs('single_dropdown');data['widget_fields']['fields'][0]['desired'].update(unsupported)
            with self.subTest(unsupported=unsupported),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',data)

    def test_options_are_full_exact_labels_and_calculation_values(self):
        desired=properties('single_dropdown');desired.update(calculations=True,
            options=[{'label':'Choice A','value':'10'},{'label':'Choice B','value':'20.5'}])
        native._properties('single_dropdown',desired)
        for change in ({'options':[{'label':'Duplicate','value':'1'},{'label':'Duplicate','value':'2'}]},
                       {'options':[{'label':'Bad','value':'nan'}]},
                       {'calculations':False}, {'calculations':1}):
            bad={**deepcopy(desired),**change}
            with self.subTest(change=change),self.assertRaises(runner.Stop):native._properties('single_dropdown',bad)

    def exercise(self,before,desired):
        panel=Panel(before)
        with patch.object(leaf,'click',side_effect=panel.click),patch.object(leaf,'fill',side_effect=panel.fill):
            leaf.write_options(panel,before,desired)
            self.assertEqual(leaf.read_options(panel),desired)
        return panel

    def test_enable_calculations_grow_and_author_complete_choices(self):
        before=deepcopy(leaf.PROFILE['defaults']);before={key:before[key] for key in ('options','calculations')}
        desired={'calculations':True,'options':[{'label':'Choice '+str(i),'value':str(i*10)} for i in (1,2,3,4)]}
        panel=self.exercise(before,desired)
        self.assertEqual([event for event in panel.events if event[0] in ('switch','add','remove')],[('switch',None),('add',None)])

    def test_disable_calculations_and_remove_owned_tail_options(self):
        before={'calculations':True,'options':[{'label':'Choice '+str(i),'value':str(i*10)} for i in (1,2,3)]}
        desired={'calculations':False,'options':[{'label':'Only choice','value':None}]}
        panel=self.exercise(before,desired)
        self.assertEqual([event for event in panel.events if event[0] in ('switch','add','remove')],
                         [('switch',None),('remove',2),('remove',1)])

    def test_changed_previous_choices_refuse_without_writing(self):
        before={'calculations':False,'options':[{'label':'Expected','value':None}]}
        panel=Panel({'calculations':False,'options':[{'label':'Concurrent','value':None}]})
        with patch.object(leaf,'click',side_effect=panel.click),patch.object(leaf,'fill',side_effect=panel.fill), \
             self.assertRaisesRegex(runner.Stop,'changed after full preflight'):
            leaf.write_options(panel,before,before)
        self.assertEqual(panel.events,[])

    def test_owned_creation_preserves_address_and_existing_widget_saves_once(self):
        data=inputs('single_dropdown');number=properties('number')
        data['widget_fields']['expected_fields']=[{'kind':'number','index':2,'properties':number}]
        spec=recipe_cli.compile_recipe('forms.configure',data)['steps'][0]
        desired=properties('single_dropdown');state={'created':False};frame=MagicMock()
        save=frame.get_by_role.return_value;save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        # These fixtures contain no HTML widget, so outer Save has no HTML warning dialog.
        frame.locator.return_value.count.return_value=0
        base=[{'types':['group'],'children':'all five preserved'},{'types':['NUMERICAL'],'properties':number},{'types':['submit']}]
        def snapshot(*_):return deepcopy(base[:2])+([{'types':['SINGLE_OPTIONS'],'properties':desired}] if state['created'] else [])+deepcopy(base[2:])
        def inventory(*_):return deepcopy(data['widget_fields']['expected_fields'])+([{'kind':'single_dropdown','index':3,'properties':desired}] if state['created'] else [])
        def append(*_):state['created']=True;return 2,MagicMock(),deepcopy(desired)
        def query(*_,**__):return {'address':'group','approved_number':'NUMERICAL',**({'approved_single_dropdown':'SINGLE_OPTIONS'} if state['created'] else {})}
        with patch.object(native,'_frame',return_value=frame),patch.object(native,'_inventory',side_effect=inventory), \
             patch.object(native,'_snapshot',side_effect=snapshot),patch.object(native,'_append',side_effect=append) as created, \
             patch.object(native,'_write'),patch.object(placement,'_inventory',side_effect=query),patch.object(native,'reopen_editor') as reopen:
            result=native.configure(MagicMock(),spec)
        created.assert_called_once();save.click.assert_called_once();reopen.assert_called_once()
        self.assertEqual(result['saved_snapshot'][0],base[0]);self.assertEqual(result['fields'][0]['properties'],number)


if __name__=='__main__':unittest.main()
