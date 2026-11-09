import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import form_submission as submission
import recipe_cli
import skill6_playwright as runner
from test_assessments import list_reopen_surface


class SubmissionValidation(unittest.TestCase):
    def test_approved_message_is_literal_normalized_plain_text(self):
        result = submission.validate({'mode': 'Message', 'message': '  Thanks\r\n<b>Literal text</b>  '})
        self.assertEqual(result['message'], 'Thanks\n<b>Literal text</b>')

    def test_redirect_must_be_https_without_credentials(self):
        for url in ('http://example.com', 'javascript:alert(1)', 'https://name:password@example.com',
                    'https://@example.com', 'https://example.com/\x00',
                    'https://example.com:bad', 'https://example.com/a b', 'https://', True):
            with self.subTest(url=url), self.assertRaises(submission.SubmissionError):
                submission.validate({'mode': 'Redirect to URL', 'redirect_url': url})
        value = 'https://example.com/thanks?utm_source=form#confirmed'
        self.assertEqual(submission.validate({'mode': 'Redirect to URL', 'redirect_url': value})['redirect_url'], value)

    def test_unknown_settings_unused_values_and_unapproved_order_modes_refuse(self):
        for config in ({'mode': 'Message', 'message': ''},
                       {'mode': 'Message', 'message': 'Thanks', 'redirect_url': 'https://example.com'},
                       {'mode': 'Redirect to URL', 'redirect_url': 'https://example.com', 'message': 'ignored'},
                       {'mode': 'Message', 'message': 'Thanks', 'facebook_pixel_id': 'ignored'},
                       {'mode': 'Message', 'message': 'Thanks', 'ack_conditional_precedence': 'true'},
                       {'mode': 'Order Confirmation'},
                       {'mode': 'Order Confirmation', 'checkout_contract': {'status': 'PASS', 'source': 'fixture'}}):
            with self.subTest(config=config), self.assertRaises(submission.SubmissionError):
                submission.validate(config)

    def test_recipe_compiles_and_validates_the_native_submission_action(self):
        inputs = {'location_id': 'fixture', 'location_name': 'Fixture',
                  'start_url': 'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form',
                  'submission': {'mode': 'Message', 'message': 'Approved message'}}
        job = recipe_cli.compile_recipe('forms.submission', inputs)
        self.assertEqual(job['steps'][0]['action'], 'form_submission')
        runner.validate_job(job, Path('.'))


class NativeSubmissionExecution(unittest.TestCase):
    def surface(self, *, precedence=False, persist=True):
        page, frame = MagicMock(), MagicMock()
        page.url = 'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form'
        state = {'mode': 'Message', 'message': 'Old native message', 'redirect': '',
                 'saves': 0, 'mode_clicks': 0, 'fills': 0}
        title = MagicMock()
        title.input_value.return_value = 'ZHC Form Fixture'
        title.count.return_value=1
        save = MagicMock()
        save.count.return_value = 1
        save.is_enabled.return_value = True
        save.click.side_effect = lambda: state.__setitem__('saves', state['saves'] + 1)
        selected, mode_root, menu = MagicMock(), MagicMock(), MagicMock()
        selected.count.return_value = 1
        selected.inner_text.side_effect = lambda: state['mode']
        selected.click.side_effect = lambda: state.__setitem__('mode_clicks', state['mode_clicks'] + 1)
        mode_root.filter.return_value = selected
        def option(name, **kw):
            loc = MagicMock()
            loc.count.return_value = 1
            loc.click.side_effect = lambda: state.__setitem__('mode', name)
            return loc
        menu.get_by_text.side_effect = option
        message, redirect = MagicMock(), MagicMock()
        message.count.return_value = redirect.count.return_value = 1
        message.inner_text.side_effect = lambda: state['message']
        redirect.input_value.side_effect = lambda: state['redirect']
        def fill_value(value, key):
            state[key] = value
            state['fills'] += 1
        message.fill.side_effect = lambda value: fill_value(value, 'message')
        redirect.fill.side_effect = lambda value: fill_value(value, 'redirect')
        def locator(selector):
            return {'.n-base-selection-input__content': mode_root,
                    '.n-base-select-option': menu,
                    'div.tiptap.ProseMirror': message}[selector]
        frame.locator.side_effect = locator
        frame.get_by_placeholder.return_value = redirect
        warning, warning_group = MagicMock(), MagicMock()
        warning.is_visible.return_value = precedence
        warning_group.all.return_value = [warning]
        frame.get_by_text.return_value = warning_group
        frame.get_by_role.side_effect = lambda role, name=None, exact=None: title if role == 'textbox' else save if name == 'Save' else MagicMock()
        page.frame_locator.return_value = frame
        def goto(*args, **kw):
            if not persist:
                state.update(mode='Message', message='Old native message', redirect='')
        page.goto.side_effect = goto
        return page, frame, state

    def run_surface(self, page, frame, config):
        cell=list_reopen_surface(page)
        with patch.object(runner, 'form_builder', return_value=frame), \
             patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value: loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'exact_search', return_value=cell):
            return submission.configure(page, config)

    def test_plain_message_saves_and_reopens_without_generating_html(self):
        page, frame, state = self.surface()
        result = self.run_surface(page, frame, {'mode': 'Message', 'message': '<b>Literal text</b>'})
        self.assertEqual(state['message'], '<b>Literal text</b>')
        self.assertEqual(state['saves'], 1)
        self.assertEqual(state['mode_clicks'], 0)
        self.assertEqual(result['status'], 'FORM_SUBMISSION_SAVED_AND_REOPENED')
        self.assertFalse(result['behavior_verified'])
        self.assertNotIn('<b>Literal text</b>', str(result))

    def test_https_redirect_mode_and_value_are_independently_reopened(self):
        page, frame, state = self.surface()
        result = self.run_surface(page, frame, {'mode': 'Redirect to URL', 'redirect_url': 'https://example.com/approved'})
        self.assertEqual(state['mode'], 'Redirect to URL')
        self.assertEqual(state['redirect'], 'https://example.com/approved')
        self.assertEqual(state['mode_clicks'], 1)
        self.assertEqual(result['independent_readback'], 'VERIFIED')

    def test_conditional_precedence_stops_before_mode_content_or_save_writes(self):
        page, frame, state = self.surface(precedence=True)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame, {'mode': 'Redirect to URL', 'redirect_url': 'https://example.com/approved'})
        self.assertEqual((state['mode_clicks'], state['fills'], state['saves']), (0, 0, 0))

    def test_existing_order_confirmation_is_not_replaced_by_plain_settings(self):
        page, frame, state = self.surface()
        state['mode'] = 'Order Confirmation'
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame, {'mode': 'Message', 'message': 'Approved copy'})
        self.assertEqual((state['mode_clicks'], state['fills'], state['saves']), (0, 0, 0))

    def test_explicit_conditional_ack_does_not_claim_behavior_verified(self):
        page, frame, state = self.surface(precedence=True)
        result = self.run_surface(page, frame, {'mode': 'Message', 'message': 'Approved copy', 'ack_conditional_precedence': True})
        self.assertTrue(result['conditional_precedence_present'])
        self.assertTrue(result['conditional_precedence_acknowledged'])
        self.assertFalse(result['behavior_verified'])

    def test_lost_saved_values_cannot_pass(self):
        for mode, field, value in (('Message', 'message', 'Approved copy'),
                                   ('Redirect to URL', 'redirect_url', 'https://example.com/approved')):
            page, frame, state = self.surface(persist=False)
            with self.subTest(mode=mode), self.assertRaises(runner.Stop):
                self.run_surface(page, frame, {'mode': mode, field: value})
            self.assertEqual(state['saves'], 1)


if __name__ == '__main__':
    unittest.main()
