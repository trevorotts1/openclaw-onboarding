"""Native folder-scoped funnel and website creation.

A journal records intent before each irreversible click. An interrupted intent is
never replayed automatically; a completed receipt is independently revalidated.
"""
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright_recipes.evidence_lease import journal_present, read_journal
from playwright_recipes.skill6_playwright import Stop, click, fill, exact_search, secure_json, wait_until


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise Stop('An exact native identifier is required')
    return value


def _name(value):
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > 500 or any(ord(c) < 32 for c in value)):
        raise Stop('An exact nonempty name is required')
    return value


def _plan(location_id, folder_type, name, start_url):
    _id(location_id); _name(name)
    if folder_type not in ('funnel', 'website'):
        raise Stop('Folder type must be funnel or website')
    try:
        url = urlsplit(start_url)
        port = url.port
    except (TypeError, ValueError):
        raise Stop('Invalid native list URL') from None
    path = '/v2/location/' + location_id + '/funnels-websites/' + folder_type + 's'
    if (url.scheme != 'https' or not url.hostname or url.username is not None
            or url.password is not None or port not in (None, 443)
            or url.path.rstrip('/') != path or url.query or url.fragment):
        raise Stop('Expected the exact location and type scoped native list URL')
    return {'location_id': location_id, 'folder_type': folder_type, 'name': name,
            'start_url': urlunsplit((url.scheme, url.netloc, path, '', ''))}


def _url(plan, folder_id):
    _id(folder_id)
    return plan['start_url'] + '?' + urlencode({'folder': folder_id})


def _fingerprint(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def _load(path, plan):
    if not journal_present(path):
        return None
    value = read_journal(path)
    if (not isinstance(value, dict) or value.get('schema') != 'skill6-page-folder/1'
            or value.get('fingerprint') != _fingerprint(plan)
            or value.get('status') != 'VERIFIED'):
        raise Stop('Folder create intent is uncertain; reconcile before another create')
    _id(value.get('folder_id'))
    return value


def _state(path, plan, status, **fields):
    secure_json(path, {'schema': 'skill6-page-folder/1',
                       'fingerprint': _fingerprint(plan), 'status': status, **fields})


def _in_scope(page, plan, folder_id):
    current = urlsplit(page.url)
    expected = urlsplit(_url(plan, folder_id))
    if ((current.scheme, current.netloc, current.path.rstrip('/')) !=
            (expected.scheme, expected.netloc, expected.path.rstrip('/'))
            or parse_qsl(current.query, keep_blank_values=True) != [('folder', folder_id)] or current.fragment):
        raise Stop('Folder route does not match the requested location, type and ID')


_PAGINATION = re.compile(r'^\s*(\d+)\s*[-–]\s*(\d+)\s+of\s+(\d+)\s*$')


def _search_snapshot(page, area, name):
    search = page.get_by_role('textbox', name='Search for ' + area, exact=True)
    previous = page.get_by_role('button', name='Previous', exact=True)
    next_button = page.get_by_role('button', name='Next', exact=True)
    grid = page.get_by_role('treegrid')
    pagination = page.locator('div.hr-dropdown-cntr p.hr-text')
    if (search.count() != 1 or search.input_value() != name or grid.count() != 1):
        return None
    rows = grid.get_by_role('row')
    data = []
    empty_rows = []
    empty_text = "No results found for '" + name + "'"
    for index in range(rows.count()):
        row = rows.nth(index)
        cells = row.get_by_role('gridcell')
        if cells.count():
            if not row.is_visible():
                return None
            values = tuple(cells.all_inner_texts())
            marker = row.get_by_text(empty_text, exact=True)
            if marker.count() == 1 and marker.is_visible():
                empty_rows.append(values)
            else:
                data.append(values)
    exact = page.get_by_role('gridcell', name=name, exact=True)
    if exact.count() > 1:
        raise Stop('Duplicate names in the scoped current folder list')
    if exact.count() and not exact.is_visible():
        return None
    # The captured empty list replaces pagination with one no-results row.
    # A generic empty table, stale marker, or additional native row is not proof.
    if empty_rows:
        if (len(empty_rows) != 1 or data or exact.count() or pagination.count()
                or page.get_by_text(empty_text, exact=True).count() != 1):
            return None
        return ('EMPTY', tuple(empty_rows), 0, search.input_value())
    if (previous.count() != 1 or next_button.count() != 1
            or previous.is_enabled() or next_button.is_enabled()
            or pagination.count() != 1 or not pagination.is_visible()):
        return None
    status = pagination.inner_text().strip()
    match = _PAGINATION.fullmatch(status)
    if not match:
        return None
    first, last, total = map(int, match.groups())
    if (len(data) != total or (total == 0 and (first, last) != (0, 0))
            or (total > 0 and (first, last) != (1, total))):
        return None
    if not exact.count():
        return None
    return (status, tuple(data), exact.count(), search.input_value())


def _settled_search(page, area, name):
    """Require the current query and its fully rendered inventory to settle.

    An unchanged UI over a bounded interval cannot guarantee server timing; it
    does prevent a transient prior result or pagination state authorizing a
    duplicate. A changed inventory resets the interval.
    """
    exact_search(page, area, name)
    state = {'snapshot': None, 'since': 0.0}
    def stable():
        snapshot = _search_snapshot(page, area, name)
        now = time.monotonic()
        if snapshot is None or snapshot != state['snapshot']:
            state.update(snapshot=snapshot, since=now)
            return False
        return now - state['since'] >= 1.5
    wait_until(stable, 'Search result did not settle with complete pagination')
    if _search_snapshot(page, area, name) != state['snapshot']:
        raise Stop('Scoped search changed before it could be used')
    return page.get_by_role('gridcell', name=name, exact=True) if state['snapshot'][2] else None


def _breadcrumb(page, plan):
    # The selected title can be truncated in the actual DOM. Bind the full name
    # through the exact root row and the folder ID through its native URL;
    # this breadcrumb proves the opened list has loaded the selected folder.
    nav = page.locator('#funnel-breadcrumb')
    nav.wait_for(state='visible', timeout=45000)
    home = nav.locator('li[data-testid="breadcrumb-home"]')
    selected = nav.locator('li[data-testid="breadcrumb-item-0"]')
    if (nav.count() != 1 or home.count() != 1 or selected.count() != 1
            or not home.is_visible() or not selected.is_visible()):
        raise Stop('Loaded folder breadcrumb is unavailable or ambiguous')
    title = selected.inner_text().strip()
    if not title:
        raise Stop('Loaded folder breadcrumb lacks a selected folder')
    if title.endswith(('...', '…')):
        prefix = title[:-3] if title.endswith('...') else title[:-1]
        if not prefix or not plan['name'].startswith(prefix.rstrip()):
            raise Stop('Folder breadcrumb does not match the selected name')
    elif title != plan['name']:
        raise Stop('Folder breadcrumb does not match the selected name')


def _at_root(page, plan):
    current = urlsplit(page.url)
    expected = urlsplit(plan['start_url'])
    if ((current.scheme, current.netloc, current.path.rstrip('/')) !=
            (expected.scheme, expected.netloc, expected.path.rstrip('/'))
            or current.query or current.fragment):
        raise Stop('Folder selection is no longer at the exact scoped root list')


def _native_open_folder(page, plan, folder_id, *, reopened=False):
    if not reopened:
        _at_root(page, plan)
        cell = _settled_search(page, plan['folder_type'] + 's', plan['name'])
        if cell is None:
            raise Stop('Folder row disappeared before opening')
        _folder_cell_kind(cell, plan['folder_type'])
        _at_root(page, plan)
        click(cell)
    _in_scope(page, plan, folder_id)
    _breadcrumb(page, plan)


def _folder_cell_kind(cell, folder_type):
    row = cell.locator('xpath=..')
    cells = row.get_by_role('gridcell')
    if row.count() != 1 or cells.count() < 3:
        raise Stop('Folder row shape differs from the captured native list')
    count = cells.nth(2).inner_text().strip()
    if not re.fullmatch(r'\d+ ' + ('Funnels?' if folder_type == 'funnel' else 'Websites?'), count):
        raise Stop('Exact name refers to a container or an unrecognized folder row')


def _native_folder_inventory(page, plan):
    page.goto(plan['start_url'], wait_until='domcontentloaded')
    cell = _settled_search(page, plan['folder_type'] + 's', plan['name'])
    _at_root(page, plan)
    if cell is None:
        return {'complete': True, 'rows': []}
    _folder_cell_kind(cell, plan['folder_type'])
    click(cell)
    current = urlsplit(page.url)
    base = urlsplit(plan['start_url'])
    query = parse_qsl(current.query, keep_blank_values=True)
    if ((current.scheme, current.netloc, current.path.rstrip('/')) !=
            (base.scheme, base.netloc, base.path.rstrip('/')) or current.fragment
            or len(query) != 1 or query[0][0] != 'folder'):
        raise Stop('Opening the exact folder row did not expose a native folder ID')
    folder_id = _id(query[0][1])
    _breadcrumb(page, plan)
    page.goto(plan['start_url'], wait_until='domcontentloaded')
    return {'complete': True, 'rows': [{'id': folder_id, 'name': plan['name'],
            'location_id': plan['location_id'], 'type': plan['folder_type']}]}


def ensure_folder(page, *, location_id, folder_type, name, start_url, journal_path,
                  inventory=None, open_folder=None):
    """Create or reuse a folder and independently reopen it.

    The native adapter searches the current list and opens the exact folder row.
    Optional adapters must return a complete scoped inventory and verify the
    loaded breadcrumb; they support isolated tests and alternate captured UIs.
    """
    plan = _plan(location_id, folder_type, name, start_url)
    path = Path(journal_path)
    stored = _load(path, plan)
    if inventory is None:
        inventory = lambda _location, _type: _native_folder_inventory(page, plan)
    if open_folder is None:
        open_folder = lambda _name, _id, reopened=False: _native_open_folder(page, plan, _id, reopened=reopened)

    def find():
        snap = inventory(location_id, folder_type)
        if not isinstance(snap, dict) or snap.get('complete') is not True or not isinstance(snap.get('rows'), list):
            raise Stop('A complete scoped native folder inventory is required')
        if any(not isinstance(r, dict) or r.get('location_id') != location_id
               or r.get('type') != folder_type or not isinstance(r.get('name'), str)
               or not isinstance(r.get('id'), str) for r in snap['rows']):
            raise Stop('Folder inventory contains incomplete or cross-scope identities')
        rows = [r for r in snap['rows'] if r.get('name') == name]
        if len(rows) > 1:
            raise Stop('Duplicate folder names in this scope; refusing ambiguous selection')
        if not rows:
            return None
        row = rows[0]
        if row.get('location_id') != location_id or row.get('type') != folder_type:
            raise Stop('Folder inventory identity differs from requested scope')
        return _id(row.get('id'))

    page.goto(plan['start_url'], wait_until='domcontentloaded')
    folder_id = find()
    if stored:
        if folder_id != stored['folder_id']:
            raise Stop('Previously verified folder no longer matches native inventory')
    elif folder_id is None:
        button = page.get_by_role('button', name='Create folder', exact=True)
        if button.count() != 1 or not button.is_enabled():
            raise Stop('Native folder create control is unavailable')
        _state(path, plan, 'INTENT_RECORDED')
        click(button)
        dialog = page.get_by_role('dialog')
        dialog.wait_for(state='visible', timeout=45000)
        if (dialog.count() != 1 or dialog.get_by_text('Organize your ' + ('funnels' if folder_type == 'funnel' else 'websites') + ' into folders', exact=True).count() != 1):
            raise Stop('Native folder dialog differs from the captured flow')
        fill(dialog.get_by_role('textbox', name='Folder name', exact=True), name)
        click(dialog.get_by_role('button', name='Confirm', exact=True))
        folder_id = find()
        if folder_id is None:
            raise Stop('Created folder is not present in the scoped native inventory')
    open_folder(name, folder_id)
    _in_scope(page, plan, folder_id)
    page.goto(_url(plan, folder_id), wait_until='domcontentloaded')
    open_folder(name, folder_id, reopened=True)
    _in_scope(page, plan, folder_id)
    _state(path, plan, 'VERIFIED', folder_id=folder_id)
    return {**plan, 'id': folder_id, 'url': _url(plan, folder_id)}


def create_in_folder(page, *, folder, name, journal_path, verify_breadcrumb=None):
    """Create a new funnel/site through its folder UI, then reopen its row.

    A completed journal is replayable only after the independently reopened
    folder inventory identifies the same object. An interrupted intent stops.
    """
    name = _name(name)
    plan = _plan(folder['location_id'], folder['folder_type'], folder['name'], folder['start_url'])
    folder_id = _id(folder['id'])
    if verify_breadcrumb is None:
        verify_breadcrumb = lambda **_kw: _breadcrumb(page, plan)
    if folder.get('url') != _url(plan, folder_id):
        raise Stop('Folder receipt URL does not match its identity')
    request = {**plan, 'folder_id': folder_id, 'object_name': name}
    path = Path(journal_path)
    old = _load(path, request)
    if old and (old['folder_id'] != folder_id or _id(old.get('object_id')) != old['object_id']):
        raise Stop('Completed container journal does not match its parent identity')
    area = plan['folder_type'] + 's'
    noun = plan['folder_type']

    def reopen():
        page.goto(_url(plan, folder_id), wait_until='domcontentloaded')
        verify_breadcrumb(name=plan['name'], folder_id=folder_id)
        _in_scope(page, plan, folder_id)

    def object_url():
        url = urlsplit(page.url)
        base = urlsplit(plan['start_url'])
        match = re.fullmatch(re.escape(base.path) + r'/([A-Za-z0-9_-]+)(?:/.*)?', url.path)
        if ((url.scheme, url.netloc) != (base.scheme, base.netloc) or not match
                or url.query or url.fragment):
            raise Stop('Created container did not open its exact native detail route')
        return match.group(1)

    reopen()
    cell = _settled_search(page, area, name)
    _in_scope(page, plan, folder_id)
    if old:
        if cell is None:
            raise Stop('Previously created container is absent from its folder')
        click(cell.get_by_text(name, exact=True))
        if object_url() != old.get('object_id'):
            raise Stop('Folder row now opens a different container')
        return {'id': old['object_id'], 'name': name, 'folder_id': folder_id,
                'type': noun, 'location_id': plan['location_id'], 'url': page.url}
    if cell is not None:
        raise Stop('An object with this name already exists in the folder')
    button = page.locator('#create-new-button').and_(
        page.get_by_role('button', name='New ' + noun, exact=True))
    if button.count() != 1 or not button.is_enabled():
        raise Stop('Native create control is unavailable in the opened folder')
    _state(path, request, 'INTENT_RECORDED')
    click(button)
    dialog = page.get_by_role('dialog')
    dialog.wait_for(state='visible', timeout=45000)
    if dialog.count() != 1:
        raise Stop('Native creation dialog is ambiguous')
    fill(dialog.get_by_role('textbox', name='e.g. Sales ' + noun, exact=True), name)
    click(dialog.get_by_role('button', name='Create', exact=True))
    page.get_by_role('button', name='Share ' + noun, exact=True).wait_for(state='visible', timeout=45000)
    created_id = object_url()
    reopen()
    cell = _settled_search(page, area, name)
    _in_scope(page, plan, folder_id)
    if cell is None:
        raise Stop('Created object was not found in its independently reopened parent folder')
    click(cell.get_by_text(name, exact=True))
    if object_url() != created_id:
        raise Stop('Parent folder row opens a different object after creation')
    _state(path, request, 'VERIFIED', folder_id=folder_id, object_id=created_id)
    return {'id': created_id, 'name': name, 'folder_id': folder_id,
            'type': noun, 'location_id': plan['location_id'], 'url': page.url}
