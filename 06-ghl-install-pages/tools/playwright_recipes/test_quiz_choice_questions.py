"""CHECKBOX native inventory, authored option values and save/reopen failures."""
from copy import deepcopy
from contextlib import ExitStack
import unittest
import re
from xml.etree import ElementTree
from unittest.mock import MagicMock,patch

import quiz_choice_questions as choice
import quiz_text_questions as text
from skill6_playwright import Stop
from test_quiz_text_questions import question
import test_quiz_text_questions as text_tests
from test_quiz_page_heading_dom import Dom


def new_question():
    return {**question('Which outcomes matter?','outcomes','CHECKBOX'),'options':['Growth','Clarity','Time']}


def step():
    return {'action':'quiz_multiple_choices','payload':{'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ',
        'expected_quiz_name':'Exact quiz','pages':[{'label':'Page 1','questions':[question()]}],
        'target_page':1,'questions':[new_question()],'acknowledge_shared_field_options':True}}


class Validation(unittest.TestCase):
    def test_complete_question_options_and_acknowledgement_are_hash_bound(self):
        self.assertEqual(choice.validate(step()),step()['payload'])
        changed=step();changed['payload']['questions'][0]['options'][1]='Confidence'
        self.assertNotEqual(choice.configuration_hash(changed),choice.configuration_hash(step()))
    def test_non_native_types_duplicate_options_old_keys_and_unacknowledged_changes_refuse(self):
        cases=[]
        for patch_values in ({'field_type':'MULTIPLE_CHOICE'},{'query_key':'radio'},
                             {'options':['A','a','B']},
                             {'options':['A','B']},{'options':['A','B',' C']}):
            value=step();value['payload']['questions'][0].update(patch_values);cases.append(value)
        value=step();value['payload']['acknowledge_shared_field_options']=False;cases.append(value)
        for value in cases:
            with self.subTest(value=value),self.assertRaises(Stop):choice.validate(value)
    def test_transient_option_rename_collision_refuses_before_native_property_write(self):
        value=step();value['payload']['questions'][0]['options']=['Option 2','Option 1','Option 3']
        with self.assertRaisesRegex(Stop,'occupied label'):choice.validate(value)
        with patch.object(choice,'_choices') as read,patch.object(text,'_write_question') as write,self.assertRaises(Stop):
            choice._write_question(MagicMock(),MagicMock(),value['payload']['questions'][0])
        read.assert_not_called();write.assert_not_called()
        choice._option_transition(['New A','Option 1','Option 2'])
    def test_existing_checkbox_requires_exact_options_and_existing_text_default_is_allowed(self):
        value=step();value['payload']['pages'][0]['questions']=[{**new_question(),'query_key':'old_choices','question':'Old question'}]
        choice.validate(value)
        value['payload']['pages'][0]['questions'][0].pop('options')
        with self.assertRaises(Stop):choice.validate(value)
        value=step();value['payload']['pages'][0]['questions']=[question('Existing short','single_line','TEXT')]
        self.assertEqual(choice.validate(value),value['payload'])


class Choices(unittest.TestCase):
    def surface(self):
        item=MagicMock();values=['Option 1','Option 2','Option 3'];fields=[];labels=[]
        prefix='checkbox-aaaaaaaa-1111-4111-8111-111111111111-'
        for index in range(3):
            field,label=MagicMock(),MagicMock();fields.append(field);labels.append(label)
            field.get_attribute.side_effect=lambda key,index=index:{'id':prefix+str(index),'name':'','disabled':''}.get(key)
            field.input_value.side_effect=lambda index=index:values[index]
            label.count.return_value=1;label.is_visible.return_value=True
            label.inner_text.side_effect=lambda index=index:values[index]
            label.fill.side_effect=lambda value,index=index:values.__setitem__(index,value)
        collection=MagicMock();collection.count.return_value=3;collection.nth.side_effect=lambda index:fields[index]
        all_labels=MagicMock();all_labels.count.return_value=3
        def locate(selector):
            if selector=='input[type="checkbox"]':return collection
            if selector=='label[contenteditable][for]':return all_labels
            for index in range(3):
                if selector=='label[contenteditable][for="'+prefix+str(index)+'"]':return labels[index]
            raise AssertionError(selector)
        item.locator.side_effect=locate
        return item,values,fields,labels,all_labels
    def test_identity_is_scoped_by_for_attribute_not_duplicated_global_id(self):
        item,values,_,_,_=self.surface()
        self.assertEqual([row['value'] for row in choice._choices(item)],values)
        self.assertTrue(all(call.args[0]!='#checkbox-aaaaaaaa-1111-4111-8111-111111111111-0'
                            for call in item.locator.call_args_list))
    def test_missing_disabled_mismatched_uuid_label_value_or_extra_option_refuses(self):
        for defect in ('disabled','identity','value','extra'):
            item,_,fields,labels,all_labels=self.surface()
            if defect=='disabled':fields[0].get_attribute.side_effect=lambda key:{'id':'checkbox-aaaaaaaa-1111-4111-8111-111111111111-0','name':''}.get(key)
            elif defect=='identity':fields[1].get_attribute.side_effect=lambda key:{'id':'checkbox-dddddddd-4444-4444-8444-444444444444-1','name':'','disabled':''}.get(key)
            elif defect=='value':labels[0].inner_text.side_effect=None;labels[0].inner_text.return_value='Different'
            else:all_labels.count.return_value=4
            with self.subTest(defect=defect),self.assertRaises(Stop):choice._choices(item)
    def test_all_three_authored_labels_are_read_back_with_sibling_preservation(self):
        item,values,_,labels,_=self.surface();frame=MagicMock();properties={key:new_question()[key] for key in text.PROPERTIES}
        metadata=[{'label':value,'category':'Select category','score':'0','score_enabled':False} for value in choice.OPTIONS]
        def read(*args,**kwargs):return {**properties,'_widget_inputs':[],
            '_choice_controls':[{**row,'label':values[index]} for index,row in enumerate(metadata)],'_choice_switches':[False]*4}
        with patch.object(text,'_write_question',return_value={'_choice_controls':metadata,'_choice_switches':[False]*4}) as write,patch.object(text,'_read_question',side_effect=read), \
                patch.object(choice,'fill',side_effect=lambda label,value:label.fill(value)), \
                patch.object(choice,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())):
            result=choice._write_question(frame,item,new_question())
        self.assertEqual(values,new_question()['options'])
        self.assertEqual(result['options'],values)
        self.assertEqual({key:value for key,value in write.call_args.kwargs.items() if key!='metadata_reader'},
            {'field_types':choice.TYPES,'new_kind':'CHECKBOX','default_key':'checkbox'})
        self.assertTrue(callable(write.call_args.kwargs['metadata_reader']))
        self.assertTrue(all(label.press.call_count==1 for label in labels))
    def test_changed_defaults_do_not_write_question_properties(self):
        item,values,_,_,_=self.surface();values[0]='Changed'
        with patch.object(text,'_write_question') as write,self.assertRaisesRegex(Stop,'differ before authoring'):
            choice._write_question(MagicMock(),item,new_question())
        write.assert_not_called()


class Execution(unittest.TestCase):
    def run_config(self,*,lost=False,collateral=False,bad_before=False):
        page,frame=MagicMock(),MagicMock();page.url=step()['payload']['start_url'];page.frame_locator.return_value=frame
        title,save=MagicMock(),MagicMock();title.count.return_value=1;title.input_value.return_value='Exact quiz'
        save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,**kw:title if role=='textbox' else save
        original=[[{**question(),'_widget_inputs':[]}]];state={'inventory':deepcopy(original),'saves':0,'reopened':False}
        if bad_before:state['inventory'][0][0]['query_key']='wrong'
        save.click.side_effect=lambda:state.__setitem__('saves',state['saves']+1)
        def write(*args):
            authored={**new_question(),'_widget_inputs':[],'_option_identity':[]}
            state['inventory'][0][-1]=authored
            if collateral:state['inventory'][0][0]['question']='Changed sibling'
            return deepcopy(authored)
        def reopen(*args):
            state['reopened']=True
            if lost:state['inventory']=deepcopy(original)
        with ExitStack() as stack:
            stack.enter_context(patch.object(choice,'assert_tenant'))
            stack.enter_context(patch.object(text,'_wait_baseline'))
            stack.enter_context(patch.object(choice,'click',side_effect=lambda target:target.click()))
            stack.enter_context(patch.object(choice,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())))
            stack.enter_context(patch.object(choice,'_inventory',side_effect=lambda *args:deepcopy(state['inventory'])))
            def insert(*args,**kwargs):
                state['inventory'][0].append({**question('Multiple Choice abc12','checkbox','CHECKBOX'),
                    'options':list(choice.OPTIONS),'_widget_inputs':[]})
                return object()
            append=stack.enter_context(patch.object(choice,'_append',side_effect=insert))
            stack.enter_context(patch.object(choice,'_fresh_choice'))
            stack.enter_context(patch.object(choice,'_write_question',side_effect=write))
            stack.enter_context(patch.object(text,'reopen_editor',side_effect=reopen))
            try:receipt=choice.configure(page,step())
            except Stop as error:return error,state,append
        return receipt,state,append
    def test_save_is_independently_reopened_and_receipt_binds_three_choices(self):
        receipt,state,append=self.run_config()
        self.assertEqual(receipt['configuration_sha256'],choice.configuration_hash(step()))
        self.assertEqual(receipt['status'],'QUIZ_MULTIPLE_CHOICES_SAVED_AND_REOPENED')
        self.assertTrue(state['reopened']);self.assertEqual(state['saves'],1);append.assert_called_once()
        self.assertFalse(receipt['submission_verified']);self.assertFalse(receipt['dependency_api_used'])
    def test_existing_drift_or_sibling_mutation_does_not_save(self):
        for options in ({'bad_before':True},{'collateral':True}):
            receipt,state,_=self.run_config(**options)
            self.assertIsInstance(receipt,Stop);self.assertEqual(state['saves'],0)
    def test_lost_save_is_not_reported_as_complete(self):
        receipt,state,_=self.run_config(lost=True)
        self.assertIsInstance(receipt,Stop);self.assertTrue(state['reopened'])


class AppendOwner(unittest.TestCase):
    def test_drag_that_creates_an_extra_page_stops_before_authoring_or_retry(self):
        frame,canvas,state,handle=text_tests.NativeAppend().surface()
        tile=frame.get_by_role.return_value.locator.return_value.filter.return_value
        tile.get_attribute.return_value='Multiple Choice1'
        calls={'owners':0}
        def owners(*args):
            calls['owners']+=1
            if calls['owners']>1:raise Stop('Unexpected new native page')
            return [(object(),canvas)]
        with patch.object(text,'_close_properties'),patch.object(text,'_close_drawer'), \
                patch.object(text,'_owners',side_effect=owners),patch.object(choice,'click'), \
                patch.object(choice,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())), \
                self.assertRaisesRegex(Stop,'Unexpected new native page'):
            choice._append(frame,step()['payload'])
        self.assertEqual(state['drags'],1)


class ChoiceDom(Dom):
    def locator(self,selector):
        result=super().locator(selector)
        required=re.findall(r'\[([A-Za-z_-]+)\]',selector)
        return ChoiceDom([node for node in result.nodes if all(key in node.attrib for key in required)],self.parents)
    def nth(self,index):return ChoiceDom([self.nodes[index]],self.parents)
    def get_attribute(self,key):
        if len(self.nodes)!=1:raise AssertionError('Ambiguous native option DOM')
        return self.nodes[0].get(key)


class CapturedChoiceDom(unittest.TestCase):
    def fixture(self):
        owner=ElementTree.Element('section',{'class':'form-builder--item','data-active':'true'})
        for index,value in enumerate(choice.OPTIONS):
            identifier='checkbox-aaaaaaaa-1111-4111-8111-111111111111-'+str(index)
            ElementTree.SubElement(owner,'input',{'id':identifier,'type':'checkbox','disabled':'','value':value})
            ElementTree.SubElement(owner,'label',{'id':identifier,'for':identifier,'contenteditable':'true'}).text=value
        return owner
    def test_native_duplicate_ids_do_not_make_scoped_input_and_label_identity_ambiguous(self):
        owner=self.fixture();surface=ChoiceDom([owner])
        self.assertEqual(surface.locator('[id="checkbox-aaaaaaaa-1111-4111-8111-111111111111-0"]').count(),2)
        actual=choice._choices(surface)
        self.assertEqual([option['value'] for option in actual],choice.OPTIONS)
        self.assertNotIn('name',owner[0].attrib)
    def test_real_dom_value_label_mismatch_and_uneditable_option_refuse(self):
        for mutation in ('value','editable','owner'):
            owner=self.fixture()
            if mutation=='value':owner[0].set('value','Wrong')
            elif mutation=='editable':owner[1].attrib.pop('contenteditable')
            else:owner[2].set('id','checkbox-dddddddd-4444-4444-8444-444444444444-1')
            with self.subTest(mutation=mutation),self.assertRaises(Stop):choice._choices(ChoiceDom([owner]))


class ChoiceMetadata(unittest.TestCase):
    def test_new_choice_stale_option_owner_or_nonzero_enabled_score_refuses_before_property_writes(self):
        defaults=[{'label':value,'score':'0','score_enabled':False} for value in choice.OPTIONS]
        for mutation in ({'label':'Other owner'},{'score':'10'},{'score_enabled':True}):
            rows=deepcopy(defaults);rows[0].update(mutation)
            with self.subTest(mutation=mutation),patch.object(choice,'_metadata',return_value={'_choice_controls':rows}),self.assertRaises(Stop):
                choice._default_metadata(MagicMock(),'CHECKBOX',choice.OPTIONS)
    def test_property_writer_refuses_collateral_score_metadata_changes(self):
        helper=text_tests.NativeQuestionProperties();frame,item,_,_=helper.surface()
        captures=iter(({'_choice_controls':[{'score':'0'}]},{'_choice_controls':[{'score':'10'}]}))
        with helper.context(),self.assertRaisesRegex(Stop,'preserved native choice metadata'):
            text._write_question(frame,item,text_tests.step()['payload']['questions'][0],
                                 metadata_reader=lambda *_:next(captures))
    def test_category_score_and_all_four_false_switch_states_are_preserved_read_only(self):
        frame=MagicMock();switches=frame.get_by_role.return_value;switches.count.return_value=4
        switch=MagicMock();switch.count.return_value=1;switch.is_visible.return_value=True;switch.get_attribute.return_value='false'
        switches.nth.return_value=switch
        rows=[{'label':value,'category':'Select category','score':'0','score_enabled':False} for value in choice.OPTIONS]
        with patch.object(text,'_radio_options',return_value=rows):result=choice._metadata(frame,'CHECKBOX')
        self.assertEqual(result,{'_choice_controls':rows,'_choice_switches':[False]*4})
        switch.click.assert_not_called()
    def test_active_jump_or_spread_and_unowned_switch_are_not_silently_omitted(self):
        for state,count in (('true',4),('false',5),('mixed',4)):
            frame=MagicMock();switches=frame.get_by_role.return_value;switches.count.return_value=count
            switch=MagicMock();switch.count.return_value=1;switch.is_visible.return_value=True;switch.get_attribute.return_value=state
            switches.nth.return_value=switch
            with self.subTest(state=state,count=count),patch.object(text,'_radio_options',return_value=[{}]*3),self.assertRaises(Stop):
                choice._metadata(frame,'CHECKBOX')


if __name__=='__main__':unittest.main()
