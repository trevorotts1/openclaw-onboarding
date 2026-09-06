"""Selected-client path and credential isolation, with real temporary stores."""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
from presentation_job import oc_paths, env_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(os, 'environ', {})
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(oc_paths, 'VPS_ROOT', tmp_path / 'data' / '.openclaw')
    monkeypatch.setattr(oc_paths.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(oc_paths, '_container', lambda: False)
    return tmp_path, home


def store(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('PRESENTATION_NOTIFY_CMD=' + value + '\n')


@pytest.mark.parametrize('os_name', ['Darwin', 'Linux'])
def test_native_defaults_use_home(client, monkeypatch, os_name):
    _, home = client
    monkeypatch.setattr(oc_paths.platform, 'system', lambda: os_name)
    assert oc_paths.root() == home / '.openclaw'
    assert oc_paths.workspace() == home / '.openclaw/workspace'


def test_container_mount_defaults_to_data(client, monkeypatch):
    oc_paths.VPS_ROOT.parent.mkdir()
    monkeypatch.setattr(oc_paths, '_container', lambda: True)
    assert oc_paths.root() == oc_paths.VPS_ROOT


def test_native_data_directory_alone_is_not_container(client):
    _, home = client
    oc_paths.VPS_ROOT.parent.mkdir()
    assert oc_paths.root() == home / '.openclaw'


def test_existing_data_root_and_ambiguous_roots(client, monkeypatch):
    _, home = client
    oc_paths.VPS_ROOT.mkdir(parents=True)
    assert oc_paths.root() == oc_paths.VPS_ROOT
    (home / '.openclaw').mkdir()
    with pytest.raises(ValueError, match='Two client roots'):
        oc_paths.root()
    monkeypatch.setenv('OPENCLAW_ROOT', str(home / '.openclaw'))
    assert oc_paths.root() == home / '.openclaw'


@pytest.mark.parametrize('mode', ['mac', 'vps'])
def test_explicit_selected_root_and_external_workspace(client, monkeypatch, mode):
    tmp, _ = client
    selected = tmp / "Owner's installation"
    workspace = tmp / "Owner's workspace"
    monkeypatch.setenv('OPENCLAW_PLATFORM', mode)
    monkeypatch.setenv('OPENCLAW_ROOT', str(selected))
    monkeypatch.setenv('OPENCLAW_WORKSPACE_PATH', str(workspace))
    monkeypatch.setenv('OPENCLAW_WORKSPACE_ROOT', str(workspace) + '/')
    monkeypatch.setenv('PRESENTATION_OC_PATHS', '0')
    assert oc_paths.root() == selected
    assert oc_paths.workspace() == workspace
    assert oc_paths.skills() == selected / 'skills'
    assert oc_paths.state_dir() == selected / 'state/presentation'
    assert oc_paths.secrets_env_candidates() == [selected / 'secrets/.env', selected / 'secrets/secrets.env', selected / '.env', workspace / '.env']


def test_selected_configuration_workspace_and_invalid_json(client, monkeypatch):
    tmp, _ = client
    selected = tmp / 'selected'; selected.mkdir()
    target = tmp / 'client-workspace'
    monkeypatch.setenv('OPENCLAW_ROOT', str(selected))
    config = selected / 'openclaw.json'
    config.write_text(json.dumps({'agents': {'defaults': {'workspace': str(target)}}}))
    assert oc_paths.workspace() == target
    config.write_text('{bad')
    with pytest.raises(ValueError):oc_paths.secrets_env_candidates()


@pytest.mark.parametrize('pins', [
    {'OPENCLAW_ROOT': 'relative'}, {'OPENCLAW_ROOT': '/'},
    {'OPENCLAW_ROOT': '/client-a', 'OC_CONFIG': '/client-b'},
    {'OPENCLAW_WORKSPACE_PATH': '/client-a', 'OPENCLAW_WORKSPACE_ROOT': '/client-b'},
    {'OPENCLAW_WORKSPACE_PATH': 'relative'}, {'OPENCLAW_PLATFORM': 'typo'},
])
def test_invalid_or_conflicting_pins_fail_before_loading(client, monkeypatch, pins):
    _, home = client
    store(home / '.openclaw/secrets/.env', 'foreign-value')
    for key, value in pins.items():monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):env_store.resolve()


def test_other_clients_mac_data_and_legacy_credentials_never_fill_gaps(client, monkeypatch):
    tmp, home = client
    selected = tmp / 'selected'
    monkeypatch.setenv('OPENCLAW_ROOT', str(selected))
    for path in [home / '.openclaw/secrets/.env', home / 'clawd/secrets/.env', oc_paths.VPS_ROOT / 'secrets/.env']:
        store(path, 'FOREIGN-CLIENT-SECRET')
    assignments, report = env_store.resolve()
    assert 'PRESENTATION_NOTIFY_CMD' not in assignments
    assert env_store.unresolved_required(report) == ['PRESENTATION_NOTIFY_CMD']
    store(selected / 'secrets/.env', 'selected-notify')
    assert env_store.resolve()[0]['PRESENTATION_NOTIFY_CMD'] == 'selected-notify'


@pytest.mark.parametrize('symlink', [False, True])
def test_foreign_override_or_standard_symlink_refused(client, monkeypatch, symlink):
    tmp, _ = client
    selected = tmp / 'selected'; selected.mkdir()
    foreign = tmp / 'another-client/secrets/.env';store(foreign, 'FOREIGN')
    monkeypatch.setenv('OPENCLAW_ROOT', str(selected))
    if symlink:
        (selected / 'secrets').mkdir();(selected / 'secrets/.env').symlink_to(foreign)
    else:
        monkeypatch.setenv('OPENCLAW_SECRETS', str(foreign))
    with pytest.raises(ValueError):env_store.resolve()


def test_same_client_custom_secret_override_and_precedence(client, monkeypatch):
    tmp, _ = client
    selected = tmp / 'selected';custom = selected / 'private/custom.env'
    store(custom, 'explicit-selected')
    store(selected / 'secrets/.env', 'default-selected')
    monkeypatch.setenv('OPENCLAW_ROOT', str(selected))
    monkeypatch.setenv('OPENCLAW_SECRETS', str(custom))
    assert env_store.resolve()[0]['PRESENTATION_NOTIFY_CMD'] == 'explicit-selected'
    monkeypatch.setenv('PRESENTATION_NOTIFY_CMD', 'process-wins')
    assert 'PRESENTATION_NOTIFY_CMD' not in env_store.resolve()[0]


def test_missing_module_does_not_fall_back_to_home(client, monkeypatch):
    _, home = client
    store(home / '.openclaw/secrets/.env', 'FOREIGN')
    monkeypatch.setitem(sys.modules, 'presentation_job.oc_paths', None)
    with pytest.raises(ModuleNotFoundError):env_store.candidate_files()


def test_cli_invalid_selection_emits_no_assignments(client):
    tmp, home = client
    store(home / '.openclaw/secrets/.env', 'FOREIGN')
    env = {'HOME': str(home), 'OPENCLAW_ROOT': 'invalid-relative', 'PYTHONPATH': str(SCRIPTS)}
    result = subprocess.run([sys.executable, '-m', 'presentation_job.env_store', '--emit-shell'], env=env, capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'FOREIGN' not in result.stderr
    assert 'no stores loaded' in result.stderr


def test_explicit_environment_drives_candidate_selection(client):
    tmp, _ = client
    selected = tmp / 'selected'
    store(selected / 'secrets/.env', 'selected')
    assignments, _ = env_store.resolve(environ={'OPENCLAW_ROOT': str(selected), 'OPENCLAW_PLATFORM': 'vps'})
    assert assignments['PRESENTATION_NOTIFY_CMD'] == 'selected'


def test_store_cannot_rebind_child_client_identity(client, monkeypatch):
    tmp, _ = client
    selected = tmp / 'selected'
    secret = selected / 'secrets/.env'
    store(secret, 'selected-notify')
    with secret.open('a') as out:
        for key in env_store._PATH_BINDINGS:
            out.write(key + '=/another-client\n')
    monkeypatch.setenv('OPENCLAW_ROOT', str(selected))
    assignments, _ = env_store.resolve()
    assert assignments == {'PRESENTATION_NOTIFY_CMD': 'selected-notify'}
