import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from playwright_recipes import page_folders as folders
from playwright_recipes.skill6_playwright import Stop

BASE = 'https://app.example/v2/location/LOC/funnels-websites/funnels'

class FolderSafetyTests(unittest.TestCase):
    def test_list_scope_validation(self):
        p = folders._plan('LOC', 'funnel', 'ZHC Test', BASE)
        self.assertEqual(folders._url(p, 'folder_1'), BASE + '?folder=folder_1')
        for url in (BASE + '?folder=other', BASE.replace('/LOC/', '/OTHER/'),
                    BASE.replace('/funnels', '/websites'), 'http://app.example' + BASE[19:]):
            with self.subTest(url=url), self.assertRaises(Stop):
                folders._plan('LOC', 'funnel', 'ZHC Test', url)

    def test_intent_never_replayed_and_completed_receipt_is_bound(self):
        p = folders._plan('LOC', 'funnel', 'ZHC Test', BASE)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'state.json'
            folders._state(path, p, 'INTENT_RECORDED')
            with self.assertRaises(Stop): folders._load(path, p)
            folders._state(path, p, 'VERIFIED', folder_id='id1')
            self.assertEqual(folders._load(path, p)['folder_id'], 'id1')
            with self.assertRaises(Stop): folders._load(path, {**p, 'name': 'different'})

    def test_breadcrumb_is_scoped_and_matches_full_or_truncated_name(self):
        class Locator:
            def __init__(self, page, selector): self.page, self.selector = page, selector
            def locator(self, selector): return Locator(self.page, selector)
            def wait_for(self, **kwargs): pass
            def count(self): return self.page.counts.get(self.selector, 1)
            def is_visible(self): return True
            def inner_text(self): return self.page.title
        class Page:
            def __init__(self, title, counts=None): self.title, self.counts = title, counts or {}
            def locator(self, selector): return Locator(self, selector)
        p = folders._plan('LOC', 'funnel', 'ZHC Folder Name', BASE)
        for title in ('ZHC Folder Name', 'ZHC Folder...', 'ZHC Folder…'):
            folders._breadcrumb(Page(title), p)
        for title in ('Other...', '', 'ZHC Folder Name Changed'):
            with self.subTest(title=title), self.assertRaises(Stop):
                folders._breadcrumb(Page(title), p)
        with self.assertRaises(Stop):
            folders._breadcrumb(Page('ZHC Folder Name', {'li[data-testid="breadcrumb-item-0"]': 2}), p)

    def test_incomplete_and_duplicate_inventory_refuse_before_create(self):
        class Page:
            def __init__(self): self.visits = []
            def goto(self, url, **kw): self.visits.append(url)
        row = {'id': 'one', 'name': 'ZHC Test', 'location_id': 'LOC', 'type': 'funnel'}
        cases = ({'complete': False, 'rows': []},
                 {'complete': True, 'rows': [row, {**row, 'id': 'two'}]},
                 {'complete': True, 'rows': [{**row, 'type': 'website'}]})
        for snap in cases:
            with self.subTest(snap=snap), tempfile.TemporaryDirectory() as d:
                page = Page()
                with self.assertRaises(Stop):
                    folders.ensure_folder(page, location_id='LOC', folder_type='funnel',
                        name='ZHC Test', start_url=BASE, journal_path=Path(d)/'state.json',
                        inventory=lambda *_: snap, open_folder=lambda *_args, **_kw: None)
                self.assertFalse((Path(d)/'state.json').exists())

    def test_creation_requires_independent_folder_reopen_and_replay(self):
        class Locator:
            def __init__(self, page, kind): self.page, self.kind = page, kind
            def count(self): return 1
            def is_enabled(self): return True
            def wait_for(self, **kwargs): pass
            def and_(self, other): return self
            def get_by_role(self, role, name, exact=True): return Locator(self.page, name)
            def get_by_text(self, name, exact=True): return Locator(self.page, 'row')
        class Page:
            def __init__(self): self.url = ''; self.visits = []
            def goto(self, url, **kwargs): self.url = url; self.visits.append(url)
            def locator(self, selector): return Locator(self, 'new')
            def get_by_role(self, role, name=None, exact=True): return Locator(self, name or role)
        folder = {**folders._plan('LOC', 'funnel', 'ZHC Folder', BASE),
                  'id': 'parent', 'url': BASE + '?folder=parent'}
        with tempfile.TemporaryDirectory() as d:
            page = Page(); path = Path(d)/'object.json'; searches = iter([None, Locator(page, 'row')])
            def click(loc):
                if loc.kind == 'new':
                    self.assertEqual(folders.read_journal(path)['status'], 'INTENT_RECORDED')
                if loc.kind in ('Create', 'row'): page.url = BASE + '/child/steps'
            with patch.object(folders, '_settled_search', side_effect=lambda *_: next(searches)), \
                 patch.object(folders, 'click', side_effect=click), patch.object(folders, 'fill'):
                result = folders.create_in_folder(page, folder=folder, name='ZHC Child',
                    journal_path=path, verify_breadcrumb=lambda **_: None)
            self.assertEqual(result['id'], 'child')
            self.assertEqual(page.visits.count(folder['url']), 2)
            with patch.object(folders, '_settled_search', return_value=Locator(page, 'row')), \
                 patch.object(folders, 'click', side_effect=click):
                replay = folders.create_in_folder(page, folder=folder, name='ZHC Child',
                    journal_path=path, verify_breadcrumb=lambda **_: None)
            self.assertEqual(replay['id'], 'child')

    def test_folder_kind_never_confuses_websites_with_funnels_or_objects(self):
        class Cells:
            def __init__(self, text): self.text = text
            def count(self): return 3
            def nth(self, _): return self
            def inner_text(self): return self.text
        class Row:
            def __init__(self, text): self.text = text
            def count(self): return 1
            def get_by_role(self, role): return Cells(self.text)
        class Cell:
            def __init__(self, text): self.text = text
            def locator(self, _): return Row(self.text)
        for kind, text in [('funnel', '0 Funnels'), ('website', '0 Websites'), ('website', '1 Website')]:
            folders._folder_cell_kind(Cell(text), kind)
        for kind, text in [('funnel', '0 Websites'), ('website', '0 Funnels'), ('website', '1 Page')]:
            with self.subTest(kind=kind, text=text), self.assertRaises(Stop):
                folders._folder_cell_kind(Cell(text), kind)

    def test_search_snapshot_binds_query_pagination_and_rows(self):
        class Loc:
            def __init__(self, page, kind, index=None): self.page, self.kind, self.index = page, kind, index
            def count(self):
                if self.kind == 'rows': return len(self.page.rows) + 1
                if self.kind == 'cells': return 0 if self.index == 0 else 1
                if self.kind == 'exact': return sum(row == self.page.query for row in self.page.rows)
                if self.kind == 'marker': return int(self.index > 0 and self.page.rows[self.index-1] == 'EMPTY')
                if self.kind == 'status': return int(self.page.status is not None)
                return 1
            def nth(self, index): return Loc(self.page, 'row', index)
            def get_by_role(self, role): return Loc(self.page, 'rows' if role == 'row' else 'cells', self.index)
            def all_inner_texts(self): return [self.page.rows[self.index-1]]
            def get_by_text(self, text, **kw): return Loc(self.page, 'marker', self.index)
            def input_value(self): return self.page.query
            def is_enabled(self): return False
            def is_visible(self): return True
            def inner_text(self): return self.page.status
        class Page:
            def __init__(self, query, status, rows): self.query, self.status, self.rows = query, status, rows
            def get_by_role(self, role, **kw): return Loc(self, {'textbox':'search', 'button':'button', 'treegrid':'grid', 'gridcell':'exact'}[role])
            def get_by_text(self, text, **kw): return Loc(self, 'empty')
            def locator(self, selector): return Loc(self, 'status')
        p = Page('ZHC One', '1 - 1 of 1', ['ZHC One'])
        self.assertEqual(folders._search_snapshot(p, 'funnels', 'ZHC One')[2], 1)
        self.assertIsNone(folders._search_snapshot(p, 'funnels', 'different'))
        p.status = '1 - 1 of 2'
        self.assertIsNone(folders._search_snapshot(p, 'funnels', 'ZHC One'))
        p.status, p.rows = None, ['EMPTY']
        self.assertEqual(folders._search_snapshot(p, 'funnels', 'ZHC One')[2], 0)
        p.rows = ['EMPTY', 'ZHC One']
        self.assertIsNone(folders._search_snapshot(p, 'funnels', 'ZHC One'))
        p.status, p.rows = '1 - 2 of 2', ['ZHC One', 'ZHC One']
        with self.assertRaises(Stop): folders._search_snapshot(p, 'funnels', 'ZHC One')

    def test_search_requires_stability_and_resets_after_change(self):
        old = ('1 - 1 of 1', (('old',),), 0, 'ZHC Test')
        new = ('1 - 1 of 1', (('ZHC Test',),), 1, 'ZHC Test')
        clock = iter([0, .8, 1, 1.8, 2.6])
        samples = iter([old, old, new, new, new, new])
        def wait(check, *_args, **_kw):
            for _ in range(5):
                if check(): return
            raise Stop('Not settled')
        page = SimpleNamespace(get_by_role=lambda *args, **kw: 'matched')
        with patch.object(folders, 'exact_search'), patch.object(folders, '_search_snapshot', side_effect=lambda *_: next(samples)), \
             patch.object(folders.time, 'monotonic', side_effect=lambda: next(clock)), \
             patch.object(folders, 'wait_until', side_effect=wait):
            self.assertEqual(folders._settled_search(page, 'funnels', 'ZHC Test'), 'matched')

    def test_folder_url_must_match_exact_scope(self):
        p = folders._plan('LOC', 'funnel', 'ZHC Test', BASE)
        folders._in_scope(SimpleNamespace(url=BASE + '?folder=one'), p, 'one')
        for url in (BASE + '?folder=two', BASE + '?folder=one&extra=1', BASE + '?folder=one&extra=', BASE + '?folder=one&folder=two'):
            with self.subTest(url=url), self.assertRaises(Stop):
                folders._in_scope(SimpleNamespace(url=url), p, 'one')

if __name__ == '__main__': unittest.main()
