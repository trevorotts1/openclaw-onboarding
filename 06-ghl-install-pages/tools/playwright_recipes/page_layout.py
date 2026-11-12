"""Native page-builder row insertion and exact column targeting.

Captured builder controls: Rows presets have IDs "1 Column" through "6 Column";
the canvas uses .c-section > .c-row > .c-column with native IDs. Insertion is
limited to a single-section canvas because the shared Rows picker has no
captured section identity. Existing columns can be resolved on multi-section
canvases using their recorded identities.
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
    if set(layout) != {'section_id', 'columns'}:
        _stop('layout requires exactly section_id and columns')
    _id(layout['section_id'], 'section_id')
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


def configure(page, step):
    from .skill6_playwright import builder, add_tile, save_page, wait_until
    layout = validate(step)
    frame = builder(page)
    sections = frame.locator('.c-section')
    if sections.count() != 1 or sections.first.get_attribute('id') != layout['section_id']:
        _stop('Native row insertion requires the exact sole section on the page')
    before = _inventory(frame)
    for item in before:
        _id(item['id'], item['kind'] + '_id')
    if len({(x['kind'], x['id']) for x in before}) != len(before):
        _stop('Existing layout identities are ambiguous')
    add_tile(frame, 'Rows', f"{layout['columns']} Column")
    def new_row_ready():
        return len([x for x in _inventory(frame) if x['kind'] == 'row']) == len([x for x in before if x['kind'] == 'row']) + 1
    wait_until(new_row_ready, 'Native row did not appear')
    after = _inventory(frame)
    if any(x not in after for x in before):
        _stop('Existing layout changed during native row insertion; page was not saved')
    added = [x for x in after if x not in before]
    rows = [x for x in added if x['kind'] == 'row']
    cols = [x for x in added if x['kind'] == 'column']
    if len(rows) != 1 or rows[0]['section_id'] != layout['section_id'] or len(cols) != layout['columns']:
        _stop('Created row does not match the requested section and column count; page was not saved')
    row_id = _id(rows[0]['id'], 'row_id')
    if any(x['row_id'] != row_id or x['section_id'] != layout['section_id'] for x in cols):
        _stop('Created columns are outside the requested row; page was not saved')
    ids = [_id(x['id'], 'column_id') for x in cols]
    if len(set(ids)) != len(ids):
        _stop('Created column identities are ambiguous; page was not saved')
    for identifier in ids:
        resolve_column(frame, {'section_id': layout['section_id'], 'row_id': row_id,
                               'column_id': identifier, 'expected_columns': layout['columns']})
    save_page(frame)
    return {'section_id': layout['section_id'], 'row_id': row_id, 'column_ids': ids,
            'expected_columns': layout['columns'], 'status': 'SAVED'}
