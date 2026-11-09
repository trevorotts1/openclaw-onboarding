"""Captured LARGE_TEXT/NUMERICAL shapes, native defaults and complete readback."""
from copy import deepcopy
from contextlib import ExitStack
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree

import quiz_written_questions as written
import quiz_text_questions as native
import quiz_choice_questions as choice
from skill6_playwright import Stop
from test_quiz_text_questions import question
from test_quiz_choice_questions import ChoiceDom


def step(kind='LARGE_TEXT'):
    return {'action':'quiz_written_answers','payload':{'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ',
        'expected_quiz_name':'Exact quiz','pages':[{'label':'Page 1','questions':[question()]}],
        'target_page':1,'questions':[{**question('Tell us more','context',kind),
                                   'placeholder':'Share your context','short_label':'Context','required':True}]}}


class Validation(unittest.TestCase):
    def test_captured_native_written_types_and_all_authored_properties_are_hash_bound(self):
        for kind in written.PROFILES:
            value=step(kind);self.assertEqual(written.validate(value),value['payload'])
            changed=deepcopy(value);changed['payload']['questions'][0]['placeholder']='Another prompt'
            self.assertNotEqual(written.configuration_hash(changed),written.configuration_hash(value))
    def test_existing_native_default_keys_are_preserved_when_authored_final_keys_are_distinct(self):
        for kind,profile in written.PROFILES.items():
            value=step(kind);value['payload']['pages'][0]['questions'][0]['query_key']=profile['default_key'].upper()
            with self.subTest(kind=kind):self.assertEqual(written.validate(value),value['payload'])
    def test_existing_checkbox_full_options_can_be_preserved_before_new_written_questions(self):
        value=step();value['payload']['pages'][0]['questions']=[{**question('Existing multi','prior_multi','CHECKBOX'),
                                                              'options':['A','B','C']}]
        self.assertEqual(written.validate(value),value['payload'])
        value['payload']['pages'][0]['questions'][0]['options']=['A','B']
        with self.assertRaises(Stop):written.validate(value)
    def test_uncaptured_types_incomplete_old_properties_and_wrong_editor_refuse(self):
        for mutate in ('type','properties','editor'):
            value=step()
            if mutate=='type':value['payload']['questions'][0]['field_type']='NUMBER'
            elif mutate=='properties':value['payload']['pages'][0]['questions'][0].pop('hidden')
            else:value['payload']['start_url']=value['payload']['start_url'].replace('/LOC/','/OTHER/')
            with self.subTest(mutate=mutate),self.assertRaises(Stop):written.validate(value)


class WrittenDom(ChoiceDom):
    def locator(self,selector):
        result=super().locator(selector);return WrittenDom(result.nodes,self.parents)
    def get_by_role(self,role,*,name,exact):
        if role=='textbox' and name=='Label':
            return WrittenDom([node for root in self.nodes for node in root.iter()
                if node.get('role')=='textbox' and node.get('aria-label')=='Label'],self.parents)
        result=super().get_by_role(role,name=name,exact=exact);return WrittenDom(result.nodes,self.parents)


class NativeShape(unittest.TestCase):
    def fixture(self,kind):
        profile=written.PROFILES[kind];suffix='720jvx' if profile['suffix']==6 else '25ka3'
        owner=ElementTree.Element('section',{'class':'form-builder--item','data-active':'true'})
        ElementTree.SubElement(owner,'div',{'role':'textbox','aria-label':'Label','data-field-type':kind,
            'contenteditable':'true'}).text=profile['tile']+' '+suffix
        attrs={'class':'form-control','value':''}
        if kind in ('TEXT','LARGE_TEXT'):attrs['class']+=' form-placeholder'
        if kind=='LARGE_TEXT':attrs.update({'placeholder':'','aria-label':'Type your message here'})
        ElementTree.SubElement(owner,'textarea' if kind=='LARGE_TEXT' else 'input',attrs)
        return owner
    def test_real_captured_textarea_and_typeless_number_dom_are_accepted(self):
        for kind in written.PROFILES:
            owner=WrittenDom([self.fixture(kind)])
            with self.subTest(kind=kind),patch.object(native,'_append_tile',return_value=owner) as append,patch.object(native,'_activate_item'):
                self.assertIs(written._append(object(),step(kind)['payload'],step(kind)['payload']['questions'][0]),owner)
            self.assertEqual(append.call_args.args[2],written.PROFILES[kind]['tile'])
    def test_invented_numeric_type_or_identifier_and_long_answer_accessible_shape_refuse(self):
        for kind,key,value in (('NUMERICAL','type','number'),('NUMERICAL','id','invented'),
                               ('NUMERICAL','placeholder','Visible prompt'),('LARGE_TEXT','aria-label','Other')):
            owner=self.fixture(kind);owner[1].set(key,value)
            with self.subTest(kind=kind,key=key),patch.object(native,'_append_tile',return_value=WrittenDom([owner])),self.assertRaises(Stop):
                written._append(object(),step(kind)['payload'],step(kind)['payload']['questions'][0])
    def test_misplaced_insert_returns_old_last_widget_and_refuses_before_property_authoring(self):
        owner=self.fixture('TEXT');owner[0].set('data-field-type','RADIO')
        with patch.object(native,'_append_tile',return_value=WrittenDom([owner])),self.assertRaisesRegex(Stop,'active native type'):
            written._append(object(),step()['payload'],step()['payload']['questions'][0])


class Execution(unittest.TestCase):
    def execute(self,kind='LARGE_TEXT',*,lost=False,collateral=False):
        plan=step(kind);page,frame=MagicMock(),MagicMock();page.url=plan['payload']['start_url'];page.frame_locator.return_value=frame
        title,save=MagicMock(),MagicMock();title.count.return_value=1;title.input_value.return_value='Exact quiz'
        save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,**kwargs:title if role=='textbox' else save
        initial=[[{**question(),'_widget_inputs':[],'_radio_options':[]}]]
        state={'inventory':deepcopy(initial),'saves':0,'reopened':False}
        save.click.side_effect=lambda:state.__setitem__('saves',state['saves']+1)
        def write(_frame,_item,question,**kwargs):
            self.assertEqual(kwargs['default_key'],written.PROFILES[kind]['default_key'])
            new={**question,'_widget_inputs':[{'tag':'TEXTAREA' if kind=='LARGE_TEXT' else 'INPUT',
                'name':None,'type':None,'value':'','placeholder':None}]}
            state['inventory'][0][-1]=new
            if collateral:state['inventory'][0][0]['query_key']='Changed sibling'
            return deepcopy(new)
        def reopen(*args):
            state['reopened']=True
            if lost:state['inventory']=deepcopy(initial)
        with ExitStack() as stack:
            stack.enter_context(patch.object(written,'assert_tenant'))
            stack.enter_context(patch.object(native,'_wait_baseline'))
            stack.enter_context(patch.object(written,'click',side_effect=lambda target:target.click()))
            stack.enter_context(patch.object(written,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())))
            stack.enter_context(patch.object(choice,'_inventory',side_effect=lambda *args,**kwargs:deepcopy(state['inventory'])))
            def insert(*args,**kwargs):
                profile=written.PROFILES[kind]
                state['inventory'][0].append({**question(profile['tile']+' abc123',profile['default_key'],kind),'_widget_inputs':[]})
                return object()
            append=stack.enter_context(patch.object(written,'_append',side_effect=insert))
            stack.enter_context(patch.object(native,'_write_question',side_effect=write))
            stack.enter_context(patch.object(native,'reopen_editor',side_effect=reopen))
            try:result=written.configure(page,plan)
            except Stop as error:return error,state,append
        return result,state,append
    def test_long_and_numeric_authored_properties_use_exact_native_defaults_and_reopen(self):
        for kind in written.PROFILES:
            result,state,append=self.execute(kind)
            self.assertEqual(result['configuration_sha256'],written.configuration_hash(step(kind)))
            self.assertEqual(result['status'],'QUIZ_WRITTEN_ANSWERS_SAVED_AND_REOPENED')
            self.assertFalse(result['submission_verified']);self.assertFalse(result['dependency_api_used'])
            self.assertEqual(state['saves'],1);self.assertTrue(state['reopened']);append.assert_called_once()
    def test_collateral_sibling_change_never_saves_and_lost_persisted_answer_never_completes(self):
        for options in ({'collateral':True},{'lost':True}):
            result,state,_=self.execute(**options)
            self.assertIsInstance(result,Stop)
            self.assertEqual(state['saves'],0 if options.get('collateral') else 1)


if __name__=='__main__':unittest.main()
