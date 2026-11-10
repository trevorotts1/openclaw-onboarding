"""Captured plain Text Blocks on an existing inactive course template.

Native Text previews have no UUID. Bind the exact sidebar UUID through the
complete sidebar-type/direct-preview-wrapper order and a unique active block.
Never infer identity from identical content or from the first active preview.
"""
from copy import deepcopy
import hashlib
import json

if __package__:
    from . import course_blocks as blocks, course_theme as theme
    from .skill6_playwright import Stop, assert_tenant, click, fill, wait_until
else:
    import course_blocks as blocks
    import course_theme as theme
    from skill6_playwright import Stop, assert_tenant, click, fill, wait_until


COMMON=blocks.COMMON
TYPES=('Category Block','Custom Block','Text Block','Image Block','Video Block')
EDITOR='div[contenteditable="true"].tiptap.ProseMirror.general-courses-editor'
PREVIEW_OWNER='#content-container > div.col-span-9.flex.flex-col.gap-4'
AUTHORED_PREVIEWS='#content-container, .welcome-hero-image, .instructor-card'


def _inspector_caption(page,caption):
    """Require the captured native caption outside measured authored regions.

    Exact text alone is ambiguous when a legitimate Content/course title is
    the same caption. Exclude the captured RTE and preview owners (including
    an ancestor that only matches because it contains authored content),
    without guessing a heading class or accepting an absent native caption.
    """
    matches=page.get_by_text(caption,exact=True);native=[]
    for index in range(matches.count()):
        candidate=matches.nth(index)
        if not candidate.is_visible():continue
        if candidate.evaluate('''(element, owners) => !owners.some(selector =>
            element.closest(selector) || element.querySelector(selector))''',
                [EDITOR,AUTHORED_PREVIEWS]):
            native.append(candidate)
    if len(native)!=1:
        raise Stop('Native '+caption+' inspector heading changed or is ambiguous outside captured authored regions')
    return native[0]


def _content(value):
    if (not isinstance(value,str) or len(value)>2500
            or any(ord(char)<32 and char not in '\n\r\t' for char in value)):
        raise Stop('Text Block content requires explicit plain text within the captured 2500-character limit')
    return value.replace('\r\n','\n').replace('\r','\n').strip()


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)-COMMON-{'text_blocks'}:
        raise Stop('Unsupported inactive-template Text Block input')
    plan=deepcopy(inputs);base={key:value for key,value in plan.items() if key in COMMON}
    theme.validate_inputs({**base,'expected_values':{'template_title':plan.get('expected_template_title')},
        'changes':{'template_title':plan.get('expected_template_title')}})
    config=plan.get('text_blocks')
    if (not isinstance(config,dict) or set(config)-{'expected_inventory','updates','append'}
            or not isinstance(config.get('expected_inventory'),list)):
        raise Stop('Text Blocks require the complete exact native ID/type/order inventory')
    inventory=config['expected_inventory'];ids=[]
    for row in inventory:
        if not isinstance(row,dict) or set(row)!={'id','type'} or row['type'] not in TYPES:
            raise Stop('Text Blocks support captured Category/Custom/Text/Image sibling types only')
        theme._id(row['id']);ids.append(row['id'])
        if (row['id']=='categoryBlock') != (row['type']=='Category Block'):
            raise Stop('Text Block Category sibling identity is malformed')
    if len(set(ids))!=len(ids) or ids.count('categoryBlock')!=1:
        raise Stop('Text Block inventory needs unique IDs and one exact categoryBlock')
    updates=config.get('updates',[]);appends=config.get('append',[])
    if not isinstance(updates,list) or not isinstance(appends,list) or not (updates or appends):
        raise Stop('Text Blocks require an authored update or append')
    seen=set()
    for update in updates:
        if (not isinstance(update,dict) or set(update)!={'id','expected_content','content','plain_text_content'}
                or not isinstance(update.get('id'),str) or update['id'] in seen
                or {'id':update['id'],'type':'Text Block'} not in inventory
                or update['plain_text_content'] is not True):
            raise Stop('Text Block edits need one exact existing Text UUID and plain-text replacement acknowledgement')
        seen.add(update['id'])
        update['expected_content']=_content(update['expected_content']);update['content']=_content(update['content'])
    for value in appends:
        if not isinstance(value,dict) or set(value)!={'content'}:
            raise Stop('Text Block appends require authored content only')
        value['content']=_content(value['content'])
    config['updates'],config['append']=updates,appends
    return plan


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action','native_course_text_blocks')!='native_course_text_blocks'):
        raise Stop('Unsupported native Text Block runner metadata')
    return validate_inputs(step.get('payload'))


def configuration_hash(inputs):
    plan=validate_inputs(inputs)
    bound={key:plan[key] for key in ('location_id','course_id','template_id','expected_template_title','text_blocks')}
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_receipt(value,step):
    plan=validate(step);config=plan['text_blocks']
    keys={'status','editor_url','course_id','template_id','configuration_sha256','independent_readback',
        'added_block_ids','block_ids','block_count','functional_verified','activation_performed'}
    if not isinstance(value,dict) or set(value)!=keys:
        raise Stop('Native Text Block outcome is incomplete or contains unbound proof')
    before=[row['id'] for row in config['expected_inventory']]
    ids=value['block_ids'];added=value['added_block_ids'];count=len(before)+len(config['append'])
    if (not isinstance(ids,list) or not isinstance(added,list) or len(ids)!=count
            or any(not isinstance(identity,str) for identity in ids)
            or len(set(ids))!=len(ids) or ids[:len(before)]!=before
            or added!=ids[len(before):] or len(added)!=len(config['append'])
            or type(value['block_count']) is not int or value['block_count']!=count):
        raise Stop('Native Text Block outcome IDs/count differ from the exact append/order plan')
    for identity in ids:theme._id(identity)
    expected={'status':'COURSE_TEXT_BLOCKS_SAVED_AND_REOPENED','editor_url':theme.editor_url(plan),
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'functional_verified':False,'activation_performed':False}
    if (any(value[key]!=wanted for key,wanted in expected.items())
            or value['functional_verified'] is not False or value['activation_performed'] is not False):
        raise Stop('Native Text Block proof differs from its exact inactive template/inputs')
    return deepcopy(value)


def _preview_order(page,inventory):
    owner=theme._one(page.locator(PREVIEW_OWNER),'Native course Body preview owner changed')
    wrappers=owner.locator(':scope > div')
    if wrappers.count()!=len(inventory):
        raise Stop('Native Body preview wrapper count differs from its complete sidebar inventory')
    result=[]
    for index,row in enumerate(inventory):
        block=theme._one(wrappers.nth(index).locator(':scope > div'),'Native Body preview wrapper is not one exact block')
        classes=(block.get_attribute('class') or '').split()
        if (block.get_attribute('data-active') not in ('true','false')
                or row['type'] in ('Category Block','Text Block') and block.get_attribute('inbody')!='true'):
            raise Stop('Native Body preview block ownership/selection state changed')
        if row['type']=='Text Block':
            valid='text-block' in classes and block.locator('.editor-content.rich-text-viewer').count()==1
        elif row['type']=='Custom Block':
            valid='custom-block' in classes and block.get_attribute('id')=='custom-block-'+row['id']
        elif row['type']=='Video Block':
            valid=(block.locator('video').count()==1 and 'text-block' not in classes
                and 'custom-block' not in classes and block.locator('.category-list-block').count()==0)
        elif row['type']=='Image Block':
            valid=(block.locator('img[alt="Image block '+row['id']+'"]').count()==1
                and 'text-block' not in classes and 'custom-block' not in classes)
        else:
            valid=('text-block' not in classes and 'custom-block' not in classes
                and block.locator('.category-list-block').count()>0)
        if not valid:
            raise Stop('Native Body preview type/order differs from the exact sidebar UUID inventory')
        result.append(block)
    return result


def _selected_preview(page,inventory,identity,kind='Text Block'):
    previews=_preview_order(page,inventory)
    target=next((index for index,row in enumerate(inventory)
        if row=={'id':identity,'type':kind}),None)
    if target is None:raise Stop('Requested Block UUID/type is absent from its complete sidebar inventory')
    active=[index for index,preview in enumerate(previews) if preview.get_attribute('data-active')=='true']
    if active!=[target]:raise Stop('Native Text Block selection does not bind its exact sidebar UUID/order')
    return previews[target]


def _open(page,plan,identity):
    inventory=blocks._inventory(page,plan)
    if {'id':identity,'type':'Text Block'} not in inventory:
        raise Stop('Requested Text Block UUID is absent or belongs to another block type')
    _preview_order(page,inventory)
    row=theme._one(page.locator('.sortable-item[id="'+identity+'"]'),'Native Text Block sidebar UUID changed')
    click(row.locator(':scope > div.w-full.hl-text-md-medium'))
    wait_until(lambda:_selected_preview(page,inventory,identity).is_visible(),
        'Native Text Block selection did not bind its exact preview order')
    _inspector_caption(page,'Text Block')
    delete=theme._one(page.locator('#delete-block-btn'),'Native Text Block inspector Delete control changed')
    if delete.inner_text().strip()!='Delete Block':raise Stop('Native Text Block inspector identity changed')
    return inventory,_selected_preview(page,inventory,identity)


def read_text_block(page,plan,identity):
    inventory,preview=_open(page,plan,identity)
    editor=theme._one(page.locator(EDITOR),'Native Text Block Content editor changed')
    rendered=theme._one(preview.locator('.editor-content.rich-text-viewer'),'Native Text Block rich-text preview changed')
    content=_content(editor.inner_text())
    if _content(rendered.inner_text())!=content:
        raise Stop('Native Text Block inspector differs from its exact order-bound preview')
    return {'content':content},{'content_html':editor.inner_html(),'preview_style':preview.get_attribute('style')}


def _write(page,plan,identity,content):
    inventory,preview=_open(page,plan,identity)
    before_style=preview.get_attribute('style')
    theme._identity(page,plan);assert_tenant(page,plan)
    _selected_preview(page,inventory,identity)
    editor=theme._one(page.locator(EDITOR),'Native Text Block Content editor changed')
    fill(editor,content);editor.press('Tab')
    result=read_text_block(page,plan,identity)
    if result[0]['content']!=content or result[1]['preview_style']!=before_style:
        raise Stop('Native Text Block content was ignored or changed protected colors')
    return result


def configure(page,step):
    plan=validate(step);config=plan['text_blocks']
    active=theme._open(page,plan,plan['expected_template_title']);protected_theme=theme._snapshot(page,plan)
    inventory=blocks._inventory(page,plan)
    if inventory!=config['expected_inventory']:raise Stop('Text Block complete native inventory is stale')
    _preview_order(page,inventory);before=blocks._snapshot(page,plan,inventory)
    for update in config['updates']:
        if before[update['id']][0]['content']!=update['expected_content']:
            raise Stop('Text Block content differs from its inventoried previous value')
    desired=deepcopy(before);wanted=deepcopy(inventory);added=[]
    for update in config['updates']:
        identity=update['id']
        if read_text_block(page,plan,identity)!=before[identity]:raise Stop('Text Block changed after preflight')
        if update['content']!=before[identity][0]['content']:
            desired[identity]=_write(page,plan,identity,update['content'])
    for authored in config['append']:
        if blocks._inventory(page,plan)!=wanted or blocks._snapshot(page,plan,wanted)!=desired:
            raise Stop('Text Block siblings changed before append')
        # Opening a block inspector removes the sidebar. Reenter Body and
        # recheck its exact inventory before addressing Add Block.
        if blocks._inventory(page,plan)!=wanted:
            raise Stop('Text Block sidebar inventory changed before native append')
        click(theme._one(page.get_by_role('button',name='Add Block',exact=True),'Native Add Block changed'))
        click(theme._one(page.get_by_role('button',name='Text Block',exact=True),'Native Text Block add option changed'))
        after=blocks._inventory(page,plan)
        if (len(after)!=len(wanted)+1 or after[:-1]!=wanted or after[-1]['type']!='Text Block'
                or after[-1]['id'] in {row['id'] for row in wanted}):
            raise Stop('Native Text Block append changed existing UUID/type/order inventory')
        identity=after[-1]['id'];added.append(identity)
        initial=read_text_block(page,plan,identity)
        if initial[0]['content']!='':raise Stop('New Text Block differs from its captured empty Content default')
        desired[identity]=_write(page,plan,identity,authored['content'])
        if desired[identity][1]['preview_style']!=initial[1]['preview_style']:
            raise Stop('Text Block authoring changed new block default colors')
        wanted=after
    if (blocks._inventory(page,plan)!=wanted or blocks._snapshot(page,plan,wanted)!=desired
            or theme._snapshot(page,plan)!=protected_theme):
        raise Stop('Text Block authoring changed an unrequested sibling or theme setting')
    theme._identity(page,plan);assert_tenant(page,plan)
    save=theme._one(page.get_by_role('button',name='Save',exact=True),'Native template Save changed')
    if desired!=before:
        if not save.is_enabled():raise Stop('Native Text Block changes did not enable Save')
        click(save);wait_until(lambda:not save.is_enabled(),'Native Text Block Save did not settle')
        try:page.wait_for_load_state('networkidle',timeout=45000)
        except Exception:raise Stop('Text Block Save remains unsettled; reconcile before another write') from None
    elif save.is_enabled():raise Stop('Unrelated unsaved theme changes require reconciliation before Save')
    reopened=theme._open(page,plan,plan['expected_template_title'])
    if (reopened!=active or blocks._inventory(page,plan)!=wanted
            or blocks._snapshot(page,plan,wanted)!=desired or theme._snapshot(page,plan)!=protected_theme):
        raise Stop('Text Block independent reopen or protected sibling/theme readback failed')
    return {'status':'COURSE_TEXT_BLOCKS_SAVED_AND_REOPENED','editor_url':page.url,
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'added_block_ids':added,'block_ids':[row['id'] for row in wanted],'block_count':len(wanted),
        'functional_verified':False,'activation_performed':False}
