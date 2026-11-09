"""Create native quiz Short Answer questions from the captured TEXT tile.

This uses native quiz authoring without a separate contact-field API provision. Canvas text
inputs expose no field id/name, so identity comes from the complete ordered
page/question inventory and independently opened native Query Key properties.
The parent runner owns the tenant lease and intent-before-insertion journal.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

if __package__:
    from .assessments import reopen_editor
    from .skill6_playwright import Stop,assert_tenant,click,fill,wait_until
else:
    from assessments import reopen_editor
    from skill6_playwright import Stop,assert_tenant,click,fill,wait_until


COMMON={'location_id','location_name','start_url'}
OWNER={'expected_quiz_name','pages','target_page','questions'}
PROPERTIES={'field_type','question','placeholder','short_label','query_key','required','hidden'}
CANVAS='#the-form-builder.form-element.form-builder--wrap > .drop > .builder_sub_container'
ITEMS=':scope > .smooth-dnd-draggable-wrapper.element-box.menu-field-wrap.col-12 > .menu-item > .menu-item > .form-builder--item'
PAGE_HEADING='.builder-form-name > div:first-child > div.flex.items-center.text-sm.font-semibold'
FIELD_INPUTS={'question':'#fieldTitle input','placeholder':'#fieldPlaceholder input',
              'short_label':'#shortLabel input','query_key':'#fieldQueryKey input'}
FLAGS={'required':'#fieldRequired[role="checkbox"]','hidden':'#fieldCheckbox[role="checkbox"]'}


def _text(value,*,empty=False):
    return (isinstance(value,str) and (empty or bool(value.strip())) and len(value)<=1000
            and not any(ord(c)<32 for c in value))


def _question(value,*,new=False):
    if not isinstance(value,dict) or set(value)!=PROPERTIES:
        raise Stop('Every quiz question needs its complete exact type/text/key/flags inventory')
    if not isinstance(value['field_type'],str) or value['field_type'] not in ({'TEXT'} if new else {'TEXT','RADIO'}):
        raise Stop('Short Answer creation supports captured TEXT with existing TEXT/RADIO inventory only')
    if (not _text(value['question']) or not _text(value['placeholder'],empty=True)
            or not _text(value['short_label'],empty=True)
            or not isinstance(value['query_key'],str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,256}',value['query_key'])
            or type(value['required']) is not bool or type(value['hidden']) is not bool):
        raise Stop('Authored quiz properties require explicit text, unique query tokens and Boolean flags')
    return deepcopy(value)


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','quiz_short_answers')!='quiz_short_answers'):
        raise Stop('Unsupported quiz Short Answer runner metadata')
    payload=step.get('payload')
    if not isinstance(payload,dict) or set(payload)!=COMMON|OWNER:
        raise Stop('Short Answer creation requires exact existing quiz/page identities and full inventory')
    loc=payload['location_id']
    if not isinstance(loc,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',loc):raise Stop('Quiz location ID is invalid')
    for key in ('location_name','expected_quiz_name'):
        if not _text(payload[key]) or payload[key]!=payload[key].strip():raise Stop('Quiz identity label is unavailable')
    try:
        url=urlsplit(payload['start_url']);port=url.port
    except (TypeError,ValueError):raise Stop('Short Answer quiz editor URL is malformed') from None
    if (url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None
            or port not in (None,443) or url.query or url.fragment
            or not re.fullmatch('/v2/location/'+re.escape(loc)+r'/quiz-builder-v2/[A-Za-z0-9_-]+',url.path)):
        raise Stop('Short Answer authoring must bind its exact existing native quiz editor URL')
    pages=payload['pages'];target=payload['target_page'];new=payload['questions']
    if (not isinstance(pages,list) or not pages or type(target) is not int or not 1<=target<=len(pages)
            or not isinstance(new,list) or not new):
        raise Stop('Quiz Short Answers require existing complete pages and at least one authored question')
    labels=[];old=[]
    for page in pages:
        if not isinstance(page,dict) or set(page)!={'label','questions'} or not _text(page['label']) or not isinstance(page['questions'],list):
            raise Stop('Quiz pages require their exact ordered labels and question inventories')
        labels.append(page['label']);old.extend(_question(q) for q in page['questions'])
    desired=[_question(q,new=True) for q in new]
    if len(labels)!=len(set(labels)):raise Stop('Quiz page labels must be unique')
    for key in ('question','query_key'):
        before=[q[key].casefold() for q in old];after=[q[key].casefold() for q in desired]
        if len(before)!=len(set(before)) or len(after)!=len(set(after)) or set(before).intersection(after):
            raise Stop('Quiz existing/new question labels and Query Keys must be unambiguous and disjoint')
    if any(q['query_key'].casefold()=='single_line' for q in old+desired):
        raise Stop('Reserved Short Answer default Query Key must be unoccupied before native insertion')
    return deepcopy(payload)


def configuration_hash(step):
    payload=validate(step)
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _one(node,reason):
    if node.count()!=1 or not node.is_visible():raise Stop(reason)
    return node


def _close_drawer(frame):
    dialog=frame.get_by_role('dialog')
    if not dialog.count():return
    if dialog.count()!=1 or dialog.get_by_text('Quiz Element',exact=True).count()!=1:
        raise Stop('An unrelated quiz dialog requires reconciliation')
    click(_one(dialog.get_by_role('button',name='Close',exact=True),'Native Quiz Element close control changed'))
    dialog.wait_for(state='hidden',timeout=45000)


def _close_properties(frame,*,required=False):
    backs=frame.get_by_role('button',name='Back',exact=True)
    if backs.count()==2:click(backs.nth(1))
    elif required or backs.count()!=1:raise Stop('Native quiz property Back controls changed')


def _owners(frame,plan):
    pages=frame.locator('.survey-form-container.flex')
    if (pages.count()!=len(plan['pages'])
            or frame.locator('.survey-form-container').count()!=pages.count()):
        raise Stop('Native quiz page inventory changed or contains an uncaptured owner shape')
    owners=[]
    for index,expected in enumerate(plan['pages']):
        page=pages.nth(index);label=page.locator(PAGE_HEADING)
        if label.count()!=1 or label.inner_text().strip()!=expected['label']:
            raise Stop('Native quiz page order/label differs from its intended owner')
        canvas=page.locator(CANVAS)
        _one(canvas,'Native quiz page canvas is absent or ambiguous')
        owners.append((page,canvas))
    return owners


def _items(canvas):
    items=canvas.locator(ITEMS)
    wrappers=canvas.locator(':scope > .smooth-dnd-draggable-wrapper')
    if wrappers.count()!=items.count():
        raise Stop('Native quiz canvas contains an uncaptured question width/wrapper; complete inventory required')
    return items


def _item_kind(item):
    label=_one(item.get_by_role('textbox',name='Label',exact=True),'Native quiz question Label is missing or ambiguous')
    kind=label.get_attribute('data-field-type')
    if kind not in ('TEXT','RADIO'):raise Stop('An existing quiz widget needs a separate type capture')
    return label,kind


def _radio_options(frame):
    """Read the existing quiz_ui option-row anchors without opening choices.

    Preserve even unassigned/disabled score states verbatim; Short Answer
    insertion has no authority to rename options, select categories or score.
    """
    pickers=frame.locator('[id="category-picker"]')
    scores=frame.get_by_role('textbox',name='10',exact=True)
    if pickers.count()<1 or scores.count()!=pickers.count():
        raise Stop('Existing RADIO option category/score inventory is incomplete')
    result=[]
    for index in range(pickers.count()):
        picker=_one(pickers.nth(index),'Existing RADIO category picker changed')
        row=picker.locator('..').locator('..').locator('..').locator('..')
        label=_one(row.get_by_role('textbox',name='Label',exact=True),
            'Existing RADIO option label owner is missing or ambiguous')
        score=_one(row.get_by_role('textbox',name='10',exact=True),
            'Existing RADIO score no longer belongs to its exact option row')
        values={'label':label.input_value(),'category':picker.inner_text().strip(),
            'score':score.input_value(),'score_enabled':score.is_enabled()}
        if (not _text(values['label']) or not _text(values['category'],empty=True)
                or not _text(values['score'],empty=True) or type(values['score_enabled']) is not bool):
            raise Stop('Existing RADIO option values are unreadable')
        result.append(values)
    return result


def _read_question(frame,item):
    _close_properties(frame)
    label,kind=_item_kind(item);click(label)
    active=frame.locator('.form-builder--item[data-active="true"]')
    wait_until(lambda:active.count()==1 and item.get_attribute('data-active')=='true',
        'Native quiz question selection is ambiguous')
    click(_one(frame.get_by_role('button',name='Open settings',exact=True),'Native quiz Open settings control changed'))
    result={'field_type':kind}
    for key,selector in FIELD_INPUTS.items():
        result[key]=_one(frame.locator(selector),'Native quiz '+key+' property control changed').input_value()
    for key,selector in FLAGS.items():
        flag=_one(frame.locator(selector),'Native quiz '+key+' checkbox changed')
        value=flag.get_attribute('aria-checked')
        if value not in ('true','false'):raise Stop('Native quiz Boolean property state is unavailable')
        result[key]=value=='true'
    _question(result)
    text=label.inner_text().strip()
    if text not in (result['question'],result['question']+'*' if result['required'] else result['question'],
                    result['question']+' *' if result['required'] else result['question']):
        raise Stop('Native canvas label and selected question property disagree')
    result['_widget_inputs']=item.locator('input,select,textarea').evaluate_all('''nodes=>nodes.map(n=>({tag:n.tagName,
        name:n.getAttribute('name'),type:n.getAttribute('type'),value:n.value,placeholder:n.getAttribute('placeholder')}))''')
    if not isinstance(result['_widget_inputs'],list):raise Stop('Native quiz widget input identity is unavailable')
    if kind=='RADIO':result['_radio_options']=_radio_options(frame)
    _close_properties(frame,required=True)
    return result


def _inventory(frame,plan):
    _close_drawer(frame);click(frame.get_by_role('tab',name='Edit',exact=True))
    result=[]
    for _,canvas in _owners(frame,plan):
        items=_items(canvas);count=items.count();questions=[]
        if not count:
            empty=canvas.get_by_text('Drag and drop components',exact=True)
            _one(empty,'Empty native quiz page is not confirmed by its captured drop placeholder')
        for index in range(count):
            if items.count()!=count:raise Stop('Quiz questions changed during inventory')
            questions.append(_read_question(frame,items.nth(index)))
        result.append(questions)
    return result


def _properties_only(inventory):
    return [[{key:q[key] for key in PROPERTIES} for q in page] for page in inventory]


def _append(frame,plan):
    _close_properties(frame)
    dialog=frame.get_by_role('dialog')
    if not dialog.count():
        click(_one(frame.get_by_role('button',name='Add Quiz Element',exact=True),'Native Add Quiz Element changed'))
        dialog=frame.get_by_role('dialog');dialog.wait_for(state='visible',timeout=45000)
    if dialog.count()!=1 or dialog.get_by_text('Quiz Element',exact=True).count()!=1:
        raise Stop('Native Quiz Element drawer changed')
    click(_one(dialog.get_by_text('Quick Add',exact=True),'Native quiz Quick Add tab changed'))
    tile=dialog.locator('.gui__builder-card').filter(has=dialog.get_by_text('Short Answer',exact=True))
    _one(tile,'Native Short Answer tile is absent or ambiguous')
    if not re.fullmatch(r'Short Answer[0-9]+',tile.get_attribute('id') or ''):
        raise Stop('Native Short Answer tile identity changed')
    handle=_one(tile.locator('img.gui__builder-card--handler'),'Native Short Answer drag handle changed')
    if handle.get_attribute('draggable')!='false':raise Stop('Native Short Answer drag-handle shape changed')
    _,canvas=_owners(frame,plan)[plan['target_page']-1]
    items=_items(canvas);before=items.count()
    handle.scroll_into_view_if_needed();canvas.scroll_into_view_if_needed()
    box=canvas.bounding_box()
    last=items.nth(before-1).bounding_box() if before else None
    if (not box or box['width']<8 or box['height']<8 or before and not last):
        raise Stop('Native quiz append destination is not measurable')
    tail=(last['y']+last['height']-box['y']) if last else 0
    if not 0<=tail<=box['height']-8:
        raise Stop('Native quiz page has no captured safe inside-canvas append area')
    # One native pointer drag into the measured owner canvas below its last
    # question. Never drop beyond the footer and never repeat an uncertain drag.
    handle.drag_to(canvas,target_position={'x':box['width']/2,'y':(tail+box['height'])/2},timeout=45000)
    wait_until(lambda:items.count()==before+1,'Short Answer insertion did not append exactly one widget')
    _close_drawer(frame)
    item=items.nth(before);label,kind=_item_kind(item)
    if (kind!='TEXT' or not re.fullmatch(r'Short Answer [a-z0-9]{6}',label.inner_text().strip())
            or item.get_attribute('data-active')!='true'):
        raise Stop('New Short Answer differs from its captured active native TEXT shape')
    field=item.locator('input.form-placeholder.form-control')
    if (field.count()!=1 or any(field.get_attribute(key) is not None for key in ('id','name','type'))
            or field.input_value()!=''):
        raise Stop('Native Short Answer input shape changed; no field identity is inferred')
    return item


def _write_question(frame,item,question):
    before=_read_question(frame,item)
    if (before['field_type']!='TEXT' or before['query_key']!='single_line'
            or before['placeholder'] or before['short_label'] or before['required'] or before['hidden']):
        raise Stop('New Short Answer default properties differ from capture')
    label,_=_item_kind(item);click(label)
    click(_one(frame.get_by_role('button',name='Open settings',exact=True),'Native new question settings changed'))
    for key,selector in FIELD_INPUTS.items():
        control=_one(frame.locator(selector),'Native Short Answer property changed')
        fill(control,question[key]);control.press('Tab')
        if control.input_value()!=question[key]:raise Stop('Native Short Answer ignored an authored property')
    for key,selector in FLAGS.items():
        flag=_one(frame.locator(selector),'Native Short Answer checkbox changed')
        value=flag.get_attribute('aria-checked')
        if value not in ('true','false') or not flag.is_enabled():raise Stop('Native Short Answer flag is unavailable')
        if (value=='true')!=question[key]:
            click(flag)
            wait_until(lambda:flag.get_attribute('aria-checked')==str(question[key]).lower(),
                       'Native Short Answer checkbox did not accept the requested state')
    _close_properties(frame,required=True)
    after=_read_question(frame,item)
    if {key:after[key] for key in PROPERTIES}!=question:
        raise Stop('New Short Answer properties differ before Save')
    return after


def configure(page,step):
    plan=validate(step);frame=page.frame_locator('iframe[name="quiz-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    def identity():
        if page.url!=plan['start_url'] or title.count()!=1 or title.input_value()!=plan['expected_quiz_name']:
            raise Stop('Short Answer quiz identity changed')
        assert_tenant(page,plan)
    title.wait_for(state='visible',timeout=45000);identity()
    before=_inventory(frame,plan)
    if _properties_only(before)!=[page['questions'] for page in plan['pages']]:
        raise Stop('Existing quiz questions differ from the complete expected inventory')
    desired=deepcopy(before);owner=plan['target_page']-1
    for question in plan['questions']:
        identity()
        if _inventory(frame,plan)!=desired:raise Stop('Quiz questions changed before the next insertion')
        item=_append(frame,plan);authored=_write_question(frame,item,question)
        desired[owner].append(authored)
        if _inventory(frame,plan)!=desired:
            raise Stop('Short Answer insertion changed existing questions or a different page')
    identity();save=_one(frame.get_by_role('button',name='Save',exact=True),'Native quiz Save changed')
    if not save.is_enabled():raise Stop('Native Short Answer configuration remains invalid')
    click(save)
    wait_until(lambda:save.is_enabled(),'Native quiz Save did not finish')
    page.wait_for_load_state('networkidle',timeout=45000)
    reopen_editor(page,'quiz',plan['expected_quiz_name'],plan['start_url'])
    frame=page.frame_locator('iframe[name="quiz-builder-app"]');title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000);identity()
    if _inventory(frame,plan)!=desired:raise Stop('New native Short Answers did not persist after independent reopen')
    return {'status':'QUIZ_SHORT_ANSWERS_SAVED_AND_REOPENED','kind':'quiz_short_answers',
        'editor_url':page.url,'configuration_sha256':configuration_hash(step),
        'question_count':len(plan['questions']),'target_page':plan['target_page'],
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False,
        'dependency_api_used':False}
