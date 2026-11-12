"""Captured Single Choice and Multiple Choice answer jumps with full option preservation."""
from copy import deepcopy
import re
from playwright_recipes import quiz_text_questions as native
from playwright_recipes.skill6_playwright import Stop,click,wait_until


def validate(config):
    if not isinstance(config,dict) or set(config)!={'question_labels','questions'}:
        raise Stop('Answer jumps require complete ordered question labels and explicit target questions')
    labels=config['question_labels'];questions=config['questions']
    if (not isinstance(labels,list) or not 1<=len(labels)<=100
            or any(not native._text(label) or label!=label.strip() or label=='Next Question' for label in labels)
            or len({label.casefold() for label in labels})!=len(labels)
            or not isinstance(questions,list) or not 1<=len(questions)<=len(labels)):
        raise Stop('Answer jumps require unique exact question labels and a bounded nonempty target list')
    indices=set()
    for question in questions:
        keys={'index','expected_question','expected_query_key','options'}
        if (not isinstance(question,dict) or not keys <= set(question) or set(question)-keys-{'presentation','field_type'}
                or question.get('field_type','RADIO') not in ('RADIO','CHECKBOX','SINGLE_OPTIONS','MULTIPLE_OPTIONS')
                or question.get('field_type','RADIO') in ('SINGLE_OPTIONS','MULTIPLE_OPTIONS') and 'presentation' in question
                or type(question['index']) is not int or not 0<=question['index']<len(labels)
                or question['index'] in indices or question['expected_question']!=labels[question['index']]
                or not isinstance(question['expected_query_key'],str)
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,256}',question['expected_query_key'])
                or not isinstance(question['options'],list) or not 2<=len(question['options'])<=50):
            raise Stop('Answer jump target requires its exact existing question index, title, Query Key and all options')
        if 'presentation' in question:
            presentation=question['presentation']
            if (not isinstance(presentation,dict) or set(presentation)!={'expected_style','style'}
                    or any(type(presentation[key]) is not str or presentation[key] not in ('Standard','Bubble')
                           for key in ('expected_style','style'))):
                raise Stop('Choice presentation needs exact prior/authored Standard or Bubble style')
        indices.add(question['index']);option_labels=[]
        for option in question['options']:
            if (not isinstance(option,dict) or set(option)!={'label','expected_destination','destination'}
                    or not native._text(option['label']) or option['label']!=option['label'].strip()):
                raise Stop('Every answer jump requires its option label and explicit old/desired destination or null')
            option_labels.append(option['label'])
            for key in ('expected_destination','destination'):
                value=option[key]
                allowed=['Next Question',*(labels[question['index']+1:] if key=='destination'
                                           else [label for index,label in enumerate(labels) if index!=question['index']])]
                if value is not None and (not isinstance(value,str) or value not in allowed):
                    raise Stop('Authored answer jumps support Next Question or an explicit forward question only')
        if len(set(option_labels))!=len(option_labels):raise Stop('Answer jump option labels must be unique')
    return deepcopy(config)


def _open(frame,config,question):
    native._close_properties(frame)
    labels=frame.get_by_role('textbox',name='Label',exact=True)
    if labels.count()!=len(config['question_labels']):raise Stop('Answer jump full canvas question count changed')
    observed=[labels.nth(index).inner_text().strip() for index in range(labels.count())]
    if observed!=config['question_labels']:raise Stop('Answer jump full canvas question order/title changed')
    label=labels.nth(question['index'])
    if label.get_attribute('data-field-type')!=question.get('field_type','RADIO'):
        raise Stop('Answer jump selected field differs from its explicit captured type')
    click(label);click(native._one(frame.get_by_role('button',name='Open settings',exact=True),
                                  'Answer jump exact question settings control changed'))
    panel=native._one(frame.locator('#quiz_element_sidebar'),'Answer jump sidebar owner changed')
    if (native._one(panel.locator('#fieldTitle input'),'Answer jump title control changed').input_value()!=question['expected_question']
            or native._one(panel.locator('#fieldQueryKey input'),'Answer jump Query Key control changed').input_value()!=question['expected_query_key']):
        raise Stop('Answer jump selected question differs from its exact title/Query Key')
    return panel


def _row(panel,index,question):
    owner=native._one(panel.locator('#option-label-'+str(index)), 'Answer jump option position changed')
    row=owner.locator('..')
    labels=row.get_by_text(re.compile(r'^Jump [Tt]o$'))
    native._one(labels,'Answer jump switch label changed')
    switch=native._one(row.get_by_role('switch'),'Answer jump option switch owner changed')
    return row,switch


def _style_controls(panel,question):
    if panel.locator('.style-option').count()!=2:
        raise Stop('Single Choice style card inventory changed')
    controls={};active=[]
    for name in ('Standard','Bubble'):
        image=native._one(panel.get_by_role('img',name=name+(' checkbox style' if question.get('field_type','RADIO')=='CHECKBOX' else ' radio style'),exact=True),
                          'Single Choice style preview identity changed')
        card=native._one(image.locator('..'),'Single Choice style card owner changed')
        classes=(card.get_attribute('class') or '').split()
        if 'style-option' not in classes:raise Stop('Single Choice style preview escaped its captured card')
        if 'style-option-active' in classes:active.append(name)
        controls[name]=card
    if len(active)!=1:raise Stop('Single Choice active style is missing or ambiguous')
    return controls,active[0]


def _selected(panel,question):
    properties={key:native._one(panel.locator(selector),'Answer jump protected text property changed').input_value()
                for key,selector in native.FIELD_INPUTS.items()}
    flags={}
    for key,selector in native.FLAGS.items():
        state=native._one(panel.locator(selector),'Answer jump protected flag changed').get_attribute('aria-checked')
        if state not in ('true','false'):raise Stop('Answer jump protected flag is unreadable')
        flags[key]=state=='true'
    if panel.locator('[id^="option-label-"] input').count()!=len(question['options']):
        raise Stop('Answer jump option count differs from complete expected inventory')
    options=[]
    for index,expected in enumerate(question['options']):
        row,switch=_row(panel,index,question)
        label=native._one(row.locator('#option-label-'+str(index)+' input'),'Answer jump exact option label changed').input_value()
        if label!=expected['label']:raise Stop('Answer jump option label/order changed')
        picker=native._one(row.locator('[id="category-picker"]'),'Answer jump protected category owner changed')
        score=native._one(row.locator('#score input'),'Answer jump protected score owner changed')
        state=switch.get_attribute('aria-checked')
        if state not in ('true','false'):raise Stop('Answer jump switch state is unreadable')
        destination=row.locator('#radio'+str(index))
        if state=='true':
            selected=native._one(destination.locator('.n-base-selection-input[title]'),'Answer jump selected destination is unavailable')
            target=selected.get_attribute('title')
            if not native._text(target) or selected.inner_text().strip()!=target:
                raise Stop('Answer jump selected destination label is ambiguous')
        else:
            if destination.count():raise Stop('Disabled answer jump unexpectedly retained a destination control')
            target=None
        options.append({'label':label,'category':picker.inner_text().strip(),'score':score.input_value(),
                        'score_enabled':score.is_enabled(),'destination':target})
    switches=panel.get_by_role('switch')
    dropdown=question.get('field_type','RADIO') in ('SINGLE_OPTIONS','MULTIPLE_OPTIONS')
    if switches.count()!=len(options)+(0 if dropdown else 1):raise Stop('Answer jump/Spread switch inventory changed')
    states=[switches.nth(index).get_attribute('aria-checked') for index in range(switches.count())]
    row_states=states if dropdown else states[:-1]
    if any(value not in ('true','false') for value in states) or row_states!=[
            'true' if option['destination'] is not None else 'false' for option in options]:
        raise Stop('Answer jump row switches escaped their complete option order')
    style=None if dropdown else _style_controls(panel,question)[1]
    return {'properties':properties,'flags':flags,'options':options,'spread_to_columns':None if dropdown else states[-1]=='true','style':style}


def read(frame,config):
    result=[]
    for question in config['questions']:
        panel=_open(frame,config,question);result.append(_selected(panel,question))
        native._close_properties(frame,required=True)
    return result


def preflight(frame,config):
    validate(config);before=read(frame,config)
    for question,record in zip(config['questions'],before):
        if 'presentation' in question and record['style']!=question['presentation']['expected_style']:
            raise Stop('Single Choice style differs from its exact prior presentation')
        if ('presentation' in question and record['style']!=question['presentation']['style']
                and record['spread_to_columns']):
            raise Stop('Changing Single Choice style with active Spread requires its captured column inventory')
        if [option['destination'] for option in record['options']]!=[option['expected_destination'] for option in question['options']]:
            raise Stop('Answer jump prior destinations differ from exact inventoried state')
    return before


def desired(config,before):
    result=deepcopy(before)
    for question,record in zip(config['questions'],result):
        if 'presentation' in question:record['style']=question['presentation']['style']
        for option,authored in zip(record['options'],question['options']):option['destination']=authored['destination']
    return result


def write(frame,config,before):
    if read(frame,config)!=before:raise Stop('Answer jump protected state changed after complete preflight')
    expected=deepcopy(before)
    for offset,question in enumerate(config['questions']):
        panel=_open(frame,config,question)
        if 'presentation' in question:
            if _selected(panel,question)!=expected[offset]:
                raise Stop('Single Choice protected state changed before style authoring')
            controls,style=_style_controls(panel,question);wanted=question['presentation']['style']
            if style!=expected[offset]['style']:
                raise Stop('Single Choice selected style changed after complete preflight')
            if style!=wanted:
                if not controls[wanted].is_enabled():raise Stop('Requested Single Choice style card is disabled')
                click(controls[wanted]);expected[offset]['style']=wanted
                wait_until(lambda:_selected(panel,question)==expected[offset],
                           'Single Choice style did not settle or changed protected answer state')
        for index,authored in enumerate(question['options']):
            if _selected(panel,question)!=expected[offset]:raise Stop('Answer jump changed a protected sibling before its next edit')
            row,switch=_row(panel,index,question);target=authored['destination']
            enabled=switch.get_attribute('aria-checked')=='true'
            if enabled!=(target is not None):
                if not switch.is_enabled():raise Stop('Requested answer jump switch is disabled')
                click(switch)
                wait_until(lambda:switch.get_attribute('aria-checked')==('true' if target is not None else 'false'),
                           'Answer jump switch did not settle')
            if target is not None and (not enabled or expected[offset]['options'][index]['destination']!=target) and not (question.get('field_type','RADIO')=='CHECKBOX' and target=='Next Question' and _selected(panel,question)['options'][index]['destination']=='Next Question'):
                select=native._one(row.locator('#radio'+str(index)+' .n-base-selection'),
                                   'Answer jump destination selector changed')
                click(select)
                options=frame.locator('.n-base-select-option:visible')
                titles=options.locator('.n-base-select-option__content p')
                menu=[titles.nth(i).inner_text().strip() for i in range(titles.count())]
                wanted=['Next Question',*[label for i,label in enumerate(config['question_labels']) if i!=question['index']]]
                if options.count()!=len(menu) or menu!=wanted:
                    raise Stop('Answer jump destination menu differs from complete existing question inventory')
                click(options.nth(menu.index(target)))
            expected[offset]['options'][index]['destination']=target
            wait_until(lambda:_selected(panel,question)==expected[offset],
                       'Answer jump destination did not settle or changed protected score/category/options')
        native._close_properties(frame,required=True)
    if read(frame,config)!=expected:raise Stop('Answer jump authoring changed a previously configured question')


def verify(frame,config,before):
    if read(frame,config)!=desired(config,before):
        raise Stop('Answer jump destination or protected state did not persist after independent reopen')
