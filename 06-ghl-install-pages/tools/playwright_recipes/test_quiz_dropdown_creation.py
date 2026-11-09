"""Quiz Single Dropdown has no Hidden/Spread controls and scoped option IDs."""
from copy import deepcopy
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree

import quiz_choice_questions as choice
import quiz_text_questions as native
import quiz_written_questions as written
from skill6_playwright import Stop
import test_quiz_text_questions as text_tests
from test_quiz_radio_creation import RadioDom,NEW_ID,OLD_ID


def authored():
    value={**text_tests.question('Select your priority','priority','SINGLE_OPTIONS'),
           'options':['Growth','Clarity','Time']}
    value.pop('hidden');return value


def step():
    return {'action':'quiz_multiple_choices','payload':{'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ',
        'expected_quiz_name':'Exact quiz','pages':[{'label':'Page 1','questions':[text_tests.question()]}],
        'target_page':1,'questions':[authored()],'acknowledge_shared_field_options':True}}


def widget(owner=NEW_ID):
    root=ElementTree.Element('section',{'class':'form-builder--item','data-active':'true'})
    ElementTree.SubElement(root,'div',{'role':'textbox','aria-label':'Label','data-field-type':'SINGLE_OPTIONS',
        'contenteditable':'true'}).text='Single Dropdown 42abx'
    ElementTree.SubElement(root,'input',{'class':'dropdown-input form-placeholder','value':''})
    card=ElementTree.SubElement(root,'div',{'id':'options-card'})
    for index,value in enumerate(choice.OPTIONS):
        row=ElementTree.SubElement(card,'div',{'class':'option'})
        ElementTree.SubElement(row,'label',{'id':'option-label-'+owner+'-'+str(index),
            'for':owner+'_'+str(index),'contenteditable':'true'}).text=value
    return root


class DropdownValidation(unittest.TestCase):
    def test_dropdown_schema_omits_hidden_and_binds_exact_three_authored_options(self):
        self.assertEqual(choice.validate(step()),step()['payload'])
        self.assertEqual(choice._profile(authored()),{'tile':'Single Dropdown','suffix':5,'default_key':'dropdown','options':choice.OPTIONS})
        for hidden in (False,True,None):
            value=step();value['payload']['questions'][0]['hidden']=hidden
            with self.subTest(hidden=hidden),self.assertRaises(Stop):choice.validate(value)
    def test_written_front_door_preserves_existing_dropdown_with_no_hidden_field(self):
        value={'action':'quiz_written_answers','payload':deepcopy(step()['payload'])}
        value['payload'].pop('acknowledge_shared_field_options')
        value['payload']['pages'][0]['questions']=[authored()]
        value['payload']['questions']=[text_tests.question('Another question','another_key','TEXT')]
        self.assertEqual(written.validate(value),value['payload'])
        value['payload']['pages'][0]['questions'][0].pop('options')
        with self.assertRaises(Stop):written.validate(value)


class DropdownDom(unittest.TestCase):
    def test_property_options_from_another_owner_cannot_bless_matching_canvas_labels(self):
        frame,canvas,items=MagicMock(),MagicMock(),MagicMock();surface=RadioDom([widget()])
        items.count.return_value=1;items.nth.return_value=surface
        record={key:value for key,value in authored().items() if key!='options'}
        record.update(_widget_inputs=[],_choice_controls=[{'label':'Different owner'}]*3,_choice_switches=[False]*3)
        with patch.object(native,'_prepare_inventory'), \
                patch.object(native,'_owners',return_value=[(object(),canvas)]),patch.object(native,'_items',return_value=items), \
                patch.object(native,'_read_question',return_value=record),patch.object(native,'_activate_item'), \
                self.assertRaisesRegex(Stop,'exact canvas choice owner'):
            choice._inventory(frame,step()['payload'])
    def test_real_option_card_labels_are_bound_to_the_selected_widget_and_native_uuid(self):
        surface=RadioDom([widget()]);actual=choice._choices(surface,'SINGLE_OPTIONS')
        self.assertEqual(actual,[{'id':NEW_ID+'_'+str(index),'value':value} for index,value in enumerate(choice.OPTIONS)])
    def test_inactive_owner_wrong_label_uuid_or_extra_option_refuses(self):
        for defect in ('inactive','identity','extra'):
            root=widget()
            if defect=='inactive':root.set('data-active','false')
            elif defect=='identity':root[2][1][0].set('for',OLD_ID+'_1')
            else:
                row=ElementTree.SubElement(root[2],'div',{'class':'option'})
                ElementTree.SubElement(row,'label',{'contenteditable':'true'}).text='Extra'
            with self.subTest(defect=defect),self.assertRaises(Stop):choice._choices(RadioDom([root]),'SINGLE_OPTIONS')
    def test_deselected_new_dropdown_is_activated_before_its_scoped_options_are_read(self):
        root=widget();root.set('data-active','false');surface=RadioDom([root])
        with patch.object(native,'_append_tile',return_value=surface), \
                patch.object(native,'_activate_item',side_effect=lambda *_:root.set('data-active','true')):
            self.assertIs(choice._append(object(),step()['payload'],authored()),surface)
    def test_fresh_dropdown_uuid_cannot_reuse_a_prior_radio_or_checkbox_owner(self):
        for old in ({'_radio_input_ids':[NEW_ID+'_0'],'_widget_inputs':[]},
                    {'_option_identity':[{'id':'checkbox-'+NEW_ID+'-0','value':'A'}],'_widget_inputs':[]},
                    {'_widget_inputs':[{'name':NEW_ID}]}):
            with self.subTest(old=old),self.assertRaisesRegex(Stop,'reused'):
                choice._fresh_choice(RadioDom([widget()]),'SINGLE_OPTIONS',[[old]])
        choice._fresh_choice(RadioDom([widget()]),'SINGLE_OPTIONS',[[{'_widget_inputs':[{'name':OLD_ID}]}]])


class DropdownProperties(unittest.TestCase):
    def test_option_writer_uses_scoped_native_labels_and_preserves_category_score_and_jump_metadata(self):
        root=widget();surface=RadioDom([root]);properties={key:value for key,value in authored().items() if key!='options'}
        controls=[{'label':value,'category':'Select category','score':'0','score_enabled':False} for value in choice.OPTIONS]
        def read(*args,**kwargs):
            return {**properties,'_widget_inputs':[],
                '_choice_controls':[{**value,'label':root[2][index][0].text} for index,value in enumerate(controls)],
                '_choice_switches':[False]*3}
        with patch.object(native,'_write_question',return_value={'_choice_controls':controls,'_choice_switches':[False]*3}), \
                patch.object(native,'_read_question',side_effect=read),patch.object(native,'_activate_item'), \
                patch.object(choice,'fill',side_effect=lambda label,value:setattr(label.nodes[0],'text',value)), \
                patch.object(RadioDom,'press',create=True), \
                patch.object(choice,'wait_until',side_effect=lambda predicate,reason:self.assertTrue(predicate())):
            result=choice._write_question(MagicMock(),surface,authored())
        self.assertEqual(result['options'],authored()['options']);self.assertNotIn('hidden',result)
        self.assertEqual(result['_choice_switches'],[False]*3)
    def test_actual_property_writer_authors_required_and_never_invents_or_accesses_hidden(self):
        helper=text_tests.NativeQuestionProperties();frame,item,values,state=helper.surface(query='dropdown')
        values.update(field_type='SINGLE_OPTIONS',question='Single Dropdown 42abx')
        label=item.get_by_role.return_value;label.get_attribute.return_value='SINGLE_OPTIONS'
        hidden=frame.locator(native.FLAGS['hidden']);hidden.count.return_value=0
        desired={key:value for key,value in authored().items() if key!='options'}
        with helper.context():
            actual=native._write_question(frame,item,desired,field_types=choice.TYPES,
                new_kind='SINGLE_OPTIONS',default_key='dropdown')
        self.assertEqual({key:actual[key] for key in native.properties_for('SINGLE_OPTIONS')},desired)
        self.assertNotIn('hidden',actual);hidden.click.assert_not_called();hidden.get_attribute.assert_not_called()
    def test_unexpected_hidden_control_stops_before_property_mutation(self):
        helper=text_tests.NativeQuestionProperties();frame,item,values,state=helper.surface(query='dropdown')
        values.update(field_type='SINGLE_OPTIONS',question='Single Dropdown 42abx')
        item.get_by_role.return_value.get_attribute.return_value='SINGLE_OPTIONS'
        with helper.context(),self.assertRaisesRegex(Stop,'Hidden control'):
            native._write_question(frame,item,{key:value for key,value in authored().items() if key!='options'},
                field_types=choice.TYPES,new_kind='SINGLE_OPTIONS',default_key='dropdown')
        self.assertEqual(state['fills'],0)
    def test_three_jump_switches_are_preserved_and_a_spread_or_hidden_extra_is_not_invented(self):
        frame=MagicMock();switches=frame.get_by_role.return_value;switches.count.return_value=3
        switch=MagicMock();switch.count.return_value=1;switch.is_visible.return_value=True;switch.get_attribute.return_value='false'
        switches.nth.return_value=switch
        with patch.object(native,'_radio_options',return_value=[{}]*3):
            self.assertEqual(choice._metadata(frame,'SINGLE_OPTIONS')['_choice_switches'],[False]*3)
            switches.count.return_value=4
            with self.assertRaises(Stop):choice._metadata(frame,'SINGLE_OPTIONS')


if __name__=='__main__':unittest.main()
