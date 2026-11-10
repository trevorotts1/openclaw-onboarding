"""Captured fixed-three-option Picture Choice authoring on an empty quiz page.

The native field is RADIO, but its picture grid is a distinct owner shape.
Media comes from explicitly approved existing Media Storage entries. Upload,
option resizing and style/switch editing are outside this bounded writer.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

from playwright_recipes import quiz_text_questions as native, quiz_choice_questions as choice
from playwright_recipes.skill6_playwright import Stop, assert_tenant, click, fill, wait_until


KIND = 'PICTURE_CHOICE'
ACTION = 'quiz_picture_choices'
DEFAULT_LABELS = ['Option1', 'Option2', 'Option3']


def _https(value):
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 for c in value):
        raise Stop('Picture Choice media requires its exact canonical HTTPS URL')
    try:
        parsed = urlsplit(value);port = parsed.port
    except ValueError:
        raise Stop('Picture Choice media URL is malformed') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or port not in (None, 443) or parsed.fragment):
        raise Stop('Picture Choice media requires canonical HTTPS without credentials or fragments')
    return value


def _question(value, *, new=False):
    if not isinstance(value, dict):raise Stop('Picture Choice inventory requires exact question objects')
    if value.get('field_type') != KIND:
        if new:raise Stop('Picture Choice authoring requires its explicit PICTURE_CHOICE type')
        return choice._question(value)
    key_name = 'expected_persisted_unique_key' if new else 'unique_key'
    if set(value) != native.PROPERTIES | {'options', key_name}:
        raise Stop('Picture Choice requires complete text/key/flags and all three label/media options')
    if not isinstance(value[key_name], str) or not re.fullmatch(r'contact\.[a-z][a-z0-9_]{0,127}', value[key_name]):
        raise Stop('Picture Choice requires its explicit expected persisted Contact Unique Key')
    projected = {key:deepcopy(value[key]) for key in native.PROPERTIES}
    projected['field_type'] = 'RADIO'
    native._question(projected, new=new, field_types=('RADIO',))
    options = value['options']
    if not isinstance(options, list) or len(options) != 3:
        raise Stop('Captured Picture Choice authoring supports exactly three explicit options')
    labels = []
    for option in options:
        keys = {'label', 'image_url', 'media_button_name'} if new else {'label', 'image_url'}
        if not isinstance(option, dict) or set(option) != keys:
            raise Stop('Picture Choice options require exact label, canonical image and approved catalog tile')
        label = option['label']
        if not native._text(label) or label != label.strip():raise Stop('Picture Choice label is empty or ambiguous')
        labels.append(label)
        _https(option['image_url'])
        if new and (not native._text(option['media_button_name'])
                    or option['media_button_name'] != option['media_button_name'].strip()):
            raise Stop('Picture Choice media requires its exact approved catalog button name')
    if len({label.casefold() for label in labels}) != 3:
        raise Stop('Picture Choice labels must be unique')
    if new:choice._option_transition(labels, DEFAULT_LABELS)
    return deepcopy(value)


def validate(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'payload'}
            or step.get('action', ACTION) != ACTION):
        raise Stop('Unsupported Picture Choice runner metadata')
    payload = step.get('payload')
    if (not isinstance(payload, dict)
            or set(payload) != native.owner_keys(payload) | {'acknowledge_shared_field_options'}
            or payload['acknowledge_shared_field_options'] is not True):
        raise Stop('Picture Choice needs full quiz inventory and explicit shared-field acknowledgement')
    projected = deepcopy(payload);projected.pop('acknowledge_shared_field_options')
    if not isinstance(projected.get('pages'), list) or not isinstance(projected.get('questions'), list):
        raise Stop('Picture Choice requires complete prior pages and one authored question')
    for owner in projected['pages']:
        if not isinstance(owner, dict) or not isinstance(owner.get('questions'), list):
            raise Stop('Picture Choice prior page inventory is malformed')
        for index, question in enumerate(owner['questions']):
            original = _question(question)
            owner['questions'][index] = {key:original[key] for key in native.properties_for(
                'RADIO' if original['field_type'] == KIND else original['field_type'])}
            if original['field_type'] == KIND:owner['questions'][index]['field_type'] = 'RADIO'
    if len(projected['questions']) != 1:
        raise Stop('Captured Picture Choice authors one question on one confirmed empty page')
    original = _question(projected['questions'][0], new=True)
    # Picture Choice and Multi Dropdown share the native Unique Key namespace;
    # a Query Key is a different property. Preserve blank unresolved old keys
    # without inventing one, and reject collisions in every known literal key.
    existing_keys = [q['unique_key'].casefold() for owner in payload['pages'] for q in owner['questions']
                     if isinstance(q.get('unique_key'), str) and q['unique_key']]
    if (len(set(existing_keys)) != len(existing_keys)
            or original['expected_persisted_unique_key'].casefold() in existing_keys):
        raise Stop('Picture Choice persisted Unique Key must be new and existing keys must be unambiguous')
    projected['questions'][0] = {key:original[key] for key in native.PROPERTIES}
    projected['questions'][0]['field_type'] = 'RADIO'
    native.validate({'action':'quiz_short_answers', 'payload':projected},
        field_types=choice.TYPES, new_types=('RADIO',), reserved_key=None)
    if not payload.get('create_page') and payload['pages'][payload['target_page'] - 1]['questions']:
        raise Stop('Picture Choice insertion requires a confirmed empty existing or explicitly appended page')
    return deepcopy(payload)


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _authored(question):
    result = deepcopy(question)
    result['unique_key'] = result.pop('expected_persisted_unique_key')
    result['options'] = [{key:value for key,value in option.items() if key != 'media_button_name'}
                         for option in question['options']]
    return result


def _tab(frame, name):
    control = native._one(frame.locator('.n-tabs-tab[data-name="' + name + '"]'),
                          'Native Picture Choice ' + name + ' tab changed')
    if control.locator('.n-tabs-tab__label').inner_text().strip() != name:
        raise Stop('Native Picture Choice inspector tab label changed')
    click(control)


def _choices(item):
    native._one(item.locator('[data-testid="picture-choice-grid"]'), 'Picture Choice grid is missing or ambiguous')
    cards = item.locator('[data-testid="picture-choice-card"]')
    if cards.count() != 3:raise Stop('Picture Choice grid requires exactly three captured cards')
    result = [];owner = None
    for index in range(3):
        card = cards.nth(index)
        field = native._one(card.locator('input[type="radio"]'), 'Picture Choice card radio is missing')
        identifier = field.get_attribute('id');name = field.get_attribute('name')
        if (not isinstance(name, str) or not re.fullmatch(r'(?:' + choice.UUID + r'|[A-Za-z0-9]{20})', name)
                or owner is not None and name != owner or identifier != name + '-' + str(index)
                or field.get_attribute('disabled') is None or field.input_value() != 'on'):
            raise Stop('Picture Choice card IDs/name/value do not bind one captured native owner')
        owner = name
        label = native._one(card.locator('span[data-testid="picture-choice-option-label-text"]'),
                            'Picture Choice option label changed')
        value = label.inner_text().strip()
        if (label.get_attribute('id') != identifier + '-label'
                or label.get_attribute('role') != 'textbox'
                or label.get_attribute('contenteditable') not in ('', 'true')
                or not native._text(value) or field.get_attribute('aria-label') != value):
            raise Stop('Picture Choice option label is not bound to its exact input owner')
        media = native._one(card.locator('[data-testid="picture-choice-option-media"]'),
                            'Picture Choice option media owner changed')
        if media.get_attribute('role') != 'button':raise Stop('Picture Choice media trigger is not its captured button')
        empty = card.locator('img[data-testid="picture-choice-empty-image"]')
        if empty.count():
            native._one(empty, 'Picture Choice empty media is ambiguous')
            if (empty.get_attribute('src') != '/assets/picture-choice-empty-42ddee2e.svg'
                    or card.locator('img').count() != 1):
                raise Stop('Picture Choice empty image differs from capture')
            image_url = None
        else:
            image = native._one(card.get_by_role('img', name=value, exact=True),
                                'Picture Choice authored image is missing or bound to another label')
            image_url = _https(image.get_attribute('src'))
        result.append({'id':identifier, 'owner':owner, 'label':value, 'image_url':image_url})
    return result


def _styles(frame):
    switches = frame.get_by_role('switch');count = switches.count()
    names = ['Show option label', 'Multiple selection', 'Other option', 'Spread to Columns'] if count == 4 else [
        'Show option label', 'Other option', 'Spread to Columns']
    if count not in (3, 4):raise Stop('Picture Choice option switches differ from captured transient/persisted shapes')
    states = []
    for index, name in enumerate(names):
        control = native._one(switches.nth(index), 'Picture Choice option switch changed')
        if control.locator('..').inner_text().strip() != name:
            raise Stop('Picture Choice option switch owner label changed')
        state = control.get_attribute('aria-checked')
        if state not in ('true', 'false'):raise Stop('Picture Choice option switch state is unreadable')
        states.append(state == 'true')
    expected = [True, False, False, True] if count == 4 else [True, False, True]
    if states != expected:raise Stop('Picture Choice writer supports only the captured default presentation switches')
    columns = native._one(frame.locator('#picture-choice-columns input'), 'Picture Choice columns control changed')
    cover = native._one(frame.locator('.n-base-selection-input[title="Cover"]'), 'Picture Choice default Cover fit changed')
    if columns.input_value() != '3' or cover.inner_text().strip() != 'Cover':
        raise Stop('Picture Choice writer supports captured three-column Cover presentation only')
    return {'columns':'3', 'image_fit':'Cover', 'show_option_label':True,
            'other_option':False, 'spread_to_columns':True, 'multiple_selection_present':count == 4}


def _read_picture(frame, item):
    native._close_properties(frame)
    label, kind = native._item_kind(item, field_types=('RADIO',))
    native._activate_item(frame, item, label)
    initial = _choices(item)
    click(native._one(frame.get_by_role('button', name='Open settings', exact=True),
                      'Picture Choice Open settings changed'))
    _tab(frame, 'Content')
    result = {'field_type':KIND}
    for key, selector in native.FIELD_INPUTS.items():
        result[key] = native._one(frame.locator(selector), 'Picture Choice ' + key + ' property changed').input_value()
    for key, selector in native.FLAGS.items():
        state = native._one(frame.locator(selector), 'Picture Choice ' + key + ' flag changed').get_attribute('aria-checked')
        if state not in ('true', 'false'):raise Stop('Picture Choice Boolean property is unreadable')
        result[key] = state == 'true'
    if label.inner_text().strip() not in (result['question'], result['question'] + '*', result['question'] + ' *'):
        raise Stop('Picture Choice selected properties and canvas label disagree')
    unique, custom_name, advanced = native._advanced_identity(frame)
    result['unique_key'] = unique.input_value()
    result['_unique_key_enabled'] = unique.is_enabled()
    result['_custom_field_name'] = custom_name.input_value()
    result['_unique_key_placeholder'] = advanced['_unique_key_placeholder']
    _tab(frame, 'Options')
    result['_styles'] = _styles(frame)
    labels = [];filenames = []
    for index in range(3):
        labels.append(native._one(frame.locator('#picture-choice-option-label-' + str(index) + ' input'),
                                  'Picture Choice Options label changed').input_value())
        filename = native._one(frame.locator('#picture-choice-option-filename-' + str(index) + ' input'),
                               'Picture Choice Options image filename changed')
        if filename.get_attribute('readonly') is None:raise Stop('Picture Choice Options filename must be read-only')
        filenames.append(filename.input_value())
    current = _choices(item)
    if current != initial or labels != [option['label'] for option in current]:
        raise Stop('Picture Choice inspector changed a native card or its exact label ownership')
    for filename, option in zip(filenames, current):
        expected = urlsplit(option['image_url']).path.rsplit('/', 1)[-1] if option['image_url'] else ''
        if filename != expected:raise Stop('Picture Choice inspector filename and canvas image disagree')
    result['_option_identity'] = current
    result['options'] = [{key:option[key] for key in ('label', 'image_url')} for option in current]
    native._close_properties(frame, required=True)
    return result


def _inventory(frame, plan):
    native._prepare_inventory(frame);result = []
    option_keys = {q['query_key'] for owner in plan['pages'] for q in owner['questions']
                   if q['field_type'] == 'RADIO' and 'options' in q}
    for _, canvas in native._owners(frame, plan):
        items = native._items(canvas);questions = []
        if not items.count():native._one(canvas.get_by_text('Drag and drop components', exact=True), 'Empty quiz page is not confirmed')
        for index in range(items.count()):
            item = items.nth(index)
            if item.locator('[data-testid="picture-choice-grid"]').count():
                question = _read_picture(frame, item)
            else:
                question = native._read_question(frame, item, field_types=choice.TYPES, metadata_reader=choice._metadata)
                kind = question['field_type']
                if kind == 'RADIO':question['_radio_input_ids'] = choice._radio_input_ids(item)
                if kind in ('CHECKBOX', *choice.DROPDOWNS) or kind == 'RADIO' and question['query_key'] in option_keys:
                    if kind in choice.DROPDOWNS:
                        label, _ = native._item_kind(item, field_types=choice.TYPES);native._activate_item(frame, item, label)
                    question['_option_identity'] = choice._choices(item, kind)
                    question['options'] = [option['value'] for option in question['_option_identity']]
                    if question['options'] != [option['label'] for option in question['_choice_controls']]:
                        raise Stop('Existing quiz choice properties and native labels disagree')
            questions.append(question)
        result.append(questions)
    return result


def _wait_baseline(frame, plan, expected=None):
    projected = deepcopy(plan)
    for owner in projected['pages']:
        for question in owner['questions']:
            if question['field_type'] == KIND:question['field_type'] = 'RADIO'
    values = deepcopy(expected)
    if values is not None:
        for owner in values:
            for question in owner:
                if question['field_type'] == KIND:question['field_type'] = 'RADIO'
    native._wait_baseline(frame, projected, expected=values)


def _target_page(frame, plan, before):
    if not plan.get('create_page'):return plan, deepcopy(before)
    native._prepare_inventory(frame);native._close_properties(frame)
    if _inventory(frame, plan) != before:raise Stop('Quiz changed before the single Picture Choice Add Page')
    owners = native._owners(frame, plan)
    if frame.locator('#add-slide-button').count() != len(owners):raise Stop('Picture Choice Add Page inventory changed')
    for owner, _ in owners:native._one(owner.locator('button#add-slide-button'), 'Add Page has an ambiguous owner')
    runtime = deepcopy(plan);runtime['pages'].append({'label':plan['new_page_label'], 'questions':[]})
    click(owners[-1][0].locator('button#add-slide-button'))
    def ready():
        count = frame.locator('.survey-form-container.flex').count()
        if count not in (len(owners), len(owners) + 1):raise Stop('Picture Choice Add Page produced an unexpected owner count')
        return count == len(owners) + 1
    wait_until(ready, 'Picture Choice Add Page did not settle; do not repeat it')
    _wait_baseline(frame, runtime, [*before, []])
    if _inventory(frame, runtime) != [*before, []]:raise Stop('Picture Choice Add Page changed old quiz questions')
    return runtime, [*deepcopy(before), []]


def _open_properties(frame, item):
    native._close_properties(frame)
    label, _ = native._item_kind(item, field_types=('RADIO',))
    native._activate_item(frame, item, label)
    click(native._one(frame.get_by_role('button', name='Open settings', exact=True), 'Picture Choice settings control changed'))
    _tab(frame, 'Content')


def _media(page, frame, item, index, option):
    before = _choices(item)
    card = item.locator('[data-testid="picture-choice-card"]').nth(index)
    media = native._one(card.locator('[data-testid="picture-choice-option-media"]'), 'Picture Choice media owner changed')
    click(media)
    dialog = page.get_by_role('dialog')
    dialog.wait_for(state='visible', timeout=45000)
    native._one(dialog, 'Picture Choice Media Storage dialog is missing or ambiguous')
    native._one(dialog.get_by_text('Media Storage', exact=True), 'Picture Choice chooser is not the captured Media Storage dialog')
    tile = native._one(dialog.get_by_role('button', name=option['media_button_name'], exact=True),
                       'Approved Picture Choice media catalog tile is missing or ambiguous')
    thumbnail = 'https://images.leadconnectorhq.com/image/f_webp/q_80/r_320/u_' + option['image_url']
    native._one(tile.locator('img[src=' + json.dumps(thumbnail) + ']'),
                'Approved Picture Choice media tile does not carry its exact expected thumbnail source')
    tile.dblclick()
    dialog.wait_for(state='hidden', timeout=45000)
    desired = deepcopy(before);desired[index]['image_url'] = option['image_url']
    wait_until(lambda:_choices(item) == desired, 'Picture Choice ignored media selection or changed a sibling option')


def _write(page, frame, item, question):
    before = _read_picture(frame, item)
    if (before['query_key'] != 'picture_choice' or before['placeholder'] or before['short_label']
            or before['required'] is not False or before['hidden'] is not False
            or before['unique_key'] != ''
            or before['_unique_key_enabled'] is not True
            or [option['label'] for option in before['options']] != DEFAULT_LABELS
            or any(option['image_url'] is not None for option in before['options'])
            or before['_styles']['multiple_selection_present'] is not True):
        raise Stop('New Picture Choice differs from captured default properties, media or presentation')
    # The measured canvas-label path also updates the new native Custom Field
    # Name. Do not assume that changing a sidebar title has the same lifecycle.
    label, _ = native._item_kind(item, field_types=('RADIO',))
    fill(label, question['question']);label.press('Tab')
    _open_properties(frame, item)
    for key, selector in native.FIELD_INPUTS.items():
        control = native._one(frame.locator(selector), 'Picture Choice authored property changed')
        if control.input_value() != question[key]:fill(control, question[key]);control.press('Tab')
        if control.input_value() != question[key]:raise Stop('Picture Choice ignored an authored property')
    for key, selector in native.FLAGS.items():
        control = native._one(frame.locator(selector), 'Picture Choice authored flag changed')
        expected = str(question[key]).lower()
        if control.get_attribute('aria-checked') != expected:click(control)
        wait_until(lambda:control.get_attribute('aria-checked') == expected, 'Picture Choice ignored an authored flag')
    unique, name, _ = native._advanced_identity(frame)
    if unique.input_value() != '' or name.input_value() != question['question']:
        raise Stop('New Picture Choice custom field identity changed before native Save')
    native._close_properties(frame, required=True)
    defaults = _choices(item)
    for index, option in enumerate(question['options']):
        expected = deepcopy(defaults)
        for offset in range(index):expected[offset]['label'] = question['options'][offset]['label']
        if _choices(item) != expected:raise Stop('Picture Choice changed an option before label authoring')
        card = item.locator('[data-testid="picture-choice-card"]').nth(index)
        label = native._one(card.locator('span[data-testid="picture-choice-option-label-text"]'), 'Picture Choice authored option label changed')
        fill(label, option['label']);label.press('Tab')
        expected[index]['label'] = option['label']
        wait_until(lambda:_choices(item) == expected, 'Picture Choice option label did not settle exactly')
    for index, option in enumerate(question['options']):_media(page, frame, item, index, option)
    after = _read_picture(frame, item)
    authored = _authored(question)
    if ({key:value for key,value in choice._properties([[after]])[0][0].items() if key != 'unique_key'}
            != {key:value for key,value in authored.items() if key != 'unique_key'}
            or after['unique_key'] != '' or after['_unique_key_enabled'] is not True
            or after['_custom_field_name'] != question['question']
            or after['_styles'] != before['_styles']):
        raise Stop('Picture Choice differs from authored properties/media or changed protected presentation before Save')
    return after


def _minted(before, after, question):
    """Only the new field may acquire its persisted owner/key on first Save."""
    if choice._properties([[after]]) != [[_authored(question)]]:
        raise Stop('Persisted Picture Choice differs from explicit authored labels, media, properties or Unique Key')
    old_options = before['_option_identity'];new_options = after['_option_identity']
    old_owner = old_options[0]['owner'];new_owner = new_options[0]['owner']
    if not re.fullmatch(choice.UUID, old_owner) or not re.fullmatch(r'[A-Za-z0-9]{20}', new_owner) or old_owner == new_owner:
        raise Stop('Picture Choice did not acquire exactly one captured persisted owner identity')
    expected_options = [{**option, 'owner':new_owner, 'id':new_owner + '-' + str(index)}
                        for index,option in enumerate(old_options)]
    if new_options != expected_options:raise Stop('Picture Choice Save changed option order, label or media while minting its identity')
    styles = deepcopy(before['_styles']);styles['multiple_selection_present'] = False
    if (after['_styles'] != styles or after['_custom_field_name'] != question['question']
            or after['_unique_key_enabled'] is not False):
        raise Stop('Picture Choice Save changed protected style/custom-field name beyond its captured transition')


def validate_receipt(value, step):
    plan = validate(step);question = plan['questions'][0]
    keys = {'status','kind','editor_url','configuration_sha256','question_count','target_page',
            'independent_readback','dependency_api_used','behavior_verified','submission_verified',
            'field_id','persisted_unique_key','image_urls_sha256'}
    expected = {'status':'QUIZ_PICTURE_CHOICES_SAVED_AND_REOPENED','kind':ACTION,
        'editor_url':plan['start_url'],'configuration_sha256':configuration_hash(step),
        'question_count':1,'target_page':plan['target_page'],'independent_readback':'VERIFIED',
        'dependency_api_used':False,'behavior_verified':False,'submission_verified':False,
        'persisted_unique_key':question['expected_persisted_unique_key'],
        'image_urls_sha256':[hashlib.sha256(option['image_url'].encode()).hexdigest() for option in question['options']]}
    if (not isinstance(value, dict) or set(value) != keys
            or any(value[key] != expected_value or type(value[key]) is not type(expected_value) for key,expected_value in expected.items())
            or not isinstance(value['field_id'], str) or not re.fullmatch(r'[A-Za-z0-9]{20}', value['field_id'])):
        raise Stop('Picture Choice completion is malformed, incomplete or unbound')
    return deepcopy(value)


def configure(page, step):
    plan = validate(step);frame = page.frame_locator('iframe[name="quiz-builder-app"]')
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    def identity():
        if page.url != plan['start_url'] or title.count() != 1 or title.input_value() != plan['expected_quiz_name']:
            raise Stop('Picture Choice exact quiz owner changed')
        assert_tenant(page, plan)
    title.wait_for(state='visible', timeout=45000);native._wait_editor_identity(page, title, plan);identity();_wait_baseline(frame, plan)
    before = _inventory(frame, plan)
    if choice._properties(before) != [owner['questions'] for owner in plan['pages']]:
        raise Stop('Picture Choice prior quiz/page/question inventory differs from the complete expected state')
    runtime, desired = _target_page(frame, plan, before);owner = plan['target_page'] - 1
    question = plan['questions'][0]
    identity()
    item = native._append_tile(frame, runtime, 'Picture Choice', page=page)
    label, kind = native._item_kind(item, field_types=('RADIO',))
    if not re.fullmatch(r'Picture Choice [a-z0-9]{6}', label.inner_text().strip()):
        raise Stop('New Picture Choice generated label differs from capture')
    native._activate_item(frame, item, label)
    native._prewrite_delta(frame, runtime, desired, _inventory, {'field_type':KIND})
    added = _choices(item)
    if not re.fullmatch(choice.UUID, added[0]['owner']):raise Stop('New Picture Choice has no captured transient UUID')
    old_ids = {option['id'] for owners in desired for prior in owners for option in prior.get('_option_identity', [])}
    old_names = {option.get('owner') for owners in desired for prior in owners for option in prior.get('_option_identity', [])}
    if old_ids.intersection(option['id'] for option in added) or added[0]['owner'] in old_names:
        raise Stop('New Picture Choice reused an existing native field owner')
    desired[owner].append(_write(page, frame, item, question))
    if _inventory(frame, runtime) != desired:raise Stop('Picture Choice authoring changed existing questions or another page')
    identity();save = native._one(frame.get_by_role('button', name='Save', exact=True), 'Picture Choice native Save changed')
    if not save.is_enabled():raise Stop('Picture Choice configuration remains invalid')
    click(save);wait_until(lambda:save.is_enabled(), 'Picture Choice Save did not finish')
    page.wait_for_load_state('networkidle', timeout=45000)
    native.reopen_editor(page, 'quiz', plan['expected_quiz_name'], plan['start_url'])
    frame = page.frame_locator('iframe[name="quiz-builder-app"]');title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000);native._wait_editor_identity(page, title, plan);identity();_wait_baseline(frame, runtime, desired)
    after = _inventory(frame, runtime)
    if len(after) != len(desired) or any(
            (current[:-1] if index == owner else current) != (expected[:-1] if index == owner else expected)
            for index,(current,expected) in enumerate(zip(after,desired))) or len(after[owner]) != len(desired[owner]):
        raise Stop('Picture Choice persisted Save changed old questions or page owners')
    _minted(desired[owner][-1], after[owner][-1], question)
    field_id = after[owner][-1]['_option_identity'][0]['owner']
    if field_id in old_names:raise Stop('Persisted Picture Choice acquired an existing field owner')
    return validate_receipt({'status':'QUIZ_PICTURE_CHOICES_SAVED_AND_REOPENED','kind':ACTION,
        'editor_url':page.url,'configuration_sha256':configuration_hash(step),'question_count':1,
        'target_page':plan['target_page'],'independent_readback':'VERIFIED','dependency_api_used':False,
        'behavior_verified':False,'submission_verified':False,'field_id':field_id,
        'persisted_unique_key':question['expected_persisted_unique_key'],
        'image_urls_sha256':[hashlib.sha256(option['image_url'].encode()).hexdigest() for option in question['options']]},step)
