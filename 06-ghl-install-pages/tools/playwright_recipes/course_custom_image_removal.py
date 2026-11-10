"""Captured empty Custom Block inspector and distinct UUID-bound placeholder."""
from copy import deepcopy
import hashlib

if __package__:
    from . import course_block_media as media, course_blocks as blocks, course_theme as theme
    from .skill6_playwright import Stop,assert_tenant,click,wait_until
else:
    import course_block_media as media
    import course_blocks as blocks
    import course_theme as theme
    from skill6_playwright import Stop,assert_tenant,click,wait_until

EMPTY_INSPECTOR='https://staging.cdn.apisystem.tech/assets/membership/image-placeholder.svg'
EMPTY_PREVIEW='https://staging.cdn.apisystem.tech/assets/membership/membership-icons/default-course-image.svg'


def _read(page,plan):
    identity=plan['custom_block_image']['block_id']
    blocks._open_block(page,plan,identity)
    if not blocks._selected(page,identity):raise Stop('Custom image removal selection changed UUID')
    preview=theme._one(page.locator('div.custom-block[id="custom-block-'+identity+'"]'),'Custom image preview UUID changed')
    image=theme._one(preview.locator('img[alt="Image block '+identity+'"]'),'Custom image UUID-bound img changed')
    inspector=theme._one(page.get_by_role('img',name='Offer poster',exact=True),'Custom image inspector changed')
    remove=theme._one(page.locator('#remove-image'),'Custom image Remove changed')
    attributes=image.evaluate('(element)=>Object.fromEntries(Array.from(element.attributes).map(attr=>[attr.name,attr.value]))')
    if not isinstance(attributes,dict) or attributes.get('alt')!='Image block '+identity:
        raise Stop('Custom image preview attributes changed identity')
    return {'inspector_url':media.media._url(inspector.get_attribute('src')),
        'preview_url':media.media._url(image.get_attribute('src')),
        'remove_enabled':remove.is_enabled(),'attributes':attributes,'preview_style':preview.get_attribute('style')}


def validate_receipt(value,step):
    plan=media.validate(step);config=plan['custom_block_image']
    expected={'status':'COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED','editor_url':theme.editor_url(plan),
        'course_id':plan['course_id'],'template_id':plan['template_id'],'block_id':config['block_id'],
        'configuration_sha256':media.configuration_hash(plan),'independent_readback':'VERIFIED',
        'image_url_sha256':hashlib.sha256(EMPTY_PREVIEW.encode()).hexdigest(),
        'inspector_url_sha256':hashlib.sha256(EMPTY_INSPECTOR.encode()).hexdigest(),
        'media_removed':True,'functional_verified':False,'activation_performed':False}
    if (config.get('remove_image') is not True or not isinstance(value,dict) or set(value)!=set(expected)
            or value!=expected or value['media_removed'] is not True
            or value['functional_verified'] is not False or value['activation_performed'] is not False):
        raise Stop('Custom image removal receipt is malformed or unbound')
    return dict(value)


def _receipt(page,plan):
    return {'status':'COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED','editor_url':page.url,
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'block_id':plan['custom_block_image']['block_id'],'configuration_sha256':media.configuration_hash(plan),
        'independent_readback':'VERIFIED','image_url_sha256':hashlib.sha256(EMPTY_PREVIEW.encode()).hexdigest(),
        'inspector_url_sha256':hashlib.sha256(EMPTY_INSPECTOR.encode()).hexdigest(),
        'media_removed':True,'functional_verified':False,'activation_performed':False}


def configure(page,step):
    plan=media.validate(step);config=plan['custom_block_image'];identity=config['block_id']
    if config.get('remove_image') is not True:raise Stop('Custom image removal requires explicit true')
    active=theme._open(page,plan,plan['expected_template_title']);protected=media._protected(page,plan)
    if protected['inventory']!=config['expected_inventory']:raise Stop('Custom image removal inventory is stale')
    before=_read(page,plan)
    if (before['inspector_url']!=config['expected_url'] or before['preview_url']!=config['expected_url']
            or before['remove_enabled'] is not True
            or protected['blocks'][identity][1]['media_src']!=config['expected_url']):
        raise Stop('Custom image removal requires matching inventoried present inspector/preview and enabled Remove')
    desired={**before,'inspector_url':EMPTY_INSPECTOR,'preview_url':EMPTY_PREVIEW,'remove_enabled':False,
        'attributes':{**before['attributes'],'src':EMPTY_PREVIEW}}
    if _read(page,plan)!=before:raise Stop('Custom image changed immediately before removal')
    theme._identity(page,plan);assert_tenant(page,plan)
    remove=theme._one(page.locator('#remove-image'),'Custom image Remove changed')
    if not remove.is_enabled():raise Stop('Custom image Remove is disabled')
    click(remove)
    wait_until(lambda:_read(page,plan)==desired,'Custom image removal did not establish captured distinct empty placeholders')
    wanted=deepcopy(protected);wanted['blocks'][identity][1]['media_src']=EMPTY_PREVIEW
    if media._protected(page,plan)!=wanted:raise Stop('Custom image removal changed protected text/link/style/siblings')
    save=theme._one(page.get_by_role('button',name='Save',exact=True),'Native template Save changed')
    if not save.is_enabled():raise Stop('Custom image removal did not enable Save')
    theme._identity(page,plan);assert_tenant(page,plan);click(save)
    wait_until(lambda:not save.is_enabled(),'Custom image removal Save did not settle')
    page.wait_for_load_state('networkidle',timeout=45000)
    if (theme._open(page,plan,plan['expected_template_title'])!=active
            or media._protected(page,plan)!=wanted or _read(page,plan)!=desired):
        raise Stop('Custom image removal saved reopen changed media or protected state')
    return validate_receipt(_receipt(page,plan),step)


def verify_completed(page,step,outcome):
    plan=media.validate(step);validate_receipt(outcome,step)
    theme._open(page,plan,plan['expected_template_title'])
    if blocks._inventory(page,plan)!=plan['custom_block_image']['expected_inventory']:
        raise Stop('Completed Custom image removal block inventory drifted')
    current=_read(page,plan)
    if (current['inspector_url']!=EMPTY_INSPECTOR or current['preview_url']!=EMPTY_PREVIEW
            or current['remove_enabled'] is not False):
        raise Stop('Completed Custom image removal native empty state drifted')
    return True
