"""Captured native image upload on one exact inactive-theme Custom Block UUID."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile

if __package__:
    from . import course_blocks as blocks, course_media as media, course_theme as theme, course_theme_media as uploads
    from .skill6_playwright import Stop, assert_tenant, click, wait_until
else:
    import course_blocks as blocks
    import course_media as media
    import course_theme as theme
    import course_theme_media as uploads
    from skill6_playwright import Stop, assert_tenant, click, wait_until


COMMON=theme.COMMON|{'course_id','template_id','expected_template_title'}


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)-COMMON-{'custom_block_image'}:
        raise Stop('Unsupported inactive-theme Custom Block image input')
    base={key:value for key,value in inputs.items() if key in COMMON}
    theme.validate_inputs({**base,'changes':{'template_title':inputs.get('expected_template_title')},
        'expected_values':{'template_title':inputs.get('expected_template_title')}})
    config=inputs.get('custom_block_image')
    if (not isinstance(config,dict) or set(config) not in ({'block_id','expected_inventory','file','sha256','expected_url'},
            {'block_id','expected_inventory','expected_url','remove_image'})
            or not isinstance(config.get('expected_inventory'),list)):
        raise Stop('Custom Block image requires exact UUID/inventory and approved PNG source')
    theme._id(config.get('block_id'));identities=[]
    for row in config['expected_inventory']:
        if (not isinstance(row,dict) or set(row)!={'id','type'}
                or row.get('type') not in ('Category Block','Custom Block','Text Block','Image Block','Video Block')):
            raise Stop('Custom Block image requires a captured Category/Custom Block inventory')
        theme._id(row.get('id'));identities.append(row['id'])
    if (len(set(identities))!=len(identities)
            or sum(row=={'id':'categoryBlock','type':'Category Block'} for row in config['expected_inventory'])!=1
            or any((row['id']=='categoryBlock')!=(row['type']=='Category Block') for row in config['expected_inventory'])
            or {'id':config['block_id'],'type':'Custom Block'} not in config['expected_inventory']):
        raise Stop('Custom Block image UUID does not identify one unique existing custom entry')
    if 'remove_image' in config:
        if config['remove_image'] is not True:
            raise Stop('Custom Block image removal requires explicit true')
        media._url(config['expected_url'])
        if __package__:
            from .course_custom_image_removal import EMPTY_INSPECTOR,EMPTY_PREVIEW
        else:
            from course_custom_image_removal import EMPTY_INSPECTOR,EMPTY_PREVIEW
        if config['expected_url'] in (EMPTY_INSPECTOR,EMPTY_PREVIEW):
            raise Stop('Custom Block removal requires a present image, not an empty placeholder')
        return deepcopy(inputs)
    media.validate_inputs({'location_id':base['location_id'],'product_id':base['course_id'],
        'expected_updated_at':'native-custom-block-validation','media_assets':[{
            'field':'heroImage','file':config['file'],'sha256':config['sha256'],
            'name':'Native Custom Block image','expected_url':config['expected_url']}]})
    media._url(config['expected_url'])
    return deepcopy(inputs)


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','native_course_block_media')!='native_course_block_media'):
        raise Stop('Unsupported Custom Block media runner metadata')
    return validate_inputs(step.get('payload'))


def configuration_hash(inputs):
    plan=validate_inputs(inputs)
    bound={key:plan[key] for key in ('location_id','course_id','template_id','expected_template_title')}
    bound['custom_block_image']={key:value for key,value in plan['custom_block_image'].items() if key!='file'}
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _image(page,plan):
    identity=plan['custom_block_image']['block_id']
    blocks._open_block(page,plan,identity)
    if not blocks._selected(page,identity):raise Stop('Custom Block image inspector changed selected UUID')
    replace=theme._one(page.locator('#replace-image'),'Native Custom Block Upload Image control changed')
    if replace.inner_text().strip()!='Upload Image' or page.locator('#remove-image').count()!=1:
        raise Stop('Native Custom Block image controls changed')
    preview=theme._one(page.locator('div.custom-block[id="custom-block-'+identity+'"] img[alt="Image block '+identity+'"]'),
        'Native Custom Block image preview UUID changed')
    source=media._url(preview.get_attribute('src'))
    inspector=theme._one(page.get_by_role('img',name='Offer poster',exact=True),'Native Custom Block image inspector changed')
    if media._url(inspector.get_attribute('src'))!=source:
        raise Stop('Custom Block image inspector differs from its UUID-bound preview')
    return replace,{'url':source,'block_id':identity}


def _protected(page,plan):
    inventory=blocks._inventory(page,plan)
    return {'theme':theme._snapshot(page,plan),'inventory':inventory,
        'blocks':blocks._snapshot(page,plan,inventory)}


def configure(page,step):
    plan=validate(step);config=plan['custom_block_image'];identity=config['block_id']
    if 'remove_image' in config:
        if __package__:
            from .course_custom_image_removal import configure as remove
        else:
            from course_custom_image_removal import configure as remove
        return remove(page,step)
    content=media._bytes(config)
    if len(content)>=10*1024*1024:raise Stop('Native Custom Block PNG must be smaller than 10 MiB')
    before_active=theme._open(page,plan,plan['expected_template_title'])
    before=_protected(page,plan)
    if before['inventory']!=config['expected_inventory']:
        raise Stop('Custom Block image native ID/type/order inventory is stale')
    if before['blocks'][identity][1]['media_src']!=config['expected_url']:
        raise Stop('Custom Block image differs from its inventoried previous URL')
    with tempfile.TemporaryDirectory(prefix='skill6-custom-block-image-') as temporary:
        path=Path(temporary)/'approved-block-image.png';path.write_bytes(content);path.chmod(0o600)
        observed=uploads.upload_captured_image(page,plan,path,len(content),inspect=_image,expected_url=config['expected_url'])
    desired=deepcopy(before)
    desired['blocks'][identity][1]['media_src']=observed['url']
    if _protected(page,plan)!=desired:
        raise Stop('Custom Block image upload changed protected block/theme content or siblings')
    theme._identity(page,plan);assert_tenant(page,plan)
    save=theme._one(page.get_by_role('button',name='Save',exact=True),'Native template Save changed')
    if not save.is_enabled():raise Stop('Custom Block image upload did not enable native Save')
    click(save);wait_until(lambda:not save.is_enabled(),'Custom Block image Save did not settle')
    try:page.wait_for_load_state('networkidle',timeout=45000)
    except Exception:raise Stop('Custom Block image Save remains unsettled; reconcile before another upload') from None
    after_active=theme._open(page,plan,plan['expected_template_title'])
    if after_active!=before_active or _protected(page,plan)!=desired or _image(page,plan)[1]!=observed:
        raise Stop('Custom Block image independent reopen failed or protected native state changed')
    return {'status':'COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED','editor_url':page.url,
        'course_id':plan['course_id'],'template_id':plan['template_id'],'block_id':identity,
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'source_sha256':config['sha256'],'image_url_sha256':hashlib.sha256(observed['url'].encode()).hexdigest(),
        'functional_verified':False,'activation_performed':False}
