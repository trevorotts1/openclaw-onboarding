"""Captured Add/tail Remove tier lifecycle retains complete row inventories."""
from copy import deepcopy
import unittest
from unittest.mock import MagicMock,patch
import quiz_ui
import skill6_playwright as runner

OLD=[{'label':'Low','from':0,'to':39},{'label':'Medium','from':40,'to':70},{'label':'High','from':71,'to':100}]
ADDED=[*deepcopy(OLD[:2]),{'label':'High','from':71,'to':84},{'label':'Premium','from':85,'to':100}]


def config(action='add'):
    before,after=(OLD,ADDED) if action=='add' else (ADDED,OLD)
    return {'expected_tier_labels':[row['label'] for row in before],'expected_tiers':deepcopy(before),
        'tier_transitions':[{'action':action,'expected_tiers':deepcopy(after)}],'tiers':deepcopy(after)}


class LifecycleTests(unittest.TestCase):
    def test_complete_add_and_remove_tail_requests_and_transition_drift(self):
        for action in ('add','remove_last'):
            self.assertEqual(quiz_ui.validate(config(action)),config(action))
        for defect in ('count','retained','range','action','duplicate','missing'):
            value=config();transition=value['tier_transitions'][0]
            if defect=='count':transition['expected_tiers']=deepcopy(OLD)
            elif defect=='retained':transition['expected_tiers'][0]['label']='Foreign'
            elif defect=='range':transition['expected_tiers'][1]['from']=41
            elif defect=='action':transition['action']='remove_first'
            elif defect=='duplicate':transition['expected_tiers'][-1]['label']='High'
            else:del value['expected_tiers']
            with self.subTest(defect=defect),self.assertRaises(quiz_ui.QuizError):quiz_ui.validate(value)
        value=config();value.pop('tier_transitions')
        with self.assertRaises(quiz_ui.QuizError):quiz_ui.validate(value)

    def test_native_lifecycle_one_click_and_full_post_delta_guard(self):
        for action in ('add','remove_last'):
            value=config(action);before=value['expected_tiers'];after=value['tiers']
            for drift in (False,True):
                popup=MagicMock();control=MagicMock();control.count.return_value=1
                control.is_visible.return_value=True;control.is_enabled.return_value=True
                control.input_value.return_value=after[-1]['label']
                popup.locator.return_value=control;control.nth.return_value=control
                control.count.return_value=1
                post=deepcopy(after)
                if drift:post[0]['label']='Foreign'
                observed=[before,post,post]
                def read(*args):return deepcopy(observed.pop(0))
                def settled(predicate,message):
                    with patch.object(control,'count',return_value=len(after)):self.assertTrue(predicate())
                with patch.object(quiz_ui,'_read_lifecycle_tiers',side_effect=read), \
                        patch.object(runner,'click',side_effect=lambda node:node.click()), \
                        patch.object(runner,'wait_until',side_effect=settled):
                    if drift:
                        with self.assertRaisesRegex(runner.Stop,'retained row'):
                            quiz_ui._resize_tiers(popup,before,value['tier_transitions'])
                    else:self.assertEqual(quiz_ui._resize_tiers(popup,before,value['tier_transitions']),after)
                control.click.assert_called_once()

    def test_variable_generated_new_label_is_read_then_authored_on_owned_tail(self):
        popup=MagicMock();action=MagicMock();label=MagicMock()
        for node in (action,label):
            node.count.return_value=1;node.is_visible.return_value=True;node.is_enabled.return_value=True
        generated=deepcopy(ADDED);generated[-1]['label']='Remarkable'
        state={'rows':deepcopy(OLD),'added':False}
        label.input_value.side_effect=lambda:state['rows'][-1]['label']
        label.fill.side_effect=lambda text:state['rows'][-1].__setitem__('label',text)
        rows=MagicMock();rows.count.side_effect=lambda:len(state['rows']);rows.nth.return_value=label
        popup.locator.side_effect=lambda selector:action if selector=='button#add-tier' else rows
        def clicked(node):
            self.assertIs(node,action);state['rows']=deepcopy(generated);state['added']=True
        with patch.object(quiz_ui,'_read_lifecycle_tiers',side_effect=lambda node:deepcopy(state['rows'])), \
                patch.object(runner,'click',side_effect=clicked) as click, \
                patch.object(runner,'fill',side_effect=lambda node,text:node.fill(text)), \
                patch.object(runner,'wait_until',side_effect=lambda predicate,message:self.assertTrue(predicate())):
            self.assertEqual(quiz_ui._resize_tiers(popup,OLD,config()['tier_transitions']),ADDED)
        self.assertEqual(click.call_count,1);label.fill.assert_called_once_with('Premium');label.press.assert_called_once_with('Tab')

    def test_preexisting_native_drift_refuses_before_count_action(self):
        popup=MagicMock();wrong=deepcopy(OLD);wrong[0]['to']=38
        with patch.object(quiz_ui,'_read_lifecycle_tiers',return_value=wrong),patch.object(runner,'click') as click:
            with self.assertRaises(runner.Stop):quiz_ui._resize_tiers(popup,OLD,config()['tier_transitions'])
            click.assert_not_called()

    def test_full_add_and_remove_recipe_save_reopen_and_saved_drift(self):
        import assessments
        import recipe_cli
        from pathlib import Path
        for action,lost in (('add',False),('remove_last',False),('add',True)):
            value=config(action);state={'rows':deepcopy(value['expected_tiers']),'saves':0}
            page,frame,popup,modal,save=MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock()
            page.url='https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ'
            page.frame_locator.return_value=frame
            title=MagicMock();title.input_value.return_value='Exact quiz'
            save.count.return_value=1;save.is_enabled.return_value=True
            save.click.side_effect=lambda:state.__setitem__('saves',state['saves']+1)
            back=MagicMock();back.count.return_value=1
            frame.get_by_role.side_effect=lambda role,**kw:title if role=='textbox' else modal if role=='dialog' else back if kw.get('name')=='Back' else save
            frame.locator.return_value=popup;popup.filter.return_value=popup;popup.count.return_value=1
            labels,ranges=MagicMock(),MagicMock()
            labels.count.side_effect=lambda:len(state['rows']);ranges.count.side_effect=lambda:2*len(state['rows'])
            def control(index,label=False):
                node=MagicMock();row=index if label else index//2;key='label' if label else ('from','to')[index%2]
                node.input_value.side_effect=lambda:str(state['rows'][row][key])
                node.is_enabled.side_effect=lambda:label or index not in (0,2*len(state['rows'])-1)
                node.fill.side_effect=lambda text:state['rows'][row].__setitem__(key,text if label else int(text))
                return node
            labels.nth.side_effect=lambda index:control(index,True);ranges.nth.side_effect=control
            def popup_controls(role,**kw):
                if role!='textbox':raise AssertionError('Captured tier popover has no Save/Cancel footer')
                return labels if kw.get('name')=='Label' else ranges
            popup.get_by_role.side_effect=popup_controls
            modal.get_by_role.return_value=save
            modal.locator.return_value=save
            def resize(node,before,transitions):
                self.assertEqual(state['rows'],before);state['rows']=deepcopy(transitions[-1]['expected_tiers'])
                return state['rows']
            def reopen(*args):
                if lost:state['rows']=deepcopy(value['expected_tiers'])
            job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',{'location_id':'LOC',
                'location_name':'Fixture','start_url':page.url,'configuration':value}),Path('.'))
            self.assertEqual(job['steps'][0]['action'],'quiz_configuration')
            with patch.object(quiz_ui,'_read_lifecycle_tiers',side_effect=lambda node:deepcopy(state['rows'])), \
                    patch.object(quiz_ui,'_resize_tiers',side_effect=resize) as resized, \
                    patch.object(runner,'click',side_effect=lambda node:node.click()), \
                    patch.object(runner,'fill',side_effect=lambda node,text:node.fill(text)), \
                    patch.object(runner,'visible',return_value=False), \
                    patch.object(runner,'wait_until',side_effect=lambda predicate,message:self.assertTrue(predicate())), \
                    patch.object(assessments,'reopen_editor',side_effect=reopen) as reopened:
                if lost:
                    with self.assertRaisesRegex(runner.Stop,'baseline differs'):
                        quiz_ui.configure(page,job['steps'][0])
                else:
                    receipt=quiz_ui.configure(page,job['steps'][0])
                    self.assertEqual(receipt['tiers'],value['tiers'])
                    self.assertFalse(receipt['submission_verified'])
                resized.assert_called_once();reopened.assert_called_once()
                modal.locator.assert_called_once_with('#modal-footer-btn-positive-action')
                self.assertGreater(state['saves'],0)

    def surface(self,rows):
        popup=MagicMock();state=deepcopy(rows);collections={key:MagicMock() for key in ('label','from','to','remove')}
        for collection in collections.values():collection.count.return_value=len(state)
        def node(key,index):
            control=MagicMock();control.input_value.side_effect=lambda:str(state[index][key])
            control.is_enabled.return_value=(index!=0 if key in ('from','remove') else index!=len(state)-1 if key=='to' else True)
            row=MagicMock();row.locator.return_value.count.return_value=1
            control.locator.return_value.locator.return_value.locator.return_value.locator.return_value=row
            return control
        controls={key:[node(key,i) for i in range(len(state))] for key in collections}
        for key,collection in collections.items():collection.nth.side_effect=lambda i,key=key:controls[key][i]
        selectors={'[id="tier-label"] input':'label','[id="from-percent"] input':'from',
            '[id="to-percent"] input':'to','button#remove-tier':'remove'}
        popup.locator.side_effect=lambda selector:collections[selectors[selector]]
        return popup,controls

    def test_captured_per_row_control_and_endpoint_binding(self):
        popup,controls=self.surface(ADDED)
        self.assertEqual(quiz_ui._read_lifecycle_tiers(popup),ADDED)
        controls['from'][0].is_enabled.return_value=True
        with self.assertRaisesRegex(runner.Stop,'captured rows'):quiz_ui._read_lifecycle_tiers(popup)


if __name__=='__main__':unittest.main()
