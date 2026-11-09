"""Captured Header cards retain business-name formatting and logo dimensions."""
from unittest.mock import MagicMock,patch
import re
import unittest

import quiz_results as results
import skill6_playwright as runner
import test_quiz_business_name as business
HTML=business.HTML


BASE_CLASSES='flex h-8 w-full items-center justify-center gap-2 rounded-lg border border-gray-300 px-6 py-[18px] pl-3 font-medium text-gray-700 transition-colors duration-200'


def config(before='Default',after='Reverse'):
    return {'result_page':{'expected':{'header_layout':before},'changes':{'header_layout':after}}}


class HeaderLayoutTests(unittest.TestCase):
    def surface(self,*,ambiguous=False,corrupt_logo=False,lost=False):
        page,state,reopen=business.BusinessNameControl().surface()
        frame=page.frame_locator.return_value
        modal=frame.get_by_role('dialog',name='UI Modal',exact=True)
        state.update(layout='Default',layout_clicks=0,logo='https://example.invalid/logo.png',width='32',height='32')
        original_locator=modal.locator.side_effect;original_role=modal.get_by_role.side_effect
        heading=MagicMock();heading.count.return_value=1;heading.is_visible.return_value=True
        labels={};cards={}
        for name in ('Default','Reverse'):
            label=MagicMock();label.fixture_name=name;label.count.return_value=1;label.is_visible.return_value=True
            label.get_attribute.side_effect=lambda key,name=name:(BASE_CLASSES+
                (' layout-card-active bg-gray-100 text-primary-700' if ambiguous or state['layout']==name else '')) if key=='class' else None
            labels[name]=label
            card=MagicMock();card.count.return_value=1;card.is_visible.return_value=True;card.get_by_text.return_value=label
            def click(name=name):
                state['layout']=name;state['layout_clicks']+=1
                if corrupt_logo:state['width']='0'
            card.click.side_effect=click;cards[name]=card
        collection=MagicMock();collection.count.return_value=2
        collection.filter.side_effect=lambda has:cards[has.fixture_name]
        modal.get_by_text.side_effect=lambda value,**kw:heading if isinstance(value,re.Pattern) else labels.get(value,heading)
        logo=MagicMock();logo.count.return_value=1;logo.is_visible.return_value=True
        logo.input_value.side_effect=lambda:state['logo']
        sizes=MagicMock();sizes.count.return_value=2
        sizes_controls=[]
        for name in ('width','height'):
            control=MagicMock();control.input_value.side_effect=lambda name=name:state[name]
            sizes_controls.append(control)
        sizes.nth.side_effect=lambda index:sizes_controls[index]
        modal.get_by_role.side_effect=lambda role,**kw:sizes if role=='textbox' and kw.get('name')=='Please Input' else original_role(role,**kw)
        def locator(selector):
            if selector=='div.flex.w-full.cursor-pointer.flex-col.items-center':return collection
            if selector=='#bgImage[name="bgImage"]':return logo
            return original_locator(selector)
        modal.locator.side_effect=locator
        def open_again(*args):
            reopen(*args)
            if lost:state['layout']='Default'
        return page,state,open_again
    def execute(self,page,plan,reopen):
        with patch.object(results,'_pane'),patch.object(results,'click',side_effect=lambda loc:loc.click()), \
             patch.object(results,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())), \
             patch.object(results,'reopen_editor',side_effect=reopen):
            return results.configure(page,plan)
    def test_exact_layout_names_require_matched_old_new_pairs(self):
        self.assertEqual(results.validate(config()),config())
        for name in ('reverse','',None,True):
            with self.subTest(name=name),self.assertRaises(runner.Stop):results.validate(config(after=name))
    def test_captured_reverse_card_selects_once_and_persists_with_untouched_header_content(self):
        page,state,reopen=self.surface()
        result=self.execute(page,config(),reopen)
        self.assertEqual(state['layout'],'Reverse');self.assertEqual(state['layout_clicks'],1)
        self.assertEqual((state['logo'],state['width'],state['height']),('https://example.invalid/logo.png','32','32'))
        self.assertTrue(state['enabled']);self.assertEqual(state['html'],HTML)
        self.assertTrue(state['reopened']);self.assertEqual(result['status'],'QUIZ_RESULTS_SAVED_AND_REOPENED')
    def test_ambiguous_selection_and_wrong_previous_layout_stop_before_click_or_save(self):
        for params,plan in (({'ambiguous':True},config()),({},config(before='Reverse',after='Default'))):
            page,state,reopen=self.surface(**params)
            with self.subTest(params=params),self.assertRaises(runner.Stop):self.execute(page,plan,reopen)
            self.assertEqual(state['layout_clicks'],0);self.assertEqual(state['modal_saves'],0)
    def test_layout_cannot_change_logo_dimensions_before_save(self):
        page,state,reopen=self.surface(corrupt_logo=True)
        with self.assertRaisesRegex(runner.Stop,'protected logo'):self.execute(page,config(),reopen)
        self.assertEqual(state['modal_saves'],0)
    def test_lost_saved_layout_never_reports_completion(self):
        page,state,reopen=self.surface(lost=True)
        with self.assertRaisesRegex(runner.Stop,'did not persist'):self.execute(page,config(),reopen)
        self.assertTrue(state['reopened'])


if __name__=='__main__':unittest.main()
