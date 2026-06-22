#!/usr/bin/env python3
"""ghl_login_browser.py — Tier-2 ONLY headless browser driver for the GHL
email-2FA auth fallback (Skill 06 / Skill 44 via the orchestrator).

ROLE IN THE 3-TIER LADDER
-------------------------
This module is the THIN browser layer used by ghl_auth_fallback.py and NOTHING
else. It is one of EXACTLY TWO files in this repo allowed to carry login/password
selectors (the other is ghl_auth_fallback.py). guard-ghl-auth-fallback.sh
allowlists the banned active-login patterns ONLY in these two files and forbids
them everywhere else; the TOKEN-ONLY guard (guard-ghl-token-only.sh) keeps the
Tier-1 files (seed-ghl-auth.py + inject-ghl-auth.sh) byte-clean.

GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY

HEADLESS DISCIPLINE (mirrors inject-ghl-auth.sh D6 HARD HEADLESS GUARD)
----------------------------------------------------------------------
The driver is headless-ONLY. Any concrete engine MUST run with the inherited
headed env stripped (unset AGENT_BROWSER_HEADED) and `--headed false` forced, and
MUST disable (or redact) screenshots / HAR / traces so a password field value or
a 2FA code can never be persisted to an artifact. The 2FA code is held only in
memory for the submit and is never logged.

DEPENDENCY INJECTION (so tests use a MOCK browser — NEVER a real one)
---------------------------------------------------------------------
LoginBrowser delegates every action to an injected `engine` object. The production
engine is a headless agent-browser / Playwright adapter; the test suite injects a
MockLoginBrowser that records calls and returns scripted DOM states with ZERO
network and ZERO real browser. No model id and no client data live here.

SECRETS
-------
A password / email / 2FA code passed to a method here is used to drive the form
ONLY; it is NEVER printed, logged, or written to any artifact.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

# ── DOM SELECTOR TABLE (future-proofing §e) ───────────────────────────────────
# Every login/2FA element is abstracted to a list of fallbacks (id, name,
# aria-label, text). A GHL DOM drift is a one-line edit here, never a rewrite.
SELECTORS: dict[str, list[str]] = {
    "email": [
        "input[type=email]",
        "input[name=email]",
        "#email",
        "input[aria-label='Email']",
    ],
    "password": [
        "input[type=password]",
        "input[name=password]",
        "#password",
        "input[aria-label='Password']",
    ],
    "send_code": [
        "button[data-action='send-code']",
        "button:has-text('Send Code')",
        "button:has-text('Send Security Code')",
    ],
    "twofa_method_email": [
        "input[value='email']",
        "[data-2fa-method='email']",
        "button:has-text('Email')",
        "label:has-text('Email')",
    ],
    "twofa_method_totp_only_signal": [
        "[data-2fa-method='totp']",
        "text=Authenticator app",
        "text=Enter the code from your authenticator",
    ],
    "code_input": [
        "input[name=code]",
        "input[autocomplete='one-time-code']",
        "#security-code",
    ],
    "submit": [
        "button[type=submit]",
        "button:has-text('Verify')",
        "button:has-text('Confirm')",
    ],
    "location_picker": [
        "[data-location-picker]",
        "select[name=location]",
        ".location-switcher",
    ],
    "dashboard_liveness": [
        "[data-agency-dashboard]",
        "#app [data-loggedin='true']",
        "text=Dashboard",
    ],
    "lockout_signal": [
        "text=too many attempts",
        "text=account locked",
        "text=temporarily blocked",
    ],
    "captcha_signal": [
        "iframe[src*='captcha']",
        "text=verify you are human",
        "[data-cf-challenge]",
    ],
}

# Login origin default — reuse inject's documented default; root-only route.
DEFAULT_AGENCY_URL = "https://app.convertandflow.com"


def _assert_headless_env() -> None:
    """Replicate inject-ghl-auth.sh's hard headless guard: a headed signal must
    never survive. Strip the inherited env and refuse if a headed flag is on."""
    os.environ.pop("AGENT_BROWSER_HEADED", None)
    os.environ["AGENT_BROWSER_HEADED"] = "false"
    headed = os.environ.get("AGENT_BROWSER_HEADED", "false")
    if headed not in ("", "0", "false", "False", "FALSE", "no", "off"):
        raise RuntimeError(
            "REFUSE: a headed browser signal survived; headless is mandatory (D6)."
        )


@dataclass
class LoginBrowser:
    """Headless-only browser driver. All side effects go through `engine` (DI).

    Production callers pass a real headless agent-browser/Playwright adapter.
    Tests pass a MockLoginBrowser. This class never imports a browser library so
    importing it is cheap and side-effect free; the engine carries the real
    automation.
    """

    engine: Any
    agency_url: str = DEFAULT_AGENCY_URL
    # No browser artifact may persist a secret: screenshots/HAR/trace disabled.
    capture_artifacts: bool = field(default=False)

    def __post_init__(self) -> None:
        _assert_headless_env()
        # Belt-and-suspenders: tell the engine to disable any secret-capturing
        # artifact surface, if it supports the knob.
        disable = getattr(self.engine, "disable_artifacts", None)
        if callable(disable):
            disable()

    # ── navigation ────────────────────────────────────────────────────────────
    def open_login_origin(self) -> None:
        """Navigate the headless browser to the agency login origin (root '/',
        NEVER a deep '/login' route — same root-only discipline as inject)."""
        self.engine.navigate(self.agency_url + "/")

    # ── credential entry (the ONLY place a password is typed in this codebase) ──
    def fill_email(self, email: str) -> None:
        # GATE-D credential — used to drive the form only; never logged.
        self.engine.fill(SELECTORS["email"], email)

    def fill_password(self, password: str) -> None:
        # The single password .fill in the codebase; value never logged/printed.
        self.engine.fill(SELECTORS["password"], password)

    # ── 2FA method selection (GATE C is DOM-authoritative here) ─────────────────
    def choose_email_2fa(self) -> bool:
        """Select 'Email' as the 2FA delivery method. Return True if selected;
        return False when only an authenticator/TOTP prompt is offered (caller
        escalates to Tier 3 with the switch-to-email instruction)."""
        if self.engine.is_present(SELECTORS["twofa_method_totp_only_signal"]) and not \
                self.engine.is_present(SELECTORS["twofa_method_email"]):
            return False
        if self.engine.is_present(SELECTORS["twofa_method_email"]):
            self.engine.click(SELECTORS["twofa_method_email"])
            return True
        # No explicit chooser shown but email is the default path → treat as email
        # ONLY when there is no TOTP-only signal.
        return not self.engine.is_present(SELECTORS["twofa_method_totp_only_signal"])

    def trigger_send_code(self) -> None:
        self.engine.click(SELECTORS["send_code"])

    def submit_code(self, code: str) -> None:
        # The 2FA code is typed into the form then discarded; never logged.
        self.engine.fill(SELECTORS["code_input"], code)
        self.engine.click(SELECTORS["submit"])

    # ── liveness + safety signals ───────────────────────────────────────────────
    def wait_positive_liveness(self) -> bool:
        """Positive liveness: the agency dashboard object is present (NOT merely
        'no error' / no password field) — same discipline as activation R4."""
        return bool(self.engine.wait_for(SELECTORS["dashboard_liveness"]))

    def detect_lockout_or_captcha(self) -> Optional[str]:
        """Return 'lockout' / 'captcha' if a hard-stop signal is present, else
        None. The caller HARD STOPS to Tier 3 on any non-None result."""
        if self.engine.is_present(SELECTORS["lockout_signal"]):
            return "lockout"
        if self.engine.is_present(SELECTORS["captcha_signal"]):
            return "captcha"
        return None

    # ── self-heal token capture surface ─────────────────────────────────────────
    def read_refresh_token(self) -> str:
        """Read the fresh Firebase refresh token from the authenticated session —
        the SAME surfaces Tier 1 uses: GET /oauth/2/login/current in-page yields
        refreshToken/refreshJwt, and the Firebase IndexedDB user record also holds
        it. Returned to the caller in memory only; NEVER logged."""
        return self.engine.read_refresh_token()

    # ── multi-location ──────────────────────────────────────────────────────────
    def list_locations(self) -> list[str]:
        return list(self.engine.list_locations())

    def select_location(self, location_id: str) -> bool:
        return bool(self.engine.select_location(location_id))
