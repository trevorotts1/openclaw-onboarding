"""Launch a user-owned video-provider OAuth flow without accepting consent.

HighLevel requires provider sign-in/authorization from the owning staff member.
This adapter switches only the Connections view to the API-unique staff record,
opens the documented provider Connect action, and returns a pending handoff.
It never reads credentials, submits consent, or claims the provider connected.

Official flows:
https://help.gohighlevel.com/support/solutions/articles/155000002372
https://help.gohighlevel.com/support/solutions/articles/155000003443
https://ideas.gohighlevel.com/changelog/simplified-google-calendar-connection-with-google-descope
"""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click, wait_until
else:
    from skill6_playwright import Stop, assert_tenant, click, wait_until

_ID=re.compile(r'[A-Za-z0-9_-]{1,128}')
_PROVIDERS=frozenset(('Zoom','Microsoft Teams','Google Calendar'))


def validate_inputs(inputs,*,require_fresh=True):
    keys={'location_id','location_name','start_url','staff_id','staff_name','provider','staff_dependency'}
    if not isinstance(inputs,dict) or set(inputs)!=keys:
        raise Stop('Provider OAuth handoff requires exact location, provider, and staff identity inputs')
    data=deepcopy(inputs)
    for key in ('location_id','staff_id'):
        if not isinstance(data[key],str) or not _ID.fullmatch(data[key]):
            raise Stop('Provider OAuth handoff requires an exact inventoried '+key)
    for key in ('location_name','staff_name'):
        if not isinstance(data[key],str) or not data[key] or data[key]!=data[key].strip() or len(data[key])>512:
            raise Stop('Provider OAuth handoff requires exact inventoried '+key)
    if not isinstance(data['provider'],str) or data['provider'] not in _PROVIDERS:
        raise Stop('Provider OAuth handoff supports only the documented Zoom, Microsoft Teams, and Google Calendar Connect options')
    try:
        route=urlsplit(data['start_url']); port=route.port
    except (TypeError,ValueError):
        raise Stop('Provider OAuth handoff calendar-settings URL is malformed') from None
    if (route.scheme!='https' or not route.hostname or route.username or route.password
            or port not in (None,443) or route.fragment
            or route.path!='/v2/location/'+data['location_id']+'/settings/calendars'
            or route.query!='section=calendars'):
        raise Stop('Provider OAuth handoff requires the exact observed same-location calendar-settings route')
    receipt=data['staff_dependency']
    if (not isinstance(receipt,dict)
            or set(receipt)!={'status','provider','location_id','observed_at','operation','http_status','users','complete','total_count'}
            or receipt['status']!='VERIFIED' or receipt['location_id']!=data['location_id']
            or receipt['provider'] not in ('skill44','public_api','official_mcp')
            or receipt['operation']!='users.search' or type(receipt['http_status']) is not int
            or receipt['http_status']!=200 or type(receipt['observed_at']) not in (int,float)
            or not math.isfinite(receipt['observed_at'])):
        raise Stop('Provider OAuth staff selector requires a verified same-location user inventory')
    if require_fresh and not 0<=__import__('time').time()-receipt['observed_at']<=3600:
        raise Stop('Provider OAuth staff inventory must be fresh')
    users=receipt['users']
    if (receipt['complete'] is not True or type(receipt['total_count']) is not int
            or not isinstance(users,list) or not users or receipt['total_count']!=len(users)):
        raise Stop('Provider OAuth staff selector requires the complete same-location user roster')
    by_id={}
    for user in users:
        if (not isinstance(user,dict) or set(user)!={'id','name','roles'}
                or not isinstance(user['id'],str) or not _ID.fullmatch(user['id']) or user['id'] in by_id
                or not isinstance(user['roles'],dict) or set(user['roles'])!={'locationIds'}
                or not isinstance(user['roles']['locationIds'],list)
                or data['location_id'] not in user['roles']['locationIds']):
            raise Stop('Provider OAuth roster contains a duplicate or cross-location user')
        if (not isinstance(user['name'],str) or not user['name'] or user['name']!=user['name'].strip()
                or any(not isinstance(value,str) or not _ID.fullmatch(value) for value in user['roles']['locationIds'])):
            raise Stop('Provider OAuth roster contains malformed identity data')
        by_id[user['id']]=user
    target=by_id.get(data['staff_id'])
    exact=[user for user in users if user['name'].casefold()==data['staff_name'].casefold()]
    if (target is None or target['name']!=data['staff_name'] or len(exact)!=1
            or exact[0]['id']!=data['staff_id']):
        raise Stop('Provider OAuth staff identity is not unique in the same-location API roster')
    return data


def configuration_hash(inputs):
    data=validate_inputs(inputs,require_fresh=False)
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _one(control,message):
    if control.count()!=1 or not control.is_visible(): raise Stop(message)
    return control


def _provider_cards(cards,provider):
    matches=[]
    for index in range(cards.count()):
        card=cards.nth(index)
        if card.is_visible() and provider in {line.strip() for line in card.inner_text().splitlines()}:
            matches.append(card)
    return matches


def _target_label(page,data):
    options=[]
    for label in (data['staff_name'],data['staff_name']+' (Me)',data['staff_name']+'(Me)'):
        candidate=page.get_by_role('option',name=label,exact=True)
        if candidate.count()==1 and candidate.is_visible(): options.append((label,candidate))
    if len(options)!=1:
        raise Stop('API-unique provider owner does not match one visible native Connections staff option')
    return options[0]


def _select_staff(page,data):
    selector=_one(page.get_by_role('combobox'),'Connections staff selector is missing or ambiguous')
    label=selector.get_attribute('aria-label')
    if label in (data['staff_name'],data['staff_name']+' (Me)',data['staff_name']+'(Me)'):
        return selector
    click(selector)
    exact_label,option=_target_label(page,data)
    click(option)
    wait_until(lambda:selector.get_attribute('aria-label')==exact_label,
        'Connections staff selector did not switch to the API-unique provider owner')
    return selector


def _at(page,data,*,connections=True):
    source=urlsplit(data['start_url']); current=urlsplit(page.url)
    expected=('/v2/location/'+data['location_id']+'/settings/calendars/connections-new' if connections
              else '/v2/location/'+data['location_id']+'/settings/calendars')
    query='' if connections else 'section=calendars'
    if ((current.scheme,current.netloc)!=(source.scheme,source.netloc)
            or current.path!=expected or current.query!=query or current.fragment):
        raise Stop('Provider OAuth page left the exact same-location Connections route')
    assert_tenant(page,data)


def launch_oauth_handoff(page,inputs):
    """Open the documented provider Connect popup and stop before auth/consent."""
    data=validate_inputs(inputs)
    source=urlsplit(data['start_url'])
    path='/v2/location/'+data['location_id']+'/settings/calendars/connections-new'
    page.goto(source.scheme+'://'+source.netloc+path,wait_until='domcontentloaded',timeout=45000)
    _at(page,data)
    tab=_one(page.get_by_role('tab',name='Video conferencing',exact=True),
             'Native Video conferencing tab is missing or ambiguous')
    click(tab)
    panel=_one(page.get_by_role('tabpanel',name='Video conferencing',exact=True),
               'Native Video conferencing panel is missing or ambiguous')
    _select_staff(page,data)
    cards=panel.locator('.calendars-account-details-card-container')
    if _provider_cards(cards,data['provider']):
        raise Stop('Requested provider already has a connection card; reconcile that account before launching another OAuth handoff')
    add_candidates=[panel.get_by_role('button',name=label,exact=True)
                    for label in ('Add New','+ Add New')]
    add_matches=[candidate for candidate in add_candidates if candidate.count()==1 and candidate.is_visible()]
    if len(add_matches)!=1:
        raise Stop('Native Add New video provider action is missing or ambiguous')
    add=add_matches[0]
    click(add)
    provider_text=_one(page.get_by_text(data['provider'],exact=True),
                       'Requested exact provider is not present in the native Add New choices')
    if not provider_text.is_enabled():
        raise Stop('Requested provider is unavailable in the native Add New choices')
    click(provider_text)
    matches=_provider_cards(page.locator('.calendars-account-details-card-container'),data['provider'])
    if len(matches)!=1:
        raise Stop('Selected provider card is not uniquely identified after Add New')
    card=matches[0]
    connect=_one(card.get_by_role('button',name='Connect',exact=True),
                 'Selected provider card does not expose one exact Connect action')
    before=set(page.context.pages)
    click(connect)
    wait_until(lambda:len(set(page.context.pages)-before)==1,
               'Provider Connect did not launch exactly one OAuth popup')
    popups=list(set(page.context.pages)-before)
    popup=popups[0]
    if popup.is_closed(): raise Stop('Provider Connect popup closed before authorization was presented')
    popup.wait_for_load_state('domcontentloaded',timeout=45000)
    destination=urlsplit(popup.url)
    if (destination.scheme!='https' or not destination.hostname
            or destination.hostname.casefold()==source.hostname.casefold()
            or destination.username or destination.password):
        raise Stop('Provider Connect popup did not reach a separate HTTPS authorization origin')
    _at(page,data)
    return {'status':'PENDING_USER_AUTHORIZATION','location_id':data['location_id'],
        'staff_id':data['staff_id'],'provider':data['provider'],
        'configuration_sha256':configuration_hash(data),'oauth_popup_opened':True,
        'authorization_completed':False,'consent_submitted':False,
        'connection_verified':False,'popup_origin_sha256':hashlib.sha256(
            (destination.scheme+'://'+destination.netloc).encode()).hexdigest()}
