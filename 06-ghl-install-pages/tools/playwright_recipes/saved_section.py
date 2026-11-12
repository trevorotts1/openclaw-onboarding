"""Native page-builder Saved Assets / Saved Sections operations.

The UI profile is intentionally explicit: section library labels and scope
controls vary between GHL builder generations. A handler only operates after
the observed profile binds those controls and the live saved-section inventory.
"""
from __future__ import annotations

import re


def _stop(message):
    from .skill6_playwright import Stop
    raise Stop(message)


def _native_id(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        _stop(f'{name} must be an exact native identity')
    return value


def validate(step):
    """Validate the public ``saved_section`` action contract."""
    if not isinstance(step, dict) or not isinstance(step.get('saved_section'), dict):
        _stop('saved_section requires a saved_section object')
    p = step['saved_section']
    op = p.get('operation')
    if op not in ('inventory', 'save', 'insert', 'reuse', 'edit'):
        _stop('saved_section operation must be inventory, save, insert, reuse, or edit')
    common = {'operation', 'profile', 'expected_saved_inventory', 'scope'}
    allowed = {
        'inventory': common,
        'save': common | {'saved_section_name', 'source_section_id', 'expected_section_inventory'},
        'insert': common | {'saved_section_id', 'saved_section_name', 'destination_section_id', 'expected_section_inventory'},
        'reuse': common | {'saved_section_id', 'saved_section_name', 'destination_section_id', 'expected_section_inventory'},
        'edit': common | {'saved_section_id', 'saved_section_name', 'expected_section_inventory', 'requested_section_inventory'},
    }
    required = {'operation', 'profile'}
    if op != 'inventory':
        required |= {'expected_saved_inventory', 'saved_section_name', 'expected_section_inventory'}
    if op in ('insert', 'reuse'):
        required.add('destination_section_id')
    if op == 'save':
        required |= {'source_section_id', 'scope'}
    if op == 'edit':
        required |= {'scope', 'requested_section_inventory'}
    if set(p) - allowed[op] or required - set(p):
        _stop(f'saved_section {op} has unsupported or missing fields')
    profile = p['profile']
    if not isinstance(profile, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', profile):
        _stop('saved_section profile must identify a captured native GHL UI profile')
    expected = p.get('expected_saved_inventory', [])
    if not isinstance(expected, list) or len(expected) > 500:
        _stop('expected_saved_inventory must be the complete bounded observed inventory')
    ids = set()
    for row in expected:
        if not isinstance(row, dict) or set(row) not in ({'name', 'scope'}, {'id', 'name', 'scope'}):
            _stop('saved inventory rows require name and scope, plus id only when the UI exposes it')
        if 'id' in row:
            _native_id(row['id'], 'saved_section_id')
        if ('id' in row and row['id'] in ids) or not isinstance(row['name'], str) or not row['name'].strip():
            _stop('saved section inventory has duplicate identity or missing name')
        if 'id' in row:
            ids.add(row['id'])
        if row['scope'] not in ('template', 'global', 'universal'):
            _stop('saved section inventory scope must be template, global, or universal')
    if op in ('insert', 'reuse', 'edit'):
        if 'saved_section_id' in p:
            _native_id(p['saved_section_id'], 'saved_section_id')
        if not isinstance(p['saved_section_name'], str) or not p['saved_section_name'].strip():
            _stop('saved_section_name must exactly identify the selected saved asset')
        matches = [x for x in expected if (
            x.get('id') == p['saved_section_id'] if 'saved_section_id' in p
            else x['name'] == p['saved_section_name'] and ('scope' not in p or x['scope'] == p['scope']))]
        if len(matches) != 1 or matches[0]['name'] != p['saved_section_name']:
            _stop('selected saved section is not bound to the complete expected inventory')
        if 'scope' in p and matches[0]['scope'] != p['scope']:
            _stop('Requested scope differs from the selected saved asset')
    if op in ('insert', 'reuse'):
        if p['destination_section_id'] is not None:
            _native_id(p['destination_section_id'], 'destination_section_id')
    if op in ('save', 'insert', 'reuse', 'edit'):
        for key in ('expected_section_inventory', 'requested_section_inventory'):
            if key in p and (not isinstance(p[key], list) or len(p[key]) > 1000):
                _stop(f'{key} must be a complete bounded native section inventory')
        for key in ('expected_section_inventory', 'requested_section_inventory'):
            if key in p:
                seen = set()
                for identifier in p[key]:
                    _native_id(identifier, key)
                    if identifier in seen:
                        _stop(f'{key} contains a duplicate native section identity')
                    seen.add(identifier)
    if op == 'save':
        _native_id(p['source_section_id'], 'source_section_id')
        if p['source_section_id'] not in p['expected_section_inventory']:
            _stop('Saved-section source must belong to the expected page inventory')
        if not isinstance(p['saved_section_name'], str) or not p['saved_section_name'].strip():
            _stop('A saved section requires a nonempty library name')
    if op == 'edit':
        scope = p['scope']
        if scope not in ('template', 'global', 'universal'):
            _stop('Editing a saved section requires an explicit template, global, or universal scope')
        row = matches[0]
        if row['scope'] != scope:
            _stop('Requested edit scope differs from the selected saved asset; refusing cross-instance changes')
    if 'scope' in p and p['scope'] not in ('template', 'global', 'universal'):
        _stop('scope must be template, global, or universal')
    return p


def configure(page, step):
    """Execute against the current page using a captured tenant-bound profile.

    Concrete profile adapters are installed only from root-provided live UI
    captures. There is deliberately no guessed selector fallback.
    """
    plan = validate(step)
    from .saved_section_profiles import get_profile
    adapter = get_profile(plan['profile'])
    return adapter.run(page, plan)


def verify_completed(page, step, result):
    """Read current saved state on replay; never repeat a library mutation."""
    plan = validate(step)
    from .saved_section_profiles import get_profile
    return get_profile(plan['profile']).verify_completed(page, plan, result)

