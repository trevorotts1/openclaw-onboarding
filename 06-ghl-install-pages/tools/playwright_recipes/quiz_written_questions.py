"""Captured native quiz written-response creation, with full owner inventories."""
from copy import deepcopy
import hashlib
import json
import re

if __package__:
    from . import quiz_text_questions as native
    from . import quiz_choice_questions as choice
    from .skill6_playwright import Stop,assert_tenant,click,wait_until
else:
    import quiz_text_questions as native
    import quiz_choice_questions as choice
    from skill6_playwright import Stop,assert_tenant,click,wait_until


TYPES=choice.TYPES
PROFILES={'TEXT':{'tile':'Short Answer','default_key':'single_line','suffix':6},
          'LARGE_TEXT':{'tile':'Long Answer','default_key':'multi_line','suffix':6},
          'NUMERICAL':{'tile':'Number','default_key':'text','suffix':5}}


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','quiz_written_answers')!='quiz_written_answers'):
        raise Stop('Unsupported native written-answer runner metadata')
    payload=step.get('payload')
    projected=deepcopy(payload)
    if isinstance(projected,dict) and isinstance(projected.get('pages'),list):
        for page in projected['pages']:
            if isinstance(page,dict) and isinstance(page.get('questions'),list):
                for index,question in enumerate(page['questions']):
                    if isinstance(question,dict) and question.get('field_type') in ('RADIO','CHECKBOX','SINGLE_OPTIONS','MULTIPLE_OPTIONS','PICTURE_CHOICE'):
                        page['questions'][index]=choice._project_existing(question)
    projected=native.validate({'action':'quiz_short_answers','payload':projected},field_types=TYPES,
                              new_types=tuple(PROFILES),reserved_key=None)
    choice._unique_keys([question for page in payload['pages'] for question in page['questions']])
    return deepcopy(payload)


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _append(frame,plan,question,*,page=None):
    kind=question['field_type'];profile=PROFILES[kind]
    item=native._append_tile(frame,plan,profile['tile'],page=page)
    label,actual=native._item_kind(item,field_types=TYPES)
    if actual!=kind or not re.fullmatch(re.escape(profile['tile'])+r' [a-z0-9]{'+str(profile['suffix'])+'}',label.inner_text().strip()):
        raise Stop('New written answer differs from its captured active native type and generated label')
    selector={'TEXT':'input.form-placeholder.form-control','LARGE_TEXT':'textarea.form-placeholder.form-control',
              'NUMERICAL':'input.form-control'}[kind]
    field=item.locator(selector)
    if (field.count()!=1 or any(field.get_attribute(key) is not None for key in ('id','name','type'))
            or field.input_value()!=''):
        raise Stop('New written answer differs from its captured typeless empty widget shape')
    if kind=='LARGE_TEXT' and (field.get_attribute('placeholder')!=''
            or field.get_attribute('aria-label')!='Type your message here'):
        raise Stop('New Long Answer differs from its captured textarea placeholder and accessible name')
    if kind=='NUMERICAL' and field.get_attribute('placeholder') is not None:
        raise Stop('New Number differs from its captured absent-placeholder input shape')
    native._activate_item(frame,item,label)
    return item


def configure(page,step):
    plan=validate(step);runtime=plan;frame=page.frame_locator('iframe[name="quiz-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    def identity():
        if page.url!=plan['start_url'] or title.count()!=1 or native.read_editor_title(title)!=plan['expected_quiz_name']:
            raise Stop('Native written-answer quiz identity changed')
        assert_tenant(page,plan)
    def inventory():return choice._inventory(frame,runtime,field_types=TYPES)
    title.wait_for(state='visible',timeout=45000);native._wait_editor_identity(page,title,plan);identity();native._wait_baseline(frame,plan)
    before=inventory()
    if choice._properties(before)!=[owner['questions'] for owner in plan['pages']]:
        raise Stop('Native quiz differs from its complete expected written-answer inventory')
    runtime,desired=native._target_page(frame,plan,before,choice._inventory);owner=plan['target_page']-1
    for question in plan['questions']:
        identity()
        if inventory()!=desired:raise Stop('Native quiz changed before the next written-answer insertion')
        item=_append(frame,runtime,question,page=page)
        native._prewrite_delta(frame,runtime,desired,choice._inventory,question)
        authored=native._write_question(frame,item,question,field_types=TYPES,new_kind=question['field_type'],
                                        default_key=PROFILES[question['field_type']]['default_key'],metadata_reader=choice._metadata)
        desired[owner].append(authored)
        if inventory()!=desired:raise Stop('Native written answer changed existing questions or the intended append order')
    identity();save=native._one(frame.get_by_role('button',name='Save',exact=True),'Native quiz Save changed')
    if not save.is_enabled():raise Stop('Native written-answer configuration remains invalid')
    click(save);wait_until(lambda:save.is_enabled(),'Native written-answer Save did not finish')
    page.wait_for_load_state('networkidle',timeout=45000)
    native.reopen_editor(page,'quiz',plan['expected_quiz_name'],plan['start_url'])
    frame=page.frame_locator('iframe[name="quiz-builder-app"]');title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000);native._wait_editor_identity(page,title,plan);identity();native._wait_baseline(frame,runtime,expected=desired)
    if inventory()!=desired:raise Stop('Native written answers did not persist after independent reopen')
    return {'status':'QUIZ_WRITTEN_ANSWERS_SAVED_AND_REOPENED','kind':'quiz_written_answers',
        'editor_url':page.url,'configuration_sha256':configuration_hash(step),
        'question_count':len(plan['questions']),'target_page':plan['target_page'],
        'independent_readback':'VERIFIED','dependency_api_used':False,
        'behavior_verified':False,'submission_verified':False}
