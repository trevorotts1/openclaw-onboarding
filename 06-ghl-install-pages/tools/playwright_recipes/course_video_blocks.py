"""Captured inactive Neo Classic Video Block upload, replacement and removal.

Sidebar UUID/order binds UUID-less native video previews. Approved regular local
MP4/WebM/MOV sources are privately copied and SHA256 checked before browser work.
The runner owns intent-before-mutation and uncertain-write refusal.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

if __package__:
    from . import course_blocks as blocks, course_theme as theme, course_text_blocks as text, course_media as media
    from .skill6_playwright import Stop, assert_tenant, click, wait_until
else:
    import course_blocks as blocks
    import course_theme as theme
    import course_text_blocks as text
    import course_media as media
    from skill6_playwright import Stop, assert_tenant, click, wait_until

COMMON=blocks.COMMON
_ACCEPT=frozenset(('video/mp4','video/webm','video/mov','video/quicktime'))
_TYPES={'.mp4':('video/mp4',),'.webm':('video/webm',),'.mov':('video/quicktime','video/mov')}
_MAX_BYTES=5_000_000_000


def _state(value):
    if not isinstance(value,dict) or set(value)!={'src','poster'}:
        raise Stop('Video Block requires exact inventoried source and poster URLs')
    return {key:media._url(url,existing=True) or '' for key,url in value.items()}


def _asset(value):
    if (not isinstance(value,dict) or set(value)!={'file','sha256'}
            or not isinstance(value['file'],str) or not Path(value['file']).is_absolute()
            or Path(value['file']).suffix.lower() not in _TYPES
            or not isinstance(value['sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}',value['sha256'])):
        raise Stop('Video Block requires one absolute approved MP4/WebM/MOV and SHA256')


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)-COMMON-{'video_blocks'}:
        raise Stop('Unsupported native Video Block input')
    plan=deepcopy(inputs);base={key:value for key,value in plan.items() if key in COMMON}
    theme.validate_inputs({**base,'expected_values':{'template_title':plan.get('expected_template_title')},
        'changes':{'template_title':plan.get('expected_template_title')}})
    config=plan.get('video_blocks')
    if (not isinstance(config,dict) or set(config)-{'expected_inventory','updates','append'}
            or not isinstance(config.get('expected_inventory'),list)):
        raise Stop('Video Blocks require complete native UUID/type/order inventory')
    text.validate_inputs({**base,'text_blocks':{'expected_inventory':config['expected_inventory'],'append':[{'content':''}]}})
    updates=config.get('updates',[]);appends=config.get('append',[]);seen=set()
    if not isinstance(updates,list) or not isinstance(appends,list) or not (updates or appends):
        raise Stop('Video Blocks require an authored update or append')
    for update in updates:
        if (not isinstance(update,dict) or set(update)!={'id','expected','changes'}
                or not isinstance(update['id'],str) or update['id'] in seen
                or {'id':update['id'],'type':'Video Block'} not in config['expected_inventory']):
            raise Stop('Video update requires one exact inventoried Video UUID')
        seen.add(update['id']);update['expected']=_state(update['expected']);changes=update['changes']
        if not isinstance(changes,dict) or set(changes) not in ({'video'},{'remove_video'}):
            raise Stop('Video updates require an exclusive approved upload or explicit removal')
        if 'video' in changes:_asset(changes['video'])
        elif changes['remove_video'] is not True or not update['expected']['src']:
            raise Stop('Video removal requires explicit true and an inventoried present video')
    for value in appends:
        if not isinstance(value,dict) or set(value)!={'video'}:
            raise Stop('New Video Blocks require an approved video source')
        _asset(value['video'])
    config['updates'],config['append']=updates,appends
    return plan


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','native_course_video_blocks')!='native_course_video_blocks'):
        raise Stop('Unsupported Video Block runner metadata')
    return validate_inputs(step.get('payload'))


def configuration_hash(inputs):
    plan=validate_inputs(inputs);config=deepcopy(plan['video_blocks'])
    for changes in [*(row['changes'] for row in config['updates']),*config['append']]:
        if 'video' in changes:changes['video']={key:value for key,value in changes['video'].items() if key!='file'}
    return hashlib.sha256(json.dumps({**{key:plan[key] for key in
        ('location_id','course_id','template_id','expected_template_title')},'video_blocks':config},
        sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _copy_approved(asset,destination):
    """Stream at most the native limit; never follow a symlink or trust a name."""
    descriptor=None
    try:
        descriptor=os.open(asset['file'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 12<info.st_size<_MAX_BYTES:
            raise Stop('Video source must be a regular file smaller than 5 GB')
        digest=hashlib.sha256();size=0;header=b''
        with os.fdopen(descriptor,'rb') as source,destination.open('xb') as target:
            descriptor=None;destination.chmod(0o600)
            while chunk:=source.read(1024*1024):
                size+=len(chunk)
                if size>=_MAX_BYTES:raise Stop('Video source exceeds the native 5 GB limit')
                if len(header)<32:header=(header+chunk)[:32]
                digest.update(chunk);target.write(chunk)
        suffix=Path(asset['file']).suffix.lower()
        valid=(header.startswith(b'\x1aE\xdf\xa3') if suffix=='.webm' else
            header[4:8]==b'ftyp' or suffix=='.mov' and header[4:8] in (b'moov',b'mdat',b'wide'))
        if size!=info.st_size or digest.hexdigest()!=asset['sha256'] or not valid:
            raise Stop('Video source differs from the approved hash/type/size')
        return size
    except OSError:
        raise Stop('Approved video source is unavailable or unsafe') from None
    finally:
        if descriptor is not None:os.close(descriptor)


def _open(page,plan,identity):
    inventory=blocks._inventory(page,plan)
    if {'id':identity,'type':'Video Block'} not in inventory:
        raise Stop('Video UUID does not identify an inventoried Video Block')
    text._preview_order(page,inventory)
    row=theme._one(page.locator('.sortable-item[id="'+identity+'"]'),'Video sidebar UUID changed')
    click(row.locator(':scope > div.w-full.hl-text-md-medium'))
    preview=text._selected_preview(page,inventory,identity,'Video Block')
    text._inspector_caption(page,'Video Block')
    return theme._one(preview.locator('video'),'Native Video Block preview changed')


def read_video_block(page,plan,identity):
    video=_open(page,plan,identity)
    upload=theme._one(page.locator('#replace-video'),'Native Upload Video changed')
    remove=theme._one(page.locator('#remove-video'),'Native Video Remove changed')
    if upload.inner_text().strip()!='Upload Video' or remove.inner_text().strip()!='Remove':
        raise Stop('Native Video Block action labels changed')
    attrs=video.evaluate('(element)=>Object.fromEntries(Array.from(element.attributes).map(attr=>[attr.name,attr.value]))')
    if (not isinstance(attrs,dict) or 'src' not in attrs or 'poster' not in attrs
            or attrs.get('controls')!=''
            or attrs.get('controlslist')!='nodownload'):
        raise Stop('Native Video Block playback controls changed')
    state=_state({'src':attrs.get('src'),'poster':attrs.get('poster')})
    empty=page.get_by_text('No video',exact=True)
    if (remove.is_enabled()!=bool(state['src']) or not state['src'] and
            (state['poster']!='' or empty.count()!=1 or not empty.is_visible())):
        raise Stop('Native video source, empty marker and Remove state disagree')
    return state,{'attributes':attrs,'remove_enabled':remove.is_enabled()}


def _write(page,plan,identity,changes,path=None,size=None):
    before=read_video_block(page,plan,identity)
    theme._identity(page,plan);assert_tenant(page,plan)
    if read_video_block(page,plan,identity)!=before:
        raise Stop('Video Block changed immediately before its media action')
    if 'remove_video' in changes:
        if not before[0]['src'] or before[1]['remove_enabled'] is not True:
            raise Stop('Video removal requires a present source and enabled native Remove')
        click(theme._one(page.locator('#remove-video'),'Native Remove Video changed'))
        desired=({'src':'','poster':''},{'attributes':{**before[1]['attributes'],'src':'','poster':''},'remove_enabled':False})
        wait_until(lambda:read_video_block(page,plan,identity)==desired,
            'Native video removal did not establish captured empty state')
        return desired
    click(theme._one(page.locator('#replace-video'),'Native Upload Video changed'))
    dialog=theme._one(page.get_by_role('dialog'),'Native video Upload File dialog changed')
    if dialog.get_by_role('heading',name='Upload File',exact=True).count()!=1:
        raise Stop('Native video Upload File heading changed')
    control=dialog.locator('#courses-ui-upload.n-upload > input[type="file"].n-upload-file-input')
    if (control.count()!=1 or control.get_attribute('multiple') is not None
            or frozenset((control.get_attribute('accept') or '').split(','))!=_ACCEPT):
        raise Stop('Native single-video upload input changed')
    control.set_input_files(str(path))
    selected=control.evaluate('(element)=>Array.from(element.files||[]).map(file=>({name:file.name,size:file.size,type:file.type}))')
    if (not isinstance(selected,list) or len(selected)!=1 or selected[0].get('name')!=path.name
            or selected[0].get('size')!=size or selected[0].get('type') not in _TYPES[path.suffix]):
        raise Stop('Native file input did not select the exact approved video')
    submit=theme._one(dialog.locator('#file-upload-footer-btn-positive-action'),'Native video Upload submit changed')
    if submit.inner_text().strip()!='Upload':raise Stop('Native video Upload label changed')
    wait_until(lambda:submit.is_enabled(),'Native video source was not accepted')
    theme._identity(page,plan);assert_tenant(page,plan);click(submit)
    dialog.wait_for(state='hidden',timeout=45000)
    observed=[]
    def ready():
        actual=read_video_block(page,plan,identity)
        if not actual[0]['src'] or actual[0]['src']==before[0]['src']:return False
        old={key:value for key,value in before[1]['attributes'].items() if key not in ('src','poster')}
        new={key:value for key,value in actual[1]['attributes'].items() if key not in ('src','poster')}
        if old!=new or actual[1]['remove_enabled'] is not True:
            raise Stop('Native video upload changed protected player controls')
        observed.append(actual);return True
    wait_until(ready,'Native video upload did not produce a new HTTPS source')
    return observed[-1]


def _proof(identity,changes,state):
    return {'block_id':identity,'source_sha256':changes['video']['sha256'] if 'video' in changes else None,
        'src_sha256':hashlib.sha256(state['src'].encode()).hexdigest(),
        'poster_sha256':hashlib.sha256(state['poster'].encode()).hexdigest(),
        'removed':'remove_video' in changes}


def validate_receipt(value,step):
    plan=validate(step);config=plan['video_blocks']
    keys={'status','editor_url','course_id','template_id','configuration_sha256','independent_readback',
        'videos','added_block_ids','block_ids','block_count','functional_verified','activation_performed'}
    if not isinstance(value,dict) or set(value)!=keys:raise Stop('Video Block outcome fields are unbound')
    before=[row['id'] for row in config['expected_inventory']];ids=value['block_ids'];added=value['added_block_ids']
    if (not isinstance(ids,list) or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids)
            or ids[:len(before)]!=before or not isinstance(added,list) or added!=ids[len(before):]
            or len(added)!=len(config['append']) or type(value['block_count']) is not int
            or value['block_count']!=len(ids)):
        raise Stop('Video Block outcome lost native UUID/order/append identity')
    for identity in ids:theme._id(identity)
    expected={'status':'COURSE_VIDEO_BLOCKS_SAVED_AND_REOPENED','editor_url':theme.editor_url(plan),
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED'}
    if (any(value[key]!=wanted for key,wanted in expected.items())
            or value['functional_verified'] is not False or value['activation_performed'] is not False):
        raise Stop('Video Block receipt retargets its job or claims unsupported proof')
    targets=[(row['id'],row['changes'],row['expected']) for row in config['updates']]
    targets.extend((identity,row,None) for identity,row in zip(added,config['append']))
    if not isinstance(value['videos'],list) or len(value['videos'])!=len(targets):
        raise Stop('Video Block outcome omitted an authored target')
    for proof,(identity,changes,old) in zip(value['videos'],targets):
        removed='remove_video' in changes
        if (not isinstance(proof,dict) or set(proof)!={'block_id','source_sha256','src_sha256','poster_sha256','removed'}
                or proof['block_id']!=identity or proof['removed'] is not removed
                or proof['source_sha256']!=(changes['video']['sha256'] if not removed else None)
                or any(not isinstance(proof[key],str) or not re.fullmatch(r'[a-f0-9]{64}',proof[key])
                    for key in ('src_sha256','poster_sha256'))):
            raise Stop('Video Block proof does not bind target/source/removal')
        if removed and any(proof[key]!=hashlib.sha256(b'').hexdigest() for key in ('src_sha256','poster_sha256')):
            raise Stop('Removed video proof is not the captured empty source/poster')
        if not removed and (proof['src_sha256']==hashlib.sha256(b'').hexdigest()
                or old and proof['src_sha256']==hashlib.sha256(old['src'].encode()).hexdigest()):
            raise Stop('Uploaded video proof retained an empty or old source')
    return deepcopy(value)


def configure(page,step):
    plan=validate(step);config=plan['video_blocks']
    changes=[*(row['changes'] for row in config['updates']),*config['append']]
    with tempfile.TemporaryDirectory(prefix='skill6-course-video-') as temporary:
        files={}
        for index,value in enumerate(changes):
            if 'video' in value:
                path=Path(temporary)/('approved-'+str(index)+Path(value['video']['file']).suffix.lower())
                files[index]=(path,_copy_approved(value['video'],path))
        active=theme._open(page,plan,plan['expected_template_title']);protected=theme._snapshot(page,plan)
        inventory=blocks._inventory(page,plan)
        if inventory!=config['expected_inventory']:raise Stop('Video Block full native inventory is stale')
        before=blocks._snapshot(page,plan,inventory)
        for row in config['updates']:
            if before[row['id']][0]!=row['expected']:raise Stop('Video Block previous source/poster inventory is stale')
        desired=deepcopy(before);wanted=deepcopy(inventory);added=[]
        for index,row in enumerate(config['updates']):
            if read_video_block(page,plan,row['id'])!=before[row['id']]:raise Stop('Video Block changed before authoring')
            desired[row['id']]=_write(page,plan,row['id'],row['changes'],*files.get(index,(None,None)))
        for offset,row in enumerate(config['append']):
            if blocks._inventory(page,plan)!=wanted or blocks._snapshot(page,plan,wanted)!=desired:
                raise Stop('Video Block siblings changed before append')
            blocks._inventory(page,plan)
            click(theme._one(page.get_by_role('button',name='Add Block',exact=True),'Native Add Block changed'))
            click(theme._one(page.get_by_role('button',name='Video Block',exact=True),'Native Video add option changed'))
            after=blocks._inventory(page,plan)
            if (len(after)!=len(wanted)+1 or after[:-1]!=wanted or after[-1]['type']!='Video Block'
                    or after[-1]['id'] in {item['id'] for item in wanted}):
                raise Stop('Native Video append changed UUID/type/order inventory')
            identity=after[-1]['id'];initial=read_video_block(page,plan,identity)
            if initial[0]!={'src':'','poster':''} or initial[1]['remove_enabled'] is not False:
                raise Stop('New Video Block differs from its captured empty state')
            desired[identity]=_write(page,plan,identity,row,*files[len(config['updates'])+offset])
            added.append(identity);wanted=after
        if (blocks._inventory(page,plan)!=wanted or blocks._snapshot(page,plan,wanted)!=desired
                or theme._snapshot(page,plan)!=protected):raise Stop('Video authoring changed protected siblings/theme')
        save=theme._one(page.get_by_role('button',name='Save',exact=True),'Native course Save changed')
        if not save.is_enabled():raise Stop('Video authoring did not enable native Save')
        theme._identity(page,plan);assert_tenant(page,plan);click(save)
        wait_until(lambda:not save.is_enabled(),'Video Save did not settle')
        page.wait_for_load_state('networkidle',timeout=45000)
        if (theme._open(page,plan,plan['expected_template_title'])!=active
                or blocks._inventory(page,plan)!=wanted or blocks._snapshot(page,plan,wanted)!=desired
                or theme._snapshot(page,plan)!=protected):raise Stop('Video saved reopen changed media or protected state')
        targets=[(row['id'],row['changes']) for row in config['updates']];targets.extend(zip(added,config['append']))
        result={'status':'COURSE_VIDEO_BLOCKS_SAVED_AND_REOPENED','editor_url':page.url,
            'course_id':plan['course_id'],'template_id':plan['template_id'],'configuration_sha256':configuration_hash(plan),
            'independent_readback':'VERIFIED','videos':[_proof(identity,change,desired[identity][0]) for identity,change in targets],
            'added_block_ids':added,'block_ids':[row['id'] for row in wanted],'block_count':len(wanted),
            'functional_verified':False,'activation_performed':False}
        return validate_receipt(result,step)


def verify_completed(page,step,outcome):
    plan=validate(step);saved=validate_receipt(outcome,step)
    theme._open(page,plan,plan['expected_template_title']);inventory=blocks._inventory(page,plan)
    before=plan['video_blocks']['expected_inventory']
    wanted=before+[{'id':identity,'type':'Video Block'} for identity in saved['added_block_ids']]
    if inventory!=wanted:raise Stop('Completed Video Block inventory drifted before replay')
    for proof in saved['videos']:
        current=read_video_block(page,plan,proof['block_id'])[0]
        if any(hashlib.sha256(current[key].encode()).hexdigest()!=proof[key+'_sha256'] for key in ('src','poster')):
            raise Stop('Completed Video Block media drifted before replay')
    return True
