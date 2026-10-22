#!/usr/bin/env python3
"""ghl_auth.py — the GHL auth ORCHESTRATOR and single entry point for Skill 06
(pages/funnels) and Skill 44 (workflows). Implements the 3-tier ladder and
decides which tier runs. Contains NO login / password / 2FA code (that lives ONLY
in ghl_auth_fallback.py + ghl_login_browser.py).

GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY

THE 3-TIER LADDER
-----------------
  Tier 1 — TOKEN-ONLY (PRIMARY, default, UNCHANGED): resolve a Firebase refresh
           token from the client store and mint+seed via seed-ghl-auth.py. If the
           token is present and the mint succeeds -> DONE. The fallback module is
           NEVER imported and the fallback-entry counter stays 0.
  Tier 2 — EMAIL-2FA BOOTSTRAP (gated, one-time): entered ONLY when Tier 1 has no
           usable token (absent / mint exit 2 / revoked exit 3). The fallback is
           LAZILY imported here; it runs the four gates, the bounded login, and
           self-heals a fresh refresh token to the client store.
  Tier 3 — FAIL LOUD: a gate failed or a hard stop hit -> non-zero exit with a
           precise, plain-language client instruction. Never silently degrade.

The Tier-1 token branch is the FIRST branch and textually precedes the
ghl_auth_fallback import (guard-ghl-auth-fallback.sh invariant 7). The fallback
import is LAZY (inside the Tier-2 branch) so a valid-token run never touches it.

Refresh-token resolution goes through the ONE shared resolver
(tools/ghl_secret_resolver.py): the *_FILE indirection
(GHL_REFRESH_TOKEN_FILE) first, then the env alias chain, then (for the
process environment only) the canonical stores. See resolve_refresh_token
for the hermetic rule for explicit env mappings.

TIER-2 ENGINE CONTRACT (S06-04 open question Q2, decided): run() takes the
Tier-2 engine as caller-injected dependencies (store / probe / driver). The
production CLI injects none, so when Tier 1 cannot serve, the CLI reports
Tier 3 (exit 7) naming this contract. Wiring a production engine is a
separate, separately verified task; the gates do not change.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Mapping, Optional

import ghl_secret_resolver as _resolver  # the ONE shared secret resolver (S06-04)

# Tier tags (kept here so the orchestrator does not need to import the fallback to
# name a tier — the fallback re-uses the same string values).
TIER1 = "tier1-token"
TIER2 = "tier2-fallback"
TIER3 = "tier3-failloud"

# Env-resolution order — IDENTICAL precedence to seed-ghl-auth.py.
REFRESH_ENV_VARS = (
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
    "CAF_FIREBASE_REFRESH_TOKEN",
    "GHL_FIREBASE_REFRESH_TOKEN",
)

# *_FILE indirection for the refresh token (packet spec 05 section 6 — the
# packet's example name, implemented in the shared resolver).
REFRESH_TOKEN_FILE_VAR = "GHL_REFRESH_TOKEN_FILE"

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_SEED_SCRIPT = os.path.join(_TOOLS_DIR, "seed-ghl-auth.py")


@dataclass
class AuthResult:
    tier: str                  # TIER1 | TIER2 | TIER3
    ok: bool
    exit_code: int             # 0 ok; non-zero on Tier 3
    fallback_entries: int = 0  # 0 when Tier 1 served the request
    reason: str = ""           # plain text, NEVER a secret
    client_message: str = ""   # Tier-3 plain-language instruction (no secret)
    healed_token_written: bool = False


class Counter:
    """Tiny counter the orchestrator increments the instant it enters the Tier-2
    fallback. A SEPARATE verifier reads {tier, fallback_entries} from the side
    file (see _persist_tier) as raw evidence for DONE checks 2 / 6."""

    def __init__(self) -> None:
        self.value = 0

    def incr(self) -> None:
        self.value += 1


def resolve_refresh_token(env: Optional[Mapping[str, str]] = None) -> tuple[str, str]:
    """Return (token, source_name) for the first usable refresh token, or
    ("", "") if none. SAME precedence as seed-ghl-auth.py — both delegate
    to the ONE shared resolver (ghl_secret_resolver.attempt_resolution):
    (1) the *_FILE indirection GHL_REFRESH_TOKEN_FILE, (2) the env alias
    chain REFRESH_ENV_VARS, (3) the canonical env stores. Dummy-literal
    placeholder candidates (is_placeholder_shape) are skipped at every
    layer (a placeholder is not a usable token).

    Hermetic rule: an explicit env mapping is a COMPLETE environment (the
    mapping plus the files its *_FILE variables name) — the canonical
    stores join only for the process environment (env=None), which is the
    production path (this module's CLI, and the seed script resolving its
    own process env in full). A set-but-broken *_FILE variable raises
    ghl_secret_resolver.SecretFileError (precise, value-free); run() and
    _check() convert it into a Tier-3 report.
    """
    res = _resolve_refresh(env)
    return res.value, res.source


def _resolve_refresh(env: Optional[Mapping[str, str]] = None) -> _resolver.Resolution:
    """The detailed resolution behind resolve_refresh_token — also carries
    the placeholder sighting so run() / _check() can fail loud with it."""
    return _resolver.attempt_resolution(
        env,
        file_vars=(REFRESH_TOKEN_FILE_VAR,),
        aliases=REFRESH_ENV_VARS,
        search_stores=env is None,
        placeholder_check=_resolver.is_placeholder_shape,
    )

def tier1_mint_and_seed(
    session: str,
    out: str,
    env: Optional[Mapping[str, str]] = None,
    *,
    seed_runner=None,
) -> AuthResult:
    """Shell out to seed-ghl-auth.py --print-seed --out <out> (Tier 1). The caller
    then runs inject on the seed. Returns AuthResult(tier=TIER1, ...). NEVER
    imports the fallback module.

    `seed_runner` is a DI hook (tests pass a stub that mimics the seed exit codes);
    production runs the real seed script via subprocess.
    """
    if seed_runner is not None:
        code = seed_runner(session, out, env)
    else:
        proc = subprocess.run(
            [sys.executable, _SEED_SCRIPT, "--print-seed", "--out", out],
            capture_output=True, text=True,
            env=dict(env) if env is not None else None,
        )
        code = proc.returncode
    if code == 0:
        return AuthResult(TIER1, True, 0, fallback_entries=0,
                          reason="tier1 token mint+seed ok")
    # exit 2 = no usable token; exit 3 = revoked/expired. Both fall through to
    # the Tier-2 evaluation in run(); surface the code for the caller's branch.
    return AuthResult(TIER1, False, code, fallback_entries=0,
                      reason=f"tier1 mint returned exit {code}")


def _persist_tier(out: str, result: AuthResult) -> None:
    """Write the raw {tier, fallback_entries} side file (mode 0600) next to the
    seed out path so a SEPARATE verifier can read the routing evidence. NEVER
    contains a secret."""
    try:
        run_dir = os.path.dirname(os.path.abspath(out)) or "."
        os.makedirs(run_dir, exist_ok=True)
        path = os.path.join(run_dir, "ghl-auth-tier.json")
        payload = {
            "tier": result.tier,
            "fallback_entries": result.fallback_entries,
            "ok": result.ok,
            "exit_code": result.exit_code,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        pass


def run(
    session: str,
    out: str,
    env: Optional[Mapping[str, str]] = None,
    *,
    fallback_entry_counter: Optional[Counter] = None,
    seed_runner=None,
    store=None,
    probe=None,
    driver=None,
) -> AuthResult:
    """THE LADDER.

    (1) Try Tier 1: if a refresh token resolves AND the mint+seed succeeds -> DONE
        (fallback NEVER imported, counter stays 0).
    (2) On token absent OR mint exit 2/3 -> LAZILY import ghl_auth_fallback, build
        store/probe/driver (or use the injected ones for tests), and run the gated
        Tier-2 ladder.
    (3) Tier-2 returns success (self-healed -> Tier 2) or a Tier-3 fail-loud.

    store/probe/driver are DI hooks: production builds real ones; tests inject
    mocks so NO real GHL and NO real Gmail are touched.
    """
    counter = fallback_entry_counter or Counter()

    # ── TIER 1 (PRIMARY, FIRST BRANCH) ──────────────────────────────────────────
    try:
        resolution = _resolve_refresh(env)
    except _resolver.SecretFileError as exc:
        # A set-but-broken *_FILE indirection is a precise Tier-3 failure:
        # the error names the variable, the path, and the mode — never a
        # value. Tier 2 is NOT entered (the fallback was never evaluated).
        result = AuthResult(
            TIER3, False, 2, fallback_entries=counter.value,
            reason=str(exc),
            client_message=(
                "The secret file named by the *_FILE variable could not be "
                "used. Fix its path or permissions (owner-only, mode 0600), "
                "or unset the variable, then retry."
            ),
        )
        _persist_tier(out, result)
        return result
    token = resolution.value
    if token:
        r1 = tier1_mint_and_seed(session, out, env, seed_runner=seed_runner)
        if r1.exit_code == 0:
            r1.fallback_entries = counter.value  # 0 — Tier 1 served the request
            _persist_tier(out, r1)
            return r1  # DONE — fallback never imported/entered
        # exit 2 (no usable) / exit 3 (revoked) -> fall through to Tier-2 eval.

    # ── NIGHT MODE (P4): no password/2FA fallback, no login popups ──────────────
    # Unattended night runs STOP here when Tier 1 cannot serve: the Tier-2
    # email-2FA bootstrap is a FALLBACK that can require human-visible login
    # steps, which night mode forbids (plan P4 / checklist C5). The fallback is
    # never imported and the entry counter stays 0.
    if night_mode(env):
        result = AuthResult(
            TIER3, False, 7, fallback_entries=counter.value,
            reason="night mode: tier-1 token path failed; the unattended "
                   "night mode forbids the password/2FA fallback",
            client_message=(
                "Night mode (unattended): the token-only auth path failed and "
                "there is NO password/2FA fallback and no login popup by "
                "design. Supply a fresh refresh token and re-run."
            ),
        )
        _persist_tier(out, result)
        return result

    # ── TIER 2 EVAL (lazy import; counter increments on entry) ──────────────────
    counter.incr()
    import ghl_auth_fallback as fallback  # LAZY — only imported when Tier 1 fails

    if store is None:
        store = fallback.SecretStore(env)
    if probe is None:
        from ghl_gmail_probe import GmailProbe
        probe = GmailProbe(store.gmail_oauth, store.gmail_mailbox)
    if driver is None:
        # Production browser engine is wired by the box's stack; absent an engine
        # we cannot drive a login -> Tier 3 (never crash, never silently degrade).
        _reason7 = (
            "no browser engine available for Tier-2 login — the Tier-2 "
            "engine is caller-injected (store/probe/driver into run()); "
            "the production CLI injects none, so Tier 2 cannot execute here"
        )
        if not token and resolution.placeholder_seen:
            _reason7 += (
                "; note: refresh-token candidate(s) were PLACEHOLDER-shaped "
                "and were skipped (a placeholder is not a credential)"
            )
        result = AuthResult(
            TIER3, False, 7, fallback_entries=counter.value,
            reason=_reason7,
            client_message=(
                "Automated login requires a headless browser on this box. Install "
                "it or provide a fresh refresh token instead."
            ),
        )
        _persist_tier(out, result)
        return result

    t2 = fallback.run_tier2(session, out, store, probe, driver)
    result = AuthResult(
        tier=t2.tier,
        ok=t2.ok,
        exit_code=t2.exit_code,
        fallback_entries=counter.value,
        reason=t2.reason,
        client_message=t2.client_message,
        healed_token_written=t2.healed_token_written,
    )
    _persist_tier(out, result)
    return result


def _check(session: str, out: str, env: Optional[Mapping[str, str]] = None) -> AuthResult:
    """--check: report the tier that WOULD run without performing any login. Never
    imports the fallback (no login code touched on a check)."""
    try:
        resolution = _resolve_refresh(env)
    except _resolver.SecretFileError as exc:
        return AuthResult(TIER3, False, 2, fallback_entries=0, reason=str(exc))
    if resolution.value:
        return AuthResult(TIER1, True, 0, fallback_entries=0,
                          reason=f"would use Tier 1 (token via {resolution.source})")
    reason = "no token; would evaluate Tier-2 gates"
    if resolution.placeholder_seen:
        reason += (" (note: refresh-token candidate(s) were PLACEHOLDER-shaped "
                   "and were skipped — a placeholder is not a credential)")
    return AuthResult(TIER2, False, 0, fallback_entries=0, reason=reason)

# ═════════════════════════════════════════════════════════════════════════════
# P4 — PLAYWRIGHT AUTH BRIDGE (plan §9.4 / P4, WF-B)
# ═════════════════════════════════════════════════════════════════════════════
# The MINIMUM bridge from the EXISTING resolver -> mint -> seed chain into a
# dedicated Playwright context (the P3 opt-in lane in browser_manager.py).
# No new secret store, no password/2FA implementation, no copied Firebase
# semantics: the seed payload is minted by seed-ghl-auth.py exactly as before
# and consumed here structurally. The refresh token and the LOCATION PIT are
# DIFFERENT credentials and are never substituted for one another. After
# seeding, the ACTUAL account/location identity is validated before anything
# else runs ("not just token presence"). Exactly ONE expired-auth re-seed is
# permitted; night mode has no password/2FA fallback and opens no login popups.
# Every surfaced message is value-free and passes redact_secrets (B19):
# tokens/cookies never reach prompts, logs, traces, or git.

LOCATION_ID_ENV_VARS = ("GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID")
LOCATION_PIT_ENV_VARS = (
    "GOHIGHLEVEL_API_KEY", "GHL_API_KEY",
    "GOHIGHLEVEL_LOCATION_PIT", "GHL_LOCATION_PIT",
)
LOCATION_PIT_FILE_VAR = "GHL_LOCATION_PIT_FILE"
NIGHT_MODE_ENV_VARS = ("GHL_NIGHT_MODE", "SKILL6_NIGHT_MODE")
TOKEN_REDACTED = "[REDACTED]"

# Identity-only in-page read (NO token/cookie values leave the page): the SPA's
# authoritative cookie `a` carries {apiKey,userId,companyId}; the location id
# comes from the app route when present. Returns identity fields ONLY.
DEFAULT_IDENTITY_JS = (
    "(() => {"
    "  let i = {};"
    "  try { const m = document.cookie.match(/(?:^|; )a=([^;]*)/);"
    "        if (m) i = JSON.parse(atob(decodeURIComponent(m[1]))); } catch (e) {}"
    "  const lm = (location.pathname || '').match(/\\/location\\/([A-Za-z0-9_-]+)/);"
    "  return { userId: i.userId || '', companyId: i.companyId || '',"
    "           locationId: lm ? lm[1] : '' };"
    "})()"
)


class AuthBridgeError(RuntimeError):
    """The auth bridge refused or stopped (token missing/expired, wrong tenant,
    or the one permitted re-seed is spent). The message is ALWAYS value-free
    and redacted — never a token/cookie/PII value."""


def redact_secrets(text, secrets) -> str:
    """B19: mask every secret VALUE appearing in text before it can reach a
    prompt, log, trace, or git. Names and paths survive; values never do."""
    out = str(text)
    for s in secrets or ():
        s = str(s or "")
        if len(s) >= 6 and s in out:
            out = out.replace(s, TOKEN_REDACTED)
    return out


def night_mode(env: Optional[Mapping[str, str]] = None) -> bool:
    """Night mode = fully unattended: NO password/2FA fallback, NO login
    popups. True when GHL_NIGHT_MODE / SKILL6_NIGHT_MODE is truthy."""
    env = env if env is not None else os.environ
    for var in NIGHT_MODE_ENV_VARS:
        v = str(env.get(var, "") or "").strip().lower()
        if v in ("1", "true", "yes", "on"):
            return True
    return False


def resolve_location_pit(env: Optional[Mapping[str, str]] = None) -> tuple[str, str]:
    """Resolve the LOCATION PIT through the ONE shared resolver (no parallel
    secret store). The PIT is NOT a refresh token — never substitute one for
    the other (assert_credentials_not_substituted enforces it)."""
    res = _resolver.attempt_resolution(
        env,
        file_vars=(LOCATION_PIT_FILE_VAR,),
        aliases=LOCATION_PIT_ENV_VARS,
        search_stores=env is None,
        placeholder_check=_resolver.is_placeholder,
    )
    return res.value, res.source


def resolve_location_id(env: Optional[Mapping[str, str]] = None) -> tuple[str, str]:
    res = _resolver.attempt_resolution(
        env,
        file_vars=(),
        aliases=LOCATION_ID_ENV_VARS,
        search_stores=env is None,
        placeholder_check=_resolver.is_placeholder_shape,
    )
    return res.value, res.source


def assert_credentials_not_substituted(refresh_source: str, pit_source: str,
                                       refresh_value: str = "",
                                       pit_value: str = "") -> None:
    """REFUSE when the refresh token and the LOCATION PIT were substituted for
    one another: a refresh resolved from a PIT alias (or vice versa), or both
    resolving to the SAME value. The message names SOURCES only — never a
    value (B19)."""
    src_r, src_p = refresh_source or "", pit_source or ""
    refresh_from_pit = any(a in src_r for a in LOCATION_PIT_ENV_VARS) \
        or src_r.endswith(LOCATION_PIT_FILE_VAR)
    pit_from_refresh = any(a in src_p for a in REFRESH_ENV_VARS) \
        or src_p.endswith(REFRESH_TOKEN_FILE_VAR)
    if refresh_from_pit or pit_from_refresh:
        raise AuthBridgeError(
            "REFUSE (P4): the refresh token and the LOCATION PIT were "
            f"substituted for one another (refresh source {src_r!r}, PIT "
            f"source {src_p!r}). They are DIFFERENT credentials — fix the "
            "alias wiring. No value is printed here."
        )
    if refresh_value and pit_value and refresh_value == pit_value:
        raise AuthBridgeError(
            "REFUSE (P4): the refresh token and the LOCATION PIT resolved to "
            "the SAME value — one credential was substituted for the other. "
            "They are different credentials; fix the secret stores. No value "
            "is printed here."
        )


def validate_location_identity(actual, expected_location_id=None,
                               expected_company_id=None) -> dict:
    """Post-seed identity check (plan §9.4: validate actual dashboard and
    location identity after seeding, not just token presence). ``actual`` is
    what the seeded context reports — identity fields ONLY, never tokens.

    Rules (fail-closed):
      * at least one identity field must be present, else REFUSE (seeding is
        not proven);
      * expected_location_id given and a location came back -> must match, else
        REFUSE (wrong tenant);
      * expected_location_id given, NO location came back -> only acceptable
        when expected_company_id is given AND the company matches (else REFUSE:
        location identity NOT confirmed);
      * expected_company_id given -> must match, else REFUSE (wrong tenant)."""
    actual = dict(actual or {})
    got_loc = str(actual.get("locationId") or actual.get("location_id") or "")
    got_company = str(actual.get("companyId") or actual.get("company_id") or "")
    got_user = str(actual.get("userId") or actual.get("user_id") or "")
    if not (got_loc or got_company or got_user):
        raise AuthBridgeError(
            "REFUSE (P4): the seeded context reported NO account/location "
            "identity — seeding is not proven. STOP before any write."
        )
    if expected_location_id:
        if got_loc:
            if got_loc != str(expected_location_id):
                raise AuthBridgeError(
                    "REFUSE (P4 wrong tenant): the seeded session's location "
                    "does not match the task location. STOP before any write. "
                    "No identity value is printed here."
                )
        elif expected_company_id and got_company == str(expected_company_id):
            pass  # company-confirmed when the location id is not reported
        else:
            raise AuthBridgeError(
                "REFUSE (P4): location identity could NOT be confirmed after "
                "seeding (the session reports no location, and no matching "
                "company expectation). Not just token presence — STOP before "
                "any write."
            )
    if expected_company_id and got_company and got_company != str(expected_company_id):
        raise AuthBridgeError(
            "REFUSE (P4 wrong tenant): the seeded session's account does not "
            "match the task account. STOP before any write. No identity value "
            "is printed here."
        )
    return {"userId": got_user, "companyId": got_company, "locationId": got_loc}


# The one in-page script of the minimum bridge: (1) write the seed's Firebase
# IndexedDB record (structure minted by seed-ghl-auth.py — this script never
# re-derives Firebase semantics), (2) run the SPA's own getCurrentUser()
# login/current call with the seed's own spec (Cloudflare blocks bare
# non-browser requests; in-page fetch is the proven path), (3) write the SPA's
# cookie contract from the response exactly as inject-ghl-auth.sh does on the
# agent-browser lane, and (4) return identity fields ONLY (never tokens).
# Mirrors inject-ghl-auth.sh's proven INJECT_JS sequence, trimmed to what a
# dedicated Playwright context needs. Called as page.evaluate(JS, seed) — the
# seed rides as the evaluate ARGUMENT, never as a loggable string literal.
PLAYWRIGHT_SEED_JS = (
    "async (seed) => {"
    "  const { database, store, keyPath, entry } = seed.indexeddb;"
    "  const v = (entry && entry.value) || {};"
    "  const missing = [];"
    "  if (!v.uid) missing.push('uid');"
    "  if (typeof v.emailVerified !== 'boolean') missing.push('emailVerified');"
    "  if (typeof v.isAnonymous !== 'boolean') missing.push('isAnonymous');"
    "  if (!v.stsTokenManager || !v.stsTokenManager.refreshToken) missing.push('stsTokenManager.refreshToken');"
    "  if (!v.stsTokenManager || !v.stsTokenManager.accessToken) missing.push('stsTokenManager.accessToken');"
    "  if (missing.length) throw new Error('SEED-INVALID: missing/badtype ' + missing.join(','));"
    "  const openDb = () => new Promise((resolve, reject) => {"
    "    const req = indexedDB.open(database);"
    "    req.onupgradeneeded = (e) => { const db = e.target.result;"
    "      if (!db.objectStoreNames.contains(store)) db.createObjectStore(store, { keyPath }); };"
    "    req.onsuccess = (e) => resolve(e.target.result);"
    "    req.onerror = (e) => reject(e.target.error); });"
    "  let db = await openDb();"
    "  if (!db.objectStoreNames.contains(store)) {"
    "    const ver = db.version + 1; db.close();"
    "    db = await new Promise((resolve, reject) => {"
    "      const req = indexedDB.open(database, ver);"
    "      req.onupgradeneeded = (e) => { const d = e.target.result;"
    "        if (!d.objectStoreNames.contains(store)) d.createObjectStore(store, { keyPath }); };"
    "      req.onsuccess = (e) => resolve(e.target.result);"
    "      req.onerror = (e) => reject(e.target.error); });"
    "  }"
    "  await new Promise((resolve, reject) => {"
    "    const tx = db.transaction(store, 'readwrite');"
    "    tx.objectStore(store).put(entry);"
    "    tx.oncomplete = () => resolve();"
    "    tx.onerror = (e) => reject(e.target.error); });"
    "  const got = await new Promise((resolve, reject) => {"
    "    const tx = db.transaction(store, 'readonly');"
    "    const r = tx.objectStore(store).get(entry.fbase_key);"
    "    r.onsuccess = () => resolve(r.result);"
    "    r.onerror = (e) => reject(e.target.error); });"
    "  db.close();"
    "  if (!got || !got.value || !got.value.stsTokenManager ||"
    "      got.value.stsTokenManager.accessToken !== entry.value.stsTokenManager.accessToken) {"
    "    throw new Error('SEED-READBACK-FAILED'); }"
    "  const lc = seed.login_current;"
    "  let deviceId = '';"
    "  try { deviceId = localStorage.getItem('deviceId') || ''; } catch (e) {}"
    "  if (!deviceId) { deviceId = (crypto && crypto.randomUUID) ? crypto.randomUUID()"
    "    : ('dev-' + Date.now());"
    "    try { localStorage.setItem('deviceId', deviceId); } catch (e) {} }"
    "  const lcHeaders = Object.assign({}, lc.headers, { 'device-id': deviceId });"
    "  let i = null, lastErr = '';"
    "  for (let attempt = 1; attempt <= 3; attempt++) {"
    "    try {"
    "      const resp = await fetch(lc.url, { method: lc.method || 'GET',"
    "        headers: lcHeaders, mode: 'cors', credentials: 'omit' });"
    "      if (resp.status === 200) {"
    "        const cand = await resp.json();"
    "        if (cand && typeof cand.apiKey === 'string' && cand.apiKey.length >= 8 &&"
    "            typeof cand.userId === 'string' && cand.userId.length >= 8) { i = cand; break; }"
    "        lastErr = 'LOGIN-CURRENT-NONAUTH';"
    "      } else { lastErr = 'LOGIN-CURRENT-' + resp.status; }"
    "    } catch (e) { lastErr = 'LOGIN-CURRENT-FETCH'; }"
    "    if (attempt < 3) await new Promise(r => setTimeout(r, 400 * attempt));"
    "  }"
    "  if (!i) throw new Error('LOGIN-CURRENT-FAILED: ' + lastErr);"
    "  const ck = seed.cookies;"
    "  const path = (ck.attrs && ck.attrs.path) || '/';"
    "  const maxAge = (ck.attrs && ck.attrs.maxAge) || 31536000;"
    "  function registrableDomain(host) {"
    "    if (!host || /^[0-9.]+$/.test(host) || host === 'localhost') return '';"
    "    const parts = host.split('.');"
    "    return parts.length < 2 ? '' : parts.slice(-2).join('.');"
    "  }"
    "  const dom = registrableDomain(location.hostname);"
    "  const attrs = '; path=' + path + '; Max-Age=' + maxAge +"
    "    (dom ? '; domain=' + dom + '; secure' : '');"
    "  const aObj = { apiKey: i.apiKey, userId: i.userId, companyId: i.companyId };"
    # RAW cookie values, exactly as the proven injector
    # (tools/inject-ghl-auth.sh) and the SPA's own setter write them: the SPA
    # getter reads the cookie value raw and applies atob to it, so
    # percent-escaping btoa output turns '+', '/' and '=' into %2B %2F %3D and
    # atob throws InvalidCharacterError -> auth/get returns user_not_logged_in
    # despite a successful mint. NEVER encodeURIComponent a cookie value here.
    "  document.cookie = ck.a_name + '=' + btoa(JSON.stringify(aObj)) + attrs;"
    # D5 — SURVIVAL CONTRACT. The SPA's boot unconditionally deletes these six
    # cookie names (30 writes: every name x domain=app.gohighlevel.com /
    # domain=gohighlevel.com / bare) and then RE-AUTHENTICATES from what
    # persisted. Two persisted artifacts decide whether it comes back logged in:
    #   (1) cookie custom-firebase-token — the Firebase custom token. The SPA's
    #       own setter takes it from the login/current response field `token`,
    #       NOT from a field named `firebaseToken`. The seed's token_map names
    #       the COOKIE `firebaseToken`, so a direct i[field] read misses it and
    #       the cookie is never written — the boot then has nothing to sign in
    #       with and every other seeded cookie stays deleted.
    #   (2) localStorage loginDate — written by the SPA after a real auth and
    #       read on boot to decide whether the persisted login is usable.
    # Measured 2x2 on fresh profiles: seed alone -> wiped; +token -> wiped;
    # +loginDate -> wiped; +both -> auth/get ok and the location route survives
    # a reload AND a fresh navigation. Missing either one is the D5 failure.
    "  const RESPONSE_ALIAS = { firebaseToken: 'token' };"
    "  for (const [field, name] of Object.entries(ck.token_map)) {"
    "    const val = i[field] || i[RESPONSE_ALIAS[field]] || '';"
    "    if (val) document.cookie = name + '=' + val + attrs;"
    "  }"
    "  try { localStorage.setItem('loginDate', new Date().toISOString()); }"
    "  catch (e) {}"
    "  const lm = (location.pathname || '').match(/\\/location\\/([A-Za-z0-9_-]+)/);"
    "  return { userId: i.userId, companyId: i.companyId,"
    "           locationId: lm ? lm[1] : '' };"
    "}"
)


def _resolve_page(context):
    """The single page the bridge seeds (first owned page of the owned context,
    creating one when the context is fresh).

    CONTRACT: this page is the SINGLE SOURCE OF TRUTH for the seeded session.
    The seed lands in this page's IndexedDB + cookie jar; the caller MUST
    navigate THIS page object (the one ``bridge_seed_into_context`` returns),
    never a fresh ``context.new_page()`` — a second page is a different origin
    store partition and its auth/get throws SecurityError / user_not_logged_in
    even though the mint succeeded.

    CALLER-ORDER PRECONDITION (B4/D5): the page must ALREADY be on the GHL app
    origin (https://app.gohighlevel.com) before the bridge runs. A fresh owned
    context starts on about:blank, an opaque origin where IndexedDB open throws
    SecurityError, document.cookie is unusable, and localStorage is unavailable —
    the seed then fails or silently lands nowhere. ``bridge_seed_into_context``
    ENFORCES this (``_require_ghl_origin``) and refuses with a precondition error
    naming the fix; it never navigates on the caller's behalf."""
    try:
        pages = getattr(context, "pages", None) or []
        if pages:
            return pages[0]
        return context.new_page()
    except Exception as exc:  # noqa: BLE001 - surfaced as a redacted blocker
        raise AuthBridgeError(
            "REFUSE (P4): no usable page in the owned context for seeding."
        ) from exc


GHL_APP_ORIGIN = "https://app.gohighlevel.com"

# about:blank and other opaque origins — a page here has no origin store to seed.
_OPAQUE_ORIGIN_PREFIXES = ("about:", "data:", "blob:", "")


def _page_url(page):
    """The page's own URL, or None when the object exposes no ``url`` at all.

    None means a DI double (a fake page in tests), not a real Playwright page:
    every real page carries ``.url``. ``_require_ghl_origin`` skips the check
    for those doubles so the bridge stays unit-testable without a browser."""
    if not hasattr(page, "url"):
        return None
    try:
        return str(getattr(page, "url", "") or "")
    except Exception:  # noqa: BLE001 - a closed page is a precondition failure
        return ""


def _require_ghl_origin(page) -> None:
    """B4 — REFUSE to seed a page that is not on the GHL app origin.

    Reads the page's own URL (no navigation, no network): a page on about:blank
    or any other origin cannot hold the seed, and seeding it is exactly the
    failure this guard exists to stop. The error is a PRECONDITION error: it
    tells the caller to navigate first, and it never mutates the page."""
    url = _page_url(page)
    if url is None:
        return  # DI double with no url attribute — not a real page
    if url.startswith(GHL_APP_ORIGIN):
        return
    if url.startswith(_OPAQUE_ORIGIN_PREFIXES) or not url:
        raise AuthBridgeError(
            "REFUSE (P4 precondition): the bridge page is on an opaque origin "
            f"({url or 'no url'}) — IndexedDB and cookies cannot be seeded "
            "there. Navigate the owned page to "
            f"{GHL_APP_ORIGIN}/ FIRST, then call the bridge. The bridge never "
            "navigates for the caller."
        )
    raise AuthBridgeError(
        "REFUSE (P4 precondition): the bridge page is on the wrong origin "
        f"({url.split('?')[0][:80]}), not {GHL_APP_ORIGIN}. The seed must land "
        "on the GHL app origin — navigate the owned page there FIRST."
    )


class BridgeReceipt(dict):
    """The REDACTED, JSON-serializable bridge receipt.

    The seeded page rides as the ``page`` ATTRIBUTE, never as a key: a receipt
    is what gets logged/printed (B19), and a live page handle must never land in
    a serialized receipt. Callers navigate ``receipt.page`` — the exact page the
    seed was applied to — instead of opening a second page (a second page is a
    different store partition and reads as user_not_logged_in)."""

    def __init__(self, *args, page=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = page

    def copy(self):
        return BridgeReceipt(self, page=self.page)

def bridge_seed_into_context(context, seed, *,
                             expected_location_id=None,
                             expected_company_id=None,
                             identity_fetcher=None) -> dict:
    """The MINIMUM Playwright-context bridge for a seed minted by
    seed-ghl-auth.py (plan §9.4 — no new password/2FA implementation, no copied
    Firebase semantics, no parallel secret store).

    1. Apply the seed structurally through ONE in-page script (IndexedDB record
       + the SPA cookie contract via the SPA's own login/current call).
    2. Fetch the ACTUAL identity and validate it (validate_location_identity)
       BEFORE anything else runs.
    3. Return a REDACTED receipt — identity fields and counters only, never a
       token or cookie value (B19). The receipt's ``page`` ATTRIBUTE is the
       exact page object the seed was applied to; callers navigate THAT page
       (see _resolve_page's contract) rather than opening another one.

    Never drives a login form, never opens a login popup, never falls back to
    password/2FA (D7 hard rule — night mode is implicit here)."""
    seed = dict(seed or {})
    secrets = []
    try:
        entry_value = seed.get("indexeddb", {}).get("entry", {}).get("value", {})
        for key in ("accessToken", "refreshToken"):
            tok = (entry_value.get("stsTokenManager") or {}).get(key)
            if tok:
                secrets.append(tok)
    except Exception:  # noqa: BLE001 - redaction is best-effort belt
        pass

    page = _resolve_page(context)
    # B4 — PRECONDITION, enforced before any seed work: the bridge page must
    # already be on the GHL app origin. A fresh owned context sits on
    # about:blank, where IndexedDB/cookies/localStorage are all unusable, and
    # seeding there fails with an opaque SecurityError. Refusing here names the
    # one-line fix (navigate first) instead of surfacing that opaque error.
    _require_ghl_origin(page)
    try:
        if identity_fetcher is not None:
            raw_identity = identity_fetcher(context)
        else:
            raw_identity = page.evaluate(PLAYWRIGHT_SEED_JS, seed)
    except AuthBridgeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AuthBridgeError(
            "REFUSE (P4): seeding the owned Playwright context failed ("
            + redact_secrets(str(exc.__class__.__name__), secrets)
            + "). No password/2FA fallback and no login popup — STOP."
        ) from exc

    # EXPIRED-CLASS (login bounce): the seed applied but the session carries NO
    # identity — the token lapsed or never authenticated. This is the ONE case
    # the caller may re-seed (exactly once, capped by mint_and_bridge); it is
    # RETURNED as an expired shape (never raised) so the bounded re-seed path
    # can fire. Wrong-tenant/mismatch below stays terminal (raised).
    raw_identity = dict(raw_identity or {})
    if not any(raw_identity.get(k) for k in
               ("userId", "user_id", "companyId", "company_id",
                "locationId", "location_id")):
        return BridgeReceipt(
            {"ok": False, "state": "SESSION_EXPIRED", "redacted": True},
            page=page)

    identity = validate_location_identity(
        raw_identity,
        expected_location_id=expected_location_id,
        expected_company_id=expected_company_id,
    )
    return BridgeReceipt(
        {"ok": True, "state": "OK", "identity": identity, "redacted": True},
        page=page)


def mint_and_bridge(context, session, out, *,
                    env: Optional[Mapping[str, str]] = None,
                    expected_location_id=None,
                    expected_company_id=None,
                    seed_runner=None,
                    identity_fetcher=None) -> dict:
    """resolve -> mint (the EXISTING seed-ghl-auth.py Tier-1 chain) -> bridge
    into the owned Playwright context -> validate identity. Exactly ONE
    expired-auth re-seed is permitted (the re-mint reuses the same token-only
    path — never a login form); after that the bridge STOPS with a redacted
    blocker (browser_manager.bounded_retry_with_reseed supplies the cap).

    Raises AuthBridgeError (redacted, value-free) on token missing / revoked /
    expired / wrong tenant. Returns the REDACTED bridge receipt plus
    ``reseed_count``."""
    import browser_manager as _bm  # same-dir module; lazy (import-only coupling)

    env = env if env is not None else os.environ
    expected_location_id = (expected_location_id if expected_location_id is not None
                            else resolve_location_id(env)[0] or None)
    pit_value, pit_source = resolve_location_pit(env)
    resolution = _resolve_refresh(env)
    assert_credentials_not_substituted(
        resolution.source, pit_source,
        refresh_value=resolution.value, pit_value=pit_value)
    secrets = [resolution.value] if resolution.value else []

    def _mint() -> bool:
        res = tier1_mint_and_seed(session, out, env, seed_runner=seed_runner)
        return res.exit_code == 0

    if not resolution.value:
        raise AuthBridgeError(
            "REFUSE (P4): no usable refresh token (checked the *_FILE "
            "indirection, the env alias chain, and the canonical stores). "
            "STOP: no password/2FA fallback, no login popup — supply a fresh "
            "refresh token and re-run."
        )
    if not _mint():
        raise AuthBridgeError(
            "REFUSE (P4): token mint FAILED — the refresh token is "
            "revoked/expired or unusable. STOP: no password/2FA fallback, no "
            "login popup. Re-grab a fresh refresh token (Convert and Flow "
            "Token Grabber) and re-run."
        )

    def _operation() -> dict:
        try:
            with open(out, encoding="utf-8") as fh:
                seed = json.load(fh)
        except (OSError, ValueError) as exc:
            raise AuthBridgeError(
                "REFUSE (P4): the minted seed file could not be read."
            ) from exc
        return bridge_seed_into_context(
            context, seed,
            expected_location_id=expected_location_id,
            expected_company_id=expected_company_id,
            identity_fetcher=identity_fetcher)

    reseed_state = {"count": 0}

    def _check(result) -> str:
        return "SESSION_EXPIRED" if result.get("state") == "SESSION_EXPIRED" else "OK"

    def _reseed() -> bool:
        reseed_state["count"] += 1
        return _mint()

    try:
        receipt = _bm.bounded_retry_with_reseed(
            _operation,
            check_session=_check,
            reseed=_reseed,
            max_transient_attempts=1,
            max_reseed_attempts=1,
            base_delay=0.05,
        )
    except _bm.SessionExpiredError as exc:
        raise AuthBridgeError(redact_secrets(str(exc), secrets)) from exc
    except AuthBridgeError as exc:
        raise AuthBridgeError(redact_secrets(str(exc), secrets)) from exc

    receipt = receipt.copy()  # keeps the seeded page handle off the dict keys
    receipt["reseed_count"] = reseed_state["count"]
    receipt["redacted"] = True
    return receipt


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="GHL auth orchestrator — 3-tier ladder (token-only primary)"
    )
    ap.add_argument("--session", required=True, help="browser session id")
    ap.add_argument("--out", required=True, help="seed JSON out path")
    ap.add_argument("--check", action="store_true",
                    help="report the tier that WOULD run; perform no login")
    args = ap.parse_args(argv)

    if args.check:
        res = _check(args.session, args.out)
        print(json.dumps({"tier": res.tier, "reason": res.reason,
                           "fallback_entries": res.fallback_entries}))
        return res.exit_code

    res = run(args.session, args.out)
    # Emit routing only (no secret). Tier-3 surfaces the client instruction.
    out_obj = {"tier": res.tier, "ok": res.ok, "fallback_entries": res.fallback_entries}
    if res.tier == TIER3:
        out_obj["client_message"] = res.client_message
    print(json.dumps(out_obj))
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
