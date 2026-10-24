"""The prompt-policy registry of record is read from the shared tree only.

A copy shipped inside the skill folder would let the skill certify its own
citations, so it must never be a resolution candidate for this artifact.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import launch_context  # noqa: E402

REGISTRY = {"entries": [{"policy_id": "p1", "entry_status": "active"}]}


def _write(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(REGISTRY), encoding="utf-8")


def _rel():
    return launch_context.PROMPT_POLICY_REGISTRY_REF


def test_registry_inside_the_skill_folder_is_never_read(tmp_path):
    skill = tmp_path / "skill"
    _write(skill / _rel())
    with pytest.raises(launch_context.LaunchContextError):
        launch_context._registry_policy_ids(str(skill))


def test_registry_in_the_shared_tree_is_read(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    _write(tmp_path / _rel())
    assert launch_context._registry_policy_ids(str(skill)) == {"p1"}


def test_shared_tree_symlink_back_into_the_skill_is_refused(tmp_path):
    skill = tmp_path / "skill"
    _write(skill / _rel())
    (tmp_path / "shared-utils").symlink_to(skill / "shared-utils",
                                           target_is_directory=True)
    with pytest.raises(launch_context.LaunchContextError):
        launch_context._registry_policy_ids(str(skill))


def test_shared_registry_symlink_to_a_skill_file_is_refused(tmp_path):
    skill = tmp_path / "skill"
    own = skill / "vendored-registry.json"
    _write(own)
    shared = tmp_path / _rel()
    shared.parent.mkdir(parents=True)
    shared.symlink_to(own)
    with pytest.raises(launch_context.LaunchContextError):
        launch_context._registry_policy_ids(str(skill))


def test_vendored_copy_does_not_shadow_a_missing_shared_registry(tmp_path):
    skill = tmp_path / "skill"
    _write(skill / "repo-integration" / "shared" / Path(_rel()).name)
    with pytest.raises(launch_context.LaunchContextError):
        launch_context._registry_policy_ids(str(skill))
