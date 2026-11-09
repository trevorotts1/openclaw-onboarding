"""Captured page-card contracts: choose exact existing pages without first-Edit guesses."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import skill6_playwright as runner

BASE = 'https://app.convertandflow.com/v2/location/FIXTURE/'


class Locator:
    def __init__(self, page, kind, name=None, indices=None):
        self.page, self.kind, self.name = page, kind, name
        self.indices = list(range(len(page.names))) if indices is None else indices

    def filter(self, *, has):
        return Locator(self.page, 'cards', indices=[
            i for i in self.indices if self.page.names[i] == has.name])

    def count(self):
        p, kind = self.page, self.kind
        if kind == 'cards':
            return len(self.indices)
        if kind == 'listing':
            return p.list_count
        if kind == 'detail':
            return p.detail_count
        if kind == 'global_text':
            # A selected funnel's title legitimately appears in both nav and detail.
            return sum(n == self.name for n in p.names) + int(p.detail_name == self.name)
        if kind == 'headings':
            return sum(n == self.name for n in p.names) + int(p.orphan_heading == self.name)
        if kind == 'card_heading':
            return sum(p.card_heading_count[i] for i in self.indices if p.names[i] == self.name)
        if kind == 'detail_title':
            return p.detail_title_count if p.detail_name == self.name else 0
        if kind == 'detail_edit':
            return p.detail_edits
        if kind == 'card_edit':
            return sum(p.card_edits[i] for i in self.indices)
        if kind == 'global_edit':
            return len(p.names) + 3
        return 0 if kind == 'absent' else 1

    def is_visible(self):
        return bool(self.count())

    def wait_for(self, **_):
        if self.count() != 1:
            raise TimeoutError('fixture missing or ambiguous locator')

    def click(self, **_):
        p = self.page
        if self.kind == 'cards':
            p.selected = self.indices[0]
            p.clicked_cards.append(p.selected)
            if p.wrong_detail is None:
                p.detail_name = p.names[p.selected]
            else:
                p.detail_name = p.wrong_detail
            p.url = p.selection_url or (BASE + 'funnels-websites/funnels/FUNNEL/'
                + 'steps/STEP_' + str(p.selected) + '/overview')
        elif self.kind in ('detail_edit', 'card_edit'):
            chosen = p.selected if self.kind == 'detail_edit' else self.indices[0]
            p.edited.append(chosen)
            p.url = BASE + 'page-builder/PAGE_' + str(chosen)
        elif self.kind == 'global_edit':
            raise AssertionError('Global Edit is never a target-page contract')
        elif self.kind == 'add':
            p.created += 1
            raise AssertionError('This test must not create pages')

    def get_by_text(self, name, exact=True):
        assert exact
        return Locator(self.page, 'detail_title' if self.kind == 'detail' else 'global_text', name)

    def get_by_role(self, role, name=None, exact=True):
        assert exact
        if self.kind == 'cards':
            return Locator(self.page, 'card_heading' if role == 'heading' else 'card_edit', name, self.indices)
        if self.kind == 'detail':
            return Locator(self.page, 'detail_edit', name)
        if self.kind == 'builder':
            return Locator(self.page, 'absent' if name == 'Close Ask AI' else 'back', name)
        if role == 'heading':
            return Locator(self.page, 'headings', name)
        if role == 'button' and name == 'Edit':
            return Locator(self.page, 'global_edit', name)
        return Locator(self.page, 'add', name)


class Page:
    def __init__(self, surface='funnel', names=None):
        self.surface = surface
        self.names = names if names is not None else ['ZHC Other', 'ZHC Target', 'ZHC Third']
        self.url = BASE + ('funnels-websites/funnels/FUNNEL/steps/STEP_0/overview'
            if surface == 'funnel' else 'funnels-websites/websites/WEBSITE/pages')
        self.selected = 0
        self.detail_name = self.names[0] if self.names else ''
        self.wrong_detail = self.selection_url = self.orphan_heading = None
        self.list_count = self.detail_count = self.detail_title_count = self.detail_edits = 1
        self.card_heading_count = [1] * len(self.names)
        self.card_edits = [1] * len(self.names)
        self.clicked_cards, self.edited = [], []
        self.created = 0

    def locator(self, selector):
        if selector == '.steps-list':
            return Locator(self, 'listing')
        if selector in ('.steps-list #step-container', '.page-card'):
            return Locator(self, 'cards')
        if selector == '#funnel-step-details':
            return Locator(self, 'detail')
        raise AssertionError('Uncaptured selector: ' + selector)

    def get_by_text(self, name, exact=True):
        return Locator(self, 'global_text', name)

    def get_by_role(self, role, **kwargs):
        return Locator(self, 'root').get_by_role(role, **kwargs)

    def frame_locator(self, selector):
        assert selector == 'iframe[name="funnel-builder"]'
        return Locator(self, 'builder')


def step(surface='funnel', name='ZHC Target', allow_creation=False):
    return {'surface':surface, 'name':name, 'path':'/target', 'allow_creation':allow_creation}


class ExistingPageTargetTests(unittest.TestCase):
    def test_funnel_selects_exact_navigation_card_and_its_independent_detail(self):
        page = Page()
        result = runner.ensure_page(page, step())
        self.assertEqual(page.clicked_cards, [1])
        self.assertEqual(page.edited, [1])
        self.assertEqual(result['editor_url'], BASE + 'page-builder/PAGE_1')
        self.assertEqual(page.created, 0)

    def test_duplicate_funnel_nav_names_stop_before_any_click(self):
        page = Page(names=['ZHC Target', 'ZHC Target'])
        with self.assertRaisesRegex(runner.Stop, 'Duplicate funnel'):
            runner.ensure_page(page, step())
        self.assertEqual(page.clicked_cards + page.edited, [])

    def test_mismatched_independent_detail_never_clicks_edit(self):
        page = Page()
        page.wrong_detail = 'ZHC Other'
        with self.assertRaisesRegex(runner.Stop, 'detail did not confirm'):
            runner.ensure_page(page, step())
        self.assertEqual(page.edited, [])

    def test_changed_tenant_container_origin_and_query_stop_before_edit(self):
        for url in (BASE.replace('/FIXTURE/', '/FOREIGN/') + 'funnels-websites/funnels/FUNNEL/steps/S/overview',
                    BASE + 'funnels-websites/funnels/OTHER/steps/S/overview',
                    'https://foreign.invalid/v2/location/FIXTURE/funnels-websites/funnels/FUNNEL/steps/S/overview',
                    BASE + 'funnels-websites/funnels/FUNNEL/steps/S/overview?unexpected=true'):
            with self.subTest(url=url):
                page = Page()
                page.selection_url = url
                with self.assertRaisesRegex(runner.Stop, 'changed location or container'):
                    runner.ensure_page(page, step())
                self.assertEqual(page.edited, [])

    def test_multiple_variant_edits_and_duplicate_detail_names_stop(self):
        for attribute in ('detail_edits', 'detail_title_count', 'detail_count'):
            with self.subTest(attribute=attribute):
                page = Page()
                setattr(page, attribute, 2)
                with self.assertRaises(runner.Stop):
                    runner.ensure_page(page, step())
                self.assertEqual(page.edited, [])

    def test_website_opens_exact_card_among_unrelated_edit_buttons(self):
        page = Page('website')
        result = runner.ensure_page(page, step('website'))
        self.assertEqual(page.edited, [1])
        self.assertEqual(page.clicked_cards, [])
        self.assertEqual(result['editor_url'], BASE + 'page-builder/PAGE_1')

    def test_duplicate_website_cards_stop_without_edit(self):
        page = Page('website', names=['ZHC Target', 'ZHC Target'])
        with self.assertRaisesRegex(runner.Stop, 'Duplicate website'):
            runner.ensure_page(page, step('website'))
        self.assertEqual(page.edited, [])

    def test_ambiguous_heading_or_edit_inside_website_card_stops(self):
        for attribute in ('card_heading_count', 'card_edits'):
            with self.subTest(attribute=attribute):
                page = Page('website')
                getattr(page, attribute)[1] = 2
                with self.assertRaises(runner.Stop):
                    runner.ensure_page(page, step('website'))
                self.assertEqual(page.edited, [])

    def test_empty_inventories_never_authorize_duplicate_creation(self):
        for surface in ('funnel', 'website'):
            with self.subTest(surface=surface):
                page = Page(surface, names=[])
                with self.assertRaisesRegex(runner.Stop, 'fresh native creation proof'):
                    runner.ensure_page(page, step(surface, allow_creation=True))
                self.assertEqual(page.created, 0)

    def test_missing_or_duplicate_funnel_list_container_stops(self):
        for count in (0, 2):
            page = Page()
            page.list_count = count
            with self.assertRaisesRegex(runner.Stop, 'inventory is unavailable'):
                runner.ensure_page(page, step(allow_creation=True))
            self.assertEqual(page.created, 0)

    def test_missing_named_page_with_no_creation_request_stops(self):
        for surface in ('funnel', 'website'):
            page = Page(surface)
            with self.assertRaisesRegex(runner.Stop, 'creation was not requested'):
                runner.ensure_page(page, step(surface, name='ZHC Missing'))
            self.assertEqual(page.created, 0)

    def test_named_website_heading_outside_cards_is_not_absence(self):
        page = Page('website')
        page.orphan_heading = 'ZHC Missing'
        with self.assertRaisesRegex(runner.Stop, 'outside the captured card'):
            runner.ensure_page(page, step('website', 'ZHC Missing', allow_creation=True))
        self.assertEqual(page.created, 0)

    def test_wrong_container_route_stops_before_read_or_click(self):
        for surface in ('funnel', 'website'):
            page = Page(surface)
            page.url = BASE + 'dashboard'
            with self.assertRaisesRegex(runner.Stop, 'captured container route'):
                runner.ensure_page(page, step(surface))
            self.assertEqual(page.clicked_cards + page.edited, [])


class ContainerCreationTargetTests(unittest.TestCase):
    def test_new_website_uses_toolbar_id_and_exact_name_not_first_duplicate(self):
        page = Mock()
        page.url = BASE + 'funnels-websites/websites/NEW_SITE/pages'
        named = Mock()
        named.count.return_value = 2
        toolbar = Mock()
        bound = Mock()
        bound.count.return_value = 1
        toolbar.and_.return_value = bound
        dialog = Mock()
        name_input, create_confirm, share = Mock(), Mock(), Mock()
        for loc in (name_input, create_confirm, share):
            loc.count.return_value = 1
        def role(role, name=None, exact=True):
            if role == 'dialog':
                return dialog
            return {'New website':named, 'Share website':share}[name]
        def dialog_role(role, name=None, exact=True):
            return name_input if role == 'textbox' else create_confirm
        page.get_by_role.side_effect = role
        dialog.get_by_role.side_effect = dialog_role
        page.locator.return_value = toolbar
        with patch.object(runner, 'exact_search', return_value=None):
            result = runner.ensure_container(page, {
                'surface':'website', 'name':'ZHC New Site', 'allow_creation':True})
        page.locator.assert_called_once_with('#create-new-button')
        toolbar.and_.assert_called_once_with(named)
        bound.click.assert_called_once()
        named.click.assert_not_called()
        create_confirm.click.assert_called_once()
        self.assertEqual(result['container_url'], page.url)

    def test_missing_captured_toolbar_does_not_click_empty_state_alternative(self):
        page = Mock()
        named, toolbar, bound = Mock(), Mock(), Mock()
        page.get_by_role.return_value = named
        page.locator.return_value = toolbar
        toolbar.and_.return_value = bound
        bound.wait_for.side_effect = runner.Stop('Captured toolbar missing')
        with patch.object(runner, 'exact_search', return_value=None):
            with self.assertRaisesRegex(runner.Stop, 'toolbar missing'):
                runner.ensure_container(page, {
                    'surface':'website', 'name':'ZHC New Site', 'allow_creation':True})
        named.click.assert_not_called()
        bound.click.assert_not_called()


class FreshContainerProvenanceTests(unittest.TestCase):
    def created(self, surface):
        page = Mock()
        page.url = BASE + ('funnels-websites/websites/NEW_SITE/pages' if surface == 'website'
                           else 'funnels-websites/funnels/NEW_FUNNEL')
        controls = {name:Mock() for name in ('named', 'toolbar', 'create', 'dialog', 'name',
            'confirm', 'share', 'inventory', 'root', 'sidebar', 'listing', 'grid', 'add_id',
            'add_role', 'add', 'detail', 'empty')}
        for control in controls.values():
            control.count.return_value = 1
            control.is_visible.return_value = True
        controls['named'].count.return_value = 2
        controls['inventory'].count.return_value = 0
        controls['toolbar'].and_.return_value = controls['create']
        controls['add_id'].and_.return_value = controls['add']
        controls['listing'].evaluate.return_value = 0
        controls['grid'].evaluate.return_value = 0
        controls['detail'].get_by_text.return_value = controls['empty']
        def locator(selector):
            return {'#create-new-button':controls['toolbar'],
                '.page-card':controls['inventory'],
                '.steps-list':controls['listing'],
                '.steps-list #step-container':controls['inventory'],
                '#steps-tab':controls['root'],
                '#steps-tab .hl_funnels--website-pages':controls['root'],
                '#steps-tab #add-step':controls['add_id']}[selector]
        page.locator.side_effect = locator
        controls['root'].locator.side_effect = lambda selector: {
            '#steps-sidebar.steps-sidebar':controls['sidebar'],
            'div.flex.flex-wrap[ghostclass="webinar-drag-ghost"]':controls['grid'],
            '#add-step':controls['add_id'], '.funnel-step-details':controls['detail']}[selector]
        controls['sidebar'].locator.side_effect = lambda selector: {
            '.steps-list':controls['listing'], '#add-step':controls['add_id']}[selector]
        controls['root'].get_by_role.return_value = controls['add_role']
        controls['sidebar'].get_by_role.return_value = controls['add_role']
        def role(role, name=None, exact=True):
            if role == 'dialog':return controls['dialog']
            if name == 'New ' + surface:return controls['named']
            if name == 'Share ' + surface:return controls['share']
            if name in ('Add new page', 'Add new step or import'):return controls['add_role']
            raise AssertionError((role,name))
        page.get_by_role.side_effect = role
        controls['dialog'].get_by_role.side_effect = lambda role, **kw: (
            controls['name'] if role == 'textbox' else controls['confirm'])
        with patch.object(runner, 'exact_search', return_value=None):
            result = runner.ensure_container(page, {
                'surface':surface, 'name':'ZHC Newly Created', 'allow_creation':True})
        return page, result, controls

    def test_actual_create_outcome_authorizes_only_captured_empty_shape(self):
        for surface in ('funnel', 'website'):
            with self.subTest(surface=surface):
                page, result, controls = self.created(surface)
                context = result.fresh_container
                target = runner._funnel_page_target if surface == 'funnel' else runner._website_page_target
                self.assertIsNone(target(page, 'ZHC First Page', fresh_container=context))
                self.assertEqual(controls['create'].click.call_count, 1)
                self.assertEqual(controls['confirm'].click.call_count, 1)
                self.assertEqual(json.loads(json.dumps(result)), {
                    'container_url':page.url, 'name':'ZHC Newly Created'})
                self.assertFalse(context.used)

    def test_json_flags_other_page_changed_url_and_used_context_cannot_attest_empty(self):
        for surface in ('funnel', 'website'):
            for changed in ('json', 'other_page', 'route', 'used'):
                with self.subTest(surface=surface, changed=changed):
                    page, result, _ = self.created(surface)
                    context = result.fresh_container
                    if changed == 'json':context = {'created_now':True, 'url':page.url}
                    if changed == 'other_page':context.page = Mock()
                    if changed == 'route':context.url += '/wrong'
                    if changed == 'used':context.used = True
                    target = runner._funnel_page_target if surface == 'funnel' else runner._website_page_target
                    with self.assertRaisesRegex(runner.Stop, 'fresh native creation proof'):
                        target(page, 'ZHC First Page', fresh_container=context)

    def test_changed_empty_shape_refuses_even_with_real_creation_provenance(self):
        for surface in ('funnel', 'website'):
            changes = ('root', 'add', 'listing', 'empty') if surface == 'funnel' else ('root', 'add', 'grid')
            for changed in changes:
                with self.subTest(surface=surface, changed=changed):
                    page, result, controls = self.created(surface)
                    if changed in ('listing', 'grid'):
                        controls[changed].evaluate.return_value = 1
                    else:
                        controls[changed].count.return_value = 2
                    target = runner._funnel_page_target if surface == 'funnel' else runner._website_page_target
                    with self.assertRaises(runner.Stop):
                        target(page, 'ZHC First Page', fresh_container=result.fresh_container)
                    controls['add'].click.assert_not_called()

    def test_fresh_context_is_consumed_before_the_first_page_mutation(self):
        for surface in ('funnel', 'website'):
            page, result, controls = self.created(surface)
            controls['add'].wait_for.side_effect = runner.Stop('fixture ends before mutation')
            with self.assertRaisesRegex(runner.Stop, 'fixture ends'):
                runner.ensure_page(page, step(surface, 'ZHC First Page', True),
                    fresh_container=result.fresh_container)
            self.assertTrue(result.fresh_container.used)
            controls['add'].click.assert_not_called()

    def test_dispatcher_carries_only_actual_outcome_provenance_not_input_flags(self):
        for real in (True, False):
            page, result, _ = self.created('website')
            returned = result if real else dict(result)
            job = {'location_id':'FIXTURE', 'location_name':'Fixture Account',
                'start_url':page.url, 'steps':[
                    {'id':'container','action':'container','surface':'website','name':'ZHC Newly Created'},
                    {'id':'page','action':'page','surface':'website','name':'ZHC First Page',
                     'path':'/first','allow_creation':True,'fresh_container':{'created_now':True}}]}
            with tempfile.TemporaryDirectory() as directory, \
                    patch.object(runner, 'assert_tenant'), \
                    patch.object(runner, 'ensure_container', return_value=returned), \
                    patch.object(runner, 'ensure_page', return_value={'editor_url':page.url}) as create:
                runner.run_on_page(page, job, directory)
                self.assertIs(create.call_args.kwargs['fresh_container'], result.fresh_container if real else None)
                persisted = json.loads(Path(directory, 'state.json').read_text())
                self.assertNotIn('fresh_container', persisted['results'][0]['result'])



if __name__ == '__main__':
    unittest.main()
