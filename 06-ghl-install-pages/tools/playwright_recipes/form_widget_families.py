"""Owned native form widgets with one captured family registry.

Creation and editing share identity, sibling preservation, save/reopen and fresh
replay verification. Profiles below are populated only from native captures;
the parent editor runner journals intent before the first native mutation.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

from playwright_recipes.skill6_playwright import Stop, assert_tenant, click, fill, form_builder, wait_until
from playwright_recipes.assessments import read_editor_title, reopen_editor
from playwright_recipes.field_placement import _close_initial, _close_properties, CANVAS_ITEMS, SUBMIT_DROP
from playwright_recipes import form_single_dropdown_native as single_dropdown
from playwright_recipes import form_multi_dropdown_native as multi_dropdown

ACTION = 'native_form_widget_fields'
COMMON = ('location_id', 'location_name', 'start_url')
BASE_PROPERTIES = {'label', 'query_key', 'required', 'hidden'}
TEXT_CONTROLS = {'label':'#label input', 'placeholder':'#fieldPlaceholder input',
                 'short_label':'#shortLabel input', 'query_key':'#fieldQueryKey input',
                 'width':'#fieldWidthKey input'}
PROFILES = {
    'single_dropdown':single_dropdown.PROFILE,
    'multi_dropdown':multi_dropdown.PROFILE,
    'url': {'type':'URL', 'tile':'URL', 'suffix':4, 'key_prefix':'url_',
        'properties':{**TEXT_CONTROLS,'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'}, 'input':'input.form-control',
        'extra':('domain_mode','domains'),
        'defaults':{'placeholder':'Enter a URL','short_label':'','width':100,'required':False,
                    'hidden':False,'domain_mode':'allow_all','domains':[]}},
    'number': {'type':'NUMERICAL', 'tile':'Number', 'suffix':5, 'key_prefix':'number_',
               'properties':{**TEXT_CONTROLS,'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'}, 'input':'input.form-control',
               'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'},
               'defaults':{'placeholder':'Enter a number', 'short_label':'', 'width':100,
                           'required':False, 'hidden':False}},
    'file_upload': {'type':'FILE_UPLOAD', 'tile':'File Upload', 'suffix':5,
        'key_prefix':'file_upload_', 'key_property':'unique_key',
        'properties':{'label':'#label input','placeholder':'#fieldPlaceholder input',
            'short_label':'#shortLabel input','custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired'}, 'input':'.form-builder--item > .flex.flex-col > svg',
        'extra':('file_access','file_types','multiple_files','max_files'),
        'defaults':{'placeholder':'Click to upload','short_label':'','required':False,
                    'file_access':'public','file_types':['all'],'multiple_files':False,'max_files':None}},
    'signature': {'type':'SIGNATURE', 'tile':'Signature', 'suffix':4,
        'key_prefix':'signature_', 'key_property':'unique_key',
        'properties':{'label':'#label input','placeholder':'#fieldPlaceholder input',
            'short_label':'#shortLabel input','width':'#fieldWidthKey input',
            'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired'}, 'input':'.signature-button',
        'defaults':{'placeholder':'Sign here','short_label':'','width':100,'required':False}},
    'checkbox': {'type':'CHECKBOX','tile':'Checkbox','suffix':5,'key_prefix':'checkbox_',
        'properties':{**TEXT_CONTROLS,'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'},
        'input':'input[type="checkbox"]','extra':('options','style','calculations','columns','other'),
        'defaults':{'placeholder':'','short_label':'','width':100,'required':False,'hidden':False,
            'options':[{'label':'Option '+str(i),'value':None} for i in (1,2,3)],
            'style':'standard','calculations':False,'columns':None,'other':None}},
}
FILE_TYPES = ('all','pdf','doc','png','gif','jpg','xls')


def _one(node, message):
    if node.count() != 1 or not node.is_visible():
        raise Stop(message)
    return node


def _text(value, key, *, token=False):
    if (not isinstance(value, str) or len(value) > 5000
            or any(ord(c) < 32 and c not in '\n\r\t' for c in value)
            or key in ('label', 'query_key', 'custom_field_name') and not value.strip()
            or token and not re.fullmatch(r'[A-Za-z0-9_.-]{1,256}', value)):
        raise Stop('Form widget requires explicit captured ' + key)
    return value


def _key(kind):
    return PROFILES[kind].get('key_property','query_key')


def _properties(kind, value, *, profile=None):
    if not isinstance(kind,str) or kind not in PROFILES:
        raise Stop('Uncaptured form widget family')
    profile = PROFILES[kind] if profile is None else profile
    keys = set(profile['properties']) | set(profile['flags']) | set(profile.get('extra', ()))
    if not isinstance(value, dict) or set(value) != keys | ({'hidden_value'} if value.get('hidden') else set()):
        raise Stop('Form widget properties must include the full captured family inventory')
    for key in profile['properties']:
        if key == 'width':
            if type(value[key]) is not int or not 1 <= value[key] <= 100:
                raise Stop('Form widget Width must be a whole percentage from 1 through 100')
        else:
            _text(value[key], key, token=key in ('query_key','unique_key'))
            if key=='unique_key' and (not value[key].startswith('contact.') or value[key]=='contact.'):
                raise Stop('Native custom-field Unique Key must be the canonical contact.* identity')
    if (any(type(value[key]) is not bool for key in profile['flags'])
            or value.get('required') and value.get('hidden')):
        raise Stop('Form widget Required and Hidden must be exclusive Boolean values')
    if value.get('hidden'):
        _text(value['hidden_value'], 'hidden_value')
    if kind=='url':
        if value['hidden']:
            raise Stop('URL Hidden-value controls have not been captured')
        _url_properties(value)
    if kind in ('single_dropdown','multi_dropdown'):single_dropdown.validate_properties(value)
    if kind == 'file_upload':
        types = value['file_types']
        if (value['file_access'] not in ('public','private') or type(value['multiple_files']) is not bool
                or not isinstance(types,list) or not types or any(x not in FILE_TYPES for x in types)
                or len(types)!=len(set(types)) or 'all' in types and types!=['all']
                or types!=[x for x in FILE_TYPES if x in types]):
            raise Stop('File Upload requires exact canonical access, file types and multiple-file choices')
        maximum=value['max_files']
        if (maximum is not None and (type(maximum) is not int or not 1<=maximum<=1000)
                or not value['multiple_files'] and maximum is not None):
            raise Stop('File Upload limits require multiple files and an explicit positive count or unlimited absence')
    if kind=='checkbox':
        options=value['options'];columns=value['columns']
        if (value['style'] not in ('standard','bubble') or type(value['calculations']) is not bool
                or columns is not None and (type(columns) is not int or not 1<=columns<=100)
                or not isinstance(options,list) or not 1<=len(options)<=100):
            raise Stop('Checkbox options require complete style/calculation/column choices')
        labels=[]
        for option in options:
            if not isinstance(option,dict) or set(option)!={'label','value'}:
                raise Stop('Checkbox requires every exact label and explicit calculation value/absence')
            _text(option['label'],'label');labels.append(option['label'])
            if value['calculations']:
                if not isinstance(option['value'],str) or option['value'] and not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?',option['value']):
                    raise Stop('Checkbox calculation values must be canonical finite decimal text')
            elif option['value'] is not None:
                raise Stop('Checkbox calculation values are absent when calculations are off')
        if len(labels)!=len(set(labels)):raise Stop('Checkbox option labels must be unique')
        other=value['other']
        if other is not None:
            if not isinstance(other,dict) or set(other)!={'label','placeholder'} or other['label']!='Other':
                raise Stop('Checkbox Other label is the captured readonly literal Other')
            _text(other['placeholder'],'placeholder')
            if 'Other' in labels:raise Stop('Checkbox Other must not duplicate a regular option label')
    return deepcopy(value)


def validate(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'payload'}
            or step.get('action', ACTION) != ACTION):
        raise Stop('Unsupported form widget runner metadata')
    plan = step.get('payload')
    if not isinstance(plan, dict) or set(plan) != set(COMMON) | {'expected_form_name', 'expected_fields', 'fields'}:
        raise Stop('Form widgets require exact editor and complete expected native family inventory')
    for key in (*COMMON, 'expected_form_name'):
        _text(plan[key], 'label')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', plan['location_id']):
        raise Stop('Form widget location identity is invalid')
    try:
        url = urlsplit(plan['start_url']); port = url.port
    except ValueError:
        raise Stop('Form widget editor URL is malformed') from None
    if (url.scheme != 'https' or not url.hostname or url.username is not None or url.password is not None
            or port not in (None, 443) or url.query or url.fragment
            or not re.fullmatch('/v2/location/' + re.escape(plan['location_id']) + r'/form-builder-v2/[A-Za-z0-9_-]+', url.path)):
        raise Stop('Form widgets must bind an exact same-location native form editor')
    before = plan['expected_fields']; changes = plan['fields']
    if not isinstance(before, list) or len(before) > 100 or not isinstance(changes, list) or not 1 <= len(changes) <= 100:
        raise Stop('Form widget inventories must be bounded explicit lists')
    indices = set(); queries = set()
    for field in before:
        if (not isinstance(field, dict) or set(field) != {'kind', 'index', 'properties'}
                or type(field['index']) is not int or field['index'] < 1 or field['index'] in indices):
            raise Stop('Existing form widgets require unique exact canvas positions')
        properties = _properties(field['kind'], field['properties'])
        if properties[_key(field['kind'])] in queries:
            raise Stop('Existing form widget Query Keys are duplicated')
        indices.add(field['index']); queries.add(properties[_key(field['kind'])])
    targets = set(); desired_keys = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'kind', 'index', 'desired'}:
            raise Stop('Each form widget write requires family, existing position or explicit new position, and complete properties')
        desired = _properties(change['kind'], change['desired'])
        identity_key = _key(change['kind'])
        index = change['index']
        if index is not None:
            if type(index) is not int or index in targets:
                raise Stop('Existing form widget edits require unique canvas positions')
            previous = [item for item in before if item['index'] == index]
            if len(previous) != 1 or previous[0]['kind'] != change['kind']:
                raise Stop('Form widget edit does not match its complete previous family inventory')
            if (identity_key=='unique_key' and desired[identity_key] != previous[0]['properties'][identity_key]
                    or desired[identity_key] != previous[0]['properties'][identity_key] and desired[identity_key] in queries):
                raise Stop('Existing widget identity is immutable or collides with another native field')
            for immutable in ('file_access','custom_field_name','unique_key'):
                if immutable in desired and desired[immutable] != previous[0]['properties'][immutable]:
                    raise Stop('Existing native custom-field access/name is immutable in this form job')
            targets.add(index)
        elif desired[identity_key] in queries:
            raise Stop('New form widget Query Key collides with a current native widget')
        if desired[identity_key] in desired_keys:
            raise Stop('Requested form widget Query Keys must be unique')
        desired_keys.add(desired[identity_key])
    return deepcopy(plan)


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _frame(page, plan):
    if page.url != plan['start_url']:
        raise Stop('Form widget editor URL changed')
    assert_tenant(page, plan)
    frame = form_builder(page)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    if title.count() != 1 or read_editor_title(title) != plan['expected_form_name']:
        raise Stop('Form widget exact native form title changed')
    _close_initial(frame)
    click(frame.get_by_role('tab', name='Edit', exact=True))
    _one(frame.locator('#form-builder-container'), 'Native form widget canvas changed')
    return frame


_SNAPSHOT_PROJECTION = '''items => items.map(item => ({
        types:Array.from(item.querySelectorAll('[data-field-type]')).map(e=>e.getAttribute('data-field-type')),
        labels:Array.from(item.querySelectorAll('[data-field-type]')).map(e=>e.textContent.trim()),
        short_labels:Array.from(item.querySelectorAll('.short-label')).map(e=>e.textContent),
        controls:Array.from(item.querySelectorAll('input,textarea,select')).filter(e=>
            !(item.querySelectorAll('[data-field-type]').length===1
              && ['SINGLE_OPTIONS','MULTIPLE_OPTIONS'].includes(item.querySelector('[data-field-type]').getAttribute('data-field-type'))
              && e.closest('#options-card'))).map(e=>
            [e.tagName,e.getAttribute('type'),e.getAttribute('name'),e.getAttribute('placeholder'),
             (item.querySelectorAll('[data-field-type]').length===1
               && ['SINGLE_OPTIONS','MULTIPLE_OPTIONS'].includes(item.querySelector('[data-field-type]').getAttribute('data-field-type'))
               && e.matches('input.dropdown-input.form-placeholder') && !e.hasAttribute('id') && !e.hasAttribute('name')
               ? '' : e.value),e.checked||false,
             e.required||false,e.disabled||false,e.getAttribute('aria-label')]),
        native_labels:Array.from(item.querySelectorAll('label,.label-container')).filter(e=>
            !(item.querySelectorAll('[data-field-type]').length===1
              && ['SINGLE_OPTIONS','MULTIPLE_OPTIONS'].includes(item.querySelector('[data-field-type]').getAttribute('data-field-type'))
              && e.closest('#options-card'))).map(e=>e.textContent.trim()),
        canvases:Array.from(item.querySelectorAll('canvas')).map(e=>[e.width,e.height]),
        width:item.style.width
    }))'''


def _snapshot(frame):
    items=frame.locator(CANVAS_ITEMS)
    records=items.evaluate_all(_SNAPSHOT_PROJECTION)
    for index,record in enumerate(records):
        if record['types'] not in (['SINGLE_OPTIONS'],['MULTIPLE_OPTIONS']):continue
        if items.count()!=len(records):raise Stop('Native dropdown canvas changed during selected-state inventory')
        item=items.nth(index)
        label=_one(item.locator('[data-field-type]'),'Native dropdown selected-state owner changed')
        click(label)
        # Native inactive dropdowns use a button, selected dropdowns use an
        # input. Retain all input attributes by comparing selected to selected.
        selected=item.evaluate('(item)=> ('+_SNAPSHOT_PROJECTION+')([item])[0]')
        if selected['types']!=record['types']:
            raise Stop('Native dropdown type changed during selected-state inventory')
        records[index]=selected
    return records


def _activate(frame, item, kind, *, profile=None):
    profile = PROFILES[kind] if profile is None else profile
    label = _one(item.locator('[data-field-type="' + profile['type'] + '"]'),
                 'Native form widget family or owner changed')
    if item.locator('[data-field-type]').count() != 1:
        raise Stop('Native form widget owns more than one field type')
    if kind in ('single_dropdown','multi_dropdown'):click(label)
    control = item.locator(profile['input'])
    if kind=='checkbox':
        if not 1<=control.count()<=101 or any(control.nth(i).is_enabled() for i in range(control.count())):
            raise Stop('Native checkbox preview must contain its captured disabled choice inputs')
    elif control.count() != 1:
        raise Stop('Native form widget input shape changed')
    if kind not in ('single_dropdown','multi_dropdown'):click(label)
    click(_one(item.locator('[aria-label="Open settings"]'), 'Native form widget settings owner changed'))
    if profile.get('sidebar_header',True):
        frame.locator('#form_custom_sidebar').get_by_text(profile['tile'],exact=True).wait_for(state='visible',timeout=45000)
    if kind in ('file_upload','checkbox','single_dropdown','multi_dropdown','url'):
        click(_one(frame.locator('#form_custom_sidebar').get_by_text('Content',exact=True),
                   'Native File Upload Content pane changed'))
    general = frame.locator('#general-settings')
    general.wait_for(state='visible', timeout=45000)
    if general.count() != 1:
        raise Stop('Native form widget General Settings changed')
    label_selector=profile['properties']['label']
    if not frame.locator(label_selector).is_visible():
        click(_one(frame.get_by_text('General Settings',exact=True),'Native widget General Settings header changed'))
    frame.locator(label_selector).wait_for(state='visible',timeout=45000)
    return profile


def _advanced(frame):
    node=frame.locator('#uniqueKey input')
    if node.count()!=1 or not node.is_visible():
        click(_one(frame.get_by_text('Advanced Settings',exact=True),'Native custom-field Advanced Settings changed'))
    frame.locator('#uniqueKey input').wait_for(state='visible',timeout=45000)
    _one(frame.locator('#uniqueKey input'),'Native custom-field Unique Key is unavailable')


def _read_input(node,key):
    value=node.input_value()
    if key=='unique_key' and not value:
        value=node.get_attribute('placeholder')
    if key=='unique_key' and isinstance(value,str) and value and not value.startswith('contact.'):
        # Captured unsaved inputs expose the bare key, while saved inputs are
        # disabled and expose contact.<key>. Normalize only that native prefix.
        value='contact.'+value
    return value



URL_MODES = ('allow_all','allow_only','block')


def _url_properties(value):
    mode=value['domain_mode'];domains=value['domains']
    if (mode not in URL_MODES or not isinstance(domains,list) or len(domains)>100
            or mode=='allow_all' and domains or mode!='allow_all' and not domains):
        raise Stop('URL requires a captured domain mode and its exact active domain list')
    for domain in domains:
        if (not isinstance(domain,str) or not 1<=len(domain)<=253
                or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?',domain)):
            raise Stop('URL domains must be explicit lowercase hostnames without paths, schemes or ports')
    if len(domains)!=len(set(domains)):
        raise Stop('URL domains must be unique')


def _url_options(frame):
    panel=_one(frame.locator('#form_custom_sidebar'),'Native URL sidebar changed')
    modes=[]
    for mode in URL_MODES:
        owner=_one(panel.locator('label[data-testid="url-mode-'+mode+'"]'),'Native URL mode owner changed')
        radio=owner.locator('input[name="url-domain-mode"][value="'+mode+'"]')
        if radio.count()!=1 or radio.get_attribute('type')!='radio':
            raise Stop('Native URL mode input changed')
        if radio.is_checked():modes.append(mode)
    if len(modes)!=1:raise Stop('Native URL domain mode is ambiguous')
    chips=panel.locator('[data-testid^="url-domain-chip-"]')
    editor=panel.locator('input#url-domain-input')
    domains=[]
    if modes[0]=='allow_all':
        if chips.count() or editor.count() and editor.is_visible():
            raise Stop('Native URL domain editor is visible in Allow all mode')
    else:
        node=_one(editor,'Native URL domain editor is unavailable')
        if node.input_value():raise Stop('Native URL has an uncommitted domain draft')
        if chips.count()>100:raise Stop('Native URL domain list exceeds its bounded inventory')
        for index in range(chips.count()):
            chip=_one(panel.locator('[data-testid="url-domain-chip-'+str(index)+'"]'),
                      'Native URL domain order changed')
            domain=chip.inner_text().strip()
            remove=_one(chip.locator('button#url-domain-remove-'+str(index)),
                        'Native URL domain removal owner changed')
            if remove.get_attribute('aria-label')!='Remove '+domain:
                raise Stop('Native URL domain chip/removal identity changed')
            domains.append(domain)
    result={'domain_mode':modes[0],'domains':domains}
    # An empty list is a valid transitional native state before adding a domain.
    if domains or modes[0]=='allow_all':_url_properties(result)
    return result


def _write_url_options(frame,before,desired):
    current=_url_options(frame)
    if current!={key:before[key] for key in ('domain_mode','domains')}:
        raise Stop('Native URL domain settings changed after preflight')
    panel=frame.locator('#form_custom_sidebar')
    if current['domain_mode']!=desired['domain_mode']:
        owner=_one(panel.locator('label[data-testid="url-mode-'+desired['domain_mode']+'"]'),
                   'Native URL requested mode owner changed')
        click(owner)
        wait_until(lambda:_url_options(frame)['domain_mode']==desired['domain_mode'],
                   'Native URL domain mode did not settle')
    if desired['domain_mode']=='allow_all':return
    current=_url_options(frame)
    if current['domains']==desired['domains']:return
    # Replace the finite active list once, with every removal bound to its chip.
    for index in range(len(current['domains'])-1,-1,-1):
        chip=_one(panel.locator('[data-testid="url-domain-chip-'+str(index)+'"]'),
                  'Native URL domain removal owner changed')
        remove=_one(chip.locator('button#url-domain-remove-'+str(index)),
                    'Native URL domain removal control changed')
        if remove.get_attribute('aria-label')!='Remove '+current['domains'][index]:
            raise Stop('Native URL domain changed before removal')
        click(remove)
        wait_until(lambda:panel.locator('[data-testid^="url-domain-chip-"]').count()==index,
                   'Native URL domain removal did not settle once')
    for index,domain in enumerate(desired['domains']):
        node=_one(panel.locator('input#url-domain-input'),'Native URL domain editor changed')
        if node.input_value():raise Stop('Native URL domain draft appeared before append')
        fill(node,domain);node.press('Enter')
        wait_until(lambda:node.input_value()=='' and panel.locator('[data-testid^="url-domain-chip-"]').count()==index+1,
                   'Native URL domain append did not settle once')
        if _url_options(frame)['domains']!=desired['domains'][:index+1]:
            raise Stop('Native URL domain append changed the ordered chip inventory')


def _upload_options(frame):
    panel=_one(frame.locator('#form_custom_sidebar'),'Native File Upload sidebar changed')
    click(_one(panel.get_by_text('Upload options',exact=True),'Native File Upload options pane changed'))
    panel.locator('#all[role="checkbox"]').wait_for(state='visible',timeout=45000)
    access=[]
    for choice in ('private','public'):
        node=panel.locator('label.n-radio-button > input[name="fileAccess"][value="'+choice+'"]')
        if node.count()!=1:raise Stop('Native File Upload access controls changed')
        if node.is_checked():access.append(choice)
    if len(access)!=1:raise Stop('Native File Upload access is ambiguous')
    selected=[]
    for key in FILE_TYPES:
        node=_one(panel.locator('#'+key+'[role="checkbox"]'),'Native File Upload file-type control changed')
        state=node.get_attribute('aria-checked')
        if state not in ('true','false'):raise Stop('Native File Upload file-type state is unavailable')
        if state=='true':selected.append(key)
    multiple=_one(panel.get_by_role('switch'),'Native File Upload multiple-files control changed')
    state=multiple.get_attribute('aria-checked')
    if state not in ('true','false'):raise Stop('Native File Upload multiple-files state is unavailable')
    maximum=panel.locator('#max-file-limit input');limit=None
    if state=='true':
        text=_one(maximum,'Native File Upload max-file limit is unavailable').input_value()
        if text:
            if not re.fullmatch(r'[1-9][0-9]{0,3}',text):raise Stop('Native max-file limit is not a positive count')
            limit=int(text)
    elif maximum.count() and maximum.is_visible():raise Stop('Single-file upload unexpectedly exposes a max-file limit')
    return {'file_access':access[0],'file_types':selected,'multiple_files':state=='true','max_files':limit}


def _option_switch(panel,label):
    return _one(panel.get_by_text(label,exact=True).locator('..').get_by_role('switch'),
                'Native Checkbox '+label+' switch changed')


def _checkbox_options(frame):
    panel=_one(frame.locator('#form_custom_sidebar'),'Native Checkbox sidebar changed')
    click(_one(panel.get_by_text('Options',exact=True),'Native Checkbox Options pane changed'))
    panel.locator('#option-label-0 input').wait_for(state='visible',timeout=45000)
    styles=[]
    for style in ('standard','bubble'):
        node=_one(panel.get_by_role('img',name=style.title()+' checkbox style',exact=True),'Native Checkbox style control changed').locator('..')
        if 'style-option-active' in (node.get_attribute('class') or '').split():styles.append(style)
    if len(styles)!=1:raise Stop('Native Checkbox style is ambiguous')
    calc=_option_switch(panel,'Enable calculations').get_attribute('aria-checked')
    spread=_option_switch(panel,'Spread to columns').get_attribute('aria-checked')
    if calc not in ('true','false') or spread not in ('true','false'):
        raise Stop('Native Checkbox calculation/column state is unavailable')
    labels=panel.locator('[id^="option-label-"] input');count=labels.count()
    if not 1<=count<=100:raise Stop('Native Checkbox option inventory is unavailable')
    options=[]
    for index in range(count):
        label=_one(panel.locator('#option-label-'+str(index)+' input'),'Native Checkbox option positions changed')
        value=panel.locator('#option-value-'+str(index)+' input')
        if calc=='true':score=_one(value,'Native Checkbox calculation value changed').input_value()
        else:
            if value.count() and value.is_visible():raise Stop('Checkbox calculation value is visible while calculations are off')
            score=None
        options.append({'label':label.input_value(),'value':score})
    column=panel.locator('#fieldQueryKey input');columns=None
    if spread=='true':
        value=_one(column,'Native Checkbox Columns input changed').input_value()
        if not re.fullmatch(r'[1-9][0-9]{0,2}',value):raise Stop('Native Checkbox Columns is not a positive count')
        columns=int(value)
    elif column.count() and column.is_visible():raise Stop('Checkbox Columns input is visible while columns are off')
    other_label=panel.locator('#other-option-label input');other=None
    if other_label.count():
        node=_one(other_label,'Native Checkbox Other label changed')
        if node.get_attribute('readonly') is None or node.input_value()!='Other':
            raise Stop('Native Checkbox Other readonly identity changed')
        other={'label':'Other','placeholder':_one(panel.locator('#other-option-placeholder input'),
                                                 'Native Checkbox Other placeholder changed').input_value()}
    return {'options':options,'style':styles[0],'calculations':calc=='true','columns':columns,'other':other}


def _write_checkbox_options(frame,before,desired):
    _checkbox_options(frame);panel=frame.locator('#form_custom_sidebar')
    if before['style']!=desired['style']:
        click(panel.get_by_role('img',name=desired['style'].title()+' checkbox style',exact=True).locator('..'))
    for label,target in (('Enable calculations',desired['calculations']),('Spread to columns',desired['columns'] is not None)):
        node=_option_switch(panel,label)
        if (node.get_attribute('aria-checked')=='true')!=target:
            click(node)
            wait_until(lambda:(node.get_attribute('aria-checked')=='true')==target,'Native Checkbox switch did not settle')
    labels=panel.locator('[id^="option-label-"] input')
    while labels.count()>len(desired['options']):
        count=labels.count()
        # The label input lives in n-input wrapper/input div; bind removal by
        # the captured option-label owner, not by a global repeated button ID.
        row=panel.locator('#option-label-'+str(count-1)).locator('..').locator('..')
        remove=_one(row.locator('button#remove-option'),'Native Checkbox option removal owner changed')
        if not remove.is_enabled():raise Stop('Native Checkbox option removal is disabled')
        click(remove);wait_until(lambda:labels.count()==count-1,'Native Checkbox option removal did not settle once')
    while labels.count()<len(desired['options']):
        count=labels.count();click(_one(panel.locator('button#add-option'),'Native Checkbox Add option changed'))
        wait_until(lambda:labels.count()==count+1,'Native Checkbox Add option did not settle once')
    for index,option in enumerate(desired['options']):
        node=panel.locator('#option-label-'+str(index)+' input')
        if node.input_value()!=option['label']:fill(node,option['label']);node.press('Tab')
        if desired['calculations']:
            node=panel.locator('#option-value-'+str(index)+' input')
            if node.input_value()!=option['value']:fill(node,option['value']);node.press('Tab')
    present=panel.locator('#other-option-label input').count()==1
    if present and desired['other'] is None:
        click(_one(panel.locator('button#remove-other-option'),'Native Checkbox Other removal changed'))
        wait_until(lambda:panel.locator('#other-option-label input').count()==0,'Native Checkbox Other did not remove once')
    elif not present and desired['other'] is not None:
        click(_one(panel.locator('button#add-other-option'),'Native Checkbox Add Other changed'))
        wait_until(lambda:panel.locator('#other-option-label input').count()==1,'Native Checkbox Other did not append once')
    if desired['other'] is not None:
        node=_one(panel.locator('#other-option-placeholder input'),'Native Checkbox Other placeholder changed')
        if node.input_value()!=desired['other']['placeholder']:fill(node,desired['other']['placeholder']);node.press('Tab')
    if desired['columns'] is not None:
        node=_one(panel.locator('#fieldQueryKey input'),'Native Checkbox Columns control changed')
        if node.input_value()!=str(desired['columns']):fill(node,str(desired['columns']));node.press('Tab')


def _read(frame, item, kind, *, profile=None):
    profile = _activate(frame, item, kind, profile=profile)
    result = {}
    for key, selector in profile['properties'].items():
        if key in ('custom_field_name','unique_key'):_advanced(frame)
        node = _one(frame.locator(selector), 'Native form widget property changed: ' + key)
        value = _read_input(node,key)
        if key == 'width':
            if not re.fullmatch(r'[0-9]{1,3}', value):
                raise Stop('Native form widget Width is not exposed as a whole percentage')
            value = int(value)
        result[key] = value
    for key, selector in profile['flags'].items():
        node = _one(frame.locator(selector), 'Native form widget Boolean changed: ' + key)
        state = node.get_attribute('aria-checked')
        if node.get_attribute('role') != 'checkbox' or state not in ('true', 'false'):
            raise Stop('Native form widget Boolean state is unexposed')
        result[key] = state == 'true'
    hidden = frame.locator('#fieldHiddenvalue input')
    if result.get('hidden'):
        result['hidden_value'] = _one(hidden, 'Native form widget Hidden value is unavailable').input_value()
    elif hidden.count() and hidden.is_visible():
        raise Stop('Native form widget exposes a Hidden value while Hidden is off')
    if kind=='url':result.update(_url_options(frame))
    if kind=='file_upload':result.update(_upload_options(frame))
    if kind=='checkbox':result.update(_checkbox_options(frame))
    if kind in ('single_dropdown','multi_dropdown'):result.update(single_dropdown.read_options(frame))
    _close_properties(frame)
    return _properties(kind, result, profile=profile)


def _inventory(frame):
    _close_initial(frame)
    items = frame.locator(CANVAS_ITEMS); count = items.count(); records = []
    family = {profile['type']:kind for kind, profile in PROFILES.items()}
    for index in range(count):
        if items.count() != count:
            raise Stop('Native form widget canvas changed during inventory')
        item = items.nth(index); labels = item.locator('[data-field-type]')
        if labels.count() != 1:
            raise Stop('Native canvas type inventory is missing or ambiguous')
        kind = family.get(labels.get_attribute('data-field-type'))
        if kind:
            records.append({'kind':kind, 'index':index + 1, 'properties':_read(frame, item, kind)})
    keys = [record['properties'][_key(record['kind'])] for record in records]
    if len(keys) != len(set(keys)):
        raise Stop('Native form widget Query Keys are duplicated')
    return records


def _write(frame, item, kind, before, desired, *, profile=None):
    if _read(frame, item, kind, profile=profile) != before:
        raise Stop('Native form widget changed after complete preflight')
    profile = _activate(frame, item, kind, profile=profile)
    def toggle(key, target):
        node = _one(frame.locator(profile['flags'][key]),
                    'Native form widget Boolean control changed')
        if (node.get_attribute('aria-checked') == 'true') != target:
            if 'n-checkbox--disabled' in (node.get_attribute('class') or '').split():
                raise Stop('Native form widget requested Boolean is disabled')
            click(node)
            wait_until(lambda:node.get_attribute('aria-checked') == ('true' if target else 'false'),
                       'Native form widget Boolean did not settle')
    # Disable mutually exclusive flags before enabling their counterpart.
    for key in profile['flags']:
        if not desired[key]:
            toggle(key, False)
    for key, selector in profile['properties'].items():
        if key in ('custom_field_name','unique_key'):_advanced(frame)
        node = _one(frame.locator(selector), 'Native form widget property control changed')
        target = str(desired[key])
        if _read_input(node,key) != target:
            fill(node, target.removeprefix('contact.') if key=='unique_key' else target); node.press('Tab')
    for key in profile['flags']:
        if desired[key]:
            toggle(key, True)
    if desired.get('hidden'):
        node = _one(frame.locator('#fieldHiddenvalue input'), 'Native form widget Hidden value changed')
        if node.input_value() != desired['hidden_value']:
            fill(node, desired['hidden_value']); node.press('Tab')
    if kind=='file_upload':
        _upload_options(frame)
        panel=frame.locator('#form_custom_sidebar')
        if before['file_access']!=desired['file_access']:
            radio=panel.locator('label.n-radio-button > input[name="fileAccess"][value="'+desired['file_access']+'"]')
            if radio.count()!=1 or not radio.locator('..').is_visible():
                raise Stop('Native File Upload access choice changed')
            if not radio.is_enabled():raise Stop('Native File Upload access is already immutable')
            click(radio.locator('..'))
            wait_until(lambda:radio.is_checked(),'Native File Upload access did not settle')
        if before['file_types']!=desired['file_types']:
            for key in FILE_TYPES:
                node=panel.locator('#'+key+'[role="checkbox"]'); target=key in desired['file_types']
                if (node.get_attribute('aria-checked')=='true')!=target:
                    click(node)
                    wait_until(lambda:(node.get_attribute('aria-checked')=='true')==target,
                               'Native File Upload file-type choice did not settle')
        multiple=panel.get_by_role('switch')
        if (multiple.get_attribute('aria-checked')=='true')!=desired['multiple_files']:
            click(multiple)
            wait_until(lambda:(multiple.get_attribute('aria-checked')=='true')==desired['multiple_files'],
                       'Native File Upload multiple-files choice did not settle')
        if desired['multiple_files']:
            node=_one(panel.locator('#max-file-limit input'),'Native File Upload max-file limit changed')
            target='' if desired['max_files'] is None else str(desired['max_files'])
            if node.input_value()!=target:fill(node,target);node.press('Tab')
    if kind=='url':_write_url_options(frame,before,desired)
    if kind=='checkbox':_write_checkbox_options(frame,before,desired)
    if kind in ('single_dropdown','multi_dropdown'):single_dropdown.write_options(frame,before,desired)
    _close_properties(frame)
    if _read(frame, item, kind, profile=profile) != desired:
        raise Stop('Native form widget ignored authored properties')


def _append(frame, kind, before_snapshot):
    profile = PROFILES[kind]
    _close_initial(frame)
    click(_one(frame.get_by_role('button', name='Add Form Element', exact=True), 'Native Add Form Element changed'))
    dialog = frame.get_by_role('dialog')
    dialog.wait_for(state='visible', timeout=45000)
    if dialog.count() != 1 or dialog.get_by_text('Form Element', exact=True).count() != 1:
        raise Stop('Native form widget Quick Add drawer changed')
    tile = dialog.locator('.gui__builder-card > .gui__builder-card--label').filter(
        has_text=re.compile(r'^\s*' + re.escape(profile['tile']) + r'\s*$'))
    source = _one(tile, 'Native form widget tile is missing or ambiguous').locator('..')
    target = _one(frame.locator(SUBMIT_DROP), 'Native form widget Submit insertion boundary changed')
    box = target.bounding_box()
    if not box or min(box['width'], box['height']) < 4:
        raise Stop('Native form widget Submit boundary has no safe geometry')
    source.drag_to(target, target_position={'x':box['width'] / 2, 'y':1}, timeout=45000)
    # Native creation is asynchronous; never repeat the drag on an old snapshot.
    wait_until(lambda:frame.locator(CANVAS_ITEMS).count() == len(before_snapshot) + 1,
               'Native form widget insertion did not produce exactly one wrapper')
    _close_initial(frame)
    after = _snapshot(frame)
    candidates = [index for index, row in enumerate(after)
                  if row['types'] == [profile['type']] and after[:index] + after[index + 1:] == before_snapshot]
    if len(candidates) != 1:
        raise Stop('Native form widget insertion changed another field or has ambiguous ownership')
    index = candidates[0]; item = frame.locator(CANVAS_ITEMS).nth(index)
    defaults = _read(frame, item, kind)
    suffix = re.fullmatch(re.escape(profile['tile']) + r' ([a-z0-9]{' + str(profile['suffix']) + '})', defaults['label'])
    if (not suffix or not _default_key(profile,defaults[_key(kind)],suffix.group(1))
            or any(defaults[key] != value for key, value in profile['defaults'].items())):
        raise Stop('New native form widget differs from its captured generated identity/defaults')
    if 'unique_key' in profile['properties'] and (defaults['custom_field_name']!=defaults['label']
            or not defaults['unique_key'].startswith('contact.'+profile['key_prefix'])
            or defaults['unique_key'][len('contact.'+profile['key_prefix']):].replace('_','')!=suffix.group(1)):
        raise Stop('New native form widget Custom Field Name differs from its generated label')
    return index, item, defaults


def _default_key(profile,key,suffix):
    if profile.get('key_property')=='unique_key':
        return bool(re.fullmatch(r'contact\.'+re.escape(profile['key_prefix'])+r'[a-z0-9_]+',key))
    return key==profile['key_prefix']+suffix


def _desired_records(plan):
    result = {record['properties'][_key(record['kind'])]:{'kind':record['kind'], 'properties':record['properties']}
              for record in plan['expected_fields']}
    for field in plan['fields']:
        if field['index'] is not None:
            previous=next(record for record in plan['expected_fields'] if record['index']==field['index'])
            result.pop(previous['properties'][_key(previous['kind'])])
        result[field['desired'][_key(field['kind'])]] = {'kind':field['kind'], 'properties':field['desired']}
    return result


def validate_receipt(value, step):
    plan = validate(step)
    keys = {'status', 'editor_url', 'configuration_sha256', 'fields', 'saved_snapshot',
            'independent_readback', 'behavior_verified', 'submission_verified'}
    if (not isinstance(value, dict) or set(value) != keys
            or value['status'] != 'FORM_WIDGET_FIELDS_SAVED_AND_REOPENED'
            or value['editor_url'] != plan['start_url']
            or value['configuration_sha256'] != configuration_hash(step)
            or value['independent_readback'] != 'VERIFIED'
            or value['behavior_verified'] is not False or value['submission_verified'] is not False
            or not isinstance(value['fields'], list) or not isinstance(value['saved_snapshot'], list)):
        raise Stop('Native form widget completion is malformed or unbound')
    expected = _desired_records(plan); actual = {}; positions = set()
    for field in value['fields']:
        if (not isinstance(field, dict) or set(field) != {'kind', 'index', 'properties'}
                or type(field['index']) is not int or not 1 <= field['index'] <= len(value['saved_snapshot'])
                or field['index'] in positions):
            raise Stop('Native form widget completion has ambiguous canvas positions')
        properties = _properties(field['kind'], field['properties']); query = properties[_key(field['kind'])]
        if query in actual:
            raise Stop('Native form widget completion has duplicate Query Keys')
        row = value['saved_snapshot'][field['index'] - 1]
        if not isinstance(row, dict) or row.get('types') != [PROFILES[field['kind']]['type']]:
            raise Stop('Native form widget completion does not match its typed canvas')
        actual[query] = {'kind':field['kind'], 'properties':properties}; positions.add(field['index'])
    if actual != expected:
        raise Stop('Native form widget completion differs from the complete requested inventory')
    edits={field['index']:field for field in plan['fields'] if field['index'] is not None}
    original_order = [(edits[record['index']]['desired'][_key(record['kind'])] if record['index'] in edits else record['properties'][_key(record['kind'])])
                      for record in sorted(plan['expected_fields'], key=lambda x:x['index'])]
    old = set(original_order)
    saved_order = [record['properties'][_key(record['kind'])] for record in sorted(value['fields'], key=lambda x:x['index'])
                   if record['properties'][_key(record['kind'])] in old]
    if saved_order != original_order:
        raise Stop('Native form widget completion reordered existing owners')
    return deepcopy(value)


def configure(page, step):
    plan = validate(step); frame = _frame(page, plan)
    before = _inventory(frame)
    if before != plan['expected_fields']:
        raise Stop('Native form widget full previous family inventory changed')
    # Read actual native Query Keys, including built-ins and Address children.
    # Family-aware central selection preserves compatibility with later edits.
    from playwright_recipes.field_placement import _inventory as query_inventory
    queries = query_inventory(frame, allow_unknown_queries=True)
    for field in plan['fields']:
        own=(next(record['properties'][_key(record['kind'])] for record in before if record['index']==field['index'])
             if field['index'] is not None else None)
        if field['desired'][_key(field['kind'])] in queries and field['desired'][_key(field['kind'])]!=own:
            raise Stop('New form widget Query Key collides with an existing native field')
    desired_snapshot = _snapshot(frame)
    for field in sorted(plan['fields'], key=lambda row:row['index'] is None):
        _frame(page, plan)
        if _snapshot(frame) != desired_snapshot:
            raise Stop('Native form widget canvas drifted before its next write')
        previous_snapshot = desired_snapshot
        if field['index'] is None:
            index, item, previous = _append(frame, field['kind'], previous_snapshot)
            inserted = _snapshot(frame)
        else:
            index = field['index'] - 1
            item = frame.locator(CANVAS_ITEMS).nth(index)
            previous = next(record['properties'] for record in before if record['index'] == field['index'])
            inserted = previous_snapshot
        _write(frame, item, field['kind'], previous, field['desired'])
        desired_snapshot = _snapshot(frame)
        expected_without = inserted[:index] + inserted[index + 1:]
        actual_without = desired_snapshot[:index] + desired_snapshot[index + 1:]
        if len(desired_snapshot) != len(inserted) or actual_without != expected_without:
            raise Stop('Native form widget editing changed an unrelated sibling')
    fields = _inventory(frame)
    if {record['properties'][_key(record['kind'])]:{'kind':record['kind'], 'properties':record['properties']} for record in fields} != _desired_records(plan):
        raise Stop('Native form widget final properties differ from the requested complete inventory')
    if _snapshot(frame) != desired_snapshot:
        raise Stop('Native form widget final inventory changed while reading properties')
    wanted_queries=dict(queries)
    for field in plan['fields']:
        if field['index'] is not None:
            old=next(record for record in before if record['index']==field['index'])
            wanted_queries.pop(old['properties'][_key(old['kind'])])
        wanted_queries[field['desired'][_key(field['kind'])]]=PROFILES[field['kind']]['type']
    if query_inventory(frame,allow_unknown_queries=True)!=wanted_queries:
        raise Stop('Native form widget editing changed another field Query Key')
    _frame(page, plan)
    save = _one(frame.get_by_role('button', name='Save', exact=True), 'Native form widget Save changed')
    click(save)
    wait_until(lambda:save.count() == 1 and save.is_enabled(), 'Native form widget Save did not finish')
    reopen_editor(page, 'form', plan['expected_form_name'], plan['start_url'])
    frame = _frame(page, plan)
    if (_inventory(frame) != fields or _snapshot(frame) != desired_snapshot
            or query_inventory(frame,allow_unknown_queries=True)!=wanted_queries):
        raise Stop('Native form widget properties or siblings did not persist after independent reopen')
    return validate_receipt({'status':'FORM_WIDGET_FIELDS_SAVED_AND_REOPENED',
        'editor_url':plan['start_url'], 'configuration_sha256':configuration_hash(step),
        'fields':fields, 'saved_snapshot':desired_snapshot, 'independent_readback':'VERIFIED',
        'behavior_verified':False, 'submission_verified':False}, step)


def verify_completed(page, step, receipt):
    value = validate_receipt(receipt, step); plan = validate(step)
    reopen_editor(page, 'form', plan['expected_form_name'], plan['start_url'])
    frame = _frame(page, plan)
    if _inventory(frame) != value['fields'] or _snapshot(frame) != value['saved_snapshot']:
        raise Stop('Completed form widget properties or sibling inventory drifted; no write repeated')
    return value
