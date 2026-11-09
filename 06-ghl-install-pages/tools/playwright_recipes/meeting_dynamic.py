"""Captured native calendar Meeting Room location editing, without appointments.

The public Calendar location enum does not currently document Meeting Room.
This UI handler changes only an existing assigned staff's captured location
control. Connection identity, complete staff/location inventory and saved
calendar identity must all agree. Booking/link generation proof stays pending.
"""
from copy import deepcopy
import hashlib
import json
import math
import re
import time
from urllib.parse import urlsplit

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click, wait_until
else:
    from skill6_playwright import Stop, assert_tenant, click, wait_until


_SUFFIX = '-calendar-team-member-meeting-location-select'
_KINDS = frozenset(('Custom', 'Meeting Room'))
_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')


def _text(value, label):
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > 512 or any(ord(c) < 32 for c in value)):
        raise Stop(label + ' must be an exact nonempty inventoried label')
    return value


def validate_inputs(inputs, *, require_fresh=True):
    keys = {'location_id', 'location_name', 'start_url', 'calendar_id', 'calendar_name',
            'staff_id', 'connection_staff_label', 'expected_staff_locations', 'staff_dependency'}
    if not isinstance(inputs, dict) or set(inputs) != keys:
        raise Stop('Native dynamic room requires the exact calendar/staff inventory contract')
    data = deepcopy(inputs)
    for key in ('location_id', 'calendar_id', 'staff_id'):
        if not isinstance(data[key], str) or not _ID.fullmatch(data[key]):
            raise Stop('Native dynamic room requires exact inventoried ' + key)
    for key in ('location_name', 'calendar_name', 'connection_staff_label'):
        _text(data[key], key)
    try:
        source = urlsplit(data['start_url'])
        port = source.port
    except (TypeError, ValueError):
        raise Stop('Native dynamic calendar start URL is malformed') from None
    if (source.scheme != 'https' or not source.hostname or source.username or source.password
            or port not in (None,443) or source.fragment
            or source.path != '/v2/location/' + data['location_id'] + '/settings/calendars'
            or source.query != 'section=calendars'):
        raise Stop('Native dynamic room requires the exact observed calendar-settings route')
    roster = data['expected_staff_locations']
    if not isinstance(roster, list) or len(roster) != 1:
        raise Stop('Native dynamic room supports only a complete single-staff/single-location personal calendar inventory')
    seen = set()
    for member in roster:
        if (not isinstance(member, dict)
                or set(member) != {'staff_id', 'staff_name', 'location_kind', 'location_value'}
                or not isinstance(member['staff_id'], str) or not _ID.fullmatch(member['staff_id'])
                or member['staff_id'] in seen or member['location_kind'] not in _KINDS
                or not isinstance(member['location_value'], str)):
            raise Stop('Assigned-staff locations require unique exact identities and supported native kinds')
        _text(member['staff_name'], 'staff_name')
        if any(ord(c) < 32 for c in member['location_value']):
            raise Stop('Native location values must be plain inventoried text')
        if member['location_kind'] != 'Custom' and member['location_value']:
            raise Stop('Only captured Custom location text is supported; other freeform location types require capture')
        seen.add(member['staff_id'])
    if data['staff_id'] not in seen:
        raise Stop('Requested native room staff must already own an inventoried calendar location')
    target = next(member for member in roster if member['staff_id'] == data['staff_id'])
    allowed_labels = {target['staff_name'], target['staff_name'] + ' (Me)', target['staff_name'] + '(Me)'}
    if data['connection_staff_label'] not in allowed_labels:
        raise Stop('Connected staff label must match the exact assigned staff inventory')
    dependency = data['staff_dependency']
    if (not isinstance(dependency, dict)
            or set(dependency) != {'status','provider','location_id','observed_at','operation','http_status','users','complete','total_count'}
            or dependency['status'] != 'VERIFIED' or dependency['location_id'] != data['location_id']
            or dependency['provider'] not in ('skill44','public_api','official_mcp')
            or dependency['operation'] != 'users.search'
            or type(dependency['http_status']) is not int or dependency['http_status'] != 200
            or type(dependency['observed_at']) not in (int,float)
            or not math.isfinite(dependency['observed_at'])):
        raise Stop('Native room connection requires a verified same-location user API receipt')
    if require_fresh and not 0 <= time.time() - dependency['observed_at'] <= 3600:
        raise Stop('Native room user identity receipt must be a fresh successful API read')
    users = dependency['users']
    if (dependency['complete'] is not True or type(dependency['total_count']) is not int
            or not isinstance(users,list) or not users or dependency['total_count'] != len(users)):
        raise Stop('Native Connections name requires a complete same-location API user inventory')
    by_id = {}
    for user in users:
        if (not isinstance(user, dict) or set(user) != {'id','name','roles'}
                or not isinstance(user['id'],str) or not _ID.fullmatch(user['id'])
                or user['id'] in by_id
                or not isinstance(user['roles'],dict) or set(user['roles']) != {'locationIds'}
                or not isinstance(user['roles']['locationIds'],list)
                or data['location_id'] not in user['roles']['locationIds']
                or any(not isinstance(value,str) or not _ID.fullmatch(value)
                       for value in user['roles']['locationIds'])):
            raise Stop('Native room staff inventory contains an unbound or duplicate user identity')
        _text(user['name'],'API user name')
        by_id[user['id']] = user
    matching = [user for user in users if user['name'].casefold() == target['staff_name'].casefold()]
    if (len(matching) != 1 or matching[0]['id'] != data['staff_id']
            or matching[0]['name'] != target['staff_name']):
        raise Stop('Native Connections selected name is ambiguous or differs from the API-confirmed assigned user')
    return data


def configuration_hash(inputs):
    return hashlib.sha256(json.dumps(validate_inputs(inputs, require_fresh=False), sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def _one(control, reason):
    if control.count() != 1 or not control.is_visible():
        raise Stop(reason)
    return control


def _origin(data):
    source = urlsplit(data['start_url'])
    return source.scheme + '://' + source.netloc


def _at(page, data, path, query=''):
    current = urlsplit(page.url)
    source = urlsplit(data['start_url'])
    if ((current.scheme,current.netloc) != (source.scheme,source.netloc)
            or current.path != '/v2/location/' + data['location_id'] + path
            or current.query != query or current.fragment):
        raise Stop('Native calendar route differs from the exact requested tenant/editor')
    assert_tenant(page, data)


def _connected(page, data):
    """Read the already selected unique inventoried staff; never switch accounts.

    The name-only connection card is a prerequisite, not authenticated-ID proof.
    The exact opaque staff ID is verified by the calendar location control."""
    path = '/settings/calendars/connections-new'
    page.goto(_origin(data) + '/v2/location/' + data['location_id'] + path,
              wait_until='domcontentloaded', timeout=45000)
    _at(page, data, path)
    tab = _one(page.get_by_role('tab',name='Video conferencing',exact=True),
               'Native Video conferencing tab changed')
    click(tab)
    current = _one(page.get_by_role('combobox',name=data['connection_staff_label'],exact=True),
                   'Connections current staff differs from the API-confirmed requested user')
    if current.get_attribute('aria-label') != data['connection_staff_label']:
        raise Stop('Native Connections staff identity changed')
    panel = _one(page.get_by_role('tabpanel',name='Video conferencing',exact=True),
                 'Native Video conferencing panel changed')
    card = _one(panel.locator('.calendars-account-details-card-container').filter(
        has=page.locator('img[alt="lc_meet"]')), 'Native Meeting Room connection card changed')
    _one(card.get_by_text('Meeting Room',exact=True), 'Native Meeting Room provider identity changed')
    _one(card.get_by_text('Connected',exact=True), 'Requested staff Meeting Room is not already connected')
    _at(page, data, path)


def _frame(page, data):
    _at(page, data, '/settings/calendars', 'section=calendars')
    iframe = page.locator('iframe[name="calendar-app"]')
    iframe.wait_for(state='visible', timeout=45000)
    _one(iframe, 'Native calendar iframe changed')
    return page.frame_locator('iframe[name="calendar-app"]')


def _open_calendar(page, data):
    page.goto(data['start_url'], wait_until='domcontentloaded', timeout=45000)
    frame = _frame(page, data)
    edit = frame.locator('#edit-calendar-' + data['calendar_id'])
    edit.wait_for(state='visible',timeout=45000)
    click(_one(edit, 'Exact native calendar edit action is missing or ambiguous'))
    frame.get_by_text('Edit - ' + data['calendar_name'],exact=True).wait_for(state='visible',timeout=45000)
    _editor_identity(page, frame, data)
    click(_one(frame.get_by_role('menuitem',name='Staff & location',exact=True),
               'Native Staff & location editor section changed'))
    return frame


def _editor_identity(page, frame, data):
    _at(page,data,'/settings/calendars','section=calendars')
    _one(frame.get_by_text('Edit - ' + data['calendar_name'],exact=True),
         'Native calendar name differs from the inventoried target')
    _one(frame.get_by_role('button',name='Calendar ID: ' + data['calendar_id'],exact=True),
         'Native calendar ID differs from the requested target')


def _location_controls(frame, data):
    """Only the captured one-staff/one-location personal editor shape."""
    selects = frame.locator('[id$="' + _SUFFIX + '"]')
    if selects.count() != 1:
        raise Stop('Only the captured single-staff/single-location calendar editor is supported')
    select = _one(frame.locator('[id="' + data['staff_id'] + _SUFFIX + '"]'),
                  'Native calendar location belongs to another assigned staff ID')
    wrapper = select.locator('..').locator('..').locator('..').locator('..')
    _one(wrapper.locator('[id="' + data['staff_id'] + '-team-member-delete"]'),
         'Native assigned-staff wrapper identity changed')
    selected = _one(select.locator('.n-base-selection-input[title]'),
                    'Native selected meeting location is ambiguous')
    content = _one(selected.locator('.n-base-selection-input__content'),
                   'Native location selection content changed')
    kind = selected.get_attribute('title')
    if kind not in _KINDS or content.inner_text().strip() != kind:
        raise Stop('Existing native calendar location kind requires another capture')
    value = ''
    custom = wrapper.get_by_role('textbox',name='Meeting location',exact=True)
    if kind == 'Custom':
        value = _one(custom, 'Custom native location textbox is missing or ambiguous').input_value()
        # The captured empty display-label state has this control. Existing
        # authored labels need their own capture to preserve them faithfully.
        _one(wrapper.get_by_text('Add display label',exact=True),
             'Custom location display-label state differs from the captured shape')
    elif custom.count():
        raise Stop('Meeting Room still exposes an unexpected custom location textbox')
    if wrapper.locator('#add-location-btn').count() != 1:
        raise Stop('Native single-location wrapper inventory changed')
    return select, {'staff_id':data['staff_id'],
        'staff_name':data['expected_staff_locations'][0]['staff_name'],
        'location_kind':kind,'location_value':value}


def configure(page, inputs):
    """Select native per-appointment Meeting Room without creating a booking."""
    data = validate_inputs(inputs)
    _connected(page,data)
    frame = _open_calendar(page,data)
    _editor_identity(page,frame,data)
    select,before = _location_controls(frame,data)
    if before != data['expected_staff_locations'][0]:
        raise Stop('Native assigned-staff location differs from the complete expected inventory')
    desired = {**before,'location_kind':'Meeting Room','location_value':''}
    changed = before != desired
    if changed:
        click(select)
        option = _one(frame.locator('.n-base-select-option').filter(
            has=frame.get_by_text('Meeting Room',exact=True)),
            'Native Meeting Room location option is missing or ambiguous')
        if (not option.is_enabled() or option.get_attribute('aria-disabled') == 'true'
                or 'n-base-select-option--disabled' in (option.get_attribute('class') or '').split()):
            raise Stop('Native Meeting Room is unavailable for the assigned staff')
        _editor_identity(page,frame,data)
        click(option)
        wait_until(lambda: _location_controls(frame,data)[1] == desired,
                   'Native Meeting Room location did not stage for the exact staff')
        _editor_identity(page,frame,data)
        if _location_controls(frame,data)[1] != desired:
            raise Stop('Native room selection changed before calendar Save')
        save = _one(frame.get_by_role('button',name='Save changes',exact=True),
                    'Native calendar Save changes control changed')
        if not save.is_enabled():
            raise Stop('Native calendar validation did not permit saving the room location')
        click(save)
        # A dismissed editor alone is not persistence proof. Fresh navigation
        # below reopens the exact calendar action/ID and staff location.
        frame.get_by_text('Edit - ' + data['calendar_name'],exact=True).wait_for(state='hidden',timeout=45000)
    frame = _open_calendar(page,data)
    _editor_identity(page,frame,data)
    if _location_controls(frame,data)[1] != desired:
        raise Stop('Native dynamic Meeting Room location did not persist after independent reopen')
    # Discard the unchanged read-only editor and leave the known settings list.
    page.goto(data['start_url'],wait_until='domcontentloaded',timeout=45000)
    _at(page,data,'/settings/calendars','section=calendars')
    return {'status':'DYNAMIC_MEETING_LOCATION_SAVED_AND_REOPENED' if changed else
            'DYNAMIC_MEETING_LOCATION_REUSED_AND_REOPENED',
        'location_id':data['location_id'],'calendar_id':data['calendar_id'],
        'staff_id':data['staff_id'],'configuration_sha256':configuration_hash(data),
        'independent_readback':'VERIFIED','native_location_kind':'Meeting Room',
        'appointment_created':False,'meeting_started':False,
        'dynamic_room_generation_verified':False,'functional_verified':False}
