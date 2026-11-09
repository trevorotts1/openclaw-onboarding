"""Authored Radio definitions to exact existing-form native placement.

Reuses the measured Skill44 Radio dependency fallback and the captured native
Add Object Fields writer. API and editor intents have separate journals. A
completed native job retains its original GET timestamp for bound replay; a
new insertion still requires fresh same-location field readback.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

if __package__:
    from . import radio_dependencies as dependencies
    from .evidence_lease import guard_delivery, journal_present, read_journal
    from .skill6_playwright import Stop, assert_tenant, click, secure_json
else:
    import radio_dependencies as dependencies
    from evidence_lease import guard_delivery, journal_present, read_journal
    from skill6_playwright import Stop, assert_tenant, click, secure_json


SCHEMA='skill6-form-radio-chain/1'


def validate_inputs(inputs):
    if (not isinstance(inputs,dict) or set(inputs)!={'location_id','location_name',
            'start_url','expected_form_name','questions'}):
        raise Stop('Form Radio chain requires exact existing form identity and authored questions')
    dependencies.validate_inputs({key:inputs[key] for key in ('location_id','questions')})
    for key in ('location_name','expected_form_name'):
        if (not isinstance(inputs[key],str) or not inputs[key].strip() or inputs[key]!=inputs[key].strip()
                or len(inputs[key])>512 or any(ord(c)<32 for c in inputs[key])):
            raise Stop('Form Radio chain requires a visible exact '+key)
    try:
        parsed=urlsplit(inputs['start_url'])
        port=parsed.port
    except (TypeError,ValueError):
        raise Stop('Form Radio chain editor URL is malformed') from None
    if (parsed.scheme!='https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or port not in (None,443) or parsed.query or parsed.fragment
            or not re.fullmatch('/v2/location/'+re.escape(inputs['location_id'])+
                r'/form-builder-v2/[A-Za-z0-9_-]+',parsed.path)):
        raise Stop('Form Radio chain must target its exact existing form editor URL')
    return deepcopy(inputs)


def configuration_hash(inputs):
    return hashlib.sha256(json.dumps(validate_inputs(inputs),sort_keys=True,
        separators=(',',':')).encode()).hexdigest()


def _stable_job(value):
    result=deepcopy(value)
    for step in result.get('steps',[]):
        step.get('payload',{}).get('field_dependencies',{}).pop('observed_at',None)
    return result


@guard_delivery('course')
def build_form_questions(inputs,evidence_root,*,page,capability,transport=None):
    """Provision explicit definitions, then invoke the real named form recipe.

    This creates no form, publishes nothing and submits no contact. Native form
    identity and actual canvas presence are checked before any API schema write.
    Uncertain API or native journal state always requires reconciliation.
    """
    plan=validate_inputs(inputs)
    if __package__:
        from .forms_advanced import _canvas_identity,_close_object_drawer
        from .recipe_cli import compile_recipe
        from .skill6_playwright import form_builder,run_on_page,validate_job
    else:
        from forms_advanced import _canvas_identity,_close_object_drawer
        from recipe_cli import compile_recipe
        from skill6_playwright import form_builder,run_on_page,validate_job
    root=Path(evidence_root).resolve()
    native=root/'native';native_job_path=root/'native-question-job.json'
    binding_path=root/'form-question-intake.json'
    if native.is_symlink() or native_job_path.is_symlink() or binding_path.is_symlink():
        raise Stop('Form Radio evidence binding contains a symlink; reconcile before schema creation')
    binding={'schema':SCHEMA,'location_id':plan['location_id'],
             'configuration_sha256':configuration_hash(plan)}
    if journal_present(binding_path) and read_journal(binding_path)!=binding:
        raise Stop('Form Radio evidence root belongs to another form or authored question plan')
    if journal_present(native/'state.json') and not journal_present(root/'delivery-state.json'):
        raise Stop('Native form question intent exists without its API dependencies')
    api=transport or dependencies.Skill44RadioTransport()
    dependencies.validate_capability(capability,plan['location_id'],version_resolver=api.version_for)
    if page.url!=plan['start_url']:
        raise Stop('Form Radio chain must start on the exact requested form editor')
    assert_tenant(page,plan)
    frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or title.input_value()!=plan['expected_form_name']:
        raise Stop('Form Radio chain cannot prove its exact existing form name')
    _close_object_drawer(frame,'form')
    click(frame.get_by_role('tab',name='Edit',exact=True))
    canvas=frame.locator('#form-builder-container')
    if canvas.count()!=1 or not canvas.is_visible():
        raise Stop('Form Radio chain cannot prove its existing owner canvas')
    before=_canvas_identity(canvas)
    if (not isinstance(before,list) or not before
            or any(not isinstance(row,dict) or set(row)!={'types','names'}
                or not isinstance(row['types'],list) or len(row['types'])!=1
                or not isinstance(row['types'][0],str) or not row['types'][0]
                or not isinstance(row['names'],list) for row in before)):
        raise Stop('Form Radio chain owner field inventory is missing or malformed')
    # Bind this root before a shared contact-field schema can be written.
    secure_json(binding_path,binding)
    prepared=dependencies._provision({key:plan[key] for key in ('location_id','questions')},
        root,capability=capability,transport=api)
    if (page.url!=plan['start_url'] or title.count()!=1
            or title.input_value()!=plan['expected_form_name']):
        raise Stop('Form Radio native target changed while API dependencies were prepared')
    assert_tenant(page,plan)
    if _canvas_identity(canvas)!=before:
        raise Stop('Form Radio owner fields changed during dependency preparation')
    data={key:plan[key] for key in ('location_id','location_name','start_url')}
    data.update(object_fields=prepared['object_fields'],field_dependencies=prepared['field_dependencies'])
    job=compile_recipe('forms.configure',data)
    if journal_present(native_job_path):
        saved=read_journal(native_job_path)
        if not isinstance(saved,dict) or _stable_job(saved)!=_stable_job(job):
            raise Stop('Saved native Radio job belongs to another form or field definition')
        if journal_present(native/'state.json'):
            job=saved
    job=validate_job(job,root)
    secure_json(native_job_path,job)
    result=run_on_page(page,job,native)
    return {'status':'NEEDS_VERIFICATION','location_id':plan['location_id'],
        'configuration_sha256':configuration_hash(plan),
        'object_fields':prepared['object_fields'],'field_dependencies':prepared['field_dependencies'],
        'native_result':result,'native_placement_required':False,
        'submission_verified':False,'behavior_verified':False}
