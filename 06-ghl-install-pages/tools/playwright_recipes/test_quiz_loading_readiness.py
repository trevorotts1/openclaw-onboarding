"""Visible native quiz titles can precede hydrated page/question DOM."""
from copy import deepcopy
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree

import quiz_text_questions as native
from skill6_playwright import Stop
from test_quiz_radio_creation import RadioDom
from test_quiz_text_questions import step,question


class LoadedDom(RadioDom):
    def locator(self,selector):
        result=super().locator(selector);return LoadedDom(result.nodes,self.parents)
    def nth(self,index):return LoadedDom([self.nodes[index]],self.parents)
    def get_by_text(self,text,*,exact):
        return LoadedDom([node for root in self.nodes for node in root.iter()
            if (node.text or '').strip()==text],self.parents)


def canvas_tree():
    root=ElementTree.fromstring('''<main><div class="survey-form-container flex"><div class="builder-form-name">
      <div><div class="flex items-center text-sm font-semibold">Page 1</div></div>
      <div id="the-form-builder" class="form-element form-builder--wrap"><div class="drop">
      <div class="builder_sub_container" /></div></div></div></div></main>''')
    canvas=root.find('.//div[@class="builder_sub_container"]')
    return root,canvas


def mount(canvas,record=None):
    record=record or question()
    wrapper=ElementTree.SubElement(canvas,'div',{'class':'smooth-dnd-draggable-wrapper element-box menu-field-wrap col-12'})
    outer=ElementTree.SubElement(wrapper,'div',{'class':'menu-item'})
    inner=ElementTree.SubElement(outer,'div',{'class':'menu-item'})
    item=ElementTree.SubElement(inner,'div',{'class':'form-builder--item'})
    ElementTree.SubElement(item,'div',{'role':'textbox','aria-label':'Label',
        'data-field-type':record['field_type'],'contenteditable':'true'}).text=record['question']


class QuizLoadingReadiness(unittest.TestCase):
    def setUp(self):
        prepare=patch.object(native,'_prepare_inventory')
        prepare.start();self.addCleanup(prepare.stop)
    def test_correct_title_waits_for_positive_existing_widget_before_full_inventory(self):
        root,canvas=canvas_tree();frame=LoadedDom([root]);polls=[]
        def wait(predicate,reason):
            polls.append(predicate());self.assertFalse(polls[-1])
            mount(canvas);polls.append(predicate());self.assertTrue(polls[-1])
        with patch.object(native,'wait_until',side_effect=wait):native._wait_baseline(frame,step()['payload'])
        self.assertEqual(polls,[False,True])
    def test_wrong_nonempty_widget_label_or_type_is_immediate_refusal(self):
        for record in (question('Wrong owner'),question(kind='TEXT')):
            root,canvas=canvas_tree();mount(canvas,record)
            with self.subTest(record=record),patch.object(native,'wait_until',side_effect=lambda fn,reason:fn()),self.assertRaises(Stop):
                native._wait_baseline(LoadedDom([root]),step()['payload'])
    def test_zero_widgets_alone_cannot_prove_an_authored_empty_page(self):
        root,canvas=canvas_tree();plan=step()['payload'];plan['pages'][0]['questions']=[]
        def wait(predicate,reason):
            self.assertFalse(predicate())
            ElementTree.SubElement(canvas,'div').text='Drag and drop components'
            self.assertTrue(predicate())
        with patch.object(native,'wait_until',side_effect=wait):native._wait_baseline(LoadedDom([root]),plan)
    def test_reopened_page_waits_against_complete_desired_inventory_after_insertions(self):
        root,canvas=canvas_tree();mount(canvas);new=question('Authored answer','answer','LARGE_TEXT')
        mount(canvas,new);desired=[[question(),new]]
        with patch.object(native,'wait_until',side_effect=lambda fn,reason:self.assertTrue(fn())):
            native._wait_baseline(LoadedDom([root]),step()['payload'],expected=desired)
    def test_empty_title_is_loading_but_a_wrong_nonempty_title_or_url_is_never_retried(self):
        plan=step()['payload'];page,title=MagicMock(),MagicMock();page.url=plan['start_url'];title.count.return_value=1
        title.input_value.side_effect=['',plan['expected_quiz_name']]
        def wait(predicate,reason):self.assertFalse(predicate());self.assertTrue(predicate())
        with patch.object(native,'wait_until',side_effect=wait):native._wait_editor_identity(page,title,plan)
        for wrong in ('title','url'):
            title.input_value.side_effect=None;title.input_value.return_value='Wrong quiz' if wrong=='title' else plan['expected_quiz_name']
            page.url=plan['start_url'] if wrong=='title' else plan['start_url'].replace('/LOC/','/OTHER/')
            with self.subTest(wrong=wrong),patch.object(native,'wait_until',side_effect=lambda fn,reason:fn()) as poll,self.assertRaises(Stop):
                native._wait_editor_identity(page,title,plan)
            poll.assert_called_once()


if __name__=='__main__':unittest.main()
