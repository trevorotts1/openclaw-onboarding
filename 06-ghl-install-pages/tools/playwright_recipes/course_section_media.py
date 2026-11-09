"""Captured Hero and Instructor PNG uploads on an inactive course theme.

The native inspector and rendered preview can use different placeholder URLs.
Both identities are inventoried; an upload must replace both with the same new
HTTPS media URL, with all other section controls and sibling blocks preserved.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile

if __package__:
    from . import course_blocks as blocks, course_media as media, course_theme as theme
    from .course_theme_media import upload_captured_image
    from .skill6_playwright import Stop,assert_tenant,click,wait_until
else:
    import course_blocks as blocks
    import course_media as media
    import course_theme as theme
    from course_theme_media import upload_captured_image
    from skill6_playwright import Stop,assert_tenant,click,wait_until


COMMON=blocks.COMMON
SECTIONS=('hero','instructor')


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)-COMMON-{'theme_images'}:
        raise Stop('Unsupported inactive course Hero/Instructor media inputs')
    base={key:value for key,value in inputs.items() if key in COMMON}
    theme.validate_inputs({**base,'expected_values':{'template_title':inputs.get('expected_template_title')},
        'changes':{'template_title':inputs.get('expected_template_title')}})
    config=inputs.get('theme_images')
    if (not isinstance(config,dict) or set(config)!={'expected','images'}
            or not isinstance(config['expected'],dict) or set(config['expected'])!=set(SECTIONS)
            or not isinstance(config['images'],list) or not config['images']):
        raise Stop('Theme media requires complete Hero/Instructor previous previews and authored PNG replacements')
    for section,value in config['expected'].items():
        if not isinstance(value,dict) or set(value)!={'inspector_url','preview_url'}:
            raise Stop('Every section requires both exact inspector and rendered preview image URLs')
        for url in value.values():media._url(url)
    seen=set()
    for asset in config['images']:
        if (not isinstance(asset,dict) or set(asset)!={'section','file','sha256'}
                or not isinstance(asset.get('section'),str) or asset['section'] not in SECTIONS
                or asset['section'] in seen):
            raise Stop('Theme PNG replacements require unique captured Hero/Instructor sections')
        seen.add(asset['section'])
        media.validate_inputs({'location_id':inputs['location_id'],'product_id':inputs['course_id'],
            'expected_updated_at':'native-section-source-validation','media_assets':[{
                'field':'heroImage' if asset['section']=='hero' else 'instructorHeadshot',
                'file':asset['file'],'sha256':asset['sha256'],'name':'Approved native course image',
                'expected_url':config['expected'][asset['section']]['inspector_url']}]})
    return deepcopy(inputs)


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','native_course_section_media')!='native_course_section_media'):
        raise Stop('Unsupported native Hero/Instructor media runner metadata')
    return validate_inputs(step.get('payload'))


def configuration_hash(inputs):
    plan=validate_inputs(inputs)
    bound={key:plan[key] for key in ('location_id','course_id','template_id','expected_template_title')}
    bound['theme_images']={'expected':plan['theme_images']['expected'],
        'images':[{key:value for key,value in asset.items() if key!='file'} for asset in plan['theme_images']['images']]}
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _sha(value):return hashlib.sha256(value.encode()).hexdigest()


def validate_receipt(value,step):
    plan=validate(step)
    keys={'status','editor_url','course_id','template_id','configuration_sha256','independent_readback',
        'images','functional_verified','activation_performed'}
    if not isinstance(value,dict) or set(value)!=keys:
        raise Stop('Native section-media outcome is incomplete or contains unbound proof')
    expected={'status':'COURSE_SECTION_MEDIA_SAVED_AND_REOPENED','editor_url':theme.editor_url(plan),
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'functional_verified':False,'activation_performed':False}
    if (any(value[key]!=wanted for key,wanted in expected.items())
            or value['functional_verified'] is not False or value['activation_performed'] is not False):
        raise Stop('Native section-media proof differs from its exact inactive template/inputs')
    images=value['images'];assets=plan['theme_images']['images']
    if not isinstance(images,list) or len(images)!=len(assets):
        raise Stop('Native section-media outcome omitted an authored section')
    for proof,asset in zip(images,assets):
        if (not isinstance(proof,dict) or set(proof)!={'section','source_sha256','inspector_url_sha256','preview_url_sha256'}
                or proof['section']!=asset['section'] or proof['source_sha256']!=asset['sha256']
                or any(not isinstance(proof[key],str) or not re.fullmatch(r'[a-f0-9]{64}',proof[key])
                    for key in ('source_sha256','inspector_url_sha256','preview_url_sha256'))
                or proof['inspector_url_sha256']!=proof['preview_url_sha256']):
            raise Stop('Native section-media outcome image/source identities are unbound')
        old=plan['theme_images']['expected'][asset['section']]
        if (proof['inspector_url_sha256']==_sha(old['inspector_url'])
                or proof['preview_url_sha256']==_sha(old['preview_url'])):
            raise Stop('Native section-media outcome did not replace both old image previews')
    return deepcopy(value)


def _flag(page,identity):
    flag=theme._one(page.locator('#'+identity),'Native course media checkbox identity changed')
    value=flag.get_attribute('aria-checked')
    if flag.get_attribute('role')!='checkbox' or value not in ('true','false'):
        raise Stop('Native course media checkbox state is unreadable')
    return value=='true'


def _visible_controls(panel,*,color_count,slider_count):
    # These are the captured shared native color-picker and slider widgets,
    # read without opening or authoring them. Preserve the complete visible
    # control order/count as well as their raw values/styles.
    swatches=panel.locator('.brand-color-value')
    if swatches.count()!=color_count:raise Stop('Native section color-picker inventory is unavailable')
    colors=[]
    for index in range(swatches.count()):
        swatch=theme._one(swatches.nth(index),'Native section color swatch changed')
        value=swatch.evaluate('(element)=>element.style.backgroundColor')
        if not isinstance(value,str) or not value:raise Stop('Native section color swatch is unreadable')
        colors.append(value)
    sliders=panel.locator('.n-slider');values=[]
    if sliders.count()!=slider_count:raise Stop('Native section transparency control count changed')
    for index in range(sliders.count()):
        slider=sliders.nth(index)
        if not slider.is_visible():continue
        fill=slider.locator('.n-slider-rail .n-slider-rail__fill')
        handle=slider.locator('.n-slider-handle-wrapper[tabindex="0"]')
        if fill.count()!=1 or handle.count()!=1:raise Stop('Native section transparency slider inventory changed')
        values.append({'fill_style':fill.get_attribute('style'),'handle_style':handle.get_attribute('style')})
    return {'colors':colors,'sliders':values}


def _open_section(page,plan,section):
    if section=='hero':
        theme._panel(page,plan,'Hero')
        flag=page.locator('#show-hero-checkbox')
        if flag.count()!=1 or not flag.is_visible():
            click(theme._one(page.get_by_text('Appearance',exact=True),'Native Hero Appearance control changed'))
        if not _flag(page,'show-hero-checkbox'):
            raise Stop('Native Hero PNG upload requires its captured visible Hero preview')
        panel=theme._one(page.locator('#show-hero-checkbox').locator('xpath:..'),
            'Native Hero Appearance inspector owner changed')
        if not {'h-full','w-full','text-gray-800'}.issubset((panel.get_attribute('class') or '').split()):
            raise Stop('Native Hero Appearance panel identity changed')
        overlay=_flag(page,'show-overlay-checkbox')
        modes={}
        for label,value in (('Color','color'),('Image','image')):
            control=theme._one(panel.get_by_role('radio',name=label,exact=True),'Native Hero media mode changed')
            if control.get_attribute('type')!='radio' or control.get_attribute('value')!=value:
                raise Stop('Native Hero image/color radio identity changed')
            modes[value]=control.is_checked()
        if modes!={'color':False,'image':True}:
            raise Stop('Native Hero PNG upload requires captured Image mode; no mode changes are implicit')
        preview=theme._one(page.locator('.welcome-hero-image[isediting="true"] img[alt="Welcome hero image"]'),
            'Native active Hero image preview binding changed')
        controls={'hero_visible':True,'overlay_visible':overlay,'modes':modes,
            **_visible_controls(panel,color_count=1,slider_count=1)}
        if len(controls['sliders'])!=1:raise Stop('Native Hero transparency control is missing or ambiguous')
    else:
        texts,radios=theme._controls(page,plan,'instructor')
        panel=theme._one(page.locator('div.w-full.p-2:has(> button#ins-sync-data)'),
            'Native Instructor inspector owner changed')
        if panel.locator(':scope > button#ins-sync-data').count()!=1:
            raise Stop('Native Instructor inspector sync anchor changed')
        # The native DOM duplicates instructor-headshot on a DIV and IMG.
        # Binding the tag is required; a global #id selector is ambiguous.
        active=theme._one(page.locator('.instructor-card[data-active="true"]'),
            'Native Instructor active preview owner changed')
        preview=theme._one(active.locator('img#instructor-headshot'),'Native Instructor headshot image binding changed')
        state={key:theme._read_radio(row,values) for key,(row,values) in radios.items()}
        if state.get('instructor_visible')!='Show' or state.get('headshot_visible')!='Show':
            raise Stop('Native Instructor PNG upload requires the captured visible instructor/headshot state')
        controls={'text':{key:control.input_value() for key,control in texts.items()},'visibility':state,
            **_visible_controls(panel,color_count=5,slider_count=0)}
    theme._identity(page,plan);assert_tenant(page,plan)
    inspector=theme._one(panel.get_by_role('img',name='Offer poster',exact=True),'Native section upload preview changed')
    upload=theme._one(panel.get_by_role('button',name='Upload Image',exact=True),'Native section Upload Image is missing or ambiguous')
    remove=theme._one(panel.get_by_role('button',name='Remove',exact=True),'Native section Remove control changed')
    controls['remove_enabled']=remove.is_enabled()
    return upload,{'inspector_url':media._url(inspector.get_attribute('src')),
        'preview_url':media._url(preview.get_attribute('src')),'controls':controls}


def _snapshot(page,plan):
    return {section:_open_section(page,plan,section)[1] for section in SECTIONS}


def _protected(page,plan):
    inventory=blocks._inventory(page,plan)
    return {'theme':theme._snapshot(page,plan),'body_inventory':inventory,'body':blocks._snapshot(page,plan,inventory)}


def configure(page,step):
    plan=validate(step);assets=plan['theme_images']['images']
    contents=[media._bytes(asset) for asset in assets]
    if any(len(content)>=10*1024*1024 for content in contents):
        raise Stop('Native section PNG sources must be smaller than 10 MiB')
    active=theme._open(page,plan,plan['expected_template_title']);protected=_protected(page,plan)
    before=_snapshot(page,plan)
    for section,expected in plan['theme_images']['expected'].items():
        if {key:before[section][key] for key in expected}!=expected:
            raise Stop('Native section inspector/rendered image URLs differ from inventoried previous values')
    desired=deepcopy(before)
    with tempfile.TemporaryDirectory(prefix='skill6-course-section-images-') as temporary:
        paths=[]
        for index,content in enumerate(contents):
            path=Path(temporary)/('approved-section-'+str(index)+'.png');path.write_bytes(content);path.chmod(0o600);paths.append(path)
        for asset,path,content in zip(assets,paths,contents):
            if _snapshot(page,plan)!=desired or _protected(page,plan)!=protected:
                raise Stop('Native section media/siblings changed before the next upload')
            section=asset['section']
            def inspect(page,plan):
                control,current=_open_section(page,plan,section)
                return control,{'url':current['inspector_url']}
            new=upload_captured_image(page,plan,path,len(content),inspect=inspect,
                expected_url=desired[section]['inspector_url'])
            _,current=_open_section(page,plan,section)
            if (current['inspector_url']!=new['url'] or current['preview_url']!=new['url']
                    or current['preview_url']==desired[section]['preview_url']):
                raise Stop('Native upload did not bind a new shared inspector/rendered section image')
            old_controls=desired[section]['controls'];new_controls=current['controls']
            # Remove availability belongs to the image, not an authored user
            # setting. It is read back, while all other controls are preserved.
            if ({key:value for key,value in new_controls.items() if key!='remove_enabled'}
                    !={key:value for key,value in old_controls.items() if key!='remove_enabled'}):
                raise Stop('Native image upload changed protected section text/visibility/colors/transparency')
            desired[section]=current
            if _snapshot(page,plan)!=desired or _protected(page,plan)!=protected:
                raise Stop('Native section upload changed a sibling image or unrelated template settings')
    theme._identity(page,plan);assert_tenant(page,plan)
    save=theme._one(page.get_by_role('button',name='Save',exact=True),'Native template Save changed')
    if not save.is_enabled():raise Stop('Native section PNG uploads did not enable Save')
    click(save);wait_until(lambda:not save.is_enabled(),'Native section-media Save did not settle')
    try:page.wait_for_load_state('networkidle',timeout=45000)
    except Exception:raise Stop('Native section-media Save remains unsettled; reconcile before another upload') from None
    reopened=theme._open(page,plan,plan['expected_template_title'])
    if reopened!=active or _snapshot(page,plan)!=desired or _protected(page,plan)!=protected:
        raise Stop('Native section media did not persist after independent reopen or protected siblings changed')
    result={'status':'COURSE_SECTION_MEDIA_SAVED_AND_REOPENED','editor_url':page.url,
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'images':[{'section':asset['section'],'source_sha256':asset['sha256'],
            'inspector_url_sha256':_sha(desired[asset['section']]['inspector_url']),
            'preview_url_sha256':_sha(desired[asset['section']]['preview_url'])} for asset in assets],
        'functional_verified':False,'activation_performed':False}
    return validate_receipt(result,step)
