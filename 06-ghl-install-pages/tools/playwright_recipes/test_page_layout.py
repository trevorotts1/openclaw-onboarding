import unittest
from unittest.mock import patch
from playwright_recipes import page_layout
from playwright_recipes.skill6_playwright import Stop


class Locator:
    def __init__(self, identity, kind, section=None, row=None, columns=None):
        self.identity, self.kind, self.section, self.row, self.columns = identity, kind, section, row, columns
    def count(self): return 1
    def evaluate(self, expression):
        if 'querySelectorAll' in expression: return self.columns
        if "closest('.c-section')" in expression: return self.section
        return self.row


class Empty:
    def count(self): return 0


class Frame:
    def __init__(self):
        self.items = {
            '.c-section[id="s"]': Locator('s', 'section'),
            '.c-row[id="r"]': Locator('r', 'row', section='s', columns=['c1', 'c2']),
            '.c-column[id="c1"]': Locator('c1', 'column', row='r'),
            '.c-column[id="c2"]': Locator('c2', 'column', row='r'),
        }
    def locator(self, selector): return self.items.get(selector, Empty())


class PageLayoutTests(unittest.TestCase):
    def test_validate_all_six_presets_and_reject_invalid(self):
        for n in range(1, 7):
            self.assertEqual(page_layout.validate({'layout': {'section_id':'s', 'columns':n}})['columns'], n)
        for n in (0, 7, True, '2'):
            with self.assertRaises(Stop): page_layout.validate({'layout': {'section_id':'s', 'columns':n}})
        with self.assertRaises(Stop): page_layout.validate({'layout': {'section_id':'s', 'columns':2, 'extra':1}})

    def test_creation_refuses_changed_existing_layout_before_save(self):
        class Sections:
            first = type('Section', (), {'get_attribute': lambda self, name: 's'})()
            def count(self): return 1
        class CreationFrame:
            def locator(self, selector): return Sections()
        frame = CreationFrame()
        before = [{'kind':'section','id':'s','section_id':'s','row_id':None},
                  {'kind':'row','id':'old','section_id':'s','row_id':'old'}]
        after = [{'kind':'section','id':'s','section_id':'s','row_id':None},
                 {'kind':'row','id':'new','section_id':'s','row_id':'new'},
                 {'kind':'row','id':'another','section_id':'s','row_id':'another'}]
        with patch('playwright_recipes.skill6_playwright.builder', return_value=frame), \
             patch('playwright_recipes.skill6_playwright.add_tile'), \
             patch('playwright_recipes.skill6_playwright.save_page') as save, \
             patch('playwright_recipes.skill6_playwright.wait_until'), \
             patch.object(page_layout, '_inventory', side_effect=[before, after]):
            with self.assertRaises(Stop):
                page_layout.configure(None, {'layout': {'section_id':'s','columns':1}})
            save.assert_not_called()

    def test_resolve_id_and_index_with_exact_scope(self):
        f = Frame()
        self.assertIs(page_layout.resolve_column(f, {'section_id':'s','row_id':'r','column_id':'c2','expected_columns':2}), f.items['.c-column[id="c2"]'])
        self.assertIs(page_layout.resolve_column(f, {'section_id':'s','row_id':'r','column_index':0,'expected_columns':2}), f.items['.c-column[id="c1"]'])
        for placement in (
            {'section_id':'s','row_id':'r','column_id':'c2','expected_columns':3},
            {'section_id':'s','row_id':'r','column_index':1},
            {'section_id':'s','row_id':'r','column_id':'other'},
            {'section_id':'s','row_id':'r','column_index':True,'expected_columns':2},
        ):
            with self.assertRaises(Stop): page_layout.resolve_column(f, placement)
        f.items['.c-row[id="r"]'].section = 'other'
        with self.assertRaises(Stop): page_layout.resolve_column(f, {'section_id':'s','row_id':'r','column_id':'c1'})


if __name__ == '__main__': unittest.main()
