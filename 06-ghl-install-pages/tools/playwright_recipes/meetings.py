#!/usr/bin/env python3
"""Meeting Room setup and permanent-link integration, without new auth paths.

Create-dialog selectors were captured in Convert & Flow on 2026-11-08.
The native persisted-room reader verifies absence, identity and saved settings;
they cannot be inferred from a click. No call is started and no co-host assigned.

Official contracts checked 2026-11-08:
https://help.gohighlevel.com/support/solutions/articles/155000009149-meeting-room-in-highlevel-overview
https://marketplace.gohighlevel.com/docs/ghl/calendars/update-calendar/
https://marketplace.gohighlevel.com/docs/ghl/calendars/get-calendar/

Static room-link integration below is NOT native per-appointment room generation.
The canonical public registry includes calendars.get and calendars.update. Its
dispatcher remains default-deny until a fresh location/version/scope capability
receipt permits the exact operations. The delivery adapter preserves that gate
and the existing Skill 44 write checks; this module supplies no new credentials,
transport, capability override or unrestricted calendar write path.

Calendar integration installs a permanent room link only. A clean canonical URL
requires manual passcode entry; a separately supplied private Invite URL embeds
the passcode in memory and the API payload, with only safe flags/hash in receipts.
Unique per-appointment room creation is a distinct native workflow and is never
inferred from this static custom-location configuration.
"""
from copy import deepcopy
import hashlib
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click, fill, navigate, wait_until
else:
    from skill6_playwright import Stop, assert_tenant, click, fill, navigate, wait_until


SECURITY = {'waiting_room':'Waiting room', 'guest_users':'Allow guest users', 'open_room':'Open room'}


def validate_room(spec):
    if not isinstance(spec, dict):
        raise Stop('Meeting Room inputs must be an object')
    canonical = {'location_id', 'location_name', 'start_url'}
    allowed = canonical | {'name', 'slug', *SECURITY, 'allow_creation',
                           'expected_room_id', 'id', 'action', '_context'}
    unsupported = set(spec) - allowed
    if unsupported:
        raise Stop('Unsupported Meeting Room controls require a captured implementation: ' + ', '.join(sorted(unsupported)))
    if 'allow_creation' in spec and type(spec['allow_creation']) is not bool:
        raise Stop('Meeting allow_creation must be a real boolean')
    if 'expected_room_id' in spec and (not isinstance(spec['expected_room_id'], str) or not spec['expected_room_id'].strip()):
        raise Stop('Meeting update requires a nonempty existing room identity')
    if 'action' in spec and spec['action'] != 'meeting':
        raise Stop('Unexpected Meeting Room runner action')
    if 'id' in spec and (not isinstance(spec['id'], str) or not re.fullmatch(r'[a-z0-9_-]+', spec['id'])):
        raise Stop('Invalid Meeting Room runner step identity')
    if '_context' in spec:
        context = spec['_context']
        if not isinstance(context, dict) or set(context) != canonical or any(context[key] != spec.get(key) for key in canonical):
            raise Stop('Meeting Room runner context must match the canonical location')
    for key in ('location_id', 'location_name', 'start_url', 'name', 'slug'):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise Stop('Meeting Room requires ' + key)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', spec['location_id']):
        raise Stop('Invalid meeting location ID')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', spec['slug']):
        raise Stop('Invalid meeting room slug')
    if any(type(spec.get(key)) is not bool for key in SECURITY):
        raise Stop('Specify every meeting security choice as a real boolean')
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
    if (not isinstance(expected_room_id, str) or not expected_room_id.strip()
            or ('expected_room_id' in spec and spec['expected_room_id'] != expected_room_id)):
        raise Stop('Meeting update requires one consistent existing room identity')
    reader = reader or read_room
    assert_tenant(page, spec)
    navigate(page, 'Meeting Room')
    before = reader(page, spec)
    if (not isinstance(before, dict) or not before.get('source')
            or before.get('status') != 'PRESENT' or before.get('location_id') != spec['location_id']
            or before.get('room_id') != expected_room_id):
        raise Stop('Requested existing room identity is not present; no update performed')
    # Validate the persisted previous state independently of the requested new
    # name/security values. A matching opaque ID alone is not a room inventory.
    previous = {**spec, **{key:before.get(key) for key in ('name','slug',*SECURITY)}}
    validate_room(previous)
    validate_observation(before, previous)
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


def _join_link(canonical, private_invite_url=None):
    """Keep a supplied private invite in memory; return only safe metadata.

    The public/safe canonical URL identifies the room. It does not embed the
    generated passcode, so it must not be described as an equivalent join link.
    """
    canonical = safe_room_url(canonical)
    metadata = {'credential_link_supplied':False, 'embedded_passcode':False,
                'passcode_required':True, 'manual_passcode_entry_required':True,
                'join_link_mode':'canonical_without_embedded_passcode'}
    if private_invite_url is None:
        return canonical, metadata
    try:
        expected, private = urlsplit(canonical), urlsplit(private_invite_url)
        pairs = parse_qsl(private.query, keep_blank_values=True, strict_parsing=True)
    except (TypeError, ValueError):
        raise Stop('Private room invite format is invalid') from None
    if (private.scheme, private.netloc, private.path) != (expected.scheme, expected.netloc, expected.path) or private.fragment or private.username or private.password:
        raise Stop('Private room invite must identify the same verified canonical room')
    if len(pairs) != 1 or pairs[0][0] != 'pwd' or not pairs[0][1]:
        raise Stop('Private room invite may contain one nonempty pwd parameter only')
    metadata.update(credential_link_supplied=True, embedded_passcode=True,
                    manual_passcode_entry_required=False,
                    join_link_mode='private_invite_with_embedded_passcode',
                    invite_url_sha256=hashlib.sha256(private_invite_url.encode()).hexdigest())
    return private_invite_url, metadata


def _put_locations(locations):
    """Only documented writable calendar-location fields, never read-only IDs."""
    allowed_kinds = {'custom','zoom_conference','google_conference','inbound_call',
                     'outbound_call','physical','booker','ms_teams_conference'}
    if not isinstance(locations, list):
        raise Stop('Existing calendar locations must be a list')
    out = []
    for value in locations:
        if not isinstance(value, dict) or value.get('kind') not in allowed_kinds:
            raise Stop('Existing calendar location kind is not supported by the documented update contract')
        clean = {'kind':value['kind']}
        if 'location' in value:
            if not isinstance(value['location'], str):
                raise Stop('Existing calendar location is malformed')
            clean['location'] = value['location']
        out.append(clean)
    return out


def _put_members(members):
    if not isinstance(members, list):
        raise Stop('Existing calendar team members must be a list')
    out = []
    seen = set()
    for member in members:
        if not isinstance(member, dict) or not isinstance(member.get('userId'), str) or not member['userId']:
            raise Stop('Existing calendar team member is malformed')
        if member['userId'] in seen:
            raise Stop('Existing calendar team member identities are duplicated')
        seen.add(member['userId'])
        if member.get('meetingLocation') and not member.get('locationConfigurations'):
            raise Stop('Migrate legacy member meeting locations before this calendar update')
        clean = {'userId':member['userId']}
        for key in ('priority','isPrimary'):
            if key in member:
                clean[key] = member[key]
        if 'locationConfigurations' in member:
            clean['locationConfigurations'] = _put_locations(member['locationConfigurations'])
        out.append(clean)
    return out


def permanent_link_patch(calendar, *, location_id, room, member_id=None, replace_index=None, private_invite_url=None):
    """Prepare only the documented location field, preserving other choices.

    Existing meeting locations are never silently replaced: append by default;
    replace_index explicitly identifies an owner-requested replacement. Multi-user
    class/collective constraints are enforced before the API dispatcher is called.
    """
    if not isinstance(calendar, dict) or calendar.get('locationId') != location_id or not calendar.get('id'):
        raise Stop('Calendar read-back is not bound to the requested location')
    if not isinstance(room, dict) or room.get('location_id') != location_id or room.get('status') != 'PRESENT' or not room.get('room_id') or not room.get('source'):
        raise Stop('A sourced, persisted room receipt for this location is required')
    canonical = safe_room_url(room.get('url'))
    link, join_metadata = _join_link(canonical, private_invite_url)
    patch = {}
    is_event = calendar.get('calendarType') == 'event'
    if is_event:
        if member_id:
            raise Stop('Event calendars do not select a team member')
        target = deepcopy(calendar.get('locationConfigurations', []))
        if calendar.get('meetingLocation') and not target:
            raise Stop('Migrate the legacy calendar meeting location before this update')
    else:
        members = deepcopy(calendar.get('teamMembers', []))
        if not isinstance(members, list):
            raise Stop('Calendar team members are malformed')
        _put_members(members)  # Validate original legacy state before mutation.
        if not member_id or len([m for m in members if m.get('userId') == member_id]) != 1:
            raise Stop('Select one existing calendar team member explicitly')
        selected = next(m for m in members if m.get('userId') == member_id)
        target = deepcopy(selected.get('locationConfigurations', []))
    if not isinstance(target, list) or any(not isinstance(x, dict) or not x.get('kind') for x in target):
        raise Stop('Existing location configuration is malformed')
    # Validate all preserved rows even when the requested link already exists.
    # An explicit replacement binds one slot, rather than any matching sibling.
    _put_locations(target)
    if replace_index is not None and (type(replace_index) is not int or not 0 <= replace_index < len(target)):
        raise Stop('Replacement index must identify an existing meeting location')
    candidates = target if replace_index is None else [target[replace_index]]
    if any(x.get('kind') == 'custom' and x.get('location') == link for x in candidates):
        return {}, {'mode':'permanent_link', 'already_configured':True, 'room_id':room['room_id'], **join_metadata}
    if replace_index is not None and any(x.get('kind') == 'custom' and x.get('location') == link
                                         for index,x in enumerate(target) if index != replace_index):
        raise Stop('Requested room link already belongs to another location slot; reconcile before replacement')
    if replace_index is None:
        # Do not duplicate the same room or silently downgrade an authenticated
        # invite to a clean URL (or replace credentials) during a later run.
        for existing in target:
            if existing.get('kind') != 'custom' or not isinstance(existing.get('location'), str):
                continue
            parsed = urlsplit(existing['location'])
            if urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', '')) == canonical:
                raise Stop('This room already has a different join-link mode; select an explicit replacement')
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
        patch['locationConfigurations'] = _put_locations(target)
    else:
        selected['locationConfigurations'] = target
        patch['teamMembers'] = _put_members(members)
    return patch, {'mode':'permanent_link', 'already_configured':False, 'room_id':room['room_id'], **join_metadata}


def integrate_calendar(api, *, location_id, calendar_id, room, member_id=None, replace_index=None, private_invite_url=None):
    """Run GET -> minimal PUT -> independent GET through a vetted dispatcher.

    api(operation_id, location_id=..., path_params=..., body=...) is the host's
    existing capability-gated dispatcher, not a raw requests session. The
    canonical calendars.get/update operations still require the host's fresh
    location/version/scope capability receipt; disabled or unverified operations
    remain refusals. This installs a permanent link, never a dynamic room per
    appointment. A private_invite_url is never included in the returned receipt.
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
    patch, receipt = permanent_link_patch(current, location_id=location_id, room=room, member_id=member_id, replace_index=replace_index, private_invite_url=private_invite_url)
    if patch:
        api('calendars.update', location_id=location_id, path_params=params, body=patch)
        saved = get()
        # Checking only that the room appears somewhere would accept a PUT that
        # silently removed another location/member or moved the requested slot.
        # Compare the entire documented writable projection of our minimal PUT.
        for key, expected in patch.items():
            actual = (_put_locations(saved.get(key)) if key == 'locationConfigurations'
                      else _put_members(saved.get(key)))
            if actual != expected:
                raise Stop('Calendar read-back changed a requested or preserved meeting-location setting')
        after, _ = permanent_link_patch(saved, location_id=location_id, room=room, member_id=member_id, replace_index=replace_index, private_invite_url=private_invite_url)
        if after:
            raise Stop('Permanent Meeting Room link did not persist on the calendar')
    return {'status':'CALENDAR_PERMANENT_ROOM_LINK_VERIFIED', 'calendar_id':calendar_id, 'location_id':location_id, **receipt, 'dynamic_room_generation':False}
