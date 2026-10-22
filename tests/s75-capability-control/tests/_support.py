import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(UNIT_ROOT))

# The production module lives in the skill tree; the tests live here. One
# implementation, two consumers: this is the only path wiring between them.
SKILL_CORE = os.path.join(REPO_ROOT, "75-drama-song-ad-factory", "scripts", "core")

for _p in (UNIT_ROOT, SKILL_CORE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json  # noqa: E402

FIXTURES = os.path.join(UNIT_ROOT, "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as fh:
        return json.load(fh)
