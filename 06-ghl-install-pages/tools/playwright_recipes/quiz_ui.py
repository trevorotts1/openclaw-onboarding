"""Native marketing quiz categories, option scores and three result tiers.

Selectors/counts were captured in quiz-builder-app on 2026-11-08. No survey or
course-quiz selector is reused. This edits an existing quiz; it does not submit
contacts, publish, delete options/categories or change custom-field definitions.
"""
from copy import deepcopy
import math


class QuizError(ValueError):
    pass


def validate(step):
    if not isinstance(step, dict):
        raise QuizError('Quiz configuration must be an object')
    if set(step) - {'id', 'action', 'categories', 'expected_question_count', 'questions', 'tiers', 'expected_tier_labels'}:
        raise QuizError('Unsupported native quiz configuration option')
    categories = step.get('categories', [])
    if not isinstance(categories, list) or any(not isinstance(x, str) or not x.strip() for x in categories):
        raise QuizError('Category names must be explicit nonempty text')
    if len(categories) != len({x.casefold() for x in categories}):
        raise QuizError('Duplicate category names')
    questions = step.get('questions', [])
    if not isinstance(questions, list):
        raise QuizError('Questions must be a list')
    count = step.get('expected_question_count')
    if questions and (type(count) is not int or count < 1):
        raise QuizError('Expected canvas question count is required')
    indexes = set()
    for q in questions:
        if not isinstance(q, dict) or type(q.get('index')) is not int or not 0 <= q['index'] < count:
            raise QuizError('Question index is outside the captured canvas count')
        if set(q) - {'index', 'expected_question', 'expected_query_key', 'options', 'question', 'append_options', 'shared_field_change_ack'}:
            raise QuizError('Unsupported native question option; question creation/renaming needs its own capture')
        if q['index'] in indexes:
            raise QuizError('Duplicate question configuration')
        indexes.add(q['index'])
        for key in ('expected_question', 'expected_query_key'):
            if not isinstance(q.get(key), str) or not q[key]:
                raise QuizError('Question identity guards are required')
        options = q.get('options')
        if not isinstance(options, list) or not options:
            raise QuizError('Supply every existing option in captured order')
        appended = q.get('append_options', [])
        if not isinstance(appended, list):
            raise QuizError('Appended quiz options must be a list')
        if 'question' in q and (not isinstance(q['question'], str) or not q['question'].strip()):
            raise QuizError('Authored quiz question text must be nonempty')
        authoring = 'question' in q or bool(appended) or any(isinstance(o, dict) and 'new_label' in o for o in options)
        if authoring and q.get('shared_field_change_ack') is not True:
            raise QuizError('Question/choice authoring requires shared_field_change_ack:true for the exact guarded field')
        labels = []
        for index, option in enumerate(options + appended):
            if not isinstance(option, dict) or not isinstance(option.get('label'), str) or not option['label']:
                raise QuizError('Each option needs its expected label')
            if set(option) - ({'label', 'category', 'score', 'new_label'} if index < len(options) else {'label', 'category', 'score'}):
                raise QuizError('Unsupported native answer option; jump routing needs its own capture')
            if 'new_label' in option and (not isinstance(option['new_label'], str) or not option['new_label'].strip()):
                raise QuizError('Renamed quiz option label must be nonempty')
            labels.append(option.get('new_label', option['label']))
            if not isinstance(option.get('category'), str) or not option['category'].strip():
                raise QuizError('Each score needs an explicit category')
            if type(option.get('score')) not in (int, float) or not math.isfinite(option['score']):
                raise QuizError('Quiz scores must be finite numbers, not booleans')
        if len(labels) != len(set(labels)):
            raise QuizError('Option labels must be unique within a question')
        existing_labels = [o['label'] for o in options]
        if len(existing_labels) != len(set(existing_labels)):
            raise QuizError('Existing option identity labels are ambiguous')
        if any(o.get('new_label', o['label']) != o['label'] and o.get('new_label') in existing_labels for o in options):
            raise QuizError('Renaming into another existing label requires a separately reconciled edit')
    tiers = step.get('tiers')
    if tiers is not None:
        if not isinstance(tiers, list) or len(tiers) != 3:
            raise QuizError('Only the captured three-tier layout is implemented')
        existing = step.get('expected_tier_labels')
        if not isinstance(existing, list) or len(existing) != 3 or any(not isinstance(x, str) or not x for x in existing):
            raise QuizError('Supply the three current tier labels as identity guards')
        previous = -1
        labels = []
        for tier in tiers:
            if not isinstance(tier, dict) or not isinstance(tier.get('label'), str) or not tier['label'].strip():
                raise QuizError('Tier labels are required')
            if set(tier) - {'label', 'from', 'to'}:
                raise QuizError('Uncaptured result tier option')
            labels.append(tier['label'])
            low, high = tier.get('from'), tier.get('to')
            if type(low) is not int or type(high) is not int or not 0 <= low <= high <= 100 or low != previous + 1:
                raise QuizError('Integer tier ranges must cover 0 through 100 without overlap or gaps')
            previous = high
        if previous != 100 or len(labels) != len(set(labels)):
            raise QuizError('Tier ranges must end at 100 and labels must be unique')
    if not categories and not questions and tiers is None:
        raise QuizError('No native quiz changes requested')
    return deepcopy(step)


def configure(page, step):
    """Save requested quiz settings and independently reopen their controls."""
    if __package__:
        from .skill6_playwright import click, fill, visible, exact_search, wait_until, Stop
        from .assessments import reopen_editor
    else:
        from skill6_playwright import click, fill, visible, exact_search, wait_until, Stop
        from assessments import reopen_editor
    step = validate(step)
    frame = page.frame_locator('iframe[name="quiz-builder-app"]')
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    quiz_name, editor_url = title.input_value(), page.url

    def close_initial():
        close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
        if visible(close):
            click(close)

    close_initial()
    active_backs = frame.get_by_role('button', name='Back', exact=True)
    if active_backs.count() == 2:
        click(active_backs.nth(1))

    def category_dialog():
        click(frame.get_by_role('button', name='Manage Categories', exact=True))
        modal = frame.get_by_role('dialog', name='UI Modal', exact=True)
        modal.wait_for(state='visible', timeout=45000)
        names = modal.get_by_role('textbox', name='Enter category name', exact=True)
        if names.count() < 1 or names.nth(0).input_value() != 'Overall Only':
            raise Stop('Native quiz category identity changed')
        return modal, names

    def categories(read_only=False):
        modal, names = category_dialog()
        observed = [names.nth(i).input_value() for i in range(names.count())]
        if len(observed) != len({x.casefold() for x in observed}):
            raise Stop('Existing quiz categories are ambiguous')
        for name in step.get('categories', []):
            if name.casefold() in {x.casefold() for x in observed}:
                if name not in observed:
                    raise Stop('Existing category differs only by case; reconcile before writes')
                continue
            if read_only:
                raise Stop('Quiz category was not persisted')
            before = names.count()
            click(modal.get_by_role('button', name='Add category', exact=True))
            if names.count() != before + 1 or names.nth(before).input_value():
                raise Stop('New category control differs from capture')
            fill(names.nth(before), name)
            observed.append(name)
        click(modal.get_by_role('button', name='Cancel' if read_only else 'Submit', exact=True))
        modal.wait_for(state='hidden', timeout=45000)

    if step.get('categories'):
        categories()

    def desired_options(question):
        return [{**option, 'label': option.get('new_label', option['label'])}
                for option in question['options']] + question.get('append_options', [])

    def controls(expected_options):
        options = frame.get_by_role('textbox', name='Label', exact=True)
        count = len(expected_options)
        if options.count() != step['expected_question_count'] + count:
            raise Stop('Quiz option count changed')
        for index, option in enumerate(expected_options):
            if options.nth(step['expected_question_count'] + index).input_value() != option['label']:
                raise Stop('Quiz option identity/order changed')
        pickers = frame.locator('[id="category-picker"]')
        scores = frame.get_by_role('textbox', name='10', exact=True)
        if pickers.count() != count or scores.count() != count:
            raise Stop('Quiz category/score controls changed')
        for index in range(count):
            row = pickers.nth(index).locator('..').locator('..').locator('..').locator('..')
            row_label = row.get_by_role('textbox', name='Label', exact=True)
            if row_label.count() != 1 or row_label.input_value() != expected_options[index]['label']:
                raise Stop('Quiz score controls no longer belong to the intended option')
        return pickers, scores

    def open_question(question, read_only=False):
        click(frame.get_by_role('tab', name='Edit', exact=True))
        labels = frame.get_by_role('textbox', name='Label', exact=True)
        if labels.count() != step['expected_question_count']:
            raise Stop('Canvas question count differs from captured quiz')
        click(labels.nth(question['index']))
        click(frame.get_by_role('button', name='Open settings', exact=True))
        properties = frame.get_by_role('textbox', name='Please Input', exact=True)
        if properties.count() != 4:
            raise Stop('Quiz question properties changed')
        for index, label in enumerate(('Question', 'Placeholder', 'Short Label', 'Query Key')):
            if label not in properties.nth(index).evaluate("el => el.closest('.form-group')?.textContent || ''"):
                raise Stop('Quiz question property ordering changed')
        question_text = question.get('question', question['expected_question']) if read_only else question['expected_question']
        if properties.nth(0).input_value() != question_text or properties.nth(3).input_value() != question['expected_query_key']:
            raise Stop('Selected quiz question identity mismatch')
        pickers, scores = controls(desired_options(question) if read_only else question['options'])
        return properties, pickers, scores

    def close_question():
        backs = frame.get_by_role('button', name='Back', exact=True)
        if backs.count() != 2:
            raise Stop('Quiz property panel Back controls changed')
        click(backs.nth(1))

    def questions(read_only=False):
        for question in step.get('questions', []):
            properties, pickers, scores = open_question(question, read_only)
            desired = desired_options(question)
            if not read_only:
                append = question.get('append_options', [])
                add = frame.get_by_role('button', name='Add option', exact=True)
                if append and (add.count() != 2 or not add.nth(1).is_enabled()):
                    raise Stop('Native append-option controls differ from the captured layout')
                if 'question' in question:
                    fill(properties.nth(0), question['question'])
                labels = frame.get_by_role('textbox', name='Label', exact=True)
                for index, option in enumerate(question['options']):
                    if option.get('new_label', option['label']) != option['label']:
                        fill(labels.nth(step['expected_question_count'] + index), option['new_label'])
                for index, option in enumerate(append):
                    before = len(question['options']) + index
                    if add.count() != 2:
                        raise Stop('Native Add option control count changed')
                    wait_until(lambda: add.nth(1).is_enabled(), 'Blank quiz option prevents another append')
                    click(add.nth(1))
                    wait_until(lambda: labels.count() == step['expected_question_count'] + before + 1,
                               'Native quiz option did not append exactly once')
                    new_label = labels.nth(step['expected_question_count'] + before)
                    if new_label.input_value():
                        raise Stop('Appended quiz option is not the captured blank control')
                    fill(new_label, option['label'])
                pickers, scores = controls(desired)
            for index, option in enumerate(desired):
                picker, score = pickers.nth(index), scores.nth(index)
                if read_only:
                    if picker.inner_text().strip() != option['category'] or not score.is_enabled():
                        raise Stop('Quiz option category was not persisted')
                else:
                    click(picker)
                    choice = frame.locator('.n-base-select-option').get_by_text(option['category'], exact=True)
                    if choice.count() != 1:
                        raise Stop('Quiz category choice absent or ambiguous')
                    click(choice)
                    wait_until(lambda: score.is_enabled(), 'Selecting category did not enable scoring')
                    fill(score, str(option['score']))
                try:
                    actual = float(score.input_value())
                except ValueError:
                    raise Stop('Quiz score is not a numeric saved value') from None
                if actual != option['score']:
                    raise Stop('Quiz option score differs from request')
            close_question()

    questions()

    def tiers(read_only=False):
        if step.get('tiers') is None:
            return
        click(frame.get_by_role('button', name='Edit Template', exact=True))
        modal = frame.get_by_role('dialog', name='UI Modal', exact=True)
        modal.get_by_text('Customise result page', exact=True).wait_for(state='visible', timeout=45000)
        click(modal.get_by_text('Configure score tiers', exact=True))
        popup = frame.locator('.n-popover__content').filter(has_text='Add tier')
        if popup.count() != 1:
            raise Stop('Result tier popover absent or ambiguous')
        labels = popup.get_by_role('textbox', name='Label', exact=True)
        ranges = popup.get_by_role('textbox', name='', exact=True)
        expected_labels = [t['label'] for t in step['tiers']] if read_only else step['expected_tier_labels']
        if labels.count() != 3 or ranges.count() != 6:
            raise Stop('Only the captured three-tier result layout can be changed')
        if [labels.nth(i).input_value() for i in range(3)] != expected_labels:
            raise Stop('Existing tier labels differ from the expected template')
        if ranges.nth(0).is_enabled() or ranges.nth(5).is_enabled() or ranges.nth(0).input_value() != '0' or ranges.nth(5).input_value() != '100':
            raise Stop('Tier endpoint guards changed')
        for index, tier in enumerate(step['tiers']):
            if not read_only:
                fill(labels.nth(index), tier['label'])
            for endpoint, key in enumerate(('from', 'to')):
                control = ranges.nth(index * 2 + endpoint)
                if not read_only and control.is_enabled():
                    fill(control, str(tier[key]))
                if control.input_value() != str(tier[key]):
                    raise Stop('Quiz result tier value differs from request')
        click(popup.get_by_role('button', name='Cancel' if read_only else 'Save', exact=True))
        popup.wait_for(state='hidden', timeout=45000)
        click(modal.get_by_role('button', name='Cancel' if read_only else 'Save', exact=True))
        modal.wait_for(state='hidden', timeout=45000)

    tiers()
    click(frame.get_by_role('button', name='Save', exact=True))
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).count() == 1
               and frame.get_by_role('button', name='Save', exact=True).is_enabled(), 'Quiz save did not finish')
    reopen_editor(page, 'quiz', quiz_name, editor_url)
    close_initial()
    if step.get('categories'):
        categories(read_only=True)
    questions(read_only=True)
    tiers(read_only=True)
    return {'status': 'QUIZ_CONFIGURATION_SAVED_AND_REOPENED', 'kind': 'quiz',
            'editor_url': page.url, 'categories': step.get('categories', []),
            'questions': len(step.get('questions', [])), 'tiers': step.get('tiers'),
            'submission_verified': False}
