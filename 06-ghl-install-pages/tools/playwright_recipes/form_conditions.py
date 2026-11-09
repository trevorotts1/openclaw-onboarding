"""Native ordered AND/OR Show/Hide groups captured November 9, 2026.

The owner runner supplies tenant checks and the intent-before-write journal.
This handler creates one rule only when the entire existing condition inventory
is empty, or reuses exactly the same persisted rule. It never overwrites,
deletes, or silently appends to unrelated conditions.
"""
from copy import deepcopy
import hashlib
import json
import re

if __package__:
    from .assessments import reopen_editor
    from .skill6_playwright import Stop, click, fill, form_builder, wait_until
else:
    from assessments import reopen_editor
    from skill6_playwright import Stop, click, fill, form_builder, wait_until


FIELDS = frozenset(('First Name','Last Name','Phone','Email','Website','TnC1',
                    'TnC2','Organization','Full Name','Date of birth'))
TARGETS = FIELDS | {'Privacy Policy | Terms of Service'}
UNARY = frozenset(('Is Empty','Is Filled'))
BINARY = frozenset(('Is Equal To','Is Not Equal To','Contains','Does Not Contain',
                    'Starts With','Ends With'))
CARD = 'div.flex.w-\\[32rem\\].flex-col'
OUTCOME = '.flex.text-xs.leading-5.text-gray-600'


def validate(step, *, minimum_clauses=2):
    if (not isinstance(step,dict)
            or set(step) - {'id','action','clauses','match','connectors','effect','target'}
            or step.get('action','native_condition_group') != 'native_condition_group'):
        raise Stop('Unsupported native form condition group')
    if not isinstance(step.get('match'),str) or step['match'] not in ('all','any','mixed'):
        raise Stop('Condition group match must be all, any or explicit mixed')
    if not isinstance(step.get('effect'),str) or step['effect'] not in ('Hide Field','Show Field'):
        raise Stop('Condition groups support captured single-field Show/Hide effects')
    if not isinstance(step.get('target'),str) or step['target'] not in TARGETS:
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
                or not isinstance(clause.get('if_field'),str) or clause['if_field'] not in FIELDS
                or not isinstance(clause.get('operator'),str) or clause['operator'] not in UNARY|BINARY):
            raise Stop('Compound clauses require captured fields and operators')
        if clause['operator'] in UNARY:
            if 'value' in clause:
                raise Stop('Unary compound clauses must not carry ignored values')
        elif (not isinstance(clause.get('value'),str) or not clause['value']
                or clause['value']!=clause['value'].strip() or len(clause['value'])>5000
                or any(ord(c)<32 for c in clause['value'])):
            raise Stop('Binary compound clauses require explicit nonempty text without surrounding whitespace')
        key = clause['if_field'],clause['operator'],clause.get('value')
        if key in seen:
            raise Stop('Duplicate compound clauses require reconciliation')
        seen.add(key)
    return deepcopy(step)


def configuration_hash(step):
    valid = validate(step)
    payload = {key:valid[key] for key in ('clauses','match','effect','target')}
    if 'connectors' in valid:payload['connectors']=valid['connectors']
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
    option = frame.locator('.n-base-select-option').get_by_text(label,exact=True)
    click(_one(option,'Compound condition choice is absent or ambiguous: '+label))
    wait_until(lambda:_selected(node)==label,'Native compound selection did not persist in the modal')


def _tokens(node):
    return node.locator('span').evaluate_all('nodes => nodes.map(n => n.textContent.trim())')


def _connectors(plan):
    """Native edge labels, in source-row order; no Boolean precedence inferred."""
    return (list(plan['connectors']) if plan['match']=='mixed' else
            [('and' if plan['match']=='all' else 'or')]*(len(plan['clauses'])-1))


def _predicate_identity(plan):
    clauses=tuple((clause['if_field'],clause['operator'],clause.get('value',''))
                  for clause in plan['clauses'])
    if plan['match']=='mixed':
        return ('mixed',clauses,tuple(_connectors(plan)))
    return (('single' if len(clauses)==1 else plan['match']),tuple(sorted(clauses)))


def _expected_rows(plan):
    joins = _connectors(plan)
    return [[('If' if index==0 else joins[index-1].title()),clause['if_field'],clause['operator']]
            + ([clause['value']] if 'value' in clause else [])
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
        value = modal.locator('#inputValue-'+str(index))
        if clause['operator'] in UNARY:
            if value.count():
                raise Stop('Unary compound clause unexpectedly contains a value control')
        elif value.count()!=1 or value.input_value()!=clause['value']:
            raise Stop('Native compound value differs from the authored clause')
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
    if title.count()!=1 or not title.input_value().strip():
        raise Stop('Native compound form identity is missing or ambiguous')
    name, editor_url = title.input_value(),page.url

    def identity():
        if page.url!=editor_url or title.count()!=1 or title.input_value()!=name:
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
                value = _one(modal.locator('#inputValue-'+str(index)),
                             'Native binary compound value control changed')
                fill(value,clause['value'])
                if value.input_value()!=clause['value']:
                    raise Stop('Native compound value did not accept the authored text')
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
