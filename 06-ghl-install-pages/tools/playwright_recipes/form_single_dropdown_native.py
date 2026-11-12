"""Captured Quick Add Single Dropdown authoring, without an invented API schema.

The shared form-widget runner owns creation, full canvas inventory, tenant/name
identity, intent journaling, changed-owner preservation and saved fresh replay.
This descriptor adds only the observed native family controls and choice rows.
"""
from copy import deepcopy
import re

from playwright_recipes.skill6_playwright import Stop, click, fill, wait_until

PROPERTIES={'label':'#label input','placeholder':'#fieldPlaceholder input',
            'short_label':'#shortLabel input','query_key':'#fieldQueryKey input',
            'width':'#fieldWidthKey input','custom_field_name':'#custom-field-label input',
            'unique_key':'#uniqueKey input'}
PROFILE={'type':'SINGLE_OPTIONS','tile':'Single Dropdown','suffix':5,
         'key_prefix':'single_dropdown_','properties':PROPERTIES,
         'flags':{'required':'#fieldRequired'},'input':'input.dropdown-input',
         'extra':('options','calculations'),
         'defaults':{'placeholder':'Select an option','short_label':'','width':100,
                     'required':False,'options':[{'label':'Option '+str(i),'value':None} for i in (1,2,3)],
                     'calculations':False}}


def validate_properties(value, *, prefill=False):
    options=value['options']
    if (not prefill and type(value['calculations']) is not bool) or not isinstance(options,list) or not 1<=len(options)<=100:
        raise Stop('Single Dropdown requires explicit complete choice/calculation inventory')
    labels=[]
    for option in options:
        if not isinstance(option,dict) or set(option)!={'label','value'}:
            raise Stop('Single Dropdown requires every exact option label and calculation value or absence')
        label=option['label']
        if (not isinstance(label,str) or not label.strip() or len(label)>5000
                or any(ord(c)<32 for c in label)):
            raise Stop('Single Dropdown option labels require explicit nonempty single-line text')
        labels.append(label)
        if prefill:
            score=option['value']
            if not isinstance(score,str) or len(score)>5000 or any(ord(c)<32 for c in score):
                raise Stop('Text Box List Prefill Value must be explicit single-line text')
        elif value['calculations']:
            score=option['value']
            if not isinstance(score,str) or score and not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?',score):
                raise Stop('Single Dropdown calculation values require canonical finite decimal text')
        elif option['value'] is not None:
            raise Stop('Single Dropdown calculation values are absent while calculations are disabled')
    if len(labels)!=len(set(labels)):
        raise Stop('Single Dropdown option labels must remain unique')
    return value


def _one(node,message):
    if node.count()!=1 or not node.is_visible():raise Stop(message)
    return node


def _panel(frame, *, sidebar='#form_custom_sidebar'):
    panel=_one(frame.locator(sidebar),'Native Single Dropdown sidebar changed')
    click(_one(panel.get_by_text('Options',exact=True),'Native Single Dropdown Options pane changed'))
    return panel


def _calculation_control(panel):
    return _one(panel.get_by_text('Enable calculations',exact=True).locator('..').get_by_role('switch'),
                'Native Single Dropdown calculation switch changed')


def read_options(frame, *, sidebar='#form_custom_sidebar', prefill=False):
    panel=_panel(frame,sidebar=sidebar)
    state=None if prefill else _calculation_control(panel).get_attribute('aria-checked')
    if not prefill and state not in ('true','false'):raise Stop('Native Single Dropdown calculation state is unavailable')
    labels=panel.locator('[id^="option-label-"] input');count=labels.count()
    if not 1<=count<=100:raise Stop('Native Single Dropdown complete options are unavailable')
    options=[]
    for index in range(count):
        label=_one(panel.locator('#option-label-'+str(index)+' input'),'Native Single Dropdown option positions changed')
        value=panel.locator(('#option-prefillValue-' if prefill else '#option-value-')+str(index)+' input')
        if prefill or state=='true':score=_one(value,'Native choice value input changed').input_value()
        else:
            if value.count() and value.is_visible():raise Stop('Single Dropdown has visible calculation values while disabled')
            score=None
        options.append({'label':label.input_value(),'value':score})
    return validate_properties({'options':options,**({} if prefill else {'calculations':state=='true'})},prefill=prefill)



def remove_option(frame,remove,labels,count):
    """Perform one authored removal and its captured shared-field confirmation.

    Unsaved options may remove immediately. Saved custom-field options expose
    the shared Delete Option modal; only that exact confirmation is accepted.
    """
    if not remove.is_enabled():raise Stop('Native option removal is disabled')
    click(remove);confirmed=False
    def settled():
        nonlocal confirmed
        if labels.count()==count-1:return True
        dialogs=frame.get_by_role('dialog')
        if dialogs.count():
            dialog=_one(dialogs,'Native option removal opened an ambiguous confirmation')
            _one(dialog.get_by_role('heading',name='Delete Option',exact=True),
                 'Native option removal confirmation identity changed')
            _one(dialog.get_by_text('Deleting an option will impact this custom field across all places where the field is used. Are you sure you wish to delete it?',exact=True),
                 'Native option removal shared-impact warning changed')
            if not confirmed:
                token=_one(dialog.locator('input[placeholder="DELETE"]'),
                           'Native option removal confirmation token changed')
                if token.input_value():raise Stop('Native option confirmation contains an unrelated draft')
                fill(token,'DELETE');token.press('Tab')
                submit=_one(dialog.get_by_role('button',name='Delete',exact=True),
                            'Native option removal confirmation action changed')
                if not submit.is_enabled():raise Stop('Native option confirmation action is disabled')
                confirmed=True;click(submit)
            return False
        return labels.count()==count-1
    wait_until(settled,'Native option removal did not settle exactly once')


def write_options(frame,before,desired, *, sidebar='#form_custom_sidebar', prefill=False):
    observed=read_options(frame,sidebar=sidebar,prefill=prefill)
    keys=('options',) if prefill else ('options','calculations')
    if any(observed[key]!=before[key] for key in keys):
        raise Stop('Native Single Dropdown choices changed after full preflight')
    panel=frame.locator(sidebar)
    calculation=None if prefill else _calculation_control(panel)
    if not prefill and (calculation.get_attribute('aria-checked')=='true')!=desired['calculations']:
        click(calculation)
        wait_until(lambda:(calculation.get_attribute('aria-checked')=='true')==desired['calculations'],
                   'Native Single Dropdown calculation choice did not settle')
    labels=panel.locator('[id^="option-label-"] input')
    while labels.count()>len(desired['options']):
        count=labels.count()
        row=panel.locator('#option-label-'+str(count-1)).locator('..').locator('..')
        remove=_one(row.locator('button#remove-option'),'Native Single Dropdown option removal owner changed')
        remove_option(frame,remove,labels,count)
    while labels.count()<len(desired['options']):
        count=labels.count()
        click(_one(panel.locator('button#add-option'),'Native Single Dropdown Add option changed'))
        wait_until(lambda:labels.count()==count+1,'Native Single Dropdown Add option did not settle once')
    for index,option in enumerate(desired['options']):
        label=_one(panel.locator('#option-label-'+str(index)+' input'),'Native Single Dropdown option label changed')
        if label.input_value()!=option['label']:
            fill(label,option['label']);label.press('Tab')
        if prefill or desired['calculations']:
            score=_one(panel.locator(('#option-prefillValue-' if prefill else '#option-value-')+str(index)+' input'),'Native choice option value changed')
            if score.input_value()!=option['value']:
                fill(score,option['value']);score.press('Tab')
    if read_options(frame,sidebar=sidebar,prefill=prefill)!={key:deepcopy(desired[key]) for key in keys}:
        raise Stop('Native Single Dropdown authored options did not settle to exact desired values')
