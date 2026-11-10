"""Captured Background Image upload on one existing inactive course template.

The native Upload File dialog and preview/slider anchors were observed November
9, 2026. Source bytes are approved by SHA256. Success requires a newly observed
HTTPS preview URL and exact independent native reopen, never a guessed toast.
The parent runner owns tenant identity, writer lease and uncertain-write journal.
"""
import hashlib
import json
from pathlib import Path
import re
import tempfile

if __package__:
    from . import course_blocks as blocks, course_media as media, course_theme as theme
    from .skill6_playwright import Stop, assert_tenant, click, wait_until
else:
    import course_blocks as blocks
    import course_media as media
    import course_theme as theme
    from skill6_playwright import Stop, assert_tenant, click, wait_until


COMMON=theme.COMMON|{'course_id','template_id','expected_template_title'}
_ACCEPT=frozenset(('image/svg+xml','image/png','image/webp','image/jpg','image/jpeg'))
_MAX_BYTES=10*1024*1024
_EMPTY_BACKGROUND='https://staging.cdn.apisystem.tech/assets/membership/image-placeholder.svg'


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)-COMMON-{'background_image','background_transparency','background_removal'}:
        raise Stop('Unsupported inactive-template Background Image input')
    base={key:value for key,value in inputs.items() if key in COMMON}
    validated=theme.validate_inputs({**base,
        'expected_values':{'template_title':inputs.get('expected_template_title')},
        'changes':{'template_title':inputs.get('expected_template_title')}})
    if len(set(inputs).intersection({'background_image','background_transparency','background_removal'}))!=1:
        raise Stop('Background upload, removal and transparency require separate explicit jobs')
    if 'background_removal' in inputs:
        control=inputs['background_removal']
        if not isinstance(control,dict) or set(control)!={'expected_url'}:
            raise Stop('Background removal requires its exact inventoried present image URL')
        media._url(control['expected_url'])
        if control['expected_url']==_EMPTY_BACKGROUND:
            raise Stop('Background removal requires a present image, not the native empty placeholder')
        return {**base,'background_removal':dict(control)}
    if 'background_transparency' in inputs:
        control=inputs['background_transparency']
        if (not isinstance(control,dict) or set(control)!={'expected_url','expected_percentage','percentage'}
                or any(type(control[key]) is not int or not 0<=control[key]<=100
                    for key in ('expected_percentage','percentage'))
                or control['percentage']==control['expected_percentage']):
            raise Stop('Background transparency requires different expected/authored integer percentages from zero to 100')
        media._url(control['expected_url'])
        return {**base,'background_transparency':dict(control)}
    asset=inputs.get('background_image')
    if not isinstance(asset,dict) or set(asset)!={'file','sha256','expected_url'}:
        raise Stop('Background Image requires approved local PNG, SHA256 and exact previous preview URL')
    media.validate_inputs({'location_id':validated['location_id'],'product_id':validated['course_id'],
        'expected_updated_at':'native-template-source-validation',
        'media_assets':[{'field':'heroImage','file':asset['file'],'sha256':asset['sha256'],
            'name':'Native template background','expected_url':asset['expected_url']}]})
    media._url(asset['expected_url'])
    return {**base,'background_image':dict(asset)}


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','native_course_theme_media')!='native_course_theme_media'):
        raise Stop('Unsupported inactive-template Background Image runner metadata')
    return validate_inputs(step.get('payload'))


def configuration_hash(inputs):
    plan=validate_inputs(inputs)
    bound={key:plan[key] for key in ('location_id','course_id','template_id','expected_template_title')}
    field=next(key for key in ('background_transparency','background_removal','background_image') if key in plan)
    bound[field]={key:value for key,value in plan[field].items() if key!='file'}
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _one(control,message):
    return theme._one(control,message)


def _background_nodes(page,plan):
    theme._panel(page,plan,'Layout')
    image=page.get_by_role('img',name='Offer poster',exact=True)
    if image.count()!=1 or not image.is_visible():
        click(_one(page.get_by_text('Background Image',exact=True),
            'Native Background Image section changed'))
        image=page.get_by_role('img',name='Offer poster',exact=True)
    image=_one(image,'Native Background Image preview is missing or ambiguous')
    panel=_one(image.locator('xpath:ancestor::div[contains(concat(" ",normalize-space(@class)," ")," h-full ") and contains(concat(" ",normalize-space(@class)," ")," w-full ")][1]'),
        'Native Background Image inspector container changed')
    if panel.get_by_text('Transparency',exact=True).count()!=1:
        raise Stop('Native Background Image transparency owner changed')
    replace=_one(panel.locator('#replace-image'),'Native Background Image Upload Image control changed')
    if replace.inner_text().strip()!='Upload Image' or panel.locator('#remove-image').count()!=1:
        raise Stop('Native Background Image action anchors changed')
    rail=panel.locator('.n-slider .n-slider-rail .n-slider-rail__fill')
    if rail.count()!=1:
        raise Stop('Native Background Image transparency fill changed')
    handle=_one(panel.locator('.n-slider .n-slider-handle-wrapper[tabindex="0"]'),
        'Native Background Image transparency handle changed')
    return replace,image,rail,handle


def _background(page,plan):
    replace,image,rail,handle=_background_nodes(page,plan)
    source=media._url(image.get_attribute('src'))
    # Native style values are read verbatim. There is no aria-valuenow/input.
    transparency={'fill_style':rail.get_attribute('style'),'handle_style':handle.get_attribute('style')}
    return replace,{'url':source,'transparency':transparency}


def _styles(value):
    if not isinstance(value,str):raise Stop('Native transparency style is unavailable')
    parts={}
    for item in value.split(';'):
        if not item.strip():continue
        pair=item.split(':',1)
        if len(pair)!=2 or pair[0].strip() in parts:raise Stop('Native transparency style is ambiguous')
        parts[pair[0].strip()]=pair[1].strip()
    return parts


def _percentage(state):
    try:
        fill=_styles(state['transparency']['fill_style']);handle=_styles(state['transparency']['handle_style'])
        width=fill['width'];left=handle['left']
    except (KeyError,TypeError):raise Stop('Native transparency percentage is unavailable') from None
    if (fill.get('left')!='0%' or not re.fullmatch(r'(?:0|[1-9][0-9]?|100)%',width)
            or width!=left):
        raise Stop('Native transparency fill and handle percentages disagree or are unsupported')
    return int(width[:-1])


def _slider_siblings(state):
    fill=_styles(state['transparency']['fill_style']);handle=_styles(state['transparency']['handle_style'])
    fill.pop('width',None);handle.pop('left',None)
    # Native focus raises the handle from z-index 0 to 1; reopening resets it.
    # Only that measured presentation-only transition is ignored.
    if handle.get('z-index') not in ('0','1'):
        raise Stop('Native transparency handle focus stacking order is unsupported')
    handle.pop('z-index')
    return fill,handle


def _transparency_readback(state):
    return state['url'],_percentage(state),_slider_siblings(state)


def _write_transparency(page,plan,before):
    control=plan['background_transparency'];current=_percentage(before)
    if current!=control['expected_percentage']:
        raise Stop('Native Background Image transparency differs from its inventoried percentage')
    target=control['percentage'];direction=1 if target>current else -1
    siblings=_slider_siblings(before);actual=before
    # Live capture proved ArrowLeft/Right move exactly one percentage point,
    # clamp at 0/100, and Home does nothing. Never use Home, End or DOM writes.
    for expected in range(current+direction,target+direction,direction):
        theme._identity(page,plan);assert_tenant(page,plan)
        if _transparency_readback(_background(page,plan)[1])!=_transparency_readback(actual):
            raise Stop('Native transparency changed before the next authored key')
        handle=_background_nodes(page,plan)[3]
        handle.press('ArrowRight' if direction==1 else 'ArrowLeft')
        observed={};previous=expected-direction
        def progressed():
            _,candidate=_background(page,plan)
            if (candidate['url']!=before['url'] or _slider_siblings(candidate)!=siblings
                    or _percentage(candidate) not in (previous,expected)):
                raise Stop('Native transparency key changed its image, percentage or protected slider state')
            if _percentage(candidate)==previous:return False
            observed.update(candidate);return True
        wait_until(progressed,'Native transparency key did not reach the exact next percentage')
        actual=dict(observed)
    return actual


def validate_receipt(value,step):
    plan=validate(step)
    fields={'status','editor_url','course_id','template_id','configuration_sha256','independent_readback',
        'background_url_sha256','functional_verified','activation_performed'}
    transparency='background_transparency' in plan
    removal='background_removal' in plan
    fields|=({'media_operation','transparency_percentage'} if transparency else
             {'media_operation','background_removed'} if removal else {'source_sha256'})
    if (not isinstance(value,dict) or set(value)!=fields
            or value.get('status')!='COURSE_THEME_MEDIA_SAVED_AND_REOPENED'
            or value.get('editor_url')!=theme.editor_url(plan)
            or value.get('course_id')!=plan['course_id'] or value.get('template_id')!=plan['template_id']
            or value.get('configuration_sha256')!=configuration_hash(plan)
            or value.get('independent_readback')!='VERIFIED'
            or value.get('functional_verified') is not False or value.get('activation_performed') is not False
            or not isinstance(value.get('background_url_sha256'),str)
            or not re.fullmatch(r'[a-f0-9]{64}',value['background_url_sha256'])):
        raise Stop('Background native receipt is malformed or unbound')
    if transparency:
        control=plan['background_transparency']
        if (value['media_operation']!='transparency' or type(value['transparency_percentage']) is not int
                or value['transparency_percentage']!=control['percentage']
                or value['background_url_sha256']!=hashlib.sha256(control['expected_url'].encode()).hexdigest()):
            raise Stop('Background transparency receipt changed image or authored percentage')
    elif removal:
        if (value['media_operation']!='removal' or value['background_removed'] is not True
                or value['background_url_sha256']!=hashlib.sha256(_EMPTY_BACKGROUND.encode()).hexdigest()):
            raise Stop('Background removal receipt lacks the exact captured empty-state proof')
    elif (value['source_sha256']!=plan['background_image']['sha256']
            or value['background_url_sha256']==hashlib.sha256(plan['background_image']['expected_url'].encode()).hexdigest()):
        raise Stop('Background upload receipt lacks approved source or new image proof')
    return dict(value)


def _protected(page,plan):
    body_inventory=blocks._inventory(page,plan)
    return {'theme':theme._snapshot(page,plan),'body_inventory':body_inventory,
        'body':blocks._snapshot(page,plan,body_inventory)}


def _upload(page,plan,path,content_size):
    return upload_captured_image(page,plan,path,content_size,inspect=_background,
        expected_url=plan['background_image']['expected_url'])


def upload_captured_image(page,plan,path,content_size,*,inspect,expected_url):
    """One observed course Upload File dialog, owned by an exact native target."""
    replace,before=inspect(page,plan)
    if before['url']!=expected_url:
        raise Stop('Course image changed immediately before native upload')
    theme._identity(page,plan);assert_tenant(page,plan);click(replace)
    dialog=_one(page.get_by_role('dialog'),'Native Upload File dialog is ambiguous')
    if dialog.get_by_role('heading',name='Upload File',exact=True).count()!=1:
        raise Stop('Unexpected native image upload dialog')
    file=dialog.locator('#courses-ui-upload.n-upload > input[type="file"].n-upload-file-input')
    if (file.count()!=1 or file.get_attribute('multiple') is not None
            or frozenset((file.get_attribute('accept') or '').split(','))!=_ACCEPT):
        raise Stop('Native single-image upload input changed')
    # set_input_files drives the observed native file input. The file is a
    # private immutable copy of the approved bytes, never a caller URL/download.
    theme._identity(page,plan);assert_tenant(page,plan)
    file.set_input_files(str(path))
    selected=file.evaluate('(element)=>Array.from(element.files||[]).map(file=>({name:file.name,size:file.size,type:file.type}))')
    if selected!=[{'name':path.name,'size':content_size,'type':'image/png'}]:
        raise Stop('Native upload input did not select the exact approved PNG')
    submit=_one(dialog.locator('#file-upload-footer-btn-positive-action'),
        'Native Upload File submit changed')
    if submit.inner_text().strip()!='Upload':
        raise Stop('Native image upload submit label changed')
    wait_until(lambda:submit.is_enabled(),'Native image input was not accepted')
    theme._identity(page,plan);assert_tenant(page,plan);click(submit)
    dialog.wait_for(state='hidden',timeout=45000)
    observed={}
    def image_ready():
        _,actual=inspect(page,plan)
        if actual['url']==before['url']:
            return False
        observed.update(actual);return True
    wait_until(image_ready,'Native upload did not produce a new HTTPS course image preview')
    if {key:value for key,value in observed.items() if key!='url'}!={key:value for key,value in before.items() if key!='url'}:
        raise Stop('Native course image upload changed protected editor state')
    return dict(observed)



def _removal_state(page,plan):
    _,state=_background(page,plan)
    image=_background_nodes(page,plan)[1]
    panel=theme._one(image.locator('xpath:ancestor::div[contains(concat(" ",normalize-space(@class)," ")," h-full ") and contains(concat(" ",normalize-space(@class)," ")," w-full ")][1]'),
        'Native Background Image removal owner changed')
    remove=theme._one(panel.locator('#remove-image'),'Native Background Image Remove changed')
    root=theme._one(page.locator('.neo-classic-template-container'),'Native course background preview is ambiguous')
    styles=root.evaluate('(element)=>Object.fromEntries(Array.from(element.style).map(key=>[key,element.style.getPropertyValue(key)]))')
    if not isinstance(styles,dict) or '--lyt-bg-image' not in styles:
        raise Stop('Native course background CSS identity is unavailable')
    return {**state,'remove_enabled':remove.is_enabled(),'preview_styles':styles}


def _css_image(css,expected):
    # CSSOM preserves the captured quote spelling. Never write a style value.
    return css in ('url("'+expected+'")',"url('"+expected+"')",'url('+expected+')')


def _remove_background(page,plan,before):
    if (before['remove_enabled'] is not True
            or not _css_image(before['preview_styles']['--lyt-bg-image'],before['url'])):
        raise Stop('Background removal requires matching present inspector/preview and enabled Remove')
    theme._identity(page,plan);assert_tenant(page,plan)
    image=_background_nodes(page,plan)[1]
    panel=theme._one(image.locator('xpath:ancestor::div[contains(concat(" ",normalize-space(@class)," ")," h-full ") and contains(concat(" ",normalize-space(@class)," ")," w-full ")][1]'),
        'Native Background Image removal owner changed')
    remove=theme._one(panel.locator('#remove-image'),'Native Background Image Remove changed')
    if not remove.is_enabled():raise Stop('Native Background Image Remove is disabled')
    if _removal_state(page,plan)!=before:
        raise Stop('Native Background Image changed immediately before removal')
    theme._identity(page,plan);assert_tenant(page,plan)
    click(remove)
    desired={**before,'url':_EMPTY_BACKGROUND,'remove_enabled':False,
        'preview_styles':{**before['preview_styles'],'--lyt-bg-image':"url('')"}}
    wait_until(lambda:_removal_state(page,plan)==desired,
        'Background removal did not establish the captured empty inspector/preview and disabled Remove')
    return desired


def verify_completed(page,step,outcome):
    """Fresh native empty state is required before replaying a removal receipt."""
    plan=validate(step)
    validate_receipt(outcome,step)
    if 'background_removal' not in plan:
        raise Stop('Fresh background removal verification requires its exact removal job')
    theme._open(page,plan,plan['expected_template_title'])
    observed=_removal_state(page,plan)
    theme._identity(page,plan);assert_tenant(page,plan)
    if (observed['url']!=_EMPTY_BACKGROUND or observed['remove_enabled'] is not False
            or observed['preview_styles'].get('--lyt-bg-image')!="url('')"):
        raise Stop('Completed background removal no longer matches the native empty state; reconcile before replay')
    return True

def configure(page,step):
    plan=validate(step)
    transparency='background_transparency' in plan
    removal='background_removal' in plan
    content=None if transparency or removal else media._bytes(plan['background_image'])
    if content is not None and len(content)>=_MAX_BYTES:
        raise Stop('Native template Background Image PNG must be smaller than 10 MiB')
    before_active=theme._open(page,plan,plan['expected_template_title'])
    protected=_protected(page,plan)
    before=_removal_state(page,plan) if removal else _background(page,plan)[1]
    control=plan['background_removal' if removal else 'background_transparency' if transparency else 'background_image']
    if before['url']!=control['expected_url']:
        raise Stop('Background Image preview differs from its inventoried previous URL')
    if removal:
        desired=_remove_background(page,plan,before)
    elif transparency:
        desired=_write_transparency(page,plan,before)
    else:
        with tempfile.TemporaryDirectory(prefix='skill6-theme-background-') as temporary:
            path=Path(temporary)/'approved-background.png';path.write_bytes(content);path.chmod(0o600)
            desired=_upload(page,plan,path,len(content))
    protected_after=_protected(page,plan)
    readback=_removal_state(page,plan) if removal else _background(page,plan)[1]
    if (protected_after!=protected or
            (_transparency_readback(readback)!=_transparency_readback(desired) if transparency else readback!=desired)):
        raise Stop('Background authoring changed protected theme/body settings before Save')
    theme._identity(page,plan);assert_tenant(page,plan)
    save=_one(page.get_by_role('button',name='Save',exact=True),'Native template Save changed')
    if not save.is_enabled():
        raise Stop('Native background authoring did not enable template Save')
    click(save)
    wait_until(lambda:not save.is_enabled(),'Native background Save did not settle')
    try:page.wait_for_load_state('networkidle',timeout=45000)
    except Exception:raise Stop('Background Save remains unsettled; reconcile before another upload') from None
    after_active=theme._open(page,plan,plan['expected_template_title'])
    protected_reopened=_protected(page,plan)
    reopened=_removal_state(page,plan) if removal else _background(page,plan)[1]
    if (after_active!=before_active or protected_reopened!=protected
            or (_transparency_readback(reopened)!=_transparency_readback(desired) if transparency else reopened!=desired)):
        raise Stop('Background Image independent reopen failed or protected theme changed')
    result={'status':'COURSE_THEME_MEDIA_SAVED_AND_REOPENED','editor_url':page.url,
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'background_url_sha256':hashlib.sha256(desired['url'].encode()).hexdigest(),
        'functional_verified':False,'activation_performed':False}
    if transparency:
        result.update(media_operation='transparency',transparency_percentage=_percentage(desired))
    elif removal:
        result.update(media_operation='removal',background_removed=True)
    else:result['source_sha256']=plan['background_image']['sha256']
    return validate_receipt(result,step)
