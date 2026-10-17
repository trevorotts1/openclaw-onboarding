#!/usr/bin/env python3
"""S06-09 offline parity tests (Skill 06).

The three parity checks the S06-09 build adds (governing brief step 6):

  (i)   Fresh-isolated-install simulation. With every OpenClaw-shaped
        path absent (HOME pointed at an empty directory; OPENCLAW_HOME,
        OPENCLAW_SKILLS_DIR and every harness marker unset), the probe
        records its honest fallbacks (runtime unknown with evidence
        "none"; storage on the skill working dir, not persistent; the
        managed-browser lane unavailable), no exercised import requires
        ~/.openclaw to exist, and the graceful-degradation contracts
        hold: model_router imports with its sovereignty delegate absent
        and its internal Anthropic guard still fires; ghl_media loads
        its KIE enforcer from the embedded copy; the shared secret
        resolver resolves nothing and its failure text names the
        sources checked.
  (ii)  Cross-copy parity over code and docs ONLY, never evidence
        records: the shipped version pair agrees (SKILL.md
        metadata.version equals skill-version.txt, enforced by running
        scripts/check-version-drift.py; the CHANGELOG top heading must
        parse but is deliberately NOT part of the comparison), and the
        embedded KIE enforcer copy is byte-identical to the repo
        shared-utils copy when that second copy ships in the tree
        (when it does not, the fresh-install leg (i) is the covering
        check and this one skips).
  (iii) Registry/docs consistency (gap 9): every engine registered in
        funnel-engines/registry.json appears as a row of the Registered
        engines table in funnel-engines/README.md carrying its skill
        and entry path, every table row names a registered engine, and
        a skeleton-readiness engine's row states that readiness.

HERMETIC: subprocesses run under a scrubbed environment and a temporary
HOME; no network, no browser, no secrets.

Run:
    python3 -m pytest tests/test_s06_09_parity.py -v
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.normpath(os.path.join(_HERE, ".."))
_TOOLS = os.path.join(_SKILL_DIR, "tools")
_TIMEOUT = 120  # every subprocess call gets a timeout (house rule)


def _scrubbed_env(home):
    """A minimal environment: no harness marker, no OpenClaw variable,
    HOME pointed at an empty directory, and a PATH carrying neither the
    openclaw nor the agent-browser CLI (a fresh box has neither; the
    suite's own test shim must not leak an install into the simulation).
    """
    path = os.pathsep.join(
        [os.path.dirname(sys.executable), "/usr/bin", "/bin"])
    return {"PATH": path, "HOME": str(home)}


# ══════════════════════════════════════════════════════════════════════════════
# (i) Fresh-isolated-install simulation
# ══════════════════════════════════════════════════════════════════════════════

def test_isolated_probe_records_honest_fallbacks(tmp_path):
    """On a box with no OpenClaw-shaped path, the probe's capability
    record says unknown / fallback, never a borrowed positive."""
    out = tmp_path / "skill6-capability.json"
    home = tmp_path / "home"
    home.mkdir()
    proc = subprocess.run(
        [sys.executable, os.path.join(_TOOLS, "capability_probe.py"),
         "--out", str(out)],
        cwd=str(tmp_path), env=_scrubbed_env(home),
        capture_output=True, text=True, timeout=_TIMEOUT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["environmentCapabilities"]["runtime"]["name"] == "unknown"
    assert doc["environmentCapabilities"]["runtime"]["evidence"] == "none"
    assert doc["lanes"]["openclaw_managed_browser"]["extension"][
        "installed"] is False
    assert doc["selectedLane"] != "openclaw_managed_browser"
    # The standalone environment-capabilities record lands beside the
    # capability JSON and carries the same honest fallbacks.
    caps_path = tmp_path / "environment-capabilities.json"
    assert caps_path.is_file()
    caps = json.loads(caps_path.read_text(encoding="utf-8"))
    assert caps["runtime"]["name"] == "unknown"
    assert caps["storage"]["source"] == "skill-working-dir"
    assert caps["storage"]["persistentRoot"] == os.path.join(
        _SKILL_DIR, "working")
    assert caps["apiOperations"]["verification"] == "declared-not-live-proven"


def test_isolated_imports_degrade_without_openclaw(tmp_path):
    """Imports exercised on an isolated install (a copy of tools/ with
    no repo parent and no ~/.openclaw) degrade exactly as documented:
    the model router loses only its sovereignty delegate, the media
    module falls back to its embedded enforcer copy, and the secret
    resolver resolves nothing while naming its sources."""
    tools_copy = tmp_path / "iso" / "skill" / "tools"
    tools_copy.mkdir(parents=True)
    for name in os.listdir(_TOOLS):
        if name.endswith(".py"):
            shutil.copy2(os.path.join(_TOOLS, name), tools_copy / name)
    home = tmp_path / "home"
    home.mkdir()
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(tools_copy)!r})\n"
        "import model_router\n"
        "assert model_router._ams is None, 'sovereignty delegate should be absent'\n"
        "try:\n"
        "    model_router.assert_no_anthropic("
        "[{'rung': 1, 'provider': 'anthropic', 'models': []}])\n"
        "except model_router.AnthropicModelError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('internal Anthropic guard did not fire')\n"
        "import ghl_media\n"
        "mod = ghl_media._load_kie_prompt_enforcer()\n"
        "assert mod.__file__.endswith('_kie_prompt_enforcer_embedded.py'), "
        "mod.__file__\n"
        "import ghl_secret_resolver as resolver\n"
        "res = resolver.attempt_resolution({}, aliases=['GHL_LOCATION_ID'], "
        "stores=[], search_stores=False)\n"
        "assert res.value == '', res\n"
        "msg = resolver.failure_message('location id', "
        "aliases=['GHL_LOCATION_ID'], stores=[])\n"
        "assert 'GHL_LOCATION_ID' in msg\n"
        "print('isolated imports OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], cwd=str(tmp_path),
        env=_scrubbed_env(home), capture_output=True, text=True,
        timeout=_TIMEOUT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "isolated imports OK" in proc.stdout


# ══════════════════════════════════════════════════════════════════════════════
# (ii) Cross-copy parity (code/docs only, never evidence records)
# ══════════════════════════════════════════════════════════════════════════════

def test_version_pair_agrees_via_drift_script():
    """The pair invariant, enforced by the tree's own drift script:
    SKILL.md metadata.version equals skill-version.txt."""
    proc = subprocess.run(
        [sys.executable,
         os.path.join(_SKILL_DIR, "scripts", "check-version-drift.py"),
         _SKILL_DIR],
        cwd=_SKILL_DIR, capture_output=True, text=True, timeout=_TIMEOUT)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_changelog_heading_parses_but_is_not_the_pair():
    """The CHANGELOG top heading is an independent namespace: it must
    parse (the drift script requires that much) and is deliberately
    never compared against the shipped pair."""
    text = open(os.path.join(_SKILL_DIR, "CHANGELOG.md"),
                encoding="utf-8").read()
    assert re.search(r"^## \[v\d+\.\d+\.\d+\]", text, re.M), (
        "CHANGELOG.md top version heading does not parse")
    pair = open(os.path.join(_SKILL_DIR, "skill-version.txt"),
                encoding="utf-8").read().strip()
    assert re.fullmatch(r"v\d+\.\d+\.\d+", pair), (
        "skill-version.txt does not carry a clean version string")


def test_embedded_enforcer_matches_second_copy_when_present():
    """Cross-copy parity for the one file this tree ships twice: the
    embedded KIE enforcer beside ghl_media.py and the repo shared-utils
    copy it was embedded from must be byte-identical. Code only; the
    guard below fails the test if either path ever points at an
    evidence record."""
    embedded = os.path.join(_TOOLS, "_kie_prompt_enforcer_embedded.py")
    second = os.path.normpath(os.path.join(
        _SKILL_DIR, "..", "shared-utils", "kie_prompt_enforcer.py"))
    for path in (embedded, second):
        assert "evidence" not in os.path.normpath(path).split(os.sep), (
            "cross-copy parity compares code/docs only, never evidence records")
    if not os.path.isfile(second):
        pytest.skip("no second distribution copy of the enforcer in this tree")

    def digest(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest()

    assert digest(embedded) == digest(second), (
        "embedded KIE enforcer copy has drifted from the shared-utils copy")


# ══════════════════════════════════════════════════════════════════════════════
# (iii) Registry/docs consistency (gap 9)
# ══════════════════════════════════════════════════════════════════════════════

def _registered_table_rows():
    readme = open(os.path.join(_SKILL_DIR, "funnel-engines", "README.md"),
                  encoding="utf-8").read()
    section = readme.split("## Registered engines", 1)[1]
    section = section.split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if line.startswith("| `"):
            rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows


def test_registry_and_readme_table_agree():
    """funnel-engines/README.md's Registered engines table and
    funnel-engines/registry.json must name the same engines, with the
    registry's skill and entry path on each row, and a skeleton
    engine's readiness stated on its row. Disagreement fails."""
    registry = json.loads(open(os.path.join(
        _SKILL_DIR, "funnel-engines", "registry.json"),
        encoding="utf-8").read())
    engines = registry["engines"]
    row_by_id = {}
    for cells in _registered_table_rows():
        m = re.fullmatch(r"`([^`]+)`", cells[0])
        assert m, f"README table row does not name an engine id: {cells[0]!r}"
        row_by_id[m.group(1)] = " | ".join(cells)
    assert set(row_by_id) == {e["id"] for e in engines}, (
        "README Registered engines table and registry.json disagree "
        "on the registered engine set")
    for engine in engines:
        row_text = row_by_id[engine["id"]]
        assert engine["skill"] in row_text, engine["id"]
        assert engine["entry"] in row_text, engine["id"]
        readiness = (engine.get("readiness") or {}).get("status", "")
        if readiness == "skeleton":
            assert "skeleton" in row_text.lower(), (
                f"skeleton engine {engine['id']} row does not state "
                "its readiness")
