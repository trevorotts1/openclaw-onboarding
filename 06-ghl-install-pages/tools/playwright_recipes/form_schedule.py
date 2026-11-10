"""Captured native form visibility scheduling, with independent saved read-back.

The parent runner owns tenant identity, writer leases and intent records. This
module never publishes a form or submits responses. Out-of-window behavior is
not promoted to functional proof by an editor Save or a matching saved value.
"""
from copy import deepcopy
from datetime import date, datetime, time, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ScheduleError(ValueError):
    pass


def _time_zone(value):
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ScheduleError('Schedule requires an explicit IANA time_zone')
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ScheduleError('Schedule time_zone is not a known IANA zone') from None


def _instant(value, label, zone):
    if (not isinstance(value, dict) or set(value) != {'mode', 'date', 'time'}
            or value.get('mode') != 'at'):
        raise ScheduleError(label + ' requires an exact date and local time')
    if (not isinstance(value.get('date'), str)
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value['date'])
            or not isinstance(value.get('time'), str)
            or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value['time'])):
        raise ScheduleError(label + ' date/time must use YYYY-MM-DD and HH:MM')
    try:
        naive = datetime.combine(date.fromisoformat(value['date']),
                                 time.fromisoformat(value['time']))
    except ValueError:
        raise ScheduleError(label + ' date/time is invalid') from None
    # A local clock time can be missing or occur twice when DST changes. The
    # native picker has no captured fold/offset choice, so neither is guessed.
    instants = set()
    for fold in (0, 1):
        instant = naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if instant.astimezone(zone).replace(tzinfo=None) == naive:
            instants.add(instant)
    if len(instants) != 1:
        raise ScheduleError(label + ' local time is ambiguous or nonexistent in its time_zone')
    return instants.pop()


def _outside(value, label):
    if not isinstance(value, dict):
        raise ScheduleError(label + ' must be an authored outside-window setting')
    if value.get('mode') == 'redirect' and set(value) == {'mode', 'url'}:
        if __package__:
            from .form_submission import validate as validate_submission
        else:
            from form_submission import validate as validate_submission
        try:
            validate_submission({'mode':'Redirect to URL', 'redirect_url':value['url']})
        except ValueError as exc:
            raise ScheduleError(label + ': ' + str(exc)) from None
    elif value.get('mode') == 'message' and set(value) == {'mode', 'message'}:
        if not isinstance(value['message'], str) or not value['message'].strip():
            raise ScheduleError(label + ' needs caller-approved plain message text')
        if any(ord(c) < 32 and c not in '\n\r\t' for c in value['message']):
            raise ScheduleError(label + ' message contains unsupported control characters')
    else:
        raise ScheduleError(label + ' must specify either redirect/url or message/message without ignored fields')


def validate(step):
    """Reject all invalid or incomplete schedule requests before browser access."""
    if (not isinstance(step, dict)
            or set(step) - {'id', 'action', 'schedule'}
            or ('action' in step and step['action'] != 'native_form_schedule')):
        raise ScheduleError('Unsupported native form scheduling option')
    value = step.get('schedule')
    if not isinstance(value, dict) or type(value.get('enabled')) is not bool:
        raise ScheduleError('Schedule requires an explicit enabled boolean')
    if value['enabled'] is False:
        if set(value) != {'enabled'}:
            raise ScheduleError('Disabled scheduling must not carry ignored window or message settings')
        return deepcopy(step)
    if set(value) - {'enabled', 'time_zone', 'opens', 'closes', 'before', 'after'}:
        raise ScheduleError('Unknown schedule setting')
    zone = _time_zone(value.get('time_zone'))
    instants = {}
    for key, immediate in (('opens', 'immediate'), ('closes', 'never')):
        endpoint = value.get(key)
        if isinstance(endpoint, dict) and endpoint == {'mode':immediate}:
            continue
        instants[key] = _instant(endpoint, key, zone)
    if ('opens' in instants and 'closes' in instants
            and instants['closes'] <= instants['opens']):
        raise ScheduleError('Schedule closes must be later than opens')
    result = deepcopy(step)
    for key in ('before', 'after'):
        if key in value:
            _outside(value[key], key)
            if value[key]['mode'] == 'message':
                result['schedule'][key]['message'] = value[key]['message'].replace('\r\n', '\n').replace('\r', '\n').strip()
    return result


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def configuration_hash(schedule):
    """Bind a minimal receipt to exactly the caller's validated schedule."""
    validated = validate({'schedule':schedule})
    return _hash(validated['schedule'])


def _stop(message):
    if __package__:
        from .skill6_playwright import Stop
    else:
        from skill6_playwright import Stop
    raise Stop(message)


def _controls(frame):
    """Bind the scheduler and ordinary flags to the captured native row shape."""
    if __package__:
        from .skill6_playwright import FORM_SETTINGS
    else:
        from skill6_playwright import FORM_SETTINGS
    switches = frame.get_by_role('switch')
    if switches.count() not in (8, 9):
        _stop('Native scheduling settings count changed; capture required')

    def row(control):
        return control.evaluate('''el => {
            for (const row of [el.parentElement, el.parentElement?.parentElement]) {
                if (row && row.querySelectorAll('[role="switch"]').length === 1
                        && row.textContent.trim()) return row.textContent;
            }
            return '';
        }''')

    def checked(control):
        value = control.get_attribute('aria-checked')
        if value not in ('true', 'false'):
            _stop('Native scheduling switch state is not exposed')
        return value == 'true'

    scheduler = switches.nth(0)
    if 'Schedule form visibility' not in row(scheduler):
        _stop('Native scheduling row identity changed')
    enabled = checked(scheduler)
    offset = int(enabled)
    if switches.count() != 8 + offset:
        _stop('Native scheduling count disagrees with its enabled state')
    protected = {}
    if enabled:
        branding = switches.nth(1)
        if 'Agency branding' not in row(branding):
            _stop('Native scheduling branding row identity changed')
        protected['agency_branding'] = checked(branding)
    for key, (index, label) in FORM_SETTINGS.items():
        control = switches.nth(index + offset)
        if label not in row(control):
            _stop('Native ordinary-setting row identity changed')
        protected[key] = checked(control)
    return scheduler, enabled, protected


def _clock(value):
    """Convert a validated 24-hour request to the captured native clock label."""
    hours, minutes = (int(part) for part in value.split(':'))
    return str(hours % 12 or 12) + ':' + str(minutes).zfill(2) + (' AM' if hours < 12 else ' PM')


def _local_clock(value):
    if not isinstance(value, str):
        _stop('Native scheduling time is not exposed')
    match = re.fullmatch(r'(0?[1-9]|1[0-2]):([0-5]\d) (AM|PM)', value)
    if not match:
        _stop('Native scheduling time format changed')
    hours = int(match[1]) % 12 + (12 if match[3] == 'PM' else 0)
    return str(hours).zfill(2) + ':' + match[2]


def _local_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{2}/\d{2}/\d{4}', value):
        _stop('Native scheduling date format changed')
    month, day, year = (int(part) for part in value.split('/'))
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        _stop('Native scheduling date value is invalid')


def _mode(frame, definition):
    buttons = {key:frame.locator(selector) for key, selector in definition['modes'].items()}
    selected = []
    for key, button in buttons.items():
        if button.count() != 1 or not button.is_visible():
            _stop('Native scheduling mode controls changed')
        if 'seg-btn--active' in (button.get_attribute('class') or '').split():
            selected.append(key)
    if len(selected) != 1:
        _stop('Native scheduling selected mode is unavailable or ambiguous')
    return selected[0], buttons


def _picker(frame, selector, placeholder):
    container = frame.locator(selector)
    if container.count() != 1:
        _stop('Native scheduling picker scope changed')
    control = container.get_by_placeholder(placeholder, exact=True)
    if control.count() != 1 or control.get_attribute('type') != 'text':
        _stop('Native scheduling picker input changed')
    control.wait_for(state='visible', timeout=45000)
    return control


def _read_endpoint(frame, definition):
    mode, _ = _mode(frame, definition)
    if mode != 'at':
        return {'mode':mode}
    return {'mode':'at',
        'date':_local_date(_picker(frame, definition['date'], 'Select Date').input_value()),
        'time':_local_clock(_picker(frame, definition['time'], 'Select Time').input_value())}


def _set_endpoint(frame, definition, wanted):
    if __package__:
        from .skill6_playwright import click, fill, wait_until
    else:
        from skill6_playwright import click, fill, wait_until
    current, buttons = _mode(frame, definition)
    if current != wanted['mode']:
        click(buttons[wanted['mode']])
        wait_until(lambda: _mode(frame, definition)[0] == wanted['mode'],
                   'Native scheduling mode did not change')
    if wanted['mode'] == 'at':
        day = date.fromisoformat(wanted['date'])
        for selector, placeholder, value in (
                (definition['date'], 'Select Date', f'{day.month:02d}/{day.day:02d}/{day.year:04d}'),
                (definition['time'], 'Select Time', _clock(wanted['time']))):
            control = _picker(frame, selector, placeholder)
            fill(control, value)
            control.press('Tab')
    if _read_endpoint(frame, definition) != wanted:
        _stop('Native scheduling endpoint did not adopt the requested value')


_WINDOWS = {
    'opens': {'modes':{'immediate':'#schedule-open-mode-anytime', 'at':'#schedule-open-mode-date'},
              'date':'#schedule-open-date', 'time':'#schedule-open-time'},
    'closes': {'modes':{'never':'#schedule-close-mode-never', 'at':'#schedule-close-mode-date'},
               'date':'#schedule-close-date', 'time':'#schedule-close-time'},
}
_HEADERS = {'before':'#schedule-state-header-before', 'after':'#schedule-state-header-after'}
_REDIRECTS = {'before':'#schedule-redirect-before', 'after':'#schedule-redirect-after'}
_RADIOS = {'message':'Show a page Design what visitors see.',
           'redirect':'Open a link Send them to another URL.'}


def _zone_label(value):
    if not isinstance(value, str):
        _stop('Native scheduling timezone label is not exposed')
    match = re.search(r'\(([^()]+)\)$', value.strip())
    if not match:
        _stop('Native scheduling timezone label changed')
    key = match[1].replace(' ', '_')
    try:
        _time_zone(key)
    except ScheduleError:
        _stop('Native scheduling timezone identity is unavailable')
    return key


def _zone(frame):
    region = frame.locator('#schedule-timezone')
    labels = region.locator('.n-base-selection-label')
    if region.count() != 1 or labels.count() != 1:
        _stop('Native scheduling timezone scope changed')
    return _zone_label(labels.get_attribute('title'))


def _set_zone(frame, wanted):
    if __package__:
        from .skill6_playwright import click, fill, wait_until
    else:
        from skill6_playwright import click, fill, wait_until
    if _zone(frame) == wanted:
        return
    region = frame.locator('#schedule-timezone')
    search = region.get_by_role('textbox')
    if search.count() != 1:
        _stop('Native scheduling timezone search changed')
    click(region)
    fill(search, wanted.replace('_', ' '))
    matches = frame.locator('.n-base-select-option').filter(
        has_text=re.compile(r'\(' + re.escape(wanted.replace('_', ' ')) + r'\)$'))

    def choice_ready():
        count = matches.count()
        if count > 1:
            _stop('Native scheduling timezone choices are ambiguous')
        return count == 1 and matches.is_visible()

    wait_until(choice_ready, 'Requested native timezone choice is unavailable')
    label = matches.inner_text().strip()
    if _zone_label(label) != wanted:
        _stop('Native scheduling timezone option identity differs')
    choice = matches.get_by_text(label, exact=True)
    if choice.count() != 1:
        _stop('Native scheduling timezone option label changed')
    click(choice)
    wait_until(lambda: _zone(frame) == wanted, 'Native scheduling timezone did not change')


def _outside_scope(frame, state):
    if __package__:
        from .skill6_playwright import click, wait_until
    else:
        from skill6_playwright import click, wait_until
    header = frame.locator(_HEADERS[state])
    if header.count() != 1:
        _stop('Native outside-window header changed')
    card = header.locator('..')
    if card.evaluate("el => el.matches('div.state-card')") is not True:
        _stop('Native outside-window header ownership changed')
    expanded = header.get_attribute('aria-expanded')
    if expanded not in ('true', 'false'):
        _stop('Native outside-window expansion state is not exposed')
    if expanded != 'true':
        click(header)
        wait_until(lambda: header.get_attribute('aria-expanded') == 'true',
                   'Native outside-window state did not open')
    body = card.locator(':scope > div.state-card__body')
    if body.count() != 1:
        _stop('Native outside-window body ownership changed')
    body.wait_for(state='visible', timeout=45000)
    if body.get_by_role('radiogroup').count() != 1:
        _stop('Native outside-window mode inventory changed')
    return body


def _radio_checked(control):
    value = control.get_attribute('aria-checked')
    if value is not None:
        if value not in ('true', 'false'):
            _stop('Native outside-window radio state changed')
        return value == 'true'
    if control.get_attribute('type') == 'radio':
        return control.is_checked()
    nested = control.locator('input[type="radio"]')
    if nested.count() != 1:
        _stop('Native outside-window radio checked state is unavailable')
    return nested.is_checked()


def _outside_mode(body):
    choices = {key:body.get_by_role('radio', name=label, exact=True)
               for key, label in _RADIOS.items()}
    if any(control.count() != 1 for control in choices.values()):
        _stop('Native outside-window radio labels changed')
    selected = [key for key, control in choices.items() if _radio_checked(control)]
    if len(selected) != 1:
        _stop('Native outside-window mode is unavailable or ambiguous')
    return selected[0], choices


def _outside_value(body, state, mode):
    if mode == 'message':
        control = body.locator('.tiptap.ProseMirror[contenteditable="true"]')
    else:
        if state not in _REDIRECTS:
            _stop('This native outside-window redirect still requires capture')
        control = body.locator(_REDIRECTS[state]).get_by_placeholder('https://example.com', exact=True)
        if control.count() == 1 and control.get_attribute('type') != 'text':
            _stop('Native outside-window redirect input type changed')
    if control.count() != 1:
        _stop('Native outside-window value editor is absent or ambiguous')
    control.wait_for(state='visible', timeout=45000)
    return control


def _read_outside(frame, state):
    body = _outside_scope(frame, state)
    mode, _ = _outside_mode(body)
    control = _outside_value(body, state, mode)
    if mode == 'message':
        return {'mode':'message', 'message':control.inner_text().replace('\r\n','\n').replace('\r','\n').strip(),
                'html':control.evaluate('el => el.innerHTML')}
    return {'mode':'redirect', 'url':control.input_value()}


def _set_outside(frame, state, wanted):
    if __package__:
        from .skill6_playwright import click, fill, wait_until
    else:
        from skill6_playwright import click, fill, wait_until
    body = _outside_scope(frame, state)
    mode, choices = _outside_mode(body)
    if mode != wanted['mode']:
        click(choices[wanted['mode']])
        wait_until(lambda: _outside_mode(body)[0] == wanted['mode'],
                   'Native outside-window mode did not change')
    value = wanted['message'] if wanted['mode'] == 'message' else wanted['url']
    fill(_outside_value(body, state, wanted['mode']), value)
    observed = _read_outside(frame, state)
    if {key:observed.get(key) for key in wanted} != wanted:
        _stop('Native outside-window state did not adopt the authored value')


def _read_schedule(frame):
    return {'time_zone':_zone(frame),
            'opens':_read_endpoint(frame, _WINDOWS['opens']),
            'closes':_read_endpoint(frame, _WINDOWS['closes']),
            'before':_read_outside(frame, 'before'),
            'after':_read_outside(frame, 'after')}


def _preserved(actual, expected):
    if any(actual.get(key) != value for key, value in expected.items()
           if key != 'agency_branding' or key in actual):
        _stop('Native ordinary form settings or exposed branding changed while scheduling')


def configure(page, step):
    """Set an authored window once, save once and independently reopen the form."""
    if __package__:
        from .skill6_playwright import click, visible, form_builder, wait_until
        from .assessments import reopen_editor, read_editor_title
    else:
        from skill6_playwright import click, visible, form_builder, wait_until
        from assessments import reopen_editor, read_editor_title
    step = validate(step)
    wanted = step['schedule']
    # An unobserved selector must not be discovered after a previous edit.
    if any(wanted.get(state, {}).get('mode') == 'redirect' and state not in _REDIRECTS
           for state in ('before', 'after')):
        _stop('Requested outside-window redirect still requires native control capture')
    frame = form_builder(page)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    form_name, editor_url = read_editor_title(title), page.url
    if not isinstance(form_name, str) or not form_name.strip():
        _stop('Saved native form identity is unavailable')
    parsed = urlsplit(editor_url)
    if (parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or not re.fullmatch(
                r'/v2/location/[A-Za-z0-9_-]+/form-builder-v2/[A-Za-z0-9_-]+/?', parsed.path)):
        _stop('Native form schedule editor identity is not a captured exact HTTPS route')

    def open_settings():
        nonlocal frame
        frame = form_builder(page)
        close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
        if visible(close):
            click(close)
        click(frame.get_by_role('tab', name='Settings', exact=True))
        wait_until(lambda: frame.get_by_role('switch').count() in (8, 9),
                   'Native scheduling settings did not become ready')
        return _controls(frame)

    scheduler, enabled, protected = open_settings()
    if enabled != wanted['enabled']:
        click(scheduler)
        wait_until(lambda: scheduler.get_attribute('aria-checked') == str(wanted['enabled']).lower()
                   and frame.get_by_role('switch').count() == (9 if wanted['enabled'] else 8),
                   'Native scheduling enabled state did not change')
    _, _, current_protected = _controls(frame)
    _preserved(current_protected, protected)
    if wanted['enabled']:
        # Enabling exposes the existing branding flag. Preserve this value as
        # well; it is never clicked and is verified again while still exposed.
        protected.update(current_protected)
        original = _read_schedule(frame)
        _set_zone(frame, wanted['time_zone'])
        for key in ('opens', 'closes'):
            _set_endpoint(frame, _WINDOWS[key], wanted[key])
        for key in ('before', 'after'):
            if key in wanted:
                _set_outside(frame, key, wanted[key])
    else:
        original = None
    _preserved(_controls(frame)[2], protected)
    save = frame.get_by_role('button', name='Save', exact=True)
    click(save)
    wait_until(lambda: save.count() == 1 and save.is_enabled(),
               'Native scheduling save did not finish')
    reopen_editor(page, 'form', form_name, editor_url)
    _, persisted_enabled, actual_protected = open_settings()
    if persisted_enabled != wanted['enabled']:
        _stop('Native scheduling enabled state did not persist')
    _preserved(actual_protected, protected)
    if wanted['enabled']:
        actual = _read_schedule(frame)
        if any(actual[key] != wanted[key] for key in ('time_zone', 'opens', 'closes')):
            _stop('Native scheduling window or timezone did not persist')
        for key in ('before', 'after'):
            if key in wanted:
                if {field:actual[key].get(field) for field in wanted[key]} != wanted[key]:
                    _stop('Authored native outside-window state did not persist')
            elif actual[key] != original[key]:
                _stop('Omitted native outside-window content changed while scheduling')
    return {'status':'FORM_SCHEDULE_SAVED_AND_REOPENED', 'editor_url':editor_url,
            'enabled':wanted['enabled'], 'configuration_sha256':configuration_hash(wanted),
            'independent_readback':'VERIFIED', 'behavior_verified':False,
            'submission_verified':False}
