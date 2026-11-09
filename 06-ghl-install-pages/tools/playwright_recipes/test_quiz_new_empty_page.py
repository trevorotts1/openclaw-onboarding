"""One explicit Add Page action binds a new empty owner before question drag."""
from copy import deepcopy
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree

import quiz_text_questions as native
import quiz_choice_questions as choice
import quiz_written_questions as written
from skill6_playwright import Stop
from test_quiz_text_questions import step as text_step,question
from test_quiz_choice_questions import step as choice_step
from test_quiz_written_questions import step as written_step
from test_quiz_dropdown_creation import authored
from test_quiz_loading_readiness import LoadedDom,canvas_tree,mount
import test_quiz_text_questions as text_tests


def new_page(value):
    result=deepcopy(value);result['payload'].update(create_page=True,new_page_label='Page 2',target_page=2)
    return result


class NewPageValidation(unittest.TestCase):
    def test_all_creation_front_doors_accept_one_explicit_new_empty_page(self):
        for module,builder in ((native,text_step),(choice,choice_step),(written,written_step)):
            value=new_page(builder())
            with self.subTest(module=module.__name__):
                self.assertEqual(module.validate(value),value['payload'])
                self.assertNotEqual(module.configuration_hash(value),module.configuration_hash(builder()))
    def test_ambiguous_mode_old_target_duplicate_label_or_many_questions_refuse(self):
        for change in ({'create_page':False},{'target_page':1},{'new_page_label':'Page 1'},{'new_page_label':'Authored page name'},
                       {'questions':[text_step()['payload']['questions'][0]]*2}):
            value=new_page(text_step());value['payload'].update(change)
            with self.subTest(change=change),self.assertRaises(Stop):native.validate(value)
        value=new_page(text_step());value['payload'].pop('new_page_label')
        with self.assertRaises(Stop):native.validate(value)


class NewPageSurface:
    def __init__(self,*,wrong_label=False,extra=False,collateral=False,missing_marker=False):
        self.root,self.canvas=canvas_tree();mount(self.canvas)
        self.old_page=self.root[0]
        ElementTree.SubElement(self.old_page,'button',{'id':'add-slide-button'}).text='Add Page'
        self.frame=LoadedDom([self.root]);self.clicks=0;self.new_canvas=None
        self.before=[[{**question(),'_widget_inputs':[],'_radio_input_ids':[]}]]
        self.inventory=deepcopy(self.before)
        self.wrong_label,self.extra,self.collateral,self.missing_marker=wrong_label,extra,collateral,missing_marker
    def click(self,control):
        self.clicks+=1
        if not isinstance(control,LoadedDom) or control.nodes[0] is not self.old_page.find('button'):
            raise AssertionError('Add Page did not belong to the exact last original owner')
        count=2 if self.extra else 1
        for offset in range(count):
            root,canvas=canvas_tree();owner=root[0]
            owner.find('.//div[@class="flex items-center text-sm font-semibold"]').text='Wrong page' if self.wrong_label else 'Page '+str(2+offset)
            ElementTree.SubElement(owner,'button',{'id':'add-slide-button'}).text='Add Page'
            ElementTree.SubElement(owner,'button',{'id':'add-elements-button'}).text='Add Elements'
            if not self.missing_marker:ElementTree.SubElement(canvas,'div').text='Drag and drop components'
            self.root.append(owner);self.new_canvas=canvas;self.inventory.append([])
        if self.collateral:self.inventory[0][0]['query_key']='Changed old query'
    def read(self,*args,**kwargs):return deepcopy(self.inventory)


class AddPageOwner(unittest.TestCase):
    def execute(self,surface):
        value=new_page(text_step());plan=native.validate(value)
        def wait(predicate,reason):
            if not predicate():raise Stop(reason)
        with patch.object(native,'_prepare_inventory'),patch.object(native,'_close_properties'), \
                patch.object(native,'click',side_effect=surface.click),patch.object(native,'wait_until',side_effect=wait):
            return native._target_page(surface.frame,plan,surface.before,surface.read)
    def test_one_scoped_add_page_and_positive_empty_marker_preserve_every_old_question(self):
        surface=NewPageSurface();original=new_page(text_step())['payload'];runtime,baseline=self.execute(surface)
        self.assertEqual(surface.clicks,1);self.assertEqual(baseline,surface.before+[[]])
        self.assertEqual(len(runtime['pages']),2);self.assertEqual(runtime['pages'][1],{'label':'Page 2','questions':[]})
        self.assertEqual(len(original['pages']),1)
    def test_wrong_page_delta_label_empty_marker_or_old_metadata_never_repeat_add(self):
        for options in ({'wrong_label':True},{'extra':True},{'collateral':True},{'missing_marker':True}):
            surface=NewPageSurface(**options)
            with self.subTest(options=options),self.assertRaises(Stop):self.execute(surface)
            self.assertEqual(surface.clicks,1)
    def test_already_added_page_cannot_be_treated_as_original_baseline_or_added_again(self):
        surface=NewPageSurface()
        with patch.object(native,'_prepare_inventory'),patch.object(native,'_close_properties'), \
                patch.object(native,'click',side_effect=surface.click),patch.object(native,'wait_until',side_effect=lambda fn,reason:fn()):
            native._target_page(surface.frame,new_page(text_step())['payload'],surface.before,surface.read)
            with self.assertRaises(Stop):
                native._target_page(surface.frame,new_page(text_step())['payload'],surface.before,surface.read)
        self.assertEqual(surface.clicks,1)


class NewPageQuestionChain(unittest.TestCase):
    def execute(self,*,lost=False,wrong_target=False):
        value=new_page(choice_step());value['payload']['questions']=[authored()]
        original=deepcopy(value);surface=NewPageSurface();page,frame=MagicMock(),MagicMock()
        page.url=value['payload']['start_url'];page.frame_locator.return_value=frame;frame.locator.side_effect=surface.frame.locator
        title,save=MagicMock(),MagicMock();title.count.return_value=1;title.input_value.return_value='Exact quiz'
        save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,**kwargs:title if role=='textbox' else save
        state={'drags':0,'saves':0,'reopened':False}
        def click(control):
            if isinstance(control,LoadedDom):surface.click(control)
            else:state['saves']+=1
        def append(_frame,runtime,*args,**kwargs):
            self.assertEqual(runtime['target_page'],2);self.assertEqual(len(runtime['pages']),2)
            self.assertEqual(surface.inventory[1],[]);state['drags']+=1
            default={**authored(),'question':'Single Dropdown abc12','query_key':'dropdown',
                'placeholder':'','short_label':'','required':False,'options':list(choice.OPTIONS),'_widget_inputs':[]}
            surface.inventory[1].append(default);mount(surface.new_canvas,default)
            return object()
        def write(*args):
            record={**authored(),'_widget_inputs':[],'_option_identity':[]}
            if wrong_target:
                surface.inventory[0].append(record);mount(surface.canvas,record)
            else:
                surface.inventory[1][-1]=record
                surface.new_canvas.findall('.//*[@role="textbox"]')[-1].text=record['question']
            return deepcopy(record)
        def reopen(*args):
            state['reopened']=True
            if lost:
                surface.root.remove(surface.root[1]);surface.inventory=deepcopy(surface.before)
        def wait(predicate,reason):
            if not predicate():raise Stop(reason)
        with patch.object(native,'_prepare_inventory'),patch.object(native,'_close_properties'), \
                patch.object(native,'click',side_effect=click),patch.object(choice,'click',side_effect=click), \
                patch.object(native,'wait_until',side_effect=wait),patch.object(choice,'wait_until',side_effect=wait), \
                patch.object(choice,'assert_tenant'),patch.object(choice,'_inventory',side_effect=surface.read), \
                patch.object(choice,'_append',side_effect=append),patch.object(choice,'_fresh_choice'), \
                patch.object(choice,'_write_question',side_effect=write),patch.object(native,'reopen_editor',side_effect=reopen):
            try:result=choice.configure(page,value)
            except Stop as error:return error,state,surface,value,original
        return result,state,surface,value,original
    def test_new_empty_owner_then_question_uses_original_hash_and_saved_full_readback(self):
        result,state,surface,value,original=self.execute()
        self.assertEqual(result['configuration_sha256'],choice.configuration_hash(original))
        self.assertEqual(result['target_page'],2);self.assertEqual(value,original)
        self.assertEqual(surface.clicks,1);self.assertEqual(state['drags'],1);self.assertEqual(state['saves'],1)
        self.assertTrue(state['reopened']);self.assertEqual(surface.inventory[0],surface.before[0])
    def test_question_on_wrong_page_or_lost_new_owner_is_not_completion(self):
        for options in ({'wrong_target':True},{'lost':True}):
            result,state,surface,_,_=self.execute(**options)
            self.assertIsInstance(result,Stop);self.assertEqual(surface.clicks,1)
            self.assertEqual(state['saves'],0 if options.get('wrong_target') else 1)


class EmptyPageDrawer(unittest.TestCase):
    def test_automatic_drawer_is_reused_and_missing_drawer_uses_only_target_scoped_add_elements(self):
        for already_open in (False,True):
            frame,canvas,state,handle=text_tests.NativeAppend().surface()
            dialog=frame.get_by_role.return_value;opened={'value':already_open};dialog.count.side_effect=lambda:int(opened['value'])
            new_owner,opener=MagicMock(),MagicMock();new_owner.locator.return_value=opener
            opener.count.return_value=1;opener.is_visible.return_value=True
            opener.click.side_effect=lambda:opened.__setitem__('value',True)
            items=canvas.locator.return_value;new_item=items.nth(1)
            state['count']=0;items.nth.side_effect=None;items.nth.return_value=new_item
            handle.drag_to.side_effect=lambda *args,**kwargs:state.__setitem__('count',1)
            runtime=new_page(text_step())['payload'];runtime['pages'].append({'label':'Page 2','questions':[]})
            with self.subTest(already_open=already_open),patch.object(native,'_close_properties'),patch.object(native,'_close_drawer'), \
                    patch.object(native,'_owners',return_value=[(object(),object()),(new_owner,canvas)]), \
                    patch.object(native,'click',side_effect=lambda control:control.click()), \
                    patch.object(native,'wait_until',side_effect=lambda fn,reason:self.assertTrue(fn())):
                native._append_tile(frame,runtime,'Short Answer')
            self.assertEqual(opener.click.call_count,0 if already_open else 1)
            self.assertFalse(any(call.kwargs.get('name')=='Add Quiz Element' for call in frame.get_by_role.call_args_list))
            self.assertEqual(handle.drag_to.call_args.kwargs['target_position'],{'x':200,'y':100})


if __name__=='__main__':unittest.main()
