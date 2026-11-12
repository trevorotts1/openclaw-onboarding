"""Captured Date & time field settings in the native form property sidebar.

The first profile edits saved DATE_TIME fields only. Existing range restrictions
must be the captured Any date state; custom time/range controls remain explicit
capture dependencies. Generic family handling owns save/reopen and replay.
"""
from playwright_recipes.skill6_playwright import Stop, click, wait_until

GROUPS = {
    'date_format': ('date-format-', ('mm-dd-yyyy', 'yyyy-mm-dd', 'dd-mm-yyyy')),
    'date_separator': ('date-separator-', ('dash', 'slash', 'dot')),
    'time_format': ('time-format-', ('24', '12')),
    'default_time': ('default-time-', ('none', 'current', 'custom')),
}
EXTRA = (*GROUPS, 'date_range', 'disable_picker')
TIME_EXTRA = ('time_format', 'default_time', 'time_range', 'disable_picker')
DATE_EXTRA = ('date_format', 'date_separator', 'date_range', 'disable_picker')


def _groups(kind):
    return GROUPS if kind == 'date_time' else {key: GROUPS[key] for key in (('date_format','date_separator') if kind=='date' else ('time_format', 'default_time'))}


def _extra(kind):
    return EXTRA if kind == 'date_time' else DATE_EXTRA if kind=='date' else TIME_EXTRA


def validate_properties(value, *, kind='date_time'):
    for key, (_, choices) in _groups(kind).items():
        if not isinstance(value[key], str) or value[key] not in choices:
            raise Stop('Date & time requires a captured ' + key)
    if value.get('default_time') == 'custom':
        raise Stop('Date & time custom default time requires its captured value control')
    if value['time_range' if kind=='time' else 'date_range'] != 'any' or type(value['disable_picker']) is not bool:
        raise Stop('Date & time requires the captured Any date range and explicit popup state')


def _one(node, message):
    if node.count() != 1 or not node.is_visible():
        raise Stop(message)
    return node


def _selected(panel, prefix, choices):
    selected = []
    for choice in choices:
        node = _one(panel.locator('#' + prefix + choice), 'Date & time segmented control changed')
        if 'dt-segmented-button--active' in (node.get_attribute('class') or '').split():
            selected.append(choice)
    if len(selected) != 1:
        raise Stop('Date & time segmented selection is missing or ambiguous')
    return selected[0]


def _panel(frame, sidebar, kind):
    panel = _one(frame.locator(sidebar), 'Date & time sidebar changed')
    click(_one(panel.locator('[data-name="settings"]'), 'Date & time Field settings tab changed'))
    panel.locator('#date-format-yyyy-mm-dd' if kind=='date' else '#time-format-24').wait_for(state='visible', timeout=45000)
    return panel


def read_options(frame, *, sidebar='#form_custom_sidebar', kind='date_time'):
    panel = _panel(frame, sidebar, kind)
    result = {key: _selected(panel, prefix, choices) for key, (prefix, choices) in _groups(kind).items()}
    mode = _one(panel.locator(('#timeMode' if kind=='time' else '#dateMode') + ' .n-base-selection-input'), 'Date & time range selection changed')
    if mode.get_attribute('title') != ('Any time' if kind=='time' else 'Any date'):
        raise Stop('Date & time existing range is outside the captured Any date profile')
    popup = _one(panel.locator('#picker-settings[role="checkbox"]'), 'Date & time popup control changed')
    checked = popup.get_attribute('aria-checked')
    if checked not in ('true', 'false'):
        raise Stop('Date & time popup state is unavailable')
    result.update({'time_range' if kind=='time' else 'date_range':'any', 'disable_picker':checked == 'true'})
    validate_properties(result,kind=kind)
    return result


def write_options(frame, before, desired, *, sidebar='#form_custom_sidebar', kind='date_time'):
    current = read_options(frame, sidebar=sidebar,kind=kind)
    if current != {key: before[key] for key in _extra(kind)}:
        raise Stop('Date & time settings changed after preflight')
    panel = frame.locator(sidebar)
    for key, (prefix, choices) in _groups(kind).items():
        if current[key] != desired[key]:
            node = _one(panel.locator('#' + prefix + desired[key]), 'Date & time requested selection changed')
            if not node.is_enabled():
                raise Stop('Date & time requested selection is disabled')
            click(node)
            wait_until(lambda: _selected(panel, prefix, choices) == desired[key],
                       'Date & time selection did not settle once')
    popup = _one(panel.locator('#picker-settings[role="checkbox"]'), 'Date & time popup control changed')
    if (popup.get_attribute('aria-checked') == 'true') != desired['disable_picker']:
        click(popup)
        wait_until(lambda: (popup.get_attribute('aria-checked') == 'true') == desired['disable_picker'],
                   'Date & time popup state did not settle once')
    if read_options(frame, sidebar=sidebar,kind=kind) != {key: desired[key] for key in _extra(kind)}:
        raise Stop('Date & time settings ignored the requested values')
