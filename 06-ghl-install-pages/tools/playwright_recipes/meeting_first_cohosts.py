"""First cohosts on the captured positive new-room form, never inferred saved emptiness.

The parent journal/lease precedes this writer. No passcode is read, authored,
returned or journaled. Candidate selection is staged before one Create click.
"""
from copy import deepcopy
import hashlib
import json
from urllib.parse import urlsplit

from playwright_recipes import meetings,meeting_cohosts as cohosts
from playwright_recipes.skill6_playwright import Stop,assert_tenant,click,fill,wait_until


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or not isinstance(inputs.get('cohosts'),dict):
        raise Stop('First cohosts require a complete approved new-room plan')
    spec=meetings.validate_room({key:value for key,value in inputs.items() if key!='cohosts'})
    configuration=inputs['cohosts']
    if (spec.get('allow_creation') is not True or 'expected_room_id' in spec
            or set(configuration)!={'expected','desired','access_change_acknowledged'}
            or configuration['expected']!=[] or configuration['access_change_acknowledged'] is not True):
        raise Stop('First cohosts require explicit new-room creation, empty initial inventory and scoped access acknowledgment')
    desired=cohosts._roster(configuration['desired'])
    if not desired:raise Stop('First-cohost creation requires at least one exact desired person')
    source=urlsplit(spec['start_url'])
    if (source.scheme!='https' or not source.hostname or source.username or source.password
            or source.query or source.fragment or not source.path.startswith('/v2/location/'+spec['location_id']+'/')):
        raise Stop('First cohosts require a credential-free same-location app start URL')
    return {**spec,'cohosts':{'expected':[],'desired':desired,'access_change_acknowledged':True}}


def configuration_hash(inputs):
    return hashlib.sha256(json.dumps(validate_inputs(inputs),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _spec(data):return {key:value for key,value in data.items() if key!='cohosts'}


def _editor(page,data):
    current=urlsplit(page.url);source=urlsplit(data['start_url'])
    if ((current.scheme,current.netloc)!=(source.scheme,source.netloc)
            or current.path!='/v2/location/'+data['location_id']+'/meetings/personal-room/new'
            or current.query or current.fragment):
        raise Stop('First cohost stage must remain on the exact positive new-room route')
    assert_tenant(page,data)
    editor=cohosts._one(page.get_by_role('region',name='Create room',exact=True),'Captured new-room form changed')
    fields=editor.get_by_role('textbox',name='Please Input',exact=True)
    if fields.count()!=3:raise Stop('Captured new-room field inventory changed')
    cohosts._one(editor.locator('#create-room-members-card'),'Captured new-room cohost card changed')
    cohosts._one(editor.locator('#create-personal-room-submit'),'Captured new-room Create control changed')
    return editor,fields


def _roster(page,data):
    editor,_=_editor(page,data)
    rows=editor.locator('#create-room-members-card').locator('.pr-members__rows > div')
    if rows.count()==0:
        # This is a positively identified UNSAVED Create form, reached only
        # after an authoritative room-absence read and causal Create click.
        # The saved-room read_roster zero-state guard is deliberately untouched.
        cohosts._one(editor.locator('#create-room-members-card').locator('.pr-members__add-trigger--link'),
                     'New-room empty roster lacks its captured Add control')
        return []
    return cohosts.read_roster(editor)


def _verify_room(page,data,room_id):
    spec=_spec(data)
    observed=meetings.validate_observation(meetings.read_room(page,spec),spec)
    if observed['room_id']!=room_id:raise Stop('Created cohost room canonical identity changed')
    detail=page.url
    click(page.get_by_text('Edit settings',exact=True))
    editor=cohosts._editor(page,{**spec,'expected_room_id':room_id})
    if not cohosts._same_roster(cohosts.read_roster(editor),data['cohosts']['desired']):
        raise Stop('Created room cohosts differ after independent persisted reopen')
    page.goto(detail,wait_until='domcontentloaded',timeout=45000)
    assert_tenant(page,data)


def validate_receipt(value,inputs):
    data=validate_inputs(inputs)
    expected={'status':'COHOSTS_CREATED_AND_REOPENED','location_id':data['location_id'],
        'configuration_sha256':configuration_hash(data),'cohost_count':len(data['cohosts']['desired']),
        'addition_count':len(data['cohosts']['desired']),'removal_count':0,
        'independent_readback':'VERIFIED','meeting_started':False,
        'functional_verified':False,'notification_behavior_verified':False}
    if (not isinstance(value,dict) or set(value)!=set(expected)|{'room_id'}
            or any(type(value[key]) is not type(item) or value[key]!=item for key,item in expected.items())):
        raise Stop('First-cohost completion is malformed or unbound')
    room=meetings.safe_room_url(value['room_id'])
    if urlsplit(room).path.rstrip('/').rsplit('/',1)[-1]!=data['slug']:
        raise Stop('First-cohost receipt room link differs from authored slug')
    return deepcopy(value)


def configure(page,inputs):
    data=validate_inputs(inputs);spec=_spec(data);source=urlsplit(data['start_url'])
    assert_tenant(page,data)
    page.goto(source.scheme+'://'+source.netloc+'/v2/location/'+data['location_id']+'/meetings/personal-room',
              wait_until='domcontentloaded',timeout=45000)
    before=meetings.read_room(page,spec)
    if (not isinstance(before,dict) or before.get('status')!='ABSENT'
            or before.get('location_id')!=data['location_id'] or not before.get('source')):
        raise Stop('First-cohost creation requires authoritative absence; existing/unknown room was not changed')
    create=page.get_by_role('region',name='Meeting Room for meetings, webinars and more',exact=True).get_by_role('button',name='Create room',exact=True)
    click(cohosts._one(create,'Native absent-room Create entry changed'))
    editor,fields=_editor(page,data)
    if _roster(page,data)!=[]:raise Stop('Positive new-room form unexpectedly contains cohosts')
    fill(fields.nth(0),data['name']);fill(fields.nth(1),data['slug']);meetings._security(editor,data)
    staged=[]
    for person in data['cohosts']['desired']:
        editor,fields=_editor(page,data)
        if not cohosts._same_roster(_roster(page,data),staged):raise Stop('New-room staged roster changed before selection')
        dialog,search=cohosts._open_directory(page,editor)
        candidate=cohosts._find_candidate(dialog,search,person)
        click(candidate);dialog.wait_for(state='hidden',timeout=45000)
        staged.append(person)
        wait_until(lambda:cohosts._same_roster(_roster(page,data),staged),
                   'First cohost did not stage its exact name/email identity')
        if page.get_by_role('dialog').count():raise Stop('Unexpected new-room cohost dialog remains; Create not attempted')
    editor,fields=_editor(page,data)
    if fields.nth(0).input_value()!=data['name'] or fields.nth(1).input_value()!=data['slug']:
        raise Stop('New-room name/slug changed before Create')
    for key,label in meetings.SECURITY.items():
        control=cohosts._one(editor.get_by_role('switch',name=label,exact=True),'New-room security changed')
        if control.get_attribute('aria-checked')!=str(data[key]).lower():raise Stop('New-room security changed before Create')
    if not cohosts._same_roster(_roster(page,data),data['cohosts']['desired']):raise Stop('New-room complete cohost roster changed before Create')
    submit=cohosts._one(editor.locator('#create-personal-room-submit'),'New-room Create control changed')
    wait_until(lambda:submit.is_enabled(),'New-room creation is invalid or room slug is unavailable')
    assert_tenant(page,data);click(submit);editor.wait_for(state='hidden',timeout=45000)
    observed=meetings.validate_observation(meetings.read_room(page,spec),spec)
    _verify_room(page,data,observed['room_id'])
    return validate_receipt({'status':'COHOSTS_CREATED_AND_REOPENED','location_id':data['location_id'],
        'room_id':observed['room_id'],'configuration_sha256':configuration_hash(data),
        'cohost_count':len(staged),'addition_count':len(staged),'removal_count':0,
        'independent_readback':'VERIFIED','meeting_started':False,
        'functional_verified':False,'notification_behavior_verified':False},data)


def verify_completed(page,inputs,receipt):
    data=validate_inputs(inputs);value=validate_receipt(receipt,data)
    source=urlsplit(data['start_url']);assert_tenant(page,data)
    page.goto(source.scheme+'://'+source.netloc+'/v2/location/'+data['location_id']+'/meetings/personal-room',
              wait_until='domcontentloaded',timeout=45000)
    _verify_room(page,data,value['room_id'])
    return value
