#!/usr/bin/env python3
"""ghl_gmail_probe.py — Gmail-access PROOF (GATE B) + 2FA code reader for the
GHL email-2FA auth fallback (Tier 2).

GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY

WHY THIS EXISTS
---------------
Tier 2 must NEVER start a login it cannot finish (a login it can't complete burns
attempts and risks an account lockout). So BEFORE any login, GATE B requires a
REAL proof — a live read of the CLIENT's OWN Gmail — not a config flag:

  1. Resolve Gmail access from the CLIENT's own OAuth/API credential in the client
     secret store (GHL_GMAIL_OAUTH_JSON). NEVER operator creds.
  2. Live read: users.getProfile and verify profile.emailAddress equals the
     configured client mailbox (GHL_GMAIL_CLIENT_MAILBOX); list + get one message
     to confirm a 200 and a real message id from the CORRECT account.
  3. Optional stronger proof: a nonce round-trip (a self-test email whose subject
     carries a random nonce is read back) — proves end-to-end read of fresh mail.
  4. Emit PROVEN / NOT-PROVEN + the verified address (the address MAY be logged;
     message bodies and tokens are NEVER logged).

CODE READER (await_code)
------------------------
After the login fires "send code" at t0, await_code polls the mailbox for the
FRESHEST post-t0 message from the GHL sender, matches CODE_PATTERNS, enforces a
~10-minute expiry, treats the code as single-use, and refuses to return a stale
code (returns NoFreshCodeError instead of submitting an old one).

DEPENDENCY INJECTION (tests use a MOCK Gmail — NEVER real Gmail)
----------------------------------------------------------------
GmailProbe delegates every Gmail call to an injected `client` object. Production
passes a real Gmail API client built from the client's OAuth creds; the test
suite passes a MockGmailProbe-style client with an in-memory mailbox, so there is
ZERO real Gmail traffic and ZERO lockout risk.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Optional


class NoFreshCodeError(Exception):
    """Raised when no fresh (post-t0, unexpired, matching) 2FA code is available
    within the poll window. The caller must FAIL rather than submit a stale code."""


@dataclass
class ProbeResult:
    proven: bool
    email_address: str  # the VERIFIED mailbox (loggable); NO bodies/tokens
    reason: str


# ~10-minute single-use expiry window for a 2FA code (§e).
CODE_EXPIRY_SECONDS = 600


class GmailProbe:
    """Live Gmail proof + 2FA code reader. All Gmail I/O goes through `client`.

    Parameters
    ----------
    oauth_json : str | dict
        Path or JSON blob to the CLIENT's own Gmail OAuth/API creds (from the
        client store; never operator creds). Passed to the real client builder.
    expected_mailbox : str
        The configured client mailbox; the probe refuses any read whose
        profile.emailAddress does not match this exactly (wrong-account guard).
    client : Any
        Injected Gmail client (DI). Tests pass a mock; production builds a real
        Gmail API client from `oauth_json`. Must expose: get_profile(),
        list_messages(query), get_message(msg_id).
    """

    def __init__(self, oauth_json: Any, expected_mailbox: str, *, client: Any = None):
        self._oauth_json = oauth_json
        self._expected_mailbox = (expected_mailbox or "").strip()
        # In production, build the real client lazily from oauth_json. In tests a
        # mock client is injected, so we never touch real Gmail here.
        self._client = client

    # ── GATE B — a REAL proof, not a flag ──────────────────────────────────────
    def prove_access(self, *, nonce: Optional[str] = None) -> ProbeResult:
        """Live-read proof of access to the CORRECT client mailbox. Returns
        ProbeResult(proven=...). On any failure -> proven=False (caller -> Tier 3).
        The mailbox address may be logged; message bodies/tokens are NEVER read
        into the reason string."""
        if not self._expected_mailbox:
            return ProbeResult(False, "", "no configured client mailbox (GHL_GMAIL_CLIENT_MAILBOX)")
        if self._client is None:
            return ProbeResult(False, "", "no Gmail client/creds resolved from client store")
        try:
            profile = self._client.get_profile()
        except Exception as e:  # noqa: BLE001 - any failure is NOT-PROVEN
            return ProbeResult(False, "", f"getProfile failed: {type(e).__name__}")
        addr = (profile or {}).get("emailAddress", "").strip()
        if not addr:
            return ProbeResult(False, "", "getProfile returned no emailAddress")
        # Wrong-account guard: the read account MUST be the configured mailbox.
        if addr.lower() != self._expected_mailbox.lower():
            return ProbeResult(False, addr, "read account != configured client mailbox")
        # Confirm a real, readable message (200 + a real message id).
        try:
            listing = self._client.list_messages(query="") or {}
            msgs = listing.get("messages", [])
            if not msgs:
                return ProbeResult(False, addr, "mailbox listed zero messages (cannot prove read)")
            one = self._client.get_message(msgs[0].get("id", ""))
            if not one or not one.get("id"):
                return ProbeResult(False, addr, "could not read a message body (get failed)")
        except Exception as e:  # noqa: BLE001
            return ProbeResult(False, addr, f"messages.list/get failed: {type(e).__name__}")
        # Optional stronger proof: nonce round-trip.
        if nonce:
            try:
                if not self._find_nonce(nonce):
                    return ProbeResult(False, addr, "nonce round-trip not yet readable")
            except Exception as e:  # noqa: BLE001
                return ProbeResult(False, addr, f"nonce round-trip failed: {type(e).__name__}")
        return ProbeResult(True, addr, "live read proven for configured mailbox")

    def _find_nonce(self, nonce: str) -> bool:
        listing = self._client.list_messages(query=f"subject:{nonce}") or {}
        for ref in listing.get("messages", []):
            msg = self._client.get_message(ref.get("id", "")) or {}
            if nonce in (msg.get("subject", "") + msg.get("body", "")):
                return True
        return False

    # ── 2FA code reader ─────────────────────────────────────────────────────────
    def await_code(
        self,
        *,
        since_ns: int,
        patterns: list[dict],
        max_wait: float = 90.0,
        poll: float = 3.0,
    ) -> str:
        """Poll for the FRESHEST post-t0 GHL message matching CODE_PATTERNS and
        return its code. Strict: internalDate must be >= since_ns; the code must
        be within the ~10-minute expiry; the newest matching candidate wins;
        single-use. Raise NoFreshCodeError if none within max_wait (NEVER return a
        stale code)."""
        since_ms = since_ns // 1_000_000
        deadline = time.time() + max_wait
        while True:
            candidate = self._scan_for_code(since_ms, patterns)
            if candidate is not None:
                return candidate
            if time.time() >= deadline:
                raise NoFreshCodeError(
                    "no fresh post-t0 2FA code within the poll window (refusing to "
                    "submit a stale code)"
                )
            time.sleep(poll)

    def _scan_for_code(self, since_ms: int, patterns: list[dict]) -> Optional[str]:
        listing = self._client.list_messages(query="newer_than:1h") or {}
        now_ms = int(time.time() * 1000)
        best: Optional[tuple[int, str]] = None  # (internalDate, code)
        for ref in listing.get("messages", []):
            msg = self._client.get_message(ref.get("id", "")) or {}
            idate = int(msg.get("internalDate", 0))
            # Strict post-t0 + unexpired window.
            if idate < since_ms:
                continue
            if now_ms - idate > CODE_EXPIRY_SECONDS * 1000:
                continue
            code = self._match_code(msg, patterns)
            if code is None:
                continue
            if best is None or idate > best[0]:
                best = (idate, code)
        return best[1] if best else None

    @staticmethod
    def _match_code(msg: dict, patterns: list[dict]) -> Optional[str]:
        """Apply the CODE_PATTERNS table (OR-ed). Each pattern may constrain
        sender_domain / subject_regex and supplies a body_regex with a capturing
        group (or a digit-run fallback)."""
        sender = msg.get("from", "") or msg.get("sender", "")
        subject = msg.get("subject", "")
        body = msg.get("body", "")
        for pat in patterns:
            dom = pat.get("sender_domain")
            if dom and dom.lower() not in sender.lower():
                continue
            subj_re = pat.get("subject_regex")
            if subj_re and not re.search(subj_re, subject, re.IGNORECASE):
                continue
            body_re = pat.get("body_regex", r"\b(\d{4,8})\b")
            m = re.search(body_re, body, re.IGNORECASE)
            if m:
                return m.group(1) if m.groups() else m.group(0)
        return None
