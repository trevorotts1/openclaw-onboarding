"""November 11 modern Group Details description edits, preserving all access."""
from pathlib import Path
import hashlib
import json
import time

from playwright_recipes import community_portal as portal
from playwright_recipes.evidence_lease import evidence_lease, journal_present
from playwright_recipes.skill6_playwright import Stop, click, fill, secure_json, wait_until

FLAGS={'accessible_from_switcher':'#group-details-switcher-checkbox-card',
       'allow_member_invites':'#group-details-invite-checkbox-card',
       'mandatory_profile':'#group-details-mandatory-profile-checkbox-card'}


def details_url(data):
    if not data['portal_url'].rstrip('/').endswith('/home'):
        raise Stop('Modern Group Details requires the captured authenticated home route')
    return data['portal_url'].rstrip('/').rsplit('/',1)[0]+'/settings/details'


def available(page,data):
    if page.url.rstrip('/')==details_url(data):return True
    locator=getattr(page,'locator',None)
    if not callable(locator):return False
    _,slug=portal._portal(data['portal_url'])
    link=locator('a[href="/communities/groups/'+slug+'/settings/details"]')
    if link.count()>1:raise Stop('Modern Group Details navigation is ambiguous')
    return link.count()==1 and link.is_visible()


def _one(node,message):
    if node.count()!=1 or not node.is_visible():raise Stop(message)
    return node


def snapshot(page,data):
    panel=_one(page.locator('#group-details-card-container'),'Modern Group Details owner changed')
    name=_one(panel.locator('#group-details-name-input input'),'Modern group name input changed')
    slug=_one(panel.locator('#group-details-slug-input input'),'Modern group slug input changed')
    description=_one(panel.locator('#group-details-description-textarea textarea'),'Modern group description input changed')
    _,expected_slug=portal._portal(data['portal_url'])
    if name.input_value()!=data['group_name'] or slug.input_value()!=expected_slug:
        raise Stop('Modern Group Details name/slug differ from exact authenticated group')
    protected={'name':name.input_value(),'slug':slug.input_value()}
    for key in ('public','private'):
        card=_one(panel.locator('#group-details-'+key+'-group-radio-card'),'Modern group privacy owner changed')
        radio=card.locator('input[type="radio"]')
        if radio.count()!=1:raise Stop('Modern group privacy input is ambiguous')
        protected[key]=radio.is_checked()
    if protected['public']==protected['private']:raise Stop('Modern group privacy selection is ambiguous')
    for key,selector in FLAGS.items():
        node=_one(panel.locator(selector),'Modern group access flag changed')
        value=node.get_attribute('aria-checked')
        if node.get_attribute('role')!='checkbox' or value not in ('true','false'):
            raise Stop('Modern group access flag state is unavailable')
        protected[key]=value=='true'
    return description,protected


def _check(page,data,context,clock):
    return portal.check_subroute(page,data,context,'settings/details',clock=clock)


def _on_details(page,data,context,clock):
    if page.url.rstrip('/')==data['portal_url'].rstrip('/'):
        portal._check_context(page,data,context,clock=clock)
        page.goto(details_url(data),wait_until='domcontentloaded',timeout=45000)
    _check(page,data,context,clock)
    page.locator('#group-details-description-textarea textarea').wait_for(state='visible',timeout=45000)


def run_details(page,inputs,evidence_root,*,portal_context,clock=time.time):
    data=portal.validate_details_inputs(inputs);root=Path(evidence_root).resolve()
    with evidence_lease(root,data['location_id'],kind='community_details'):
        path=root/'community-details-state.json'
        fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        _on_details(page,data,portal_context,clock)
        if journal_present(path):
            result=portal._replay_details(path,data,fingerprint)
            page.reload(wait_until='domcontentloaded',timeout=45000)
            _check(page,data,portal_context,clock)
            page.locator('#group-details-description-textarea textarea').wait_for(state='visible',timeout=45000)
            description,_=snapshot(page,data)
            if description.input_value()!=data['details']['description']:
                raise Stop('Completed modern community description changed; reconcile without another write')
            return result
        description,protected=snapshot(page,data)
        current=description.input_value();wanted=data['details']['description']
        if current not in (data['details']['expected_description'],wanted):
            raise Stop('Modern community description differs from expected inventory')
        _,slug=portal._portal(data['portal_url'])
        state={'schema':'skill6-community-details/1','fingerprint':fingerprint,
            'location_id':data['location_id'],'group_slug':slug,'status':'INTENT_RECORDED',
            'description_sha256':hashlib.sha256(wanted.encode()).hexdigest()}
        secure_json(path,state)
        try:
            reused=current==wanted
            if not reused:
                fill(description,wanted)
                _check(page,data,portal_context,clock)
                description,staged=snapshot(page,data)
                if staged!=protected or description.input_value()!=wanted:
                    raise Stop('Modern description edit changed name, slug, privacy or access')
                save=_one(page.locator('#group-settings-save-button'),'Modern Group Details Save changed')
                if not save.is_enabled():raise Stop('Modern Group Details Save is disabled')
                click(save)
                wait_until(lambda:save.count()==1 and save.is_enabled(),'Modern Group Details Save did not settle')
                page.wait_for_load_state('networkidle',timeout=45000)
            page.reload(wait_until='domcontentloaded',timeout=45000)
            _check(page,data,portal_context,clock)
            page.locator('#group-details-description-textarea textarea').wait_for(state='visible',timeout=45000)
            description,retained=snapshot(page,data)
            if description.input_value()!=wanted or retained!=protected:
                raise Stop('Modern Group Details independent readback or protected controls differ')
            outcome={'status':'NEEDS_VERIFICATION','location_id':data['location_id'],
                'objects':[{'kind':'community','id':slug}],
                'description_sha256':state['description_sha256'],'description_verified':True,
                'protected_access_unchanged':True,'group_activation_attempted':False,'reused':reused,
                'behavior_verified':False,'verification_required':True,
                'identity_source':'same_session_authenticated_read'}
            state.update(status='NEEDS_VERIFICATION',outcome=outcome);secure_json(path,state)
            return outcome
        except Exception as error:
            state.update(status='RECONCILIATION_REQUIRED',error_type=type(error).__name__)
            secure_json(path,state);raise


def run_access(page,inputs,evidence_root,*,portal_context,access_authorization=None,clock=time.time):
    """Reuse the existing access contract on the captured modern Details form."""
    from playwright_recipes import community_access as access
    data=access.validate_inputs(inputs);root=Path(evidence_root).resolve()
    with evidence_lease(root,data['location_id'],kind='community_access'):
        path=root/access._JOURNAL;_on_details(page,data,portal_context,clock)
        desired=access._desired(data)
        if journal_present(path):
            result=access._replay(path,data)
            page.reload(wait_until='domcontentloaded',timeout=45000)
            _check(page,data,portal_context,clock)
            page.locator('#group-details-description-textarea textarea').wait_for(state='visible',timeout=45000)
            description,protected=snapshot(page,data)
            if (access._state(protected)!=desired or hashlib.sha256(description.input_value().encode()).hexdigest()
                    !=result['protected_description_sha256']):
                raise Stop('Completed modern community access or protected description changed; reconcile without another write')
            return result
        description,protected=snapshot(page,data)
        current=access._state(protected)
        if current not in (data['access']['expected'],desired):
            raise Stop('Modern community access differs from expected inventory')
        reused=current==desired;expanded=not reused and access.expands_access(current,desired)
        if expanded:access._check_authorization(page,data,portal_context,access_authorization,clock)
        copy=description.input_value();digest=hashlib.sha256(copy.encode()).hexdigest()
        _,slug=portal._portal(data['portal_url'])
        state={'schema':access._SCHEMA,'configuration_sha256':access.configuration_hash(data),
            'location_id':data['location_id'],'group_slug':slug,'status':'INTENT_RECORDED'}
        secure_json(path,state)
        try:
            if not reused:
                if current['privacy']!=desired['privacy']:
                    node=_one(page.locator('#group-details-'+desired['privacy']+'-group-radio-card'),
                              'Modern desired group privacy control changed')
                    if node.get_attribute('aria-disabled')!='false':raise Stop('Modern group privacy control is disabled')
                    click(node)
                for key,selector in FLAGS.items():
                    if current[key]!=desired[key]:
                        node=_one(page.locator(selector),'Modern desired access control changed')
                        if node.get_attribute('aria-disabled')!='false':raise Stop('Modern group access control is disabled')
                        click(node)
                _check(page,data,portal_context,clock)
                description,staged=snapshot(page,data)
                if (access._state(staged)!=desired or description.input_value()!=copy
                        or any(staged[key]!=protected[key] for key in ('name','slug'))):
                    raise Stop('Modern access edit changed protected copy/identity or ignored requested values')
                if expanded:access._check_authorization(page,data,portal_context,access_authorization,clock,consume=True)
                save=_one(page.locator('#group-settings-save-button'),'Modern Group Details Save changed')
                if not save.is_enabled():raise Stop('Modern Group Details Save is disabled')
                click(save);wait_until(lambda:save.count()==1 and save.is_enabled(),'Modern Group Details Save did not settle')
                page.wait_for_load_state('networkidle',timeout=45000)
            page.reload(wait_until='domcontentloaded',timeout=45000)
            _check(page,data,portal_context,clock)
            page.locator('#group-details-description-textarea textarea').wait_for(state='visible',timeout=45000)
            description,retained=snapshot(page,data)
            if (access._state(retained)!=desired or description.input_value()!=copy
                    or any(retained[key]!=protected[key] for key in ('name','slug'))):
                raise Stop('Modern access independent readback or protected description/identity differ')
            outcome=access._receipt(data,reused=reused,description_hash=digest,expanded=expanded)
            state.update(status='NEEDS_VERIFICATION',outcome=outcome);secure_json(path,state)
            return outcome
        except Exception as error:
            state.update(status='RECONCILIATION_REQUIRED',error_type=type(error).__name__)
            secure_json(path,state);raise
