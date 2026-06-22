"""Regression tests for scripts/guard-ghl-auth-fallback.sh + DONE 1, 8, 10.

PROVES the new guard does its job: it PASSES a GOOD repo skeleton (contained,
gated-before-login, bounded, self-healing, leak-free, sentinel present) and FAILS
each BAD variant (containment leak, gate-after-login, attempts>3, no-self-heal,
secret-print, operator-path, fallback-before-tier1, missing-sentinel). Also DONE 1
(the Tier-1 token-only + activation-resilience guards stay green) and DONE 10
(the Tier-2 sentinel is present verbatim in all 5 docs).

Deterministic, self-contained, no network / no browser. Each fixture lays down a
tiny repo skeleton in a tmp dir, copies the REAL guard, and runs it with
--repo-root. The final SHIP-GATE test runs the REAL guard against the REAL repo.

NO client names / IDs — only fabricated placeholders.
"""
from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent
_REPO_ROOT = _SKILL_DIR.parent
_GUARD = _REPO_ROOT / "scripts" / "guard-ghl-auth-fallback.sh"
_TOKEN_GUARD = _REPO_ROOT / "scripts" / "guard-ghl-token-only.sh"

_SENTINEL = ("GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated "
             "(auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY")
_T1_SENTINEL = ("GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the "
                "only auth path; NO auto UI-login / password / 2FA")

# ---------------------------------------------------------------------------
# GOOD fixture sources (trimmed but carrying exactly the required invariants)
# ---------------------------------------------------------------------------
_GOOD_FALLBACK = '''#!/usr/bin/env python3
"""Tier-2 fixture — contained login, gated-before-login, bounded, self-heal."""
import time

REFRESH_TOKEN_KEY = "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"
MAX_LOGIN_ATTEMPTS = 3


class SecretStore:
    def read_secret(self, k): return ""
    def write_secret(self, k, v): return True
    @property
    def password(self): return self.read_secret("p")


def backoff(attempt):
    time.sleep(0)


def gate_a_authorization(store):  # GATE-A: AUTHORIZATION
    return True


def gate_b_gmail_proven(probe, store):  # GATE-B: GMAIL-PROVEN
    return True


def gate_c_email_2fa(store):  # GATE-C: EMAIL-2FA-SELECTED
    return True


def gate_d_creds_present(store):  # GATE-D: CREDS-PRESENT
    return True


def check_all_gates(store, probe):
    return (gate_a_authorization(store) and gate_b_gmail_proven(probe, store)
            and gate_c_email_2fa(store) and gate_d_creds_present(store))


def login_with_2fa(driver, probe, store):
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        driver.fill_password(store.password)
        sig = driver.detect_lockout_or_captcha()
        if sig:
            return False
        if driver.wait_positive_liveness():
            return True
        backoff(attempt)
    return False


def capture_and_persist_refresh_token(driver, store):
    token = driver.read_refresh_token()
    return store.write_secret(REFRESH_TOKEN_KEY, token)


def run_tier2(session, out, store, probe, driver):
    if not check_all_gates(store, probe):
        return "tier3"
    if not login_with_2fa(driver, probe, store):
        return "tier3"
    capture_and_persist_refresh_token(driver, store)
    return "tier2"
'''

_GOOD_BROWSER = '''#!/usr/bin/env python3
"""Browser helper fixture — carries the password selector (allowlisted)."""
SELECTORS = {"password": ["input[type=password]"]}


class LoginBrowser:
    def __init__(self, engine):
        self.engine = engine

    def fill_password(self, password):
        self.engine.fill(SELECTORS["password"], password)
'''

_GOOD_ORCH = '''#!/usr/bin/env python3
"""Orchestrator fixture — Tier-1 branch precedes the lazy fallback import."""
import os

REFRESH_ENV_VARS = ("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",)


def resolve_refresh_token(env=None):
    src = env if env is not None else os.environ
    for n in REFRESH_ENV_VARS:
        v = (src.get(n, "") or "").strip()
        if v:
            return v, n
    return "", ""


def tier1_mint_and_seed(session, out, env=None, seed_runner=None):
    return 0


def run(session, out, env=None):
    token, _ = resolve_refresh_token(env)
    if token:
        if tier1_mint_and_seed(session, out, env) == 0:
            return "tier1"
    import ghl_auth_fallback as fallback
    store = fallback.SecretStore()
    return fallback.run_tier2(session, out, store, None, None)
'''


def _doc_with_sentinel():
    return f"# doc\n\n{_SENTINEL}\n\n{_T1_SENTINEL}\n"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
def _lay_repo(tmp_path: Path, *, fallback=_GOOD_FALLBACK, browser=_GOOD_BROWSER,
              orch=_GOOD_ORCH, docs_sentinel=True, copy_token_guard=True) -> Path:
    scripts_dir = tmp_path / "scripts"
    skill_dir = tmp_path / "06-ghl-install-pages"
    tools_dir = skill_dir / "tools"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    tools_dir.mkdir(parents=True, exist_ok=True)

    g = scripts_dir / "guard-ghl-auth-fallback.sh"
    shutil.copy2(_GUARD, g)
    g.chmod(g.stat().st_mode | stat.S_IEXEC)

    if copy_token_guard and _TOKEN_GUARD.exists():
        tg = scripts_dir / "guard-ghl-token-only.sh"
        shutil.copy2(_TOKEN_GUARD, tg)
        tg.chmod(tg.stat().st_mode | stat.S_IEXEC)

    (tools_dir / "ghl_auth_fallback.py").write_text(fallback, encoding="utf-8")
    (tools_dir / "ghl_login_browser.py").write_text(browser, encoding="utf-8")
    (tools_dir / "ghl_auth.py").write_text(orch, encoding="utf-8")
    # Tier-1 files the token-only companion guard re-checks: clean stubs.
    (tools_dir / "seed-ghl-auth.py").write_text(
        '#!/usr/bin/env python3\n"""clean seed"""\nprint("ok")\n', encoding="utf-8")
    (tools_dir / "inject-ghl-auth.sh").write_text(
        '#!/usr/bin/env bash\n# clean inject\necho ok\n', encoding="utf-8")

    body = _doc_with_sentinel() if docs_sentinel else "# doc (no sentinel)\n"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    (skill_dir / "INSTRUCTIONS.md").write_text(body, encoding="utf-8")
    (skill_dir / "CORE_UPDATES.md").write_text(body, encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(body, encoding="utf-8")
    (tmp_path / "TOOLS.md").write_text(body, encoding="utf-8")
    return g


def _run(tmp_path: Path, **kw) -> subprocess.CompletedProcess:
    g = _lay_repo(tmp_path, **kw)
    return subprocess.run(["bash", str(g), "--repo-root", str(tmp_path)],
                          capture_output=True, text=True, timeout=120)


# ---------------------------------------------------------------------------
# GOOD fixture passes
# ---------------------------------------------------------------------------
class TestGuardPassesGood:
    def test_good_fixture_passes(self, tmp_path):
        res = _run(tmp_path)
        assert res.returncode == 0, f"GOOD fixture must PASS.\n{res.stdout}\n{res.stderr}"


# ---------------------------------------------------------------------------
# Each BAD variant fails
# ---------------------------------------------------------------------------
class TestGuardFailsEachBad:
    def test_containment_leak_in_orchestrator(self, tmp_path):
        """A password .fill in the orchestrator (outside the allowlist) must FAIL."""
        bad_orch = _GOOD_ORCH + '\n\ndef _leak(driver, pw):\n    driver.fill("input[type=password]", pw)\n'
        res = _run(tmp_path, orch=bad_orch)
        assert res.returncode == 1, res.stdout
        assert "OUTSIDE the allowlist" in res.stdout, res.stdout

    def test_gate_after_login(self, tmp_path):
        """A login/password action BEFORE the last gate call must FAIL ordering."""
        bad = _GOOD_FALLBACK.replace(
            "def gate_a_authorization(store):  # GATE-A: AUTHORIZATION\n    return True",
            "def gate_a_authorization(store):  # GATE-A: AUTHORIZATION\n"
            "    return True\n\n\ndef _early(driver):\n    driver.fill_password('x')",
        )
        res = _run(tmp_path, fallback=bad)
        assert res.returncode == 1, res.stdout
        assert "BEFORE the last gate call" in res.stdout, res.stdout

    def test_attempts_exceed_cap(self, tmp_path):
        bad = _GOOD_FALLBACK.replace("MAX_LOGIN_ATTEMPTS = 3", "MAX_LOGIN_ATTEMPTS = 5")
        res = _run(tmp_path, fallback=bad)
        assert res.returncode == 1, res.stdout
        assert "exceeds the cap" in res.stdout, res.stdout

    def test_no_self_heal(self, tmp_path):
        bad = _GOOD_FALLBACK.replace(
            "    return store.write_secret(REFRESH_TOKEN_KEY, token)",
            "    return True  # self-heal removed",
        )
        res = _run(tmp_path, fallback=bad)
        assert res.returncode == 1, res.stdout
        assert "self-heal" in res.stdout.lower(), res.stdout

    def test_secret_print(self, tmp_path):
        bad = _GOOD_FALLBACK.replace(
            "    token = driver.read_refresh_token()",
            "    token = driver.read_refresh_token()\n    print(refresh_token)",
        )
        res = _run(tmp_path, fallback=bad)
        assert res.returncode == 1, res.stdout
        assert "secret" in res.stdout.lower(), res.stdout

    def test_operator_path(self, tmp_path):
        bad = _GOOD_FALLBACK.replace(
            'REFRESH_TOKEN_KEY = "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"',
            'REFRESH_TOKEN_KEY = "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"\n'
            '_OP = open("/Users/operator/secret").read()',
        )
        res = _run(tmp_path, fallback=bad)
        assert res.returncode == 1, res.stdout
        assert "operator path" in res.stdout.lower(), res.stdout

    def test_fallback_before_tier1(self, tmp_path):
        """A module-top fallback import (before the Tier-1 branch) must FAIL."""
        bad_orch = "import ghl_auth_fallback\n" + _GOOD_ORCH
        res = _run(tmp_path, orch=bad_orch)
        assert res.returncode == 1, res.stdout
        assert ("module top level" in res.stdout or "precedes the Tier-1" in res.stdout), res.stdout

    def test_missing_sentinel(self, tmp_path):
        res = _run(tmp_path, docs_sentinel=False)
        assert res.returncode == 1, res.stdout
        assert "sentinel MISSING" in res.stdout, res.stdout


# ---------------------------------------------------------------------------
# DONE 10 — sentinel verbatim in all 5 real docs
# ---------------------------------------------------------------------------
class TestSentinelInDocs:
    @pytest.mark.parametrize("rel", [
        "06-ghl-install-pages/SKILL.md",
        "06-ghl-install-pages/INSTRUCTIONS.md",
        "06-ghl-install-pages/CORE_UPDATES.md",
        "AGENTS.md",
        "TOOLS.md",
    ])
    def test_sentinel_present_verbatim(self, rel):
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert _SENTINEL in text, f"Tier-2 sentinel missing from {rel}"

    def test_ladder_described(self):
        skill = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        assert "Tier 1" in skill and "Tier 2" in skill and "Tier 3" in skill


# ---------------------------------------------------------------------------
# DONE 1 — Tier-1 guards stay green
# ---------------------------------------------------------------------------
class TestTier1Untouched:
    def test_token_only_guard_green(self):
        res = subprocess.run(["bash", str(_TOKEN_GUARD)], capture_output=True,
                             text=True, timeout=60, cwd=str(_REPO_ROOT))
        assert res.returncode == 0, (
            f"Tier-1 token-only guard must stay green.\n{res.stdout}\n{res.stderr}")

    def test_activation_resilience_guard_green(self):
        guard = _REPO_ROOT / "scripts" / "guard-ghl-activation-resilience.sh"
        res = subprocess.run(["bash", str(guard)], capture_output=True,
                             text=True, timeout=60, cwd=str(_REPO_ROOT))
        assert res.returncode == 0, (
            f"Tier-1 activation-resilience guard must stay green.\n{res.stdout}\n{res.stderr}")


# ---------------------------------------------------------------------------
# Guard self-consistency + SHIP GATE
# ---------------------------------------------------------------------------
class TestGuardWellFormed:
    def test_guard_exists_and_is_bash(self):
        assert _GUARD.exists()
        first = _GUARD.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("#!") and "bash" in first

    def test_guard_clean_bash_syntax(self):
        res = subprocess.run(["bash", "-n", str(_GUARD)], capture_output=True,
                             text=True, timeout=30)
        assert res.returncode == 0, res.stderr


class TestShipGate:
    def test_real_files_pass_guard(self):
        res = subprocess.run(["bash", str(_GUARD)], capture_output=True,
                             text=True, timeout=120, cwd=str(_REPO_ROOT))
        assert res.returncode == 0, (
            "SHIP GATE: the real Tier-2 files do not pass guard-ghl-auth-fallback.\n"
            f"exit={res.returncode}\n{res.stdout}\n{res.stderr}")
