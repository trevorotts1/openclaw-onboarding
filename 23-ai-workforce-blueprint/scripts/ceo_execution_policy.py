"""Locate the canonical policy in repo, installed-skill and flattened layouts.

This small loader travels with the complete Skill 23 scripts tree. Policy text
remains in the installed shared-utils tree; no operator home or foreign-client
workspace is searched or inferred.
"""
import importlib.util
from pathlib import Path

_candidates = []
for _root in list(Path(__file__).resolve().parents)[:3]:
    _candidates.extend((_root / 'shared-utils/ceo_execution_policy.py',
                        _root / 'skills/shared-utils/ceo_execution_policy.py'))
for _path in _candidates:
    if _path.is_file() and _path.resolve() != Path(__file__).resolve():
        _spec = importlib.util.spec_from_file_location('_onb_canonical_ceo_policy', _path)
        _policy = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_policy)
        block = _policy.block
        upgrade = _policy.upgrade
        registry_rows = _policy.registry_rows
        POLICY = _policy.POLICY
        break
else:
    raise ImportError('Missing installed shared-utils/ceo_execution_policy.py; refresh the complete shared-utils tree')
