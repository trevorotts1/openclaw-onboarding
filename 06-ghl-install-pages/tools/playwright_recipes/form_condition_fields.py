"""Captured local Single Line identities for native form conditions.

No contact-field API definition is created or inferred. The custom TEXT canvas
label and its separately read native Query Key bind one existing form widget.
"""
from copy import deepcopy
import re

if __package__:
    from .field_placement import CANVAS_ITEMS,CAPTURED_FIELDS,_close_initial,_close_properties
    from .skill6_playwright import Stop,click
else:
    from field_placement import CANVAS_ITEMS,CAPTURED_FIELDS,_close_initial,_close_properties
    from skill6_playwright import Stop,click


def validate(value,*,reserved=()):
    if not isinstance(value,list) or not 1<=len(value)<=100:
        raise Stop('Condition field_bindings requires the complete nonempty custom TEXT inventory')
    labels=set();keys=set()
    builtin_keys={key for field in CAPTURED_FIELDS.values() for key in field['query_keys']}
    for field in value:
        if (not isinstance(field,dict) or set(field)!={'label','query_key','field_type'}
                or field['field_type']!='TEXT'
                or not isinstance(field['label'],str) or not field['label'].strip()
                or field['label']!=field['label'].strip() or len(field['label'])>256
                or any(ord(c)<32 for c in field['label'])
                or not isinstance(field['query_key'],str)
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,256}',field['query_key'])):
            raise Stop('Condition bindings require exact captured TEXT label and native Query Key')
        if (field['label'] in labels or field['label'] in reserved
                or field['query_key'] in keys or field['query_key'] in builtin_keys):
            raise Stop('Condition field labels and Query Keys must be unique and not shadow built-ins')
        labels.add(field['label']);keys.add(field['query_key'])
    return deepcopy(value)


def _one(node,reason):
    if node.count()!=1:raise Stop(reason)
    return node


def _texts(frame):
    """Read every custom TEXT label, including siblings not used by a rule."""
    items=frame.locator(CANVAS_ITEMS)
    if not items.count():raise Stop('Native condition canvas inventory is unavailable')
    result=[]
    for index in range(items.count()):
        item=items.nth(index)
        labels=_one(item.locator('[data-field-type]'),'Native condition canvas field type is ambiguous')
        if labels.get_attribute('data-field-type')!='TEXT':continue
        if (labels.get_attribute('contenteditable')!='true'
                or labels.get_attribute('role')!='textbox'
                or labels.get_attribute('aria-label')!='Label'):
            raise Stop('Native custom TEXT label identity changed')
        label=labels.inner_text().strip()
        result.append((item,labels,label))
    if len({label for _,_,label in result})!=len(result):
        raise Stop('Native custom TEXT labels are duplicated; condition identity is ambiguous')
    return result


def preflight(frame,bindings,identity):
    """Read complete local TEXT label/key bindings without editing any property."""
    _close_initial(frame)
    entries=_texts(frame)
    if [label for _,_,label in entries]!=[field['label'] for field in bindings]:
        raise Stop('Native custom TEXT inventory differs from complete condition field_bindings')
    observed=[]
    for index,field in enumerate(bindings):
        identity()
        current=_texts(frame)
        if [label for _,_,label in current]!=[row['label'] for row in bindings]:
            raise Stop('Native custom TEXT canvas changed during condition preflight')
        item,label,_=current[index]
        control=_one(item.locator('input.form-placeholder.form-control'),
                     'Native custom TEXT canvas input changed')
        if control.get_attribute('name') not in (None,''):
            raise Stop('Local custom TEXT unexpectedly has an API field identity')
        click(label)
        gear=item.locator('[aria-label="Open settings"]')
        gear.wait_for(state='visible',timeout=45000)
        _one(gear,'Native custom TEXT settings control changed')
        click(gear)
        frame.get_by_text('General Settings',exact=True).wait_for(state='visible',timeout=45000)
        query=_one(frame.locator('#fieldQueryKey input.n-input__input-el'),
                   'Native custom TEXT Query Key input changed')
        if not query.is_visible() or query.input_value()!=field['query_key']:
            raise Stop('Native custom TEXT Query Key differs from condition binding')
        observed.append(dict(field))
        _close_properties(frame)
    identity()
    if [label for _,_,label in _texts(frame)]!=[field['label'] for field in bindings]:
        raise Stop('Native custom TEXT canvas changed after condition preflight')
    return observed
