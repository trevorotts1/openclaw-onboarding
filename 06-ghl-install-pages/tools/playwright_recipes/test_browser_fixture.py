"""Opt-in real Chromium tests against an isolated captured-shape fixture.

Set SKILL6_BROWSER_FIXTURE=1 after installing Playwright's Chromium. CI does so
explicitly; an unavailable browser then fails setup rather than becoming a skip.
This is browser/runtime proof, never a claim of native GHL execution.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

import skill6_playwright as runner


LABELS = [
    'Schedule form visibility', 'Save progress for forms',
    'Generate submission document', 'Show form recommendations',
    'Sticky Contact', 'Create Conversation on Submission',
    'Enable Timezone', 'Use GDPR Compliant Font',
]
INITIAL = [False, True, False, True, False, False, True, False]


def builder_html(mode):
    labels = list(LABELS)
    initial = list(INITIAL)
    if mode.startswith('scheduled'):
        labels.insert(1, 'Agency branding')
        initial[0] = True
        initial.insert(1, True)
    if mode == 'scheduled-wrong-branding':
        labels[1] = 'Unexpected branding control'
    if mode == 'wrong-row':
        labels[3], labels[6] = labels[6], labels[3]
    if mode == 'wrong-count':
        labels.pop()
    rows = ''.join(
        '<div class="settings-row"><button type="button" role="switch" '
        'aria-checked="false"></button><span>' + label + '</span></div>'
        for label in labels
    )
    return '''<!doctype html><html lang="en"><title>Native settings shape fixture</title>
<button type="button" role="tab">Edit</button>
<button type="button" role="tab">Settings</button>
<button type="button" id="save">Save</button>
<main>''' + rows + '''</main>
<script>
const mode = ''' + json.dumps(mode) + ''';
const defaults = ''' + json.dumps(initial) + ''';
const switches = [...document.querySelectorAll('[role="switch"]')];
const stored = JSON.parse(localStorage.getItem('settings') || 'null');
switches.forEach((control,index) => {
  control.setAttribute('aria-checked', String((stored || defaults)[index]));
  control.onclick = () => control.setAttribute('aria-checked',
    String(control.getAttribute('aria-checked') !== 'true'));
});
document.getElementById('save').onclick = () => {
  localStorage.setItem('saves', String(Number(localStorage.getItem('saves') || 0)+1));
  if (!mode.endsWith('lost-save')) localStorage.setItem('settings', JSON.stringify(
    switches.map(control => control.getAttribute('aria-checked') === 'true')));
};
</script></html>'''


@contextmanager
def fixture_server(render):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = render(self.path).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@unittest.skipUnless(os.environ.get('SKILL6_BROWSER_FIXTURE') == '1',
                     'Real Chromium fixture is opt-in; CI explicitly enables it')
class RealBrowserFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Do not catch ImportError or launch failure: selected tests must fail
        # when the declared browser dependency is unavailable.
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.profile = TemporaryDirectory(prefix='skill6-fixture-profile-')
        try:
            cls.context = cls.playwright.chromium.launch_persistent_context(
                cls.profile.name, headless=True
            )
        except BaseException:
            try:
                cls.playwright.stop()
            finally:
                cls.profile.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            cls.context.close()
        finally:
            try:
                cls.playwright.stop()
            finally:
                cls.profile.cleanup()

    @contextmanager
    def page_for(self, mode='normal'):
        # Different ports make the builder genuinely cross-origin. The final
        # maintained frame locator and Playwright transport must handle it.
        with fixture_server(lambda path: builder_html(parse_qs(urlsplit(path).query).get('mode', ['normal'])[0])) as child:
            def shell(_):
                return '<!doctype html><html><title>Fixture shell</title><iframe name="form-builder-app" src="' + child + '/builder?mode=' + mode + '"></iframe></html>'
            with fixture_server(shell) as parent:
                page = self.context.new_page()
                try:
                    page.goto(parent + '/v2/location/FIXTURE/form-builder-v2/fixture', wait_until='load')
                    # A single persistent fixture context owns the suite. Clear
                    # only this local builder's state once before a test, so OS
                    # port reuse cannot leak state between tests. Reload checks
                    # performed by the executor still see the saved values.
                    child_frame = next(frame for frame in page.frames
                                       if frame.name == 'form-builder-app')
                    child_frame.evaluate('() => localStorage.clear()')
                    page.reload(wait_until='load')
                    yield page
                finally:
                    page.close()

    def saved(self, page):
        frames = [frame for frame in page.frames if frame.name == 'form-builder-app']
        self.assertEqual(len(frames), 1)
        return frames[0].evaluate('() => ({saves:Number(localStorage.getItem("saves") || 0), settings:JSON.parse(localStorage.getItem("settings") || "null")})')

    def test_actual_executor_saves_and_reloads_seven_settings_cross_origin(self):
        values = {
            'save_progress': False, 'submission_document': True,
            'recommendations': False, 'sticky_contact': True,
            'conversation_on_submission': True, 'capture_timezone': False,
            'gdpr_font': True,
        }
        with self.page_for() as page:
            result = runner.form_settings(page, {'settings': values})
            self.assertEqual(result['status'], 'FORM_SETTINGS_PERSISTED')
            observed = self.saved(page)
            self.assertEqual(observed['saves'], 1)
            self.assertEqual(observed['settings'], [False, False, True, False, True, True, False, True])

    def test_changed_row_identity_refuses_before_save(self):
        with self.page_for('wrong-row') as page:
            with self.assertRaises(runner.Stop):
                runner.form_settings(page, {'settings': {'recommendations': False}})
            self.assertEqual(self.saved(page)['saves'], 0)

    def test_existing_schedule_and_branding_are_preserved_while_flags_shift(self):
        with self.page_for('scheduled') as page:
            result = runner.form_settings(page, {'settings': {
                'save_progress': False, 'capture_timezone': False, 'gdpr_font': True,
            }})
            self.assertEqual(result['status'], 'FORM_SETTINGS_PERSISTED')
            observed = self.saved(page)
            self.assertEqual(observed['saves'], 1)
            self.assertEqual(observed['settings'], [True, True, False, False, True, False, False, False, True])

    def test_scheduled_form_with_unknown_branding_row_never_saves(self):
        with self.page_for('scheduled-wrong-branding') as page:
            with self.assertRaises(runner.Stop):
                runner.form_settings(page, {'settings': {'capture_timezone': False}})
            self.assertEqual(self.saved(page)['saves'], 0)

    def test_scheduled_form_lost_save_does_not_pass_reopen(self):
        with self.page_for('scheduled-lost-save') as page:
            with self.assertRaises(runner.Stop):
                runner.form_settings(page, {'settings': {'capture_timezone': False}})
            self.assertEqual(self.saved(page)['saves'], 1)

    def test_changed_control_count_refuses_before_save(self):
        original_wait = runner.wait_until
        with self.page_for('wrong-count') as page, patch.object(
            runner, 'wait_until', side_effect=lambda fn, message, timeout=45: original_wait(fn, message, timeout=.5)
        ):
            with self.assertRaises(runner.Stop):
                runner.form_settings(page, {'settings': {'recommendations': False}})
            self.assertEqual(self.saved(page)['saves'], 0)

    def test_save_click_without_persistence_is_failure_after_reload(self):
        with self.page_for('lost-save') as page:
            with self.assertRaises(runner.Stop):
                runner.form_settings(page, {'settings': {'capture_timezone': False}})
            observed = self.saved(page)
            self.assertEqual(observed['saves'], 1)
            self.assertIsNone(observed['settings'])


if __name__ == '__main__':
    unittest.main()
