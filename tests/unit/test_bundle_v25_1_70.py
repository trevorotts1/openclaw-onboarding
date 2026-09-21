"""Audience rule, safe env loader, contract check, Skill 59 roster, maxConcurrent.

Five independent findings, one release. Each test names the behaviour it pins,
not the implementation, except where the only honest check is source-level
(shell embedded in a heredoc).
"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.join(_ROOT, relpath)))
    spec.loader.exec_module(mod)
    return mod


pb = _load("persona_blend_under_test", "23-ai-workforce-blueprint/scripts/persona_blend.py")


# ─── 1. The audience gate confirms only on real ambiguity ───────────────────
# persona_blend.resolve_audience returned confirm_required=True on EVERY branch
# but an explicit override, so a company with one ICP — or none — parked every
# content task at the audience gate for the full confirm window.

_CAT = {"personas": []}


def _cfg(*icps):
    # "audiences" is one of persona_blend._ICP_LIST_KEYS.
    return {"audiences": list(icps)} if icps else {}


def test_no_icp_does_not_require_confirmation():
    out = pb.resolve_audience(_CAT, _cfg(), "")
    assert out["confirm_required"] is False
    assert out["candidates"] == []


def test_single_icp_does_not_require_confirmation():
    out = pb.resolve_audience(_CAT, _cfg("small business owners"), "")
    assert out["confirm_required"] is False
    assert out["source"] == "onboarding_icp"
    assert out["ask"], "the prompt is still offered for a caller that wants it"


def test_two_icps_still_require_confirmation():
    out = pb.resolve_audience(_CAT, _cfg("small business owners", "enterprise buyers"), "")
    assert out["confirm_required"] is True
    assert len(out["candidates"]) == 2


def test_explicit_override_does_not_require_confirmation():
    out = pb.resolve_audience(_CAT, _cfg("a", "b"), "", audience_override="enterprise buyers")
    assert out["confirm_required"] is False
    assert out["source"] == "operator_confirmed"


@pytest.mark.parametrize("word", ["none", "None", " NO AUDIENCE "])
def test_explicit_audience_none_is_an_answer_not_a_gap(word):
    out = pb.resolve_audience(_CAT, _cfg("a", "b"), "", audience_override=word)
    assert out["confirm_required"] is False
    assert out["label"] is None
    assert out["ask"] is None


@pytest.mark.parametrize("dept", ["marketing", "web-development", "Marketing"])
def test_hard_hold_department_always_confirms(dept):
    # D23 (as corrected 2026-07-16) hard-holds these departments' content tasks.
    for cfg in (_cfg(), _cfg("one icp")):
        out = pb.resolve_audience(_CAT, cfg, "", department=dept)
        assert out["confirm_required"] is True, (dept, cfg)
    out = pb.resolve_audience(_CAT, _cfg(), "", audience_override="none", department=dept)
    assert out["confirm_required"] is True


def test_a_normal_department_does_not_confirm_on_a_single_icp():
    out = pb.resolve_audience(_CAT, _cfg("one icp"), "", department="audio")
    assert out["confirm_required"] is False


# ─── 2. The safe env loader ─────────────────────────────────────────────────
# `set -a; . file` hands a client-owned file to the shell: every line runs, and
# a key the shell cannot accept (9R_GATEWAY_KEY) aborts the load so every later
# key silently goes missing.

_ENVLOAD = os.path.join(_ROOT, "shared-utils", "env-load.sh")


def _sh(script):
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def test_env_load_self_check_passes():
    r = subprocess.run(["bash", _ENVLOAD], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all self-checks pass" in r.stdout


def test_a_bad_key_does_not_stop_the_rest_of_the_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("GOOD=1\n9R_GATEWAY_KEY=bad\nAFTER=2\n")
    r = _sh(f'. "{_ENVLOAD}"; env_load_quiet "{f}"; echo "$GOOD/$AFTER/$ENV_LOAD_SKIPPED"')
    assert r.stdout.strip() == "1/2/1", r.stdout + r.stderr


def test_the_loader_never_executes_the_file(tmp_path):
    # The whole point: a command in the file must NOT run.
    f = tmp_path / ".env"
    marker = tmp_path / "pwned"
    f.write_text(f'GOOD=1\ntouch {marker}\nALSO=2\n')
    r = _sh(f'. "{_ENVLOAD}"; env_load_quiet "{f}"; echo "$GOOD/$ALSO"')
    assert r.stdout.strip() == "1/2"
    assert not marker.exists(), "the loader executed a line from the file"


def test_the_loader_never_prints_the_offending_line(tmp_path):
    f = tmp_path / ".env"
    f.write_text("SECRET_TOKEN=s3cr3t\nnot an assignment with s3cr3t in it\n")
    r = _sh(f'. "{_ENVLOAD}"; env_load "{f}" >/dev/null')
    assert "s3cr3t" not in r.stderr, "a skipped line leaked into the log"
    assert "1 line(s) skipped" in r.stderr


def test_missing_file_returns_nonzero(tmp_path):
    r = _sh(f'. "{_ENVLOAD}"; env_load_quiet "{tmp_path}/nope"; echo "rc=$?"')
    assert "rc=1" in r.stdout


@pytest.mark.parametrize("key,ok", [
    ("GOOD", True), ("_UNDER", True), ("A1", True),
    ("9R_GATEWAY_KEY", False), ("WITH-DASH", False), ("", False),
])
def test_env_valid_key_rejects_what_the_shell_cannot_export(key, ok):
    r = _sh(f'. "{_ENVLOAD}"; env_valid_key "{key}" && echo yes || echo no')
    assert r.stdout.strip() == ("yes" if ok else "no")


@pytest.mark.parametrize("script", [
    "38-conversational-ai-system/scripts/26-verify-pixel-prerequisites.sh",
    "38-conversational-ai-system/scripts/29-deploy-pixel-cloudflare.sh",
    "38-conversational-ai-system/scripts/15-configure-hooks-mappings.sh",
    "38-conversational-ai-system/scripts/28-configure-pixel-hook.sh",
    "38-conversational-ai-system/scripts/14-install-cloudflared-service.sh",
    "38-conversational-ai-system/scripts/24-self-test-hook.sh",
    "35-social-media-planner/qc-skill35.sh",
    "23-ai-workforce-blueprint/templates/role-library/presentations/scripts/board-reconcile-sweep.sh",
])
def test_every_converted_reader_routes_through_the_loader(script):
    src = open(os.path.join(_ROOT, script)).read()
    assert "env-load.sh" in src, f"{script} does not source the safe loader"
    assert "env_load" in src, f"{script} does not call the safe loader"


# ─── 3. The contract check ──────────────────────────────────────────────────

def test_update_roll_runs_the_contract_check_warn_only():
    src = open(os.path.join(_ROOT, "update-skills.sh")).read()
    assert "openclaw-contract-check.mjs" in src
    assert "WARN on an update roll" in src
    # and it must run BEFORE the refresh it is checking
    assert src.index("CC contract check") < src.index("Refreshing Command Center web app")


def test_full_install_makes_the_contract_check_fatal():
    src = open(os.path.join(_ROOT, "32-command-center-setup/scripts/run-full-install.sh")).read()
    assert "openclaw-contract-check.mjs" in src
    assert 'fail_install "contract-check:' in src
    # update-only must NOT be fatal
    i = src.index("CC_CONTRACT_CHECK=")
    seg = src[i:i + 2000]
    assert 'if [[ "${UPDATE_ONLY:-false}" == "true" ]]; then' in seg
    assert seg.index('UPDATE_ONLY:-false') < seg.index('fail_install "contract-check:')


def test_a_cc_without_the_script_is_not_a_failure():
    src = open(os.path.join(_ROOT, "32-command-center-setup/scripts/run-full-install.sh")).read()
    assert "not present in this CC version -- skipping" in src


# ─── 4. Skill 59 writes the roster shape the gateway reads ──────────────────

_S59 = os.path.join(_ROOT, "59-anthology-engine/scripts/provision-anthology-client.sh")


def test_skill59_prefers_agents_entries():
    src = open(_S59).read()
    assert "MODE_ENTRIES" in src
    assert 'entries = agents.get("entries")' in src


def test_skill59_uses_the_live_workspace_path():
    src = open(_S59).read()
    assert 'os.path.join(oc_root, "workspaces", "command-center", slug)' in src
    assert 'os.path.join(oc_root, "workspace", "departments", slug)' not in src


def test_skill59_nests_memory_search_in_entries_mode():
    src = open(_S59).read()
    assert '"memory": {"search": _mem}' in src
    assert 'existing.pop("memorySearch", None)' in src


def test_skill59_pins_no_model():
    # Sibling dept- entries carry no model and inherit agents.defaults.
    src = open(_S59).read()
    block = src[src.index("MODE_ENTRIES ="):src.index("# Backup (best-effort)")]
    assert '"model"' not in block, "step 3.6 hardcodes a model"


def test_skill59_read_back_checks_the_shape_it_wrote():
    src = open(_S59).read()
    assert 'if MODE_ENTRIES:\n    count = 1 if isinstance(_ba.get("entries", {}).get(agent_id), dict) else 0' in src


# ─── 5. Explicit agents.defaults.maxConcurrent ──────────────────────────────

def test_installer_preserves_an_existing_max_concurrent():
    src = open(os.path.join(_ROOT, "install.sh")).read()
    assert "if 'maxConcurrent' in defaults:" in src
    assert "preserved at" in src


def test_installer_only_creates_the_key_on_a_runtime_that_has_it():
    # AgentDefaultsSchema is .strict(): creating this key on an older runtime
    # makes that runtime reject the client's ENTIRE config.
    src = open(os.path.join(_ROOT, "install.sh")).read()
    assert "_ver_ge_9_5" in src
    assert "predates 2026.9.5" in src
    assert "_OC_RUNTIME_VERSION=" in src


@pytest.mark.parametrize("ver,want", [
    ("2026.9.5", True), ("2026.9.6", True), ("2027.1.0", True),
    ("2026.9.4", False), ("2026.8.9", False), ("", False), ("garbage", False),
])
def test_version_gate_boundary(ver, want):
    def _ver_ge_9_5(v):
        parts = (v or "").lstrip("vV").split(".")
        try:
            nums = [int(x) for x in parts[:3]]
        except ValueError:
            return False
        return len(nums) == 3 and tuple(nums) >= (2026, 9, 5)
    assert _ver_ge_9_5(ver) is want
