#!/usr/bin/env python3
"""test_department_runtime.py -- regression tests for the Wave 5 canary gap:

    the "Anthology Producer" department board renders in Command Center but NO
    OpenClaw agent runtime is wired to it, so every card lands and immediately
    STICKS in "Blocked" with reason no_specialist_runtime ("No OpenClaw runtime
    for 'Anthology Producer'. Wire ~/.openclaw/agents/<dept-slug>/ ...").

These tests prove provision-anthology-client.sh's wire_department_runtime step
materializes exactly the runtime the Command Center dispatch check looks for
(the openclaw.json agents.list[] dept-<slug> entry + ~/.openclaw/agents/dept-<slug>/
dir), against a HERMETIC / mocked dispatch gate -- a synthetic board card BLOCKS
before wiring and RELEASES after. No live gateway, no live Command Center, no
credential value, no Anthropic identifier. Python 3 stdlib only.

Run: python3 -m pytest 59-anthology-engine/tests/test_department_runtime.py -q
 or: python3 59-anthology-engine/tests/test_department_runtime.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PROVISION = SKILL_DIR / "scripts" / "provision-anthology-client.sh"
DEPT_SLUG = "anthology"

# Anthropic-family id shapes assembled from fragments; no banned literal appears.
_A = "anthro" + "pic"
_C = "clau" + "de-"
BANNED = re.compile(_C + r"|" + _A + r"/|us\." + _A + r"\.", re.I)


def _mock_cc_dispatch(oc_root: Path, slug: str) -> str:
    """A HERMETIC stand-in for the Command Center dispatch gate. Returns
    "no_specialist_runtime" (the card would stick in Blocked) unless an OpenClaw
    runtime exists for the department: an agents.list[] entry whose id resolves the
    dept slug AND its ~/.openclaw/agents/dept-<slug>/ dir. This mirrors the checks
    register-routing-dept.py (agent id contains the slug) and materialize-dept-
    agents.sh (agentDir) already encode -- i.e. exactly what the runtime dispatch
    resolves before releasing a department's cards."""
    cfg_path = oc_root / "openclaw.json"
    if not cfg_path.is_file():
        return "no_specialist_runtime"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    aid = "dept-%s" % slug
    agents = (cfg.get("agents") or {}).get("list") or []
    has_entry = any(isinstance(a, dict) and (a.get("id") == aid or slug in str(a.get("id", "")))
                    for a in agents)
    has_dir = (oc_root / "agents" / aid).is_dir()
    return "released" if (has_entry and has_dir) else "no_specialist_runtime"


def _wire(oc_root: Path):
    """Invoke the department-runtime wiring step against a TEMP OpenClaw root."""
    env = dict(os.environ)
    env["ANTHOLOGY_OC_ROOT"] = str(oc_root)
    return subprocess.run(["bash", str(PROVISION), "--wire-department"],
                          capture_output=True, text=True, timeout=60, env=env)


def _write_cfg(oc_root: Path, extra_agents=None):
    oc_root.mkdir(parents=True, exist_ok=True)
    agents = [
        {"id": "main", "name": "Main", "workspace": "/x/main"},
        {"id": "dept-marketing", "name": "Chief Marketing Officer", "workspace": "/x/mkt"},
    ]
    if extra_agents:
        agents.extend(extra_agents)
    cfg = {"agents": {"defaults": {"model": "ollama/kimi-k2.6:cloud"}, "list": agents}}
    (oc_root / "openclaw.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
def test_card_blocks_before_wiring_and_releases_after():
    with tempfile.TemporaryDirectory() as td:
        oc = Path(td) / ".openclaw"
        _write_cfg(oc)

        # BEFORE: a synthetic card would stick in Blocked (no_specialist_runtime).
        assert _mock_cc_dispatch(oc, DEPT_SLUG) == "no_specialist_runtime"

        r = _wire(oc)
        assert r.returncode == 0, "wire step failed:\n%s\n%s" % (r.stdout, r.stderr)

        # AFTER: the same dispatch check now RELEASES the department.
        assert _mock_cc_dispatch(oc, DEPT_SLUG) == "released", \
            "card still blocked after wiring:\n%s" % r.stderr

        # The exact runtime the CC message asks for exists on disk.
        assert (oc / "agents" / ("dept-%s" % DEPT_SLUG)).is_dir()

        cfg = json.loads((oc / "openclaw.json").read_text(encoding="utf-8"))
        entry = next(a for a in cfg["agents"]["list"] if a.get("id") == "dept-%s" % DEPT_SLUG)
        assert entry["name"] == "Anthology Producer"
        assert entry["agentDir"].endswith("agents/dept-%s" % DEPT_SLUG)
        # memorySearch schema matches materialize-dept-agents.sh (multimodal off,
        # fallback openai) so the dept agent is schema-valid and memory-safe.
        assert entry["memorySearch"]["multimodal"]["enabled"] is False
        assert entry["memorySearch"]["fallback"] == "openai"


def test_wiring_preserves_sibling_agents():
    with tempfile.TemporaryDirectory() as td:
        oc = Path(td) / ".openclaw"
        _write_cfg(oc)
        assert _wire(oc).returncode == 0
        ids = [a.get("id") for a in json.loads((oc / "openclaw.json")
                                               .read_text(encoding="utf-8"))["agents"]["list"]]
        # Every pre-existing agent survives; only the dept agent is added.
        assert "main" in ids and "dept-marketing" in ids and "dept-%s" % DEPT_SLUG in ids


def test_wiring_is_idempotent_no_duplicate():
    with tempfile.TemporaryDirectory() as td:
        oc = Path(td) / ".openclaw"
        _write_cfg(oc)
        assert _wire(oc).returncode == 0
        assert _wire(oc).returncode == 0          # re-run
        ids = [a.get("id") for a in json.loads((oc / "openclaw.json")
                                               .read_text(encoding="utf-8"))["agents"]["list"]]
        assert ids.count("dept-%s" % DEPT_SLUG) == 1, "re-run duplicated the dept agent: %r" % ids


def test_command_center_absent_holds_not_crashes():
    with tempfile.TemporaryDirectory() as td:
        oc = Path(td) / ".openclaw"
        oc.mkdir(parents=True)                     # no openclaw.json inside
        r = _wire(oc)
        # HELD (exit 3), never a crash and never a false success.
        assert r.returncode == 3, "CC-absent must HELD (exit 3), got %d:\n%s" % (r.returncode, r.stderr)
        assert _mock_cc_dispatch(oc, DEPT_SLUG) == "no_specialist_runtime"


def test_wired_config_has_no_anthropic_id_and_no_secret_value():
    with tempfile.TemporaryDirectory() as td:
        oc = Path(td) / ".openclaw"
        _write_cfg(oc)
        assert _wire(oc).returncode == 0
        blob = (oc / "openclaw.json").read_text(encoding="utf-8")
        assert not BANNED.search(blob), "wired openclaw.json carries an Anthropic-family id"
        # The wiring writes only labels/paths -- never a credential-shaped 64-hex value.
        assert not re.search(r"[0-9a-f]{64}", blob), "wired config carries a secret-shaped value"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("  [PASS] %s" % fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [FAIL] %s -- %s" % (fn.__name__, exc))
    print("test_department_runtime: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES", len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
