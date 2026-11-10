"""Captured native Address child properties and two-clause consent editing.

Uses the same native five-child Address layout captured for field placement.
Address edits existing child query keys and captured child properties. Consent uses its separately
captured two-clause panel. Neither fabricates custom-field definitions or
infers unseen choice/upload property controls.
The parent runner owns the tenant guard and intent-before-mutation journal.
"""
from copy import deepcopy
import hashlib
import json
import math
import re
import time
from urllib.parse import urlsplit

if __package__:
    from .field_placement import (
        CANVAS_ITEMS, _ADDRESS_QUERIES, _close_initial, _close_properties,
        _inventory, _query_controls, _query_key, _address_headers,
    )
    from .assessments import reopen_editor, read_editor_title
    from .skill6_playwright import Stop, click, fill, form_builder, wait_until
else:
    from field_placement import (
        CANVAS_ITEMS, _ADDRESS_QUERIES, _close_initial, _close_properties,
        _inventory, _query_controls, _query_key, _address_headers,
    )
    from assessments import reopen_editor, read_editor_title
    from skill6_playwright import Stop, click, fill, form_builder, wait_until


def _token(value):
    if (not isinstance(value, str) or not value or len(value) > 256
            or any(char.isspace() or ord(char) < 32 for char in value)):
        raise Stop('Address child Query Key must be a nonempty token without whitespace')
    return value


def validate(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'address_fields'}
            or step.get('action', 'native_address_fields') != 'native_address_fields'):
        raise Stop('Unsupported Address child configuration')
    fields = step.get('address_fields')
    if not isinstance(fields, list) or not fields:
        raise Stop('address_fields must be a nonempty list of existing Address children')
    seen = set()
    result = deepcopy(step)
    before = dict(_ADDRESS_QUERIES)
    after = dict(before)
    for field in result['address_fields']:
        if (not isinstance(field, dict)
                or set(field) - {'field', 'query_key', 'current_query_key', 'properties', 'expected_properties'}
                or not isinstance(field.get('field'),str) or field['field'] not in _ADDRESS_QUERIES
                or 'query_key' not in field or field['field'] in seen):
            raise Stop('Address child edits require unique captured field names and explicit Query Keys')
        label = field['field']
        seen.add(label)
        current = _token(field.get('current_query_key', _ADDRESS_QUERIES[label]))
        desired = _token(field['query_key'])
        before[label], after[label] = current, desired
        if ('properties' in field)!=('expected_properties' in field):
            raise Stop('Address property edits require matching expected_properties')
        if 'properties' in field:
            properties,expected=field['properties'],field['expected_properties']
            allowed={'label','placeholder','short_label','required','hidden','hidden_value'}
            if (not isinstance(properties,dict) or not properties or not isinstance(expected,dict)
                    or set(properties)-allowed or set(expected)!=set(properties)):
                raise Stop('Address properties need identical nonempty previous/desired captured property keys')
            for values in (properties,expected):
                for key,value in values.items():
                    if key in ('required','hidden'):
                        if type(value) is not bool:
                            raise Stop('Address Required/Hidden properties require real booleans')
                    elif key=='hidden_value' and value is None and values.get('hidden') is False:
                        pass  # Hidden value has no visible native control when Hidden is off.
                    elif (not isinstance(value,str) or len(value)>5000
                            or any(ord(c)<32 and c not in '\n\r\t' for c in value)
                            or (key=='label' and not value.strip())):
                        raise Stop('Address child text properties require explicit valid text')
                if values.get('required') is True and values.get('hidden') is True:
                    raise Stop('An Address child cannot be Required and Hidden')
                if 'hidden_value' in values and 'hidden' not in values:
                    raise Stop('Address hidden_value requires an explicit Hidden state')
                if values.get('hidden') is False and values.get('hidden_value') is not None:
                    raise Stop('An unhidden Address child cannot have an authored hidden_value')
            if (properties.get('hidden') is True and expected.get('hidden') is False
                    and ('hidden_value' not in properties or not isinstance(properties['hidden_value'],str))):
                raise Stop('Enabling Hidden requires explicit Address child hidden_value and previous absence')
    if len(set(before.values())) != len(before) or len(set(after.values())) != len(after):
        raise Stop('Address child Query Keys must remain unique')
    for label in seen:
        if any(after[label] == key for other, key in before.items() if other != label):
            raise Stop('Address child Query Key collides with another current child')
    return result


def configuration_hash(step):
    valid = validate(step)
    fields = [{'field':f['field'],
               'current_query_key':f.get('current_query_key', _ADDRESS_QUERIES[f['field']]),
               'query_key':f['query_key'],
               **({key:f[key] for key in ('properties','expected_properties')}
                  if 'properties' in f else {})} for f in valid['address_fields']]
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _open_address(frame):
    _close_initial(frame)
    click(frame.get_by_role('tab', name='Edit', exact=True))
    items = frame.locator(CANVAS_ITEMS)
    groups = items.filter(has=frame.locator('[data-field-type="group"]'))
    if groups.count() != 1:
        raise Stop('Exactly one existing native Address group is required')
    kind = groups.locator('[data-field-type]')
    if kind.count() != 1 or kind.get_attribute('data-field-type') != 'group':
        raise Stop('Address wrapper belongs to an unexpected native field type')
    controls = groups.locator('input')
    if controls.count() != 6:
        raise Stop('Native Address selectable input shape changed')
    click(controls.nth(1))
    gear = groups.locator('[aria-label="Open settings"]')
    if gear.count() != 1:
        raise Stop('Native Address settings control is missing or ambiguous')
    click(gear)
    frame.get_by_text('Address Fields', exact=True).wait_for(state='visible', timeout=45000)
    _address_headers(frame)
    for label in _ADDRESS_QUERIES:
        enabled = frame.get_by_role('checkbox', name=label, exact=True)
        if enabled.count() != 1 or not enabled.is_checked():
            raise Stop('Address child visibility differs from the captured complete group')


def _child_item(frame,label):
    headers = _address_headers(frame)
    header = headers.filter(has_text=re.compile(r'^\s*' + re.escape(label) + r'\s*$'))
    if header.count() != 1:
        raise Stop('Native Address child header is missing or ambiguous')
    item = header.locator('..').locator('..')
    controls = _query_controls(item)
    if len(controls) > 1:
        raise Stop('Native Address child Query Key is ambiguous')
    if not controls or not controls[0].is_visible():
        click(header)
    controls = _query_controls(item)
    if len(controls) != 1 or not controls[0].is_visible():
        raise Stop('Native Address child Query Key control did not open')
    return item


def _child(frame, label):
    item=_child_item(frame,label)
    controls=_query_controls(item)
    return controls[0], _token(_query_key(item))


_ADDRESS_TEXT_CONTROLS={'label':('#label input','Label'),
    'placeholder':('#fieldPlaceholder input','Placeholder'),
    'short_label':('#shortLabel input','Short Label')}
_ADDRESS_CHECKBOX_CONTROLS={'required':'#fieldRequired[role="checkbox"]',
                           'hidden':'#fieldCheckbox[role="checkbox"]'}


def _child_properties(frame,label):
    """Read only the scoped child controls observed in the native Address panel."""
    item=_child_item(frame,label)
    controls,state={},{}
    for key,(selector,row_label) in _ADDRESS_TEXT_CONTROLS.items():
        control=item.locator(selector)
        if control.count()!=1 or not control.is_visible():
            raise Stop('Native Address child text control is missing or ambiguous: '+key)
        row=control.evaluate("el => el.closest('.form-group')?.textContent || ''")
        suffix=r'(?:\s*Please Input)?' if key=='short_label' else ''
        if not isinstance(row,str) or not re.fullmatch(r'\s*'+re.escape(row_label)+suffix+r'\s*',row):
            raise Stop('Native Address child property row identity changed: '+key)
        controls[key],state[key]=control,control.input_value()
        if not isinstance(state[key],str):
            raise Stop('Native Address child text value is unavailable')
    for key,selector in _ADDRESS_CHECKBOX_CONTROLS.items():
        control=item.locator(selector)
        if control.count()!=1 or not control.is_visible():
            raise Stop('Native Address child checkbox is missing or ambiguous: '+key)
        value=control.get_attribute('aria-checked')
        if value not in ('true','false'):
            raise Stop('Native Address child checkbox state is unavailable')
        controls[key],state[key]=control,value=='true'
    if state['required'] and state['hidden']:
        raise Stop('Native Address child has conflicting Required/Hidden state')
    hidden_value=item.locator('#fieldHiddenvalue input')
    if state['hidden']:
        if hidden_value.count()!=1 or not hidden_value.is_visible():
            raise Stop('Native Address child Hidden value control is unavailable')
        row=hidden_value.evaluate("el => el.closest('.form-group')?.textContent || ''")
        if not isinstance(row,str) or not re.fullmatch(r'\s*Hidden value\s*(?:Please Input)?\s*',row):
            raise Stop('Native Address child Hidden value row identity changed')
        state['hidden_value']=hidden_value.input_value()
        controls['hidden_value']=hidden_value
    else:
        if hidden_value.count() and hidden_value.is_visible():
            raise Stop('Native Address child has a visible Hidden value while Hidden is off')
        state['hidden_value']=None
    return controls,state


def _write_child_properties(frame,label,before,desired):
    controls,current=_child_properties(frame,label)
    if current!=before:
        raise Stop('Native Address child properties changed after preflight')
    # Native Required/Hidden are mutually exclusive, including intermediates.
    def toggle(key,value):
        click(controls[key])
        wait_until(lambda:controls[key].get_attribute('aria-checked')==('true' if value else 'false'),
                   'Native Address child checkbox did not change: '+key)
    for key in ('required','hidden'):
        if current[key] and not desired[key]:
            toggle(key,False)
    for key in _ADDRESS_TEXT_CONTROLS:
        if before[key]!=desired[key]:
            fill(controls[key],desired[key])
    for key in ('required','hidden'):
        if not before[key] and desired[key]:
            toggle(key,True)
    if desired['hidden']:
        fresh_controls,fresh_state=_child_properties(frame,label)
        if fresh_state['hidden_value']!=desired['hidden_value']:
            fill(fresh_controls['hidden_value'],desired['hidden_value'])
    if _child_properties(frame,label)[1]!=desired:
        raise Stop('Native Address child properties or preserved values differ from the target')


def _snapshot(frame):
    return {label:_child(frame, label)[1] for label in _ADDRESS_QUERIES}


def configure(page, step):
    plan = validate(step)
    frame = form_builder(page)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    if title.count() != 1 or not read_editor_title(title).strip():
        raise Stop('Native form identity is missing or ambiguous')
    name, editor_url = read_editor_title(title), page.url
    inventory = _inventory(frame, allow_unknown_queries=True)
    _open_address(frame)
    before = _snapshot(frame)
    desired = dict(before)
    wanted_inventory = dict(inventory)
    property_plans={}
    for field in plan['address_fields']:
        label = field['field']
        old = field.get('current_query_key', _ADDRESS_QUERIES[label])
        new = field['query_key']
        if before[label] != old or inventory.get(old) != 'group':
            raise Stop('Address child differs from its inventoried current Query Key')
        if new != old and new in wanted_inventory:
            raise Stop('New Address child Query Key already belongs to another native field')
        desired[label] = new
        wanted_inventory[new] = wanted_inventory.pop(old)
        if 'properties' in field:
            _,observed=_child_properties(frame,label)
            if any(observed[key]!=value for key,value in field['expected_properties'].items()):
                raise Stop('Address child properties differ from their inventoried previous values')
            wanted={**observed,**field['properties']}
            if wanted['required'] and wanted['hidden']:
                raise Stop('Address property target conflicts with the preserved Required/Hidden state')
            if not wanted['hidden']:
                wanted['hidden_value']=None
            property_plans[label]=(observed,wanted)
    # All targets and collisions are known before the first fill.
    if _snapshot(frame) != before:
        raise Stop('Address child inventory changed after preflight')
    for label,(observed,_) in property_plans.items():
        if _child_properties(frame,label)[1]!=observed:
            raise Stop('Address child properties changed after the complete preflight')
    for field in plan['address_fields']:
        control, current = _child(frame, field['field'])
        if current != before[field['field']]:
            raise Stop('Address child changed immediately before editing')
        if current != field['query_key']:
            fill(control, field['query_key'])
        if control.input_value() != field['query_key']:
            raise Stop('Native Address child ignored the authored Query Key')
        if field['field'] in property_plans:
            _write_child_properties(frame,field['field'],*property_plans[field['field']])
    if _snapshot(frame) != desired:
        raise Stop('Address child Query Keys or protected sibling identities changed')
    for label,(_,wanted) in property_plans.items():
        if _child_properties(frame,label)[1]!=wanted:
            raise Stop('Another Address child edit changed a requested child property')
    _close_properties(frame)
    if _inventory(frame, allow_unknown_queries=True) != wanted_inventory:
        raise Stop('Native query inventory differs from the requested Address edit')
    _close_initial(frame)
    click(frame.get_by_role('button', name='Save', exact=True))
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).count() == 1
        and frame.get_by_role('button', name='Save', exact=True).is_enabled(),
        'Native form save did not finish')
    reopen_editor(page, 'form', name, editor_url)
    frame = form_builder(page)
    if _inventory(frame, allow_unknown_queries=True) != wanted_inventory:
        raise Stop('Saved Address query inventory did not persist')
    _open_address(frame)
    if _snapshot(frame) != desired:
        raise Stop('Address child Query Keys did not persist after independent reopen')
    for label,(_,wanted) in property_plans.items():
        if _child_properties(frame,label)[1]!=wanted:
            raise Stop('Address child properties did not persist after independent reopen')
    _close_properties(frame)
    _close_initial(frame)
    return {'status':'ADDRESS_FIELDS_SAVED_AND_REOPENED', 'editor_url':page.url,
        'fields':[{'field':field['field'], 'query_key':field['query_key']}
                  for field in plan['address_fields']],
        'configuration_sha256':configuration_hash(plan),
        'independent_readback':'VERIFIED', 'submission_verified':False}


def validate_consent(step):
    """Existing two-clause native T&C, using caller-authored plaintext only."""
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'consent'}
            or step.get('action', 'native_form_consent') != 'native_form_consent'):
        raise Stop('Unsupported native consent runner configuration')
    consent = step.get('consent')
    if (not isinstance(consent, dict)
            or set(consent) - {'expected_query_key', 'query_key', 'required', 'expected_required', 'clauses'}):
        raise Stop('Unsupported native consent option; adding/removing clauses requires separate capture')
    _token(consent.get('expected_query_key'))
    if 'query_key' in consent:
        _token(consent['query_key'])
    if 'required' in consent:
        if type(consent['required']) is not bool or type(consent.get('expected_required')) is not bool:
            raise Stop('Consent Required edits need explicit real desired and previous booleans')
    elif 'expected_required' in consent:
        raise Stop('expected_required without a Required edit would be ignored')
    clauses = consent.get('clauses', [])
    if not isinstance(clauses, list) or ('clauses' in consent and not clauses):
        raise Stop('Consent clauses must be a nonempty list when supplied')
    indexes = set()
    result = deepcopy(step)
    for clause in result['consent'].get('clauses', []):
        if (not isinstance(clause, dict)
                or set(clause) != {'index', 'text', 'expected_html_sha256'}
                or type(clause['index']) is not int or clause['index'] not in (1, 2)
                or clause['index'] in indexes):
            raise Stop('Consent edits require unique existing clause indexes1or2 and exact previous HTML hashes')
        indexes.add(clause['index'])
        if (not isinstance(clause['text'], str) or not clause['text'].strip()
                or len(clause['text']) > 20000
                or any(ord(char) < 32 and char not in '\r\n\t' for char in clause['text'])):
            raise Stop('Consent text must be explicit nonempty caller-approved plaintext')
        if (not isinstance(clause['expected_html_sha256'], str)
                or not re.fullmatch(r'[a-f0-9]{64}', clause['expected_html_sha256'])):
            raise Stop('Consent text edits require an inventoried previous HTML SHA256')
        clause['text'] = _plain(clause['text'])
    if not set(consent).intersection({'query_key', 'required', 'clauses'}):
        raise Stop('Native consent configuration needs at least one requested edit')
    return result


def _plain(value):
    return value.replace('\r\n', '\n').replace('\r', '\n').strip()


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def consent_configuration_hash(step):
    valid = validate_consent(step)
    return _digest(json.dumps(valid['consent'], sort_keys=True, separators=(',', ':')))


def _open_consent(frame):
    if __package__:
        from .assessments import FIELD_WRAPPER
    else:
        from assessments import FIELD_WRAPPER
    _close_initial(frame)
    click(frame.get_by_role('tab', name='Edit', exact=True))
    element = frame.locator('#tnc-element')
    if element.count() != 1:
        raise Stop('Native T&C element is absent or ambiguous')
    paragraphs = element.locator('.tnc')
    if paragraphs.count() != 2:
        raise Stop('This handler requires the captured existing two-clause native T&C element')
    for key in ('terms-and-conditions', 'terms-and-conditions-2'):
        if element.locator('input#' + key).count() != 1:
            raise Stop('Native T&C checkbox identity differs from the captured element')
    wrapper = element.locator(FIELD_WRAPPER)
    if wrapper.count() != 1:
        raise Stop('Native T&C does not belong to one direct canvas wrapper')
    click(paragraphs.nth(0))
    gear = wrapper.locator('[aria-label="Open settings"]')
    if gear.count() != 1:
        raise Stop('Native T&C settings control is missing or ambiguous')
    click(gear)
    panel = frame.locator('#general-settings')
    panel.wait_for(state='visible', timeout=45000)
    if (panel.count() != 1
            or panel.get_by_role('heading', name='T & C', exact=True, level=6).count() != 1):
        raise Stop('Native T&C settings panel identity changed')
    editors = panel.locator('.tiptap.ProseMirror[contenteditable="true"]')
    required = panel.get_by_role('checkbox', name='Required', exact=True)
    queries = _query_controls(panel)
    if editors.count() != 2 or required.count() != 1 or len(queries) != 1:
        raise Stop('Native T&C property control inventory changed')
    if any(not editors.nth(i).is_visible() for i in range(2)):
        raise Stop('Both captured native T&C clause editors must be visible')
    return editors, required, queries[0]


def _consent_snapshot(editors, required, query):
    return {'html':[editors.nth(i).inner_html() for i in range(2)],
            'text':[_plain(editors.nth(i).inner_text()) for i in range(2)],
            'required':required.is_checked(), 'query_key':_token(query.input_value())}


def inspect_consent(page):
    """Read caller preflight hashes without saving or exposing legal plaintext."""
    frame = form_builder(page)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    if title.count() != 1 or not read_editor_title(title).strip():
        raise Stop('Native form identity is missing or ambiguous')
    editors, required, query = _open_consent(frame)
    state = _consent_snapshot(editors, required, query)
    result = {'status':'CONSENT_INVENTORIED', 'editor_url':page.url,
        'expected_query_key':state['query_key'], 'expected_required':state['required'],
        'clauses':[{'index':i + 1, 'expected_html_sha256':_digest(html)}
                   for i, html in enumerate(state['html'])]}
    _close_properties(frame)
    _close_initial(frame)
    return result


def configure_consent(page, step):
    plan = validate_consent(step)
    consent = plan['consent']
    frame = form_builder(page)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    if title.count() != 1 or not read_editor_title(title).strip():
        raise Stop('Native form identity is missing or ambiguous')
    form_name, editor_url = read_editor_title(title), page.url
    query_inventory = None
    if consent.get('query_key', consent['expected_query_key']) != consent['expected_query_key']:
        query_inventory = _inventory(frame, allow_unknown_queries=True)
        if consent['query_key'] in query_inventory:
            raise Stop('Native consent Query Key would collide with an existing contact field')
    editors, required, query = _open_consent(frame)
    before = _consent_snapshot(editors, required, query)
    if before['query_key'] != consent['expected_query_key']:
        raise Stop('Native T&C query identity differs from the expected existing element')
    if 'required' in consent and before['required'] != consent['expected_required']:
        raise Stop('Native T&C Required value changed since inventory')
    for clause in consent.get('clauses', []):
        if _digest(before['html'][clause['index'] - 1]) != clause['expected_html_sha256']:
            raise Stop('Native T&C clause changed since the caller approved its previous HTML')
    # Every supplied value and old-clause hash is checked before the first edit.
    desired_html = list(before['html'])
    desired_text = list(before['text'])
    for clause in consent.get('clauses', []):
        index = clause['index'] - 1
        fill(editors.nth(index), clause['text'])
        if _plain(editors.nth(index).inner_text()) != clause['text']:
            raise Stop('Native consent editor ignored caller-authored text')
        desired_text[index] = clause['text']
        desired_html[index] = editors.nth(index).inner_html()
    desired_required = consent.get('required', before['required'])
    desired_query = consent.get('query_key', before['query_key'])
    if required.is_checked() != desired_required:
        required.set_checked(desired_required)
    if query.input_value() != desired_query:
        fill(query, desired_query)
    desired = {'html':desired_html, 'text':desired_text,
               'required':desired_required, 'query_key':desired_query}
    if _consent_snapshot(editors, required, query) != desired:
        raise Stop('Native consent authored values or preserved sibling HTML changed before Save')
    _close_properties(frame)
    _close_initial(frame)
    if query_inventory is not None and _inventory(frame, allow_unknown_queries=True) != query_inventory:
        raise Stop('Unrelated contact-field identities changed during native consent editing')
    click(frame.get_by_role('button', name='Save', exact=True))
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).count() == 1
        and frame.get_by_role('button', name='Save', exact=True).is_enabled(),
        'Native form save did not finish')
    reopen_editor(page, 'form', form_name, editor_url)
    frame = form_builder(page)
    if query_inventory is not None and _inventory(frame, allow_unknown_queries=True) != query_inventory:
        raise Stop('Unrelated contact-field identities changed after consent save')
    editors, required, query = _open_consent(frame)
    if _consent_snapshot(editors, required, query) != desired:
        raise Stop('Native consent did not persist after independent form-list reopen')
    _close_properties(frame)
    _close_initial(frame)
    return {'status':'CONSENT_SAVED_AND_REOPENED', 'editor_url':page.url,
        'configuration_sha256':consent_configuration_hash(plan),
        'independent_readback':'VERIFIED', 'submission_verified':False, 'behavior_verified':False}


def _object_record(value):
    """One existing API-owned native Radio field, including its authored options."""
    if not isinstance(value, dict) or set(value) != {'id', 'name', 'field_key', 'data_type', 'options'}:
        raise Stop('Object fields require exact API id/name/key/type/options inventory')
    if not isinstance(value['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', value['id']):
        raise Stop('Object field API identity is invalid')
    if (not isinstance(value['name'], str) or not value['name'].strip()
            or len(value['name']) > 500):
        raise Stop('Object field API name is missing')
    key = _token(value['field_key'])
    if not key.startswith('contact.') or len(key) <= len('contact.'):
        raise Stop('Native object fields require their exact contact-prefixed API fieldKey')
    # A data type enters this list only after its actual native widget capture.
    # Existing custom-field schemas/options remain owned by the API dependency rail.
    if value['data_type'] != 'RADIO':
        raise Stop('This object-field native widget still requires its own capture')
    options = value['options']
    if (not isinstance(options, list) or not options
            or any(not isinstance(option, str) or not option.strip() for option in options)
            or len(set(options)) != len(options)):
        raise Stop('Native Radio object fields require exact unique API option strings')
    return deepcopy(value)


def validate_object_fields(step, *, kind='form', require_fresh=False):
    """Validate dependency identity; only a new native execution requires age.

    Intake, compilation and completed replay must remain structurally valid as
    the original GET ages. configure_object_fields separately opts into the
    fresh same-location read required before touching native controls.
    """
    if type(require_fresh) is not bool:
        raise Stop('Object-field freshness requirement must be a real boolean')
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'payload'}
            or step.get('action', 'native_object_fields') != 'native_object_fields'
            or kind not in ('form', 'survey')):
        raise Stop('Unsupported object-field placement configuration')
    payload = step.get('payload')
    if (not isinstance(payload, dict)
            or set(payload) != {'location_id', 'location_name', 'start_url', 'object_fields', 'field_dependencies'}):
        raise Stop('Object-field placement needs its exact native editor and API dependency inventory')
    loc = payload['location_id']
    if not isinstance(loc, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', loc):
        raise Stop('Object-field placement requires a location identity')
    if not isinstance(payload['location_name'], str) or not payload['location_name'].strip():
        raise Stop('Object-field placement requires a visible account name')
    if not isinstance(payload['start_url'], str):
        raise Stop('Object-field placement requires its exact editor URL')
    parsed = urlsplit(payload['start_url'])
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment
            or not re.fullmatch('/v2/location/' + re.escape(loc) + '/' + kind
                                + r'-builder-v2/[A-Za-z0-9_-]+/?', parsed.path)):
        raise Stop('Object-field placement URL belongs to a different editor or location')
    fields = payload['object_fields']
    if not isinstance(fields, list) or not fields:
        raise Stop('object_fields must be a nonempty API-inventoried field list')
    requested = [_object_record(field) for field in fields]
    for key in ('id', 'field_key'):
        if len({field[key] for field in requested}) != len(requested):
            raise Stop('Object-field IDs and keys must be unique')
    dependency = payload['field_dependencies']
    if (not isinstance(dependency, dict)
            or set(dependency) != {'status', 'provider', 'location_id', 'observed_at', 'operation', 'http_status', 'fields'}
            or dependency['status'] != 'VERIFIED' or dependency['location_id'] != loc
            or dependency['provider'] not in ('skill44', 'public_api', 'official_mcp')
            or dependency['operation'] not in ('custom_fields.get', 'custom_fields.list')
            or type(dependency['http_status']) is not int or dependency['http_status'] != 200
            or type(dependency['observed_at']) not in (int, float)
            or not math.isfinite(dependency['observed_at'])
            or dependency['observed_at'] < 0
            or (require_fresh and not 0 <= time.time() - dependency['observed_at'] <= 3600)
            or not isinstance(dependency['fields'], list)):
        raise Stop('Object fields require fresh verified same-location API dependency read-back')
    # A real location list includes fields that are not being placed in this
    # job. They need unambiguous API identities, not the requested widget's
    # native Radio shape. In particular, unrelated TEXT/DATE fields must not
    # prevent placing an independently captured RADIO widget.
    by_id, keys = {}, set()
    for field in dependency['fields']:
        if (not isinstance(field, dict)
                or not isinstance(field.get('id'), str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', field['id'])):
            raise Stop('API field dependency identity is invalid')
        key = _token(field.get('field_key'))
        if not key.startswith('contact.') or len(key) <= len('contact.'):
            raise Stop('API field dependency key must identify a contact field')
        if field['id'] in by_id or key in keys:
            raise Stop('API field dependency identity or key is duplicated')
        by_id[field['id']] = field
        keys.add(key)
    if any(field['id'] not in by_id or _object_record(by_id[field['id']]) != field
           for field in requested):
        raise Stop('Requested object fields differ from their API-confirmed definitions')
    return deepcopy(step)


def object_fields_configuration_hash(step, *, kind='form'):
    # Configuration hashes remain usable on replay after a capability ages out.
    # Freshness is an execution preflight, not permission to forget an old write.
    valid=validate_object_fields(step,kind=kind,require_fresh=False)
    payload=valid['payload']
    fields = [_object_record(field) for field in payload.get('object_fields', [])]
    if not fields:
        raise Stop('Object-field receipt has no authored fields')
    return _digest(json.dumps({'kind':kind,
        'location_id':payload.get('location_id'), 'start_url':payload.get('start_url'),
        'object_fields':fields}, sort_keys=True, separators=(',', ':')))


def _close_object_drawer(frame, kind):
    dialog = frame.get_by_role('dialog')
    if not dialog.count():
        return
    label = 'Form Element' if kind == 'form' else 'Survey Element'
    if dialog.count() != 1 or dialog.get_by_text(label, exact=True).count() != 1:
        raise Stop('Unexpected native object-field drawer requires reconciliation')
    close = dialog.get_by_role('button', name='Close', exact=True)
    if close.count() != 1 or not close.is_visible():
        raise Stop('Native object-field drawer close control changed')
    click(close)


def _object_dialog(frame, kind):
    _close_object_drawer(frame, kind)
    click(frame.get_by_role('button', name='Add Form Element' if kind == 'form' else 'Add Survey Element', exact=True))
    dialog = frame.get_by_role('dialog')
    dialog.wait_for(state='visible', timeout=45000)
    if dialog.count() != 1 or dialog.get_by_text('Form Element' if kind == 'form' else 'Survey Element', exact=True).count() != 1:
        raise Stop('Native object-field drawer is missing or ambiguous')
    click(dialog.get_by_text('Add Object Fields', exact=True))
    search = dialog.get_by_role('textbox', name='Search by name', exact=True)
    search.wait_for(state='visible', timeout=45000)
    if search.count() != 1:
        raise Stop('Native object-field search control changed')
    return dialog, search


def _object_row(dialog, search, field):
    fill(search, field['name'])
    row = dialog.locator('.cf-row-wrap[data-field-id="' + field['id'] + '"]')
    row.wait_for(state='visible', timeout=45000)
    if row.count() != 1:
        raise Stop('Exact API-owned native object field is absent or ambiguous')
    tile = row.locator('.custom-item')
    label = row.locator('.custom-item-label span')
    key = row.locator('.custom-item-key')
    checkbox = row.locator('#custom-field-check-' + field['id'])
    if (tile.count() != 1 or label.count() != 1 or key.count() != 1 or checkbox.count() != 1
            or label.get_attribute('title') != field['name']
            or key.get_attribute('title') != field['field_key']
            or (key.inner_text() or '').strip() != field['field_key']
            or tile.get_attribute('aria-disabled') not in ('true', 'false')
            or checkbox.get_attribute('aria-checked') not in ('true', 'false')):
        raise Stop('Native object-field row differs from its exact API id/name/key')
    return row, tile, checkbox


def _field_wrappers(scope):
    # Native Forms capture proves wrappers are direct canvas children. Survey
    # owner slides use a separately captured descendant layout; do not change
    # that layout by inferring it from the form canvas.
    direct=scope.get_attribute('id')=='form-builder-container'
    return scope.locator(':scope > .form-field-wrapper' if direct else '.form-field-wrapper')


def _canvas_identity(scope):
    # Name/type identities survive native reopen; generated framework IDs do not.
    return _field_wrappers(scope).evaluate_all('''items => items.map(item => {
        const labels = item.querySelectorAll('[data-field-type]');
        const types = Array.from(labels).map(e => e.getAttribute('data-field-type'));
        return {types,
            names:Array.from(item.querySelectorAll('input,textarea,select')).filter(e =>
                !(types.length === 1 && types[0] === 'SINGLE_OPTIONS'
                    && e.matches('input.dropdown-input.form-placeholder')
                    && !e.hasAttribute('id') && !e.hasAttribute('name'))).map(e =>
                [e.tagName, e.getAttribute('type'), e.getAttribute('name')])};
    })''')


def _object_wrapper(frame, scope, field):
    inputs = frame.locator('input[name="' + field['id'] + '"]')
    scoped = scope.locator('input[name="' + field['id'] + '"]')
    if scoped.count() != len(field['options']) or inputs.count() != scoped.count():
        raise Stop('Native object-field inputs are missing, duplicated or outside the requested canvas')
    item = _field_wrappers(scope).filter(has=inputs)
    if item.count() != 1:
        raise Stop('Native API field does not belong to one requested canvas wrapper')
    label = item.locator('[data-field-type="RADIO"]')
    if label.count() != 1 or item.locator('[data-field-type]').count() != 1:
        raise Stop('Native object-field widget differs from its captured Radio type')
    if (any(scoped.nth(i).get_attribute('type') != 'radio' for i in range(scoped.count()))
            or [scoped.nth(i).get_attribute('value') for i in range(scoped.count())] != field['options']):
        raise Stop('Native Radio options differ from their API-owned definition')
    return item, label


def _read_object_binding(frame, scope, field):
    item, label = _object_wrapper(frame, scope, field)
    click(label)
    gear = item.locator('[aria-label="Open settings"]')
    if gear.count() != 1:
        raise Stop('Native object-field settings control changed')
    click(gear)
    frame.get_by_text('General Settings', exact=True).wait_for(state='visible', timeout=45000)
    click(frame.get_by_text('General Settings', exact=True))
    # Exact opaque input[name=API_ID], native type and ordered choices were
    # proved by _object_wrapper. Query Key is separate form URL-prefill metadata
    # and legacy UI values need not equal the API fieldKey suffix.
    query=_query_key(frame)
    _close_properties(frame)
    return query


def configure_object_fields(page, step, *, kind='form', frame=None, canvas_scope=None, reopen=None):
    """Place API-precreated Radio fields; survey wrapper supplies an exact slide.

    A survey caller must select and bind its owner slide before calling this,
    and supply an independent reopen callback returning fresh (frame, scope).
    No custom-field schema or global choice value is created/edited here.
    """
    plan = validate_object_fields(step, kind=kind, require_fresh=True)
    payload = plan['payload']
    if page.url != payload['start_url']:
        raise Stop('Object-field placement page differs from its requested editor')
    if kind == 'survey' and (frame is None or canvas_scope is None or not callable(reopen)):
        raise Stop('Survey object fields require an exact selected owner slide and independent reader')
    if frame is None:
        frame = form_builder(page)
    if canvas_scope is None:
        canvas_scope = frame.locator('#form-builder-container')
    if canvas_scope.count() != 1:
        raise Stop('Object-field owner canvas is absent or ambiguous')
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    if title.count() != 1 or not read_editor_title(title).strip():
        raise Stop('Native editor identity is missing or ambiguous')
    name, editor_url = read_editor_title(title), page.url
    fields = payload['object_fields']
    before = _canvas_identity(canvas_scope)
    dialog, search = _object_dialog(frame, kind)
    selected_counter = dialog.get_by_text(re.compile(r'^\s*\d+ selected\s*$'))
    if selected_counter.count():
        raise Stop('Native object-field drawer already has an unrelated selection')
    pending, existing = [], []
    for field in fields:
        _, tile, checkbox = _object_row(dialog, search, field)
        disabled = tile.get_attribute('aria-disabled') == 'true'
        if not disabled and checkbox.get_attribute('aria-checked') != 'false':
            raise Stop('Native object-field drawer already contains an unrelated selection')
        if disabled:
            _object_wrapper(frame, canvas_scope, field)
            existing.append(field)
        else:
            if frame.locator('input[name="' + field['id'] + '"]').count():
                raise Stop('Object field exists on another canvas or native placement state conflicts')
            pending.append(field)
    # Capture each existing API-bound widget's actual Query Key before any
    # different field is inserted, then preserve that observed UI metadata.
    # Close the drawer before opening a field property panel, then reopen the
    # same captured picker when there is actual insertion work left to do.
    native_queries={}
    if existing:
        fill(search, '')
        _close_object_drawer(frame, kind)
        for field in existing:
            native_queries[field['id']]=_read_object_binding(frame, canvas_scope, field)
        if _canvas_identity(canvas_scope) != before:
            raise Stop('Native object-field identities changed during binding preflight')
        if pending:
            dialog, search = _object_dialog(frame, kind)
            selected_counter = dialog.get_by_text(re.compile(r'^\s*\d+ selected\s*$'))
            if selected_counter.count():
                raise Stop('Native object-field drawer selection changed after binding preflight')
    # Read every API-bound target before selecting any field for insertion.
    # The current native Add 1 field control was captured directly. Select and
    # add each different field once; do not guess plural control labels.
    for field in pending:
        _, tile, checkbox = _object_row(dialog, search, field)
        if tile.get_attribute('aria-disabled') != 'false' or checkbox.get_attribute('aria-checked') != 'false':
            raise Stop('Native object-field availability changed after preflight')
        click(checkbox)
        wait_until(lambda: checkbox.get_attribute('aria-checked') == 'true', 'Native field selection did not stick')
        selected = dialog.locator('.cf-row-wrap').filter(
            has=dialog.locator('.custom-item[aria-disabled="false"]')).filter(
            has=dialog.locator('[role="checkbox"][aria-checked="true"]'))
        if (selected.count() != 1 or selected.get_attribute('data-field-id') != field['id']
                or dialog.get_by_text('1 selected', exact=True).count() != 1):
            raise Stop('Native object-field selection includes unexpected fields')
        add = dialog.get_by_role('button', name='Add 1 field', exact=True)
        if add.count() != 1 or not add.is_enabled():
            raise Stop('Native selected-field Add control changed')
        click(add)  # Exactly one insertion of this identity; never a blind retry.
        wait_until(lambda: canvas_scope.locator('input[name="' + field['id'] + '"]').count()
            == len(field['options']) and tile.get_attribute('aria-disabled') == 'true'
            and dialog.get_by_role('button', name='Add', exact=True).count() == 1,
            'Native object field did not appear with its source selection cleared')
    if not existing or pending:
        fill(search, '')
        _close_object_drawer(frame, kind)
    for field in fields:
        query=_read_object_binding(frame, canvas_scope, field)
        if field['id'] in native_queries and native_queries[field['id']]!=query:
            raise Stop('Existing native object-field Query Key changed during placement')
        native_queries[field['id']]=query
    after = _canvas_identity(canvas_scope)
    new_ids = {field['id'] for field in pending}
    preserved = [row for row in after if not any(name[2] in new_ids for name in row['names'])]
    if preserved != before or len(after) != len(before) + len(pending):
        raise Stop('Object-field placement changed unrelated canvas identities')
    if pending:
        save = frame.get_by_role('button', name='Save', exact=True)
        click(save)
        wait_until(lambda: save.count() == 1 and save.is_enabled(), 'Native object-field save did not finish')
    if callable(reopen):
        frame, canvas_scope = reopen()
    else:
        reopen_editor(page, kind, name, editor_url)
        frame = form_builder(page)
        canvas_scope = frame.locator('#form-builder-container')
    if page.url != editor_url or canvas_scope.count() != 1:
        raise Stop('Native object-field independent reopen changed editor/canvas identity')
    _close_object_drawer(frame, kind)
    if _canvas_identity(canvas_scope) != after:
        raise Stop('Native object-field canvas identities did not persist')
    for field in fields:
        if _read_object_binding(frame, canvas_scope, field)!=native_queries[field['id']]:
            raise Stop('Native object-field Query Key did not persist after independent reopen')
    return {'status':'OBJECT_FIELDS_SAVED_AND_REOPENED', 'editor_url':page.url,
        'fields':[{'id':field['id'], 'field_key':field['field_key'], 'data_type':field['data_type'],
                   'placement':'added' if field['id'] in new_ids else 'reused'} for field in fields],
        'configuration_sha256':object_fields_configuration_hash(plan, kind=kind),
        'independent_readback':'VERIFIED', 'submission_verified':False}
