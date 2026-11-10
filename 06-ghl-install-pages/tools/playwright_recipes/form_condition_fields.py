"""Captured local text and Number identities for native form conditions.

No contact-field API definition is created or inferred. The typed canvas label and its separately read native Query Key bind one existing
form widget. Number bindings reuse captured native General Settings controls.
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
        raise Stop('Condition field_bindings requires the complete nonempty custom field inventory')
    labels=set();keys=set()
    builtin_keys={key for field in CAPTURED_FIELDS.values() for key in field['query_keys']}
    for field in value:
        if (not isinstance(field,dict) or set(field)!={'label','query_key','field_type'}
                or field['field_type'] not in ('TEXT','NUMERICAL')
                or not isinstance(field['label'],str) or not field['label'].strip()
                or field['label']!=field['label'].strip() or len(field['label'])>256
                or any(ord(c)<32 for c in field['label'])
                or not isinstance(field['query_key'],str)
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,256}',field['query_key'])):
            raise Stop('Condition bindings require exact captured TEXT/NUMERICAL label and native Query Key')
        if (field['label'] in labels or field['label'] in reserved
                or field['query_key'] in keys or field['query_key'] in builtin_keys):
            raise Stop('Condition field labels and Query Keys must be unique and not shadow built-ins')
        labels.add(field['label']);keys.add(field['query_key'])
    return deepcopy(value)


def _one(node,reason):
    if node.count()!=1:raise Stop(reason)
    return node


def _texts(frame,field_types=('TEXT',)):
    """Read every label of each explicitly bound type, including unused siblings."""
    items=frame.locator(CANVAS_ITEMS)
    if not items.count():raise Stop('Native condition canvas inventory is unavailable')
    result=[]
    for index in range(items.count()):
        item=items.nth(index)
        labels=_one(item.locator('[data-field-type]'),'Native condition canvas field type is ambiguous')
        if labels.get_attribute('data-field-type') not in field_types:continue
        if (labels.get_attribute('contenteditable')!='true'
                or labels.get_attribute('role')!='textbox'
                or labels.get_attribute('aria-label')!='Label'):
            raise Stop('Native custom condition label identity changed')
        label=labels.inner_text().strip()
        result.append((item,labels,label))
    if len({label for _,_,label in result})!=len(result):
        raise Stop('Native custom condition labels are duplicated; condition identity is ambiguous')
    return result


def preflight(frame,bindings,identity):
    """Read typed label/key bindings without editing any property.

    TEXT retains its complete legacy inventory contract. Once Number is bound,
    every Number sibling is inventoried as well; unbound families stay untouched."""
    _close_initial(frame)
    field_types={'TEXT'}|{field['field_type'] for field in bindings}
    def entries_now():return _texts(frame,field_types)
    entries=entries_now()
    if [label for _,_,label in entries]!=[field['label'] for field in bindings]:
        raise Stop('Native custom condition inventory differs from complete condition field_bindings')
    observed=[]
    for index,field in enumerate(bindings):
        identity()
        current=entries_now()
        if [label for _,_,label in current]!=[row['label'] for row in bindings]:
            raise Stop('Native custom condition canvas changed during condition preflight')
        item,label,_=current[index]
        if label.get_attribute('data-field-type')!=field['field_type']:
            raise Stop('Native condition field type differs from its binding')
        selector=('input.form-placeholder.form-control' if field['field_type']=='TEXT'
                  else 'input.form-control')
        control=_one(item.locator(selector),'Native custom condition canvas input changed')
        if control.get_attribute('name') not in (None,''):
            raise Stop('Local condition field unexpectedly has an API field identity')
        click(label)
        gear=item.locator('[aria-label="Open settings"]')
        gear.wait_for(state='visible',timeout=45000)
        _one(gear,'Native custom condition settings control changed')
        click(gear)
        frame.get_by_text('General Settings',exact=True).wait_for(state='visible',timeout=45000)
        query=_one(frame.locator('#fieldQueryKey input.n-input__input-el'),
                   'Native custom condition Query Key input changed')
        if not query.is_visible() or query.input_value()!=field['query_key']:
            raise Stop('Native custom condition Query Key differs from condition binding')
        observed.append(dict(field))
        _close_properties(frame)
    identity()
    if [label for _,_,label in entries_now()]!=[field['label'] for field in bindings]:
        raise Stop('Native custom condition canvas changed after condition preflight')
    return observed
