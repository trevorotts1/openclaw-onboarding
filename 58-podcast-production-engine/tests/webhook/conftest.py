"""Pytest wiring for the independent webhook layer tests.

System under test (SUT) resolution, in order:

  1. If the environment variable PODCAST_WEBHOOK_SUT names an importable module,
     that module is the SUT. It MUST expose map_payload, compute_job_key, Ledger,
     and intake with the signatures documented in README.md. A failed import here
     is a hard error (never a silent fallback), so a misconfigured binding is loud.
  2. Else, if a module named podcast_webhook_sut is importable (a thin adapter the
     merge phase may drop on sys.path pointing at the shipped mapper), it is the SUT.
  3. Else, the spec_reference oracle in this directory is the SUT.

This is what makes the suite the independent check on the webhook-layer slice
(W1.16): the same tests run against the shipped mapper when it is bound, and
against the executable specification otherwise. If the shipped mapper diverges from
the contract, the tests fail.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from types import SimpleNamespace

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIXTURES = os.path.join(_HERE, "fixtures")

# Make `import spec_reference` and any adapter module resolvable.
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_REQUIRED_NAMES = ("map_payload", "compute_job_key", "Ledger", "intake")


def _bind(module, name):
    missing = [n for n in _REQUIRED_NAMES if not hasattr(module, n)]
    if missing:
        raise RuntimeError(
            "SUT module '" + name + "' is missing required names: " + ", ".join(missing)
        )
    return SimpleNamespace(
        name=name,
        map_payload=module.map_payload,
        compute_job_key=module.compute_job_key,
        Ledger=module.Ledger,
        intake=module.intake,
    )


def _resolve_sut():
    override = os.environ.get("PODCAST_WEBHOOK_SUT")
    if override:
        module = importlib.import_module(override)
        return _bind(module, override + " (env override)")
    try:
        module = importlib.import_module("podcast_webhook_sut")
        return _bind(module, "podcast_webhook_sut (adapter)")
    except ModuleNotFoundError:
        pass
    module = importlib.import_module("spec_reference")
    return _bind(module, "spec_reference oracle")


_SUT = _resolve_sut()


def pytest_report_header(config):
    return "podcast webhook SUT: " + _SUT.name


@pytest.fixture(scope="session")
def sut():
    return _SUT


@pytest.fixture(scope="session")
def fixtures_dir():
    return _FIXTURES


@pytest.fixture(scope="session")
def load_fixture():
    def _load(name):
        with open(os.path.join(_FIXTURES, name), "r", encoding="utf-8") as handle:
            return json.load(handle)
    return _load


@pytest.fixture
def make_ledger(sut, tmp_path):
    """Return a factory for throwaway ledgers rooted under a fresh tmp dir."""
    counter = {"n": 0}

    def _factory(subdir=None):
        counter["n"] += 1
        name = subdir or ("ledger_" + str(counter["n"]))
        return sut.Ledger(os.path.join(str(tmp_path), name))
    return _factory


# The Location ID configured for this synthetic client at onboarding. The tenant
# check compares a payload's mapped location_id against this value.
TENANT_LOCATION_ID = "Loc0Abc123Xyz789"


@pytest.fixture(scope="session")
def tenant_location_id():
    return TENANT_LOCATION_ID
