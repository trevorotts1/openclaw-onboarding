"""Place existing API-owned SINGLE_OPTIONS fields using captured native controls.

The native dropdown has no API field ID on its canvas wrapper. Its picker row
does: bind that exact ID/key/name to the independently inventoried native Query
Key, label and ordered options. Never invent a canvas ID or derive Query Key
from API fieldKey; legacy forms can expose different strings for those keys.
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
    from .assessments import reopen_editor, read_editor_title
    from .skill6_playwright import Stop,assert_tenant,click,fill,form_builder,wait_until
else:
    from forms_advanced import _object_dialog,_object_row,_close_object_drawer,_canvas_identity
    from field_placement import _close_properties
    from assessments import reopen_editor, read_editor_title
    from skill6_playwright import Stop,assert_tenant,click,fill,form_builder,wait_until


API_KEYS={'id','name','field_key','data_type','options'}
UI_KEYS={'native_query_key','expected_label'}
COMMON={'location_id','location_name','start_url'}


def _text(value,label,*,token=False):
    if (not isinstance(value,str) or not value or value!=value.strip() or len(value)>500
            or any(ord(c)<32 or token and c.isspace() for c in value)):
        raise Stop('Dropdown '+label+' must be explicit inventoried text')
    return value


def _definition(value):
    if not isinstance(value,dict) or set(value)!=API_KEYS:
        raise Stop('Dropdown API definitions require exact id/name/key/type/options')
    if not isinstance(value['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',value['id']):
        raise Stop('Dropdown API field ID is invalid')
    _text(value['name'],'API name');_text(value['field_key'],'API key',token=True)
    if not value['field_key'].startswith('contact.') or value['field_key']=='contact.':
        raise Stop('Dropdown fieldKey must identify an existing contact field')
    options=value['options']
    if (value['data_type']!='SINGLE_OPTIONS' or not isinstance(options,list) or not 1<=len(options)<=500
            or any(not isinstance(option,str) or not option or option!=option.strip()
                   or any(ord(c)<32 for c in option) for option in options)
            or len(set(options))!=len(options)):
        raise Stop('Dropdown requires its complete ordered SINGLE_OPTIONS API choice list')
    return deepcopy(value)


def validate(step,*,require_fresh=False):
    if (type(require_fresh) is not bool or not isinstance(step,dict)
            or set(step)-{'id','action','payload'}
            or step.get('action','native_dropdown_fields')!='native_dropdown_fields'):
        raise Stop('Unsupported native dropdown placement metadata')
    payload=step.get('payload')
    if not isinstance(payload,dict) or set(payload)!=COMMON|{'dropdown_fields','field_dependencies'}:
        raise Stop('Dropdown placement requires exact editor, native binding and API dependency inputs')
    if not isinstance(payload['location_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',payload['location_id']):
        raise Stop('Dropdown placement requires its exact location ID')
    _text(payload['location_name'],'account name')
    try:source=urlsplit(payload['start_url']);port=source.port
    except (TypeError,ValueError):raise Stop('Dropdown editor URL is malformed') from None
    if (source.scheme!='https' or not source.hostname or source.username is not None or source.password is not None
            or port not in (None,443) or source.query or source.fragment
            or not re.fullmatch('/v2/location/'+re.escape(payload['location_id'])+
                                r'/form-builder-v2/[A-Za-z0-9_-]+',source.path)):
        raise Stop('Dropdown placement must use the exact existing same-location form editor')
    fields=payload['dropdown_fields']
    if not isinstance(fields,list) or not 1<=len(fields)<=100:
        raise Stop('Dropdown fields must be a nonempty bounded placement list')
    for field in fields:
        if not isinstance(field,dict) or set(field)!=API_KEYS|UI_KEYS:
            raise Stop('Dropdown placement requires separate explicit native Query Key and expected label')
        _definition({key:field[key] for key in API_KEYS})
        _text(field['native_query_key'],'native Query Key',token=True)
        _text(field['expected_label'],'native label')
    for key in ('id','field_key','native_query_key'):
        if len({field[key] for field in fields})!=len(fields):
            raise Stop('Dropdown requested IDs, API keys and native Query Keys must be unique')
    dep=payload['field_dependencies']
    if (not isinstance(dep,dict)
            or set(dep)!={'status','provider','location_id','observed_at','operation','http_status','fields'}
            or dep['status']!='VERIFIED' or dep['provider'] not in ('skill44','public_api','official_mcp')
            or dep['location_id']!=payload['location_id'] or dep['operation'] not in ('custom_fields.get','custom_fields.list')
            or type(dep['http_status']) is not int or dep['http_status']!=200
            or type(dep['observed_at']) not in (int,float) or not math.isfinite(dep['observed_at'])
            or dep['observed_at']<0 or require_fresh and not 0<=time.time()-dep['observed_at']<=3600
            or not isinstance(dep['fields'],list)):
        raise Stop('Dropdown placement needs verified same-location API readback, fresh before a new mutation')
    definitions={};keys=set()
    for field in dep['fields']:
        if (not isinstance(field,dict) or not isinstance(field.get('id'),str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',field['id'])):
            raise Stop('Dropdown dependency inventory identity is invalid')
        key=_text(field.get('field_key'),'dependency key',token=True)
        if not key.startswith('contact.') or key=='contact.' or field['id'] in definitions or key in keys:
            raise Stop('Dropdown dependency inventory has duplicate or unbound identities')
        definitions[field['id']]=field;keys.add(key)
    for field in fields:
        if (field['id'] not in definitions or _definition(definitions[field['id']])!=
                {key:field[key] for key in API_KEYS}):
            raise Stop('Dropdown request differs from its exact API-confirmed definition')
    return deepcopy(step)


def configuration_hash(step):
    payload=validate(step)['payload']
    return hashlib.sha256(json.dumps({**{key:payload[key] for key in COMMON},
        'dropdown_fields':payload['dropdown_fields']},sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _one(node,message):
    if node.count()!=1:raise Stop(message)
    return node


def _stable_canvas(scope):
    # The active dropdown's editor-only placeholder input has no API name and
    # disappears when it loses selection. Exclude precisely that captured UI
    # control, retaining actual input/select identities on every other widget.
    return _canvas_identity(scope)


def _widget(frame,item,index):
    labels=item.locator('[data-field-type="SINGLE_OPTIONS"]')
    label=_one(labels,'Native dropdown type/label is missing or ambiguous')
    if item.locator('[data-field-type]').count()!=1:
        raise Stop('Native dropdown wrapper has more than one field type')
    click(label)
    options=item.locator('#options-card .option label[contenteditable]')
    options.first.wait_for(state='visible',timeout=45000)
    values=options.evaluate_all('nodes=>nodes.map(node=>(node.textContent||"").trim())')
    if (not isinstance(values,list) or not values or len(set(values))!=len(values)
            or any(not isinstance(v,str) or not v for v in values)):
        raise Stop('Native dropdown complete option inventory is unavailable')
    click(_one(item.locator('[aria-label="Open settings"]'),'Native dropdown settings owner changed'))
    query=frame.locator('#fieldQueryKey input')
    if query.count()!=1 or not query.is_visible():
        click(_one(frame.get_by_text('General Settings',exact=True),'Native dropdown General Settings changed'))
    query=_one(frame.locator('#fieldQueryKey input'),'Native dropdown Query Key control changed')
    title=_one(frame.locator('#label input'),'Native dropdown Label control changed')
    query.wait_for(state='visible',timeout=45000);title.wait_for(state='visible',timeout=45000)
    record={'native_query_key':_text(query.input_value(),'native Query Key',token=True),
            'expected_label':_text(title.input_value(),'native label'),'options':values}
    _close_properties(frame);_close_object_drawer(frame,'form')
    return index,record


def _inventory(frame,scope):
    _close_object_drawer(frame,'form')
    items=scope.locator(':scope > .form-field-wrapper');count=items.count();result=[]
    for index in range(count):
        if items.count()!=count:raise Stop('Native dropdown owner canvas changed during inventory')
        item=items.nth(index);kind=item.locator('[data-field-type]')
        if kind.count()!=1:raise Stop('Native canvas field type inventory is incomplete')
        if kind.get_attribute('data-field-type')=='SINGLE_OPTIONS':
            result.append(_widget(frame,item,index))
    keys=[record['native_query_key'] for _,record in result]
    if len(set(keys))!=len(keys):raise Stop('Native dropdown Query Keys are duplicated')
    return result



def _prove_existing_owner(frame,scope,field,inventory):
    """Join the actual Advanced canonical key to the exact API-owned picker row.

    Disabled picker state alone proves no canvas ownership. The current native
    Query Key, label and ordered choices must identify exactly one wrapper, and
    that wrapper's saved canonical name/key must independently match the API.
    """
    matches=[(index,record) for index,record in inventory
             if record['native_query_key']==field['native_query_key']]
    if len(matches)!=1 or matches[0][1]!=_expected(field):
        raise Stop('DROPDOWN_REUSE_IDENTITY_UNVERIFIED: current native owner differs from its exact API-bound Query Key/label/options')
    from playwright_recipes.form_widget_families import _read
    index=matches[0][0];items=scope.locator(':scope > .form-field-wrapper')
    count=items.count()
    if type(count) is not int or index>=count:
        raise Stop('DROPDOWN_REUSE_IDENTITY_UNVERIFIED: legacy canvas owner is missing or ambiguous')
    observed=_read(frame,items.nth(index),'single_dropdown')
    if (observed['unique_key']!=field['field_key'] or observed['custom_field_name']!=field['name']
            or observed['query_key']!=field['native_query_key'] or observed['label']!=field['expected_label']
            or [option['label'] for option in observed['options']]!=field['options']):
        raise Stop('DROPDOWN_REUSE_IDENTITY_UNVERIFIED: native Advanced canonical metadata does not match the exact API field')
    return observed


def _expected(field):
    return {key:field[key] for key in ('native_query_key','expected_label','options')}


def _receipt_reuse_proof(observed):
    return {'unique_key':observed['unique_key'],'custom_field_name':observed['custom_field_name'],
        'query_key':observed['query_key'],'label':observed['label'],
        'options':[{'label':option['label']} for option in observed['options']]}


def _preserved(before_canvas,before_dropdowns,after_canvas,after_dropdowns,added):
    new={field['native_query_key']:_expected(field) for field in added}
    found={record['native_query_key']:(index,record) for index,record in after_dropdowns}
    if any(key not in found or found[key][1]!=record for key,record in new.items()):
        raise Stop('Added dropdown differs from its captured native Query Key/label/options')
    indices={found[key][0] for key in new}
    if ([row for index,row in enumerate(after_canvas) if index not in indices]!=before_canvas
            or [record for _,record in after_dropdowns if record['native_query_key'] not in new]
            !=[record for _,record in before_dropdowns]):
        raise Stop('Dropdown insertion changed unrelated native field identities or dropdown definitions')


def configure(page,step):
    plan=validate(step,require_fresh=True);data=plan['payload']
    if page.url!=data['start_url']:raise Stop('Dropdown current editor differs from the exact requested form')
    assert_tenant(page,data)
    frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or not read_editor_title(title).strip():raise Stop('Dropdown form identity is unavailable')
    name=read_editor_title(title);scope=_one(frame.locator('#form-builder-container'),'Native dropdown owner canvas changed')
    _close_object_drawer(frame,'form');click(frame.get_by_role('tab',name='Edit',exact=True))
    before_dropdowns=_inventory(frame,scope);before_canvas=_stable_canvas(scope)
    known={record['native_query_key']:record for _,record in before_dropdowns}
    dialog,search=_object_dialog(frame,'form')
    if dialog.get_by_text(re.compile(r'^\s*\d+ selected\s*$')).count():
        raise Stop('Native dropdown picker contains an unrelated selection')
    pending=[];reused=[]
    for field in data['dropdown_fields']:
        _,tile,checkbox=_object_row(dialog,search,field)
        if tile.get_attribute('aria-disabled')=='true':
            reused.append(field)
        else:
            if (checkbox.get_attribute('aria-checked')!='false'
                    or field['native_query_key'] in known or field['expected_label']!=field['name']):
                raise Stop('Pending API dropdown conflicts with existing native identity or default label')
            pending.append(field)
    fill(search,'');_close_object_drawer(frame,'form')
    adopted={field['id']:_prove_existing_owner(frame,scope,field,before_dropdowns) for field in reused}
    if _stable_canvas(scope)!=before_canvas:
        raise Stop('Legacy Dropdown adoption changed an existing canvas identity')
    added=[]
    for field in pending:
        validate(plan,require_fresh=True);assert_tenant(page,data)
        if page.url!=data['start_url'] or read_editor_title(title)!=name:
            raise Stop('Native dropdown target changed before insertion')
        current=_inventory(frame,scope);canvas=_stable_canvas(scope)
        _preserved(before_canvas,before_dropdowns,canvas,current,added)
        dialog,search=_object_dialog(frame,'form')
        if dialog.get_by_text(re.compile(r'^\s*\d+ selected\s*$')).count():
            raise Stop('Native dropdown picker selection changed after preflight')
        _,tile,checkbox=_object_row(dialog,search,field)
        if tile.get_attribute('aria-disabled')!='false' or checkbox.get_attribute('aria-checked')!='false':
            raise Stop('Native dropdown availability changed after preflight')
        click(checkbox)
        wait_until(lambda:checkbox.get_attribute('aria-checked')=='true','Native dropdown selection did not stick')
        selected=dialog.locator('.cf-row-wrap').filter(has=dialog.locator('.custom-item[aria-disabled="false"]')).filter(
            has=dialog.locator('[role="checkbox"][aria-checked="true"]'))
        if (selected.count()!=1 or selected.get_attribute('data-field-id')!=field['id']
                or dialog.get_by_text('1 selected',exact=True).count()!=1):
            raise Stop('Native dropdown insertion includes an unrelated selected field')
        add=_one(dialog.get_by_role('button',name='Add 1 field',exact=True),'Native Add 1 field control changed')
        if not add.is_enabled():raise Stop('Native dropdown Add control is disabled')
        count=len(canvas);click(add)
        wait_until(lambda:scope.locator(':scope > .form-field-wrapper').count()==count+1
            and tile.get_attribute('aria-disabled')=='true','Native dropdown insertion did not settle once')
        fill(search,'');_close_object_drawer(frame,'form')
        added.append(field)
        _preserved(before_canvas,before_dropdowns,_stable_canvas(scope),_inventory(frame,scope),added)
    final_dropdowns=_inventory(frame,scope);final_canvas=_stable_canvas(scope)
    _preserved(before_canvas,before_dropdowns,final_canvas,final_dropdowns,added)
    if pending:
        assert_tenant(page,data)
        if page.url!=data['start_url'] or read_editor_title(title)!=name:raise Stop('Dropdown target changed before Save')
        save=_one(frame.get_by_role('button',name='Save',exact=True),'Native dropdown Save changed')
        click(save);wait_until(lambda:save.is_enabled(),'Native dropdown Save remains busy')
        try:page.wait_for_load_state('networkidle',timeout=45000)
        except Exception:raise Stop('Native dropdown Save traffic did not settle; reconcile before another insert') from None
    reopen_editor(page,'form',name,data['start_url'])
    frame=form_builder(page);scope=_one(frame.locator('#form-builder-container'),'Reopened dropdown owner changed')
    assert_tenant(page,data)
    after_dropdowns=_inventory(frame,scope)
    if any(_prove_existing_owner(frame,scope,field,after_dropdowns)!=adopted[field['id']] for field in reused):
        raise Stop('Legacy Dropdown canonical owner changed after independent reopen')
    if (after_dropdowns!=final_dropdowns or _stable_canvas(scope)!=final_canvas):
        raise Stop('Native dropdown definitions or other field identities did not persist after independent reopen')
    return {'status':'DROPDOWN_FIELDS_SAVED_AND_REOPENED','editor_url':page.url,
        'fields':[{**{key:field[key] for key in ('id','field_key','data_type','native_query_key')},
            'placement':'reused' if field['id'] in adopted else 'added',
            **({'reuse_proof':_receipt_reuse_proof(adopted[field['id']])} if field['id'] in adopted else {})}
            for field in data['dropdown_fields']],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False}


def validate_receipt(result,step):
    """Completed insertions and positively joined legacy owners retain exact identities."""
    plan=validate(step);data=plan['payload']
    records=result.get('fields') if isinstance(result,dict) else None
    if (not isinstance(records,list) or len(records)!=len(data['dropdown_fields'])
            or any(not isinstance(record,dict) or record.get('placement') not in ('added','reused') for record in records)):
        raise Stop('Dropdown completion lacks its exact placement disposition')
    expected_fields=[]
    for field,record in zip(data['dropdown_fields'],records):
        expected={**{key:field[key] for key in ('id','field_key','data_type','native_query_key')},
                  'placement':record['placement']}
        if record['placement']=='reused':
            proof=record.get('reuse_proof')
            from playwright_recipes.form_widget_families import _read
            if (not isinstance(proof,dict) or set(proof)!={'unique_key','custom_field_name','query_key','label','options'}
                    or proof.get('unique_key')!=field['field_key'] or proof.get('custom_field_name')!=field['name']
                    or proof.get('query_key')!=field['native_query_key'] or proof.get('label')!=field['expected_label']
                    or not isinstance(proof.get('options'),list)
                    or any(not isinstance(option,dict) or set(option)!={'label'} for option in proof['options'])
                    or [option['label'] for option in proof['options']]!=field['options']):
                raise Stop('Reused dropdown lacks an exact canonical native owner proof')
            expected['reuse_proof']=deepcopy(proof)
        elif 'reuse_proof' in record:
            raise Stop('New dropdown insertion cannot carry a legacy reuse proof')
        expected_fields.append(expected)
    if (not isinstance(result,dict) or result.get('status')!='DROPDOWN_FIELDS_SAVED_AND_REOPENED'
            or result.get('editor_url')!=data['start_url'] or result.get('fields')!=expected_fields
            or result.get('configuration_sha256')!=configuration_hash(plan)
            or result.get('independent_readback')!='VERIFIED'
            or result.get('behavior_verified') is not False or result.get('submission_verified') is not False):
        raise Stop('Native dropdown placement receipt is malformed or lacks exact ownership provenance')
    return {'fields':expected_fields,'configuration_sha256':configuration_hash(plan)}


def verify_completed(page,step,receipt):
    """Re-read API-picker/canonical canvas joins without repeating Add or Save."""
    validate_receipt(receipt,step);data=validate(step)['payload']
    if page.url!=data['start_url']:raise Stop('Completed Dropdown replay changed its exact editor')
    assert_tenant(page,data);frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or not read_editor_title(title).strip():
        raise Stop('Completed Dropdown form identity is unavailable')
    name=read_editor_title(title)
    reopen_editor(page,'form',name,data['start_url']);frame=form_builder(page)
    assert_tenant(page,data)
    scope=_one(frame.locator('#form-builder-container'),'Completed Dropdown owner canvas changed')
    _close_object_drawer(frame,'form');click(frame.get_by_role('tab',name='Edit',exact=True))
    inventory=_inventory(frame,scope);before=_stable_canvas(scope)
    dialog,search=_object_dialog(frame,'form')
    for field in data['dropdown_fields']:
        _,tile,_=_object_row(dialog,search,field)
        if tile.get_attribute('aria-disabled')!='true':
            raise Stop('Completed Dropdown no longer owns its exact API picker field')
    fill(search,'');_close_object_drawer(frame,'form')
    for field,record in zip(data['dropdown_fields'],receipt['fields']):
        observed=_prove_existing_owner(frame,scope,field,inventory)
        if record['placement']=='reused' and _receipt_reuse_proof(observed)!=record['reuse_proof']:
            raise Stop('Completed Dropdown canonical owner differs from its recorded reuse proof')
    if _stable_canvas(scope)!=before:
        raise Stop('Completed Dropdown verification changed a sibling owner')
    return deepcopy(receipt)
