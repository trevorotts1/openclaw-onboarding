"""Captured variable-count Picture Choice authoring on an inventoried quiz page.

The native field is RADIO, but its picture grid is a distinct owner shape.
Media comes from explicitly approved existing Media Storage entries. Upload,
Local uploads and uncaptured switch modes remain outside this bounded writer. Count authoring uses the
measured indexed canvas Add/Delete controls and preserves retained card owners.
"""
from copy import deepcopy
import hashlib
import json
import os
import stat
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from playwright_recipes import quiz_text_questions as native, quiz_choice_questions as choice
from playwright_recipes.skill6_playwright import Stop, assert_tenant, click, fill, wait_until


KIND = 'PICTURE_CHOICE'
ACTION = 'quiz_picture_choices'
DEFAULT_LABELS = ['Option1', 'Option2', 'Option3']
DEFAULT_LABEL_PROFILES = (tuple(DEFAULT_LABELS), ('Option 1', 'Option 2', 'Option 3'))


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


def _question(value, *, new=False, default_labels=True):
    if not isinstance(value, dict):raise Stop('Picture Choice inventory requires exact question objects')
    if value.get('field_type') != KIND:
        if new:raise Stop('Picture Choice authoring requires its explicit PICTURE_CHOICE type')
        return choice._question(value)
    key_name = 'expected_persisted_unique_key' if new else 'unique_key'
    keys=native.PROPERTIES | {'options', key_name}
    if set(value) not in (keys,keys|{'presentation'} if new else keys):
        raise Stop('Picture Choice requires complete text/key/flags and its ordered label/media options')
    if not isinstance(value[key_name], str) or not re.fullmatch(r'contact\.[a-z][a-z0-9_]{0,127}', value[key_name]):
        raise Stop('Picture Choice requires its explicit expected persisted Contact Unique Key')
    if 'presentation' in value:
        _presentation(value['presentation'])
    projected = {key:deepcopy(value[key]) for key in native.PROPERTIES}
    projected['field_type'] = 'RADIO'
    native._question(projected, new=new, field_types=('RADIO',))
    options = value['options']
    if not isinstance(options, list) or not 2 <= len(options) <= 50:
        raise Stop('Picture Choice authoring requires two to fifty explicit options')
    labels = []
    for option in options:
        keys = ({'label', 'image_url', 'media_button_name'}, {'label','local_file','sha256'}) if new else ({'label', 'image_url'},)
        if not isinstance(option, dict) or set(option) not in keys:
            raise Stop('Picture Choice options require exact label, canonical image and approved catalog tile')
        label = option['label']
        if not native._text(label) or label != label.strip():raise Stop('Picture Choice label is empty or ambiguous')
        labels.append(label)
        if 'local_file' in option:
            if (not isinstance(option['local_file'],str) or not Path(option['local_file']).is_absolute()
                    or Path(option['local_file']).suffix.lower() not in ('.png','.jpg','.jpeg')
                    or not isinstance(option['sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}',option['sha256'])):
                raise Stop('Local Picture Choice upload requires absolute PNG/JPEG and approved SHA256')
        else:_https(option['image_url'])
        if new and 'media_button_name' in option and (not native._text(option['media_button_name'])
                    or option['media_button_name'] != option['media_button_name'].strip()):
            raise Stop('Picture Choice media requires its exact approved catalog button name')
    if len({label.casefold() for label in labels}) != len(options):
        raise Stop('Picture Choice labels must be unique')
    if new and default_labels and len(options) == 3:
        # Both complete initial vectors were captured. Refuse any authored
        # rename collision under either profile before a native insertion.
        for profile in DEFAULT_LABEL_PROFILES:choice._option_transition(labels, profile)
    return deepcopy(value)


def validate(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'payload'}
            or step.get('action', ACTION) != ACTION):
        raise Stop('Unsupported Picture Choice runner metadata')
    payload = step.get('payload')
    if (not isinstance(payload, dict)
            or set(payload) != native.owner_keys(payload) | {'acknowledge_shared_field_options'}
                | ({'update_question_index'} if 'update_question_index' in payload else set())
            or payload['acknowledge_shared_field_options'] is not True):
        raise Stop('Picture Choice needs full quiz inventory and explicit shared-field acknowledgement')
    projected = deepcopy(payload);projected.pop('acknowledge_shared_field_options')
    update_index = projected.pop('update_question_index', None)
    updating = 'update_question_index' in payload
    if updating and (type(update_index) is not int or update_index < 0 or 'create_page' in payload):
        raise Stop('Picture Choice updates need one existing zero-based question index and cannot create a page')
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
        raise Stop('Captured Picture Choice authors exactly one question on its inventoried target page')
    original = _question(projected['questions'][0], new=True, default_labels=not updating)
    if updating:
        target = payload.get('target_page')
        if (type(target) is not int or not 1 <= target <= len(payload['pages'])
                or update_index >= len(payload['pages'][target - 1]['questions'])):
            raise Stop('Picture Choice update index is outside the exact existing target page')
        prior = payload['pages'][target - 1]['questions'][update_index]
        if (prior.get('field_type') != KIND or original['expected_persisted_unique_key'] != prior['unique_key']
                or any(original[key] != prior[key] for key in native.PROPERTIES)):
            raise Stop('Picture Choice option updates preserve the exact existing field key, text and flags')
        retained = min(len(original['options']), len(prior['options']))
        choice._option_transition([option['label'] for option in original['options'][:retained]],
                                  [option['label'] for option in prior['options'][:retained]])
        projected['pages'][target - 1]['questions'].pop(update_index)
    # Picture Choice and Multi Dropdown share the native Unique Key namespace;
    # a Query Key is a different property. Preserve blank unresolved old keys
    # without inventing one, and reject collisions in every known literal key.
    existing_keys = [q['unique_key'].casefold() for page_index, owner in enumerate(payload['pages'])
                     for question_index, q in enumerate(owner['questions'])
                     if isinstance(q.get('unique_key'), str) and q['unique_key']
                     and not (updating and page_index == payload['target_page'] - 1 and question_index == update_index)]
    if (len(set(existing_keys)) != len(existing_keys)
            or original['expected_persisted_unique_key'].casefold() in existing_keys):
        raise Stop('Picture Choice persisted Unique Key must be new and existing keys must be unambiguous')
    projected['questions'][0] = {key:original[key] for key in native.PROPERTIES}
    projected['questions'][0]['field_type'] = 'RADIO'
    native.validate({'action':'quiz_short_answers', 'payload':projected},
        field_types=choice.TYPES, new_types=('RADIO',), reserved_key=None)
    return deepcopy(payload)


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _stage_local_assets(plan, directory):
    """Freeze caller-approved PNG/JPEG bytes before any quiz mutation."""
    from io import BytesIO
    staged={};limit=25*1024*1024
    for index,option in enumerate(plan['questions'][0]['options']):
        if 'local_file' not in option:continue
        try:from PIL import Image
        except ImportError:raise Stop('Local Picture Choice upload requires Pillow for image verification') from None
        descriptor=None
        try:
            descriptor=os.open(option['local_file'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            info=os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=limit:
                raise Stop('Picture Choice local image must be a regular file at most 25 MiB')
            with os.fdopen(descriptor,'rb') as stream:
                descriptor=None;content=stream.read(limit+1)
            if len(content)>limit or hashlib.sha256(content).hexdigest()!=option['sha256']:
                raise Stop('Picture Choice local image differs from approved SHA256')
            with Image.open(BytesIO(content)) as image:
                fmt=image.format;image.verify()
            suffix=Path(option['local_file']).suffix.lower()
            if (fmt=='PNG' and suffix!='.png') or (fmt=='JPEG' and suffix not in ('.jpg','.jpeg')) or fmt not in ('PNG','JPEG'):
                raise Stop('Picture Choice local image MIME and extension must be PNG or JPEG')
        except Stop:raise
        except Exception:raise Stop('Picture Choice local image is unavailable, unsafe or invalid') from None
        finally:
            if descriptor is not None:os.close(descriptor)
        mime='image/png' if fmt=='PNG' else 'image/jpeg'
        path=Path(directory)/(option['sha256']+('.png' if fmt=='PNG' else '.jpg'))
        path.write_bytes(content);staged[index]=(path,len(content),mime,option['sha256'])
    return staged


def _authored(question):
    result = deepcopy(question)
    result['unique_key'] = result.pop('expected_persisted_unique_key')
    result.pop('presentation',None)
    if any('local_file' in option for option in question['options']):
        raise Stop('Local Picture Choice uploads need their observed URL before a following compiled batch')
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
    other=cards.locator('[data-testid="picture-choice-other-image"]')
    if other.count() not in (0,1):raise Stop('Picture Choice Other card is ambiguous')
    count=cards.count()-other.count()
    if not 2 <= count <= 50:raise Stop('Picture Choice grid count is outside the bounded native inventory')
    result = [];owner = None
    for index in range(count):
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
        media_role=media.get_attribute('role')
        empty = card.locator('img[data-testid="picture-choice-empty-image"]')
        if empty.count():
            if media_role!='button':raise Stop('Empty Picture Choice media trigger is not its captured button')
            native._one(empty, 'Picture Choice empty media is ambiguous')
            if (empty.get_attribute('src') != '/assets/picture-choice-empty-42ddee2e.svg'
                    or card.locator('img').count() != 1):
                raise Stop('Picture Choice empty image differs from capture')
            image_url = None
        else:
            if media_role is None and media.get_attribute('tabindex')=='-1':
                # Current filled media has a non-button wrapper and one exact
                # index-bound Change Image action. Empty cards keep their
                # captured Upload Image button; no generic role relaxation.
                actions=native._one(media.locator('[data-testid="picture-choice-filled-image-actions"]'),
                                    'Filled Picture Choice media action owner changed')
                change=native._one(actions.locator('button[data-testid="picture-choice-change-image-'+str(index)+'"]'),
                                   'Filled Picture Choice Change Image index changed')
                if (change.get_attribute('aria-label')!='Change Image' or change.get_attribute('type')!='button'
                        or change.get_attribute('tabindex')!='0' or not change.is_enabled()
                        or media.locator('button[aria-label="Change Image"]').count()!=1):
                    raise Stop('Filled Picture Choice media lacks its exact captured Change Image control')
            elif media_role!='button':
                raise Stop('Filled Picture Choice media differs from both captured container profiles')
            image = native._one(card.get_by_role('img', name=value, exact=True),
                                'Picture Choice authored image is missing or bound to another label')
            image_url = _https(image.get_attribute('src'))
        result.append({'id':identifier, 'owner':owner, 'label':value, 'image_url':image_url})
    if other.count():
        card=cards.nth(count)
        field=native._one(card.locator('input[type="radio"]'),'Picture Choice Other radio changed')
        tooltip=native._one(card.locator('[data-testid="picture-choice-other-image-tooltip-trigger"]'),
                            'Picture Choice Other image owner changed')
        image=native._one(card.locator('[data-testid="picture-choice-other-image"]'),
                          'Picture Choice Other image changed')
        label=native._one(card.locator('[data-testid="picture-choice-option-label-text"]'),
                          'Picture Choice Other label changed')
        if (field.get_attribute('id')!=owner+'-'+str(count) or field.get_attribute('name')!=owner
                or field.get_attribute('aria-label')!='Other' or field.get_attribute('disabled') is None
                or label.inner_text().strip()!='Other' or label.get_attribute('contenteditable') is not None
                or tooltip.get_attribute('aria-label')!='An image cannot be uploaded for the Other option.'
                or image.get_attribute('src')!='/assets/picture-choice-other-db07bc65.svg'):
            raise Stop('Picture Choice Other card differs from captured owner')
    return result



def _presentation(value):
    required={'show_option_label','columns'}
    optional={'image_fit','spread_to_columns','other_option'}
    if (not isinstance(value,dict) or not required <= set(value) or set(value)-required-optional
            or type(value['show_option_label']) is not bool
            or any(type(value[key]) is not bool for key in ('spread_to_columns','other_option') if key in value)
            or value['columns'] is not None and (type(value['columns']) is not int or not 1<=value['columns']<=12)
            or 'spread_to_columns' in value and (value['columns'] is None) == value['spread_to_columns']
            or 'image_fit' in value and value['image_fit'] not in ('Cover','Contain','Fill')):
        raise Stop('Picture Choice presentation needs exact labels, fit, switches and active columns')
    return deepcopy(value)


def _write_presentation(frame,item,value):
    desired=_presentation(value)
    _open_properties(frame,item);_tab(frame,'Options')
    before=_styles(frame); expected=deepcopy(before)
    spread=desired.get('spread_to_columns',before['spread_to_columns'])
    if (desired['columns'] is None) == spread:
        raise Stop('Picture Choice columns must be specified exactly when Spread is enabled')
    switches=frame.get_by_role('switch')
    planned=((0,'show_option_label',desired['show_option_label']),
             (switches.count()-2,'other_option',desired.get('other_option',before['other_option'])),
             (switches.count()-1,'spread_to_columns',spread))
    for index,key,wanted in planned:
        if before[key]!=wanted and not switches.nth(index).is_enabled():
            raise Stop('Requested Picture Choice switch is not editable')
    if spread and before['spread_to_columns'] and before['columns']!=str(desired['columns']):
        if not native._one(frame.locator('#picture-choice-columns input'),'Picture Choice columns control changed').is_enabled():
            raise Stop('Requested Picture Choice columns are not editable')
    for index,key,wanted in planned:
        control=native._one(switches.nth(index),'Picture Choice option switch changed')
        if expected[key]!=wanted:
            if not control.is_enabled():raise Stop('Requested Picture Choice switch is not editable')
            click(control)
            wait_until(lambda:control.get_attribute('aria-checked')==str(wanted).lower(),
                       'Picture Choice switch did not settle')
            expected[key]=wanted
            if key=='spread_to_columns':
                # The columns control disappears with Spread off. When enabled,
                # inspect its native value before setting the requested value.
                expected['columns']=_styles(frame)['columns']
            if _styles(frame)!=expected:raise Stop('Picture Choice switch changed protected presentation')
    if spread and expected['columns']!=str(desired['columns']):
        columns=native._one(frame.locator('#picture-choice-columns input'),'Picture Choice columns control changed')
        if not columns.is_enabled():raise Stop('Requested Picture Choice columns are not editable')
        fill(columns,str(desired['columns']));columns.press('Tab');expected['columns']=str(desired['columns'])
    fit=desired.get('image_fit',before['image_fit'])
    if before['image_fit']!=fit:
        select=native._one(frame.locator('#picture-choice-image-fit .n-base-selection'),
                           'Picture Choice image-fit selection changed')
        if not select.is_enabled():raise Stop('Requested Picture Choice image fit is not editable')
        click(select)
        options=[native._one(frame.locator('p:visible').filter(has_text=re.compile(r'^\s*'+name+r'\s*$')),
                             'Picture Choice image-fit menu changed') for name in ('Cover','Contain','Fill')]
        click(options[('Cover','Contain','Fill').index(fit)]);expected['image_fit']=fit
    if _styles(frame)!=expected:
        raise Stop('Picture Choice presentation did not settle or changed a protected property')
    native._close_properties(frame,required=True)
    return expected


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
    if count==4 and states[1] is not False:
        raise Stop('Picture Choice multiple selection differs from the supported profile')
    columns = frame.locator('#picture-choice-columns input')
    if states[-1]:
        native._one(columns, 'Picture Choice columns control changed')
        value=columns.input_value()
    else:
        if columns.count():raise Stop('Picture Choice columns control remained when Spread is off')
        value=None
    fit = native._one(frame.locator('#picture-choice-image-fit .n-base-selection-input[title]'), 'Picture Choice image-fit selection changed')
    fit_value=fit.get_attribute('title')
    if (value is not None and not re.fullmatch(r'[1-9]|1[0-2]',value) or fit_value not in ('Cover','Contain','Fill')
            or fit.inner_text().strip()!=fit_value):
        raise Stop('Picture Choice columns or image fit differs from captured controls')
    return {'columns':value, 'image_fit':fit_value, 'show_option_label':states[0],
            'other_option':states[-2], 'spread_to_columns':states[-1], 'multiple_selection_present':count == 4}


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
    if bool(item.locator('[data-testid="picture-choice-other-image"]').count()) != result['_styles']['other_option']:
        raise Stop('Picture Choice Other switch and canvas card disagree')
    labels = [];filenames = []
    for index in range(len(initial)):
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


def _media(page, frame, item, index, option, staged=None):
    if ('local_file' in option)!=(staged is not None):
        raise Stop('Picture Choice upload lacks its frozen approved asset')
    editor_url=page.url
    before = _choices(item)
    card = item.locator('[data-testid="picture-choice-card"]').nth(index)
    media = native._one(card.locator('[data-testid="picture-choice-option-media"]'), 'Picture Choice media owner changed')
    if before[index]['image_url'] is None or media.get_attribute('role') == 'button':
        control = media
    else:
        control = native._one(media.locator('button[data-testid="picture-choice-change-image-' + str(index) + '"][aria-label="Change Image"]'),
                              'Filled Picture Choice Change Image owner changed')
    if not control.is_enabled():raise Stop('Picture Choice media action is disabled')
    click(control)
    dialog = page.get_by_role('dialog')
    dialog.wait_for(state='visible', timeout=45000)
    native._one(dialog, 'Picture Choice Media Storage dialog is missing or ambiguous')
    native._one(dialog.get_by_text('Media Storage', exact=True), 'Picture Choice chooser is not the captured Media Storage dialog')
    if staged is not None:
        path,size,mime,source_hash=staged
        native._one(dialog.get_by_role('grid',name='Files',exact=True),'Media Storage Files owner changed')
        native._one(dialog.get_by_text('My Media',exact=True),'Media Storage current folder changed')
        native._one(dialog.get_by_role('button',name='Upload media',exact=True),'Media Storage upload owner changed')
        tiles=dialog.get_by_role('button',name=re.compile(r'^'+re.escape(path.name)+r'(?:\s|$)'))
        if tiles.count():raise Stop('Approved upload filename already exists; reconcile before upload')
        file=page.locator('#file-upload-input[type="file"]')
        if file.count()!=1 or file.get_attribute('multiple') is None:
            raise Stop('Media Storage native file input changed')
        if page.url!=editor_url:raise Stop('Quiz editor identity changed before media upload')
        file.set_input_files(str(path))
        selected=file.evaluate('(element)=>Array.from(element.files||[]).map(file=>({name:file.name,size:file.size,type:file.type}))')
        if selected!=[{'name':path.name,'size':size,'type':mime}]:
            raise Stop('Media Storage did not select the approved image bytes')
        wait_until(lambda:tiles.count()==1 and tiles.is_visible(),'Uploaded media tile did not settle uniquely')
        tile=native._one(tiles,'Uploaded media tile is ambiguous')
        image=native._one(tile.locator('img'),'Uploaded media tile thumbnail changed')
        prefix='https://images.leadconnectorhq.com/image/f_webp/q_80/r_320/u_'
        thumbnail=image.get_attribute('src')
        if not isinstance(thumbnail,str) or not thumbnail.startswith(prefix):
            raise Stop('Uploaded media tile has no captured canonical thumbnail source')
        target=_https(thumbnail[len(prefix):])
    else:
        tile = native._one(dialog.get_by_role('button', name=option['media_button_name'], exact=True),
                           'Approved Picture Choice media catalog tile is missing or ambiguous')
        thumbnail = 'https://images.leadconnectorhq.com/image/f_webp/q_80/r_320/u_' + option['image_url']
        native._one(tile.locator('img[src=' + json.dumps(thumbnail) + ']'),
                    'Approved Picture Choice media tile does not carry its exact expected thumbnail source')
        target=option['image_url']
    if page.url!=editor_url:raise Stop('Quiz editor identity changed before media selection')
    tile.dblclick()
    dialog.wait_for(state='hidden', timeout=45000)
    desired = deepcopy(before);desired[index]['image_url'] = target
    wait_until(lambda:_choices(item) == desired, 'Picture Choice ignored media selection or changed a sibling option')
    if staged is not None:
        option.pop('local_file');option.pop('sha256');option['image_url']=target
    return target




def _resize_options(frame,item,target):
    """Change only the tail through captured index-bound Add/Delete controls."""
    current=_choices(item)
    while len(current)!=target:
        before=deepcopy(current);count=len(before);adding=count<target
        if adding:
            control=native._one(item.locator('button[data-testid="picture-choice-preview-add-option"]'),
                                'Picture Choice Add option owner changed')
        else:
            card=item.locator('[data-testid="picture-choice-card"]').nth(count-1)
            control=native._one(card.locator('button[data-testid="picture-choice-delete-option-'+str(count-1)+'"][aria-label="Delete option"]'),
                                'Picture Choice tail Delete option owner changed')
        if not control.is_enabled():raise Stop('Picture Choice option-count control is disabled')
        click(control);wanted=count+(1 if adding else -1)
        def settled():
            observed=item.locator('[data-testid="picture-choice-card"]').count() - item.locator('[data-testid="picture-choice-other-image"]').count()
            if observed not in (count,wanted):raise Stop('Picture Choice resize changed an unexpected number of cards')
            return observed==wanted
        wait_until(settled,'Picture Choice option-count action did not settle exactly once; do not repeat it')
        current=_choices(item)
        if adding:
            if (current[:-1]!=before or current[-1]['owner']!=before[0]['owner']
                    or current[-1]['image_url'] is not None):
                raise Stop('Picture Choice Add changed retained cards or added a nonempty/foreign card')
        elif current!=before[:-1]:
            raise Stop('Picture Choice Delete changed a retained card identity, label or media')
    return current


def _default_label_profile(labels):
    profile=tuple(labels)
    if profile not in DEFAULT_LABEL_PROFILES:
        raise Stop('New Picture Choice option labels differ from both complete captured default profiles')
    return profile


def _write(page, frame, item, question, staged=None):
    before = _read_picture(frame, item)
    _default_label_profile([option['label'] for option in before['options']])
    if (before['query_key'] != 'picture_choice' or before['placeholder'] or before['short_label']
            or before['required'] is not False or before['hidden'] is not False
            or before['unique_key'] != ''
            or before['_unique_key_enabled'] is not True
            or any(option['image_url'] is not None for option in before['options'])
            or before['_styles']!={'columns':'3','image_fit':'Cover','show_option_label':True,
                'other_option':False,'spread_to_columns':True,'multiple_selection_present':True}):
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
    defaults = _resize_options(frame,item,len(question['options']))
    choice._option_transition([option['label'] for option in question['options']], [option['label'] for option in defaults])
    for index, option in enumerate(question['options']):
        expected = deepcopy(defaults)
        for offset in range(index):expected[offset]['label'] = question['options'][offset]['label']
        if _choices(item) != expected:raise Stop('Picture Choice changed an option before label authoring')
        card = item.locator('[data-testid="picture-choice-card"]').nth(index)
        label = native._one(card.locator('span[data-testid="picture-choice-option-label-text"]'), 'Picture Choice authored option label changed')
        fill(label, option['label']);label.press('Tab')
        expected[index]['label'] = option['label']
        wait_until(lambda:_choices(item) == expected, 'Picture Choice option label did not settle exactly')
    for index, option in enumerate(question['options']):_media(page, frame, item, index, option, (staged or {}).get(index))
    expected_styles=(_write_presentation(frame,item,question['presentation']) if 'presentation' in question else before['_styles'])
    after = _read_picture(frame, item)
    authored = _authored(question)
    if ({key:value for key,value in choice._properties([[after]])[0][0].items() if key != 'unique_key'}
            != {key:value for key,value in authored.items() if key != 'unique_key'}
            or after['unique_key'] != '' or after['_unique_key_enabled'] is not True
            or after['_custom_field_name'] != question['question']
            or after['_styles'] != expected_styles):
        raise Stop('Picture Choice differs from authored properties/media or changed protected presentation before Save')
    return after


def _update_options(page, frame, item, question, staged=None):
    """Edit inventoried saved cards through the same captured canvas controls."""
    before = _read_picture(frame, item)
    if (before['unique_key'] != question['expected_persisted_unique_key']
            or before['_unique_key_enabled'] is not False
            or not re.fullmatch(r'[A-Za-z0-9]{20}', before['_option_identity'][0]['owner'])
            or any(before[key] != question[key] for key in native.PROPERTIES)):
        raise Stop('Picture Choice update no longer binds the exact persisted field')
    current = _resize_options(frame, item, len(question['options']))
    choice._option_transition([option['label'] for option in question['options']],
                              [option['label'] for option in current])
    for index, option in enumerate(question['options']):
        expected = deepcopy(current)
        if current[index]['label'] != option['label']:
            card = item.locator('[data-testid="picture-choice-card"]').nth(index)
            label = native._one(card.locator('span[data-testid="picture-choice-option-label-text"]'),
                                'Picture Choice update label owner changed')
            fill(label, option['label']);label.press('Tab')
            expected[index]['label'] = option['label']
            wait_until(lambda:_choices(item) == expected, 'Picture Choice update changed a sibling label or media')
        current = expected
    for index, option in enumerate(question['options']):
        if 'local_file' in option or current[index]['image_url'] != option['image_url']:
            if 'local_file' in option:_media(page, frame, item, index, option, (staged or {}).get(index))
            else:_media(page, frame, item, index, option)
            current[index]['image_url'] = option['image_url']
    expected_styles = (_write_presentation(frame, item, question['presentation'])
                       if 'presentation' in question else before['_styles'])
    after = _read_picture(frame, item)
    expected = {**before, 'options':_authored(question)['options'],
                '_option_identity':current, '_styles':expected_styles}
    if after != expected:
        raise Stop('Picture Choice update changed protected field identity, properties or sibling cards')
    return after


def _receipt_media(question,step):
    original=step['payload']['questions'][0]['options']
    hashes=[hashlib.sha256(option['image_url'].encode()).hexdigest() for option in question['options']]
    uploads=[{'index':index,'source_sha256':option['sha256'],'url':question['options'][index]['image_url']}
             for index,option in enumerate(original) if 'local_file' in option]
    return {'image_urls_sha256':hashes,**({'uploaded_media':uploads} if uploads else {})}


def _configure_update(page, frame, step, plan, before, identity, staged=None):
    owner = plan['target_page'] - 1;index = plan['update_question_index'];question = plan['questions'][0]
    identity()
    item = native._items(native._owners(frame, plan)[owner][1]).nth(index)
    desired = deepcopy(before)
    desired[owner][index] = (_update_options(page, frame, item, question, staged) if staged
                            else _update_options(page, frame, item, question))
    if _inventory(frame, plan) != desired:
        raise Stop('Picture Choice update changed another inventoried question or page')
    identity()
    save = native._one(frame.get_by_role('button', name='Save', exact=True), 'Picture Choice Save changed')
    if not save.is_enabled():raise Stop('Picture Choice updated options remain invalid')
    click(save);wait_until(lambda:save.is_enabled(), 'Picture Choice update Save did not finish')
    page.wait_for_load_state('networkidle', timeout=45000)
    native.reopen_editor(page, 'quiz', plan['expected_quiz_name'], plan['start_url'])
    frame = page.frame_locator('iframe[name="quiz-builder-app"]')
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    native._wait_editor_identity(page, title, plan);identity();_wait_baseline(frame, plan, desired)
    if _inventory(frame, plan) != desired:
        raise Stop('Picture Choice updated options did not persist or changed protected quiz inventory')
    return validate_receipt({'status':'QUIZ_PICTURE_CHOICES_SAVED_AND_REOPENED','kind':ACTION,
        'editor_url':page.url,'configuration_sha256':configuration_hash(step),'question_count':1,
        'target_page':plan['target_page'],'independent_readback':'VERIFIED','dependency_api_used':False,
        'behavior_verified':False,'submission_verified':False,
        'field_id':desired[owner][index]['_option_identity'][0]['owner'],
        'persisted_unique_key':question['expected_persisted_unique_key'],
        **_receipt_media(question,step)}, step)


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
    plan=validate(step);question=plan['questions'][0];options=question['options']
    local=[(index,option) for index,option in enumerate(options) if 'local_file' in option]
    keys={'status','kind','editor_url','configuration_sha256','question_count','target_page',
          'independent_readback','dependency_api_used','behavior_verified','submission_verified',
          'field_id','persisted_unique_key','image_urls_sha256'} | ({'uploaded_media'} if local else set())
    expected={'status':'QUIZ_PICTURE_CHOICES_SAVED_AND_REOPENED','kind':ACTION,
        'editor_url':plan['start_url'],'configuration_sha256':configuration_hash(step),
        'question_count':1,'target_page':plan['target_page'],'independent_readback':'VERIFIED',
        'dependency_api_used':False,'behavior_verified':False,'submission_verified':False,
        'persisted_unique_key':question['expected_persisted_unique_key']}
    if (not isinstance(value,dict) or set(value)!=keys
            or any(value[key]!=item or type(value[key]) is not type(item) for key,item in expected.items())
            or not isinstance(value['field_id'],str) or not re.fullmatch(r'[A-Za-z0-9]{20}',value['field_id'])
            or not isinstance(value['image_urls_sha256'],list) or len(value['image_urls_sha256'])!=len(options)):
        raise Stop('Picture Choice completion is malformed, incomplete or unbound')
    uploads=value.get('uploaded_media',[])
    if not isinstance(uploads,list) or len(uploads)!=len(local):raise Stop('Picture Choice upload receipt is incomplete')
    by_index={}
    for record,(index,asset) in zip(uploads,local):
        if (not isinstance(record,dict) or set(record)!={'index','source_sha256','url'}
                or type(record['index']) is not int or record['index']!=index or record['source_sha256']!=asset['sha256']):
            raise Stop('Picture Choice upload receipt differs from the approved local asset')
        by_index[index]=_https(record['url'])
    for index,option in enumerate(options):
        url=by_index[index] if index in by_index else option['image_url']
        if value['image_urls_sha256'][index]!=hashlib.sha256(url.encode()).hexdigest():
            raise Stop('Picture Choice receipt image URL differs from independent readback')
    return deepcopy(value)


def _configure(page, step, plan, staged):
    frame = page.frame_locator('iframe[name="quiz-builder-app"]')
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    def identity():
        if page.url != plan['start_url'] or title.count() != 1 or native.read_editor_title(title) != plan['expected_quiz_name']:
            raise Stop('Picture Choice exact quiz owner changed')
        assert_tenant(page, plan)
    title.wait_for(state='visible', timeout=45000);native._wait_editor_identity(page, title, plan);identity();_wait_baseline(frame, plan)
    before = _inventory(frame, plan)
    if choice._properties(before) != [owner['questions'] for owner in plan['pages']]:
        raise Stop('Picture Choice prior quiz/page/question inventory differs from the complete expected state')
    if 'update_question_index' in plan:
        return _configure_update(page, frame, step, plan, before, identity, staged)
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
    desired[owner].append(_write(page, frame, item, question, staged))
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
        **_receipt_media(question,step)},step)


def configure(page,step):
    plan=validate(step)
    with tempfile.TemporaryDirectory(prefix='skill6-picture-') as directory:
        staged=_stage_local_assets(plan,directory)
        return _configure(page,step,plan,staged)
