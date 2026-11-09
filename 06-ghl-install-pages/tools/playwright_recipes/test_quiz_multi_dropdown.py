"""Multi Dropdown owns an explicit native Unique Key, not a Query Key alias."""
from copy import deepcopy
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree

import quiz_choice_questions as choice
import quiz_text_questions as native
import quiz_written_questions as written
from skill6_playwright import Stop
from test_quiz_choice_questions import step as base_step
from test_quiz_radio_creation import RadioDom,NEW_ID
import test_quiz_text_questions as text_tests
from test_quiz_dropdown_creation import widget


def authored(count=3):
    return {'field_type':'MULTIPLE_OPTIONS','question':'Select every priority','placeholder':'Choose priorities',
        'short_label':'Priorities','unique_key':'brand_priorities','required':True,
        'options':['Growth','Clarity','Time','Team','Revenue'][:count]}


def step(count=3):
    value=base_step();value['payload']['questions']=[authored(count)];return value


class MultiValidation(unittest.TestCase):
    def test_explicit_unique_key_without_hidden_or_query_key_and_variable_options_are_bound(self):
        for count in (2,3,4,5):
            value=step(count);self.assertEqual(choice.validate(value),value['payload'])
        digest=choice.configuration_hash(step())
        value=step();value['payload']['questions'][0]['unique_key']='another_key'
        self.assertNotEqual(choice.configuration_hash(value),digest)
    def test_blank_new_key_placeholder_alias_query_key_hidden_or_wrong_option_counts_refuse(self):
        for changes in ({'unique_key':''},{'query_key':'dropdown'},{'hidden':False},
                        {'unique_key_placeholder':'generated_hint'},{'options':['A']},
                        {'options':['A']*4}):
            value=step();value['payload']['questions'][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(Stop):choice.validate(value)
    def test_actual_key_namespaces_are_distinct_and_blank_old_key_is_not_placeholder_identity(self):
        value=step();value['payload']['questions'][0]['unique_key']='radio'
        self.assertEqual(choice.validate(value),value['payload'])
        old={**authored(),'question':'Prior multiple choices','unique_key':''}
        value=step();value['payload']['pages'][0]['questions']=[old]
        self.assertEqual(choice.validate(value),value['payload'])
        old['unique_key']='BRAND_PRIORITIES'
        with self.assertRaises(Stop):choice.validate(value)
    def test_written_front_door_can_preserve_existing_multi_dropdown_without_query_alias(self):
        value=text_tests.step();value['action']='quiz_written_answers'
        value['payload']['pages'][0]['questions']=[{**authored(),'question':'Existing multi','unique_key':''}]
        self.assertEqual(written.validate(value),value['payload'])


class AdvancedSurface:
    def __init__(self):
        helper=text_tests.NativeQuestionProperties();self.helper=helper
        self.frame,self.item,self.values,self.state=helper.surface(query='unused')
        self.values.update(field_type='MULTIPLE_OPTIONS',question='Multi Dropdown 7abc')
        self.item.get_by_role.return_value.get_attribute.return_value='MULTIPLE_OPTIONS'
        self.frame.locator(native.FLAGS['hidden']).count.return_value=0
        self.frame.locator(native.FIELD_INPUTS['query_key']).count.return_value=0
        self.advanced={'open':False,'key':'','name':'Multi Dropdown 7abc','placeholder':'multi_dropdown_7_abc','opens':0}
        self.unique,self.name,self.header=MagicMock(),MagicMock(),MagicMock()
        for control in (self.unique,self.name):
            control.count.side_effect=lambda:int(self.advanced['open']);control.is_visible.side_effect=lambda:self.advanced['open']
        self.unique.input_value.side_effect=lambda:self.advanced['key']
        self.unique.get_attribute.side_effect=lambda name:self.advanced['placeholder'] if name=='placeholder' else None
        self.unique.fill.side_effect=lambda value:self.advanced.__setitem__('key',value)
        self.name.input_value.side_effect=lambda:self.advanced['name']
        self.header.count.return_value=1;self.header.is_visible.return_value=True
        def expand():self.advanced['open']=True;self.advanced['opens']+=1
        self.header.click.side_effect=expand
        old_locator=self.frame.locator.side_effect
        def locate(selector):
            if selector=='#uniqueKey input':return self.unique
            if selector=='#custom-field-label input':return self.name
            if selector=='div.n-collapse-item__header-main:visible':
                node=MagicMock();node.filter.return_value=self.header;return node
            return old_locator(selector)
        self.frame.locator.side_effect=locate
        gear=self.frame.get_by_role('button',name='Open settings',exact=True);old_open=gear.click.side_effect
        def open_properties():old_open();self.advanced['open']=False
        gear.click.side_effect=open_properties
    def write(self):
        properties={key:value for key,value in authored().items() if key!='options'}
        with self.helper.context():
            return native._write_question(self.frame,self.item,properties,field_types=choice.TYPES,
                new_kind='MULTIPLE_OPTIONS',default_key='')


class AdvancedIdentity(unittest.TestCase):
    def test_retained_metadata_cannot_change_between_resize_and_first_property_write(self):
        ui=AdvancedSurface();properties={key:value for key,value in authored().items() if key!='options'}
        original=[{'label':label,'category':'Select category','score':'0','score_enabled':False} for label in choice.OPTIONS]
        changed=deepcopy(original);changed[0]['category']='Unexpected category'
        with ui.helper.context(),self.assertRaisesRegex(Stop,'identity metadata changed before property'):
            native._write_question(ui.frame,ui.item,properties,field_types=choice.TYPES,
                new_kind='MULTIPLE_OPTIONS',default_key='',
                metadata_reader=lambda *_:{'_choice_controls':changed,'_choice_switches':[False]*3},
                expected_metadata={'_choice_controls':original,'_choice_switches':[False]*3})
        self.assertEqual(ui.state['fills'],0);ui.unique.fill.assert_not_called()
    def test_pre_resize_identity_metadata_must_still_match_before_any_question_property_write(self):
        ui=AdvancedSurface();properties={key:value for key,value in authored().items() if key!='options'}
        with ui.helper.context(),self.assertRaisesRegex(Stop,'identity metadata changed before property'):
            native._write_question(ui.frame,ui.item,properties,field_types=choice.TYPES,
                new_kind='MULTIPLE_OPTIONS',default_key='',expected_metadata={'_custom_field_name':'Different original field'})
        self.assertEqual(ui.state['fills'],0);ui.unique.fill.assert_not_called()
    def test_actual_property_controls_expand_each_fresh_panel_and_preserve_name_and_placeholder(self):
        ui=AdvancedSurface();actual=ui.write()
        self.assertEqual(actual['unique_key'],'brand_priorities');self.assertNotIn('query_key',actual);self.assertNotIn('hidden',actual)
        self.assertEqual(actual['_custom_field_name'],'Multi Dropdown 7abc')
        self.assertEqual(actual['_unique_key_placeholder'],'multi_dropdown_7_abc')
        self.assertEqual(ui.advanced['opens'],3)
        ui.name.fill.assert_not_called();ui.name.click.assert_called_once()
    def test_already_visible_advanced_identity_is_read_without_toggling_it_closed(self):
        ui=AdvancedSurface();ui.advanced['open']=True
        with ui.helper.context():_,_,metadata=native._advanced_identity(ui.frame)
        self.assertEqual(metadata['_custom_field_name'],ui.advanced['name']);ui.header.click.assert_not_called()
    def test_unrequested_custom_field_name_change_is_refused_before_unique_key_write(self):
        ui=AdvancedSurface();control=ui.frame.locator(native.FIELD_INPUTS['question']);fill=control.fill.side_effect
        def alter_name(value):fill(value);ui.advanced['name']='Unexpected renamed schema'
        control.fill.side_effect=alter_name
        with self.assertRaisesRegex(Stop,'protected Custom Field Name'):ui.write()
        ui.unique.fill.assert_not_called()
    def test_key_input_refusal_or_placeholder_change_is_not_accepted(self):
        for defect in ('value','placeholder'):
            ui=AdvancedSurface()
            if defect=='value':ui.unique.fill.side_effect=lambda value:None
            else:
                def change(value):ui.advanced['key']=value;ui.advanced['placeholder']='Changed hint'
                ui.unique.fill.side_effect=change
            with self.subTest(defect=defect),self.assertRaises(Stop):ui.write()


class MultiDom(RadioDom):
    def locator(self,selector):
        if selector=='#options-card .option':return super().locator('#options-card').locator('.option')
        return super().locator(selector)


class MultiOptionSurface:
    def __init__(self,*,uncertain=False,extra=False,drift=False,wrong_icon=False):
        self.root=widget();self.root[0].set('data-field-type','MULTIPLE_OPTIONS');self.root[0].text='Multi Dropdown 7abc'
        self.card=self.root[2];self.counts={'add':0,'delete':0}
        self.uncertain,self.extra,self.drift,self.wrong_icon=uncertain,extra,drift,wrong_icon
        for row in self.card:self.trash(row)
        ElementTree.SubElement(self.root,'button',{'id':'add-option'}).text='Add option'
        self.surface=MultiDom([self.root])
    def trash(self,row):
        svg=ElementTree.SubElement(row,'svg',{'class':'ml-2 cursor-pointer'})
        ElementTree.SubElement(svg,'path',{'d':'M1 1' if self.wrong_icon else 'M16 6v-.8 m2 5.5v5m4-5v5'})
    def click(self,control):
        node=control.nodes[0]
        if node.get('id')=='add-option':
            self.counts['add']+=1
            if self.uncertain:return
            for _ in range(2 if self.extra else 1):
                index=len(self.card);row=ElementTree.SubElement(self.card,'div',{'class':'option'})
                ElementTree.SubElement(row,'label',{'for':NEW_ID+'_'+str(index),
                    'id':'option-label-'+NEW_ID+'-'+str(index),'contenteditable':'true'}).text='Option '+str(index+1)
                self.trash(row)
            if self.drift:self.card[0][0].text='Changed retained choice'
        else:
            self.counts['delete']+=1
            row=next(row for row in self.card if node in list(row))
            self.card.remove(row)
    def resize(self,count):
        def wait(predicate,reason):
            if not predicate():raise Stop(reason)
        def snapshot(*args,**kwargs):
            return {'field_type':'MULTIPLE_OPTIONS','question':'Multi Dropdown 7abc','placeholder':'','short_label':'',
                'unique_key':'','required':False,'_widget_inputs':[],
                '_custom_field_name':'Multi Dropdown 7abc','_unique_key_placeholder':'multi_dropdown_7_abc',
                '_choice_controls':[{'label':row[0].text,'category':'Select category','score':'0','score_enabled':False} for row in self.card],
                '_choice_switches':[False]*len(self.card)}
        with patch.object(choice,'click',side_effect=self.click),patch.object(choice,'wait_until',side_effect=wait), \
                patch.object(native,'_activate_item'),patch.object(native,'_read_question',side_effect=snapshot):
            options,_=choice._resize_multi(MagicMock(),self.surface,count)
            return options


class VariableOptions(unittest.TestCase):
    def test_captured_add_delete_exact_deltas_and_same_uuid_indices(self):
        ui=MultiOptionSurface();options=ui.resize(5)
        self.assertEqual(ui.counts,{'add':2,'delete':0})
        self.assertEqual([option['value'] for option in options],['Option '+str(index+1) for index in range(5)])
        self.assertEqual(options[-1]['id'],NEW_ID+'_4')
        options=ui.resize(2);self.assertEqual(len(options),2);self.assertEqual(ui.counts['delete'],3)
    def test_uncertain_extra_row_or_retained_drift_never_retries_add(self):
        for change in ({'uncertain':True},{'extra':True},{'drift':True}):
            ui=MultiOptionSurface(**change)
            with self.subTest(change=change),self.assertRaises(Stop):ui.resize(4)
            self.assertEqual(ui.counts['add'],1)
    def test_unmeasured_delete_glyph_stops_without_a_click(self):
        ui=MultiOptionSurface(wrong_icon=True)
        with self.assertRaisesRegex(Stop,'trash glyph'):ui.resize(2)
        self.assertEqual(ui.counts['delete'],0)


class MultiWriterChain(unittest.TestCase):
    def execute(self,*,changed_name=False,resize_drift=None,target=4,observed=None):
        ui=MultiOptionSurface();desired=authored(target);state={'authored':False,'property_calls':0}
        protected={'_custom_field_name':'Multi Dropdown 7abc','_unique_key_placeholder':'multi_dropdown_7_abc'}
        def controls():
            rows=[{'label':row[0].text,'category':'Select category','score':'0','score_enabled':False} for row in ui.card]
            if (ui.counts['add'] or ui.counts['delete']) and resize_drift in ('category','score','score_enabled'):
                rows[0].update({resize_drift:{'category':'Unexpected category','score':'0.00','score_enabled':True}[resize_drift]})
            if ui.counts['add'] and resize_drift=='new_category':rows[-1]['category']='Unexpected new category'
            return rows
        def snapshot(*args,**kwargs):
            properties=({key:value for key,value in desired.items() if key!='options'} if state['authored'] else
                {'field_type':'MULTIPLE_OPTIONS','question':'Multi Dropdown 7abc','placeholder':'','short_label':'','unique_key':'','required':False})
            metadata=deepcopy(protected)
            if changed_name and ui.card[0][0].text=='Growth':metadata['_custom_field_name']='Unrequested name'
            switches=[False]*len(ui.card)
            if (ui.counts['add'] or ui.counts['delete']) and resize_drift=='jump':switches[0]=True
            if ui.counts['add'] and resize_drift=='new_jump':switches[-1]=True
            return {**properties,**metadata,'_widget_inputs':[],
                '_choice_controls':controls(),'_choice_switches':switches}
        frame=MagicMock();switches=frame.get_by_role.return_value;switches.count.side_effect=lambda:len(ui.card)
        flag=MagicMock();flag.count.return_value=1;flag.is_visible.return_value=True;flag.get_attribute.return_value='false'
        switches.nth.return_value=flag
        def author(_frame,_item,properties,**kwargs):
            state['property_calls']+=1
            self.assertEqual(kwargs['default_key'],'');self.assertEqual(kwargs['expected_metadata'],snapshot())
            self.assertNotIn('query_key',properties);self.assertNotIn('hidden',properties)
            self.assertEqual(kwargs['metadata_reader'](frame,'MULTIPLE_OPTIONS')['_choice_controls'],controls())
            state['authored']=True;ui.root[0].text=properties['question']
            return snapshot()
        def wait(predicate,reason):
            if not predicate():raise Stop(reason)
        with patch.object(native,'_read_question',side_effect=snapshot),patch.object(native,'_write_question',side_effect=author), \
                patch.object(native,'_radio_options',side_effect=lambda _:controls()),patch.object(native,'_activate_item'), \
                patch.object(choice,'click',side_effect=ui.click),patch.object(choice,'wait_until',side_effect=wait), \
                patch.object(choice,'fill',side_effect=lambda label,value:setattr(label.nodes[0],'text',value)), \
                patch.object(RadioDom,'press',create=True):
            try:result=choice._write_question(frame,ui.surface,desired)
            finally:
                if observed is not None:observed.update(property_calls=state['property_calls'],**ui.counts)
        return result,ui
    def test_resize_then_exact_unique_property_authoring_then_canvas_labels_preserve_all_metadata(self):
        result,ui=self.execute()
        self.assertEqual(ui.counts,{'add':1,'delete':0});self.assertEqual(result['options'],authored(4)['options'])
        self.assertEqual(result['unique_key'],'brand_priorities');self.assertNotIn('query_key',result);self.assertNotIn('hidden',result)
        self.assertEqual(result['_choice_switches'],[False]*4)
    def test_options_cannot_silently_change_custom_field_name(self):
        with self.assertRaisesRegex(Stop,'protected native custom-field'):self.execute(changed_name=True)
    def test_add_retains_every_old_category_raw_score_enabled_state_and_jump_before_properties(self):
        for drift in ('category','score','score_enabled','jump','new_category','new_jump'):
            observed={}
            with self.subTest(drift=drift),self.assertRaises(Stop):self.execute(resize_drift=drift,observed=observed)
            self.assertEqual(observed,{'property_calls':0,'add':1,'delete':0})
    def test_delete_retains_the_complete_metadata_prefix_before_properties(self):
        for drift in ('category','score','score_enabled','jump'):
            observed={}
            with self.subTest(drift=drift),self.assertRaises(Stop):self.execute(resize_drift=drift,target=2,observed=observed)
            self.assertEqual(observed,{'property_calls':0,'add':0,'delete':1})


if __name__=='__main__':unittest.main()
