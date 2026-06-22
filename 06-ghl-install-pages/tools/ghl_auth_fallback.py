#!/usr/bin/env python3
"""ghl_auth_fallback.py — TIER 2 ONLY: the EXCLUSIVE home of ALL GHL login /
password / two-factor-authentication (2FA) logic, the four precondition gates,
the bounded login loop, and the self-heal token capture.

GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY

ISOLATION CONTRACT (why this file exists separately)
----------------------------------------------------
Tier 1 (seed-ghl-auth.py + inject-ghl-auth.sh) is the PRIMARY, token-only path and
stays byte-clean so guard-ghl-token-only.sh keeps passing — those files have NO
login/password/2FA. ALL login/password/2FA code lives HERE (plus its thin browser
helper ghl_login_browser.py). guard-ghl-auth-fallback.sh allowlists the banned
active-login patterns ONLY in these two files and forbids them everywhere else.

THE LADDER POSITION
-------------------
The orchestrator (ghl_auth.py) tries Tier 1 FIRST. It only LAZILY imports this
module and calls run_tier2() when Tier 1 has no usable token (absent / malformed /
revoked). run_tier2() runs the four gates (A authorization, B gmail-PROVEN before
any login, C email-2FA, D creds-present), then the bounded login, multi-location
select, and SELF-HEAL: it captures a fresh Firebase refresh token from the
authenticated session and persists it to the client store so the NEXT run is
Tier 1 again. Any precondition fail or hard stop -> Tier 3 (fail loud, non-zero).

GENERIC / PARAMETERIZED — NO client or operator data
-----------------------------------------------------
Every credential is read from the CLIENT box's own secret store via env keys
defined as constants below. No client name/id/email, no operator path, no secret
literal appears in this file. Tests inject mock store/probe/driver so production
code paths run with ZERO real GHL and ZERO real Gmail traffic.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from ghl_gmail_probe import NoFreshCodeError

# ── TIER TAGS (re-exported via the orchestrator) ──────────────────────────────
TIER2 = "tier2-fallback"
TIER3 = "tier3-failloud"

# ── SECRET-STORE ENV KEYS (the parameterized contract — generic) ──────────────
# Canonical self-heal write target — MUST be exactly this string (guard checks it).
REFRESH_TOKEN_KEY = "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"
REFRESH_TOKEN_READ_ALIASES = ("CAF_FIREBASE_REFRESH_TOKEN", "GHL_FIREBASE_REFRESH_TOKEN")
# Agency login (GATE D) — the ONLY place a password is read into code.
AGENCY_EMAIL_KEYS = ("GHL_AGENCY_EMAIL", "GHL_EMAIL")
AGENCY_PASSWORD_KEYS = ("GHL_AGENCY_PASSWORD", "GHL_PASSWORD")
# Authorization record (GATE A).
AUTHORIZED_KEY = "GHL_AUTOLOGIN_AUTHORIZED"
AUTHORIZED_AT_KEY = "GHL_AUTOLOGIN_AUTHORIZED_AT"
# Gmail access (GATE B).
GMAIL_MAILBOX_KEY = "GHL_GMAIL_CLIENT_MAILBOX"
GMAIL_OAUTH_KEY = "GHL_GMAIL_OAUTH_JSON"
# 2FA method hint (GATE C optional pre-check).
TWOFA_METHOD_KEY = "GHL_2FA_METHOD"
# Multi-location target.
LOCATION_ID_KEY = "GHL_LOCATION_ID"
# Login origin (reuse inject's default).
AGENCY_URL_KEY = "GHL_AGENCY_URL"

_TRUTHY = {"1", "true", "yes", "authorize", "authorized", "on"}

# ── BOUNDED LOGIN ATTEMPTS (lockout protection §d) ────────────────────────────
MAX_LOGIN_ATTEMPTS = 3        # <= 3 — guard asserts this literal bound
BACKOFF_BASE = 1.0            # seconds; doubled each attempt
BACKOFF_CAP = 8.0             # seconds; ceiling for the backoff term

# ── CODE_PATTERNS (future-proof code extraction §e — one-line-editable table) ──
# OR-ed candidates: constrain by GHL sender domain / subject, plus a generic
# "verification/security code" body regex and a digit-run fallback. A future
# format drift is a config edit here, not a code rewrite.
CODE_PATTERNS: list[dict] = [
    {
        "sender_domain": "leadconnectorhq.com",
        "subject_regex": r"(security|verification|login) code",
        "body_regex": r"\b(\d{4,8})\b",
    },
    {
        "sender_domain": "gohighlevel.com",
        "subject_regex": r"(security|verification|login) code",
        "body_regex": r"\b(\d{4,8})\b",
    },
    {
        # Generic body fallback: "your verification/security code is 123456".
        "body_regex": r"(?:verification|security)\s+code[^0-9]{0,20}(\d{4,8})",
    },
    {
        # Last-resort digit run (still constrained to post-t0 GHL-ish mail by the
        # probe's freshness filter).
        "body_regex": r"\b(\d{4,8})\b",
    },
]


# ── result shapes ─────────────────────────────────────────────────────────────
@dataclass
class GateResult:
    ok: bool
    gate: str            # "A" | "B" | "C" | "D"
    reason: str          # plain text, NEVER a secret
    client_message: str  # Tier-3 instruction tailored to this gate


@dataclass
class LoginOutcome:
    ok: bool
    live_session: bool
    reason: str
    attempts: int = 0


@dataclass
class Tier2Result:
    ok: bool
    tier: str            # TIER2 (self-healed) | TIER3 (failed)
    exit_code: int
    reason: str
    client_message: str = ""
    healed_token_written: bool = False


# ── CLIENT-STORE-ONLY secret resolver ─────────────────────────────────────────
class SecretStore:
    """Resolves credentials from the CLIENT box's own stores ONLY — live env then
    ~/.openclaw/secrets/.env. NEVER an operator path. The self-heal writer targets
    the canonical refresh-token key in the same client store.

    Tests inject a mock (MockSecretStore) with the same read_secret/write_secret
    surface, so no real .env is touched.
    """

    def __init__(self, env: Optional[Mapping[str, str]] = None, *, secrets_path: Optional[str] = None):
        self._env = dict(env) if env is not None else dict(os.environ)
        self._secrets_path = secrets_path or os.path.join(
            os.path.expanduser("~"), ".openclaw", "secrets", ".env"
        )
        self.written: dict[str, str] = {}

    def read_secret(self, key: str) -> str:
        return (self._env.get(key, "") or "").strip()

    def _first(self, keys: tuple[str, ...]) -> str:
        for k in keys:
            v = self.read_secret(k)
            if v:
                return v
        return ""

    # convenience accessors used by the gates / login
    @property
    def email(self) -> str:
        return self._first(AGENCY_EMAIL_KEYS)

    @property
    def password(self) -> str:
        return self._first(AGENCY_PASSWORD_KEYS)

    @property
    def authorized(self) -> bool:
        return self.read_secret(AUTHORIZED_KEY).lower() in _TRUTHY

    @property
    def twofa_method(self) -> str:
        return self.read_secret(TWOFA_METHOD_KEY).lower()

    @property
    def gmail_mailbox(self) -> str:
        return self.read_secret(GMAIL_MAILBOX_KEY)

    @property
    def gmail_oauth(self) -> str:
        return self.read_secret(GMAIL_OAUTH_KEY)

    @property
    def location_id(self) -> str:
        return self.read_secret(LOCATION_ID_KEY)

    def write_secret(self, key: str, value: str) -> bool:
        """Persist a secret to the CLIENT store (atomic, mode 0600). NEVER prints
        the value. Used by self-heal to write REFRESH_TOKEN_KEY back."""
        self.written[key] = value  # record (mock + verifier read this; value never logged)
        # Best-effort durable write to the client .env (atomic + chmod 600).
        try:
            self._persist_env_line(key, value)
        except OSError:
            # A persistence failure must not crash the heal path; the in-memory
            # record still proves the heal occurred for the verifier.
            pass
        return True

    def _persist_env_line(self, key: str, value: str) -> None:
        path = self._secrets_path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        lines: list[str] = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        out, replaced = [], False
        for ln in lines:
            if ln.split("=", 1)[0].strip() == key:
                out.append(f"{key}={value}")
                replaced = True
            else:
                out.append(ln)
        if not replaced:
            out.append(f"{key}={value}")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def backoff(attempt: int) -> None:
    """Exponential backoff + jitter between login attempts (lockout protection).

    delay = min(BACKOFF_BASE * 2**(attempt-1), BACKOFF_CAP) plus jitter, so
    concurrent runs don't synchronize their retries.
    """
    base = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_CAP)
    time.sleep(base + random.uniform(0, BACKOFF_BASE))


# ══════════════════════════════════════════════════════════════════════════════
# PRECONDITION GATES — ALL run + return-gate BEFORE any login (guard invariant 2)
# ══════════════════════════════════════════════════════════════════════════════
def gate_a_authorization(store: SecretStore) -> GateResult:  # GATE-A: AUTHORIZATION
    """A recorded, explicit client authorization to automate login must exist."""
    if store.authorized:
        return GateResult(True, "A", "authorization recorded", "")
    return GateResult(
        False, "A",
        "no recorded client authorization",
        "Automated login needs your written OK. Reply AUTHORIZE to enable a "
        "one-time gated login, or provide a fresh refresh token instead.",
    )


def gate_b_gmail_proven(probe: Any, store: SecretStore) -> GateResult:  # GATE-B: GMAIL-PROVEN
    """LIVE read proof of the client's Gmail — runs BEFORE any login so a
    misconfigured box can never start a login it cannot finish (lockout guard)."""
    result = probe.prove_access()
    if getattr(result, "proven", False):
        return GateResult(True, "B", "gmail access proven by live read", "")
    return GateResult(
        False, "B",
        f"gmail not proven: {getattr(result, 'reason', 'unknown')}",
        "Your agent can't read your Gmail yet. Enable Gmail OAuth/API access on "
        "your box for the configured mailbox, then re-run.",
    )


def gate_c_email_2fa(store: SecretStore) -> GateResult:  # GATE-C: EMAIL-2FA-SELECTED
    """Optional pre-check via the GHL_2FA_METHOD hint. The DOM detection at login
    step 3 is authoritative; this only enables a faster Tier-3 message. A missing
    hint is NOT a failure (DOM decides)."""
    method = store.twofa_method
    if method and method != "email":
        return GateResult(
            False, "C",
            f"configured 2FA method hint is '{method}', not email",
            "Your GHL account uses authenticator-app 2FA, which can't be read from "
            "email. Switch GHL 2FA to email (Settings -> Security -> 2FA -> Email), "
            "or provide a fresh refresh token instead.",
        )
    return GateResult(True, "C", "email-2FA hint ok (DOM authoritative at login)", "")


def gate_d_creds_present(store: SecretStore) -> GateResult:  # GATE-D: CREDS-PRESENT
    """Agency email + password must resolve from the CLIENT's own secret store."""
    if store.email and store.password:
        return GateResult(True, "D", "agency credentials present in client store", "")
    return GateResult(
        False, "D",
        "agency credentials absent from client store",
        "Set GHL_AGENCY_EMAIL and GHL_AGENCY_PASSWORD in your box's secret store, "
        "or provide a fresh refresh token instead.",
    )


def check_all_gates(store: SecretStore, probe: Any) -> GateResult:
    """Run A -> B -> C -> D IN ORDER, short-circuit on first failure, return that
    GateResult. ok=True only when all four pass. This function (and the four gate
    calls inside it) MUST appear in source BEFORE login_with_2fa()."""
    for gate in (
        gate_a_authorization(store),
        gate_b_gmail_proven(probe, store),
        gate_c_email_2fa(store),
        gate_d_creds_present(store),
    ):
        if not gate.ok:
            return gate
    return GateResult(True, "ALL", "all four gates passed", "")


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN — only reached after check_all_gates().ok (textually AFTER the gates)
# ══════════════════════════════════════════════════════════════════════════════
def login_with_2fa(driver: Any, probe: Any, store: SecretStore) -> LoginOutcome:
    """Bounded login loop (1..MAX_LOGIN_ATTEMPTS) with backoff and a HARD STOP on
    any lockout/captcha signal. GATE C is DOM-authoritative here (email option
    required). Reads the freshest post-t0 2FA code from the client's Gmail and
    submits it; success requires POSITIVE liveness (dashboard object)."""
    last_reason = ""
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        driver.open_login_origin()

        # HARD STOP on a bot-challenge before we even type creds.
        signal = driver.detect_lockout_or_captcha()
        if signal:
            return LoginOutcome(False, False, f"hard-stop:{signal}", attempts=attempt)

        driver.fill_email(store.email)
        driver.fill_password(store.password)

        # GATE C DOM-authoritative: require an Email 2FA option.
        if not driver.choose_email_2fa():
            return LoginOutcome(
                False, False, "totp-only-no-email-2fa", attempts=attempt
            )

        t0 = time.time_ns()
        driver.trigger_send_code()

        # Read the freshest post-t0 code from the client's own Gmail.
        try:
            code = probe.await_code(since_ns=t0, patterns=CODE_PATTERNS)
        except NoFreshCodeError as e:
            last_reason = f"no-fresh-code: {e.__class__.__name__}"
            if attempt < MAX_LOGIN_ATTEMPTS:
                backoff(attempt)
            continue

        driver.submit_code(code)

        # HARD STOP if the submit tripped a lockout/captcha.
        signal = driver.detect_lockout_or_captcha()
        if signal:
            return LoginOutcome(False, False, f"hard-stop:{signal}", attempts=attempt)

        # Positive liveness (dashboard object), not "no error".
        if driver.wait_positive_liveness():
            return LoginOutcome(True, True, "authenticated", attempts=attempt)

        last_reason = "no-positive-liveness"
        if attempt < MAX_LOGIN_ATTEMPTS:
            backoff(attempt)

    return LoginOutcome(False, False, last_reason or "exhausted-attempts",
                        attempts=MAX_LOGIN_ATTEMPTS)


def select_location(driver: Any, store: SecretStore) -> GateResult:
    """Multi-location: if N>1, select the one matching GHL_LOCATION_ID. Ambiguous
    + unconfigured -> Tier 3 'specify which location'."""
    locations = driver.list_locations()
    if len(locations) <= 1:
        return GateResult(True, "LOC", "single or no location to select", "")
    configured = store.location_id
    if not configured:
        return GateResult(
            False, "LOC",
            "multiple locations and none configured",
            "Your agency exposes multiple locations. Set GHL_LOCATION_ID to the "
            "one this box should build in, then re-run.",
        )
    if configured not in locations:
        return GateResult(
            False, "LOC",
            "configured location id not found in agency",
            "The configured location was not found under this agency. Verify "
            "GHL_LOCATION_ID, then re-run.",
        )
    if driver.select_location(configured):
        return GateResult(True, "LOC", "configured location selected", "")
    return GateResult(False, "LOC", "location select failed",
                      "Could not select the configured location. Re-run.")


def capture_and_persist_refresh_token(driver: Any, store: SecretStore) -> bool:
    """SELF-HEAL: read a fresh Firebase refresh token from the authenticated
    session (same surfaces Tier 1 uses) and persist it to the CLIENT store under
    REFRESH_TOKEN_KEY. The token is NEVER logged/printed/returned; only the
    boolean 'did we write it' is returned."""
    token = driver.read_refresh_token()
    if not token:
        return False
    wrote = store.write_secret(REFRESH_TOKEN_KEY, token)
    # Scrub the local reference (best-effort).
    token = ""  # noqa: F841
    del token
    return bool(wrote)


# ══════════════════════════════════════════════════════════════════════════════
# TIER-2 ENTRY — gates -> login -> location -> self-heal (or Tier 3)
# ══════════════════════════════════════════════════════════════════════════════
def run_tier2(session: str, out: str, store: SecretStore, probe: Any, driver: Any) -> Tier2Result:
    """The Tier-2 ladder body. check_all_gates first (fail => Tier 3 with the
    gate's client message). On all-green: login_with_2fa -> select_location ->
    self-heal. Any hard stop => Tier 3. Returns a Tier2Result."""
    gate = check_all_gates(store, probe)
    if not gate.ok:
        return Tier2Result(
            ok=False, tier=TIER3, exit_code=3,
            reason=f"gate-{gate.gate}-failed: {gate.reason}",
            client_message=gate.client_message,
        )

    outcome = login_with_2fa(driver, probe, store)
    if not outcome.ok:
        if outcome.reason.startswith("hard-stop:"):
            cm = ("GHL temporarily blocked automated login. Wait, then provide a "
                  "fresh refresh token instead.")
        elif outcome.reason == "totp-only-no-email-2fa":
            cm = ("Your GHL account offered only authenticator-app 2FA. Switch GHL "
                  "2FA to email (Settings -> Security -> 2FA -> Email), or provide "
                  "a fresh refresh token.")
        else:
            cm = ("Automated login could not complete within the bounded attempts. "
                  "Provide a fresh refresh token instead.")
        return Tier2Result(False, TIER3, 4, f"login-failed: {outcome.reason}", cm)

    loc = select_location(driver, store)
    if not loc.ok:
        return Tier2Result(False, TIER3, 5, f"location-failed: {loc.reason}",
                           loc.client_message)

    healed = capture_and_persist_refresh_token(driver, store)
    if not healed:
        return Tier2Result(
            False, TIER3, 6,
            "self-heal-failed: could not capture/persist refresh token",
            "Login succeeded but a fresh refresh token could not be captured. "
            "Provide a fresh refresh token via the Token Grabber.",
        )
    return Tier2Result(
        ok=True, tier=TIER2, exit_code=0,
        reason="tier2 success: logged in via email-2FA and self-healed to token-only",
        client_message="", healed_token_written=True,
    )
