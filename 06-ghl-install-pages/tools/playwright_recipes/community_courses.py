"""Captured native course association in an authenticated community Learning tab.

Native course option titles are bound to a complete same-location API inventory;
the saved card independently exposes exact product/group IDs. This operation
never offers member access, buys a course, sends an invitation or shares a post.
"""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

if __package__:
    from . import community_portal as portal, delivery
    from .evidence_lease import evidence_lease, journal_present, read_journal
    from .skill6_playwright import Stop, click, fill, secure_json, wait_until
else:
    import community_portal as portal
    import delivery
    from evidence_lease import evidence_lease, journal_present, read_journal
    from skill6_playwright import Stop, click, fill, secure_json, wait_until


_SCHEMA='skill6-community-course-association/1'
_JOURNAL='community-details-state.json'
# November 11 independent native reopen: All members cards expose Free.
# Existing Free badges still require access details before reuse.
_VISIBILITY_BADGES={'Private':'Private','All members':'Free'}


def _title(value):
    if (not isinstance(value,str) or not value.strip() or len(value)>1000
            or value!=value.strip() or any(ord(char)<32 for char in value)):
        raise Stop('Community course title must be the exact native/API inventory title')
    return value


def validate_inputs(inputs):
    data=portal._validate_base(inputs,portal._BASE_INPUTS|{'course_associations','api_capability'})
    config=data.get('course_associations')
    if (not isinstance(config,dict)
            or set(config)-{'course_id','course_title','expected_group_id','expected_courses','visibility','expected_visibility'}
            or not {'course_id','course_title','expected_group_id','expected_courses','visibility'}<=set(config)
            or not isinstance(config.get('visibility'),str)
            or config.get('visibility') not in _VISIBILITY_BADGES
            or not isinstance(config.get('expected_courses'),list)):
        raise Stop('Course association requires exact previous inventory and captured Private/All members visibility')
    if 'expected_visibility' in config and (not isinstance(config['expected_visibility'],str)
            or config['expected_visibility'] not in _VISIBILITY_BADGES):
        raise Stop('Course visibility changes require a captured expected Private/All members mode')
    for key in ('course_id','expected_group_id'):delivery._id(config.get(key),key)
    _title(config.get('course_title'))
    identities=[]
    for row in config['expected_courses']:
        if not isinstance(row,dict) or set(row)!={'course_id','title','visibility'}:
            raise Stop('Every native course card requires its exact ID/title/visibility inventory')
        delivery._id(row.get('course_id'),'course_id');_title(row.get('title'))
        visibility=row['visibility']
        if visibility is not None and (not isinstance(visibility,str) or not visibility.strip() or len(visibility)>1000):
            raise Stop('Native course card visibility must be its inventoried badge text or null')
        identities.append(row['course_id'])
    if len(set(identities))!=len(identities):
        raise Stop('Native course card inventory contains duplicate product identities')
    if 'expected_visibility' in config:
        target=[row for row in config['expected_courses'] if row['course_id']==config['course_id']]
        if len(target)!=1 or target[0]['visibility']!=_VISIBILITY_BADGES[config['expected_visibility']]:
            raise Stop('Explicit course visibility changes require the exact existing target and expected native badge')
    return deepcopy(data)


def configuration_hash(inputs):
    plan=validate_inputs(inputs)
    bound={key:plan[key] for key in ('location_id','portal_url','group_name','course_associations')}
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _capability(record,location_id):
    scopes=record.get('scopes') if isinstance(record,dict) else None
    if not isinstance(scopes,list) or any(not isinstance(scope,str) for scope in scopes):
        raise Stop('Course association requires a proven same-location Courses API read capability')
    delivery._capability(record,location_id,scopes=('courses.readonly',))


def _course_identity(api,plan):
    """Enumerate every product so a title-only native selector is unambiguous."""
    config=plan['course_associations'];matches=[];cursor=None;cursors=set();identities=set()
    for _ in range(100):
        query={'limit':'50'}
        if cursor is not None:query['cursor']=cursor
        data=api.request('GET','/courses/products',location_id=plan['location_id'],query=query)
        if not isinstance(data,dict) or not isinstance(data.get('products'),list):
            raise Stop('Complete course API inventory is unavailable')
        for product in data['products']:
            identity=delivery._id(product.get('id') if isinstance(product,dict) else None,'course.id')
            delivery._bound_resource(product,identity,plan['location_id'],'course')
            title=_title(product.get('title'))
            if identity in identities:raise Stop('Course inventory repeats a product ID across pages')
            identities.add(identity)
            if title.casefold()==config['course_title'].casefold():matches.append((identity,title))
        cursor=data.get('nextCursor')
        if cursor in (None,''):break
        if (not isinstance(cursor,str) or len(cursor)>2000 or cursor in cursors
                or any(ord(char)<32 for char in cursor)):
            raise Stop('Course API inventory pagination is ambiguous')
        cursors.add(cursor)
    else:raise Stop('Complete course inventory exceeded bounded pagination')
    if matches!=[(config['course_id'],config['course_title'])]:
        raise Stop('Native course title does not bind one exact same-location API product')
    actual=delivery._bound_resource(api.request('GET','/courses/products/'+config['course_id'],
        location_id=plan['location_id']),config['course_id'],plan['location_id'],'course')
    if actual.get('title')!=config['course_title']:
        raise Stop('Course title changed after complete inventory')


def _learning_url(plan):
    if not urlsplit(plan['portal_url']).path.rstrip('/').endswith('/home'):
        raise Stop('Course association requires an active authenticated group home')
    return plan['portal_url'].rstrip('/').rsplit('/',1)[0]+'/learning'


def _check(page,plan,context,*,clock):
    """Carry the opaque home context onto this exact Learning route/user."""
    if (not isinstance(context,portal.PortalContext) or context._proof is not portal._PROOF
            or context.page is not page or context.location_id!=plan['location_id']
            or context.portal_url.rstrip('/')!=plan['portal_url'].rstrip('/')
            or context.group_name!=plan['group_name']
            or not 0<=clock()-context.observed_at<=portal._CONTEXT_TTL
            or page.url.rstrip('/')!=_learning_url(plan)):
        raise Stop('Fresh exact same-session community Learning context required')
    if page.get_by_placeholder('Password',exact=True).count():
        raise Stop('Community portal authentication required')
    origin,slug=portal._portal(plan['portal_url'])
    try:actual=context.identity_reader(page)
    except Exception:raise Stop('Community Learning authenticated identity read failed') from None
    if (not isinstance(actual,Mapping) or actual.get('authenticated') is not True
            or actual.get('location_id')!=plan['location_id'] or actual.get('portal_origin')!=origin
            or actual.get('group_slug')!=slug or actual.get('group_name')!=plan['group_name']
            or not isinstance(actual.get('user_id'),str) or not actual['user_id']
            or hashlib.sha256(actual['user_id'].encode()).hexdigest()!=context.user_hash
            or actual.get('source_kind')!='same_session_authenticated_read'
            or not 0<=clock()-context.observed_at<=portal._CONTEXT_TTL
            or page.url.rstrip('/')!=_learning_url(plan)):
        raise Stop('Community Learning account/user/location/group identity changed')
    if 'group_id' in actual and actual['group_id']!=plan['course_associations']['expected_group_id']:
        raise Stop('Authenticated group ID differs from the requested native group')
    return dict(actual)


def _one(control,message):
    if control.count()!=1 or not control.is_visible():raise Stop(message)
    return control


def _on_learning(page,plan,context,*,clock):
    if page.url.rstrip('/')==plan['portal_url'].rstrip('/'):
        portal._check_context(page,plan,context,clock=clock)
        page.goto(_learning_url(plan),wait_until='domcontentloaded',timeout=45000)
    return _check(page,plan,context,clock=clock)


def _inventory(page,plan,facts):
    heading=page.get_by_text('Courses in '+plan['group_name'],exact=True)
    _one(heading,'Native Learning heading changed')
    _one(page.get_by_role('button',name='Add course card',exact=True),'Native Add course card changed')
    pagination=page.get_by_role('button',name=re.compile(r'^(?:Next|Previous|Load more|Next page|Previous page)$',re.IGNORECASE))
    if any(pagination.nth(index).is_visible() for index in range(pagination.count())):
        raise Stop('Native Learning inventory is paginated; complete capture required')
    grid=_one(page.locator('div.courses-grid'),'Native Learning course grid changed')
    selector='div.course-card[role="button"][aria-label="Course Card"]'
    cards=grid.locator(selector)
    if cards.count()!=page.locator(selector).count():
        raise Stop('Native Learning course cards escaped their captured grid owner')
    rows=[];seen=set()
    for index in range(cards.count()):
        card=cards.nth(index)
        try:analytics=json.loads(card.get_attribute('data-analytics') or '')
        except (ValueError,TypeError):raise Stop('Native course card identity analytics are unavailable') from None
        if (not isinstance(analytics,dict) or analytics.get('event')!='community_course_opened_event'
                or analytics.get('groupId')!=plan['course_associations']['expected_group_id']):
            raise Stop('Native course card belongs to another group identity')
        product=delivery._id(analytics.get('productId'),'course.productId')
        if product in seen or card.get_attribute('id')!='course-card-'+product+'-':
            raise Stop('Native course card product identity is ambiguous')
        seen.add(product)
        content=card.locator('[id="course-card-'+product+'-content"][role="button"]')
        if content.count()!=1:raise Stop('Native course card content ownership changed')
        title=_title(_one(card.locator('h2[id="course-title-'+product+'-"]'),'Native course card title changed').inner_text().strip())
        badge=card.locator('[id="lock-text-badge-'+product+'-"]')
        if badge.count()>1:raise Stop('Native course card visibility is ambiguous')
        visibility=badge.inner_text().strip() if badge.count()==1 else None
        if visibility=='':raise Stop('Native course card visibility badge is unreadable')
        rows.append({'course_id':product,'title':title,'visibility':visibility})
    if not rows:
        # November 11 owned first-course capture: the loaded empty grid has
        # one direct wrapper containing only its fully rendered Add card.
        # An arbitrary missing list or zero count never satisfies this shape.
        page.wait_for_load_state('networkidle',timeout=45000)
        if cards.count()!=0:
            raise Stop('Native empty Learning inventory changed while settling')
        error=page.get_by_text('Error Loading Courses',exact=True)
        retry=page.get_by_role('button',name='Retry',exact=True)
        if (any(error.nth(i).is_visible() for i in range(error.count()))
                or any(retry.nth(i).is_visible() for i in range(retry.count()))):
            raise Stop('NATIVE_EMPTY_COURSE_INVENTORY_UNPROVEN: native course loading failed')
        add=grid.locator('[id="add-course-card-container-"][role="button"][aria-label="Add course card"]')
        title=add.locator('[id="add-course-title-text-"]')
        description=add.locator('[id="add-course-description-text-"]')
        if (grid.locator(':scope > *').count()!=1
                or grid.locator(':scope > div > *').count()!=1
                or grid.locator(':scope > div > [id="add-course-card-container-"]').count()!=1
                or add.count()!=1 or not add.is_visible()
                or title.count()!=1 or not title.is_visible() or title.inner_text().strip()!='Add New Course'
                or description.count()!=1 or not description.is_visible()
                or description.inner_text().strip()!='Create a new course to share knowledge with your community'):
            raise Stop('NATIVE_EMPTY_COURSE_INVENTORY_UNPROVEN: loaded empty Learning grid differs from its captured Add card profile')
    return rows


def _add(page,plan,context,clock):
    config=plan['course_associations']
    _check(page,plan,context,clock=clock)
    click(_one(page.get_by_role('button',name='Add course card',exact=True),'Native Add course card changed'))
    modal=_one(page.locator('#courses-add-modal'),'Native Add Course dialog changed')
    selector=_one(modal.locator('#course-modal-select-course'),'Native Select Course owner changed')
    click(selector)
    search=selector.locator('.hr-select input')
    if search.count()!=1:raise Stop('Native hidden-role course search input changed')
    fill(search,config['course_title'])
    option=page.get_by_role('option',name=config['course_title'],exact=True)
    wait_until(lambda:option.count()==1 and option.is_visible(),'Exact native course option is missing or ambiguous')
    click(option)
    selected=modal.locator('#course-modal-selected-course-text')
    if selected.count()!=1 or (selected.text_content() or '').strip()!=config['course_title']:
        raise Stop('Native selected course title differs from its API-bound identity')
    visibility=_one(modal.locator('#visibility-select-select-'),'Native course visibility selector changed')
    wanted=config['visibility']
    if visibility.get_by_text(wanted,exact=True).count()!=1:
        click(visibility)
        option=page.get_by_role('option').filter(has=page.get_by_text(wanted,exact=True))
        click(_one(option,'Native requested course visibility is missing or ambiguous'))
    if visibility.get_by_text(wanted,exact=True).count()!=1:
        raise Stop('Native course visibility did not select the requested access')
    _check(page,plan,context,clock=clock)
    submit=_one(modal.locator('#add-course-button-button-'),'Native Add Course submit changed')
    if not submit.is_enabled():raise Stop('Native course association is not accepted')
    click(submit);modal.wait_for(state='hidden',timeout=45000)
    prompt=page.get_by_role('dialog').filter(has=page.get_by_text('Share Course as Post',exact=True))
    card=page.locator('[id="course-card-'+config['course_id']+'-"]')
    wait_until(lambda:prompt.count()==1 and prompt.is_visible() or card.count()==1,
        'Native course association did not return a share prompt or bound course card')
    # The prompt can appear after the card renders. Finish the captured native
    # modal lifecycle before reload; never click Share as Post.
    page.wait_for_load_state('networkidle',timeout=45000)
    skipped=False
    if prompt.count():
        prompt=_one(prompt,'Native share prompt is ambiguous')
        click(_one(prompt.get_by_role('button',name='Skip',exact=True),'Native Skip share control changed'))
        prompt.wait_for(state='hidden',timeout=45000);skipped=True
    return skipped


def _edit_state(modal,plan):
    config=plan['course_associations']
    if _one(modal.locator('#modal-title-text-'),'Native course Edit title changed').inner_text().strip()!='Edit Course':
        raise Stop('Native course editor is not the captured Edit Course mode')
    selector=_one(modal.locator('#course-modal-select-course'),'Native edit course owner changed')
    control=selector.locator('input')
    if control.count()!=1 or control.is_enabled():
        raise Stop('Native edit course must preserve its disabled original product selector')
    selected=modal.locator('#course-modal-selected-course-text')
    if selected.count()!=1 or (selected.text_content() or '').strip()!=config['course_title']:
        raise Stop('Native Edit Course selected product differs from the API-bound course')
    visibility=_one(modal.locator('#visibility-select-select-'),'Native edit course visibility changed')
    label=visibility.locator('.hr-base-selection-input')
    value=label.get_attribute('title') if label.count()==1 else None
    if value not in _VISIBILITY_BADGES:raise Stop('Existing native course uses an uncaptured visibility mode')
    return visibility,value


def _open_edit(page,plan,context,clock):
    _check(page,plan,context,clock=clock)
    config=plan['course_associations']
    card=_one(page.locator('[id="course-card-'+config['course_id']+'-"]'),'Native course edit card changed')
    trigger=_one(card.locator('button[id="course-action-dropdown-trigger-'+config['course_id']+'-"]'),
                 'Native Course actions trigger changed')
    click(trigger)
    menu=page.get_by_role('menu',name='Course actions',exact=True)
    wait_until(lambda:menu.count()==1 and menu.is_visible(),
        'Native Course actions menu is missing or ambiguous')
    edit=_one(menu.get_by_role('menuitem',name='Edit',exact=True),
        'Native Edit Course menu item changed')
    click(edit)
    modal=page.locator('#courses-add-modal')
    modal.wait_for(state='visible',timeout=45000)
    _one(modal,'Native Edit Course dialog changed')
    return modal


def _close_edit(modal):
    click(_one(modal.locator('button#hr-modal__close-button'),'Native Edit Course Close changed'))
    modal.wait_for(state='hidden',timeout=45000)


def _read_visibility(page,plan,context,clock):
    modal=_open_edit(page,plan,context,clock)
    try:return _edit_state(modal,plan)[1]
    finally:_close_edit(modal)


def _update_visibility(page,plan,context,clock):
    config=plan['course_associations'];modal=_open_edit(page,plan,context,clock)
    visibility,current=_edit_state(modal,plan)
    if current!=config['expected_visibility']:
        _close_edit(modal);raise Stop('Native course visibility changed after preflight')
    click(visibility)
    option=page.get_by_role('option').filter(has=page.get_by_text(config['visibility'],exact=True))
    click(_one(option,'Native requested course visibility option changed'))
    if _edit_state(modal,plan)[1]!=config['visibility']:
        raise Stop('Native course visibility ignored its requested update')
    _check(page,plan,context,clock=clock)
    submit=_one(modal.locator('#add-course-button-button-'),'Native Update Course submit changed')
    if submit.inner_text().strip()!='Update Course' or not submit.is_enabled():
        raise Stop('Native Update Course action is unavailable')
    click(submit);modal.wait_for(state='hidden',timeout=45000)
    page.wait_for_load_state('networkidle',timeout=45000)


def _receipt(plan,*,reused,skipped):
    config=plan['course_associations'];_,slug=portal._portal(plan['portal_url'])
    return {'status':'NEEDS_VERIFICATION','location_id':plan['location_id'],
        'objects':[{'kind':'community','id':slug}], 'course_id':config['course_id'],
        'group_id':config['expected_group_id'],'visibility':config['visibility'],
        'configuration_sha256':configuration_hash(plan),'controls_verified':True,
        'independent_readback':'VERIFIED','reused':reused,'share_post_skipped':skipped,
        'communication_attempted':False,'behavior_verified':False,'functional_verified':False,
        'group_activation_attempted':False,'verification_required':True,
        'identity_source':'same_session_authenticated_read_and_native_course_card'}


def _updates_visibility(plan):
    config=plan['course_associations']
    return 'expected_visibility' in config and config['expected_visibility']!=config['visibility']


def _matches_completed_inventory(plan,rows,*,reused):
    """Bind a completed association to its full saved contract, not its journal.

    Native new-card position is not fixed. The requested card must appear once,
    and all independently inventoried siblings must retain their exact order
    and metadata. Reuse must preserve the complete original list unchanged.
    """
    config=plan['course_associations'];before=config['expected_courses']
    wanted={'course_id':config['course_id'],'title':config['course_title'],
            'visibility':_VISIBILITY_BADGES[config['visibility']]}
    matches=[row for row in rows if row['course_id']==config['course_id']]
    if matches!=[wanted]:return False
    if _updates_visibility(plan):
        return rows==[{**row,'visibility':wanted['visibility']} if row['course_id']==config['course_id'] else row for row in before]
    if reused:return rows==before
    return (len(rows)==len(before)+1
        and [row for row in rows if row['course_id']!=config['course_id']]==before)


def run_courses(page,inputs,evidence_root,*,portal_context,transport=None,clock=time.time):
    plan=validate_inputs(inputs);_capability(plan.get('api_capability'),plan['location_id'])
    root=Path(evidence_root).resolve()
    with evidence_lease(root,plan['location_id'],kind='community_details'):
        journal=root/_JOURNAL;digest=configuration_hash(plan)
        if journal_present(journal):
            state=read_journal(journal);raw=state.get('outcome') if isinstance(state,dict) else None
            if (not isinstance(state,dict) or state.get('schema')!=_SCHEMA
                    or state.get('fingerprint')!=digest or state.get('location_id')!=plan['location_id']
                    or state.get('status')!='NEEDS_VERIFICATION' or not isinstance(raw,dict)
                    or type(raw.get('reused')) is not bool or type(raw.get('share_post_skipped')) is not bool):
                raise Stop('Community course journal is uncertain or unbound; reconcile before another association')
            expected=_receipt(plan,reused=raw['reused'],skipped=raw['share_post_skipped'])
            if raw!=expected or raw['reused'] and raw['share_post_skipped']:
                raise Stop('Community course saved proof differs from its authored operation')
            _on_learning(page,plan,portal_context,clock=clock)
            # A prior successful receipt does not establish current native
            # membership. Reload the same Learning route before replaying;
            # drift stops without another API call, association or journal edit.
            page.reload(wait_until='domcontentloaded',timeout=45000)
            page.wait_for_load_state('networkidle',timeout=45000)
            facts=_check(page,plan,portal_context,clock=clock)
            if not _matches_completed_inventory(plan,_inventory(page,plan,facts),reused=raw['reused']):
                raise Stop('Saved native course association or sibling inventory changed; reconcile before replay')
            if _updates_visibility(plan) or plan['course_associations']['visibility']=='All members':
                if _read_visibility(page,plan,portal_context,clock)!=plan['course_associations']['visibility']:
                    raise Stop('Saved native course visibility changed; reconcile before replay')
            return {**expected,'replayed':True}
        api=transport or delivery.Skill44Transport();_course_identity(api,plan)
        facts=_on_learning(page,plan,portal_context,clock=clock)
        page.wait_for_load_state('networkidle',timeout=45000)
        before=_inventory(page,plan,facts)
        page.reload(wait_until='domcontentloaded',timeout=45000)
        page.wait_for_load_state('networkidle',timeout=45000)
        facts=_check(page,plan,portal_context,clock=clock)
        if _inventory(page,plan,facts)!=before:
            raise Stop('Native community course inventory changed during independent preflight')
        config=plan['course_associations']
        if before!=config['expected_courses']:
            raise Stop('Native community course inventory changed before association')
        wanted={'course_id':config['course_id'],'title':config['course_title'],
            'visibility':_VISIBILITY_BADGES[config['visibility']]}
        matches=[row for row in before if row['course_id']==config['course_id']]
        updating=_updates_visibility(plan)
        if matches and matches!=[wanted] and not updating:
            raise Stop('Existing course association has different title/access; explicit update required')
        if matches and (updating or config['visibility']=='All members' or 'expected_visibility' in config):
            expected=config.get('expected_visibility',config['visibility'])
            if _read_visibility(page,plan,portal_context,clock)!=expected:
                raise Stop('Existing course native access differs from its explicitly expected visibility')
        reused=bool(matches) and not updating;state={'schema':_SCHEMA,'fingerprint':digest,
            'location_id':plan['location_id'],'status':'INTENT_RECORDED'}
        secure_json(journal,state)
        try:
            if updating:
                _update_visibility(page,plan,portal_context,clock);skipped=False
            else:skipped=False if reused else _add(page,plan,portal_context,clock)
            facts=_check(page,plan,portal_context,clock=clock)
            desired=_inventory(page,plan,facts)
            if not _matches_completed_inventory(plan,desired,reused=reused):
                raise Stop('Native course association changed target or sibling cards')
            page.reload(wait_until='domcontentloaded',timeout=45000)
            page.wait_for_load_state('networkidle',timeout=45000)
            facts=_check(page,plan,portal_context,clock=clock)
            if _inventory(page,plan,facts)!=desired:
                raise Stop('Native course association readback or sibling cards differ')
            if updating or config['visibility']=='All members':
                if _read_visibility(page,plan,portal_context,clock)!=config['visibility']:
                    raise Stop('Saved course native access differs after independent reload')
            outcome=_receipt(plan,reused=reused,skipped=skipped)
            state.update(status='NEEDS_VERIFICATION',outcome=outcome);secure_json(journal,state)
            return outcome
        except Exception as error:
            state.update(status='RECONCILIATION_REQUIRED',error_type=type(error).__name__)
            secure_json(journal,state);raise
