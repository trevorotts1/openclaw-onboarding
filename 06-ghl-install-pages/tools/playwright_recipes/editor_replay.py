"""Validate completed editor journals without reading a browser or replaying writes."""
from collections.abc import Mapping
import re
from urllib.parse import parse_qsl, urlsplit

if __package__:
    from .skill6_playwright import Stop
    from .evidence_lease import read_journal
    from .receipt_validation import pending_proof
else:
    from skill6_playwright import Stop
    from evidence_lease import read_journal
    from receipt_validation import pending_proof


STATUSES = {
    'html': {'RENDERED'}, 'seo': {'SEO_RENDERED'}, 'checkout': {'COMPONENT_SAVED'},
    'form': {'SAVED_AND_REOPENED'}, 'form_css': {'FORM_CSS_RENDERED'},
    'native_form_css': {'NATIVE_FORM_CSS_SAVED_AND_REOPENED'},
    'native_fields': {'FIELD_PROPERTIES_SAVED_AND_REOPENED'},
    'native_field_placement': {'BUILTIN_FIELDS_SAVED_AND_REOPENED', 'BUILTIN_FIELDS_REUSED_AND_REOPENED'},
    'native_condition': {'CONDITION_ALREADY_PRESENT', 'CONDITION_SAVED_AND_REOPENED', 'CONDITION_SAVE_SUBMITTED'},
    'quiz_configuration': {'QUIZ_CONFIGURATION_SAVED_AND_REOPENED'},
    'survey_configuration': {'SURVEY_RULE_ALREADY_PRESENT', 'SURVEY_RULE_SAVED_AND_REOPENED'},
    'assessment': {'ASSESSMENT_REUSED', 'ASSESSMENT_SAVE_SUBMITTED'},
    'form_settings': {'FORM_SETTINGS_PERSISTED'},
    'native_form_schedule': {'FORM_SCHEDULE_SAVED_AND_REOPENED'},
    'form_submission': {'FORM_SUBMISSION_SAVED_AND_REOPENED'},
    'form_notifications': {'NOTIFICATION_SETTINGS_SAVED_AND_REOPENED'},
    'options': {'RECORDED_OPTIONS_EXECUTED'},
    'community': {'GROUP_RETAINED_INACTIVE', 'GROUP_CREATED'},
    'meeting': {'ROOM_CREATED_VERIFIED', 'ROOM_REUSED_VERIFIED', 'ROOM_UPDATED_VERIFIED'},
    'native_checkout': {'NATIVE_CONFIGURATION_READBACK_VERIFIED'},
    'native_checkout_ui': {'NATIVE_CHECKOUT_UI_READBACK_VERIFIED'},
}
REQUIRED = {
    'navigate': ('area',), 'container': ('container_url', 'name'), 'page': ('editor_url',),
    'html': ('editor_url', 'html_sha256'), 'seo': ('canonical',),
    'checkout': ('mode', 'payment_verified', 'checkout_ready'), 'form': ('form_url',),
    'form_css': ('radius',), 'native_form_css': ('editor_url', 'css_sha256', 'submission_verified'),
    'native_fields': ('editor_url', 'fields', 'submission_verified'),
    'native_field_placement': ('editor_url', 'fields', 'submission_verified'),
    'native_condition': ('kind', 'effect', 'if_field', 'operator', 'target', 'independent_readback', 'submission_verified', 'behavior_verified'),
    'quiz_configuration': ('kind', 'editor_url', 'questions', 'submission_verified'),
    'survey_configuration': ('kind', 'editor_url', 'source_slide', 'target_slide', 'independent_readback', 'submission_verified', 'behavior_verified'),
    'assessment': ('kind', 'editor_url', 'independent_readback'),
    'form_settings': ('settings', 'editor_url'),
    'native_form_schedule': ('editor_url', 'enabled', 'configuration_sha256', 'independent_readback', 'behavior_verified', 'submission_verified'),
    'form_submission': ('mode', 'editor_url', 'value_sha256', 'independent_readback', 'behavior_verified', 'submission_verified'),
    'form_notifications': ('enabled', 'configuration_sha256', 'recipient_count', 'independent_readback', 'behavior_verification'),
    'options': ('count', 'capture_source'), 'community': ('name', 'slug', 'discovery', 'deleted'),
    'meeting': ('room', 'meeting_started'),
    'native_checkout': ('component_id', 'page_id', 'operations', 'payment_verified', 'checkout_ready', 'independent_readback'),
    'native_checkout_ui': ('element_id', 'editor_url', 'payment_verified', 'checkout_ready'),
}
BOOLEANS = frozenset(('behavior_verified', 'submission_verified', 'payment_verified',
    'functional_verified', 'checkout_ready', 'meeting_started', 'discovery', 'deleted',
    'products_missing', 'form_submitted', 'notifications_sent', 'legal_copy_saved', 'legal_acceptance',
    'conditional_precedence_present', 'conditional_precedence_acknowledged'))
COUNTS = frozenset(('count', 'radius', 'render_checks', 'recipient_count', 'questions', 'source_slide', 'target_slide'))
IDS = frozenset(('element_id', 'section_id', 'component_id', 'page_id', 'calendar_id', 'slug'))
HASHES = frozenset(('html_sha256', 'css_sha256', 'value_sha256', 'configuration_sha256'))
ID_PATTERN = re.compile(r'[A-Za-z0-9_-]{1,256}')


def _fail():
    raise Stop('Saved editor completion is malformed or unbound; reconciliation required')


def _url(value, job, *, public_room=False):
    if not isinstance(value, str):
        _fail()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _fail()
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or port not in (None, 443)):
        _fail()
    if public_room:
        if parsed.query or not re.fullmatch(r'/[A-Za-z0-9/_-]+', parsed.path):
            _fail()
    else:
        requested = urlsplit(job['start_url'])
        if parsed.netloc != requested.netloc:
            _fail()
        path = r'/(?:v2/)?location/' + re.escape(job['location_id']) + r'/'
        path += (r'(?:page-builder/[A-Za-z0-9_-]+|(?:form|survey|quiz)-builder-v2/[A-Za-z0-9_-]+'
                 r'|funnels-websites/(?:funnels|websites)/[A-Za-z0-9_-]+(?:/pages|/steps/[A-Za-z0-9_-]+/overview)?)/?')
        if not re.fullmatch(path, parsed.path):
            _fail()
        if parsed.query and (not '/page-builder/' in parsed.path
                or parse_qsl(parsed.query, keep_blank_values=True) not in
                ([('source', 'website')], [('source', 'funnel')])):
            _fail()
    return value


def _operation(value):
    if not isinstance(value, Mapping):
        _fail()
    # Preserve exact component identifiers and readback markers, not arbitrary
    # native adapter responses or authored/payment data nested alongside them.
    if 'op' in value:
        if (value.get('state') != 'bound-verified' or not isinstance(value.get('checkout_component_id'), str)
                or not ID_PATTERN.fullmatch(value['checkout_component_id'])):
            _fail()
        return {'checkout_component_id':value['checkout_component_id'], 'state':'bound-verified', 'op':_operation(value['op'])}
    keys = ('route', 'tab_id', 'frame_id', 'target', 'readback')
    if any(not isinstance(value.get(key), str) or not value[key] for key in keys):
        _fail()
    if value['readback'] != 'verified' or not re.fullmatch(r'[A-Za-z0-9_.-]+', value['route']):
        _fail()
    if any(not ID_PATTERN.fullmatch(value[key]) for key in ('tab_id', 'frame_id', 'target')):
        _fail()
    return {key:value[key] for key in keys}


def _result(step, value, job):
    action = step['action']
    if not isinstance(value, Mapping) or action not in REQUIRED:
        _fail()
    if any(key not in value for key in REQUIRED[action]):
        _fail()
    if action in ('navigate', 'container', 'page'):
        if value.get('status') is not None:
            _fail()
        safe = {}
    else:
        if not isinstance(value.get('status'), str) or value['status'] not in STATUSES.get(action, ()):
            _fail()
        safe = {'status':value['status']}
    if 'location_id' in value and value['location_id'] != job['location_id']:
        _fail()
    extra = {
        'html': {'element_id', 'section_id'}, 'native_form_css': {'render_checks'},
        'meeting': {'previous_room_identity'},
    }.get(action, set())
    # A familiar field on an unrelated handler is still an arbitrary extra.
    allowed = set(REQUIRED[action]) | extra | BOOLEANS | {
        'status', 'independent_readback', 'behavior_verification'}
    value = {key:item for key,item in value.items() if key in allowed}
    for key in BOOLEANS.intersection(value):
        if type(value[key]) is not bool:
            _fail()
        safe[key] = value[key]
    for key in COUNTS.intersection(value):
        if type(value[key]) is not int or value[key] < 0:
            _fail()
        safe[key] = value[key]
    for key in IDS.intersection(value):
        if value[key] is None and key in ('element_id', 'section_id'):
            continue
        if not isinstance(value[key], str) or not ID_PATTERN.fullmatch(value[key]):
            _fail()
        safe[key] = value[key]
    for key in HASHES.intersection(value):
        if not isinstance(value[key], str) or not re.fullmatch(r'[a-f0-9]{64}', value[key]):
            _fail()
        if key in step and step[key] != value[key]:
            _fail()
        safe[key] = value[key]
    for key in ('editor_url', 'container_url', 'form_url'):
        if key in value:
            safe[key] = _url(value[key], job)
            if key != 'container_url':
                family = ('page-builder' if action in ('page', 'html', 'native_checkout_ui')
                    else 'quiz-builder-v2' if action == 'quiz_configuration' or (action == 'assessment' and step.get('kind') == 'quiz')
                    else 'survey-builder-v2' if action == 'survey_configuration' or action == 'assessment'
                    else 'form-builder-v2')
                if '/' + family + '/' not in urlsplit(safe[key]).path:
                    _fail()
                requested = urlsplit(job['start_url'])
                if '/' + family + '/' in requested.path and requested.path != urlsplit(safe[key]).path:
                    _fail()
    for key in ('independent_readback', 'behavior_verification'):
        if key in value:
            allowed = ('REQUIRED', 'VERIFIED', 'COMPLETE') if key == 'independent_readback' else ('REQUIRED',)
            if value[key] not in allowed:
                _fail()
            safe[key] = value[key]
    if 'kind' in value:
        if value['kind'] not in ('quiz', 'survey', 'form_condition', 'survey_condition'):
            _fail()
        safe['kind'] = value['kind']
    if 'mode' in value and value['mode'] is not None:
        if value['mode'] not in ('Message', 'Redirect to URL', 'One-step', 'Two-step', 'Split'):
            _fail()
        safe['mode'] = value['mode']
    for key in ('area', 'name', 'slug', 'canonical', 'effect', 'if_field', 'operator', 'target', 'source_slide', 'target_slide'):
        if key in value and key in step and value[key] != step[key]:
            _fail()
    if action == 'navigate':
        safe['area'] = step['area']
    if action == 'container':
        safe['name'] = step['name']
        family = '/funnels-websites/' + ('funnels/' if step['surface'] == 'funnel' else 'websites/')
        if family not in urlsplit(safe['container_url']).path:
            _fail()
    if action in ('assessment', 'quiz_configuration') and value.get('kind') != ('quiz' if action == 'quiz_configuration' else step.get('kind')):
        _fail()
    if action in ('native_condition', 'survey_configuration') and value['kind'] != (
            'form_condition' if action == 'native_condition' else 'survey_condition'):
        _fail()
    if action == 'form_settings':
        if value['settings'] != step.get('settings') or not isinstance(value['settings'], dict) or any(type(x) is not bool for x in value['settings'].values()):
            _fail()
        safe['settings'] = dict(value['settings'])
    if action == 'native_form_schedule':
        from playwright_recipes.form_schedule import configuration_hash
        if (type(value['enabled']) is not bool
                or value['enabled'] != step['schedule']['enabled']
                or value['configuration_sha256'] != configuration_hash(step['schedule'])
                or value['independent_readback'] != 'VERIFIED'
                or value['behavior_verified'] is not False
                or value['submission_verified'] is not False):
            _fail()
        safe['enabled'] = value['enabled']
    if action == 'native_fields':
        fields = [field['field'] for field in step.get('fields', [])]
        if value['fields'] != fields:
            _fail()
        safe['fields'] = fields
    if action == 'native_field_placement':
        from playwright_recipes.field_placement import CAPTURED_FIELDS
        requested = step.get('add_fields')
        fields = value['fields']
        if not isinstance(requested, list) or not isinstance(fields, list) or len(fields) != len(requested):
            _fail()
        clean = []
        for label, field in zip(requested, fields):
            spec = CAPTURED_FIELDS.get(label)
            if (not spec or not isinstance(field, Mapping)
                    or field.get('field') != label
                    or field.get('query_keys') != list(spec['query_keys'])
                    or field.get('placement') not in ('added', 'reused')):
                _fail()
            clean.append({'field':label, 'query_keys':list(spec['query_keys']), 'placement':field['placement']})
        added = any(field['placement'] == 'added' for field in clean)
        if (not requested or value['submission_verified'] is not False
                or (value['status'] == 'BUILTIN_FIELDS_SAVED_AND_REOPENED') != added):
            _fail()
        safe['fields'] = clean
    if action == 'options':
        if value['count'] != len(step.get('steps', [])) or value['capture_source'] != step.get('capture_source'):
            _fail()
    if action == 'form_notifications':
        expected = {key:step[key]['enabled'] for key in ('email_notification', 'auto_responder') if key in step}
        if value['enabled'] != expected or any(type(x) is not bool for x in value['enabled'].values()):
            _fail()
        safe['enabled'] = expected
    if action == 'meeting':
        room = value['room']
        if not isinstance(room, Mapping) or room.get('location_id') != job['location_id'] or room.get('status') != 'PRESENT':
            _fail()
        url = _url(room.get('url'), job, public_room=True)
        room_id = room.get('room_id')
        if not isinstance(room_id, str):
            _fail()
        if room_id.startswith('https://'):
            _url(room_id, job, public_room=True)
        elif not ID_PATTERN.fullmatch(room_id):
            _fail()
        if (room.get('identity_source') == 'canonical_room_link' and room_id != url
                or room.get('slug') != urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1]):
            _fail()
        safe_room = {'room_id':room_id, 'url':url, 'location_id':job['location_id'], 'slug':room['slug'], 'status':'PRESENT'}
        for key in ('name', 'slug', 'waiting_room', 'guest_users', 'open_room'):
            if key not in room or (key in step and room[key] != step[key]):
                _fail()
            if key in ('waiting_room', 'guest_users', 'open_room'):
                if type(room[key]) is not bool:
                    _fail()
                safe_room[key] = room[key]
        safe['room'] = safe_room
        if 'previous_room_identity' in value:
            if value['previous_room_identity'] != step.get('expected_room_id'):
                _fail()
            previous = value['previous_room_identity']
            if not isinstance(previous, str):
                _fail()
            if previous.startswith('https://'):
                _url(previous, job, public_room=True)
            elif not ID_PATTERN.fullmatch(previous):
                _fail()
            safe['previous_room_identity'] = previous
    if action == 'native_checkout_ui' and value['element_id'] != step.get('payload', {}).get('element_id'):
        _fail()
    if action == 'native_checkout':
        payload = step.get('payload', {})
        if value['page_id'] != payload.get('page_id') or not isinstance(value['operations'], list):
            _fail()
        safe['operations'] = [_operation(record) for record in value['operations']]
    return safe


def completed_editor_replay(path, job, fingerprint):
    """Read and bind saved completion before the caller consults a browser."""
    old = read_journal(path)
    steps = job.get('steps')
    if (not isinstance(old, Mapping) or old.get('fingerprint') != fingerprint
            or old.get('location_id') != job.get('location_id')
            or not isinstance(steps, list) or not steps):
        _fail()
    if old.get('status') not in ('EDITOR_STEPS_COMPLETE', 'NEEDS_VERIFICATION'):
        raise Stop('An interrupted job exists: reconcile recorded objects before any replay')
    if (any(not isinstance(step, Mapping) or not isinstance(step.get('id'), str)
            or not re.fullmatch(r'[a-z0-9_-]+', step['id'])
            or not isinstance(step.get('action'), str) or step['action'] not in REQUIRED for step in steps)
            or len({step['id'] for step in steps}) != len(steps)):
        _fail()
    if (old.get('current_step_status') != 'FINISHED' or old.get('current_step') != steps[-1].get('id')
            or not isinstance(old.get('results'), list) or len(old['results']) != len(steps)):
        _fail()
    results, pending = [], []
    for step, row in zip(steps, old['results']):
        if not isinstance(row, Mapping) or row.get('id') != step.get('id') or row.get('action') != step.get('action'):
            _fail()
        value = row.get('result')
        safe = _result(step, value, job)
        if pending_proof(value) or value.get('kind') == 'quiz':
            pending.append(step['id'])
        results.append({'id':step['id'], 'action':step['action'], 'result':safe})
    if (old.get('verification_required') != pending
            or (old['status'] == 'NEEDS_VERIFICATION') != bool(pending)):
        _fail()
    return {'status':'NEEDS_VERIFICATION' if pending else 'ALREADY_EXECUTED',
            'fingerprint':fingerprint, 'location_id':job['location_id'],
            'current_step':steps[-1]['id'], 'current_step_status':'FINISHED',
            'results':results, 'verification_required':pending, 'replayed':True,
            'meaning':'No writes repeated. Reconcile saved outputs before a new build.'}
