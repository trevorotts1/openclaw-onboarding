"""pytest fixture for the final_assembler suites that take a tmp_root argument.

The suites also run as plain scripts (they build tmp_root themselves in main());
under pytest this supplies the same thing.
"""
import pytest


@pytest.fixture
def tmp_root(tmp_path):
    return str(tmp_path)
