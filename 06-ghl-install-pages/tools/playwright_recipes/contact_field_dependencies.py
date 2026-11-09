"""Documented Contact v3 LARGE_TEXT creation and exact Dropdown/textarea reuse.

The Contact create schema has no option-array request property. SINGLE_OPTIONS
creation therefore refuses before transport use; Custom Fields V2's options
schema is for Company/Custom Objects and is not substituted for Contact fields.
Native placement is a separately journaled, captured operation.
"""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
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


SCHEMA='skill6-contact-field-dependencies/1'
CAPABILITY='skill6-contact-fields-v3-capability/1'
LIST_PATH='/locations/{locationId}/customFields'
GET_PATH=LIST_PATH+'/{id}'
TYPES={'SINGLE_OPTIONS','LARGE_TEXT'}


def _text(value,*,empty=False):
    return (isinstance(value,str) and (empty or bool(value.strip())) and len(value)<=20000
        and not any(ord(char)<32 and char not in '\n\r\t' for char in value))


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)!={'location_id','fields'}:
        raise Stop('Contact dependencies require the exact location and authored fields')
    delivery._id(inputs['location_id'],'location_id')
    fields=inputs['fields']
    if not isinstance(fields,list) or not 1<=len(fields)<=100:
        raise Stop('Contact dependencies require one to 100 explicit fields')
    ids=set();names=set();keys=set()
    for field in fields:
        if not isinstance(field,dict) or not isinstance(field.get('data_type'),str) or field['data_type'] not in TYPES:
            raise Stop('Only Contact LARGE_TEXT and SINGLE_OPTIONS dependencies are implemented')
        kind=field['data_type'];specific={'placeholder'} if kind=='LARGE_TEXT' else {'options'}
        if (set(field)!={'name','field_key','data_type','expected_id','allow_creation'}|specific
                or not isinstance(field['name'],str) or not field['name'].strip()
                or field['name']!=field['name'].strip() or len(field['name'])>500
                or any(ord(c)<32 for c in field['name'])
                or not isinstance(field['field_key'],str)
                or not re.fullmatch(r'contact\.[A-Za-z0-9_.-]{1,240}',field['field_key'])
                or type(field['allow_creation']) is not bool):
            raise Stop('Contact field identity, type-specific values and creation intent must be explicit')
        if field['expected_id'] is not None:
            delivery._id(field['expected_id'],'expected_id')
            if field['expected_id'] in ids:raise Stop('Duplicate requested Contact field ID')
            ids.add(field['expected_id'])
        elif field['allow_creation'] is not True:
            raise Stop('Contact field reuse requires an exact existing ID')
        if kind=='SINGLE_OPTIONS':
            if field['allow_creation'] or field['expected_id'] is None:
                raise Stop('B-OPTIONS-FIELD: Contact v3 has no documented option-array create payload; Dropdown creation is not implemented')
            options=field['options']
            if (not isinstance(options,list) or not 1<=len(options)<=500
                    or any(not isinstance(v,str) or not v or v!=v.strip() or any(ord(c)<32 for c in v) for v in options)
                    or len(options)!=len(set(options))):
                raise Stop('Dropdown reuse requires its complete exact ordered API options')
        elif not _text(field['placeholder'],empty=True):
            raise Stop('LARGE_TEXT placeholder must be exact text, including significant surrounding whitespace')
        name,key=field['name'].casefold(),field['field_key'].casefold()
        if name in names or key in keys:raise Stop('Contact dependency names/keys must be unique')
        names.add(name);keys.add(key)
    return deepcopy(inputs)


def configuration_hash(inputs):
    return hashlib.sha256(json.dumps(validate_inputs(inputs),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_capability(value,location_id,*,creation=False):
    keys={'schema','location_id','provider','auth_kind','version','status','scopes','checked_at','source'}
    if (not isinstance(value,dict) or set(value)!=keys or value['schema']!=CAPABILITY
            or value['provider']!='public_api' or value['auth_kind'] not in ('location_pit','location_oauth')
            or value['status']!='PASS' or not isinstance(value['checked_at'],str)
            or not isinstance(value['source'],str) or not value['source'].strip()
            or not isinstance(value['scopes'],list) or any(not isinstance(scope,str) for scope in value['scopes'])):
        raise Stop('Contact dependencies need a fresh actual sub-account public-v3 capability receipt')
    scopes=('locations/customFields.readonly','locations/customFields.write') if creation else ('locations/customFields.readonly',)
    delivery._capability(value,location_id,scopes=scopes)
    try:age=(datetime.now(timezone.utc)-datetime.fromisoformat(value['checked_at'].replace('Z','+00:00'))).total_seconds()
    except (ValueError,TypeError):raise Stop('Contact capability timestamp must be timezone-aware') from None
    if not 0<=age<=3600:raise Stop('Contact capability is stale; a fresh same-location probe is required')
    return deepcopy(value)


class ContactFieldTransport:
    """Existing Skill44 credentials/headers/write gate; exact documented v3 routes."""
    def __init__(self):self.client=delivery.Skill44Transport().client
    def request(self,method,path,*,location_id,body=None,query=None):
        from urllib.parse import urlencode
        url=self.client.BASE_URL+path+('?' + urlencode(query) if query else '')
        if method!='GET':self.client.check_write(method,url,body,location_id=location_id)
        response=self.client.requests.request(method,url,headers=self.client._headers('v3',path,method),json=body,timeout=30)
        response.raise_for_status()
        return {'http_status':response.status_code,'body':response.json()}


def _request(api,plan,method,*,identity=None,body=None):
    path=(GET_PATH if identity is not None else LIST_PATH).replace('{locationId}',plan['location_id'])
    if identity is not None:path=path.replace('{id}',delivery._id(identity,'field id'))
    value=api.request(method,path,location_id=plan['location_id'],body=body,
        query={'model':'contact'} if method=='GET' and identity is None else None)
    status=201 if method=='POST' else 200
    if (not isinstance(value,dict) or set(value)!={'http_status','body'}
            or type(value['http_status']) is not int or value['http_status']!=status or not isinstance(value['body'],dict)):
        raise Stop('Contact API response lacks the exact documented successful status/wrapper')
    return value['body']


def _inventory(api,plan):
    value=_request(api,plan,'GET')
    if set(value)!={'customFields'} or not isinstance(value['customFields'],list):
        raise Stop('Contact field inventory is not the complete documented list wrapper')
    ids=set();keys=set()
    for field in value['customFields']:
        if (not isinstance(field,dict) or field.get('locationId')!=plan['location_id']
                or field.get('model')!='contact' or not isinstance(field.get('name'),str)
                or not field['name'].strip() or not isinstance(field.get('fieldKey'),str)
                or not field['fieldKey'].startswith('contact.')):
            raise Stop('Contact inventory has missing/foreign tenant, model, name or key identity')
        identity=delivery._id(field.get('id'),'inventory field id')
        key=field['fieldKey'].casefold()
        if identity in ids or key in keys:raise Stop('Contact inventory has duplicate field identities/keys')
        ids.add(identity);keys.add(key)
    return value['customFields']


def _get(api,plan,field,identity):
    if field['expected_id'] is not None and identity!=field['expected_id']:
        raise Stop('Contact reuse read must retain the exact authored field ID')
    value=_request(api,plan,'GET',identity=identity)
    if set(value)!={'customField'} or not isinstance(value['customField'],dict):
        raise Stop('Contact GET wrapper is not the documented exact field response')
    record=value['customField']
    if (record.get('id')!=identity or record.get('locationId')!=plan['location_id']
            or record.get('model')!='contact' or record.get('name')!=field['name']
            or record.get('fieldKey')!=field['field_key'] or record.get('dataType')!=field['data_type']):
        raise Stop('Contact API definition differs from exact requested ID/tenant/model/name/key/type')
    result={'id':identity,**{key:field[key] for key in ('name','field_key','data_type')}}
    if field['data_type']=='SINGLE_OPTIONS':
        if record.get('picklistOptions')!=field['options'] or record.get('picklistImageOptions') not in (None,[]):
            raise Stop('Dropdown API ordered options differ from the exact reuse inventory')
        result['options']=deepcopy(field['options'])
    elif record.get('placeholder')!=field['placeholder'] or record.get('picklistOptions') not in (None,[]):
        raise Stop('LARGE_TEXT API placeholder/type-specific data differ from the authored definition')
    return result


def _result(plan,fields):
    return {'status':'FIELD_DEPENDENCIES_VERIFIED','location_id':plan['location_id'],
        'configuration_sha256':configuration_hash(plan),'fields':deepcopy(fields),
        'field_dependencies':{'status':'VERIFIED','provider':'public_api','location_id':plan['location_id'],
            'observed_at':time.time(),'operation':'custom_fields.get','http_status':200,'fields':deepcopy(fields)},
        'native_placement_required':True,'submission_verified':False}


@guard_delivery('course')
def provision_fields(inputs,evidence_root,*,capability,transport=None):
    return _provision(inputs,evidence_root,capability=capability,transport=transport)


def _provision(inputs,evidence_root,*,capability,transport=None):
    plan=validate_inputs(inputs);validate_capability(capability,plan['location_id'])
    if os.environ.get('CAF_DRY_RUN','').lower() in ('1','true','yes','on'):
        raise Stop('Contact dependency dry run is read-only; use validate_inputs instead')
    root=Path(evidence_root).resolve();journal=root/'delivery-state.json';fingerprint=configuration_hash(plan)
    api=transport or ContactFieldTransport()
    if journal_present(journal):
        old=read_journal(journal)
        if (not isinstance(old,dict) or old.get('schema')!=SCHEMA or old.get('location_id')!=plan['location_id']
                or old.get('fingerprint')!=fingerprint or old.get('status')!='API_STEPS_COMPLETE'
                or old.get('current_step_status')!='VERIFIED' or not isinstance(old.get('fields'),list)
                or len(old['fields'])!=len(plan['fields'])):
            raise Stop('Contact dependency intent is uncertain or unbound; reconcile without another POST')
        verified=[]
        for field,saved in zip(plan['fields'],old['fields']):
            if not isinstance(saved,dict):raise Stop('Saved Contact dependency identity is malformed')
            actual=_get(api,plan,field,delivery._id(saved.get('id'),'saved field id'))
            if actual!=saved:raise Stop('Saved Contact dependency changed; do not recreate it')
            verified.append(actual)
        return _result(plan,verified)
    listed=_inventory(api,plan);seen_ids={row['id'] for row in listed};fields=[None]*len(plan['fields']);pending=[]
    for index,field in enumerate(plan['fields']):
        matches=[row for row in listed if row['id']==field['expected_id'] or row['name'].casefold()==field['name'].casefold()
            or row['fieldKey'].casefold()==field['field_key'].casefold()]
        if field['expected_id'] is None:
            if matches:raise Stop('Expected-absent Contact name/key exists; inventory the exact ID before reuse')
            pending.append((index,field))
        else:
            if len(matches)!=1 or matches[0]['id']!=field['expected_id']:
                raise Stop('Exact Contact reuse identity is absent or conflicted; creation is not a fallback')
            fields[index]=_get(api,plan,field,field['expected_id'])
    if pending:validate_capability(capability,plan['location_id'],creation=True)
    state={'schema':SCHEMA,'location_id':plan['location_id'],'fingerprint':fingerprint,
        'status':'RUNNING','current_step_status':'PREFLIGHT_COMPLETE','fields':fields}
    secure_json(journal,state)
    try:
        for index,field in pending:
            validate_capability(capability,plan['location_id'],creation=True)
            latest=_inventory(api,plan);latest_ids={row['id'] for row in latest}
            if any(row['name'].casefold()==field['name'].casefold() or row['fieldKey'].casefold()==field['field_key'].casefold() for row in latest):
                raise Stop('Contact name/key appeared after preflight; do not create or silently adopt it')
            body={'name':field['name'],'dataType':'LARGE_TEXT','placeholder':field['placeholder'],'model':'contact'}
            state.update(current_step_status='INTENT_RECORDED',current_field=index)
            secure_json(journal,state)
            created=_request(api,plan,'POST',body=body)
            if set(created)!={'customField'} or not isinstance(created['customField'],dict):raise Stop('Contact POST response lacks a created field identity')
            identity=delivery._id(created['customField'].get('id'),'created field id')
            state['created_id']=identity;secure_json(journal,state)
            if identity in seen_ids|latest_ids:raise Stop('Contact POST returned an already inventoried field ID')
            fields[index]=_get(api,plan,field,identity);seen_ids.add(identity)
            state.update(fields=fields,current_step_status='VERIFIED');secure_json(journal,state)
        for field,verified in zip(plan['fields'],fields):
            if _get(api,plan,field,verified['id'])!=verified:raise Stop('Earlier Contact dependency changed during provisioning')
        state.update(status='API_STEPS_COMPLETE',current_step_status='VERIFIED');secure_json(journal,state)
        return _result(plan,fields)
    except Exception as error:
        state.update(status='NEEDS_RECONCILIATION',error_type=type(error).__name__);secure_json(journal,state)
        raise
