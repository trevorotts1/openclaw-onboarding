#!/usr/bin/env python3
"""Create a scheduled built-in Live Session from a captured course editor.

This is the course's native Live Sessions wizard. It does not bind a personal
Meeting Room, start a call, publish the course, or notify learners. The captured
profile supports ISO dates, quarter-hour time choices and the captured New York
timezone. Creation remains explicitly opt-in and saved state is reopened.

HighLevel's official reusable Personal Meeting Link settings are documented for
Communities Live Sessions; the captured course wizard does not expose that
control. Course-to-personal-room association is therefore marked UNAVAILABLE:
https://help.gohighlevel.com/support/solutions/articles/155000008012-communities-live-session-enhancements-personal-meeting-links-recordings-hub-noise-cancellation
"""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click, fill, wait_until
else:
    from skill6_playwright import Stop, assert_tenant, click, fill, wait_until


_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
_TITLE = 'Add a title that describes your stream'
_DESCRIPTION = 'Tell viewers more about your stream'
_TIMEZONE = '(GMT-0500) New York'
_TIME_MENU_LABEL = re.compile(r'^(?P<time>(?:[01]\d|2[0-3]):(?:00|15|30|45))(?:\s+\((?:(?:\d+h)(?:\s*\d+min)?|\d+min)\))?$')
_NOTIFICATION_SWITCHES = {
    'notify_on_changes': ('notify-on-changes-toggle', 'Notify learners about session changes'),
    'notify_on_go_live': ('notify-on-go-live-toggle', 'Notify learners when you go live'),
    'remind_before_session': ('remind-before-session-toggle', 'Remind learners before your session'),
}


def validate_inputs(inputs):
    required = {
        'location_id', 'location_name', 'start_url', 'product_id', 'session_name',
        'description', 'instructor_name', 'date', 'start_time', 'end_time',
        'timezone', 'allow_creation',
    }
    if not isinstance(inputs, dict) or set(inputs) != required:
        raise Stop('Course Live Session requires the exact captured course/session input contract')
    data = deepcopy(inputs)
    for key in ('location_id', 'product_id'):
        if not isinstance(data[key], str) or not _ID.fullmatch(data[key]):
            raise Stop('Course Live Session requires exact inventoried ' + key)
    for key in ('location_name', 'session_name', 'instructor_name'):
        value = data[key]
        if (not isinstance(value, str) or value != value.strip() or not value
                or len(value) > (100 if key == 'session_name' else 128)
                or any(ord(c) < 32 for c in value)):
            raise Stop(key + ' must be exact nonempty plain text within the captured limit')
    if (not isinstance(data['description'], str) or len(data['description']) > 300
            or any(ord(c) < 32 and c not in '\n\t' for c in data['description'])):
        raise Stop('Live Session description must be plain text of at most 300 characters')
    if type(data['allow_creation']) is not bool:
        raise Stop('Course Live Session allow_creation must be a real boolean')
    if data['allow_creation'] is not True:
        raise Stop('Creating a new course Live Session requires explicit allow_creation=true')
    try:
        parsed = urlsplit(data['start_url'])
        query = parse_qs(parsed.query, strict_parsing=True)
    except (TypeError, ValueError):
        raise Stop('Course editor URL is malformed') from None
    expected_path = '/v2/location/' + data['location_id'] + '/memberships/courses/course-creator-studio'
    if (parsed.scheme != 'https' or parsed.netloc != 'app.convertandflow.com'
            or parsed.path != expected_path or parsed.fragment or parsed.username or parsed.password
            or query != {'view': ['manager'], 'sub_view': ['outline'], 'product_id': [data['product_id']]}):
        raise Stop('Live Session requires the exact observed course outline manager URL and product identity')
    try:
        chosen_date = date.fromisoformat(data['date'])
    except (TypeError, ValueError):
        raise Stop('Session date must be ISO YYYY-MM-DD') from None
    if data['timezone'] != _TIMEZONE:
        raise Stop('Captured Live Session timezone must be ' + _TIMEZONE)
    time_pattern = r'(?:[01]\d|2[0-3]):(?:00|15|30|45)'
    if not isinstance(data['start_time'], str) or not re.fullmatch(time_pattern, data['start_time']):
        raise Stop('start_time must be an exact quarter-hour time from the captured menu')
    if not isinstance(data['end_time'], str) or not re.fullmatch(time_pattern, data['end_time']):
        raise Stop('end_time must be an exact quarter-hour time from the captured menu')
    try:
        start = datetime.strptime(data['start_time'], '%H:%M').time()
        end = datetime.strptime(data['end_time'], '%H:%M').time()
    except ValueError:
        raise Stop('Session time is invalid') from None
    if end <= start:
        raise Stop('Session end time must follow its start time on the same day')
    return data


def configuration_hash(inputs):
    data = validate_inputs(inputs)
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _one(locator, message):
    if locator.count() != 1 or not locator.is_visible():
        raise Stop(message)
    return locator


def _course_route(page, data):
    expected = urlsplit(data['start_url'])
    current = urlsplit(page.url)
    if ((current.scheme, current.netloc, current.path, current.query, current.fragment)
            != (expected.scheme, expected.netloc, expected.path, expected.query, expected.fragment)):
        raise Stop('Current course editor differs from the exact requested product URL')
    assert_tenant(page, data)


def _open_course(page, data):
    """Start from the already authenticated tenant and navigate to its exact course."""
    assert_tenant(page, data)
    page.goto(data['start_url'], wait_until='domcontentloaded', timeout=45000)
    _course_route(page, data)


def _toggle_off(dialog, switch_id, label):
    control = _one(dialog.locator('#' + switch_id), 'Native notification toggle changed: ' + label)
    if control.get_attribute('role') != 'switch':
        raise Stop('Native notification control is no longer a switch: ' + label)
    state = control.get_attribute('aria-checked')
    if state not in ('true', 'false'):
        raise Stop('Native notification state is not readable: ' + label)
    if state == 'true':
        click(control)
    wait_until(lambda: control.get_attribute('aria-checked') == 'false',
               'Could not disable learner notification: ' + label)


def _navigate_to_month(calendar, target):
    """Navigate with the captured prev/next month controls and read each month heading."""
    header = _one(calendar.locator('.hr-date-panel-month__text'),
                  'Captured date picker month heading changed')
    target_index = target.year * 12 + target.month - 1
    current_text = header.inner_text().strip()
    try:
        current = datetime.strptime(current_text, '%b %Y')
    except ValueError:
        raise Stop('Date picker month heading is not in the captured English month format') from None
    current_index = current.year * 12 + current.month - 1
    delta = target_index - current_index
    direction = 1 if delta > 0 else -1
    for _ in range(abs(delta)):
        current_index += direction
        expected = datetime(current_index // 12, current_index % 12 + 1, 1).strftime('%b %Y')
        selector = '.hr-date-panel-month__next' if direction > 0 else '.hr-date-panel-month__prev'
        click(_one(calendar.locator(selector), 'Captured date picker month navigation changed'))
        wait_until(lambda: header.inner_text().strip() == expected,
                   'Date picker did not move to the next requested month')


def _select_calendar_day(calendar, target):
    """Select one enabled cell in the requested displayed month, excluding adjacent-month duplicates."""
    day = str(target.day)
    cells = calendar.locator('[data-n-date="true"]')
    matches = []
    for index in range(cells.count()):
        cell = cells.nth(index)
        if not cell.is_visible() or cell.inner_text().strip() != day:
            continue
        classes = set((cell.get_attribute('class') or '').split())
        if 'hr-date-panel-date--excluded' not in classes:
            matches.append(cell)
    if len(matches) != 1:
        raise Stop('Requested calendar day is missing or ambiguous in its target month')
    if 'hr-date-panel-date--disabled' in (matches[0].get_attribute('class') or '').split():
        raise Stop('Requested Live Session date is disabled by the native calendar')
    click(matches[0])


def _choose_end_time(dialog, time_value):
    """Choose the unique visible native option whose leading token is the requested HH:MM."""
    candidates = dialog.get_by_text(_TIME_MENU_LABEL)
    labels = []
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        if not candidate.is_visible():
            continue
        label = candidate.inner_text().strip()
        match = _TIME_MENU_LABEL.fullmatch(label)
        if match and match.group('time') == time_value and label not in labels:
            labels.append(label)
    if len(labels) != 1:
        raise Stop('End-time menu must expose one unique captured option for the requested HH:MM')
    option = dialog.get_by_text(labels[0], exact=True)
    return click(_one(option, 'Observed End-time option changed or became ambiguous'))


def read_live_session(page, inputs):
    """Read the exact session title after reopening the same course outline."""
    data = validate_inputs(inputs)
    _open_course(page, data)
    page.reload(wait_until='domcontentloaded', timeout=45000)
    _course_route(page, data)
    live_sessions = _one(page.get_by_text('Live Sessions', exact=True),
                         'Captured course Live Sessions section changed')
    click(live_sessions)
    title = page.get_by_text(data['session_name'], exact=True)
    wait_until(lambda: title.count() == 1 and title.is_visible(),
               'Created Live Session was not present after reopening the course editor')
    return {'status': 'PRESENT', 'source': 'native course Live Sessions list after independent reload',
            'location_id': data['location_id'], 'product_id': data['product_id'],
            'session_name': data['session_name']}


def create_live_session(page, inputs, *, reader=None):
    """Create one scheduled built-in session with all learner notices disabled.

    The modal's final Create action is a write. It is reached only after an
    exact course/tenant binding, duplicate check, staged-value checks and three
    explicit notification-off readbacks. A separate reload confirms persistence.
    """
    data = validate_inputs(inputs)
    reader = reader or read_live_session
    _open_course(page, data)
    section = _one(page.get_by_text('Live Sessions', exact=True),
                   'Captured course Live Sessions section changed')
    click(section)
    if page.get_by_text(data['session_name'], exact=True).count():
        raise Stop('A Live Session with this exact title already exists; reconcile before creating')
    add = _one(page.get_by_role('button', name='Add live session', exact=True),
               'Captured Add live session control changed')
    click(add)
    dialog = _one(page.locator('#create-live-session-modal'),
                  'Captured Create live session wizard changed')

    name = _one(dialog.get_by_role('textbox', name=_TITLE, exact=True),
                'Live Session title field changed')
    description = _one(dialog.get_by_role('textbox', name=_DESCRIPTION, exact=True),
                       'Live Session description field changed')
    instructor = _one(dialog.get_by_role('textbox', name='Instructor name', exact=True),
                      'Live Session instructor field changed')
    fill(name, data['session_name'])
    fill(description, data['description'])
    fill(instructor, data['instructor_name'])
    for field, expected in ((name, data['session_name']), (description, data['description']),
                            (instructor, data['instructor_name'])):
        if field.input_value() != expected:
            raise Stop('Live Session basic details changed before Next')
    click(_one(dialog.locator('#modal-next-btn'), 'Captured Live Session Next control changed'))

    date_picker = _one(dialog.locator('#hr-date-picker-start'), 'Captured Live Session date picker changed')
    date_input = _one(date_picker.locator('input[type="text"]'),
                      'Captured Live Session date input changed')
    click(date_picker)
    calendar = _one(dialog.get_by_role('dialog', name='Choose Date', exact=True),
                    'Captured Live Session date calendar changed')
    target_date = date.fromisoformat(data['date'])
    _navigate_to_month(calendar, target_date)
    _select_calendar_day(calendar, target_date)
    staged_date = date_input.input_value()
    expected_display = date.fromisoformat(data['date']).strftime('%d / %m / %Y')
    if staged_date != expected_display:
        # Some captured builds expose the selected date as an input value.
        staged_date = date_input.input_value()
    if staged_date != expected_display:
        raise Stop('Live Session date did not stage to the exact requested day')

    time_section = _one(dialog.locator('#schedule-date-time-section'),
                        'Captured Live Session schedule controls changed')
    start_control = _one(time_section.locator('#start-time'), 'Captured session start-time selector changed')
    click(start_control)
    start_option = _one(dialog.get_by_text(data['start_time'], exact=True),
                        'Requested session start time is absent or ambiguous')
    click(start_option)
    end_control = _one(time_section.locator('#end-time'), 'Captured session end-time selector changed')
    click(end_control)
    _choose_end_time(dialog, data['end_time'])
    recurrence = _one(dialog.locator('#session-type'), 'Captured recurrence selector changed')
    if recurrence.locator('.hr-base-selection-input__content').inner_text().strip() != 'Does not repeat':
        raise Stop('Only the captured nonrecurring Live Session profile is supported')
    timezone = _one(dialog.locator('#timezone'), 'Captured timezone selector changed')
    if timezone.locator('.hr-base-selection-input__content').inner_text().strip() != data['timezone']:
        raise Stop('Live Session timezone differs from the captured New York profile')
    actual_start = _one(time_section.locator('#start-time .hr-base-selection-input__content'),
                        'Selected session start time is not readable')
    actual_end = _one(time_section.locator('#end-time .hr-base-selection-input__content'),
                      'Selected session end time is not readable')
    if (actual_start.inner_text().strip() != data['start_time']
            or not _TIME_MENU_LABEL.fullmatch(actual_end.inner_text().strip())
            or _TIME_MENU_LABEL.fullmatch(actual_end.inner_text().strip()).group('time') != data['end_time']):
        raise Stop('Session time did not stage to the requested canonical times')
    click(_one(dialog.locator('#modal-next-btn'), 'Captured Live Session Next control changed'))

    for key, (switch_id, label) in _NOTIFICATION_SWITCHES.items():
        _toggle_off(dialog, switch_id, label)
    if any(dialog.locator('#' + switch_id).get_attribute('aria-checked') != 'false'
           for switch_id, _label in _NOTIFICATION_SWITCHES.values()):
        raise Stop('Learner notification settings changed before final Create')
    create = _one(dialog.locator('#modal-done-btn'), 'Captured Live Session Create control changed')
    if create.inner_text().strip() != 'Create' or not create.is_enabled():
        raise Stop('Live Session is incomplete or the final Create action changed')
    click(create)
    dialog.wait_for(state='hidden', timeout=45000)
    _course_route(page, data)
    observed = reader(page, data)
    if (not isinstance(observed, dict) or observed.get('status') != 'PRESENT'
            or observed.get('location_id') != data['location_id']
            or observed.get('product_id') != data['product_id']
            or observed.get('session_name') != data['session_name'] or not observed.get('source')):
        raise Stop('Independent course Live Session readback did not match the requested identity')
    return validate_receipt({'status': 'COURSE_LIVE_SESSION_CREATED_AND_REOPENED',
            'location_id': data['location_id'], 'product_id': data['product_id'],
            'session_name': data['session_name'], 'date': data['date'],
            'start_time': data['start_time'], 'end_time': data['end_time'],
            'timezone': data['timezone'], 'recurrence': 'Does not repeat',
            'learner_notifications_enabled': False, 'personal_room_association': 'UNAVAILABLE',
            'meeting_started': False, 'identity_readback': 'VERIFIED',
            'settings_readback': 'PENDING', 'functional_verified': False,
            'configuration_sha256': configuration_hash(data)}, data)


def validate_receipt(receipt, inputs):
    data = validate_inputs(inputs)
    expected = {
        'status': 'COURSE_LIVE_SESSION_CREATED_AND_REOPENED',
        'location_id': data['location_id'], 'product_id': data['product_id'],
        'session_name': data['session_name'], 'date': data['date'],
        'start_time': data['start_time'], 'end_time': data['end_time'],
        'timezone': data['timezone'], 'recurrence': 'Does not repeat',
        'learner_notifications_enabled': False, 'personal_room_association': 'UNAVAILABLE',
        'meeting_started': False, 'identity_readback': 'VERIFIED',
        'settings_readback': 'PENDING', 'functional_verified': False,
        'configuration_sha256': configuration_hash(data),
    }
    if not isinstance(receipt, dict) or set(receipt) != set(expected) or receipt != expected:
        raise Stop('Completed course Live Session receipt is malformed or belongs to another course')
    return deepcopy(receipt)


def verify_completed(page, inputs, receipt):
    """Replay completed journal by checking the unique saved course/title identity."""
    data = validate_inputs(inputs)
    value = validate_receipt(receipt, data)
    observed = read_live_session(page, data)
    if (observed.get('status') != 'PRESENT' or observed.get('location_id') != data['location_id']
            or observed.get('product_id') != data['product_id']
            or observed.get('session_name') != data['session_name']):
        raise Stop('Completed course Live Session identity drifted; no write was replayed')
    return value
