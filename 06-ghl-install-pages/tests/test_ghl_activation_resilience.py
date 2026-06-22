"""Regression tests for scripts/guard-ghl-activation-resilience.sh.

These tests PROVE the guard does its job: it must PASS a hardened (GOOD) pair of
auth tool files and FAIL every BAD variant that reintroduces the Layer-2
activation race (single-shot activate, hasPwd-only liveness, post-seed reload,
hardcoded deep /location/<id> route) or drops a required resilience marker.

HOW IT WORKS (deterministic, self-contained, no network / no browser):
  Each fixture test builds a fake repo skeleton in a tmp dir:
      <tmp>/scripts/guard-ghl-activation-resilience.sh   (a copy of the real guard)
      <tmp>/06-ghl-install-pages/tools/inject-ghl-auth.sh (fixture)
      <tmp>/06-ghl-install-pages/tools/seed-ghl-auth.py   (fixture)
  then runs the guard with `--repo-root <tmp>` and asserts the exit code.

The final test runs the guard against the ACTUAL repo tool files — this is the
SHIP GATE. If the real tools are not yet fully hardened it will FAIL, which is
correct and intentional: the gate blocks the release until the hardening lands.

NO client names / IDs appear in any fixture — only fabricated 20-char ids and the
generic origin already used by the shipped tooling.
"""
from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent
_REPO_ROOT = _SKILL_DIR.parent
_GUARD = _REPO_ROOT / "scripts" / "guard-ghl-activation-resilience.sh"

# Fabricated, non-client identifiers used only inside fixtures.
_FAKE_API_KEY = "AIzaFAKEfakefakeFAKEfakefakeFAKE12345678"
_FAKE_LOCATION_ID = "abcd1234EFGH5678ijkl"  # 20-char fabricated location id


# ---------------------------------------------------------------------------
# Fixture source snippets
# ---------------------------------------------------------------------------
# A minimal but representative HARDENED inject-ghl-auth.sh — it carries exactly
# the resilience markers the guard requires (R1..R5) and none of the banned
# patterns. It is intentionally trimmed: the guard scans for markers, not for a
# runnable script.
_GOOD_INJECT = r'''#!/usr/bin/env bash
# Hardened inject fixture — Layer-2 activation is resilient (no single-shot).
set -euo pipefail
SESSION="${1:-}"; SEED_FILE="${2:-}"
export GHL_SEED_JSON="$(cat "$SEED_FILE")"

# Stage the seed object, then run the injector (login/current + cookie write).
AB --session "$SESSION" eval --stdin <<EOF >/dev/null
window.__GHL_SEED__ = ${GHL_SEED_JSON};
EOF

read -r -d '' INJECT_JS <<'JS' || true
(async () => {
  const seed = window.__GHL_SEED__;
  const lc = seed.login_current;            // /oauth/2/login/current
  const lcHeaders = Object.assign({}, lc.headers); // carries token-id
  // Bounded retry on the login/current re-fetch (token-only re-assert).
  let i = null;
  for (let attempt = 1; attempt <= 4; attempt++) {
    const resp = await fetch(lc.url, { headers: lcHeaders, credentials: "omit" });
    if (resp.status === 200) { i = await resp.json(); if (i && i.apiKey) break; }
  }
  // Re-write cookie `a` from the token-only response (re-assert).
  const aObj = { apiKey: i.apiKey, userId: i.userId, companyId: i.companyId };
  document.cookie = "a=" + btoa(JSON.stringify(aObj)) + ";path=/";
  function getCookie(n){const m=document.cookie.match(new RegExp("(?:^|; )"+n+"=([^;]*)"));return m?m[1]:null;}
  const rawA = getCookie("a");
  let decoded = null; try { decoded = JSON.parse(atob(rawA)); } catch(e){}
  if (!decoded || !decoded.apiKey) throw new Error("COOKIE-A-READBACK-FAILED");
  return "seeded";
})()
JS

AB --session "$SESSION" eval --stdin <<EOF
${INJECT_JS}
EOF

read -r -d '' ACTIVATE_JS <<'AJS' || true
(async () => {
  const ACT_MAX_ATTEMPTS = 4;
  function jitter(ms){ return Math.round(ms * (0.7 + Math.random()*0.6)); }
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  // Warm-store readiness gate: poll for #app.__vue_app__ $store + $router.
  let store = null, router = null;
  for (let w = 0; w < 16; w++) {
    const el = document.querySelector('#app');
    const gp = el && el.__vue_app__ && el.__vue_app__.config && el.__vue_app__.config.globalProperties;
    if (gp && gp.$store && gp.$router) { store = gp.$store; router = gp.$router; break; }
    await sleep(500);
  }
  if (!store || !router) throw new Error("ACTIVATE-NO-STORE-ROUTER");
  let user = null, lastErr = "";
  for (let attempt = 1; attempt <= ACT_MAX_ATTEMPTS; attempt++) {
    try { user = await store.dispatch('auth/get'); } catch(e){ user = null; }
    if (user && user.apiKey && user.userId) {
      try { await router.push({ path: '/' }); } catch(e){}
      await sleep(900);
      const hasPwd = !!document.querySelector('input[type=password]');
      // Positive liveness: decode cookie `a` and assert apiKey matches user.
      function getCookie(n){const m=document.cookie.match(new RegExp("(?:^|; )"+n+"=([^;]*)"));return m?m[1]:null;}
      let decoded=null; try{ decoded = JSON.parse(atob(getCookie("a"))); }catch(e){}
      const live = !!(decoded && decoded.apiKey && decoded.apiKey === user.apiKey) && !hasPwd;
      if (live) return "activated:attempt=" + attempt;
      lastErr = "BOUNCED-TO-LOGIN hasPwd=" + hasPwd;
    }
    if (attempt < ACT_MAX_ATTEMPTS) await sleep(jitter(600 * Math.pow(2, attempt - 1)));
  }
  throw new Error("ACTIVATE-FAILED: " + lastErr);
})()
AJS

AB --session "$SESSION" eval --stdin <<EOF
${ACTIVATE_JS}
EOF
# DO NOT RELOAD — activation is via $router.push only.
echo "NEXT: snapshot -i  # do NOT reload"
'''

# A minimal HARDENED seed-ghl-auth.py — Layer-1 mint has a bounded retry (R6).
_GOOD_SEED = '''#!/usr/bin/env python3
"""Hardened seed fixture — securetoken mint has a bounded retry (not single-shot)."""
import json
import time
import urllib.request

FIREBASE_API_KEY = "''' + _FAKE_API_KEY + '''"
FIREBASE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token?key=" + FIREBASE_API_KEY


def _exchange(refresh_token):
    body = ("grant_type=refresh_token&refresh_token=" + refresh_token).encode()
    req = urllib.request.Request(FIREBASE_TOKEN_URL, data=body, method="POST")
    MINT_MAX_ATTEMPTS = 3
    last = None
    for attempt in range(1, MINT_MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e
            time.sleep(0.4 * attempt)
    raise RuntimeError("securetoken exchange failed after retries: %s" % last)


if __name__ == "__main__":
    pass
'''


# ---------------------------------------------------------------------------
# Bad-variant transforms (each reintroduces ONE banned regression / drops a marker)
# ---------------------------------------------------------------------------

def _bad_single_shot(good_inject: str) -> str:
    """F1 / R1: rip out the bounded retry loop around the activate — leave a
    single-shot auth/get + router.push with no surrounding loop."""
    return r'''#!/usr/bin/env bash
set -euo pipefail
SESSION="${1:-}"; SEED_FILE="${2:-}"
read -r -d '' ACTIVATE_JS <<'AJS' || true
(async () => {
  const el = document.querySelector('#app');
  const gp = el && el.__vue_app__ && el.__vue_app__.config && el.__vue_app__.config.globalProperties;
  const store = gp.$store, router = gp.$router;
  const user = await store.dispatch('auth/get');   // SINGLE-SHOT — no retry loop
  await router.push({ path: '/' });
  await new Promise(r => setTimeout(r, 900));
  function getCookie(n){const m=document.cookie.match(new RegExp("(?:^|; )"+n+"=([^;]*)"));return m?m[1]:null;}
  let decoded=null; try{ decoded = JSON.parse(atob(getCookie("a"))); }catch(e){}
  if (decoded && decoded.apiKey === user.apiKey) return "activated";
  throw new Error("ACTIVATE-NO-STORE-ROUTER");
})()
AJS
AB --session "$SESSION" eval --stdin <<EOF
${ACTIVATE_JS}
EOF
echo "NEXT: snapshot -i  # do NOT reload"
'''


def _bad_haspwd_only(good_inject: str) -> str:
    """F2 / R4: liveness based ONLY on hasPwd / no-password-box — strip every
    cookie-`a`+apiKey assertion (no decoded.apiKey, no user.apiKey, no atob)."""
    return r'''#!/usr/bin/env bash
set -euo pipefail
SESSION="${1:-}"
read -r -d '' ACTIVATE_JS <<'AJS' || true
(async () => {
  const ACT_MAX_ATTEMPTS = 4;
  function jitter(ms){ return Math.round(ms * (0.7 + Math.random()*0.6)); }
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const el = document.querySelector('#app');
  const gp = el && el.__vue_app__ && el.__vue_app__.config && el.__vue_app__.config.globalProperties;
  const store = gp.$store, router = gp.$router;
  if (!store || !router) throw new Error("ACTIVATE-NO-STORE-ROUTER");
  for (let attempt = 1; attempt <= ACT_MAX_ATTEMPTS; attempt++) {
    await store.dispatch('auth/get');
    await router.push({ path: '/' });
    await sleep(900);
    const hasPwd = !!document.querySelector('input[type=password]');
    if (!hasPwd) return "activated";   // hasPwd-ONLY liveness — no cookie `a` check
    if (attempt < ACT_MAX_ATTEMPTS) await sleep(jitter(600 * Math.pow(2, attempt - 1)));
  }
  throw new Error("ACTIVATE-FAILED");
})()
AJS
AB --session "$SESSION" eval --stdin <<EOF
${ACTIVATE_JS}
EOF
echo "NEXT: snapshot -i  # do NOT reload"
'''


def _bad_reload(good_inject: str) -> str:
    """F3: reintroduce a post-seed reload — append a real location.reload() call
    in executable code (after the seed/activate)."""
    return good_inject + '\nAB --session "$SESSION" eval "window.location.reload()"\n'


def _bad_deep_route(good_inject: str) -> str:
    """F4: hardcode a deep /location/<id>/ route literal into the activate path."""
    return good_inject.replace(
        "router.push({ path: '/' })",
        "router.push({ path: '/location/" + _FAKE_LOCATION_ID + "/dashboard' })",
    )


# ---------------------------------------------------------------------------
# Test harness — build a fake repo + run the guard with --repo-root
# ---------------------------------------------------------------------------

def _run_guard_against(tmp_path: Path, inject_src: str, seed_src: str) -> subprocess.CompletedProcess:
    """Lay down scripts/ + 06-ghl-install-pages/tools/ in tmp_path and run the
    REAL guard against it with --repo-root. Returns the completed process."""
    assert _GUARD.exists(), f"guard script not found: {_GUARD}"

    scripts_dir = tmp_path / "scripts"
    tools_dir = tmp_path / "06-ghl-install-pages" / "tools"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    tools_dir.mkdir(parents=True, exist_ok=True)

    guard_copy = scripts_dir / "guard-ghl-activation-resilience.sh"
    shutil.copy2(_GUARD, guard_copy)
    guard_copy.chmod(guard_copy.stat().st_mode | stat.S_IEXEC)

    (tools_dir / "inject-ghl-auth.sh").write_text(inject_src, encoding="utf-8")
    (tools_dir / "seed-ghl-auth.py").write_text(seed_src, encoding="utf-8")

    return subprocess.run(
        ["bash", str(guard_copy), "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# GOOD fixture must PASS
# ---------------------------------------------------------------------------

class TestGuardPassesHardenedFixture:
    def test_good_fixture_passes(self, tmp_path):
        res = _run_guard_against(tmp_path, _GOOD_INJECT, _GOOD_SEED)
        assert res.returncode == 0, (
            "Hardened GOOD fixture must PASS the guard.\n"
            f"exit={res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        # Sanity: all required markers reported present.
        for marker in ("R1 present", "R2 present", "R3 present",
                       "R4 present", "R5 present", "R6 present"):
            assert marker in res.stdout, f"expected '{marker}' in guard output:\n{res.stdout}"
        # Sanity: no forbidden pattern flagged.
        assert "PRESENT (banned regression)" not in res.stdout, res.stdout


# ---------------------------------------------------------------------------
# Each BAD fixture must FAIL — and for the SPECIFIC reason
# ---------------------------------------------------------------------------

class TestGuardFailsRegressions:
    def test_single_shot_activate_fails(self, tmp_path):
        """F1: single-shot activate (no retry loop) must FAIL."""
        res = _run_guard_against(tmp_path, _bad_single_shot(_GOOD_INJECT), _GOOD_SEED)
        assert res.returncode == 1, (
            f"single-shot activate must FAIL.\n{res.stdout}\n{res.stderr}"
        )
        # The single-shot violation surfaces as R1 absent and F1 present.
        assert "R1 ABSENT" in res.stdout, res.stdout
        assert "F1 PRESENT" in res.stdout, res.stdout

    def test_haspwd_only_liveness_fails(self, tmp_path):
        """F2: hasPwd-only liveness (no cookie-`a`+apiKey) must FAIL."""
        res = _run_guard_against(tmp_path, _bad_haspwd_only(_GOOD_INJECT), _GOOD_SEED)
        assert res.returncode == 1, (
            f"hasPwd-only liveness must FAIL.\n{res.stdout}\n{res.stderr}"
        )
        assert "R4 ABSENT" in res.stdout, res.stdout
        assert "F2 PRESENT" in res.stdout, res.stdout

    def test_post_seed_reload_fails(self, tmp_path):
        """F3: a post-seed reload() must FAIL."""
        res = _run_guard_against(tmp_path, _bad_reload(_GOOD_INJECT), _GOOD_SEED)
        assert res.returncode == 1, (
            f"post-seed reload must FAIL.\n{res.stdout}\n{res.stderr}"
        )
        assert "F3 PRESENT" in res.stdout, res.stdout

    def test_deep_location_route_fails(self, tmp_path):
        """F4: a hardcoded /location/<id> route literal must FAIL."""
        res = _run_guard_against(tmp_path, _bad_deep_route(_GOOD_INJECT), _GOOD_SEED)
        assert res.returncode == 1, (
            f"hardcoded deep /location/<id> route must FAIL.\n{res.stdout}\n{res.stderr}"
        )
        assert "F4 PRESENT" in res.stdout, res.stdout

    def test_layer1_mint_single_shot_fails(self, tmp_path):
        """R6: a single-shot securetoken mint (no retry loop) must FAIL."""
        single_shot_seed = '''#!/usr/bin/env python3
"""Un-hardened seed — single-shot securetoken mint (no retry)."""
import json
import urllib.request

FIREBASE_API_KEY = "''' + _FAKE_API_KEY + '''"
FIREBASE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token?key=" + FIREBASE_API_KEY


def _exchange(refresh_token):
    body = ("grant_type=refresh_token&refresh_token=" + refresh_token).encode()
    req = urllib.request.Request(FIREBASE_TOKEN_URL, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:   # SINGLE-SHOT — no loop
        return json.loads(r.read())
'''
        res = _run_guard_against(tmp_path, _GOOD_INJECT, single_shot_seed)
        assert res.returncode == 1, (
            f"single-shot Layer-1 mint must FAIL.\n{res.stdout}\n{res.stderr}"
        )
        assert "R6 ABSENT" in res.stdout, res.stdout


# ---------------------------------------------------------------------------
# Guard self-consistency
# ---------------------------------------------------------------------------

class TestGuardWellFormed:
    def test_guard_exists_and_is_bash(self):
        assert _GUARD.exists(), f"guard script missing: {_GUARD}"
        first = _GUARD.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("#!") and "bash" in first, first

    def test_guard_has_clean_bash_syntax(self):
        """`bash -n` must parse the guard (catches the backtick-in-echo class of
        bug that would crash the remedy block at runtime)."""
        res = subprocess.run(
            ["bash", "-n", str(_GUARD)], capture_output=True, text=True, timeout=30
        )
        assert res.returncode == 0, f"guard has bash syntax errors:\n{res.stderr}"

    def test_guard_no_client_identifiers_in_fixtures(self):
        """This test file must not embed any real client name/id — only fabricated
        placeholders. (Guards against accidental leakage into fixtures.)"""
        text = Path(__file__).read_text(encoding="utf-8")
        # The fabricated markers we DO allow.
        assert _FAKE_LOCATION_ID in text
        assert _FAKE_API_KEY in text


# ---------------------------------------------------------------------------
# SHIP GATE — run the guard against the ACTUAL repo tool files
# ---------------------------------------------------------------------------

class TestShipGateAgainstRealTools:
    """This runs the REAL guard against the REAL 06-ghl-install-pages/tools files.

    It is the release gate. If the real tools are not fully hardened yet, this
    FAILS — which is correct: the gate must block the release until the hardening
    (R1..R6, no F1..F4) lands in the shipped tools. When the tools are hardened,
    this turns green and stays green (any later regression flips it red again).
    """

    def test_real_tools_pass_activation_resilience_guard(self):
        res = subprocess.run(
            ["bash", str(_GUARD)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(_REPO_ROOT),
        )
        assert res.returncode == 0, (
            "SHIP GATE: the real 06-ghl-install-pages/tools files are NOT fully "
            "hardened against the Layer-2 activation regression. The release is "
            "BLOCKED until R1..R6 hold and no F1..F4 pattern is present.\n"
            f"exit={res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
