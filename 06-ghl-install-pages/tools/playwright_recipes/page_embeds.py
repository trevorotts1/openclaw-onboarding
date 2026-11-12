"""Approved iframe presentation and safe initialization plans for page embeds.

This helper never edits the approved embed fragment. It verifies the existing
HTML/receipt binding, then emits an independent, scoped native Code fragment
that may be installed through the existing Code element path.
"""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit

from .skill6_playwright import Stop


_KEYS = {
    'iframe_id', 'approved_html_sha256', 'aspect_ratio', 'height_px',
    'min_height_px', 'max_height_px', 'max_width_px', 'resize_origin',
    'initialize_selector', 'initialize_call',
}


def _fail(message):
    raise Stop(message)


def _px(value, name, *, optional=False):
    if optional and value is None:
        return None
    if type(value) is not int or not 1 <= value <= 10000:
        _fail(name + ' must be an integer from 1 through 10000')
    return value


def _origin(value):
    if value is None:
        return None
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        _fail('resize_origin must be an explicit credential-free HTTPS origin')
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'https' and parsed.hostname and not parsed.username
                 and not parsed.password and parsed.port in (None, 443)
                 and parsed.path in ('', '/') and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        _fail('resize_origin must be an explicit credential-free HTTPS origin')
    return parsed.scheme + '://' + parsed.netloc


def validate(config, *, approved_html, receipt, location_id):
    """Validate a standalone plan without modifying the approved fragment."""
    if not isinstance(config, dict) or set(config) - _KEYS:
        _fail('page_embed config has unknown properties')
    required = {'iframe_id', 'approved_html_sha256'}
    if not required <= set(config):
        _fail('page_embed requires iframe_id and approved_html_sha256')
    iframe_id = config['iframe_id']
    if not isinstance(iframe_id, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', iframe_id):
        _fail('iframe_id must be a simple exact HTML ID')
    if not isinstance(approved_html, str) or not approved_html.strip():
        _fail('The original approved HTML fragment is required')
    digest = hashlib.sha256(approved_html.encode()).hexdigest()
    if config['approved_html_sha256'] != digest:
        _fail('page_embed plan does not bind the exact approved HTML hash')
    if (not isinstance(receipt, dict) or receipt.get('status') != 'PASS'
            or receipt.get('location_id') != location_id
            or receipt.get('html_sha256') != digest):
        _fail('page_embed requires the existing PASS receipt for this location and exact HTML hash')
    # Re-use the existing normalized fragment integrity behavior: do not rewrite
    # the document or change a byte covered by the receipt.
    tag = re.compile(r'<iframe\b([^>]*)>', re.I)
    frames = list(tag.finditer(approved_html))
    if not frames:
        _fail('Approved fragment has no iframe to size')
    # Small attribute parser preserves the guard's limited purpose here: bind
    # exactly one frame by identity and verify that its existing URL is receipt-backed.
    attr_text = frames[0].group(1)
    id_match = re.search(r'\bid\s*=\s*(["\'])(.*?)\1', attr_text, re.I)
    src_match = re.search(r'\bsrc\s*=\s*(["\'])(.*?)\1', attr_text, re.I)
    if (len(frames) != 1 or not id_match or id_match.group(2) != iframe_id
            or not src_match or src_match.group(2) not in receipt.get('embed_urls', [])):
        _fail('iframe_id and source must identify the single receipt-backed iframe')
    ratio = config.get('aspect_ratio')
    if ratio is not None and (not isinstance(ratio, (int, float)) or isinstance(ratio, bool)
                              or not 0.1 <= ratio <= 10):
        _fail('aspect_ratio must be a number from 0.1 through 10')
    height = _px(config.get('height_px'), 'height_px', optional=True)
    minimum = _px(config.get('min_height_px'), 'min_height_px', optional=True)
    maximum = _px(config.get('max_height_px'), 'max_height_px', optional=True)
    max_width = _px(config.get('max_width_px'), 'max_width_px', optional=True)
    if ratio is None and height is None:
        _fail('Set aspect_ratio or height_px explicitly')
    if minimum is not None and maximum is not None and minimum > maximum:
        _fail('min_height_px must not exceed max_height_px')
    if height is not None and ((minimum is not None and height < minimum)
                               or (maximum is not None and height > maximum)):
        _fail('height_px must be within the explicit height bounds')
    selector = config.get('initialize_selector')
    call = config.get('initialize_call')
    if (selector is None) != (call is None):
        _fail('initialize_selector and initialize_call must be supplied together')
    if selector is not None:
        if not isinstance(selector, str) or not re.fullmatch(r'#[A-Za-z][A-Za-z0-9_-]{0,63}', selector):
            _fail('initialize_selector must be one exact #id selector')
        if (not isinstance(call, str) or not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*){0,3}', call)):
            _fail('initialize_call must be an exact global function path')
    origin = _origin(config.get('resize_origin'))
    return {
        'iframe_id': iframe_id, 'approved_html_sha256': digest,
        'aspect_ratio': ratio, 'height_px': height, 'min_height_px': minimum,
        'max_height_px': maximum, 'max_width_px': max_width,
        'resize_origin': origin, 'initialize_selector': selector,
        'initialize_call': call, 'source_url': src_match.group(2),
    }


def build_fragment(plan):
    """Return scoped CSS/JS as a separate HTML fragment for native Code."""
    if not isinstance(plan, dict) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', str(plan.get('iframe_id', ''))):
        _fail('A validated page_embed plan is required')
    ident = plan['iframe_id']
    selector = '#' + ident
    declarations = ['display:block', 'width:100%', 'border:0', 'max-width:100%']
    if plan.get('aspect_ratio') is not None:
        declarations.append('aspect-ratio:' + str(plan['aspect_ratio']) + '/1')
        if plan.get('height_px') is None:
            declarations.append('height:auto')
    if plan.get('height_px') is not None:
        declarations.append('height:' + str(plan['height_px']) + 'px')
    if plan.get('min_height_px') is not None:
        declarations.append('min-height:' + str(plan['min_height_px']) + 'px')
    if plan.get('max_height_px') is not None:
        declarations.append('max-height:' + str(plan['max_height_px']) + 'px')
    if plan.get('max_width_px') is not None:
        declarations.append('max-width:' + str(plan['max_width_px']) + 'px')
    style_id = 'zhc-embed-style-' + ident
    script_id = 'zhc-embed-init-' + ident
    cfg = {k: plan.get(k) for k in ('iframe_id', 'resize_origin', 'initialize_selector', 'initialize_call', 'height_px', 'min_height_px', 'max_height_px')}
    cfg_json = json.dumps(cfg, separators=(',', ':'))
    # Resize messages are ignored unless origin, exact iframe window and a
    # bounded integer height all match. No message is required for sizing.
    js = """(function(){
  'use strict';
  var c=CFG,w=window,d=document,key='__zhcEmbedInit_'+c.iframe_id;
  if(w[key])return;w[key]=true;
  var tries=0,done=false,timer=null,observer=null;
  function schedule(){
    if(done||timer!==null||tries>=120)return;
    timer=w.setTimeout(function(){timer=null;attempt();},250);
  }
  function attempt(){
    if(done||tries>=120)return;
    tries++;
    var f=d.getElementById(c.iframe_id);
    if(!f||f.tagName!=='IFRAME'){schedule();return;}
    if(c.height_px)f.style.height=c.height_px+'px';
    if(c.min_height_px)f.style.minHeight=c.min_height_px+'px';
    if(c.max_height_px)f.style.maxHeight=c.max_height_px+'px';
    var waiting=false;
    if(c.initialize_selector&&c.initialize_call){
      var target=d.querySelector(c.initialize_selector),parts=c.initialize_call.split('.'),owner=w,fn=w;
      for(var i=0;i<parts.length&&fn;i++){owner=fn;fn=fn[parts[i]];}
      if(!target||typeof fn!=='function')waiting=true;
      else if(!target.__zhcEmbedTargetInit){
        try{fn.call(owner,target);target.__zhcEmbedTargetInit=true;}
        catch(_error){waiting=true;}
      }
    }
    if(waiting){schedule();return;}
    done=true;
    if(observer){observer.disconnect();observer=null;}
  }
  function start(){
    if(done)return;
    attempt();
    if(!done&&observer===null&&w.MutationObserver){
      observer=new MutationObserver(attempt);
      observer.observe(d.documentElement,{childList:true,subtree:true});
    }
  }
  if(d.readyState==='loading')d.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
  w.addEventListener('hydrationDone',start,{once:true});
  w.setTimeout(start,1500);
  if(c.resize_origin){w.addEventListener('message',function(e){
    if(e.origin!==c.resize_origin)return;
    var f=d.getElementById(c.iframe_id);
    if(!f||e.source!==f.contentWindow)return;
    var m=e.data;
    if(!m||m.type!=='zhc:embed-resize'||!Number.isInteger(m.height)||m.height<80||m.height>10000)return;
    var min=c.min_height_px||80,max=c.max_height_px||10000;
    f.style.height=Math.min(max,Math.max(min,m.height))+'px';
  });}
})();""".replace('CFG', cfg_json)
    return ('<style id="' + style_id + '">' + selector + '{' + ';'.join(declarations) + '}</style>'
            + '<script id="' + script_id + '">' + js + '</script>')


def verify_dom_state(plan, state):
    """Check an observed iframe DOM snapshot; this does not mutate the page."""
    if not isinstance(state, dict):
        _fail('iframe DOM readback must be an object')
    if state.get('id') != plan.get('iframe_id') or state.get('tag') != 'IFRAME':
        _fail('iframe DOM readback identity does not match the plan')
    width, height = state.get('width'), state.get('height')
    if (type(width) is not int or width < 1 or type(height) is not int or height < 1
            or state.get('display') == 'none' or state.get('visible') is not True):
        _fail('iframe DOM readback is not visibly sized')
    if plan.get('max_width_px') and width > plan['max_width_px']:
        _fail('iframe DOM readback exceeds max_width_px')
    if plan.get('min_height_px') and height < plan['min_height_px']:
        _fail('iframe DOM readback is below min_height_px')
    if plan.get('max_height_px') and height > plan['max_height_px']:
        _fail('iframe DOM readback exceeds max_height_px')
    if plan.get('height_px') is not None and height != plan['height_px']:
        _fail('iframe DOM readback height differs from the explicit height')
    if plan.get('aspect_ratio') is not None and plan.get('height_px') is None:
        expected_height = width / plan['aspect_ratio']
        if plan.get('min_height_px') is not None:
            expected_height = max(expected_height, plan['min_height_px'])
        if plan.get('max_height_px') is not None:
            expected_height = min(expected_height, plan['max_height_px'])
        if abs(height - expected_height) > 1.5:
            _fail('iframe DOM readback does not match the responsive aspect ratio')
    return {'iframe_id': plan['iframe_id'], 'width': width, 'height': height,
            'visible': True, 'status': 'VERIFIED'}


def configure(page, step):
    """Insert the generated helper as a separate native Code element and read back preview DOM."""
    from .skill6_playwright import (builder, click, fill, visible, add_tile,
                                    save_page, native_order_inventory,
                                    assert_native_orders_preserved,
                                    select_install_column, validate_placement,
                                    placement_column_id, page_builder_ready)
    if not isinstance(step, dict) or not isinstance(step.get('plan'), dict):
        _fail('page_embed executor requires its validated plan')
    plan = step['plan']
    fragment = build_fragment(plan)
    if not isinstance(step.get('id'), str) or not re.fullmatch(r'[a-z0-9_-]+', step['id']):
        _fail('page_embed requires a unique simple step id')
    placement = step.get('placement')
    validate_placement(placement)
    page_builder_ready(page)
    frame = builder(page)
    before_orders = native_order_inventory(frame)
    before_ids = set(frame.locator('.c-custom-code').evaluate_all('(els)=>els.map(el=>el.id)'))
    target_column = placement_column_id(frame, placement)
    select_install_column(frame, placement)
    add_tile(frame, 'Elements', 'Code')
    name = 'ZHC Embed ' + step['id']
    fill(frame.get_by_role('textbox', name='Element name', exact=True), name)
    click(frame.get_by_role('button', name='Open Code Editor', exact=True))
    modal = frame.get_by_role('dialog', name='UI Modal', exact=True)
    fill(modal.get_by_role('textbox'), fragment)
    click(modal.get_by_role('button', name='Save', exact=True))
    modal.wait_for(state='hidden')
    close = frame.get_by_role('button', name='Close', exact=True)
    if visible(close):
        click(close)
    assert_native_orders_preserved(before_orders, native_order_inventory(frame))
    after_ids = set(frame.locator('.c-custom-code').evaluate_all('(els)=>els.map(el=>el.id)'))
    created = after_ids - before_ids
    if len(created) != 1:
        _fail('Native Code element identity is missing or ambiguous; page was not saved')
    code_id = next(iter(created))
    code = frame.locator('.c-custom-code[id=' + json.dumps(code_id) + ']')
    if code.count() != 1 or code.evaluate("el => el.closest('.c-column')?.id || null") != target_column:
        _fail('Embed helper Code element is outside its requested native column; page was not saved')
    save_page(frame)
    href = frame.locator('a[href*="/preview/"]').get_attribute('href')
    check = page.context.new_page()
    try:
        response = check.goto(href, wait_until='domcontentloaded', timeout=45000)
        if response is None or response.status != 200:
            _fail('Page preview did not return HTTP 200')
        iframe = check.locator('#' + plan['iframe_id'])
        iframe.wait_for(state='visible', timeout=30000)
        state = iframe.evaluate("e => {const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {id:e.id,tag:e.tagName,width:Math.round(r.width),height:Math.round(r.height),display:s.display,visible:r.width>0&&r.height>0&&s.visibility!=='hidden'}}")
        readback = verify_dom_state(plan, state)
        return {'status': 'VERIFIED', 'preview_url': check.url,
                'code_element_id': code_id, 'approved_html_sha256': plan['approved_html_sha256'],
                'iframe': readback}
    finally:
        check.close()


def verify_completed(page, step, result):
    """Reopen the installed Code element and preview readback without writing."""
    from .skill6_playwright import builder, placement_column_id, page_builder_ready
    from .pages_checkout import resolve_code_target
    if not isinstance(step, dict) or not isinstance(step.get('plan'), dict):
        _fail('page_embed replay requires its validated plan')
    plan = step['plan']
    placement = step.get('placement')
    from .skill6_playwright import validate_placement
    validate_placement(placement)
    if (not isinstance(result, dict) or result.get('status') != 'VERIFIED'
            or not isinstance(result.get('code_element_id'), str)
            or result.get('approved_html_sha256') != plan.get('approved_html_sha256')
            or not isinstance(result.get('preview_url'), str)):
        _fail('page_embed completion receipt does not match its approved plan')
    expected_readback = result.get('iframe')
    if (not isinstance(expected_readback, dict) or expected_readback.get('status') != 'VERIFIED'
            or expected_readback.get('iframe_id') != plan.get('iframe_id')):
        _fail('page_embed receipt has no matching iframe verification')
    page_builder_ready(page)
    frame = builder(page)
    code_id = result['code_element_id']
    expected_name = 'ZHC Embed ' + str(step.get('id', ''))
    selected = resolve_code_target(frame, code_id, expected_name)
    code = selected['locator']
    desired_column = placement_column_id(frame, placement)
    parents = code.evaluate("el => ({section_id:el.closest('.c-section')?.id||null,row_id:el.closest('.c-row')?.id||null,column_id:el.closest('.c-column')?.id||null})")
    if selected.get('section_id') != placement['section_id'] or parents != {
            'section_id': placement['section_id'], 'row_id': placement['row_id'],
            'column_id': desired_column}:
        _fail('Saved embed helper Code element is no longer in its recorded native placement')
    preview_link = frame.locator('a[href*="/preview/"]')
    if preview_link.count() != 1:
        _fail('Saved page preview link is missing or ambiguous')
    href = preview_link.get_attribute('href')
    if not isinstance(href, str) or not href:
        _fail('Saved page preview URL is unavailable')
    check = page.context.new_page()
    try:
        response = check.goto(href, wait_until='domcontentloaded', timeout=45000)
        if response is None or response.status != 200:
            _fail('Saved page preview did not return HTTP 200 during replay')
        if check.url != result['preview_url']:
            _fail('Saved page preview URL differs from the completed receipt')
        iframe = check.locator('#' + plan['iframe_id'])
        iframe.wait_for(state='visible', timeout=30000)
        state = iframe.evaluate("e => {const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {id:e.id,tag:e.tagName,width:Math.round(r.width),height:Math.round(r.height),display:s.display,visible:r.width>0&&r.height>0&&s.visibility!=='hidden'}}")
        observed = verify_dom_state(plan, state)
        if observed != expected_readback:
            _fail('Saved iframe preview dimensions differ from the completion receipt')
        return {'status': 'VERIFIED', 'code_element_id': code_id,
                'approved_html_sha256': plan['approved_html_sha256'],
                'preview_url': check.url, 'iframe': observed}
    finally:
        check.close()

