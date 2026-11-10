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
    from .assessments import reopen_editor,read_editor_title
    from .skill6_playwright import Stop,assert_tenant,click,fill,wait_until
else:
    from assessments import reopen_editor,read_editor_title
    from skill6_playwright import Stop,assert_tenant,click,fill,wait_until


COMMON={'location_id','location_name','start_url'}
OWNER={'expected_quiz_name','pages','target_page','questions'}
PAGE_CREATION={'create_page','new_page_label'}
PROPERTIES={'field_type','question','placeholder','short_label','query_key','required','hidden'}
CANVAS='#the-form-builder.form-element.form-builder--wrap > .drop > .builder_sub_container'
ITEMS=':scope > .smooth-dnd-draggable-wrapper.element-box.menu-field-wrap.col-12 > .menu-item > .menu-item > .form-builder--item'
PAGE_HEADING='.builder-form-name > div:first-child > div.flex.items-center.text-sm.font-semibold'
FIELD_INPUTS={'question':'#fieldTitle input','placeholder':'#fieldPlaceholder input',
              'short_label':'#shortLabel input','query_key':'#fieldQueryKey input'}
FLAGS={'required':'#fieldRequired[role="checkbox"]','hidden':'#fieldCheckbox[role="checkbox"]'}


def properties_for(kind):
    # The captured quiz Single Dropdown exposes Required and no Hidden
    # control. Absence of a supported setting is not a fabricated false value.
    if kind=='MULTIPLE_OPTIONS':return PROPERTIES-{'hidden','query_key'}|{'unique_key'}
    return PROPERTIES-{'hidden'} if kind=='SINGLE_OPTIONS' else PROPERTIES


def key_for(kind):
    return 'unique_key' if kind=='MULTIPLE_OPTIONS' else 'query_key'


def owner_keys(payload):
    return COMMON|OWNER|(PAGE_CREATION if set(payload).intersection(PAGE_CREATION) else set())


def _text(value,*,empty=False):
    return (isinstance(value,str) and (empty or bool(value.strip())) and len(value)<=1000
            and not any(ord(c)<32 for c in value))


def _question(value,*,new=False,field_types=None):
    if not isinstance(value,dict) or set(value)!=properties_for(value.get('field_type')):
        raise Stop('Every quiz question needs its complete exact type/text/key/flags inventory')
    if not isinstance(value['field_type'],str) or value['field_type'] not in (field_types if field_types is not None else {'TEXT'} if new else {'TEXT','RADIO'}):
        raise Stop('Short Answer creation supports captured TEXT with existing TEXT/RADIO inventory only')
    key=key_for(value['field_type']);token=value[key]
    token_valid=isinstance(token,str) and bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,256}',token))
    if key=='unique_key' and not new and token=='':token_valid=True
    if (not _text(value['question']) or not _text(value['placeholder'],empty=True)
            or not _text(value['short_label'],empty=True)
            or not token_valid
            or type(value['required']) is not bool or 'hidden' in value and type(value['hidden']) is not bool):
        raise Stop('Authored quiz properties require explicit text, literal native keys and Boolean flags')
    return deepcopy(value)


def validate(step,*,field_types=('TEXT','RADIO'),new_types=('TEXT',),reserved_key=None):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','quiz_short_answers')!='quiz_short_answers'):
        raise Stop('Unsupported quiz Short Answer runner metadata')
    payload=step.get('payload')
    if not isinstance(payload,dict) or set(payload)!=owner_keys(payload):
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
    create_page='create_page' in payload
    if create_page and (payload['create_page'] is not True or not _text(payload['new_page_label'])
            or payload['new_page_label']!=payload['new_page_label'].strip()):
        raise Stop('New empty-page mode requires explicit true and the exact expected new page label')
    if (not isinstance(pages,list) or not pages or type(target) is not int or not 1<=target<=len(pages)+int(create_page)
            or not isinstance(new,list) or not new):
        raise Stop('Quiz Short Answers require existing complete pages and at least one authored question')
    if create_page and (target!=len(pages)+1 or len(new)!=1):
        raise Stop('New empty-page mode authors exactly one question on one explicitly appended page')
    if create_page and payload['new_page_label']!='Page '+str(len(pages)+1):
        raise Stop('New page label must be the captured generated Page N+1 caption; this mode does not rename pages')
    labels=[];old=[]
    for page in pages:
        if not isinstance(page,dict) or set(page)!={'label','questions'} or not _text(page['label']) or not isinstance(page['questions'],list):
            raise Stop('Quiz pages require their exact ordered labels and question inventories')
        labels.append(page['label']);old.extend(_question(q,field_types=field_types) for q in page['questions'])
    desired=[_question(q,new=True,field_types=new_types) for q in new]
    if len(labels)!=len(set(labels)):raise Stop('Quiz page labels must be unique')
    if create_page and payload['new_page_label'] in labels:raise Stop('New page label collides with an existing page owner')
    before=[q['question'].casefold() for q in old];after=[q['question'].casefold() for q in desired]
    if len(before)!=len(set(before)) or len(after)!=len(set(after)) or set(before).intersection(after):
        raise Stop('Quiz existing/new question labels must be unambiguous and disjoint')
    def identities(questions):
        # Empty native Unique Key values are unknown; their placeholders are
        # preserved metadata, never a query key or a derived field identity.
        return [(key_for(q['field_type']),q[key_for(q['field_type'])].casefold())
                for q in questions if q[key_for(q['field_type'])]]
    before,after=identities(old),identities(desired)
    if len(before)!=len(set(before)) or len(after)!=len(set(after)) or set(before).intersection(after):
        raise Stop('Quiz authored keys must be unique and disjoint in their actual native property namespace')
    if reserved_key is not None and any(q['query_key'].casefold()==reserved_key.casefold() for q in old+desired):
        raise Stop('Reserved native question default Query Key must be unoccupied before insertion')
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


def _item_kind(item,*,field_types=('TEXT','RADIO')):
    label=_one(item.get_by_role('textbox',name='Label',exact=True),'Native quiz question Label is missing or ambiguous')
    kind=label.get_attribute('data-field-type')
    if kind not in field_types:raise Stop('An existing quiz widget needs a separate type capture')
    return label,kind


def _activate_item(frame,item,label):
    click(label)
    active=frame.locator('.form-builder--item[data-active="true"]')
    wait_until(lambda:active.count()==1 and item.get_attribute('data-active')=='true',
               'Native quiz question selection is ambiguous')


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


def _advanced_identity(frame):
    unique=frame.locator('#uniqueKey input');name=frame.locator('#custom-field-label input')
    if unique.count()>1 or name.count()>1:raise Stop('Native custom-field identity controls are ambiguous')
    if unique.count()!=1 or not unique.is_visible():
        header=frame.locator('div.n-collapse-item__header-main:visible').filter(
            has_text=re.compile(r'^\s*Advanced\s*Settings\s*$'))
        click(_one(header,'Native Advanced Settings opener changed'))
        wait_until(lambda:unique.count()==1 and unique.is_visible() and name.count()==1 and name.is_visible(),
                   'Native custom-field Advanced Settings did not expose its measured identity controls')
    _one(unique,'Native Unique Key input changed');_one(name,'Native Custom Field Name input changed')
    actual_name=name.input_value();placeholder=unique.get_attribute('placeholder')
    if not _text(actual_name) or not _text(placeholder):
        raise Stop('Native custom-field name or key placeholder cannot be preserved')
    return unique,name,{'_custom_field_name':actual_name,'_unique_key_placeholder':placeholder}


def _read_question(frame,item,*,field_types=('TEXT','RADIO'),metadata_reader=None):
    _close_properties(frame)
    label,kind=_item_kind(item,field_types=field_types);_activate_item(frame,item,label)
    click(_one(frame.get_by_role('button',name='Open settings',exact=True),'Native quiz Open settings control changed'))
    result={'field_type':kind}
    for key,selector in FIELD_INPUTS.items():
        if kind=='MULTIPLE_OPTIONS' and key=='query_key':
            if frame.locator(selector).count()!=0:raise Stop('Multi Dropdown unexpectedly exposes an unmeasured Query Key')
            continue
        result[key]=_one(frame.locator(selector),'Native quiz '+key+' property control changed').input_value()
    for key,selector in FLAGS.items():
        if key not in properties_for(kind):
            if frame.locator(selector).count()!=0:raise Stop('An unsupported dropdown Hidden control appeared')
            continue
        flag=_one(frame.locator(selector),'Native quiz '+key+' checkbox changed')
        value=flag.get_attribute('aria-checked')
        if value not in ('true','false'):raise Stop('Native quiz Boolean property state is unavailable')
        result[key]=value=='true'
    custom_identity={}
    if kind=='MULTIPLE_OPTIONS':
        unique,_,custom_identity=_advanced_identity(frame)
        result['unique_key']=unique.input_value()
    _question(result,field_types=field_types)
    text=label.inner_text().strip()
    if text not in (result['question'],result['question']+'*' if result['required'] else result['question'],
                    result['question']+' *' if result['required'] else result['question']):
        raise Stop('Native canvas label and selected question property disagree')
    result['_widget_inputs']=item.locator('input,select,textarea').evaluate_all('''nodes=>nodes.map(n=>({tag:n.tagName,
        name:n.getAttribute('name'),type:n.getAttribute('type'),value:n.value,placeholder:n.getAttribute('placeholder')}))''')
    if not isinstance(result['_widget_inputs'],list):raise Stop('Native quiz widget input identity is unavailable')
    if kind=='RADIO':result['_radio_options']=_radio_options(frame)
    result.update(custom_identity)
    if metadata_reader is not None:result.update(metadata_reader(frame,kind))
    _close_properties(frame,required=True)
    return result


def _prepare_inventory(frame):
    _close_drawer(frame);click(frame.get_by_role('tab',name='Edit',exact=True))


def _inventory(frame,plan,*,field_types=('TEXT','RADIO'),metadata_reader=None):
    _prepare_inventory(frame)
    result=[]
    for _,canvas in _owners(frame,plan):
        items=_items(canvas);count=items.count();questions=[]
        if not count:
            empty=canvas.get_by_text('Drag and drop components',exact=True)
            _one(empty,'Empty native quiz page is not confirmed by its captured drop placeholder')
        for index in range(count):
            if items.count()!=count:raise Stop('Quiz questions changed during inventory')
            questions.append(_read_question(frame,items.nth(index),field_types=field_types,metadata_reader=metadata_reader))
        result.append(questions)
    return result


def _properties_only(inventory):
    return [[{key:q[key] for key in properties_for(q['field_type'])} for q in page] for page in inventory]


def _wait_editor_identity(page,title,plan):
    def ready():
        if page.url!=plan['start_url']:raise Stop('Native quiz editor URL changed while loading')
        if title.count()>1:raise Stop('Native quiz title is ambiguous while loading')
        if title.count()==0:return False
        name=read_editor_title(title)
        if not name or not name.strip():return False
        if name!=plan['expected_quiz_name']:raise Stop('Native quiz title differs from its exact intended owner')
        return True
    wait_until(ready,'Native quiz owner did not finish loading')


def _wait_baseline(frame,plan,*,expected=None):
    """Wait only for missing loading DOM, never forgive a positive mismatch."""
    _prepare_inventory(frame)
    def ready():
        pages=frame.locator('.survey-form-container.flex')
        if pages.count()==0 and frame.locator('.survey-form-container').count()==0:return False
        for index in range(pages.count()):
            heading=pages.nth(index).locator(PAGE_HEADING)
            if heading.count()==0 or heading.count()==1 and not heading.inner_text().strip():return False
        for index,(_,canvas) in enumerate(_owners(frame,plan)):
            questions=expected[index] if expected is not None else plan['pages'][index]['questions'];items=_items(canvas)
            if items.count()==0 and questions:return False
            if items.count()!=len(questions):raise Stop('Loaded native quiz question count differs from its expected baseline')
            if not questions:
                marker=canvas.get_by_text('Drag and drop components',exact=True)
                if marker.count()==0:return False
                _one(marker,'Native empty quiz baseline marker is ambiguous')
            for offset,question in enumerate(questions):
                label=items.nth(offset).get_by_role('textbox',name='Label',exact=True)
                if label.count()==0:return False
                _one(label,'Native quiz baseline Label is ambiguous')
                value=label.inner_text().strip();kind=label.get_attribute('data-field-type')
                if not value or not kind:return False
                expected_kind='RADIO' if question['field_type']=='PICTURE_CHOICE' else question['field_type']
                if (kind!=expected_kind or value not in (question['question'],question['question']+'*',question['question']+' *')):
                    raise Stop('Loaded native quiz question owner differs from its expected baseline')
        return True
    wait_until(ready,'Native quiz baseline widgets did not finish loading')


def _target_page(frame,plan,before,inventory_reader):
    """Append one explicitly requested empty owner before its first question."""
    if not plan.get('create_page'):return plan,deepcopy(before)
    _prepare_inventory(frame);_close_properties(frame)
    if inventory_reader(frame,plan)!=before:raise Stop('Quiz baseline changed before the single Add Page action')
    owners=_owners(frame,plan)
    if frame.locator('#add-slide-button').count()!=len(owners):
        raise Stop('Native Add Page control inventory differs from the complete page owners')
    for owner,_ in owners:
        _one(owner.locator('button#add-slide-button'),'Native Add Page control is not scoped once to its exact page')
    add=owners[-1][0].locator('button#add-slide-button')
    runtime=deepcopy(plan);runtime['pages'].append({'label':plan['new_page_label'],'questions':[]})
    expected_count=len(runtime['pages'])
    click(add)
    def one_new_owner():
        count=frame.locator('.survey-form-container.flex').count()
        if count>expected_count or count<len(owners):raise Stop('Native Add Page changed an unexpected number of owners')
        return count==expected_count
    wait_until(one_new_owner,'Native Add Page did not append exactly one owner; do not repeat it')
    _wait_baseline(frame,runtime,expected=[*before,[]])
    new_owner,new_canvas=_owners(frame,runtime)[-1]
    _one(new_owner.locator('button#add-elements-button'),'New native empty page has no captured Add Elements control')
    _one(new_canvas.get_by_text('Drag and drop components',exact=True),'New native page lacks its positive empty canvas marker')
    if frame.locator('#add-slide-button').count()!=expected_count:
        raise Stop('New page Add Page controls do not match the exact owner count')
    after=inventory_reader(frame,runtime)
    if after!=[*before,[]]:raise Stop('Native Add Page changed existing questions or did not create an exact empty owner')
    return runtime,deepcopy(after)


def _prewrite_delta(frame,plan,before,inventory_reader,question):
    """Prove the appended index is new before touching any field properties."""
    after=inventory_reader(frame,plan);owner=plan['target_page']-1
    if len(after)!=len(before) or len(after[owner])!=len(before[owner])+1:
        raise Stop('Native question insertion did not produce the exact new-owner widget delta')
    for index,previous in enumerate(before):
        current=after[index][:-1] if index==owner else after[index]
        if current!=previous:
            raise Stop('Native question insertion changed an old prefix or another page before property authoring')
    if after[owner][-1]['field_type']!=question['field_type']:
        raise Stop('Native appended widget type changed before property authoring')


def _append_tile(frame,plan,tile_label,*,page=None):
    _close_properties(frame)
    dialog=frame.get_by_role('dialog')
    if not dialog.count():
        if plan.get('create_page'):
            owner,_=_owners(frame,plan)[plan['target_page']-1]
            opener=owner.locator('button#add-elements-button')
            _one(opener,'New native empty page Add Elements opener changed')
        else:
            opener=_one(frame.get_by_role('button',name='Add Quiz Element',exact=True),'Native Add Quiz Element changed')
        click(opener)
        dialog=frame.get_by_role('dialog');dialog.wait_for(state='visible',timeout=45000)
    if dialog.count()!=1 or dialog.get_by_text('Quiz Element',exact=True).count()!=1:
        raise Stop('Native Quiz Element drawer changed')
    click(_one(dialog.get_by_text('Quick Add',exact=True),'Native quiz Quick Add tab changed'))
    tile=dialog.locator('.gui__builder-card').filter(has=dialog.get_by_text(tile_label,exact=True))
    _one(tile,'Native Short Answer tile is absent or ambiguous')
    if not re.fullmatch(re.escape(tile_label)+r'[0-9]+',tile.get_attribute('id') or ''):
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
    if last:
        # Guarded attempted append geometry from the captured lower-edge drag.
        # Populated-page acceptance remains unresolved: this can create a new
        # page, which must stop before properties or Save. Normal canvases end
        # at their last wrapper, so a blank-tail requirement is not usable.
        x=last['x']+last['width']/2-box['x'];y=last['y']+last['height']-7-box['y']
        if last['width']<8 or last['height']<14:
            raise Stop('Native final question has no captured inside-edge drop area')
    else:x,y=box['width']/2,box['height']/2
    if not 1<=x<=box['width']-1 or not 1<=y<=box['height']-1:
        raise Stop('Native quiz page has no captured safe inside-canvas append area')
    if page is None:
        handle.drag_to(canvas,target_position={'x':x,'y':y},timeout=45000)
    else:
        source=handle.bounding_box()
        if not source or source['width']<=0 or source['height']<=0:
            raise Stop('Native quiz drag handle is not measurable')
        destination=(box['x']+x,box['y']+y)
        page.mouse.move(source['x']+source['width']/2,source['y']+source['height']/2)
        page.mouse.down()
        try:
            page.mouse.move(*destination,steps=15)
            # Smooth DnD's captured successful pointer path held the final
            # inside-edge point three times before releasing. One drag only.
            for _ in range(3):page.mouse.move(*destination)
        finally:page.mouse.up()
    def one_inserted():
        _owners(frame,plan)
        count=items.count()
        if count>before+1 or count<before:raise Stop('Native question drag changed an unexpected number of existing-owner widgets')
        return count==before+1
    wait_until(one_inserted,'Native question insertion did not append exactly one widget')
    _owners(frame,plan);_close_drawer(frame)
    return items.nth(before)


def _append(frame,plan,*,page=None):
    item=_append_tile(frame,plan,'Short Answer',page=page);label,kind=_item_kind(item)
    if kind!='TEXT' or not re.fullmatch(r'Short Answer [a-z0-9]{6}',label.inner_text().strip()):
        raise Stop('New Short Answer differs from its captured active native TEXT shape')
    field=item.locator('input.form-placeholder.form-control')
    if (field.count()!=1 or any(field.get_attribute(key) is not None for key in ('id','name','type'))
            or field.input_value()!=''):
        raise Stop('Native Short Answer input shape changed; no field identity is inferred')
    _activate_item(frame,item,label)
    return item


def _write_question(frame,item,question,*,field_types=('TEXT','RADIO'),new_kind='TEXT',default_key='single_line',metadata_reader=None,expected_metadata=None):
    before=_read_question(frame,item,field_types=field_types,metadata_reader=metadata_reader)
    if (before['field_type']!=new_kind or before[key_for(new_kind)]!=default_key
            or before['placeholder'] or before['short_label'] or before['required'] or before.get('hidden',False)):
        raise Stop('New native question default properties differ from capture')
    if expected_metadata is not None and any(before.get(key)!=value for key,value in expected_metadata.items()):
        raise Stop('New native custom-field identity metadata changed before property authoring')
    label,_=_item_kind(item,field_types=field_types);click(label)
    click(_one(frame.get_by_role('button',name='Open settings',exact=True),'Native new question settings changed'))
    for key,selector in FIELD_INPUTS.items():
        if new_kind=='MULTIPLE_OPTIONS' and key=='query_key':
            if frame.locator(selector).count()!=0:raise Stop('Multi Dropdown unexpectedly exposes an unmeasured Query Key')
            continue
        control=_one(frame.locator(selector),'Native question property changed')
        if control.input_value()!=question[key]:
            fill(control,question[key]);control.press('Tab')
        if control.input_value()!=question[key]:raise Stop('Native question ignored an authored property')
    for key,selector in FLAGS.items():
        if key not in properties_for(new_kind):
            if frame.locator(selector).count()!=0:raise Stop('An unsupported dropdown Hidden control appeared')
            continue
        flag=_one(frame.locator(selector),'Native question checkbox changed')
        value=flag.get_attribute('aria-checked')
        if value not in ('true','false') or not flag.is_enabled():raise Stop('Native question flag is unavailable')
        if (value=='true')!=question[key]:
            click(flag)
            wait_until(lambda:flag.get_attribute('aria-checked')==str(question[key]).lower(),
                       'Native question checkbox did not accept the requested state')
    if new_kind=='MULTIPLE_OPTIONS':
        unique,name,protected=_advanced_identity(frame)
        if any(protected[key]!=before[key] for key in protected):
            raise Stop('Question properties changed protected Custom Field Name or Unique Key placeholder')
        fill(unique,question['unique_key']);click(name)
        if unique.input_value()!=question['unique_key']:
            raise Stop('Native Multi Dropdown ignored the authored explicit Unique Key')
    _close_properties(frame,required=True)
    after=_read_question(frame,item,field_types=field_types,metadata_reader=metadata_reader)
    if {key:after[key] for key in properties_for(new_kind)}!=question:
        raise Stop('New native question properties differ before Save')
    for key in ('_radio_options','_choice_controls','_choice_switches','_custom_field_name','_unique_key_placeholder'):
        if before.get(key)!=after.get(key):
            raise Stop('Authoring question properties changed preserved native choice metadata')
    return after


def configure(page,step):
    plan=validate(step);frame=page.frame_locator('iframe[name="quiz-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    def identity():
        if page.url!=plan['start_url'] or title.count()!=1 or read_editor_title(title)!=plan['expected_quiz_name']:
            raise Stop('Short Answer quiz identity changed')
        assert_tenant(page,plan)
    title.wait_for(state='visible',timeout=45000);_wait_editor_identity(page,title,plan);identity();_wait_baseline(frame,plan)
    before=_inventory(frame,plan)
    if _properties_only(before)!=[page['questions'] for page in plan['pages']]:
        raise Stop('Existing quiz questions differ from the complete expected inventory')
    runtime,desired=_target_page(frame,plan,before,_inventory);owner=plan['target_page']-1
    for question in plan['questions']:
        identity()
        if _inventory(frame,runtime)!=desired:raise Stop('Quiz questions changed before the next insertion')
        item=_append(frame,runtime,page=page)
        _prewrite_delta(frame,runtime,desired,_inventory,question)
        authored=_write_question(frame,item,question)
        desired[owner].append(authored)
        if _inventory(frame,runtime)!=desired:
            raise Stop('Short Answer insertion changed existing questions or a different page')
    identity();save=_one(frame.get_by_role('button',name='Save',exact=True),'Native quiz Save changed')
    if not save.is_enabled():raise Stop('Native Short Answer configuration remains invalid')
    click(save)
    wait_until(lambda:save.is_enabled(),'Native quiz Save did not finish')
    page.wait_for_load_state('networkidle',timeout=45000)
    reopen_editor(page,'quiz',plan['expected_quiz_name'],plan['start_url'])
    frame=page.frame_locator('iframe[name="quiz-builder-app"]');title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000);_wait_editor_identity(page,title,plan);identity();_wait_baseline(frame,runtime,expected=desired)
    if _inventory(frame,runtime)!=desired:raise Stop('New native Short Answers did not persist after independent reopen')
    return {'status':'QUIZ_SHORT_ANSWERS_SAVED_AND_REOPENED','kind':'quiz_short_answers',
        'editor_url':page.url,'configuration_sha256':configuration_hash(step),
        'question_count':len(plan['questions']),'target_page':plan['target_page'],
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False,
        'dependency_api_used':False}
