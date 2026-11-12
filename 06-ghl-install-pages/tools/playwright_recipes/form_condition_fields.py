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


OPTION_TYPES=frozenset(('SINGLE_OPTIONS','MULTIPLE_OPTIONS','CHECKBOX','RADIO'))
UNIQUE_TYPES=frozenset(('MULTIPLE_OPTIONS','FILE_UPLOAD','SIGNATURE','TEXTBOX_LIST'))
QUERYLESS_TYPES=frozenset(('RATING',))
PROFILE_TYPES=frozenset(('TEXT','LARGE_TEXT','NUMERICAL','MONETORY','SCORE','DATE_TIME','DATE','TIME','URL','TEXTBOX_LIST','FILE_UPLOAD','SIGNATURE','RATING'))|OPTION_TYPES


def validate(value,*,reserved=()):
    if not isinstance(value,list) or not 1<=len(value)<=100:
        raise Stop('Condition field_bindings requires the complete nonempty custom field inventory')
    labels=set();keys=set()
    builtin_keys={key for field in CAPTURED_FIELDS.values() for key in field['query_keys']}
    for field in value:
        kind=field.get('field_type') if isinstance(field,dict) else None
        key=None if kind in QUERYLESS_TYPES else 'unique_key' if kind in UNIQUE_TYPES else 'query_key'
        if (not isinstance(field,dict) or set(field)!=({'label','field_type'}|({key} if key else set()))
                or not isinstance(field['field_type'],str)
                or field['field_type'] not in PROFILE_TYPES
                or not isinstance(field['label'],str) or not field['label'].strip()
                or field['label']!=field['label'].strip() or len(field['label'])>256
                or any(ord(c)<32 for c in field['label'])
                or key is not None and (not isinstance(field[key],str)
                or not re.fullmatch(r'[A-Za-z0-9_.&-]{1,256}' if field['field_type']=='DATE_TIME' else r'[A-Za-z0-9_.-]{1,256}',field[key])
                or key=='unique_key' and not re.fullmatch(r'contact\.[A-Za-z0-9_.-]+',field[key]))):
            raise Stop('Condition bindings require exact captured field labels and their native Query Key or canonical Unique Key')
        if (field['label'] in labels or field['label'] in reserved
                or key is not None and (field[key] in keys or field[key] in builtin_keys)):
            raise Stop('Condition field labels and native keys must be unique and not shadow built-ins')
        labels.add(field['label'])
        if key is not None:keys.add(field[key])
    return deepcopy(value)


def _one(node,reason):
    if node.count()!=1:raise Stop(reason)
    return node


def _texts(frame,field_types=('TEXT',),*,items_selector=CANVAS_ITEMS):
    """Read every label of each explicitly bound type, including unused siblings."""
    items=frame.locator(items_selector)
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


def preflight(frame,bindings,identity,*,items_selector=CANVAS_ITEMS):
    """Read typed label/key bindings without editing any property.

    TEXT retains its complete legacy inventory contract. Once Number is bound,
    every Number sibling is inventoried as well; unbound families stay untouched."""
    _close_initial(frame)
    field_types={'TEXT'}|{field['field_type'] for field in bindings}
    def entries_now():return _texts(frame,field_types,items_selector=items_selector)
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
        if field['field_type'] in ('SINGLE_OPTIONS','MULTIPLE_OPTIONS'):
            click(label) # Dropdown preview inputs appear only after selecting this typed widget.
            control=_one(item.locator('input.dropdown-input'),'Native choice condition preview input changed')
            if control.get_attribute('name') not in (None,''):
                raise Stop('Native dropdown preview acquired an unexpected API name')
        elif field['field_type'] in ('CHECKBOX','RADIO'):
            kind='checkbox' if field['field_type']=='CHECKBOX' else 'radio'
            controls=item.locator('input[type="'+kind+'"]')
            if not 1<=controls.count()<=101:
                raise Stop('Native condition choice input inventory changed')
            if kind=='checkbox' and any(controls.nth(i).is_enabled() for i in range(controls.count())):
                raise Stop('Native Checkbox condition preview unexpectedly became editable')
            if kind=='radio':
                names=[controls.nth(i).get_attribute('name') for i in range(controls.count())]
                if any(not isinstance(name,str) or not name for name in names) or len(set(names))!=1:
                    raise Stop('Native Radio condition no longer belongs to one existing API field')
            click(label)
        elif field['field_type'] in ('FILE_UPLOAD','SIGNATURE','TEXTBOX_LIST','RATING','LARGE_TEXT'):
            selectors={'FILE_UPLOAD':'.form-builder--item > .flex.flex-col > svg',
                       'SIGNATURE':'.signature-button','TEXTBOX_LIST':'input.form-control',
                       'RATING':'input.rating-input','LARGE_TEXT':'textarea'}
            controls=item.locator(selectors[field['field_type']])
            count=controls.count()
            if not (count==2 if field['field_type']=='RATING' else 1<=count<=101 if field['field_type']=='TEXTBOX_LIST' else count==1):
                raise Stop('Native custom condition widget preview changed')
            click(label)
        elif field['field_type'] in ('DATE_TIME','DATE'):
            controls=item.locator('.date-time-preview-row input')
            expected=2 if field['field_type']=='DATE_TIME' else 1
            if controls.count()!=expected or any(controls.nth(i).get_attribute('name') not in (None,'') for i in range(expected)):
                raise Stop('Native Date & time condition preview changed')
            click(label)
        else:
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
        if field['field_type']=='RATING':
            frame.locator('#rating-general-settings').wait_for(state='visible',timeout=45000)
        else:
            frame.get_by_text('General Settings',exact=True).wait_for(state='visible',timeout=45000)
        if field['field_type'] in UNIQUE_TYPES:
            if __package__:
                from .form_widget_families import _advanced,_read_input
            else:
                from form_widget_families import _advanced,_read_input
            _advanced(frame)
            query=_one(frame.locator('#uniqueKey input'),'Native Multi Dropdown Unique Key changed')
            if not query.is_visible() or _read_input(query,'unique_key')!=field['unique_key']:
                raise Stop('Native Multi Dropdown Unique Key differs from condition binding')
        elif field['field_type'] not in QUERYLESS_TYPES:
            query=_one(frame.locator('#fieldQueryKey input.n-input__input-el'),
                       'Native custom condition Query Key input changed')
            if not query.is_visible():
                click(_one(frame.get_by_text('General Settings',exact=True),'Native condition General Settings owner changed'))
                query.wait_for(state='visible',timeout=45000)
            if not query.is_visible() or query.input_value()!=field['query_key']:
                raise Stop('Native custom condition Query Key differs from condition binding')
        observed.append(dict(field))
        _close_properties(frame)
    identity()
    if [label for _,_,label in entries_now()]!=[field['label'] for field in bindings]:
        raise Stop('Native custom condition canvas changed after condition preflight')
    return observed
