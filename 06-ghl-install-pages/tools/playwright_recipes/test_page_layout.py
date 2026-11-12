import unittest
from unittest.mock import patch
from playwright_recipes import page_layout
from playwright_recipes.skill6_playwright import Stop, page_builder_ready


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


class FakePage:
    url = "https://example.test/editor"
    def goto(self, *args, **kwargs): pass


class PageLayoutTests(unittest.TestCase):
    def test_builder_ready_waits_before_dismissing_ask_ai(self):
        events = []
        class Button:
            def __init__(self, name): self.name = name
            def wait_for(self, **kwargs): events.append(('wait', self.name, kwargs['state']))
        back, ai = Button('Back'), Button('Close Ask AI')
        class Frame:
            def get_by_role(self, role, **kwargs):
                return back if kwargs['name'] == 'Back' else ai
        frame = Frame()
        with patch('playwright_recipes.skill6_playwright.builder', return_value=frame), \
             patch('playwright_recipes.skill6_playwright.visible', side_effect=lambda obj: events.append(('visible', obj.name)) or True), \
             patch('playwright_recipes.skill6_playwright.click', side_effect=lambda obj: events.append(('click', obj.name))):
            self.assertIs(page_builder_ready(None), frame)
        self.assertEqual(events, [('wait', 'Back', 'visible'), ('visible', 'Close Ask AI'), ('click', 'Close Ask AI')])

    def test_existing_layout_order_and_parent_are_preserved(self):
        before = [{'id': 'a', 'parent': 's'}, {'id': 'b', 'parent': 's'}]
        self.assertTrue(page_layout._preserves_order(before, [before[0], {'id':'new'}, before[1]]))
        self.assertFalse(page_layout._preserves_order(before, list(reversed(before))))
        self.assertFalse(page_layout._preserves_order(before, [before[0], {'id':'b','parent':'other'}]))

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
        with patch('playwright_recipes.skill6_playwright.page_builder_ready', return_value=frame), \
             patch('playwright_recipes.skill6_playwright.add_tile'), \
             patch('playwright_recipes.skill6_playwright.native_order_inventory', return_value={}), \
             patch('playwright_recipes.skill6_playwright.save_page') as save, \
             patch('playwright_recipes.skill6_playwright.wait_until'), \
             patch.object(page_layout, '_inventory', side_effect=[before, after]):
            with self.assertRaises(Stop):
                page_layout.configure(FakePage(), {'layout': {'section_id':'s','columns':1}})
            save.assert_not_called()

    def test_multi_section_inserts_using_exact_empty_slot(self):
        class Group:
            def __init__(self, count): self.n = count
            def count(self): return self.n
        class Target(Group):
            def locator(self, selector):
                self.selector = selector
                return slot
        slot = Group(1)
        target = Target(1)
        preset = Group(1)
        class MultiFrame:
            def locator(self, selector):
                if selector == '.c-section': return Group(2)
                if selector == '.c-section[id="s"]': return target
                if selector == 'div.gui__builder-card[id="2 Column"]': return preset
                raise AssertionError(selector)
        before = [{'kind':'section','id':'other','section_id':'other','row_id':None},
                  {'kind':'section','id':'s','section_id':'s','row_id':None}]
        after = before + [{'kind':'row','id':'r','section_id':'s','row_id':'r'},
                          {'kind':'column','id':'c1','section_id':'s','row_id':'r'},
                          {'kind':'column','id':'c2','section_id':'s','row_id':'r'}]
        with patch('playwright_recipes.skill6_playwright.page_builder_ready', return_value=MultiFrame()), \
             patch('playwright_recipes.skill6_playwright.click') as click, \
             patch('playwright_recipes.skill6_playwright.add_tile') as global_picker, \
             patch('playwright_recipes.skill6_playwright.wait_until'), \
             patch('playwright_recipes.skill6_playwright.native_order_inventory', return_value={}), \
             patch('playwright_recipes.skill6_playwright.save_page'), \
             patch.object(page_layout, 'resolve_column'), \
             patch.object(page_layout, '_inventory', side_effect=[before, after, after]):
            result = page_layout.configure(FakePage(), {'layout': {'section_id':'s','columns':2}})
        self.assertEqual(target.selector, ':scope > .inner > .empty-slot .empty-component')
        self.assertEqual([call.args[0] for call in click.call_args_list], [slot, preset])
        global_picker.assert_not_called()
        self.assertEqual(result['column_ids'], ['c1','c2'])

    def test_populated_section_selects_and_inserts_after_exact_row(self):
        class Item:
            def __init__(self, count=1): self.n = count
            def count(self): return self.n
        selected, label, column, crumb = Item(), Item(), Item(), Item()
        label.inner_text = lambda: '2 Column Row'
        class Anchor(Item):
            def evaluate(self, expression):
                return ['c1', 'c2'] if 'querySelectorAll' in expression else 's'
            def locator(self, selector):
                return selected if selector == ':scope > .ui-row.selected' else label
        anchor = Anchor()
        class Navigation:
            def get_by_role(self, role, **kwargs):
                assert role == 'button' and kwargs['name'] == '2 Column Row'
                return crumb
        class Dialog:
            def get_by_role(self, role, **kwargs): return Item(0)
        class Frame:
            def locator(self, selector):
                if selector == '.c-section': return Item(2)
                if selector == '.c-section[id="s"]': return Item()
                if selector == '.c-row[id="old"]': return anchor
                raise AssertionError(selector)
            def get_by_role(self, role, **kwargs):
                return Navigation() if role == 'navigation' else Dialog()
        before = [{'kind':'section','id':'s','section_id':'s','row_id':None},
                  {'kind':'row','id':'old','section_id':'s','row_id':'old'}]
        after = before + [{'kind':'row','id':'new','section_id':'s','row_id':'new'},
                          {'kind':'column','id':'newcol','section_id':'s','row_id':'new'}]
        with patch('playwright_recipes.skill6_playwright.page_builder_ready', return_value=Frame()), \
             patch('playwright_recipes.skill6_playwright.click') as click, \
             patch('playwright_recipes.skill6_playwright.add_tile') as picker, \
             patch('playwright_recipes.skill6_playwright.wait_until'), \
             patch('playwright_recipes.skill6_playwright.native_order_inventory', return_value={}), \
             patch('playwright_recipes.skill6_playwright.save_page'), \
             patch.object(page_layout, 'resolve_column', return_value=column), \
             patch.object(page_layout, '_inventory', side_effect=[before, after, after]):
            result = page_layout.configure(FakePage(), {'layout': {'section_id':'s','columns':1,'after_row_id':'old'}})
        self.assertEqual([call.args[0] for call in click.call_args_list], [column, crumb])
        picker.assert_called_once()
        self.assertEqual(result['row_id'], 'new')

    def test_existing_order_cannot_move_before_save(self):
        class Sections:
            first = type('Section', (), {'get_attribute': lambda self, name: 's'})()
            def count(self): return 1
        class CreationFrame:
            def locator(self, selector): return Sections()
        before = [{'kind':'section','id':'s','section_id':'s','row_id':None}]
        after = before + [{'kind':'row','id':'r','section_id':'s','row_id':'r'},
                          {'kind':'column','id':'c','section_id':'s','row_id':'r'}]
        order = {'payment': {'id':'payment', 'section_id':'s', 'row_id':'old', 'column_id':'oldcol'}}
        moved = {'payment': dict(order['payment'], column_id='newcol')}
        with patch('playwright_recipes.skill6_playwright.page_builder_ready', return_value=CreationFrame()), \
             patch('playwright_recipes.skill6_playwright.add_tile'), \
             patch('playwright_recipes.skill6_playwright.wait_until'), \
             patch('playwright_recipes.skill6_playwright.native_order_inventory', side_effect=[order, moved]), \
             patch('playwright_recipes.skill6_playwright.save_page') as save, \
             patch.object(page_layout, 'resolve_column'), \
             patch.object(page_layout, '_inventory', side_effect=[before, after]):
            with self.assertRaises(Stop):
                page_layout.configure(FakePage(), {'layout': {'section_id':'s','columns':1}})
            save.assert_not_called()

    def test_saved_readback_requires_new_row_and_existing_siblings(self):
        class Sections:
            first = type('Section', (), {'get_attribute': lambda self, name: 's'})()
            def count(self): return 1
        class CreationFrame:
            def locator(self, selector): return Sections()
        before = [{'kind':'section','id':'s','section_id':'s','row_id':None}]
        after = before + [{'kind':'row','id':'r','section_id':'s','row_id':'r'},
                          {'kind':'column','id':'c','section_id':'s','row_id':'r'}]
        with patch('playwright_recipes.skill6_playwright.page_builder_ready', return_value=CreationFrame()), \
             patch('playwright_recipes.skill6_playwright.add_tile'), \
             patch('playwright_recipes.skill6_playwright.wait_until'), \
             patch('playwright_recipes.skill6_playwright.native_order_inventory', return_value={}), \
             patch('playwright_recipes.skill6_playwright.save_page'), \
             patch.object(page_layout, 'resolve_column'), \
             patch.object(page_layout, '_inventory', side_effect=[before, after, before]):
            with self.assertRaises(Stop):
                page_layout.configure(FakePage(), {'layout': {'section_id':'s','columns':1}})

    def test_responsive_width_uses_native_device_and_reads_back(self):
        class Item:
            def count(self): return 1
        class Width(Item):
            values = iter(['100', '85', '100', '85'])
            def input_value(self): return next(self.values)
            def press(self, key): self.key = key
        class Slider(Item):
            def get_attribute(self, name): return {'min':'30','max':'100'}[name]
        width, slider = Width(), Slider()
        class Row(Item):
            def evaluate(self, expression): return '85%'
        events = []
        class Page:
            url = 'https://example.test/editor'
            def goto(self, *args, **kwargs): events.append('goto')
        class Frame:
            def locator(self, selector): return Item()
            def get_by_placeholder(self, *args, **kwargs): return width
            def get_by_role(self, *args, **kwargs): return slider
        p = {'profile':'funnel_row_width_v1', 'section_id':'s', 'row_id':'r', 'device':'tablet', 'width_percent':85}
        with patch('playwright_recipes.skill6_playwright.page_builder_ready', side_effect=lambda page: events.append('ready') or Frame()), \
             patch('playwright_recipes.skill6_playwright.click'), \
             patch('playwright_recipes.skill6_playwright.fill', side_effect=lambda loc, value: setattr(loc, 'value', value)), \
             patch('playwright_recipes.skill6_playwright.native_order_inventory', return_value={}), \
             patch('playwright_recipes.skill6_playwright.save_page'), \
             patch.object(page_layout, '_select_row', return_value=Row()), \
             patch.object(page_layout, '_inventory', return_value=[]):
            result = page_layout.configure_responsive(Page(), {'responsive':p})
        self.assertEqual(events, ['ready', 'goto', 'ready'])
        self.assertEqual(result['width_percent'], 85)
        self.assertEqual(width.key, 'Tab')
        with self.assertRaises(Stop):
            page_layout.validate_responsive({'responsive': dict(p, device='mobile')})

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
