#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/custom_values_check.py
# THE FOUR LOCATION CUSTOM VALUES, CHECKED — never-a-real-token gate
# (U02 item 7; the same contract surface as live_verify_template.py).
# -----------------------------------------------------------------------------
# WHAT THIS OWNS
#   The engine's PYTHON code reads ZERO location custom-values; these four are
#   the SNAPSHOT'S OWN plumbing, consumed by the tag -> notification GHL
#   workflow (config/anthology-snapshot-contract.json location_custom_values.
#   required). Each must exist BY KEY on the location, each holding ONLY a
#   clearly-labeled REPLACE-ME placeholder: the TEMPLATE location must never
#   carry a real hook URL or a real Authorization token (never-a-real-token,
#   Skill 38 rule). This module checks exactly that — READ-ONLY, fail-closed,
#   contract-driven. It NEVER creates, NEVER updates, NEVER deletes, and NEVER
#   prints a value. A real-looking value is REFUSED (exit 5), never reported
#   as a clean pass.
#
# FAIL-CLOSED, BOTH DIRECTIONS, LIKE THE fieldKey GATE:
#   - a missing contract key on the location  -> FAIL (ok=False, found/missing)
#   - a renamed / extra / real-valued key     -> FAIL (ok=False) — an extra
#     key is a key the TEMPLATE was never supposed to carry; a real value is
#     the attack this gate exists for.
#
# EXIT CODES (house convention, anthology_registry.py / drive_adapter.py):
#   0  verified: all contract keys present, each a placeholder
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP-family guard refusal — token cannot READ custom values, or the
#      contract itself does not declare the custom values (a missing contract
#      section is NEVER a blind pass)
#   3  Convert and Flow API unreachable / upstream edge block (retryable;
#      the result is UNDETERMINED, never a fabricated all-present)
#   5  mismatch family — missing / extra / renamed key, or a real-looking
#      value where the template must hold a placeholder (never-a-real-token)
#
# RESULT SHAPE (exactly as the caller's contract states):
#   {"ok": bool, "found": [key...], "missing": [key...]}
#   Every key listed by key only. A value is NEVER printed, echoed, or
#   reflected in any surface.
#
# STDLIB ONLY (urllib + json via anthology_registry, the house adapter).
# Calls NO model. Every request carries the house browser User-Agent
# (CAF_BROWSER_UA) because services.leadconnectorhq.com is Cloudflare-fronted
# and 403s urllib's default UA at the WAF edge (CF 1010) before the request
# ever reaches Convert and Flow. Bare 401/403 is HELD (exit 3), NEVER
# mislabeled as a scope problem (scope-vs-edge-block discrimination, per
# anthology_registry.UpstreamBlockedError). Credentials resolved BY LABEL
# (SET / NOT SET only). Move in silence; nothing Anthropic in any runtime
# file; Convert and Flow naming in every client surface.
#
# IMPORT: imported by NAME as u02_modules.custom_values_check from the engine
# scripts (the package init is a pure namespace container). It is a MODULE,
# not a standalone CLI — the caller owns the operator surface.
# =============================================================================
"""custom_values_check.py -- check the four REPLACE-ME location custom values."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

# The never-a-real-token markers a custom value must carry. A value that is
# neither empty nor marker-labeled is REAL and REFUSED. This is the exact
# marker set live_verify_template.py uses for the same template gate.
PLACEHOLDER_MARKERS = ("REPLACE-ME", "replace-me", "<PUBLIC_HOSTNAME>")

# Exit codes (house convention).
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = 0, 1, 2, 3, 5


def is_placeholder(value: str) -> bool:
    """True when a custom-value payload is a clearly-labeled placeholder:
    empty or carrying a PLACEHOLDER_MARKERS marker. A real-looking value
    (e.g. https://... or Bearer ...) is NOT a placeholder. Only the fixed
    marker substrings are matched — the value itself is never printed."""
    v = (value or "").strip()
    if not v:
        return True
    return any(marker in v for marker in PLACEHOLDER_MARKERS)


def contract_custom_values(contract: dict) -> list:
    """The contract's required location custom values, contract-driven
    (never a hardcoded tuple). Empty when the contract declares none."""
    return [dict(cv) for cv in ((contract.get("location_custom_values") or {}).get("required") or [])
            if isinstance(cv, dict)]


def check_custom_values(client, location_id: str, contract: dict,
                        *, out=None, jsonout=None) -> int:
    """READ-ONLY check of the four REPLACE-ME location custom values.

    Every contract key must be present BY KEY on the location and hold a
    placeholder (never-a-real-token). Both key-set directions fail closed:
    missing keys FAIL, extra/renamed keys FAIL. Returns the exit code; on
    success (and mismatch) emits the result shape to ``jsonout``:
    {"ok": bool, "found": [key...], "missing": [key...]}. The JSON result
    NEVER carries a value — keys only. On STOP/HELD the outcome is written
    to ``out`` (stderr) and NO result JSON is emitted (the caller must not
    see a fabricated all-present).

    Exit mapping (fail-closed):
      0  all contract keys present as placeholders
      2  token cannot READ custom values (AF-AE-PIT-SCOPE family) or the
         contract declares no custom values (refused, never a blind pass)
      3  Convert and Flow unreachable / upstream edge block (UNDETERMINED,
         retryable)
      5  missing / extra / renamed key, or a real-looking value on the
         template location (never-a-real-token)
    """
    out = out or sys.stderr

    want_rows = contract_custom_values(contract)
    if not want_rows:
        reg._stop(out, "The snapshot contract declares NO location custom values.",
                  ["config/anthology-snapshot-contract.json location_custom_values.required "
                   "is empty or absent.",
                   "The four custom values (anthology_webhook_url / anthology_hook_secret / "
                   "producer / producer_email) are REQUIRED by the snapshot.",
                   "A missing contract section is NEVER a blind pass — fix the contract, "
                   "then re-run."])
        return EX_STOP
    want = [cv.get("key") for cv in want_rows if cv.get("key")]
    if not want or len(want) != len(want_rows):
        reg._stop(out, "The contract's custom-value list is malformed (a row lacks its key).",
                  ["config/anthology-snapshot-contract.json location_custom_values.required.",
                   "Fix the contract, then re-run."])
        return EX_STOP

    masked = reg._mask_location(location_id)
    try:
        live = client.list_custom_values(location_id)
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot READ location custom values.",
                  ["Location marker: %s" % masked,
                   "Grant the client's OWN location-scoped PIT the customValues READ scope.",
                   "AF-AE-PIT-SCOPE family: STOP, never a fabricated all-present."])
        return EX_STOP
    except reg.CafUnreachable as exc:
        # Includes UpstreamBlockedError (a Cloudflare/WAF edge 403 that did NOT
        # match a genuine scope-denial signature) — the result is UNDETERMINED,
        # never a clean pass, and never mislabeled as a scope problem.
        out.write("[custom-values] HELD (marker %s): %s. Retryable.\n" % (masked, exc))
        return EX_HELD

    got = {}
    for cv in live:
        k = cv.get("key") or cv.get("name") or ""
        if k:
            got[k] = cv

    want_set, got_set = set(want), set(got)
    missing = sorted(want_set - got_set)
    extra = sorted(got_set - want_set)
    found = sorted(want_set & got_set)

    # Real-valued placeholders: a template location must NEVER carry a real
    # hook URL or a real token. Refuse with a LOUD surface, naming the key
    # only (the value is never surfaced, never printed).
    real_keys = [k for k in found
                 if not is_placeholder((got[k] or {}).get("value") or "")]

    ok = (not missing and not extra and not real_keys)
    result = {"ok": ok, "found": found, "missing": missing}

    if jsonout is not None:
        json.dump(result, jsonout)
        jsonout.write("\n")

    if missing or extra or real_keys:
        # The FULL check result goes to the JSON surface (the caller's contract
        # shape); the operator surface names every deviation, keys only.
        if real_keys:
            out.write("[custom-values] NEVER-A-REAL-TOKEN REFUSED (marker %s): %d custom "
                      "value(s) hold a real-looking value on the TEMPLATE location: %s. "
                      "The template must carry REPLACE-ME placeholders only — replace the "
                      "value(s) with the placeholder and re-run.\n"
                      % (masked, len(real_keys), ", ".join(real_keys)))
        if missing:
            out.write("[custom-values] missing contract key(s): %s\n" % ", ".join(missing))
        if extra:
            out.write("[custom-values] unexpected custom value key(s) on the location: %s\n"
                      % ", ".join(extra))
        out.write("[custom-values] FAIL (marker %s): %d present, %d missing, %d unexpected, "
                  "%d real-valued. Fail-closed.\n"
                  % (masked, len(found), len(missing), len(extra), len(real_keys)))
        return EX_MISMATCH

    out.write("[custom-values] OK (marker %s): all %d contract custom value(s) present "
              "and holding placeholders.\n" % (masked, len(want)))
    return EX_OK
