"""Typed named-recipe boundary for Contact dependencies and native placement.

Authored inputs and API capability evidence stay separate. The maintained
chain owns the API/native journals; the runner owns the enclosing write intent.
"""
from copy import deepcopy
import hashlib
import json

if __package__:
    from . import contact_field_dependencies as dependencies, form_contact_field_chain as chain
    from .skill6_playwright import Stop
else:
    import contact_field_dependencies as dependencies
    import form_contact_field_chain as chain
    from skill6_playwright import Stop


ACTION = 'native_contact_field_chain'
COMMON = ('location_id', 'location_name', 'start_url')


def payload_from_inputs(data):
    value = data.get('contact_field_plan')
    if not isinstance(value, dict) or set(value) != {'expected_form_name', 'fields', 'native_bindings'}:
        raise Stop('Contact field plan requires exact form name, fields and native bindings; owner identity comes from parent inputs')
    return chain.validate_inputs({**{key:data[key] for key in COMMON}, **value})


def validate(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'payload'}
            or step.get('action', ACTION) != ACTION):
        raise Stop('Contact field chain accepts only its exact typed payload')
    return chain.validate_inputs(step.get('payload'))


def validate_capability(step, capability):
    plan = validate(step)
    dependencies.validate_capability(capability, plan['location_id'],
        creation=any(field['allow_creation'] for field in plan['fields']))


def validate_runtime(job, capability):
    steps = job.get('steps')
    if not isinstance(steps, list) or len(steps) != 1:
        raise Stop('Contact dependency chain cannot share an execution with another editor action')
    plan = validate(steps[0])
    if any(plan[key] != job.get(key) for key in COMMON):
        raise Stop('Contact dependency chain belongs to another parent editor')
    validate_capability(steps[0], capability)


def _native_step(plan, api_fields):
    """Rebuild the precise captured placement contract, without refreshing it."""
    from playwright_recipes.recipe_cli import compile_recipe
    bindings = {row['field_key']:row for row in plan['native_bindings']}
    large = plan['fields'][0]['data_type'] == 'LARGE_TEXT'
    family = 'large_text_fields' if large else 'dropdown_fields'
    fields = [{**field, **{key:value for key,value in bindings[field['field_key']].items()
        if key != 'field_key'}} for field in api_fields]
    dependency = {'status':'VERIFIED', 'provider':'public_api', 'location_id':plan['location_id'],
        'observed_at':0, 'operation':'custom_fields.get', 'http_status':200,
        'fields':deepcopy(api_fields)}
    return compile_recipe('forms.configure', {**{key:plan[key] for key in COMMON},
        family:fields, 'field_dependencies':dependency})['steps'][0]


def validate_receipt(value, step):
    plan = validate(step)
    keys = {'status','location_id','editor_url','configuration_sha256','api_fields',
        'native_receipt','field_count','independent_readback','dependency_api_used',
        'native_placement_required','behavior_verified','submission_verified'}
    if (not isinstance(value, dict) or set(value) != keys
            or value['status'] != 'CONTACT_FIELDS_SAVED_AND_REOPENED'
            or value['location_id'] != plan['location_id'] or value['editor_url'] != plan['start_url']
            or value['configuration_sha256'] != chain.configuration_hash(plan)
            or type(value['field_count']) is not int or value['field_count'] != len(plan['fields'])
            or value['independent_readback'] != 'VERIFIED' or value['dependency_api_used'] is not True
            or any(value[key] is not False for key in ('native_placement_required','behavior_verified','submission_verified'))
            or not isinstance(value['api_fields'], list) or len(value['api_fields']) != len(plan['fields'])):
        raise Stop('Contact chain completion lacks exact API/native identity and pending proof')
    ids = set()
    for requested, actual in zip(plan['fields'], value['api_fields']):
        fields = {'id','name','field_key','data_type'} | ({'options'} if requested['data_type'] == 'SINGLE_OPTIONS' else set())
        if (not isinstance(actual, dict) or set(actual) != fields
                or any(actual[key] != requested[key] for key in ('name','field_key','data_type'))
                or requested['expected_id'] is not None and actual['id'] != requested['expected_id']
                or requested['data_type'] == 'SINGLE_OPTIONS' and actual['options'] != requested['options']):
            raise Stop('Contact chain API receipt differs from its authored field definition')
        identity = dependencies.delivery._id(actual['id'], 'completed Contact field id')
        if identity in ids:
            raise Stop('Contact chain receipt repeats a field identity')
        ids.add(identity)
    native = _native_step(plan, value['api_fields'])
    from playwright_recipes.editor_replay import _result
    result = deepcopy(value)
    result['native_receipt'] = _result(native, value['native_receipt'],
        {key:plan[key] for key in COMMON})
    return result


def configure(page, step, root, *, capability):
    plan = validate(step)
    validate_capability(step, capability)
    raw = chain.build_form_fields(plan, root, page=page, capability=capability)
    if (not isinstance(raw, dict) or raw.get('status') != 'NEEDS_VERIFICATION'
            or raw.get('location_id') != plan['location_id']
            or raw.get('configuration_sha256') != chain.configuration_hash(plan)
            or raw.get('native_placement_required') is not False
            or raw.get('behavior_verified') is not False or raw.get('submission_verified') is not False):
        raise Stop('Contact chain did not return its original bound completion')
    from playwright_recipes.evidence_lease import read_journal
    from playwright_recipes.editor_replay import completed_editor_replay
    from pathlib import Path
    api = read_journal(Path(root) / 'delivery-state.json')
    if (not isinstance(api, dict) or api.get('schema') != dependencies.SCHEMA
            or api.get('location_id') != plan['location_id']
            or api.get('fingerprint') != dependencies.configuration_hash(
                {key:plan[key] for key in ('location_id','fields')})
            or api.get('status') != 'API_STEPS_COMPLETE'
            or api.get('current_step_status') != 'VERIFIED' or api.get('fields') != raw['fields']):
        raise Stop('Contact chain completion differs from its original verified API journal')
    native_job = read_journal(Path(root) / 'native-field-job.json')
    # Independently validate the actual saved native journal, rather than a
    # callback status or a replacement copy embedded in the outer outcome.
    native = completed_editor_replay(Path(root) / 'native' / 'state.json', native_job,
        hashlib.sha256(json.dumps(native_job, sort_keys=True).encode()).hexdigest())
    if len(native['results']) != 1:
        raise Stop('Contact chain native completion has an unexpected step inventory')
    value = {'status':'CONTACT_FIELDS_SAVED_AND_REOPENED', 'location_id':plan['location_id'],
        'editor_url':plan['start_url'], 'configuration_sha256':chain.configuration_hash(plan),
        'api_fields':raw['fields'], 'native_receipt':native['results'][0]['result'],
        'field_count':len(plan['fields']), 'independent_readback':'VERIFIED',
        'dependency_api_used':True, 'native_placement_required':False,
        'behavior_verified':False, 'submission_verified':False}
    return validate_receipt(value, step)
