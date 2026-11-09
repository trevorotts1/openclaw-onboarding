"""Native survey forward Jump To rules and complete ordered branch stacks.

Rule save, drawer save and form save are separate operations. Preview behavior
is a separate verification concern from persisted native configuration. The
same captured rule controls support a fully inventoried ordered stack, without
inventing compound conditions or completion effects.
"""
from copy import deepcopy
import hashlib
import json
import re


class SurveyError(ValueError):
    pass


OPERATORS = {'Is Equal To', 'Is Not Equal To', 'Contains', 'Does Not Contain',
             'Starts With', 'Ends With', 'Is Empty', 'Is Filled'}


def _validate_rule(step):
    if not isinstance(step, dict):
        raise SurveyError('Survey rule must be an object')
    if set(step) - {'id', 'action', 'expected_slide_count', 'source_slide', 'target_slide',
                    'slide_labels', 'if_field', 'source_placeholder', 'operator', 'value'}:
        raise SurveyError('Unsupported native survey configuration option')
    count = step.get('expected_slide_count')
    if type(count) is not int or count < 2:
        raise SurveyError('Expected native slide count must be at least two')
    source, target = step.get('source_slide'), step.get('target_slide')
    if type(source) is not int or type(target) is not int or not 1 <= source < target <= count:
        raise SurveyError('Survey jumps must move forward between existing slides')
    labels = step.get('slide_labels')
    if not isinstance(labels, list) or len(labels) != count:
        raise SurveyError('Supply all exact native slide target labels')
    for index, label in enumerate(labels, 1):
        if not isinstance(label, str) or not re.fullmatch('P' + str(index) + r' - .+', label):
            raise SurveyError('Slide label does not match its native numbered position')
    if len(set(labels)) != len(labels):
        raise SurveyError('Duplicate slide labels')
    if not isinstance(step.get('if_field'), str) or not step['if_field'].strip():
        raise SurveyError('An exact native condition field label is required')
    if 'source_placeholder' in step and (not isinstance(step['source_placeholder'], str) or not step['source_placeholder']):
        raise SurveyError('Source placeholder must be explicit nonempty text')
    if step.get('operator') not in OPERATORS:
        raise SurveyError('Uncaptured survey condition operator')
    unary = step['operator'] in {'Is Empty', 'Is Filled'}
    if unary and 'value' in step:
        raise SurveyError('Unary survey rule must not carry an ignored value')
    if not unary and (not isinstance(step.get('value'), str) or not step['value']):
        raise SurveyError('This comparison requires an explicit text value')
    return deepcopy(step)


def validate(step):
    """Accept one rule or an explicitly ordered stack of existing-slide rules."""
    if not isinstance(step, dict) or 'rules' not in step:
        return _validate_rule(step)
    if set(step) - {'id', 'action', 'expected_slide_count', 'slide_labels', 'rules'}:
        raise SurveyError('Unsupported native survey rule-stack option')
    rules = step.get('rules')
    if not isinstance(rules, list) or not rules:
        raise SurveyError('A survey rule stack requires at least one explicit rule')
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - {
                'source_slide', 'target_slide', 'if_field', 'source_placeholder', 'operator', 'value'}:
            raise SurveyError('Survey stack rules must contain only their authored condition and targets')
        value = _validate_rule({
            'expected_slide_count':step.get('expected_slide_count'),
            'slide_labels':step.get('slide_labels'), **rule})
        # Native summary cards identify the condition independently of its
        # destination. Duplicate/conflicting destinations are not two rules.
        identity = (value['if_field'], value['operator'], value.get('value'))
        if identity in seen:
            raise SurveyError('Duplicate survey stack condition requires reconciliation')
        seen.add(identity)
    return deepcopy(step)


def configuration_hash(step):
    value = validate(step)
    canonical = {key:item for key, item in value.items() if key not in ('id', 'action')}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _summary(rule):
    return 'If' + rule['if_field'] + rule['operator'] + rule.get('value', '')


def configure(page, step):
    """Author every requested forward branch without a model call per rule."""
    value = validate(step)
    if 'rules' not in value:
        return _configure_rule(page, value)
    common = {key:value[key] for key in ('expected_slide_count', 'slide_labels')}
    rules = [{**common, **rule} for rule in value['rules']]
    # Read every source, slide inventory and conflicting native condition before
    # the first new rule. Each later write remains individually duplicate-safe.
    intended_order = [_summary(rule) for rule in rules]
    existing_order = None
    for rule in rules:
        observed = _configure_rule(page, rule, preflight=True)['_native_summaries']
        if existing_order is None:
            existing_order = observed
        if observed != existing_order or observed != intended_order[:len(observed)]:
            raise SurveyError('Existing survey conditions are not the exact prefix of this complete ordered rule stack')
    for rule in rules:
        _configure_rule(page, rule)
    # Later rule saves must not silently remove an earlier branch. Reopen and
    # inspect every requested native summary card after the last authored rule.
    for rule in rules:
        observed = _configure_rule(page, rule, read_only=True)['_native_summaries']
        if observed != intended_order:
            raise SurveyError('Saved survey stack priority/order differs from the requested complete rule stack')
    return {'status':'SURVEY_RULE_STACK_SAVED_AND_REOPENED',
            'kind':'survey_condition_stack', 'editor_url':page.url,
            'rule_count':len(rules), 'configuration_sha256':configuration_hash(value),
            'independent_readback':'VERIFIED', 'behavior_verified':False,
            'submission_verified':False}


def _configure_rule(page, step, *, preflight=False, read_only=False):
    """Create/reuse one native forward rule and independently reopen its card.

    Source ownership is checked against actual survey slide containers before
    opening the rule editor. Save completion does not claim preview behavior.
    """
    if __package__:
        from .skill6_playwright import click, fill, visible, wait_until, Stop
    else:
        from skill6_playwright import click, fill, visible, wait_until, Stop
    step = _validate_rule(step)
    frame = page.frame_locator('iframe[name="survey-builder-app"]')
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    survey_name, editor_url = title.input_value(), page.url
    unary = step['operator'] in {'Is Empty', 'Is Filled'}
    target_label = step['slide_labels'][step['target_slide'] - 1]
    summary = 'If' + step['if_field'] + step['operator'] + ('' if unary else step['value'])

    def close_initial():
        close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
        if visible(close):
            click(close)

    def source_guard():
        slides = frame.locator('.survey-form-container')
        if slides.count() != step['expected_slide_count'] or frame.get_by_role('button', name='Add Slide', exact=True).count() != step['expected_slide_count']:
            raise Stop('Survey slide count changed')
        for index, label in enumerate(step['slide_labels']):
            header = slides.nth(index).locator('.builder-form-name')
            if header.count() != 1 or header.inner_text().strip() != label.split(' - ', 1)[1]:
                raise Stop('Native slide order/name changed')
        owner = slides.nth(step['source_slide'] - 1)
        defaults = {'Email': 'your@email.com', 'First Name': 'Enter your first name',
                    'Last Name': 'Enter your last name', 'Phone': '+1 (555) 000-0000'}
        placeholder = step.get('source_placeholder', defaults.get(step['if_field']))
        if placeholder:
            target = owner.get_by_placeholder(placeholder, exact=True)
            if target.count() != 1:
                raise Stop('Conditional field does not belong to the claimed source slide')
        else:
            plain = owner.get_by_text(step['if_field'], exact=True)
            required = owner.get_by_text(step['if_field'] + '*', exact=True)
            if plain.count() + required.count() != 1:
                raise Stop('Custom conditional field owner is absent or ambiguous')
            target = plain if plain.count() else required
        return target

    close_initial()
    click(frame.get_by_role('tab', name='Edit', exact=True))
    source = source_guard()
    # The captured legacy survey rail selects the owner before opening its
    # amber condition control. Merely finding a field on that slide does not
    # change which slide/field is currently selected in the native editor.
    click(source)
    click(frame.get_by_role('button', name='Open Conditional Logic', exact=True))
    dialog = frame.get_by_role('dialog')
    dialog.wait_for(state='visible', timeout=45000)

    def persisted_match():
        rows = dialog.locator('.condition-summary-row')
        matching_rows = []
        for index in range(rows.count()):
            raw = (rows.nth(index).text_content() or '').replace('\u00a0', ' ').strip()
            if raw == summary:
                matching_rows.append(rows.nth(index))
        if len(matching_rows) > 1:
            raise Stop('Duplicate survey conditions require reconciliation')
        if not matching_rows:
            return False
        body = matching_rows[0].locator('..')
        if body.get_by_text('JUMP TO', exact=True).count() != 1 or body.get_by_text(target_label, exact=True).count() != 1:
            raise Stop('Existing survey condition has a different jump target')
        return True

    def result(status):
        outcome = {'status': status, 'kind': 'survey_condition', 'editor_url': page.url,
                'if_field': step['if_field'], 'operator': step['operator'],
                'source_slide': step['source_slide'], 'target_slide': step['target_slide'],
                'independent_readback': 'VERIFIED', 'behavior_verified': False,
                'submission_verified': False}
        if preflight or read_only:
            rows = dialog.locator('.condition-summary-row')
            outcome['_native_summaries'] = [
                (rows.nth(index).text_content() or '').replace('\u00a0', ' ').strip()
                for index in range(rows.count())]
        return outcome

    matched = persisted_match()
    if preflight or read_only:
        if read_only and not matched:
            raise Stop('A previously saved survey stack rule is absent from independent read-back')
        outcome = result('SURVEY_RULE_PREFLIGHT_READY' if preflight else 'SURVEY_RULE_ALREADY_PRESENT')
        close = dialog.get_by_role('button', name='Close', exact=True)
        if close.count() != 1 or not close.is_visible():
            raise Stop('Captured survey condition drawer close control is unavailable; no rule save attempted')
        click(close)
        dialog.wait_for(state='hidden', timeout=45000)
        return outcome
    if matched:
        return result('SURVEY_RULE_ALREADY_PRESENT')
    click(dialog.get_by_text('Jump To', exact=True))
    inputs = dialog.get_by_role('textbox')
    if inputs.count() != 5 or inputs.nth(0).input_value() != 'Field':
        raise Stop('Native Jump To editor controls changed')

    def choose(label):
        loc = dialog.get_by_text(label, exact=True)
        if loc.count() != 1:
            loc = frame.get_by_text(label, exact=True)
        if loc.count() != 1:
            raise Stop('Native survey dropdown choice is absent or ambiguous: ' + label)
        click(loc)

    click(inputs.nth(1))
    choose(step['if_field'])
    click(inputs.nth(2))
    choose(step['operator'])
    if inputs.count() != (4 if unary else 5):
        raise Stop('Survey comparison control shape changed')
    if not unary:
        fill(dialog.get_by_placeholder('Please Type a value here', exact=True), step['value'])
    click(inputs.nth(3 if unary else 4))
    choose(target_label)
    save = dialog.get_by_role('button', name='Save', exact=True)
    if not save.is_enabled():
        raise Stop('Native survey condition remains invalid; no save attempted')
    click(save)
    wait_until(persisted_match, 'Saved native survey rule card did not appear')
    click(dialog.get_by_role('button', name='Save', exact=True))
    dialog.wait_for(state='hidden', timeout=45000)
    click(frame.get_by_role('button', name='Save', exact=True))
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).count() == 1
               and frame.get_by_role('button', name='Save', exact=True).is_enabled(), 'Survey save did not finish')
    page.goto(editor_url, wait_until='domcontentloaded', timeout=45000)
    title.wait_for(state='visible', timeout=45000)
    if page.url != editor_url or title.input_value() != survey_name:
        raise Stop('Reopened survey identity changed')
    close_initial()
    click(frame.get_by_role('tab', name='Edit', exact=True))
    source = source_guard()
    click(source)
    click(frame.get_by_role('button', name='Open Conditional Logic', exact=True))
    dialog.wait_for(state='visible', timeout=45000)
    if not persisted_match():
        raise Stop('Saved survey rule absent from independent editor read-back')
    return result('SURVEY_RULE_SAVED_AND_REOPENED')
