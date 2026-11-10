"""Captured inactive course-theme Custom Block append, editing and deletion.

Body block IDs, editor inputs, native radio labels and preview bindings were
captured November 9, 2026. The handler edits plain authored text/HTTPS links;
an exclusive explicit deletion delegates to its captured confirmation handler.
It never activates a template, publishes a course or uploads media.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

if __package__:
    from . import course_theme as theme
    from .skill6_playwright import Stop, assert_tenant, click, fill, wait_until
else:
    import course_theme as theme
    from skill6_playwright import Stop, assert_tenant, click, fill, wait_until


COMMON = theme.COMMON | {'course_id', 'template_id', 'expected_template_title'}
FIELDS = frozenset(('heading', 'content', 'button_text', 'button_url',
                    'button_visibility', 'button_type', 'button_alignment'))
RADIOS = {'button_visibility':('visibility', ('show','hide')),
          'button_type':('button-type', ('solid','link')),
          'button_alignment':('button-alignment', ('left','center','right'))}
_LIMITS = {'heading':2500, 'content':50000, 'button_text':300, 'button_url':1000}


def _text(value, key):
    if (not isinstance(value, str) or len(value) > _LIMITS[key]
            or any(ord(char) < 32 and char not in '\n\r\t' for char in value)):
        raise Stop('Custom Block requires explicit plain text within native limits')
    value = value.replace('\r\n','\n').replace('\r','\n').strip()
    if key in ('heading','button_text') and not value:
        raise Stop('Custom Block heading and button text must be authored')
    if key == 'button_url' and value:
        try:
            parsed=urlsplit(value);port=parsed.port
        except ValueError:
            raise Stop('Custom Block button URL is malformed') from None
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or port not in (None,443)
                or any(char.isspace() for char in value)):
            raise Stop('Custom Block button URL must be credential-free HTTPS')
    return value


def _values(value, *, complete):
    if (not isinstance(value, dict) or not value or set(value)-FIELDS
            or complete and set(value)!=FIELDS):
        raise Stop('Custom Block values must use the exact captured fields')
    result={}
    for key,item in value.items():
        if key in RADIOS:
            if not isinstance(item,str) or item not in RADIOS[key][1]:
                raise Stop('Custom Block radio choice was not captured')
            result[key]=item
        else:
            result[key]=_text(item,key)
    return result


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)-COMMON-{'custom_blocks'}:
        raise Stop('Unsupported inactive theme Custom Block input')
    plan=deepcopy(inputs)
    # Reuse exact course/template manager identity and inactive-theme contract.
    base={key:value for key,value in plan.items() if key in COMMON}
    theme.validate_inputs({**base, 'expected_values':{'template_title':plan.get('expected_template_title')},
        'changes':{'template_title':plan.get('expected_template_title')}})
    config=plan.get('custom_blocks')
    if (not isinstance(config,dict) or set(config)-{'expected_inventory','updates','append','deletion'}
            or not isinstance(config.get('expected_inventory'),list)):
        raise Stop('Custom Blocks require their complete inventoried native ID/type order')
    identities=[]
    for row in config['expected_inventory']:
        if (not isinstance(row,dict) or set(row)!={'id','type'}
                or row.get('type') not in ('Category Block','Custom Block','Text Block','Image Block','Video Block')):
            raise Stop('Only captured Category/Custom/Text/Image Block inventories are supported')
        theme._id(row.get('id'));identities.append(row['id'])
    if len(set(identities))!=len(identities) or identities.count('categoryBlock')!=1:
        raise Stop('Native block IDs must be unique with one captured Category Block')
    if any((row['id']=='categoryBlock') != (row['type']=='Category Block') for row in config['expected_inventory']):
        raise Stop('Category Block inventory identity differs from its captured type')
    if 'deletion' in config:
        deletion=config['deletion']
        if (set(config)!={'expected_inventory','deletion'} or not isinstance(deletion,dict)
                or set(deletion)!={'action','id','expected','expected_content_html','expected_media_url'}
                or deletion.get('action')!='delete' or not isinstance(deletion.get('id'),str)
                or {'id':deletion['id'],'type':'Custom Block'} not in config['expected_inventory']):
            raise Stop('Custom Block deletion requires an exclusive explicit delete action and existing Custom UUID')
        deletion['expected']=_values(deletion['expected'],complete=True)
        html=deletion['expected_content_html']
        if (not isinstance(html,str) or len(html)>200000
                or any(ord(char)<32 and char not in '\n\r\t' for char in html)):
            raise Stop('Custom Block deletion requires its exact inventoried rich HTML')
        if __package__:
            from .course_media import _url
        else:
            from course_media import _url
        _url(deletion['expected_media_url'])
        return plan
    updates=config.get('updates',[]);appends=config.get('append',[])
    if not isinstance(updates,list) or not isinstance(appends,list) or not (updates or appends):
        raise Stop('Custom Blocks require an authored update or append')
    seen=set()
    for update in updates:
        if (not isinstance(update,dict) or set(update)!={'id','expected','changes','plain_text_content'}
                or not isinstance(update.get('id'),str) or update['id'] in seen
                or not any(row=={'id':update['id'],'type':'Custom Block'} for row in config['expected_inventory'])
                or update['plain_text_content'] is not True):
            raise Stop('Existing Custom Block edits require exact ID and plain-text replacement acknowledgement')
        seen.add(update['id'])
        update['expected']=_values(update['expected'],complete=True)
        update['changes']=_values(update['changes'],complete=False)
    for index,value in enumerate(appends):
        appends[index]=_values(value,complete=True)
    config['updates'],config['append']=updates,appends
    return plan


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','native_course_blocks')!='native_course_blocks'):
        raise Stop('Unsupported Custom Block runner metadata')
    return validate_inputs(step.get('payload'))


def configuration_hash(inputs):
    plan=validate_inputs(inputs)
    bound={key:plan[key] for key in ('location_id','course_id','template_id','expected_template_title','custom_blocks')}
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _one(control,message):
    return theme._one(control,message)


def _inventory(page,plan):
    theme._panel(page,plan,'Body')
    return _visible_inventory(page)


def _visible_inventory(page):
    """Read the already-open Body without clicking behind a native dialog."""
    rows=page.locator('.sortable-item')
    result=[]
    for index in range(rows.count()):
        row=rows.nth(index);identity=theme._id(row.get_attribute('id'))
        title=_one(row.locator(':scope > div.w-full.hl-text-md-medium'),
            'Native course block type label changed').inner_text().strip()
        if title not in ('Category Block','Custom Block','Text Block','Image Block','Video Block'):
            raise Stop('Uncaptured native block type requires inventory before editing')
        result.append({'id':identity,'type':title})
    if (len({row['id'] for row in result})!=len(result)
            or sum(row=={'id':'categoryBlock','type':'Category Block'} for row in result)!=1):
        raise Stop('Native course block inventory is ambiguous')
    return result


def _input(page,maximum):
    return _one(page.locator('[placeholder="Type here"][maxlength="'+str(maximum)+'"]'),
        'Native Custom Block text input changed')


def _radios(page,key):
    name,values=RADIOS[key]
    inputs=page.locator('input[type="radio"][name="'+name+'"]')
    if inputs.count()!=len(values):
        raise Stop('Native Custom Block radio inventory changed')
    controls={}
    for value in values:
        control=page.locator('input[type="radio"][name="'+name+'"][value="'+value+'"]')
        if control.count()!=1:
            raise Stop('Native Custom Block radio identity is ambiguous')
        parent=control.locator('xpath:..')
        if (parent.count()!=1 or parent.evaluate('(element)=>element.tagName')!='LABEL'
                or 'n-radio' not in (parent.get_attribute('class') or '').split()):
            raise Stop('Native Custom Block radio label changed')
        controls[value]=(control,parent)
    selected=[value for value,(control,_) in controls.items() if control.is_checked()]
    if len(selected)!=1:
        raise Stop('Native Custom Block radio state is ambiguous')
    return selected[0],controls


def _open_block(page,plan,identity):
    inventory=_inventory(page,plan)
    if {'id':identity,'type':'Custom Block'} not in inventory:
        raise Stop('Custom Block ID does not identify an inventoried custom entry')
    row=_one(page.locator('.sortable-item[id="'+identity+'"]'),'Native Custom Block entry disappeared')
    click(row.locator(':scope > div.w-full.hl-text-md-medium'))
    wait_until(lambda:_selected(page,identity),
        'Native Custom Block inspector did not bind the exact selected preview UUID')
    _input(page,2500)
    _one(page.get_by_role('button',name='Delete Block',exact=True),'Native Custom Block inspector changed')
    return inventory


def _selected(page,identity):
    selected=page.locator('.custom-block[data-active="true"]')
    return (selected.count()==1 and selected.is_visible()
            and selected.get_attribute('id')=='custom-block-'+identity)


def _read_block(page,plan,identity):
    _open_block(page,plan,identity)
    return _read_selected_block(page,identity)


def _read_selected_block(page,identity):
    if not _selected(page,identity):raise Stop('Custom Block selected inspector changed UUID')
    content=_one(page.locator('div[contenteditable="true"].tiptap.ProseMirror.general-courses-editor'),
        'Native Custom Block Content editor changed')
    state={'heading':_text(_input(page,2500).input_value(),'heading'),
        'content':_text(content.inner_text(),'content'),
        'button_text':_text(_input(page,300).input_value(),'button_text'),
        'button_url':_text(_one(page.get_by_placeholder('Eg: https://abc.com',exact=True),
            'Native Custom Block Go to URL input changed').input_value(),'button_url')}
    state.update({key:_radios(page,key)[0] for key in RADIOS})
    preview=_one(page.locator('div.custom-block[id="custom-block-'+identity+'"]'),
        'Native Custom Block preview identity changed')
    buttons=preview.locator('[id="custom-block-btn-'+identity+'"]')
    if (preview.locator('.custom-block-heading').count()!=1
            or preview.locator('.editor-content.rich-text-viewer').count()!=1
            or buttons.count()>1 or state['button_visibility']=='show' and buttons.count()!=1):
        raise Stop('Native Custom Block preview anchors changed')
    if (_text(preview.locator('.custom-block-heading').inner_text(),'heading')!=state['heading']
            or _text(preview.locator('.editor-content.rich-text-viewer').inner_text(),'content')!=state['content']
            or state['button_visibility']=='show' and _text(buttons.inner_text(),'button_text')!=state['button_text']):
        raise Stop('Custom Block inspector does not match its exact UUID-bound preview')
    media=_one(preview.locator('img[alt="Image block '+identity+'"]'),
        'Native Custom Block preview image identity changed')
    return state,{'content_html':content.inner_html(),'media_src':media.get_attribute('src')}


def _snapshot(page,plan,inventory):
    result={}
    for row in inventory:
        if row['type']=='Custom Block':
            result[row['id']]=_read_block(page,plan,row['id'])
        elif row['type']=='Text Block':
            if __package__:
                from .course_text_blocks import read_text_block
            else:
                from course_text_blocks import read_text_block
            result[row['id']]=read_text_block(page,plan,row['id'])
        elif row['type']=='Video Block':
            if __package__:
                from .course_video_blocks import read_video_block
            else:
                from course_video_blocks import read_video_block
            result[row['id']]=read_video_block(page,plan,row['id'])
        elif row['type']=='Image Block':
            if __package__:
                from .course_image_blocks import read_image_block
            else:
                from course_image_blocks import read_image_block
            result[row['id']]=read_image_block(page,plan,row['id'])
    return result


def _write_block(page,plan,identity,changes):
    _open_block(page,plan,identity)
    fields={'heading':lambda:_input(page,2500), 'button_text':lambda:_input(page,300),
        'content':lambda:_one(page.locator('div[contenteditable="true"].tiptap.ProseMirror.general-courses-editor'),
            'Native Custom Block Content editor changed'),
        'button_url':lambda:_one(page.get_by_placeholder('Eg: https://abc.com',exact=True),
            'Native Custom Block Go to URL input changed')}
    for key,value in changes.items():
        theme._identity(page,plan)
        if not _selected(page,identity):
            raise Stop('Custom Block inspector changed its selected native UUID before editing')
        if key in RADIOS:
            current,controls=_radios(page,key)
            if current!=value:click(controls[value][1])
        else:
            control=fields[key]();fill(control,value);control.press('Tab')
    actual,protected=_read_block(page,plan,identity)
    if any(actual[key]!=value for key,value in changes.items()):
        raise Stop('Native Custom Block ignored an authored value')
    return actual,protected


def configure(page,step):
    plan=validate(step);config=plan['custom_blocks']
    if 'deletion' in config:
        if __package__:
            from .course_block_delete import configure as delete
        else:
            from course_block_delete import configure as delete
        return delete(page,step)
    before_active=theme._open(page,plan,plan['expected_template_title'])
    protected_theme=theme._snapshot(page,plan)
    inventory=_inventory(page,plan)
    if inventory!=config['expected_inventory']:
        raise Stop('Native Custom Block ID/type/order inventory is stale')
    before=_snapshot(page,plan,inventory)
    for update in config['updates']:
        if before[update['id']][0]!=update['expected']:
            raise Stop('Existing Custom Block differs from its expected previous values')
    desired=deepcopy(before);wanted_inventory=deepcopy(inventory)
    # All existing block IDs and values have been checked before the first write.
    for update in config['updates']:
        identity=update['id']
        if _read_block(page,plan,identity)!=before[identity]:
            raise Stop('Native Custom Block changed after preflight')
        expected={**before[identity][0],**update['changes']}
        actual,protected=_write_block(page,plan,identity,update['changes'])
        if actual!=expected or protected['media_src']!=before[identity][1]['media_src']:
            raise Stop('Custom Block edit changed unrequested fields or media')
        if 'content' not in update['changes'] and protected['content_html']!=before[identity][1]['content_html']:
            raise Stop('Custom Block edit changed protected rich content')
        desired[identity]=(actual,protected)
    added=[]
    for authored in config['append']:
        if _inventory(page,plan)!=wanted_inventory:
            raise Stop('Native block inventory changed before append')
        click(_one(page.get_by_role('button',name='Add Block',exact=True),'Native Add Block control changed'))
        click(_one(page.get_by_role('button',name='Custom Block',exact=True),'Native Custom Block add option changed'))
        after=_inventory(page,plan)
        if (len(after)!=len(wanted_inventory)+1 or after[:-1]!=wanted_inventory
                or after[-1]['type']!='Custom Block' or after[-1]['id'] in {row['id'] for row in wanted_inventory}):
            raise Stop('Native Custom Block append did not preserve the exact sibling ID/type order')
        identity=after[-1]['id'];added.append(identity)
        _,new_protected=_read_block(page,plan,identity)
        desired[identity]=_write_block(page,plan,identity,authored)
        if desired[identity][1]['media_src']!=new_protected['media_src']:
            raise Stop('Custom Block text/button authoring changed its default media')
        wanted_inventory=after
    if (_inventory(page,plan)!=wanted_inventory or _snapshot(page,plan,wanted_inventory)!=desired
            or theme._snapshot(page,plan)!=protected_theme):
        raise Stop('Native Custom Block desired state or protected theme changed before Save')
    theme._identity(page,plan);assert_tenant(page,plan)
    save=_one(page.get_by_role('button',name='Save',exact=True),'Native template Save changed')
    if desired!=before:
        if not save.is_enabled():
            raise Stop('Custom Block edits did not enable native Save')
        click(save)
        wait_until(lambda:not save.is_enabled(),'Native Custom Block Save did not settle')
        try:page.wait_for_load_state('networkidle',timeout=45000)
        except Exception:raise Stop('Custom Block Save remains unsettled; reconcile before another write') from None
    elif save.is_enabled():
        raise Stop('Unrelated unsaved theme changes require reconciliation before Save')
    after_active=theme._open(page,plan,plan['expected_template_title'])
    if (after_active!=before_active or _inventory(page,plan)!=wanted_inventory
            or _snapshot(page,plan,wanted_inventory)!=desired
            or theme._snapshot(page,plan)!=protected_theme):
        raise Stop('Custom Block independent reopen failed or protected theme changed')
    return {'status':'COURSE_BLOCKS_SAVED_AND_REOPENED','editor_url':page.url,
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'added_block_ids':added,'block_ids':[row['id'] for row in wanted_inventory],
        'functional_verified':False,'activation_performed':False}
