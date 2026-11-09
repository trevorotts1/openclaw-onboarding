"""Captured Neo Classic text/visibility controls on an existing inactive theme.

Native controls captured November 9, 2026. This edits an inventoried template;
it never activates a theme, publishes a course, enrolls a learner or uploads media.
https://help.gohighlevel.com/support/solutions/articles/155000004888-new-theme-customizer-for-courses
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import parse_qsl, urlsplit

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click, fill, wait_until
else:
    from skill6_playwright import Stop, assert_tenant, click, fill, wait_until


TEXT_LIMITS = {
    'template_title': 128, 'search_placeholder': 500,
    'hero_title': 500, 'hero_description': 2500, 'start_button_text': 300,
    'progress_text': 500, 'instructor_heading': 500, 'instructor_name': 500,
    'instructor_title': 500, 'instructor_bio': 2500,
    'primary_font':128, 'primary_weight':64, 'secondary_font':128, 'secondary_weight':64,
}
VISIBILITY = {'progress_visible', 'instructor_visible', 'headshot_visible'}
FONT_FIELDS = {'primary_font','primary_weight','secondary_font','secondary_weight'}
FIELDS = set(TEXT_LIMITS) | VISIBILITY | {'hero_spacing','layout_palette'}
COMMON = {'location_id', 'location_name', 'start_url', 'publish', 'auth_activation'}
INPUTS = {'course_id', 'template_id', 'expected_template_title', 'changes', 'expected_values'}


def _text(value, label, limit, *, empty=False):
    if (not isinstance(value, str) or len(value) > limit
            or (not empty and not value.strip())
            or any(ord(c) < 32 and c not in '\n\r\t' for c in value)):
        raise Stop('Invalid course theme ' + label)
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', value):
        raise Stop('Course theme requires exact course and template identities')
    return value


def _hexa(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?', value):
        raise Stop('Theme palette colors require explicit #RRGGBB or #RRGGBBAA values')
    return value.upper() + ('FF' if len(value) == 7 else '')


def _palette(value):
    if (not isinstance(value,dict) or set(value) != {'base','accent'}
            or not isinstance(value['base'],list) or len(value['base']) != 2
            or not isinstance(value['accent'],list) or len(value['accent']) != 4):
        raise Stop('Theme palette requires exactly two base and four accent colors')
    return {key:[_hexa(color) for color in value[key]] for key in ('base','accent')}


def validate_inputs(inputs):
    if not isinstance(inputs, dict) or set(inputs) - COMMON - INPUTS:
        raise Stop('Unsupported course theme input; activation and media require separate operations')
    if 'publish' in inputs and inputs['publish'] is not False:
        raise Stop('Course template editing never publishes or activates a theme')
    for key in ('location_id', 'location_name', 'start_url'):
        _text(inputs.get(key), key, 2000)
    _id(inputs['location_id'])
    for key in ('course_id', 'template_id'):
        _id(inputs.get(key))
    _text(inputs.get('expected_template_title'), 'expected_template_title', 128)
    changes, expected = inputs.get('changes'), inputs.get('expected_values')
    if (not isinstance(changes, dict) or not changes or set(changes) - FIELDS
            or not isinstance(expected, dict) or set(expected) != set(changes)):
        raise Stop('Every requested theme change requires its exact inventoried previous value')
    for values in (changes, expected):
        for key, value in values.items():
            if key == 'layout_palette':
                _palette(value)
            elif key in VISIBILITY:
                if type(value) is not bool:
                    raise Stop('Theme visibility requires real booleans')
            elif key == 'hero_spacing':
                if value not in ('Small', 'Medium', 'Large'):
                    raise Stop('Uncaptured course hero spacing')
            else:
                _text(value, key, TEXT_LIMITS[key], empty=key != 'template_title' and key not in FONT_FIELDS)
    if 'template_title' in expected and expected['template_title'] != inputs['expected_template_title']:
        raise Stop('Conflicting inventoried template titles')
    _manager_parts(inputs['start_url'], inputs)
    plan = deepcopy(inputs)
    for values in (plan['changes'],plan['expected_values']):
        if 'layout_palette' in values:
            values['layout_palette'] = _palette(values['layout_palette'])
    return plan


def validate(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'payload'}
            or step.get('action', 'native_course_theme') != 'native_course_theme'):
        raise Stop('Unsupported course theme runner metadata')
    return validate_inputs(step.get('payload'))


def configuration_hash(inputs):
    plan = validate_inputs(inputs)
    bound = {key:plan[key] for key in ('location_id', *sorted(INPUTS))}
    return hashlib.sha256(json.dumps(bound, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _manager_parts(url, plan):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        raise Stop('Malformed course Customize manager URL') from None
    path = '/v2/location/' + plan['location_id'] + '/memberships/courses/course-creator-studio'
    query = parse_qsl(parsed.query, keep_blank_values=True)
    expected = [('view', 'manager'), ('sub_view', 'customize'), ('product_id', plan['course_id'])]
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or port not in (None, 443)
            or parsed.fragment or parsed.path != path or sorted(query) != sorted(expected)):
        raise Stop('Course theme start URL must identify its exact Customize manager')
    return parsed


def editor_url(plan):
    origin = _manager_parts(plan['start_url'], plan)
    return (origin.scheme + '://' + origin.netloc + '/v2/location/' + plan['location_id']
            + '/memberships/courses/themes-overview/' + plan['course_id']
            + '/edit/template/' + plan['template_id'])


def _one(locator, message):
    if locator.count() != 1 or not locator.is_visible():
        raise Stop(message)
    return locator


def _section(page, name):
    return _one(page.locator('section').filter(has=page.get_by_text(name, exact=True)),
                'Course template inventory section changed')


def _inventory(page, plan):
    if page.url != plan['start_url']:
        page.goto(plan['start_url'], wait_until='domcontentloaded', timeout=45000)
    page.get_by_text('My Templates', exact=True).wait_for(state='visible', timeout=45000)
    assert_tenant(page, plan)
    _manager_parts(page.url, plan)
    active = _section(page, 'Current Theme').locator('.template-card')
    _one(active, 'Current course theme identity is ambiguous')
    _one(active.get_by_text('Active', exact=True), 'Current course theme is not independently identified')
    active_state = (active.get_attribute('id'), active.locator('[id^="template-title-"]').inner_text())
    owned = _section(page, 'My Templates')
    card = _one(owned.locator('#template-card-' + plan['template_id']),
                'Requested existing template is missing or not owned by this course inventory')
    title = _one(card.locator('#template-title-' + plan['template_id']),
                 'Native template title identity changed').inner_text()
    if (card.get_by_text('Active', exact=True).count()
            or active.get_attribute('id') == 'template-card-' + plan['template_id']):
        raise Stop('This handler edits inactive templates only; activation requires a separate operation')
    _one(card.get_by_role('button', name='Apply', exact=True), 'Inactive template marker changed')
    return card, title, active_state


def _open(page, plan, title):
    card, actual, active = _inventory(page, plan)
    if actual != title:
        raise Stop('Template inventory differs from its expected title')
    click(card.get_by_role('button', name='Customize', exact=True))
    wait_until(lambda: page.url == editor_url(plan), 'Template editor did not open the requested identity')
    page.get_by_placeholder('Template title', exact=True).wait_for(state='visible', timeout=45000)
    _identity(page, plan)
    return active


def _identity(page, plan):
    if page.url != editor_url(plan):
        raise Stop('Course template editor changed identity')
    _one(page.get_by_placeholder('Template title', exact=True), 'Template editor identity is missing')
    _one(page.get_by_role('button', name='Activate Template', exact=True), 'Unexpected course template editor')


def _panel(page, plan, name, subsection=None):
    _identity(page, plan)
    click(page.get_by_role('button', name=name, exact=True))
    if subsection == 'Instructor':
        click(page.locator('#instructorBlock').get_by_text('Instructor', exact=True))
    elif subsection:
        # The captured tabs can retain an expanded subsection. Clicking its
        # heading again would close it and hide the very fields being edited.
        expanded_field = {'Search':'Placeholder Text', 'Course Info':'Course Title',
                          'Progress Block':'Text'}.get(subsection)
        labels = page.locator('.n-form-item-label__text').filter(
            has_text=re.compile(r'^\s*' + re.escape(expanded_field or '') + r'\s*$'))
        if not expanded_field or labels.count() != 1 or not labels.is_visible():
            click(page.get_by_text(subsection, exact=True))
    _identity(page, plan)


def _field(page, label):
    labels = page.locator('.n-form-item-label__text').filter(
        has_text=re.compile(r'^\s*' + re.escape(label) + r'\s*$'))
    row = _one(page.locator('.n-form-item').filter(has=labels), 'Course theme field label changed: ' + label)
    return _one(row.get_by_role('textbox'), 'Course theme field is ambiguous: ' + label)


def _radios(page, label, margin):
    return _one(page.locator('div.h-full.w-full.' + margin).filter(
        has=page.get_by_text(label, exact=True)), 'Theme radio group changed: ' + label)


def _read_radio(row, values):
    if row.get_by_role('radio').count() != len(values):
        raise Stop('Theme radio choice inventory changed')
    selected = [value for value in values if _one(row.get_by_role('radio', name=value, exact=True),
                'Theme radio label changed').is_checked()]
    if len(selected) != 1:
        raise Stop('Theme radio state is ambiguous')
    return selected[0]


def _controls(page, plan, group):
    if group == 'title':
        return {'template_title':page.get_by_placeholder('Template title', exact=True)}, {}
    if group == 'header':
        _panel(page, plan, 'Header', 'Search')
        return {'search_placeholder':_field(page, 'Placeholder Text')}, {}
    if group == 'hero':
        _panel(page, plan, 'Hero', 'Course Info')
        return {key:_field(page, label) for key, label in (
            ('hero_title', 'Course Title'), ('hero_description', 'Course Description'),
            ('start_button_text', 'Button Text'))}, {
                'hero_spacing':(_radios(page, 'Vertical spacing', 'mb-3'), ('Small', 'Medium', 'Large'))}
    if group == 'progress':
        _panel(page, plan, 'Sidebar', 'Progress Block')
        return {'progress_text':_field(page, 'Text')}, {
            'progress_visible':(_radios(page, 'Progress bar', 'mb-4'), ('Show', 'Hide'))}
    _panel(page, plan, 'Sidebar', 'Instructor')
    return {key:_field(page, label) for key, label in (
        ('instructor_heading', 'Heading'), ('instructor_name', 'Name'),
        ('instructor_title', 'Title'), ('instructor_bio', 'Bio'))}, {
            'instructor_visible':(_radios(page, 'Visibility', 'mb-4'), ('Show', 'Hide')),
            'headshot_visible':(_radios(page, 'Headshot', 'mb-4'), ('Show', 'Hide'))}


GROUPS = ('title', 'header', 'hero', 'progress', 'instructor')


def _layout_section(page, plan, identity, title, *, expanded_selector):
    _panel(page, plan, 'Layout')
    section = _one(page.locator('#' + identity), 'Native course Layout section changed: ' + title)
    probe = section.locator(expanded_selector)
    if not probe.count() or not probe.first.is_visible():
        click(section.locator('.n-collapse-item__header-main'))
    _identity(page, plan)
    return section


def _palette_controls(page, plan):
    section = _layout_section(page,plan,'colorTheme','Color Theme',
                              expanded_selector='[role="button"][aria-label="Brand color picker"]')
    if (section.get_by_text('Base Colors',exact=True).count() != 1
            or section.get_by_text('Accent Colors',exact=True).count() != 1):
        raise Stop('Native base/accent palette labels changed')
    controls = section.get_by_role('button',name='Brand color picker',exact=True)
    if controls.count() != 6:
        raise Stop('Native course palette order/count changed')
    return controls


def _swatch(control):
    swatch = _one(control.locator('.brand-color-value'), 'Native course palette swatch changed')
    value = swatch.evaluate('(element) => element.style.backgroundColor')
    match = re.fullmatch(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(0(?:\.\d+)?|1(?:\.0+)?))?\s*\)', value or '')
    if not match or any(int(part) > 255 for part in match.groups()[:3]):
        raise Stop('Native course palette no longer exposes a captured RGB color')
    channels = [int(part) for part in match.groups()[:3]]
    alpha = match[4]
    channels.append(int(float(alpha) * 255 + .5) if alpha is not None else 255)
    return '#' + ''.join(format(channel,'02X') for channel in channels)


def _palette_snapshot(page, plan):
    controls = _palette_controls(page,plan)
    colors = [_swatch(controls.nth(index)) for index in range(6)]
    return {'base':colors[:2], 'accent':colors[2:]}


def _font_controls(page, plan):
    section = _layout_section(page,plan,'textTheme','Text Theme',expanded_selector='.n-base-selection')
    if section.locator('.n-base-selection').count() != 4:
        raise Stop('Native primary/secondary font selector inventory changed')
    controls = {}
    for prefix,label in (('primary','Primary Font'),('secondary','Secondary Font')):
        heading = _one(section.get_by_text(label,exact=True), 'Native course font group label changed')
        row = _one(heading.locator('xpath:../..'), 'Native course font group changed')
        if not {'h-full','w-full'}.issubset(set((row.get_attribute('class') or '').split())):
            raise Stop('Native course font group container changed')
        selections = row.locator('.n-base-selection')
        if selections.count() != 2:
            raise Stop('Native font family/weight pairing changed')
        controls[prefix+'_font'], controls[prefix+'_weight'] = selections.nth(0), selections.nth(1)
    return controls


def _selected_font(control):
    label = _one(control.locator('.n-base-selection-label'), 'Native course font value changed')
    return _text(label.inner_text().strip(),'selected font value',128)


def _font_snapshot(page, plan):
    return {key:_selected_font(control) for key,control in _font_controls(page,plan).items()}


def _option(page, value):
    paragraph = page.locator('p').filter(has_text=re.compile(r'^\s*' + re.escape(value) + r'\s*$'))
    option = page.locator('.n-base-select-option').filter(has=paragraph)
    wait_until(lambda: option.count() == 1 and option.is_visible(),
               'Requested font or weight is not available in the native selector')
    return _one(option,'Native font selection is ambiguous')


def _font_preflight(page, plan, before, desired):
    """Prove requested families exist without selecting or saving anything."""
    controls = _font_controls(page,plan)
    for prefix in ('primary','secondary'):
        family,weight = prefix+'_font',prefix+'_weight'
        control = controls[family]
        if family in plan['changes'] and desired[family] != before[family]:
            click(control)
            search = _one(control.get_by_role('textbox'),'Native font search input changed')
            fill(search,desired[family])
            _option(page,desired[family])
            search.press('Escape')
            if _selected_font(control) != before[family]:
                raise Stop('Font availability inspection unexpectedly changed the selected family')
        # A future family's available weights are checked after its selection,
        # before Save. For an unchanged family they can be proved read-only now.
        if desired[family] == before[family] and weight in plan['changes'] and desired[weight] != before[weight]:
            click(controls[weight])
            _option(page,desired[weight])
            click(controls[weight])
            if _selected_font(controls[weight]) != before[weight]:
                raise Stop('Font availability inspection unexpectedly changed the selected weight')
    _identity(page,plan)


def _apply_fonts(page, plan, before, desired):
    controls = _font_controls(page,plan)
    if any(_selected_font(control) != before[key] for key,control in controls.items()):
        raise Stop('Native course font values changed after the full preflight')
    # Family selection may reset its weight. Restore the inventoried weight
    # unless the caller requested another available native weight explicitly.
    for suffix in ('font','weight'):
        for prefix in ('primary','secondary'):
            key = prefix+'_'+suffix
            control = controls[key]
            if _selected_font(control) == desired[key]:
                continue
            _identity(page,plan)
            click(control)
            if suffix == 'font':
                search = _one(control.get_by_role('textbox'),'Native font search input changed')
                fill(search,desired[key])
            click(_option(page,desired[key]))
            wait_until(lambda: _selected_font(control) == desired[key],
                       'Native course font selection did not persist in the editor')


def _apply_palette(page, plan, before, desired):
    controls = _palette_controls(page,plan)
    actual = [_swatch(controls.nth(index)) for index in range(6)]
    if actual != before['base'] + before['accent']:
        raise Stop('Native course palette changed after the full preflight')
    colors = desired['base'] + desired['accent']
    for index,value in enumerate(colors):
        trigger = controls.nth(index)
        if _swatch(trigger) == value:
            continue
        _identity(page,plan)
        click(trigger)
        # Add belongs to the Default palette, not the global Add Brand Colors
        # action. The latter is never invoked by this template handler.
        click(_one(page.get_by_role('button',name='Add',exact=True),'Native Default palette Add changed'))
        hexadecimal = _one(page.get_by_placeholder('HEX',exact=True),'Native HEX palette input changed')
        fill(hexadecimal,value)
        if _hexa(hexadecimal.input_value()) != value:
            raise Stop('Native palette HEX input ignored the requested color')
        hexadecimal.press('Tab')
        if hexadecimal.count() == 1 and hexadecimal.is_visible():
            hexadecimal.press('Escape')
        # Escape closes the custom HEX editor, but not its surrounding palette.
        # Toggle this exact trigger closed before touching another control.
        palette = page.get_by_text('Brand Colors',exact=True)
        if palette.count() == 1 and palette.is_visible():
            click(trigger)
        if _swatch(trigger) != value:
            raise Stop('Native course palette swatch differs from the requested HEXA color')


def _snapshot(page, plan):
    state = {'layout_palette':_palette_snapshot(page,plan), **_font_snapshot(page,plan)}
    for group in GROUPS:
        text, radios = _controls(page, plan, group)
        for key, control in text.items():
            state[key] = _one(control, 'Course theme input changed').input_value()
        for key, (row, choices) in radios.items():
            selected = _read_radio(row, choices)
            state[key] = selected == 'Show' if key in VISIBILITY else selected
    return state


def configure(page, step):
    plan = validate(step)
    before_active = _open(page, plan, plan['expected_template_title'])
    before = _snapshot(page, plan)
    if before['template_title'] != plan['expected_template_title'] or any(
            before[key] != value for key, value in plan['expected_values'].items()):
        raise Stop('Course theme inputs are stale; refresh the inventory before editing')
    desired = {**before, **plan['changes']}
    if FONT_FIELDS.intersection(plan['changes']):
        _font_preflight(page,plan,before,desired)
    for group in GROUPS:
        text, radios = _controls(page, plan, group)
        for key, control in text.items():
            if key in plan['changes'] and control.input_value() != desired[key]:
                _identity(page, plan)
                fill(control, desired[key])
                control.press('Tab')
                if control.input_value() != desired[key]:
                    raise Stop('Native theme input ignored an authored value')
        for key, (row, choices) in radios.items():
            if key in plan['changes']:
                value = ('Show' if desired[key] else 'Hide') if key in VISIBILITY else desired[key]
                if _read_radio(row, choices) != value:
                    _identity(page, plan)
                    click(row.get_by_role('radio', name=value, exact=True))
                if _read_radio(row, choices) != value:
                    raise Stop('Native theme radio ignored an authored value')
    if 'layout_palette' in plan['changes']:
        _apply_palette(page,plan,before['layout_palette'],desired['layout_palette'])
    if FONT_FIELDS.intersection(plan['changes']):
        _apply_fonts(page,plan,before,desired)
    if _snapshot(page, plan) != desired:
        raise Stop('Course theme desired state or protected text/visibility changed before Save')
    _identity(page, plan)
    save = _one(page.get_by_role('button', name='Save', exact=True), 'Native template Save changed')
    if desired != before:
        if not save.is_enabled():
            raise Stop('Course template changes did not enable Save')
        click(save)
        wait_until(lambda: not save.is_enabled(), 'Course template save has not settled')
        # Disabled can mean an in-flight save as well as a clean editor. Let
        # outstanding requests settle before leaving; only the independent
        # inventory/editor read-back below establishes persisted completion.
        try:
            page.wait_for_load_state('networkidle', timeout=45000)
        except Exception:
            raise Stop('Course template save is still unsettled; reconcile before another write') from None
    elif save.is_enabled():
        raise Stop('Unrelated unsaved template changes require reconciliation')
    # Return through the native course inventory, then open the exact existing ID.
    after_active = _open(page, plan, desired['template_title'])
    if after_active != before_active or _snapshot(page, plan) != desired:
        raise Stop('Course theme independent read-back failed or the active theme changed')
    return {'status':'COURSE_THEME_SAVED_AND_REOPENED', 'editor_url':page.url,
        'course_id':plan['course_id'], 'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan), 'independent_readback':'VERIFIED',
        'functional_verified':False, 'activation_performed':False}
