#!/usr/bin/env python3
"""standing_gate.py -- fleet approval-gate client for the Anthology Engine (Skill 59).

WHAT THIS IS: a small, dependency-free helper that S0 (intake_router.py) calls, once
per intake webhook delivery, to ask the fleet-wide generic standing-check endpoint
(Item 1, n8n workflow `fleet-system-standing-check` / NIR2n0HM3mkGu6PH) whether THIS
box is approved for the anthology system, BEFORE any participant row is created, any
Drive folder is provisioned, or any model call is made. On a definite or suspected
refusal it also fires the shared rejection notifier (system-access-rejection-notify /
UqfhxcPqlB0aPgf5) so the client is told, on whichever channels reach them.

WHY THIS EXISTS: anthology_approved is a real column on every fleet_standing row and,
before this file, nothing in the anthology engine ever read it -- two clients marked
not-approved for the book project were not actually blocked from it.

CREDENTIAL MODEL (read this before touching the auth wiring): this endpoint's webhook
is protected by the SAME n8n httpHeaderAuth credential (id 8HTB7khC7fDcRVhN,
"fleetStandingCheck Header Auth") that already authenticates FOUR other surfaces --
system-access-rejection-notify, podcast-standing-check, the podcast publish gate, and
the legacy (currently inactive) fleet-standing-check roster gate -- confirmed by
directly reading each workflow's webhook node. The legacy roster gate's own box-side
values (`FLEET_STANDING_GATE_HEADER` / `FLEET_STANDING_GATE_SECRET`, propagated fleet-
wide by scripts/fleet-standing/propagate-fleet-standing-gate.sh) are therefore ALSO the
correct credential for THIS endpoint -- verified live 2026-07-31 with a real call
(`box_slug=blackceomacmini`, `system=anthology`) returning HTTP 200. No new secret needs
provisioning on any box that already has the legacy propagation; this file only adds a
new URL, never a new credential. `FLEET_STANDING_BOX_SLUG` (same 3-tier resolution
update-skills.sh's `fleet_standing_resolve_slug()` already uses: explicit env, then
openclaw.json's `env.vars`, then hostname) is reused as this box's own identity for the
SAME reason -- do not invent a second convention beside a working one.

FAIL CLOSED (the opposite of the legacy roster gate's deliberate fail-OPEN doctrine --
that asymmetry is intentional, not a copy/paste error: a book build spends real model
and media cost, so a false PROCEED is far more expensive than a false REFUSE, which
just holds one submission for a retry). Unreachable endpoint, non-200, a missing
credential, or a malformed/unexpected JSON body are ALL treated as NOT approved.

Never invents or hedges a reason. reason_code is passed through byte-for-byte from the
endpoint's own response ('standing' or 'not_enrolled'), or left '' when the gate itself
could not be evaluated (network/shape failure) -- an infra failure is never dressed up
as a specific business reason. This is safe to leave empty when notifying: the shared
notifier (system-access-rejection-notify) computes its OWN authoritative reason_code
independently from the same fleet_standing table (see its "Resolve Target + Plan
Channels" node) and only threads the caller's reason into its internal ledger note, so
an uncertain reason_code here can never cause the notifier to tell a client the wrong
thing.

SECRET HYGIENE: mirrors 58-podcast-production-engine/scripts/podbean_publish.sh's
proven idiom exactly -- the header value is placed into a curl config document that
rides to curl over STDIN (`curl -K -`), never in argv (no `ps` exposure) and never
written to disk. Never printed, logged, or returned by this module.
"""
import json
import os
import socket
import subprocess
from pathlib import Path

STANDING_CHECK_URL = os.environ.get(
    "FLEET_SYSTEM_STANDING_CHECK_URL",
    "https://main.blackceoautomations.com/webhook/system-standing-check",
)
NOTIFY_URL = os.environ.get(
    "FLEET_SYSTEM_ACCESS_REJECTION_NOTIFY_URL",
    "https://main.blackceoautomations.com/webhook/system-access-rejection-notify",
)
DEFAULT_HEADER_NAME = "X-Fleet-Standing-Secret"
DEFAULT_TIMEOUT = 10  # seconds; this gate must stay well inside S0's ack budget


# ---------------------------------------------------------------------------
# Box identity + credential resolution (reuses the legacy gate's propagated env,
# same convention as update-skills.sh's fleet_standing_resolve_slug()).
# ---------------------------------------------------------------------------
def _resolve_oc_json():
    explicit = os.environ.get("OC_JSON", "").strip()
    if explicit:
        return Path(explicit)
    home = Path.home() / ".openclaw" / "openclaw.json"
    if home.is_file():
        return home
    data = Path("/data/.openclaw/openclaw.json")
    if data.is_file():
        return data
    return home


def resolve_box_slug():
    """1. explicit env  2. openclaw.json env.vars  3. hostname -- IDENTICAL in spirit
    to update-skills.sh's fleet_standing_resolve_slug(), so a box already provisioned
    for the legacy gate needs nothing new to answer this question either."""
    explicit = os.environ.get("FLEET_STANDING_BOX_SLUG", "").strip()
    if explicit:
        return explicit
    oc_json = _resolve_oc_json()
    if oc_json.is_file():
        try:
            d = json.loads(oc_json.read_text(encoding="utf-8"))
            v = ((d.get("env") or {}).get("vars") or {}).get("FLEET_STANDING_BOX_SLUG", "")
            if v:
                return str(v).strip()
        except Exception:  # noqa: BLE001 - never let a config read crash the gate
            pass
    try:
        return (socket.gethostname() or "").split(".")[0]
    except Exception:  # noqa: BLE001
        return ""


def _resolve_header_auth():
    """Returns (header_name, header_value); value is '' when not configured. Reuses
    the legacy roster gate's already-propagated FLEET_STANDING_GATE_HEADER /
    FLEET_STANDING_GATE_SECRET -- the SAME n8n credential, proven live 2026-07-31.

    3-tier resolution (IDENTICAL in spirit to resolve_box_slug() above):
      1. explicit process env
      2. openclaw.json env.vars
      3. '' (absent -> fail closed by the caller, never this function)"""
    name = os.environ.get("FLEET_STANDING_GATE_HEADER", "").strip() or DEFAULT_HEADER_NAME
    value = os.environ.get("FLEET_STANDING_GATE_SECRET", "").strip()
    if not value:
        oc_json = _resolve_oc_json()
        if oc_json.is_file():
            try:
                d = json.loads(oc_json.read_text(encoding="utf-8"))
                v = ((d.get("env") or {}).get("vars") or {}).get("FLEET_STANDING_GATE_SECRET", "")
                if v:
                    value = str(v).strip()
            except Exception:  # noqa: BLE001 - never let a config read crash the gate
                pass
    return name, value


# ---------------------------------------------------------------------------
# Transport: curl config on stdin, never argv, never disk. One bounded retry on
# a transient failure only (network error / 5xx) -- mirrors podbean_publish.sh's
# proxy_request exactly; a deterministic 2xx/4xx reply is never retried.
# ---------------------------------------------------------------------------
def _curl_cfg_text(url, header_name, header_value):
    lines = [
        'request = "POST"',
        'url = "%s"' % url,
        "silent",
        "show-error",
        "location",
        "max-time = %d" % DEFAULT_TIMEOUT,
        'header = "Content-Type: application/json"',
    ]
    if header_name and header_value:
        lines.append('header = "%s: %s"' % (header_name, header_value))
    return "\n".join(lines) + "\n"


def _is_transient(code):
    return code in ("", "000") or (len(code) == 3 and code.startswith("5"))


def _curl_post_json(url, body_obj, header_name, header_value, timeout=DEFAULT_TIMEOUT):
    """POST body_obj as JSON; returns (body_text_or_None, http_code_or_None, err_or_None).
    Never raises. Never includes the header value in argv, stdout, or any exception text."""
    body_text = json.dumps(body_obj)
    cfg_text = _curl_cfg_text(url, header_name, header_value)
    attempt = 1
    while True:
        try:
            proc = subprocess.run(
                ["curl", "-K", "-", "--data-binary", body_text, "-w", "\n%{http_code}"],
                input=cfg_text, capture_output=True, text=True, timeout=timeout + 5,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return None, None, "curl invocation failed: %s" % type(exc).__name__
        out = proc.stdout or ""
        if "\n" not in out:
            return None, None, "malformed curl output (no status line)"
        body_part, _, code_part = out.rpartition("\n")
        code = code_part.strip()
        if _is_transient(code) and attempt < 2:
            attempt += 1
            continue
        return body_part, (code or None), None


# ---------------------------------------------------------------------------
# The gate itself.
# ---------------------------------------------------------------------------
def check_standing(system, timeout=DEFAULT_TIMEOUT):
    """Ask the fleet standing-check endpoint whether THIS box is approved for
    `system`. Returns a dict: {'approved': bool, 'reason_code': str, 'note': str}.

    FAIL CLOSED: 'approved' is False whenever the endpoint could not be reached,
    replied non-200, or replied with an unexpected shape -- exactly as if it had
    said 'not approved'. 'reason_code' is '' in that case (never guessed); 'note'
    is an operator-only diagnostic string, never secret, never shown to a client.
    """
    box_slug = resolve_box_slug()
    if not box_slug:
        return {"approved": False, "reason_code": "", "note": "box_slug could not be resolved"}
    hdr_name, hdr_val = _resolve_header_auth()
    if not hdr_val:
        return {"approved": False, "reason_code": "", "note": "FLEET_STANDING_GATE_SECRET not set on this box"}

    body_text, code, err = _curl_post_json(
        STANDING_CHECK_URL, {"system": system, "box_slug": box_slug}, hdr_name, hdr_val, timeout=timeout)
    if err:
        return {"approved": False, "reason_code": "", "note": err}
    if code != "200":
        return {"approved": False, "reason_code": "", "note": "standing-check returned HTTP %s" % code}
    try:
        parsed = json.loads(body_text) if body_text else None
    except (TypeError, ValueError):
        parsed = None
    if not isinstance(parsed, dict) or parsed.get("ok") is not True or "approved" not in parsed:
        return {"approved": False, "reason_code": "", "note": "unexpected response shape from standing-check"}

    approved = parsed.get("approved")
    reason_code = parsed.get("reason_code") or ""
    if approved is True:
        return {"approved": True, "reason_code": "", "note": "approved"}
    if reason_code in ("standing", "not_enrolled"):
        return {"approved": False, "reason_code": reason_code, "note": "not approved (%s)" % reason_code}
    # approved explicitly False but reason_code missing/unrecognized: refuse, but
    # never guess which of the two reasons it was.
    return {"approved": False, "reason_code": "", "note": "not approved (reason_code unrecognized)"}


def notify_rejection(system, box_slug, reason_code, client_label="", client_email="", timeout=DEFAULT_TIMEOUT):
    """Best-effort call to the shared rejection notifier. NEVER raises and never
    changes the caller's own refusal decision -- the notifier is strictly downstream
    of a decision already made, and it computes its own authoritative reason_code
    independently from fleet_standing (see its "Resolve Target + Plan Channels" node),
    so a '' reason_code here can never cause it to tell a client the wrong thing.
    Returns (http_code_or_None, err_or_None) for the caller's own operator-only log."""
    hdr_name, hdr_val = _resolve_header_auth()
    body = {"system": system, "box_slug": box_slug, "reason": reason_code or ""}
    if client_label:
        body["client_label"] = client_label
    if client_email:
        body["client_email"] = client_email
    _, code, err = _curl_post_json(NOTIFY_URL, body, hdr_name, hdr_val, timeout=timeout)
    return code, err


def self_test():
    """Offline, network-free contract checks."""
    assert DEFAULT_HEADER_NAME == "X-Fleet-Standing-Secret"
    n, v = _resolve_header_auth()
    assert isinstance(n, str) and n
    assert isinstance(v, str)
    assert _is_transient("000") and _is_transient("") and _is_transient("503")
    assert not _is_transient("200") and not _is_transient("403") and not _is_transient("404")
    cfg = _curl_cfg_text("https://example.invalid/x", "X-Test", "shh-secret-value")
    assert "shh-secret-value" not in repr(check_standing) and "shh-secret-value" in cfg, \
        "sanity: the secret belongs in the curl config text, nowhere else"
    assert 'header = "X-Test: shh-secret-value"' in cfg
    slug_before = os.environ.get("FLEET_STANDING_BOX_SLUG")
    os.environ["FLEET_STANDING_BOX_SLUG"] = "self-test-probe-box"
    try:
        assert resolve_box_slug() == "self-test-probe-box"
    finally:
        if slug_before is None:
            os.environ.pop("FLEET_STANDING_BOX_SLUG", None)
        else:
            os.environ["FLEET_STANDING_BOX_SLUG"] = slug_before
    print("standing_gate self-test: OK")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(self_test())
