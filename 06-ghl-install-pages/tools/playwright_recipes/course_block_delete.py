"""Delete one exact existing inactive-theme Custom Block through native confirm.

The confirmation dialog and UUID disappearance were captured November 9, 2026.
Other block kinds, block reordering and image removal are separate operations.
The maintained runner owns durable write intent, lease and uncertain recovery.
"""
from copy import deepcopy

if __package__:
    from . import course_blocks as blocks, course_theme as theme, course_text_blocks as text
    from . import course_theme_media as background, course_section_media as sections
    from .skill6_playwright import Stop,assert_tenant,click,wait_until
else:
    import course_blocks as blocks
    import course_theme as theme
    import course_text_blocks as text
    import course_theme_media as background
    import course_section_media as sections
    from skill6_playwright import Stop,assert_tenant,click,wait_until


_QUESTION='Are you sure want to remove this block?'
_WARNING='All the data associated with this block will be removed.'
_HEADING=_QUESTION+' '+_WARNING


def _surrounding(page,plan):
    # The section readers refuse unsupported hidden/color-mode shapes instead
    # of treating unobservable media/controls as empty preserved inventories.
    return {'theme':theme._snapshot(page,plan),'background':background._background(page,plan)[1],
        'sections':{section:sections._open_section(page,plan,section)[1] for section in sections.SECTIONS}}


def _guard_target(page,plan,inventory,expected):
    identity=plan['custom_blocks']['deletion']['id']
    theme._identity(page,plan);assert_tenant(page,plan)
    if blocks._visible_inventory(page)!=inventory:
        raise Stop('Custom Block deletion inventory changed before the destructive action')
    text._selected_preview(page,inventory,identity,'Custom Block')
    if blocks._read_selected_block(page,identity)!=expected:
        raise Stop('Custom Block deletion target content changed before the destructive action')


def _confirm_dialog(page):
    dialog=theme._one(page.get_by_role('dialog'),'Custom Block deletion confirmation is ambiguous')
    if (dialog.get_by_role('heading',name=_HEADING,exact=True).count()!=1
            or dialog.get_by_text(_WARNING,exact=True).count()!=1):
        raise Stop('Custom Block deletion dialog title or warning changed')
    theme._one(dialog.get_by_role('button',name='Cancel',exact=True),'Native deletion Cancel changed')
    confirm=theme._one(dialog.get_by_role('button',name='Confirm',exact=True),'Native deletion Confirm changed')
    if not confirm.is_enabled():raise Stop('Custom Block deletion Confirm is disabled')
    return dialog,confirm


def validate_receipt(value,step):
    plan=blocks.validate(step);config=plan['custom_blocks']
    if 'deletion' not in config:raise Stop('Deletion receipt requires its original explicit deletion plan')
    keys={'status','editor_url','course_id','template_id','configuration_sha256','independent_readback',
        'added_block_ids','removed_block_ids','block_ids','functional_verified','activation_performed'}
    identity=config['deletion']['id']
    expected={'status':'COURSE_BLOCKS_SAVED_AND_REOPENED','editor_url':theme.editor_url(plan),
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':blocks.configuration_hash(plan),'independent_readback':'VERIFIED',
        'added_block_ids':[],'removed_block_ids':[identity],
        'block_ids':[row['id'] for row in config['expected_inventory'] if row['id']!=identity],
        'functional_verified':False,'activation_performed':False}
    if (not isinstance(value,dict) or set(value)!=keys
            or any(value[key]!=item for key,item in expected.items())
            or value['functional_verified'] is not False or value['activation_performed'] is not False):
        raise Stop('Custom Block deletion receipt is malformed or unbound to its original target/inventory')
    return deepcopy(value)


def configure(page,step):
    plan=blocks.validate(step);config=plan['custom_blocks']
    if 'deletion' not in config:raise Stop('Native deletion needs its explicit exclusive delete plan')
    deletion=config['deletion'];identity=deletion['id']
    active=theme._open(page,plan,plan['expected_template_title'])
    save=theme._one(page.get_by_role('button',name='Save',exact=True),'Native deletion Save changed')
    if save.is_enabled():raise Stop('Unrelated unsaved course changes prevent Custom Block deletion')
    surrounding=_surrounding(page,plan)
    inventory=blocks._inventory(page,plan)
    if inventory!=config['expected_inventory']:
        raise Stop('Custom Block deletion complete UUID/type/order inventory is stale')
    text._preview_order(page,inventory)
    before=blocks._snapshot(page,plan,inventory)
    expected=(deletion['expected'],{'content_html':deletion['expected_content_html'],
        'media_src':deletion['expected_media_url']})
    if before[identity]!=expected:
        raise Stop('Custom Block deletion target differs from its complete expected snapshot')
    # Establish every surrounding/sibling value before opening destructive UI.
    if _surrounding(page,plan)!=surrounding:
        raise Stop('Protected course surroundings changed during deletion preflight')
    blocks._read_block(page,plan,identity)
    _guard_target(page,plan,inventory,expected)
    delete=theme._one(page.get_by_role('button',name='Delete Block',exact=True),'Native Custom Block Delete changed')
    if not delete.is_enabled():raise Stop('Native Custom Block Delete is disabled')
    click(delete)
    dialog,confirm=_confirm_dialog(page)
    # These helpers only read the existing selected inspector/Body. No panel
    # switches or other clicks are attempted through the modal backdrop.
    _guard_target(page,plan,inventory,expected)
    click(confirm)
    dialog.wait_for(state='hidden',timeout=45000)
    wanted=[deepcopy(row) for row in inventory if row['id']!=identity]
    def removed():
        actual=blocks._inventory(page,plan)
        if actual==inventory:return False
        if actual!=wanted:raise Stop('Native deletion changed another block identity/type/order')
        if page.locator('div.custom-block[id="custom-block-'+identity+'"]').count():return False
        text._preview_order(page,wanted)
        return True
    wait_until(removed,'Native Custom Block deletion did not remove the exact sidebar and preview UUID')
    desired=deepcopy(before);desired.pop(identity)
    if blocks._snapshot(page,plan,wanted)!=desired or _surrounding(page,plan)!=surrounding:
        raise Stop('Custom Block deletion changed protected sibling content or course surroundings')
    theme._identity(page,plan);assert_tenant(page,plan)
    save=theme._one(page.get_by_role('button',name='Save',exact=True),'Native deletion Save changed')
    if not save.is_enabled():raise Stop('Native Custom Block deletion did not enable Save')
    click(save);wait_until(lambda:not save.is_enabled(),'Custom Block deletion Save did not settle')
    try:page.wait_for_load_state('networkidle',timeout=45000)
    except Exception:raise Stop('Custom Block deletion Save remains unsettled; reconcile before another write') from None
    reopened=theme._open(page,plan,plan['expected_template_title'])
    current=blocks._inventory(page,plan)
    if (reopened!=active or current!=wanted
            or page.locator('div.custom-block[id="custom-block-'+identity+'"]').count()
            or blocks._snapshot(page,plan,wanted)!=desired or _surrounding(page,plan)!=surrounding):
        raise Stop('Custom Block deletion independent reopen failed or protected state changed')
    text._preview_order(page,wanted)
    return validate_receipt({'status':'COURSE_BLOCKS_SAVED_AND_REOPENED','editor_url':page.url,
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':blocks.configuration_hash(plan),'independent_readback':'VERIFIED',
        'added_block_ids':[],'removed_block_ids':[identity],'block_ids':[row['id'] for row in wanted],
        'functional_verified':False,'activation_performed':False},step)
