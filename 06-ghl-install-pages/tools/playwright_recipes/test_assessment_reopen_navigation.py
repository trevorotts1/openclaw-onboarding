"""A canceled native editor exit must never masquerade as independent reopen."""
import unittest
from unittest.mock import MagicMock,patch

import assessments
import skill6_playwright as core


class ReopenNavigation(unittest.TestCase):
    def surface(self,*,blocked=False,retained_editor=False,list_drift=False,duplicate_editor=False):
        editor='https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ'
        listing='https://app.convertandflow.com/v2/location/LOC/quiz-builder/main'
        page=MagicMock();page.url=editor;state={'iframes':1,'list_seen':False}
        frames=MagicMock();frames.count.side_effect=lambda:state['iframes'];page.locator.return_value=frames
        title=page.frame_locator.return_value.get_by_role.return_value
        title.count.return_value=1;title.input_value.return_value='Exact quiz'
        cell=MagicMock();link=cell.get_by_text.return_value
        def navigate(url,**kwargs):
            if not blocked:
                page.url=url;state['iframes']=1 if retained_editor else 0
        page.goto.side_effect=navigate
        def search(*args):
            state['list_seen']=page.url==listing and state['iframes']==0
            if list_drift:page.url=editor;state['iframes']=1
            return cell
        def open_editor():
            page.url=editor;state['iframes']=2 if duplicate_editor else 1
        link.click.side_effect=open_editor
        return page,editor,state,cell,search
    def run_helper(self,page,editor,search):
        def wait(predicate,reason):
            if not predicate():raise core.Stop(reason)
        with patch.object(core,'exact_search',side_effect=search) as query, \
                patch.object(core,'wait_until',side_effect=wait), \
                patch.object(core,'click',side_effect=lambda control:control.click()):
            assessments.reopen_editor(page,'quiz','Exact quiz',editor)
        return query
    def test_actual_list_route_without_editor_is_observed_before_a_new_editor_is_opened(self):
        page,editor,state,_,search=self.surface()
        query=self.run_helper(page,editor,search)
        self.assertTrue(state['list_seen']);query.assert_called_once();self.assertEqual(page.url,editor)
    def test_canceled_goto_with_same_title_and_background_grid_cannot_fake_reopen(self):
        # Before the guard, mocked/background exact_search + a no-op click
        # left the original editor/title intact and the helper returned success.
        page,editor,state,cell,search=self.surface(blocked=True)
        with self.assertRaisesRegex(core.Stop,'did not leave the editor'):
            self.run_helper(page,editor,search)
        self.assertFalse(state['list_seen']);cell.get_by_text.assert_not_called()
    def test_list_url_with_retained_editor_is_not_independent_document_evidence(self):
        page,editor,state,cell,search=self.surface(retained_editor=True)
        with self.assertRaisesRegex(core.Stop,'did not leave the editor'):
            self.run_helper(page,editor,search)
        cell.get_by_text.assert_not_called()
    def test_navigation_drift_during_exact_list_search_cannot_click_a_stale_cell(self):
        page,editor,_,cell,search=self.surface(list_drift=True)
        with self.assertRaisesRegex(core.Stop,'list identity changed'):
            self.run_helper(page,editor,search)
        cell.get_by_text.assert_not_called()
    def test_reopened_editor_must_have_one_exact_iframe_and_form_name(self):
        page,editor,_,_,search=self.surface(duplicate_editor=True)
        with self.assertRaisesRegex(core.Stop,'editor identity changed'):
            self.run_helper(page,editor,search)
    def test_new_editor_visible_blank_title_waits_for_its_positive_saved_name(self):
        page,editor,state,_,search=self.surface()
        title=page.frame_locator.return_value.get_by_role.return_value;title.input_value.return_value=''
        def wait(predicate,reason):
            if predicate():return
            title.input_value.return_value='Exact quiz'
            self.assertTrue(predicate())
        with patch.object(core,'exact_search',side_effect=search),patch.object(core,'wait_until',side_effect=wait), \
                patch.object(core,'click',side_effect=lambda control:control.click()):
            assessments.reopen_editor(page,'quiz','Exact quiz',editor)
        self.assertTrue(state['list_seen'])
    def test_wrong_nonempty_saved_title_is_immediate_refusal(self):
        page,editor,_,_,search=self.surface()
        page.frame_locator.return_value.get_by_role.return_value.input_value.return_value='Other quiz'
        with self.assertRaisesRegex(core.Stop,'editor identity changed'):
            self.run_helper(page,editor,search)


if __name__=='__main__':unittest.main()
