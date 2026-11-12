"""Captured modern Channel creation with explicit private/read-only flags."""
from copy import deepcopy
from pathlib import Path
from collections.abc import Mapping
import hashlib
import json
import re
from urllib.parse import urlsplit

from playwright_recipes import community_portal as portal
from playwright_recipes.evidence_lease import read_journal
from playwright_recipes.skill6_playwright import Stop, click, fill, secure_json, wait_until

ENTRY='#communities-sidebar-create-channel-button'
MODAL='#channels-create-modal'

_ICON_EVIDENCE=json.loads(Path(__file__).with_name('community_channel_icons.json').read_text())
if (not isinstance(_ICON_EVIDENCE,dict) or _ICON_EVIDENCE.get('schema')!='skill6-community-channel-icons/1'
        or not isinstance(_ICON_EVIDENCE.get('icons'),list)):
    raise RuntimeError('Captured community channel icon evidence is invalid')
_ICON_CATALOG={row['icon']:tuple(row['paths']) for row in _ICON_EVIDENCE['icons']
    if isinstance(row,dict) and isinstance(row.get('icon'),str) and isinstance(row.get('paths'),list)}
if len(_ICON_CATALOG)!=len(_ICON_EVIDENCE['icons']) or len({value for value in _ICON_CATALOG.values()})!=len(_ICON_CATALOG):
    raise RuntimeError('Captured community channel icon catalog is ambiguous')


def _one(node,message):
    if node.count()!=1 or not node.is_visible():raise Stop(message)
    return node


def available(page):
    locator=getattr(page,'locator',None)
    if not callable(locator):return False
    node=locator(ENTRY)
    if node.count()>1:raise Stop('Modern channel entry is ambiguous')
    return node.count()==1 and node.is_visible()


def entry(page):return _one(page.locator(ENTRY),'Modern Create Channel entry changed')


def _inventory(page,data):
    _,slug=portal._portal(data['portal_url'])
    sidebar=_one(page.get_by_role('complementary').filter(
        has=page.get_by_role('button',name=data['group_name'],exact=True)),
        'Modern exact-group channel sidebar is ambiguous')
    channels=_one(sidebar.get_by_role('button',name='Channels',exact=True),'Modern Channels header changed')
    expanded=channels.get_attribute('aria-expanded')
    if expanded not in ('true','false'):raise Stop('Modern channel-list expanded state is unavailable')
    if expanded=='false':
        click(channels);wait_until(lambda:channels.get_attribute('aria-expanded')=='true','Modern channel list did not expand')
    prefix='/communities/groups/'+slug+'/channels/'
    links=sidebar.locator('a[href^="'+prefix+'"]');rows=[];names=set();hrefs=set()
    for i in range(links.count()):
        link=links.nth(i);href=link.get_attribute('href');name=link.inner_text().strip()
        if (not name or not isinstance(href,str) or not re.fullmatch(re.escape(prefix)+r'[A-Za-z0-9_-]+',href)
                or name.casefold() in names or href in hrefs):
            raise Stop('Modern channel names or native href identities are missing or ambiguous')
        names.add(name.casefold());hrefs.add(href);rows.append({'name':name,'href':href})
    return rows


def _section_inventory(page,data):
    sidebar=_one(page.get_by_role('complementary').filter(
        has=page.get_by_role('button',name=data['group_name'],exact=True)),
        'Modern exact-group section sidebar is ambiguous')
    toggles=sidebar.locator('div[id^="channel-sections-toggle-"][role="button"]')
    rows=[];names=set();ids=set()
    for index in range(toggles.count()):
        toggle=toggles.nth(index);identity=toggle.get_attribute('id')
        if not isinstance(identity,str) or not re.fullmatch(r'channel-sections-toggle-[A-Za-z0-9_-]+',identity):
            raise Stop('Modern section header identity is unavailable')
        row=sidebar.locator('div.group.flex.items-center.gap-1.w-full').filter(has=toggle)
        if row.count()!=1:raise Stop('Modern section header owner changed')
        name=toggle.inner_text().strip();expanded=toggle.get_attribute('aria-expanded')
        # The settings id contains the same opaque suffix as the visible
        # section header; preserve embedded dashes in that identity.
        suffix=identity.removeprefix('channel-sections-toggle-')
        settings=row.locator('button[id="channel-sections-settings-'+suffix+'"][aria-label="Open section settings"]')
        icon_owner=toggle.locator('#channel-icon-unknown-container')
        paths=icon_owner.locator('path')
        signature=tuple((paths.nth(i).get_attribute('d') or '') for i in range(paths.count()))
        icon_matches=[name for name,path_signature in _ICON_CATALOG.items() if path_signature==signature]
        if (not name or name.casefold() in names or identity in ids or expanded not in ('true','false')
                or settings.count()!=1 or not settings.is_visible() or len(icon_matches)!=1):
            raise Stop('Modern section native name/icon/owner metadata is ambiguous')
        names.add(name.casefold());ids.add(identity)
        rows.append({'name':name,'id':identity,'expanded':expanded,'icon':icon_matches[0]})
    return rows


def _expected_metadata(channel):
    private=channel.get('private',False)
    return {'name':channel['name'],'description':channel['description'],
        'icon':channel.get('icon','Hash02Icon'),'private':private,
        'private_visibility':channel.get('private_visibility','hidden') if private else None,
        'read_only':channel.get('read_only',False)}


def _route_identity(page,data,context,clock,href):
    origin,slug=portal._portal(data['portal_url'])
    expected=origin+href
    if (not isinstance(context,portal.PortalContext) or context._proof is not portal._PROOF
            or context.page is not page or context.location_id!=data['location_id']
            or context.portal_url.rstrip('/')!=data['portal_url'].rstrip('/')
            or context.group_name!=data['group_name']
            or not 0<=clock()-context.observed_at<=portal._CONTEXT_TTL
            or page.url.rstrip('/')!=expected):
        raise Stop('Fresh exact same-session community channel context required')
    if page.get_by_placeholder('Password',exact=True).count():
        raise Stop('Community portal authentication required')
    try:actual=context.identity_reader(page)
    except Exception:raise Stop('Community channel authenticated identity read failed') from None
    if (not isinstance(actual,Mapping) or actual.get('authenticated') is not True
            or actual.get('location_id')!=data['location_id'] or actual.get('portal_origin')!=origin
            or actual.get('group_slug')!=slug or actual.get('group_name')!=data['group_name']
            or not isinstance(actual.get('user_id'),str) or not actual['user_id']
            or hashlib.sha256(actual['user_id'].encode()).hexdigest()!=context.user_hash
            or actual.get('source_kind')!='same_session_authenticated_read'):
        raise Stop('Community channel account/user/location/group identity changed')
    return actual


def _read_channel_metadata(page,data,context,clock,row):
    """Read the captured About → Channel Details Edit form, then close without save."""
    channel_slug=row['href'].rsplit('/',1)[-1]
    if not re.fullmatch(r'[A-Za-z0-9_-]+',channel_slug):
        raise Stop('Native channel settings identity is malformed')
    origin,_=portal._portal(data['portal_url'])
    page.goto(origin+row['href'],wait_until='domcontentloaded',timeout=45000)
    page.wait_for_load_state('networkidle',timeout=45000)
    _route_identity(page,data,context,clock,row['href'])
    trigger=_one(page.locator('#channel-settings-'+channel_slug),
        'Native channel settings trigger changed')
    click(trigger)
    modal=page.locator('#channels-settings-modal')
    modal.wait_for(state='visible',timeout=45000);_one(modal,'Native channel settings dialog changed')
    details=_one(modal.get_by_text('Channel Details',exact=True),
        'Native Channel Details panel changed')
    edits=modal.get_by_text('Edit',exact=True)
    if edits.count()!=2 or not edits.nth(0).is_visible():
        raise Stop('Native Channel Details Edit action is ambiguous')
    click(edits.nth(0))
    form=_one(modal.locator('#channels-create-form'),'Native Edit Channel form changed')
    name=_one(form.locator('#channels-create-name-input input'),'Native channel name field changed').input_value()
    icon=_one(form.locator('#channels-create-icon-field input'),'Native channel icon field changed').input_value()
    description=_one(form.locator('#channels-create-description-input textarea'),
        'Native channel description field changed').input_value()
    private=_one(form.locator('#channels-create-private-toggle-switch'),
        'Native private channel switch changed').get_attribute('aria-checked')
    readonly=_one(form.locator('#channels-create-readonly-toggle-switch'),
        'Native read-only channel switch changed').get_attribute('aria-checked')
    if private not in ('true','false') or readonly not in ('true','false'):
        raise Stop('Native channel access values are unreadable')
    is_private=private=='true';private_visibility=None
    if is_private:
        states=[]
        for mode in ('visible','hidden'):
            radio=form.locator('#channels-create-discoverable-'+mode+'-radio-card input[type="radio"]')
            if radio.count()!=1:raise Stop('Native private channel visibility radio changed')
            states.append((mode,radio.is_checked()))
        selected=[mode for mode,checked in states if checked]
        if len(selected)!=1:raise Stop('Native private channel visibility is ambiguous')
        private_visibility=selected[0]
    close=_one(modal.locator('button#hr-modal__close-button'),'Native channel details Close changed')
    actual={'name':name,'description':description,'icon':icon,'private':is_private,
        'private_visibility':private_visibility,'read_only':readonly=='true'}
    click(close);modal.wait_for(state='hidden',timeout=45000)
    return actual


def _select_icon(page,modal,field,icon_name,*,trigger_selector='#channels-create-icon-field-trigger'):
    expected=_ICON_CATALOG.get(icon_name)
    if expected is None:raise Stop('Requested channel icon is outside the captured native icon catalog')
    click(_one(modal.locator(trigger_selector),
        'Modern channel icon picker trigger changed'))
    tab=_one(modal.get_by_role('tab',name='Icons',exact=True),
        'Modern icon picker Icons tab changed')
    click(tab)
    panel=_one(modal.get_by_role('tabpanel',name='Icons',exact=True),
        'Modern icon picker Icons panel changed')
    buttons=panel.get_by_role('button',name='Select Icon',exact=True)
    matches=[]
    for index in range(buttons.count()):
        button=buttons.nth(index)
        if not button.is_visible():continue
        paths=button.locator('svg path')
        signature=tuple((paths.nth(i).get_attribute('d') or '') for i in range(paths.count()))
        if signature==expected:matches.append(button)
    if len(matches)!=1:
        raise Stop('Requested native icon path signature is missing or ambiguous')
    click(matches[0])
    wait_until(lambda:field.input_value()==icon_name,
        'Modern icon picker did not select the exact authored native icon value')


def _create_section(page,data,context,clock,section):
    """Author one captured Section with its exact name and catalog icon."""
    portal._check_context(page,data,context,clock=clock)
    click(entry(page))
    modal=_one(page.locator(MODAL),'Modern Create Section modal changed')
    channel=modal.locator('#channels-create-channel-radio-card input[type="radio"]')
    section_mode=modal.locator('#channels-create-section-radio-card input[type="radio"]')
    if channel.count()!=1 or section_mode.count()!=1:
        raise Stop('Modern Section/Channel mode controls changed')
    if section_mode.is_checked() is not True:
        card=_one(modal.locator('#channels-create-section-radio-card'),
            'Modern Section mode card changed')
        click(card)
        wait_until(lambda:section_mode.is_checked(),'Modern Section mode did not select')
    if channel.is_checked() or not section_mode.is_checked():
        raise Stop('Modern creation is outside the captured Section mode')
    form=_one(modal.locator('#channel-sections-create-form'),'Modern Create Section form changed')
    name=_one(form.locator('#channel-sections-create-name-input input'),
        'Modern section name field changed')
    icon=_one(form.locator('#channel-sections-create-icon-field input'),
        'Modern section icon field changed')
    wanted_icon=section.get('icon','Hash02Icon')
    if wanted_icon!='Hash02Icon':
        _select_icon(page,modal,icon,wanted_icon,
            trigger_selector='#channel-sections-create-icon-field-trigger')
    name_value=section['name']
    fill(name,name_value)
    if name.input_value()!=name_value or icon.input_value()!=wanted_icon:
        raise Stop('Modern Section native name/icon fields differ from the authored values')
    submit=_one(modal.locator('#channel-sections-create-submit-button'),
        'Modern Create Section submit changed')
    if submit.inner_text().strip()!='Create Section' or not submit.is_enabled():
        raise Stop('Modern Create Section action is unavailable')
    portal._check_context(page,data,context,clock=clock,verify_control=False)
    click(submit)
    modal.wait_for(state='hidden',timeout=45000)
    page.wait_for_load_state('networkidle',timeout=45000)


def _defaults(modal,channel=None):
    channel=channel or {}
    for mode,expected in (('channel',True),('section',False)):
        radio=modal.locator('#channels-create-'+mode+'-radio-card input[type="radio"]')
        if radio.count()!=1 or radio.is_checked() is not expected:
            raise Stop('Modern channel creation is outside the captured ordinary Channel mode')
    icon=_one(modal.locator('#channels-create-icon-field input'),'Modern default channel icon changed')
    if icon.input_value()!=channel.get('icon','Hash02Icon'):
        raise Stop('Modern default icon/custom icon differs from its authored native value')
    if modal.get_by_role('switch').count()!=2:raise Stop('Modern channel mode switches changed')
    for key,field in (('private','private'),('readonly','read_only')):
        toggle=_one(modal.locator('#channels-create-'+key+'-toggle-switch'),'Modern channel access toggle changed')
        expected='true' if channel.get(field,False) else 'false'
        if toggle.get_attribute('role')!='switch' or toggle.get_attribute('aria-checked')!=expected:
            raise Stop('Modern channel private/read-only access differs from its authored state')
    if channel.get('private',False):
        discoverable=channel.get('private_visibility','hidden')
        for mode in ('visible','hidden'):
            radio=modal.locator('#channels-create-discoverable-'+mode+'-radio-card input[type="radio"]')
            if radio.count()!=1 or radio.is_checked()!=(mode==discoverable):
                raise Stop('Modern private channel discoverability differs from its authored state')


def _create(page,data,context,clock,channel):
    portal._check_context(page,data,context,clock=clock)
    click(entry(page));modal=page.locator(MODAL);modal.wait_for(state='visible',timeout=45000)
    _one(modal,'Modern channel modal is ambiguous');_defaults(modal)
    name=_one(modal.locator('#channels-create-name-input input'),'Modern channel name input changed')
    icon=_one(modal.locator('#channels-create-icon-field input'),'Modern channel icon input changed')
    description=_one(modal.locator('#channels-create-description-input textarea'),'Modern channel description input changed')
    fill(name,channel['name']);fill(description,channel['description'])
    for key,field in (('private','private'),('readonly','read_only')):
        toggle=_one(modal.locator('#channels-create-'+key+'-toggle-switch'),'Modern channel access toggle changed')
        expected='true' if channel.get(field,False) else 'false'
        if toggle.get_attribute('aria-checked')!=expected:
            if toggle.get_attribute('aria-disabled')!='false':raise Stop('Modern requested channel access toggle is disabled')
            click(toggle)
            wait_until(lambda:toggle.get_attribute('aria-checked')==expected,'Modern channel access toggle did not settle')
    # The picker is scoped to its captured field owner. Selection is by the
    # exact accessible option name supplied by the authored profile, then
    # independently bound to the native field value.
    desired_icon=channel.get('icon','Hash02Icon')
    if desired_icon!='Hash02Icon':
        _select_icon(page,modal,icon,desired_icon)
    _defaults(modal,channel)
    if name.input_value()!=channel['name'] or description.input_value()!=channel['description']:
        raise Stop('Modern channel creation ignored the authored text')
    portal._check_context(page,data,context,clock=clock,verify_control=False)
    submit=_one(modal.locator('#channels-create-submit-button'),'Modern Create Channel submit changed')
    wait_until(lambda:submit.is_enabled(),'Modern ordinary channel inputs were not accepted')
    if channel.get('private',False):
        step=modal.locator('#channels-create-step-indicator')
        if submit.inner_text().strip()!='Continue' or step.count()!=1 or step.inner_text().strip()!='Step 1/2':
            raise Stop('Modern private channel Step 1 transition changed')
        click(submit)
        wait_until(lambda:step.inner_text().strip()=='Step 2/2',
            'Modern private channel Step 2 did not open')
        payment=modal.locator('#channel-payment-setup-type-free-radio input[type="radio"]')
        empty=modal.locator('#channel-payment-setup-free-empty-state')
        if (payment.count()!=1 or not payment.is_checked() or empty.count()!=1 or not empty.is_visible()
                or empty.locator('#channel-payment-setup-free-empty-title').inner_text().strip()
                !='No pricing options available for free channel'):
            raise Stop('Modern private channel requires the captured Free/no-charge setup')
        submit=_one(modal.locator('#channels-create-submit-button'),'Modern private Create Channel submit changed')
        if submit.inner_text().strip()!='Create Channel' or not submit.is_enabled():
            raise Stop('Modern private channel free setup is not ready to create')
        portal._check_context(page,data,context,clock=clock,verify_control=False)
        click(submit);modal.wait_for(state='hidden',timeout=45000)
        page.wait_for_load_state('networkidle',timeout=45000)
        return
    click(submit);modal.wait_for(state='hidden',timeout=45000)
    page.wait_for_load_state('networkidle',timeout=45000)


def _home(page,data,context,clock):
    if page.url.rstrip('/')!=data['portal_url'].rstrip('/'):
        page.goto(data['portal_url'],wait_until='domcontentloaded',timeout=45000)
    else:page.reload(wait_until='domcontentloaded',timeout=45000)
    page.wait_for_load_state('networkidle',timeout=45000)
    portal._check_context(page,data,context,clock=clock)


def run_owned(page,data,root,context,clock):
    """Caller holds the existing channel runner/provider evidence locks."""
    for channel in data['channels']:
        if (len(channel['description'])>500 or channel['name']!=channel['name'].strip()
                or any(ord(c)<32 for c in channel['name'])):
            raise Stop('Modern channel text differs from its captured authored profile')
        if channel.get('icon','Hash02Icon') not in _ICON_CATALOG:
            raise Stop('Modern channel icon is outside the captured native icon catalog')
    for section in data.get('sections',[]):
        if section.get('icon','Hash02Icon') not in _ICON_CATALOG:
            raise Stop('Modern section icon is outside the captured native icon catalog')
    path=Path(root)/'community-portal-state.json'
    fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    _,slug=portal._portal(data['portal_url'])
    expected_channels=[{'name_sha256':hashlib.sha256(channel['name'].encode()).hexdigest(),
        'name_seen_after_reload':True,'description_verified':True,'access_verified':True,
        'icon_verified':True} for channel in data['channels']]
    expected_sections=[{'name_sha256':hashlib.sha256(section['name'].encode()).hexdigest(),
        'name_seen_after_reload':True,'icon':section.get('icon','Hash02Icon'),
        'icon_verified':True} for section in data.get('sections',[])]
    expected_outcome={'status':'NEEDS_VERIFICATION','location_id':data['location_id'],
        'objects':[{'kind':'community','id':slug}],'channel_count':len(data['channels']),
        'section_count':len(data.get('sections',[])),
        'channel_names_seen_after_reload':bool(data['channels']),
        'description_verified':bool(data['channels']),'access_verified':bool(data['channels']),
        'icon_verified':bool(data['channels']),
        'section_names_seen_after_reload':bool(data.get('sections',[])),
        'section_icons_verified':bool(data.get('sections',[])),'behavior_verified':False,
        'verification_required':True,'identity_source':'same_session_authenticated_read'}
    if portal._has_evidence(path):
        state=read_journal(path);expected=state.get('modern_links') if isinstance(state,dict) else None
        if (not isinstance(state,dict) or state.get('schema')!='skill6-community-portal/1'
                or state.get('fingerprint')!=fingerprint or state.get('location_id')!=data['location_id']
                or state.get('status')!='NEEDS_VERIFICATION' or state.get('channels')!=expected_channels
                or state.get('sections')!=expected_sections
                or state.get('outcome')!=expected_outcome or not isinstance(expected,list)):
            raise Stop('Modern channel journal is uncertain or unbound; reconcile without another create')
        expected_sections_native=state.get('modern_sections')
        if not isinstance(expected_sections_native,list):
            raise Stop('Modern section journal lacks its full saved native sidebar inventory')
        _home(page,data,context,clock)
        if _inventory(page,data)!=expected:raise Stop('Completed modern channel or sibling links changed; reconcile without another create')
        if _section_inventory(page,data)!=expected_sections_native:
            raise Stop('Completed modern section or sibling headers changed; reconcile without another create')
        for channel in data['channels']:
            rows=[row for row in expected if row['name']==channel['name']]
            if len(rows)!=1 or _read_channel_metadata(page,data,context,clock,rows[0])!=_expected_metadata(channel):
                raise Stop('Saved modern channel description/icon/access changed; reconcile without another create')
        _home(page,data,context,clock)
        if _inventory(page,data)!=expected:raise Stop('Modern channel link inventory changed during native metadata replay')
        if _section_inventory(page,data)!=expected_sections_native:
            raise Stop('Modern section sidebar changed during native metadata replay')
        for section in data.get('sections',[]):
            rows=[row for row in expected_sections_native if row['name']==section['name']]
            if len(rows)!=1 or rows[0]['icon']!=section.get('icon','Hash02Icon'):
                raise Stop('Saved modern section name/icon differs from its authored contract')
        return {**expected_outcome,'replayed':True}
    before=_inventory(page,data);_home(page,data,context,clock)
    if _inventory(page,data)!=before:raise Stop('Modern channel inventory changed during independent preflight')
    before_sections=_section_inventory(page,data)
    if _section_inventory(page,data)!=before_sections:
        raise Stop('Modern section inventory changed during independent preflight')
    reuse_names=set()
    for channel in data['channels']:
        existing=[row for row in before if row['name']==channel['name']]
        if len(existing)>1:raise Stop('Existing modern channel name is ambiguous')
        if existing:
            metadata=_read_channel_metadata(page,data,context,clock,existing[0])
            if metadata!=_expected_metadata(channel):
                raise Stop('Existing modern channel metadata differs from the authored reuse contract')
            reuse_names.add(channel['name'])
            _home(page,data,context,clock)
            if _inventory(page,data)!=before:
                raise Stop('Modern channel link inventory changed during native metadata preflight')
    reuse_sections=set()
    for section in data.get('sections',[]):
        existing=[row for row in before_sections if row['name']==section['name']]
        if len(existing)>1:raise Stop('Existing modern section name is ambiguous')
        if existing:
            if existing[0]['icon']!=section.get('icon','Hash02Icon'):
                raise Stop('Existing modern section icon differs from the authored reuse contract')
            reuse_sections.add(section['name'])
    state={'schema':'skill6-community-portal/1','fingerprint':fingerprint,
        'location_id':data['location_id'],'group_slug':slug,'status':'STARTED','channels':[],'sections':[]}
    secure_json(path,state);current=deepcopy(before);current_sections=deepcopy(before_sections)
    try:
        for index,channel in enumerate(data['channels']):
            if _inventory(page,data)!=current:raise Stop('Modern channel sibling inventory changed before the next create')
            digest=hashlib.sha256(channel['name'].encode()).hexdigest()
            state.update(status='INTENT_RECORDED',current_channel=index,current_name_sha256=digest);secure_json(path,state)
            if channel['name'] in reuse_names:
                pass
            else:
                _create(page,data,context,clock,channel);_home(page,data,context,clock)
                actual=_inventory(page,data);added=[row for row in actual if row['name']==channel['name']]
                if len(added)!=1 or len(actual)!=len(current)+1 or [row for row in actual if row!=added[0]]!=current:
                    raise Stop('Modern channel create changed its target or retained sibling links')
                current=actual
                metadata=_read_channel_metadata(page,data,context,clock,added[0])
                if metadata!=_expected_metadata(channel):
                    raise Stop('Saved modern channel metadata differs from the authored creation contract')
                _home(page,data,context,clock)
                if _inventory(page,data)!=current:
                    raise Stop('Modern channel link inventory changed during native metadata readback')
            state['channels'].append(expected_channels[index])
            state.update(status='CHANNEL_METADATA_OBSERVED_AFTER_RELOAD');secure_json(path,state)
        for index,section in enumerate(data.get('sections',[])):
            if _inventory(page,data)!=current:raise Stop('Modern channel siblings changed before the next section create')
            if _section_inventory(page,data)!=current_sections:
                raise Stop('Modern section siblings changed before the next section create')
            digest=hashlib.sha256(section['name'].encode()).hexdigest()
            state.update(status='SECTION_INTENT_RECORDED',current_section=index,
                current_section_name_sha256=digest);secure_json(path,state)
            if section['name'] not in reuse_sections:
                _create_section(page,data,context,clock,section)
                _home(page,data,context,clock)
                actual_sections=_section_inventory(page,data)
                added=[row for row in actual_sections if row['name']==section['name']]
                if (len(added)!=1 or added[0]['icon']!=section.get('icon','Hash02Icon')
                        or len(actual_sections)!=len(current_sections)+1
                        or [row for row in actual_sections if row!=added[0]]!=current_sections):
                    raise Stop('Modern section create changed its target or retained sibling headers')
                if _inventory(page,data)!=current:
                    raise Stop('Modern section create changed channel siblings')
                current_sections=actual_sections
            state['sections'].append(expected_sections[index])
            state.update(status='SECTION_METADATA_OBSERVED_AFTER_RELOAD');secure_json(path,state)
        for channel in data['channels']:
            rows=[row for row in current if row['name']==channel['name']]
            if len(rows)!=1 or _read_channel_metadata(page,data,context,clock,rows[0])!=_expected_metadata(channel):
                raise Stop('Final modern channel metadata differs from the authored contract')
            _home(page,data,context,clock)
            if _inventory(page,data)!=current:
                raise Stop('Modern channel sibling inventory changed during final metadata verification')
        for section in data.get('sections',[]):
            rows=[row for row in current_sections if row['name']==section['name']]
            if len(rows)!=1 or rows[0]['icon']!=section.get('icon','Hash02Icon'):
                raise Stop('Final modern section name/icon differs from the authored contract')
            _home(page,data,context,clock)
            if _section_inventory(page,data)!=current_sections or _inventory(page,data)!=current:
                raise Stop('Modern section or channel sibling inventory changed during final verification')
        outcome=expected_outcome
        state.update(status='NEEDS_VERIFICATION',outcome=outcome,modern_links=current,
            modern_sections=current_sections);secure_json(path,state)
        return outcome
    except Exception as error:
        state.update(status='RECONCILIATION_REQUIRED',error_type=type(error).__name__)
        secure_json(path,state);raise
