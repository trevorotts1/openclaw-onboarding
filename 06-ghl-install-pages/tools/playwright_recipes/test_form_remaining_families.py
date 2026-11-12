"""Remaining captured native form families extend the maintained widget writer."""
from copy import deepcopy
from pathlib import Path
import importlib
import re
import unittest
from unittest.mock import MagicMock,patch

import recipe_cli
import skill6_playwright as runner
from test_form_widget_families import inputs,properties,receipt
from test_form_single_dropdown_native import Node,Panel

native=importlib.import_module('playwright_recipes.form_widget_families')
choices=importlib.import_module('playwright_recipes.form_single_dropdown_native')


class PrefillNode(Node):
    def count(self):return 1 if self.kind=='value' else super().count()


class PrefillPanel(Panel):
    def locator(self,selector):
        match=re.fullmatch(r'#option-prefillValue-(\d+) input',selector)
        if match:return PrefillNode(self,'value',int(match[1]))
        return super().locator(selector)


class RemainingFormFamilies(unittest.TestCase):
    def test_text_box_list_uses_its_actual_canonical_identity_and_prefill_schema(self):
        job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',inputs('text_box_list')),Path('.'))
        spec=job['steps'][0]
        self.assertEqual(spec['action'],native.ACTION)
        self.assertEqual(native.PROFILES['text_box_list']['type'],'TEXTBOX_LIST')
        self.assertEqual(native._key('text_box_list'),'unique_key')
        native.validate_receipt(receipt(spec),spec)
        for key,value in [('query_key','invented'),('placeholder','invented'),('hidden',False),('calculations',True)]:
            bad=inputs('text_box_list');bad['widget_fields']['fields'][0]['desired'][key]=value
            with self.subTest(key=key),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',bad)
        existing=inputs('text_box_list');value=properties('text_box_list')
        existing['widget_fields']['expected_fields']=[{'kind':'text_box_list','index':1,'properties':value}]
        existing['widget_fields']['fields'][0]['index']=1
        existing['widget_fields']['fields'][0]['desired']['unique_key']='contact.foreign'
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',existing)

    def test_text_box_list_reuses_exact_option_rows_with_prefills_and_owned_tail_removal(self):
        before={'options':[{'label':'Option '+str(i),'value':''} for i in (1,2,3)]}
        desired={'options':[{'label':'First value','value':'One'},{'label':'Second value','value':'Two'}]}
        panel=PrefillPanel({**before,'calculations':False})
        with patch.object(choices,'click',side_effect=panel.click),patch.object(choices,'fill',side_effect=panel.fill):
            choices.write_options(panel,before,desired,prefill=True)
            self.assertEqual(choices.read_options(panel,prefill=True),desired)
        self.assertEqual([event for event in panel.events if event[0] in ('switch','add','remove')],[('remove',2)])
        panel=PrefillPanel({'options':[{'label':'Concurrent','value':''}],'calculations':False})
        with patch.object(choices,'click',side_effect=panel.click),patch.object(choices,'fill',side_effect=panel.fill),self.assertRaises(runner.Stop):
            choices.write_options(panel,before,desired,prefill=True)
        self.assertEqual(panel.events,[])

    def test_saved_option_delete_confirms_exact_shared_modal_once_and_unknown_modal_refuses(self):
        frame=MagicMock();remove=MagicMock();labels=MagicMock();dialog=frame.get_by_role.return_value
        state={'removed':False,'opened':False,'confirm':0}
        remove.is_enabled.return_value=True
        for node in (dialog,dialog.get_by_role.return_value,dialog.get_by_text.return_value,dialog.locator.return_value):
            node.count.return_value=1;node.is_visible.return_value=True
        token=dialog.locator.return_value;token.input_value.return_value=''
        submit=dialog.get_by_role.return_value;submit.is_enabled.return_value=True
        labels.count.side_effect=lambda:2 if state['removed'] else 3
        dialog.count.side_effect=lambda:int(state['opened'])
        def click(node):
            if node is remove:state['opened']=True
            elif node is submit:state.update(removed=True,opened=False,confirm=state['confirm']+1)
            else:raise AssertionError('unexpected native click')
        with patch.object(choices,'click',side_effect=click),patch.object(choices,'fill') as fill:
            choices.remove_option(frame,remove,labels,3)
        self.assertEqual(state['confirm'],1);fill.assert_called_once_with(token,'DELETE')
        token.press.assert_called_once_with('Tab')
        dialog.locator.assert_called_once_with('input[placeholder="DELETE"]')
        state.update(removed=False,opened=False,confirm=0)
        dialog.get_by_role.return_value.count.return_value=0
        with patch.object(choices,'click',side_effect=click),patch.object(choices,'fill') as fill,self.assertRaises(runner.Stop):
            choices.remove_option(frame,remove,labels,3)
        self.assertEqual(state['confirm'],0);fill.assert_not_called()

    def test_monetary_and_source_compile_with_native_properties_without_invented_queries(self):
        for kind in ('monetary','source'):
            spec=recipe_cli.compile_recipe('forms.configure',inputs(kind))['steps'][0]
            native.validate_receipt(receipt(spec),spec)
        self.assertEqual(native.PROFILES['monetary']['type'],'MONETORY')
        self.assertEqual(properties('source'),{'value':'Approved fixture source'})
        self.assertEqual(native._identity('source',properties('source')),'@source')
        before=properties('source');source=inputs('source')
        source['widget_fields']['expected_fields']=[{'kind':'source','index':2,'properties':before}]
        source['widget_fields']['fields'][0]['index']=2
        source['widget_fields']['fields'][0]['desired']={'value':'Updated source'}
        spec=recipe_cli.compile_recipe('forms.configure',source)['steps'][0]
        self.assertEqual(native._desired_records(native.validate(spec)),{'@source':{'kind':'source','properties':{'value':'Updated source'}}})
        bad=inputs('source');bad['widget_fields']['fields'].append(deepcopy(bad['widget_fields']['fields'][0]))
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',bad)
        bad=inputs('source');bad['widget_fields']['fields'][0]['desired']['query_key']='invented'
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',bad)
        bad=inputs('monetary');bad['widget_fields']['fields'][0]['desired'].update(hidden=True,hidden_value='12')
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',bad)

    def test_source_parent_creation_preserves_contact_inventory_and_saves_reopens_once(self):
        placement=importlib.import_module('playwright_recipes.field_placement')
        spec=recipe_cli.compile_recipe('forms.configure',inputs('source'))['steps'][0]
        frame=MagicMock();save=frame.get_by_role.return_value
        save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        # These fixtures contain no HTML widget, so outer Save has no HTML warning dialog.
        frame.locator.return_value.count.return_value=0
        original=[{'types':['text'],'name':'first_name'},{'types':['submit']}]
        state={'created':False,'properties':None};item=MagicMock()
        def snapshot(*args):
            return [deepcopy(original[0])]+([{'types':['source'],'properties':deepcopy(state['properties'])}] if state['created'] else [])+[deepcopy(original[1])]
        def inventory(*args):
            return [{'kind':'source','index':2,'properties':deepcopy(state['properties'])}] if state['created'] else []
        def append(*args):state.update(created=True,properties={'value':''});return 1,item,{'value':''}
        def write(*args):state['properties']=deepcopy(args[-1])
        with patch.object(native,'_frame',return_value=frame),patch.object(native,'_inventory',side_effect=inventory), \
                patch.object(native,'_snapshot',side_effect=snapshot),patch.object(native,'_append',side_effect=append) as created, \
                patch.object(native,'_write',side_effect=write),patch.object(placement,'_inventory',return_value={'first_name':'text'}), \
                patch.object(native,'reopen_editor') as reopen:
            result=native.configure(MagicMock(),spec)
        created.assert_called_once();save.click.assert_called_once();reopen.assert_called_once()
        self.assertEqual(result['fields'][0]['properties'],properties('source'))
        self.assertEqual(result['saved_snapshot'][0],original[0])

    def test_score_and_rating_bind_native_existing_owners_and_support_captured_creation(self):
        for kind in ('score','rating'):
            source=inputs(kind)
            source['widget_fields']['expected_fields']=[{'kind':kind,'index':1,'properties':properties(kind)}]
            source['widget_fields']['fields'][0]['index']=1
            spec=runner.validate_job(recipe_cli.compile_recipe('forms.configure',source),Path('.'))['steps'][0]
            native.validate_receipt(receipt(spec),spec)
            self.assertEqual(spec['payload']['fields'][0]['index'],1)
            fresh=deepcopy(source);fresh['widget_fields']['fields'][0]['index']=None
            fresh['widget_fields']['expected_fields']=[]
            recipe_cli.compile_recipe('forms.configure',fresh)
            for key,value in [('unique_key','contact.invented'),('calculations','unmeasured'),('rating_style','stars')]:
                bad=deepcopy(source);bad['widget_fields']['fields'][0]['desired'][key]=value
                with self.subTest(kind=kind,key=key),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',bad)
        self.assertEqual(native.PROFILES['rating']['general_selector'],'#rating-general-settings')
        self.assertEqual(native.PROFILES['rating']['input_count'],2)
        self.assertNotIn('unique_key',native.PROFILES['score']['properties'])
        self.assertNotIn('unique_key',native.PROFILES['rating']['properties'])

    def test_rating_endpoint_labels_write_only_to_captured_owner_inputs(self):
        profile=native.PROFILES['rating'];before=properties('rating')
        desired={**before,'lowest_label':'Poor','highest_label':'Excellent'}
        item=MagicMock();frame=MagicMock();controls={}
        for key,selector in profile['properties'].items():
            node=MagicMock();node.count.return_value=1;node.is_visible.return_value=True;node.input_value.return_value=str(before[key]);controls[selector]=node
        flag=MagicMock();flag.count.return_value=1;flag.is_visible.return_value=True;flag.get_attribute.return_value='false'
        controls['#fieldRequired']=flag;frame.locator.side_effect=lambda selector:controls[selector]
        preview={}
        for key,selector in profile['preview_properties'].items():
            node=MagicMock();node.count.return_value=1;node.is_visible.return_value=True;node.input_value.return_value=before[key];preview[selector]=node
        item.locator.side_effect=lambda selector:preview[selector]
        with patch.object(native,'_read',side_effect=[before,desired]),patch.object(native,'_activate',return_value=profile), \
                patch.object(native,'fill') as fill,patch.object(native,'_close_properties'):
            native._write(frame,item,'rating',before,desired)
        self.assertEqual(fill.call_count,2)
        for key,selector in profile['preview_properties'].items():
            self.assertIn(unittest.mock.call(preview[selector],desired[key]),fill.call_args_list)
            preview[selector].press.assert_called_once_with('Tab')


if __name__=='__main__':unittest.main()
