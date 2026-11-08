#!/usr/bin/env python3
"""Meeting Room setup and permanent-link integration, without new auth paths.

Create-dialog selectors were captured in Convert & Flow on 2026-11-08.
An independent host reader is mandatory: absence, identity and saved settings
cannot be inferred from a click. No call is started and no co-host is assigned.

Official contracts checked 2026-11-08:
https://help.gohighlevel.com/support/solutions/articles/155000009149-meeting-room-in-highlevel-overview
https://marketplace.gohighlevel.com/docs/ghl/calendars/update-calendar/
https://marketplace.gohighlevel.com/docs/ghl/calendars/get-calendar/

Static room-link integration below is NOT native per-appointment room generation.
The existing frozen public registry does not include calendars.update. The host
must supply its vetted API dispatcher with that operation enabled; this module
does not invent a transport, credential resolver or override the registry gate.
"""
from copy import deepcopy
import re
from urllib.parse import urlsplit, urlunsplit

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click, fill, navigate, wait_until
else:
    from skill6_playwright import Stop, assert_tenant, click, fill, navigate, wait_until


SECURITY = {'waiting_room':'Waiting room', 'guest_users':'Allow guest users', 'open_room':'Open room'}


def validate_room(spec):
    if not isinstance(spec, dict):
        raise Stop('Meeting Room inputs must be an object')
    for key in ('location_id', 'location_name', 'start_url', 'name', 'slug'):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise Stop('Meeting Room requires ' + key)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', spec['location_id']):
        raise Stop('Invalid meeting location ID')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', spec['slug']):
        raise Stop('Invalid meeting room slug')
    if any(type(spec.get(key)) is not bool for key in SECURITY):
        raise Stop('Specify every meeting security choice as a real boolean')
    if spec.get('cohosts') or spec.get('passcode') or spec.get('start_meeting'):
        raise Stop('Co-host, passcode and call-start actions require their separate identity/security workflows')
    return deepcopy(spec)


def safe_room_url(value):
    parsed = urlsplit(value) if isinstance(value, str) else None
    if not parsed or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise Stop('Use the verified permanent HTTPS room link without credentials, passcodes or query parameters')
    return value


def read_room(page, inputs):
    """Read persisted My room and its editor, captured live 2026-11-08.

    The Invite link contains a passcode query. It is read only to recover its
    canonical origin/path; the query is discarded before any returned receipt.
    room_id is the natural canonical room-link identity, not a backend UUID.
    """
    spec = validate_room(inputs)
    assert_tenant(page, spec)
    detail_url = page.url
    if urlsplit(detail_url).query or urlsplit(detail_url).fragment:
        raise Stop('Meeting detail app URL must not contain credential parameters')
    page.reload(wait_until='domcontentloaded', timeout=45000)
    assert_tenant(page, spec)
    create = page.get_by_role('region', name='Meeting Room for meetings, webinars and more', exact=True).get_by_role('button', name='Create room', exact=True)
    invite = page.get_by_role('textbox', name='Invite link', exact=True)
    wait_until(lambda: (create.count() == 1 and create.is_visible()) or (invite.count() == 1 and invite.is_visible()), 'Meeting Room inventory did not load')
    if create.count() == 1 and create.is_visible():
        return {'status':'ABSENT', 'location_id':spec['location_id'], 'source':'native My room authoritative empty state after reload'}
    parts = urlsplit(invite.input_value())
    canonical = safe_room_url(urlunsplit((parts.scheme, parts.netloc, parts.path, '', '')))
    owner = page.get_by_role('complementary', name='Room owner and status', exact=True)
    if owner.count() != 1:
        raise Stop('Meeting owner/detail structure changed')
    # Security controls were captured on the detail screen, outside the owner box.
    states = {}
    for key, label in SECURITY.items():
        switch = page.get_by_role('switch', name=label, exact=True)
        if switch.count() != 1 or switch.get_attribute('aria-checked') not in ('true', 'false'):
            raise Stop('Meeting read-back security controls changed')
        states[key] = switch.get_attribute('aria-checked') == 'true'
    click(page.get_by_text('Edit settings', exact=True))
    editor = page.get_by_role('region', name=re.compile(r'^Edit ".*"$'))
    editor.wait_for(state='visible', timeout=45000)
    if editor.count() != 1:
        raise Stop('Meeting settings editor is ambiguous')
    fields = editor.get_by_role('textbox', name='Please Input', exact=True)
    if fields.count() != 3:
        raise Stop('Meeting read-back detail inputs changed')
    name, slug = fields.nth(0).input_value(), fields.nth(1).input_value()
    for key, label in SECURITY.items():
        value = editor.get_by_role('switch', name=label, exact=True).get_attribute('aria-checked')
        if value != str(states[key]).lower():
            raise Stop('Meeting detail and edit security states disagree')
    # No inputs were changed. Return to the observed detail URL, avoiding the
    # mislabelled Cancel button and never interacting with the passcode input.
    page.goto(detail_url, wait_until='domcontentloaded', timeout=45000)
    assert_tenant(page, spec)
    return {'status':'PRESENT', 'source':'native My room and Edit settings after reload; captured 2026-11-08',
            'room_id':canonical, 'identity_source':'canonical_room_link',
            'location_id':spec['location_id'], 'name':name, 'slug':slug,
            'url':canonical, **states}


def validate_observation(observed, spec, *, allow_absent=False):
    if not isinstance(observed, dict) or observed.get('location_id') != spec['location_id'] or not observed.get('source'):
        raise Stop('Meeting read-back must be sourced and bound to the requested location')
    if observed.get('status') == 'ABSENT' and allow_absent:
        return None
    if observed.get('status') != 'PRESENT' or not observed.get('room_id'):
        raise Stop('Room presence is uncertain; reconcile before creating or updating')
    safe_room_url(observed.get('url'))
    if urlsplit(observed['url']).path.rstrip('/').rsplit('/', 1)[-1] != observed.get('slug'):
        raise Stop('Meeting room link and saved slug disagree')
    for key in ('name', 'slug', *SECURITY):
        if observed.get(key) != spec[key] or (key in SECURITY and type(observed.get(key)) is not bool):
            raise Stop('Meeting read-back differs from requested ' + key)
    # Never forward passcodes, raw HTML, transcripts or unrelated reader payload.
    result = {key: observed[key] for key in ('room_id', 'location_id', 'name', 'slug', 'url', *SECURITY)}
    result.update(status='PRESENT', source='persisted native Meeting Room read-back')
    if observed.get('identity_source') == 'canonical_room_link':
        result['identity_source'] = 'canonical_room_link'
    return result


# Explicit name for host integrations; both names use the same concrete reader.
read_room_browser = read_room


def _security(region, spec):
    for key, label in SECURITY.items():
        control = region.get_by_role('switch', name=label, exact=True)
        if control.count() != 1:
            raise Stop('Meeting security controls changed; capture required')
        current = control.get_attribute('aria-checked')
        if current not in ('true', 'false'):
            raise Stop('Meeting switch state is not exposed')
        expected = str(spec[key]).lower()
        if current != expected:
            click(control)
        wait_until(lambda: control.get_attribute('aria-checked') == expected, 'Meeting switch did not persist its editor state')


def create_room(page, inputs, *, read_room=None):
    """Idempotent native create, using an independent persisted-room reader.

    read_room(page, location_id) must read authoritative persisted state and
    return PRESENT (safe fields above), ABSENT, or an unknown status that stops.
    The host must not implement the reader from the intended request itself.
    """
    spec = validate_room(inputs)
    if read_room is None:
        reader = globals()['read_room']
        read_room = lambda current_page, location_id: reader(current_page, spec)
    if not callable(read_room):
        raise Stop('Native Meeting Room reader is required before creation')
    assert_tenant(page, spec)
    navigate(page, 'Meeting Room')
    before = read_room(page, spec['location_id'])
    existing = validate_observation(before, spec, allow_absent=True)
    if existing:
        return {'status':'ROOM_REUSED_VERIFIED', 'room':existing, 'meeting_started':False}
    if inputs.get('allow_creation') is not True:
        raise Stop('Room is absent; explicit creation input is required')
    create = page.get_by_role('region', name='Meeting Room for meetings, webinars and more', exact=True).get_by_role('button', name='Create room', exact=True)
    if create.count() != 1 or not create.is_visible():
        raise Stop('Meeting Room create screen changed; capture required')
    click(create)
    region = page.get_by_role('region', name='Create room', exact=True)
    fields = region.get_by_role('textbox', name='Please Input', exact=True)
    if fields.count() != 3:
        raise Stop('Meeting detail controls changed; capture required')
    fill(fields.nth(0), spec['name'])
    fill(fields.nth(1), spec['slug'])
    _security(region, spec)
    submit = region.get_by_role('button', name='Create room', exact=True)
    wait_until(lambda: submit.is_enabled(), 'Room link unavailable or required details invalid')
    click(submit)
    region.wait_for(state='hidden', timeout=45000)
    assert_tenant(page, spec)
    # The reader must reopen/read persisted state. A dismissed modal is not proof.
    observed = validate_observation(read_room(page, spec['location_id']), spec)
    return {'status':'ROOM_CREATED_VERIFIED', 'room':observed, 'meeting_started':False}


def update_room(page, inputs, *, expected_room_id, reader=None):
    """Update the captured native room editor and independently reload it.

    expected_room_id must come from read_room's canonical identity, preventing
    an update from being applied to a different owner's room after navigation.
    """
    spec = validate_room(inputs)
    reader = reader or read_room
    assert_tenant(page, spec)
    navigate(page, 'Meeting Room')
    before = reader(page, spec)
    if not before.get('source') or before.get('status') != 'PRESENT' or before.get('location_id') != spec['location_id'] or before.get('room_id') != expected_room_id:
        raise Stop('Requested existing room identity is not present; no update performed')
    click(page.get_by_text('Edit settings', exact=True))
    region = page.get_by_role('region', name=re.compile(r'^Edit ".*"$'))
    region.wait_for(state='visible', timeout=45000)
    fields = region.get_by_role('textbox', name='Please Input', exact=True)
    if region.count() != 1 or fields.count() != 3:
        raise Stop('Meeting edit controls changed')
    fill(fields.nth(0), spec['name'])
    fill(fields.nth(1), spec['slug'])
    _security(region, spec)
    submit = region.get_by_role('button', name='Save changes', exact=True)
    wait_until(lambda: submit.is_enabled(), 'Meeting settings are invalid or room link unavailable')
    click(submit)
    region.wait_for(state='hidden', timeout=45000)
    assert_tenant(page, spec)
    result = validate_observation(reader(page, spec), spec)
    return {'status':'ROOM_UPDATED_VERIFIED', 'room':result, 'meeting_started':False,
            'previous_room_identity':expected_room_id}


def permanent_link_patch(calendar, *, location_id, room, member_id=None, replace_index=None):
    """Prepare only the documented location field, preserving other choices.

    Existing meeting locations are never silently replaced: append by default;
    replace_index explicitly identifies an owner-requested replacement. Multi-user
    class/collective constraints are enforced before the API dispatcher is called.
    """
    if not isinstance(calendar, dict) or calendar.get('locationId') != location_id or not calendar.get('id'):
        raise Stop('Calendar read-back is not bound to the requested location')
    if not isinstance(room, dict) or room.get('location_id') != location_id or room.get('status') != 'PRESENT' or not room.get('room_id') or not room.get('source'):
        raise Stop('A sourced, persisted room receipt for this location is required')
    link = safe_room_url(room.get('url'))
    patch = {}
    is_event = calendar.get('calendarType') == 'event'
    if is_event:
        if member_id:
            raise Stop('Event calendars do not select a team member')
        target = deepcopy(calendar.get('locationConfigurations', []))
    else:
        members = deepcopy(calendar.get('teamMembers', []))
        if not member_id or len([m for m in members if m.get('userId') == member_id]) != 1:
            raise Stop('Select one existing calendar team member explicitly')
        selected = next(m for m in members if m.get('userId') == member_id)
        target = deepcopy(selected.get('locationConfigurations', []))
    if not isinstance(target, list) or any(not isinstance(x, dict) or not x.get('kind') for x in target):
        raise Stop('Existing location configuration is malformed')
    if any(x.get('kind') == 'custom' and x.get('location') == link for x in target):
        return {}, {'mode':'permanent_link', 'already_configured':True, 'room_id':room['room_id']}
    new = {'kind':'custom', 'location':link}
    if replace_index is None:
        target.append(new)
    elif type(replace_index) is int and 0 <= replace_index < len(target):
        target[replace_index] = new
    else:
        raise Stop('Replacement index must identify an existing meeting location')
    if not is_event and (len(members) > 1 or calendar.get('calendarType') in ('class_booking', 'collective')) and len(target) > 1:
        raise Stop('This calendar supports one location per team member; request an explicit replacement')
    if is_event:
        patch['locationConfigurations'] = target
    else:
        selected['locationConfigurations'] = target
        patch['teamMembers'] = members
    return patch, {'mode':'permanent_link', 'already_configured':False, 'room_id':room['room_id']}


def integrate_calendar(api, *, location_id, calendar_id, room, member_id=None, replace_index=None):
    """Run GET -> minimal PUT -> independent GET through a vetted dispatcher.

    api(operation_id, location_id=..., path_params=..., body=...) is the host's
    existing capability-gated dispatcher, not a raw requests session. Missing
    calendars.update in that registry must remain a refusal at the host boundary.
    """
    if not callable(api) or not re.fullmatch(r'[A-Za-z0-9_-]+', str(calendar_id)):
        raise Stop('A vetted calendar dispatcher and exact calendar ID are required')
    params = {'calendarId':calendar_id}
    def get():
        result = api('calendars.get', location_id=location_id, path_params=params)
        calendar = result.get('calendar') if isinstance(result, dict) else None
        if not isinstance(calendar, dict) or calendar.get('id') != calendar_id:
            raise Stop('Calendar API read-back identity mismatch')
        return calendar
    current = get()
    patch, receipt = permanent_link_patch(current, location_id=location_id, room=room, member_id=member_id, replace_index=replace_index)
    if patch:
        api('calendars.update', location_id=location_id, path_params=params, body=patch)
        saved = get()
        after, _ = permanent_link_patch(saved, location_id=location_id, room=room, member_id=member_id, replace_index=replace_index)
        if after:
            raise Stop('Permanent Meeting Room link did not persist on the calendar')
    return {'status':'CALENDAR_PERMANENT_ROOM_LINK_VERIFIED', 'calendar_id':calendar_id, 'location_id':location_id, **receipt, 'dynamic_room_generation':False}
