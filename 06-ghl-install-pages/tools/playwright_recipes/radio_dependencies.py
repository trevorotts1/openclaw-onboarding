"""Provision authored Radio dependencies through the existing Skill44 fallback.

Public v3 choice-schema creation remains B-OPTIONS-FIELD. This explicit legacy
fallback reuses caf's /custom-fields/ body only with fresh measured same-location
POST/readback evidence. It never probes a write to learn a schema. An uncertain
POST is never repeated. Native placement remains a separately journaled step.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

if __package__:
    from . import delivery
    from .evidence_lease import guard_delivery, journal_present, read_journal
    from .skill6_playwright import Stop, secure_json
else:
    import delivery
    from evidence_lease import guard_delivery, journal_present, read_journal
    from skill6_playwright import Stop, secure_json


SCHEMA = 'skill6-radio-dependencies/1'
CREATE_PATH = '/custom-fields/'
GET_PATH = '/custom-fields/{id}'
LIST_PATH = '/locations/{locationId}/customFields'
HEX = re.compile(r'[a-f0-9]{64}')


def _text(value):
    return (isinstance(value, str) and bool(value) and value == value.strip()
            and len(value) <= 500 and not any(ord(c) < 32 for c in value))


def validate_inputs(inputs):
    if not isinstance(inputs, dict) or set(inputs) != {'location_id', 'questions'}:
        raise Stop('Radio provisioning requires only its exact location and authored questions')
    delivery._id(inputs['location_id'], 'location_id')
    questions = inputs['questions']
    if not isinstance(questions, list) or not questions:
        raise Stop('Authored Radio questions must be a nonempty list')
    keys, names, identities = set(), set(), set()
    for q in questions:
        if (not isinstance(q, dict) or set(q) != {'name', 'field_key', 'data_type', 'options', 'expected_id', 'allow_creation'}
                or not _text(q['name']) or q['data_type'] != 'RADIO'
                or not isinstance(q['field_key'], str)
                or not re.fullmatch(r'contact\.[A-Za-z0-9_.-]{1,240}', q['field_key'])
                or type(q['allow_creation']) is not bool):
            raise Stop('Radio questions require exact authored name/key/type/options and creation intent')
        if q['expected_id'] is not None:
            delivery._id(q['expected_id'], 'expected_id')
            if q['expected_id'] in identities:
                raise Stop('Duplicate expected Radio field identity')
            identities.add(q['expected_id'])
        elif q['allow_creation'] is not True:
            raise Stop('Reuse requires an exact existing field ID; absence is not permission to create')
        if (q['field_key'].casefold() in keys or q['name'].casefold() in names
                or not isinstance(q['options'], list) or len(q['options']) < 2
                or any(not _text(option) for option in q['options'])
                or len(q['options']) != len(set(q['options']))):
            raise Stop('Radio question names/keys/options must be explicit and unique')
        keys.add(q['field_key'].casefold()); names.add(q['name'].casefold())
    return deepcopy(inputs)


def configuration_hash(inputs):
    return hashlib.sha256(json.dumps(validate_inputs(inputs), sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def validate_capability(receipt, location_id, *, creation=False, version_resolver=None):
    """Accept measured route evidence, never a caller's supported=true flag."""
    if (not isinstance(receipt, dict) or set(receipt) != {'schema', 'location_id', 'provider', 'auth_kind', 'scopes', 'observed_at', 'source', 'operations'}
            or receipt['schema'] != 'skill44-radio-fallback-capability/1'
            or receipt['location_id'] != location_id or receipt['provider'] != 'skill44_legacy'
            or receipt['auth_kind'] != 'location_pit'
            or not isinstance(receipt['scopes'],list) or any(not isinstance(scope,str) for scope in receipt['scopes'])
            or 'locations/customFields.readonly' not in receipt['scopes']
            or creation and 'locations/customFields.write' not in receipt['scopes']
            or not _text(receipt['source']) or type(receipt['observed_at']) not in (int, float)
            or not math.isfinite(receipt['observed_at']) or not 0 <= time.time()-receipt['observed_at'] <= 3600
            or not isinstance(receipt['operations'], dict)):
        raise Stop('Radio fallback requires fresh measured same-location Skill44 capability evidence')
    if version_resolver is None:
        version_resolver = delivery.Skill44Transport().client._resolve_version
    if not callable(version_resolver):
        raise Stop('Legacy transport must expose its canonical per-operation version resolver')
    routes = {'list':('GET', LIST_PATH, 200), 'get':('GET', GET_PATH, 200)}
    if creation:
        routes['create'] = ('POST', CREATE_PATH, 201)
    for key, (method, path, status) in routes.items():
        row = receipt['operations'].get(key)
        if (not isinstance(row, dict) or set(row) != {'method', 'path', 'version', 'http_status', 'response_sha256', 'sample'}
                or (row['method'], row['path'], row['http_status']) != (method, path, status)
                or type(row['http_status']) is not int
                or row['version'] != version_resolver(method, path.replace('{locationId}',location_id).replace('{id}','MEASURED_ID'))
                or not isinstance(row['response_sha256'], str) or not HEX.fullmatch(row['response_sha256'])):
            raise Stop('Radio fallback route/method/version lacks successful measured evidence')
        if key in ('create', 'get'):
            sample = row['sample']
            if (not isinstance(sample, dict) or set(sample) != {'id','locationId','dataType','picklistOptions'}
                    or sample['locationId'] != location_id or sample['dataType'] != 'RADIO'
                    or not isinstance(sample['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', sample['id'])
                    or not isinstance(sample['picklistOptions'], list) or len(sample['picklistOptions']) < 2
                    or any(not _text(option) for option in sample['picklistOptions'])
                    or len(set(sample['picklistOptions'])) != len(sample['picklistOptions'])):
                raise Stop('Measured Radio route must include exact same-location choice readback evidence')
    if creation:
        post, get = (receipt['operations'][key]['sample'] for key in ('create', 'get'))
        if post != get:
            raise Stop('Radio creation capability must prove exact POST identity/options through independent GET')
    return deepcopy(receipt)


class Skill44RadioTransport:
    """Existing caf client resolver, per-operation headers and write safety gate."""
    def __init__(self):
        self.client = delivery.Skill44Transport().client

    def version_for(self, method, path):
        return self.client._resolve_version(method,path)

    def request(self, method, path, *, location_id, version, body=None):
        if method == 'POST':
            self.client.check_write(method, self.client.BASE_URL + path, body, location_id=location_id)
        response = self.client.requests.request(method, self.client.BASE_URL + path,
            headers=self.client._headers(version, path, method), json=body, timeout=30)
        response.raise_for_status()
        return {'http_status':response.status_code, 'body':response.json()}


def _request(api, receipt, key, location_id, *, identity=None, body=None):
    row = receipt['operations'][key]
    path = row['path'].replace('{locationId}', location_id)
    if identity is not None:
        path = path.replace('{id}', delivery._id(identity, 'field id'))
    result = api.request(row['method'], path, location_id=location_id, version=row['version'], body=body)
    if (not isinstance(result, dict) or set(result) != {'http_status','body'}
            or type(result['http_status']) is not int or result['http_status'] != row['http_status']
            or not isinstance(result['body'], dict)):
        raise Stop('Radio fallback did not return its exact measured successful response shape')
    return result['body']


def _record(value, location_id, expected=None):
    if (not isinstance(value, dict) or value.get('locationId') != location_id
            or value.get('model', value.get('objectKey')) != 'contact'
            or not _text(value.get('name')) or value.get('dataType') != 'RADIO'
            or value.get('optionDisplayType','TEXT_ONLY') != 'TEXT_ONLY'
            or not isinstance(value.get('fieldKey'), str)
            or not re.fullmatch(r'contact\.[A-Za-z0-9_.-]{1,240}', value['fieldKey'])):
        raise Stop('Radio API readback is not an exact same-location contact definition')
    identity = delivery._id(value.get('id'), 'field id')
    options = value.get('picklistOptions')
    if (not isinstance(options, list) or len(options) < 2
            or any(not _text(option) for option in options) or len(set(options)) != len(options)):
        raise Stop('Radio API readback lacks the complete ordered choice list')
    result = {'id':identity,'name':value['name'],'field_key':value['fieldKey'],
              'data_type':'RADIO','options':deepcopy(options)}
    if expected is not None and (any(result[key] != expected[key] for key in ('name','field_key','data_type','options'))
            or expected['expected_id'] is not None and identity != expected['expected_id']):
        raise Stop('Radio API definition differs from the exact authored ID/name/key/options')
    return result


def _get(api, receipt, plan, question, identity):
    value = _request(api,receipt,'get',plan['location_id'],identity=identity)
    if set(value) != {'customField'}:
        raise Stop('Radio GET wrapper is unrecognized')
    result = _record(value['customField'],plan['location_id'],question)
    if result['id'] != identity:
        raise Stop('Radio GET returned another field identity')
    return result


def _result(plan, fields):
    return {'status':'FIELD_DEPENDENCIES_VERIFIED', 'location_id':plan['location_id'],
        'configuration_sha256':configuration_hash(plan), 'object_fields':deepcopy(fields),
        'field_dependencies':{'status':'VERIFIED','provider':'skill44',
            'location_id':plan['location_id'],'observed_at':time.time(),
            'operation':'custom_fields.get','http_status':200,'fields':deepcopy(fields)},
        'native_placement_required':True, 'submission_verified':False}


@guard_delivery('course')
def provision_radio(inputs, evidence_root, *, capability, transport=None):
    """Use the existing API-delivery lease/journal family; no course API is called."""
    return _provision(inputs, evidence_root, capability=capability, transport=transport)


def _provision(inputs, evidence_root, *, capability, transport=None):
    plan = validate_inputs(inputs)
    api = transport or Skill44RadioTransport()
    receipt = validate_capability(capability, plan['location_id'], version_resolver=api.version_for)
    if os.environ.get('CAF_DRY_RUN','').lower() in ('1','true','yes','on'):
        raise Stop('Radio provisioning is not a dry-run operation; validate_inputs is read-only')
    root = Path(evidence_root).resolve(); journal = root/'delivery-state.json'
    fingerprint = configuration_hash(plan)
    if journal_present(journal):
        state = read_journal(journal)
        if (not isinstance(state, dict) or state.get('schema') != SCHEMA
                or state.get('location_id') != plan['location_id'] or state.get('fingerprint') != fingerprint
                or state.get('status') != 'API_STEPS_COMPLETE' or state.get('current_step_status') != 'VERIFIED'
                or not isinstance(state.get('fields'), list) or len(state['fields']) != len(plan['questions'])):
            raise Stop('Radio dependency intent is uncertain or unbound; reconcile without another POST')
        fields=[]
        for question, field in zip(plan['questions'],state['fields']):
            if not isinstance(field,dict) or set(field) != {'id','name','field_key','data_type','options'}:
                raise Stop('Saved Radio dependency identity is malformed')
            seen = _get(api,receipt,plan,question,field['id'])
            if seen != field:
                raise Stop('Saved Radio dependency changed; reconcile before native placement')
            fields.append(seen)
        return _result(plan,fields)
    listed = _request(api,receipt,'list',plan['location_id'])
    if set(listed) != {'customFields'} or not isinstance(listed['customFields'],list):
        raise Stop('Custom-field list is not an authoritative complete field inventory')
    seen_ids=set(); all_fields=listed['customFields']
    for field in all_fields:
        if (not isinstance(field,dict) or field.get('locationId') != plan['location_id']
                or not isinstance(field.get('fieldKey'),str) or not _text(field.get('name'))):
            raise Stop('Custom-field inventory has missing/foreign identity evidence')
        identity=delivery._id(field.get('id'),'inventory field id')
        if identity in seen_ids: raise Stop('Custom-field list contains duplicate identities')
        seen_ids.add(identity)
    fields=[None]*len(plan['questions']); pending=[]
    for index,question in enumerate(plan['questions']):
        matches=[field for field in all_fields if field['fieldKey'].casefold()==question['field_key'].casefold()
                 or field['name'].casefold()==question['name'].casefold()
                 or field['id']==question['expected_id']]
        if question['expected_id'] is None:
            if matches: raise Stop('Expected-absent Radio identity/name/key already exists; inventory its exact ID before reuse')
            pending.append((index,question))
        else:
            if len(matches)!=1 or matches[0]['id']!=question['expected_id']:
                raise Stop('Exact requested Radio reuse identity is absent or conflicted; never create as fallback')
            fields[index]=_get(api,receipt,plan,question,question['expected_id'])
    if pending: receipt=validate_capability(capability,plan['location_id'],creation=True,version_resolver=api.version_for)
    state={'schema':SCHEMA,'location_id':plan['location_id'],'fingerprint':fingerprint,
        'status':'RUNNING','current_step_status':'PREFLIGHT_COMPLETE','fields':fields}
    secure_json(journal,state)
    try:
        for index,question in pending:
            validate_capability(capability,plan['location_id'],creation=True,version_resolver=api.version_for)
            # Refresh the same complete inventory just before a global schema
            # write; a concurrent matching key/name is a stop, never adoption.
            latest=_request(api,receipt,'list',plan['location_id'])
            if set(latest)!={'customFields'} or not isinstance(latest['customFields'],list):
                raise Stop('Custom-field inventory changed shape immediately before schema creation')
            latest_ids=set()
            for field in latest['customFields']:
                if (not isinstance(field,dict) or field.get('locationId')!=plan['location_id']
                        or not _text(field.get('name')) or not isinstance(field.get('fieldKey'),str)):
                    raise Stop('Custom-field prewrite inventory lacks exact tenant/key/name identity')
                identity=delivery._id(field.get('id'),'prewrite field id')
                if identity in latest_ids:raise Stop('Custom-field prewrite inventory has duplicate IDs')
                latest_ids.add(identity)
                if (field['name'].casefold()==question['name'].casefold()
                        or field['fieldKey'].casefold()==question['field_key'].casefold()):
                    raise Stop('Radio name/key appeared after preflight; do not create or silently reuse')
            # The legacy caf body is reused exactly. fieldKey is generated by
            # the provider, and must match the separately authored expected key.
            body={'locationId':plan['location_id'],'name':question['name'],
                  'dataType':'RADIO','objectKey':'contact','options':question['options']}
            state.update(current_step_status='INTENT_RECORDED',current_question=index)
            secure_json(journal,state)
            created=_request(api,receipt,'create',plan['location_id'],body=body)
            if set(created)!={'customField'} or not isinstance(created['customField'],dict):
                raise Stop('Radio POST response lacks the created exact native field identity')
            identity=delivery._id(created['customField'].get('id'),'created field id')
            if identity in seen_ids: raise Stop('Radio POST returned an already inventoried field identity')
            state['created_id']=identity;secure_json(journal,state)
            fields[index]=_get(api,receipt,plan,question,identity)
            seen_ids.add(identity);state['fields']=fields;state['current_step_status']='VERIFIED'
            secure_json(journal,state)
        # Re-read every earlier target after the last schema creation.
        for question,field in zip(plan['questions'],fields):
            if _get(api,receipt,plan,question,field['id']) != field:
                raise Stop('Earlier Radio definition changed during dependency creation')
        state.update(status='API_STEPS_COMPLETE',current_step_status='VERIFIED')
        secure_json(journal,state)
        return _result(plan,fields)
    except Exception as error:
        state.update(status='NEEDS_RECONCILIATION',error_type=type(error).__name__)
        secure_json(journal,state)
        raise


def _survey_plan(inputs):
    if (not isinstance(inputs,dict) or set(inputs) != {'location_id','location_name','start_url',
            'expected_slide_count','slide_labels','target_slide','questions'}):
        raise Stop('Radio survey chain requires exact existing editor, slide inventory and authored questions')
    plan=validate_inputs({key:inputs[key] for key in ('location_id','questions')})
    if __package__:
        from .survey_fields import _validate_shape
    else:
        from survey_fields import _validate_shape
    _validate_shape({'payload':{**{key:inputs[key] for key in (
        'location_id','location_name','start_url','expected_slide_count','slide_labels','target_slide')},
        'object_fields':[],'field_dependencies':{}}})
    return plan


@guard_delivery('course')
def build_survey_questions(inputs, evidence_root, *, page, capability, transport=None):
    """Provision Radio definitions, then invoke the existing native slide writer.

    The outer API-delivery lease protects the chain. Native mutation uses its
    own child-root editor journal; completed native replay reuses its frozen
    dependency receipt so a refreshed GET timestamp never repeats a placement.
    Existing uncertain API or editor journals still stop, never auto-retry.
    """
    plan=_survey_plan(inputs)
    root=Path(evidence_root).resolve();native=root/'native'
    native_job_path=root/'native-question-job.json'
    if native.is_symlink():
        raise Stop('Native question evidence directory is a symlink; reconcile before any schema creation')
    if __package__:
        from . import survey_fields
        from .recipe_cli import compile_recipe
        from .skill6_playwright import assert_tenant, run_on_page, validate_job
    else:
        import survey_fields
        from recipe_cli import compile_recipe
        from skill6_playwright import assert_tenant, run_on_page, validate_job
    api=transport or Skill44RadioTransport()
    validate_capability(capability,plan['location_id'],version_resolver=api.version_for)
    if page.url != inputs['start_url']:
        raise Stop('Survey Radio chain must start on its exact existing editor')
    assert_tenant(page,inputs)
    # Confirm the actual complete owner-slide inventory before creating any
    # shared contact-field definition, even though selection is read-only.
    frame=page.frame_locator('iframe[name="survey-builder-app"]')
    from playwright_recipes.assessments import read_editor_title
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or not read_editor_title(title).strip():
        raise Stop('Survey Radio chain cannot prove its native survey identity')
    survey_fields._close_initial(frame)
    survey_fields._owner(frame,inputs)
    if journal_present(native/'state.json') and not journal_present(root/'delivery-state.json'):
        raise Stop('Native question intent exists without its API dependencies; reconcile before schema creation')
    prepared=_provision(plan,root,capability=capability,transport=api)
    data={key:inputs[key] for key in ('location_id','location_name','start_url')}
    data['configuration']={**{key:inputs[key] for key in ('expected_slide_count','slide_labels','target_slide')},
        'object_fields':prepared['object_fields'],'field_dependencies':prepared['field_dependencies']}
    job=compile_recipe('surveys.configure',data)
    if journal_present(native_job_path):
        saved=read_journal(native_job_path)
        def stable(value):
            result=deepcopy(value)
            for step in result.get('steps',[]):
                step.get('payload',{}).get('field_dependencies',{}).pop('observed_at',None)
            return result
        if not isinstance(saved,dict) or stable(saved)!=stable(job):
            raise Stop('Saved native Radio job belongs to another editor/slide/definition')
        if journal_present(native/'state.json'):
            job=saved
    job=validate_job(job,root)
    secure_json(native_job_path,job)
    native_result=run_on_page(page,job,native)
    return {'status':'NEEDS_VERIFICATION','location_id':plan['location_id'],
        'object_fields':prepared['object_fields'],'field_dependencies':prepared['field_dependencies'],
        'native_result':native_result,'native_placement_required':False,
        'submission_verified':False,'behavior_verified':False}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Prepare exact authored Radio dependencies using a measured Skill44 fallback')
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--capability',type=Path,required=True)
    parser.add_argument('--evidence-root',type=Path,required=True)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args(argv)
    try:
        inputs=json.loads(args.inputs.read_text())
        measured=json.loads(args.capability.read_text())
        plan=validate_inputs(inputs)
        validate_capability(measured,plan['location_id'],creation=any(q['expected_id'] is None for q in plan['questions']))
        if args.check:
            result={'status':'VALIDATED_ONLY','location_id':plan['location_id'],
                    'configuration_sha256':configuration_hash(plan),'network_used':False}
        else:
            result=provision_radio(plan,args.evidence_root,capability=measured)
        print(json.dumps(result,indent=2));return 0
    except Exception as error:
        print(json.dumps({'status':'STOP_REQUIRES_RECONCILIATION','error_type':type(error).__name__}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
