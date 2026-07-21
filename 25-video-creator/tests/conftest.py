import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def skill_root():
    configured = os.environ.get("SKILL25_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def load_script(skill_root):
    def load(name):
        path = skill_root / "scripts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"skill25_{name}", path)
        module = importlib.util.module_from_spec(spec)
        # Current origin/main has an unresolved runtime annotation in add_music.py.
        # Seed only that annotation name so the regression reaches and measures the
        # silent missing-audio behavior under review instead of failing at import.
        if name == "add_music":
            module.AudioFileClip = object
        spec.loader.exec_module(module)
        return module

    return load
