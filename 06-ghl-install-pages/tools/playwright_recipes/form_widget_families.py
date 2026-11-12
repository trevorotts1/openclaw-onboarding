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
from playwright_recipes import form_datetime as datetime_fields
from playwright_recipes import form_html as html_fields

ACTION = 'native_form_widget_fields'
COMMON = ('location_id', 'location_name', 'start_url')
BASE_PROPERTIES = {'label', 'query_key', 'required', 'hidden'}
TEXT_CONTROLS = {'label':'#label input', 'placeholder':'#fieldPlaceholder input',
                 'short_label':'#shortLabel input', 'query_key':'#fieldQueryKey input',
                 'width':'#fieldWidthKey input'}
PROFILES = {
    'image': {'type':'img','tile':'Image','queryless':True,'contact_field':False,
        'sidebar_header':False,'general_selector':'#form_custom_sidebar','key_property':'label',
        'properties':{'label':'#imageLabelInline input','image_url':'#media-center-input','alt_text':'#altText input'},
        'flags':{},'input':None,'generated_label_pattern':r'Image [1-9][0-9]*',
        'defaults':{'image_url':'','alt_text':''}},
    'text_heading': {'type':'h1','tile':'Text','queryless':True,'contact_field':False,
        'key_property':'text','properties':{'text':'.tiptap.ProseMirror'},'flags':{},'input':None},
    'picture_choice': {'type':'RADIO','tile':'Picture Choice','suffix':6,'key_prefix':'picture_choice_',
        'defaults':{'placeholder':'','short_label':'','width':100,'required':False,'hidden':False,
            'options':[{'label':'Option '+str(i),'image_url':None,'alt':''} for i in (1,2,3)]},
        'properties':dict(TEXT_CONTROLS),'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'},
        'input':'[data-testid="picture-choice-card"] input[type="radio"]','picture_inputs':True,
        'hidden_value_captured':False,'extra':('options',)},
    'html': {'type':'html','tile':'Html','generated_label_pattern':r'HTML [1-9][0-9]*',
        'queryless':True,'contact_field':False,'sidebar_header':False,'key_property':'label',
        'properties':{'label':'#htmlLabelInline input'},'flags':{},'input':'input,textarea,select','arbitrary_inputs':True,
        'extra':('html',),'defaults':{'html':''}},
    'bot_protection': {'type':'captcha','tile':'Bot protection','fixed_identity':'@captcha',
        'queryless':True,'contact_field':False,'sidebar_header':False,
        'properties':{'label':'#captchaLabel input'},'flags':{},'input':None,
        'extra':('verification_mode',),'defaults':{'label':'Bot protection','verification_mode':'interactive'}},
    'date': {'type':'DATE','tile':'Date & time','suffix':5,'key_prefix':'date_',
        'creation_mode':'date','generated_prefix':'Date',
        'properties':{**TEXT_CONTROLS,'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'},
        'input':'.date-time-preview-row input','input_count':1,'hidden_value_captured':False,
        'query_pattern':r'[A-Za-z0-9_.&-]{1,256}',
        'general_tab':'[data-name="general"]','general_selector':'#form_custom_sidebar',
        'extra':datetime_fields.DATE_EXTRA,
        'defaults':{'placeholder':'YYYY-MM-DD','short_label':'','width':100,'required':False,'hidden':False,
            'date_format':'yyyy-mm-dd','date_separator':'dash','date_range':'any','disable_picker':False}},
    'time': {'type':'TIME','tile':'Date & time','suffix':5,'key_prefix':'time_','creation_mode':'time','generated_prefix':'Time',
        'properties':{**TEXT_CONTROLS,'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'},
        'input':'input.form-control','hidden_value_captured':False,
        'general_tab':'[data-name="general"]','general_selector':'#form_custom_sidebar',
        'extra':datetime_fields.TIME_EXTRA,
        'defaults':{'placeholder':'HH:MM','short_label':'','width':100,'required':False,'hidden':False,
            'time_format':'24','default_time':'none','time_range':'any','disable_picker':False}},
    'date_time': {'type':'DATE_TIME','tile':'Date & time','suffix':5,'key_prefix':'date_&_time_','unique_key_prefix':'date_','creation_mode':'date_time','generated_prefix':'Date & time',
        'properties':{**TEXT_CONTROLS,'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'},
        'input':'.date-time-preview-row input','input_count':2,'hidden_value_captured':False,
        'query_pattern':r'[A-Za-z0-9_.&-]{1,256}',
        'general_tab':'[data-name="general"]','general_selector':'#form_custom_sidebar',
        'extra':datetime_fields.EXTRA,
        'defaults':{'placeholder':'YYYY-MM-DD','short_label':'','width':100,'required':False,'hidden':False,
            'date_format':'yyyy-mm-dd','date_separator':'dash','time_format':'24','default_time':'none',
            'date_range':'any','disable_picker':False}},
    'single_dropdown':single_dropdown.PROFILE,
    'multi_dropdown':multi_dropdown.PROFILE,
    'url': {'type':'URL', 'tile':'URL', 'suffix':4, 'key_prefix':'url_',
        'properties':{**TEXT_CONTROLS,'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'}, 'input':'input.form-control',
        'extra':('domain_mode','domains'),
        'defaults':{'placeholder':'Enter a URL','short_label':'','width':100,'required':False,
                    'hidden':False,'domain_mode':'allow_all','domains':[]}},
    'text_box_list': {'type':'TEXTBOX_LIST','tile':'Text Box List','suffix':4,'key_prefix':'text_box_list_',
        'key_property':'unique_key','properties':{'label':'#label input','short_label':'#shortLabel input',
            'width':'#fieldWidthKey input','custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired'},'input':'input.form-control','multiple_inputs':True,
        'extra':('options',),'defaults':{'short_label':'','width':100,'required':False,
            'options':[{'label':'Option '+str(i),'value':''} for i in (1,2,3)]}},
    'monetary': {'type':'MONETORY','tile':'Monetary','suffix':4,'key_prefix':'monetary_',
        'properties':{**TEXT_CONTROLS,'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'},
        'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'},'input':'input.form-control',
        'hidden_value_captured':False,'defaults':{'placeholder':'Enter amount','short_label':'','width':100,
            'required':False,'hidden':False}},
    'source': {'type':'source','tile':'Source','fixed_identity':'@source','contact_field':False,
        'properties':{'value':'#sourceLabel input'},'flags':{},'input':None,'primary_property':'value',
        'sidebar_header':False,'defaults':{'value':''}},
    'score': {'type':'SCORE','tile':'Score','suffix':4,'key_prefix':'score_',
        'properties':dict(TEXT_CONTROLS),'flags':{'required':'#fieldRequired','hidden':'#fieldCheckbox'},
        'input':'input.form-control','hidden_value_captured':False,
        'defaults':{'placeholder':'Ex: Your Score is 100%','short_label':'','width':100,'required':False,'hidden':False}},
    'rating': {'type':'RATING','tile':'Rating','generated_label_pattern':r'Rating .+','fixed_identity':'@rating',
        'queryless':True,'general_selector':'#rating-general-settings','input':'input.rating-input','input_count':2,
        'properties':{'label':'#label input','short_label':'#shortLabel input','width':'#fieldWidthKey input'},
        'flags':{'required':'#fieldRequired'},'preview_properties':{
            'lowest_label':'input[placeholder="Lowest Rating"]','highest_label':'input[placeholder="Highest Rating"]'},
        'defaults':{'short_label':'','width':100,'required':False,'lowest_label':'Bad','highest_label':'Good'}},
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


def _identity(kind,properties):
    return PROFILES[kind].get('fixed_identity') or properties[_key(kind)]


def _properties(kind, value, *, profile=None):
    if (not isinstance(kind,str) or kind not in PROFILES
            and not (kind=='date' and profile is not None and profile.get('collection_mode')=='date')):
        raise Stop('Uncaptured form widget family')
    profile = PROFILES[kind] if profile is None else profile
    keys = set(profile['properties']) | set(profile['flags']) | set(profile.get('extra', ())) | set(profile.get('preview_properties',{}))
    if not isinstance(value, dict) or set(value) != keys | ({'hidden_value'} if value.get('hidden') else set()):
        raise Stop('Form widget properties must include the full captured family inventory')
    for key in profile['properties']:
        if key == 'width':
            if type(value[key]) is not int or not 1 <= value[key] <= 100:
                raise Stop('Form widget Width must be a whole percentage from 1 through 100')
        else:
            _text(value[key], key, token=key in ('query_key','unique_key') and not (key=='query_key' and profile.get('query_pattern')))
            if key=='query_key' and profile.get('query_pattern') and not re.fullmatch(profile['query_pattern'],value[key]):
                raise Stop('Native Date & time Query Key has an uncaptured shape')
            if key=='unique_key' and (not value[key].startswith('contact.') or value[key]=='contact.'):
                raise Stop('Native custom-field Unique Key must be the canonical contact.* identity')
    for key in profile.get('preview_properties',{}):_text(value[key],key)
    if (any(type(value[key]) is not bool for key in profile['flags'])
            or value.get('required') and value.get('hidden')):
        raise Stop('Form widget Required and Hidden must be exclusive Boolean values')
    if value.get('hidden'):
        if profile.get('hidden_value_captured') is False:
            raise Stop('Native widget Hidden-value control requires its captured family profile')
        _text(value['hidden_value'], 'hidden_value')
    if kind=='image' and value['image_url']:
        from playwright_recipes.quiz_picture_questions import _https
        _https(value['image_url'])
    if kind=='text_heading' and (not value['text'].strip() or any(ord(c)<32 for c in value['text'])):
        raise Stop('Text heading requires one explicit plain-text line')
    if kind=='picture_choice':
        options=value['options']
        if not isinstance(options,list) or not 2<=len(options)<=50:raise Stop('Picture Choice requires its complete option inventory')
        for option in options:
            if not isinstance(option,dict) or set(option) not in ({'label','image_url','alt'},{'label','image_url','alt','media_button_name'}):raise Stop('Picture Choice requires exact label, image URL and alt text')
            _text(option['label'],'label');_text(option['alt'],'alt')
            if option['image_url'] is not None:
                from playwright_recipes.quiz_picture_questions import _https
                if option['image_url'] is not None:_https(option['image_url'])
            elif option['alt']!='':raise Stop('Blank Picture Choice image must have empty alt')
            if 'media_button_name' in option:_text(option['media_button_name'],'media_button_name')
        if len({x['label'].casefold() for x in options})!=len(options):raise Stop('Picture Choice option labels must be unique')
    if kind=='html':html_fields.validate_html(value['html'])
    if kind=='bot_protection' and value['verification_mode']!='interactive':
        raise Stop('Bot protection requires the captured Interactive verification mode')
    if kind in ('date','date_time','time') and profile.get('datetime_options',True):datetime_fields.validate_properties(value,kind=kind)
    if profile.get('collection_mode') and value.get('collection_mode')!=profile['collection_mode']:
        raise Stop('Survey Date & time collection mode is fixed to its captured typed family')
    if kind=='url':
        if value['hidden']:
            raise Stop('URL Hidden-value controls have not been captured')
        _url_properties(value)
    if kind=='text_box_list':single_dropdown.validate_properties(value,prefill=True)
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
        if _identity(field['kind'],properties) in queries:
            raise Stop('Existing form widget Query Keys are duplicated')
        indices.add(field['index']); queries.add(_identity(field['kind'],properties))
    targets = set(); desired_keys = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'kind', 'index', 'desired'}:
            raise Stop('Each form widget write requires family, existing position or explicit new position, and complete properties')
        desired = _properties(change['kind'], change['desired'])
        if change['index'] is None and PROFILES[change['kind']].get('creation_supported') is False:
            raise Stop('Native widget creation requires its captured generated canonical identity')
        if change['kind']=='picture_choice' and change['index'] is None:
            if len(desired['options'])!=3 or any(option['image_url'] is None or not option.get('media_button_name') for option in desired['options']):
                raise Stop('New Picture Choice requires three approved catalog image tiles')
        identity_key = _key(change['kind'])
        desired_identity=_identity(change['kind'],desired)
        index = change['index']
        if index is not None:
            if type(index) is not int or index in targets:
                raise Stop('Existing form widget edits require unique canvas positions')
            previous = [item for item in before if item['index'] == index]
            if len(previous) != 1 or previous[0]['kind'] != change['kind']:
                raise Stop('Form widget edit does not match its complete previous family inventory')
            if (identity_key=='unique_key' and desired[identity_key] != previous[0]['properties'][identity_key]
                    or desired_identity != _identity(change['kind'],previous[0]['properties']) and desired_identity in queries):
                raise Stop('Existing widget identity is immutable or collides with another native field')
            for immutable in ('file_access','custom_field_name','unique_key'):
                if immutable in desired and desired[immutable] != previous[0]['properties'][immutable]:
                    raise Stop('Existing native custom-field access/name is immutable in this form job')
            if change['kind']=='picture_choice':
                old=previous[0]['properties']['options'];new=desired['options']
                if len(old)!=len(new):raise Stop('Existing Picture Choice preserves option count')
                for a,b in zip(old,new):
                    if a['image_url']!=b['image_url']:
                        if not b['image_url'] or not b.get('media_button_name'):
                            raise Stop('Picture Choice image replacement requires an approved catalog tile')
                    elif a['alt']!=b['alt']:
                        raise Stop('Picture Choice alt follows the selected catalog image')
                from playwright_recipes.quiz_choice_questions import _option_transition
                _option_transition([x['label'] for x in new],[x['label'] for x in old])
            targets.add(index)
        elif desired_identity in queries:
            raise Stop('New form widget Query Key collides with a current native widget')
        if desired_identity in desired_keys:
            raise Stop('Requested form widget Query Keys must be unique')
        desired_keys.add(desired_identity)
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
        if record['types'] not in (['SINGLE_OPTIONS'],['MULTIPLE_OPTIONS'],['TEXTBOX_LIST']):continue
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
    control = item.locator(profile['input'] or 'input,textarea,select')
    if profile.get('arbitrary_inputs'):
        # Custom HTML owns its authored descendants, not native Contact fields.
        pass
    elif profile['input'] is None:
        if control.count():raise Stop('Native non-contact widget unexpectedly exposes a preview input')
    elif profile.get('picture_inputs'):
        if not 2<=control.count()<=50 or any(control.nth(i).is_enabled() for i in range(control.count())):
            raise Stop('Native Picture Choice preview must contain disabled radio inputs')
    elif kind=='checkbox':
        if not 1<=control.count()<=101 or any(control.nth(i).is_enabled() for i in range(control.count())):
            raise Stop('Native checkbox preview must contain its captured disabled choice inputs')
    elif 'input_count' in profile:
        if control.count()!=profile['input_count']:raise Stop('Native widget preview input count changed')
    elif profile.get('multiple_inputs'):
        if not 1<=control.count()<=100 or any(control.nth(i).get_attribute('type')!='text' for i in range(control.count())):
            raise Stop('Native Text Box List input inventory changed')
    elif control.count() != 1:
        raise Stop('Native form widget input shape changed')
    if kind not in ('single_dropdown','multi_dropdown'):click(label)
    click(_one(item.locator('[aria-label="Open settings"]'), 'Native form widget settings owner changed'))
    if profile.get('sidebar_header',True):
        frame.locator(profile.get('sidebar','#form_custom_sidebar')).get_by_text(
            profile.get('sidebar_title',profile['tile']),exact=True).wait_for(state='visible',timeout=45000)
    if kind in ('file_upload','checkbox','single_dropdown','multi_dropdown','url','text_box_list','date_time','time','date','picture_choice',
                'monetary','score','source','bot_protection','rating'):
        click(_one(frame.locator(profile.get('sidebar','#form_custom_sidebar')).get_by_text('Content',exact=True),
                   'Native File Upload Content pane changed'))
    if profile.get('general_tab'):
        click(_one(frame.locator(profile.get('sidebar','#form_custom_sidebar')).locator(profile['general_tab']),
                   'Native Date & time General tab changed'))
    general = frame.locator(profile.get('general_selector','#general-settings'))
    general.wait_for(state='visible', timeout=45000)
    if general.count() != 1:
        raise Stop('Native form widget General Settings changed')
    label_selector=profile['properties'][profile.get('primary_property','label')]
    if not frame.locator(label_selector).is_visible():
        click(_one(frame.get_by_text('General Settings',exact=True),'Native widget General Settings header changed'))
    frame.locator(label_selector).wait_for(state='visible',timeout=45000)
    return profile


def read_text_heading(item):
    label=item.locator('[data-field-type="h1"]')
    if label.count()!=1 or item.locator('[data-field-type]').count()!=1:
        raise Stop('Text heading owner changed')
    editor=_one(item.locator('.tiptap.ProseMirror[contenteditable="true"]'),'Text heading editor changed')
    heading=_one(editor.locator(':scope > h1'),'Text heading markup changed')
    if editor.locator(':scope > *').count()!=1 or heading.locator('*').count()!=0:
        raise Stop('Text heading contains uncaptured markup')
    if (heading.get_attribute('style') or '').replace(' ','')!='padding-left:0px!important;':
        raise Stop('Text heading style differs from captured default')
    return heading.inner_text()


def _set_survey_collection_mode(frame,item,profile):
    """Select the captured Date & time variant before scanning its new defaults."""
    panel_selector=profile.get('sidebar','#survey_custom_sidebar')
    label=_one(item.locator('[data-field-type]'),'Survey Date & time created widget changed')
    if item.locator('[data-field-type]').count()!=1:
        raise Stop('Survey Date & time created widget has an ambiguous type owner')
    click(label)
    click(_one(item.locator('[aria-label="Open settings"]'),'Survey Date & time Open settings changed'))
    panel=_one(frame.locator(panel_selector),'Survey Date & time sidebar changed')
    click(_one(panel.get_by_text('Content',exact=True),'Survey Date & time Content tab changed'))
    click(_one(panel.locator('[data-name="general"]'),'Survey Date & time General tab changed'))
    options=(('date','collect-date'),('time','collect-time'),('date_time','collect-date-time'))
    target=profile.get('collection_mode')
    if target not in dict(options):raise Stop('Survey Date & time collection mode is not captured')
    for mode,button_id in options:
        button=_one(panel.locator('#'+button_id),'Survey Date & time Collect mode changed')
        selected='dt-segmented-button--active' in (button.get_attribute('class') or '').split()
        if (mode==target)!=selected and mode==target:
            if not button.is_enabled():raise Stop('Survey Date & time requested Collect mode is disabled')
            click(button)
            wait_until(lambda:'dt-segmented-button--active' in (button.get_attribute('class') or '').split(),
                       'Survey Date & time Collect mode did not settle')
    click(_one(panel.locator('[data-name="settings"]'),'Survey Date & time Field settings tab changed'))


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


def _url_options(frame, *, profile=None):
    profile=PROFILES['url'] if profile is None else profile
    panel=_one(frame.locator(profile.get('sidebar','#form_custom_sidebar')),'Native URL sidebar changed')
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


def _write_url_options(frame,before,desired, *, profile=None):
    profile=PROFILES['url'] if profile is None else profile
    current=_url_options(frame,profile=profile)
    if current!={key:before[key] for key in ('domain_mode','domains')}:
        raise Stop('Native URL domain settings changed after preflight')
    panel=frame.locator(profile.get('sidebar','#form_custom_sidebar'))
    if current['domain_mode']!=desired['domain_mode']:
        owner=_one(panel.locator('label[data-testid="url-mode-'+desired['domain_mode']+'"]'),
                   'Native URL requested mode owner changed')
        click(owner)
        wait_until(lambda:_url_options(frame,profile=profile)['domain_mode']==desired['domain_mode'],
                   'Native URL domain mode did not settle')
    if desired['domain_mode']=='allow_all':return
    current=_url_options(frame,profile=profile)
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
        if _url_options(frame,profile=profile)['domains']!=desired['domains'][:index+1]:
            raise Stop('Native URL domain append changed the ordered chip inventory')


def _upload_options(frame, *, sidebar='#form_custom_sidebar'):
    panel=_one(frame.locator(sidebar),'Native File Upload sidebar changed')
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


def _checkbox_options(frame, *, profile=None):
    profile=PROFILES['checkbox'] if profile is None else profile
    panel=_one(frame.locator(profile.get('sidebar','#form_custom_sidebar')),'Native Checkbox sidebar changed')
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


def _write_checkbox_options(frame,before,desired, *, profile=None):
    profile=PROFILES['checkbox'] if profile is None else profile
    _checkbox_options(frame,profile=profile);panel=frame.locator(profile.get('sidebar','#form_custom_sidebar'))
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
        single_dropdown.remove_option(frame,remove,labels,count)
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


def read_text_heading(item):
    label=item.locator('[data-field-type="h1"]')
    if label.count()!=1 or item.locator('[data-field-type]').count()!=1:
        raise Stop('Text heading owner changed')
    editor=_one(item.locator('.tiptap.ProseMirror[contenteditable="true"]'),'Text heading editor changed')
    heading=_one(editor.locator(':scope > h1'),'Text heading markup changed')
    if editor.locator(':scope > *').count()!=1 or heading.locator('*').count()!=0:
        raise Stop('Text heading contains uncaptured markup')
    if (heading.get_attribute('style') or '').replace(' ','')!='padding-left:0px!important;':
        raise Stop('Text heading style differs from captured default')
    return heading.inner_text()


def picture_options(item):
    cards=item.locator('[data-testid="picture-choice-card"]')
    if item.locator('[data-testid="picture-choice-grid"]').count()!=1 or not 2<=cards.count()<=50:
        raise Stop('Native Picture Choice grid changed')
    result=[];owner=None
    for index in range(cards.count()):
        card=cards.nth(index);radio=_one(card.locator('input[type="radio"]'),'Picture Choice radio changed')
        name=radio.get_attribute('name');ident=radio.get_attribute('id')
        if not name or owner is not None and owner!=name or ident!=name+'-'+str(index) or radio.is_enabled():
            raise Stop('Picture Choice card ownership changed')
        owner=name;label=_one(card.locator('[data-testid="picture-choice-option-label-text"]'),'Picture Choice label changed')
        text=label.inner_text().strip()
        if label.get_attribute('id')!=ident+'-label' or radio.get_attribute('aria-label')!=text:
            raise Stop('Picture Choice label and radio identity disagree')
        image=_one(card.locator('[data-testid="picture-choice-option-media"] img'),'Picture Choice image changed')
        src=image.get_attribute('src');alt=image.get_attribute('alt') or ''
        if image.get_attribute('data-testid')=='picture-choice-empty-image':
            if src!='/assets/picture-choice-empty-42ddee2e.svg':raise Stop('Picture Choice blank image changed')
            src=None;alt=''
        else:
            from playwright_recipes.quiz_picture_questions import _https
            _https(src)
        result.append({'label':text,'image_url':src,'alt':alt})
    return result


def write_picture_options(item,before,desired):
    if len(before)!=len(desired) or any((a['image_url'],a['alt'])!=(b['image_url'],b['alt']) for a,b in zip(before,desired)):
        raise Stop('Existing Picture Choice currently preserves option count, catalog images and alt text')
    from playwright_recipes.quiz_choice_questions import _option_transition
    _option_transition([x['label'] for x in desired],[x['label'] for x in before])
    current=deepcopy(before)
    for index,option in enumerate(desired):
        if current[index]['label']==option['label']:continue
        label=_one(item.locator('[data-testid="picture-choice-card"]').nth(index).locator(
            '[data-testid="picture-choice-option-label-text"]'),'Picture Choice option label changed')
        fill(label,option['label']);label.press('Tab');current[index]['label']=option['label']
        wait_until(lambda:picture_options(item)==current,'Picture Choice label did not settle or changed media')


def select_picture_media(page,item,index,option):
    before=picture_options(item);card=item.locator('[data-testid="picture-choice-card"]').nth(index)
    media=_one(card.locator('[data-testid="picture-choice-option-media"]'),'Picture Choice media owner changed')
    if before[index]['image_url'] is None:
        control=media
    else:
        control=_one(media.locator('button[data-testid="picture-choice-change-image-'+str(index)+'"][aria-label="Change Image"]'),
                     'Picture Choice indexed Change Image changed')
        media.hover()
    click(control);dialog=page.get_by_role('dialog');dialog.wait_for(state='visible',timeout=45000)
    _one(dialog,'Picture Choice Media Storage dialog changed')
    _one(dialog.get_by_text('Media Storage',exact=True),'Picture Choice Media Storage title changed')
    tile=_one(dialog.get_by_role('button',name=option['media_button_name'],exact=True),'Approved Picture Choice catalog tile changed')
    thumbnail='https://images.leadconnectorhq.com/image/f_webp/q_80/r_320/u_'+option['image_url']
    _one(tile.locator('img[src='+json.dumps(thumbnail)+']'),'Approved Picture Choice thumbnail changed')
    tile.dblclick();dialog.wait_for(state='hidden',timeout=45000)
    expected=deepcopy(before);expected[index]={k:option[k] for k in ('label','image_url','alt')}
    wait_until(lambda:picture_options(item)==expected,'Picture Choice catalog image or independent alt did not settle')


def _read(frame, item, kind, *, profile=None):
    if kind=='text_heading':return _properties(kind,{'text':read_text_heading(item)},profile=profile)
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
    for key,selector in profile.get('preview_properties',{}).items():
        result[key]=_one(item.locator(selector),'Native widget preview label changed').input_value()
    if kind=='text_box_list':result.update(single_dropdown.read_options(frame,sidebar=profile.get('sidebar','#form_custom_sidebar'),prefill=True))
    if kind=='image':
        panel=frame.locator(profile.get('sidebar','#form_custom_sidebar'))
        dimensions=panel.locator('#text-input input')
        if dimensions.count()!=2 or any(dimensions.nth(i).input_value() for i in range(2)):
            raise Stop('Image dimensions differ from the captured blank profile')
        images=item.locator('img')
        if result['image_url']:
            image=_one(images,'Native image preview changed')
            if image.get_attribute('src')!=result['image_url'] or image.get_attribute('alt')!=result['alt_text']:
                raise Stop('Image preview URL or alt differs from its editor')
        elif images.count():raise Stop('Empty Image unexpectedly has a preview')
    if kind=='picture_choice':result['options']=picture_options(item)
    if kind=='html':result['html']=html_fields.read_html(frame)
    if kind=='bot_protection':
        selected=_one(frame.locator(profile.get('sidebar','#form_custom_sidebar')).locator(
            '[id^="captcha-verification-mode-"] .n-base-selection-input'),
            'Native Bot protection verification mode changed')
        if selected.get_attribute('title')!='Interactive':
            raise Stop('Native Bot protection mode is outside the captured Interactive profile')
        result['verification_mode']='interactive'
    if kind in ('date','date_time','time') and profile.get('datetime_options',True):
        result.update(datetime_fields.read_options(frame,sidebar=profile.get('sidebar','#form_custom_sidebar'),kind=kind))
    if profile.get('collection_mode'):
        panel=frame.locator(profile.get('sidebar','#form_custom_sidebar'))
        click(_one(panel.locator('[data-name="general"]'),'Survey Date & time General tab changed'))
        selected=[]
        for mode,button_id in (('date','collect-date'),('time','collect-time'),('date_time','collect-date-time')):
            node=_one(panel.locator('#'+button_id),'Survey Date & time Collect mode changed')
            if 'dt-segmented-button--active' in (node.get_attribute('class') or '').split():selected.append(mode)
        if selected!=[profile['collection_mode']]:raise Stop('Survey Date & time saved Collect mode differs from its typed family')
        result['collection_mode']=selected[0]
        click(_one(panel.locator('[data-name="settings"]'),'Survey Date & time Field settings tab changed'))
    if kind=='url':result.update(_url_options(frame,profile=profile))
    if kind=='file_upload':result.update(_upload_options(frame,sidebar=profile.get('sidebar','#form_custom_sidebar')))
    if kind=='checkbox':result.update(_checkbox_options(frame,profile=profile))
    if kind in ('single_dropdown','multi_dropdown'):result.update(single_dropdown.read_options(frame,sidebar=profile.get('sidebar','#form_custom_sidebar')))
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
        if kind=='picture_choice' and item.locator('[data-testid="picture-choice-grid"]').count()!=1:kind=None
        if kind=='text_heading' and item.locator('.tiptap.ProseMirror[contenteditable="true"]').count()!=1:kind=None
        if kind:
            records.append({'kind':kind, 'index':index + 1, 'properties':_read(frame, item, kind)})
    keys = [_identity(record['kind'],record['properties']) for record in records]
    if len(keys) != len(set(keys)):
        raise Stop('Native form widget Query Keys are duplicated')
    return records


def _write(frame, item, kind, before, desired, *, profile=None):
    if kind=='text_heading':
        if read_text_heading(item)!=before['text']:raise Stop('Text heading changed after preflight')
        editor=_one(item.locator('.tiptap.ProseMirror[contenteditable="true"]'),'Text heading editor changed')
        click(editor);editor.press('ControlOrMeta+A');editor.press_sequentially(desired['text'])
        wait_until(lambda:read_text_heading(item)==desired['text'],'Text heading did not settle')
        return
    if _read(frame, item, kind, profile=profile) != before:
        raise Stop('Native form widget changed after complete preflight')
    profile = _activate(frame, item, kind, profile=profile)
    if kind in ('date','date_time','time') and profile.get('datetime_options',True):
        datetime_fields.write_options(frame,before,desired,sidebar=profile.get('sidebar','#form_custom_sidebar'),kind=kind)
        # Format changes can alter the default placeholder. Author requested
        # General values last, then read the complete final profile once.
        _activate(frame,item,kind,profile=profile)
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
        _upload_options(frame,sidebar=profile.get('sidebar','#form_custom_sidebar'))
        panel=frame.locator(profile.get('sidebar','#form_custom_sidebar'))
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
    if kind=='picture_choice':write_picture_options(item,before['options'],desired['options'])
    if kind=='html':html_fields.write_html(frame,before['html'],desired['html'])
    for key,selector in profile.get('preview_properties',{}).items():
        node=_one(item.locator(selector),'Native widget preview label control changed')
        if node.input_value()!=desired[key]:fill(node,desired[key]);node.press('Tab')
    if kind=='text_box_list':single_dropdown.write_options(frame,before,desired,sidebar=profile.get('sidebar','#form_custom_sidebar'),prefill=True)
    if kind=='url':_write_url_options(frame,before,desired,profile=profile)
    if kind=='checkbox':_write_checkbox_options(frame,before,desired,profile=profile)
    if kind in ('single_dropdown','multi_dropdown'):single_dropdown.write_options(frame,before,desired,sidebar=profile.get('sidebar','#form_custom_sidebar'))
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
    if profile.get('creation_mode'):
        added=[i for i in range(len(after)) if after[:i]+after[i+1:]==before_snapshot]
        if len(added)!=1:raise Stop('Native Date & time insertion changed another field')
        item=frame.locator(CANVAS_ITEMS).nth(added[0]);label=_one(item.locator('[data-field-type]'),'Date & time owner changed')
        click(label);click(_one(item.locator('[aria-label="Open settings"]'),'Date & time settings changed'))
        panel=_one(frame.locator('#form_custom_sidebar'),'Date & time sidebar changed')
        click(_one(panel.get_by_text('Content',exact=True),'Date & time Content changed'))
        click(_one(panel.locator('[data-name="general"]'),'Date & time General tab changed'))
        button=_one(panel.locator('#collect-'+profile['creation_mode'].replace('_','-')),'Date & time Collect mode changed')
        if 'dt-segmented-button--active' not in (button.get_attribute('class') or '').split():
            click(button)
            wait_until(lambda:'dt-segmented-button--active' in (button.get_attribute('class') or '').split(),'Date & time Collect mode did not settle')
        _close_properties(frame);after=_snapshot(frame)
    candidates = [index for index, row in enumerate(after)
                  if row['types'] == [profile['type']] and after[:index] + after[index + 1:] == before_snapshot]
    if len(candidates) != 1:
        raise Stop('Native form widget insertion changed another field or has ambiguous ownership')
    index = candidates[0]; item = frame.locator(CANVAS_ITEMS).nth(index)
    defaults = _read(frame, item, kind)
    if kind=='text_heading':
        if defaults!={'text':'Text'}:raise Stop('New Text heading differs from captured default')
        return index,item,defaults
    if profile.get('generated_label_pattern'):
        if (not re.fullmatch(profile['generated_label_pattern'],defaults['label'])
                or item.locator('[data-field-type]').inner_text().strip()!=defaults['label']
                or any(defaults[key]!=value for key,value in profile['defaults'].items())):
            raise Stop('New native widget differs from its captured generated label/defaults')
        return index,item,defaults
    if profile.get('fixed_identity'):
        if (item.locator('[data-field-type]').inner_text().strip()!=profile['tile']
                or defaults!=profile['defaults']):
            raise Stop('New native singleton widget differs from its captured label/defaults')
        return index,item,defaults
    suffix = re.fullmatch(re.escape(profile.get('generated_prefix',profile['tile'])) + r' ([a-z0-9]{' + str(profile['suffix']) + '})', defaults['label'])
    if (not suffix or not _default_key(profile,defaults[_key(kind)],suffix.group(1))
            or any(defaults[key] != value for key, value in profile['defaults'].items())):
        raise Stop('New native form widget differs from its captured generated identity/defaults')
    if 'unique_key' in profile['properties'] and (defaults['custom_field_name']!=defaults['label']
            or not defaults['unique_key'].startswith('contact.'+profile.get('unique_key_prefix',profile['key_prefix']))
            or defaults['unique_key'][len('contact.'+profile.get('unique_key_prefix',profile['key_prefix'])):].replace('_','')!=suffix.group(1)):
        raise Stop('New native form widget Custom Field Name differs from its generated label')
    return index, item, defaults


def _default_key(profile,key,suffix):
    if profile.get('key_property')=='unique_key':
        return bool(re.fullmatch(r'contact\.'+re.escape(profile['key_prefix'])+r'[a-z0-9_]+',key))
    return key==profile['key_prefix']+suffix


def _picture_readback(value):
    result=deepcopy(value)
    result['options']=[{k:v for k,v in x.items() if k!='media_button_name'} for x in result['options']]
    return result


def _desired_records(plan):
    result = {_identity(record['kind'],record['properties']):{'kind':record['kind'], 'properties':record['properties']}
              for record in plan['expected_fields']}
    for field in plan['fields']:
        if field['index'] is not None:
            previous=next(record for record in plan['expected_fields'] if record['index']==field['index'])
            result.pop(_identity(previous['kind'],previous['properties']))
        result[_identity(field['kind'],field['desired'])] = {'kind':field['kind'], 'properties':_picture_readback(field['desired']) if field['kind']=='picture_choice' else field['desired']}
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
        properties = _properties(field['kind'], field['properties']); query = _identity(field['kind'],properties)
        if query in actual:
            raise Stop('Native form widget completion has duplicate Query Keys')
        row = value['saved_snapshot'][field['index'] - 1]
        if not isinstance(row, dict) or row.get('types') != [PROFILES[field['kind']]['type']]:
            raise Stop('Native form widget completion does not match its typed canvas')
        actual[query] = {'kind':field['kind'], 'properties':properties}; positions.add(field['index'])
    if actual != expected:
        raise Stop('Native form widget completion differs from the complete requested inventory')
    edits={field['index']:field for field in plan['fields'] if field['index'] is not None}
    original_order = [(_identity(record['kind'],edits[record['index']]['desired']) if record['index'] in edits else _identity(record['kind'],record['properties']))
                      for record in sorted(plan['expected_fields'], key=lambda x:x['index'])]
    old = set(original_order)
    saved_order = [_identity(record['kind'],record['properties']) for record in sorted(value['fields'], key=lambda x:x['index'])
                   if _identity(record['kind'],record['properties']) in old]
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
        if PROFILES[field['kind']].get('contact_field') is False or PROFILES[field['kind']].get('queryless'):continue
        own=(next(_identity(record['kind'],record['properties']) for record in before if record['index']==field['index'])
             if field['index'] is not None else None)
        if _identity(field['kind'],field['desired']) in queries and _identity(field['kind'],field['desired'])!=own:
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
        desired=field['desired']
        if field['kind']=='picture_choice':
            staged=_picture_readback(desired)
            for old,new in zip(previous['options'],staged['options']):
                new['image_url']=old['image_url'];new['alt']=old['alt']
            _write(frame,item,field['kind'],previous,staged)
            for i,option in enumerate(desired['options']):
                if previous['options'][i]['image_url']!=option['image_url']:
                    select_picture_media(page,item,i,option)
        else:_write(frame, item, field['kind'], previous, desired)
        desired_snapshot = _snapshot(frame)
        expected_without = inserted[:index] + inserted[index + 1:]
        actual_without = desired_snapshot[:index] + desired_snapshot[index + 1:]
        if len(desired_snapshot) != len(inserted) or actual_without != expected_without:
            raise Stop('Native form widget editing changed an unrelated sibling')
    fields = _inventory(frame)
    if {_identity(record['kind'],record['properties']):{'kind':record['kind'], 'properties':record['properties']} for record in fields} != _desired_records(plan):
        raise Stop('Native form widget final properties differ from the requested complete inventory')
    if _snapshot(frame) != desired_snapshot:
        raise Stop('Native form widget final inventory changed while reading properties')
    wanted_queries=dict(queries)
    for field in plan['fields']:
        if PROFILES[field['kind']].get('contact_field') is False or PROFILES[field['kind']].get('queryless'):continue
        if field['index'] is not None:
            old=next(record for record in before if record['index']==field['index'])
            wanted_queries.pop(_identity(old['kind'],old['properties']))
        wanted_queries[_identity(field['kind'],field['desired'])]=PROFILES[field['kind']]['type']
    if query_inventory(frame,allow_unknown_queries=True)!=wanted_queries:
        raise Stop('Native form widget editing changed another field Query Key')
    _frame(page, plan)
    save = _one(frame.get_by_role('button', name='Save', exact=True), 'Native form widget Save changed')
    click(save)
    html_fields.confirm_save_warning(frame)
    from playwright_recipes.form_conditions import _wait_for_form_save
    _wait_for_form_save(page,save)
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
