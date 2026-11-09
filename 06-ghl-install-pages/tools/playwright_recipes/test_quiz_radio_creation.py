"""Captured Single Choice / Yes-No UUIDs and safe authored choice creation."""
from copy import deepcopy
from contextlib import ExitStack
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree

import quiz_choice_questions as choice
import quiz_text_questions as native
from skill6_playwright import Stop
from test_quiz_choice_questions import ChoiceDom
from test_quiz_text_questions import question


NEW_ID='bbbbbbbb-2222-4222-8222-222222222222'
OLD_ID='cccccccc-3333-4333-8333-333333333333'


def authored(count=3):
    return {**question('Which priority fits?','priority','RADIO'),
            'options':['Grow','Simplify','Delegate'] if count==3 else ['Ready','Later']}


def step(count=3):
    return {'action':'quiz_multiple_choices','payload':{'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ',
        'expected_quiz_name':'Exact quiz','pages':[{'label':'Page 1','questions':[question()]}],
        'target_page':1,'questions':[authored(count)],'acknowledge_shared_field_options':True}}


class RadioDom(ChoiceDom):
    def locator(self,selector):
        result=super().locator(selector);return RadioDom(result.nodes,self.parents)
    def nth(self,index):return RadioDom([self.nodes[index]],self.parents)
    def evaluate_all(self,script):
        if script!='nodes=>nodes.map(node=>node.getAttribute("id"))':raise AssertionError(script)
        return [node.get('id') for node in self.nodes]
    def get_by_role(self,role,*,name,exact):
        if role=='textbox' and name=='Label':
            return RadioDom([node for root in self.nodes for node in root.iter()
                if node.get('role')=='textbox' and node.get('aria-label')=='Label'],self.parents)
        result=super().get_by_role(role,name=name,exact=exact);return RadioDom(result.nodes,self.parents)


def widget(count=3,owner=NEW_ID):
    root=ElementTree.Element('section',{'class':'form-builder--item','data-active':'false'})
    profile=choice._profile(authored(count))
    ElementTree.SubElement(root,'div',{'role':'textbox','aria-label':'Label','data-field-type':'RADIO',
        'contenteditable':'true'}).text=profile['tile']+' 104nic'
    for index,value in enumerate(profile['options']):
        identifier=owner+'_'+str(index)
        ElementTree.SubElement(root,'input',{'type':'radio','id':identifier,'name':owner,'disabled':'','value':value})
        ElementTree.SubElement(root,'label',{'id':'option-label-'+owner+'-'+str(index),
            'for':identifier,'contenteditable':'true'}).text=value
    return root


class RadioValidation(unittest.TestCase):
    def test_same_radio_type_selects_measured_single_choice_three_or_yes_no_two_profile(self):
        for count,label in ((3,'Single Choice'),(2,'Yes / No')):
            value=step(count);self.assertEqual(choice.validate(value),value['payload'])
            self.assertEqual(choice._profile(authored(count))['tile'],label)
            self.assertEqual(choice._profile(authored(count))['default_key'],'radio')
    def test_unknown_counts_missing_options_and_transient_yes_no_swap_refuse(self):
        for options in ([],['A'],['A','B','C','D'],['No','Yes']):
            value=step();value['payload']['questions'][0]['options']=options
            with self.subTest(options=options),self.assertRaises(Stop):choice.validate(value)
        value=step();value['payload']['questions'][0].pop('options')
        with self.assertRaises(Stop):choice.validate(value)
    def test_existing_radio_can_explicitly_bind_its_two_or_three_options(self):
        value=step();value['payload']['pages'][0]['questions'][0]['options']=['A','B']
        self.assertEqual(choice.validate(value),value['payload'])


class RadioNativeDom(unittest.TestCase):
    def test_captured_radio_names_ids_label_ids_and_two_three_option_values(self):
        for count in (2,3):
            root=widget(count);surface=RadioDom([root]);options=choice._choices(surface,'RADIO')
            self.assertEqual([option['value'] for option in options],choice._profile(authored(count))['options'])
            self.assertEqual(choice._radio_input_ids(surface),[NEW_ID+'_'+str(index) for index in range(count)])
            self.assertEqual(root[2].get('id'),'option-label-'+NEW_ID+'-0')
            self.assertNotIn('role',root[2].attrib)
    def test_mixed_owner_name_wrong_label_identity_or_unowned_extra_option_refuse(self):
        for defect in ('name','label','extra'):
            root=widget()
            if defect=='name':root[1].set('name',OLD_ID)
            elif defect=='label':root[2].set('id','option-label-'+OLD_ID+'-0')
            else:ElementTree.SubElement(root,'label',{'for':'extra','contenteditable':'true'}).text='Extra'
            with self.subTest(defect=defect),self.assertRaises(Stop):choice._choices(RadioDom([root]),'RADIO')
    def test_new_index_bound_deselected_radio_is_activated_after_exact_native_shape_check(self):
        for count in (2,3):
            surface=RadioDom([widget(count)])
            with patch.object(native,'_append_tile',return_value=surface) as append,patch.object(native,'_activate_item') as activate:
                self.assertIs(choice._append(object(),step(count)['payload'],authored(count)),surface)
            self.assertEqual(append.call_args.args[2],choice._profile(authored(count))['tile'])
            activate.assert_called_once()


class RadioExecution(unittest.TestCase):
    def execute(self,count=3,*,reuse=False,lost=False,collateral=False):
        plan=step(count);page,frame=MagicMock(),MagicMock();page.url=plan['payload']['start_url'];page.frame_locator.return_value=frame
        title,save=MagicMock(),MagicMock();title.count.return_value=1;title.input_value.return_value='Exact quiz'
        save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,**kwargs:title if role=='textbox' else save
        owner=NEW_ID if reuse else OLD_ID
        old={**question(),'_widget_inputs':[{'type':'radio','name':owner,'value':'Old A'}],
             '_radio_input_ids':[owner+'_0',owner+'_1']}
        initial=[[old]];state={'inventory':deepcopy(initial),'writes':0,'saves':0,'reopened':False}
        save.click.side_effect=lambda:state.__setitem__('saves',state['saves']+1)
        def write(*args,**kwargs):
            state['writes']+=1
            new={**authored(count),'_widget_inputs':[{'type':'radio','name':NEW_ID,'value':label} for label in authored(count)['options']],
                '_radio_input_ids':[NEW_ID+'_'+str(index) for index in range(count)]}
            state['inventory'][0][-1]=new
            if collateral:state['inventory'][0][0]['query_key']='Changed old key'
            return deepcopy(new)
        def reopen(*args):
            state['reopened']=True
            if lost:state['inventory']=deepcopy(initial)
        with ExitStack() as stack:
            stack.enter_context(patch.object(choice,'assert_tenant'))
            stack.enter_context(patch.object(native,'_wait_baseline'))
            stack.enter_context(patch.object(choice,'click',side_effect=lambda target:target.click()))
            stack.enter_context(patch.object(choice,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())))
            stack.enter_context(patch.object(choice,'_inventory',side_effect=lambda *args,**kwargs:deepcopy(state['inventory'])))
            def insert(*args,**kwargs):
                state['inventory'][0].append({**question('New native choice','radio','RADIO'),'_widget_inputs':[],
                    '_radio_input_ids':[NEW_ID+'_'+str(index) for index in range(count)]})
                return RadioDom([widget(count)])
            stack.enter_context(patch.object(choice,'_append',side_effect=insert))
            writer=stack.enter_context(patch.object(choice,'_write_question',side_effect=write))
            stack.enter_context(patch.object(native,'reopen_editor',side_effect=reopen))
            try:result=choice.configure(page,plan)
            except Stop as error:return error,state,writer
        return result,state,writer
    def test_same_default_radio_key_on_old_question_survives_new_distinct_uuid_and_final_key(self):
        for count in (2,3):
            result,state,writer=self.execute(count)
            self.assertEqual(result['status'],'QUIZ_MULTIPLE_CHOICES_SAVED_AND_REOPENED')
            self.assertEqual(state['inventory'][0][0]['query_key'],'radio')
            self.assertEqual(state['inventory'][0][1]['query_key'],'priority')
            self.assertEqual(state['saves'],1);self.assertTrue(state['reopened']);writer.assert_called_once()
    def test_reused_native_uuid_refuses_before_question_or_option_authoring(self):
        result,state,writer=self.execute(reuse=True)
        self.assertIsInstance(result,Stop);self.assertEqual(state['writes'],0);self.assertEqual(state['saves'],0)
        writer.assert_not_called()
    def test_collateral_old_identity_or_lost_save_is_not_completion(self):
        for options in ({'collateral':True},{'lost':True}):
            result,state,_=self.execute(**options)
            self.assertIsInstance(result,Stop);self.assertEqual(state['saves'],0 if options.get('collateral') else 1)


if __name__=='__main__':unittest.main()
