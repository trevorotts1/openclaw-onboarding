"""Date & time settings use captured native owners and finite state transitions."""
from copy import deepcopy
from pathlib import Path
import importlib
import unittest
from unittest.mock import MagicMock, patch
import recipe_cli
import skill6_playwright as runner
from test_form_widget_families import inputs, properties, receipt

native = importlib.import_module('playwright_recipes.form_widget_families')
datetime = importlib.import_module('playwright_recipes.form_datetime')


class DateTimeFields(unittest.TestCase):
    def test_existing_profile_preserves_canonical_metadata_and_actual_ampersand_query(self):
        source = inputs('date_time')
        source['widget_fields']['expected_fields']=[{'kind':'date_time','index':1,'properties':deepcopy(source['widget_fields']['fields'][0]['desired'])}]
        source['widget_fields']['fields'][0]['index']=1
        before = source['widget_fields']['expected_fields'][0]['properties']
        before['query_key'] = 'date_&_time_10ow3'
        source['widget_fields']['fields'][0]['desired']['query_key'] = before['query_key']
        source['widget_fields']['fields'][0]['desired']['label'] = 'Preferred appointment'
        spec = runner.validate_job(recipe_cli.compile_recipe('forms.configure', source), Path('.'))['steps'][0]
        native.validate_receipt(receipt(spec), spec)
        self.assertEqual(native.PROFILES['date_time']['input_count'], 2)
        for key, value in (('unique_key', 'contact.foreign'), ('custom_field_name', 'Renamed global field'),
                           ('query_key', 'unmeasured?query'), ('date_range', 'past'), ('default_time', 'custom')):
            bad = deepcopy(source)
            bad['widget_fields']['fields'][0]['desired'][key] = value
            with self.subTest(key=key), self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('forms.configure', bad)
        bad = inputs('number'); bad['widget_fields']['fields'][0]['desired']['query_key'] = 'date_&_time'
        with self.assertRaises(runner.Stop): recipe_cli.compile_recipe('forms.configure', bad)

    def controls(self, state):
        frame = MagicMock(); panel = frame.locator.return_value
        panel.count.return_value = 1; panel.is_visible.return_value = True
        events = []
        def locator(selector):
            node = MagicMock(); node.count.return_value = 1; node.is_visible.return_value = True
            node.is_enabled.return_value = True; node.selector = selector
            if selector in ('#dateMode .n-base-selection-input','#timeMode .n-base-selection-input'):
                node.get_attribute.side_effect = lambda name: ('Any date' if selector.startswith('#dateMode') else 'Any time') if name == 'title' else None
            elif selector == '#picker-settings[role="checkbox"]':
                node.get_attribute.side_effect = lambda name: ('true' if state['disable_picker'] else 'false') if name == 'aria-checked' else None
            else:
                for key, (prefix, choices) in datetime.GROUPS.items():
                    if selector.startswith('#' + prefix):
                        choice = selector.removeprefix('#' + prefix)
                        node.get_attribute.side_effect = lambda name, k=key, c=choice: ('dt-segmented-button--active' if state[k] == c else '') if name == 'class' else None
                        break
            return node
        panel.locator.side_effect = locator
        def click(node):
            selector = node.selector; events.append(selector)
            if selector == '#picker-settings[role="checkbox"]': state['disable_picker'] = not state['disable_picker']
            for key, (prefix, choices) in datetime.GROUPS.items():
                if selector.startswith('#' + prefix): state[key] = selector.removeprefix('#' + prefix)
        return frame, panel, events, click

    def test_segmented_settings_update_exact_owned_buttons_and_drift_refuses(self):
        before = {key: properties('date_time')[key] for key in datetime.EXTRA}
        desired = {**before, 'date_format': 'dd-mm-yyyy', 'date_separator': 'slash',
                   'time_format': '12', 'disable_picker': True}
        state = deepcopy(before); frame, panel, events, click = self.controls(state)
        with patch.object(datetime, 'click', side_effect=click):
            datetime.write_options(frame, before, desired)
            self.assertEqual(datetime.read_options(frame), desired)
        self.assertEqual([event for event in events if event.startswith('#')],
                         ['#date-format-dd-mm-yyyy', '#date-separator-slash', '#time-format-12', '#picker-settings[role="checkbox"]'])
        state['date_format'] = 'mm-dd-yyyy'; events.clear()
        with patch.object(datetime, 'click', side_effect=click), self.assertRaisesRegex(runner.Stop, 'preflight'):
            datetime.write_options(frame, before, desired)
        self.assertEqual([event for event in events if event.startswith('#')], [])

    def test_time_only_sibling_profile_never_requires_or_invents_date_controls(self):
        source=inputs('time')
        source['widget_fields']['fields'][0]['desired']['label']='Call time'
        spec=runner.validate_job(recipe_cli.compile_recipe('forms.configure',source),Path('.'))['steps'][0]
        native.validate_receipt(receipt(spec),spec)
        before={key:properties('time')[key] for key in datetime.TIME_EXTRA}
        desired={**before,'time_format':'12','disable_picker':True}
        state=deepcopy(before);frame,panel,events,click=self.controls(state)
        with patch.object(datetime,'click',side_effect=click):
            datetime.write_options(frame,before,desired,kind='time')
            self.assertEqual(datetime.read_options(frame,kind='time'),desired)
        self.assertEqual([event for event in events if event.startswith('#')],
                         ['#time-format-12','#picker-settings[role="checkbox"]'])
        calls=[call.args[0] for call in panel.locator.call_args_list]
        self.assertFalse(any(selector.startswith(('#date-format','#date-separator','#dateMode')) for selector in calls))

    def test_unmeasured_custom_time_refuses_without_writes(self):
        state = {key: properties('date_time')[key] for key in datetime.EXTRA}
        frame, panel, events, click = self.controls(state)
        state['default_time'] = 'custom'
        with patch.object(datetime, 'click', side_effect=click), self.assertRaisesRegex(runner.Stop, 'custom default time'):
            datetime.read_options(frame)
        self.assertEqual([event for event in events if event.startswith('#')], [])


if __name__ == '__main__': unittest.main()
