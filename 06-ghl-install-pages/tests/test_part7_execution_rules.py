#!/usr/bin/env python3
"""MOCK-only meta tests — fix-plan Part 7 execution rules (Skill 06).

Each test PROVES that one Part 7 rule has concrete enforcement by either:
  (a) running an existing hermetic suite's key cases as a subprocess pytest
      invocation (mock-only, no network, timeout=120, rc asserted), or
  (b) asserting the doctrine text that enforces the rule still stands in the
      skill docs (INSTALL.md / SKILL.md / QC.md) or the QC script wiring.

This file adds NO new enforcement logic and edits NO other test — it is a
guard-rail over the already-shipped fail-closed suites:
  * tests/test_capability_probe.py           (lane selection, fail-closed, secrets)
  * tests/test_iframe_router.py              (wrong-frame / stale / ambiguous fail)
  * tests/test_cua_last_resort_adapter.py    (CUA never-default, opt-in gate)
  * tests/test_browser_manager_capability_wire.py (receipt freshness STATE_WAITING)
  * tests/test_openclaw_browser_adapter.py   (Lane-2 75 refusals, CLI-absent 64)

Rules under guard (fix-plan lines 388-400):
  1. Do not require OpenClaw 2.0 or CUA for Skill 6 to be considered installed
  2. Do not remove agent-browser PRIMARY until Lane 2 is proven equivalent on GHL
  3. Do not silent-fallback CUA
  4. Fail closed when zero browser lanes
  5. Preserve TOKEN-ONLY default auth
  6. Preserve FAB-QC >= 8.5 and human publish gate
  7. Hermetic tests for probe selection + iframe wrong-frame fail  (the suites above)
  8. Never weaken verify/receipt fail-closed behavior to "make green"

HERMETIC: every subprocess here is a pytest run of a mock-only suite or a
`--static` guard read; no network, no browser, no secrets. Doc-content checks
read the committed files in this skill directory only.

Run:
    python3 -m pytest tests/test_part7_execution_rules.py -v
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.normpath(os.path.join(_HERE, ".."))
_TESTS_DIR = _HERE
_TIMEOUT = 120  # every subprocess call gets a timeout (house rule)

_INSTALL_MD = os.path.join(_SKILL_DIR, "INSTALL.md")
_SKILL_MD = os.path.join(_SKILL_DIR, "SKILL.md")
_QC_MD = os.path.join(_SKILL_DIR, "QC.md")
_GUARD_MD = os.path.join(_SKILL_DIR, "scripts", "guard-ghl-method-decision.sh")
_GUARD_VU = os.path.join(
    _SKILL_DIR, "scripts", "guard-ghl-verify-unfakeable.sh")
_QC_SH = os.path.join(_SKILL_DIR, "qc-ghl-install-pages.sh")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _pytest(*args):
    """Run a subset of an existing suite; return the CompletedProcess."""
    cmd = [sys.executable, "-m", "pytest"] + list(args) + ["-q"]
    return subprocess.run(
        cmd, cwd=_SKILL_DIR, capture_output=True, text=True, timeout=_TIMEOUT)


# ══════════════════════════════════════════════════════════════════════════════
# Rule 1 — OpenClaw 2.0 / CUA are NOT install requirements
# ══════════════════════════════════════════════════════════════════════════════

def test_rule1_agent_browser_only_box_is_qc_passable():
    """An agent-browser-only host gets full capability: lane selected, zero
    blockers, CUA/managed lane NOT required (probe suite, 9.6 table)."""
    proc = _pytest("tests/test_capability_probe.py",
                   "-k", "agent_browser_only or lane_selection")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rule1_install_step1_does_not_require_openclaw_2x_or_cua():
    """INSTALL.md Step 1 must not name OpenClaw 2.x or CUA as an install gate.
    Mentions are allowed ONLY in the negative/doctrine form (the literal
    'Do NOT require OpenClaw 2.0 or CUA' sentence and the pre-2.0 lane row)."""
    src = _read(_INSTALL_MD)
    # The pre-2.0 row is REQUIRED to exist: an old OpenClaw does not block.
    assert "Pre-2.0 OpenClaw + agent-browser" in src, (
        "INSTALL.md lost its pre-2.0-OpenClaw lane row (rule 1)")
    # The doctrine sentence is REQUIRED to exist (the guard text itself).
    assert re.search(
        r"Do NOT require OpenClaw 2\.0 or CUA", src), (
        "INSTALL.md lost the 'Do NOT require OpenClaw 2.0 or CUA' doctrine")
    # The Prerequisites Verification list (the actual install gate) must not
    # demand CUA or OpenClaw 2.x. Extract that list and assert absence.
    block = src.split("## Prerequisites Verification", 1)[1]
    block = block.split("## Step 1:", 1)[0]
    assert not re.search(r"\bCUA\b", block), (
        "INSTALL.md prerequisites list names CUA as required (rule 1)")
    assert not re.search(r"OpenClaw\s*(≥|>=)?\s*2\.\d", block), (
        "INSTALL.md prerequisites list requires OpenClaw 2.x (rule 1)")


# ══════════════════════════════════════════════════════════════════════════════
# Rule 2 — agent-browser stays PRIMARY until Lane 2 is proven equivalent
# ══════════════════════════════════════════════════════════════════════════════

def test_rule2_lane_selection_priority_keeps_agent_browser_primary():
    """Lane 1 (agent_browser) still heads the 9.6 priority table; lane 2 is
    only reached when agent-browser is absent."""
    proc = _pytest("tests/test_capability_probe.py", "-k", "lane_selection")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rule2_install_names_agent_browser_primary():
    """INSTALL.md Step 1 keeps agent-browser as the PRIMARY lane header, and
    the OpenClaw managed browser stays marked not-yet-PRIMARY (alt/experimental)."""
    src = _read(_INSTALL_MD)
    assert re.search(
        r"Step 1: Set Up the Browser Lane — agent-browser \(PRIMARY\)", src), (
        "INSTALL.md Step 1 no longer names agent-browser PRIMARY (rule 2)")
    assert re.search(
        r"agent-browser \(Vercel Labs\) is the PRIMARY engine", src), (
        "INSTALL.md no longer states agent-browser is the PRIMARY engine (rule 2)")
    # Lane 2 downgrade marker (experimental, not Skill 6 PRIMARY) must remain.
    assert re.search(
        r"not yet wired as Skill 6 PRIMARY", src), (
        "INSTALL.md lost the 'managed browser not yet Skill 6 PRIMARY' marker (rule 2)")


# ══════════════════════════════════════════════════════════════════════════════
# Rule 3 — CUA is never a silent fallback (explicit opt-in only)
# ══════════════════════════════════════════════════════════════════════════════

def test_rule3_cua_last_resort_suite_passes():
    """The full CUA contract suite: gate matrix, request-without-optin exits 75
    with NO receipt, doctrine note tokens."""
    proc = _pytest("tests/test_cua_last_resort_adapter.py")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rule3_existing_session_never_default_without_optin():
    """existing_session lane is also never a silent default (probe suite)."""
    proc = _pytest("tests/test_capability_probe.py", "-k", "existing_session")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rule3_lane2_adapter_refuses_without_gate():
    """Lane-2 adapter refuses with 75 when the capability gate fails and with
    64 when the openclaw CLI is absent — no silent CUA/lane drift."""
    proc = _pytest("tests/test_openclaw_browser_adapter.py",
                   "-k", "cli_absent or cliworks")
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ══════════════════════════════════════════════════════════════════════════════
# Rule 4 — fail closed when zero browser lanes
# ══════════════════════════════════════════════════════════════════════════════

def test_rule4_nothing_present_fails_closed_with_blocker():
    """Bare box -> selectedLane null + no-browser-lane blocker (probe)."""
    proc = _pytest("tests/test_capability_probe.py", "-k", "nothing_present")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rule4_iframe_router_no_lane_fails_closed_pinned_reason():
    """Zero usable iframe lanes -> ok=False with the PINNED reason (router)."""
    proc = _pytest("tests/test_iframe_router.py", "-k", "no_lane")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rule4_install_documented_zero_lane_acceptance():
    """INSTALL.md keeps the Day-0 acceptance line: selectedLane != null is the
    install gate; a zero-lane host is not installable."""
    src = _read(_INSTALL_MD)
    assert re.search(
        r"`selectedLane != null` is the Day-0 acceptance", src), (
        "INSTALL.md lost the selectedLane Day-0 acceptance gate (rule 4)")
    assert re.search(
        r"a host with zero browser lanes is not installable \(fail closed\)", src), (
        "INSTALL.md lost the zero-lane fail-closed sentence (rule 4)")


# ══════════════════════════════════════════════════════════════════════════════
# Rule 5 — TOKEN-ONLY default auth preserved
# ══════════════════════════════════════════════════════════════════════════════

def test_rule5_skill_md_carries_token_only_doctrine():
    """SKILL.md keeps the TOKEN-ONLY (D7) doctrine markers."""
    src = _read(_SKILL_MD)
    assert re.search(r"TOKEN-ONLY \(D7\)", src), (
        "SKILL.md lost the TOKEN-ONLY (D7) doctrine marker (rule 5)")
    assert "refresh-token seed is the only auth path" in src, (
        "SKILL.md lost the 'refresh-token seed is the only auth path' line (rule 5)")


def test_rule5_install_qc_require_token_not_email():
    """INSTALL.md and QC.md must keep the refresh-token as the credential gate
    and must NOT carry GHL_EMAIL as an install REQUIREMENT. (Manual-only
    last-resort mentions are allowed; a prerequisites-list entry is not.)"""
    for path, name in ((_INSTALL_MD, "INSTALL.md"), (_QC_MD, "QC.md")):
        src = _read(path)
        assert "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN" in src, (
            f"{name} lost the refresh-token requirement (rule 5)")
        assert re.search(r"TOKEN-ONLY", src), (
            f"{name} lost the TOKEN-ONLY marker (rule 5)")
    # INSTALL.md prerequisites list must not demand email/password creds.
    src = _read(_INSTALL_MD)
    block = src.split("## Prerequisites Verification", 1)[1]
    block = block.split("## Step 1:", 1)[0]
    assert not re.search(r"GHL_(EMAIL|PASSWORD)", block), (
        "INSTALL.md prerequisites list requires GHL_EMAIL/GHL_PASSWORD (rule 5)")


def test_rule5_probe_never_leaks_secret_values():
    """Probe output JSON carries secret booleans only, never values (P0)."""
    proc = _pytest("tests/test_capability_probe.py", "-k", "no_secret_values")
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ══════════════════════════════════════════════════════════════════════════════
# Rule 6 — FAB-QC >= 8.5 threshold and human publish gate preserved
# ══════════════════════════════════════════════════════════════════════════════

def test_rule6_fab_qc_threshold_still_named():
    """SKILL.md and QC.md still carry the FAB-QC >= 8.5 build-quality gate."""
    src_skill = _read(_SKILL_MD)
    assert re.search(r"FAB-QC ≥ 8\.5", src_skill), (
        "SKILL.md lost the FAB-QC ≥ 8.5 gate (rule 6)")
    src_qc = _read(_QC_MD)
    assert re.search(r"Pass gate: 8\.5/10 minimum", src_qc), (
        "QC.md lost the 8.5/10 pass gate (rule 6)")
    assert re.search(r"FAB-QC ≥ 8\.5", src_qc), (
        "QC.md lost the FAB-QC ≥ 8.5 per-build gate (rule 6)")


def test_rule6_human_publish_gate_still_named():
    """The never-publish-without-approval doctrine stays in SKILL.md, QC.md and
    INSTALL.md (pre-existing; guarded, not edited)."""
    src_skill = _read(_SKILL_MD)
    assert re.search(
        r"NEVER publish without explicit user approval", src_skill), (
        "SKILL.md lost the publish-approval gate (rule 6)")
    src_qc = _read(_QC_MD)
    assert re.search(
        r"does \*\*not\*\* publish without explicit user approval", src_qc), (
        "QC.md lost the no-publish-without-approval check (rule 6)")
    src_install = _read(_INSTALL_MD)
    assert re.search(
        r"NEVER publish without explicit approval", src_install), (
        "INSTALL.md lost the never-publish-without-approval rule (rule 6)")


# ══════════════════════════════════════════════════════════════════════════════
# Rule 7 — hermetic tests exist for probe selection + iframe wrong-frame fail
# ══════════════════════════════════════════════════════════════════════════════

def test_rule7_iframe_router_wrong_frame_fails_closed_suite():
    """Stale epoch / ambiguous selectors / double builder-iframe paths all stay
    fail-closed in the router suite."""
    proc = _pytest("tests/test_iframe_router.py",
                   "-k", "stale_epoch or ambiguous or double_builder")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rule7_probe_iframe_drag_hybrid_contract():
    """iframeDrag is fail-closed in the probe (available only on the AB+
    Playwright hybrid; STOP otherwise)."""
    proc = _pytest("tests/test_capability_probe.py", "-k", "iframe_drag")
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ══════════════════════════════════════════════════════════════════════════════
# Rule 8 — verify/receipt fail-closed behavior not weakened
# ══════════════════════════════════════════════════════════════════════════════

def test_rule8_qc_guards_exist_and_are_wired_into_qc_script():
    """Both fail-closed QC guards exist and qc-ghl-install-pages.sh references
    them (presence + wiring — the guards' full bodies are outside test scope;
    the method-decision static gate is cheap enough to run hermetically)."""
    assert os.path.isfile(_GUARD_VU), (
        "scripts/guard-ghl-verify-unfakeable.sh missing (rule 8)")
    assert os.path.isfile(_GUARD_MD), (
        "scripts/guard-ghl-method-decision.sh missing (rule 8)")
    qc_src = _read(_QC_SH)
    assert "guard-ghl-verify-unfakeable.sh" in qc_src, (
        "qc-ghl-install-pages.sh no longer references the verify-unfakeable guard (rule 8)")
    assert "guard-ghl-method-decision.sh" in qc_src, (
        "qc-ghl-install-pages.sh no longer references the method-decision guard (rule 8)")
    # The guard scripts must keep their fail-closed exit contract headers.
    vu_src = _read(_GUARD_VU)
    assert "exit 1" in vu_src and "exit 0" in vu_src, (
        "verify-unfakeable guard lost its 0/1 exit contract (rule 8)")
    md_src = _read(_GUARD_MD)
    assert "exit 1" in md_src and "exit 0" in md_src, (
        "method-decision guard lost its 0/1 exit contract (rule 8)")


def test_rule8_method_decision_static_gate_passes():
    """The cheap static half of the method-decision guard (gates.json carries
    the required fail-closed gate) runs clean offline."""
    proc = subprocess.run(
        ["bash", _GUARD_MD, "--static"], cwd=_SKILL_DIR,
        capture_output=True, text=True, timeout=_TIMEOUT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "STATIC PASS" in proc.stdout, proc.stdout


def test_rule8_verify_layer_safety_symbols_present():
    """The verify layer still exposes the anti-fabrication contract symbols the
    verify-unfakeable guard demands (checked statically here; the guard script's
    full per-line scan is far too slow for a test subprocess)."""
    verify_py = os.path.join(_SKILL_DIR, "tools", "ghl_verify.py")
    src = _read(verify_py)
    assert re.search(r"^class VerifyContradiction\b", src, re.M), (
        "ghl_verify.py lost VerifyContradiction (rule 8)")
    assert re.search(r"^def assert_consistent\b", src, re.M), (
        "ghl_verify.py lost assert_consistent (rule 8)")
    assert re.search(r"^def verify_all\b", src, re.M), (
        "ghl_verify.py lost verify_all (rule 8)")
    assert re.search(r"^def derive_summary\b", src, re.M), (
        "ghl_verify.py lost derive_summary (rule 8)")


def test_rule8_gates_json_has_no_marker_in_storage_pass():
    """gates.json carries no result=PASS entry whose evidence leans on the
    banned storage-marker shortcut (the verify-unfakeable guard's Assertion E,
    re-proven cheaply here)."""
    import json
    gates = os.path.join(_SKILL_DIR, "tools", "gates.json")
    with open(gates, encoding="utf-8") as fh:
        doc = json.load(fh)

    def walk(obj):
        hits = 0
        if isinstance(obj, dict):
            res = obj.get("result")
            if isinstance(res, str) and res.upper() == "PASS":
                blob = json.dumps(obj).lower()
                if ("marker in storage" in blob
                        or "marker in stored bytes" in blob):
                    hits += 1
            for v in obj.values():
                hits += walk(v)
        elif isinstance(obj, list):
            for v in obj:
                hits += walk(v)
        return hits

    assert walk(doc) == 0, (
        "gates.json contains a PASS result backed by a storage-marker claim (rule 8)")


def test_rule8_receipt_freshness_holds_in_waiting():
    """Stale/missing capability JSON holds the dispatcher in STATE_WAITING and
    mirrors the receipt shape — receipt freshness stays fail-closed."""
    proc = _pytest("tests/test_browser_manager_capability_wire.py",
                   "-k", "holds_in_waiting")
    assert proc.returncode == 0, proc.stdout + proc.stderr