"""Native draft Facebook Pixel ID/events settings captured November 9, 2026.

No preview, form submission, network Pixel test, or external event is initiated.
The parent runner owns tenant identity, writer leases and uncertain journals.
"""
from copy import deepcopy
import hashlib
import json
import re

if __package__:
    from .assessments import reopen_editor
    from .field_placement import _close_initial
    from .skill6_playwright import Stop, click, fill, form_builder, wait_until
else:
    from assessments import reopen_editor
    from field_placement import _close_initial
    from skill6_playwright import Stop, click, fill, form_builder, wait_until


EVENTS=frozenset(('AddToWishlist','CompleteRegistration','Contact','CustomizeProduct',
    'Donate','FindLocation','InitiateCheckout','Lead','Page View','Purchase',
    'Schedule','Search','StartTrial','Submit Application','Subscribe'))
SELECTORS={'page_view_event':'#facebookEventsPageView',
           'submission_event':'#facebokEventsSubmission'}
MENU='.n-base-select-menu.n-select-menu:visible'
SCROLLER='.n-virtual-list.v-vl'


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','tracking'}
            or step.get('action','native_form_tracking')!='native_form_tracking'):
        raise Stop('Unsupported native form tracking action')
    data=step.get('tracking')
    if not isinstance(data,dict) or set(data)!={'expected','changes'}:
        raise Stop('Native tracking requires expected and changes objects')
    previous,desired=data['expected'],data['changes']
    if (not isinstance(previous,dict) or not isinstance(desired,dict) or not desired
            or set(previous)!=set(desired)
            or set(desired)-{'pixel_id','page_view_event','submission_event'}):
        raise Stop('Tracking previous and desired values must use identical nonempty captured keys')
    for values in (previous,desired):
        for key,value in values.items():
            if key=='pixel_id':
                if not isinstance(value,str) or (value!='' and not re.fullmatch(r'[0-9]{1,64}',value)):
                    raise Stop('Facebook Pixel ID must be an explicit numeric string or empty to clear')
            elif not isinstance(value,str) or value not in EVENTS:
                raise Stop('Tracking event must use an exact captured native option label')
    return deepcopy(step)


def configuration_hash(step):
    valid=validate(step)
    return hashlib.sha256(json.dumps(valid['tracking'],sort_keys=True,
        separators=(',',':')).encode()).hexdigest()


def _one(node,reason):
    if node.count()!=1:raise Stop(reason)
    return node


def _event(node):
    selected=_one(node.locator('.n-base-selection-input'),
                  'Native tracking selected event structure changed')
    content=_one(selected.locator('.n-base-selection-input__content'),
                 'Native tracking selected event text is missing or ambiguous')
    title,text=selected.get_attribute('title'),(content.inner_text() or '').strip()
    if not isinstance(title,str) or title!=text or title not in EVENTS:
        raise Stop('Native tracking selected event is unknown or inconsistent')
    return title


def _read(frame):
    pixel=_one(frame.locator('#facbookPixelId').get_by_placeholder(
        'Enter Facebook Pixel ID',exact=True),'Native Facebook Pixel ID control changed')
    if not pixel.is_visible():raise Stop('Native Facebook Pixel ID is not visible in Settings')
    value=pixel.input_value()
    if not isinstance(value,str) or (value!='' and not re.fullmatch(r'[0-9]{1,64}',value)):
        raise Stop('Existing native Facebook Pixel ID requires reconciliation')
    controls={'pixel_id':pixel}
    state={'pixel_id':value}
    for key,selector in SELECTORS.items():
        control=_one(frame.locator(selector),'Native tracking event selector changed: '+key)
        if not control.is_visible():raise Stop('Native tracking event selector is not visible: '+key)
        controls[key],state[key]=control,_event(control)
    return controls,state


def _choose(frame,node,label):
    """Bounded scan of the captured native virtualized option list.

    Scroll only the visible select menu, never the entire Settings page. Every
    candidate is selected by its exact displayed option label. Unknown or
    incomplete menus stop before the form Save.
    """
    click(node)
    menu=_one(frame.locator(MENU),'Native tracking event menu is absent or ambiguous')
    scroller=_one(menu.locator(SCROLLER),'Native tracking virtual option list changed')
    scroller.evaluate('el => { el.scrollTop = 0; }')
    last_top=-1
    for _ in range(20):
        metrics=scroller.evaluate('''el => new Promise(resolve => requestAnimationFrame(() =>
            resolve({top:el.scrollTop,height:el.clientHeight,total:el.scrollHeight})))''')
        if (not isinstance(metrics,dict) or set(metrics)!={'top','height','total'}
                or any(type(metrics[k]) not in (int,float) for k in metrics)
                or metrics['height']<=0 or metrics['total']<metrics['height']):
            raise Stop('Native tracking option scroll geometry is unavailable')
        option=menu.locator('.n-base-select-option').get_by_text(label,exact=True)
        if option.count()>1:
            raise Stop('Native tracking event option is ambiguous: '+label)
        if option.count()==1 and option.is_visible():
            click(option)
            wait_until(lambda:_event(node)==label,'Native tracking event selection did not stick')
            return
        maximum=metrics['total']-metrics['height']
        if metrics['top']>=maximum-1 or metrics['top']<=last_top:
            break
        last_top=metrics['top']
        target=min(maximum,metrics['top']+max(1,metrics['height']*0.75))
        scroller.evaluate('(el,top) => { el.scrollTop=top; }',target)
    raise Stop('Requested native tracking event is absent from the bounded option inventory: '+label)


def configure(page,step):
    plan=validate(step)
    frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or not title.input_value().strip():
        raise Stop('Native tracking form identity is unavailable')
    name,editor_url=title.input_value(),page.url

    def identity():
        if page.url!=editor_url or title.count()!=1 or title.input_value()!=name:
            raise Stop('Native tracking form identity changed')

    def open_settings():
        _close_initial(frame)
        click(frame.get_by_role('tab',name='Settings',exact=True))

    open_settings()
    controls,before=_read(frame)
    data=plan['tracking']
    if any(before[key]!=value for key,value in data['expected'].items()):
        raise Stop('Native tracking differs from the inventoried previous values')
    desired={**before,**data['changes']}
    if _read(frame)[1]!=before:
        raise Stop('Native tracking changed after preflight')
    for key,value in data['changes'].items():
        identity()
        if before[key]==value:continue
        if key=='pixel_id':fill(controls[key],value)
        else:_choose(frame,controls[key],value)
    if _read(frame)[1]!=desired:
        raise Stop('Native tracking desired state or preserved event values changed before Save')
    identity()
    save=_one(frame.get_by_role('button',name='Save',exact=True),'Native tracking outer Save changed')
    click(save)
    wait_until(lambda:save.is_enabled(),'Native tracking form Save did not finish')
    reopen_editor(page,'form',name,editor_url)
    frame=form_builder(page)
    open_settings()
    if _read(frame)[1]!=desired:
        raise Stop('Native tracking settings did not persist after independent reopen')
    return {'status':'FORM_TRACKING_SAVED_AND_REOPENED','editor_url':page.url,
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False}
