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
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Mapping, Optional

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
    """Return (token, env_var_name) for the first non-empty refresh-token var, or
    ("", "") if none. SAME precedence as seed-ghl-auth.py."""
    src = env if env is not None else os.environ
    for name in REFRESH_ENV_VARS:
        val = (src.get(name, "") or "").strip()
        if val:
            return val, name
    return "", ""


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
    token, _env_name = resolve_refresh_token(env)
    if token:
        r1 = tier1_mint_and_seed(session, out, env, seed_runner=seed_runner)
        if r1.exit_code == 0:
            r1.fallback_entries = counter.value  # 0 — Tier 1 served the request
            _persist_tier(out, r1)
            return r1  # DONE — fallback never imported/entered
        # exit 2 (no usable) / exit 3 (revoked) -> fall through to Tier-2 eval.

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
        result = AuthResult(
            TIER3, False, 7, fallback_entries=counter.value,
            reason="no browser engine available for Tier-2 login",
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
    token, env_name = resolve_refresh_token(env)
    if token:
        return AuthResult(TIER1, True, 0, fallback_entries=0,
                          reason=f"would use Tier 1 (token via {env_name})")
    return AuthResult(TIER2, False, 0, fallback_entries=0,
                      reason="no token; would evaluate Tier-2 gates")


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
