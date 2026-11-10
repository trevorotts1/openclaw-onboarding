"""Captured Image Block append, PNG replacement/removal and HTTPS destination.

Exact sidebar UUID/type/order and active preview img alt bind each inspector.
The parent runner owns durable intent, the write lease and uncertain-run refusal.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile

if __package__:
    from . import course_blocks as blocks, course_media as media, course_text_blocks as text, course_theme as theme
    from .course_theme_media import upload_captured_image
    from .skill6_playwright import Stop,assert_tenant,click,fill,wait_until
else:
    import course_blocks as blocks
    import course_media as media
    import course_text_blocks as text
    import course_theme as theme
    from course_theme_media import upload_captured_image
    from skill6_playwright import Stop,assert_tenant,click,fill,wait_until


COMMON=blocks.COMMON


def _asset(asset,plan):
    if not isinstance(asset,dict) or set(asset)!={'file','sha256'}:
        raise Stop('Image Block media needs one approved local PNG and SHA256')
    media.validate_inputs({'location_id':plan['location_id'],'product_id':plan['course_id'],
        'expected_updated_at':'native-image-block-source-validation','media_assets':[{
            'field':'heroImage','file':asset['file'],'sha256':asset['sha256'],
            'name':'Approved native Image Block','expected_url':None}]})


def _state(value):
    if not isinstance(value,dict) or set(value)!={'inspector_url','preview_url','url'}:
        raise Stop('Image Block previous state requires both image previews and destination URL')
    return {'inspector_url':media._url(value['inspector_url']),
        'preview_url':media._url(value['preview_url']),'url':blocks._text(value['url'],'button_url')}


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)-COMMON-{'image_blocks'}:
        raise Stop('Unsupported native Image Block inputs')
    plan=deepcopy(inputs);base={key:value for key,value in plan.items() if key in COMMON}
    theme.validate_inputs({**base,'expected_values':{'template_title':plan.get('expected_template_title')},
        'changes':{'template_title':plan.get('expected_template_title')}})
    config=plan.get('image_blocks')
    if (not isinstance(config,dict) or set(config)-{'expected_inventory','updates','append'}
            or not isinstance(config.get('expected_inventory'),list)):
        raise Stop('Image Blocks require the complete native UUID/type/order inventory')
    # The Text contract has the same captured read-only sibling inventory.
    text.validate_inputs({**base,'text_blocks':{'expected_inventory':config['expected_inventory'],'append':[{'content':''}]}})
    updates=config.get('updates',[]);appends=config.get('append',[])
    if not isinstance(updates,list) or not isinstance(appends,list) or not (updates or appends):
        raise Stop('Image Blocks require an authored edit or append')
    seen=set()
    for update in updates:
        if (not isinstance(update,dict) or set(update)!={'id','expected','changes'}
                or not isinstance(update.get('id'),str) or update['id'] in seen
                or {'id':update['id'],'type':'Image Block'} not in config['expected_inventory']):
            raise Stop('Image Block edits require exact unique inventoried Image UUIDs')
        seen.add(update['id']);update['expected']=_state(update['expected'])
        changes=update['changes']
        if not isinstance(changes,dict) or not changes or set(changes)-{'image','remove_image','url'}:
            raise Stop('Image Block changes support approved PNG, explicit image removal and HTTPS destination only')
        if 'remove_image' in changes:
            removal=changes['remove_image']
            if ('image' in changes or not isinstance(removal,dict)
                    or set(removal)!={'inspector_url','preview_url'}):
                raise Stop('Image removal requires its exact inventoried empty inspector/rendered URLs and no replacement')
            removal={key:media._url(value) for key,value in removal.items()}
            if (removal['inspector_url']!=removal['preview_url']
                    or any(removal[key]==update['expected'][key] for key in removal)):
                raise Stop('Image removal requires a matching empty placeholder distinct from both previous image URLs')
            changes['remove_image']=removal
        if 'image' in changes:_asset(changes['image'],plan)
        if 'url' in changes:changes['url']=blocks._text(changes['url'],'button_url')
    for value in appends:
        if not isinstance(value,dict) or set(value)!={'image','url'}:
            raise Stop('New Image Blocks require an approved PNG and explicit destination URL')
        _asset(value['image'],plan);value['url']=blocks._text(value['url'],'button_url')
    config['updates'],config['append']=updates,appends
    return plan


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','native_course_image_blocks')!='native_course_image_blocks'):
        raise Stop('Unsupported native Image Block runner metadata')
    return validate_inputs(step.get('payload'))


def configuration_hash(inputs):
    plan=validate_inputs(inputs);config=deepcopy(plan['image_blocks'])
    for value in [*(update['changes'] for update in config['updates']),*config['append']]:
        if 'image' in value:value['image']={key:item for key,item in value['image'].items() if key!='file'}
    bound={key:plan[key] for key in ('location_id','course_id','template_id','expected_template_title')}
    bound['image_blocks']=config
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _sha(value):return hashlib.sha256(value.encode()).hexdigest()


def validate_receipt(value,step):
    plan=validate(step);config=plan['image_blocks']
    keys={'status','editor_url','course_id','template_id','configuration_sha256','independent_readback',
        'images','added_block_ids','block_ids','block_count','functional_verified','activation_performed'}
    if not isinstance(value,dict) or set(value)!=keys:
        raise Stop('Native Image Block outcome is incomplete or contains unbound proof')
    before=[row['id'] for row in config['expected_inventory']];ids=value['block_ids'];added=value['added_block_ids']
    count=len(before)+len(config['append'])
    if (not isinstance(ids,list) or not isinstance(added,list) or len(ids)!=count
            or any(not isinstance(identity,str) for identity in ids) or len(set(ids))!=len(ids)
            or ids[:len(before)]!=before or added!=ids[len(before):]
            or type(value['block_count']) is not int or value['block_count']!=count):
        raise Stop('Native Image Block outcome IDs/count differ from exact native order/append plan')
    for identity in ids:theme._id(identity)
    expected={'status':'COURSE_IMAGE_BLOCKS_SAVED_AND_REOPENED','editor_url':theme.editor_url(plan),
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'functional_verified':False,'activation_performed':False}
    if (any(value[key]!=wanted for key,wanted in expected.items())
            or value['functional_verified'] is not False or value['activation_performed'] is not False):
        raise Stop('Native Image Block outcome is retargeted or claims unsupported proof')
    requests=[(update['id'],update['changes'],update['expected']) for update in config['updates']]
    requests.extend((identity,authored,None) for identity,authored in zip(added,config['append']))
    if not isinstance(value['images'],list) or len(value['images'])!=len(requests):
        raise Stop('Native Image Block outcome omitted authored targets')
    for proof,(identity,changes,old) in zip(value['images'],requests):
        expected_source=changes['image']['sha256'] if 'image' in changes else None
        proof_keys={'block_id','source_sha256','inspector_url_sha256','preview_url_sha256','url_sha256'}
        if 'remove_image' in changes:proof_keys.add('media_removed')
        if (not isinstance(proof,dict) or set(proof)!=proof_keys
                or proof['block_id']!=identity or proof['source_sha256']!=expected_source
                or any(not isinstance(proof[key],str) or not re.fullmatch(r'[a-f0-9]{64}',proof[key])
                    for key in ('inspector_url_sha256','preview_url_sha256','url_sha256'))
                or proof['url_sha256']!=_sha(changes.get('url',old['url'] if old else ''))):
            raise Stop('Native Image Block outcome target/source/destination hashes are unbound')
        if 'remove_image' in changes:
            if (proof['media_removed'] is not True
                    or any(proof[key+'_sha256']!=_sha(url) for key,url in changes['remove_image'].items())):
                raise Stop('Removed Image Block outcome does not bind its exact empty placeholder')
        elif expected_source is not None:
            if proof['inspector_url_sha256']!=proof['preview_url_sha256']:
                raise Stop('Uploaded Image Block inspector/rendered previews do not identify one image')
            if old and (proof['inspector_url_sha256']==_sha(old['inspector_url']) or proof['preview_url_sha256']==_sha(old['preview_url'])):
                raise Stop('Uploaded Image Block still carries an old native preview')
        elif (proof['inspector_url_sha256']!=_sha(old['inspector_url'])
                or proof['preview_url_sha256']!=_sha(old['preview_url'])):
            raise Stop('URL-only Image Block edit changed its preserved media')
    return deepcopy(value)


def _open(page,plan,identity):
    inventory=blocks._inventory(page,plan)
    if {'id':identity,'type':'Image Block'} not in inventory:raise Stop('Requested Image Block UUID/type is absent')
    text._preview_order(page,inventory)
    row=theme._one(page.locator('.sortable-item[id="'+identity+'"]'),'Native Image Block sidebar UUID changed')
    click(row.locator(':scope > div.w-full.hl-text-md-medium'))
    preview=text._selected_preview(page,inventory,identity,'Image Block')
    image=theme._one(preview.locator('img[alt="Image block '+identity+'"]'),'Native Image Block UUID-bound image changed')
    text._inspector_caption(page,'Image')
    theme._one(page.get_by_role('button',name='Delete Block',exact=True),'Native Image Block inspector changed')
    return inventory,image


def read_image_block(page,plan,identity):
    inventory,image=_open(page,plan,identity)
    inspector=theme._one(page.get_by_role('img',name='Offer poster',exact=True),'Native Image Block Offer poster changed')
    upload=theme._one(page.get_by_role('button',name='Upload Image',exact=True),'Native Image Block Upload Image changed')
    remove=theme._one(page.get_by_role('button',name='Remove',exact=True),'Native Image Block Remove changed')
    url=theme._one(page.get_by_placeholder('Eg: https://abc.com',exact=True),'Native Image Block Go to URL changed')
    attributes=image.evaluate('(element)=>Object.fromEntries(Array.from(element.attributes).map(attribute=>[attribute.name,attribute.value]))')
    if not isinstance(attributes,dict) or attributes.get('alt')!='Image block '+identity:
        raise Stop('Native Image Block image attributes do not bind its exact UUID')
    state=_state({'inspector_url':inspector.get_attribute('src'),'preview_url':image.get_attribute('src'),'url':url.input_value()})
    return state,{'preview_attributes':attributes,'remove_enabled':remove.is_enabled()}


def _write(page,plan,identity,changes,path=None,size=None):
    before=read_image_block(page,plan,identity)
    if 'remove_image' in changes:
        if before[1]['remove_enabled'] is not True:
            raise Stop('Native Image Block has no removable image; reconcile before removing')
        _open(page,plan,identity);theme._identity(page,plan);assert_tenant(page,plan)
        remove=theme._one(page.get_by_role('button',name='Remove',exact=True),'Native Image Block Remove changed')
        if not remove.is_enabled():raise Stop('Native Image Block Remove is disabled')
        click(remove)
        def removed():
            current=read_image_block(page,plan,identity)
            return (all(current[0][key]==value for key,value in changes['remove_image'].items())
                and current[0]['url']==before[0]['url'] and current[1]['remove_enabled'] is False)
        wait_until(removed,'Native image removal did not establish the exact empty placeholder and disabled Remove')
    if 'image' in changes:
        def inspect(page,plan):
            state,_=read_image_block(page,plan,identity)
            return theme._one(page.get_by_role('button',name='Upload Image',exact=True),'Native Image Block upload target changed'),{'url':state['inspector_url']}
        uploaded=upload_captured_image(page,plan,path,size,inspect=inspect,expected_url=before[0]['inspector_url'])
        current=read_image_block(page,plan,identity)
        if (current[0]['inspector_url']!=uploaded['url'] or current[0]['preview_url']!=uploaded['url']
                or current[0]['preview_url']==before[0]['preview_url']):
            raise Stop('Image Block upload did not establish new matching inspector/rendered previews')
    if 'url' in changes:
        _open(page,plan,identity);theme._identity(page,plan);assert_tenant(page,plan)
        field=theme._one(page.get_by_placeholder('Eg: https://abc.com',exact=True),'Native Image Block destination target changed')
        if field.input_value()!=changes['url']:fill(field,changes['url']);field.press('Tab')
    actual=read_image_block(page,plan,identity)
    if actual[0]['url']!=changes.get('url',before[0]['url']):raise Stop('Native Image Block ignored destination URL')
    if 'remove_image' in changes:
        expected_state={**before[0],**changes['remove_image'],'url':changes.get('url',before[0]['url'])}
        expected_attrs={**before[1]['preview_attributes'],'src':changes['remove_image']['preview_url']}
        if actual!=(expected_state,{'preview_attributes':expected_attrs,'remove_enabled':False}):
            raise Stop('Image removal changed unrequested native image attributes or destination')
    elif 'image' not in changes and actual!=({**before[0],'url':actual[0]['url']},before[1]):
        raise Stop('Image Block destination editing changed preserved media/attributes')
    if 'image' in changes:
        expected_attrs={key:value for key,value in before[1]['preview_attributes'].items() if key!='src'}
        actual_attrs={key:value for key,value in actual[1]['preview_attributes'].items() if key!='src'}
        if expected_attrs!=actual_attrs:raise Stop('Image Block upload changed unrequested native image attributes')
    return actual


def configure(page,step):
    plan=validate(step);config=plan['image_blocks']
    authored=[*(update['changes'] for update in config['updates']),*config['append']]
    contents={index:media._bytes(value['image']) for index,value in enumerate(authored) if 'image' in value}
    if any(len(content)>=10*1024*1024 for content in contents.values()):raise Stop('Native Image Block PNG must be smaller than 10 MiB')
    active=theme._open(page,plan,plan['expected_template_title']);protected_theme=theme._snapshot(page,plan)
    inventory=blocks._inventory(page,plan)
    if inventory!=config['expected_inventory']:raise Stop('Native Image Block complete UUID/type/order inventory is stale')
    text._preview_order(page,inventory);before=blocks._snapshot(page,plan,inventory)
    for update in config['updates']:
        if before[update['id']][0]!=update['expected']:raise Stop('Image Block differs from expected previous native state')
        if 'remove_image' in update['changes'] and before[update['id']][1]['remove_enabled'] is not True:
            raise Stop('Inventoried Image Block has no removable image; no image writes performed')
    desired=deepcopy(before);wanted=deepcopy(inventory);added=[]
    with tempfile.TemporaryDirectory(prefix='skill6-native-image-block-') as temporary:
        paths={}
        for index,content in contents.items():
            path=Path(temporary)/('approved-image-block-'+str(index)+'.png');path.write_bytes(content);path.chmod(0o600);paths[index]=path
        for index,update in enumerate(config['updates']):
            if blocks._snapshot(page,plan,wanted)!=desired:raise Stop('Image Block siblings changed after preflight')
            desired[update['id']]=_write(page,plan,update['id'],update['changes'],paths.get(index),len(contents[index]) if index in contents else None)
        for offset,value in enumerate(config['append']):
            if blocks._snapshot(page,plan,wanted)!=desired or blocks._inventory(page,plan)!=wanted:
                raise Stop('Native Image Block siblings/inventory changed before append')
            click(theme._one(page.get_by_role('button',name='Add Block',exact=True),'Native Add Block changed'))
            click(theme._one(page.get_by_role('button',name='Image Block',exact=True),'Native Image Block add option changed'))
            after=blocks._inventory(page,plan)
            if (len(after)!=len(wanted)+1 or after[:-1]!=wanted or after[-1]['type']!='Image Block'
                    or after[-1]['id'] in {row['id'] for row in wanted}):
                raise Stop('Native Image Block append changed existing UUID/type/order inventory')
            identity=after[-1]['id'];initial=read_image_block(page,plan,identity)
            if initial[0]['url']!='' or initial[1]['remove_enabled'] is not False:
                raise Stop('New Image Block differs from captured empty URL/disabled Remove defaults')
            index=len(config['updates'])+offset
            desired[identity]=_write(page,plan,identity,value,paths[index],len(contents[index]));added.append(identity);wanted=after
    if (blocks._inventory(page,plan)!=wanted or blocks._snapshot(page,plan,wanted)!=desired
            or theme._snapshot(page,plan)!=protected_theme):
        raise Stop('Image Block authoring changed an unrequested sibling or protected theme')
    theme._identity(page,plan);assert_tenant(page,plan)
    save=theme._one(page.get_by_role('button',name='Save',exact=True),'Native template Save changed')
    if desired!=before:
        if not save.is_enabled():raise Stop('Native Image Block edits did not enable Save')
        click(save);wait_until(lambda:not save.is_enabled(),'Native Image Block Save did not settle')
        try:page.wait_for_load_state('networkidle',timeout=45000)
        except Exception:raise Stop('Image Block Save remains unsettled; reconcile before another write') from None
    elif save.is_enabled():raise Stop('Unrelated unsaved template edits require reconciliation before Save')
    reopened=theme._open(page,plan,plan['expected_template_title'])
    if (reopened!=active or blocks._inventory(page,plan)!=wanted or blocks._snapshot(page,plan,wanted)!=desired
            or theme._snapshot(page,plan)!=protected_theme):
        raise Stop('Image Block independent reopen or complete protected sibling/theme readback failed')
    targets=[(update['id'],update['changes']) for update in config['updates']]
    targets.extend(zip(added,config['append']))
    result={'status':'COURSE_IMAGE_BLOCKS_SAVED_AND_REOPENED','editor_url':page.url,
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'added_block_ids':added,'block_ids':[row['id'] for row in wanted],'block_count':len(wanted),
        'images':[{'block_id':identity,'source_sha256':changes['image']['sha256'] if 'image' in changes else None,
            'inspector_url_sha256':_sha(desired[identity][0]['inspector_url']),
            'preview_url_sha256':_sha(desired[identity][0]['preview_url']),
            'url_sha256':_sha(desired[identity][0]['url']),
            **({'media_removed':True} if 'remove_image' in changes else {})} for identity,changes in targets],
        'functional_verified':False,'activation_performed':False}
    return validate_receipt(result,step)
