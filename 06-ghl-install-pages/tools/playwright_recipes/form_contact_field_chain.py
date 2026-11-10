"""Typed Contact v3 definitions to captured Dropdown/LARGE_TEXT placement.

No native selector or query-key derivation is added. API and editor evidence
remain separate; a fresh picker-row insertion proves native provenance, while
arbitrary legacy disabled-row reuse remains refused by the captured leaf.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

if __package__:
    from .assessments import read_editor_title
    from . import contact_field_dependencies as dependencies,dropdown_fields,large_text_fields
    from .evidence_lease import guard_delivery,journal_present,read_journal
    from .skill6_playwright import Stop,assert_tenant,click,secure_json
else:
    from assessments import read_editor_title
    import contact_field_dependencies as dependencies
    import dropdown_fields,large_text_fields
    from evidence_lease import guard_delivery,journal_present,read_journal
    from skill6_playwright import Stop,assert_tenant,click,secure_json


SCHEMA='skill6-form-contact-field-chain/1'


def validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)!={'location_id','location_name','start_url','expected_form_name','fields','native_bindings'}:
        raise Stop('Contact form chain requires exact existing form identity, typed definitions and separate native bindings')
    dependencies.validate_inputs({key:inputs[key] for key in ('location_id','fields')})
    kinds={field['data_type'] for field in inputs['fields']}
    if len(kinds)!=1:raise Stop('Each captured native placement family uses its own independently journaled chain')
    for key in ('location_name','expected_form_name'):
        value=inputs[key]
        if not isinstance(value,str) or not value.strip() or value!=value.strip() or any(ord(c)<32 for c in value):
            raise Stop('Contact form chain needs exact visible '+key)
    try:parsed=urlsplit(inputs['start_url']);port=parsed.port
    except (TypeError,ValueError):raise Stop('Contact form editor URL is malformed') from None
    if (parsed.scheme!='https' or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or port not in (None,443) or parsed.query or parsed.fragment
            or not re.fullmatch('/v2/location/'+re.escape(inputs['location_id'])+r'/form-builder-v2/[A-Za-z0-9_-]+',parsed.path)):
        raise Stop('Contact form chain must bind its exact existing same-location editor')
    bindings=inputs['native_bindings'];large=next(iter(kinds))=='LARGE_TEXT'
    native=large_text_fields if large else dropdown_fields
    if not isinstance(bindings,list) or len(bindings)!=len(inputs['fields']):
        raise Stop('Every API field needs one separately supplied native binding')
    expected={field['field_key'] for field in inputs['fields']};keys=set();queries=set()
    for binding in bindings:
        if not isinstance(binding,dict) or set(binding)!={'field_key','native_query_key','expected_label'}|({'expected_placeholder'} if large else set()):
            raise Stop('Native field bindings require exact query/label and type-specific placeholder metadata')
        if not isinstance(binding['field_key'],str) or binding['field_key'] not in expected or binding['field_key'] in keys:
            raise Stop('Native bindings must match each exact authored API field key once')
        keys.add(binding['field_key'])
        native._text(binding['native_query_key'],'native Query Key',token=True)
        native._text(binding['expected_label'],'native label')
        if binding['native_query_key'] in queries:raise Stop('Native binding Query Keys must remain unique')
        queries.add(binding['native_query_key'])
        if large:native._placeholder(binding['expected_placeholder'])
    return deepcopy(inputs)


def configuration_hash(inputs):
    return hashlib.sha256(json.dumps(validate_inputs(inputs),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _stable_job(value):
    result=deepcopy(value)
    for step in result.get('steps',[]):step.get('payload',{}).get('field_dependencies',{}).pop('observed_at',None)
    return result


@guard_delivery('course')
def build_form_fields(inputs,evidence_root,*,page,capability,transport=None):
    plan=validate_inputs(inputs)
    if __package__:
        from .forms_advanced import _canvas_identity,_close_object_drawer
        from .recipe_cli import compile_recipe
        from .skill6_playwright import form_builder,run_on_page,validate_job
    else:
        from forms_advanced import _canvas_identity,_close_object_drawer
        from recipe_cli import compile_recipe
        from skill6_playwright import form_builder,run_on_page,validate_job
    dependencies.validate_capability(capability,plan['location_id'])
    root=Path(evidence_root).resolve();native=root/'native';job_path=root/'native-field-job.json';binding_path=root/'form-field-intake.json'
    if any(path.is_symlink() for path in (native,job_path,binding_path)):
        raise Stop('Contact form evidence binding contains a symlink; reconcile before API creation')
    binding={'schema':SCHEMA,'location_id':plan['location_id'],'configuration_sha256':configuration_hash(plan)}
    if journal_present(binding_path) and read_journal(binding_path)!=binding:
        raise Stop('Contact form evidence root belongs to another editor or authored binding')
    if journal_present(native/'state.json') and not journal_present(root/'delivery-state.json'):
        raise Stop('Native placement evidence exists without its API dependency journal')
    if page.url!=plan['start_url']:raise Stop('Contact form chain must start on its exact editor URL')
    assert_tenant(page,plan);frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True);title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or read_editor_title(title)!=plan['expected_form_name']:
        raise Stop('Contact form chain cannot prove its exact existing form name')
    _close_object_drawer(frame,'form');click(frame.get_by_role('tab',name='Edit',exact=True))
    canvas=frame.locator('#form-builder-container')
    if canvas.count()!=1 or not canvas.is_visible():raise Stop('Contact form chain owner canvas is missing or ambiguous')
    before=_canvas_identity(canvas)
    if (not isinstance(before,list) or not before or any(not isinstance(row,dict) or set(row)!={'types','names'}
            or not isinstance(row['types'],list) or len(row['types'])!=1 or not isinstance(row['types'][0],str)
            or not row['types'][0] or not isinstance(row['names'],list) for row in before)):
        raise Stop('Contact form chain owner inventory is missing or malformed')
    secure_json(binding_path,binding)
    prepared=dependencies._provision({key:plan[key] for key in ('location_id','fields')},root,capability=capability,transport=transport)
    if page.url!=plan['start_url'] or title.count()!=1 or read_editor_title(title)!=plan['expected_form_name']:
        raise Stop('Contact form editor changed while API dependencies were prepared')
    assert_tenant(page,plan)
    if _canvas_identity(canvas)!=before:raise Stop('Contact form owner fields changed during API preparation')
    bindings={row['field_key']:row for row in plan['native_bindings']}
    fields=[{**field,**{key:value for key,value in bindings[field['field_key']].items() if key!='field_key'}} for field in prepared['fields']]
    data={key:plan[key] for key in ('location_id','location_name','start_url')}
    family='large_text_fields' if plan['fields'][0]['data_type']=='LARGE_TEXT' else 'dropdown_fields'
    data.update({family:fields,'field_dependencies':prepared['field_dependencies']})
    job=compile_recipe('forms.configure',data)
    if journal_present(job_path):
        saved=read_journal(job_path)
        if not isinstance(saved,dict) or _stable_job(saved)!=_stable_job(job):
            raise Stop('Saved native Contact job belongs to another form/definition/binding')
        if journal_present(native/'state.json'):job=saved
    job=validate_job(job,root);secure_json(job_path,job)
    result=run_on_page(page,job,native)
    return {'status':'NEEDS_VERIFICATION','location_id':plan['location_id'],
        'configuration_sha256':configuration_hash(plan),'fields':prepared['fields'],
        'field_dependencies':prepared['field_dependencies'],'native_result':result,
        'native_placement_required':False,'submission_verified':False,'behavior_verified':False}
