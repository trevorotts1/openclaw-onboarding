"""Captured existing community event -> native Live Room association.

Selecting Live Room immediately provisions a native room. This is a write even
before Update Event, so the dedicated evidence lease and intent journal precede
that selection. No event is created, post shared, invitation sent, or call started.
The host must supply a live same-session portal identity reader, never JSON proof.
"""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import sys
import time
from urllib.parse import urlsplit

if __package__:
    from . import community_portal as portal
    from .evidence_lease import evidence_lease, journal_present, read_journal
    from .skill6_playwright import Stop, click, secure_json, wait_until
else:
    import community_portal as portal
    from evidence_lease import evidence_lease, journal_present, read_journal
    from skill6_playwright import Stop, click, secure_json, wait_until

if __name__ == 'community_event_meeting':
    sys.modules.setdefault('playwright_recipes.community_event_meeting',sys.modules[__name__])
elif __name__ == 'playwright_recipes.community_event_meeting':
    sys.modules.setdefault('community_event_meeting',sys.modules[__name__])

_PROOF = object()
_TTL = 300
_JOURNAL = 'community-event-state.json'
_SCHEMA = 'skill6-community-event-room/1'
_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
_ROOM = re.compile(r'[a-f0-9]{24}')
_PENCIL = 'M2.876 18.116c.046-.414.069-.62.131-.814a2 2 0 01.234-.485c.111-.17.259-.317.553-.61L17 3a2.828 2.828 0 114 4L7.794 20.206c-.294.294-.442.442-.611.553a2 2 0 01-.485.233c-.193.063-.4.086-.814.132L2.5 21.5l.376-3.384z'
_FORM_KEYS = {'title','description','start_date','start_time','start_ampm','end_date',
    'end_time','end_ampm','timezone','recurrence','location_type','location_url',
    'hide_location','remind','hide_attendees','attendees','thumbnail_src'}
_VIEW_KEYS = {'title','date','time','description','attendee_count','fee','location_text','location_url'}
_TEXT_INPUTS = {'title':('#event-form-title','input'),
    'description':('#event-form-description','textarea'),
    'start_date':('#event-form-start-date','input'),
    'start_time':('#start-time-picker','input'),
    'end_date':('#event-form-end-date','input'),
    'end_time':('#end-time-picker','input'),
    'location_url':('#event-form-location-url','input')}
_SELECTIONS = {'start_ampm':'#event-form-start-time-ampm',
    'end_ampm':'#event-form-end-time-ampm','timezone':'#event-form-timezone',
    'recurrence':'#event-form-recurrence','location_type':'#event-form-location',
    'attendees':'#event-form-attendees'}
_FLAGS = {'hide_location':'#event-form-hide-location','remind':'#event-form-remind',
    'hide_attendees':'#event-form-hide-attendees'}
_VIEW_FIELDS = {'title':'#event-view-title','date':'#event-date-details',
    'time':'#event-time-details','description':'#event-description-value',
    'attendee_count':'#event-attendee-count','fee':'#event-entry-fee-value',
    'location_text':'#event-location-value'}


def _text(value,label,*,empty=False):
    if (not isinstance(value,str) or (not empty and not value.strip())
            or len(value)>10000 or any(ord(char)<32 and char not in '\n\r\t' for char in value)):
        raise Stop('Event '+label+' must be literal inventoried text')
    return value


def validate_inputs(inputs):
    data=portal._validate_base(inputs,portal._BASE_INPUTS|{
        'group_id','event_id','allow_room_creation','expected'})
    for key in ('group_id','event_id'):
        if not isinstance(data.get(key),str) or not _ID.fullmatch(data[key]):
            raise Stop('Existing community event requires exact '+key)
    if type(data.get('allow_room_creation')) is not bool:
        raise Stop('Native room generation requires an explicit creation choice')
    expected=data.get('expected')
    if (not isinstance(expected,Mapping) or set(expected)!={'view','form'}
            or not isinstance(expected['view'],Mapping) or set(expected['view'])!=_VIEW_KEYS
            or not isinstance(expected['form'],Mapping) or set(expected['form'])!=_FORM_KEYS):
        raise Stop('Existing event requires complete captured view/form metadata before room association')
    view,form=expected['view'],expected['form']
    for key in _VIEW_KEYS-{'location_url'}:
        _text(view[key],'view.'+key,empty=key in ('description','location_text'))
    if view['location_url'] is not None: _text(view['location_url'],'view.location_url')
    for key in _FORM_KEYS-set(_FLAGS)-{'thumbnail_src'}:
        _text(form[key],'form.'+key,empty=key in ('description','location_url'))
    if (view['title']!=form['title'] or view['description']!=form['description']
            or view['fee']!='Free' or form['recurrence'] not in ("Doesn't repeat",'Doesn’t repeat')
            or form['attendees']!='All members' or form['thumbnail_src'] is not None
            or any(type(form[key]) is not bool for key in _FLAGS)
            or form['hide_location'] is not False or form['remind'] is not False
            or form['start_ampm'] not in ('AM','PM') or form['end_ampm'] not in ('AM','PM')
            or form['location_type'] not in ('Other','Live Room')):
        raise Stop('Only the captured free nonrecurring all-member visible event without reminders/thumbnail is supported')
    if form['location_type']=='Other' and data['allow_room_creation'] is not True:
        raise Stop('Selecting Live Room provisions a room; explicit room-creation input is required')
    if form['location_type']=='Live Room': _room_id(form['location_url'],data)
    return deepcopy(data)


def configuration_hash(inputs):
    return hashlib.sha256(json.dumps(validate_inputs(inputs),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _events_url(data):
    origin,slug=portal._portal(data['portal_url'])
    return origin+'/communities/groups/'+slug+'/events'


def _room_id(url,data):
    source,slug=portal._portal(data['portal_url'])
    try: parts=urlsplit(url)
    except (TypeError,ValueError): raise Stop('Native event room link is malformed') from None
    if (parts.scheme+'://'+parts.netloc!=source or parts.query or parts.fragment
            or parts.username is not None or parts.password is not None
            or not parts.path.startswith('/meet/') or not _ROOM.fullmatch(parts.path[6:])):
        raise Stop('Native event room must be a same-portal canonical generated room link')
    return parts.path[6:]


def _one(control,message):
    if control.count()!=1 or not control.is_visible(): raise Stop(message)
    return control


def _route(page,data):
    if page.url.rstrip('/')!=_events_url(data):
        raise Stop('Community event is on another origin/group route')
    if page.get_by_placeholder('Password',exact=True).count():
        raise Stop('Community event portal authentication required')


@dataclass(frozen=True)
class EventPortalContext:
    page:object
    identity_reader:object
    location_id:str
    portal_url:str
    group_id:str
    group_name:str
    user_hash:str
    observed_at:float
    _proof:object


def _identity(page,data,reader):
    _route(page,data)
    if not callable(reader): raise Stop('Authenticated same-session event portal identity reader required')
    group=page.get_by_text(data['group_name'],exact=True)
    if not group.count() or not any(group.nth(i).is_visible() for i in range(group.count())):
        raise Stop('Expected community name is absent from the authenticated event portal')
    try: value=reader(page)
    except Exception: raise Stop('Authenticated community event identity read failed') from None
    origin,slug=portal._portal(data['portal_url'])
    if (not isinstance(value,Mapping) or value.get('authenticated') is not True
            or value.get('source_kind')!='same_session_authenticated_read'
            or value.get('location_id')!=data['location_id'] or value.get('portal_origin')!=origin
            or value.get('group_slug')!=slug or value.get('group_id')!=data['group_id']
            or value.get('group_name')!=data['group_name']
            or not isinstance(value.get('user_id'),str) or not value['user_id']):
        raise Stop('Community event location/group/current-user identity unconfirmed')
    _route(page,data)
    return hashlib.sha256(value['user_id'].encode()).hexdigest()


def capture_context(page,inputs,*,identity_reader,clock=time.time):
    data=validate_inputs(inputs)
    return EventPortalContext(page,identity_reader,data['location_id'],data['portal_url'],
        data['group_id'],data['group_name'],_identity(page,data,identity_reader),clock(),_PROOF)


def _check_context(page,data,context,clock):
    if (not isinstance(context,EventPortalContext) or context._proof is not _PROOF
            or context.page is not page or context.location_id!=data['location_id']
            or context.portal_url!=data['portal_url'] or context.group_id!=data['group_id']
            or context.group_name!=data['group_name'] or not 0<=clock()-context.observed_at<=_TTL):
        raise Stop('Fresh caller-owned authenticated event portal context required')
    if _identity(page,data,context.identity_reader)!=context.user_hash:
        raise Stop('Community event authenticated user changed')
    if not 0<=clock()-context.observed_at<=_TTL:
        raise Stop('Community event identity context expired')


def _open_view(page,data):
    _route(page,data)
    modal=page.locator('#event-view-modal')
    if modal.count()>1: raise Stop('Native event view modal is ambiguous')
    if modal.count()!=1 or not modal.is_visible():
        sidebar=page.locator('[id="events-sidebar-event-'+data['event_id']+'"]')
        sidebar.wait_for(state='visible',timeout=45000)
        _one(sidebar,'Exact existing native event sidebar identity is missing')
        click(sidebar)
        modal=page.locator('#event-view-modal')
        modal.wait_for(state='visible',timeout=45000)
    _one(modal,'Native event view modal changed')
    def bound():
        marker=modal.locator('#event-attendee-eye-icon')
        if marker.count()!=1 or not marker.is_visible(): return False
        try: analytics=json.loads(marker.get_attribute('data-analytics'))
        except (TypeError,ValueError): return False
        return (isinstance(analytics,dict) and analytics.get('event')=='event_attendees_viewed_event'
            and analytics.get('eventId')==data['event_id'] and analytics.get('groupId')==data['group_id'])
    wait_until(bound,'Native event view did not expose its exact existing event/group identity')
    return modal


def _read_view(modal):
    out={key:_one(modal.locator(selector),'Native event view '+key+' changed').inner_text().strip()
         for key,selector in _VIEW_FIELDS.items()}
    links=modal.locator('#event-location-value').locator('a')
    if links.count()>1: raise Stop('Native event location contains ambiguous links')
    out['location_url']=links.get_attribute('href') if links.count()==1 else None
    return out


def _wait_view(modal,expected,*,room_id=None):
    """Wait for a stable complete native view, never accept transient unlinked room IDs."""
    ready={}
    previous=[None]
    def settled():
        try: actual=_read_view(modal)
        except Stop: return False
        if room_id is None:
            matches=actual==expected
        else:
            matches=(all(actual[key]==expected[key] for key in _VIEW_KEYS-{'location_text'})
                and actual['location_text'] in (room_id,expected['location_url']))
        if not matches:
            previous[0]=None
            return False
        stable=previous[0]==actual
        previous[0]=actual
        if stable: ready['view']=actual
        return stable
    wait_until(settled,'Native event complete metadata/link did not settle to the inventoried state')
    return ready['view']


def _open_edit(page,modal):
    paths=modal.locator('path')
    pencils=[paths.nth(i) for i in range(paths.count()) if paths.nth(i).get_attribute('d')==_PENCIL]
    if len(pencils)!=1: raise Stop('Exact native event edit pencil identity changed')
    svg=pencils[0].locator('..')
    control=svg.locator('..')
    if (svg.evaluate('el => el.tagName.toLowerCase()')!='svg'
            or control.evaluate('el => el.tagName.toLowerCase()')!='div'):
        raise Stop('Native event edit pencil click-container changed')
    click(_one(control,'Native event edit pencil is not uniquely interactable'))
    dialog=page.get_by_role('dialog',name='Edit Event Event Payment Details',exact=True)
    dialog.wait_for(state='visible',timeout=45000)
    if _one(dialog,'Native existing-event edit dialog changed').get_attribute('id')!='event-create-modal':
        raise Stop('Native event edit dialog identity changed')
    return dialog


def _flag(control):
    _one(control,'Native event checkbox is missing or ambiguous')
    if control.get_attribute('type')=='checkbox': return control.is_checked()
    value=control.get_attribute('aria-checked')
    if control.get_attribute('role')!='checkbox' or value not in ('true','false'):
        raise Stop('Native event checkbox state is not exposed')
    return value=='true'


def _read_form(dialog):
    out={key:_one(dialog.locator(wrapper).locator(child),'Native event '+key+' input changed').input_value()
         for key,(wrapper,child) in _TEXT_INPUTS.items()}
    out.update({key:_one(dialog.locator(selector),'Native event '+key+' selection changed').inner_text().strip()
                for key,selector in _SELECTIONS.items()})
    out.update({key:_flag(dialog.locator(selector)) for key,selector in _FLAGS.items()})
    thumbnail=_one(dialog.get_by_role('button',name='Event Thumbnail',exact=True),
                   'Native event thumbnail container changed')
    upload=thumbnail.locator('#event-form-thumbnail-input')
    if (upload.count()!=1 or upload.get_attribute('type')!='file'
            or upload.get_attribute('accept')!='image/*' or upload.input_value()
            or thumbnail.locator('img').count()
            or thumbnail.get_by_text('Click or drag to upload',exact=True).count()!=1):
        raise Stop('Only the captured empty event thumbnail state can be preserved')
    out['thumbnail_src']=None
    return out


def _wait_generated_room(dialog,data):
    # The selection label can hydrate before the asynchronous room URL. The
    # previous Other link being nonempty is not a generated-room observation.
    ready={}
    previous=[None]
    def generated():
        try:
            current=_read_form(dialog)
            if current['location_type']!='Live Room': return False
            _room_id(current['location_url'],data)
            control=dialog.locator('#event-form-location-url').locator('input')
            if control.count()!=1 or control.is_enabled(): return False
        except Stop:
            previous[0]=None
            return False
        stable=previous[0]==current
        previous[0]=current
        if stable: ready['form']=current
        return stable
    wait_until(generated,'Native event generated room link did not settle to its canonical read-only state')
    return ready['form']


def _next(dialog):
    control=_one(dialog.get_by_role('button',name='Next',exact=True),'Native event Next control changed')
    if control.get_attribute('id')!='event-form-submit-btn': raise Stop('Native event Next identity changed')
    click(control)


def _read_fee(dialog):
    free=_one(dialog.get_by_role('radio',name='Free No payment required',exact=True),
              'Native event Free fee control changed')
    radios=dialog.get_by_role('radio')
    if radios.count()!=2 or not free.is_checked() or sum(radios.nth(i).is_checked() for i in range(2))!=1:
        raise Stop('Only the captured existing Free event payment state is supported')
    price=_one(dialog.get_by_placeholder('0',exact=True),'Native event price input changed')
    mode=_one(dialog.get_by_role('switch'),'Native event payment Test Mode changed')
    if price.is_enabled() or price.input_value() not in ('','0') or mode.is_enabled():
        raise Stop('Native Free event price/test-mode protection changed')
    _one(dialog.get_by_text('USD',exact=True),'Native event currency is not the captured USD state')
    _one(dialog.get_by_role('button',name='Update Event',exact=True),'Native existing-event Update control changed')
    return {'free':True,'price':price.input_value(),'currency':'USD',
        'test_mode':mode.get_attribute('aria-checked'),'test_mode_disabled':True}


def _back(dialog):
    click(_one(dialog.get_by_role('button',name='Back',exact=True),'Native event payment Back control changed'))


def _receipt(data,room_id,*,changed):
    return {'status':'NEEDS_VERIFICATION','location_id':data['location_id'],
        'event_id':data['event_id'],'group_id':data['group_id'],'room_id':room_id,
        'configuration_sha256':configuration_hash(data),'independent_readback':'VERIFIED',
        'room_link_saved':True,'room_creation_attempted':changed,'event_created':False,
        'announcement_attempted':False,'email_reminders_enabled':False,'payment_changed':False,
        'meeting_started':False,'functional_verified':False,'notification_behavior_verified':False,
        'reused':not changed,'verification_required':True}


def _replay(path,data):
    old=read_journal(path)
    if (not isinstance(old,Mapping) or old.get('schema')!=_SCHEMA
            or old.get('configuration_sha256')!=configuration_hash(data)
            or old.get('location_id')!=data['location_id'] or old.get('event_id')!=data['event_id']
            or old.get('group_id')!=data['group_id'] or old.get('status')!='NEEDS_VERIFICATION'):
        raise Stop('Event room journal is interrupted or unbound; reconcile before another write')
    raw=old.get('outcome')
    if not isinstance(raw,Mapping) or type(raw.get('reused')) is not bool or not isinstance(raw.get('room_id'),str) or not _ROOM.fullmatch(raw['room_id']):
        raise Stop('Saved event room receipt is malformed')
    changed=data['expected']['form']['location_type']!='Live Room'
    if raw['reused'] != (not changed): raise Stop('Saved event room receipt has contradictory creation state')
    if not changed and raw['room_id']!=_room_id(data['expected']['form']['location_url'],data):
        raise Stop('Saved event room receipt identifies a different reused room')
    expected=_receipt(data,raw['room_id'],changed=changed)
    if any(not portal._same_value(raw.get(key),value) for key,value in expected.items()):
        raise Stop('Saved event room receipt differs from the exact completed operation')
    return {**expected,'replayed':True}


def run_event(page,inputs,evidence_root,*,portal_context,clock=time.time):
    data=validate_inputs(inputs)
    root=Path(evidence_root).resolve()
    with evidence_lease(root,data['location_id'],kind='community_event'):
        path=root/_JOURNAL
        if journal_present(path):
            result=_replay(path,data)
            _check_context(page,data,portal_context,clock)
            return result
        _check_context(page,data,portal_context,clock)
        view=_open_view(page,data)
        _wait_view(view,data['expected']['view'])
        dialog=_open_edit(page,view)
        before=_read_form(dialog)
        if before!=data['expected']['form']:
            raise Stop('Existing event edit metadata differs from the complete expected state')
        _next(dialog)
        fee=_read_fee(dialog)
        _back(dialog)
        if _read_form(dialog)!=before: raise Stop('Event metadata changed during payment preflight')
        _check_context(page,data,portal_context,clock)
        state={'schema':_SCHEMA,'configuration_sha256':configuration_hash(data),
            'location_id':data['location_id'],'event_id':data['event_id'],'group_id':data['group_id'],
            'status':'INTENT_RECORDED'}
        secure_json(path,state)
        changed=before['location_type']!='Live Room'
        try:
            if changed:
                click(_one(dialog.locator('#event-form-location'),'Native event location selector changed'))
                option=_one(page.get_by_role('option',name='Live Room',exact=True),
                            'Native Live Room event location option changed')
                if not option.is_enabled() or option.get_attribute('aria-disabled')=='true':
                    raise Stop('Native Live Room is unavailable for this event')
                _check_context(page,data,portal_context,clock)
                state.update(status='ROOM_GENERATION_INTENT_RECORDED')
                secure_json(path,state)
                click(option)
                _wait_generated_room(dialog,data)
            staged=_read_form(dialog)
            url_control=dialog.locator('#event-form-location-url').locator('input')
            if url_control.is_enabled(): raise Stop('Generated native Live Room link must be disabled/read-only')
            room_id=_room_id(staged['location_url'],data)
            desired={**before,'location_type':'Live Room','location_url':staged['location_url']}
            if staged!=desired: raise Stop('Native room selection changed protected event metadata')
            if changed:
                _next(dialog)
                if _read_fee(dialog)!=fee: raise Stop('Native room selection changed event payment metadata')
                _back(dialog)
                if _read_form(dialog)!=desired: raise Stop('Native event room/copy changed before Update Event')
                _next(dialog)
                if _read_fee(dialog)!=fee: raise Stop('Native event payment metadata changed before Update')
                _check_context(page,data,portal_context,clock)
                state.update(status='EVENT_UPDATE_INTENT_RECORDED',room_id=room_id)
                secure_json(path,state)
                click(_one(dialog.get_by_role('button',name='Update Event',exact=True),
                           'Native existing-event update action changed'))
                dialog.wait_for(state='hidden',timeout=45000)
            else:
                page.keyboard.press('Escape')
                dialog.wait_for(state='hidden',timeout=45000)
            page.reload(wait_until='domcontentloaded',timeout=45000)
            _check_context(page,data,portal_context,clock)
            reopened=_open_view(page,data)
            expected_view={**data['expected']['view'],'location_url':desired['location_url']}
            _wait_view(reopened,expected_view,room_id=room_id)
            reopened_dialog=_open_edit(page,reopened)
            if _read_form(reopened_dialog)!=desired: raise Stop('Saved event form or protected metadata changed after independent reopen')
            _next(reopened_dialog)
            if _read_fee(reopened_dialog)!=fee: raise Stop('Saved event payment metadata changed after independent reopen')
            page.keyboard.press('Escape')
            reopened_dialog.wait_for(state='hidden',timeout=45000)
            _check_context(page,data,portal_context,clock)
            outcome=_receipt(data,room_id,changed=changed)
            state.update(status='NEEDS_VERIFICATION',outcome=outcome)
            secure_json(path,state)
            return outcome
        except Exception as exc:
            state.update(status='RECONCILIATION_REQUIRED',error_type=type(exc).__name__)
            secure_json(path,state)
            raise
