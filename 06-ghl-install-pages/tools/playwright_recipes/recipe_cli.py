#!/usr/bin/env python3
"""Named entry points for the shared Skill 6 Playwright runner."""
import argparse
import json
from pathlib import Path
import sys
if __package__:
    from .skill6_playwright import Stop, execute, validate_job
else:
    from skill6_playwright import Stop, execute, validate_job


def compile_recipe(operation, data):
    base={k:data[k] for k in ('location_id','location_name','start_url')}
    steps=[]
    def add(action,**kw):
        steps.append({'id':kw.pop('id',action+str(len(steps)+1)),'action':action,**kw})
    if operation in ('funnels.create','funnels.add_page','websites.create','websites.add_page'):
        surface='funnel' if operation.startswith('funnels.') else 'website'
        add('navigate',area='Funnels' if surface=='funnel' else 'Websites')
        add('container',surface=surface,name=data['container_name'],allow_creation=operation.endswith('.create'))
        add('page',surface=surface,name=data['page_name'],path=data['path'],allow_creation=True)
        if data.get('file'):
            add('html',id=data.get('code_id','main_code'),file=data['file'],marker=data['marker'])
            add('seo',**data['seo'])
    elif operation in ('pages.install_code','pages.install_embed'):
        if operation=='pages.install_embed':
            receipt=data.get('embed_receipt',{})
            if receipt.get('status')!='PASS' or receipt.get('location_id')!=data['location_id'] or not receipt.get('source'):
                raise Stop('Hosted embed needs the existing embeddability-gate PASS receipt bound to this location')
        add('html',id=data.get('code_id','main_code'),file=data['file'],marker=data['marker'],append=data.get('append',False),**({'embed_receipt':data['embed_receipt']} if operation=='pages.install_embed' else {}))
        add('seo',**data['seo'])
    elif operation=='checkout.wrap_native':
        add('html',id='checkout_before',file=data['before_file'],marker=data['before_marker'])
        add('checkout',**data.get('checkout',{}))
        if data.get('after_file'):
            add('html',id='checkout_after',file=data['after_file'],marker=data['after_marker'],append=True)
        add('seo',**data['seo'])
    elif operation=='pages.seo':
        add('seo',**data['seo'])
    elif operation=='forms.create':
        add('form',name=data['name'],required=data.get('required',{}),allow_creation=data.get('allow_creation',False))
        add('form_css',radius=data.get('radius',12))
    elif operation=='forms.style':
        add('form_css',radius=data.get('radius',12))
    elif operation in ('surveys.create','quizzes.create'):
        add('assessment',kind='survey' if operation=='surveys.create' else 'quiz',name=data['name'],allow_creation=data.get('allow_creation',False),standard_fields=data.get('standard_fields',[]))
        if operation=='quizzes.create' and not data.get('options') and not data.get('fixture'):
            raise Stop('A production marketing quiz needs a captured scoring/result/options profile')
    elif operation=='communities.create':
        add('community',**data['community'])
    elif operation=='meetings.setup':
        add('meeting',**data['meeting'])
    elif operation in ('forms.configure','checkout.one_click_upsell','funnels.split_variant','communities.configure','courses.configure_ui','meetings.integrate'):
        if operation=='checkout.one_click_upsell':
            receipt=data.get('checkout_contract',{})
            if receipt.get('status')!='PASS' or receipt.get('location_id')!=data['location_id'] or not all(receipt.get(k) for k in ('product_id','price_id','source_step_id','upsell_step_id','source')) or receipt.get('prior_payment_verified') is not True:
                raise Stop('Native upsell requires a location-bound Skill 44/79 product, price, source/upsell step and verified prior-payment contract')
        if not data.get('options'):
            raise Stop('This operation needs its recorded options profile; hand off for browser capture')
    elif operation=='courses.create':
        raise Stop('API_ROUTE: Courses v3 create is documented. Use the per-location API probe and Skill 44/official MCP')
    else:
        raise Stop('Unknown operation')
    if data.get('options'):
        add('options',**data['options'])
    return {**base,'steps':steps,'publish':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipe',required=True)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--evidence-root',type=Path)
    a=p.parse_args()
    try:
        job=validate_job(compile_recipe(a.recipe,json.loads(a.inputs.read_text())),a.inputs.resolve().parent)
        if not a.execute:
            print(json.dumps({'status':'VALIDATED_ONLY','recipe':a.recipe,'steps':len(job['steps'])}))
            return 0
        if a.evidence_root is None:
            raise Stop('Durable --evidence-root is required')
        result=execute(job,a.evidence_root)
        print(json.dumps({'status':result['status'],'recipe':a.recipe}))
        return 0 if result['status']=='EDITOR_STEPS_COMPLETE' else 3
    except (Stop,KeyError,ValueError,OSError) as exc:
        print(json.dumps({'status':'NEEDS_BROWSER_RECOVERY','error_type':type(exc).__name__,'reason':str(exc)}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
