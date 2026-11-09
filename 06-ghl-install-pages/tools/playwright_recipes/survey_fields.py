"""Place API-inventoried object questions on an exact existing survey slide.

Shares the captured Add Object Fields rail with forms_advanced. Survey ownership
uses the native .survey-form-container/.builder-form-name inventory already used
by survey_ui, plus the slide-selection flow in ghl_survey_builder.py. This never
creates a contact-field schema, adds a slide or submits a respondent answer.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click
    from .assessments import reopen_editor
else:
    from skill6_playwright import Stop, assert_tenant, click
    from assessments import reopen_editor


OWNER = {'expected_slide_count', 'slide_labels', 'target_slide'}
COMMON = {'location_id', 'location_name', 'start_url'}
FIELDS = {'object_fields', 'field_dependencies'}


def _object_step(payload):
    return {'action':'native_object_fields',
            'payload':{key:deepcopy(payload[key]) for key in COMMON | FIELDS}}


def _validate_shape(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'payload'}
            or step.get('action', 'native_survey_object_fields') != 'native_survey_object_fields'):
        raise Stop('Unsupported native survey question placement metadata')
    payload = step.get('payload')
    if (not isinstance(payload, dict) or set(payload) != COMMON | OWNER | FIELDS):
        raise Stop('Survey object questions require exact editor, dependency and owner-slide inputs')
    count, target = payload['expected_slide_count'], payload['target_slide']
    if (type(count) is not int or count < 1 or type(target) is not int
            or not 1 <= target <= count):
        raise Stop('Survey question owner must be an existing inventoried slide')
    labels = payload['slide_labels']
    if (not isinstance(labels, list) or len(labels) != count
            or any(not isinstance(label, str) or not re.fullmatch('P' + str(index) + r' - .+', label)
                   for index, label in enumerate(labels, 1))
            or len(set(labels)) != len(labels)):
        raise Stop('Supply the complete exact numbered survey slide inventory')
    for key in COMMON:
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise Stop('Survey question placement requires ' + key)
    parsed = urlsplit(payload['start_url'])
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.port not in (None, 443)
            or not re.fullmatch(r'/v2/location/' + re.escape(payload['location_id'])
                                + r'/survey-builder-v2/[A-Za-z0-9_-]+', parsed.path)):
        raise Stop('Survey questions must bind the exact existing survey editor URL')
    return deepcopy(step)


def validate(step, *, require_fresh=False):
    value = _validate_shape(step)
    payload = value['payload']
    if __package__:
        from .forms_advanced import validate_object_fields
    else:
        from forms_advanced import validate_object_fields
    # Structural validation also remains usable on completed replay. Execution
    # separately requires a fresh GET before touching the native owner controls.
    validate_object_fields(_object_step(payload), kind='survey', require_fresh=require_fresh)
    return value


def configuration_hash(step):
    value = _validate_shape(step)
    payload = value['payload']
    if __package__:
        from .forms_advanced import object_fields_configuration_hash
    else:
        from forms_advanced import object_fields_configuration_hash
    # API freshness gates a new mutation. It must not invalidate an already
    # completed, target-bound replay as its original GET observation ages.
    binding = {key:payload[key] for key in COMMON | OWNER}
    binding['object_fields_sha256'] = object_fields_configuration_hash(_object_step(payload), kind='survey')
    return hashlib.sha256(json.dumps(binding, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _close_initial(frame):
    dialogs = frame.get_by_role('dialog')
    if not dialogs.count():
        return
    if (dialogs.count() != 1
            or dialogs.get_by_text('Survey Element', exact=True).count() != 1):
        raise Stop('Unexpected survey drawer requires reconciliation before question placement')
    close = dialogs.get_by_role('button', name='Close', exact=True)
    if close.count() != 1 or not close.is_visible():
        raise Stop('Captured Survey Element close control changed')
    click(close)


def _owner(frame, payload):
    slides = frame.locator('.survey-form-container')
    if (slides.count() != payload['expected_slide_count']
            or frame.get_by_role('button', name='Add Slide', exact=True).count()
            != payload['expected_slide_count']):
        raise Stop('Survey slide inventory changed before object-question placement')
    counts = []
    for index, label in enumerate(payload['slide_labels']):
        slide = slides.nth(index)
        name = slide.locator('.builder-form-name')
        if name.count() != 1 or name.inner_text().strip() != label.split(' - ', 1)[1]:
            raise Stop('Survey slide order/name differs from the intended object-question owner')
        counts.append(slide.locator('.form-field-wrapper').count())
    target = slides.nth(payload['target_slide'] - 1)
    # The canonical survey rail selects the owner before Add Object Fields.
    # The shared helper additionally verifies new field IDs inside this scope.
    click(target.locator('.builder-form-name'))
    return target, counts


def configure(page, step):
    value = validate(step, require_fresh=True)
    payload = value['payload']
    if page.url != payload['start_url']:
        raise Stop('Current survey editor is not the requested question target')
    assert_tenant(page, payload)
    frame = page.frame_locator('iframe[name="survey-builder-app"]')
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    name, original_url = title.input_value(), page.url
    if not isinstance(name, str) or not name.strip():
        raise Stop('Survey identity is unavailable before object-question placement')
    _close_initial(frame)
    click(frame.get_by_role('tab', name='Edit', exact=True))
    owner, before_counts = _owner(frame, payload)

    def reopen():
        reopen_editor(page, 'survey', name, original_url)
        if page.url != original_url:
            raise Stop('Survey identity changed while independently reopening questions')
        assert_tenant(page, payload)
        fresh = page.frame_locator('iframe[name="survey-builder-app"]')
        title = fresh.get_by_role('textbox', name='Form Name', exact=True)
        title.wait_for(state='visible', timeout=45000)
        if title.input_value() != name:
            raise Stop('Survey name changed while reopening object questions')
        _close_initial(fresh)
        click(fresh.get_by_role('tab', name='Edit', exact=True))
        scope, after_counts = _owner(fresh, payload)
        if any(after != before for index, (before, after) in enumerate(zip(before_counts, after_counts), 1)
               if index != payload['target_slide']):
            raise Stop('Object-question placement changed an unrequested survey slide')
        return fresh, scope

    if __package__:
        from .forms_advanced import configure_object_fields
    else:
        from forms_advanced import configure_object_fields
    result = configure_object_fields(page, _object_step(payload), kind='survey',
                                     frame=frame, canvas_scope=owner, reopen=reopen)
    if (not isinstance(result, dict) or result.get('independent_readback') != 'VERIFIED'
            or result.get('submission_verified') is not False):
        raise Stop('Shared object-question handler did not return its required independent read-back')
    return {'status':'SURVEY_OBJECT_FIELDS_SAVED_AND_REOPENED',
            'kind':'survey_object_fields', 'editor_url':page.url,
            'target_slide':payload['target_slide'],
            'field_count':len(payload['object_fields']),
            'configuration_sha256':configuration_hash(value),
            'independent_readback':'VERIFIED', 'behavior_verified':False,
            'submission_verified':False}
