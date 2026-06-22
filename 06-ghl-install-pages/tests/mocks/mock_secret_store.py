"""MockSecretStore — dict-backed stand-in for ghl_auth_fallback.SecretStore.

Records writes so the self-heal can be asserted
(store.written["GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"]). Configurable presence of
each gate's env keys. NO real .env is ever touched. Only fabricated values.
"""
from __future__ import annotations

import os
import sys

# tools dir = <skill>/tools, two levels up from this file's tests/mocks/ dir.
_TOOLS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools")
)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_auth_fallback as _fb  # noqa: E402

REFRESH_TOKEN_KEY = _fb.REFRESH_TOKEN_KEY


class MockSecretStore:
    """In-memory secret store mirroring SecretStore's read/write + properties."""

    def __init__(self, **values: str):
        self._env: dict[str, str] = {k: v for k, v in values.items() if v is not None}
        self.written: dict[str, str] = {}

    # raw surface
    def read_secret(self, key: str) -> str:
        return (self._env.get(key, "") or "").strip()

    def write_secret(self, key: str, value: str) -> bool:
        self.written[key] = value
        self._env[key] = value  # so an immediate re-read sees the healed token
        return True

    def _first(self, keys) -> str:
        for k in keys:
            v = self.read_secret(k)
            if v:
                return v
        return ""

    # property surface (mirrors production SecretStore)
    @property
    def email(self) -> str:
        return self._first(_fb.AGENCY_EMAIL_KEYS)

    @property
    def password(self) -> str:
        return self._first(_fb.AGENCY_PASSWORD_KEYS)

    @property
    def authorized(self) -> bool:
        return self.read_secret(_fb.AUTHORIZED_KEY).lower() in _fb._TRUTHY

    @property
    def twofa_method(self) -> str:
        return self.read_secret(_fb.TWOFA_METHOD_KEY).lower()

    @property
    def gmail_mailbox(self) -> str:
        return self.read_secret(_fb.GMAIL_MAILBOX_KEY)

    @property
    def gmail_oauth(self) -> str:
        return self.read_secret(_fb.GMAIL_OAUTH_KEY)

    @property
    def location_id(self) -> str:
        return self.read_secret(_fb.LOCATION_ID_KEY)


def fully_provisioned_store(**overrides: str) -> MockSecretStore:
    """A store that PASSES all four gates by default (fabricated values only)."""
    base = {
        _fb.AUTHORIZED_KEY: "AUTHORIZE",
        _fb.AGENCY_EMAIL_KEYS[0]: "agent@example.test",
        _fb.AGENCY_PASSWORD_KEYS[0]: "FAKE-pw-not-a-real-secret",
        _fb.TWOFA_METHOD_KEY: "email",
        _fb.GMAIL_MAILBOX_KEY: "agent@example.test",
        _fb.GMAIL_OAUTH_KEY: '{"_fake":"oauth-blob"}',
    }
    base.update(overrides)
    return MockSecretStore(**base)
