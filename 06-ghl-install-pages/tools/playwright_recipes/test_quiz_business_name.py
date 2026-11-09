"""The captured switch controls business-name display, preserving stored copy."""
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import editor_replay
import quiz_results as results
import recipe_cli
import skill6_playwright as runner


BASE={'location_id':'LOC','location_name':'Fixture Account',
      'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ'}
HTML='<p><span style="font-size: 32px">Stored business name</span></p>'


def config(before=True,after=False):
    return {'result_page':{'expected':{'business_name_enabled':before},
                           'changes':{'business_name_enabled':after}}}


class BusinessNameControl(unittest.TestCase):
    def surface(self,*,enabled=True,lost=False,mutate_markup=False,label_present=True):
        page,frame,modal=MagicMock(),MagicMock(),MagicMock()
        page.url=BASE['start_url'];page.frame_locator.return_value=frame
        state={'enabled':enabled,'html':HTML,'text':'Stored business name','switches':0,
               'modal':False,'modal_saves':0,'outer_saves':0,'reopened':False}
        title=MagicMock();title.count.return_value=1;title.input_value.return_value='Exact fixture quiz'
        rte=MagicMock();rte.count.return_value=1;rte.is_visible.return_value=True
        rte.inner_text.side_effect=lambda:state['text'];rte.inner_html.side_effect=lambda:state['html']
        switch=MagicMock();switch.count.return_value=1;switch.is_visible.return_value=True;switch.is_enabled.return_value=True
        switch.get_attribute.side_effect=lambda key:str(state['enabled']).lower() if key=='aria-checked' else None
        def toggle():
            state['enabled']=not state['enabled'];state['switches']+=1
            if mutate_markup:state['html']='<p>Altered stored formatting</p>'
        switch.click.side_effect=toggle
        label=MagicMock();label.count.return_value=int(label_present);label.is_visible.return_value=True
        label.filter.return_value=label
        modal.locator.side_effect=lambda selector:rte if selector.startswith('.tiptap') else label
        modal.count.return_value=1;modal.is_visible.return_value=True
        save=MagicMock();save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        def modal_save():state['modal_saves']+=1;state['modal']=False
        save.click.side_effect=modal_save
        cancel=MagicMock();cancel.count.return_value=1;cancel.is_visible.return_value=True
        cancel.click.side_effect=lambda:state.__setitem__('modal',False)
        modal.get_by_role.side_effect=lambda role,**kw:switch if role=='switch' else save if kw.get('name')=='Save' else cancel
        outer=MagicMock();outer.count.return_value=1;outer.is_enabled.return_value=True
        outer.click.side_effect=lambda:state.__setitem__('outer_saves',state['outer_saves']+1)
        empty=MagicMock();empty.count.side_effect=lambda:int(state['modal'])
        opener=MagicMock();opener.click.side_effect=lambda:state.__setitem__('modal',True)
        def role(role,**kw):
            if role=='textbox':return title
            if role=='dialog':return modal if kw.get('name')=='UI Modal' else empty
            if kw.get('name')=='Save':return outer
            return opener
        frame.get_by_role.side_effect=role
        def reopen(*args):
            state['reopened']=True
            if lost:state['enabled']=enabled
        return page,state,reopen
    def run_surface(self,page,plan,reopen):
        with patch.object(results,'_pane'), \
             patch.object(results,'_layout_controls',return_value=({},'Default')), \
             patch.object(results,'click',side_effect=lambda loc:loc.click()), \
             patch.object(results,'fill',side_effect=lambda loc,value:loc.fill(value)), \
             patch.object(results,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())), \
             patch.object(results,'reopen_editor',side_effect=reopen):
            return results.configure(page,plan)
    def test_business_name_flag_requires_boolean_previous_and_desired_pair(self):
        self.assertEqual(results.validate(config()),config())
        for value in ('false',0,None):
            plan=config();plan['result_page']['changes']['business_name_enabled']=value
            with self.subTest(value=value),self.assertRaises(runner.Stop):results.validate(plan)
        plan=config();plan['result_page']['expected']={'business_name':'Ignored old field'}
        with self.assertRaises(runner.Stop):results.validate(plan)
    def test_disabling_name_preserves_stored_text_markup_and_saves_then_reopens(self):
        page,state,reopen=self.surface()
        receipt=self.run_surface(page,config(),reopen)
        self.assertFalse(state['enabled']);self.assertEqual(state['switches'],1)
        self.assertEqual(state['html'],HTML);self.assertTrue(state['reopened'])
        self.assertEqual((state['modal_saves'],state['outer_saves']),(1,1))
        self.assertEqual(receipt['status'],'QUIZ_RESULTS_SAVED_AND_REOPENED')
        self.assertFalse(receipt['behavior_verified']);self.assertFalse(receipt['submission_verified'])
    def test_enabling_name_uses_same_captured_visible_editor_and_keeps_copy(self):
        page,state,reopen=self.surface(enabled=False)
        self.run_surface(page,config(False,True),reopen)
        self.assertTrue(state['enabled']);self.assertEqual(state['switches'],1)
        self.assertEqual(state['html'],HTML)
    def test_flag_drift_or_missing_business_name_label_stops_before_click_or_save(self):
        for params in ({'enabled':False},{'label_present':False}):
            page,state,reopen=self.surface(**params)
            with self.subTest(params=params),self.assertRaises(runner.Stop):
                self.run_surface(page,config(),reopen)
            self.assertEqual(state['switches'],0);self.assertEqual(state['modal_saves'],0)
    def test_native_toggle_collateral_markup_change_refuses_before_save(self):
        page,state,reopen=self.surface(mutate_markup=True)
        with self.assertRaisesRegex(runner.Stop,'protected stored markup'):
            self.run_surface(page,config(),reopen)
        self.assertEqual(state['modal_saves'],0)
    def test_lost_saved_switch_never_reports_completion(self):
        page,state,reopen=self.surface(lost=True)
        with self.assertRaisesRegex(runner.Stop,'did not persist'):
            self.run_surface(page,config(),reopen)
        self.assertTrue(state['reopened'])
    def test_compiler_and_replay_bind_switch_intent_and_cannot_claim_header_hidden(self):
        data={**BASE,'configuration':config()}
        job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',data),Path('.'))
        step=job['steps'][0]
        receipt={'status':'QUIZ_RESULTS_SAVED_AND_REOPENED','kind':'quiz_results',
                 'editor_url':BASE['start_url'],'configuration_sha256':results.configuration_hash(step),
                 'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False}
        self.assertEqual(editor_replay._result(step,receipt,job)['kind'],'quiz_results')
        changed=config(False,True)
        self.assertNotEqual(results.configuration_hash(changed),receipt['configuration_sha256'])
        with self.assertRaises(runner.Stop):results.validate({'result_page':{'expected':{'header_visible':True},'changes':{'header_visible':False}}})


if __name__=='__main__':unittest.main()
