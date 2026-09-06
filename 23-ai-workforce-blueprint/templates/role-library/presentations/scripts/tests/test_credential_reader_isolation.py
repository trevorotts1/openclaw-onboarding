"""Exercise actual presentation credential readers against isolated client stores."""
import importlib.util
import os
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
from presentation_job import model_router, research_web, oc_paths


def load_kie(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROLE_KIE = load_kie('fixture_role_kie_reader', SCRIPTS / 'kie_generate.py')
RENDER_KIE = load_kie('fixture_render_kie_reader', SCRIPTS.parents[2] / 'presentation-render/kie_generate.py')
READERS = [
    ('router', lambda: model_router.provider_key_resolves('openrouter')),
    ('research', lambda: research_web._read_secret_named('BRAVE_SEARCH_API_KEY')),
    ('role-kie', ROLE_KIE._load_api_key),
    ('render-kie', RENDER_KIE._load_api_key),
]
KEY = 'sk-or-v1-Q7w9E2r4T6y8U1i3O5p7A9s2D4f6G8h1J3k5L7z9'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(os, 'environ', {})
    home = tmp_path / 'foreign-home'
    selected = tmp_path / "selected client's root"
    workspace = tmp_path / 'selected workspace'
    home.mkdir()
    selected.mkdir()
    workspace.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('OPENCLAW_ROOT', str(selected))
    monkeypatch.setenv('OPENCLAW_WORKSPACE_PATH', str(workspace))
    monkeypatch.setenv('OPENCLAW_WORKSPACE_ROOT', str(workspace))
    monkeypatch.setattr(model_router, '_SECRET_HELPER_MOD', None)
    monkeypatch.setattr(model_router, '_SECRET_HELPER_TRIED', False)
    monkeypatch.setattr(oc_paths, 'VPS_ROOT', tmp_path / 'unrelated-data/.openclaw')
    foreign_stores = [home / '.openclaw/secrets/.env', home / '.openclaw/workspace/.env', home / 'clawd/secrets/.env', oc_paths.VPS_ROOT / 'secrets/.env']
    for store in foreign_stores:
        write_store(store, 'foreign-credential-must-never-be-read-0123456789')
    original_read = Path.read_text
    def guarded_read(path, *args, **kwargs):
        assert path not in foreign_stores, 'reader attempted a foreign client credential store'
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', guarded_read)
    return selected, workspace, foreign_stores


def write_store(path, key):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(name + '=' + key for name in ['OPENROUTER_API_KEY', 'BRAVE_SEARCH_API_KEY', 'KIE_API_KEY']) + '\n')


@pytest.mark.parametrize('name,reader', READERS)
@pytest.mark.parametrize('platform', ['mac', 'vps'])
def test_actual_readers_use_selected_store(client, monkeypatch, name, reader, platform):
    selected, _, _ = client
    monkeypatch.setenv('OPENCLAW_PLATFORM', platform)
    write_store(selected / 'secrets/.env', KEY)
    assert reader() == (True if name == 'router' else KEY)


@pytest.mark.parametrize('name,reader', READERS)
def test_missing_selected_credentials_never_borrow_home_clawd_or_data(client, name, reader):
    if name.endswith('kie'):
        with pytest.raises(SystemExit) as caught:
            reader()
        assert caught.value.code == 2
    else:
        assert reader() is (False if name == 'router' else None)


@pytest.mark.parametrize('name,reader', READERS)
@pytest.mark.parametrize('invalid', ['foreign-override', 'conflicting-root', 'conflicting-workspace'])
def test_invalid_pins_fail_before_actual_foreign_file_reads(client, monkeypatch, name, reader, invalid):
    selected, workspace, foreign = client
    write_store(selected / 'secrets/.env', KEY)
    if invalid == 'foreign-override':
        monkeypatch.setenv('OPENCLAW_SECRETS', str(foreign[0]))
    elif invalid == 'conflicting-root':
        monkeypatch.setenv('OC_CONFIG', str(foreign[0].parents[1]))
    else:
        monkeypatch.setenv('OPENCLAW_WORKSPACE_ROOT', str(workspace / 'different'))
    with pytest.raises(ValueError):
        reader()


@pytest.mark.parametrize('name,reader', READERS)
def test_missing_path_authority_never_falls_back_to_foreign_stores(client, monkeypatch, name, reader):
    def unavailable(*args, **kwargs):
        raise ImportError('fixture missing selected-client authority')
    monkeypatch.setattr(oc_paths, 'secrets_env_candidates', unavailable)
    with pytest.raises(ImportError):
        reader()
