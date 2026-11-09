"""Read-only native co-host inventory and candidate preflight.

Captured November 9, 2026: existing room edit, co-host rows, Add co-host
dialog and exact name/email candidate identities. Assignment, removal and
save behavior remain uncaptured and are deliberately not implemented here.
No returned preflight status is a completed meeting operation.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

if __package__:
    from . import meetings
    from .skill6_playwright import Stop, assert_tenant, click, fill, navigate, wait_until
else:
    import meetings
    from skill6_playwright import Stop, assert_tenant, click, fill, navigate, wait_until


_EMAIL = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')


def _roster(value):
    if not isinstance(value, list):
        raise Stop('Co-host roster must be an explicit complete list')
    identities = []
    for person in value:
        if (not isinstance(person, dict) or set(person) != {'name', 'email'}
                or not isinstance(person['name'], str) or not person['name'].strip()
                or person['name'] != person['name'].strip() or len(person['name']) > 256
                or any(ord(char) < 32 for char in person['name'])
                or not isinstance(person['email'], str) or len(person['email']) > 320
                or not _EMAIL.fullmatch(person['email'])):
            raise Stop('Each co-host requires exact inventoried name and email')
        # Email case variants are the same account identity, never two people.
        identity = person['email'].casefold()
        if identity in identities:
            raise Stop('Co-host email identities must be unique')
        identities.append(identity)
    return deepcopy(value)


def validate_inputs(inputs):
    if not isinstance(inputs, dict):
        raise Stop('Co-host preflight inputs must be an object')
    spec = meetings.validate_room({key:value for key,value in inputs.items() if key != 'cohosts'})
    if spec.get('allow_creation') is not False:
        raise Stop('Co-host preflight is restricted to an existing room')
    room_id = meetings.safe_room_url(spec.get('expected_room_id'))
    if urlsplit(room_id).path.rstrip('/').rsplit('/', 1)[-1] != spec['slug']:
        raise Stop('Co-host expected room link and slug disagree')
    configuration = inputs.get('cohosts')
    if not isinstance(configuration, dict) or set(configuration) != {'expected', 'desired'}:
        raise Stop('Co-host preflight requires complete expected and desired rosters')
    expected, desired = _roster(configuration['expected']), _roster(configuration['desired'])
    # A name change on an occupied email is not a second candidate. The owner
    # must first reconcile the directory identity rather than silently rename.
    known = {person['email'].casefold():person for person in expected}
    for person in desired:
        if person['email'].casefold() in known and known[person['email'].casefold()] != person:
            raise Stop('An existing co-host email has conflicting name/case identity')
    return {**spec, 'cohosts':{'expected':expected, 'desired':desired}}


def configuration_hash(inputs):
    data = validate_inputs(inputs)
    bound = {key:data[key] for key in ('location_id','expected_room_id','name','slug',
                                      *meetings.SECURITY,'cohosts')}
    return hashlib.sha256(json.dumps(bound, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _one(control, reason):
    if control.count() != 1 or not control.is_visible():
        raise Stop(reason)
    return control


def _same_roster(first, second):
    # Native ordering does not grant access; compare complete exact identities.
    return sorted(first, key=lambda person:person['email']) == sorted(second, key=lambda person:person['email'])


def read_roster(editor):
    card = _one(editor.locator('#create-room-members-card'), 'Native co-host card changed')
    rows = card.locator('.pr-members__rows > div')
    roster = []
    for index in range(rows.count()):
        row = rows.nth(index)
        # The remove button contains another hr-text-lg paragraph. The captured
        # medium-weight name class distinguishes it from that semibold label.
        name = _one(row.locator('p.hr-text-lg.hr-text-medium'),
                    'Native co-host name identity changed').inner_text().strip()
        email = _one(row.locator('p.hr-text-md'), 'Native co-host email identity changed').inner_text().strip()
        _one(row.get_by_text('Co-host', exact=True), 'Native co-host role changed')
        remove = _one(row.get_by_role('button', name='Delete', exact=True),
                      'Native co-host removal control is ambiguous')
        if row.get_by_role('button').count() != 1 or not remove.is_enabled():
            raise Stop('Native co-host row control inventory changed')
        roster.append({'name':name, 'email':email})
    return _roster(roster)


def _editor(page, data):
    actual = urlsplit(page.url)
    start = urlsplit(data['start_url'])
    if ((actual.scheme,actual.netloc) != (start.scheme,start.netloc)
            or actual.path != '/v2/location/' + data['location_id'] + '/meetings/personal-room/edit'
            or actual.query or actual.fragment):
        raise Stop('Co-host editor differs from the requested native location and origin')
    assert_tenant(page, data)
    editor = _one(page.get_by_role('region', name='Edit "' + data['name'] + '"', exact=True),
                  'Native room edit region changed')
    fields = editor.get_by_role('textbox', name='Please Input', exact=True)
    if (fields.count() != 3 or fields.nth(0).input_value() != data['name']
            or fields.nth(1).input_value() != data['slug']):
        raise Stop('Native room name/slug inventory changed before co-host preflight')
    for key,label in meetings.SECURITY.items():
        control = _one(editor.get_by_role('switch', name=label, exact=True),
                       'Native room security inventory changed')
        if control.get_attribute('aria-checked') != str(data[key]).lower():
            raise Stop('Native room security differs from the expected unchanged settings')
    return editor


def _candidate(dialog, person):
    candidates = dialog.locator('.pr-members__menu-item')
    matches = []
    for index in range(candidates.count()):
        button = candidates.nth(index)
        content = button.locator('.pr-members__candidate-content p')
        if content.count() != 2:
            raise Stop('Native co-host candidate identity structure changed')
        name, email = (content.nth(i).inner_text().strip() for i in range(2))
        if name == person['name'] and email == person['email']:
            matches.append(button)
    if len(matches) != 1:
        return None
    return _one(matches[0], 'Native co-host candidate is hidden or ambiguous')


def prepare(page, inputs):
    """Independently bind the room, roster and candidate plan without writes.

    Opens native edit and searches the directory but never selects a candidate,
    clicks Delete or Save, starts a meeting, or changes access. If the Add
    dialog is opened it remains open; its closing control is not yet captured.
    The shared runner must not advertise this as an executable writer.
    """
    data = validate_inputs(inputs)
    assert_tenant(page, data)
    navigate(page, 'Meeting Room')
    observed = meetings.read_room(page, {key:value for key,value in data.items() if key != 'cohosts'})
    meetings.validate_observation(observed, data)
    if observed['room_id'] != data['expected_room_id']:
        raise Stop('Co-host preflight found a different existing room identity')
    click(page.get_by_text('Edit settings', exact=True))
    editor = _editor(page, data)
    before = read_roster(editor)
    expected, desired = data['cohosts']['expected'], data['cohosts']['desired']
    if not _same_roster(before, expected):
        raise Stop('Native co-host roster differs from the complete expected inventory')
    additions = [person for person in desired if person not in before]
    removals = [person for person in before if person not in desired]
    if additions:
        card = editor.locator('#create-room-members-card')
        trigger = _one(card.locator('.pr-members__add-trigger--link'), 'Native Add co-host trigger changed')
        click(trigger)
        dialog = page.get_by_role('dialog').filter(
            has=page.locator('#personal-room-co-host-search'))
        _one(dialog, 'Native Add co-host dialog is ambiguous')
        if dialog.get_attribute('aria-labelledby') != 'personal-room-co-hosts-1-title':
            raise Stop('Native Add co-host dialog identity changed')
        _one(dialog.get_by_text('Add co-host', exact=True), 'Native Add co-host title changed')
        search_wrapper = _one(dialog.locator('#personal-room-co-host-search'),
                              'Native co-host directory search wrapper changed')
        search = _one(search_wrapper.get_by_role('textbox', name='Search users', exact=True),
                      'Native co-host directory search input changed')
        if search.get_attribute('placeholder') != 'Search users':
            raise Stop('Native co-host directory placeholder changed')
        for person in additions:
            fill(search, person['email'])
            wait_until(lambda: _candidate(dialog, person) is not None,
                       'Exact name/email co-host candidate is absent or ambiguous')
            if not _candidate(dialog, person).is_enabled():
                raise Stop('Exact co-host candidate is not selectable')
    # Directory inspection must not have assigned anyone as a side effect.
    if not _same_roster(read_roster(editor), before):
        raise Stop('Read-only co-host inspection unexpectedly changed the native roster')
    assert_tenant(page, data)
    return {'status':'COHOST_PREFLIGHT_ONLY', 'location_id':data['location_id'],
            'room_id':data['expected_room_id'], 'configuration_sha256':configuration_hash(data),
            'existing_count':len(before), 'addition_count':len(additions), 'removal_count':len(removals),
            'mutation_attempted':False, 'assignment_supported':False,
            'independent_readback':'PENDING_ASSIGNMENT_CAPTURE',
            'verification_required':'Capture candidate selection/removal/save and persisted roster before enabling a writer'}
