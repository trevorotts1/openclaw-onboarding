"""MockGHL — a mock browser ENGINE + a LoginBrowser built around it, for the
auth-fallback tests. NEVER opens a real browser and NEVER touches a real GHL
account. All DOM state is scripted; all I/O is in-memory; zero lockout risk.

The mock plugs in as the `engine` that the PRODUCTION ghl_login_browser.LoginBrowser
delegates to, so the production driver code path runs unchanged against scripted
DOM responses. It records attempt_count, password_filled, and the send-code time.
"""
from __future__ import annotations

import os
import sys

_TOOLS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools")
)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from ghl_login_browser import LoginBrowser  # noqa: E402

# Fabricated refresh token emitted by self-heal (NOT a real secret).
_FAKE_REFRESH_TOKEN = "FAKErefreshTOKENfakeREFRESHtoken0123456789"


class MockBrowserEngine:
    """Scripted headless-browser engine. Configures one login scenario.

    Flags
    -----
    offers_email_2fa : bool   — an Email 2FA option is present.
    only_totp : bool          — only authenticator/TOTP is offered (no email).
    lockout_on_attempt : int|None — emit a lockout signal starting at this attempt.
    captcha : bool            — emit a captcha signal.
    liveness : bool           — wait_positive_liveness succeeds.
    locations : list[str]     — list_locations result.
    refresh_token_to_emit : str — value read_refresh_token returns.
    """

    def __init__(self, *, offers_email_2fa: bool = True, only_totp: bool = False,
                 lockout_on_attempt=None, captcha: bool = False, liveness: bool = True,
                 locations=None, refresh_token_to_emit: str = _FAKE_REFRESH_TOKEN):
        self.offers_email_2fa = offers_email_2fa
        self.only_totp = only_totp
        self.lockout_on_attempt = lockout_on_attempt
        self.captcha = captcha
        self.liveness = liveness
        self.locations = list(locations) if locations is not None else []
        self.refresh_token_to_emit = refresh_token_to_emit

        # records
        self.attempt_count = 0
        self.password_filled = 0
        self.email_filled = 0
        self.fired_send_code_at_ns: list[int] = []
        self.artifacts_disabled = False
        self.call_log: list[str] = []

    # the production LoginBrowser asks the engine to disable artifacts
    def disable_artifacts(self) -> None:
        self.artifacts_disabled = True

    def navigate(self, url: str) -> None:
        self.attempt_count += 1  # one navigate == one login attempt to the origin
        self.call_log.append("navigate")

    def fill(self, selectors, value: str) -> None:
        # We can tell which field by the selector list identity.
        from ghl_login_browser import SELECTORS
        if selectors is SELECTORS["password"]:
            self.password_filled += 1
            self.call_log.append("fill_password")
        elif selectors is SELECTORS["email"]:
            self.email_filled += 1
            self.call_log.append("fill_email")
        elif selectors is SELECTORS["code_input"]:
            self.call_log.append("fill_code")
        else:
            self.call_log.append("fill_other")

    def click(self, selectors) -> None:
        from ghl_login_browser import SELECTORS
        if selectors is SELECTORS["send_code"]:
            import time
            self.fired_send_code_at_ns.append(time.time_ns())
            self.call_log.append("send_code")
        elif selectors is SELECTORS["submit"]:
            self.call_log.append("submit")
        else:
            self.call_log.append("click_other")

    def is_present(self, selectors) -> bool:
        from ghl_login_browser import SELECTORS
        if selectors is SELECTORS["twofa_method_email"]:
            return self.offers_email_2fa and not self.only_totp
        if selectors is SELECTORS["twofa_method_totp_only_signal"]:
            return self.only_totp
        if selectors is SELECTORS["lockout_signal"]:
            return bool(self.lockout_on_attempt is not None
                        and self.attempt_count >= self.lockout_on_attempt)
        if selectors is SELECTORS["captcha_signal"]:
            return self.captcha
        return False

    def wait_for(self, selectors) -> bool:
        from ghl_login_browser import SELECTORS
        if selectors is SELECTORS["dashboard_liveness"]:
            return self.liveness
        return False

    def read_refresh_token(self) -> str:
        return self.refresh_token_to_emit

    def list_locations(self):
        return list(self.locations)

    def select_location(self, location_id: str) -> bool:
        return location_id in self.locations


def build_driver(**engine_kwargs) -> LoginBrowser:
    """Wrap a scripted MockBrowserEngine in the PRODUCTION LoginBrowser (DI)."""
    return LoginBrowser(engine=MockBrowserEngine(**engine_kwargs))
