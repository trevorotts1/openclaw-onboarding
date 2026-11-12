"""Saved-section intent validation and explicit synchronization scope guards."""
import unittest
from unittest.mock import Mock, patch

from playwright_recipes import saved_section
from playwright_recipes.skill6_playwright import Stop
from playwright_recipes import saved_section_profiles


ROWS = [
    {'id': 'sec_template', 'name': 'Hero Copy', 'scope': 'template'},
    {'id': 'sec_global', 'name': 'Promo Global', 'scope': 'global'},
    {'id': 'sec_universal', 'name': 'Footer Universal', 'scope': 'universal'},
]


def step(operation, **fields):
    payload = {'operation': operation, 'profile': 'saved-assets-new',
               'expected_saved_inventory': ROWS}
    payload.update(fields)
    return {'action': 'saved_section', 'saved_section': payload}


class SavedSectionTests(unittest.TestCase):
    def test_native_ui_name_scope_identity_and_save_contract(self):
        rows = [{'name':'Hero', 'scope':'template'}]
        payload = step('reuse', expected_saved_inventory=rows, saved_section_name='Hero',
                       scope='template', destination_section_id='a',
                       expected_section_inventory=['a', 'b'])
        self.assertEqual(saved_section.validate(payload)['scope'], 'template')
        with self.assertRaises(Stop):
            saved_section.validate({**payload, 'saved_section':{
                **payload['saved_section'], 'expected_saved_inventory':rows + rows}})
        for scope in ('template', 'global', 'universal'):
            payload = step('save', expected_saved_inventory=[], scope=scope,
                           saved_section_name='Reusable hero', source_section_id='a',
                           expected_section_inventory=['a', 'b'])
            self.assertEqual(saved_section.validate(payload)['source_section_id'], 'a')
        self.assertIsInstance(saved_section_profiles.get_profile('saved-assets-new'),
                              saved_section_profiles.NativeSavedAssets)

    def test_exact_inventory_rows_and_operation_contract(self):
        self.assertEqual(saved_section.validate(step('inventory'))['operation'], 'inventory')
        for bad in (
            step('inventory', extra=True),
            step('inventory', expected_saved_inventory=ROWS + [ROWS[0]]),
            step('inventory', expected_saved_inventory=[{'id':'x','name':'x','scope':'shared'}]),
            {'action':'saved_section', 'saved_section':{}},
        ):
            with self.subTest(bad=bad), self.assertRaises(Stop): saved_section.validate(bad)

    def test_reuse_binds_exact_asset_and_destination(self):
        good = step('reuse', saved_section_id='sec_template', saved_section_name='Hero Copy',
                    destination_section_id='destination', expected_section_inventory=[])
        self.assertEqual(saved_section.validate(good)['saved_section_id'], 'sec_template')
        bad_name = step('reuse', saved_section_id='sec_template', saved_section_name='Other',
                        destination_section_id='destination', expected_section_inventory=[])
        with self.assertRaises(Stop): saved_section.validate(bad_name)
        bad_target = step('reuse', saved_section_id='sec_template', saved_section_name='Hero Copy',
                          destination_section_id='../foreign', expected_section_inventory=[])
        with self.assertRaises(Stop): saved_section.validate(bad_target)

    def test_edit_must_explicitly_match_native_sync_scope(self):
        for scope in ('template', 'global', 'universal'):
            payload = step('edit', saved_section_id='sec_' + scope,
                           saved_section_name={'template':'Hero Copy','global':'Promo Global',
                                               'universal':'Footer Universal'}[scope],
                           scope=scope, expected_section_inventory=[], requested_section_inventory=[])
            self.assertEqual(saved_section.validate(payload)['scope'], scope)
        for scope, ident, name in (('universal','sec_global','Promo Global'),
                                   ('global','sec_template','Hero Copy')):
            payload = step('edit', saved_section_id=ident, saved_section_name=name, scope=scope,
                           expected_section_inventory=[], requested_section_inventory=[])
            with self.subTest(scope=scope), self.assertRaises(Stop): saved_section.validate(payload)

    def test_scope_mismatch_never_opens_browser_or_profile(self):
        payload = step('edit', saved_section_id='sec_global', saved_section_name='Promo Global',
                       scope='universal', expected_section_inventory=[], requested_section_inventory=[])
        page = Mock()
        with patch('playwright_recipes.saved_section_profiles.get_profile') as profile:
            with self.assertRaises(Stop): saved_section.configure(page, payload)
        profile.assert_not_called()
        page.assert_not_called()


class NativeCanvas:
    def __init__(self, drift=False):
        self.sections = ['a', 'b']
        self.forms = [{'id':'order_a', 'section_id':'a', 'row_id':'row_a', 'column_id':'col_a'}]
        self.library = [{'name':'Hero', 'scope':'template'}]
        self.dragged = self.moved = self.saved = self.reopened = 0
        self.drift = drift

    def locator(self, selector):
        return CanvasLocator(self, selector)

    def get_by_text(self, text, **kwargs):
        return CanvasLocator(self, 'name:' + text)
    def get_by_role(self, role, **kwargs):
        return CanvasLocator(self, 'role:' + role)


class CanvasLocator:
    def __init__(self, canvas, selector): self.canvas, self.selector = canvas, selector
    def filter(self, **kwargs): return self
    def count(self): return 1
    def wait_for(self, **kwargs): pass
    def bounding_box(self): return {'width':800, 'height':200}
    def hover(self, **kwargs): pass
    def locator(self, selector): return CanvasLocator(self.canvas, selector)
    def evaluate_all(self, expression):
        if self.selector == '.c-section': return list(self.canvas.sections)
        if self.selector == '.c-order-form': return list(self.canvas.forms)
        raise AssertionError('Unexpected native inventory selector: ' + self.selector)
    def drag_to(self, target):
        self.canvas.dragged += 1
        # The captured native builder inserts the saved Section before the anchor.
        self.canvas.sections.insert(0, 'new_section')
    def click(self, **kwargs):
        if 'Move Down' not in self.selector and 'Move Up' not in self.selector:
            return
        self.canvas.moved += 1
        index = self.canvas.sections.index('new_section')
        delta = 1 if 'Move Down' in self.selector else -1
        self.canvas.sections[index], self.canvas.sections[index + delta] = (
            self.canvas.sections[index + delta], self.canvas.sections[index])


class OwnedPage:
    url = 'https://app.gohighlevel.com/location/loc/page-builder/page'
    def __init__(self, canvas): self.canvas = canvas
    def goto(self, url, **kwargs):
        self.canvas.reopened += 1
        if self.canvas.drift: self.canvas.forms = []


def immediate_readback(predicate, message, **kwargs):
    if not predicate(): raise Stop(message)


class NativeSavedSectionExecution(unittest.TestCase):
    def run_fixture(self, canvas):
        page = OwnedPage(canvas)
        payload = step('reuse', expected_saved_inventory=canvas.library,
                       saved_section_name='Hero', scope='template',
                       destination_section_id='a', expected_section_inventory=['a','b'])
        profile = saved_section_profiles.get_profile('saved-assets-new')
        def saved(frame): canvas.saved += 1
        with patch('playwright_recipes.skill6_playwright.page_builder_ready', return_value=canvas) as ready, \
             patch('playwright_recipes.skill6_playwright.wait_until', side_effect=immediate_readback), \
             patch('playwright_recipes.skill6_playwright.save_page', side_effect=saved), \
             patch.object(profile, '_open'), \
             patch.object(profile, '_library', side_effect=lambda frame, scope:list(canvas.library)):
            result = saved_section.configure(page, payload)
            saved_section.verify_completed(page, payload, result)
        self.assertEqual(ready.call_count, 3)
        return result

    def test_native_drag_reorder_save_reopen_and_replay_without_duplicate_write(self):
        canvas = NativeCanvas()
        result = self.run_fixture(canvas)
        self.assertEqual(canvas.sections, ['a', 'new_section', 'b'])
        self.assertEqual((canvas.dragged, canvas.moved, canvas.saved, canvas.reopened), (1,1,1,1))
        self.assertEqual(result['status'], 'SAVED_READBACK_VERIFIED')
        self.assertFalse(result['payment_verified'])

    def test_native_form_lost_after_reopen_refuses_completion(self):
        canvas = NativeCanvas(drift=True)
        with self.assertRaisesRegex(Stop, 'Native order forms changed'):
            self.run_fixture(canvas)
        self.assertEqual((canvas.dragged, canvas.saved, canvas.reopened), (1,1,1))

    def test_save_section_keeps_page_and_native_form_then_replay_does_not_duplicate(self):
        canvas, dialog, name_input, save_button, scope_label = (
            NativeCanvas(), Mock(), Mock(), Mock(), Mock())
        page = OwnedPage(canvas)
        dialog.filter.return_value = dialog
        dialog.get_by_role.side_effect = lambda role, **kwargs: (
            name_input if role == 'textbox' else save_button)
        dialog.get_by_text.return_value = scope_label
        name_input.count.return_value = save_button.count.return_value = scope_label.count.return_value = 1
        save_button.click.side_effect = lambda **kwargs: canvas.library.append(
            {'name':'Reusable hero', 'scope':'template'})
        payload = step('save', expected_saved_inventory=list(canvas.library),
                       saved_section_name='Reusable hero', scope='template',
                       source_section_id='a', expected_section_inventory=['a','b'])
        profile = saved_section_profiles.get_profile('saved-assets-new')
        with patch('playwright_recipes.skill6_playwright.page_builder_ready', return_value=canvas) as ready, \
             patch('playwright_recipes.skill6_playwright.wait_until', side_effect=immediate_readback), \
             patch.object(canvas, 'get_by_role', return_value=dialog), \
             patch.object(profile, '_open'), \
             patch.object(profile, '_library', side_effect=lambda frame, scope:list(canvas.library)):
            result = saved_section.configure(page, payload)
            saved_section.verify_completed(page, payload, result)
        self.assertEqual(ready.call_count, 3)
        self.assertEqual(result['status'], 'SAVED_ASSET_READBACK_VERIFIED')
        self.assertEqual(canvas.sections, ['a','b'])
        self.assertEqual((canvas.dragged, canvas.moved, canvas.reopened), (0,0,1))
        self.assertEqual(len(canvas.library), 2)
        name_input.fill.assert_called_once_with('Reusable hero')
        save_button.click.assert_called_once()
        self.assertFalse(result['payment_verified'])


if __name__ == '__main__': unittest.main()
