"""Captured Saved Assets UI profile registry.

Profiles are added only after a live tenant capture records exact controls and
the observed scope model. No selector is inferred from another GHL surface.
"""
import json

from .skill6_playwright import Stop


_PROFILES = {}


def register(name, adapter):
    if not isinstance(name, str) or not name or name in _PROFILES:
        raise ValueError('profile name must be unique')
    if not callable(getattr(adapter, 'run', None)):
        raise TypeError('saved-section profile adapter must implement run(page, plan)')
    _PROFILES[name] = adapter


def get_profile(name):
    adapter = _PROFILES.get(name)
    if adapter is None:
        raise Stop(f'No captured native Saved Assets profile is installed for {name!r}')
    return adapter


class NativeSavedAssets:
    """Observed Saved Assets panel; library identity is explicit scope + name.

    This builder does not expose a saved-asset ID on its library cards. Never
    turn a card position, display name hash or DOM index into a native ID.
    """
    card_selector = 'div.cursor-move.bg-gray-50.mt-2.p-3.mb-3.border'
    name_selector = 'p.whitespace-pre.hl-text-xs-medium'
    scope_labels = {'template': 'Section Templates', 'global': 'Global Sections',
                    'universal': 'Universal Sections'}
    search_names = {'template':'Search Section Templates', 'global':'Search Global Sections',
                    'universal':'Search Templates'}
    empty_text = {'template':'There are no templates available in this location',
                  'global':'There are no global sections available in this Funnel/Website',
                  'universal':'There are no templates available in this location'}

    @staticmethod
    def _panel(frame):
        panel = frame.get_by_role('dialog').filter(
            has=frame.get_by_role('button', name='Saved Assets New', exact=True))
        if panel.count() != 1:
            raise Stop('Native Saved Assets panel is missing or ambiguous')
        return panel

    def _open(self, frame, scope):
        from .skill6_playwright import click, wait_until
        entry = frame.get_by_role('button', name='Saved Assets New', exact=True)
        if not entry.is_visible():
            click(frame.locator('#hl-builder-add-elements-button'))
        click(entry)
        panel = self._panel(frame)
        click(panel.get_by_role('button', name=self.scope_labels[scope], exact=True))
        search = panel.get_by_role('textbox', name=self.search_names[scope], exact=True)
        search.wait_for(state='visible', timeout=45000)
        if search.count() != 1:
            raise Stop('Saved Assets scope search is ambiguous')
        # A retained search would hide siblings from the scoped inventory.
        if search.input_value():
            search.fill('')

    def _library(self, frame, scope):
        cards = self._panel(frame).locator(self.card_selector + ':visible')
        names = cards.evaluate_all('''(cards) => cards.map(card => {
            const labels = card.querySelectorAll('p.whitespace-pre.hl-text-xs-medium');
            return labels.length === 1 ? labels[0].textContent.trim() : null;
        })''')
        if any(not isinstance(name, str) or not name for name in names):
            raise Stop('Saved Assets library card name is missing or ambiguous')
        return [{'name': name, 'scope': scope} for name in names]

    def _loaded_empty(self, frame, scope):
        marker = self._panel(frame).get_by_text(self.empty_text[scope], exact=True)
        return marker.count() == 1 and marker.is_visible()

    @staticmethod
    def _sections(frame):
        ids = frame.locator('.c-section').evaluate_all('els => els.map(el => el.id)')
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            raise Stop('Native section inventory is missing or ambiguous')
        return ids

    @staticmethod
    def _expected(plan, scope):
        rows = [x for x in plan.get('expected_saved_inventory', []) if x['scope'] == scope]
        if any('id' in row for row in rows) or 'saved_section_id' in plan:
            raise Stop('This Saved Assets UI exposes scope and name, not a native saved-asset ID')
        return rows

    @staticmethod
    def _same_library(actual, expected):
        return sorted((x['scope'], x['name']) for x in actual) == sorted(
            (x['scope'], x['name']) for x in expected)

    def _reorder(self, frame, inserted, wanted):
        from .skill6_playwright import click, wait_until
        original = [identifier for identifier in wanted if identifier != inserted]
        for _ in range(len(wanted) + 1):
            current = self._sections(frame)
            if current == wanted:
                return current
            if (set(current) != set(wanted)
                    or [identifier for identifier in current if identifier != inserted] != original):
                raise Stop('Native section inventory changed while positioning the saved section')
            index, target = current.index(inserted), wanted.index(inserted)
            delta = 1 if index < target else -1
            title = 'Move Down' if delta == 1 else 'Move Up'
            section = frame.locator('.c-section[id=' + json.dumps(inserted) + ']')
            box = section.bounding_box()
            if not box:
                raise Stop('Inserted saved section is not visible for native positioning')
            section.hover(position={'x':box['width'] / 2, 'y':5})
            control = section.locator(':scope > .ui-section [title=' + json.dumps(title) + ']:visible')
            click(control)
            next_order = list(current)
            next_order[index], next_order[index + delta] = next_order[index + delta], next_order[index]
            wait_until(lambda: self._sections(frame) == next_order,
                       'Native saved-section move did not produce exactly one expected position change')
        raise Stop('Saved section could not reach its requested native position')

    def _save(self, page, frame, plan, before, before_orders, library):
        from .skill6_playwright import (click, page_builder_ready, wait_until, native_order_inventory)
        name, scope = plan['saved_section_name'], plan['scope']
        if any(row['name'] == name for row in library):
            raise Stop('Saved asset name already exists in the selected scope; do not overwrite or duplicate it')
        section = frame.locator('.c-section[id=' + json.dumps(plan['source_section_id']) + ']')
        if section.count() != 1:
            raise Stop('Saved-section source is absent or ambiguous')
        box = section.bounding_box()
        if not box:
            raise Stop('Saved-section source is not visible')
        section.hover(position={'x':box['width'] / 2, 'y':5})
        click(section.locator(':scope > .ui-section [title="Save Section"]:visible'))
        dialog = frame.get_by_role('dialog').filter(has_text='Save This Section')
        dialog.wait_for(state='visible', timeout=45000)
        names = dialog.get_by_role('textbox')
        if names.count() != 1:
            raise Stop('Native Save This Section name input is ambiguous')
        click(dialog.get_by_text(self.scope_labels[scope], exact=True))
        names.fill(name)
        click(dialog.get_by_role('button', name='Save', exact=True))
        dialog.wait_for(state='hidden', timeout=45000)
        page.goto(page.url, wait_until='domcontentloaded', timeout=45000)
        fresh = page_builder_ready(page)
        wait_until(lambda: self._sections(fresh) == before,
                   'Source page must retain its saved sections before library reuse')
        if native_order_inventory(fresh) != before_orders:
            raise Stop('Native order forms changed while saving the reusable section')
        self._open(fresh, scope)
        expected = library + [{'name':name, 'scope':scope}]
        wait_until(lambda: self._same_library(self._library(fresh, scope), expected),
                   'Saved asset did not persist in the intended synchronization scope')
        return {'status':'SAVED_ASSET_READBACK_VERIFIED', 'scope':scope,
                'identity_kind':'unique_name_and_scope', 'saved_section_name':name,
                'source_section_id':plan['source_section_id'], 'section_ids':before,
                'native_order_forms':before_orders, 'saved_inventory':expected,
                'payment_verified':False, 'verification_required':True}

    def run(self, page, plan):
        from .skill6_playwright import (page_builder_ready, click, save_page, wait_until,
                                       native_order_inventory, assert_native_orders_preserved)
        operation = plan['operation']
        if operation == 'edit':
            raise Stop('Saved Assets reuse does not authorize editing a syncing library asset')
        scope = plan.get('scope')
        if scope is None and operation not in ('inventory', 'save'):
            scope = next(row['scope'] for row in plan['expected_saved_inventory']
                         if row['name'] == plan['saved_section_name'])
        scope = scope or 'template'
        frame = page_builder_ready(page)
        before = self._sections(frame)
        before_orders = native_order_inventory(frame)
        if operation != 'inventory':
            if before != plan['expected_section_inventory']:
                raise Stop('Native page sections changed before saved-section insertion')
        if operation in ('insert', 'reuse'):
            anchor = plan['destination_section_id']
            if anchor is None and before or anchor is not None and anchor not in before:
                raise Stop('Saved-section insertion requires its exact existing anchor or an empty canvas')
            if anchor is not None:
                section = frame.locator('.c-section[id=' + json.dumps(anchor) + ']')
                if section.count() != 1:
                    raise Stop('Saved-section insertion anchor is missing or ambiguous')
                box = section.bounding_box()
                if not box:
                    raise Stop('Saved-section insertion anchor is not visible')
                section.hover(position={'x':box['width'] / 2, 'y':5})
                click(frame.locator('.ui-section.hovered [title="Open Settings"]:visible'))
        self._open(frame, scope)
        if 'expected_saved_inventory' in plan:
            expected = self._expected(plan, scope)
            wait_until(lambda: self._same_library(self._library(frame, scope), expected)
                       and (bool(expected) or self._loaded_empty(frame, scope)),
                       'Saved Assets inventory differs from the approved scoped inventory')
        else:
            expected = None
        wait_until(lambda: bool(self._library(frame, scope)) or self._loaded_empty(frame, scope),
                   'Saved Assets has not exposed loaded cards or positive empty evidence')
        library = self._library(frame, scope)
        if operation == 'inventory':
            # An empty rendered list alone is not positive proof of an empty library.
            if not library and not self._loaded_empty(frame, scope):
                raise Stop('An empty Saved Assets view needs positive loaded-empty evidence')
            return {'status':'INVENTORIED', 'scope':scope,
                    'identity_kind':'unique_name_and_scope', 'saved_inventory':library}
        if operation == 'save':
            return self._save(page, frame, plan, before, before_orders, library)
        matches = [x for x in library if x['name'] == plan['saved_section_name']]
        if len(matches) != 1:
            raise Stop('Requested saved section name is absent or duplicated in its scope')
        card = self._panel(frame).locator(self.card_selector + ':visible').filter(
            has=frame.get_by_text(plan['saved_section_name'], exact=True))
        if card.count() != 1:
            raise Stop('Requested saved section card is missing or ambiguous')
        if plan['destination_section_id'] is None:
            raise Stop('Empty-canvas saved-section drop target has not been captured')
        anchor = frame.locator('.c-section[id=' + json.dumps(plan['destination_section_id']) + ']')
        card.drag_to(anchor)
        wait_until(lambda: len(self._sections(frame)) > len(before),
                   'Saved section did not appear on the native canvas')
        after = self._sections(frame)
        added = [identifier for identifier in after if identifier not in before]
        if len(added) != 1 or [identifier for identifier in after if identifier in before] != before:
            raise Stop('Saved section insertion changed existing sections or added an unexpected batch')
        insertion_index = 0 if plan['destination_section_id'] is None else before.index(plan['destination_section_id']) + 1
        wanted = before[:insertion_index] + added + before[insertion_index:]
        if after != wanted:
            after = self._reorder(frame, added[0], wanted)
        after_orders = native_order_inventory(frame)
        assert_native_orders_preserved(before_orders, after_orders)
        save_page(frame)
        editor_url = page.url
        page.goto(editor_url, wait_until='domcontentloaded', timeout=45000)
        reopened = page_builder_ready(page)
        wait_until(lambda: self._sections(reopened) == after,
                   'Saved section order did not survive independent reopen')
        if native_order_inventory(reopened) != after_orders:
            raise Stop('Native order forms changed after saved-section insertion reopened')
        return {'status':'SAVED_READBACK_VERIFIED', 'scope':scope,
                'identity_kind':'unique_name_and_scope', 'saved_section_name':plan['saved_section_name'],
                'inserted_section_id':added[0], 'section_ids':after,
                'native_order_forms':after_orders, 'payment_verified':False,
                'verification_required':True}

    def verify_completed(self, page, plan, result):
        from .skill6_playwright import page_builder_ready, native_order_inventory, wait_until
        frame = page_builder_ready(page)
        if plan['operation'] == 'inventory':
            return self.run(page, plan)
        if self._sections(frame) != result.get('section_ids'):
            raise Stop('Completed saved-section layout changed; do not insert it again')
        if native_order_inventory(frame) != result.get('native_order_forms'):
            raise Stop('Completed saved-section native order forms changed')
        if plan['operation'] == 'save':
            self._open(frame, result['scope'])
            wait_until(lambda: self._same_library(
                self._library(frame, result['scope']), result['saved_inventory']),
                'Completed saved asset library changed; do not save a duplicate')
        return result


register('saved-assets-new', NativeSavedAssets())
