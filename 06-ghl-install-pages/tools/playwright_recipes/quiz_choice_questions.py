"""Create captured native quiz CHECKBOX and RADIO questions with authored choices.

The full prior page inventory, selected Query Keys and option values bind each
write. The outer runner owns the lease and durable intent-before-drag journal.
"""
from copy import deepcopy
import hashlib
import json
import re

if __package__:
    from . import quiz_text_questions as native
    from .skill6_playwright import Stop,assert_tenant,click,fill,wait_until
else:
    import quiz_text_questions as native
    from skill6_playwright import Stop,assert_tenant,click,fill,wait_until


TYPES=('TEXT','RADIO','CHECKBOX','LARGE_TEXT','NUMERICAL','SINGLE_OPTIONS','MULTIPLE_OPTIONS')
DROPDOWNS=('SINGLE_OPTIONS','MULTIPLE_OPTIONS')
OPTIONS=['Option 1','Option 2','Option 3']
UUID=r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'


def _question(value,*,new=False):
    if not isinstance(value,dict):raise Stop('Multiple Choice question inventory must be an object')
    kind=value.get('field_type')
    if kind=='PICTURE_CHOICE' and not new:
        from playwright_recipes.quiz_picture_questions import _question as picture_question
        return picture_question(value)
    has_options=kind in ('CHECKBOX',*DROPDOWNS) or kind=='RADIO' and (new or 'options' in value)
    expected=native.properties_for(kind)|({'options'} if has_options else set())
    if set(value)!=expected or new and kind not in ('RADIO','CHECKBOX',*DROPDOWNS):
        raise Stop('Native choice authoring needs exact RADIO/CHECKBOX properties and options')
    native._question({key:value[key] for key in native.properties_for(kind)},new=new,field_types=TYPES)
    if has_options:
        options=value['options']
        valid_count=(lambda count:2<=count<=50) if kind=='MULTIPLE_OPTIONS' else (lambda count:count in ((2,3) if kind=='RADIO' else (3,)))
        if (not isinstance(options,list) or not valid_count(len(options))
                or any(not native._text(option) or option!=option.strip() for option in options)
                or len({option.casefold() for option in options})!=len(options)):
            raise Stop('Choice options exceed this adapter\'s bounded unique-option authoring profiles')
    return deepcopy(value)


def _project_existing(question):
    """Validate a complete prior owner, then project native scalar properties.

    Picture Choice is natively RADIO, but retains its distinct media/Unique Key
    inventory in the original payload and in every actual DOM readback.
    """
    original=_question(question)
    kind='RADIO' if original['field_type']=='PICTURE_CHOICE' else original['field_type']
    return {**{key:original[key] for key in native.properties_for(kind)},'field_type':kind}


def _unique_keys(questions):
    keys=[question['unique_key'].casefold() for question in questions
          if isinstance(question.get('unique_key'),str) and question['unique_key']]
    if len(keys)!=len(set(keys)):
        raise Stop('Quiz existing/new Unique Keys must be unambiguous in their shared native namespace')


def _option_transition(desired,defaults=OPTIONS):
    current=list(defaults)
    for index,value in enumerate(desired):
        if value.casefold() in {label.casefold() for i,label in enumerate(current) if i!=index}:
            raise Stop('Native option rename would collide with another occupied label; staged renames need a separate capture')
        current[index]=value


def _profile(question):
    if question['field_type']=='MULTIPLE_OPTIONS':
        return {'tile':'Multi Dropdown','default_key':'','options':OPTIONS}
    if question['field_type']=='SINGLE_OPTIONS':
        return {'tile':'Single Dropdown','suffix':5,'default_key':'dropdown','options':OPTIONS}
    if question['field_type']=='CHECKBOX':
        return {'tile':'Multiple Choice','suffix':5,'default_key':'checkbox','options':OPTIONS}
    if len(question['options'])==2:
        return {'tile':'Yes / No','suffix':6,'default_key':'radio','options':['Yes','No']}
    return {'tile':'Single Choice','suffix':6,'default_key':'radio','options':OPTIONS}


def _desired_defaults(question):
    if question['field_type']=='MULTIPLE_OPTIONS':return ['Option '+str(index+1) for index in range(len(question['options']))]
    return _profile(question)['options']


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','quiz_multiple_choices')!='quiz_multiple_choices'):
        raise Stop('Unsupported native Multiple Choice runner metadata')
    payload=step.get('payload')
    if (not isinstance(payload,dict) or set(payload)!=native.owner_keys(payload)|{'acknowledge_shared_field_options'}
            or payload['acknowledge_shared_field_options'] is not True):
        raise Stop('Native Multiple Choice needs exact quiz inventory and explicit shared-option acknowledgement')
    # Reuse exact tenant/editor/page/collision validation. The projection only
    # separates options from the shared text/key/flag property schema.
    projected=deepcopy(payload);projected.pop('acknowledge_shared_field_options')
    if not isinstance(projected.get('pages'),list) or not isinstance(projected.get('questions'),list):
        raise Stop('Multiple Choice needs complete prior pages and authored questions')
    for page in projected['pages']:
        if not isinstance(page,dict) or not isinstance(page.get('questions'),list):
            raise Stop('Multiple Choice prior page inventory is malformed')
        for index,question in enumerate(page['questions']):
            page['questions'][index]=_project_existing(question)
    for index,question in enumerate(projected['questions']):
        original=_question(question,new=True)
        _option_transition(original['options'],_desired_defaults(original))
        projected['questions'][index]={key:original[key] for key in native.properties_for(original['field_type'])}
    _unique_keys([question for page in payload['pages'] for question in page['questions']] + payload['questions'])
    native.validate({'action':'quiz_short_answers','payload':projected},field_types=TYPES,
                    new_types=('RADIO','CHECKBOX',*DROPDOWNS),reserved_key=None)
    return deepcopy(payload)


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _choices(item,kind='CHECKBOX'):
    if kind in DROPDOWNS:return _dropdown_choices(item,kind)
    fields=item.locator('input[type="'+kind.lower()+'"]');count=fields.count()
    if count not in ((2,3) if kind=='RADIO' else (3,)):
        raise Stop('Native choice inputs differ from the captured option counts')
    result=[];owner=None
    for index in range(count):
        field=fields.nth(index);identifier=field.get_attribute('id') or ''
        pattern=r'('+UUID+r')_'+str(index) if kind=='RADIO' else r'checkbox-('+UUID+r')-'+str(index)
        match=re.fullmatch(pattern,identifier)
        if not match or field.get_attribute('disabled') is None:
            raise Stop('Native Multiple Choice option identity differs from its captured disabled checkbox shape')
        if ((kind=='RADIO' and field.get_attribute('name')!=match.group(1))
                or kind=='CHECKBOX' and field.get_attribute('name') not in ('',None)):
            raise Stop('Native choice field name differs from its captured owner binding')
        if owner is not None and owner!=match.group(1):raise Stop('Native Multiple Choice options have different field identities')
        owner=match.group(1)
        label=native._one(item.locator('label[contenteditable][for="'+identifier+'"]'),
                          'Native Multiple Choice editable option label changed')
        if kind=='RADIO' and label.get_attribute('id')!='option-label-'+match.group(1)+'-'+str(index):
            raise Stop('Native RADIO option-label ID differs from its exact input owner/index')
        value=label.inner_text().strip()
        if not native._text(value) or value!=field.input_value():
            raise Stop('Native Multiple Choice checkbox values and option labels disagree')
        result.append({'id':identifier,'value':value})
    if item.locator('label[contenteditable][for]').count()!=count:
        raise Stop('Native Multiple Choice contains additional unowned editable options')
    return result


def _dropdown_choices(item,kind='SINGLE_OPTIONS'):
    if item.get_attribute('data-active')!='true':
        raise Stop('Native dropdown option inventory requires its exact selected widget')
    cards=item.locator('#options-card');native._one(cards,'Native selected dropdown options card changed')
    rows=cards.locator('.option')
    count=rows.count()
    if (kind=='SINGLE_OPTIONS' and count!=3) or (kind=='MULTIPLE_OPTIONS' and not 2<=count<=50):
        raise Stop('Native dropdown option count differs from its captured supported shape')
    result=[];owner=None
    for index in range(count):
        label=native._one(rows.nth(index).locator('label[contenteditable]'),'Native dropdown editable label changed')
        identifier=label.get_attribute('for') or ''
        match=re.fullmatch('('+UUID+r')_'+str(index),identifier)
        if (not match or owner is not None and owner!=match.group(1)
                or label.get_attribute('id')!='option-label-'+match.group(1)+'-'+str(index)):
            raise Stop('Native dropdown option identity differs from its captured owner/index')
        owner=match.group(1);value=label.inner_text().strip()
        if not native._text(value):raise Stop('Native dropdown option label is unreadable')
        result.append({'id':identifier,'value':value})
    if cards.locator('label[contenteditable]').count()!=count:
        raise Stop('Native dropdown options contain additional unowned labels')
    return result


def _radio_input_ids(item):
    values=item.locator('input[type="radio"]').evaluate_all('nodes=>nodes.map(node=>node.getAttribute("id"))')
    if not isinstance(values,list) or any(value is not None and not isinstance(value,str) for value in values):
        raise Stop('Existing RADIO input ID inventory is unreadable')
    return values


def _metadata(frame,kind):
    if kind not in ('RADIO','CHECKBOX',*DROPDOWNS):return {}
    options=native._radio_options(frame)
    switches=frame.get_by_role('switch')
    if switches.count()!=len(options)+(0 if kind in DROPDOWNS else 1):
        raise Stop('Native choice Jump To/Spread to columns switch inventory changed')
    states=[]
    for index in range(switches.count()):
        state=native._one(switches.nth(index),'Native choice switch is unavailable').get_attribute('aria-checked')
        if state not in ('true','false'):raise Stop('Native choice switch state is unreadable')
        states.append(state=='true')
    # Enabling Jump To introduces additional destination controls, whose
    # selected identities need a separate capture. Never omit that inventory.
    if any(states):raise Stop('Active native choice jumps/spread require separately captured configuration inventory')
    return {'_choice_controls':options,'_choice_switches':states}


def _default_metadata(frame,kind,defaults):
    result=_metadata(frame,kind);options=result['_choice_controls']
    if ([option['label'] for option in options]!=defaults
            or any(option['score']!='0' or option['score_enabled'] is not False for option in options)):
        raise Stop('New native choice differs from its captured unscored default option metadata')
    return result


def _inventory(frame,plan,*,field_types=TYPES):
    native._prepare_inventory(frame)
    result=[]
    option_keys={question['query_key'] for owner in plan['pages'] for question in owner['questions']
                 if question['field_type']=='RADIO' and 'options' in question}
    option_keys.update(question['query_key'] for question in plan['questions']
                       if question['field_type']=='RADIO' and 'options' in question)
    pictures=any(question['field_type']=='PICTURE_CHOICE'
                 for owner in plan['pages'] for question in owner['questions'])
    for _,canvas in native._owners(frame,plan):
        items=native._items(canvas);count=items.count();questions=[]
        if not count:native._one(canvas.get_by_text('Drag and drop components',exact=True),
                                'Empty native quiz page is not confirmed')
        for index in range(count):
            if items.count()!=count:raise Stop('Native quiz changed during question inventory')
            item=items.nth(index)
            if pictures and item.locator('[data-testid="picture-choice-grid"]').count():
                from playwright_recipes.quiz_picture_questions import _read_picture
                questions.append(_read_picture(frame,item))
                continue
            question=native._read_question(frame,item,field_types=field_types,metadata_reader=_metadata)
            if question['field_type']=='RADIO':question['_radio_input_ids']=_radio_input_ids(item)
            if question['field_type'] in DROPDOWNS:
                label,_=native._item_kind(item,field_types=field_types);native._activate_item(frame,item,label)
            if question['field_type'] in ('CHECKBOX',*DROPDOWNS) or question['field_type']=='RADIO' and question['query_key'] in option_keys:
                question['_option_identity']=_choices(item,question['field_type'])
                question['options']=[option['value'] for option in question['_option_identity']]
                if question['options']!=[option['label'] for option in question['_choice_controls']]:
                    raise Stop('Native option property labels do not belong to the exact canvas choice owner')
            elif question['field_type']=='RADIO':
                values=[field['value'] for field in question['_widget_inputs'] if field.get('type')=='radio']
                if values!=[option['label'] for option in question['_choice_controls']]:
                    raise Stop('Existing RADIO input values and selected option property labels disagree')
            questions.append(question)
        result.append(questions)
    return result


def _properties(inventory):
    return [[{key:value for key,value in question.items() if not key.startswith('_')}
             for question in page] for page in inventory]


def _append(frame,plan,question=None,*,page=None):
    question=question or plan['questions'][0];profile=_profile(question);expected_kind=question['field_type']
    item=native._append_tile(frame,plan,profile['tile'],page=page)
    label,kind=native._item_kind(item,field_types=TYPES)
    if kind!=expected_kind or not re.fullmatch(re.escape(profile['tile'])+r' [a-z0-9]{1,64}',label.inner_text().strip()):
        raise Stop('New choice differs from its captured native type/default options/generated label')
    native._activate_item(frame,item,label)
    if [option['value'] for option in _choices(item,kind)]!=profile['options']:
        raise Stop('New choice differs from its captured native default options')
    if kind in DROPDOWNS:
        control=native._one(item.locator('input.dropdown-input.form-placeholder'),'Native Single Dropdown input changed')
        if (any(control.get_attribute(key) is not None for key in ('id','name','type'))
                or control.input_value()!=''):
            raise Stop('Native Single Dropdown differs from its captured empty typeless input')
    return item


def _resize_snapshot(frame,item,choices):
    snapshot=native._read_question(frame,item,field_types=TYPES,metadata_reader=_metadata)
    label,_=native._item_kind(item,field_types=TYPES);native._activate_item(frame,item,label)
    if _choices(item,'MULTIPLE_OPTIONS')!=choices:
        raise Stop('Native choice identities changed during resize metadata readback')
    _check_resize_snapshot(snapshot,choices)
    return snapshot


def _check_resize_snapshot(snapshot,choices):
    controls=snapshot.get('_choice_controls');switches=snapshot.get('_choice_switches')
    if (not isinstance(controls,list) or not isinstance(switches,list)
            or len(controls)!=len(choices) or len(switches)!=len(choices)
            or any(type(value) is not bool for value in switches)):
        raise Stop('Native option resize metadata inventory is incomplete')
    for control,choice in zip(controls,choices):
        if (not isinstance(control,dict) or set(control)!={'label','category','score','score_enabled'}
                or control['label']!=choice['value'] or not isinstance(control['category'],str)
                or not isinstance(control['score'],str) or type(control['score_enabled']) is not bool):
            raise Stop('Native resize metadata does not belong to the exact option owner')


def _resize_multi(frame,item,target,*,initial=None):
    """Use captured canvas Add/Delete once per exact option-count delta."""
    current=_choices(item,'MULTIPLE_OPTIONS')
    snapshot=deepcopy(initial) if initial is not None else _resize_snapshot(frame,item,current)
    _check_resize_snapshot(snapshot,current)
    while len(current)!=target:
        before=deepcopy(current);before_snapshot=deepcopy(snapshot);count=len(before)
        if [option['value'] for option in before]!=['Option '+str(index+1) for index in range(count)]:
            raise Stop('Multi Dropdown defaults changed before option-count authoring')
        label,_=native._item_kind(item,field_types=TYPES);native._activate_item(frame,item,label)
        adding=count<target;wanted=count+(1 if adding else -1)
        if adding:
            control=native._one(item.locator('#add-option'),'Native Multi Dropdown Add option control changed')
        else:
            row=item.locator('#options-card .option').nth(count-1)
            control=native._one(row.locator('svg.ml-2.cursor-pointer'),'Native last-option delete icon changed')
            path=control.locator('path')
            if path.count()!=1 or not (path.get_attribute('d') or '').startswith('M16 6v-.8'):
                raise Stop('Native option trash glyph differs from its captured delete control')
        click(control)
        label,_=native._item_kind(item,field_types=TYPES);native._activate_item(frame,item,label)
        def exact_delta():
            actual=item.locator('#options-card .option').count()
            if actual>max(count,wanted) or actual<min(count,wanted):
                raise Stop('Native option-count action changed more than one row')
            return actual==wanted
        wait_until(exact_delta,'Native option-count action did not settle exactly once; do not repeat it')
        current=_choices(item,'MULTIPLE_OPTIONS')
        if adding:
            if current[:-1]!=before or current[-1]['value']!='Option '+str(wanted):
                raise Stop('Native Add option changed existing choices or its measured default new label')
        elif current!=before[:-1]:
            raise Stop('Native Delete option changed a retained choice or its field identity')
        snapshot=_resize_snapshot(frame,item,current)
        retained=min(count,wanted)
        if (snapshot['_choice_controls'][:retained]!=before_snapshot['_choice_controls'][:retained]
                or snapshot['_choice_switches'][:retained]!=before_snapshot['_choice_switches'][:retained]):
            raise Stop('Native option resize changed retained category, score, enabled state or jump metadata')
        other=lambda value:{key:entry for key,entry in value.items() if key not in ('_choice_controls','_choice_switches')}
        if other(snapshot)!=other(before_snapshot):
            raise Stop('Native option resize changed protected question or advanced identity metadata')
        if adding:
            expected={'label':'Option '+str(wanted),'category':before_snapshot['_choice_controls'][-1]['category'],
                      'score':'0','score_enabled':False}
            if snapshot['_choice_controls'][-1]!=expected or snapshot['_choice_switches'][-1] is not False:
                raise Stop('Native added option differs from its captured unscored, non-routing defaults')
    return current,snapshot


def _write_question(frame,item,question):
    question=_question(question,new=True);kind=question['field_type'];profile=_profile(question)
    _option_transition(question['options'],_desired_defaults(question))
    defaults=_choices(item,kind)
    if [option['value'] for option in defaults]!=profile['options']:
        raise Stop('New Multiple Choice options differ before authoring')
    protected=None
    if kind=='MULTIPLE_OPTIONS':
        initial=native._read_question(frame,item,field_types=TYPES,metadata_reader=_metadata)
        if (initial['field_type']!=kind or initial['unique_key']!='' or initial['placeholder']
                or initial['short_label'] or initial['required']
                or any(row['score']!='0' or row['score_enabled'] is not False for row in initial['_choice_controls'])
                or any(initial['_choice_switches'])):
            raise Stop('New Multi Dropdown differs from its captured pre-resize defaults')
        label,_=native._item_kind(item,field_types=TYPES);native._activate_item(frame,item,label)
        defaults,protected=_resize_multi(frame,item,len(question['options']),initial=initial)
    properties={key:question[key] for key in native.properties_for(kind)}
    authored=native._write_question(frame,item,properties,field_types=TYPES,new_kind=kind,default_key=profile['default_key'],
        metadata_reader=lambda selected,selected_kind:_default_metadata(selected,selected_kind,_desired_defaults(question)),
        **({'expected_metadata':protected} if protected is not None else {}))
    if kind in DROPDOWNS:
        label,_=native._item_kind(item,field_types=TYPES);native._activate_item(frame,item,label)
    if _choices(item,kind)!=defaults:raise Stop('Question properties unexpectedly changed the native choice inventory')
    # Scope each captured contenteditable label to its exact option's for
    # attribute. RADIO uses distinct option-label IDs; CHECKBOX duplicates the
    # input ID on the label, so a global ID selector would be ambiguous.
    for index,option in enumerate(defaults):
        expected=[{'id':old['id'],'value':question['options'][i] if i<index else old['value']}
                  for i,old in enumerate(defaults)]
        if _choices(item,kind)!=expected:raise Stop('Multiple Choice options changed before the next authored label')
        label=native._one(item.locator('label[contenteditable][for="'+option['id']+'"]'),
                          'Native editable Multiple Choice option changed')
        fill(label,question['options'][index]);label.press('Tab')
        if kind in DROPDOWNS:
            question_label,_=native._item_kind(item,field_types=TYPES)
            native._activate_item(frame,item,question_label)
        expected[index]['value']=question['options'][index]
        wait_until(lambda:_choices(item,kind)==expected,'Native Multiple Choice ignored an authored option value')
    after=native._read_question(frame,item,field_types=TYPES,metadata_reader=_metadata)
    expected_controls=deepcopy(authored['_choice_controls'])
    for index,option in enumerate(expected_controls):option['label']=question['options'][index]
    if (after['_choice_controls']!=expected_controls
            or after['_choice_switches']!=authored['_choice_switches']):
        raise Stop('Authoring native options unexpectedly changed categories, scores or jump/spread controls')
    if kind=='MULTIPLE_OPTIONS' and any(after.get(key)!=authored.get(key)
            for key in ('_custom_field_name','_unique_key_placeholder')):
        raise Stop('Option labels changed protected native custom-field identity metadata')
    if kind in DROPDOWNS:
        label,_=native._item_kind(item,field_types=TYPES);native._activate_item(frame,item,label)
    after['_option_identity']=_choices(item,kind)
    if kind=='RADIO':after['_radio_input_ids']=_radio_input_ids(item)
    after['options']=[option['value'] for option in after['_option_identity']]
    if _properties([[after]])!=[[question]]:raise Stop('Authored Multiple Choice differs before Save')
    return after


def _fresh_choice(item,kind,inventory):
    new_options=_choices(item,kind)
    def owner(identifier):
        if not isinstance(identifier,str):return None
        match=re.fullmatch(r'(?:checkbox-)?('+UUID+r')[-_][0-9]+',identifier)
        return match.group(1) if match else None
    new_owner=owner(new_options[0]['id']);new_ids={option['id'] for option in new_options}
    old_ids=set();old_names=set();old_owners=set()
    for page in inventory:
        for question in page:
            ids=[*question.get('_radio_input_ids',[]),
                 *(option['id'] for option in question.get('_option_identity',[]))]
            old_ids.update(identifier for identifier in ids if isinstance(identifier,str))
            old_owners.update(owner(identifier) for identifier in ids)
            old_names.update(field.get('name') for field in question['_widget_inputs'] if isinstance(field.get('name'),str))
    if new_ids.intersection(old_ids) or new_owner in old_owners or new_owner in old_names:
        raise Stop('New native choice reused an existing question field identity')


def configure(page,step):
    plan=validate(step);frame=page.frame_locator('iframe[name="quiz-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    def identity():
        if page.url!=plan['start_url'] or title.count()!=1 or native.read_editor_title(title)!=plan['expected_quiz_name']:
            raise Stop('Native Multiple Choice quiz identity changed')
        assert_tenant(page,plan)
    title.wait_for(state='visible',timeout=45000);native._wait_editor_identity(page,title,plan);identity();native._wait_baseline(frame,plan)
    before=_inventory(frame,plan)
    if _properties(before)!=[owner['questions'] for owner in plan['pages']]:
        raise Stop('Native quiz differs from its complete prior question/option inventory')
    runtime,desired=native._target_page(frame,plan,before,_inventory);owner=plan['target_page']-1
    for question in plan['questions']:
        identity()
        if _inventory(frame,runtime)!=desired:raise Stop('Quiz questions changed before the next Multiple Choice insertion')
        item=_append(frame,runtime,question,page=page)
        native._prewrite_delta(frame,runtime,desired,_inventory,question)
        _fresh_choice(item,question['field_type'],desired)
        desired[owner].append(_write_question(frame,item,question))
        if _inventory(frame,runtime)!=desired:
            raise Stop('Native Multiple Choice changed existing questions, options or another page')
    identity();save=native._one(frame.get_by_role('button',name='Save',exact=True),'Native quiz Save changed')
    if not save.is_enabled():raise Stop('Native Multiple Choice configuration remains invalid')
    click(save);wait_until(lambda:save.is_enabled(),'Native quiz Save did not finish')
    page.wait_for_load_state('networkidle',timeout=45000)
    native.reopen_editor(page,'quiz',plan['expected_quiz_name'],plan['start_url'])
    frame=page.frame_locator('iframe[name="quiz-builder-app"]');title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000);native._wait_editor_identity(page,title,plan);identity();native._wait_baseline(frame,runtime,expected=desired)
    if _inventory(frame,runtime)!=desired:raise Stop('Native Multiple Choice did not persist after independent reopen')
    return {'status':'QUIZ_MULTIPLE_CHOICES_SAVED_AND_REOPENED','kind':'quiz_multiple_choices',
        'editor_url':page.url,'configuration_sha256':configuration_hash(step),
        'question_count':len(plan['questions']),'target_page':plan['target_page'],
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False,
        'dependency_api_used':False}
