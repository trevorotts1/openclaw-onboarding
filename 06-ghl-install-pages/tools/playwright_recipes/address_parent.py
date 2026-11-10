"""Captured parent Address controls with complete protected child inventory."""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

if __package__:
    from . import forms_advanced as child
    from .skill6_playwright import Stop, assert_tenant, click, form_builder, wait_until
    from .assessments import read_editor_title, reopen_editor
else:
    import forms_advanced as child
    from skill6_playwright import Stop, assert_tenant, click, form_builder, wait_until
    from assessments import read_editor_title, reopen_editor

FLAGS={'autocomplete','search_required'}
CHILD_PROPERTIES={'label','placeholder','short_label','required','hidden','hidden_value'}
COMMON={'location_id','location_name','start_url','form_name','expected_inventory',
        'expected_children','expected_controls','controls'}


def _text(value):
    return isinstance(value,str) and bool(value.strip()) and value==value.strip() and not any(ord(c)<32 for c in value)


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','native_address_parent')!='native_address_parent'):
        raise Stop('Unsupported parent Address configuration')
    data=step.get('payload')
    if not isinstance(data,dict) or set(data)!=COMMON:
        raise Stop('Parent Address requires complete identities, controls and preservation inventories')
    if any(not _text(data[key]) for key in ('location_id','location_name','start_url','form_name')):
        raise Stop('Parent Address identity is missing')
    for key in ('expected_controls','controls'):
        if not isinstance(data[key],dict) or set(data[key])!=FLAGS or any(type(v) is not bool for v in data[key].values()):
            raise Stop('Both parent Address choices require explicit Boolean values')
        if data[key]['search_required'] and not data[key]['autocomplete']:
            raise Stop('Mandatory address selection requires parent autocomplete enabled')
    url=urlsplit(data['start_url'])
    path='/v2/location/'+re.escape(data['location_id'])+'/form-builder-v2/[A-Za-z0-9_-]+'
    if (url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None
            or url.query or url.fragment or url.port not in (None,443) or not re.fullmatch(path,url.path)):
        raise Stop('Parent Address must bind the exact native form editor')
    inventory=data['expected_inventory']
    if (not isinstance(inventory,dict) or not inventory or any(not _text(k) or not _text(v) for k,v in inventory.items())):
        raise Stop('Parent Address requires the full expected query/type inventory')
    children=data['expected_children']
    if not isinstance(children,dict) or set(children)!=set(child._ADDRESS_QUERIES):
        raise Stop('Parent Address requires all five protected children')
    keys=set()
    for label,item in children.items():
        if not isinstance(item,dict) or set(item)!=CHILD_PROPERTIES|{'query_key'}:
            raise Stop('Each protected Address child requires its complete property inventory')
        query=child._token(item['query_key'])
        if query in keys or inventory.get(query)!='group':
            raise Stop('Protected Address child query identities are missing or duplicated')
        keys.add(query)
        for key,value in item.items():
            if key in ('required','hidden'):
                if type(value) is not bool:raise Stop('Protected child flags require real Booleans')
            elif key=='hidden_value' and value is None and item.get('hidden') is False:pass
            elif not isinstance(value,str) or len(value)>5000 or any(ord(c)<32 and c not in '\n\r\t' for c in value):
                raise Stop('Protected child text properties are invalid')
        if not item['label'].strip() or item['required'] and item['hidden']:
            raise Stop('Protected Address child has invalid label or mutually exclusive flags')
        if not item['hidden'] and item['hidden_value'] is not None:
            raise Stop('Unhidden protected child must have absent hidden value')
    return deepcopy(step)


def preflight(job):
    matching=[step for step in job.get('steps',[]) if step.get('action')=='native_address_parent']
    if matching:
        if len(job['steps'])!=1:raise Stop('Parent Address requires one independently journaled step')
        plan=validate(matching[0])
        if any(plan['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):
            raise Stop('Parent Address payload belongs to another parent job')


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step)['payload'],sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _children(frame):
    return {label:{'query_key':child._child(frame,label)[1],**child._child_properties(frame,label)[1]}
            for label in child._ADDRESS_QUERIES}


def _controls(frame):
    section=frame.locator('#address-auto-complete.n-collapse-item')
    if section.count()!=1:raise Stop('Native Address autocomplete section changed')
    header=section.locator('.n-collapse-item__header-main')
    if header.count()!=1 or not re.fullmatch(r'\s*Auto Complete Address\s*New\s*',header.inner_text()):
        raise Stop('Native Address autocomplete heading changed')
    rows=section.locator('.flex.justify-between.py-2')
    if rows.count()==0 or not rows.first.is_visible():
        click(header)
    rows=section.locator('.flex.justify-between.py-2')
    wait_until(lambda:rows.count()==2 and rows.first.is_visible(),'Native Address parent control section did not open')
    if rows.count()!=2:raise Stop('Native Address parent control row inventory changed')
    controls,state={},{}
    for key,label in (('autocomplete','Auto-Complete Address'),
                      ('search_required','Mandatory to Select Address in Search Bar')):
        row=rows.filter(has=frame.get_by_text(label,exact=True))
        control=row.locator('div[role="switch"]')
        if row.count()!=1 or control.count()!=1 or not control.is_visible():
            raise Stop('Native Address parent switch identity changed: '+key)
        checked=control.get_attribute('aria-checked')
        if checked not in ('true','false'):
            raise Stop('Native Address parent switch state is unavailable')
        controls[key],state[key]=control,checked=='true'
    if state['search_required'] and not state['autocomplete']:
        raise Stop('Native Address mandatory dependency changed')
    for key in FLAGS:
        disabled='n-switch--disabled' in (controls[key].get_attribute('class') or '').split()
        if disabled!=(key=='search_required' and not state['autocomplete']):
            raise Stop('Native Address parent disabled-state dependency changed')
    return controls,state


def _open(page,data):
    if page.url!=data['start_url']:raise Stop('Parent Address editor URL changed')
    assert_tenant(page,data)
    frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or read_editor_title(title)!=data['form_name']:
        raise Stop('Parent Address form title changed')
    if child._inventory(frame,allow_unknown_queries=True)!=data['expected_inventory']:
        raise Stop('Parent Address protected sibling inventory changed')
    child._open_address(frame)
    if _children(frame)!=data['expected_children']:
        raise Stop('Parent Address protected child properties changed')
    return frame


def _receipt(page,step):
    return {'status':'ADDRESS_PARENT_SAVED_AND_REOPENED','kind':'address_parent','editor_url':page.url,
        'configuration_sha256':configuration_hash(step),'controls':deepcopy(step['payload']['controls']),
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False}


def verify(page,step,result):
    plan=validate(step);validate_receipt(result,plan)
    frame=_open(page,plan['payload'])
    if _controls(frame)[1]!=plan['payload']['controls']:
        raise Stop('Parent Address completed replay no longer matches saved controls')
    child._close_properties(frame);child._close_initial(frame)
    return result


def configure(page,step):
    plan=validate(step);data=plan['payload']
    frame=_open(page,data)
    controls,before=_controls(frame)
    if before not in (data['expected_controls'],data['controls']):
        raise Stop('Parent Address controls differ from expected and desired inventories')
    if before!=data['controls']:
        def identity():
            if page.url!=data['start_url']:
                raise Stop('Parent Address editor changed during write')
            assert_tenant(page,data)
            title=frame.get_by_role('textbox',name='Form Name',exact=True)
            if title.count()!=1 or read_editor_title(title)!=data['form_name']:
                raise Stop('Parent Address form identity changed during write')
            if _children(frame)!=data['expected_children']:
                raise Stop('Parent Address children changed during write')
        current=dict(before)
        def toggle(key,value):
            identity()
            controls,observed=_controls(frame)
            if observed!=current:raise Stop('Parent Address controls changed after complete preflight')
            if 'n-switch--disabled' in (controls[key].get_attribute('class') or '').split():
                raise Stop('Native Address target switch remains disabled')
            click(controls[key])
            wait_until(lambda:_controls(frame)[1][key] is value,'Native Address switch did not change: '+key)
            current.update(_controls(frame)[1])
        # Native parent-off atomically clears and disables mandatory selection;
        # parent-on enables the dependent switch without enabling it implicitly.
        wanted=data['controls']
        if current['autocomplete']!=wanted['autocomplete']:
            toggle('autocomplete',wanted['autocomplete'])
        if current['search_required']!=wanted['search_required']:
            toggle('search_required',wanted['search_required'])
        identity()
        if _controls(frame)[1]!=wanted:raise Stop('Parent Address desired controls did not persist in editor')
        child._close_properties(frame)
        if child._inventory(frame,allow_unknown_queries=True)!=data['expected_inventory']:
            raise Stop('Parent Address write changed protected sibling inventory')
        child._close_initial(frame)
        save=frame.get_by_role('button',name='Save',exact=True)
        if save.count()!=1 or not save.is_enabled():raise Stop('Parent Address outer Save changed')
        click(save)
        if __package__:
            from .form_conditions import _wait_for_form_save
        else:
            from form_conditions import _wait_for_form_save
        _wait_for_form_save(page,save)
    else:
        child._close_properties(frame);child._close_initial(frame)
    reopen_editor(page,'form',data['form_name'],data['start_url'])
    result=_receipt(page,plan)
    return verify(page,plan,result)


def validate_receipt(result,step):
    plan=validate(step)
    if (not isinstance(result,dict) or result.get('status')!='ADDRESS_PARENT_SAVED_AND_REOPENED'
            or result.get('kind')!='address_parent' or result.get('editor_url')!=plan['payload']['start_url']
            or result.get('configuration_sha256')!=configuration_hash(plan)
            or not isinstance(result.get('controls'),dict)
            or set(result['controls'])!=FLAGS or any(type(v) is not bool for v in result['controls'].values())
            or result['controls']!=plan['payload']['controls']
            or result.get('independent_readback')!='VERIFIED'
            or result.get('behavior_verified') is not False or result.get('submission_verified') is not False):
        raise Stop('Parent Address receipt is unbound or overclaims respondent behavior')
    return {key:deepcopy(result[key]) for key in ('status','kind','editor_url','configuration_sha256','controls',
        'independent_readback','behavior_verified','submission_verified')}
