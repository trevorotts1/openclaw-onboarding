"""New local TEXT questions retain exact page/query identities and no-retry flow."""
from copy import deepcopy
import unittest
from unittest.mock import MagicMock,patch

import quiz_text_questions as text
import skill6_playwright as runner


def question(name='Existing choice',key='radio',kind='RADIO'):
    return {'field_type':kind,'question':name,'placeholder':'','short_label':'',
            'query_key':key,'required':False,'hidden':False}


def step():
    return {'action':'quiz_short_answers','payload':{'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ',
        'expected_quiz_name':'Exact quiz','pages':[{'label':'Page 1','questions':[question()]}],
        'target_page':1,'questions':[{**question('What should we know?','context','TEXT'),
                                    'placeholder':'Type your answer','short_label':'Context','required':True}]}}


def inventory():
    return [[{**question(),'_widget_inputs':[{'tag':'INPUT','name':'RADIO_ID','type':'radio','value':'A','placeholder':None}],
        '_radio_options':[{'label':'Option A','category':'Overall Only','score':'12.5','score_enabled':True}]}]]


class TextValidation(unittest.TestCase):
    def test_complete_existing_and_authored_short_answer_inventory_is_retained(self):
        self.assertEqual(text.validate(step()),step()['payload'])
    def test_query_label_collision_reserved_default_and_unseen_type_refuse(self):
        for change in ({'query_key':'radio'},{'question':'Existing choice'},
                       {'field_type':'LARGE_TEXT'},{'field_type':[]},{'required':'true'}):
            value=step();value['payload']['questions'][0].update(change)
            with self.subTest(change=change),self.assertRaises(runner.Stop):text.validate(value)
    def test_native_default_query_key_is_not_an_artificial_reservation(self):
        value=step();value['payload']['pages'][0]['questions'][0].update(field_type='TEXT',query_key='single_line')
        self.assertEqual(text.validate(value),value['payload'])
        value=step();value['payload']['questions'][0]['query_key']='single_line'
        self.assertEqual(text.validate(value),value['payload'])
    def test_full_page_count_owner_and_field_schema_are_required(self):
        for change in ({'target_page':2},{'target_page':True},{'pages':[]},{'expected_quiz_name':''}):
            value=step();value['payload'].update(change)
            with self.subTest(change=change),self.assertRaises(runner.Stop):text.validate(value)
        value=step();value['payload']['pages'][0]['questions'][0].pop('query_key')
        with self.assertRaises(runner.Stop):text.validate(value)
    def test_uncaptured_native_width_or_wrapper_cannot_be_omitted_from_full_inventory(self):
        canvas=MagicMock();known=MagicMock();all_wrappers=MagicMock()
        known.count.return_value=1;all_wrappers.count.return_value=2
        canvas.locator.side_effect=lambda selector:known if selector==text.ITEMS else all_wrappers
        with self.assertRaisesRegex(runner.Stop,'uncaptured question width/wrapper'):text._items(canvas)
    def test_hash_binds_question_properties_page_and_exact_editor(self):
        digest=text.configuration_hash(step())
        for key,value in (('target_page',1),('expected_quiz_name','Other quiz')):
            changed=step();changed['payload'][key]=value
            if value==step()['payload'][key]:continue
            self.assertNotEqual(text.configuration_hash(changed),digest)
        changed=step();changed['payload']['questions'][0]['hidden']=True
        self.assertNotEqual(text.configuration_hash(changed),digest)


class TextExecution(unittest.TestCase):
    def surface(self,*,lost=False,collateral=False,bad_before=False):
        page,frame=MagicMock(),MagicMock();page.url=step()['payload']['start_url'];page.frame_locator.return_value=frame
        title=MagicMock();title.count.return_value=1;title.input_value.return_value='Exact quiz'
        save=MagicMock();save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        state={'inventory':inventory(),'saves':0,'reopened':False,'writes':0}
        if bad_before:state['inventory'][0][0]['query_key']='wrong'
        save.click.side_effect=lambda:state.__setitem__('saves',state['saves']+1)
        frame.get_by_role.side_effect=lambda role,**kw:title if role=='textbox' else save
        def authored(_frame,_item,question):
            state['writes']+=1
            row={**deepcopy(question),'_widget_inputs':[{'tag':'INPUT','name':None,'type':None,'value':'','placeholder':question['placeholder']}]}
            state['inventory'][0][-1]=row
            if collateral:state['inventory'][0][0]['placeholder']='Changed sibling'
            return deepcopy(row)
        def reopen(*args):
            state['reopened']=True
            if lost:state['inventory']=inventory()
        return page,state,authored,reopen
    def execute(self,page,state,authored,reopen,plan=None):
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.object(text,'assert_tenant'))
            stack.enter_context(patch.object(text,'_wait_baseline'))
            stack.enter_context(patch.object(text,'click',side_effect=lambda loc:loc.click()))
            stack.enter_context(patch.object(text,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())))
            stack.enter_context(patch.object(text,'_inventory',side_effect=lambda frame,plan:deepcopy(state['inventory'])))
            def insert(*args,**kwargs):
                row={**question('Short Answer def456','single_line','TEXT'),'_widget_inputs':[]}
                if state.get('misplaced'):state['inventory'][0].insert(0,row)
                else:state['inventory'][0].append(row)
                return object()
            append=stack.enter_context(patch.object(text,'_append',side_effect=insert))
            stack.enter_context(patch.object(text,'_write_question',side_effect=authored))
            stack.enter_context(patch.object(text,'reopen_editor',side_effect=reopen))
            receipt=text.configure(page,plan or step())
        return receipt,append
    def test_one_append_no_global_field_schema_and_independent_complete_readback(self):
        page,state,authored,reopen=self.surface()
        receipt,append=self.execute(page,state,authored,reopen)
        append.assert_called_once();self.assertEqual(state['writes'],1);self.assertEqual(state['saves'],1)
        self.assertTrue(state['reopened']);self.assertEqual(receipt['question_count'],1)
        self.assertFalse(receipt['dependency_api_used']);self.assertFalse(receipt['submission_verified'])
    def test_changed_existing_query_or_collateral_sibling_never_reaches_save(self):
        for params in ({'bad_before':True},{'collateral':True}):
            page,state,authored,reopen=self.surface(**params)
            with self.subTest(params=params),self.assertRaises(runner.Stop):self.execute(page,state,authored,reopen)
            self.assertEqual(state['saves'],0)
    def test_lost_persisted_question_is_not_completion(self):
        page,state,authored,reopen=self.surface(lost=True)
        with self.assertRaisesRegex(runner.Stop,'did not persist'):self.execute(page,state,authored,reopen)
        self.assertTrue(state['reopened'])
    def test_existing_default_text_key_is_preserved_while_new_index_gets_distinct_authored_key(self):
        page,state,authored,reopen=self.surface();plan=step()
        state['inventory'][0][0].update(field_type='TEXT',query_key='single_line')
        plan['payload']['pages'][0]['questions'][0].update(field_type='TEXT',query_key='single_line')
        receipt,_=self.execute(page,state,authored,reopen,plan)
        self.assertEqual(receipt['status'],'QUIZ_SHORT_ANSWERS_SAVED_AND_REOPENED')
        self.assertEqual(state['inventory'][0][0]['query_key'],'single_line')
        self.assertEqual(state['inventory'][0][1]['query_key'],'context')
    def test_misplaced_new_default_text_cannot_author_the_old_default_text_at_last_index(self):
        page,state,authored,reopen=self.surface();plan=step();state['misplaced']=True
        old=question('Short Answer abc123','single_line','TEXT')
        state['inventory'][0][0]={**old,'_widget_inputs':[]};plan['payload']['pages'][0]['questions']=[old]
        with self.assertRaisesRegex(runner.Stop,'old prefix'):
            self.execute(page,state,authored,reopen,plan)
        self.assertEqual(state['writes'],0);self.assertEqual(state['saves'],0)
        self.assertEqual(state['inventory'][0][1]['question'],'Short Answer abc123')
    def test_collateral_radio_choice_or_score_change_is_detected_before_save(self):
        for key,value in (('label','Changed option'),('category','Changed category'),
                          ('score','99'),('score_enabled',False)):
            page,state,authored,reopen=self.surface()
            def corrupt(frame,item,question,key=key,value=value):
                result=authored(frame,item,question)
                state['inventory'][0][0]['_radio_options'][0][key]=value
                return result
            with self.subTest(key=key),self.assertRaisesRegex(runner.Stop,'existing questions'):
                self.execute(page,state,corrupt,reopen)
            self.assertEqual(state['saves'],0)


class NativeAppend(unittest.TestCase):
    def surface(self,*,safe=True,insert=True):
        frame,dialog,tile,handle,canvas,items=tuple(MagicMock() for _ in range(6))
        dialog.count.return_value=1;dialog.get_by_text.return_value.count.return_value=1
        dialog.get_by_text.return_value.is_visible.return_value=True
        frame.get_by_role.return_value=dialog
        frame.locator.return_value.count.return_value=1
        collection=MagicMock();dialog.locator.return_value=collection;collection.filter.return_value=tile
        tile.count.return_value=1;tile.is_visible.return_value=True;tile.get_attribute.return_value='Short Answer3';tile.locator.return_value=handle
        handle.count.return_value=1;handle.is_visible.return_value=True;handle.get_attribute.return_value='false'
        canvas.locator.return_value=items;canvas.bounding_box.return_value={'x':0,'y':100,'width':400,'height':200}
        state={'count':1,'drags':0};items.count.side_effect=lambda:state['count']
        old,new=MagicMock(),MagicMock();old.bounding_box.return_value={'x':0,'y':100,'width':400,'height':150 if safe else 208}
        label=MagicMock();label.count.return_value=1;label.is_visible.return_value=True
        label.get_attribute.return_value='TEXT';label.inner_text.return_value='Short Answer a1b2c3'
        new.get_by_role.return_value=label;new.get_attribute.return_value='true'
        field=new.locator.return_value;field.count.return_value=1;field.get_attribute.return_value=None;field.input_value.return_value=''
        items.nth.side_effect=lambda index:old if index==0 else new
        def drag(*args,**kwargs):
            state['drags']+=1
            if insert:state['count']=2
        handle.drag_to.side_effect=drag
        return frame,canvas,state,handle
    def test_drag_is_bound_seven_pixels_inside_the_exact_final_question_edge(self):
        frame,canvas,state,handle=self.surface()
        with patch.object(text,'_close_properties'),patch.object(text,'_close_drawer'), \
                patch.object(text,'_owners',return_value=[(object(),canvas)]), \
                patch.object(text,'click'),patch.object(text,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())):
            text._append(frame,step()['payload'])
        self.assertEqual(state['drags'],1)
        self.assertEqual(handle.drag_to.call_args.kwargs['target_position'],{'x':200,'y':143})
    def test_real_populated_canvas_has_no_blank_tail_and_uses_one_native_pointer_drag(self):
        frame,canvas,state,handle=self.surface();page=MagicMock()
        canvas.bounding_box.return_value={'x':500,'y':190.234,'width':400,'height':145.195}
        canvas.locator.return_value.nth(0).bounding_box.return_value=dict(canvas.bounding_box.return_value)
        handle.bounding_box.return_value={'x':50,'y':362,'width':20,'height':20}
        page.mouse.up.side_effect=lambda:state.__setitem__('count',2)
        with patch.object(text,'_close_properties'),patch.object(text,'_close_drawer'), \
                patch.object(text,'_owners',return_value=[(object(),canvas)]), \
                patch.object(text,'click'),patch.object(text,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())):
            text._append(frame,step()['payload'],page=page)
        handle.drag_to.assert_not_called();page.mouse.down.assert_called_once();page.mouse.up.assert_called_once()
        destination=page.mouse.move.call_args_list[1]
        self.assertEqual(destination.kwargs,{'steps':15})
        self.assertAlmostEqual(destination.args[0],700)
        self.assertAlmostEqual(destination.args[1],328.429)
        self.assertEqual([call.args for call in page.mouse.move.call_args_list[2:]],[(700,328.429)]*3)
    def test_outside_footer_or_uncertain_insertion_never_retries_drag(self):
        for params in ({'safe':False},{'insert':False}):
            frame,canvas,state,handle=self.surface(**params)
            def wait(predicate,reason):
                if not predicate():raise runner.Stop(reason)
            with self.subTest(params=params),patch.object(text,'_close_properties'),patch.object(text,'_close_drawer'), \
                    patch.object(text,'_owners',return_value=[(object(),canvas)]), \
                    patch.object(text,'click'),patch.object(text,'wait_until',side_effect=wait),self.assertRaises(runner.Stop):
                text._append(frame,step()['payload'])
            self.assertEqual(state['drags'],0 if params.get('safe') is False else 1)
    def test_closing_drawer_may_deselect_all_widgets_and_new_bound_label_is_explicitly_reselected(self):
        frame,canvas,state,_=self.surface();item=canvas.locator.return_value.nth(1)
        selection={'active':False};item.get_attribute.side_effect=lambda key:'true' if selection['active'] else 'false'
        item.get_by_role.return_value.click.side_effect=lambda:selection.__setitem__('active',True)
        with patch.object(text,'_close_properties'),patch.object(text,'_close_drawer'), \
                patch.object(text,'_owners',return_value=[(object(),canvas)]), \
                patch.object(text,'click',side_effect=lambda locator:locator.click()), \
                patch.object(text,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())):
            text._append(frame,step()['payload'])
        self.assertTrue(selection['active']);item.get_by_role.return_value.click.assert_called_once()
    def test_unexpected_new_page_is_refused_during_the_first_insertion_poll(self):
        frame,canvas,state,_=self.surface(insert=False);calls={'owners':0}
        def owners(*args):
            calls['owners']+=1
            if calls['owners']>1:raise runner.Stop('Unexpected new page owner')
            return [(object(),canvas)]
        def poll(predicate,reason):
            if not predicate():raise runner.Stop('Insertion count timeout')
        with patch.object(text,'_close_properties'),patch.object(text,'_close_drawer'),patch.object(text,'click'), \
                patch.object(text,'_owners',side_effect=owners),patch.object(text,'wait_until',side_effect=poll), \
                self.assertRaisesRegex(runner.Stop,'Unexpected new page owner'):
            text._append(frame,step()['payload'])
        self.assertEqual(state['drags'],1)


class NativeQuestionProperties(unittest.TestCase):
    def surface(self,query='single_line'):
        frame,item=MagicMock(),MagicMock()
        values={'field_type':'TEXT','question':'Short Answer a1b2c3','placeholder':'',
            'short_label':'','query_key':query,'required':False,'hidden':False}
        state={'open':False,'fills':0}
        label=MagicMock();label.count.return_value=1;label.is_visible.return_value=True
        label.get_attribute.return_value='TEXT'
        label.inner_text.side_effect=lambda:values['question']+('*' if values['required'] else '')
        item.get_by_role.return_value=label;item.get_attribute.return_value='true'
        inputs=item.locator.return_value
        inputs.evaluate_all.side_effect=lambda script:[{'tag':'INPUT','name':None,'type':None,
            'value':'','placeholder':values['placeholder']}]
        active=MagicMock();active.count.return_value=1
        controls={}
        for key,selector in text.FIELD_INPUTS.items():
            control=MagicMock();control.count.return_value=1;control.is_visible.return_value=True
            control.input_value.side_effect=lambda key=key:values[key]
            def fill(value,key=key):values[key]=value;state['fills']+=1
            control.fill.side_effect=fill;controls[selector]=control
        for key,selector in text.FLAGS.items():
            flag=MagicMock();flag.count.return_value=1;flag.is_visible.return_value=True;flag.is_enabled.return_value=True
            flag.get_attribute.side_effect=lambda attr,key=key:str(values[key]).lower()
            flag.click.side_effect=lambda key=key:values.__setitem__(key,not values[key])
            controls[selector]=flag
        frame.locator.side_effect=lambda selector:active if selector=='.form-builder--item[data-active="true"]' else controls[selector]
        backs=MagicMock();backs.count.side_effect=lambda:2 if state['open'] else 1
        backs.nth.return_value.click.side_effect=lambda:state.__setitem__('open',False)
        settings=MagicMock();settings.count.return_value=1;settings.is_visible.return_value=True
        settings.click.side_effect=lambda:state.__setitem__('open',True)
        frame.get_by_role.side_effect=lambda role,**kw:backs if kw.get('name')=='Back' else settings
        return frame,item,values,state
    def context(self):
        from contextlib import ExitStack
        stack=ExitStack();stack.enter_context(patch.object(text,'click',side_effect=lambda loc:loc.click()))
        stack.enter_context(patch.object(text,'fill',side_effect=lambda loc,value:loc.fill(value)))
        stack.enter_context(patch.object(text,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())))
        return stack
    def test_actual_native_property_ids_and_checkbox_states_author_then_read_exact_question(self):
        frame,item,values,state=self.surface()
        desired=step()['payload']['questions'][0]
        with self.context():actual=text._write_question(frame,item,desired)
        self.assertEqual({key:actual[key] for key in text.PROPERTIES},desired)
        self.assertEqual(state['fills'],4);self.assertFalse(state['open'])
        self.assertEqual(actual['_widget_inputs'][0]['name'],None)
    def test_uncaptured_new_default_query_does_not_author_any_property(self):
        frame,item,values,state=self.surface(query='unknown_default')
        with self.context(),self.assertRaisesRegex(runner.Stop,'default properties'):
            text._write_question(frame,item,step()['payload']['questions'][0])
        self.assertEqual(state['fills'],0)


if __name__=='__main__':unittest.main()
