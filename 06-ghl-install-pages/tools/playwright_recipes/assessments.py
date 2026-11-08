"""Native assessment field edits and independent branch/score validation.

Field controls were inspected in form-builder-app on 2026-11-08. This module
never invents survey/quiz scoring selectors; validate_model and evaluate_model
provide exact expected behavior for their independent submission checks.
"""
from copy import deepcopy


STANDARD_FIELDS = {
    'First Name': ('Enter your first name', 'first_name'),
    'Last Name': ('Enter your last name', 'last_name'),
    'Phone': ('+1 (555) 000-0000', 'phone'),
    'Email': ('your@email.com', 'email'),
}
PROPERTIES = ('label', 'placeholder', 'short_label', 'query_key', 'width_pct')


class AssessmentError(ValueError):
    pass


def validate_fields(step):
    fields = step.get('fields')
    if not isinstance(fields, list) or not fields:
        raise AssessmentError('fields must be a nonempty list')
    seen = set()
    result = deepcopy(step)
    for field in result['fields']:
        if not isinstance(field, dict) or field.get('field') not in STANDARD_FIELDS:
            raise AssessmentError('Only captured standard native fields are supported')
        if field['field'] in seen:
            raise AssessmentError('Duplicate field edit')
        seen.add(field['field'])
        if set(field) - {'field', *PROPERTIES, 'required', 'hidden', 'current_placeholder', 'current_query_key'}:
            raise AssessmentError('Unknown field property')
        if not set(field).intersection({*PROPERTIES, 'required', 'hidden'}):
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
        if field.get('hidden') is True:
            raise AssessmentError('Hidden-field reopen anchor has not been captured; no mutation allowed')
        for key in PROPERTIES[:-1]:
            if key in field and not isinstance(field[key], str):
                raise AssessmentError(key + ' must be text')
        if 'placeholder' in field and not field['placeholder'].strip():
            raise AssessmentError('Placeholder must remain an unambiguous field anchor')
        if 'label' in field and not field['label'].strip():
            raise AssessmentError('Field label cannot be empty')
        if 'width_pct' in field and (type(field['width_pct']) is not int or not 1 <= field['width_pct'] <= 100):
            raise AssessmentError('Field width must be an integer from 1 to 100')
    anchors = {field: values[0] for field, values in STANDARD_FIELDS.items()}
    anchors.update({f['field']: f.get('placeholder', f.get('current_placeholder', anchors[f['field']])) for f in result['fields']})
    placeholders = list(anchors.values())
    if len(placeholders) != len(set(placeholders)):
        raise AssessmentError('Edited placeholders must remain unique')
    return result


def configure_fields(page, step):
    """Edit standard native form properties and verify them after list reopen.

    Parent runner provides tenant checks and durable intent-before-mutation state.
    Advanced custom fields remain owned by the pre-created-field dependency rail.
    """
    if __package__:
        from .skill6_playwright import click, fill, form_builder, visible, exact_search, wait_until, Stop
    else:
        from skill6_playwright import click, fill, form_builder, visible, exact_search, wait_until, Stop
    step = validate_fields(step)
    frame = form_builder(page)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    name = title.input_value()
    editor_url = page.url
    close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
    if visible(close):
        click(close)

    def panel(field, placeholder):
        click(frame.get_by_role('tab', name='Edit', exact=True))
        target = frame.get_by_placeholder(placeholder, exact=True)
        if target.count() != 1:
            raise Stop('Field anchor is absent or ambiguous: ' + field['field'])
        click(target)
        click(frame.get_by_label('Open settings', exact=True))
        frame.get_by_text('General Settings', exact=True).wait_for(state='visible', timeout=45000)
        inputs = frame.get_by_role('textbox', name='Please Input', exact=True)
        if inputs.count() != 5:
            raise Stop('Native field property panel changed; capture required')
        for index, label in enumerate(('Label', 'Placeholder', 'Short Label', 'Query Key', 'Field Width')):
            if label not in inputs.nth(index).evaluate("el => el.closest('.form-group')?.textContent || ''"):
                raise Stop('Native field property order changed; capture required')
        return inputs

    def close_panel():
        backs = frame.get_by_role('button', name='Back', exact=True)
        if backs.count() != 2:
            raise Stop('Native field panel Back controls changed')
        click(backs.nth(1))

    expected = []
    for field in step['fields']:
        default_placeholder, default_key = STANDARD_FIELDS[field['field']]
        old_placeholder = field.get('current_placeholder', default_placeholder)
        key = field.get('current_query_key', default_key)
        inputs = panel(field, old_placeholder)
        if inputs.nth(3).input_value() != key:
            raise Stop('Standard field identity differs from captured query key')
        required = frame.get_by_role('checkbox', name='Required', exact=True)
        hidden = frame.get_by_role('checkbox', name='Hidden', exact=True)
        wanted_required = field.get('required', required.is_checked())
        wanted_hidden = field.get('hidden', hidden.is_checked())
        if wanted_required and wanted_hidden:
            raise Stop('Requested field would become required and hidden')
        # Uncheck first so even intermediate states preserve the mutual exclusion.
        if not wanted_required:
            required.set_checked(False)
        if not wanted_hidden:
            hidden.set_checked(False)
        for index, prop in enumerate(PROPERTIES):
            if prop in field:
                fill(inputs.nth(index), str(field[prop]))
        if wanted_required:
            required.set_checked(True)
        if wanted_hidden:
            hidden.set_checked(True)
        expected.append((field, [inputs.nth(i).input_value() for i in range(5)], wanted_required, wanted_hidden))
        close_panel()
    click(frame.get_by_role('button', name='Save', exact=True))
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).is_enabled(), 'Form save did not finish')
    click(frame.get_by_role('button', name='Back', exact=True))
    cell = exact_search(page, 'forms', name)
    if cell is None:
        raise Stop('Saved form absent from independent list read-back')
    click(cell.get_by_text(name, exact=True))
    title.wait_for(state='visible', timeout=45000)
    if page.url != editor_url:
        raise Stop('Reopened form identity changed')
    if visible(close):
        click(close)
    for field, values, required, hidden in expected:
        inputs = panel(field, values[1])
        if [inputs.nth(i).input_value() for i in range(5)] != values:
            raise Stop('Field properties did not persist: ' + field['field'])
        for label, value in (('Required', required), ('Hidden', hidden)):
            if frame.get_by_role('checkbox', name=label, exact=True).is_checked() != value:
                raise Stop('Field boolean did not persist: ' + field['field'] + '/' + label)
        close_panel()
    return {'status': 'FIELD_PROPERTIES_SAVED_AND_REOPENED', 'editor_url': page.url,
            'fields': [f['field'] for f in step['fields']], 'submission_verified': False}


def validate_condition(step):
    """Current capture supports one explicit Hide Field condition per run."""
    allowed = {'First Name', 'Last Name', 'Phone', 'Email', 'TnC1', 'TnC2'}
    if step.get('if_field') not in allowed or step.get('target') not in allowed | {'Privacy Policy | Terms of Service'}:
        raise AssessmentError('Condition fields must match captured native labels')
    operators = {'Is Equal To', 'Is Not Equal To', 'Contains', 'Does Not Contain',
                 'Starts With', 'Ends With', 'Is Empty', 'Is Filled'}
    if step.get('operator') not in operators:
        raise AssessmentError('Uncaptured condition operator')
    if step.get('action', 'Hide Field') != 'Hide Field':
        raise AssessmentError('Only the captured Hide Field action is implemented')
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
        from .skill6_playwright import click, fill, form_builder, visible, Stop
    else:
        from skill6_playwright import click, fill, form_builder, visible, Stop
    step = validate_condition(step)
    frame = form_builder(page)
    close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
    if visible(close):
        click(close)
    click(frame.get_by_role('tab', name='Edit', exact=True))
    click(frame.get_by_role('button', name='Open Conditional Logic', exact=True))
    dialog = frame.get_by_role('dialog')
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
    unary = step['operator'] in {'Is Empty', 'Is Filled'}
    if inputs.count() != (4 if unary else 5):
        raise Stop('Native condition operator shape changed')
    if not unary:
        fill(dialog.get_by_placeholder('Please Type a value here', exact=True), step['value'])
    # The action is explicitly Hide Field, the only action captured live.
    if inputs.nth(2 if unary else 3).input_value() != 'Hide Field':
        raise Stop('Native condition action differs from captured Hide Field')
    click(inputs.nth(3 if unary else 4))
    choose(step['target'])
    save = dialog.get_by_role('button', name='Save', exact=True)
    if not save.is_enabled():
        raise Stop('Native condition remains invalid; no save attempted')
    click(save)
    return {'status': 'CONDITION_SAVE_SUBMITTED', 'kind': 'form_condition',
            'independent_readback': 'REQUIRED', 'submission_verified': False,
            'if_field': step['if_field'], 'operator': step['operator'], 'target': step['target']}


def validate_model(model):
    """Validate authored survey branches and quiz score/result contracts.

    This is an independent functional oracle, not a claim that UI wiring exists.
    Branches are forward-only and choices/results are exact, never invented.
    """
    if not isinstance(model, dict) or model.get('kind') not in ('survey', 'quiz'):
        raise AssessmentError('Model kind must be survey or quiz')
    questions = model.get('questions')
    if not isinstance(questions, list) or not questions:
        raise AssessmentError('Questions are required')
    ids = [q.get('id') if isinstance(q, dict) else None for q in questions]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise AssessmentError('Question IDs must be unique nonempty strings')
    for index, q in enumerate(questions):
        choices = q.get('choices')
        if not isinstance(choices, list) or not choices:
            raise AssessmentError('Explicit question choices are required')
        values = [c.get('value') if isinstance(c, dict) else None for c in choices]
        if any(not isinstance(x, str) or not x for x in values) or len(values) != len(set(values)):
            raise AssessmentError('Choice values must be unique nonempty strings')
        for c in choices:
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
