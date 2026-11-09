"""Append captured native form built-ins without creating custom field schemas.

The parent editor runner owns tenant identity, writer leases and uncertain-write
journals. This operation never submits a form, creates a contact or changes a
contact-field definition. Existing standard-field property edits remain separate.
"""
from copy import deepcopy
import re


BUILTIN_LABELS = (
    'First Name', 'Last Name', 'Phone', 'Email',
    'Full Name', 'Date of birth', 'Address', 'City', 'State', 'Country',
    'Postal Code', 'Organization', 'Website',
)


class FieldPlacementError(ValueError):
    pass


def validate(step):
    if (not isinstance(step, dict)
            or set(step) - {'id', 'action', 'add_fields'}):
        raise FieldPlacementError('Unsupported native built-in placement option')
    if 'action' in step and step['action'] != 'native_field_placement':
        raise FieldPlacementError('Native placement action does not match this handler')
    fields = step.get('add_fields')
    if not isinstance(fields, list) or not fields:
        raise FieldPlacementError('add_fields must be a nonempty list of captured built-in labels')
    if any(not isinstance(field, str) or field not in BUILTIN_LABELS for field in fields):
        raise FieldPlacementError('Only captured built-in form labels are supported; custom fields require their dependency rail')
    if len(fields) != len(set(fields)):
        raise FieldPlacementError('Duplicate requested built-in fields require reconciliation')
    if 'Address' in fields and set(fields).intersection({'City', 'State', 'Country', 'Postal Code'}):
        raise FieldPlacementError('Address already owns its address children; standalone overlaps require reconciliation')
    return deepcopy(step)


def _stop(reason):
    if __package__:
        from .skill6_playwright import Stop
    else:
        from skill6_playwright import Stop
    raise Stop(reason)


def _query_controls(frame):
    """Read the captured visible Query Key row, never a placeholder guess.

    Website and existing standard fields expose these same native property
    controls. Row identity is checked before using an input's value; counts or
    indices alone are insufficient when different field types add controls.
    """
    inputs = frame.get_by_role('textbox', name='Please Input', exact=True)
    matches = []
    for index in range(inputs.count()):
        row = inputs.nth(index).evaluate("el => el.closest('.form-group')?.textContent || ''")
        if isinstance(row, str) and re.fullmatch(r'\s*Query Key\s*', row):
            matches.append(inputs.nth(index))
    return matches


def _query_key(frame):
    matches = _query_controls(frame)
    if len(matches) != 1:
        _stop('Native field Query Key row is missing or ambiguous; capture required')
    matches[0].wait_for(state='visible', timeout=45000)
    value = matches[0].input_value()
    if not isinstance(value, str) or not value.strip() or len(value) > 256 or any(ord(c) < 32 for c in value):
        _stop('Native field query identity is unavailable; reconcile before placement')
    return value


# Only live-observed native identities enter this map. Menu labels alone do not
# prove a contact-field key or permission to invent an unobserved placement.
CAPTURED_FIELDS = {
    'First Name': {'field_type':'text', 'query_keys':('first_name',)},
    'Last Name': {'field_type':'text', 'query_keys':('last_name',)},
    'Phone': {'field_type':'text', 'query_keys':('phone',)},
    'Email': {'field_type':'email', 'query_keys':('email',)},
    'Full Name': {'field_type':'text', 'query_keys':('full_name',)},
    'Website': {'field_type':'text', 'query_keys':('website',)},
    'Organization': {'field_type':'text', 'query_keys':('organization',)},
    'Date of birth': {'field_type':'date', 'query_keys':('date_of_birth',)},
    'City': {'field_type':'text', 'query_keys':('city',)},
    'State': {'field_type':'text', 'query_keys':('state',)},
    'Country': {'field_type':'select', 'query_keys':('country',)},
    'Postal Code': {'field_type':'text', 'query_keys':('postal_code',)},
    'Address': {'field_type':'group', 'query_keys':('address', 'country', 'state', 'city', 'postal_code')},
}
SELECTABLE_INPUT_TYPES = frozenset(('text', 'email', 'date', 'select', 'RADIO'))
NON_CONTACT_TYPES = frozenset(('terms_and_conditions', 'submit', 'h1'))
CANVAS_ITEMS = '#form-builder-container > .form-field-wrapper'
SUBMIT_DROP = CANVAS_ITEMS + ':has(button#submit-button)'


def _close_initial(frame):
    dialog = frame.get_by_role('dialog')
    if dialog.count():
        if dialog.count() != 1 or dialog.get_by_text('Form Element', exact=True).count() != 1:
            _stop('Unexpected native form dialog requires reconciliation')
        close = dialog.get_by_role('button', name='Close', exact=True)
        if close.count() != 1:
            _stop('Native Form Element close control changed')
        close.click(timeout=45000)


def _close_properties(frame):
    # Captured top-level Back plus the property-panel Back. Select by the
    # observed exact count; never use the first global Back as a field control.
    backs = frame.get_by_role('button', name='Back', exact=True)
    if backs.count() != 2:
        _stop('Native field property Back controls changed')
    backs.nth(1).click(timeout=45000)


_ADDRESS_QUERIES = {
    'Street Address':'address', 'Country':'country', 'State':'state',
    'City':'city', 'Postal Code':'postal_code',
}


def _address_headers(frame):
    """Accept the five captured children plus the observed autocomplete section.

    The November 9 builder adds an Auto Complete Address / New accordion to the
    same panel. It is a settings section, not a sixth contact-field identity.
    Unknown extra sections remain a capture blocker.
    """
    headers = frame.locator('.n-collapse-item__header-main')
    count=headers.count()
    if count not in (len(_ADDRESS_QUERIES),len(_ADDRESS_QUERIES)+1):
        _stop('Native Address child inventory is incomplete or changed')
    if count==len(_ADDRESS_QUERIES)+1:
        autocomplete=headers.filter(has_text=re.compile(r'^\s*Auto Complete Address\s*New\s*$'))
        if autocomplete.count()!=1:
            _stop('Unknown extra native Address accordion requires capture')
    return headers


def _address_keys(frame, *, allow_unknown_queries=False):
    """Read the captured five child fields of one complete native Address group."""
    headers=_address_headers(frame)
    observed = []
    for label, expected in _ADDRESS_QUERIES.items():
        enabled = frame.get_by_role('checkbox', name=label, exact=True)
        if enabled.count() != 1 or not enabled.is_checked():
            _stop('Native Address child selection differs from the captured complete group')
        header = headers.filter(has_text=re.compile(r'^\s*' + re.escape(label) + r'\s*$'))
        if header.count() != 1:
            _stop('Native Address child header is missing or ambiguous')
        item = header.locator('..').locator('..')
        controls = _query_controls(item)
        if len(controls) > 1:
            _stop('Native Address child Query Key is ambiguous')
        if not controls or not controls[0].is_visible():
            header.click(timeout=45000)
        key = _query_key(item)
        if not allow_unknown_queries and key != expected:
            _stop('Native Address child Query Key differs from its captured identity')
        if allow_unknown_queries and any(char.isspace() for char in key):
            _stop('Native Address child Query Key is not a valid query token')
        observed.append(key)
    if len(set(observed)) != len(_ADDRESS_QUERIES):
        _stop('Native Address child query identities are duplicated')
    return tuple(observed)


def _inventory(frame, *, allow_unknown_queries=False):
    """Read captured native shapes; optionally retain arbitrary existing keys.

    Placement keeps unknown keys refused, because they can be renamed built-ins.
    Property updates may read those keys to prove a new query key is unoccupied;
    this option never relaxes type, shape or duplicate-key validation.
    """
    # Native property Back restores a previously open Quick Add drawer. Close
    # that known drawer before inventory so a later Add action cannot toggle it.
    _close_initial(frame)
    items = frame.locator(CANVAS_ITEMS)
    count = items.count()
    if not count:
        _stop('Native form field inventory is unavailable; refusing inferred absence')
    inventory = {}
    for index in range(count):
        if items.count() != count:
            _stop('Native canvas inventory changed while reading field identities')
        item = items.nth(index)
        labels = item.locator('[data-field-type]')
        if labels.count() != 1:
            _stop('Native canvas field type is missing or ambiguous')
        field_type = labels.get_attribute('data-field-type')
        if field_type in NON_CONTACT_TYPES:
            continue
        if field_type not in SELECTABLE_INPUT_TYPES | {'group'}:
            _stop('Uncaptured existing native field type requires inventory capture')
        controls = item.locator('input')
        if field_type == 'RADIO':
            radios = item.locator('input[type="radio"]')
            if radios.count() < 1 or radios.count() != controls.count():
                _stop('Native custom Radio input inventory is missing or changed')
            ids = [radios.nth(i).get_attribute('name') for i in range(radios.count())]
            if not ids[0] or len(set(ids)) != 1:
                _stop('Native custom Radio inputs do not share one existing field identity')
            selected = labels
        else:
            expected_count = 6 if field_type == 'group' else 1
            if controls.count() != expected_count:
                _stop('Native field selectable input is missing or ambiguous')
            # The complete Address group has search plus five child inputs. Its
            # second input selects the whole group, including renamed labels.
            selected = controls.nth(1) if field_type == 'group' else controls
        selected.click(timeout=45000)
        if field_type in ('date', 'select'):
            selected.press('Escape', timeout=45000)
        gear = item.locator('[aria-label="Open settings"]')
        gear.wait_for(state='visible', timeout=45000)
        if gear.count() != 1:
            _stop('Native field settings control does not belong to its canvas wrapper')
        gear.click(timeout=45000)
        frame.get_by_text('Address Fields' if field_type == 'group' else 'General Settings', exact=True).wait_for(state='visible', timeout=45000)
        keys = _address_keys(frame, allow_unknown_queries=allow_unknown_queries) if field_type == 'group' else (_query_key(frame),)
        known = {'first_name', 'last_name', 'phone', 'email'} | {
            key for spec in CAPTURED_FIELDS.values() for key in spec['query_keys']}
        for key in keys:
            if not allow_unknown_queries and key not in known:
                _stop('Uncaptured existing native field query requires inventory capture')
            if key in inventory:
                _stop('Duplicate native field query identities require reconciliation')
            inventory[key] = field_type
        _close_properties(frame)
    if items.count() != count:
        _stop('Native canvas inventory changed while reading field identities')
    return inventory


def _drag_builtin(frame, label, spec):
    import re
    if __package__:
        from .skill6_playwright import click
    else:
        from skill6_playwright import click
    click(frame.get_by_role('button', name='Add Form Element', exact=True))
    dialog = frame.get_by_role('dialog')
    dialog.wait_for(state='visible', timeout=45000)
    if dialog.count() != 1 or dialog.get_by_text('Form Element', exact=True).count() != 1:
        _stop('Native Quick Add drawer is unavailable or ambiguous')
    tile_labels = dialog.locator('.gui__builder-card:visible > .gui__builder-card--label').filter(
        has_text=re.compile(r'^\s*' + re.escape(label) + r'\s*$'))
    if tile_labels.count() > 1:
        _stop('Requested native Quick Add tile is unavailable or ambiguous')
    tile_labels.wait_for(state='visible', timeout=45000)
    if tile_labels.count() != 1:
        _stop('Requested native Quick Add tile is unavailable or ambiguous')
    source = tile_labels.locator('..')
    target = frame.locator(SUBMIT_DROP)
    if source.count() != 1 or target.count() != 1 or not target.is_visible():
        _stop('Native built-in drag source or Submit boundary changed')
    box = target.bounding_box()
    if not box or box['width'] < 4 or box['height'] < 4:
        _stop('Native Submit boundary has no safe drop position')
    # A tile click only selects in this native builder. Perform one real pointer
    # drag; never repeat it when its outcome is uncertain.
    source.drag_to(target, target_position={'x':box['width'] / 2, 'y':1}, timeout=45000)
    frame.get_by_text('Address Fields' if spec['field_type'] == 'group' else 'General Settings', exact=True).wait_for(state='visible', timeout=45000)
    keys = _address_keys(frame) if spec['field_type'] == 'group' else (_query_key(frame),)
    if keys != spec['query_keys']:
        _stop('New native field query identity does not match the captured built-in')
    _close_properties(frame)


def configure(page, step):
    """Append captured built-ins, reuse existing queries and independently reopen.

    A built-in without a captured query/type mapping remains unsupported. This
    handler never creates contact-field schemas or retries an uncertain drag.
    """
    if __package__:
        from .skill6_playwright import click, form_builder, wait_until
        from .assessments import reopen_editor
    else:
        from skill6_playwright import click, form_builder, wait_until
        from assessments import reopen_editor
    step = validate(step)
    if any(label not in CAPTURED_FIELDS for label in step['add_fields']):
        _stop('Requested native built-in still requires field/query capture')
    frame = form_builder(page)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    name, editor_url = title.input_value(), page.url
    if not isinstance(name, str) or not name.strip():
        _stop('Saved native form identity is unavailable')
    _close_initial(frame)
    click(frame.get_by_role('tab', name='Edit', exact=True))
    initial = _inventory(frame)
    # Resolve every requested field against the complete existing inventory
    # before the first drag. A later Address/standalone overlap or type conflict
    # must not follow an earlier successful insertion in the same job.
    planned = dict(initial)
    placements = []
    for label in step['add_fields']:
        spec = CAPTURED_FIELDS[label]
        keys = spec['query_keys']
        present = [key for key in keys if key in planned]
        if present:
            if len(present) != len(keys) or any(planned[key] != spec['field_type'] for key in keys):
                _stop('Existing native query belongs to a different field type or overlapping address layout')
            placements.append((label, spec, True))
        else:
            placements.append((label, spec, False))
            planned.update({key:spec['field_type'] for key in keys})
    expected, outcomes = dict(initial), []
    added = False
    for label, spec, reused in placements:
        keys = spec['query_keys']
        if reused:
            outcomes.append({'field':label, 'query_keys':list(keys), 'placement':'reused'})
            continue
        if _inventory(frame) != expected:
            _stop('Native canvas identities changed after the complete placement preflight')
        _drag_builtin(frame, label, spec)
        expected.update({key:spec['field_type'] for key in keys})
        if _inventory(frame) != expected:
            _stop('Native built-in placement changed the expected canvas identity inventory')
        outcomes.append({'field':label, 'query_keys':list(keys), 'placement':'added'})
        added = True
    if added:
        save = frame.get_by_role('button', name='Save', exact=True)
        click(save)
        wait_until(lambda: save.count() == 1 and save.is_enabled(), 'Native form save did not finish')
    reopen_editor(page, 'form', name, editor_url)
    frame = form_builder(page)
    _close_initial(frame)
    click(frame.get_by_role('tab', name='Edit', exact=True))
    if _inventory(frame) != expected:
        _stop('Saved native built-in field identities did not persist after reopen')
    return {'status':'BUILTIN_FIELDS_SAVED_AND_REOPENED' if added else 'BUILTIN_FIELDS_REUSED_AND_REOPENED',
            'editor_url':editor_url, 'fields':outcomes, 'submission_verified':False}
