"""Native assessment field edits and independent branch/score validation.

Field controls were inspected in form-builder-app on 2026-11-08. This module
never invents survey/quiz scoring selectors; validate_model and evaluate_model
provide exact expected behavior for their independent submission checks.
"""
from copy import deepcopy
import re
import hashlib
from urllib.parse import urlsplit


STANDARD_FIELDS = {
    'First Name': ('Enter your first name', 'first_name'),
    'Last Name': ('Enter your last name', 'last_name'),
    'Phone': ('+1 (555) 000-0000', 'phone'),
    'Email': ('your@email.com', 'email'),
}
# Only the complete native simple-field property layout has been captured here.
# Keep STANDARD_FIELDS separate: condition menus have their own narrower capture.
SIMPLE_FIELDS = {**STANDARD_FIELDS,
    'Full Name': ('Enter your full name', 'full_name'),
    'Organization': ('Enter your organization', 'organization'),
    'Website': ('https://yourwebsite.com', 'website'),
    'Date of birth': ('DD / MM / YYYY', 'date_of_birth'),
    'City': ('Enter your city', 'city'),
    'State': ('Enter your state', 'state'),
    'Country': ('Enter your country', 'country'),
    'Postal Code': ('ZIP or postal code', 'postal_code'),
}
SIMPLE_FIELD_TYPES = {name: ('email' if name == 'Email' else
    'date' if name == 'Date of birth' else 'select' if name == 'Country' else 'text')
    for name in SIMPLE_FIELDS}
FIELD_WRAPPER = 'xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " form-field-wrapper ") and parent::*[@id="form-builder-container"]][1]'
PROPERTIES = ('label', 'placeholder', 'short_label', 'query_key', 'width_pct')


class AssessmentError(ValueError):
    pass


def reopen_editor(page, kind, name, editor_url):
    """Independent list read-back without relying on browser history.

    Native Back returns about:blank when a host starts at a direct editor URL.
    These list routes were captured in the corresponding native builders.
    """
    if __package__:
        from .skill6_playwright import exact_search, click, Stop
    else:
        from skill6_playwright import exact_search, click, Stop
    if kind not in ('form', 'survey', 'quiz'):
        raise AssessmentError('Unknown native editor kind')
    parsed = urlsplit(editor_url)
    match = re.fullmatch(r'/v2/location/([A-Za-z0-9_-]+)/' + kind + r'-builder-v2/[A-Za-z0-9_-]+/?', parsed.path)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment or not match:
        raise Stop('Native editor identity is not a captured exact HTTPS route')
    list_url = parsed.scheme + '://' + parsed.netloc + '/v2/location/' + match.group(1) + '/' + kind + '-builder/main'
    page.goto(list_url, wait_until='domcontentloaded', timeout=45000)
    cell = exact_search(page, kind + ('zes' if kind == 'quiz' else 's'), name)
    if cell is None:
        raise Stop('Saved ' + kind + ' absent from independent list read-back')
    click(cell.get_by_text(name, exact=True))
    title = page.frame_locator('iframe[name="' + kind + '-builder-app"]').get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    if page.url != editor_url or title.input_value() != name:
        raise Stop('Reopened native editor identity changed')


def validate_css(step):
    if not isinstance(step, dict) or set(step) - {'id', 'action', 'custom_css', 'css_key', 'expect_styles'}:
        raise AssessmentError('Unsupported native CSS configuration option')
    css = step.get('custom_css')
    if not isinstance(css, str) or not css.strip():
        raise AssessmentError('Approved custom CSS text is required')
    key = step.get('css_key', 'approved-css')
    if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9_-]+', key):
        raise AssessmentError('CSS key must be a simple lowercase identifier')
    if 'ZHC-SKILL6-APPROVED-CSS-' in css:
        raise AssessmentError('CSS text contains a reserved ownership marker')
    checks = step.get('expect_styles', [])
    if not isinstance(checks, list):
        raise AssessmentError('Computed style checks must be a list')
    for check in checks:
        if not isinstance(check, dict) or set(check) != {'selector', 'count', 'properties'}:
            raise AssessmentError('Each style check needs an exact selector/count/property mapping')
        if not isinstance(check['selector'], str) or not check['selector'] or type(check['count']) is not int or check['count'] < 1:
            raise AssessmentError('Style check selector and positive element count are required')
        if not isinstance(check['properties'], dict) or not check['properties'] or any(
            not isinstance(k, str) or not re.fullmatch(r'--?[a-z][a-z0-9-]*|[a-z][a-z0-9-]*', k)
            or not isinstance(v, str) for k, v in check['properties'].items()):
            raise AssessmentError('Style properties must be explicit CSS property/value strings')
    return deepcopy(step)


def merge_css(existing, step):
    """Replace only this operation's owned block; preserve other client CSS."""
    step = validate_css(step)
    key = step.get('css_key', 'approved-css')
    begin = '/* ZHC-SKILL6-APPROVED-CSS-' + key + '-BEGIN */'
    end = '/* ZHC-SKILL6-APPROVED-CSS-' + key + '-END */'
    if not isinstance(existing, str):
        raise AssessmentError('Existing native CSS was not readable text')
    if existing.count(begin) != existing.count(end) or existing.count(begin) > 1:
        raise AssessmentError('Existing owned CSS markers are ambiguous; reconcile before replacement')
    if begin in existing and existing.index(end) < existing.index(begin):
        raise AssessmentError('Existing CSS ownership markers are out of order')
    css = step['custom_css'].replace('\r\n', '\n').replace('\r', '\n').strip()
    block = begin + '\n' + css + '\n' + end
    if begin in existing:
        return re.sub(re.escape(begin) + r'.*?' + re.escape(end), lambda _: block, existing, flags=re.S)
    return existing + ('\n' if existing and not existing.endswith('\n') else '') + block + '\n'


def configure_css(page, step):
    """Install approved native form CSS, reopen it and check requested rendering."""
    if __package__:
        from .skill6_playwright import click, fill, form_builder, visible, wait_until, Stop
    else:
        from skill6_playwright import click, fill, form_builder, visible, wait_until, Stop
    step = validate_css(step)
    frame = form_builder(page)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    name, editor_url = title.input_value(), page.url

    def close_initial():
        close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
        if visible(close):
            click(close)

    def open_css():
        advanced = frame.get_by_text('Advanced', exact=True)
        if not visible(advanced):
            click(frame.get_by_role('button', name='Styles & Options', exact=True))
        click(advanced)
        click(frame.get_by_text('Custom CSS', exact=True))
        pane = frame.get_by_role('dialog').filter(has_text='Custom CSS')
        editor = pane.get_by_role('textbox')
        if pane.count() != 1 or editor.count() != 1:
            raise Stop('Native Custom CSS editor changed')
        editor.wait_for(state='visible', timeout=45000)
        return pane, editor

    def content(editor):
        value = editor.evaluate("el => el.value ?? el.innerText ?? ''")
        if not isinstance(value, str):
            raise Stop('Native CSS editor content could not be read')
        return value

    close_initial()
    pane, editor = open_css()
    expected = merge_css(content(editor), step)
    fill(editor, expected)
    click(pane.get_by_role('button', name='Close', exact=True))
    click(frame.get_by_role('button', name='Save', exact=True))
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).count() == 1
               and frame.get_by_role('button', name='Save', exact=True).is_enabled(), 'Native CSS save did not finish')
    reopen_editor(page, 'form', name, editor_url)
    close_initial()
    pane, editor = open_css()
    if content(editor) != expected:
        raise Stop('Native form CSS did not persist exactly')
    click(pane.get_by_role('button', name='Close', exact=True))
    if step.get('expect_styles'):
        with page.context.expect_page(timeout=45000) as event:
            click(frame.get_by_role('button', name='Preview', exact=True))
        preview = event.value
        try:
            preview.wait_for_load_state('domcontentloaded')
            for check in step['expect_styles']:
                elements = preview.locator(check['selector'])
                elements.first.wait_for(state='visible', timeout=45000)
                if elements.count() != check['count']:
                    raise Stop('Native styled element count differs from request')
                for prop, value in check['properties'].items():
                    observed = elements.evaluate_all('(els, property) => els.map(el => getComputedStyle(el).getPropertyValue(property).trim())', prop)
                    if len(observed) != check['count'] or any(actual != value for actual in observed):
                        raise Stop('Native form computed CSS property differs: ' + prop)
        finally:
            preview.close()
    return {'status': 'NATIVE_FORM_CSS_SAVED_AND_REOPENED', 'editor_url': page.url,
            'css_sha256': hashlib.sha256(expected.encode()).hexdigest(),
            'render_checks': len(step.get('expect_styles', [])), 'submission_verified': False}


def validate_fields(step):
    if not isinstance(step, dict) or set(step) - {'id', 'action', 'fields'}:
        raise AssessmentError('Unsupported native field configuration option')
    if 'action' in step and step['action'] != 'native_fields':
        raise AssessmentError('Native field action does not match this handler')
    fields = step.get('fields')
    if not isinstance(fields, list) or not fields:
        raise AssessmentError('fields must be a nonempty list')
    seen = set()
    result = deepcopy(step)
    for field in result['fields']:
        if not isinstance(field, dict) or field.get('field') not in SIMPLE_FIELDS:
            raise AssessmentError('Only captured simple native fields are supported')
        if field['field'] in seen:
            raise AssessmentError('Duplicate field edit')
        seen.add(field['field'])
        if set(field) - {'field', *PROPERTIES, 'required', 'hidden', 'hidden_value', 'current_placeholder', 'current_query_key'}:
            raise AssessmentError('Unknown field property')
        if not set(field).intersection({*PROPERTIES, 'required', 'hidden', 'hidden_value'}):
            raise AssessmentError('A field edit must change at least one property')
        if ('current_placeholder' in field) != ('current_query_key' in field):
            raise AssessmentError('Current field anchor requires both placeholder and query key')
        for key in ('current_placeholder', 'current_query_key'):
            if key in field and (not isinstance(field[key], str) or not field[key].strip()):
                raise AssessmentError('Current field anchors must be nonempty text')
        for key in ('required', 'hidden'):
            if key in field and type(field[key]) is not bool:
                raise AssessmentError(key + ' must be a boolean')
        if field.get('required') and field.get('hidden'):
            raise AssessmentError('A field cannot be required and hidden')
        if 'hidden_value' in field and (not isinstance(field['hidden_value'], str) or field.get('hidden') is not True):
            raise AssessmentError('Hidden value requires explicit hidden:true and a text value')
        for key in PROPERTIES[:-1]:
            if key in field and not isinstance(field[key], str):
                raise AssessmentError(key + ' must be text')
        if 'placeholder' in field and not field['placeholder'].strip():
            raise AssessmentError('Placeholder must remain an unambiguous field anchor')
        if 'label' in field and not field['label'].strip():
            raise AssessmentError('Field label cannot be empty')
        for key in ('query_key', 'current_query_key'):
            if key in field and (not field[key].strip() or len(field[key]) > 256
                    or any(char.isspace() or ord(char) < 32 for char in field[key])):
                raise AssessmentError('Field query keys must be nonempty tokens without whitespace')
        if 'width_pct' in field and (type(field['width_pct']) is not int or not 1 <= field['width_pct'] <= 100):
            raise AssessmentError('Field width must be an integer from 1 to 100')
    # Reject collisions before any browser access. In particular, swaps would
    # make the next field ambiguous during the unsaved intermediate state.
    for prop, current, offset in (('placeholder', 'current_placeholder', 0),
                                  ('query_key', 'current_query_key', 1)):
        old = {name: values[offset] for name, values in SIMPLE_FIELDS.items()}
        for field in result['fields']:
            old[field['field']] = field.get(current, old[field['field']])
        if len(set(old.values())) != len(old):
            raise AssessmentError('Current field ' + prop + ' identities must remain unique')
        final = dict(old)
        for field in result['fields']:
            name, value = field['field'], field.get(prop, old[field['field']])
            if any(value == previous for other, previous in old.items() if other != name):
                raise AssessmentError('Edited field ' + prop + ' collides with another current identity')
            final[name] = value
        if len(set(final.values())) != len(final):
            raise AssessmentError('Edited field ' + prop + ' identities must remain unique')
    return result


def configure_fields(page, step):
    """Edit captured native simple-field properties with complete preflight.

    Composite Address child properties and custom schemas remain separate rails.
    The parent runner supplies tenant checks and intent-before-mutation state.
    All requested native identities and resulting booleans are checked before the
    first property write; Save is attempted once, followed by exact list reopen.
    """
    if __package__:
        from .skill6_playwright import click, fill, form_builder, wait_until, Stop
    else:
        from skill6_playwright import click, fill, form_builder, wait_until, Stop
    step = validate_fields(step)
    frame = form_builder(page)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    if title.count() != 1:
        raise Stop('Native form title is missing or ambiguous')
    name, editor_url = title.input_value(), page.url
    if not isinstance(name, str) or not name.strip():
        raise Stop('Saved native form identity is unavailable')

    def close_drawer():
        dialog = frame.get_by_role('dialog')
        if not dialog.count():
            return
        if dialog.count() != 1 or dialog.get_by_text('Form Element', exact=True).count() != 1:
            raise Stop('Unexpected native form dialog requires reconciliation')
        close = dialog.get_by_role('button', name='Close', exact=True)
        if close.count() != 1:
            raise Stop('Native Form Element Close control changed')
        click(close)

    def panel(field, placeholder):
        close_drawer()
        click(frame.get_by_role('tab', name='Edit', exact=True))
        target = frame.get_by_placeholder(placeholder, exact=True)
        if target.count() != 1:
            raise Stop('Field anchor is absent or ambiguous: ' + field['field'])
        wrapper = target.locator(FIELD_WRAPPER)
        kind = wrapper.locator('[data-field-type]')
        if (wrapper.count() != 1 or kind.count() != 1
                or kind.get_attribute('data-field-type') != SIMPLE_FIELD_TYPES[field['field']]
                or wrapper.locator('input').count() != 1):
            raise Stop('Field anchor belongs to a different native type or composite group')
        click(target)
        if SIMPLE_FIELD_TYPES[field['field']] in ('date', 'select'):
            target.press('Escape', timeout=45000)
        gear = wrapper.locator('[aria-label="Open settings"]')
        click(gear)
        frame.get_by_text('General Settings', exact=True).wait_for(state='visible', timeout=45000)
        inputs = frame.get_by_role('textbox', name='Please Input', exact=True)
        hidden = frame.get_by_role('checkbox', name='Hidden', exact=True)
        required = frame.get_by_role('checkbox', name='Required', exact=True)
        if hidden.count() != 1 or required.count() != 1:
            raise Stop('Native field boolean controls changed')
        expected_count = 6 if hidden.is_checked() else 5
        if inputs.count() != expected_count:
            raise Stop('Native field property panel changed; capture required')
        for index, label in enumerate(('Label', 'Placeholder', 'Short Label', 'Query Key', 'Field Width')):
            row = inputs.nth(index).evaluate("el => el.closest('.form-group')?.textContent || ''")
            suffix = r'(?:\s*Please Input)?' if label == 'Short Label' else r'\s*%?' if label == 'Field Width' else ''
            if not isinstance(row, str) or not re.fullmatch(r'\s*' + re.escape(label) + suffix + r'\s*', row):
                raise Stop('Native field property order changed; capture required')
        if expected_count == 6 and 'hidden value' not in inputs.nth(5).evaluate("el => el.closest('.form-group')?.textContent || ''").casefold():
            raise Stop('Native hidden value control changed')
        return inputs, required, hidden

    def close_panel():
        backs = frame.get_by_role('button', name='Back', exact=True)
        if backs.count() != 2:
            raise Stop('Native field panel Back controls changed')
        click(backs.nth(1))

    # Read-only selection of every requested target before touching properties.
    plans = []
    for field in step['fields']:
        default_placeholder, default_key = SIMPLE_FIELDS[field['field']]
        old_placeholder = field.get('current_placeholder', default_placeholder)
        key = field.get('current_query_key', default_key)
        inputs, required, hidden = panel(field, old_placeholder)
        new_placeholder = field.get('placeholder', old_placeholder)
        if new_placeholder != old_placeholder and frame.get_by_placeholder(new_placeholder, exact=True).count():
            raise Stop('New field placeholder is already present in the native editor')
        before = [inputs.nth(i).input_value() for i in range(inputs.count())]
        if before[3] != key:
            raise Stop('Native field identity differs from captured query key')
        booleans = (required.is_checked(), hidden.is_checked())
        wanted = (field.get('required', booleans[0]), field.get('hidden', booleans[1]))
        if wanted[0] and wanted[1]:
            raise Stop('Requested field would become required and hidden')
        plans.append((field, before, booleans, wanted))
        close_panel()

    # Query keys can be renamed on unrequested fields, including custom text
    # fields. Static canonical names cannot establish that a new key is free.
    query_inventory = None
    if any('query_key' in field and field['query_key'] != before[3]
            for field, before, _, _ in plans):
        if __package__:
            from .field_placement import _inventory
        else:
            from field_placement import _inventory
        query_inventory = _inventory(frame, allow_unknown_queries=True)
        for field, before, _, _ in plans:
            key, wanted_key = before[3], field.get('query_key', before[3])
            if query_inventory.get(key) != SIMPLE_FIELD_TYPES[field['field']]:
                raise Stop('Native query inventory differs from the requested field identity')
            if wanted_key != key:
                if wanted_key in query_inventory:
                    raise Stop('New query key already belongs to an existing native field')
                query_inventory[wanted_key] = query_inventory.pop(key)

    expected = []
    for field, before, booleans, wanted in plans:
        inputs, required, hidden = panel(field, before[1])
        if ([inputs.nth(i).input_value() for i in range(inputs.count())] != before
                or (required.is_checked(), hidden.is_checked()) != booleans):
            raise Stop('Native field changed after preflight; reconcile before editing')
        wanted_required, wanted_hidden = wanted
        # Expected state is authored overrides plus the preflight baseline,
        # never whatever a framework happened to retain after fill().
        desired_values = [str(field[prop]) if prop in field else before[index]
                          for index, prop in enumerate(PROPERTIES)]
        desired_hidden = (field['hidden_value'] if 'hidden_value' in field else
                          before[5] if len(before) == 6 else None)
        # Turn exclusions off before enabling either side, preserving the rule
        # even during intermediate states. Avoid touching unchanged switches.
        if not wanted_required and required.is_checked():
            required.set_checked(False)
        if not wanted_hidden and hidden.is_checked():
            hidden.set_checked(False)
            wait_until(lambda: inputs.count() == 5, 'Hidden value control did not close')
        for index, prop in enumerate(PROPERTIES):
            if prop in field and inputs.nth(index).input_value() != desired_values[index]:
                fill(inputs.nth(index), desired_values[index])
            if inputs.nth(index).input_value() != desired_values[index]:
                raise Stop('Native field property did not accept the authored or preserved value: ' + prop)
        if wanted_required and not required.is_checked():
            required.set_checked(True)
        if wanted_hidden:
            if not hidden.is_checked():
                hidden.set_checked(True)
            wait_until(lambda: inputs.count() == 6, 'Hidden value control did not appear')
            if 'hidden value' not in inputs.nth(5).evaluate("el => el.closest('.form-group')?.textContent || ''").casefold():
                raise Stop('Native hidden value control changed')
            # A newly exposed, unrequested default was not visible during
            # preflight. Preserve it as found; authored defaults always take
            # precedence and can never be learned from a failed fill.
            if desired_hidden is None:
                desired_hidden = inputs.nth(5).input_value()
            if 'hidden_value' in field:
                fill(inputs.nth(5), desired_hidden)
            if inputs.nth(5).input_value() != desired_hidden:
                raise Stop('Native field hidden value did not accept the authored or preserved value')
            desired_values.append(desired_hidden)
        if ([inputs.nth(i).input_value() for i in range(inputs.count())] != desired_values
                or (required.is_checked(), hidden.is_checked()) != wanted):
            raise Stop('Native field properties differ from the authored or preserved target before Save')
        expected.append((field, desired_values, wanted_required, wanted_hidden))
        close_panel()
    close_drawer()
    if query_inventory is not None and _inventory(frame, allow_unknown_queries=True) != query_inventory:
        raise Stop('Native field query inventory changed during editing')
    click(frame.get_by_role('button', name='Save', exact=True))
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).count() == 1
               and frame.get_by_role('button', name='Save', exact=True).is_enabled(), 'Form save did not finish')
    reopen_editor(page, 'form', name, editor_url)
    frame = form_builder(page)
    if query_inventory is not None and _inventory(frame, allow_unknown_queries=True) != query_inventory:
        raise Stop('Saved native field query inventory did not persist')
    for field, values, required, hidden in expected:
        inputs, actual_required, actual_hidden = panel(field, values[1])
        if [inputs.nth(i).input_value() for i in range(inputs.count())] != values:
            raise Stop('Field properties did not persist: ' + field['field'])
        if actual_required.is_checked() != required or actual_hidden.is_checked() != hidden:
            raise Stop('Field booleans did not persist: ' + field['field'])
        close_panel()
    close_drawer()
    return {'status': 'FIELD_PROPERTIES_SAVED_AND_REOPENED', 'editor_url': page.url,
            'fields': [f['field'] for f in step['fields']], 'submission_verified': False}


def validate_condition(step):
    """Single-target Hide/Show Field effects; plural effects remain uncaptured."""
    if not isinstance(step, dict) or set(step) - {'id', 'action', 'effect', 'if_field', 'operator', 'value', 'target'}:
        raise AssessmentError('Unsupported native condition configuration option')
    if 'action' in step and step['action'] not in ('native_condition', 'Hide Field', 'Show Field'):
        raise AssessmentError('Uncaptured condition action')
    allowed = {'First Name', 'Last Name', 'Phone', 'Email', 'TnC1', 'TnC2'}
    if step.get('if_field') not in allowed or step.get('target') not in allowed | {'Privacy Policy | Terms of Service'}:
        raise AssessmentError('Condition fields must match captured native labels')
    operators = {'Is Equal To', 'Is Not Equal To', 'Contains', 'Does Not Contain',
                 'Starts With', 'Ends With', 'Is Empty', 'Is Filled'}
    if step.get('operator') not in operators:
        raise AssessmentError('Uncaptured condition operator')
    legacy = step.get('action') if step.get('action') in ('Hide Field', 'Show Field') else None
    effect = step.get('effect', legacy or 'Hide Field')
    if effect not in ('Hide Field','Show Field') or (legacy is not None and legacy != effect):
        raise AssessmentError('Conflicting or uncaptured single-field condition effect')
    unary = step['operator'] in {'Is Empty', 'Is Filled'}
    if not unary and (not isinstance(step.get('value'), str) or not step['value']):
        raise AssessmentError('This condition operator requires an explicit text value')
    if unary and 'value' in step:
        raise AssessmentError('Unary condition must not carry an ignored value')
    return deepcopy(step)


def configure_condition(page, step):
    """Native one-condition creation, grounded in the Nov 8 live drawer capture.

    Existing rules require inventory/reconciliation. Never append blindly when
    their intended persisted identity is unknown. Save is not functional proof.
    """
    if __package__:
        from .skill6_playwright import click, fill, form_builder, visible, wait_until, Stop
    else:
        from skill6_playwright import click, fill, form_builder, visible, wait_until, Stop
    step = validate_condition(step)
    frame = form_builder(page)
    editor_url = page.url
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    form_name = title.input_value()
    close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
    if visible(close):
        click(close)
    click(frame.get_by_role('tab', name='Edit', exact=True))
    click(frame.get_by_role('button', name='Open Conditional Logic', exact=True))
    dialog = frame.get_by_role('dialog')
    unary = step['operator'] in {'Is Empty', 'Is Filled'}
    effect = step.get('effect',step.get('action') if step.get('action') in ('Hide Field','Show Field') else 'Hide Field')
    # Both single-field effects were saved and independently reopened in the
    # native editor on 2026-11-08. This verifies configuration, not submissions.
    verified_card_effect = effect in ('Hide Field','Show Field')

    def persisted_match():
        if not unary:
            return False  # Binary condition card text needs its own capture.
        rows = dialog.locator('.condition-summary-row')
        expected = ''.join(('If' + step['if_field'] + step['operator']).split())
        matches = 0
        for index in range(rows.count()):
            row = rows.nth(index)
            if ''.join((row.text_content() or '').split()) != expected:
                continue
            # Fresh Hide/Show capture: the source summary row's second ancestor
            # is this rule's card, not the whole drawer/list of unrelated rules.
            card = row.locator('..').locator('..')
            if card.get_by_text(step['target'], exact=True).count() == 1 and card.get_by_text(effect, exact=True).count() == 2:
                matches += 1
        if matches > 1:
            raise Stop('Duplicate persisted conditions require reconciliation')
        return matches == 1

    if persisted_match():
        return {'status': 'CONDITION_ALREADY_PRESENT', 'kind': 'form_condition',
                'independent_readback': 'VERIFIED' if verified_card_effect else 'REQUIRED', 'submission_verified': False, 'behavior_verified':False,
                'effect':effect, 'if_field': step['if_field'], 'operator': step['operator'], 'target': step['target']}
    if dialog.get_by_text('No existing conditions yet', exact=True).count() != 1:
        raise Stop('Existing conditions require inventory before another create')
    click(dialog.get_by_text('Show/Hide Fields', exact=True))
    inputs = dialog.get_by_role('textbox')
    if inputs.count() != 5:
        raise Stop('Native condition control count changed')
    def choose(label):
        # Naive UI may portal a dropdown within the frame outside the dialog.
        # Accept only one exact visible-text candidate, never an indexed guess.
        loc = dialog.get_by_text(label, exact=True)
        if loc.count() != 1:
            loc = frame.get_by_text(label, exact=True)
        if loc.count() != 1:
            raise Stop('Condition choice absent or ambiguous: ' + label)
        click(loc)
    click(inputs.nth(0))
    choose(step['if_field'])
    click(inputs.nth(1))
    choose(step['operator'])
    if inputs.count() != (4 if unary else 5):
        raise Stop('Native condition operator shape changed')
    if not unary:
        fill(dialog.get_by_placeholder('Please Type a value here', exact=True), step['value'])
    # Naive UI's searchable INPUT value is blank even when an effect is selected.
    # Read the captured visible selected label and overlay, never hidden state.
    action_input = inputs.nth(2 if unary else 3)
    def selected_effect():
        observed = action_input.evaluate('''el => {
            const selection = el.closest('.n-base-selection');
            if (!selection) return null;
            const labels = selection.querySelectorAll('.n-base-selection-label');
            const overlays = selection.querySelectorAll('.n-base-selection-overlay__wrapper');
            return {labels: labels.length, overlays: overlays.length,
                    title: labels.length === 1 ? labels[0].getAttribute('title') : null,
                    text: overlays.length === 1 ? overlays[0].textContent.trim() : null};
        }''')
        if not isinstance(observed,dict) or observed.get('labels') != 1 or observed.get('overlays') != 1 or observed.get('title') != observed.get('text'):
            raise Stop('Native condition selected-effect structure changed')
        current = observed.get('title')
        if current not in ('Hide Field','Show Field'):
            raise Stop('Native condition selected effect is not a captured single-field effect')
        return current
    current = selected_effect()
    if current != effect:
        # Only the default Hide -> explicitly requested Show transition was captured.
        if current != 'Hide Field' or effect != 'Show Field':
            raise Stop('Native condition effect differs from the captured default')
        click(action_input)
        option = frame.locator('.n-base-select-option').get_by_text(effect,exact=True)
        if option.count() != 1:
            raise Stop('Native condition effect option absent or ambiguous')
        click(option)
        wait_until(lambda:selected_effect()==effect,'Native condition effect did not change')
    click(inputs.nth(3 if unary else 4))
    choose(step['target'])
    save = dialog.get_by_role('button', name='Save', exact=True)
    if not save.is_enabled():
        raise Stop('Native condition remains invalid; no save attempted')
    click(save)
    wait_until(lambda: dialog.get_by_text(effect, exact=True).count() >= 2,
               'Saved native condition card did not appear')
    # The first Save stores the rule card; the drawer Save stores its list.
    click(dialog.get_by_role('button', name='Save', exact=True))
    dialog.wait_for(state='hidden', timeout=45000)
    click(frame.get_by_role('button', name='Save', exact=True))
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).count() == 1
               and frame.get_by_role('button', name='Save', exact=True).is_enabled(), 'Form save did not finish')
    page.goto(editor_url, wait_until='domcontentloaded', timeout=45000)
    title.wait_for(state='visible', timeout=45000)
    if page.url != editor_url or title.input_value() != form_name:
        raise Stop('Reopened form identity changed')
    if visible(close):
        click(close)
    click(frame.get_by_role('tab', name='Edit', exact=True))
    click(frame.get_by_role('button', name='Open Conditional Logic', exact=True))
    if unary and not persisted_match():
        raise Stop('Saved native condition absent from independent editor read-back')
    return {'status': 'CONDITION_SAVED_AND_REOPENED' if unary and verified_card_effect else 'CONDITION_SAVE_SUBMITTED', 'kind': 'form_condition',
            'independent_readback': 'VERIFIED' if unary and verified_card_effect else 'REQUIRED', 'submission_verified': False, 'behavior_verified':False,
            'effect':effect, 'if_field': step['if_field'], 'operator': step['operator'], 'target': step['target']}


def validate_model(model):
    """Validate authored survey branches and quiz score/result contracts.

    This is an independent functional oracle, not a claim that UI wiring exists.
    Branches are forward-only and choices/results are exact, never invented.
    """
    if not isinstance(model, dict) or model.get('kind') not in ('survey', 'quiz'):
        raise AssessmentError('Model kind must be survey or quiz')
    if set(model) - {'kind', 'questions', 'results'}:
        raise AssessmentError('Unsupported assessment model setting')
    questions = model.get('questions')
    if not isinstance(questions, list) or not questions:
        raise AssessmentError('Questions are required')
    ids = [q.get('id') if isinstance(q, dict) else None for q in questions]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise AssessmentError('Question IDs must be unique nonempty strings')
    for index, q in enumerate(questions):
        if set(q) - {'id', 'choices'}:
            raise AssessmentError('Unsupported modeled question setting')
        choices = q.get('choices')
        if not isinstance(choices, list) or not choices:
            raise AssessmentError('Explicit question choices are required')
        values = [c.get('value') if isinstance(c, dict) else None for c in choices]
        if any(not isinstance(x, str) or not x for x in values) or len(values) != len(set(values)):
            raise AssessmentError('Choice values must be unique nonempty strings')
        for c in choices:
            if set(c) - {'value', 'score', 'next'}:
                raise AssessmentError('Unsupported modeled choice setting')
            if model['kind'] == 'quiz' and (type(c.get('score')) is not int):
                raise AssessmentError('Each quiz choice needs an integer score')
            target = c.get('next')
            if target is not None and target != 'submit' and (target not in ids or ids.index(target) <= index):
                raise AssessmentError('Branch must target an existing later question or submit')
    if model['kind'] == 'quiz':
        results = model.get('results')
        if not isinstance(results, list) or not results:
            raise AssessmentError('Quiz results are required')
        result_ids = [r.get('id') if isinstance(r, dict) else None for r in results]
        if any(not isinstance(x, str) or not x for x in result_ids) or len(set(result_ids)) != len(result_ids):
            raise AssessmentError('Result IDs must be unique nonempty strings')
        ranges = []
        for r in results:
            if set(r) - {'id', 'min', 'max'}:
                raise AssessmentError('Unsupported modeled result setting')
            if type(r.get('min')) is not int or type(r.get('max')) is not int or r['min'] > r['max']:
                raise AssessmentError('Result ranges must have integer min <= max')
            ranges.append((r['min'], r['max']))
        ranges.sort()
        if any(a[1] >= b[0] for a, b in zip(ranges, ranges[1:])):
            raise AssessmentError('Quiz result score ranges overlap')
        # Every reachable score, including early-submit branches, must map to a
        # result before any UI write. This catches gaps that min/max alone miss.
        pending, seen, scores = [(0, 0)], set(), set()
        while pending:
            index, total = pending.pop()
            if (index, total) in seen:
                continue
            seen.add((index, total))
            if len(seen) > 10000:
                raise AssessmentError('Quiz score state space exceeds the validation bound')
            for choice in questions[index]['choices']:
                next_score = total + choice['score']
                target = choice.get('next')
                if target == 'submit' or (target is None and index == len(questions) - 1):
                    scores.add(next_score)
                else:
                    pending.append((ids.index(target) if target else index + 1, next_score))
        if any(sum(low <= score <= high for low, high in ranges) != 1 for score in scores):
            raise AssessmentError('A reachable quiz score has no authored result')
    return deepcopy(model)


def evaluate_model(model, answers):
    """Return expected visited questions, score and result for one fixture."""
    model = validate_model(model)
    if not isinstance(answers, dict):
        raise AssessmentError('Fixture answers must be a mapping')
    questions = model['questions']
    ids = [q['id'] for q in questions]
    if set(answers) - set(ids):
        raise AssessmentError('Fixture contains unknown question IDs')
    current, visited, score = 0, [], 0
    while current < len(questions):
        q = questions[current]
        visited.append(q['id'])
        if q['id'] not in answers:
            raise AssessmentError('Missing answer for visited question: ' + q['id'])
        choice = next((c for c in q['choices'] if c['value'] == answers[q['id']]), None)
        if choice is None:
            raise AssessmentError('Unknown answer choice for ' + q['id'])
        score += choice.get('score', 0) if model['kind'] == 'quiz' else 0
        target = choice.get('next')
        if target == 'submit':
            break
        current = ids.index(target) if target is not None else current + 1
    result = None
    if model['kind'] == 'quiz':
        matches = [r['id'] for r in model['results'] if r['min'] <= score <= r['max']]
        if len(matches) != 1:
            raise AssessmentError('Quiz score has no unique authored result')
        result = matches[0]
    return {'visited': visited, 'score': score if model['kind'] == 'quiz' else None,
            'result': result, 'ignored_unvisited_answers': sorted(set(answers) - set(visited))}


def verify_submission(model, answers, observed):
    if not isinstance(observed, dict):
        raise AssessmentError('Observed submission must be a mapping')
    expected = evaluate_model(model, answers)
    differences = [key for key in ('visited', 'score', 'result') if observed.get(key) != expected[key]]
    return {'status': 'PASS' if not differences else 'FAIL', 'differences': differences, 'expected': expected}
