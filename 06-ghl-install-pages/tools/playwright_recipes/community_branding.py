"""Captured modern community Branding page with guarded native PNG choosers.

The three picker IDs, native file-chooser trigger, empty preview owners and
Save changes/Cancel controls were captured November 9, 2026. Unexpected crop
dialogs, absent preview URLs or changed sibling images stop before Save.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time

if __package__:
    from . import community_portal as portal, course_media as media
    from .evidence_lease import evidence_lease, journal_present, read_journal
    from .skill6_playwright import Stop, click, secure_json, wait_until
else:
    import community_portal as portal
    import course_media as media
    from evidence_lease import evidence_lease, journal_present, read_journal
    from skill6_playwright import Stop, click, secure_json, wait_until


SLOTS=('logo','favicon','cover')
_SCHEMA='skill6-community-branding/1'
_JOURNAL='community-details-state.json'


def validate_inputs(inputs):
    plan=portal._validate_base(inputs,portal._BASE_INPUTS|{'branding'})
    if not plan['portal_url'].rstrip('/').endswith('/home'):
        raise Stop('Modern Branding requires its exact active group home context')
    config=plan.get('branding')
    if (not isinstance(config,dict) or set(config)!={'expected','images'}
            or not isinstance(config.get('expected'),dict) or set(config['expected'])!=set(SLOTS)
            or not isinstance(config.get('images'),list) or not config['images']):
        raise Stop('Branding requires all three previous previews and authored PNG replacements')
    for value in config['expected'].values():
        if value is not None:media._url(value)
    seen=set()
    for asset in config['images']:
        if (not isinstance(asset,dict) or set(asset)!={'slot','file','sha256'}
                or not isinstance(asset.get('slot'),str) or asset['slot'] not in SLOTS
                or asset['slot'] in seen):
            raise Stop('Branding replacements require unique captured logo/favicon/cover slots')
        seen.add(asset['slot'])
        media.validate_inputs({'location_id':plan['location_id'],'product_id':'branding-validation',
            'expected_updated_at':'native-source-validation','media_assets':[{
                'field':'logoImage','file':asset['file'],'sha256':asset['sha256'],
                'name':'Native branding source','expected_url':None}]})
    return deepcopy(plan)


def configuration_hash(inputs):
    plan=validate_inputs(inputs)
    bound={key:plan[key] for key in ('location_id','portal_url','group_name')}
    bound['branding']={'expected':plan['branding']['expected'],
        'images':[{key:value for key,value in asset.items() if key!='file'} for asset in plan['branding']['images']]}
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _url(plan):
    return plan['portal_url'].rstrip('/').rsplit('/',1)[0]+'/settings/branding'


def _one(control,message):
    if control.count()!=1 or not control.is_visible():raise Stop(message)
    return control


def _check(page,plan,context,clock):
    return portal.check_subroute(page,plan,context,'settings/branding',clock=clock)


def _on_branding(page,plan,context,clock):
    if page.url.rstrip('/')==plan['portal_url'].rstrip('/'):
        portal._check_context(page,plan,context,clock=clock)
        page.goto(_url(plan),wait_until='domcontentloaded',timeout=45000)
    _check(page,plan,context,clock)
    _one(page.get_by_role('button',name='Save changes',exact=True),'Modern Branding Save changes control changed')
    _one(page.get_by_role('button',name='Cancel',exact=True),'Modern Branding Cancel control changed')


def _preview(page,slot):
    picker=_one(page.locator('#group-branding-'+slot+'-picker-icon'),
        'Native Branding picker identity changed')
    if picker.get_attribute('role')!='button' or picker.get_attribute('aria-label')!='Add media':
        raise Stop('Modern Branding picker role/label changed')
    parent=picker.locator('xpath:..')
    if parent.count()!=1 or 'relative' not in (parent.get_attribute('class') or '').split():
        raise Stop('Modern Branding preview owner changed')
    images=parent.locator('img')
    if images.count()==1:
        return picker,media._url(images.get_attribute('src'))
    if images.count()==0 and parent.locator('div.w-full.h-full.bg-100').count()==1:
        return picker,None
    raise Stop('Modern Branding preview is missing or ambiguous')


def _snapshot(page):
    return {slot:_preview(page,slot)[1] for slot in SLOTS}


def _dialogs(page):
    dialogs=page.get_by_role('dialog')
    return any(dialogs.nth(index).is_visible() for index in range(dialogs.count()))


def _upload(page,plan,context,asset,path,clock):
    _check(page,plan,context,clock)
    if _dialogs(page):raise Stop('Unexpected Branding dialog requires reconciliation before upload')
    picker,before=_preview(page,asset['slot'])
    # Modern Branding opens a native chooser directly, with no persistent DOM
    # file input. Use the actual chooser capability created by this exact click.
    with page.expect_file_chooser(timeout=45000) as pending:
        click(picker)
    chooser=pending.value
    if chooser.is_multiple is not False or chooser.element.get_attribute('type')!='file':
        raise Stop('Native Branding picker did not produce a single-file chooser')
    accept=chooser.element.get_attribute('accept')
    if accept:
        types={item.strip().lower() for item in accept.split(',')}
        if not types.intersection({'image/png','image/*','.png','*/*','*'}):
            raise Stop('Native Branding chooser does not accept the approved PNG type')
    _check(page,plan,context,clock)
    chooser.set_files(str(path))
    observed={}
    def ready():
        if _dialogs(page):raise Stop('Unexpected native crop/upload dialog; no Branding Save attempted')
        _,url=_preview(page,asset['slot'])
        if url is None or url==before:return False
        observed['url']=url;return True
    wait_until(ready,'Native Branding chooser did not produce a new HTTPS preview URL')
    return observed['url']


def _receipt(plan,desired):
    _,slug=portal._portal(plan['portal_url'])
    return {'status':'NEEDS_VERIFICATION','location_id':plan['location_id'],
        'objects':[{'kind':'community','id':slug}],
        'configuration_sha256':configuration_hash(plan),'controls_verified':True,
        'independent_readback':'VERIFIED','branding_slots':[asset['slot'] for asset in plan['branding']['images']],
        'preview_sha256':{slot:hashlib.sha256(value.encode()).hexdigest() if value is not None else None for slot,value in desired.items()},
        'source_sha256':{asset['slot']:asset['sha256'] for asset in plan['branding']['images']},
        'behavior_verified':False,'functional_verified':False,'verification_required':True,
        'group_activation_attempted':False,'communication_attempted':False,
        'identity_source':'same_session_authenticated_read_and_modern_branding_previews'}


def run_branding(page,inputs,evidence_root,*,portal_context,clock=time.time):
    plan=validate_inputs(inputs);root=Path(evidence_root).resolve()
    with evidence_lease(root,plan['location_id'],kind='community_details'):
        journal=root/_JOURNAL;digest=configuration_hash(plan)
        if journal_present(journal):
            state=read_journal(journal)
            if (not isinstance(state,dict) or state.get('schema')!=_SCHEMA
                    or state.get('fingerprint')!=digest or state.get('location_id')!=plan['location_id']
                    or state.get('status')!='NEEDS_VERIFICATION' or not isinstance(state.get('desired'),dict)
                    or set(state['desired'])!=set(SLOTS)):
                raise Stop('Branding journal is uncertain or unbound; reconcile before another upload')
            desired=state['desired']
            for value in desired.values():
                if value is not None:media._url(value)
            expected=_receipt(plan,desired)
            if state.get('outcome')!=expected:
                raise Stop('Branding saved proof differs from the authored operation')
            _on_branding(page,plan,portal_context,clock)
            return {**expected,'replayed':True}
        content=[media._bytes(asset) for asset in plan['branding']['images']]
        if any(len(raw)>=10*1024*1024 for raw in content):
            raise Stop('This Branding runner accepts approved PNGs smaller than 10 MiB')
        _on_branding(page,plan,portal_context,clock)
        page.wait_for_load_state('networkidle',timeout=45000)
        before=_snapshot(page)
        if before!=plan['branding']['expected']:
            raise Stop('Modern Branding previews changed since inventory')
        state={'schema':_SCHEMA,'fingerprint':digest,'location_id':plan['location_id'],
            'status':'INTENT_RECORDED','observed_uploads':{}}
        secure_json(journal,state);desired=dict(before)
        try:
            with tempfile.TemporaryDirectory(prefix='skill6-community-branding-') as temporary:
                for index,(asset,raw) in enumerate(zip(plan['branding']['images'],content)):
                    if _snapshot(page)!=desired:
                        raise Stop('Modern Branding previews changed before the next authored upload')
                    path=Path(temporary)/(asset['slot']+'.png');path.write_bytes(raw);path.chmod(0o600)
                    state.update(current_slot=asset['slot'],status='INTENT_RECORDED');secure_json(journal,state)
                    desired[asset['slot']]=_upload(page,plan,portal_context,asset,path,clock)
                    state['observed_uploads'][asset['slot']]=desired[asset['slot']];secure_json(journal,state)
            if _snapshot(page)!=desired or _dialogs(page):
                raise Stop('Modern Branding authoring changed sibling images or opened an unexpected dialog')
            _check(page,plan,portal_context,clock)
            save=_one(page.get_by_role('button',name='Save changes',exact=True),'Modern Branding Save changes changed')
            if not save.is_enabled():raise Stop('Modern Branding has not accepted its new media')
            state.update(status='SAVE_INTENT_RECORDED',desired=desired);secure_json(journal,state)
            click(save)
            page.wait_for_load_state('networkidle',timeout=45000)
            page.reload(wait_until='domcontentloaded',timeout=45000)
            page.wait_for_load_state('networkidle',timeout=45000)
            _check(page,plan,portal_context,clock)
            if _snapshot(page)!=desired:
                raise Stop('Modern Branding independent preview readback differs')
            outcome=_receipt(plan,desired)
            state.update(status='NEEDS_VERIFICATION',outcome=outcome,desired=desired);secure_json(journal,state)
            return outcome
        except Exception as error:
            state.update(status='RECONCILIATION_REQUIRED',error_type=type(error).__name__)
            secure_json(journal,state);raise
