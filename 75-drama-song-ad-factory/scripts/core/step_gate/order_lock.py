"""order_lock.py - N-38: reference pictures, then keyframes, then clips.

A step refuses to start until the step before it has passed the style check.
Reads and writes only control/style-checks.json inside the run folder.
Stdlib only.

ponytail: the style verdict is one boolean per step. Split it per picture when
a run needs to open a step with only some pictures passed.
"""
import json
import os

ORDER = ("reference", "keyframe", "clip")
CODE = "ORDER_SKIPPED"


class OrderSkipped(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _path(run_dir):
    return os.path.join(os.path.abspath(run_dir), "control", "style-checks.json")


def load_style_passes(run_dir):
    """{"reference": bool, "keyframe": bool, "clip": bool} from the run folder."""
    try:
        with open(_path(run_dir), "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    passed = doc.get("passed", {}) if isinstance(doc, dict) else {}
    return {step: bool(passed.get(step)) for step in ORDER}


def _save(run_dir, passed):
    path = _path(run_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {"schema": "blackceo.style-checks/v1",
           "passed": {k: bool(passed.get(k)) for k in ORDER}}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def mark_style_passed(run_dir, step, passed=True):
    if step not in ORDER:
        raise OrderSkipped(CODE, "unknown step %r (known: %s)" % (step, ", ".join(ORDER)))
    current = load_style_passes(run_dir)
    current[step] = bool(passed)
    _save(run_dir, current)
    return current


def check_order(step, passed):
    """The step may start only when every earlier step passed the style check."""
    if step not in ORDER:
        return {"ok": False, "code": CODE,
                "detail": "unknown step %r" % step, "missing": []}
    idx = ORDER.index(step)
    missing = [s for s in ORDER[:idx] if not (passed or {}).get(s)]
    if missing:
        return {"ok": False, "code": CODE,
                "detail": "%s cannot start: %s has not passed the style check"
                          % (step, " and ".join(missing)),
                "missing": missing}
    return {"ok": True, "code": None, "detail": None, "missing": []}


def require(step, passed):
    """check_order, raised. Returns True when the step may start."""
    result = check_order(step, passed)
    if not result["ok"]:
        raise OrderSkipped(result["code"], result["detail"])
    return True


def begin_step(run_dir, step):
    """Read the run's style passes and refuse a skipped order, or allow it."""
    return check_order(step, load_style_passes(run_dir))
