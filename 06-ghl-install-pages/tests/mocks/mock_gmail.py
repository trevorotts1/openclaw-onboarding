"""MockGmail — in-memory Gmail client + a MockGmailProbe-style wrapper for the
auth-fallback tests. NEVER touches real Gmail; zero network, zero lockout risk.

The mock Gmail *client* implements the get_profile / list_messages / get_message
surface that ghl_gmail_probe.GmailProbe drives, so the PRODUCTION probe code path
(prove_access + await_code) is exercised against an in-memory mailbox.
"""
from __future__ import annotations

import os
import sys
import time

_TOOLS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools")
)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from ghl_gmail_probe import GmailProbe  # noqa: E402


class MockGmailClient:
    """In-memory Gmail API stand-in.

    Parameters
    ----------
    profile_address : str
        What users.getProfile().emailAddress returns (set != expected to simulate
        a wrong-account read).
    messages : list[dict]
        Mailbox, newest-anywhere; each dict carries id, internalDate (epoch-ms),
        from, subject, body.
    fail_profile / fail_list : bool
        Simulate API errors for the NOT-PROVEN paths.
    """

    def __init__(self, *, profile_address: str, messages=None,
                 fail_profile: bool = False, fail_list: bool = False,
                 live_code: str = ""):
        self.profile_address = profile_address
        self.messages = list(messages or [])
        self.fail_profile = fail_profile
        self.fail_list = fail_list
        # live_code: a 2FA code that "arrives" the FIRST time the mailbox is read
        # after send-code fires — its internalDate is stamped NOW, so it is always
        # fresh relative to the login's t0 (deterministic; mirrors a real inbound
        # email). This avoids the timing flake of a fixed-timestamp fixture that
        # may pre-date t0.
        self._live_code = live_code
        self._live_emitted = False

    def _materialize_live(self) -> None:
        if self._live_code and not self._live_emitted:
            # Stamp the live code a hair in the FUTURE so it is unconditionally
            # fresh relative to the login's t0 (which is captured on the real
            # clock just before await_code polls). A future internalDate still
            # satisfies the probe's expiry filter (now_ms - idate is negative,
            # i.e. <= the 10-min window), so this is deterministic, not flaky.
            self.messages.append(ghl_code_message(
                msg_id="__live__", code=self._live_code, age_ms=-2000))
            self._live_emitted = True

    def get_profile(self) -> dict:
        if self.fail_profile:
            raise RuntimeError("simulated getProfile failure")
        return {"emailAddress": self.profile_address}

    def list_messages(self, query: str = "") -> dict:
        if self.fail_list:
            raise RuntimeError("simulated messages.list failure")
        self._materialize_live()
        # Return refs newest-first (the probe re-reads internalDate per message).
        refs = sorted(self.messages, key=lambda m: m.get("internalDate", 0), reverse=True)
        return {"messages": [{"id": m["id"]} for m in refs]}

    def get_message(self, msg_id: str) -> dict:
        for m in self.messages:
            if m.get("id") == msg_id:
                return dict(m)
        return {}


def now_ms() -> int:
    return int(time.time() * 1000)


def ghl_code_message(*, msg_id: str, code: str, age_ms: int = 0,
                     sender: str = "no-reply@leadconnectorhq.com",
                     subject: str = "Your login security code") -> dict:
    """Build a GHL-style 2FA email carrying `code`, `age_ms` old (0 = just now)."""
    return {
        "id": msg_id,
        "internalDate": now_ms() - age_ms,
        "from": sender,
        "subject": subject,
        "body": f"Your verification code is {code}. It expires in 10 minutes.",
    }


def build_probe(client: MockGmailClient, expected_mailbox: str) -> GmailProbe:
    """Wrap the mock client in the PRODUCTION GmailProbe (DI), so prove_access /
    await_code run real code against the in-memory mailbox."""
    return GmailProbe('{"_fake":"oauth"}', expected_mailbox, client=client)
