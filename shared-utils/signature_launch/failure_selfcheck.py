"""Runnable self-check for contained unit failure. ``python3 failure_selfcheck.py``.

Asserts, does not print a pass banner that could hide a skip: each check calls
``assert`` and the final line is the package record it proved.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # .../shared-utils

from signature_launch.package import build_package  # noqa: E402
from signature_launch.failure import DONE, FAILED, run_units  # noqa: E402


def _runner(unit_id, payload):
    if payload.get("boom"):
        raise RuntimeError("unit %s exploded" % unit_id)
    return payload.get("value", unit_id)


# 1. A failing middle unit stops nothing: all three attempted, order kept.
units = {"a": {"value": 1}, "b": {"boom": True}, "c": {"value": 3}}
package = build_package(units, _runner)
assert [u["unit_id"] for u in package["units"]] == ["a", "b", "c"]
assert package["units"][0]["status"] == DONE
assert package["units"][2]["status"] == DONE
assert package["units"][2]["value"] == 3
assert package["units"][1]["status"] == FAILED
assert package["units"][1]["error"] == {
    "type": "RuntimeError", "message": "unit b exploded",
}
assert package["completed_units"] == ["a", "c"]
assert package["failed_units"] == ["b"]
assert package["counts"] == {"total": 3, "done": 2, "failed": 1}

# 2. The package marks itself failed, never done, when any unit failed.
assert package["status"] == FAILED
assert package["ok"] is False

# 3. All units done -> package done. No failure invented.
clean = build_package({"a": {}, "b": {}}, _runner)
assert clean["status"] == DONE and clean["ok"] is True
assert clean["counts"] == {"total": 2, "done": 2, "failed": 0}

# 4. Every unit failed -> still every unit attempted, package failed.
all_bad = build_package({"a": {"boom": True}, "b": {"boom": True}}, _runner)
assert all_bad["counts"]["failed"] == 2
assert all_bad["status"] == FAILED

# 5. An interrupt is not a unit failure; it propagates and stops the run.
def _interrupting(unit_id, payload):
    raise KeyboardInterrupt

try:
    run_units({"a": {}, "b": {}}, _interrupting)
except KeyboardInterrupt:
    pass
else:
    raise AssertionError("KeyboardInterrupt was wrongly contained")

# 6. Package record is JSON-safe as written.
json.dumps(package)
print(json.dumps({
    "selfcheck": "ok",
    "package_status": package["status"],
    "failed_units": package["failed_units"],
}, sort_keys=True))
