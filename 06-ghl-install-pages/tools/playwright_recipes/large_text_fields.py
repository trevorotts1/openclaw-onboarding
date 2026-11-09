"""Place existing API-owned LARGE_TEXT fields through captured native controls.

The textarea has no API ID/name. Bind the exact API picker row to an explicit
native Query Key, label and placeholder. Native keys can contain colon/question
mark, and placeholder whitespace is significant. No global schema is created.
"""
from copy import deepcopy
import hashlib
import json
import math
import re
import time
from urllib.parse import urlsplit

if __package__:
    from .forms_advanced import _object_dialog,_object_row,_close_object_drawer,_canvas_identity
    from .field_placement import _close_properties
    from .assessments import reopen_editor
    from .skill6_playwright import Stop,assert_tenant,click,fill,form_builder,wait_until
else:
    from forms_advanced import _object_dialog,_object_row,_close_object_drawer,_canvas_identity
    from field_placement import _close_properties
    from assessments import reopen_editor
    from skill6_playwright import Stop,assert_tenant,click,fill,form_builder,wait_until


API_KEYS={'id','name','field_key','data_type'}
UI_KEYS={'native_query_key','expected_label','expected_placeholder'}
COMMON={'location_id','location_name','start_url'}


def _text(value,label,*,token=False):
    if (not isinstance(value,str) or not value or value!=value.strip() or len(value)>500
            or any(ord(c)<32 or token and c.isspace() for c in value)):
        raise Stop('Large Text '+label+' must be explicit inventoried text')
    return value


def _placeholder(value):
    if (not isinstance(value,str) or len(value)>20000
            or any(ord(c)<32 and c not in '\n\r\t' for c in value)):
        raise Stop('Large Text placeholder must be explicit exact text, including surrounding whitespace')
    return value


def _definition(value):
    if not isinstance(value,dict) or set(value)!=API_KEYS:
        raise Stop('Large Text API definitions require exact id/name/key/type')
    if not isinstance(value['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',value['id']):
        raise Stop('Large Text API field ID is invalid')
    _text(value['name'],'API name');_text(value['field_key'],'API key',token=True)
    if not value['field_key'].startswith('contact.') or value['field_key']=='contact.':
        raise Stop('Large Text fieldKey must identify an existing contact field')
    if value['data_type']!='LARGE_TEXT':
        raise Stop('Large Text requires its exact API LARGE_TEXT type')
    return deepcopy(value)


def validate(step,*,require_fresh=False):
    if (type(require_fresh) is not bool or not isinstance(step,dict)
            or set(step)-{'id','action','payload'}
            or step.get('action','native_large_text_fields')!='native_large_text_fields'):
        raise Stop('Unsupported native large_text placement metadata')
    payload=step.get('payload')
    if not isinstance(payload,dict) or set(payload)!=COMMON|{'large_text_fields','field_dependencies'}:
        raise Stop('Large Text placement requires exact editor, native binding and API dependency inputs')
    if not isinstance(payload['location_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',payload['location_id']):
        raise Stop('Large Text placement requires its exact location ID')
    _text(payload['location_name'],'account name')
    try:source=urlsplit(payload['start_url']);port=source.port
    except (TypeError,ValueError):raise Stop('Large Text editor URL is malformed') from None
    if (source.scheme!='https' or not source.hostname or source.username is not None or source.password is not None
            or port not in (None,443) or source.query or source.fragment
            or not re.fullmatch('/v2/location/'+re.escape(payload['location_id'])+
                                r'/form-builder-v2/[A-Za-z0-9_-]+',source.path)):
        raise Stop('Large Text placement must use the exact existing same-location form editor')
    fields=payload['large_text_fields']
    if not isinstance(fields,list) or not 1<=len(fields)<=100:
        raise Stop('Large Text fields must be a nonempty bounded placement list')
    for field in fields:
        if not isinstance(field,dict) or set(field)!=API_KEYS|UI_KEYS:
            raise Stop('Large Text placement requires separate explicit native Query Key and expected label')
        _definition({key:field[key] for key in API_KEYS})
        _text(field['native_query_key'],'native Query Key',token=True)
        _text(field['expected_label'],'native label')
        _placeholder(field['expected_placeholder'])
    for key in ('id','field_key','native_query_key'):
        if len({field[key] for field in fields})!=len(fields):
            raise Stop('Large Text requested IDs, API keys and native Query Keys must be unique')
    dep=payload['field_dependencies']
    if (not isinstance(dep,dict)
            or set(dep)!={'status','provider','location_id','observed_at','operation','http_status','fields'}
            or dep['status']!='VERIFIED' or dep['provider'] not in ('skill44','public_api','official_mcp')
            or dep['location_id']!=payload['location_id'] or dep['operation'] not in ('custom_fields.get','custom_fields.list')
            or type(dep['http_status']) is not int or dep['http_status']!=200
            or type(dep['observed_at']) not in (int,float) or not math.isfinite(dep['observed_at'])
            or dep['observed_at']<0 or require_fresh and not 0<=time.time()-dep['observed_at']<=3600
            or not isinstance(dep['fields'],list)):
        raise Stop('Large Text placement needs verified same-location API readback, fresh before a new mutation')
    definitions={};keys=set()
    for field in dep['fields']:
        if (not isinstance(field,dict) or not isinstance(field.get('id'),str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',field['id'])):
            raise Stop('Large Text dependency inventory identity is invalid')
        key=_text(field.get('field_key'),'dependency key',token=True)
        if not key.startswith('contact.') or key=='contact.' or field['id'] in definitions or key in keys:
            raise Stop('Large Text dependency inventory has duplicate or unbound identities')
        definitions[field['id']]=field;keys.add(key)
    for field in fields:
        if (field['id'] not in definitions or _definition(definitions[field['id']])!=
                {key:field[key] for key in API_KEYS}):
            raise Stop('Large Text request differs from its exact API-confirmed definition')
    return deepcopy(step)


def configuration_hash(step):
    payload=validate(step)['payload']
    return hashlib.sha256(json.dumps({**{key:payload[key] for key in COMMON},
        'large_text_fields':payload['large_text_fields']},sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _one(node,message):
    if node.count()!=1:raise Stop(message)
    return node


def _stable_canvas(scope):
    # An unrelated active Single Dropdown has a transient editor input. Exclude
    # only that captured UI control; keep this field's actual textarea identity.
    return _canvas_identity(scope)


def _widget(frame,item,index):
    labels=item.locator('[data-field-type="LARGE_TEXT"]')
    label=_one(labels,'Native large_text type/label is missing or ambiguous')
    if item.locator('[data-field-type]').count()!=1:
        raise Stop('Native large_text wrapper has more than one field type')
    click(label)
    textarea=_one(item.locator('textarea.form-placeholder.form-control'),
                  'Native Large Text textarea is missing or ambiguous')
    textarea.wait_for(state='visible',timeout=45000)
    if textarea.get_attribute('id') is not None or textarea.get_attribute('name') is not None:
        raise Stop('Native Large Text textarea identity differs from the captured no-ID/no-name shape')
    if textarea.input_value()!='':
        raise Stop('Native Large Text textarea contains an unexpected authored value')
    placeholder=_placeholder(textarea.get_attribute('aria-label'))
    click(_one(item.locator('[aria-label="Open settings"]'),'Native large_text settings owner changed'))
    query=frame.locator('#fieldQueryKey input')
    if query.count()!=1 or not query.is_visible():
        click(_one(frame.get_by_text('General Settings',exact=True),'Native large_text General Settings changed'))
    query=_one(frame.locator('#fieldQueryKey input'),'Native large_text Query Key control changed')
    title=_one(frame.locator('#label input'),'Native large_text Label control changed')
    query.wait_for(state='visible',timeout=45000);title.wait_for(state='visible',timeout=45000)
    property_placeholder=_one(frame.locator('#fieldPlaceholder input'),'Native Large Text Placeholder control changed')
    if property_placeholder.input_value()!=placeholder:
        raise Stop('Native Large Text textarea and Placeholder property differ')
    record={'native_query_key':_text(query.input_value(),'native Query Key',token=True),
            'expected_label':_text(title.input_value(),'native label'),'expected_placeholder':placeholder}
    _close_properties(frame);_close_object_drawer(frame,'form')
    return index,record


def _inventory(frame,scope):
    _close_object_drawer(frame,'form')
    items=scope.locator(':scope > .form-field-wrapper');count=items.count();result=[]
    for index in range(count):
        if items.count()!=count:raise Stop('Native large_text owner canvas changed during inventory')
        item=items.nth(index);kind=item.locator('[data-field-type]')
        if kind.count()!=1:raise Stop('Native canvas field type inventory is incomplete')
        if kind.get_attribute('data-field-type')=='LARGE_TEXT':
            result.append(_widget(frame,item,index))
    keys=[record['native_query_key'] for _,record in result]
    if len(set(keys))!=len(keys):raise Stop('Native large_text Query Keys are duplicated')
    return result


def _expected(field):
    return {key:field[key] for key in ('native_query_key','expected_label','expected_placeholder')}


def _preserved(before_canvas,before_large_texts,after_canvas,after_large_texts,added):
    new={field['native_query_key']:_expected(field) for field in added}
    found={record['native_query_key']:(index,record) for index,record in after_large_texts}
    if any(key not in found or found[key][1]!=record for key,record in new.items()):
        raise Stop('Added large_text differs from its captured native Query Key/label/placeholder')
    indices={found[key][0] for key in new}
    if ([row for index,row in enumerate(after_canvas) if index not in indices]!=before_canvas
            or [record for _,record in after_large_texts if record['native_query_key'] not in new]
            !=[record for _,record in before_large_texts]):
        raise Stop('Large Text insertion changed unrelated native field identities or large_text definitions')


def configure(page,step):
    plan=validate(step,require_fresh=True);data=plan['payload']
    if page.url!=data['start_url']:raise Stop('Large Text current editor differs from the exact requested form')
    assert_tenant(page,data)
    frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or not title.input_value().strip():raise Stop('Large Text form identity is unavailable')
    name=title.input_value();scope=_one(frame.locator('#form-builder-container'),'Native large_text owner canvas changed')
    _close_object_drawer(frame,'form');click(frame.get_by_role('tab',name='Edit',exact=True))
    before_large_texts=_inventory(frame,scope);before_canvas=_stable_canvas(scope)
    known={record['native_query_key']:record for _,record in before_large_texts}
    dialog,search=_object_dialog(frame,'form')
    if dialog.get_by_text(re.compile(r'^\s*\d+ selected\s*$')).count():
        raise Stop('Native large_text picker contains an unrelated selection')
    pending=[]
    for field in data['large_text_fields']:
        _,tile,checkbox=_object_row(dialog,search,field)
        if tile.get_attribute('aria-disabled')=='true':
            raise Stop('LARGE_TEXT_REUSE_IDENTITY_UNVERIFIED: disabled API picker row has no captured canvas API-ID link; use the original completed insertion journal or reconcile before any write')
        else:
            if (checkbox.get_attribute('aria-checked')!='false'
                    or field['native_query_key'] in known or field['expected_label']!=field['name']):
                raise Stop('Pending API large_text conflicts with existing native identity or default label')
            pending.append(field)
    fill(search,'');_close_object_drawer(frame,'form')
    added=[]
    for field in pending:
        validate(plan,require_fresh=True);assert_tenant(page,data)
        if page.url!=data['start_url'] or title.input_value()!=name:
            raise Stop('Native large_text target changed before insertion')
        current=_inventory(frame,scope);canvas=_stable_canvas(scope)
        _preserved(before_canvas,before_large_texts,canvas,current,added)
        dialog,search=_object_dialog(frame,'form')
        if dialog.get_by_text(re.compile(r'^\s*\d+ selected\s*$')).count():
            raise Stop('Native large_text picker selection changed after preflight')
        _,tile,checkbox=_object_row(dialog,search,field)
        if tile.get_attribute('aria-disabled')!='false' or checkbox.get_attribute('aria-checked')!='false':
            raise Stop('Native large_text availability changed after preflight')
        click(checkbox)
        wait_until(lambda:checkbox.get_attribute('aria-checked')=='true','Native large_text selection did not stick')
        selected=dialog.locator('.cf-row-wrap').filter(has=dialog.locator('.custom-item[aria-disabled="false"]')).filter(
            has=dialog.locator('[role="checkbox"][aria-checked="true"]'))
        if (selected.count()!=1 or selected.get_attribute('data-field-id')!=field['id']
                or dialog.get_by_text('1 selected',exact=True).count()!=1):
            raise Stop('Native large_text insertion includes an unrelated selected field')
        add=_one(dialog.get_by_role('button',name='Add 1 field',exact=True),'Native Add 1 field control changed')
        if not add.is_enabled():raise Stop('Native large_text Add control is disabled')
        count=len(canvas);click(add)
        wait_until(lambda:scope.locator(':scope > .form-field-wrapper').count()==count+1
            and tile.get_attribute('aria-disabled')=='true','Native large_text insertion did not settle once')
        fill(search,'');_close_object_drawer(frame,'form')
        added.append(field)
        _preserved(before_canvas,before_large_texts,_stable_canvas(scope),_inventory(frame,scope),added)
    final_large_texts=_inventory(frame,scope);final_canvas=_stable_canvas(scope)
    _preserved(before_canvas,before_large_texts,final_canvas,final_large_texts,added)
    if pending:
        assert_tenant(page,data)
        if page.url!=data['start_url'] or title.input_value()!=name:raise Stop('Large Text target changed before Save')
        save=_one(frame.get_by_role('button',name='Save',exact=True),'Native large_text Save changed')
        click(save);wait_until(lambda:save.is_enabled(),'Native large_text Save remains busy')
        try:page.wait_for_load_state('networkidle',timeout=45000)
        except Exception:raise Stop('Native large_text Save traffic did not settle; reconcile before another insert') from None
    reopen_editor(page,'form',name,data['start_url'])
    frame=form_builder(page);scope=_one(frame.locator('#form-builder-container'),'Reopened large_text owner changed')
    assert_tenant(page,data)
    after_large_texts=_inventory(frame,scope)
    if (after_large_texts!=final_large_texts or _stable_canvas(scope)!=final_canvas):
        raise Stop('Native large_text definitions or other field identities did not persist after independent reopen')
    return {'status':'LARGETEXT_FIELDS_SAVED_AND_REOPENED','editor_url':page.url,
        'fields':[{**{key:field[key] for key in ('id','field_key','data_type','native_query_key')},
            'placement':'added'} for field in data['large_text_fields']],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False}


def validate_receipt(result,step):
    """Known completed insertions may replay; unproven legacy reuse may not."""
    plan=validate(step);data=plan['payload']
    expected_fields=[{**{key:field[key] for key in ('id','field_key','data_type','native_query_key')},
                      'placement':'added'} for field in data['large_text_fields']]
    if (not isinstance(result,dict) or result.get('status')!='LARGETEXT_FIELDS_SAVED_AND_REOPENED'
            or result.get('editor_url')!=data['start_url'] or result.get('fields')!=expected_fields
            or result.get('configuration_sha256')!=configuration_hash(plan)
            or result.get('independent_readback')!='VERIFIED'
            or result.get('behavior_verified') is not False or result.get('submission_verified') is not False):
        raise Stop('Native Large Text insertion receipt is malformed or lacks exact new-insertion provenance')
    return {'fields':expected_fields,'configuration_sha256':configuration_hash(plan)}
