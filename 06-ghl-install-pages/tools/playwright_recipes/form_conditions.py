"""Native ordered AND/OR Show/Hide groups captured November 9, 2026.

The owner runner supplies tenant checks and the intent-before-write journal.
This handler creates one rule only when the entire existing condition inventory
is empty, or reuses exactly the same persisted rule. It never overwrites,
deletes, or silently appends to unrelated conditions.
"""
from copy import deepcopy
from decimal import Decimal
from datetime import datetime
import hashlib
import json
import re

if __package__:
    from . import form_condition_fields as field_identity
    from .assessments import reopen_editor, read_editor_title
    from .skill6_playwright import Stop, click, fill, form_builder, wait_until
else:
    import form_condition_fields as field_identity
    from assessments import reopen_editor, read_editor_title
    from skill6_playwright import Stop, click, fill, form_builder, wait_until


FIELDS = frozenset(('First Name','Last Name','Phone','Email','Website','TnC1',
                    'TnC2','Organization','Full Name','Date of birth'))
TARGETS = FIELDS | {'Privacy Policy | Terms of Service'}
CHECKED = frozenset(('Is Checked','Is Not Checked'))
UNARY = frozenset(('Is Empty','Is Filled')) | CHECKED
TEXT_BINARY = frozenset(('Is Equal To','Is Not Equal To','Contains','Does Not Contain',
                         'Starts With','Ends With'))
NUMBER_BINARY = frozenset(('Is Equal To','Is Not Equal To','Greater Than','Less Than','Between'))
OPTION_BINARY = frozenset(('Is Equal To','Is Not Equal To'))
DATE_BINARY = frozenset(('Is Equal To','Is Not Equal To','Before','After','Between'))
BINARY = TEXT_BINARY | NUMBER_BINARY | DATE_BINARY
CARD = 'div.flex.w-\\[32rem\\].flex-col'
OUTCOME = '.flex.text-xs.leading-5.text-gray-600'


def validate(step, *, minimum_clauses=2):
    if (not isinstance(step,dict)
            or set(step) - {'id','action','clauses','match','connectors','effect','target','field_bindings'}
            or step.get('action','native_condition_group') != 'native_condition_group'):
        raise Stop('Unsupported native form condition group')
    bindings=condition_bindings(step)
    labels={field['label'] for field in bindings}
    field_types={field['label']:field['field_type'] for field in bindings}
    target_labels={field['label'] for field in bindings}
    if not isinstance(step.get('match'),str) or step['match'] not in ('all','any','mixed'):
        raise Stop('Condition group match must be all, any or explicit mixed')
    if not isinstance(step.get('effect'),str) or step['effect'] not in ('Hide Field','Show Field'):
        raise Stop('Condition groups support captured single-field Show/Hide effects')
    if not isinstance(step.get('target'),str) or step['target'] not in TARGETS|target_labels:
        raise Stop('Condition target must use a captured native field label')
    clauses = step.get('clauses')
    if (type(minimum_clauses) is not int or minimum_clauses not in (1,2)
            or not isinstance(clauses,list) or not minimum_clauses <= len(clauses) <= 20):
        raise Stop('A native condition requires '+str(minimum_clauses)+' to 20 explicit clauses')
    if step['match']=='mixed':
        joins=step.get('connectors')
        if (not isinstance(joins,list) or len(joins)!=len(clauses)-1
                or any(not isinstance(join,str) or join not in ('and','or') for join in joins)
                or set(joins)!={'and','or'}):
            raise Stop('Mixed conditions require one ordered and/or connector between each clause and both connector types')
    elif 'connectors' in step:
        raise Stop('Explicit connectors require match=mixed; all/any must not carry ignored connector data')
    seen = set()
    for clause in clauses:
        if (not isinstance(clause,dict)
                or set(clause)-{'if_field','operator','value'}
                or not isinstance(clause.get('if_field'),str) or clause['if_field'] not in FIELDS|labels
                or not isinstance(clause.get('operator'),str) or clause['operator'] not in UNARY|BINARY):
            raise Stop('Compound clauses require captured fields and operators')
        if clause['operator'] in CHECKED and clause['if_field'] not in ('TnC1','TnC2'):
            raise Stop('Checked conditions require a native consent source')
        date_type=field_types.get(clause['if_field'], 'DATE' if clause['if_field']=='Date of birth' else None)
        date=date_type in ('DATE','DATE_TIME')
        number=field_types.get(clause['if_field']) in ('NUMERICAL','MONETORY','SCORE')
        choices=field_types.get(clause['if_field']) in field_identity.OPTION_TYPES
        time=date_type=='TIME'
        unary_only=field_types.get(clause['if_field']) in ('FILE_UPLOAD','SIGNATURE','TEXTBOX_LIST','RATING')
        allowed=frozenset() if unary_only else DATE_BINARY if date or time else OPTION_BINARY if choices else NUMBER_BINARY if number else TEXT_BINARY
        if clause['operator'] not in ((UNARY if clause['if_field'] in ('TnC1','TnC2') else UNARY-CHECKED)|allowed):
            raise Stop('Condition operator is not captured for its bound field type')
        if clause['operator'] in UNARY:
            if 'value' in clause:
                raise Stop('Unary compound clauses must not carry ignored values')
        elif clause['operator']=='Between':
            bounds=clause.get('value')
            if date:
                try:
                    if not isinstance(bounds,list) or len(bounds)!=2:raise ValueError()
                    fmt='%Y-%m-%d' if date_type=='DATE' else '%Y-%m-%d %H:%M'
                    pattern=r'\d{4}-\d{2}-\d{2}' if date_type=='DATE' else r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}'
                    if any(not isinstance(bound,str) or not re.fullmatch(pattern,bound) for bound in bounds):raise ValueError()
                    parsed=[datetime.strptime(bound,fmt) for bound in bounds]
                    if parsed[0]>parsed[1]:raise ValueError()
                except ValueError:
                    raise Stop('Date & time Between requires two ordered YYYY-MM-DD HH:MM values') from None
            elif time:
                if (not isinstance(bounds,list) or len(bounds)!=2 or any(not isinstance(v,str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',v) for v in bounds) or bounds[0]>bounds[1]):
                    raise Stop('Time Between requires two ordered HH:MM values')
            elif (not number or not isinstance(bounds,list) or len(bounds)!=2
                    or any(not isinstance(bound,str) or len(bound)>5000 or not re.fullmatch(
                        r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',bound) for bound in bounds)
                    or Decimal(bounds[0])>Decimal(bounds[1])):
                raise Stop('Between requires two ordered explicit finite decimal bounds on a Number field')
        elif (not isinstance(clause.get('value'),str) or not clause['value']
                or clause['value']!=clause['value'].strip() or len(clause['value'])>5000
                or any(ord(c)<32 for c in clause['value'])):
            raise Stop('Binary compound clauses require explicit nonempty text without surrounding whitespace')
        if date and clause['operator'] in DATE_BINARY-{'Between'}:
            try:
                value=clause['value']
                fmt='%Y-%m-%d' if date_type=='DATE' else '%Y-%m-%d %H:%M'
                pattern=r'\d{4}-\d{2}-\d{2}' if date_type=='DATE' else r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}'
                if not re.fullmatch(pattern,value):raise ValueError()
                datetime.strptime(value,fmt)
            except (KeyError,ValueError,TypeError):
                raise Stop('Date & time comparison requires YYYY-MM-DD HH:MM') from None
        if time and clause['operator'] in DATE_BINARY-{'Between'} and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',clause['value']):
            raise Stop('Time comparison requires HH:MM')
        if number and clause['operator'] in NUMBER_BINARY-{'Between'} and not re.fullmatch(
                r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',clause['value']):
            raise Stop('Number condition comparisons require finite decimal text')
        value=clause.get('value')
        key = clause['if_field'],clause['operator'],tuple(value) if isinstance(value,list) else value
        if key in seen:
            raise Stop('Duplicate compound clauses require reconciliation')
        seen.add(key)
    return deepcopy(step)


def condition_bindings(step):
    return field_identity.validate(step['field_bindings'],reserved=TARGETS) if 'field_bindings' in step else []


def _preflight_fields(frame,plan,identity):
    if 'field_bindings' in plan:
        field_identity.preflight(frame,plan['field_bindings'],identity)


def configuration_hash(step):
    valid = validate(step)
    payload = {key:valid[key] for key in ('clauses','match','effect','target')}
    if 'connectors' in valid:payload['connectors']=valid['connectors']
    if 'field_bindings' in valid:payload['field_bindings']=valid['field_bindings']
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _one(node, reason):
    if node.count() != 1:
        raise Stop(reason)
    return node


def _selected(node):
    # The native selector id belongs to a div.n-select. The displayed selected
    # label is a DOM child of its unique .n-base-selection-label, never input.value.
    label = _one(node.locator('.n-base-selection-label'),
                 'Native compound selection label is missing or ambiguous')
    render = _one(label.locator('.n-base-selection-label__render-label'),
                  'Native compound selected text structure changed')
    title, text = label.get_attribute('title'), (render.inner_text() or '').strip()
    if not isinstance(title,str) or not title or title != text:
        raise Stop('Native compound selected identity is unavailable or inconsistent')
    return text


def _choose(frame, selector, label):
    node = _one(frame.locator(selector),'Native compound select is missing or ambiguous')
    click(node)
    if ((selector.startswith('#selectedField-') or selector=='#selectedFieldShowHide')
            and label not in TARGETS):
        search=_one(node.locator('input.n-base-selection-input'),
                    'Native custom condition field search is missing or ambiguous')
        fill(search,label)
    option = frame.locator('.n-base-select-option:visible').get_by_text(label,exact=True)
    if selector.startswith('#picklistOptions-') and label=='Other' and option.count()==0:
        option=frame.locator('.n-base-select-option:visible').get_by_text('--Other--',exact=True)
    wait_until(lambda:option.count()==1,'Native condition choice did not resolve uniquely: '+label)
    click(_one(option,'Compound condition choice is absent or ambiguous: '+label))
    wait_until(lambda:(_selected_choice(node) if selector.startswith('#picklistOptions-') else _selected(node))==label,
               'Native compound selection did not persist in the modal')


def _tokens(node):
    return node.locator(':scope > span').evaluate_all('nodes => nodes.map(n => n.textContent.trim())')


def _connectors(plan):
    """Native edge labels, in source-row order; no Boolean precedence inferred."""
    return (list(plan['connectors']) if plan['match']=='mixed' else
            [('and' if plan['match']=='all' else 'or')]*(len(plan['clauses'])-1))


def _predicate_identity(plan):
    clauses=tuple((clause['if_field'],clause['operator'],
                   tuple(clause['value']) if isinstance(clause.get('value'),list) else clause.get('value',''))
                  for clause in plan['clauses'])
    if plan['match']=='mixed':
        return ('mixed',clauses,tuple(_connectors(plan)))
    return (('single' if len(clauses)==1 else plan['match']),tuple(sorted(clauses)))


def _expected_rows(plan):
    joins = _connectors(plan)
    return [[('If' if index==0 else joins[index-1].title()),clause['if_field'],clause['operator']]
            + ([clause['value'][0]+' And '+clause['value'][1]] if clause['operator']=='Between' else
               [clause['value']] if 'value' in clause else [])
            for index,clause in enumerate(plan['clauses'])]


def _inventory(dialog):
    """Read every displayed rule card, not a matching fragment of its text."""
    cards = dialog.locator(CARD)
    no_rules = dialog.get_by_text('No existing conditions yet',exact=True)
    if cards.count()==0:
        if no_rules.count()!=1:
            raise Stop('Native condition inventory is unavailable; refusing inferred absence')
        return []
    if no_rules.count():
        raise Stop('Native condition empty-state conflicts with displayed rule cards')
    inventory = []
    for index in range(cards.count()):
        card = cards.nth(index)
        if (card.locator('#edit-condition').count()!=1
                or card.locator('#delete-condition').count()!=1):
            raise Stop('Native condition card actions changed')
        effect = _one(card.locator('.text-sm.font-semibold'),
                      'Native condition card effect heading changed').inner_text().strip()
        rows = card.locator('.condition-summary-row')
        if rows.count()<1:
            raise Stop('Native condition card has no readable clauses')
        clauses = [_tokens(rows.nth(i)) for i in range(rows.count())]
        outcome = _tokens(_one(card.locator(OUTCOME),
                               'Native condition card target row changed'))
        inventory.append({'effect':effect,'rows':clauses,'outcome':outcome})
    return inventory


def _expected(plan):
    return [{'effect':plan['effect'],'rows':_expected_rows(plan),
             'outcome':[plan['effect'],plan['target']]}]


def _value_input(modal,index,*,unary=False):
    """Bind the captured n-input DIV to its actual nested text input.

    Unary operators retain a positively invisible wrapper in the native DOM.
    Its existence is not an ignored authored value. A visible value control,
    ambiguous wrapper or changed nested-input shape still refuses.
    """
    wrapper=modal.locator('#inputValue-'+str(index))
    if unary and wrapper.count()==0:return None  # previously captured absent shape
    _one(wrapper,'Native condition value wrapper is missing or ambiguous')
    classes=(wrapper.get_attribute('class') or '').split()
    if 'n-input' not in classes:
        raise Stop('Native condition value owner is not the captured n-input wrapper')
    control=_one(wrapper.locator('input.n-input__input-el'),
                 'Native condition nested value input is missing or ambiguous')
    if (control.get_attribute('type')!='text'
            or control.get_attribute('placeholder')!='Please Type a value here'):
        raise Stop('Native condition nested value input identity changed')
    if unary:
        if 'invisible' not in classes or wrapper.is_visible() or control.is_visible():
            raise Stop('Native unary condition unexpectedly exposes a value control')
        return None
    if 'invisible' in classes or not wrapper.is_visible() or not control.is_visible():
        raise Stop('Native binary condition value input is not visible')
    return control



def _between_inputs(modal,index):
    controls=[]
    for side,placeholder in (('Start','Start Value'),('End','End Value')):
        wrapper=_one(modal.locator('#inputValue'+side+'-'+str(index)),
                     'Native Between range wrapper is missing or ambiguous')
        if 'n-input' not in (wrapper.get_attribute('class') or '').split():
            raise Stop('Native Between wrapper identity changed')
        control=_one(wrapper.locator('input.n-input__input-el'),
                     'Native Between nested range input is missing or ambiguous')
        if (not wrapper.is_visible() or not control.is_visible()
                or control.get_attribute('type')!='text'
                or control.get_attribute('placeholder')!=placeholder):
            raise Stop('Native Between input type, placeholder or visibility changed')
        controls.append(control)
        if side=='Start':owner=wrapper.locator('..').locator('..').locator('..')
    if owner.locator('#selectedField-'+str(index)).count()!=1:
        raise Stop('Native Between inclusion controls belong to another predicate')
    for side in ('start','end'):
        inclusion=_one(owner.locator('#include-'+side),'Native Between inclusion control is ambiguous')
        if (not inclusion.is_visible() or inclusion.get_attribute('role')!='checkbox'
                or inclusion.get_attribute('aria-checked')!='true'):
            raise Stop('Only the captured inclusive Between endpoints are supported')
    return controls




def _selected_choice(node):
    value=_selected(node)
    return 'Other' if value=='--Other--' else value


def _picklist(modal,index):
    node=_one(modal.locator('#picklistOptions-'+str(index)),
              'Native option-valued condition picker is missing or ambiguous')
    if not node.is_visible() or 'n-select' not in (node.get_attribute('class') or '').split():
        raise Stop('Native option-valued condition picker changed')
    return node


def _date_controls(modal,index,side=''):
    date=_one(modal.locator('#inputDateTime'+side+'Date-'+str(index)),'Native condition date picker changed')
    time=_one(modal.locator('#inputDateTime'+side+'Time-'+str(index)),'Native condition time picker changed')
    if date.get_attribute('aria-label')!=('End date' if side=='End' else 'Start date') or time.get_attribute('aria-label')!=(side+' time' if side else 'Time format'):
        raise Stop('Native condition date/time picker identity changed')
    day=_one(date.locator('input.n-input__input-el'),'Native condition date input changed')
    clock=_one(time.locator('input.n-input__input-el'),'Native condition time input changed')
    if day.get_attribute('placeholder')!='Select Date' or clock.get_attribute('placeholder')!='HH:MM':
        raise Stop('Native condition date/time input placeholders changed')
    return date,day,clock


def _write_date(modal,frame,index,value,writer,side=''):
    if frame is None:raise Stop('Native date picker requires its exact frame portal')
    wanted=datetime.strptime(value,'%Y-%m-%d %H:%M')
    owner,day,clock=_date_controls(modal,index,side)
    _select_calendar_date(frame,owner,wanted)
    writer(clock,wanted.strftime('%H:%M'));clock.press('Tab')
    if day.input_value()!=wanted.strftime('%Y-%m-%d') or clock.input_value()!=wanted.strftime('%H:%M'):
        raise Stop('Native condition date/time did not retain the authored value')


def _select_calendar_date(frame,owner,wanted):
    click(owner)
    panel=_one(frame.locator('.n-date-panel-calendar:visible'),'Native condition calendar is missing or ambiguous')
    header=_one(panel.locator('.n-date-panel-month__text'),'Native condition calendar month changed')
    for _ in range(241):
        try:shown=datetime.strptime(header.inner_text().strip(),'%b %Y')
        except ValueError:raise Stop('Native condition calendar month is unrecognized') from None
        delta=(wanted.year-shown.year)*12+wanted.month-shown.month
        if not delta:break
        before=header.inner_text()
        click(_one(panel.locator('.n-date-panel-month__next' if delta>0 else '.n-date-panel-month__prev'),
                   'Native condition calendar navigation changed'))
        wait_until(lambda:header.inner_text()!=before,'Native condition calendar month did not change')
    else:raise Stop('Native condition date is outside the bounded calendar navigation range')
    dates=panel.locator('.n-date-panel-date:not(.n-date-panel-date--excluded)').get_by_text(str(wanted.day),exact=True)
    click(_one(dates,'Native condition calendar day is missing or ambiguous'))


def _date_range_controls(modal,index):
    controls=[_date_controls(modal,index,side) for side in ('Start','End')]
    owner=controls[0][0]
    for _ in range(4):owner=owner.locator('..')
    if owner.locator('#selectedField-'+str(index)).count()!=1:
        raise Stop('Native date range inclusions belong to another predicate')
    for side in ('start','end'):
        box=_one(owner.locator('#include-'+side),'Native date range inclusion changed')
        if not box.is_visible() or box.get_attribute('role')!='checkbox' or box.get_attribute('aria-checked')!='true':
            raise Stop('Only captured inclusive date range endpoints are supported')
    return controls


def _date_only_controls(modal,index,clause):
    values=clause.get('value')
    values=values if isinstance(values,list) else [values]
    if not values or any(not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) for value in values):
        return []
    row=modal.locator('#selectedField-'+str(index)).locator('..')
    inputs=row.locator('input[placeholder="Select Date"]')
    if inputs.count()==0:return []
    if inputs.count()!=len(values) or row.locator('input[placeholder="HH:MM"]').count():
        raise Stop('Native date-only condition controls are ambiguous')
    controls=[inputs.nth(i) for i in range(inputs.count())]
    if any(not control.is_visible() or control.get_attribute('type')!='text' for control in controls):
        raise Stop('Native date-only condition inputs changed')
    if len(values)==2:
        owner=row.locator('..')
        if owner.locator('#selectedField-'+str(index)).count()!=1:
            raise Stop('Native date range inclusions belong to another predicate')
        for side in ('start','end'):
            box=_one(owner.locator('#include-'+side),'Native date range inclusion changed')
            if not box.is_visible() or box.get_attribute('role')!='checkbox' or box.get_attribute('aria-checked')!='true':
                raise Stop('Only captured inclusive date range endpoints are supported')
    return controls


def _time_only_controls(modal,index,clause):
    values=clause.get('value');values=values if isinstance(values,list) else [values]
    if not values or any(not isinstance(value,str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',value) for value in values):return []
    row=modal.locator('#selectedField-'+str(index)).locator('..')
    controls=row.locator('input[placeholder="HH:MM"]')
    if controls.count()==0:return []
    if controls.count()!=len(values) or row.locator('input[placeholder="Select Date"]').count():
        raise Stop('Native time-only condition controls are ambiguous')
    result=[controls.nth(i) for i in range(controls.count())]
    if any(not node.is_visible() or node.get_attribute('type')!='text' for node in result):
        raise Stop('Native time-only condition input changed')
    if len(values)==2:
        owner=row.locator('..')
        if owner.locator('#selectedField-'+str(index)).count()!=1:
            raise Stop('Native time range inclusions belong to another predicate')
        for side in ('start','end'):
            box=_one(owner.locator('#include-'+side),'Native time range inclusion changed')
            if not box.is_visible() or box.get_attribute('role')!='checkbox' or box.get_attribute('aria-checked')!='true':
                raise Stop('Only inclusive time range endpoints are supported')
    return result


def _write_clause_value(modal,index,clause,*,writer=None,frame=None):
    writer=fill if writer is None else writer
    time_only=_time_only_controls(modal,index,clause)
    date_only=_date_only_controls(modal,index,clause)
    if time_only:
        values=clause['value'] if isinstance(clause['value'],list) else [clause['value']]
        for control,value in zip(time_only,values):writer(control,value);control.press('Tab')
        if [control.input_value() for control in time_only]!=values:
            raise Stop('Native time-only condition did not retain authored values')
    elif date_only:
        if frame is None:raise Stop('Native date picker requires its exact frame portal')
        values=clause['value'] if isinstance(clause['value'],list) else [clause['value']]
        for control,value in zip(date_only,values):
            _select_calendar_date(frame,control,datetime.strptime(value,'%Y-%m-%d'))
        if [control.input_value() for control in date_only]!=values:
            raise Stop('Native date-only condition did not retain authored values')
    elif modal.locator('#inputDateTimeStartDate-'+str(index)).count()==1:
        _date_range_controls(modal,index)
        for side,value in zip(('Start','End'),clause['value']):_write_date(modal,frame,index,value,writer,side)
        _read_clause_value(modal,index,clause)
    elif modal.locator('#inputDateTimeDate-'+str(index)).count()==1:
        _write_date(modal,frame,index,clause['value'],writer)
    elif clause['operator']=='Between':
        controls=_between_inputs(modal,index)
        for control,value in zip(controls,clause['value']):writer(control,value)
        if [control.input_value() for control in _between_inputs(modal,index)]!=clause['value']:
            raise Stop('Native Between bounds did not accept the authored range')
    elif modal.locator('#inputValue-'+str(index)).count()==0:
        if frame is None:raise Stop('Native choice condition requires its exact frame portal')
        _picklist(modal,index)
        _choose(frame,'#picklistOptions-'+str(index),clause['value'])
        if _selected_choice(_picklist(modal,index))!=clause['value']:
            raise Stop('Native choice condition did not accept its authored option')
    else:
        value=_value_input(modal,index)
        writer(value,clause['value'])
        if value.input_value()!=clause['value']:
            raise Stop('Native condition value did not accept the authored text')


def _read_clause_value(modal,index,clause):
    if clause['operator'] in UNARY:
        _value_input(modal,index,unary=True)
    elif _time_only_controls(modal,index,clause):
        controls=_time_only_controls(modal,index,clause)
        values=clause['value'] if isinstance(clause['value'],list) else [clause['value']]
        if [control.input_value() for control in controls]!=values:
            raise Stop('Native time-only condition differs from authored values')
    elif _date_only_controls(modal,index,clause):
        controls=_date_only_controls(modal,index,clause)
        values=clause['value'] if isinstance(clause['value'],list) else [clause['value']]
        if [control.input_value() for control in controls]!=values:
            raise Stop('Native date-only condition differs from authored values')
    elif modal.locator('#inputDateTimeStartDate-'+str(index)).count()==1:
        controls=_date_range_controls(modal,index)
        if [day.input_value()+' '+clock.input_value() for _,day,clock in controls]!=clause['value']:
            raise Stop('Native date range differs from authored values')
    elif modal.locator('#inputDateTimeDate-'+str(index)).count()==1:
        _,day,clock=_date_controls(modal,index)
        if day.input_value()+' '+clock.input_value()!=clause['value']:
            raise Stop('Native condition date/time differs from authored value')
    elif clause['operator']=='Between':
        if [control.input_value() for control in _between_inputs(modal,index)]!=clause['value']:
            raise Stop('Native Between bounds differ from the authored range')
    elif modal.locator('#inputValue-'+str(index)).count()==0:
        if _selected_choice(_picklist(modal,index))!=clause['value']:
            raise Stop('Native choice condition differs from its authored option')
    elif _value_input(modal,index).input_value()!=clause['value']:
        raise Stop('Native compound value differs from the authored clause')


def _modal_state(modal,plan):
    count = len(plan['clauses'])
    sources = modal.locator('[id^="selectedField-"]')
    operators = modal.locator('[id^="selectedOperation-"]')
    if sources.count()!=count or operators.count()!=count:
        raise Stop('Native compound row count differs from the authored group')
    for index,clause in enumerate(plan['clauses']):
        if (_selected(_one(modal.locator('#selectedField-'+str(index)),
                           'Native compound source is missing'))!=clause['if_field']
                or _selected(_one(modal.locator('#selectedOperation-'+str(index)),
                                  'Native compound operator is missing'))!=clause['operator']):
            raise Stop('Native compound clause differs from the authored source/operator')
        _read_clause_value(modal,index,clause)
    joins = modal.locator('.n-tabs')
    if joins.count()!=count:
        raise Stop('Native compound connector count changed')
    wanted = _connectors(plan)
    for index in range(count):
        active = joins.nth(index).locator('.n-tabs-tab--active')
        if (active.count()!=1 or active.get_attribute('data-name') !=
                ('then' if index==count-1 else wanted[index])):
            raise Stop('Native compound AND/OR connector differs from the authored match mode')
    if (_selected(modal.locator('#showHideFieldType'))!=plan['effect']
            or _selected(modal.locator('#selectedFieldShowHide'))!=plan['target']):
        raise Stop('Native compound outcome differs from its authored effect/target')


def _wait_for_form_save(page,save):
    """Allow native Save traffic to settle before an independent navigation.

    Enabled controls alone can precede an asynchronous Save request. A native
    network-idle wait does not establish success; exact fresh readback still
    decides persistence. Unsettled traffic is an uncertain write, not a retry.
    """
    wait_until(lambda:save.count()==1 and save.is_enabled(),'Native form Save remains busy')
    try:
        page.wait_for_load_state('networkidle',timeout=45000)
    except Exception:
        raise Stop('Native form Save traffic did not settle; reconcile before another write') from None
    wait_until(lambda:save.count()==1 and save.is_enabled(),'Native form Save became busy again')


def configure(page,step):
    plan = validate(step)
    frame = form_builder(page)
    title = frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or not read_editor_title(title).strip():
        raise Stop('Native compound form identity is missing or ambiguous')
    name, editor_url = read_editor_title(title),page.url

    def identity():
        if page.url!=editor_url or title.count()!=1 or read_editor_title(title)!=name:
            raise Stop('Native compound form identity changed during editing')

    def open_conditions():
        dialog = frame.get_by_role('dialog')
        if dialog.count():
            if dialog.count()!=1 or dialog.get_by_text('Form Element',exact=True).count()!=1:
                raise Stop('An unrelated native dialog is already open')
            click(_one(dialog.get_by_role('button',name='Close',exact=True),
                       'Native Form Element close changed'))
        click(frame.get_by_role('tab',name='Edit',exact=True))
        click(frame.get_by_role('button',name='Open Conditional Logic',exact=True))
        dialog = frame.get_by_role('dialog')
        dialog.wait_for(state='visible',timeout=45000)
        return _one(dialog,'Native Conditions dialog is missing or ambiguous')

    _preflight_fields(frame,plan,identity)
    dialog = open_conditions()
    before, wanted = _inventory(dialog),_expected(plan)
    if before and before!=wanted:
        raise Stop('Existing native conditions differ; explicit reconciliation is required')
    added = not before
    if added:
        click(_one(dialog.get_by_text('Show/Hide Fields',exact=True),
                   'Native Show/Hide Fields entry changed'))
        # The active rule editor is the same native dialog as the Conditions
        # drawer. Counts and native row IDs bind every operation.
        modal = frame.get_by_role('dialog')
        _one(modal,'Native compound editor is missing or ambiguous')
        for index,clause in enumerate(plan['clauses']):
            identity()
            if modal.locator('[id^="selectedField-"]').count()!=index+1:
                raise Stop('Native compound editor has unrelated or missing source rows')
            _choose(frame,'#selectedField-'+str(index),clause['if_field'])
            _choose(frame,'#selectedOperation-'+str(index),clause['operator'])
            if clause['operator'] in BINARY:
                _write_clause_value(modal,index,clause,frame=frame)
            if index<len(plan['clauses'])-1:
                joins = modal.locator('.n-tabs')
                if joins.count()!=index+1:
                    raise Stop('Native compound append connector changed')
                choice = joins.nth(index).locator('[data-name="'+_connectors(plan)[index]+'"]')
                click(_one(choice,'Native compound append option is ambiguous'))
                wait_until(lambda:modal.locator('[id^="selectedField-"]').count()==index+2,
                           'Native compound row did not append once')
        _choose(frame,'#showHideFieldType',plan['effect'])
        _choose(frame,'#selectedFieldShowHide',plan['target'])
        _modal_state(modal,plan)
        identity()
        save = _one(modal.locator('#modal-footer-btn-positive-action'),
                    'Native compound modal Save changed')
        if not save.is_enabled():
            raise Stop('Native compound condition is invalid; Save not attempted')
        click(save)
        wait_until(lambda:dialog.locator(CARD).count()==1
                   and dialog.locator('.condition-summary-row').count()==len(plan['clauses']),
                   'Native compound saved card did not appear')
        if _inventory(dialog)!=wanted:
            raise Stop('Native compound saved card differs from the complete authored rule')
    # Save-close persists only this exact rule inventory; there is no append
    # into arbitrary existing rules and no card-deletion implementation.
    if _inventory(dialog)!=wanted:
        raise Stop('Native condition inventory changed before save-close')
    identity()
    click(_one(dialog.locator('#conditional-logic-save-close'),
               'Native Conditions save-close changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    if added:
        identity()
        save = _one(frame.get_by_role('button',name='Save',exact=True),
                    'Native outer form Save changed')
        click(save)
        _wait_for_form_save(page,save)
    reopen_editor(page,'form',name,editor_url)
    frame = form_builder(page)
    _preflight_fields(frame,plan,identity)
    dialog = open_conditions()
    if _inventory(dialog)!=wanted:
        raise Stop('Native compound condition did not persist after independent reopen')
    click(_one(dialog.locator('#conditional-logic-save-close'),
               'Reopened native Conditions save-close changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    return {'status':'CONDITION_GROUP_SAVED_AND_REOPENED' if added else 'CONDITION_GROUP_REUSED_AND_REOPENED',
        'kind':'form_condition_group','editor_url':page.url,
        'configuration_sha256':configuration_hash(plan),'clause_count':len(plan['clauses']),
        'independent_readback':'VERIFIED','submission_verified':False,'behavior_verified':False}
