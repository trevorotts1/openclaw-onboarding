"""Captured Background Image upload on one existing inactive course template.

The native Upload File dialog and preview/slider anchors were observed November
9, 2026. Source bytes are approved by SHA256. Success requires a newly observed
HTTPS preview URL and exact independent native reopen, never a guessed toast.
The parent runner owns tenant identity, writer lease and uncertain-write journal.
"""
import hashlib
import json
from pathlib import Path
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


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)-COMMON-{'background_image'}:
        raise Stop('Unsupported inactive-template Background Image input')
    base={key:value for key,value in inputs.items() if key in COMMON}
    validated=theme.validate_inputs({**base,
        'expected_values':{'template_title':inputs.get('expected_template_title')},
        'changes':{'template_title':inputs.get('expected_template_title')}})
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
    bound['background_image']={key:value for key,value in plan['background_image'].items() if key!='file'}
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _one(control,message):
    return theme._one(control,message)


def _background(page,plan):
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
    source=media._url(image.get_attribute('src'))
    # These are native style attributes read verbatim, never authored/inferred
    # slider values. The current native slider exposes no aria-valuenow/input.
    transparency={'fill_style':rail.get_attribute('style'),'handle_style':handle.get_attribute('style')}
    return replace,{'url':source,'transparency':transparency}


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


def configure(page,step):
    plan=validate(step)
    content=media._bytes(plan['background_image'])
    if len(content)>=_MAX_BYTES:
        raise Stop('Native template Background Image PNG must be smaller than 10 MiB')
    before_active=theme._open(page,plan,plan['expected_template_title'])
    protected=_protected(page,plan)
    _,before=_background(page,plan)
    if before['url']!=plan['background_image']['expected_url']:
        raise Stop('Background Image preview differs from its inventoried previous URL')
    with tempfile.TemporaryDirectory(prefix='skill6-theme-background-') as temporary:
        path=Path(temporary)/'approved-background.png';path.write_bytes(content);path.chmod(0o600)
        desired=_upload(page,plan,path,len(content))
    if (_protected(page,plan)!=protected or _background(page,plan)[1]!=desired):
        raise Stop('Background upload changed protected theme/body settings before Save')
    theme._identity(page,plan);assert_tenant(page,plan)
    save=_one(page.get_by_role('button',name='Save',exact=True),'Native template Save changed')
    if not save.is_enabled():
        raise Stop('Native background upload did not enable template Save')
    click(save)
    wait_until(lambda:not save.is_enabled(),'Native background Save did not settle')
    try:page.wait_for_load_state('networkidle',timeout=45000)
    except Exception:raise Stop('Background Save remains unsettled; reconcile before another upload') from None
    after_active=theme._open(page,plan,plan['expected_template_title'])
    if (after_active!=before_active or _protected(page,plan)!=protected
            or _background(page,plan)[1]!=desired):
        raise Stop('Background Image independent reopen failed or protected theme changed')
    return {'status':'COURSE_THEME_MEDIA_SAVED_AND_REOPENED','editor_url':page.url,
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'background_url_sha256':hashlib.sha256(desired['url'].encode()).hexdigest(),
        'source_sha256':plan['background_image']['sha256'],
        'functional_verified':False,'activation_performed':False}
