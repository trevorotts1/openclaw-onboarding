"""Exact native co-host inventory, preflight and guarded roster reconciliation.

Captured November 9, 2026: existing room editor, complete co-host rows,
Add co-host dialog, exact selectable name/email candidates, row Delete and
Save changes. The writer verifies staged state after each known control and
stops on an unexpected native confirmation/dialog shape. Native assignment
and its notification behavior have not been exercised as acceptance proof.
The parent editor runner owns intent journals and the tenant writer lease.
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
    bound = {key:data[key] for key in ('location_id','location_name','start_url','expected_room_id','name','slug',
                                      *meetings.SECURITY,'cohosts')}
    return hashlib.sha256(json.dumps(bound, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _one(control, reason):
    if control.count() != 1 or not control.is_visible():
        raise Stop(reason)
    return control


def _same_roster(first, second):
    # Native ordering does not grant access; compare complete exact identities.
    return sorted(first, key=lambda person:person['email']) == sorted(second, key=lambda person:person['email'])


def read_roster(editor, *, page=None, data=None):
    card = _one(editor.locator('#create-room-members-card'), 'Native co-host card changed')
    rows = card.locator('.pr-members__rows > div')
    count = rows.count()
    if count == 0:
        return _ready_empty_roster(page, data)
    roster = []
    for index in range(count):
        if rows.count() != count:
            raise Stop('Native co-host roster changed during its complete inventory')
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
    if rows.count() != count:
        raise Stop('Native co-host roster changed during its complete inventory')
    return _roster(roster)


def _ready_empty_roster(page, data):
    """Recognize the November 11 saved-empty card after exact owner load.

    Missing rows alone remain unknown. The captured empty profile is one
    complete card containing only its Co-hosts heading and enabled Add button,
    with no rows container, busy/error state or extra controls. No private
    Invite URL or passcode input is consulted by this reader.
    """
    if page is None or data is None:
        raise Stop('Native loaded-empty co-host profile needs exact saved-room context; zero rows remain unknown')
    try:page.wait_for_load_state('networkidle',timeout=45000)
    except Exception:
        raise Stop('Native co-host load did not settle; empty roster remains unknown') from None
    editor=_editor(page,data)
    if editor.get_attribute('aria-busy')=='true':
        raise Stop('Native co-host editor is still busy')
    unsafe=editor.locator('[aria-busy="true"], [role="progressbar"], [role="alert"], [aria-invalid="true"], .n-spin-body, .n-skeleton')
    if unsafe.count():raise Stop('Native co-host editor exposes loading or error state')
    card=_one(editor.locator('#create-room-members-card'),'Native loaded-empty co-host card changed')
    body=_one(card.locator('.pr-members__card'),'Native loaded-empty co-host card body changed')
    _one(card.get_by_role('heading',name='Co-hosts',exact=True),'Native loaded-empty co-host heading changed')
    add=_one(card.locator('.pr-members__add-trigger--link'),'Native loaded-empty co-host Add changed')
    if (card.get_attribute('aria-busy')=='true' or body.locator(':scope > div').count()!=1
            or card.locator('.pr-members__rows').count()!=0
            or card.locator('.pr-members__rows > div').count()!=0
            or card.get_by_role('button').count()!=1 or not add.is_enabled()
            or add.inner_text().strip()!='Add' or add.get_attribute('type')!='button'
            or add.get_attribute('aria-haspopup')!='dialog'
            or add.get_attribute('aria-expanded') not in ('true','false')
            or not re.fullmatch(r'personal-room-co-hosts-[1-9][0-9]*',add.get_attribute('aria-controls') or '')):
        raise Stop('Native loaded-empty co-host card differs from the complete captured profile')
    if card.locator('.pr-members__rows > div').count()!=0:
        raise Stop('Native loaded-empty co-host inventory changed during its complete read')
    return []


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
    before = read_roster(editor, page=page, data=data)
    expected, desired = data['cohosts']['expected'], data['cohosts']['desired']
    if not _same_roster(before, expected):
        raise Stop('Native co-host roster differs from the complete expected inventory')
    additions = [person for person in desired if person not in before]
    removals = [person for person in before if person not in desired]
    if additions:
        dialog, search = _open_directory(page, editor)
        for person in additions:
            fill(search, person['email'])
            wait_until(lambda: _candidate(dialog, person) is not None,
                       'Exact name/email co-host candidate is absent or ambiguous')
            if not _candidate(dialog, person).is_enabled():
                raise Stop('Exact co-host candidate is not selectable')
    # Directory inspection must not have assigned anyone as a side effect.
    if not _same_roster(read_roster(editor, page=page, data=data), before):
        raise Stop('Read-only co-host inspection unexpectedly changed the native roster')
    assert_tenant(page, data)
    return {'status':'COHOST_PREFLIGHT_ONLY', 'location_id':data['location_id'],
            'room_id':data['expected_room_id'], 'configuration_sha256':configuration_hash(data),
            'existing_count':len(before), 'addition_count':len(additions), 'removal_count':len(removals),
            'mutation_attempted':False, 'assignment_supported':False,
            'independent_readback':'PENDING_ASSIGNMENT_CAPTURE',
            'verification_required':'Capture candidate selection/removal/save and persisted roster before enabling a writer'}


def validate_write_inputs(inputs):
    """Require an explicit acknowledgment bound to one complete roster plan.

    This flag records an already approved access change; it is not a substitute
    for the calling host obtaining that approval from the owner. The runtime
    must never fabricate the acknowledgment or infer it from a room update.
    """
    if isinstance(inputs,dict) and inputs.get('allow_creation') is True:
        from playwright_recipes.meeting_first_cohosts import validate_inputs as validate_creation
        return validate_creation(inputs)
    if not isinstance(inputs, dict) or not isinstance(inputs.get('cohosts'), dict):
        raise Stop('Co-host writer requires one complete approved roster plan')
    configuration = inputs['cohosts']
    if (set(configuration) != {'expected', 'desired', 'access_change_acknowledged'}
            or configuration['access_change_acknowledged'] is not True):
        raise Stop('Co-host access changes require explicit scoped acknowledgment')
    data = validate_inputs({**inputs, 'cohosts':{
        'expected':configuration['expected'], 'desired':configuration['desired']}})
    data['cohosts']['access_change_acknowledged'] = True
    return data


def write_configuration_hash(inputs):
    data = validate_write_inputs(inputs)
    if data.get('allow_creation') is True:
        from playwright_recipes.meeting_first_cohosts import configuration_hash
        return configuration_hash(data)
    bound = {key:data[key] for key in ('location_id', 'location_name', 'start_url',
        'expected_room_id', 'name', 'slug', *meetings.SECURITY, 'cohosts')}
    return hashlib.sha256(json.dumps(bound, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _read_inputs(data):
    return {key:value for key,value in data.items() if key != 'cohosts'}


def _open_existing(page, data):
    """Reopen persisted room identity and editor before trusting any row."""
    assert_tenant(page, data)
    navigate(page, 'Meeting Room')
    observed = meetings.read_room(page, _read_inputs(data))
    meetings.validate_observation(observed, data)
    if observed['room_id'] != data['expected_room_id']:
        raise Stop('Co-host writer found a different existing room identity')
    detail_url = page.url
    click(page.get_by_text('Edit settings', exact=True))
    editor = _editor(page, data)
    return editor, detail_url


def _open_directory(page, editor):
    card = _one(editor.locator('#create-room-members-card'), 'Native co-host card changed')
    trigger=_one(card.locator('.pr-members__add-trigger--link'), 'Native Add co-host trigger changed')
    owner=trigger.get_attribute('aria-controls')
    if not isinstance(owner,str) or not re.fullmatch(r'personal-room-co-hosts-[1-9][0-9]*',owner):
        raise Stop('Native Add co-host dialog owner identity changed')
    click(trigger)
    dialog = _one(page.get_by_role('dialog').filter(
        has=page.locator('#personal-room-co-host-search')), 'Native Add co-host dialog is ambiguous')
    if dialog.get_attribute('aria-labelledby') != owner+'-title':
        raise Stop('Native Add co-host dialog identity changed')
    _one(dialog.get_by_text('Add co-host', exact=True), 'Native Add co-host title changed')
    wrapper = _one(dialog.locator('#personal-room-co-host-search'), 'Native co-host search wrapper changed')
    search = _one(wrapper.get_by_role('textbox', name='Search users', exact=True),
                  'Native co-host search input changed')
    if search.get_attribute('placeholder') != 'Search users':
        raise Stop('Native co-host search placeholder changed')
    return dialog, search


def _find_candidate(dialog, search, person):
    fill(search, person['email'])
    wait_until(lambda: _candidate(dialog, person) is not None,
               'Exact name/email co-host candidate is absent or ambiguous')
    candidate = _candidate(dialog, person)
    if candidate is None or not candidate.is_enabled():
        raise Stop('Exact co-host candidate is not selectable')
    return candidate


def _remove_control(editor, person):
    # read_roster first verifies every row's known shape, role and uniqueness.
    read_roster(editor)
    rows = editor.locator('#create-room-members-card').locator('.pr-members__rows > div')
    matched = []
    for index in range(rows.count()):
        row = rows.nth(index)
        name = row.locator('p.hr-text-lg.hr-text-medium').inner_text().strip()
        email = row.locator('p.hr-text-md').inner_text().strip()
        if (name, email) == (person['name'], person['email']):
            matched.append(row.get_by_role('button', name='Delete', exact=True))
    if len(matched) != 1:
        raise Stop('Requested co-host removal identity is absent or ambiguous')
    return _one(matched[0], 'Exact co-host removal control changed')


def _staged_roster(page, data, expected):
    editor = _editor(page, data)
    roster = read_roster(editor, page=page, data=data)
    if not _same_roster(roster, expected):
        raise Stop('Native staged co-host roster differs from the complete expected state')
    return editor


def verify_completed(page,inputs,receipt):
    """Read the current exact persisted roster; never repeat access writes."""
    data=validate_write_inputs(inputs)
    if data.get('allow_creation') is True:
        from playwright_recipes.meeting_first_cohosts import verify_completed as verify_creation
        return verify_creation(page,data,receipt)
    if (not isinstance(receipt,dict) or receipt.get('location_id')!=data['location_id']
            or receipt.get('room_id')!=data['expected_room_id']
            or receipt.get('configuration_sha256')!=write_configuration_hash(data)
            or type(receipt.get('cohost_count')) is not int
            or receipt['cohost_count']!=len(data['cohosts']['desired'])):
        raise Stop('Completed cohost receipt is unbound; current roster was not read')
    editor,detail=_open_existing(page,data)
    current=read_roster(editor,page=page,data=data)
    if not _same_roster(current,data['cohosts']['desired']):
        raise Stop('Completed cohost roster changed; access writes were not repeated')
    page.goto(detail,wait_until='domcontentloaded',timeout=45000)
    assert_tenant(page,data)
    return deepcopy(receipt)


def configure(page, inputs):
    """Reconcile one approved existing-room roster, then independently reopen.

    All candidate identities are preflighted before the first access mutation.
    The parent runner must record intent before calling this function. A stop
    after selection/removal/save is uncertain and must be reconciled by reading
    the same room; never retry the writer automatically. No call is started.
    """
    data = validate_write_inputs(inputs)
    if data.get('allow_creation') is True:
        from playwright_recipes.meeting_first_cohosts import configure as create_with_cohosts
        return create_with_cohosts(page,data)
    editor, detail_url = _open_existing(page, data)
    expected = data['cohosts']['expected']
    desired = data['cohosts']['desired']
    before = read_roster(editor, page=page, data=data)
    if not _same_roster(before, expected):
        raise Stop('Native co-host roster differs from the complete expected inventory')
    additions = [person for person in desired if person not in before]
    removals = [person for person in before if person not in desired]
    if additions:
        dialog, search = _open_directory(page, editor)
        for person in additions:
            _find_candidate(dialog, search, person)
        if not _same_roster(read_roster(editor, page=page, data=data), before):
            raise Stop('Read-only co-host candidate inspection changed the roster')
        # The captured picker has no closing control. Discard read-only search
        # through the known detail URL, never guess a Close/Cancel selector.
        page.goto(detail_url, wait_until='domcontentloaded', timeout=45000)
        editor, current_detail = _open_existing(page, data)
        if current_detail != detail_url:
            raise Stop('Room detail route changed during co-host preflight')
        _staged_roster(page, data, before)
    staged = deepcopy(before)
    # Add before revoking retained access. Each zero state still requires the
    # complete captured loaded-empty card through read_roster(page=, data=).
    for person in additions:
        editor = _staged_roster(page, data, staged)
        dialog, search = _open_directory(page, editor)
        candidate = _find_candidate(dialog, search, person)
        click(candidate)
        dialog.wait_for(state='hidden', timeout=45000)
        staged.append(person)
        wait_until(lambda: _same_roster(read_roster(_editor(page, data), page=page, data=data), staged),
                   'Co-host selection did not stage its exact identity')
        if page.get_by_role('dialog').count():
            raise Stop('Unexpected native dialog after co-host selection requires reconciliation')
    for person in removals:
        editor = _staged_roster(page, data, staged)
        remove = _remove_control(editor, person)
        if not remove.is_enabled():
            raise Stop('Exact co-host removal is disabled')
        click(remove)
        staged = [entry for entry in staged if entry != person]
        # Any unexpected confirmation keeps the old row or a visible dialog;
        # neither can be accepted as a staged removal.
        wait_until(lambda: _same_roster(read_roster(_editor(page, data), page=page, data=data), staged),
                   'Co-host removal did not stage; unexpected native confirmation requires capture')
        if page.get_by_role('dialog').count():
            raise Stop('Unexpected native dialog after co-host removal requires reconciliation')
    editor = _staged_roster(page, data, desired)
    changed = bool(additions or removals)
    if changed:
        save = _one(editor.get_by_role('button', name='Save changes', exact=True),
                    'Native co-host Save changes control changed')
        if not save.is_enabled():
            raise Stop('Native co-host plan is invalid; Save not attempted')
        assert_tenant(page, data)
        click(save)
        editor.wait_for(state='hidden', timeout=45000)
    # read_room reloads persisted state, checks protected room settings and
    # reopens independently. No in-memory list or dismissed dialog is proof.
    editor, reopened_detail = _open_existing(page, data)
    if reopened_detail != detail_url:
        raise Stop('Saved co-host room detail route changed')
    _staged_roster(page, data, desired)
    page.goto(detail_url, wait_until='domcontentloaded', timeout=45000)
    assert_tenant(page, data)
    return {'status':'COHOSTS_SAVED_AND_REOPENED' if changed else 'COHOSTS_REUSED_AND_REOPENED',
        'location_id':data['location_id'], 'room_id':data['expected_room_id'],
        'configuration_sha256':write_configuration_hash(data),
        'cohost_count':len(desired), 'addition_count':len(additions), 'removal_count':len(removals),
        'independent_readback':'VERIFIED', 'meeting_started':False,
        'functional_verified':False, 'notification_behavior_verified':False}
