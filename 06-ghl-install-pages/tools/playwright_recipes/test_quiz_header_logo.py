"""Captured Header logo URL/dimensions preserve the other Header values."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import quiz_results as results
import recipe_cli
import skill6_playwright as runner
from test_quiz_header_layout import HeaderLayoutTests


def config():
    return {'result_page':{'header_logo':{
        'expected':{'url':'https://example.invalid/logo.png','width':'32','height':'32'},
        'changes':{'url':'https://example.invalid/new-logo.png','width':'64','height':'48'}}}}


class HeaderLogoTests(unittest.TestCase):
    def surface(self,*,readonly=False,lost=False):
        page,state,reopen=HeaderLayoutTests().surface()
        modal=page.frame_locator.return_value.get_by_role('dialog',name='UI Modal',exact=True)
        controls=results._logo_controls(modal)
        for key,node in controls.items():
            name='logo' if key=='url' else key
            node.is_enabled.return_value=True
            node.get_attribute.side_effect=lambda attr: '' if readonly and attr=='readonly' else None
            node.fill.side_effect=lambda value,name=name:state.__setitem__(name,value)
        def open_again(*args):
            reopen(*args)
            if lost:state['logo']='https://example.invalid/logo.png'
        return page,state,open_again

    def execute(self,page,plan,reopen):
        with patch.object(results,'_pane'),patch.object(results,'click',side_effect=lambda loc:loc.click()), \
                patch.object(results,'fill',side_effect=lambda loc,value:loc.fill(value)), \
                patch.object(results,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())), \
                patch.object(results,'reopen_editor',side_effect=reopen):
            return results.configure(page,plan)

    def test_full_logo_change_routes_saves_reopens_and_preserves_other_header_values(self):
        page,state,reopen=self.surface();plan=config()
        data={'location_id':'LOC','location_name':'Fixture','start_url':page.url,'configuration':plan}
        job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',data),Path('.'))
        receipt=self.execute(page,job['steps'][0],reopen)
        self.assertEqual((state['logo'],state['width'],state['height']),('https://example.invalid/new-logo.png','64','48'))
        self.assertEqual((state['layout'],state['enabled']),('Default',True))
        self.assertEqual((state['modal_saves'],state['outer_saves']),(1,1))
        self.assertEqual(receipt['configuration_sha256'],results.configuration_hash(plan))
        self.assertFalse(receipt['behavior_verified']);self.assertFalse(receipt['submission_verified'])

    def test_previous_value_or_readonly_control_refuses_before_any_save(self):
        for wrong,readonly in ((True,False),(False,True)):
            page,state,reopen=self.surface(readonly=readonly);plan=config()
            if wrong:plan['result_page']['header_logo']['expected']['height']='99'
            with self.subTest(wrong=wrong,readonly=readonly),self.assertRaises(runner.Stop):self.execute(page,plan,reopen)
            self.assertEqual((state['modal_saves'],state['outer_saves']),(0,0))
            self.assertEqual(state['logo'],'https://example.invalid/logo.png')

    def test_unsafe_metadata_and_lost_saved_logo_never_claim_completion(self):
        for key,value in [('url','javascript:alert(1)'),('width','0'),('height',True)]:
            plan=config();plan['result_page']['header_logo']['changes'][key]=value
            with self.subTest(key=key),self.assertRaises(runner.Stop):results.validate(plan)
        page,state,reopen=self.surface(lost=True)
        with self.assertRaisesRegex(runner.Stop,'did not persist|changed after independent reopen'):
            self.execute(page,config(),reopen)


if __name__=='__main__':unittest.main()
