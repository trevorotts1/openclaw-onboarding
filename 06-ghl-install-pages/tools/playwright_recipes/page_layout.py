"""Native page-builder row insertion and exact column targeting.

Captured builder controls: Rows presets have IDs "1 Column" through "6 Column";
the canvas uses .c-section > .c-row > .c-column with native IDs. Insertion is
uses a section-scoped empty-slot control on multi-section canvases.
Existing columns can be resolved using their recorded identities.
"""
from __future__ import annotations

import json
import re


def _stop(message):
    from .skill6_playwright import Stop
    raise Stop(message)


def _id(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        _stop(f'{name} must be an exact native ID')
    return value


def validate(step):
    if not isinstance(step, dict) or not isinstance(step.get('layout'), dict):
        _stop('page_layout requires a layout object')
    layout = step['layout']
    if not {'section_id', 'columns'} <= set(layout) or set(layout) - {'section_id', 'columns', 'after_row_id'}:
        _stop('layout requires section_id and columns, and may specify after_row_id')
    _id(layout['section_id'], 'section_id')
    if 'after_row_id' in layout:
        _id(layout['after_row_id'], 'after_row_id')
    if type(layout['columns']) is not int or not 1 <= layout['columns'] <= 6:
        _stop('columns must be an integer from 1 through 6')
    return layout


def _selector(cls, identifier):
    return '.' + cls + '[id=' + json.dumps(identifier) + ']'


def _one(locator, message):
    if locator.count() != 1:
        _stop(message)
    return locator


def _columns(row):
    return row.evaluate("row => Array.from(row.querySelectorAll('.c-column')).filter(e => e.closest('.c-row') === row).map(e => e.id)")


def resolve_column(frame, placement):
    if not isinstance(placement, dict):
        _stop('placement must be an object')
    allowed = {'section_id', 'row_id', 'column_id', 'column_index', 'expected_columns'}
    if set(placement) - allowed or not {'section_id', 'row_id'} <= set(placement):
        _stop('placement requires exact section_id and row_id')
    if ('column_id' in placement) == ('column_index' in placement):
        _stop('placement requires exactly one of column_id or column_index')
    section_id = _id(placement['section_id'], 'section_id')
    row_id = _id(placement['row_id'], 'row_id')
    expected = placement.get('expected_columns')
    if expected is not None and (type(expected) is not int or not 1 <= expected <= 6):
        _stop('expected_columns must be an integer from 1 through 6')
    if 'column_index' in placement:
        index = placement['column_index']
        if type(index) is not int or not 0 <= index < 6 or expected is None or index >= expected:
            _stop('column_index requires expected_columns and must be in range')
    else:
        _id(placement['column_id'], 'column_id')
    section = _one(frame.locator(_selector('c-section', section_id)), 'Section identity is missing or ambiguous')
    row = _one(frame.locator(_selector('c-row', row_id)), 'Row identity is missing or ambiguous')
    if row.evaluate("e => e.closest('.c-section')?.id") != section_id:
        _stop('Row does not belong to the requested section')
    ids = _columns(row)
    if not ids or len(ids) > 6 or len(ids) != len(set(ids)):
        _stop('Row columns are missing or ambiguous')
    for identifier in ids:
        _id(identifier, 'column_id')
    if expected is not None and len(ids) != expected:
        _stop('Row column count does not match expected_columns')
    column_id = ids[placement['column_index']] if 'column_index' in placement else placement['column_id']
    if column_id not in ids:
        _stop('Column does not belong to the requested row')
    column = _one(frame.locator(_selector('c-column', column_id)), 'Column identity is missing or ambiguous')
    if column.evaluate("e => e.closest('.c-row')?.id") != row_id:
        _stop('Column does not belong to the requested row')
    return column


def _inventory(frame):
    return frame.locator('.c-section, .c-row, .c-column').evaluate_all('''els => els.map(e => ({
        kind: e.classList.contains('c-section') ? 'section' : e.classList.contains('c-row') ? 'row' : 'column',
        id: e.id, section_id: e.closest('.c-section')?.id || null,
        row_id: e.closest('.c-row')?.id || null
    }))''')


def _preserves_order(previous, current):
    """Require every existing identity and its parent in the same relative order."""
    remaining = iter(current)
    return all(any(item == candidate for candidate in remaining) for item in previous)



def _select_row(frame, section_id, row_id):
    from .skill6_playwright import click, visible
    _one(frame.locator(_selector('c-section', section_id)), 'Section identity is missing or ambiguous')
    row = _one(frame.locator(_selector('c-row', row_id)), 'Row identity is missing or ambiguous')
    if row.evaluate("e => e.closest('.c-section')?.id") != section_id:
        _stop('Row does not belong to the requested section')
    columns = _columns(row)
    if not columns or len(columns) > 6 or len(set(columns)) != len(columns):
        _stop('Row columns are missing or ambiguous')
    column = resolve_column(frame, {'section_id': section_id, 'row_id': row_id,
                                    'column_id': columns[0], 'expected_columns': len(columns)})
    name = _one(row.locator(':scope > .ui-row .element-name'), 'Row label is missing or ambiguous').inner_text().strip()
    if not name:
        _stop('Row label is empty')
    click(column)
    breadcrumb = frame.get_by_role('navigation', name='Page structure breadcrumb', exact=True).get_by_role('button', name=name, exact=True)
    click(_one(breadcrumb, 'Row breadcrumb is missing or ambiguous'))
    selected = row.locator(':scope > .ui-row.selected')
    _one(selected, 'Requested row was not selected')
    quick_add = frame.get_by_role('dialog').get_by_role('button', name='Quick Add', exact=True)
    if quick_add.count() == 1 and visible(quick_add):
        click(frame.locator('#hl-builder-add-elements-button'))
    elif quick_add.count() > 1:
        _stop('Quick Add panel identity is ambiguous')
    _one(selected, 'Row selection was lost')
    return row


def validate_responsive(step):
    p = step.get('responsive') if isinstance(step, dict) else None
    if not isinstance(p, dict) or set(p) != {'profile', 'section_id', 'row_id', 'device', 'width_percent'}:
        _stop('responsive requires profile, section_id, row_id, device and width_percent')
    if p['profile'] != 'funnel_row_width_v1':
        _stop('Unsupported captured responsive profile')
    _id(p['section_id'], 'section_id')
    _id(p['row_id'], 'row_id')
    if p['device'] not in ('desktop', 'tablet'):
        _stop('This captured profile supports desktop and tablet widths only')
    if type(p['width_percent']) is not int or not 30 <= p['width_percent'] <= 100:
        _stop('width_percent must be an integer from 30 through 100')
    return p


def configure_responsive(page, step):
    from .skill6_playwright import page_builder_ready, click, fill, save_page, wait_until, native_order_inventory, assert_native_orders_preserved
    p = validate_responsive(step)
    frame = page_builder_ready(page)
    device = _one(frame.locator('#pg-funnel-builder__btn--' + p['device']), 'Captured device control is missing or ambiguous')
    before = _inventory(frame)
    orders = native_order_inventory(frame)
    alternate = 'tablet' if p['device'] == 'desktop' else 'desktop'
    other_device = _one(frame.locator('#pg-funnel-builder__btn--' + alternate), 'Alternate device control is missing or ambiguous')
    click(other_device)
    _select_row(frame, p['section_id'], p['row_id'])
    other_before = _one(frame.get_by_placeholder('Please Input', exact=True), 'Alternate row width input is missing or ambiguous').input_value().strip()
    click(device)
    row = _select_row(frame, p['section_id'], p['row_id'])
    width = _one(frame.get_by_placeholder('Please Input', exact=True), 'Row width input is missing or ambiguous')
    slider = _one(frame.get_by_role('slider', name='Width', exact=True), 'Row width slider is missing or ambiguous')
    # Check the displayed native bounds before changing any values.
    minimum, maximum = slider.get_attribute('min'), slider.get_attribute('max')
    try:
        within_bounds = float(minimum) <= p['width_percent'] <= float(maximum)
    except (TypeError, ValueError):
        within_bounds = False
    if not within_bounds:
        _stop('Requested width is outside the captured native slider bounds')
    fill(width, str(p['width_percent']))
    width.press('Tab')
    if (width.input_value().strip() != str(p['width_percent'])
            or row.evaluate('e => e.style.width') != str(p['width_percent']) + '%'):
        _stop('Row width readback did not retain the requested value; page was not saved')
    if _inventory(frame) != before:
        _stop('Existing layout changed during responsive edit; page was not saved')
    assert_native_orders_preserved(orders, native_order_inventory(frame))
    editor_url = page.url
    save_page(frame)
    page.goto(editor_url, wait_until='domcontentloaded', timeout=45000)
    frame = page_builder_ready(page)
    device = _one(frame.locator('#pg-funnel-builder__btn--' + p['device']), 'Saved device control is missing or ambiguous')
    other_device = _one(frame.locator('#pg-funnel-builder__btn--' + alternate), 'Saved alternate device control is missing or ambiguous')
    wait_until(lambda: _inventory(frame) == before, 'Layout did not persist after the responsive edit was reopened')
    click(other_device)
    _select_row(frame, p['section_id'], p['row_id'])
    other_after = _one(frame.get_by_placeholder('Please Input', exact=True), 'Alternate row width input is missing or ambiguous').input_value().strip()
    if other_after != other_before:
        _stop('Another device width changed after the saved responsive edit')
    click(device)
    _select_row(frame, p['section_id'], p['row_id'])
    width = _one(frame.get_by_placeholder('Please Input', exact=True), 'Saved row width input is missing or ambiguous')
    if width.input_value().strip() != str(p['width_percent']):
        _stop('Saved row width readback does not match the request')
    assert_native_orders_preserved(orders, native_order_inventory(frame))
    return {'status': 'RESPONSIVE_SAVED', 'section_id': p['section_id'], 'row_id': p['row_id'],
            'device': p['device'], 'width_percent': p['width_percent']}

def configure(page, step):
    from .skill6_playwright import (page_builder_ready, add_tile, click, visible, save_page, wait_until,
                                    native_order_inventory, assert_native_orders_preserved)
    layout = validate(step)
    frame = page_builder_ready(page)
    sections = frame.locator('.c-section')
    if 'after_row_id' in layout:
        target = _one(frame.locator(_selector('c-section', layout['section_id'])), 'Section identity is missing or ambiguous')
        anchor = _one(frame.locator(_selector('c-row', layout['after_row_id'])), 'Anchor row identity is missing or ambiguous')
        if anchor.evaluate("e => e.closest('.c-section')?.id") != layout['section_id']:
            _stop('Anchor row does not belong to the requested section')
        anchor_columns = _columns(anchor)
        if not anchor_columns or len(anchor_columns) > 6 or len(set(anchor_columns)) != len(anchor_columns):
            _stop('Anchor row columns are missing or ambiguous')
        anchor_column = resolve_column(frame, {'section_id': layout['section_id'], 'row_id': layout['after_row_id'], 'column_id': anchor_columns[0], 'expected_columns': len(anchor_columns)})
        name = _one(anchor.locator(':scope > .ui-row .element-name'), 'Anchor row label is missing or ambiguous').inner_text().strip()
        if not name:
            _stop('Anchor row label is empty')
    elif sections.count() == 1 and sections.first.get_attribute('id') == layout['section_id']:
        target = None
    else:
        target = _one(frame.locator(_selector('c-section', layout['section_id'])), 'Section identity is missing or ambiguous')
        slot = target.locator(':scope > .inner > .empty-slot .empty-component')
        _one(slot, 'The target section does not expose its captured empty row slot')
    before_orders = native_order_inventory(frame)
    before = _inventory(frame)
    for item in before:
        _id(item['id'], item['kind'] + '_id')
    if len({(x['kind'], x['id']) for x in before}) != len(before):
        _stop('Existing layout identities are ambiguous')
    if 'after_row_id' in layout:
        click(anchor_column)
        breadcrumb = frame.get_by_role('navigation', name='Page structure breadcrumb', exact=True).get_by_role('button', name=name, exact=True)
        click(_one(breadcrumb, 'Anchor row breadcrumb is missing or ambiguous'))
        selected = anchor.locator(':scope > .ui-row.selected')
        _one(selected, 'Requested anchor row was not selected')
        quick_add = frame.get_by_role('dialog').get_by_role('button', name='Quick Add', exact=True)
        if quick_add.count() == 1 and visible(quick_add):
            click(frame.locator('#hl-builder-add-elements-button'))
        elif quick_add.count() > 1:
            _stop('Quick Add panel identity is ambiguous')
        _one(selected, 'Anchor row selection was lost')
        add_tile(frame, 'Rows', f"{layout['columns']} Column")
    elif target is None:
        add_tile(frame, 'Rows', f"{layout['columns']} Column")
    else:
        click(slot)
        preset = frame.locator('div.gui__builder-card[id=' + json.dumps(f"{layout['columns']} Column") + ']')
        _one(preset, 'The requested native Rows preset is missing or ambiguous')
        click(preset)
    def new_row_ready():
        return len([x for x in _inventory(frame) if x['kind'] == 'row']) == len([x for x in before if x['kind'] == 'row']) + 1
    wait_until(new_row_ready, 'Native row did not appear')
    after = _inventory(frame)
    if not _preserves_order(before, after):
        _stop('Existing layout changed during native row insertion; page was not saved')
    added = [x for x in after if x not in before]
    rows = [x for x in added if x['kind'] == 'row']
    cols = [x for x in added if x['kind'] == 'column']
    if len(rows) != 1 or rows[0]['section_id'] != layout['section_id'] or len(cols) != layout['columns']:
        _stop('Created row does not match the requested section and column count; page was not saved')
    row_id = _id(rows[0]['id'], 'row_id')
    if 'after_row_id' in layout:
        section_rows = [x['id'] for x in after if x['kind'] == 'row' and x['section_id'] == layout['section_id']]
        if section_rows.index(row_id) != section_rows.index(layout['after_row_id']) + 1:
            _stop('Created row is not immediately after its requested anchor; page was not saved')
    if any(x['row_id'] != row_id or x['section_id'] != layout['section_id'] for x in cols):
        _stop('Created columns are outside the requested row; page was not saved')
    ids = [_id(x['id'], 'column_id') for x in cols]
    if len(set(ids)) != len(ids):
        _stop('Created column identities are ambiguous; page was not saved')
    for identifier in ids:
        resolve_column(frame, {'section_id': layout['section_id'], 'row_id': row_id,
                               'column_id': identifier, 'expected_columns': layout['columns']})
    assert_native_orders_preserved(before_orders, native_order_inventory(frame))
    editor_url = page.url
    save_page(frame)
    page.goto(editor_url, wait_until='domcontentloaded', timeout=45000)
    frame = page_builder_ready(page)
    wait_until(lambda: _inventory(frame) == after, 'Saved layout did not reappear after reopening')
    persisted = _inventory(frame)
    if persisted != after:
        _stop('Saved layout readback does not retain the requested row and existing siblings')
    assert_native_orders_preserved(before_orders, native_order_inventory(frame))
    return {'section_id': layout['section_id'], 'row_id': row_id, 'column_ids': ids,
            'expected_columns': layout['columns'], 'status': 'SAVED'}


def verify_completed(page, step, result):
    """Re-read the exact native row and columns after a completed journal."""
    from .skill6_playwright import page_builder_ready
    layout = validate(step)
    if not isinstance(result, dict) or result.get('status') != 'SAVED':
        _stop('Native row receipt is invalid')
    row_id = _id(result.get('row_id'), 'row_id')
    ids = result.get('column_ids')
    if (result.get('section_id') != layout['section_id'] or result.get('expected_columns') != layout['columns']
            or not isinstance(ids, list) or len(ids) != layout['columns']
            or any(not isinstance(x, str) for x in ids) or len(set(ids)) != len(ids)):
        _stop('Native row receipt does not match the requested layout')
    frame = page_builder_ready(page)
    for identifier in ids:
        resolve_column(frame, {'section_id': layout['section_id'], 'row_id': row_id,
                               'column_id': _id(identifier, 'column_id'), 'expected_columns': layout['columns']})
    if 'after_row_id' in layout:
        section_rows = [x['id'] for x in _inventory(frame) if x['kind'] == 'row' and x['section_id'] == layout['section_id']]
        if layout['after_row_id'] not in section_rows or row_id not in section_rows or section_rows.index(row_id) != section_rows.index(layout['after_row_id']) + 1:
            _stop('Saved row no longer follows its requested anchor')
    row = _one(frame.locator(_selector('c-row', row_id)), 'Saved row identity is missing or ambiguous')
    if _columns(row) != ids:
        _stop('Saved row column order does not match the receipt')
    return result


def verify_responsive(page, step, result):
    """Re-read a saved responsive width from the captured device-specific UI."""
    from .skill6_playwright import page_builder_ready, click
    p = validate_responsive(step)
    if not isinstance(result, dict) or result.get('status') != 'RESPONSIVE_SAVED' or any(result.get(k) != p[k] for k in ('section_id', 'row_id', 'device', 'width_percent')):
        _stop('Responsive receipt does not match the request')
    frame = page_builder_ready(page)
    click(_one(frame.locator('#pg-funnel-builder__btn--' + p['device']), 'Captured device control is missing or ambiguous'))
    _select_row(frame, p['section_id'], p['row_id'])
    width = _one(frame.get_by_placeholder('Please Input', exact=True), 'Saved row width input is missing or ambiguous')
    if width.input_value().strip() != str(p['width_percent']):
        _stop('Saved responsive width no longer matches the receipt')
    return result
