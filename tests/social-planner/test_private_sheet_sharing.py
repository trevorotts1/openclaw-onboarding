"""Exercise permission readback before the planner reports client access."""
import json
import pathlib
import subprocess
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '35-social-media-planner/config/n8n/social-planner-sheet-create.json'


def check(permissions, context=None, executed=False):
    workflow = json.loads(WORKFLOW.read_text())
    code = next(n['parameters']['jsCode'] for n in workflow['nodes'] if n['name'] == 'Check Sharing Permission')
    args = {'permissions': permissions, 'context': context or {'sharing': 'private', 'clientEmail': 'client@example.com'}, 'executed': executed}
    script = """const a=JSON.parse(process.argv[1]); const code=process.argv[2];
const input={first:()=>({json:{permissions:a.permissions}})};
const node=name=>({first:()=>({json:a.context}),isExecuted:a.executed});
try { console.log(JSON.stringify({result:new Function('$input','$',code)(input,node)})); }
catch(e) { console.log(JSON.stringify({error:e.message})); }
"""
    result = subprocess.run(['node', '-e', script, json.dumps(args), code], capture_output=True, text=True, check=True, timeout=10)
    return json.loads(result.stdout)

OWNER = {'type': 'user', 'role': 'owner', 'emailAddress': 'operator@example.com'}
CLIENT = {'type': 'user', 'role': 'writer', 'emailAddress': 'client@example.com'}


def test_private_requires_targeted_client_access():
    assert check([OWNER])['result'][0]['json']['shared'] is False
    assert check([OWNER, CLIENT])['result'][0]['json']['shared'] is True


@pytest.mark.parametrize('public_type', ['anyone', 'domain'])
def test_private_rejects_public_permissions(public_type):
    assert 'public sharing' in check([OWNER, CLIENT, {'type': public_type, 'role': 'reader'}])['error']


def test_readback_failure_stops_instead_of_repeating_permission_write():
    assert 'did not confirm' in check([OWNER], executed=True)['error']


def test_wrong_client_does_not_count_as_access():
    assert check([OWNER, {**CLIENT, 'emailAddress': 'other@example.com'}])['result'][0]['json']['shared'] is False


def test_private_policy_persists_on_deduplicated_request():
    context = {'clientEmail': 'client@example.com', 'existingFile': {'appProperties': {'skill35_sharing': 'private'}}}
    assert check([OWNER, CLIENT], context)['result'][0]['json']['shared'] is True
    assert 'public sharing' in check([OWNER, {'type': 'anyone', 'role': 'writer'}], context)['error']


def test_default_anyone_policy_remains_compatible():
    assert check([OWNER, {'type': 'anyone', 'role': 'writer'}], {'clientEmail': 'client@example.com'})['result'][0]['json']['shared'] is True


def test_permission_write_is_followed_by_actual_readback():
    workflow = json.loads(WORKFLOW.read_text())
    targets = workflow['connections']['Set Anyone Can Edit']['main'][0]
    assert targets == [{'node': 'Read Sharing Permission', 'type': 'main', 'index': 0}]
