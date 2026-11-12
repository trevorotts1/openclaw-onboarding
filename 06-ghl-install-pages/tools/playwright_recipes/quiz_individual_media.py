"""Captured media in one existing Individual category result section."""
from copy import deepcopy
import re
from playwright_recipes.skill6_playwright import Stop,click,fill,wait_until
from playwright_recipes.assessments import reopen_editor,read_editor_title
from playwright_recipes import quiz_results as result

PLACEMENTS=('Left center','Right center','Top','Bottom','Left fixed','Right fixed')


def validate(value):
    keys={'category','expected','changes'}
    if not isinstance(value,dict) or set(value) not in (keys,keys|{'expected_target'}):
        raise Stop('Individual category media needs exact category and previous/desired state')
    if not isinstance(value['category'],str) or not value['category'].strip() or value['category']!=value['category'].strip():
        raise Stop('Individual category media needs an exact existing category name')
    states=('expected','changes')+ (('expected_target',) if 'expected_target' in value else ())
    for key in states:
        state=value[key]
        if (not isinstance(state,dict) or set(state)!={'type','url','placement'}
                or state['type'] not in ('image','video') or state['placement'] not in PLACEMENTS):
            raise Stop('Individual category media needs exact type, HTTPS URL and captured placement')
        result._https(state['url'])
    if value['expected']['type']!=value['changes']['type']:
        if 'expected_target' not in value or value['expected_target']['type']!=value['changes']['type']:
            raise Stop('Changing media type requires the exact inactive target URL and placement')
    elif 'expected_target' in value:
        raise Stop('Inactive target inventory is used only for a media-type change')
    return deepcopy(value)


def _pane(modal,category):
    # The explicit category is opened from the existing result section list.
    owner=result._one(modal.locator('#section-list'),'Individual category section list changed')
    group=result._one(owner.locator('.n-collapse-item').filter(
        has=owner.get_by_role('button',name='Individual category',exact=True)),
        'Individual category result section owner changed')
    button=group.get_by_role('button',name=category,exact=True)
    if button.count()!=1 or not button.is_visible():
        click(result._one(group.get_by_role('button',name='Individual category',exact=True),
                          'Individual category section opener changed'))
    button=result._one(button,'Exact Individual category result owner changed')
    click(button)
    classes=(button.get_attribute('class') or '').split()
    if '!text-primary-700' not in classes or '!bg-primary-50' not in classes:
        raise Stop('Individual category selected owner did not settle')
    return result._one(modal.locator('#individual-category-settings'),
                       'Individual category result inspector changed')


def _read(panel):
    label=result._one(panel.get_by_text('Image / video',exact=True),'Individual media visibility label changed')
    switch=result._one(label.locator('..').get_by_role('switch'),'Individual media visibility owner changed')
    if switch.get_attribute('aria-checked')!='true':
        raise Stop('Individual media must be enabled in this captured profile')
    selected=[]
    for kind in ('image','video'):
        control=result._one(panel.locator('#'+kind+'-placement input[type="radio"]'),
                            'Individual media type control changed')
        if control.get_attribute('value')!=kind:raise Stop('Individual media type identity changed')
        if control.is_checked():selected.append(kind)
    if len(selected)!=1:raise Stop('Individual media type is missing or ambiguous')
    chosen=[]
    for name in PLACEMENTS:
        label=result._one(panel.get_by_text(name,exact=True),'Individual media placement inventory changed')
        if 'text-blue-600' in (label.get_attribute('class') or '').split():chosen.append(name)
    if len(chosen)!=1:raise Stop('Individual media placement is missing or ambiguous')
    source=result._one(panel.locator('#bgImage[name="bgImage"]'),'Individual media URL field changed')
    content=result._one(panel.locator('#richTextEditor .tiptap.ProseMirror[contenteditable="true"]'),
                        'Individual category protected content owner changed')
    return {'type':selected[0],'url':result._https(source.input_value()),'placement':chosen[0]},content.inner_html()


def _protected(panel):
    fields=panel.locator('input:not(#bgImage):not([name="video-placement"]), textarea, select').evaluate_all(
        'nodes=>nodes.map(n=>({tag:n.tagName,type:n.type||null,value:n.value,checked:!!n.checked,disabled:!!n.disabled}))')
    switches=panel.locator('[role="switch"]').evaluate_all(
        'nodes=>nodes.filter(n=>n.parentElement.innerText.trim()!=="Image / video").map(n=>n.getAttribute("aria-checked"))')
    if not isinstance(fields,list) or not isinstance(switches,list) or any(s not in ('true','false') for s in switches):
        raise Stop('Individual category protected field inventory is unreadable')
    return {'fields':fields,'switches':switches}


def _write(panel,plan,before,markup):
    desired=plan['changes'];current=before
    if current['type']!=desired['type']:
        radio=result._one(panel.locator('#'+desired['type']+'-placement input[type="radio"]'),
                          'Individual media target type changed')
        if not radio.is_enabled():raise Stop('Individual media target type is disabled')
        click(result._one(panel.locator('#'+desired['type']+'-placement'),'Individual media target label changed'))
        wait_until(lambda:_read(panel)[0]['type']==desired['type'],'Individual media type did not settle')
        current,content=_read(panel)
        if current!=plan['expected_target'] or content!=markup:
            raise Stop('Inactive individual media or protected content differs from exact inventory')
    if current['placement']!=desired['placement']:
        control=result._one(panel.get_by_text(desired['placement'],exact=True).locator('..'),
                            'Individual media target placement changed')
        click(control)
        wait_until(lambda:_read(panel)[0]['placement']==desired['placement'],'Individual media placement did not settle')
    if current['url']!=desired['url']:
        source=result._one(panel.locator('#bgImage[name="bgImage"]'),'Individual media URL field changed')
        if not source.is_enabled() or source.get_attribute('readonly') is not None:
            raise Stop('Individual media URL is not editable')
        fill(source,desired['url']);source.press('Tab')
    if _read(panel)!=(desired,markup):raise Stop('Individual media changed protected content or did not settle')


def _verify_inactive(panel,plan,markup,protected):
    if plan['expected']['type']==plan['changes']['type']:return
    previous=plan['expected']['type'];current=plan['changes']['type']
    click(result._one(panel.locator('#'+previous+'-placement'),
                      'Individual media inactive type control changed'))
    wait_until(lambda:_read(panel)[0]['type']==previous,'Individual inactive media did not settle')
    old,content=_read(panel)
    if old['url']!=plan['expected']['url'] or content!=markup or _protected(panel)!=protected:
        raise Stop('Individual media changed the protected inactive URL or content')
    click(result._one(panel.locator('#'+current+'-placement'),
                      'Individual media desired type control changed'))
    wait_until(lambda:_read(panel)[0]['type']==current,'Individual desired media did not settle')
    if _read(panel)!=(plan['changes'],markup) or _protected(panel)!=protected:
        raise Stop('Individual media changed while verifying the inactive variant')


def configure(page,step):
    plan=validate(step['result_page']['individual_category_media']);editor_url=page.url
    parsed=result.urlsplit(editor_url)
    if (parsed.scheme!='https' or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.port not in (None,443)
            or not re.fullmatch(r'/v2/location/[A-Za-z0-9_-]+/quiz-builder-v2/[A-Za-z0-9_-]+/?',parsed.path)):
        raise Stop('Individual media requires an exact native quiz editor URL')
    frame=page.frame_locator('iframe[name="quiz-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True);title.wait_for(state='visible',timeout=45000)
    name=read_editor_title(title)
    if not isinstance(name,str) or not name.strip():raise Stop('Quiz editor identity unavailable')
    def identity():
        if page.url!=editor_url or read_editor_title(title)!=name:raise Stop('Quiz editor identity changed')
    def open_results():
        identity();existing=frame.get_by_role('dialog')
        if existing.count():
            if (existing.count()!=1 or existing.get_by_text('Form Element',exact=True).count()
                    +existing.get_by_text('Quiz Element',exact=True).count()!=1):
                raise Stop('Unexpected quiz modal requires reconciliation')
            click(result._one(existing.get_by_role('button',name='Close',exact=True),'Initial quiz drawer close changed'))
        click(result._one(frame.get_by_role('button',name='Edit Template',exact=True),'Result template opener changed'))
        modal=result._one(frame.get_by_role('dialog',name='UI Modal',exact=True),'Result template modal changed')
        modal.get_by_text('Customise result page',exact=True).wait_for(state='visible',timeout=45000)
        return modal
    modal=open_results();panel=_pane(modal,plan['category']);before,markup=_read(panel);protected=_protected(panel)
    if before!=plan['expected']:raise Stop('Individual media differs from exact previous state')
    identity();_write(panel,plan,before,markup)
    if _protected(panel)!=protected:raise Stop('Individual media changed protected category fields')
    _verify_inactive(panel,plan,markup,protected)
    identity();save=result._one(modal.get_by_role('button',name='Save',exact=True),'Result modal Save changed')
    if not save.is_enabled():raise Stop('Individual media remains invalid')
    click(save);modal.wait_for(state='hidden',timeout=45000)
    outer=result._one(frame.get_by_role('button',name='Save',exact=True),'Quiz Save changed');click(outer)
    wait_until(lambda:outer.is_enabled(),'Quiz outer Save did not settle')
    reopen_editor(page,'quiz',name,editor_url);title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000);modal=open_results();panel=_pane(modal,plan['category'])
    if _read(panel)!=(plan['changes'],markup) or _protected(panel)!=protected:
        raise Stop('Individual media did not persist or protected category fields changed')
    _verify_inactive(panel,plan,markup,protected)
    click(result._one(modal.get_by_role('button',name='Cancel',exact=True),'Result modal Cancel changed'))
    modal.wait_for(state='hidden',timeout=45000)
    return {'status':'QUIZ_RESULTS_SAVED_AND_REOPENED','kind':'quiz_results','editor_url':page.url,
            'configuration_sha256':result.configuration_hash(step),'independent_readback':'VERIFIED',
            'behavior_verified':False,'submission_verified':False}
