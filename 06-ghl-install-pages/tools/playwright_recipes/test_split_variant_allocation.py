"""Captured active state and single-confirm allocation writes retain both page IDs."""
import unittest
from unittest.mock import Mock, patch

from test_split_variant_native import inputs, job
from playwright_recipes import split_variant as native
from skill6_playwright import Stop


def active_inputs(*,traffic=49):
    data=inputs()
    data.update(expected_variant_id='VARIANT',allow_creation=False,expected_active=True,
                active=True,expected_control_traffic=50,control_traffic=traffic,
                traffic_change_authorized=traffic!=50)
    return data


def inventory(traffic=50,active=True):
    return {'variant_present':True,'control_page_id':'CONTROL','variant_page_id':'VARIANT',
            'control_traffic':traffic,'active':active}


def instant(fn,message):
    if not fn():raise Stop(message)


class AllocationLifecycleTests(unittest.TestCase):
    def test_active_reuse_is_read_only_and_receipt_binds_active_fresh_state(self):
        data=active_inputs(traffic=50);step=job(data)['steps'][0]
        with patch.object(native,'read_inventory',return_value=inventory()), \
             patch.object(native,'_create') as create,patch.object(native,'_allocate') as allocate:
            result=native.configure(Mock(),step)
        self.assertEqual(result['status'],'SPLIT_VARIANT_REUSED_AND_REOPENED')
        self.assertEqual(result['control_traffic'],50);self.assertTrue(result['active'])
        create.assert_not_called();allocate.assert_not_called()
        self.assertEqual(native.validate_receipt(result,step),result)

    def test_authorized_update_requires_exact_page_identity_and_independent_readback(self):
        step=job(active_inputs())['steps'][0]
        with patch.object(native,'read_inventory',side_effect=[inventory(),inventory(),inventory(49),inventory(49)]), \
             patch.object(native,'_create') as create,patch.object(native,'_allocate') as allocate:
            result=native.configure(Mock(),step)
        self.assertEqual(result['control_traffic'],49);self.assertEqual(result['variant_traffic'],51)
        self.assertEqual(result['status'],'SPLIT_VARIANT_SAVED_AND_REOPENED')
        allocate.assert_called_once();create.assert_not_called()
        for changed in (dict(inventory(49),variant_page_id='OTHER'),inventory(50)):
            with self.subTest(changed=changed), \
                 patch.object(native,'read_inventory',side_effect=[inventory(),inventory(),inventory(49),changed]), \
                 patch.object(native,'_allocate'),self.assertRaises(Stop):
                native.configure(Mock(),step)

    def test_baseline_drift_never_stages_or_applies(self):
        step=job(active_inputs())['steps'][0]
        with patch.object(native,'read_inventory',return_value=inventory(40)), \
             patch.object(native,'_allocate') as allocate,self.assertRaises(Stop):
            native.configure(Mock(),step)
        allocate.assert_not_called()

    def test_slider_stages_each_exact_percentage_and_applies_once(self):
        for start,wanted,expected_key in ((50,49,'ArrowLeft'),(49,51,'ArrowRight')):
            data=active_inputs(traffic=wanted)
            data['expected_control_traffic']=start
            baseline=inventory(start)
            state={'traffic':start};slider,panel,page=Mock(),Mock(),Mock()
            element=Mock();element.count.return_value=1;element.is_visible.return_value=True
            panel.get_by_text.return_value=element;panel.get_by_role.return_value=element
            def press(key,**kwargs):state['traffic']+=1 if key=='ArrowRight' else -1
            slider.press.side_effect=press
            with self.subTest(start=start,wanted=wanted), \
                 patch.object(native,'_ui_state',return_value={key:baseline[key] for key in ('variant_present','control_traffic','active')}), \
                 patch.object(native,'_overview',return_value=(panel,Mock(),Mock())), \
                 patch.object(native,'_slider',side_effect=lambda _:(slider,state['traffic'])), \
                 patch.object(native,'_apply') as apply,patch.object(native,'wait_until',side_effect=instant):
                native._allocate(page,data,baseline)
            self.assertEqual(state['traffic'],wanted)
            self.assertEqual(slider.press.call_count,abs(wanted-start))
            self.assertEqual(slider.press.call_args.args,(expected_key,))
            apply.assert_called_once_with(page,panel)

    def test_inactive_activation_uses_start_then_existing_apply_without_recreating_variant(self):
        data=inputs();data.update(expected_variant_id='VARIANT',allow_creation=False,
                                 active=True,control_traffic=50,traffic_change_authorized=True)
        baseline=inventory(100,False)
        page,panel,start,element,slider=Mock(),Mock(),Mock(),Mock(),Mock()
        start.count.return_value=element.count.return_value=1
        start.is_visible.return_value=element.is_visible.return_value=True
        panel.get_by_role.side_effect=lambda role,**kwargs:start if kwargs.get('name')=='Start split test' else element
        panel.get_by_text.return_value=element
        with patch.object(native,'_ui_state',return_value={key:baseline[key] for key in ('variant_present','control_traffic','active')}), \
             patch.object(native,'_overview',return_value=(panel,Mock(),Mock())), \
             patch.object(native,'_slider',return_value=(slider,50)), \
             patch.object(native,'click') as click,patch.object(native,'_apply') as apply, \
             patch.object(native,'wait_until',side_effect=instant):
            native._allocate(page,data,baseline)
        click.assert_called_once_with(start);slider.press.assert_not_called()
        apply.assert_called_once_with(page,panel)


class ActiveInventoryTests(unittest.TestCase):
    def test_running_marker_and_full_statistics_prove_saved_active_shape(self):
        panel,start,running,apply,stats=Mock(),Mock(),Mock(),Mock(),Mock()
        start.count.return_value=0;apply.count.return_value=0
        running.count.return_value=stats.count.return_value=1
        running.is_visible.return_value=stats.is_visible.return_value=True
        panel.get_by_role.side_effect=lambda role,**kwargs:apply if kwargs.get('name')=='Apply' else start
        panel.get_by_text.return_value=running
        panel.locator.return_value=stats
        with patch.object(native,'_overview',return_value=(panel,Mock(),Mock())), \
             patch.object(native,'_variant_present',return_value=True), \
             patch.object(native,'_slider',return_value=(Mock(),50)):
            self.assertEqual(native._ui_state(Mock(),active_inputs()),
                             {'variant_present':True,'control_traffic':50,'active':True})
            stats.count.return_value=0
            with self.assertRaisesRegex(Stop,'statistics'):
                native._ui_state(Mock(),active_inputs())
            stats.count.return_value=1;apply.count.return_value=1
            with self.assertRaisesRegex(Stop,'still staged'):
                native._ui_state(Mock(),active_inputs())


class ConfirmationTests(unittest.TestCase):
    def exercise(self,kinds):
        page,panel,button=Mock(),Mock(),Mock()
        state={'staged':True,'listener':None};dialogs=[]
        button.count.side_effect=lambda:int(state['staged'])
        button.is_visible.return_value=True;button.is_enabled.return_value=True
        panel.get_by_role.return_value=button
        page.on.side_effect=lambda event,listener:state.update(listener=listener)
        for kind in kinds:
            dialog=Mock();dialog.type=kind
            dialog.accept.side_effect=lambda:state.update(staged=False)
            dialogs.append(dialog)
        def click(_):
            for dialog in dialogs:state['listener'](dialog)
        with patch.object(native,'click',side_effect=click),patch.object(native,'wait_until',side_effect=instant):
            try:result=native._apply(page,panel)
            except Stop as error:result=error
        page.remove_listener.assert_called_once_with('dialog',state['listener'])
        return result,dialogs

    def test_only_one_confirm_from_apply_is_accepted(self):
        result,dialogs=self.exercise(['confirm'])
        self.assertIsNone(result);dialogs[0].accept.assert_called_once();dialogs[0].dismiss.assert_not_called()

    def test_missing_wrong_or_second_dialog_is_never_silently_accepted(self):
        for kinds in ([],['alert'],['confirm','confirm']):
            with self.subTest(kinds=kinds):
                result,dialogs=self.exercise(kinds)
                self.assertIsInstance(result,Stop)
                if kinds==['alert']:dialogs[0].dismiss.assert_called_once();dialogs[0].accept.assert_not_called()
                if len(kinds)>1:dialogs[1].dismiss.assert_called_once();dialogs[1].accept.assert_not_called()


if __name__=='__main__':unittest.main()
