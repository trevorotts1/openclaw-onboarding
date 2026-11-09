"""An assertion against edited UI is not independent saved-object readback."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import skill6_playwright as runner
import test_editor_hydration as hydration


class RecordedOptionsEvidenceTests(unittest.TestCase):
    def test_click_navigation_cannot_send_the_next_fill_to_another_target(self):
        base = 'https://app.convertandflow.com/v2/location/FIXTURE/form-builder-v2/FORM'
        destinations = [base.replace('/FIXTURE/', '/FOREIGN/'),
                        base.replace('app.convertandflow.com', 'foreign.invalid'),
                        base.replace('/FORM', '/OTHER_FORM')]
        for destination in destinations:
            page = hydration.Page('form-builder-v2/FORM')
            page.frames['form-builder-app'] = 1
            control = Mock()
            control.count.return_value = 1
            control.evaluate.return_value = 'Open appearance'
            control.click.side_effect = lambda **_kwargs: setattr(page, 'url', destination)
            target = {'by': 'role', 'role': 'button', 'value': 'Open appearance'}
            job = {'location_id': 'FIXTURE', 'location_name': 'Fixture', 'start_url': base,
                   'steps': [{'id': 'options', 'action': 'options',
                              'capture_source': 'fixture:navigation-identity',
                              'steps': [{'action': 'click', 'target': target},
                                        {'action': 'fill', 'target': target, 'value': 'PRIVATE_LOCAL_FIXTURE'},
                                        {'action': 'expect_value', 'target': target, 'value': 'PRIVATE_LOCAL_FIXTURE'}]}]}
            with self.subTest(destination=destination), tempfile.TemporaryDirectory() as root, \
                    patch.object(runner, 'option_locator', return_value=control):
                with self.assertRaises(runner.Stop):
                    runner.run_on_page(page, job, root)
                control.click.assert_called_once()
                control.fill.assert_not_called()
                state = json.loads(Path(root, 'state.json').read_text())
                self.assertEqual(state['status'], 'NEEDS_BROWSER_RECOVERY')
                self.assertEqual(state['current_step_status'], 'INTENT_RECORDED')
                self.assertNotIn('PRIVATE_LOCAL_FIXTURE', json.dumps(state))

    def test_unsaved_ui_assertion_stays_pending_on_first_run_and_replay(self):
        page=Mock()
        control=page.get_by_role.return_value
        control.count.return_value=1
        control.evaluate.return_value='Course title textbox'
        value={'text':'Old title'}
        control.fill.side_effect=lambda text:value.update(text=text)
        control.input_value.side_effect=lambda:value['text']
        target={'by':'role','role':'textbox','value':'Course title'}
        job={'location_id':'FIXTURE','location_name':'Fixture account',
             'start_url':'https://app.convertandflow.com/v2/location/FIXTURE/dashboard',
             'steps':[{'id':'appearance','action':'options',
                'capture_source':'fixture:course-appearance',
                'steps':[{'action':'fill','target':target,'value':'Approved title'},
                         {'action':'expect_value','target':target,'value':'Approved title'}]}]}
        with tempfile.TemporaryDirectory() as directory, patch.object(runner,'assert_tenant'):
            initial=runner.run_on_page(page,job,directory)
            self.assertEqual(initial['status'],'NEEDS_VERIFICATION')
            self.assertEqual(initial['verification_required'],['appearance'])
            state=json.loads((Path(directory)/'state.json').read_text())
            self.assertEqual(state['results'][0]['result']['independent_readback'],'REQUIRED')
            replay=runner.run_on_page(page,job,directory)
            self.assertEqual(replay['status'],'NEEDS_VERIFICATION')
            self.assertEqual(replay['verification_required'],['appearance'])
        control.fill.assert_called_once_with('Approved title')
        page.reload.assert_not_called()


if __name__ == '__main__':unittest.main()
